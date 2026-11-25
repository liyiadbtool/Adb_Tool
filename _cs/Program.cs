// ============================================================================
//  adb 工具 v6 (C# 版) — 设备日志浏览/导出 + 中文意图发送（融合版）
//
//  设计原则（继承 v5，一条都不能破）：
//     1) 输入侧 100% 遵循 adb / shell 原生语法；未识别的输入原样透传给设备
//     2) 工具只做四件事：跨命令保持当前目录 / 相对路径补全 / 输出排版适配 /
//        把"中文"这条最快路径接到意图发送上
//     3) 发送是"附加分支"，不得侵占 adb 与 shell 的命令空间
//
//  融合后的输入规则（优先级从上到下）：
//     ① 整行是电脑路径 C:\XX            -> 把当前目录导出到该路径
//     ② 已知命令 cd/ls/lsf/pull/push/... -> 各自功能（行为与 v5 完全一致）
//     ③ send <文本>                     -> 发送中文意图（显式，零误判）
//     ④ 含中文且首 token 非 ASCII 命令  -> 直接当文本发送（纯中文裸输入原本透传必然报错，故无损）
//     ⑤ 其余                            -> 原样透传给设备 shell
//
//  C# 5.0 兼容（系统自带 csc.exe 是 .NET 4.x 的 C# 5.0，非 Roslyn）：
//     不用 out var / out _ / 局部函数 / => 表达式体 / $"..." / ?. / nameof
//  本文件：配置、入口、主循环、命令分派、历史持久化、通用工具
// ============================================================================
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading;

namespace AdbLogExport
{
    internal static partial class App
    {
        // ==================== 一、配置（可被同目录 adb_log_export.ini 覆盖）====================
        internal static string ADB = "adb";
        // 2026-11-22：adb 是从哪儿来的，供诊断页显示。
        // 现场排查"adb 连不上"时，第一件事就是确认到底用的哪一份 ——
        // 本机经常同时存在 SDK 的一份、platform-tools 解压的一份、
        // 别的工具自带的一份，版本不同会互相抢 5037 端口。
        internal static string ADB_SOURCE = "";
        // 内置 platform-tools 的版本号（读 source.properties 或 adb version 缓存）
        internal static string ADB_BUILTIN_VER = "";
        internal static string SERIAL = "";
        internal static string FFMPEG = "ffmpeg.exe";   // 截帧录屏编码用（ini: ffmpeg=路径）
        // 外挂 scrcpy（R10）：有它就用它开流畅窗口，没有就走内置截帧通道。
        // 默认值 "scrcpy.exe" 表示"没配"，查找逻辑会从程序同级/PATH 自动找。
        internal static string SCRCPY = "scrcpy.exe";
        internal static string ROOT = "/";   // 起始目录：adb 原始位置（2026-11-11 改，原为 /log/android_log/androidlog）
        // 日志目录仍保留给 logs 跳转命令（见 JUMP_LOG），但不再是启动/刷新的默认目录。
        internal static string JUMP_RES = "/iflytek_a/iflytek/res";
        internal static string JUMP_LOG = "/log/android_log/androidlog";
        internal static string JUMP_ANR = "/data/anr";
        internal static string JUMP_DROPBOX = "/data/system/dropbox";
        internal static bool AUTO_ROOT = true;
        internal static bool WATCH_DEV = true;
        internal static int LS_MAXCOL = 10;
        internal static int LS_GAP = 3;
        internal static int LS_WIDTH = 100;
        internal static bool EXPORT_FLAT = false;
        internal static int EXPORT_ZIP = 2;              // 0=不打包 1=总是打包 2=超阈值才打包
        internal static int EXPORT_ZIP_MIN = 100;        // 文件数达到这个数才打包（配合 export_zip=2）
        internal static int RECONN_TRY = 5;
        internal static bool LS_COLOR = true;            // ls 目录/文件着色
        internal static bool ECHO_ACTION = true;         // 隐式判定时回显"工具怎么理解这条输入"
        internal static bool CD_LS = true;               // cd 之后是否自动列目录
        // 【2026-11-13】cd 到目录后不再自动 ls。
        // 用户原话："指令输入页执行 cd 到目录的时候不要执行 ls"。
        // 单独一个开关而不是改 CD_LS：r / 刷新也需要列一次目录（那些地方保留）。
        internal static readonly bool CD_LISTS_AFTER = false;
        internal static int WAIT_HINT_MS = 300;          // 超过多少毫秒才显示等待指示
        // 提示符样式：0=设备号 + 目录（默认，停在 root 时只显示设备号）
        //             1=只显示设备号   2=只显示目录（v7.13 及更早的老样式）
        internal static int PROMPT_MODE = 0;

        // ---- 发送子系统配置 ----
        internal static string ACTION = "android.intent.action.VIEW";
        internal static string URI_PREFIX = "sr://syncore.vpa.sr/test?text=";
        internal static int RETRY = 1;                    // 单条发送失败重试次数，0=不重试
        internal static string AM_CMD = "startservice";    // startservice / start / start-foreground-service
        internal static string COMPONENT = "";             // 形如 com.pkg/.Svc，填了就加 -n
        internal static bool BATCH_STOP_ON_ERROR = false;  // 批量遇错是否立即停止
        internal static string[] QUICK = new string[10];   // QUICK[1..9] 常用语

        // ==================== 二、运行时状态 ====================
        internal static string CUR = "/";
        internal static string OLDPWD = "";
        internal static int LSW = 0;              // 窗口宽度，会话内只取一次
        internal static int DEVN = 0;             // 在线设备数（按序列号去重）
        internal static int DEVOTHER = 0;         // 离线/未授权设备数（不计入 DEVN）
        internal static volatile bool CTRL_C_PRESSED = false;
        internal static string DEVID = "";        // 当前设备序列号

        // 诊断轨迹钩子：GUI 里接到 GuiEntry.Trace（写 gui_trace.log），
        // CLI 里恒为 null（不影响控制台输出）。
        // 后台能力（设备监听 / 自动重连）出问题时，没有这条线索就只能靠猜。
        internal static Action<string> TRACE_HOOK = null;

        // 2026-11-15 闪退修复：GUI 模式标记。命令框输入 q/quit/exit 时若走
        // Environment.Exit(0) 会把整个窗口无提示干掉（不写任何日志）——
        // 这正是"工具开着开着突然消失"的最可能根因。GUI 下必须拒绝硬退出。
        internal static volatile bool GUI_MODE = false;

        // 2026-11-15（网联服务）：长等待类内置命令的"可中断"标志。
        // :sxlog 等设备重启最多要空转 60 秒；GUI 点「停止」走的是 kill 当前 adb 进程，
        // 纯 sleep 轮询不受影响 —— 所以另立一个标志，由 GuiWeb.StopWorker 置位、
        // SubmitCmd 清零、等待循环里每 2 秒读一次。
        internal static volatile bool GUISTOP = false;

        internal static void Trace(string msg)
        {
            Action<string> h = TRACE_HOOK;
            if (h == null) return;
            try { h(msg); } catch { }
        }
        // 需求1（并行多命令）：CMD_OK 改成线程本地。
        // 原来全局单例，真并行时两个 worker 会互相覆盖"上一条命令是否成功"，
        // 导致结果串位。用 [ThreadStatic] 让每个 worker 线程各持一份，
        // 无需改动其余 70+ 处引用。注意：主线程初值为 true，worker 线程默认 false，
        // 但 Dispatch 入口会立即重置为 false，语义不变。
        [ThreadStatic]
        internal static bool CMD_OK = true;       // 上一条命令是否成功（用于跳过设备探测）
        // 需求1（并行多命令）：当前 worker 线程属于哪个输入框槽位（0/1/2）。
        // [ThreadStatic] 让每个 worker 线程各记一份，GuiSink 据此给输出行打槽位标记，
        // 前端才能把并行命令的输出路由到各自独立的输出区。
        [ThreadStatic]
        internal static int CUR_SLOT = 0;
        // 槽位总数：GUI 的 MAX_SLOT、Adb 的运行中进程表都以它为唯一来源，
        // 避免"改了一处忘了另一处"（原来 MAX_SLOT 是 GuiWeb 里的私有常量）。
        internal const int SLOT_COUNT = 3;
        internal static bool OFFLINE = false;
        internal static bool CONFLICT = false;
        internal static bool PERMOK = true;
        internal static string PEND_K = "";       // 待重试的操作类型 CD/LS/PULL
        internal static string LAST_CMD = "";      // 上一条真正执行过的命令（不含 rl）
        internal static string LAST_FAIL_CMD = ""; // 上一条失败的命令，rl 优先重跑它
        internal static System.Func<string, string> IdleHook;  // 空闲钩子：返回新提示符，null=无变化
        private static long LAST_IDLE_PROBE = -100000;
        private static long LAST_ONLINE_PROBE = 0;
        private static int HANG_COUNT = 0;             // 连续探测超时次数（2 次才判定僵死）
        private static long LAST_RECOVER_AT = 0;       // 上次急救时间（20 秒冷却，防止连杀）
        internal static string PEND_R = "";
        internal static string PEND_N = "";
        internal static string PEND_A = "";
        internal static bool PERF = false;        // 打印每条命令耗时
        internal static bool SELFTEST = false;
        internal static bool VERBOSE = false;     // 打印实际下发的 adb 命令
        internal static bool INTERACTIVE = true;  // stdin 是否可交互（决定是否记历史）
        // 是否把命令追加进历史文件。与 INTERACTIVE 分开：GUI 没有 stdin，
        // 但显然应该记历史。默认跟随 INTERACTIVE，由入口各自覆盖。
        internal static bool RECORD_HIST = true;
        internal static int INPUT_MODE = 0;       // 0=编辑 1=中文常驻 2=中文一次
        internal static bool INPUT_AUTO = false;  // 跟随系统输入法状态
        internal static bool IME_ACTIVE = false;  // 本行实际走 ReadLine（Prompt 时算好）
        internal static bool SUPPRESS_PROMPT = false; // 内部批量循环时压制"读取中"

