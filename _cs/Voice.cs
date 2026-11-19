// ============================================================================
//  Voice.cs — 语音助手（讯飞）调试能力（融合自「语音助手工具.exe」）
//
//  来源：Downloads\语音助手工具.exe（Python 3.13 + Tkinter / PyInstaller 打包）
//        逆向还原出 src/util/AndroidAdbUtil.py 的全部 adb 调用逻辑，
//        本节按本项目风格重写，不引入任何原工具依赖。
//
//  为什么不做成 :send 的子参数：
//        :send 的 URI 前缀在 ini 里硬编码、BuildAmCmd 只认单一前缀；
//        语音侧需要 3 种 URI（vr:// / sr:// / sr://+local）与 2 个可选参数
//        （voiceArea / mode），且 :send 的批量发送能力必须原样保留。
//        独立成模块，边界干净，互不牵扯。
//
//  URI 家族（车道语音框架）
//    vr://com.iflytek.autofly.vr/interaction/start?type=N[&canSleep=false]
//        -> 唤醒。type 的语义随项目/APK 版本不同，故两条都留、命令区分。
//    sr://syncore.vpa.sr/test?text=<文本>[&voiceArea=N][&mode=local]
//        -> 识别。文本须 URL 编码；voiceArea 指定音区；mode=local 走离线。
//    am startservice -a com.iflytek.auto.speechclient.sdk.TextSemanticService
//        -> 旧版文本语义（--es text/msgType/package），作为兜底保留。
//
//  音区映射（AH8 0626apk 起支持）
//        0 主驾  1 副驾  2 二排左  3 二排右  4 三排左  5 三排右
//
//  C# 5.0 兼容：不用 out var / 局部函数 / => 表达式体 / $"..."。
// ============================================================================
using System;
using System.Collections.Generic;
using System.Text;

namespace AdbLogExport
{
    internal static partial class App
    {
        // ==================== 一、可配置项（ini 的 vr_* 段）====================
        // 唤醒 type：1 = 新文档写法；99 = 原工具实测写法。
        // 两个值在不同 APK 上行为不同（99 附带 canSleep=false），所以都在。
        internal static string VR_WAKE_TYPE = "1";
        internal static string VR_WAKE_TYPE_ALT = "99";

        // 语助应用包名（原工具 Constants.SpeechHmiPackageName）
        internal static string VR_PKG = "com.iflytek.cutefly.speechclient.hmi";

        // URI 模板：只在 ini 里改这两行就能换接口版本
        internal static string VR_VR_URI = "vr://com.iflytek.autofly.vr/interaction/start";
        internal static string VR_SR_URI = "sr://syncore.vpa.sr/test?text=";

        // 文本上限：原工具限 50 字（limit_text_length），超过会被设备侧截断
        internal static int VR_TEXT_MAX = 50;

        // 旧版文本语义服务
        internal static string VR_TS_SERVICE = "com.iflytek.auto.speechclient.sdk.TextSemanticService";
        internal static string VR_TS_PACKAGE = "com.example.package";

        // 语音输出（TTS）服务 action（用户提供：加文字即可出声）
        internal static string VR_TTS_SERVICE = "com.iflytek.autofly.TtsService";

        // 调试页 Activity 的**类相对名**。
        //
        // 【bug 修复 1】原工具把类名整串直接拼在包名后面：
        //     adb shell am start -n com.iflytek...hmi/com.iflytek...hmi.SettingDebugActivity
        // 这是**错的**。am 的 -n 要的是 "包名/类名"，斜杠右边以 . 开头表示
        // 相对包名（am 自己补全）。原工具把完整类名再拼一次包名，成了
        // `pkg/com.pkg.Cls` 的双包名写法，多数 ROM 上 ActivityNotFound。
        // 改成标准写法 pkg/.Cls，由 VrComponent() 负责拼装。
        //
        // 【bug 修复 2】相对名不能凭猜。上面改成 .SettingDebugActivity 之后，
        // 真机实测报：
        //     Error type 3
        //     Error: Activity class {...hmi/com.iflytek...hmi.SettingDebugActivity} does not exist
        // 因为真实类名带完整子包路径。下面的名字是从设备上 dumpsys 出来的：
        //     com.syncore.speech.core.business.debugpages.setting.SettingDebugActivity
        //     com.syncore.speech.core.business.debugpages.textsemantic.DebugTextExecuteSemanticActivity
        // 这里存**完整类名**（不带前导点），由 VrComponent 拼成 pkg/完整类名。
        internal static string VR_ACT_SETTING =
            "com.syncore.speech.core.business.debugpages.setting.SettingDebugActivity";
        internal static string VR_ACT_TEXTDBG =
            "com.syncore.speech.core.business.debugpages.textsemantic.DebugTextExecuteSemanticActivity";

        // ==================== 二、音区表 ====================
        // 顺序即 voiceArea 取值，不得调整
        private static readonly string[] VR_AREAS = new string[]
        {
            "主驾", "副驾", "二排左", "二排右", "三排左", "三排右"
        };

        private static readonly string[] VR_AREA_KEYS = new string[]
        {
            "driver", "passenger", "rear2l", "rear2r", "rear3l", "rear3r"
        };

