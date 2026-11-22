// ============================================================================
//  Prefix.cs — 命名空间与词法路由（v7）
//
//  设计原则（这一版的核心）：
//     归属由**语法前缀**决定，不再由 if 的书写顺序决定。
//
//        !  开头  -> 强制交给设备 shell
//        :  开头  -> 工具自身能力（永不与设备命令冲突）
//        @  开头  -> 配置引用（跳转点）
//        X:\ 开头 -> 本地路径（导出）
//        裸名 7 个-> cd ls pwd pull push adb shell（设备语义 + 增强）
//        其余     -> 原样透传设备
//
//     设备命令里永远不会出现以 : ! @ 开头的写法，所以前缀与透传之间
//     不存在竞争关系 —— 这是**词法层**的保证，不需要任何优先级排序。
//
//  兼容：旧裸名（send / env / ver / now / test ...）在 legacy_alias=1 时
//        继续可用，但只提示一次迁移方向；设 0 则彻底关闭，还原纯设备语义。
//
//  C# 5.0 兼容：不用 out var / 局部函数 / => 表达式体 / $"..."。
// ============================================================================
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

namespace AdbLogExport
{
    internal static partial class App
    {
        // ==================== 一、开关 ====================
        internal static bool LIGHT_THEME = false;   // ini: theme=light（CLI 控制台配色用）
        // GUI 三套主题：dark / light / eye（护眼暖纸色）。ini 里存字符串，LIGHT_THEME 仍留给 CLI。
        internal static string THEME = "dark";
        // 2026-11-15：强调色与明暗主题正交，持久化在 ini 的 accent=，16 选 1
        internal static string ACCENT = "blue";
        // A17 修复：这张白名单以前在 GuiWeb.cs 和 Program.cs 各写一份。
        // 扩到 16 色时只改了 Program.cs，GuiWeb 那份还是 9 色旧表 ——
        // 用户选了 cyan / teal / graphite / 三白，保存时被判非法、静默改写成 blue，
        // 重启就是"强调色没记忆、回到默认蓝"。现在只在这里维护一份。
        internal static readonly string[] ACCENTS = new string[]
        {
            "blue", "cyan", "teal", "mint", "green", "yellow", "orange", "red",
            "pink", "purple", "indigo", "brown", "graphite",
            "purewhite", "eyewhite", "glasswhite"
        };
        /// <summary>把外部传入的强调色名规整成合法值（非法回退 blue，旧名 white/black 迁到 graphite）。</summary>
        internal static string NormalizeAccent(string v)
        {
            v = (v == null ? "" : v.Trim().ToLowerInvariant());
            if (v == "white" || v == "black") v = "graphite";
            for (int i = 0; i < ACCENTS.Length; i++)
                if (ACCENTS[i] == v) return v;
            return "blue";
        }
        /// <summary>
        /// 强调色的深色主题明亮版，返回 0xRRGGBB。
        /// 为什么返回 int 而不是 Color：CLI 那个 exe 编译时不引用 System.Drawing，
        /// 这里一旦出现 Color 类型，控制台版就编不过（CS0234）。
        /// </summary>
        internal static int AccentArgb()
        {
            switch (NormalizeAccent(ACCENT))
            {
                case "cyan": return 0x64D2FF;
                case "teal": return 0x40C8E0;
                case "mint": return 0x63E6E2;
                case "green": return 0x30D158;
                case "yellow": return 0xFFD60A;
                case "orange": return 0xFF9F0A;
                case "red": return 0xFF453A;
                case "pink": return 0xFF375F;
                case "purple": return 0xBF5AF2;
                case "indigo": return 0x5E5CE6;
                case "brown": return 0xAC8E68;
                case "graphite": return 0xAEAEB2;
                // 三白在深色主题下是接近纯白的中性灰白；启动层底是近黑，直接给中性亮值。
                // A19：glasswhite 原 0xE9E9EE 带冷蓝调、eyewhite 原 0xFFFDF5 带暖黄调，
                // 画在深色图标底上分别显蓝/显黄，统一改成中性灰白（与 _gen_accent.py 一致）。
                case "purewhite": return 0xF2F2F2;
                case "eyewhite": return 0xF0F0F0;
                case "glasswhite": return 0xE6E6E6;
                default: return 0x0A84FF;
            }
        }
        // 字体 / 字号 / 动效偏好：base64 不透明串（前端 JSON → base64），
        // C# 只存取不解析，和 CustomStore 同一条思路。ini: prefs=
        internal static string PREFS = "";
        internal static bool LEGACY_ALIAS = true;   // ini: legacy_alias=0 关闭旧裸名

        // 已提示过迁移的旧命令（每个会话只提示一次，避免刷屏）
        private static readonly Dictionary<string, bool> LEGACY_NOTIFIED =
            new Dictionary<string, bool>(StringComparer.OrdinalIgnoreCase);

        // ==================== 二、设备命令黑名单 ====================
        // DIY 命令如果取这些名字，会把设备命令抢走 —— 必须改用 :name 形式。
        // 这张表不求完整（设备命令随版本/厂商变化），只求覆盖高频且易误伤的。
        private static readonly string[] DEVICE_CMDS = new string[]
        {
            "ls", "cd", "pwd", "cat", "ps", "top", "kill", "killall", "clear", "ping",
            "env", "test", "df", "du", "stop", "start", "mount", "umount", "rm", "cp",
            "mv", "mkdir", "rmdir", "touch", "chmod", "chown", "ln", "find", "grep",
            "date", "echo", "sleep", "id", "whoami", "uptime", "free", "dmesg",
            "logcat", "getprop", "setprop", "watch", "nohup", "sed", "awk", "sort",
            "pm", "am", "wm", "input", "monkey", "dumpsys", "settings", "content",
            "screencap", "screenrecord", "netstat", "ifconfig", "ip", "svc", "cmd",
            "service", "bugreport", "reboot", "install", "uninstall", "su", "sh"
        };

        internal static bool IsDeviceName(string n)
        {
            if (string.IsNullOrEmpty(n)) return false;
            string t = n.ToLowerInvariant();
            for (int i = 0; i < DEVICE_CMDS.Length; i++)
            {
                if (DEVICE_CMDS[i] == t) return true;
            }
            return false;
        }

        // DIY 命令是否允许用裸名：撞设备命令的只能 :name
        internal static bool CmdBareOk(string n)
        {
            return !IsDeviceName(n);
        }

