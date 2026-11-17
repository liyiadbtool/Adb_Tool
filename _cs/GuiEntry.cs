// ============================================================================
//  GuiEntry.cs - GUI 入口
//
//  编译方式与命令行版**共用同一批源文件**，只是 /main: 指向不同的类：
//     命令行版  /main:AdbLogExport.App
//     图形版    /main:AdbLogExport.Gui.GuiEntry
//
//  为什么这么做：需求要求"指令输入完全保留当前工具的能力"。把 9600 行命令
//  逻辑复制一份到 GUI 里，两份代码必然渐渐分叉。共用源码 + 共用 Dispatch，
//  能力就是同一套东西 —— 命令行能做的，GUI 一定能做。
// ============================================================================
using System;
using System.IO;
using System.Text;
using System.Windows.Forms;

namespace AdbLogExport.Gui
{
    internal static class GuiEntry
    {
        // 【单 exe（R8）第一步】把 AssemblyResolve 挂在**类型初始化**上。
        // CLR 保证进入 Main 之前先跑静态构造函数，所以任何 WebView2 类型
        // （哪怕只在字段声明里出现）被碰到时，解析器已经在位了。
        // 放进 Main 体里就晚了：字段初始化 / JIT 触发的类型加载可能更早。
        static GuiEntry()
        {
            try { Embed.HookAssemblyResolve(); }
            catch { }
        }

        [System.Runtime.InteropServices.DllImport("user32.dll")]
        private static extern bool SetProcessDpiAwarenessContext(int value);

        [System.Runtime.InteropServices.DllImport("user32.dll")]
        private static extern bool SetProcessDPIAware();

        // Per-Monitor V2 DPI 感知的上下文值：
        //   DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
        private const int PER_MONITOR_AWARE_V2 = -4;

        [STAThread]
        internal static int Main(string[] args)
        {
            // 【文字清晰的关键】没有 DPI 感知时，Windows 会把"未感知 DPI"的窗口
            // 在位图层面整窗拉伸，文字发虚模糊 —— 字号调再大也救不回来。
            // 这里必须在任何窗体创建之前声明 Per-Monitor V2，
            // 让 WebView2 按真实像素渲染，文字才清晰。
            try
            {
                if (!SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2))
                    SetProcessDPIAware();   // 旧系统回退
            }
            catch { }

            // GUI 进程没有控制台，异常默认"窗口一闪就没了"。三处兜底全挂上：
            //   · Application.ThreadException   -> UI 线程异常
            //   · AppDomain.UnhandledException   -> 其它线程异常
            //   · try/catch                      -> 启动阶段异常（最常见）
            Application.ThreadException += new System.Threading.ThreadExceptionEventHandler(OnUiError);
            AppDomain.CurrentDomain.UnhandledException += new UnhandledExceptionEventHandler(OnAnyError);

            Trace("进入 Main");

            // ---- 自检模式（2026-11-17 O6 改造）----
            // 原来这里直接 return GuiSelfCheck.Run()，测的是 A12 之后就没再上过阵的
            // 老 WinForms 窗体 GuiMain —— 对真实界面零覆盖，还会因为本机没装
            // winget scrcpy 而误红。
            // 现在只记一个标记，照常走真实启动链路（Embed 释放 → GuiBoot → WebView2
            // → 加载 ui.html），页面就绪后由 GuiWeb 回调 GuiSelfCheck.RunOn() 做断言，
            // 跑完自己关窗并把退出码带回来。
            // 注意顺序：--selfcheck 必须先于 --exec 判断，否则 "--exec ... --selfcheck"
            // 会被无头执行分支接走。
            bool selfCheck = GuiHeadless.HasSelfCheck(args);

            // ---- 无头执行模式：把命令喂进 GUI 的真实管道，供等价性验证 ----
            // 与 --selfcheck 同理：不显示窗口，可进 CI。区别是它跑真命令，
            // 输出经 GuiSink 渲染成"级别 + 文本"，用来和命令行版逐行比对。
            if (GuiHeadless.HasFlag(args))
            {
                return GuiHeadless.Run(args);
            }

            try
            {
                // 【单 exe（R8）】配置文件缺失时先写内嵌默认值，再读 ini。
                // 顺序不能反：GuiBoot 的 LoadIni 只读不写，先读会读到空配置，
                // adb 路径、root 开关全用代码里的兜底值，用户改 ini 也不知从哪改。
                try { Embed.EnsureIniDefaults(); }
                catch { }

                // 原生 WebView2Loader.dll：单 exe 版要先把内嵌的那份释放出来，
                // 否则创建 WebView2 环境时报"找不到 WebView2Loader.dll"。
                try { Embed.PrepareNativeLoader(); }
                catch { }

                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);