        internal static readonly List<string> Hist = new List<string>();

        // ==================== 三、入口 ====================
        // ==================== GUI 入口的初始化（v8.0）====================
        //
        // 与 Main 的区别，只有一条原则：**不碰控制台**。
        //   · 不调 SetupConsole —— 它会改窗口大小/标题，GUI 进程没有那个窗口
        //   · 不调 ConsoleUtil.Init —— 那是给控制台开 QuickEdit 的
        //   · 不调 HookCtrlC —— GUI 由窗体自己管键盘
        //   · 不调 InitEnv —— 它会阻塞几秒，交给窗体在后台线程里做
        // 其余（读 ini、定位 adb、加载主题色、加载自定义命令）完全一致，
        // 所以 GUI 里的命令语义与命令行版逐字相同。
        internal static void GuiBoot(string[] args)
        {
            InstallCrashLog();
            LoadIni();
            ResolveAdb();
            ApplyTheme(LIGHT_THEME);
            LoadCmds();

            // 控制台相关状态在 GUI 下固定成"非交互"，避免行编辑逻辑被触发
            INTERACTIVE = false;
            SUPPRESS_PROMPT = true;
            // 但历史照记：GUI 是人在敲，和"管道喂输入"不是一回事
            RECORD_HIST = true;

            // 历史记录共用同一个文件：命令行敲过的命令，GUI 里按 ↑ 也能翻到
            LoadHistory();

            Bg.Start();
        }

        internal static int Main(string[] args)
        {
            SetupConsole();
            ConsoleUtil.Init();          // 打开 QuickEdit：滚轮上滑 / 拖选复制 / 右键粘贴都靠它
            InstallCrashLog();
            LoadIni();
            ResolveAdb();                // adb 不在 PATH 时按常见位置兜底
            ApplyTheme(LIGHT_THEME);
            LoadCmds();
            if (!ParseArgs(args)) return 2;
            if (SELFTEST) return SelfTest();

            try { INTERACTIVE = !Console.IsInputRedirected; }
            catch { INTERACTIVE = false; }
            // 命令行版：与旧行为完全一致 —— 管道喂输入时不记历史
            RECORD_HIST = INTERACTIVE;
            LoadHistory();
            HookCtrlC();

            // 后台探测线程：设备巡检一律在这里跑，输入线程不再碰 adb
            Bg.Start();
            IdleHook = IdleTick;

            if (!InitEnv())
            {
                // 不退出：进入离线模式，仍可看帮助、看命令、重试连接
                OFFLINE = true;
                OfflineBanner();
            }
            MainLoop();
            return 0;
        }

        // adb 定位：ini 没写死路径时，别指望用户配好 PATH。
        // 现场大量机器是"platform-tools 解压在某个目录、adb 没进 PATH"，
        // 旧版直接报"无法执行 adb"就废了 —— 这里按常见位置挨个找。
        private static void ResolveAdb()
        {
            if (string.IsNullOrEmpty(ADB)) ADB = "adb";

            // 带路径（相对/绝对）就尊重它，不再猜
            if (ADB.IndexOf('\\') >= 0 || ADB.IndexOf('/') >= 0 || ADB.IndexOf(':') >= 0) return;
            if (!string.Equals(ADB, "adb", StringComparison.OrdinalIgnoreCase)
                && !string.Equals(ADB, "adb.exe", StringComparison.OrdinalIgnoreCase)) return;

            List<string> cands = new List<string>();

            // 0) PATH 里的 adb 优先。
            //
            // 这是 v7.13 补的第一条，也是"经常断线、断线后搜不到设备"的一个
            // 环境级根因：Windows 上的 adb server 是全局共享的（固定 5037 端口），
            // 由第一个连上来的客户端启动。如果本工具选了 A 目录的 adb，
            // 而用户平时在命令行敲的是 PATH 里 B 目录的 adb，两边版本一旦不同，
            // 每次调用都会出现
            //     adb server version (41) doesn't match this client (39); killing...
            // 也就是"客户端把正在用的 server 杀掉重起" —— 表现就是随机断线、
            // 隔一会儿又搜不到设备。
            //
            // 现场实测就踩到了：PATH 是 platform-tools 37.0.0，
            // 而旧逻辑按 LOCALAPPDATA 找到了另一个 SDK 里的旧版。
            string pathEnv = Environment.GetEnvironmentVariable("PATH");
            if (!string.IsNullOrEmpty(pathEnv))
            {
                string[] dirs = pathEnv.Split(';');
                for (int i = 0; i < dirs.Length; i++)
                {
                    string d = dirs[i].Trim().Trim('"');
                    if (d.Length == 0) continue;
                    try
                    {
                        string cand = Path.Combine(d, "adb.exe");
                        if (File.Exists(cand)) { ADB = cand; ADB_SOURCE = "系统 PATH"; return; }
                    }
                    catch { }
                }
            }

            // 1) 程序自己目录（绿色版常把 adb.exe 放旁边）
            try { cands.Add(Path.Combine(ExeDir(), "adb.exe")); } catch { }
            // 2026-11-23：绿色包自带 platform-tools\adb.exe —— 解压即用，
            // 不要求目标机器装过 Android SDK（原先只找 exe 同级，包里放子目录就找不到）。
            try { cands.Add(Path.Combine(Path.Combine(ExeDir(), "platform-tools"), "adb.exe")); } catch { }
            // 2) 环境变量里的 SDK
            string[] envs = { "ANDROID_HOME", "ANDROID_SDK_ROOT", "ANDROID_SDK_HOME" };
            for (int i = 0; i < envs.Length; i++)
            {
                string root = Environment.GetEnvironmentVariable(envs[i]);
                if (!string.IsNullOrEmpty(root))
                    cands.Add(Path.Combine(root, "platform-tools", "adb.exe"));
            }

            // 3) 默认安装位置
            string local = Environment.GetEnvironmentVariable("LOCALAPPDATA");
            if (!string.IsNullOrEmpty(local))
            {
                cands.Add(Path.Combine(local, "Android", "Sdk", "platform-tools", "adb.exe"));
                cands.Add(Path.Combine(local, "Android", "Sdk", "platform-tools", "adb"));
            }
            string user = Environment.GetEnvironmentVariable("USERPROFILE");
            if (!string.IsNullOrEmpty(user))
                cands.Add(Path.Combine(user, "AppData", "Local", "Android", "Sdk",
                                      "platform-tools", "adb.exe"));

            // 4) 盘根上的常见解压位置
            string[] drv = { "C:", "D:", "E:", "F:" };
            for (int i = 0; i < drv.Length; i++)
            {
                cands.Add(drv[i] + "\\platform-tools\\adb.exe");
                cands.Add(drv[i] + "\\adb\\adb.exe");
                cands.Add(drv[i] + "\\Android\\platform-tools\\adb.exe");
                cands.Add(drv[i] + "\\Program Files\\platform-tools\\adb.exe");
            }

            // 5) 内置 platform-tools（2026-11-22）
            //
            // 为什么放在**最后**而不是最前：
            //   Windows 的 adb server 是全局单例（固定 5037 端口），由第一个
            //   连上来的客户端启动。如果本工具用内置的那份（版本固定），
            //   而用户平时在命令行用 PATH 里的另一份，两边版本不一致就会
            //       adb server version (41) doesn't match this client (39); killing...
            //   —— 客户端反复杀掉正在用的 server 重启，表现就是随机断线。
            //   （见上面第 0 条注释里记的那个现场问题。）
            //   所以：用户环境有 adb 就用他的，一份都没有才用内置的兜底，
            //   这样不会去抢别人正在用的 server。
            try
            {
                cands.Add(Path.Combine(ExeDir(), Path.Combine("platform-tools", "adb.exe")));
            }
            catch { }

            for (int i = 0; i < cands.Count; i++)
            {
                try
                {
                    if (File.Exists(cands[i]))
                    {
                        ADB = cands[i];
                        ADB_SOURCE = SourceOf(cands[i]);
                        return;
                    }
                }
                catch { }
            }

            // 一份都没找到：仍然保留 "adb"（PATH 里可能有但读不到），
            // 由调用方报错。诊断页会显示"未安装"，并提供内置一键安装。
            ADB_SOURCE = "未找到";
        }

        // 把候选路径翻译成人能看懂的中文来源，供诊断页显示。
        private static string SourceOf(string path)
        {
            try
            {
                string exe = ExeDir();
                if (!string.IsNullOrEmpty(exe)
                    && path.StartsWith(exe, StringComparison.OrdinalIgnoreCase))
                {
                    // 程序目录下还要再区分「绿色版放旁边」和「内置 platform-tools」
                    if (path.IndexOf("platform-tools", StringComparison.OrdinalIgnoreCase) >= 0)
                        return "内置 platform-tools";
                    return "程序目录";
                }
                if (path.IndexOf("Android\\Sdk", StringComparison.OrdinalIgnoreCase) >= 0
                    || path.IndexOf("Android/Sdk", StringComparison.OrdinalIgnoreCase) >= 0)
                    return "Android SDK";
            }
            catch { }
            return "常见安装位置";
        }

        // 双击启动时崩溃不会有任何提示，窗口一闪就没了 —— 至少落一份现场
        private static void InstallCrashLog()        {
            try
            {
                AppDomain.CurrentDomain.UnhandledException += new UnhandledExceptionEventHandler(
                    delegate(object sender, UnhandledExceptionEventArgs e)
                    {
                        try
                        {
                            string p = Path.Combine(ExeDir(), "adb_log_export_error.log");
                            File.AppendAllText(
                                p,
                                DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "  "
                                + (e.ExceptionObject == null ? "unknown" : e.ExceptionObject.ToString())
                                + Environment.NewLine + Environment.NewLine,
                                Encoding.UTF8);
                        }
                        catch { }
                    });
            }
            catch { }
        }