        // 把 -a 后面的值解析成 0~5；失败返回 -1
        // 认三种写法：数字 "1" / 中文 "副驾" / 英文别名 "passenger"
        private static int ParseArea(string s)
        {
            if (string.IsNullOrEmpty(s)) return -1;
            string t = s.Trim();

            int n;
            if (int.TryParse(t, out n)) return (n >= 0 && n <= 5) ? n : -1;

            for (int i = 0; i < VR_AREAS.Length; i++)
            {
                if (t == VR_AREAS[i]) return i;
            }
            string low = t.ToLowerInvariant();
            for (int i = 0; i < VR_AREA_KEYS.Length; i++)
            {
                if (low == VR_AREA_KEYS[i]) return i;
            }
            return -1;
        }

        private static string AreaName(int idx)
        {
            if (idx >= 0 && idx < VR_AREAS.Length) return VR_AREAS[idx];
            return "?";
        }

        // ==================== 三、参数解析 ====================
        // 从参数串里摘出 -a <音区> 与 -l/--local，剩下的原文就是待识别文本。
        // 这样 :vr sr 打开车窗 -a 1 与 :vr sr -a 1 打开车窗 都成立。
        //
        // areaBad：用户写了 -a 但值不合法（如 -a 9 / -a 中排）。
        // 【bug 修复】早先把非法值当普通文本保留，于是
        //     :vr sr 打开车窗 -a 9
        // 会把 "-a 9" 一起发出去，用户以为指定了音区、实际念出了错误文本。
        // 这类静默走样比报错更危险，改为显式报错。
        private static string VrStripArgs(string argRaw, out int area, out bool local,
                                          out string areaBad)
        {
            area = -1;
            local = false;
            areaBad = "";
            if (string.IsNullOrEmpty(argRaw)) return "";

            List<string> toks = SplitTokens(argRaw);
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < toks.Count; i++)
            {
                string t = toks[i];
                string low = t.ToLowerInvariant();

                // -a 3 / -a 副驾 / --area 副驾
                if (low == "-a" || low == "--area" || low == "-area")
                {
                    if (i + 1 < toks.Count)
                    {
                        int a = ParseArea(toks[i + 1]);
                        if (a >= 0) { area = a; i++; continue; }
                        areaBad = toks[i + 1];
                        i++;
                        continue;
                    }
                    // -a 后面没跟值
                    areaBad = "（缺少值）";
                    continue;
                }

                // -a1 连写
                if (low.Length > 2 && low.Substring(0, 2) == "-a" && char.IsDigit(low[2]))
                {
                    int a = ParseArea(low.Substring(2));
                    if (a >= 0) { area = a; continue; }
                    areaBad = low.Substring(2);
                    continue;
                }

                // -l / --local / -local：离线模式
                //
                // 【bug 修复】原来这里还认裸词 "local"，导致
                //     :vr sr 打开 local 模式
                // 里的 "local" 被当成开关吞掉，真正发的文本变成 "打开 模式"。
                // 语音指令文本里出现 local 是完全可能的（"打开本地音乐"的拼音输入
                // 习惯、或英文媒体名），不能当保留字。裸词只保留 "-" 开头的写法。
                if (low == "-l" || low == "--local" || low == "-local")
                {
                    local = true;
                    continue;
                }

                if (sb.Length > 0) sb.Append(' ');
                sb.Append(t);
            }
            return sb.ToString().Trim();
        }

        // 两参数版本：不需要关心音区合法性时（自检 / 旧调用）用
        private static string VrStripArgs(string argRaw, out int area, out bool local)
        {
            string bad;
            return VrStripArgs(argRaw, out area, out local, out bad);
        }

        // 按空白切词，但保留引号内的空格（"打开 车窗" 算一个词）
        private static List<string> SplitTokens(string s)
        {
            List<string> list = new List<string>();
            if (string.IsNullOrEmpty(s)) return list;

            StringBuilder cur = new StringBuilder();
            char quote = '\0';
            for (int i = 0; i < s.Length; i++)
            {
                char c = s[i];
                if (quote != '\0')
                {
                    if (c == quote) quote = '\0';
                    else cur.Append(c);
                    continue;
                }
                if (c == '"' || c == '\'') { quote = c; continue; }
                if (c == ' ' || c == '\t')
                {
                    if (cur.Length > 0) { list.Add(cur.ToString()); cur.Length = 0; }
                    continue;
                }
                cur.Append(c);
            }
            if (cur.Length > 0) list.Add(cur.ToString());
            return list;
        }