                // 复用命令行版的初始化（读 ini、定位 adb、加载自定义命令）。
                // 注意：这里**不调用** SetupConsole —— GUI 没有控制台；
                // 也不调用 InitEnv —— 那个会阻塞数秒，交给窗体在后台线程做。
                App.GuiBoot(args);
                Trace("GuiBoot 完成");
            }
            catch (Exception ex)
            {
                Dump("GuiBoot", ex);
                MessageBox.Show("初始化失败：\r\n" + ex.Message,
                    "adb_Tool", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }

            try
            {
                Trace("构造 GuiWeb");
                // 定位 ui.html：外置优先（webview2\ui.html），没有就用内嵌的那份。
                // 单 exe 版就是靠这里"凭空"拿到界面的，所以不能再写死路径。
                string uiPath = Embed.PrepareUiHtml();
                Trace("ui.html = " + uiPath);
                if (!File.Exists(uiPath))
                {
                    MessageBox.Show(
                        "找不到界面文件，也没有内嵌资源。\r\n\r\n"
                        + "期望位置：\r\n" + uiPath + "\r\n\r\n"
                        + "请把 webview2\\ui.html 放回程序目录，或使用完整版发布包。",
                        "adb_Tool", MessageBoxButtons.OK, MessageBoxIcon.Error);
                    return 2;
                }
                GuiWeb f = new GuiWeb(uiPath);
                if (selfCheck)
                {
                    // 自检：窗口移到屏幕外，不抢焦点，不显示任务栏按钮
                    f.SelfCheckMode = true;
                    f.ShowInTaskbar = false;
                }
                Trace("GuiWeb 构造完成，进入消息循环");
                Application.Run(f);
                Trace("消息循环结束（窗口已关闭）");
            }
            catch (Exception ex)
            {
                Dump("Application.Run", ex);
                MessageBox.Show("运行时错误：\r\n" + ex.Message,
                    "adb_Tool", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }
            // 自检模式的退出码由断言结果决定（0=全通过）
            if (selfCheck)
            {
                Trace("自检退出码 = " + GuiSelfCheck.ExitCode);
                return GuiSelfCheck.ExitCode;
            }
            Trace("Main 返回 0");
            return 0;
        }

        // 诊断日志的落点：%LOCALAPPDATA%\adb_Tool\logs
        //
        // 为什么不放 exe 同级：发布包会被整个拷给同事，运行期一写日志就在发布目录
        // 里留垃圾；包放在只读介质（光盘、只读共享、Program Files）上时写还会失败。
        // 和 WebView2 缓存走同一个思路 —— 可写数据一律进 LocalAppData。
        // 取不到 LocalAppData 时退化为 exe 同级（至少日志不丢）。
        internal static string LogDir()
        {
            try
            {
                string root = Environment.GetFolderPath(
                    Environment.SpecialFolder.LocalApplicationData);
                if (string.IsNullOrEmpty(root) || root.Trim().Length == 0)
                    root = Environment.GetEnvironmentVariable("LOCALAPPDATA");
                if (!string.IsNullOrEmpty(root) && root.Trim().Length > 0)
                {
                    string d = Path.Combine(root, "adb_Tool", "logs");
                    Directory.CreateDirectory(d);
                    return d;
                }
            }
            catch { }
            return AppDomain.CurrentDomain.BaseDirectory;
        }

        // 启动阶段追踪：GUI 闪退时看不出来到哪一步，靠这个定位
        internal static void Trace(string msg)
        {
            try
            {
                string p = Path.Combine(LogDir(), "gui_trace.log");
                File.AppendAllText(p,
                    DateTime.Now.ToString("HH:mm:ss.fff") + "  " + msg + Environment.NewLine,
                    Encoding.UTF8);
            }
            catch { }
        }

        private static void OnUiError(object sender, System.Threading.ThreadExceptionEventArgs e)
        {
            Dump("UI线程", e.Exception);
        }

        private static void OnAnyError(object sender, UnhandledExceptionEventArgs e)
        {
            Dump("非UI线程", e.ExceptionObject as Exception);
        }

        // 崩溃现场落到 exe 同目录，方便取证（GUI 没有控制台可看）
        internal static void Dump(string where, Exception ex)
        {
            try
            {
                string dir = LogDir();
                string p = Path.Combine(dir, "gui_error.log");
                StringBuilder sb = new StringBuilder();
                sb.AppendLine("============================================================");
                sb.AppendLine(DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "  [" + where + "]");
                sb.AppendLine(ex == null ? "(no exception object)" : ex.ToString());
                sb.AppendLine();
                File.AppendAllText(p, sb.ToString(), Encoding.UTF8);
            }
            catch { }
        }
    }
}