        private static void SetupConsole()
        {
            // 中文 Windows 控制台默认代码页是 GBK(936)，Console.OutputEncoding 默认就是 GBK，
            // 直接用它输出中文即可正确显示，不必 chcp。这里不做任何改动，避免引入乱码。
            Util.SetTitle("adb 工具 v6  [日志导出 + 中文发送]");
        }

        // ==================== 四、配置读取 ====================
        // 同目录 ini：key=value，# 与 ; 开头为注释。
        // 向后兼容：主 ini 不存在时，回退读老 adb_send_chinese.ini 的发送项。
        private static void LoadIni()
        {
            string dir = ExeDir();

            string path = Path.Combine(dir, "adb_log_export.ini");
            if (File.Exists(path)) ParseIniFile(path, false);

            string sendIni = Path.Combine(dir, "adb_send_chinese.ini");
            if (!File.Exists(path) && File.Exists(sendIni)) ParseIniFile(sendIni, true);
        }

        // legacy=true 表示这是老的发送工具 ini，只取发送相关键
        private static void ParseIniFile(string path, bool legacy)
        {
            string[] lines;
            try { lines = File.ReadAllLines(path, Encoding.UTF8); }
            catch { return; }

            foreach (string raw in lines)
            {
                string s = raw.Trim();
                if (s.Length == 0) continue;
                if (s[0] == '#' || s[0] == ';' || s[0] == '[') continue;
                int eq = s.IndexOf('=');
                if (eq <= 0) continue;
                string k = s.Substring(0, eq).Trim().ToLowerInvariant();
                string v = s.Substring(eq + 1).Trim();

                if (!legacy)
                {
                    switch (k)
                    {
                        case "adb": ADB = v; break;
                        // hdc（HarmonyOS Device Connector）路径。
                        // 只在清 HiCar 历史设备 / 列 hdc 设备时用到，
                        // 所以默认留空 —— 让 Hdc.ResolveHdc() 走"exe 同级 -> PATH"
                        // 的自动查找，绝大多数人不需要配。
                        // 【为什么必须有这个 case】Hdc.cs 的注释和运行期提示都写着
                        // "可在 ini 里配 hdc=路径"，但此前这个 case 根本不存在，
                        // 用户照着提示配了也不生效，只能靠把 hdc.exe 塞进 PATH 绕过。
                        case "hdc": HDC = v; break;
                        case "ffmpeg": FFMPEG = v; break;
                        case "scrcpy": SCRCPY = v; break;
                        case "serial": SERIAL = v; break;
                        case "root": if (v.Length > 0) ROOT = v; break;
                        case "jump_res": JUMP_RES = v; break;
                        case "jump_log": JUMP_LOG = v; break;
                        case "jump_anr": JUMP_ANR = v; break;
                        case "jump_dropbox": JUMP_DROPBOX = v; break;
                        case "auto_root": AUTO_ROOT = IsTrue(v); break;
                        case "watch_dev": WATCH_DEV = IsTrue(v); break;
                        case "ls_maxcol": LS_MAXCOL = ToInt(v, LS_MAXCOL); break;
                        case "ls_gap": LS_GAP = ToInt(v, LS_GAP); break;
                        case "ls_width": LS_WIDTH = ToInt(v, LS_WIDTH); break;
                        case "ls_color": LS_COLOR = IsTrue(v); break;
                        case "color": COLOR = IsTrue(v); break;
                        case "echo_action": ECHO_ACTION = IsTrue(v); break;
                        case "theme":
                            {
                                string tv = (v == null ? "" : v.Trim().ToLowerInvariant());
                                if (tv != "light" && tv != "eye") tv = "dark";
                                THEME = tv;
                                LIGHT_THEME = (tv == "light");
                            }
                            break;
                        case "accent":
                            {
                                // 2026-11-15（A17）：13 色强调色，非法值回退蓝。
                                // white / black 是旧版的名字，已合并成 graphite（石墨）——
                                // 老 ini 里存着的值必须能读进来，否则升级后强调色静默丢失。
                                /* ★ 2026-11-23（第 26 批）：**读取端也要认 HEX**。
                                   这是"切换强调色后启动又变蓝"的确切根因：
                                     · 写入端 NormalizeAccent 已支持 #RRGGBB → ini 存下 "#A7B1A3"
                                     · 读取端这里还是旧的 16 色白名单 → 不认 HEX → 回退 blue
                                   于是 ini 里明明写着用户选的颜色，启动却永远回到蓝。 */
                                string av = (v == null ? "" : v.Trim());
                                if (av.Length == 7 && av[0] == '#'
                                    && System.Text.RegularExpressions.Regex.IsMatch(av, "^#[0-9A-Fa-f]{6}$"))
                                {
                                    ACCENT = av.ToUpperInvariant();
                                    break;
                                }
                                av = av.ToLowerInvariant();
                                if (av == "white" || av == "black") av = "graphite";
                                if ("|blue|cyan|teal|mint|green|yellow|orange|red|pink|purple|indigo|brown|graphite|purewhite|eyewhite|glasswhite|"
                                    .IndexOf("|" + av + "|", StringComparison.Ordinal) < 0) av = "blue";
                                ACCENT = av;
                            }
                            break;
                        case "prefs":
                            // 字体 / 字号 / 动效（base64 不透明串），原样存回
                            PREFS = v == null ? "" : v.Trim();
                            break;
                        case "legacy_alias": LEGACY_ALIAS = IsTrue(v); break;
                        case "input":
                            {
                                string iv = v.Trim().ToLowerInvariant();
                                if (iv == "ime" || iv == "cn") { INPUT_MODE = 1; INPUT_AUTO = false; }
                                else if (iv == "auto") { INPUT_MODE = 0; INPUT_AUTO = true; }
                                else { INPUT_MODE = 0; INPUT_AUTO = false; }
                            }
                            break;
                        case "cd_ls": CD_LS = IsTrue(v); break;
                        // 提示符样式，见 Prompt() 头注释
                        //   dev  = 设备号 + 目录（默认，dev 指"设备号为主"）
                        //   id   = 只显示设备号
                        //   path = 只显示目录
                        case "prompt":
                            {
                                string pv = v.Trim().ToLowerInvariant();
                                if (pv == "id" || pv == "only" || pv == "devonly") PROMPT_MODE = 1;
                                else if (pv == "path" || pv == "dir" || pv == "old") PROMPT_MODE = 2;
                                else PROMPT_MODE = 0;      // dev / 空 / 其他 -> 默认
                            }
                            break;
                        case "wait_hint_ms": WAIT_HINT_MS = ToInt(v, WAIT_HINT_MS); break;
                        // 普通 adb 命令的默认超时（毫秒，0=不限制）。防的是唤醒后
                        // adb 卡在失效 USB 句柄上把界面一起拖死。
                        case "timeout_ms": CALL_TIMEOUT_MS = ToInt(v, CALL_TIMEOUT_MS); break;
                        // 后台探活单次上限（毫秒）。太大会让"设备掉了"发现得慢，
                        // 太小会在慢机器上误判超时，4 秒是实测比较稳的值。
                        case "probe_ms": Bg.PROBE_TIMEOUT_MS = ToInt(v, Bg.PROBE_TIMEOUT_MS); break;
                        // 控制台 QuickEdit：1=保留鼠标滚轮/拖选复制/右键粘贴（默认），
                        // 0=关掉（鼠标不再抢焦点，但也复制不了东西）。
                        case "quick_edit":
                            ConsoleUtil.QuickEdit = IsTrue(v);
                            ConsoleUtil.Refresh();
                            break;
                        case "export_flat": EXPORT_FLAT = IsTrue(v); break;
                        case "export_zip": EXPORT_ZIP = ToInt(v, EXPORT_ZIP); break;
                        case "export_zip_min": EXPORT_ZIP_MIN = ToInt(v, EXPORT_ZIP_MIN); break;
                        case "reconn_try": RECONN_TRY = ToInt(v, RECONN_TRY); break;
                        case "batch_stop_on_error": BATCH_STOP_ON_ERROR = IsTrue(v); break;
                        case "env_prop_deploy": ENV_P_DEPLOY = v; break;
                        case "env_prop_https": ENV_P_HTTPS = v; break;
                        case "env_prop_domain": ENV_P_DOMAIN = v; break;
                    }

                    // env_xxx=deploy值;https值;domain值   （xxx 是环境名，如 test / pre / dev）
                    // 排除 env_prop_* 这类属性名配置
                    if (k.Length > 4 && k.Substring(0, 4) == "env_" && k.IndexOf("prop_") < 0)
                    {
                        LoadEnvProfile(k.Substring(4), v);
                    }
                }

                // 发送相关键（两个文件都认）
                switch (k)
                {
                    case "action": ACTION = v; break;
                    case "uri_prefix": URI_PREFIX = v; break;
                    case "retry": RETRY = ToInt(v, RETRY); break;
                    case "am_cmd": if (v.Length > 0) AM_CMD = v; break;
                    case "component": COMPONENT = v; break;
                    case "app": APP_PKG = v; break;
                    case "version_pkgs": LoadVerPkgs(v); break;

                    // ---- 语音助手（:vr）----
                    case "vr_wake_type": if (v.Length > 0) VR_WAKE_TYPE = v; break;
                    case "vr_wake_type_alt": if (v.Length > 0) VR_WAKE_TYPE_ALT = v; break;
                    case "vr_pkg": if (v.Length > 0) VR_PKG = v; break;
                    case "vr_vr_uri": if (v.Length > 0) VR_VR_URI = v; break;
                    case "vr_sr_uri": if (v.Length > 0) VR_SR_URI = v; break;
                    case "vr_text_max": VR_TEXT_MAX = ToInt(v, VR_TEXT_MAX); break;
                    case "vr_ts_service": if (v.Length > 0) VR_TS_SERVICE = v; break;
                    case "vr_ts_package": if (v.Length > 0) VR_TS_PACKAGE = v; break;
                    case "quick_1": QUICK[1] = v; break;
                    case "quick_2": QUICK[2] = v; break;
                    case "quick_3": QUICK[3] = v; break;
                    case "quick_4": QUICK[4] = v; break;
                    case "quick_5": QUICK[5] = v; break;
                    case "quick_6": QUICK[6] = v; break;
                    case "quick_7": QUICK[7] = v; break;
                    case "quick_8": QUICK[8] = v; break;
                    case "quick_9": QUICK[9] = v; break;
                }
            }
        }