        // ==================== 四、:vr 路由 ====================
        internal static void RouteVr(string argRaw)
        {
            string a = (argRaw == null) ? "" : argRaw.Trim();
            if (a.Length == 0) { VrHelp(); OkLocal(); return; }

            string sub;
            string rest;
            SplitLine(a, out sub, out rest);
            string n = sub.ToLowerInvariant();

            if (n == "wake" || n == "w") { VrWake(rest); return; }
            if (n == "sr" || n == "rec" || n == "say") { VrSr(rest); return; }
            if (n == "local" || n == "off") { VrLocal(rest); return; }
            if (n == "ts" || n == "semantic") { VrTextSemantic(rest); return; }
            if (n == "tts" || n == "output" || n == "speak") { VrTts(rest); return; }
            if (n == "ver" || n == "version") { VrVersion(); return; }
            if (n == "restart" || n == "rs") { VrRestart(); return; }
            if (n == "reboot" || n == "rb")
            {
                if (OFFLINE) { Warn("设备未连接"); Hint("输入 :r 重连"); return; }
                // 【安全护栏】重车机是全局破坏性操作，误触代价很大
                // （测试中途重启会丢掉现场、断掉其他同事的连接）。
                // 因此必须显式带 -y 才执行，裸 :vr reboot 只做提示。
                if (!VrConfirmNo(rest, "重启车机", ":vr reboot -y"))
                {
                    Warn("重启车机需要确认");
                    Hint("确认后执行：:vr reboot -y");
                    Hint("（会立即重启整台车机，正在跑的其他测试会被打断）");
                    return;
                }
                Info("正在重启车机…");
                VrAdb(new List<string> { "reboot" }, "重启指令已下发");
                return;
            }
            if (n == "un" || n == "uninstall") { VrUninstall(rest); return; }
            if (n == "set" || n == "settings") { VrOpenAct(VR_ACT_SETTING, "语音后台设置"); return; }
            if (n == "dbg" || n == "debug") { VrOpenAct(VR_ACT_TEXTDBG, "文本语义调试页"); return; }
            if (n == "area" || n == "areas") { VrAreaTable(); OkLocal(); return; }
            if (n == "log" || n == "logs") { VrLog(rest); OkLocal(); return; }
            if (n == "h" || n == "help" || n == "?") { VrHelp(); OkLocal(); return; }

            // 兜底：:vr 后面直接跟文本，等价于 :vr sr 文本（最省事的写法）
            VrSr(a);
        }

        // ==================== 五、唤醒 ====================
        // :vr wake          用 ini 的 vr_wake_type（默认 1）
        // :vr wake 99       用原工具那套 type=99&canSleep=false
        private static void VrWake(string rest)
        {
            if (OFFLINE) { Warn("设备未连接，无法唤醒"); Hint("输入 :r 重连"); return; }

            // 2026-11-19：支持 -a <音区>，例如 `:vr wake -a 副驾` / `:vr wake 1 -a 1`
            int area; bool _localM; string areaBad;
            string t = VrStripArgs(rest ?? "", out area, out _localM, out areaBad).Trim();
            if (areaBad.Length > 0)
            {
                Fail("音区不合法：" + areaBad);
                Hint("可用：-a 0~5 或 -a 主驾/副驾/二排左/二排右/三排左/三排右");
                return;
            }
            string type = VR_WAKE_TYPE;
            bool withSleep = false;

            if (t.Length > 0)
            {
                if (t == "99" || t == "alt" || t == "old")
                {
                    type = VR_WAKE_TYPE_ALT;
                    withSleep = true;
                }
                else
                {
                    type = t;   // 允许填任意 type 值，方便新项目试
                }
            }

            string uri = VrBuildWakeUri(type, withSleep, area);

            string cmd = VrBuildAmCmd(uri);
            string tail = (area >= 0) ? "，音区=" + AreaName(area) : "";
            if (VrAdb(new List<string> { "shell", cmd }, "唤醒指令已下发（type=" + type + tail + "）"))
            {
                Hint("URI：" + UrlDecodeForDisplay(uri));
                if (area >= 0)
                    Hint("提示：该参数仅在 AH8 项目（0626apk 起）生效；换音区前先让上一个音区休眠");
            }
        }

        // ==================== 六、识别（主入口）====================
        // :vr sr 打开车窗              主驾
        // :vr sr 打开车窗 -a 1         副驾
        // :vr sr -a 2 打开车窗         二排左
        private static void VrSr(string rest)
        {
            int area;
            bool local;
            string areaBad;
            string text = VrStripArgs(rest, out area, out local, out areaBad);

            if (areaBad.Length > 0)
            {
                Fail("音区值无效：" + areaBad);
                Hint("可用 0~5，或 主驾/副驾/二排左/二排右/三排左/三排右");
                Hint("输入 :vr area 看对照表");
                return;
            }
            if (text.Length == 0)
            {
                Fail("缺少要识别的文本");
                Hint("例：:vr sr 打开车窗 -a 1");
                return;
            }
            if (local) { VrSrLocal(text, area); return; }

            VrSendSr(text, area, false);
        }

        // :vr local 打开车门 [ -a N ] —— AH8 断网识别
        private static void VrLocal(string rest)
        {
            int area;
            bool flag;
            string areaBad;
            string text = VrStripArgs(rest, out area, out flag, out areaBad);
            if (areaBad.Length > 0)
            {
                Fail("音区值无效：" + areaBad);
                Hint("可用 0~5，或 主驾/副驾/二排左/二排右/三排左/三排右");
                return;
            }
            if (text.Length == 0)
            {
                Fail("缺少要识别的文本");
                Hint("例：:vr local 打开车门");
                return;
            }
            VrSrLocal(text, area);
        }

        private static void VrSrLocal(string text, int area)
        {
            VrSendSr(text, area, true);
        }