        // ==================== 三、跳转点 ====================
        // @logs / @res / @anr / @dropbox —— 跳转是**数据**，不是命令
        internal static string JumpPath(string name)
        {
            if (string.IsNullOrEmpty(name)) return "";
            string n = name.ToLowerInvariant();
            if (n == "res") return JUMP_RES;
            if (n == "logs" || n == "log") return JUMP_LOG;
            if (n == "anr") return JUMP_ANR;
            if (n == "dropbox") return JUMP_DROPBOX;
            return "";
        }

        // ==================== 四、: 命名空间路由 ====================
        // :send 文本 / :env [test|pre|dev] / :pkg ver / :pkg now
        // :which 输入 / :h / :cmds / :r :rl :rr :ri :rw / :q
        // 以及自定义命令 :net :mem ...
        internal static void RouteColon(string body)
        {
            string name;
            string arg;
            SplitLine(body, out name, out arg);

            if (name.Length == 0)
            {
                Fail(": 后面要跟命令名");
                Hint("输入 :h 查看命令索引");
                return;
            }

            string n = name.ToLowerInvariant();

            // ---- 发送 ----
            if (n == "send") { DoSend(arg); return; }

            // ---- 环境：:env 查询；:env test 切换 ----
            if (n == "env")
            {
                string a = arg.Trim();
                if (a.Length == 0) { DoEnvQuery(); return; }
                string sub;
                string rest2;
                SplitLine(a, out sub, out rest2);
                DoEnvSwitch(sub.ToLowerInvariant());
                return;
            }

            // ---- 包：:pkg ver / :pkg now ----
            // 注意：这里**不能**再收 "apk" 这个别名 —— 2026-11-11 起 :apk
            // 已改成"导出前台 APK"命令（见下方 DoExportApk），别名与命令撞名，
            // 会让 :apk 永远进不到导出分支（实测 :apk 会回 :pkg 的用法提示）。
            if (n == "pkg")
            {
                string sub;
                string rest2;
                SplitLine(arg, out sub, out rest2);
                string s = sub.ToLowerInvariant();
                if (s == "ver" || s == "versions") { DoVersions(rest2); return; }
                if (s == "front") { DoFront(); return; }
                if (s == "now") { DoNowRetired(); return; }
                Fail(":pkg 的用法：:pkg ver [包名...]  /  :pkg now");
                return;
            }

            // ---- 分辨率查询（需求1）----
            if (n == "res" || n == "resolution") { DoRes(); return; }

            // ---- UUID / DID 单项查询（需求4：内置化，绿色精简输出）----
            if (n == "uuid") { DoUuid(); return; }
            if (n == "did") { DoDid(); return; }

            // ---- 车机信息九项（需求4）----
            // :car          取一次并输出 9 项（车型/SOC/MCU/Android/VIN/UUID/DID/OPENID/分辨率）
            // :car cmd      连同取值命令一起输出
            // :car miss     只列没取到的项（快速核对哪项没配）
            if (n == "car" || n == "info" || n == "vehicle") { DoCar(arg); return; }

            // ---- 一键查询前台应用包名 + Activity + 路径（需求2.2）----
            if (n == "front" || n == "fg") { DoFront(); return; }

            // ---- 一键清理前台应用（需求2.1）----
            if (n == "fstop") { DoFstop(); return; }
            // Kill 前台 = adb shell kill -9（只杀进程，不清数据），与 fstop(pm clear) 分开
            if (n == "killfront" || n == "killfg") { DoKillFront(); return; }
            // 查系统深色模式设置
            if (n == "sysnight" || n == "sysmode") { DoSysNight(); return; }
            // 排查用：看 ps 样本与 pid 匹配结果
            if (n == "pid" || n == "pidtest") { DoPidTest(arg); return; }

            // ---- 升级前置指令（需求3）----
            if (n == "preup" || n == "upgrade") { DoPreUpgrade(); return; }

            // ---- 语音助手调试（融合自 语音助手工具.exe）----
            if (n == "vr" || n == "voice") { RouteVr(arg); return; }

            // ---- 导出类快捷指令（2026-11-10）----
            // :apk      导出前台 APK 到 桌面\logcat\<今天>\APK
            // :pcm      PCM 采集导出（前置：工程模式→日志设置→audio→使能）
            // :dlog     Android 日志导出（/log/android_log）
            // :carplay  carplay 音频文件导出（/data/carplay/records）
            if (n == "apk" || n == "apkexport" || n == "exportapk") { DoExportApk(); return; }
            if (n == "pcm" || n == "pcmexport" || n == "exportpcm") { DoExportPcm(); return; }
            if (n == "dlog" || n == "androidlog" || n == "exportlog") { DoExportDlog(); return; }
            if (n == "carplay" || n == "carplayexport") { DoExportCarplay(); return; }

            // :anrlog     导出 ANR 日志（/data/anr -> 桌面\logcat\日期\anr）
            // :dropboxlog 导出 crash 日志（/data/system/dropbox -> 桌面\logcat\日期\dropbox）
            //
            // 【命名冲突】不能叫 :anr / :dropbox —— 这两个名字已经被跳转点占用
            // （cd @anr / cd @dropbox），MovedTo 会抢先拦成"它现在叫 cd @anr"。
            // 加上 -log 后缀既避开冲突，也把"这条是导日志"的意图说清楚了。
            if (n == "anrlog" || n == "exportanr" || n == "anrlogexport") { DoExportAnr(); return; }
            if (n == "dropboxlog" || n == "exportdropbox" || n == "crashlog") { DoExportDropbox(); return; }

            // :reboot 重启车机（内置，带下发回显 + 断线判定）
            // 裸 reboot 也能透传，但那样输出框是空的、用户不知道发没发出去，
            // 所以这里显式接管成内置命令。
            if (n == "reboot" || n == "restartcar" || n == "rbt") { DoReboot(); return; }

            // ---- 网联服务（2026-11-15）：导出 / 埋点 / 设备标识 / 打开链接 ----
            // :wsalipay   导出支付宝日志      -> 桌面\logcat\<今天>\alipay\applog
            // :wswmpf     导出微信小程序日志  -> ...\wmpf\xlog_sdcard（主）/ xlog_storage（备）
            // :wswx       导出车载微信日志    -> ...\wxmsg\log + ...\wxmsg\autowechat
            if (n == "wsalipay" || n == "alipaylog") { DoExportAlipayLog(); return; }
            if (n == "wswmpf" || n == "wmpflog") { DoExportWmpfLog(); return; }
            if (n == "wswx" || n == "wxlog") { DoExportWxMsgLog(); return; }

            // :sxlog [on|get|set]  星河云埋点
            //   :sxlog      等价 :sxlog on（用户口述的"打开星河云埋点"含重启）
            //   :sxlog get  只回读
            //   :sxlog set  只写 privacy_enabled=true（不重启）
            if (n == "sxlog" || n == "xinghe" || n == "sxtrace")
            {
                string sub = (arg ?? "").Trim().ToLowerInvariant();
                if (sub.Length == 0 || sub == "on" || sub == "open" || sub == "开")
                { DoSxTraceOn(); return; }
                if (sub == "get" || sub == "q" || sub == "查")
                { DoSxTraceGet(); return; }
                if (sub == "set" || sub == "true" || sub == "1")
                { DoSxTraceSet(); return; }
                Fail(":sxlog 的参数不认识：" + arg);
                Hint("用法：:sxlog          打开（含重启 + 等待上线）");
                Hint("      :sxlog get      只看当前设置");
                Hint("      :sxlog set      只写 privacy_enabled=true");
                return;
            }

            // :wsdevid  查设备标识（navi.did / android_id / navi.uuid）
            // :proxydel  删除代理（三个键分别删、分别回显）
            if (n == "proxydel" || n == "delproxy") { DoProxyDel(); return; }

            // :tbosprod yes / :tbospre yes / :tboschek   TBOX 环境切换（写 mcu_spi + 重启 MCU）
            if (n == "tbosprod" || n == "tbosformal") { DoTbox(false, arg); return; }
            if (n == "tbospre" || n == "tbosstaging") { DoTbox(true, arg); return; }
            if (n == "tbos" || n == "tboschek" || n == "tboshelp")
            {
                // 不带子命令时给两套环境的差异对照，避免用户靠记
                Console.WriteLine();
                Console.WriteLine("  TBOX 环境切换（写 /dev/mcu_spi，末帧重启 MCU）");
                Console.WriteLine("    :tbosprod yes    正式：mqtt-*-access.gacicv.com / cms-sm-access.gacicv.com");
                Console.WriteLine("    :tbospre  yes    预发布：pre-mqtt-*-access.gacicv.com / pre-sm-cms.gacicv.com");
                Console.WriteLine("    不带 yes 只做 dry-run，不写设备");
                Console.WriteLine();
                OkLocal();
                return;
            }

            // :qnxlog [路径]  导出 QNX 侧日志（默认 /share/log）到 桌面\logcat\<日期>\qnx
            if (n == "qnxlog" || n == "qnxl" || n == "qnx") { DoQnxLog(arg); return; }

            // ---- 2026-11-20 第 5 批：手车互联 / 智驾出行 ----
            // :audiohal [config|rc]   导讯飞音频 HAL 配置（两个文件都落 \audiohal）
            // :selinux [off|on]       关/开 SELinux（root → remount → setenforce）
            // :md5so                  生成 /vendor/lib(64) 下 .so 的 md5 清单
            // :md5pull                导 /data/md5.txt
            // :audiodump              建 /data/misc/audio/audioserver/audiotrack（777）
            // :audiodumppull          导整个 /data/misc/audio/audioserver
            // :gmqtlog                导高德日志 /data/misc/bllog
            if (n == "audiohal" || n == "audiohalcfg" || n == "xfyunaudio") { DoAudioHalCfg(arg); return; }
            if (n == "selinux" || n == "se" || n == "selinuxset") { DoSelinuxCmd(arg); return; }
            if (n == "md5so" || n == "md5find" || n == "sofind") { DoMd5So(); return; }
            if (n == "md5pull" || n == "md5export") { DoMd5Pull(); return; }
            if (n == "audiodumpcreate" || n == "audiodump") { DoAudioDumpCreate(); return; }
            if (n == "audiodumppull" || n == "dumppull") { DoAudioDumpPull(); return; }
            if (n == "gmqtlog" || n == "amap" || n == "amapbllog") { DoAmapLog(); return; }

            // ---- 2026-11-22 第 12 批需求 3：环境与校验 ----
            // :envdomain      查环境域名（getprop | grep -i domain）
            // :envhttps       查环境 https（getprop | grep -i https）
            // :apkverify [on|off]  开关系统 APK 验证检查（persist.sys.verify_apk）
            if (n == "envdomain" || n == "envdomaincheck") { DoEnvDomain(); return; }
            if (n == "envhttps" || n == "envhttpscheck") { DoEnvHttps(); return; }
            if (n == "apkverify" || n == "verifyapk") { DoApkVerify(arg); return; }

            // :pki [del|pre|prod]   PKI 证书：删除 / 切预发布 / 切正式（root + 多步）
            if (n == "pki" || n == "pkicert") { DoPkiCmd(arg); return; }

            // :castrec <屏号> [秒]  投屏并录制（scrcpy --record，默认 60 秒）
            if (n == "castrec" || n == "castrecord") { DoCastRec(arg); return; }

            // :caststop <屏号|all>  取消投屏（投屏是独立进程，不关会一直活着）
            if (n == "caststop" || n == "castclose") { DoCastStop(arg); return; }

            // :cfg export|import|info  配置文件（自定义指令 + APK 列表 + 界面偏好）
            if (n == "cfg" || n == "profile") { DoCfg(arg); return; }

            if (n == "wsdevid" || n == "devid") { DoDeviceId(); return; }

            // :url <地址>  用桌面系统默认浏览器打开（不是车机）
            if (n == "url" || n == "openurl" || n == "link") { DoOpenUrl(arg); return; }

            // :scrcpy <屏号|名称>  拉起外部 scrcpy 窗口投指定屏（A15）
            //   映射：主屏 0 / 后排屏 1 / HUD 3 / 副屏 4 / PHUD-B 9 / PHUD-C 10
            if (n == "scrcpy" || n == "cast" || n == "投屏") { DoScrcpy(arg); return; }

            // ---- 顺序执行类快捷指令（2026-11-10）----
            // :hicar     打开 HiCarSDK 日志（6 条顺序执行，失败跳过并报告）
            // :carplayon 打开 carplay 音频（2 条顺序执行，失败跳过并报告）
            if (n == "hicar" || n == "hicarsdk") { DoHicarDebug(); return; }
            if (n == "carplayon" || n == "carplayaudio") { DoCarplayOn(); return; }

            // ---- 手车互联（2026-11-12 需求1~4）----
            // CarPlay 认证属性：CERT=true 放行，CERT=false 拒绝
            //   :carplaycert on      设为 true
            //   :carplaycert off     设为 false
            //   :carplaycert         查询当前值
            // 也支持 :carplaycert true / :carplaycert false 两种直白写法。
            if (n == "carplaycert" || n == "cpcert")
            {
                string cv = (arg ?? "").Trim().ToLowerInvariant();
                if (cv.Length == 0) { DoCarplayCertGet(); return; }
                if (cv == "on" || cv == "true" || cv == "1" || cv == "开")
                { DoCarplayCertSet(true); return; }
                if (cv == "off" || cv == "false" || cv == "0" || cv == "关")
                { DoCarplayCertSet(false); return; }
                Fail("参数不认识：" + arg);
                Hint("用法：:carplaycert        查询");
                Hint("      :carplaycert on     设为 true");
                Hint("      :carplaycert off    设为 false");
                return;
            }
            if (n == "carplaycertget" || n == "cpcertget") { DoCarplayCertGet(); return; }

            // 清除 HiCar 历史设备（走 hdc，不是 adb）
            if (n == "hicarclear" || n == "hicarclean" || n == "clearhicar")
            { DoClearHicarDevices(); return; }

            // hdc 设备列表（排查用）
            if (n == "hdclist" || n == "hdcdev") { DoHdcList(); return; }

            // 方控强制重启（组合键：电话 503 + 星号 520 同时按住 N 秒）
            //   :fkforce        默认 20 秒
            //   :fkforce 25     按住 25 秒
            if (n == "fkforce" || n == "fkreboot" || n == "fkrst")
            {
                int hold = 20;
                string ha = (arg ?? "").Trim();
                if (ha.Length > 0) int.TryParse(ha, out hold);
                DoForceReboot(hold);
                return;
            }

            // 方控长按：单键 down → 按住 3 秒 → up（与短按 inject-key 区分）
            //   :fkvoicelong   语音键(508) 长按
            //   :fkcalllong    通话键(503) 长按
            // 2026-11-18：按住时长 4 秒 → 3 秒（用户要求，真机手感更接近长按）
            if (n == "fkvoicelong" || n == "fkvhold") { DoKeyHold(508, 3000); return; }
            if (n == "fkcalllong" || n == "fkcallhold") { DoKeyHold(503, 3000); return; }

            // 方控星号键（短按，car_service 自动 down+up）
            //   :fkstarleft / :fkstarl    左星号 521
            //   :fkstarright / :fkstarr   右星号 520
            // 2026-11-18 修复：这两个名字此前只出现在 :h 帮助与快捷卡片里，
            // 路由里**根本没有分支** → 点卡片会落到"没有这个命令：fkstarleft"。
            // 编码取自 SynTestUtil 逆向（leftkey=521 / rightkey=520）。
            if (n == "fkstarleft" || n == "fkstarl") { DoFkTap(521, "左星号键"); return; }
            if (n == "fkstarright" || n == "fkstarr") { DoFkTap(520, "右星号键"); return; }

            // ---- 无感知截图（需求2）：绕过 cmd.exe 的黑框 ----
            // :shot 原走 cmds.ini 的 `adb exec-out screencap -p > path`，
            // 那条含 `>` 会进 cmd.exe，cmd 再拉起 adb.exe（控制台程序）
            // 就弹黑框。现在改成内置静默实现，直接捕获 adb 的 PNG 二进制。
            // :shot -r  仍走老的重定向路径（逃生舱，万一静默路径在某种 ROM 上不行）
            if (n == "shot" || n == "screencap" || n == "snap")
            {
                string a = (arg ?? "").Trim().ToLowerInvariant();
                if (a == "-r" || a == "--raw" || a == "raw") { TryRunCmd("shot", ""); return; }
                DoShotSilent();
                return;
            }

            // 截帧录屏（屏幕受 FLAG_SECURE 保护时的兜底：screencap 连拍 + ffmpeg 合成）
            // :rec          无限录，靠卡片再点一次停止
            // :rec 15       录 15 秒自动停止并合成
            if (n == "rec" || n == "record" || n == "recgrab") { DoRecGrab(arg); return; }

            // 录屏编码器 ffmpeg：查看当前用的是哪一个 / 手动指定路径
            //   :ffmpeg            看状态（四级查找的结果 + 找过哪些位置）
            //   :ffmpeg auto       强制重新查找（忽略缓存）
            //   :ffmpeg D:\ff\ffmpeg.exe   校验并记住这个路径
            if (n == "ffmpeg" || n == "ffp") { DoFfmpeg(arg); return; }

            // ---- 输入模式：中文（输入法） / 编辑（方向键历史） ----
            if (n == "ime" || n == "cn") { DoIme(arg); return; }

            // ---- 解释一条输入会怎么执行 ----
            if (n == "which" || n == "explain") { Which(arg); return; }

            // ---- 帮助与列表（纯本地，无需设备，显式标记成功）----
            if (n == "h" || n == "help" || n == "?")
            {
                if (arg.Trim().ToLowerInvariant() == "all") { HelpAll(); OkLocal(); return; }
                HelpIndex();
                OkLocal();
                return;
            }
            if (n == "cmds") { ListCmds(); OkLocal(); return; }

            // ---- 会话 ----
            if (n == "r") { RetrySoft(); return; }
            if (n == "rl") { RetryLast(); return; }
            if (n == "rr") { RetryHard(); return; }
            if (n == "ri" || n == "i") { DoInit(); return; }
            if (n == "rw") { DoRewidth(); return; }
            if (n == "q" || n == "quit" || n == "exit")
            {
                Pause();
                Environment.Exit(0);
                return;
            }
            if (n == "ping") { Ping(); return; }

            // ---- adb 连接体检：搜不到设备时先看这个 ----
            if (n == "diag" || n == "doctor") { DoDiag(); return; }

            // ---- 自定义命令（统一进 : 空间，零冲突）----
            if (HasCmd(n)) { TryRunCmd(n, arg); return; }

            // ---- 旧名兜底提示 ----
            string moved = MovedTo(n);
            if (moved.Length > 0)
            {
                Fail(":" + n + " 不是命令；它现在叫 :" + moved);
                return;
            }

            Fail("没有这个命令：" + n);
            Hint("输入 :h 查看索引，:cmds 查看自定义命令");
        }