        // 1/true/yes/on 都算真；其余算假
        private static bool IsTrue(string v)
        {
            if (v == null) return false;
            string t = v.Trim().ToLowerInvariant();
            return t == "1" || t == "true" || t == "yes" || t == "on";
        }

        internal static int ToInt(string s, int def)
        {
            int t;
            if (int.TryParse(s, out t)) return t;
            return def;
        }

        /* ★ 2026-11-23（第 26 批）：**exe 目录必须用进程真实路径**。
           ------------------------------------------------------------------
           症状：白天切黑夜 → 关闭 → 再打开还是白天；强调色/字号也一样。
           根因：单文件发布下 Assembly.GetExecutingAssembly().Location 可能返回空，
                回退到 Environment.CurrentDirectory —— 那是"启动时的工作目录"，
                未必是 exe 所在目录。于是 ini 读不到 → 全部用默认值（light + blue），
                用户改的设置看起来"没保存"。
           修法：优先 ProcessPath / MainModule.FileName（总是真实 exe 路径）。
           ------------------------------------------------------------------ */
        internal static string ExeDir()
        {
            // 本项目是 .NET Framework，没有 Environment.ProcessPath，
            // 直接用 MainModule.FileName（总是真实 exe 路径，不受单文件解压影响）。
            try
            {
                string mm = System.Diagnostics.Process.GetCurrentProcess().MainModule.FileName;
                if (!string.IsNullOrEmpty(mm)) return Path.GetDirectoryName(mm);
            }
            catch { }
            try
            {
                string d = Path.GetDirectoryName(System.Reflection.Assembly.GetExecutingAssembly().Location);
                if (!string.IsNullOrEmpty(d)) return d;
            }
            catch { }
            return Environment.CurrentDirectory;
        }

        private static bool ParseArgs(string[] args)
        {
            for (int i = 0; i < args.Length; i++)
            {
                string a = args[i];
                if (string.Equals(a, "-perf", StringComparison.OrdinalIgnoreCase)) { PERF = true; continue; }
                if (string.Equals(a, "-v", StringComparison.OrdinalIgnoreCase)) { VERBOSE = true; continue; }
                if (string.Equals(a, "-selftest", StringComparison.OrdinalIgnoreCase)) { SELFTEST = true; continue; }
                // 2026-11-20（P3）：-casttest / -castserve / -castprobe 随投屏通道一起删除
                if (string.Equals(a, "-adb", StringComparison.OrdinalIgnoreCase))
                {
                    if (i + 1 >= args.Length) { Console.WriteLine("缺少 -adb 的路径参数"); return false; }
                    ADB = args[++i]; continue;
                }
                if (string.Equals(a, "-s", StringComparison.OrdinalIgnoreCase))
                {
                    if (i + 1 >= args.Length) { Console.WriteLine("缺少 -s 的序列号参数"); return false; }
                    SERIAL = args[++i]; continue;
                }
                if (a == "-h" || a == "--help" || a == "/?")
                {
                    Console.WriteLine("用法: adb_log_export.exe [-adb <adb路径>] [-s <序列号>] [-perf] [-v] [-selftest]");
                    return false;
                }
            }
            return true;
        }

        // ==================== 五、Ctrl+C：中断当前 adb 操作 ====================
        // 行编辑期间 ReadKey 已截获 Ctrl+C（清空当前行），不会走到这里；
        // 只有在 adb 长操作（pull 大目录、ls 大目录）执行中按 Ctrl+C 才触发，用于杀掉子进程。
        private static void HookCtrlC()
        {
            try
            {
                Console.CancelKeyPress += new ConsoleCancelEventHandler(delegate(object sender, ConsoleCancelEventArgs e)
                {
                    // 永远不因为 Ctrl+C 退出程序：控制台程序的惯例是"取消当前动作"，
                    // 退出用 :q。原来只在有子进程时才 Cancel，空输入按 Ctrl+C 会直接退。
                    e.Cancel = true;
                    CTRL_C_PRESSED = true;

                    // 并行多命令时可能有多个子进程，逐个杀（GUI 的"停止"走 KillRunning(slot)）
                    if (KillAllRunning())
                    {
                        Console.WriteLine();
                        Console.WriteLine("  [中断] 已取消当前操作");
                    }
                });
            }
            catch { }
        }

        // ==================== 六、历史持久化 ====================
        private static string HistPath()
        {
            // 2026-11-19：发布包结构改成 exe + internal\ + log\，历史文件这种运行期
            // 产物不该躺在根目录（一个点文件很碍眼）。有 log\ 就往里放，没有则保持旧行为。
            try
            {
                string lg = Path.Combine(ExeDir(), "log");
                if (Directory.Exists(lg)) return Path.Combine(lg, ".adb_tool_history");
            }
            catch { }
            return Path.Combine(ExeDir(), ".adb_tool_history");
        }

        // 只保留最近 500 条，避免文件无限增长
        private static void LoadHistory()
        {
            try
            {
                string p = HistPath();
                if (!File.Exists(p)) return;
                string[] lines = File.ReadAllLines(p, Encoding.UTF8);
                int start = lines.Length - 500;
                if (start < 0) start = 0;
                for (int i = start; i < lines.Length; i++)
                {
                    string l = lines[i];
                    if (l != null && l.Trim().Length > 0) Hist.Add(l);
                }
            }
            catch { }
        }

        // 每条命令追加落盘：即使崩溃也不丢历史
        //
        // 【v8.0】门禁从 INTERACTIVE 拆成独立开关 RECORD_HIST。
        // 原来这里判断 INTERACTIVE（= stdin 是否重定向），但 GUI 进程压根没有 stdin，
        // INTERACTIVE 必然为 false —— 如果继续用同一个变量，GUI 里敲过的命令
        // 永远写不进历史，与"完全保留现有能力"相悖。
        // 现在两者含义分开：INTERACTIVE 管行编辑/提示符回执，RECORD_HIST 管要不要记历史。
        internal static void AppendHistory(string line)
        {
            if (!RECORD_HIST) return;   // 管道喂输入时不记，避免污染
            string t = line.Trim();
            if (t.Length == 0) return;
            try { File.AppendAllText(HistPath(), t + "\r\n", new UTF8Encoding(false)); }
            catch { }
        }

        // ==================== 七、主循环 ====================
        // 提示符：设备号 [: 目录] + 箭头
        //
        // 要点（v7.14，按现场反馈改）：
        //   1) 停在起始目录时只显示【设备号】—— 一眼确认"我现在操作的是哪台车机"。
        //      旧版这里写的是目录末段 "androidlog"，两台设备同时插着时完全分不清。
        //   2) cd 进任何目录后显示【设备号 : 目录】—— 设备没变、位置变了，两个信息都在。
        //   3) 起始目录本身不重复显示（它就是 ini 里的 root，属于"出厂设置"，不是位置）。
        //   4) 总宽有上限：超了就把目录压成末段，绝不让提示符吃掉半行。
        //
        // 完整路径在标题栏常驻（零占行），所以这里可以放心只给摘要。
        private const int PROMPT_MAX_W = 38;   // 提示符正文（不含 " > "）的宽度上限

        // 提示符里显示的设备标识
        private static string PromptDev()
        {
            if (!string.IsNullOrEmpty(DEVID)) return DEVID;
            return DEVN > 0 ? "(未知)" : "(无设备)";
        }

        // 提示符里显示的目录：起始目录返回空串（只显示设备号）
        //
        // 抽成纯函数（dev / cur / root 全部当参数传）：这样自检能直接喂数据，
        // 不用连真机，也不会被当前全局状态干扰。
        internal static string PromptDirFor(string cur, string root)
        {
            if (string.IsNullOrEmpty(cur)) return "";
            string c = cur.Length > 1 ? cur.TrimEnd('/') : cur;
            if (c == "/") return "";

            // 尾斜杠不该影响"这是不是起始目录"的判断（ini 里手写 root 常带尾斜杠）
            string r = string.IsNullOrEmpty(root) ? "" : (root.Length > 1 ? root.TrimEnd('/') : root);
            if (r.Length > 0 && string.Equals(c, r, StringComparison.OrdinalIgnoreCase))
                return "";                            // 就在 ini 的 root 上：只显示设备号

            // 已经够短：照实给完整路径（/data/anr 这种反而最清楚）
            if (DispWidth(c) <= 22) return c;

            // 长路径：末两段 + "…/" 前缀。
            //
            // 这里**不用**"相对 root 的路径"：那会得到 "/288" 这种以斜杠开头的串，
            // 看起来像是根目录下的 288，比截断更容易误导。
            // "…/" 前缀的含义无歧义：前面还有，只是没显示。
            string tail = LastSeg(c);
            string parent = LastSeg(ParentOf(c));
            if (parent.Length > 0 && parent != "/" && tail != "/")
                return "\u2026/" + parent + "/" + tail;
            return "\u2026/" + tail;
        }