        // 统一构造并下发 sr:// 意图
        private static void VrSendSr(string text, int area, bool local)
        {
            if (OFFLINE) { Warn("设备未连接，无法发送"); Hint("输入 :r 重连"); return; }

            string raw = text.Trim();
            string clean = VrTextTrim(raw);
            bool clipped = clean.Length < raw.Length;

            string uri = VrBuildUri(clean, area, local);

            // 整条 -d 用双引号包住，避免本地 cmd 把 & 当管道分隔符
            string cmd = VrBuildAmCmd(uri);

            StringBuilder label = new StringBuilder();
            label.Append("识别已下发：").Append(Clip(clean, 24));
            if (area >= 0) label.Append("  [").Append(AreaName(area)).Append("(").Append(area).Append(")]");
            if (local) label.Append("  [断网模式]");

            if (VrAdb(new List<string> { "shell", cmd }, label.ToString()))
            {
                if (clipped) Hint("文本超过 " + VR_TEXT_MAX + " 字，已截断（ini 的 vr_text_max 可改）");
                Hint("URI：" + uri);
            }
        }

        // ==================== 六点五、URI 构造（供自检直接调用）====================
        // 生产与自检共用这一份，避免"自检测的是副本、实际拼的是另一份"。
        //
        // 【bug 修复·重要】引号只能有一层。
        //
        // 早先这里写成 uri.Append("'&'voiceArea=")，理由是"设备侧 shell 要用单引号
        // 包住 & 才是字面量"。这个结论只在 **URI 外层不加引号** 时成立（原 Python
        // 工具就是把整条 -d 裸着拼的）。但我们这一版把整条 URI 用双引号包住了：
        //     am startservice -a ... -d "sr://...text=abc'&'voiceArea=1"
        // 而 sh 只在 **未加引号** 的位置把 ' 当引号、把 & 当控制符；进到双引号里
        // 之后，单引号和 & 都退化成普通字符。于是设备真正收到的 argv 是：
        //     sr://...text=abc'&'voiceArea=1
        // 结果：text 尾巴多一个 '，voiceArea 的值变成 "1'" 而解析失败。
        //
        // 正确写法：既然整条被双引号包住，& 天然是字面量，直接写裸 & 即可。
        // 已用伪造 am 脚本实测 argv 确认（见自检锚点）。
        internal static string VrBuildUri(string text, int area, bool local)
        {
            StringBuilder uri = new StringBuilder();
            uri.Append(VR_SR_URI);
            uri.Append(Util.EscapeData(text));
            if (area >= 0) uri.Append("&voiceArea=").Append(area);
            if (local) uri.Append("&mode=local");
            return uri.ToString();
        }

        internal static string VrBuildWakeUri(string type, bool withSleep, int area = -1)
        {
            string uri = VR_VR_URI + "?type=" + type;
            if (withSleep) uri += "&canSleep=false";
            // 2026-11-19：按音区唤醒。voiceArea 与识别侧同一套取值（0主驾 1副驾
            // 2二排左 3二排右 4三排左 5三排右），复用 VR_AREAS 的顺序。
            // area<0 时不拼任何东西 —— 旧调用方（含自检）行为逐字节不变。
            if (area >= 0) uri += "&voiceArea=" + area;
            return uri;
        }

        // 构造 am 命令：子命令与 action 都取 ini 配置（AM_CMD / ACTION），
        // 与 :send 保持一致 —— 遇到 "not allowed to start service" 时，
        // 用户把 ini 的 am_cmd 改成 start-foreground-service，:vr 也跟着变。
        // 之前这里是硬编码 startservice + VIEW，改了 ini 对 :vr 无效。
        internal static string VrBuildAmCmd(string uri)
        {
            StringBuilder sb = new StringBuilder();
            sb.Append("am ");
            sb.Append(AM_CMD);
            sb.Append(" -a ");
            sb.Append(ACTION);
            sb.Append(" -d \"");
            sb.Append(uri);
            sb.Append('"');
            return sb.ToString();
        }

        // 按 ini 的 vr_text_max 截断（0 或负数 = 不限制）
        // 注意：不能用 Clip()——它尾部会补一个 "…"，长度就变成 max+1 了。
        // 这里是发往设备的真实文本，必须严格 <= 上限，且不能带省略号。
        internal static string VrTextTrim(string text)
        {
            if (text == null) return "";
            string t = text.Trim();
            if (VR_TEXT_MAX <= 0) return t;
            if (t.Length <= VR_TEXT_MAX) return t;
            int n = VR_TEXT_MAX;
            // 别把代理对（emoji 等）切成半个，否则 URI 编码出来是坏字符
            if (n > 0 && char.IsHighSurrogate(t[n - 1])) n--;
            return t.Substring(0, n);
        }