        // 旧名 -> 新名，用于 :oldname 的纠错提示
        private static string MovedTo(string n)
        {
            if (n == "ver" || n == "versions") return "pkg ver";
            if (n == "now" || n == "front") return "pkg now";
            if (n == "test" || n == "pre" || n == "dev") return "env " + n;
            if (n == "syncore") return "env";
            if (n == "res" || n == "logs" || n == "anr" || n == "dropbox") return "cd @" + n;
            return "";
        }

        // ==================== 分辨率查询（需求1） ====================
        // 成功输出分辨率（成功色），失败输出报错信息
        // ==================== 车机信息九项（需求4） ====================
        // 用户给的口径：
        //   车型值      adb shell getprop sys.product.gacvehicleplatform
        //   SOC 版本    adb shell getprop ro.product.version.short_name
        //   MCU 版本    adb shell getprop sys.vehicle.mcu.version
        //   Android 版本 adb shell getprop ro.build.version.release
        //   VIN 码      adb shell getprop persist.sys.vehicle.vin
        //   UUID        adb shell getprop persist.sys.navi.uuid
        //   DID         adb shell getprop persist.sys.navi.did
        //   OPENID      adb shell getprop persist.sys.navi.openid
        //   屏幕分辨率   adb shell wm size
        //
        // 采集逻辑在 CarInfo.cs（一次 shell 往返取全部 9 项），
        // 这里只负责"何时取、怎么显示"，避免同一份口径散落两处。
        private static void DoCar(string arg)
        {
            string a = (arg ?? "").Trim().ToLowerInvariant();

            bool withCmd = (a == "cmd" || a == "--cmd" || a == "-v" || a == "verbose");
            bool onlyMissing = (a == "miss" || a == "missing" || a == "empty");

            if (a == "help" || a == "-h" || a == "--help")
            {
                OkLocal();
                Console.WriteLine();
                UseDim(); Console.Write("  用法  "); UseDefault();
                Console.WriteLine(":car            查询车机信息九项（一次 shell 往返）");
                Console.WriteLine("          :car cmd       连同取值命令一起输出，方便复制复现");
                Console.WriteLine("          :car miss      只列出没取到的项");
                Console.WriteLine();
                UseDim(); Console.Write("  说明  "); UseDefault();
                Console.WriteLine("车型/SOC/MCU/Android/VIN/UUID/DID/OPENID 走 getprop，");
                Console.WriteLine("          分辨率走 wm size（Override 优先于 Physical）。");
                Console.WriteLine("          断链后输入 r 刷新会自动重查这九项。");
                Console.WriteLine();
                return;
            }

            if (OFFLINE || DEVN == 0)
            {
                Warn("设备未连接，无法查询车机信息");
                Hint("输入 r 重连（重连后会自动重查这九项）");
                return;
            }

            Console.WriteLine("  [车机信息] 正在读取 ...");

            // 把"正在执行的命令"打出来（用户要求能看到执行了什么）
            if (!onlyMissing)
            {
                UseDim();
                Console.Write("  $ adb shell getprop ");
                for (int i = 0; i < CAR_KEYS.Length; i++)
                {
                    if (i > 0) Console.Write(" + ");
                    Console.Write(CAR_KEYS[i]);
                }
                Console.WriteLine();
                UseDim();
                Console.WriteLine("  $ adb shell wm size");
                UseDefault();
                Console.WriteLine();
            }

            bool got = LoadCarInfo();
            if (!got)
            {
                CMD_OK = false;
                Fail("车机信息读取失败（设备无响应，或属性全部为空）");
                Hint("确认设备在线：devices；断链后输入 r 重连");
                return;
            }

            CMD_OK = true;
            RenderCarInfo(withCmd, onlyMissing);

            if (!onlyMissing)
            {
                Ok("车机信息查询完成（" + CAR_KEYS.Length + " 项属性 + 分辨率）");
                Hint("只想看没取到的项：:car miss    想看取值命令：:car cmd");
            }
        }