        // 提示符正文（不含 " > "）。纯函数：不读全局状态，可单测。
        //
        // mode 0 = 设备号[: 目录]   1 = 只设备号   2 = 只目录
        internal static string PromptBody(int mode, string dev, string cur, string root)
        {
            if (mode == 1)
            {
                return dev.Length > 0 ? dev : "(无设备)";
            }

            if (mode == 2)
            {
                string d2 = PromptDirFor(cur, root);
                return d2.Length > 0 ? d2 : LastSeg(cur);
            }

            string dv = dev.Length > 0 ? dev : "(无设备)";
            string dir = PromptDirFor(cur, root);
            if (dir.Length == 0) return dv;
            return dv + ":" + dir;
        }

        // 超宽时的兜底：只留 设备号:末段
        internal static string PromptBodyTight(string dev, string cur)
        {
            string dv = dev.Length > 0 ? dev : "(无设备)";
            string tail = LastSeg(cur);
            if (tail.Length == 0 || tail == "/") return dv;
            return dv + ":" + tail;
        }

        private static string Prompt()
        {
            // 先定这一行走哪条读法：:ime / input=auto 都要在打印提示符前算好
            IME_ACTIVE = (INPUT_MODE == 1 || INPUT_MODE == 2);
            if (!IME_ACTIVE && INPUT_AUTO && !OFFLINE) IME_ACTIVE = ImeIsChinese();

            // 分段着色的下标每次重建：任何一个 return 分支漏设，都会让
            // DrawPrompt 拿着上一轮的旧下标去切新串（颜色错位比不彩色更难看）。
            PROMPT_DEV_AT = -1;
            PROMPT_DEV_LEN = 0;
            PROMPT_DIR_AT = -1;
            PROMPT_DIR_LEN = 0;

            // 离线：保留上次的设备号，比光秃秃一句"(离线)"有用得多
            if (OFFLINE)
            {
                string od = string.IsNullOrEmpty(DEVID) ? "" : (" " + DEVID);
                if (IME_ACTIVE) return "(离线" + od + ") [IME] > ";
                return "(离线" + od + ") > ";
            }

            string dev = PromptDev();
            string body = PromptBody(PROMPT_MODE, dev, CUR, ROOT);
            if (DispWidth(body) > PROMPT_MAX_W) body = PromptBodyTight(dev, CUR);

            string prefix = IME_ACTIVE ? "[IME] " : "";
            body = prefix + body;

            // 在拼好的正文里反查两段的位置（反查比一路手工记下标可靠：
            // 压缩分支走完不需要再重新对齐一遍，也不会漏改某一处长度）。
            int baseAt = prefix.Length;
            if (PROMPT_MODE != 2 && dev.Length > 0 && string.CompareOrdinal(body, baseAt, dev, 0, dev.Length) == 0)
            {
                PROMPT_DEV_AT = baseAt;
                PROMPT_DEV_LEN = dev.Length;
            }

            int colon = body.IndexOf(':', PROMPT_DEV_LEN > 0 ? PROMPT_DEV_AT + PROMPT_DEV_LEN : baseAt);
            if (colon >= 0 && colon < body.Length - 1)
            {
                PROMPT_DIR_AT = colon + 1;
                PROMPT_DIR_LEN = body.Length - colon - 1;
            }
            else if (PROMPT_MODE == 2)
            {
                PROMPT_DIR_AT = baseAt;
                PROMPT_DIR_LEN = body.Length - baseAt;
            }

            return body + " > ";
        }

        // 提示符分段着色的位置（-1 表示该段不存在）
        internal static int PROMPT_DEV_AT = -1;
        internal static int PROMPT_DEV_LEN = 0;
        internal static int PROMPT_DIR_AT = -1;
        internal static int PROMPT_DIR_LEN = 0;

        private static void MainLoop()
        {
            while (true)
            {
                // 上一条命令成功就不探测设备：能成功执行说明设备必然在线
                if (!OFFLINE && WATCH_DEV && !CMD_OK) WatchDev();

                // 离线时每条命令前探一次（内部有 1.2s 节流）：
                // 这样即使当前是中文/IME 模式（没有读键循环），插上设备也能自动连上
                ProbeBeforePrompt();

                string line = Read(Prompt());
                if (line == null)
                {
                    Console.WriteLine("  输入已结束");
                    Pause();
                    return;
                }
                line = NormalizeLead(line.Trim());
                if (line.Length == 0)
                {
                    // 空回车必须给个回执：否则屏幕上什么都不发生变化，
                    // 看起来就像程序卡住没响应。这里打一行当前状态，信息量最低但可见。
                    ShowQuickStatus();
                    continue;
                }

                AppendHistory(line);

                // rl 自己不算"上一条命令"，否则第二次 rl 只会重跑 rl
                string lc = line.ToLowerInvariant();
                bool isRetry = (lc == "rl" || lc == ":rl");

                Stopwatch sw = null;
                if (PERF) { sw = Stopwatch.StartNew(); }

                try { Dispatch(line); }
                catch (Exception ex)
                {
                    Fail("内部错误：" + ex.Message);
                    CMD_OK = false;
            // 2026-11-25：记录本条指令 id，供 OutDir 决定用自定义还是默认导出目录
            try
            {
                string t0 = (line ?? "").Trim();
                if (t0.StartsWith(":")) t0 = t0.Substring(1);
                int sp0 = t0.IndexOf(' ');
                CUR_EXPORT_ID = (sp0 > 0 ? t0.Substring(0, sp0) : t0).Trim().ToLowerInvariant();
            }
            catch { }
                }

                if (sw != null)
                {
                    sw.Stop();
                    Console.WriteLine("  [perf] " + line + " -> " + sw.ElapsedMilliseconds + " ms");
                }

                if (!isRetry)
                {
                    LAST_CMD = line;
                    if (!CMD_OK) LAST_FAIL_CMD = line;
                    else LAST_FAIL_CMD = "";   // 后续有命令成功了，失败的就不再是"上一次"
                }
            }
        }

        // ==================== 七点五、空闲探测与空回车回执 ====================

        // 空闲钩子：只在"停在提示符 + 一个字都没输入"时被调用。
        //
        // 【v7.11 关键改动】这里**不再同步调用 adb**。
        // 息屏往往伴随系统挂起（Modern Standby），唤醒后 adb server 可能握着
        // 已经失效的 USB 句柄；旧版这个钩子直接 AdbCall("devices") 且没有超时，
        // 一卡就把输入线程堵死 —— 表现就是"亮屏后敲字不上屏，只能重开工具"。
        // 现在只做三件事：处理唤醒事件、取后台结果、按节流发探测请求。
        // 返回非 null 表示提示符那一行已被清掉、由调用方重画。
        private static string IdleTick(string prompt)
        {
            // ---- 0. 用户正在拖选/复制：什么都别打印 ----
            // QuickEdit 打开后，选择期间写屏幕会把人家正在选的范围冲乱，
            // 而且键盘本来就进不来，探测完也只能攒着。直接让本轮空转。
            if (ConsoleUtil.SelectionInProgress()) return null;

            // ---- 1. 唤醒事件：控制台与 adb 一起体检 ----
            if (Bg.TakeWake())
            {
                ConsoleUtil.Recover();          // 丢掉睡眠期间攒的按键，恢复输入模式
                if (prompt != null) ClearPromptLine(prompt);
                Hint("系统刚唤醒：刷新控制台输入、重启 adb 连接 ...");
                Bg.RequestRecover();
                LAST_IDLE_PROBE = -100000;
                LAST_ONLINE_PROBE = 0;
                return Prompt();
            }

            // ---- 2. 取后台结果（永远不阻塞） ----
            string text;
            int rc;
            int kind;
            if (!Bg.TryTake(out text, out rc, out kind))
            {
                long now = Environment.TickCount;
                long last = OFFLINE ? LAST_IDLE_PROBE : LAST_ONLINE_PROBE;
                long gap = OFFLINE ? 1200 : 8000;
                if (now - last >= gap && !Bg.Busy)
                {
                    if (OFFLINE) LAST_IDLE_PROBE = now;
                    else LAST_ONLINE_PROBE = now;
                    Bg.Request();
                }
                return null;
            }

            // ---- 3. adb 服务急救的结果 ----
            if (kind == Bg.KIND_RECOVER)
            {
                if (prompt != null) ClearPromptLine(prompt);
                if (rc == 0)
                {
                    Hint("adb 服务已重启，重新检测设备 ...");
                    Bg.Request();
                }
                else
                {
                    Warn("adb 服务重启未成功（rc=" + rc + "），插好设备后按 :r 重试");
                }
                return Prompt();
            }

            // ---- 4. 一次 devices 探测的结果 ----
            if (rc == 124)
            {
                // v7.13：单次超时不再立刻重启服务。
                // 首次拉起 server、USB 刚插入重新枚举时，devices 慢一点很正常；
                // 一超时就 kill-server 等于"越救越坏" —— 用户看到的就是
                // "重连之后反而搜不到设备了"。连续两次超时才认定僵死。
                HANG_COUNT++;
                long nowms = Environment.TickCount;
                if (HANG_COUNT >= 2 && nowms - LAST_RECOVER_AT > 20000)
                {
                    HANG_COUNT = 0;
                    LAST_RECOVER_AT = nowms;
                    if (prompt != null) ClearPromptLine(prompt);
                    Warn("adb 连续无响应，正在重启 adb 服务 ...");
                    Bg.RequestRecover();
                    LAST_IDLE_PROBE = -100000;      // 急救完马上重新探一次
                    return Prompt();
                }
                return null;
            }
            HANG_COUNT = 0;
            if (rc != 0) return null;           // adb 本身调不起来：不打扰用户

            string old = DEVID;
            ParseDevices(text);

            if (!OFFLINE) return OnlineAfterProbe(prompt, old);
            return OfflineAfterProbe(prompt);
        }