        // ==================== 七、旧版文本语义 API ====================
        // :vr ts 打开车窗
        //
        // 与 sr:// 的差别：这条走旧的 action，不带 -d URI，文本用 --es 传。
        // 本机实测：即使包没装，am 也会先打 "Starting service:" 再报
        //   Error: Not found; no service started.
        // 所以不能只看 stdout 有没有 "Starting"，必须让 VrLooksBad 判失败
        // （marks 里已有 "error " / "not found"，这条能被抓住）。
        private static void VrTextSemantic(string rest)
        {
            if (OFFLINE) { Warn("设备未连接"); Hint("输入 :r 重连"); return; }

            string text = (rest == null) ? "" : rest.Trim();
            if (text.Length == 0) { Fail("缺少要识别的文本"); Hint("例：:vr ts 打开车窗"); return; }

            StringBuilder cmd = new StringBuilder();
            cmd.Append("am ").Append(AM_CMD);
            cmd.Append(" -a ").Append(VR_TS_SERVICE);
            cmd.Append(" --es 'text' '").Append(VrShellSafe(text)).Append('\'');
            cmd.Append(" --es 'msgType' '1'");
            cmd.Append(" --es 'package' '").Append(VrShellSafe(VR_TS_PACKAGE)).Append('\'');

            VrAdb(new List<string> { "shell", cmd.ToString() }, "文本语义已下发（旧 API）：" + Clip(text, 24));
        }

        // 语音日志：只保留两类行（用户 2026-11-14 要求）
        //   1) 识别结果：... 讲话内容=今天的天气, 套件事件ID=90008, ...
        //   2) 播报回执：【TTS】收到播放任务 内容=..., 来源=..., uuid=...
        // 其余 logcat 行一律丢弃 —— 语音场景噪音太大，只看这两类才能核对。
        // 为什么在本地过滤而不是设备侧 grep：
        //   设备侧 grep 中文模式串在多语言 ROM 上容易匹配不到，本地过滤更稳。
        internal static void VrLog(string arg)
        {
            // 用法：:vr log            只要 讲话内容= / 【TTS】 两类
            //       :vr log -a         放宽为所有含 TTS 的行（两类行缺失时用它排查）
            //       :vr log 天气        再按关键字过滤
            string a = (arg == null) ? "" : arg.Trim();
            bool allMode = a.IndexOf("-a", StringComparison.Ordinal) >= 0;
            string kw = a.Replace("-a", "").Trim();
            if (OFFLINE)
            {
                Warn("设备未连接");
                Hint("输入 :r 重连");
                return;
            }

            string o = "";
            string e = "";
            // -d 取一次快照；-v time 保留时间戳便于对齐
            ShellCall(CUR, "logcat -d -v time 2>/dev/null | tail -n 4000", out o, out e);
            string all = o + "\n" + e;

            string[] lines = all.Split('\n');
            int shown = 0;
            int total = 0;

            Console.WriteLine();
            UseDim();
            Console.WriteLine("  语音日志（只显示 讲话内容= / 【TTS】）");
            UseDefault();

            for (int i = 0; i < lines.Length; i++)
            {
                string line = lines[i].TrimEnd('\r');
                if (line.Length == 0) continue;

                bool want = line.IndexOf("讲话内容=", StringComparison.Ordinal) >= 0
                            || line.IndexOf("【TTS】", StringComparison.Ordinal) >= 0
                            || line.IndexOf("播放任务", StringComparison.Ordinal) >= 0;
                if (allMode) want = line.IndexOf("TTS", StringComparison.OrdinalIgnoreCase) >= 0;
                if (want && kw.Length > 0) want = line.IndexOf(kw, StringComparison.Ordinal) >= 0;
                if (!want) continue;

                total++;
                if (shown >= 60) continue;      // 上限，避免刷屏
                shown++;

                if (line.IndexOf("【TTS】", StringComparison.Ordinal) >= 0) UsePath();
                else UseOk();
                Console.WriteLine("  " + line);
                UseDefault();
            }

            Console.WriteLine();
            if (total == 0)
            {
                Warn("没有匹配的语音日志");
                Hint("先发一条语音指令，再执行一次 :vr log");
                Hint("若仍为空，用 :vr log -a 看所有 TTS 相关行（可能 tag 与预期不同）");

                // 给 3 行 TTS 样本，便于确认实际日志长什么样
                int shown2 = 0;
                for (int i = lines.Length - 1; i >= 0 && shown2 < 3; i--)
                {
                    string l2 = lines[i].Trim();
                    if (l2.Length == 0) continue;
                    if (l2.IndexOf("TTS", StringComparison.OrdinalIgnoreCase) < 0) continue;
                    UseDim();
                    Console.WriteLine("  [样本] " + l2);
                    UseDefault();
                    shown2++;
                }
            }
            else
            {
                Info("共匹配 " + total + " 行" + (total > shown ? "（只显示前 " + shown + " 行）" : ""));
            }
            CMD_OK = true;
        }