        private static void DoRes()
        {
            if (OFFLINE)
            {
                Warn("设备未连接，无法查询分辨率");
                Hint("输入 :r 重连");
                return;
            }

            string o = "";
            string e = "";
            int rc = ShellCall(CUR, "wm size 2>&1", out o, out e);
            string all = o + e;

            if (rc != 0 || all.Trim().Length == 0)
            {
                CMD_OK = false;
                string detail = FirstLine(all.Trim());
                Fail("分辨率查询失败" + (detail.Length > 0 ? "：" + detail : ""));
                return;
            }

            CMD_OK = true;
            string res = "";
            string[] lines = all.Split('\n');
            for (int i = 0; i < lines.Length; i++)
            {
                string t = lines[i].Trim();
                if (t.StartsWith("Physical size:", StringComparison.Ordinal))
                {
                    res = t.Substring("Physical size:".Length).Trim();
                    break;
                }
            }
            if (res.Length == 0) res = all.Trim();

            UseOk();
            Console.WriteLine("  分辨率  " + res);
            UseDefault();
        }

        // ==================== UUID / DID 单项查询（需求4） ====================
        // 需求4：从 cmds.ini 自定义命令升级为内置命令，与 :res 同类——
        // 用 getprop 精确取单属性（纯值，不带 [key]: 方括号前缀），绿色输出精简结果。
        private static void DoUuid()
        {
            DoSingleProp("uuid", "persist.sys.navi.uuid");
        }