        // 在线时：设备被拔掉但还没发命令，界面会一直显示"在线"。
        // 8 秒一次足够及时发现；频率再高就是空转刷 adb 进程，不划算。
        private static string OnlineAfterProbe(string prompt, string old)
        {
            if (DEVN > 0)
            {
                // 还是同一台：什么都不用做
                if (old.Length == 0 || DEVID == old) return null;

                // 换了另一台：旧设备的路径可能不存在，回根目录并重新取设备信息
                if (prompt != null) ClearPromptLine(prompt);
                Warn("设备已切换：" + old + " -> " + DEVID);
                CUR = ROOT;
                OLDPWD = "";
                PEND_K = "";
                AutoRoot();
                Probe();
                LoadDeviceInfo();
                RenderDeviceInfo();
                Ok("已切换到 " + DEVID + "，当前目录 " + CUR);
                return Prompt();
            }

            OFFLINE = true;
            CMD_OK = false;

            if (prompt != null) ClearPromptLine(prompt);
            Warn("设备已断开" + (old.Length > 0 ? "：" + old : ""));
            Hint("插回设备会自动重连；也可输入 :r 手动重连");
            return Prompt();
        }

        // 提示符前的一次静默探测：IME 模式下没有读键循环，靠这里补上自动连接
        private static void ProbeBeforePrompt()
        {
            if (!OFFLINE || !WATCH_DEV) return;

            long now = Environment.TickCount;
            if (now - LAST_IDLE_PROBE < 1200) return;
            LAST_IDLE_PROBE = now;

            // IME / 非交互模式没有空闲钩子可用，只能同步探（内部有 4 秒上限）
            if (IME_ACTIVE || !INTERACTIVE)
            {
                AutoConnect(null);
                return;
            }

            // 普通编辑模式：交给后台线程，输入永远不会被 adb 卡住
            Bg.Request();
        }

        // 离线状态下探测到设备：走正式初始化并打印状态栏
        // prompt 为 null 表示"当前屏幕上没有待擦的提示符行"
        private static string OfflineAfterProbe(string prompt)
        {
            if (DEVN == 0)
            {
                // v7.13：设备没上线时不能再一声不响。
                // 现场"搜不到设备"绝大多数是下面三种，界面上必须说清楚，
                // 否则用户只看到提示符，分不清是没插、没授权、还是 adb 坏了。
                return ReportNoDevice(prompt);
            }

            // 设备出现了 —— 先把提示符那一行擦掉，再走正式初始化（会打印状态栏）
            if (prompt != null) ClearPromptLine(prompt);
            Hint("检测到设备 " + DEVID + "，正在自动连接 ...");

            if (InitEnv())
            {
                LAST_NODEV_NOTE = "";
                Ok("已自动连接：" + DEVID);
            }
            else
            {
                OFFLINE = true;
                Hint("连接未完成，插好设备后会自动再试一次");
                LAST_IDLE_PROBE = Environment.TickCount;   // 别立刻反复重试刷屏
            }

            // 连上后 OFFLINE 变了，提示符必须重算，否则会继续显示「(离线) >」
            return Prompt();
        }

        // 上次报过的"没设备"原因，只在变化时报一次，避免每 1.2 秒刷屏
        private static string LAST_NODEV_NOTE = "";
        private static long LAST_NODEV_AT = 0;

        private static string ReportNoDevice(string prompt)
        {
            string st;
            if (DEV_UNAUTH > 0) st = "unauth";
            else if (DEVOTHER > 0) st = "offline";
            else st = "none";

            // 同一种状态 10 秒内只提醒一次；状态变了立刻提醒
            long now = Environment.TickCount;
            if (st == LAST_NODEV_NOTE && now - LAST_NODEV_AT < 10000) return null;

            // 空列表别每次都刷 —— 它是最常见的"正在等"，第一次说过就够了
            if (st == "none" && LAST_NODEV_NOTE == "none") return null;

            LAST_NODEV_NOTE = st;
            LAST_NODEV_AT = now;

            if (prompt != null) ClearPromptLine(prompt);

            if (st == "unauth")
            {
                Warn("设备已识别，但还没授权 USB 调试");
                Hint("请在车机弹出的「允许 USB 调试」上点允许（勾选\"一律允许\"）");
                Hint("授权后会自动连上，不用重开工具");
            }
            else if (st == "offline")
            {
                Warn("设备处于 offline：拔插残留的旧连接还没被回收");
                Hint("正在自动 reconnect；若一直不动，按 :rr 重启 adb 服务");
            }
            else
            {
                Hint("等待设备上线：拔插后通常要 3~6 秒（USB 重新枚举 + adbd 重启）");
                Hint("一直等不到就按 :rr 重启 adb 服务，或用 :diag 看体检报告");
            }

            return Prompt();
        }

        // prompt 为 null 表示"当前屏幕上没有待擦的提示符行"
        private static string AutoConnect(string prompt)
        {
            string o = "";
            string e = "";
            if (AdbProbe(out o, out e) != 0) return null;

            ParseDevices(MergeStream(o, e));
            return OfflineAfterProbe(prompt);
        }

        // 擦掉提示符那一行（此时缓冲为空，行上只有提示符）
        private static void ClearPromptLine(string prompt)
        {
            try
            {
                Console.Write('\r');
                int w = DispWidth(prompt) + 2;
                for (int i = 0; i < w; i++) Console.Write(' ');
                Console.Write('\r');
            }
            catch { }
        }

        // 空回车的回执：一行当前状态，证明程序还活着、顺带确认在跟谁说话
        private static void ShowQuickStatus()
        {
            UseDim();
            Console.Write("  \u00B7 ");

            if (OFFLINE)
            {
                Console.WriteLine("设备未连接 · 插上设备会自动连接 · :r 立即重连 · :h 帮助");
                UseDefault();
                return;
            }

            Console.Write(string.IsNullOrEmpty(DEVID) ? "-" : DEVID);
            Console.Write(" 在线");
            if (!string.IsNullOrEmpty(DEV_PLAT)) Console.Write(" · " + DEV_PLAT);
            Console.Write(" · " + CUR);
            Console.WriteLine();
            UseDefault();
        }

        // 纯本地命令的成功标记。
        //
        // Dispatch 入口会把 CMD_OK 置为 false（见那里的注释），而纯本地命令
        // （帮助、命令列表、pwd、音区表……）不调用任何 adb，没有机会把它改回
        // true。它们本身"没有失败"，所以用这个函数显式标记成功。
        //
        // 注意：只给"确实完成了它该做的事"的本地命令用。参数缺失、跳转点不存在
        // 这类已经打了 Fail 的分支不要调它，保持失败态才是对的。
        internal static void OkLocal()
        {
            CMD_OK = true;
        }

        // ==================== 八、命令分派 ====================
        // v8.0：改 internal 供 GUI 入口复用。
        // GUI 不重写任何命令语义，只把同样的输入交给这一个函数 —— 这是"完全保留
        // 现有能力"的唯一可靠做法：命令行和界面走的是同一条 Dispatch 管道。

        /* 2026-11-24（A3）：纯打印/纯本地命令的"无标记"成功。
           Dispatch 契约是"入口先当失败"，只有显式成功才转 true；
           但 60+ 个前缀命令里有十几处只打印（帮助、列表、pwd、跳转说明），
           既不打 √ 也不打 ×，于是永远标红。
           这里在**调用方**做一次收口，而不是改十几个 handler：
             没有 × (FAIL_N==0) 且 没有 √ (OK_N==0) 且 仍未成功 → 视为成功。
           风险：真失败但只用 Warn/Hint 表达的分支会被误判成功 —— 已确认现有
           handler 里参数缺失/设备离线都用 Fail()，所以实际面很小。 */
        // 本条命令的耗时（ms），由 GUI 在调用前写入，供"静默成功"判断是否值得提示
        internal static long LAST_MS = 0;

        internal static void DispatchChecked(string line)
        {
            OK_N = 0; FAIL_N = 0;
            var swD = System.Diagnostics.Stopwatch.StartNew();
            Dispatch(line);
            LAST_MS = swD.ElapsedMilliseconds;
            if (!CMD_OK && FAIL_N == 0 && OK_N == 0)
            {
                CMD_OK = true;
                // 2026-11-24：静默成功补一行总账（仅耗时命令，快命令保持安静）
                if (LAST_MS > 300) Ok("命令执行完成（" + LAST_MS + " ms）");
            }
        }