        // ==================== 语音输出（TTS）====================
        // 需求（2026-11-12）：语音助手增加「语音输出」模式，走讯飞 TTS 服务。
        //   am startservice -a com.iflytek.autofly.TtsService --es text '<文本>'
        // 不关联音区（voiceArea），只把文本念出来。
        // 把 URI 里的 %XX（UTF-8）还原成中文，便于肉眼核对。
        // 只影响显示，真正下发的仍是原始 uri。
        internal static string UrlDecodeForDisplay(string s)
        {
            if (string.IsNullOrEmpty(s) || s.IndexOf('%') < 0) return s;

            StringBuilder sb = new StringBuilder(s.Length);
            int i = 0;
            while (i < s.Length)
            {
                if (s[i] == '%' && i + 2 < s.Length
                    && IsHex(s[i + 1]) && IsHex(s[i + 2]))
                {
                    List<byte> buf = new List<byte>();
                    while (i + 2 < s.Length && s[i] == '%' && IsHex(s[i + 1]) && IsHex(s[i + 2]))
                    {
                        buf.Add((byte)Convert.ToInt32(s.Substring(i + 1, 2), 16));
                        i += 3;
                    }
                    try { sb.Append(Encoding.UTF8.GetString(buf.ToArray())); }
                    catch { sb.Append("<decode-error>"); }
                }
                else
                {
                    sb.Append(s[i]);
                    i++;
                }
            }
            return sb.ToString();
        }

        private static bool IsHex(char c)
        {
            return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
        }

        internal static string VrBuildTtsCmd(string text)
        {
            return "am " + AM_CMD + " -a " + VR_TTS_SERVICE
                 + " --es 'text' '" + VrShellSafe(text) + "'";
        }

        private static void VrTts(string rest)
        {
            if (OFFLINE) { Warn("设备未连接"); Hint("输入 :r 重连"); return; }

            string text = (rest == null) ? "" : rest.Trim();
            if (text.Length == 0) { Fail("缺少要播报的文本"); Hint("例：:vr tts 你好"); return; }

            string cmd = VrBuildTtsCmd(text);
            VrAdb(new List<string> { "shell", cmd }, "语音输出已下发：" + Clip(text, 24));
        }

        // 把文本塞进单引号里之前，先去掉单引号本身；
        // 顺便挡掉 $(...) 与反引号 —— 否则文本里的命令替换会被设备 shell 执行。
        // 语音识别文本通常不含这些，但 :vr ts 是"旧 API 兜底"，输入来源不可控。
        internal static string VrShellSafe(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            return s.Replace("'", "").Replace("`", "").Replace("$(", "");
        }

        // ==================== 八、版本号 ====================
        // 原工具用的是 Windows 的 findstr，把设备命令当本地命令跑了 —— 这里改成设备侧 grep
        private static void VrVersion()
        {
            if (OFFLINE) { Warn("设备未连接，无法查询版本"); Hint("输入 :r 重连"); return; }

            string o = "";
            string e = "";
            int rc = ShellCall(CUR, "dumpsys package " + VR_PKG + " 2>&1 | grep -E 'versionName|versionCode'", out o, out e);
            string all = (o + e).Trim();

            if (rc != 0 || all.Length == 0)
            {
                CMD_OK = false;
                // 包没装时 dumpsys 返回空，给一条更准的提示
                string chk = "";
                string chkE = "";
                ShellCall(CUR, "pm list packages " + VR_PKG, out chk, out chkE);
                if (chk.Trim().Length == 0)
                {
                    Fail("语助应用未安装：" + VR_PKG);
                    Hint("ini 的 vr_pkg 可改包名");
                }
                else
                {
                    Fail("版本号查询失败" + (all.Length > 0 ? "：" + FirstLine(all) : ""));
                }
                return;
            }

            CMD_OK = true;
            string vn = "";
            string vc = "";
            string[] lines = all.Split('\n');
            for (int i = 0; i < lines.Length; i++)
            {
                string t = lines[i].Trim();
                int p = t.IndexOf("versionName=", StringComparison.Ordinal);
                if (p >= 0 && vn.Length == 0) vn = t.Substring(p + 12).Trim();
                int q = t.IndexOf("versionCode=", StringComparison.Ordinal);
                if (q >= 0 && vc.Length == 0)
                {
                    vc = t.Substring(q + 12).Trim();
                    int sp = vc.IndexOf(' ');
                    if (sp > 0) vc = vc.Substring(0, sp);
                }
            }

            UseOk();
            if (vn.Length > 0) Console.WriteLine("  语助版本  " + vn + (vc.Length > 0 ? "   (" + vc + ")" : ""));
            else Console.WriteLine("  " + all);
            UseDefault();
        }

        // ==================== 九、重启语助进程 ====================
        private static void VrRestart()
        {
            if (OFFLINE) { Warn("设备未连接"); Hint("输入 :r 重连"); return; }
            VrAdb(new List<string> { "shell", "am force-stop " + VR_PKG }, "语助进程已强制停止（再次语音可拉起）");
        }

        // ==================== 十、卸载语助 ====================
        // 【安全护栏】卸载生产语助是这台车上最危险的操作之一：
        // 卸掉之后语音全废，且普通 adb 装不回来（需要对应 APK + 签名）。
        // 所以必须带 -y 才执行，且执行前把版本号打出来，方便事后找回同一个包。
        private static void VrUninstall(string rest)
        {
            if (OFFLINE) { Warn("设备未连接"); Hint("输入 :r 重连"); return; }

            if (!VrConfirmNo(rest, "卸载 " + VR_PKG, ":vr un -y"))
            {
                Warn("卸载语助需要确认");
                Hint("确认后执行：:vr un -y");
                Hint("（卸载后语音功能全废，且需要对应 APK 才能装回）");
                return;
            }

            // 卸载前先留一份版本号，万一需要恢复能对上是哪个包
            string o = "";
            string e = "";
            ShellCall(CUR, "dumpsys package " + VR_PKG + " 2>&1 | grep -m1 versionName", out o, out e);
            string ver = FirstLine((o + e).Trim());
            if (ver.Length > 0) Info("待卸载版本：" + ver.Replace("versionName=", "").Trim());

            Info("正在卸载 " + VR_PKG + " …");
            VrAdb(new List<string> { "uninstall", VR_PKG }, "卸载成功");
        }