        private static void DoDid()
        {
            DoSingleProp("did", "persist.sys.navi.did");
        }

        // 通用：查单个系统属性，绿色输出「key: 值」。
        private static void DoSingleProp(string key, string prop)
        {
            if (OFFLINE)
            {
                Warn("设备未连接，无法查询 " + key.ToUpperInvariant());
                Hint("输入 :r 重连");
                return;
            }

            string o = "";
            string e = "";
            int rc = ShellCall(CUR, "getprop " + prop + " 2>&1", out o, out e);
            string val = FirstLine((o + e).Trim());

            if (rc != 0 || val.Length == 0)
            {
                CMD_OK = false;
                Fail(key.ToUpperInvariant() + " 查询失败（属性 " + prop + " 无值）");
                return;
            }

            CMD_OK = true;
            UseOk();
            Console.WriteLine("  " + key + ": " + val);
            UseDefault();
        }

        // ==================== 升级前置指令（需求3） ====================
        // 依次执行 root / enable-verity / reboot，报错输出报错并跳过继续下一条
        private static void DoPreUpgrade()
        {
            if (OFFLINE)
            {
                Warn("设备未连接，无法执行升级前置指令");
                Hint("输入 :r 重连");
                return;
            }

            string[] steps = new string[] { "root", "enable-verity", "reboot" };
            bool anyOk = false;

            for (int i = 0; i < steps.Length; i++)
            {
                string c = steps[i];
                string o = "";
                string e = "";
                int rc = AdbCall(new List<string> { c }, out o, out e);
                string combined = (o + e).Trim();
                string low = combined.ToLowerInvariant();

                bool ok = (rc == 0)
                    && !low.Contains("error")
                    && !low.Contains("cannot")
                    && !low.Contains("fail")
                    && !low.Contains("denied")
                    && !low.Contains("not found");

                if (ok)
                {
                    anyOk = true;
                    UseOk();
                    Console.WriteLine("  \u221A adb " + c + " 完成"
                        + (combined.Length > 0 ? "：" + FirstLine(combined) : ""));
                    UseDefault();
                }
                else
                {
                    UseErr();
                    Console.WriteLine("  \u00D7 adb " + c + " 报错"
                        + (combined.Length > 0 ? "：" + FirstLine(combined) : ""));
                    UseDefault();
                    // 报错跳过，继续执行下一条
                }
            }

            CMD_OK = anyOk;
        }