        internal static void Dispatch(string line)
        {
            // 【bug 修复·重要】入口先把"上一条是否成功"置为失败。
            //
            // 原实现只在真正跑过 adb 的地方设置 CMD_OK，而 Dispatch 里有大量
            // **提前 return** 的分支（离线拦截、参数缺失、纯本地帮助、跳转点、
            // 交互式提示……）。这些分支返回时不碰 CMD_OK，于是它保留着
            // 「上一次命令的结果」或初始值 true —— GUI 据此把
            // **"设备未连接，命令根本没执行" 显示成了"成功"**。
            //
            // 现在的契约：进入 Dispatch 一律先当作失败，只有真正成功的路径
            // 才把它改成 true。这样任何"什么都没干就返回"的情况都算失败，
            // 不需要逐个分支去补，也不会漏。
            CMD_OK = false;

            // 分支 0：离线模式闸门
            // 只放行不依赖设备的命令；其余命令先探测一次（也许设备刚插上），
            // 探测不到才拒绝 —— 这样"插上设备直接敲命令"也能用。
            if (OFFLINE)
            {
                string f0;
                string r0;
                SplitLine(line, out f0, out r0);

                if (!OfflineAllowed(f0.ToLowerInvariant()))
                {
                    // v7.13：给 2.5 秒宽限，而不是探一次就拒绝。
                    // "插上线马上敲命令"是最常见的动作，此时 USB 往往还在枚举，
                    // 旧版会直接回一句"设备未连接"，看起来就是"搜不到设备"。
                    if (!Rec.WaitDevice(2500, false, true) || DEVN == 0)
                    {
                        Warn("设备未连接。输入 :r 重连、:h 看帮助、:cmds 看命令");
                        if (DEV_UNAUTH > 0)
                            Hint("设备已识别但还没授权：在车机上点「允许 USB 调试」即可");
                        else if (DEVOTHER > 0)
                            Hint("设备处于 offline：按 :r 刷新（会自动 reconnect），或 :rr 重启服务");
                        return;
                    }
                    OFFLINE = false;
                    LAST_NODEV_NOTE = "";
                    AutoRoot();
                    Probe();
                    Ok("设备已连接：" + DEVID + "   当前目录 " + CUR);
                }
            }

            // 分支 1：! 前缀 —— 强制按原样透传给设备 shell（逃生舱）
            //         用于绕过交互式提示等保护，例如 !top
            if (line.Length > 0 && line[0] == '!')
            {
                string forced = line.Substring(1).Trim();
                if (forced.Length == 0) return;
                string fc;
                string fa;
                SplitLine(forced, out fc, out fa);
                if (fc.Length == 0) return;
                DoPass(fc, fa);
                return;
            }

            // 分支 2：整行是电脑路径 => 把当前目录导出到该路径
            if (IsWinPath(line)) { Export(CUR, LastSeg(CUR), line); return; }

            // 分支 3：: 命名空间 —— 词法唯一，不参与任何优先级竞争
            //         设备命令里不可能出现以 : 开头的写法，所以这里与透传零冲突
            if (line.Length > 0 && line[0] == ':')
            {
                RouteColon(line.Substring(1));
                return;
            }

            string cmd;
            string argRaw;
            SplitLine(line, out cmd, out argRaw);
            if (cmd.Length == 0) return;
            string c = cmd.ToLowerInvariant();

            // 分支 4：@ 跳转点（跳转是数据，不是命令）
            if (line.Length > 0 && line[0] == '@')
            {
                string jname = cmd.Substring(1).ToLowerInvariant();
                string jp = JumpPath(jname);
                if (jp.Length == 0)
                {
                    Fail("没有这个跳转点：@" + jname);
                    Hint("可用：@logs @res @anr @dropbox（目标配在 ini 的 jump_*）");
                    return;
                }
                DoJump(jp, "@" + jname, argRaw);
                return;
            }

            // 分支 5：裸名白名单 —— 只有"设备语义等价增强"与协议入口能占裸名
            //         cd/ls/pwd 就是设备那条命令，只是补了 cwd 与排版；
            //         adb/shell 是协议入口；pull/push 是文件传输入口。
            //
            // 【2026-11-12 修复】接管前先做"复合命令体检"。
            //
            // 原来的问题（实测）：
            //     ls && echo ok        -> 被判成"设备（语义增强）"
            //     ls > /sdcard/a.txt   -> 同上
            //     cd /sdcard && ls     -> 同上
            // 因为分支 5 先命中 ls/cd，DoLs 看到 arg[0] 不是 '-' 就把
            // "&& echo ok" / "> /sdcard/a.txt" 整串当成**路径参数**塞进
            // `ls -1pF '<这里>'`，必然报 No such file or directory。
            // 用户以为自己做了重定向或串联，实际什么都发生不了 —— 静默错。
            //
            // 现在：参数里出现【引号外】的 shell 连接符/重定向符时，放弃接管，
            // 落到分支 12 原样透传给设备 shell。这样
            //     ls && echo ok        -> 设备 shell，两个命令都真的跑
            //     ls > /sdcard/a.txt   -> 设备 shell，重定向真的生效
            // 而单纯 `ls`、`ls -l`、`ls /sdcard`（无连接符）仍然走增强渲染。
            //
            // 注意：不能用 HasLocalRedir —— 那个把 `>` 判成"本地重定向"（给
            // adb exec-out 截图用的）。裸 ls 的重定向语义是**设备侧**的，
            // 交给设备 shell 才对。所以这里单独判，只用来"放弃接管"。
            bool complex = IsComplexShellLine(argRaw) || IsComplexShellLine(line);

            if (c == "adb") { DoAdbPrefix(argRaw); return; }
            if (c == "shell") { RunAdbShell(argRaw); return; }
            if (c == "cd" && !complex) { DoCd(argRaw); return; }
            if (c == "pwd" && !complex) { Console.WriteLine("  " + CUR); OkLocal(); return; }
            if (c == "ls" && !complex) { DoLs(argRaw, false); return; }
            if (c == "pull" && !complex) { DoPull(argRaw); return; }
            if (c == "push" && !complex) { DoPush(argRaw); return; }

            // 帮助与退出：不依赖设备，也不属于"设备语义"，必须始终可用
            // （所以不放在 legacy 兼容里 —— 关掉旧名后 h 仍然要能用）
            if (c == "h" || c == "?" || c == "help")
            {
                if (argRaw.Trim().ToLowerInvariant() == "all") HelpAll();
                else HelpIndex();
                OkLocal();
                return;
            }
            if (c == "q" || c == "quit" || c == "exit")
            {
                // GUI 模式绝不允许这里退出：用户在命令框里敲 q/exit（或自定义
                // 指令里带了 exit）会把整个窗口直接干掉，且 gui_error.log 什么
                // 都不留 —— 表现就是"工具突然消失"。CLI 行为保持不变。
                if (GUI_MODE)
                {
                    Console.WriteLine("  [GUI] 界面模式下不执行退出命令，要关闭工具请直接关窗口。");
                    OkLocal();
                    return;
                }
                Pause();
                Environment.Exit(0);
                return;
            }

            // 分支 6：旧裸名兼容（legacy_alias=1 时生效，每个命令只提示一次）
            if (TryLegacy(c, argRaw)) return;

            // 分支 7：纯中文启发式 —— 首 token 含中文说明用户就是想发这条消息
            //         （纯中文透传给 shell 必然报 not found，故不侵占任何有效输入）
            if (IsProbablyText(cmd)) { Echo("send", Clip(line, 50)); SendText(line); return; }

            // 分支 8：自定义命令。撞设备命令的名字不在这里接（只能用 :name）
            if (HasCmd(c) && CmdBareOk(c)) { TryRunCmd(c, argRaw); return; }

            // 分支 9：adb 专属子命令（裸输入也能直接跑）
            //         白名单只收"设备 shell 上不存在或极少用"的，pm/am/dumpsys 等仍走 shell
            if (IsAdbSubcmd(c)) { DoAdbBare(c, argRaw); return; }

            // 分支 10：裸命令 + 本地过滤器
            //          getprop | findstr navi  -> findstr 是 Windows 命令，必须本地跑
            //          ps | grep xxx           -> grep 是设备命令，保持设备侧（不触发）
            if (IsLocalPipe(line)) { RunShellPipe(line); return; }

            // 分支 10.5：裸包名 —— 查版本与安装路径
            //   无损：裸包名发给设备 shell 必然 not found，不存在"抢占有效输入"
            if (IsMaybePkg(line)) { DoPkgLookup(line); return; }

            // 分支 11：交互式命令 —— 只提示，不拦截（设备优先：这是合法命令）
            if (IsInteractiveBare(c, argRaw))
            {
                Hint(c + " 会持续运行、不返回，看起来像卡住；要结束按 Ctrl+C");
            }

            // 分支 12：其余一律原样透传给设备 shell
            DoPass(cmd, argRaw);
        }

        // 离线模式下允许的命令：不依赖设备，或本身就是"连接设备"的操作
        // 2026-11-20：GUI 的命令入口也要用这份白名单（无设备快判）
        internal static bool OfflineAllowed(string c)
        {
            if (string.IsNullOrEmpty(c)) return true;

            // : 前缀的工具命令：只放行纯本地的那几个
            if (c[0] == ':')
            {
                string n = c.Substring(1);
                return n == "h" || n == "help" || n == "?" || n == "cmds"
                    || n == "q" || n == "quit" || n == "exit"
                    || n == "r" || n == "rr" || n == "ri" || n == "i" || n == "rw"
                    || n == "which" || n == "ime" || n == "cn"
                    || n == "diag" || n == "doctor"
                    || n == "vr" || n == "voice"   // :vr 内部按子命令自行判设备，帮助/音区表为纯本地
                    // 2026-11-20：:url 是"在电脑上打开浏览器"，不碰 adb。
                    // 漏在门外会导致设备掉线时点「云平台」四张卡全被拒（用户实际遇到）。
                    || n == "url" || n == "openurl" || n == "link"
                    // 2026-11-21：:cfg 是本地文件读写（导出/导入配置），与设备无关
                    || n == "cfg" || n == "profile";
            }

            if (c[0] == '!') return false;

            return c == "h" || c == "?" || c == "help" || c == "all"
                || c == "cmds"
                || c == "diag" || c == "doctor"
                || c == "q" || c == "quit" || c == "exit"
                || c == "r" || c == "rr" || c == "ri" || c == "i"
                || c == "rw"
                || c == "adb" || c == "devices" || c == "version"
                || c == "connect" || c == "disconnect" || c == "tcpip" || c == "pair"
                || c == "start-server" || c == "kill-server";
        }

        // ==================== 全角前缀归一化 ====================
        // 中文输入法下行首的 : ! @ 常被打成全角（：！＠），命令就识别不到。
        // 只归一化"第一个词"，且只在它看起来是命令时才动手 ——
        // 否则 "你好！" 这种要发出去的文本会被改掉。
        internal static string NormalizeLead(string line)
        {
            if (string.IsNullOrEmpty(line)) return line;

            int i = 0;
            while (i < line.Length && line[i] != ' ' && line[i] != '\t') i++;

            string head = line.Substring(0, i);
            if (!LooksLikeCommandToken(head)) return line;

            StringBuilder sb = new StringBuilder();
            for (int k = 0; k < head.Length; k++) sb.Append(HalfWidth(head[k]));
            if (i < line.Length) sb.Append(line.Substring(i));
            return sb.ToString();
        }