        // 破坏性操作确认：参数里带 -y / --yes 才放行
        // 单独抽出来，便于自检验证"不带 -y 一定不放行"
        internal static bool VrConfirmNo(string rest, string what, string example)
        {
            if (string.IsNullOrEmpty(rest)) return false;
            List<string> toks = SplitTokens(rest);
            for (int i = 0; i < toks.Count; i++)
            {
                string low = toks[i].ToLowerInvariant();
                if (low == "-y" || low == "--yes" || low == "-yes") return true;
            }
            return false;
        }

        // ==================== 十一、打开调试页 ====================
        // actRel 传类相对名（以 . 开头），这里补上「包名/」前缀，拼成 am -n 的
        // 标准 "pkg/.Cls" 形式。组合逻辑单独抽成 VrComponent() 便于自检。
        private static void VrOpenAct(string actRel, string label)
        {
            if (OFFLINE) { Warn("设备未连接"); Hint("输入 :r 重连"); return; }
            VrAdb(new List<string> { "shell", "am start -n " + VrComponent(actRel) }, "已打开" + label);
        }

        // "pkg/Cls" —— am -n 的标准写法。
        //
        // 传进来的 actRel 有三种形态，分别处理（都用真机验证过）：
        //   1) 含 "/"         已经是完整组件，原样返回
        //   2) 以 "." 开头    相对名，直接 pkg/+a；am 会把前导点展开成 pkg.Cls
        //   3) 完整类名       必须写成 pkg/+a（**不能**变成 pkg/.Cls）
        //
        // 第 3 种是踩过的坑：写成 pkg/.com.syncore... 时 am 会展开成
        // pkg.com.syncore...，等于又拼了一层包名，必然 ActivityNotFound。
        internal static string VrComponent(string actRel)
        {
            string a = (actRel == null) ? "" : actRel.Trim();
            if (a.Length == 0) return VR_PKG;
            if (a[0] == '/') a = a.Substring(1);
            // 已经是完整组件（含 /）就不重复拼
            if (a.IndexOf('/') >= 0) return a;
            // 以 . 开头：相对包名，am 自己展开
            if (a[0] == '.') return VR_PKG + "/" + a;
            // 完整类名（含包名点）或裸类名：都按 pkg/Cls 拼
            return VR_PKG + "/" + a;
        }

        // ==================== 十二、音区对照表 ====================
        private static void VrAreaTable()
        {
            Console.WriteLine();
            Console.WriteLine("  voiceArea 对照（-a 后面可填数字 / 中文 / 英文）");
            for (int i = 0; i < VR_AREAS.Length; i++)
            {
                Console.WriteLine("    " + i + "  " + VR_AREAS[i] + "    -a " + i + "  或  -a " + VR_AREA_KEYS[i]);
            }
            Console.WriteLine();
            UseDim();
            Console.WriteLine("  仅 AH8 项目（0626apk 起）支持指定音区；其他项目忽略该参数");
            Console.WriteLine("  换方位前请先休眠当前方位（原工具提示）");
            UseDefault();
            Console.WriteLine();
        }

        // ==================== 十三、日志抓取提示 ====================
        // 原工具有独立的 logcat 落盘窗口；本项目已有更完整的 hci 导出与
        // :sid 实时过滤，这里只做引导，不重复造轮子。
        private static void VrLogHint()
        {
            Console.WriteLine();
            Console.WriteLine("  语音日志相关，本项目已有更合适的入口：");
            Console.WriteLine("    :sid            实时过滤日志 20009");
            Console.WriteLine("    :hci            导出 btsnoop 蓝牙日志到桌面 logcat");
            Console.WriteLine("    :crash          崩溃缓冲区");
            Console.WriteLine("    logcat -d | grep 语助包名   自定义过滤");
            Console.WriteLine();
        }