        // ==================== 五、旧裸名兼容 ====================
        // 返回 true 表示已处理。旧名照旧可用，但不再提示迁移（提示本身是噪音）。
        internal static bool TryLegacy(string c, string argRaw)
        {
            if (!LEGACY_ALIAS) return false;

            if (c == "send") { DoSend(argRaw); return true; }
            if (c == "syncore" || c == "env") { DoEnvQuery(); return true; }
            if (c == "test" || c == "pre" || c == "dev")
            {
                DoEnvSwitch(c);
                return true;
            }
            if (c == "res" || c == "logs" || c == "anr" || c == "dropbox")
            {
                DoJump(JumpPath(c), c, argRaw);
                return true;
            }
            if (c == "logcat") { DoLogcat(argRaw); return true; }
            if (c == "ver" || c == "versions") { DoVersions(argRaw); return true; }
            if (c == "front") { DoFront(); return true; }
            if (c == "now") { DoNowRetired(); return true; }
            if (c == "cmds") { ListCmds(); OkLocal(); return true; }
            if (c == "lsf") { DoLs(argRaw, true); return true; }
            if (c == "r") { RetrySoft(); return true; }
            if (c == "rl") { RetryLast(); return true; }
            if (c == "rr") { RetryHard(); return true; }
            if (c == "ri" || c == "i") { DoInit(); return true; }
            if (c == "rw") { DoRewidth(); return true; }
            return false;
        }

        // 迁移提示：每个旧名每会话只打一次，灰色，不打断
        private static void Note(string oldName, string newName)
        {
            if (LEGACY_NOTIFIED.ContainsKey(oldName)) return;
            LEGACY_NOTIFIED[oldName] = true;
            Hint(oldName + " 已迁移到 " + newName + "（本会话只提示一次）");
        }

        // ==================== 六、:which —— 解释归属 ====================
        // 不解剖执行，只回答"这条会被谁接走、最终执行什么"
        internal static void Which(string argRaw)
        {
            string t = argRaw.Trim();
            if (t.Length == 0)
            {
                Fail("用法：:which <任意输入>");
                Hint("例：:which devices   :which 你好   :which df -h");
                return;
            }

            string kind;
            string detail;
            Classify(t, out kind, out detail);

            Console.WriteLine();
            // v8.0：补一次 UseDefault()。这行原先直接输出，而上一行可能刚设过
            // 暗色（UseDim）或其它颜色，于是"输入 xxx"会继承上一条的色彩 ——
            // 表现为这一行颜色随上一条命令而变。GUI 侧把这个泄漏如实暴露了出来
            // （级别被标成 4=弱化），所以在这里把颜色归位。
            UseDefault();
            Console.WriteLine("  输入   " + t);
            UseOk();
            Console.Write("  归属   ");
            Console.Write(kind);
            UseDefault();
            Console.WriteLine();
            if (detail.Length > 0)
            {
                UseDim();
                Console.WriteLine("  执行   " + detail);
                UseDefault();
            }
            Console.WriteLine();
            OkLocal();
        }

        // 与 Dispatch 保持同一套判定，但只分类不执行
        //
        // 【v7.15 修复】旧版这里判完 cd/ls/pwd/pull/push 就直接做"中文判定 -> 自定义命令
        // -> adb 子命令"，**漏掉了 TryLegacy 这一层**。于是 send / ver / now / logs /
        // lsf / r / cmds / logcat 这些旧裸名被报成"透传设备 shell"，
        // 而实际执行时 Dispatch 分支 6 会先把它们接走 —— :which 的结论与真实行为相反。
        // 这对"解释这条输入会怎么执行"这个需求是致命的：解释错了比不解释更糟。
        //
        // 现在的顺序与 Dispatch 严格一致：
        //   adb/shell -> cd/pwd/ls/pull/push -> h/q -> 旧裸名 -> 中文 -> 自定义 -> adb 子命令
        internal static void Classify(string t, out string kind, out string detail)
        {
            kind = "";
            detail = "";

            if (t.Length == 0) { kind = "空"; return; }

            if (t[0] == '!') { kind = "设备（强制）"; detail = t.Substring(1).Trim(); return; }
            if (t[0] == ':') { kind = "工具"; detail = t; return; }
            if (t[0] == '@')
            {
                string jp = JumpPath(t.Substring(1).ToLowerInvariant());
                kind = "跳转";
                detail = (jp.Length == 0) ? "未配置的跳转点" : ("cd " + jp);
                return;
            }
            if (IsWinPath(t)) { kind = "导出"; detail = CUR + "  ->  " + t; return; }

            string c;
            string a;
            SplitLine(t, out c, out a);
            string lc = c.ToLowerInvariant();

            if (lc == "adb") { kind = "adb"; detail = "adb " + a; return; }
            if (lc == "shell") { kind = "设备 shell"; detail = a; return; }

            // 复合命令体检：与 Dispatch 分支 5 的 complex 判定严格一致。
            // ls && echo ok / ls > /sdcard/a / cd x && ls 这类会放弃增强接管、
            // 原样透传，所以这里不能报"设备（语义增强）"—— 否则解释与行为相反。
            bool complex = IsComplexShellLine(a) || IsComplexShellLine(t);
            if (!complex
                && (lc == "cd" || lc == "pwd" || lc == "ls" || lc == "pull" || lc == "push"))
            {
                kind = "设备（语义增强）";
                detail = lc + (a.Length > 0 ? " " + a : "");
                return;
            }

            // 帮助与退出：始终可用，且不属于 legacy（关掉旧名也要能用）
            if (lc == "h" || lc == "?" || lc == "help")
            {
                kind = "工具";
                detail = (a.Trim().ToLowerInvariant() == "all") ? "帮助（完整）" : "帮助（索引）";
                return;
            }
            if (lc == "q" || lc == "quit" || lc == "exit")
            {
                kind = "工具";
                detail = "退出";
                return;
            }

            // 旧裸名：Dispatch 分支 6 会先接走，这里必须同步认出来
            string legacy = LegacyKind(lc, a);
            if (legacy.Length > 0)
            {
                kind = "工具（旧名）";
                detail = legacy;
                return;
            }

            if (IsProbablyText(c)) { kind = "发送到 App"; detail = t; return; }

            if (HasCmd(lc))
            {
                kind = CmdBareOk(lc) ? "自定义命令" : "自定义命令（必须写 :" + lc + "）";
                detail = ExpandTemplate(CMDS[lc].Run, a, lc);
                return;
            }

            if (IsAdbSubcmd(lc)) { kind = "adb"; detail = "adb " + t; return; }

            // 本地管道：Dispatch 分支 10 会把它接走，用 cmd /c 在电脑侧执行
            // 右半段的 findstr / sort / more。
            //
            // 【2026-11-12 修复】这里原来直接落到"透传设备 shell"，于是
            //     :which getprop | findstr navi
            // 报「透传设备 shell」，实际执行却走 RunShellPipe（本地过滤）。
            // 解释与行为相反 —— 比不解释更糟。注释里 v7.15 那轮修过
            // TryLegacy 的同类缺口，这次补齐 IsLocalPipe 这一层。
            if (IsLocalPipe(t))
            {
                kind = "设备 + 本地过滤";
                detail = t;
                return;
            }

            kind = "透传设备 shell";
            detail = t;
        }