        private static bool LooksLikeCommandToken(string t)
        {
            if (string.IsNullOrEmpty(t)) return false;

            char c0 = HalfWidth(t[0]);
            if (c0 == ':' || c0 == '!' || c0 == '@') return true;

            // 含 ASCII 字母才算命令词；纯中文（"你好！"）原样保留
            for (int i = 0; i < t.Length; i++)
            {
                char c = t[i];
                if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z')) return true;
            }
            return false;
        }

        // 常见全角标点 -> 半角
        private static char HalfWidth(char c)
        {
            if (c == '\uFF1A') return ':';  // ：
            if (c == '\uFF01') return '!';   // ！
            if (c == '\uFF20') return '@';   // ＠
            if (c == '\uFF0F') return '/';   // ／
            if (c == '\uFF3C') return '\\';  // ＼
            if (c == '\uFF0D') return '-';   // －
            return c;
        }

        // 判据：首 token 含非 ASCII 字符 => 视为待发文本
        //   "你好"          -> cmd="你好" 含中文 -> 文本
        //   "cat 日志.txt"  -> cmd="cat" 纯 ASCII -> 不是文本（走透传）
        //   "351"           -> 无中文 -> 不是文本（走透传）
        private static bool IsProbablyText(string cmdToken)
        {
            if (string.IsNullOrEmpty(cmdToken)) return false;
            for (int i = 0; i < cmdToken.Length; i++)
            {
                if (cmdToken[i] > 127) return true;
            }
            return false;
        }

        // ==================== 交互式命令预判 ====================
        // 这些命令会持续运行、不返回（看起来像卡死），所以执行前先提示，
        // 而不是等用户发现没反应再解释。确实要跑就用 ! 前缀。
        private static readonly string[] INTERACTIVE_CMDS = new string[]
        {
            "top", "vi", "vim", "nano", "less", "more", "tailf", "watch", "screenrecord"
        };

        internal static bool IsInteractiveBare(string cmd, string argRaw)
        {
            if (string.IsNullOrEmpty(cmd)) return false;

            string c = cmd.ToLowerInvariant();
            bool found = false;
            for (int i = 0; i < INTERACTIVE_CMDS.Length; i++)
            {
                if (INTERACTIVE_CMDS[i] == c) { found = true; break; }
            }
            if (!found) return false;

            string a = (argRaw == null) ? "" : argRaw;

            // top 带 -n 会自己结束，不算交互式
            if (c == "top" && a.IndexOf("-n", StringComparison.Ordinal) >= 0) return false;
            // screenrecord 带 --time-limit 会自己结束
            if (c == "screenrecord" && a.IndexOf("--time-limit", StringComparison.Ordinal) >= 0) return false;

            return true;
        }

        // ==================== 九、通用工具 ====================
        // 把一行拆成命令名与参数原文（参数保留引号，供透传使用）
        internal static void SplitLine(string line, out string cmd, out string argRaw)
        {
            cmd = "";
            argRaw = "";
            if (line == null) return;
            int i = 0;
            while (i < line.Length && (line[i] == ' ' || line[i] == '\t')) i++;
            int s = i;
            while (i < line.Length && line[i] != ' ' && line[i] != '\t') i++;
            cmd = line.Substring(s, i - s);
            while (i < line.Length && (line[i] == ' ' || line[i] == '\t')) i++;
            if (i < line.Length) argRaw = line.Substring(i);
        }

        // 该行是否是"复合 shell 命令"——含引号外的连接符 / 重定向符。
        //
        // 用途：裸名白名单（ls / cd / pwd / pull / push）接管前先问一句。
        // 命中就放弃增强接管，原样透传给设备 shell —— 因为这些符号是
        // shell 语法，不是路径的一部分，塞给 ls -1pF 只会变成"文件不存在"。
        //
        // 判定口径（引号外才算）：
        //   && || ;        命令串联
        //   |              管道（findstr 那类本地管道走别的分支，这里只为放弃接管）
        //   > >> <         重定向（设备侧语义）
        //   `  $(          命令替换
        //
        // 不判 & 单字符：`ls &` 少见，而 & 出现在路径里（如 a&b）时误判代价更大。
        internal static bool IsComplexShellLine(string s)
        {
            if (string.IsNullOrEmpty(s)) return false;

            bool inq = false;
            for (int i = 0; i < s.Length; i++)
            {
                char ch = s[i];
                if (ch == '"') { inq = !inq; continue; }
                if (inq) continue;

                if (ch == ';' || ch == '|' || ch == '>' || ch == '<' || ch == '`') return true;

                // $( 与 && —— 只看第一个字符就够，不必配对
                if (ch == '$' && i + 1 < s.Length && s[i + 1] == '(') return true;
                if (ch == '&' && i + 1 < s.Length && s[i + 1] == '&') return true;
            }
            return false;
        }

        // 按引号感知分词：pull 351 "D:\my log" => [351, D:\my log]
        internal static List<string> SplitArgs(string s)
        {
            List<string> r = new List<string>();
            if (s == null) return r;
            StringBuilder cur = new StringBuilder();
            bool inq = false;
            bool any = false;
            for (int i = 0; i < s.Length; i++)
            {
                char ch = s[i];
                if (ch == '"') { inq = !inq; any = true; continue; }
                if (!inq && (ch == ' ' || ch == '\t'))
                {
                    if (any) { r.Add(cur.ToString()); cur.Length = 0; any = false; }
                    continue;
                }
                cur.Append(ch);
                any = true;
            }
            if (any) r.Add(cur.ToString());
            return r;
        }

        // 去掉最外层一对引号（"C:\my dir" => C:\my dir）
        internal static string Unquote(string s)
        {
            if (s == null) return "";
            s = s.Trim();
            if (s.Length >= 2 && s[0] == '"' && s[s.Length - 1] == '"')
                return s.Substring(1, s.Length - 2).Trim();
            return s;
        }

        // 整行是否是电脑本地路径：盘符开头 C:\ C:/ 或 UNC \\server
        internal static bool IsWinPath(string p)
        {
            if (p == null) return false;
            if (p.Length >= 3)
            {
                char c0 = p[0];
                bool alpha = (c0 >= 'A' && c0 <= 'Z') || (c0 >= 'a' && c0 <= 'z');
                if (alpha && p[1] == ':' && (p[2] == '\\' || p[2] == '/')) return true;
            }
            if (p.Length >= 2 && p[0] == '\\' && p[1] == '\\') return true;
            return false;
        }

        // 设备路径最后一段：/a/b/ => b    / => /
        internal static string LastSeg(string p)
        {
            if (string.IsNullOrEmpty(p)) return "/";
            string t = p.TrimEnd('/');
            if (t.Length == 0) return "/";
            int i = t.LastIndexOf('/');
            if (i < 0) return t;
            return t.Substring(i + 1);
        }

        // 归一化设备绝对路径：合并 //、消解 . 与 ..
        internal static string NormPath(string p)
        {
            if (string.IsNullOrEmpty(p)) return "/";
            string[] parts = p.Replace('\\', '/').Split('/');
            List<string> st = new List<string>();
            foreach (string seg in parts)
            {
                if (seg.Length == 0 || seg == ".") continue;
                if (seg == "..")
                {
                    if (st.Count > 0) st.RemoveAt(st.Count - 1);
                    continue;
                }
                st.Add(seg);
            }
            if (st.Count == 0) return "/";
            StringBuilder sb = new StringBuilder();
            foreach (string seg in st)
            {
                sb.Append('/');
                sb.Append(seg);
            }
            return sb.ToString();
        }

        // 相对设备路径补全成绝对路径（相对当前目录）
        internal static string DevAbs(string p)
        {
            if (string.IsNullOrEmpty(p)) return CUR;
            if (p == "~") return "/";
            if (p[0] == '/') return NormPath(p);
            return NormPath(CUR + "/" + p);
        }

        // 单个字符的显示宽度：中日韩全角算 2 列
        internal static int CharWidth(char c)
        {
            if (c >= '\u1100' && c <= '\u115F') return 2;
            if (c >= '\u2E80' && c <= '\uA4CF') return 2;
            if (c >= '\uAC00' && c <= '\uD7A3') return 2;
            if (c >= '\uF900' && c <= '\uFAFF') return 2;
            if (c >= '\uFE30' && c <= '\uFE6F') return 2;
            if (c >= '\uFF00' && c <= '\uFF60') return 2;
            if (c >= '\uFFE0' && c <= '\uFFE6') return 2;
            return 1;
        }

        // 显示宽度：中日韩全角算 2 列，其余算 1 列
        // 比 bat 版的"GBK 字节数"更准，UTF-8 下也成立
        internal static int DispWidth(string s)
        {
            if (string.IsNullOrEmpty(s)) return 0;
            int w = 0;
            for (int i = 0; i < s.Length; i++) w += CharWidth(s[i]);
            return w;
        }

        internal static string FirstLine(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            int i = s.IndexOf('\n');
            string t = (i < 0) ? s : s.Substring(0, i);
            return t.TrimEnd('\r').Trim();
        }

        // 确保输出以换行结尾，避免提示符粘在设备输出后面
        internal static string EnsureEndsNewline(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            if (s.EndsWith("\n")) return s;
            return s + Environment.NewLine;
        }

        internal static void Pause()
        {
            Console.WriteLine();
            Console.Write("  按任意键退出 ...");
            try { Console.ReadKey(true); }
            catch { }
            Console.WriteLine();
        }
    }
}