        // ==================== 十四、帮助 ====================
        private static void VrHelp()
        {
            Console.WriteLine();
            Separator("-");
            Console.WriteLine("  语音助手调试（:vr 命名空间）");
            Console.WriteLine();
            Console.WriteLine("    唤醒 / 识别");
            Console.WriteLine("      :vr wake               主驾唤醒（type 取 ini 的 vr_wake_type）");
            Console.WriteLine("      :vr wake 99            用原工具参数 type=99&canSleep=false");
            Console.WriteLine("      :vr sr 打开车窗         主驾识别");
            Console.WriteLine("      :vr sr 打开车窗 -a 1    指定音区（副驾）");
            Console.WriteLine("      :vr local 打开车门      AH8 断网识别");
            Console.WriteLine("      :vr local 打开车门 -a 2 断网 + 二排左");
            Console.WriteLine("      :vr ts 打开车窗         旧版 TextSemanticService API");
            Console.WriteLine();
            Console.WriteLine("    应用 / 系统");
            Console.WriteLine("      :vr ver                语助版本号（versionName + versionCode）");
            Console.WriteLine("      :vr restart            重启语助进程（force-stop）");
            Console.WriteLine("      :vr set                打开语音后台设置页");
            Console.WriteLine("      :vr dbg                打开文本语义调试页");
            Console.WriteLine();
            Console.WriteLine("    破坏性操作（必须加 -y 才执行）");
            Console.WriteLine("      :vr reboot -y          重启车机（会打断正在跑的其他测试）");
            Console.WriteLine("      :vr un -y              卸载语助（卸后语音全废，需对应 APK 才能装回）");
            Console.WriteLine();
            Console.WriteLine("    参考");
            Console.WriteLine("      :vr area               音区对照表");
            Console.WriteLine("      :vr log                语音日志相关入口引导");
            Console.WriteLine();
            UseDim();
            Console.WriteLine("  简写：:vr 打开车窗 等价于 :vr sr 打开车窗");
            UseDefault();
            Separator("-");
        }

        // ==================== 十五、统一执行 + 错误归类 ====================
        // 返回是否成功，供调用方决定是否补充提示
        private static bool VrAdb(List<string> argv, string okMsg)
        {
            string o = "";
            string e = "";
            int rc = AdbCall(argv, out o, out e);
            string combined = o + "\n" + e;

            if (rc == 0 && !VrLooksBad(combined))
            {
                CMD_OK = true;
                Ok(okMsg);
                return true;
            }

            CMD_OK = false;
            string detail = VrFirstBadLine(combined);
            Fail("执行失败" + (detail.Length > 0 ? "：" + detail : ""));

            string tip = VrTip(combined);
            if (tip.Length > 0) Hint("建议：" + tip);
            return false;
        }

        // internal：自检要直接验证失败识别（rc=0 但输出 Failure 的情况）
        internal static bool VrLooksBad(string s)
        {
            if (string.IsNullOrEmpty(s)) return false;
            string low = s.ToLowerInvariant();
            // 注意：不能把 "Error type" 之类泛匹配，只挑真正致命的。
            //
            // 【bug 修复】原来漏了 "failure" / "failed"：
            //   adb uninstall 失败时标准输出是 "Failure [DELETE_FAILED_INTERNAL_ERROR]"
            //   且 **退出码是 0**，只看 rc 会误判为"卸载成功"。
            //   同理 am 的 "Error: Activity not started" 也走 stderr 但 rc=0。
            string[] marks = new string[]
            {
                "error:", "error ", "exception", "failure", "failed",
                "not allowed", "does not exist",
                "permission denial", "unable to resolve", "not found",
                "no devices", "device offline", "unauthorized", "cannot"
            };
            for (int i = 0; i < marks.Length; i++)
            {
                if (low.IndexOf(marks[i], StringComparison.OrdinalIgnoreCase) >= 0) return true;
            }
            return false;
        }

        private static string VrFirstBadLine(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            string[] lines = s.Replace("\r\n", "\n").Split('\n');
            for (int i = 0; i < lines.Length; i++)
            {
                string t = lines[i].Trim();
                if (t.Length == 0) continue;
                if (VrLooksBad(t)) return Clip(t.Replace("\"", ""), 90);
            }
            for (int i = 0; i < lines.Length; i++)
            {
                string t = lines[i].Trim();
                if (t.Length > 0) return Clip(t.Replace("\"", ""), 90);
            }
            return "";
        }

        // 语音意图的高频失败原因与处置建议
        private static string VrTip(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            string low = s.ToLowerInvariant();

            if (low.IndexOf("unable to resolve intent", StringComparison.OrdinalIgnoreCase) >= 0)
                return "设备上没有接收该 URI 的服务：确认语助 APK 已安装且支持此 scheme（" + VR_PKG + "）";
            if (low.IndexOf("not allowed to start service", StringComparison.OrdinalIgnoreCase) >= 0 ||
                low.IndexOf("background start not allowed", StringComparison.OrdinalIgnoreCase) >= 0)
                return "Android 8+ 后台服务限制：把语助保持在前台，或换用 :vr ts 走 TextSemanticService";
            if (low.IndexOf("does not exist", StringComparison.OrdinalIgnoreCase) >= 0)
                return "语助未安装或包名不对：:vr ver 查状态，ini 的 vr_pkg 可改包名";
            if (low.IndexOf("permission denial", StringComparison.OrdinalIgnoreCase) >= 0)
                return "权限不足：该服务可能需要系统签名，普通 adb 无法调用";
            if (low.IndexOf("device offline", StringComparison.OrdinalIgnoreCase) >= 0)
                return "设备离线，检查数据线，或输入 :r 重连";
            if (low.IndexOf("unauthorized", StringComparison.OrdinalIgnoreCase) >= 0)
                return "设备未授权，请在车机弹窗中允许 USB 调试";
            if (low.IndexOf("no devices", StringComparison.OrdinalIgnoreCase) >= 0)
                return "未检测到设备，输入 :diag 做连接体检";
            return "";
        }
    }
}