        // 旧裸名 -> 它实际会执行什么。必须与 TryLegacy 一一对应。
        private static string LegacyKind(string lc, string argRaw)
        {
            if (!LEGACY_ALIAS) return "";

            if (lc == "send") return "send " + argRaw.Trim();
            if (lc == "syncore" || lc == "env") return "env（查询）";
            if (lc == "test" || lc == "pre" || lc == "dev") return "env " + lc + "（切换）";
            if (lc == "res" || lc == "logs" || lc == "anr" || lc == "dropbox")
                return "cd @" + lc;
            if (lc == "logcat") return (argRaw.Trim().Length > 0) ? ("logcat " + argRaw.Trim()) : "logcat -d";
            if (lc == "ver" || lc == "versions") return "pkg ver";
            if (lc == "now" || lc == "front") return "pkg now";
            if (lc == "cmds") return "列出自定义命令";
            if (lc == "lsf") return "lsf" + (argRaw.Trim().Length > 0 ? " " + argRaw.Trim() : "");
            if (lc == "r") return "刷新回根目录";
            if (lc == "rl") return "重试上次失败的操作";
            if (lc == "rr") return "重启 adb 服务后重连";
            if (lc == "ri" || lc == "i") return "完全初始化";
            if (lc == "rw") return "重取窗口宽度";
            return "";
        }

        // ==================== 七、标题栏 ====================
        // 控制台标题零占行、始终可见。信息按"最可能被截断的放后面"排序：
        // 任务栏只显示前 ~30 字符，所以设备号与在线状态必须在前。
        internal static void UpdateTitle()
        {
            StringBuilder sb = new StringBuilder("adb");

            if (OFFLINE)
            {
                sb.Append(" · 未连接");
            }
            else if (string.IsNullOrEmpty(DEVID))
            {
                sb.Append(" · 无设备");
            }
            else
            {
                sb.Append(" · ");
                sb.Append(DEVID);
                sb.Append(DEVN > 0 ? " 在线" : " 离线");
            }

            if (!PERMOK) sb.Append(" · 目录受限");
            if (!string.IsNullOrEmpty(DEV_PLAT)) { sb.Append(" · "); sb.Append(DEV_PLAT); }
            sb.Append(" · ");
            sb.Append(CUR);

            Util.SetTitle(sb.ToString());
        }

        // ==================== 八、帮助索引 ====================
        // 默认只给一屏索引；完整帮助用 h all
        internal static void HelpIndex()
        {
            Console.WriteLine();
            Separator("-");
            Console.WriteLine("  输入即命令：不认识的一律原样交给设备 shell");
            Console.WriteLine("    adb xxx       走 adb 层       !xxx   强制走设备 shell");
            Console.WriteLine("    :xxx          工具自身命令    @xxx   跳转点（@logs 等）");
            Console.WriteLine("    X:\\目录       把当前目录导出到该路径");
            Console.WriteLine();
            Console.WriteLine("  设备命令（裸名，语义与原生一致）");
            Console.WriteLine("    cd  ls  pwd  pull  push  adb  shell");
            Console.WriteLine("    其他一切（df -h、pm list、cat x.log、351）直接透传");
            Console.WriteLine();
            Console.WriteLine("  工具命令（: 前缀）");
            Console.WriteLine("    :send 文本     发到 App        :env [test|pre|dev]  切换/查询环境");
            Console.WriteLine("    :pkg ver      批量查版本        :pkg now             查前台应用");
            Console.WriteLine("    :car          车机信息九项      :car cmd             连取值命令一起显示");
            Console.WriteLine("    :vr help      语音助手调试      :vr sr 打开车窗      语音识别");
            Console.WriteLine("    :carplaycert  手车互联认证      :hicarclear         清 HiCar 历史");
            Console.WriteLine("    :fk*          方控按键注入      :fkforce            组合键强重启");
            Console.WriteLine("    :which 输入   解释会怎么执行    :cmds                自定义命令列表");
            Console.WriteLine("    :h            本索引            :h all               完整帮助");
            Console.WriteLine("    :r :rl :rr :ri :rw             刷新 / 重试 / 重连 / 重取宽度");
            Console.WriteLine();
            Console.WriteLine("  跳转点（@ 前缀，目标在 ini 的 jump_*）");
            Console.WriteLine("    cd @logs   cd @res   cd @anr   cd @dropbox");
            Console.WriteLine();
            UseDim();
            Console.WriteLine("  旧名仍可用（send / ver / now / test ...），但不占裸名；");
            Console.WriteLine("  输入 :h all 看完整帮助，:which send 看它现在的归属");
            UseDefault();
            Separator("-");
        }

        // ==================== 输入模式切换 ====================
        // 控制台里"输入法"和"行编辑"是互斥的：
        //   ReadConsoleInput（ReadKey）读不到输入法的组字结果，中文变成拼音字母；
        //   ReadConsole（ReadLine）能挂输入法，但拿不到方向键。
        // 所以做成三档：一次性 / 常驻 / 跟随系统输入法状态。
        internal static void DoIme(string argRaw)
        {
            string a = (argRaw == null) ? "" : argRaw.Trim().ToLowerInvariant();

            if (a.Length == 0)
            {
                INPUT_AUTO = false;
                INPUT_MODE = 2;                 // 一次性：下一条走输入法，读完回编辑
            }
            else if (a == "on" || a == "1" || a == "cn")
            {
                INPUT_AUTO = false;
                INPUT_MODE = 1;
            }
            else if (a == "off" || a == "0" || a == "edit")
            {
                INPUT_AUTO = false;
                INPUT_MODE = 0;
            }
            else if (a == "auto")
            {
                INPUT_AUTO = true;
                INPUT_MODE = 0;
            }
            else
            {
                Fail("用法：:ime [on|off|auto]");
                Hint(":ime        下一条用输入法（读完自动回编辑）");
                Hint(":ime on     常驻中文模式    :ime off    关闭");
                Hint(":ime auto   跟随系统输入法状态（能检测到时自动切）");
                return;
            }

            Console.WriteLine();

            if (INPUT_AUTO)
            {
                int st = ImeNativeState();
                Ok("输入模式：跟随系统输入法");
                if (st == 1) Hint("当前检测到：中文状态 -> 这一行用 ReadLine，可以打中文");
                else if (st == 0) Hint("当前检测到：英文状态 -> 这一行用行编辑器，方向键可用");
                else Hint("检测不到输入法状态（Windows Terminal 常见）-> 退回行编辑器；要打中文用 :ime");
                Hint("检测原理：ImmGetConversionStatus 读 IME_CMODE_NATIVE；切输入法即切模式");
            }
            else if (INPUT_MODE == 2)
            {
                Ok("下一条用中文输入（读完自动回编辑模式）");
                Hint("适合偶尔发一条中文；想连续输入用 :ime on");
            }
            else if (INPUT_MODE == 1)
            {
                Ok("输入模式：中文（常驻）");
                Hint("现在可以正常用输入法打中文；方向键 / Tab / 历史 不可用");
                Hint("切回：:ime off");
            }
            else
            {
                Ok("输入模式：编辑（方向键 / Tab / 历史可用）");
                Hint("要打中文：:ime（一次性）或 :ime on（常驻）");
                Hint("也可以在 ini 里写 input=ime / input=auto");
            }

            Console.WriteLine();
        }

        // ==================== 系统输入法状态 ====================
        // ReadKey 绕过 IME 是 Win32 的既定行为，改不了；
        // 但"当前 IME 处在中文还是英文"是可以问系统的，据此决定用哪条读法。
        [DllImport("kernel32.dll")]
        private static extern IntPtr GetConsoleWindow();

        [DllImport("imm32.dll")]
        private static extern IntPtr ImmGetContext(IntPtr hWnd);

        [DllImport("imm32.dll")]
        private static extern bool ImmReleaseContext(IntPtr hWnd, IntPtr hIMC);

        [DllImport("imm32.dll")]
        private static extern bool ImmGetConversionStatus(IntPtr hIMC, out int conv, out int sentence);

        private const int IME_CMODE_NATIVE = 0x0001;

        // 返回 1=中文  0=英文  -1=检测不到
        internal static int ImeNativeState()
        {
            try
            {
                IntPtr hwnd = GetConsoleWindow();
                if (hwnd == IntPtr.Zero) return -1;

                IntPtr himc = ImmGetContext(hwnd);
                if (himc == IntPtr.Zero) return -1;

                try
                {
                    int conv;
                    int sentence;
                    if (!ImmGetConversionStatus(himc, out conv, out sentence)) return -1;
                    return ((conv & IME_CMODE_NATIVE) != 0) ? 1 : 0;
                }
                finally
                {
                    ImmReleaseContext(hwnd, himc);
                }
            }
            catch
            {
                return -1;
            }
        }

        internal static bool ImeIsChinese()
        {
            return ImeNativeState() == 1;
        }

        // ==================== 九、裸包名判定 ====================
        // 直接输入 com.x.y 就查它的版本与安装路径。
        //
        // 无损性论证：裸包名发给设备 shell 必然返回 "not found"（没有这种可执行文件），
        // 所以接管它不侵占任何原本有效的输入 —— 和"纯中文启发式"是同一条理由。
        //
        // 排除项：带空格（有参数不猜）、带路径分隔符（是文件）、纯数字目录名、
        //         以数字开头、以及常见的文件扩展名（build.prop / a.log ...）。
        private static readonly string[] FILE_EXTS = new string[]
        {
            ".apk", ".txt", ".log", ".sh", ".prop", ".so", ".xml", ".json",
            ".ini", ".bat", ".ps1", ".zip", ".gz", ".png", ".jpg", ".mp4"
        };

        internal static bool IsMaybePkg(string line)
        {
            if (string.IsNullOrEmpty(line)) return false;
            if (line.Length < 4 || line.Length > 150) return false;
            if (line.IndexOf(' ') >= 0) return false;
            if (line.IndexOf('/') >= 0 || line.IndexOf('\\') >= 0) return false;

            int dots = 0;
            for (int i = 0; i < line.Length; i++)
            {
                char c = line[i];
                bool ok = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z')
                    || (c >= '0' && c <= '9') || c == '.' || c == '_';
                if (!ok) return false;
                if (c == '.') dots++;
            }

            if (dots < 1) return false;
            if (line[0] == '.' || line[line.Length - 1] == '.') return false;
            if (line[0] >= '0' && line[0] <= '9') return false;

            string low = line.ToLowerInvariant();
            for (int i = 0; i < FILE_EXTS.Length; i++)
            {
                if (low.EndsWith(FILE_EXTS[i], StringComparison.Ordinal)) return false;
            }

            return true;
        }

        // ==================== 十、连通性快测 ====================
        // 一条命令确认"设备在、shell 通、耗时多少"，比 devices 更有信息量
        internal static void Ping()
        {
            if (OFFLINE)
            {
                Warn("设备未连接");
                Hint("输入 :r 重连");
                return;
            }

            Echo("ping", "设备连通性");

            System.Diagnostics.Stopwatch sw = System.Diagnostics.Stopwatch.StartNew();
            string o = "";
            string e = "";
            int rc = ShellCall(CUR, "echo ok", out o, out e);
            sw.Stop();

            string t = MergeStream(o, e).Trim();
            if (rc == 0 && t.IndexOf("ok", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                Ok("设备响应正常 · " + sw.ElapsedMilliseconds + " ms · " + (DEVID.Length > 0 ? DEVID : "unknown"));
                CMD_OK = true;
            }
            else
            {
                CMD_OK = false;
                Fail("设备无响应（退出码 " + rc + "）");
                Hint("输入 :rl 重试上次操作，或 :rr 重启 adb 服务");
            }
        }
    }
}
