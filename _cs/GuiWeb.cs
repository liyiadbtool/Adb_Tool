// ============================================================================
//  GuiWeb.cs - WebView2 版界面外壳（v8.2）
//
//  UI 从 WinForms 换成 WebView2 内嵌 HTML（ui.html），彻底解决 GDI+ 做不出
//  现代质感的问题。命令逻辑仍然一行不改：
//    页面按键 → postMessage('cmd', text) → 这里调 App.Dispatch（与命令行同一个函数）
//    命令输出 → Console → GuiSink 拆行 → PostWebMessageAsJson('line', …) → 页面着色
//
//  依赖：Microsoft.Web.WebView2.WinForms / Core（net462 版，随包放 webview2\ 目录）
//  语法：全部走 C# 5.0（事件 + BeginInvoke），不用 async/await —— 与 build.bat
//        的 /langversion:5 保持一致。
// ============================================================================
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Text;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace AdbLogExport.Gui
{
    internal sealed class GuiWeb : Form
    {
        private WebView2 _web;
        private GuiSink _sink;
        private System.Windows.Forms.Timer _tick;
        // 需求1（并行多命令）：单 worker → 每槽位一个 worker / busy / 来源 / 停止标记。
        // 槽位 0 = 主输入框，1/2 = 点 + 加出来的输入框。快捷指令页命令固定走槽位 0。
        private const int MAX_SLOT = App.SLOT_COUNT;
        private Thread[] _worker = new Thread[MAX_SLOT];
        private volatile bool[] _busy = new bool[MAX_SLOT];
        private volatile int[] _cmdSource = new int[MAX_SLOT];   // 0=指令输入页 1=快捷指令页
        private volatile bool[] _stopRequested = new bool[MAX_SLOT];
        private string[] _lastCmd = new string[MAX_SLOT];
        private string _uiPath;

        // 原生加载遮罩（WebView2 就绪前的过渡，避免白屏）
        private Panel _splashPanel;
        private System.Windows.Forms.Timer _splashTimer;

        // ---------------- 自检通道（2026-11-17 O6） ----------------
        // 目的：让 --selfcheck 测**真正在跑的界面**（GuiWeb + ui.html），
        // 而不是 A12 之后就没再上过阵的 WinForms 老窗体 GuiMain。
        // 打开方式：GuiEntry 在 --selfcheck 时不直接 return，而是照常建窗，
        // 把 SelfCheckMode 置 true —— 复用真实启动链路（Embed 释放、GuiBoot、
        // WebView2 初始化、页面加载），测出来的才是用户看到的东西。
        internal bool SelfCheckMode = false;
        private volatile bool _navDone = false;
        private bool _selfCheckStarted = false;

        // ---- UI 测试通道（377 用，2026-11-18）----
        // 为什么需要：377 原来用 msedge --headless --dump-dom 量 ui.html。换到
        // Edge 154 之后，headless 下根元素(html/body)与伪元素(::after)的
        // getComputedStyle 返回的是**不更新的快照**（现场插 !important 规则都不生效），
        // 且 --virtual-time-budget 会冻结动画时钟，.frame 的入场动画(fill:backwards)
        // 被钉在 opacity:0 —— 9 条断言必红，跟代码对错无关。
        // 现在改为在**真实 WebView2** 里跑：同一个 GuiWeb、同一个渲染器，量到的就是
        // 用户看到的东西。复用的是自检那条链路（离屏窗口 + 页面就绪后 ExecuteScriptAsync）。
        // ProbeJs 非空即进入该模式：页面就绪后执行它，结果经 ProbeResult 回传。
        internal string ProbeJs = null;
        internal int ProbeWaitMs = 800;
        internal Action<string> ProbeResult = null;
        // 诊断用：off-screen 窗口会被 Chromium 判为"被遮挡"，动画/合成被节流，
        // 入场动画永远停在 currentTime=0，量出来的是"隐藏态"。置 true 时窗口留在
        // 屏幕内，动画按真实时钟跑完 —— 用来区分"页面真有问题"和"离屏导致的假象"。
        internal bool ProbeOnScreen = false;

        internal bool NavDone { get { return _navDone; } }

        // 页面就绪后延迟一拍再跑（splash 淡出 280ms + buildSlots 在 DOMContentLoaded）
        private void StartSelfCheck()
        {
            if (_selfCheckStarted) return;
            _selfCheckStarted = true;
            System.Windows.Forms.Timer t = new System.Windows.Forms.Timer();
            t.Interval = ProbeWaitMs > 0 ? ProbeWaitMs : 800;
            t.Tick += delegate
            {
                try { t.Stop(); t.Dispose(); } catch { }
                string js = ProbeJs;
                if (js != null)
                {
                    // UI 测试：把页面里注入的断言脚本的自述结果取回来
                    EvalForSelfCheck(js, delegate(string r)
                    {
                        try { if (ProbeResult != null) ProbeResult(r); }
                        catch (Exception ex) { GuiEntry.Dump("uitest result", ex); }
                    });
                    return;
                }
                try { GuiSelfCheck.RunOn(this); } catch (Exception ex) { GuiEntry.Dump("selfcheck", ex); }
            };
            t.Start();
        }

        // 把一段 JS 丢给页面执行，结果回 UI 线程。
        // 自检专用：不参与任何业务逻辑，失败一律回空串而不是抛。
        internal void EvalForSelfCheck(string js, Action<string> done)
        {
            try
            {
                if (_web == null || _web.CoreWebView2 == null) { done(""); return; }
                System.Threading.Tasks.Task<string> task =
                    _web.CoreWebView2.ExecuteScriptAsync(js);
                task.ContinueWith(delegate(System.Threading.Tasks.Task<string> x)
                {
                    string r = "";
                    try { r = x.Result; }
                    catch (Exception ex) { GuiEntry.Dump("selfcheck eval", ex); }
                    // 注意：不能写 (done)(r) —— C# 会把 (done) 当成类型做强制转换。
                    try { done(r); }
                    catch { }
                }, System.Threading.Tasks.TaskScheduler.FromCurrentSynchronizationContext());
            }
            catch (Exception ex)
            {
                GuiEntry.Dump("selfcheck eval", ex);
                try { done(""); } catch { }
            }
        }

        internal GuiWeb(string uiPath)
        {
            _uiPath = uiPath;
            // A17：标题只留产品名。原来叫「网联服务_Adb_Tool」——
            // 用户看到的是任务栏预览 / Alt+Tab 里那一长串，而且"网联服务"是
            // 某一轮需求里加的定语，不是产品名，容易误以为是另一个工具。
            Text = "Adb_Tool";
            ShowIcon = false;
            // 需求2：多屏场景下强制居中到**主屏**。
            // FormStartPosition.CenterScreen 在多显示器下会居中到"当前工作屏幕"
            // （可能是副屏/拓展屏），用户取消拓展后副屏没了，窗口就可能出现在
            // 屏幕外看不见。这里改成 Manual，在 Load 时按 Screen.PrimaryScreen
            // 的工作区中心定位，保证永远落在主屏、永远可见。
            StartPosition = FormStartPosition.Manual;
            ClientSize = new Size(1100, 760);
            MinimumSize = new Size(820, 560);

            // ---- 2026-11-15：自绘标题栏 ----
            // 原生 DWM 标题栏实测在深色 / 浅色下都是纯黑 #000、文字恒白：
            // 既跟不上应用主题，字体也改不了（用户连续三条反馈：颜色不跟随、
            // 切模式没变化、字体和全局不一致）。改成无边框窗口，标题栏画进 ui.html，
            // 颜色走 CSS 令牌、字体跟随全局字体设置，窗口按钮也统一成一套视觉。
            FormBorderStyle = FormBorderStyle.None;

            // Dock/任务栏图标：加载 exe 内嵌的黑猫 ico（Windows 任务栏/Alt+Tab
            // 切换器里显示它，与文件管理器、标题栏一致）
            TrySetCatIcon();

            // 预先创建桌面 logcat 文件夹：截图/录屏/HCI 导出都往这里放（需求5）
            EnsureLogcatDir();

            // 顺手清掉老版本留在 exe 同级的 WebView2 缓存（约 70 MB）。
            // 后台线程执行，不阻塞窗口显示。
            CleanupLegacyWebData();

            BuildUi();
            InstallSink();
            BootDevice();

            // 深色标题栏：默认是白底标题栏 + 深色界面，两者衔接突兀。
            // 延迟到句柄就绪后再开 immersive dark mode。
            HandleCreated += (s, e) => ApplyDarkTitleBar();

            // 窗口显示前居中到主屏（需求2：取消拓展屏后仍落在主屏）
            Load += (s, e) => CenterToPrimaryScreen();
        }

        // 把窗口居中到主显示器的工作区（需求2）。
        // 用 PrimaryScreen.WorkingArea 而非 Bounds：避开任务栏，保证窗口标题栏可见。
        private void CenterToPrimaryScreen()
        {
            try
            {
                // 自检模式：窗口移到屏幕外。WebView2 需要真实 HWND 与消息泵才能
                // 完成初始化，所以不能"不显示"；但也不能抢用户焦点。
                // ProbeOnScreen 时例外：离屏会被判为遮挡，动画被节流（见字段注释）。
                if (SelfCheckMode && !ProbeOnScreen)
                {
                    Location = new System.Drawing.Point(-8000, 0);
                    return;
                }
                Screen primary = Screen.PrimaryScreen;
                if (primary == null) return;
                System.Drawing.Rectangle wa = primary.WorkingArea;
                int x = wa.Left + Math.Max(0, (wa.Width - Width) / 2);
                int y = wa.Top + Math.Max(0, (wa.Height - Height) / 2);
                // 若窗口比工作区还大（极小屏），贴左上角，避免负坐标跑到屏外
                Location = new System.Drawing.Point(x, y);
            }
            catch { }
        }

        // 预建导出目录树：桌面\logcat\<今天>\{screencap,screenrecord,HCI}
        // 需求：导出文件按「日期 / 分类」两级存放，不再全平铺在 logcat 根下。
        // 启动时就建好，用户点导出必然有落点，不会因为目录不存在而写失败
        // （重定向 `> path` 到不存在的目录是直接报错的）。
        private void EnsureLogcatDir()
        {
            try
            {
                // 不带分类 = 只到日期层；再逐个补三个分类子目录。
                // 走 App.OutDir 保证与 cmds.ini 里 $(out:xxx) 用的是同一套规则。
                App.OutDir("");
                App.OutDir("shot");
                App.OutDir("rec");
                App.OutDir("hci");
            }
            catch { }
        }

        // 从 exe 所在目录加载黑猫 ico 设为窗口图标（找不到则尝试内嵌图标）
        private void TrySetCatIcon()
        {
            try
            {
                string icp = System.IO.Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "adb_Tool.ico");
                if (System.IO.File.Exists(icp))
                {
                    using (Icon ic = new Icon(icp)) { Icon = (Icon)ic.Clone(); }
                }
                else
                {
                    // 兜底：从 exe 本身提取图标（/win32icon 已把黑猫嵌入）
                    Icon = System.Drawing.Icon.ExtractAssociatedIcon(
                        System.Reflection.Assembly.GetEntryAssembly().Location);
                }
            }
            catch { }
        }

        // ---------------- 深色标题栏 ----------------

        [System.Runtime.InteropServices.DllImport("dwmapi.dll")]
        private static extern int DwmSetWindowAttribute(
            IntPtr hwnd, int attr, ref int attrValue, int attrSize);

        private const int DWMWA_USE_IMMERSIVE_DARK_MODE = 20;   // Win10 19041+/Win11
        private const int DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19; // 旧版回退值

        private void ApplyDarkTitleBar()
        {
            SetTitleBarDark(true);
        }

        // ---------------- 自绘标题栏：原生能力桥接（2026-11-15） ----------------
        // 无边框后这些能力都得自己接：拖动 = 伪造一次"点在标题栏上"，
        // 边缘缩放 = 伪造一次"点在某条边框上"，都交回系统做（含 DPI、最小尺寸、
        // 贴边分屏），不自己算坐标 —— 自己算在缩放/多屏下必翻车。
        [System.Runtime.InteropServices.DllImport("user32.dll")]
        private static extern bool ReleaseCapture();

        [System.Runtime.InteropServices.DllImport("user32.dll")]
        private static extern IntPtr SendMessage(IntPtr hWnd, int msg, IntPtr wParam, IntPtr lParam);

        private const int WM_NCLBUTTONDOWN = 0x00A1;
        private const int HTCAPTION = 2;

        // 页面驱动的边缘缩放：记住按下瞬间的窗口矩形，之后只套"总位移"
        private bool _rzActive = false;
        private string _rzDir = "";
        private Rectangle _rzRect = Rectangle.Empty;

        // 无边框窗口默认最大化会铺满整屏、盖住任务栏：限制到当前屏工作区。
        // 拖到别的显示器后要重算，否则在副屏最大化会跑偏。
        private void UpdateMaximizedBounds()
        {
            try
            {
                if (WindowState != FormWindowState.Normal) return;
                Rectangle wa = Screen.FromControl(this).WorkingArea;
                if (MaximizedBounds != wa) MaximizedBounds = wa;
            }
            catch { }
        }

        // ================= A13：圆角窗口 + 跨屏最大化 =================
        //
        // 为什么圆角要分两条路：
        //   Win11 有 DWMWA_WINDOW_CORNER_PREFERENCE，交给 DWM 画，边缘是抗锯齿的；
        //   Win10 没有这个属性，只能 SetWindowRgn 按像素裁，边缘必然有 1px 台阶。
        //   这不是"没做好"，是系统能力差异 —— WebView2 不支持透明分层窗口，
        //   所以 Win10 上不存在第二条能出抗锯齿的路。
        [System.Runtime.InteropServices.DllImport("user32.dll")]
        private static extern int SetWindowRgn(IntPtr hWnd, IntPtr hRgn, bool bRedraw);

        [System.Runtime.InteropServices.DllImport("gdi32.dll")]
        private static extern IntPtr CreateRoundRectRgn(
            int x1, int y1, int x2, int y2, int w, int h);

        [System.Runtime.InteropServices.DllImport("dwmapi.dll")]
        private static extern int DwmGetWindowAttribute(
            IntPtr hwnd, int attr, out int val, int size);

        private const int DWMWA_WINDOW_CORNER_PREFERENCE = 33;
        private const int DWMWCP_ROUND = 2;      // 标准圆角（系统设置页同款）
        private const int DWMWCP_ROUNDSMALL = 3; // 小圆角

        private const int WM_GETMINMAXINFO = 0x0024;
        private const int WM_DPICHANGED = 0x02E0;

        private bool _dwmCorner = false;   // DWM 圆角是否接管（true 时不再设 region）
        private int _cornerDip = 8;        // 圆角半径（DIP，按 DPI 换算成像素）

        [System.Runtime.InteropServices.StructLayout(
            System.Runtime.InteropServices.LayoutKind.Sequential)]
        private struct POINTAPI { public int X; public int Y; }

        [System.Runtime.InteropServices.StructLayout(
            System.Runtime.InteropServices.LayoutKind.Sequential)]
        private struct MINMAXINFO
        {
            public POINTAPI ptReserved;
            public POINTAPI ptMaxSize;       // 最大化时的宽高
            public POINTAPI ptMaxPosition;   // 最大化时的左上角
            public POINTAPI ptMinTrackSize;
            public POINTAPI ptMaxTrackSize;
        }

        // 窗体底色跟主题 —— 圆角裁开四角后，露出来的就是这层颜色。
        // 不跟着主题的话，白天/护眼主题下四角会露出构造时写死的深色块。
        private void ApplyChromeColor()
        {
            try
            {
                if (App.THEME == "light") BackColor = Color.FromArgb(254, 254, 255);
                else if (App.THEME == "eye") BackColor = Color.FromArgb(255, 251, 240);
                else BackColor = Color.FromArgb(13, 17, 23);
            }
            catch { }
        }

        // Win11：交给 DWM 画抗锯齿圆角。返回非 0 说明系统不支持（Win10），
        // 之后统一走 region 兜底。
        private void TryDwmCorner()
        {
            try
            {
                int build = Environment.OSVersion.Version.Build;
                if (build < 22000) { _dwmCorner = false; return; }

                int v = DWMWCP_ROUND;
                int hr = DwmSetWindowAttribute(
                    Handle, DWMWA_WINDOW_CORNER_PREFERENCE, ref v, sizeof(int));
                _dwmCorner = (hr == 0);

                // 读回校验：属性没被采纳时（部分无边框窗口会被忽略）退回 region。
                if (_dwmCorner)
                {
                    int back = -1;
                    if (DwmGetWindowAttribute(
                            Handle, DWMWA_WINDOW_CORNER_PREFERENCE, out back, sizeof(int)) == 0)
                    {
                        if (back != DWMWCP_ROUND && back != DWMWCP_ROUNDSMALL) _dwmCorner = false;
                    }
                }
            }
            catch { _dwmCorner = false; }
        }

        // 按当前尺寸 / DPI / 窗口状态重设圆角。三种情况：
        //   · 最大化或全屏  -> 取消圆角（全屏圆角是错的，而且尺寸变化会闪）
        //   · DWM 已接管     -> 什么都不做，交给系统（Win11，抗锯齿）
        //   · 其余            -> SetWindowRgn 按像素裁（Win10，1px 台阶）
        private void ApplyWindowCorner()
        {
            try
            {
                if (!IsHandleCreated) return;

                if (WindowState != FormWindowState.Normal)
                {
                    SetWindowRgn(Handle, IntPtr.Zero, true);
                    return;
                }
                if (_dwmCorner) return;

                int dpi = 96;
                try { dpi = DeviceDpi; } catch { }
                int r = (int)Math.Round(_cornerDip * (dpi / 96.0));
                if (r < 2) r = 2;

                // 宽高 +1：CreateRoundRectRgn 的右/下边界是开区间，不加会在右边和下边
                // 各少 1px，表现为窗口右下角有一条 1px 的缝。
                IntPtr h = CreateRoundRectRgn(0, 0, Width + 1, Height + 1, r * 2, r * 2);

                // SetWindowRgn 会接管这个 region 的所有权，系统负责释放 ——
                // 这里绝对不能再 DeleteObject，否则重复释放直接崩。
                SetWindowRgn(Handle, h, true);
            }
            catch { }
        }

        // ==================== A15：窗口开合与任务栏收起 ====================
        //
        // 1) 点任务栏图标不收起 —— 根因是样式位缺 WS_MINIMIZEBOX。
        //    实测本窗口样式 0x16010000 = VISIBLE|CLIPSIBLINGS|CLIPCHILDREN|TABSTOP，
        //    没有 WS_MINIMIZEBOX(0x00020000)。资源管理器据此判定"不可最小化"，
        //    点任务栏只激活不发 SC_MINIMIZE。无 WS_CAPTION 时补这一位不会画出
        //    系统按钮（标题栏是我们自绘的），只影响外壳判定。
        private const int WS_MINIMIZEBOX = 0x00020000;
        private const int WM_ACTIVATE = 0x0006;
        private const int WA_INACTIVE = 0;

        protected override CreateParams CreateParams
        {
            get
            {
                CreateParams cp = base.CreateParams;
                cp.Style |= WS_MINIMIZEBOX;
                // A17：无边框窗口在浅色桌面上"看不出边界"。
                // CS_DROPSHADOW 让系统给一层投影（配合页面内的 1px 描边），
                // 比自己在网页里画外阴影可靠 —— 网页画不了窗口以外的区域。
                cp.ClassStyle |= 0x00020000;   // CS_DROPSHADOW
                return cp;
            }
        }

        [System.Runtime.InteropServices.DllImport("user32.dll")]
        private static extern IntPtr GetForegroundWindow();
        [System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
        private static extern int GetClassName(IntPtr hWnd, StringBuilder sb, int max);
        [System.Runtime.InteropServices.DllImport("user32.dll")]
        private static extern bool SetWindowPos(IntPtr hWnd, IntPtr after,
            int x, int y, int cx, int cy, uint flags);

        private bool _tbChecking = false;

        /// <summary>
        /// 兜底：个别外壳版本即便有 WS_MINIMIZEBOX 也不发 SC_MINIMIZE（无边框窗口常见）。
        /// 判定方式 —— 窗口失活后看前台窗口的类名：任务是 Shell_TrayWnd /
        /// Shell_SecondaryTrayWnd 就说明用户点的是任务栏图标，自己收起。
        /// 点其它窗口时前台是那个窗口，不会误触发。
        /// </summary>
        private void CheckTaskbarMinimize()
        {
            if (_tbChecking) return;
            if (_closing) return;         // A17：正在关就别再插一脚把它最小化
            _tbChecking = true;
            System.Windows.Forms.Timer t = new System.Windows.Forms.Timer();
            t.Interval = 120;
            t.Tick += delegate
            {
                t.Stop();
                t.Dispose();
                _tbChecking = false;
                try
                {
                    IntPtr fg = GetForegroundWindow();
                    if (fg == IntPtr.Zero) return;
                    StringBuilder sb = new StringBuilder(96);
                    GetClassName(fg, sb, sb.Capacity);
                    string cn = sb.ToString();
                    if (cn == "Shell_TrayWnd" || cn == "Shell_SecondaryTrayWnd")
                        if (WindowState != FormWindowState.Minimized)
                            // A16：不再改窗口尺寸；A17：补上内容层收起动效。
                            PlayOutThen(delegate
                            {
                                if (WindowState != FormWindowState.Minimized)
                                    WindowState = FormWindowState.Minimized;
                            });
                }
                catch { }
            };
            t.Start();
        }

        // ==================== A16：窗口开合（不再改窗口尺寸） ====================
        // 上一版为了让窗口"从任务栏长出来"，用 SetWindowPos 把窗口**真缩**到 168x100，
        // 再靠 11 帧定时器放大回去。三个必现故障全部出在"改尺寸"这一步本身：
        //   ① 动画目标是运行时读的 Bounds —— 只要重入一次，目标就变成 168x100，
        //      窗口永远回不到正常大小；
        //   ② WebView2 初始化会堵住 UI 线程消息泵 1~3 秒，定时器帧整段丢失，
        //      动画停在第一帧，用户看到的就是"打开很小、点不动"；
        //   ③ 任何中断（另一个动画 Stop 掉这一个、OnFormClosing 被取消）都会把窗口
        //      停在中间尺寸**且不最小化** —— 用户截图里那个矮窗口正是这个残局。
        // 这一版彻底不碰窗口尺寸：窗口一步到位，动效交给页面内容
        // transform:scale(.94)→1 淡入（120ms，只重排一次，比每帧重排 11 次更省）。
        // 另加一道 EnsureSaneBounds 兜底，尺寸只要低于 MinimumSize 就立刻拉回。
        private Rectangle _sane;      // 最近一次"正常尺寸"，只用于兜底恢复

        // ==================== A17：收起 / 关闭动效（同样不碰窗口尺寸） ====================
        // 页面侧只加一个 .v17-out class（scale .96 + opacity 0，130ms），
        // 播完再由这里执行真正的动作（最小化 / Close）。
        // 这样"点一下就有反馈"，即使后面的清理慢，用户也不会以为没点上。
        private bool _closing;

        /// <summary>
        /// 关窗看门狗：清理路径（adb 同步读、线程 Abort）有可能卡住，
        /// 卡住时用户看到的是"窗口没了但进程还在、任务管理器里还挂着一个"。
        /// 给一个硬上限，超过就直接退，绝不把"关不掉"留给用户。
        /// 用后台线程而不是 Timer：UI 线程此时正好可能被清理堵住。
        /// </summary>
        private static void StartExitWatchdog(int ms)
        {
            try
            {
                System.Threading.ThreadPool.QueueUserWorkItem(delegate
                {
                    try { System.Threading.Thread.Sleep(ms); } catch { }
                    try { Environment.Exit(0); } catch { }
                });
            }
            catch { }
        }

        /// <summary>先让页面播 130ms 的收起动效，再执行 after。</summary>
        private void PlayOutThen(Action after)
        {
            bool started = false;
            try
            {
                if (_web != null && _web.CoreWebView2 != null)
                {
                    _web.CoreWebView2.ExecuteScriptAsync("window.v17Out && window.v17Out()");
                    started = true;
                }
            }
            catch { }
            if (!started) { try { after(); } catch { } return; }
            System.Windows.Forms.Timer t = new System.Windows.Forms.Timer();
            t.Interval = 130;
            t.Tick += delegate
            {
                t.Stop();
                t.Dispose();
                try { after(); } catch { }
            };
            t.Start();
        }

        /// <summary>记住当前正常尺寸（最小化 / 最大化时不动它）。</summary>
        private void RefreshSane()
        {
            try
            {
                if (IsDisposed) return;
                if (WindowState != FormWindowState.Normal) return;
                Rectangle b = Bounds;
                if (b.Width >= MinimumSize.Width && b.Height >= MinimumSize.Height) _sane = b;
            }
            catch { }
        }

        /// <summary>
        /// 尺寸兜底：窗口一旦被缩到比 MinimumSize 还小（历史遗留动画、外部
        /// SetWindowPos、Aero Snap 异常），立刻拉回 _sane，绝不留"小到不能用"的窗口。
        /// </summary>
        private void EnsureSaneBounds()
        {
            try
            {
                if (IsDisposed || !IsHandleCreated) return;
                if (WindowState != FormWindowState.Normal) return;
                Rectangle b = Bounds;
                int minW = MinimumSize.Width, minH = MinimumSize.Height;
                if (b.Width >= minW && b.Height >= minH) { _sane = b; return; }

                Rectangle t = _sane;
                if (t.Width < minW || t.Height < minH)
                {
                    Rectangle wa = Screen.FromHandle(Handle).WorkingArea;
                    int w = Math.Min(Math.Max(minW, 1100), wa.Width);
                    int h = Math.Min(Math.Max(minH, 760), wa.Height);
                    t = new Rectangle(wa.Left + (wa.Width - w) / 2,
                                      wa.Top + (wa.Height - h) / 2, w, h);
                }
                // SWP_NOZORDER(0x0004) | SWP_NOACTIVATE(0x0010)
                SetWindowPos(Handle, IntPtr.Zero, t.X, t.Y, t.Width, t.Height, 0x0004 | 0x0010);
                _sane = t;
                GuiEntry.Dump("EnsureSaneBounds 拉回尺寸",
                    new Exception(b.Width + "x" + b.Height + " -> " + t.Width + "x" + t.Height));
            }
            catch { }
        }

        protected override void OnShown(EventArgs e)
        {
            base.OnShown(e);
            // 窗口尺寸在构造函数里就定了，这里只做一次兜底校验 ——
            // 不再存在"先缩小再放大"的中间态，从根上不可能出现小窗口。
            RefreshSane();
            EnsureSaneBounds();
        }

        // 最大化尺寸实时算：不用 MaximizedBounds。
        // MaximizedBounds 是"设一次就一直用"的缓存，窗口拖到另一块屏（不同分辨率/
        // 不同 DPI）后它还是老值 —— 这就是"接 27 寸屏后最大化没铺满"的根因。
        // WM_GETMINMAXINFO 每次最大化都会问一遍，在这里按当前屏工作区回答即可。
        protected override void WndProc(ref Message m)
        {
            try
            {
                if (m.Msg == WM_GETMINMAXINFO)
                {
                    Rectangle wa = Screen.FromHandle(Handle).WorkingArea;
                    MINMAXINFO mmi = (MINMAXINFO)m.GetLParam(typeof(MINMAXINFO));
                    mmi.ptMaxPosition.X = wa.Left;
                    mmi.ptMaxPosition.Y = wa.Top;
                    mmi.ptMaxSize.X = wa.Width;
                    mmi.ptMaxSize.Y = wa.Height;
                    // A16：开合不再改窗口尺寸，跟踪下限恢复成真实 MinimumSize。
                    // 这一条同时是"不可能再出现小窗口"的系统级保险：即使有人
                    // （或某个残留的 SetWindowPos）想把窗口缩得更小，系统也会夹住。
                    mmi.ptMinTrackSize.X = MinimumSize.Width;
                    mmi.ptMinTrackSize.Y = MinimumSize.Height;
                    System.Runtime.InteropServices.Marshal.StructureToPtr(
                        mmi, m.LParam, false);
                    return;
                }
                if (m.Msg == WM_ACTIVATE)
                {
                    // 点任务栏图标收起（兜底，见 CheckTaskbarMinimize 注释）
                    int wa2 = (int)(m.WParam.ToInt64() & 0xFFFF);
                    if (wa2 == WA_INACTIVE) CheckTaskbarMinimize();
                    else
                    {
                        // A16：从最小化恢复 / 被激活时校验一次尺寸。
                        // 用 BeginInvoke 延后，等 WindowState 真正回到 Normal 再判断，
                        // 否则会把恢复过程中的临时状态误判成"尺寸异常"。
                        try
                        {
                            BeginInvoke((Action)delegate
                            {
                                if (_closing) return;       // A17：正在关就别再拉尺寸
                                RefreshSane();
                                EnsureSaneBounds();
                                // 从最小化恢复：把收起动效留下的 scale/opacity 复位
                                try
                                {
                                    if (_web != null && _web.CoreWebView2 != null)
                                        _web.CoreWebView2.ExecuteScriptAsync(
                                            "window.v17InRestore && v17InRestore()");
                                }
                                catch { }
                            });
                        }
                        catch { }
                    }
                }
                if (m.Msg == WM_DPICHANGED)
                {
                    // 拖到另一块 DPI 不同的屏：圆角像素半径要按新 DPI 重算
                    base.WndProc(ref m);
                    ApplyWindowCorner();
                    return;
                }
            }
            catch { }
            base.WndProc(ref m);
        }

        protected override void OnLoad(EventArgs e)
        {
            base.OnLoad(e);
            UpdateMaximizedBounds();

            // ---- A13：圆角 + 窗体底色 ----
            // 圆角要在句柄就绪后才能设；底色必须在圆角之前定好，
            // 否则裁掉四角的一瞬间会露出构造时那个深色底。
            ApplyChromeColor();
            TryDwmCorner();
            ApplyWindowCorner();
        }

        protected override void OnResize(EventArgs e)
        {
            base.OnResize(e);
            PushWinState();

            // region 是按像素矩形生成的，窗口一变就必须重设，否则四角会残留旧曲线。
            // 最大化时这里会走「取消圆角」分支，正好避免全屏出现圆角。
            ApplyWindowCorner();

            // A18：内嵌投屏是原生子窗口，不会跟着 HTML 重排，窗口一变就得重新摆。
            // 每格重新按上次的比例摆一次（页面会再回报一次精确值，这里先粗摆防跳）。
            try
            {
                if (_castHost != null)
                {
                    for (int i = 0; i < CAST_SLOTS; i++)
                        if (_castHost[i] != null && _castHost[i].Visible)
                            ScrcpyEmbedPlace("{\"slot\":" + i + "}");
                }
            }
            catch { }
        }

        // 最大化 / 还原后要告诉页面：最大化按钮图标要换成"还原"，边缘热区要藏起来。
        private void PushWinState()
        {
            try
            {
                if (_web == null || _web.CoreWebView2 == null) return;
                _web.CoreWebView2.PostWebMessageAsJson(
                    "{\"kind\":\"winstate\",\"max\":"
                    + (WindowState == FormWindowState.Maximized ? "1" : "0") + "}");
            }
            catch { }
        }

        private void PushRaw(string json)
        {
            try
            {
                if (_web != null && _web.CoreWebView2 != null)
                    _web.CoreWebView2.PostWebMessageAsJson(json);
            }
            catch { }
        }

        // ---------------- 界面搭建 ----------------

        // WebView2 用户数据目录（运行期缓存，约 70 MB，绝不能放进发布目录）。
        //
        // 落点优先级：
        //   1) %LOCALAPPDATA%\adb_Tool\WebView2   —— 正常情况
        //   2) %TEMP%\adb_Tool_WebView2           —— LocalAppData 取不到时兜底
        //   3) exe 目录\wb2data                   —— 最后兜底（至少能跑起来）
        // 每层都要保证目录存在，CreateAsync 不会替你建。
        private static string ResolveWebDataDir()
        {
            string root = "";
            try
            {
                root = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            }
            catch { root = ""; }

            if (string.IsNullOrEmpty(root) || root.Trim().Length == 0)
            {
                try { root = Environment.GetEnvironmentVariable("LOCALAPPDATA"); }
                catch { root = ""; }
            }

            if (!string.IsNullOrEmpty(root) && root.Trim().Length > 0)
            {
                return System.IO.Path.Combine(root, "adb_Tool", "WebView2");
            }

            try
            {
                string tmp = System.IO.Path.GetTempPath();
                if (!string.IsNullOrEmpty(tmp) && tmp.Trim().Length > 0)
                {
                    return System.IO.Path.Combine(tmp, "adb_Tool_WebView2");
                }
            }
            catch { }

            return System.IO.Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "wb2data");
        }

        // 清理旧版本遗留在 exe 目录里的 wb2data（最多 70 MB）。
        //
        // 老版本把缓存写在 exe 同级，升级上来的机器目录里还留着这份垃圾。
        // 这里在启动时顺手删掉 —— 但要满足两个前提，避免误删或删一半：
        //   1) 目录必须在 exe 同级（只删自己那份，绝不碰别的路径）；
        //   2) 删除失败就静默放弃（可能被占用），下次启动再试，绝不报错打扰用户。
        // 用后台线程做，避免删除 70 MB 时窗口卡住。
        private static void CleanupLegacyWebData()
        {
            try
            {
                string baseDir = AppDomain.CurrentDomain.BaseDirectory;
                string legacy = System.IO.Path.Combine(baseDir, "wb2data");
                bool hasDir = System.IO.Directory.Exists(legacy);

                // 旧版本的诊断日志也写在 exe 同级，一并清掉（现在改到 LocalAppData\logs）。
                // 但如果日志目录本身就兜底回了 exe 同级，那就不能删 —— 那是当前正在写的。
                string[] legacyFiles = new string[] { "gui_trace.log", "gui_error.log", "gui_selfcheck.log" };
                bool hasFile = false;
                bool sameDir = string.Equals(
                    System.IO.Path.GetFullPath(GuiEntry.LogDir()).TrimEnd('\\'),
                    System.IO.Path.GetFullPath(baseDir).TrimEnd('\\'),
                    StringComparison.OrdinalIgnoreCase);
                if (!sameDir)
                {
                    for (int i = 0; i < legacyFiles.Length; i++)
                    {
                        if (System.IO.File.Exists(System.IO.Path.Combine(baseDir, legacyFiles[i])))
                            hasFile = true;
                    }
                }
                if (!hasDir && !hasFile) return;

                System.Threading.Thread t = new System.Threading.Thread(
                    new System.Threading.ThreadStart(delegate()
                    {
                        if (hasDir)
                        {
                            try { System.IO.Directory.Delete(legacy, true); }
                            catch { /* 被占用 / 无权限：留给下次 */ }
                        }
                        if (!sameDir)
                        {
                            for (int i = 0; i < legacyFiles.Length; i++)
                            {
                                try
                                {
                                    string f = System.IO.Path.Combine(baseDir, legacyFiles[i]);
                                    if (System.IO.File.Exists(f)) System.IO.File.Delete(f);
                                }
                                catch { }
                            }
                        }
                    }));
                t.IsBackground = true;
                t.Start();
            }
            catch { }
        }

        private void BuildUi()
        {
            _web = new WebView2();
            _web.Dock = DockStyle.Fill;
            Controls.Add(_web);

            // 原生加载遮罩：WebView2 环境初始化 + 页面加载这段"白屏期"，
            // 用一个深色面板 + 黑猫 Drawing 盖住，打开应用立即看到动画，
            // 而不是白屏。页面真正渲染出来后（NavigationCompleted）再移除。
            AddSplashOverlay();

            // WebView2 环境初始化完成后加载本地 ui.html
            _web.CoreWebView2InitializationCompleted += OnCoreReady;

            // 页面发来的消息
            _web.WebMessageReceived += OnWebMessage;

            // 页面导航完成 = 网页已经加载（含它自己的黑猫 splash），
            // 此时可安全撤掉原生遮罩，交给网页端的 splash 继续过渡。
            _web.NavigationCompleted += (s, e) =>
            {
                _navDone = true;
                FinishInvoke(RemoveSplashOverlay);
                if (SelfCheckMode) FinishInvoke(StartSelfCheck);
            };
            // 【性能优化】原来 `CreateAsync(...).Result` 同步阻塞主线程，窗口白屏。
            // 改为纯异步:主线程立刻返回显示窗口+加载遮罩,运行时就绪后再加载页面。
            // 【体积优化 2026-11-12】WebView2 用户数据目录不能放在 exe 同级目录。
            //
            // 原写法 Path.Combine(BaseDirectory, "wb2data") 会把这块数据塞进发布目录。
            // 而 WebView2 首次运行会自动往这个目录下载/写入一堆组件：
            //     WidevineCdm（Widevine 解密模块）      22 MB
            //     component_crx_cache（组件包缓存）      22 MB
            //     Subresource Filter（广告过滤规则）     13 MB
            //     GrShaderCache / ShaderCache / GPUCache  7 MB
            //     Speech Recognition（语音识别）         2.6 MB
            //     hyphen-data（断词表）/ BrowserMetrics   3 MB
            // 合计 70 MB 上下 —— 这跟工具本身无关，纯属浏览器的运行期缓存。
            // 一旦用户点过一次 exe，发布目录就从 1 MB 涨到 70 MB，
            // 拷给别人/打压缩包时全部带上了，这就是"打包 40 多 MB"的真正来源。
            //
            // 现在改为"用户级应用数据目录"，与 exe 所在位置彻底解耦：
            //     %LOCALAPPDATA%\adb_Tool\WebView2
            // 好处：
            //   1) 发布目录永远只含程序本体（exe + dll + html + ini ≈ 1.2 MB）；
            //   2) 同一台机器上多个副本共用一份缓存，不会每个目录各涨 70 MB；
            //   3) 无写权限的目录（如放在 Program Files）也不会因创建失败而起不来。
            //
            // 注意不能直接用 %LOCALAPPDATA% 环境变量（GUI 环境里可能为空/被改），
            // 用 .NET 的 SpecialFolder 让系统给出权威路径。
            string dir = ResolveWebDataDir();
            try { System.IO.Directory.CreateDirectory(dir); }
            catch { /* 建不出来就让 WebView2 自己再试一次，失败会走下面的 catch */ }
            try
            {
                System.Threading.Tasks.Task<CoreWebView2Environment> t =
                    CoreWebView2Environment.CreateAsync(null, dir);
                t.ContinueWith(done =>
                {
                    if (done.IsFaulted || done.Result == null)
                    {
                        GuiEntry.Dump("WebView2 CreateAsync 失败",
                            done.Exception == null ? new Exception("env null") : done.Exception);
                        return;
                    }
                    try { _web.EnsureCoreWebView2Async(done.Result); }
                    catch (Exception ex) { GuiEntry.Dump("WebView2 Ensure", ex); }
                }, System.Threading.Tasks.TaskScheduler.FromCurrentSynchronizationContext());
            }
            catch (Exception ex)
            {
                GuiEntry.Dump("WebView2 初始化", ex);
                MessageBox.Show(
                    "WebView2 运行时不可用。\r\n请安装 Microsoft Edge WebView2 Runtime 后重试。\r\n\r\n" + ex.Message,
                    "adb_Tool", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        // 原生加载遮罩：深色底 + 居中黑猫呼吸动效（只显示黑猫，不显示文字）
        private void AddSplashOverlay()
        {
            _splashPanel = new Panel();
            _splashPanel.Dock = DockStyle.Fill;
            // A17：启动层不再是纯黑一块。底色留给 SplashPaint 画渐变换掉，
            // 这里只保证未绘制前不是白闪。
            _splashPanel.BackColor = Color.FromArgb(10, 10, 12);
            _splashPanel.Paint += SplashPaint;
            // 30fps 重绘 + 渐变背景，不双缓冲会闪
            try
            {
                System.Reflection.PropertyInfo db = typeof(Panel).GetProperty(
                    "DoubleBuffered", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic);
                if (db != null) db.SetValue(_splashPanel, true, null);
            }
            catch { }
            Controls.Add(_splashPanel);          // 先加入
            _splashPanel.BringToFront();         // 再置顶（顺序不能反，否则无效）

            // 驱动呼吸动画的重绘定时器
            _splashTimer = new System.Windows.Forms.Timer();
            _splashTimer.Interval = 33;  // ~30fps
            _splashTimer.Tick += delegate
            {
                try { if (_splashPanel != null && !_splashPanel.IsDisposed) _splashPanel.Invalidate(); }
                catch { }
            };
            _splashTimer.Start();
        }

        // WebView2 就绪后内部 HWND 可能重建，遮罩可能被盖到下面，
        // 这里再次置顶，确保加载期始终显示黑猫而不是白屏。
        private void ReTopSplash()
        {
            try
            {
                if (_splashPanel != null && !_splashPanel.IsDisposed) _splashPanel.BringToFront();
            }
            catch { }
        }

        private void RemoveSplashOverlay()
        {
            try
            {
                if (_splashTimer != null) { _splashTimer.Stop(); _splashTimer.Dispose(); _splashTimer = null; }
            }
            catch { }
            try
            {
                if (_splashPanel == null) return;
                if (_splashPanel.IsDisposed) return;
                Controls.Remove(_splashPanel);
                _splashPanel.Dispose();
                _splashPanel = null;
            }
            catch { }
        }

        // 强调色 → GDI+ 颜色。表已挪到 App.AccentArgb()（与 CLI 共用一份），
        // 这里只做 int → Color 的转换，避免两处各写一张 switch 再漂移。
        private static Color AccentColor()
        {
            int v = App.AccentArgb();
            return Color.FromArgb((v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF);
        }

        // 启动层：图标 + 呼吸动画 + "正在连接设备"文字
        //
        // A15 修：这一层原来画的是**旧的黑猫**，而且颜色写死 (63,185,155)。
        // 上一轮只换了网页里的 .splash，而 WebView2 初始化要 0.5~2 秒，
        // 用户看到的正是这层原生绘制 —— 所以"启动动画没换"。
        // 现在几何改成与 ui.html / ico 同源（信号双弧 + 中控屏 + >_ + 底座），
        // 颜色取 App.ACCENT，换强调色启动层一起变。
        private void SplashPaint(object sender, PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            g.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
            int w = _splashPanel.Width, h = _splashPanel.Height;

            // A17：背景从"纯黑"换成"高斯模糊渐变" —— 见 PaintSplashBackdrop。
            PaintSplashBackdrop(g, w, h);

            // 呼吸缩放（用时间算，不依赖 timer）
            double t = (DateTime.Now.Ticks / 100000.0) % 2000.0 / 2000.0;  // 0~1 循环 2s
            double breathe = 1.0 + 0.06 * Math.Sin(t * Math.PI * 2);
            float size = (float)(116 * breathe);
            float cx = w / 2f, cy = h / 2f - 16f;

            // 图标颜色跟随强调色（App.AccentArgb，16 色齐全；三白也各是各的白）
            DrawLogo(g, AccentColor(), cx, cy, size);

            // "正在连接设备 …" 文字提醒
            using (SolidBrush tipBrush = new SolidBrush(Color.FromArgb(140, 146, 158)))
            using (Font tipFont = new Font("Microsoft YaHei UI", 12f))
            {
                string tip = "正在连接设备 …";
                SizeF ts = g.MeasureString(tip, tipFont);
                g.DrawString(tip, tipFont, tipBrush, cx - ts.Width / 2f, cy + size / 2f + 22f);
            }
        }

        // 启动层背景：竖向深灰渐变 + 两团强调色光晕（等价于"高斯模糊后的渐变"）。
        //
        // 为什么不用真 blur：GDI+ 没有高斯模糊；把整幅截图缩到 1/16 再双线性放大回来
        // 能做出 blur，但要每帧缩放一张 1100×760 的位图，30fps 下 CPU 直接飙。
        // 这里用 PathGradientBrush 画"中心有色、边缘透明"的径向渐变 —— 视觉上就是
        // 一团被模糊掉的光，成本是一次性画一张、之后每帧贴图。
        // 缓存键 = 尺寸 + 强调色，切强调色或改窗口大小才重画。
        private Bitmap _splashBg;
        private int _splashBgKey;

        private void PaintSplashBackdrop(Graphics g, int w, int h)
        {
            if (w <= 0 || h <= 0) return;
            int key = (w * 397) ^ h ^ (AccentColor().ToArgb() * 31);
            if (_splashBg == null || _splashBgKey != key)
            {
                try
                {
                    if (_splashBg != null) { _splashBg.Dispose(); _splashBg = null; }
                    Bitmap bmp = new Bitmap(w, h);
                    using (Graphics bg = Graphics.FromImage(bmp))
                    {
                        bg.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
                        // ① 底：上浅下深的竖向渐变。
                        //    A18：整体提亮一档（原来 #1A1A20→#070709 太黑，用户要"再白一点"），
                        //    同时把中段拉到 #26282E —— 渐变在视觉上才有"过渡"，不是一块死黑。
                        using (System.Drawing.Drawing2D.LinearGradientBrush lg =
                            new System.Drawing.Drawing2D.LinearGradientBrush(
                                new Rectangle(0, 0, w, h),
                                Color.FromArgb(0x3C, 0x3E, 0x45),
                                Color.FromArgb(0x12, 0x13, 0x16), 90f))
                        {
                            System.Drawing.Drawing2D.ColorBlend cb =
                                new System.Drawing.Drawing2D.ColorBlend(3);
                            cb.Colors = new Color[] {
                                Color.FromArgb(0x3C, 0x3E, 0x45),
                                Color.FromArgb(0x26, 0x28, 0x2E),
                                Color.FromArgb(0x12, 0x13, 0x16) };
                            cb.Positions = new float[] { 0f, 0.52f, 1f };
                            lg.InterpolationColors = cb;
                            bg.FillRectangle(lg, 0, 0, w, h);
                        }
                        // ② 两团强调色光晕：主光在图标正后方，副光偏左下。
                        //    A18：半径与 alpha 都加大 —— 用户要"高斯模糊再多点"，
                        //    光晕铺得越开，越像被大半径模糊过的一张底图。
                        Color a = AccentColor();
                        float m = Math.Min(w, h);
                        DrawGlow(bg, a, w * 0.50f, h * 0.42f, m * 0.78f, 84);
                        DrawGlow(bg, a, w * 0.28f, h * 0.78f, m * 0.62f, 40);
                        // ③ 中央一层极淡白雾：压住上面的彩光，做出"磨砂玻璃"而不是"彩色灯箱"
                        DrawGlow(bg, Color.White, w * 0.50f, h * 0.38f, m * 0.66f, 16);
                        // ④ 四角压暗，把注意力收到中间（比 A17 轻，别又把画面压回黑）
                        DrawGlow(bg, Color.Black, w * 0.02f, h * 0.02f, m * 0.60f, 42);
                        DrawGlow(bg, Color.Black, w * 0.98f, h * 0.98f, m * 0.60f, 42);
                    }
                    _splashBg = bmp;
                    _splashBgKey = key;
                }
                catch { }
            }
            if (_splashBg != null) g.DrawImageUnscaled(_splashBg, 0, 0);
        }

        /// <summary>画一团"中心有色、边缘全透明"的径向渐变，模拟高斯模糊的光晕。</summary>
        private static void DrawGlow(Graphics g, Color c, float cx, float cy, float r, int alpha)
        {
            if (r <= 0) return;
            using (System.Drawing.Drawing2D.GraphicsPath gp = new System.Drawing.Drawing2D.GraphicsPath())
            {
                gp.AddEllipse(cx - r, cy - r, r * 2, r * 2);
                using (System.Drawing.Drawing2D.PathGradientBrush pg =
                    new System.Drawing.Drawing2D.PathGradientBrush(gp))
                {
                    pg.CenterColor = Color.FromArgb(alpha, c);
                    pg.SurroundColors = new Color[] { Color.FromArgb(0, c) };
                    pg.FocusScales = new PointF(0.12f, 0.12f);
                    g.FillPath(pg, gp);
                }
            }
        }

        // 启动层图形 —— A18 起与 ui.html 的 #appmark-glyph **完全同源**：
        // 同一套 100×100 坐标、同样的四块（屏幕面板 / >_ / 双弧 / 底座）、同样的透明度。
        //
        // 为什么必须改：A17 把网页与 ico 换成 100 视窗的简化稿，但这个方法里还留着
        // 24 视窗的旧几何（双弧+屏幕框那一版）。结果是**原生遮罩用旧图，网页 splash
        // 用新图**，两者交接的那一帧图形轮廓会跳一下 —— 用户说的"闪一帧"里有一半是它。
        private void DrawLogo(Graphics g, Color c, float cx, float cy, float size)
        {
            float s = size / 100f;
            float ox = cx - 50f * s, oy = cy - 50f * s;

            // ① 中控屏面板：fill 16% + 1.35 描边 30%（对应 <rect x13 y32 w74 h42 rx10>）
            using (GraphicsPath scr = RoundedRect(ox + 13f * s, oy + 32f * s, 74f * s, 42f * s, 10f * s))
            {
                using (SolidBrush fb = new SolidBrush(Color.FromArgb(41, c)))
                    g.FillPath(fb, scr);
                using (Pen sp = new Pen(Color.FromArgb(77, c), Math.Max(1f, 1.35f * s)))
                    g.DrawPath(sp, scr);
            }

            // ② 终端提示符 >_（唯一的一级高光，纯色不降透明度）
            using (Pen p = new Pen(c, Math.Max(1.6f, 5.8f * s)))
            {
                p.StartCap = System.Drawing.Drawing2D.LineCap.Round;
                p.EndCap = System.Drawing.Drawing2D.LineCap.Round;
                p.LineJoin = System.Drawing.Drawing2D.LineJoin.Round;
                g.DrawLines(p, new PointF[] {
                    new PointF(ox + 33f * s, oy + 46f * s),
                    new PointF(ox + 44f * s, oy + 53f * s),
                    new PointF(ox + 33f * s, oy + 60f * s)
                });
                g.DrawLines(p, new PointF[] {
                    new PointF(ox + 56f * s, oy + 60f * s),
                    new PointF(ox + 67f * s, oy + 60f * s)
                });
            }

            // ③ 信号双弧（圆心 50,27，半径 9 / 16，只画上半圆，透明度 55%）
            using (Pen ap = new Pen(Color.FromArgb(140, c), Math.Max(1f, 3f * s)))
            {
                ap.StartCap = System.Drawing.Drawing2D.LineCap.Round;
                ap.EndCap = System.Drawing.Drawing2D.LineCap.Round;
                g.DrawArc(ap, ox + 41f * s, oy + 18f * s, 18f * s, 18f * s, 180f, 180f);
                g.DrawArc(ap, ox + 34f * s, oy + 11f * s, 32f * s, 32f * s, 180f, 180f);
            }

            // ④ 中控台底座（34% 白）
            using (GraphicsPath led = RoundedRect(ox + 30f * s, oy + 79f * s, 40f * s, 4.5f * s, 2.25f * s))
            using (SolidBrush lb = new SolidBrush(Color.FromArgb(87, c)))
                g.FillPath(lb, led);
        }

        // 圆角矩形 path（GDI+ 无内置 RoundedRect，用 AddArc 拼）
        private GraphicsPath RoundedRect(float x, float y, float w, float h, float r)
        {
            GraphicsPath gp = new GraphicsPath();
            if (r <= 0) { gp.AddRectangle(new RectangleF(x, y, w, h)); return gp; }
            float d = r * 2;
            gp.AddArc(x, y, d, d, 180, 90);
            gp.AddArc(x + w - d, y, d, d, 270, 90);
            gp.AddArc(x + w - d, y + h - d, d, d, 0, 90);
            gp.AddArc(x, y + h - d, d, d, 90, 90);
            gp.CloseFigure();
            return gp;
        }

        private void OnCoreReady(object sender, CoreWebView2InitializationCompletedEventArgs e)
        {
            if (e.IsSuccess)
            {
                try
                {
                    _web.CoreWebView2.Settings.IsZoomControlEnabled = false;

                    // A18/A21：启动"最后一帧蓝色 icon"的根因与彻底修复。
                    //
                    // 根因：ui.html 里 <html data-theme="dark" data-accent="blue"> 是写死的。
                    // 启动层(#splash)图标的颜色 = currentColor = var(--accent)，
                    // 而 --accent 由 data-accent 决定。在用户保存的强调色（如 glasswhite）
                    // 被回填之前，data-accent 还是写死的 blue → 图标本体 + 外圈光晕
                    // 全部是蓝色。之前的修法只在 DocumentCreated 时用 JS 改 data-accent，
                    // 但那个脚本的执行时机晚于浏览器对 <html> 初始属性的首帧样式计算，
                    // 于是"启动动画最后一帧"仍能看到蓝色 —— 用户连报多轮都没根治。
                    //
                    // 彻底修复：不依赖任何 JS 时序，在 Navigate 之前直接把 ui.html 源文件里
                    // 写死的 data-accent / data-theme **字符串替换**成用户保存的真实值，
                    // 写到一个临时副本再加载。这样 HTML 源本身的第一帧就是正确强调色，
                    // 无论脚本何时执行都不会再有蓝帧。保留 DocumentCreated 脚本作为双保险
                    // （防止替换失败时仍回退默认蓝）。
                    string acc = App.NormalizeAccent(App.ACCENT);
                    string thm = App.THEME;
                    if (thm != "light" && thm != "eye") thm = "dark";

                    string uiPathForLoad = _uiPath;
                    // UI 测试模式（ProbeJs 非空）不许宿主改写页面的 data-theme /
                    // data-accent —— 否则测的不是"页面自己切过去的样子"。
                    if (ProbeJs == null)
                    try
                    {
                        string html = System.IO.File.ReadAllText(_uiPath, System.Text.Encoding.UTF8);
                        // 只替换 <html> 标签开头的两个属性值；用正则兜住属性顺序/引号差异。
                        string replaced = System.Text.RegularExpressions.Regex.Replace(
                            html,
                            "(<html[^>]*?data-theme=\")([^\"]*)(\")",
                            "$1" + thm + "$3",
                            System.Text.RegularExpressions.RegexOptions.IgnoreCase);
                        replaced = System.Text.RegularExpressions.Regex.Replace(
                            replaced,
                            "(<html[^>]*?data-accent=\")([^\"]*)(\")",
                            "$1" + acc + "$3",
                            System.Text.RegularExpressions.RegexOptions.IgnoreCase);
                        if (replaced != html)
                        {
                            string tmp = System.IO.Path.Combine(
                                System.IO.Path.GetTempPath(),
                                "adb_Tool_ui_" + System.Diagnostics.Process.GetCurrentProcess().Id + ".html");
                            System.IO.File.WriteAllText(tmp, replaced, new System.Text.UTF8Encoding(false));
                            uiPathForLoad = tmp;
                            App.Trace("accent: 已把 ui.html 默认 data-accent 替换为 " + acc
                                      + "（临时副本 " + tmp + "）");
                        }
                    }
                    catch (Exception exx) { App.Trace("accent: 替换 ui.html 默认值失败 " + exx.Message); }

                    // 双保险：DocumentCreated 时再同步改一次（若上面替换没生效，仍有这一层兜底）
                    if (ProbeJs == null) _web.CoreWebView2.AddScriptToExecuteOnDocumentCreatedAsync(
                        "(function(){ var d=document.documentElement; " +
                        "d.setAttribute('data-theme','" + thm + "'); " +
                        "d.setAttribute('data-accent','" + acc + "'); })();");

                    // 防止 WebView2 缓存旧版 ui.html：file:// 内容改动后
                    // 不刷新会一直显示上一次的界面（用户看到蓝色图标就是缓存）。
                    // 用时间戳 query 让每次加载都走新 URL。
                    string url = new Uri(uiPathForLoad).AbsoluteUri;
                    url += "?v=" + System.IO.File.GetLastWriteTimeUtc(uiPathForLoad).Ticks;
                    _web.CoreWebView2.Navigate(url);

                    // WebView2 内部 HWND 重建后，把原生遮罩重新置顶，
                    // 避免加载期被 WebView2 的白色默认底盖住（问题1）。
                    ReTopSplash();
                }
                catch (Exception ex) { GuiEntry.Dump("加载 ui.html", ex); }
            }
            else
            {
                GuiEntry.Dump("CoreWebView2 初始化失败", e.InitializationException);
            }
        }

        // ---------------- Console → 页面 ----------------

        private void InstallSink()
        {
            _sink = new GuiSink();
            Console.SetOut(_sink);
            Console.SetError(_sink);
            App.GUI_COLOR_HOOK = delegate(ConsoleColor c) { _sink.SyncColor(c); };
            // 流式输出在线程池线程上回调，CUR_SLOT 在那里恒为 0；
            // AdbCallStream 通过这个旁路把"这一行属于哪个槽"带过来。
            App.GUI_SLOT_HOOK = delegate(int slot) { GuiSink.SlotHint = slot; };
            // 后台能力（设备监听/自动重连）的轨迹写进 gui_trace.log：
            // 这类问题没法靠界面复现，只能靠日志定位。
            App.TRACE_HOOK = delegate(string m) { GuiEntry.Trace(m); };
            // 2026-11-15 闪退修复：标记 GUI 模式，CLI 的 q/quit/exit 分支据此
            // 拒绝 Environment.Exit（否则命令框敲 q = 整个窗口无提示消失）。
            App.GUI_MODE = true;

            _tick = new System.Windows.Forms.Timer();
            _tick.Interval = 50;
            _tick.Tick += delegate { PumpOutput(); };
            _tick.Start();

            // 空闲时定时器会降到 250ms（见 PumpOutput），这里在"有新行"的瞬间
            // 把它拉回 33ms —— 否则空闲后敲一条命令，第一行输出最多要等 250ms。
            _sink.OnFirstLine = delegate { WakePump(); };
        }

        // 队列由空变非空：把轮询提速（跨线程，必须回 UI 线程改 Timer）
        private void WakePump()
        {
            try
            {
                FinishInvoke(delegate
                {
                    // 窗口关闭时 Timer 可能已 Dispose，取 Interval 会抛，
                    // 这里必须自己兜住 —— 异常跑在 UI 线程上会直接崩程序。
                    try
                    {
                        if (_tick != null && _tick.Interval != 33) _tick.Interval = 33;
                    }
                    catch { }
                });
            }
            catch { }
        }

        private void PumpOutput()
        {
            // WinForms Timer 回调跑在 UI 线程上，这里任何一个异常都会直接崩程序。
            // 整个泵血逻辑都要兜住 —— 崩了宁可这一帧丢掉，下一 tick 接着来。
            try
            {
            if (_sink == null || _web == null) return;
            GuiSink s = _sink;

            long t0 = Stopwatch.GetTimestamp();
            List<GuiLine> batch = new List<GuiLine>(256);
            // 一次取一批：批量 JSON 后，200 条消息变成 1 条，
            // 200 次 JS 回调变成 1 次，200 次滚动变成 1 次。
            int n = s.DrainTo(batch, 500);
            int dropped = s.TakeDropped();

            if (n > 0 || dropped > 0) PushLines(batch, dropped);

            // 自适应节奏：有积压就快，空闲就慢（减少无意义的唤醒）。
            int interval = 50;
            if (n == 0 && dropped == 0) interval = 250;
            else if (s.Pending > 0) interval = 33;
            if (_tick.Interval != interval) _tick.Interval = interval;

            PerfSample(n, s.Pending, (Stopwatch.GetTimestamp() - t0) * 1000.0 / Stopwatch.Frequency);
            }
            catch (Exception ex) { GuiEntry.Dump("PumpOutput", ex); }
        }

        // 批量推一帧输出。items 里每条仍带 level/src/slot，
        // 页面按 src 分流（日志区 / 反馈区），语义与单行消息完全一致。
        private void PushLines(List<GuiLine> batch, int dropped)
        {
            try
            {
                StringBuilder sb = new StringBuilder(4096 + batch.Count * 64);
                sb.Append("{\"kind\":\"lines\",\"items\":[");
                bool firstItem = true;

                if (dropped > 0)
                {
                    sb.Append("{\"level\":3,\"src\":0,\"slot\":0,\"text\":")
                      .Append(Json("（输出过多，已丢弃最早的 " + dropped + " 行）"))
                      .Append('}');
                    firstItem = false;
                }

                for (int i = 0; i < batch.Count; i++)
                {
                    GuiLine l = batch[i];
                    if (!firstItem) sb.Append(',');
                    firstItem = false;
                    int slot = l.Slot;
                    if (slot < 0 || slot >= MAX_SLOT) slot = 0;
                    sb.Append("{\"level\":").Append(l.Level)
                      .Append(",\"src\":").Append(_cmdSource[slot])
                      .Append(",\"slot\":").Append(slot)
                      .Append(",\"text\":").Append(Json(l.Text))
                      .Append('}');
                }
                sb.Append("]}");
                _web.CoreWebView2.PostWebMessageAsJson(sb.ToString());
            }
            catch { }
        }

        // ---------------- 性能埋点 ----------------
        // 每 5 秒往 logs/gui_perf.log 落一行，便于对比优化前后：
        //   lines/s 吞吐、batch 最大批、q 队列深度、tick 单次耗时
        private long _perfLines = 0, _perfBatches = 0, _perfMaxBatch = 0, _perfLastWrite = 0;
        private double _perfTickMs = 0, _perfMaxTickMs = 0;

        private void PerfSample(int n, int qdepth, double tickMs)
        {
            if (n > 0)
            {
                _perfLines += n;
                _perfBatches++;
                if (n > _perfMaxBatch) _perfMaxBatch = n;
                _perfTickMs += tickMs;
                if (tickMs > _perfMaxTickMs) _perfMaxTickMs = tickMs;
            }
            long now = DateTime.Now.Ticks;
            if (_perfLastWrite == 0) { _perfLastWrite = now; return; }
            if (now - _perfLastWrite < 5 * TimeSpan.TicksPerSecond) return;
            if (_perfBatches == 0) { _perfLastWrite = now; return; }

            double secs = (now - _perfLastWrite) / (double)TimeSpan.TicksPerSecond;
            string line = "t=" + DateTime.Now.ToString("HH:mm:ss")
                + " lines/s=" + (long)(_perfLines / secs)
                + " batches=" + _perfBatches
                + " maxBatch=" + _perfMaxBatch
                + " q=" + qdepth
                + " tickAvg=" + (_perfTickMs / _perfBatches).ToString("0.00") + "ms"
                + " tickMax=" + _perfMaxTickMs.ToString("0.00") + "ms";

            _perfLines = 0; _perfBatches = 0; _perfMaxBatch = 0;
            _perfTickMs = 0; _perfMaxTickMs = 0; _perfLastWrite = now;

            try
            {
                string dir = GuiEntry.LogDir();
                if (!string.IsNullOrEmpty(dir))
                {
                    Directory.CreateDirectory(dir);
                    File.AppendAllText(Path.Combine(dir, "gui_perf.log"), line + Environment.NewLine);
                }
            }
            catch { }
        }

        // ---------------- 页面 → 命令 ----------------

        private void OnWebMessage(object sender, CoreWebView2WebMessageReceivedEventArgs e)
        {
            // 拖拽文件：页面用 postMessageWithAdditionalObjects 把 File 对象传过来，
            // AdditionalObjects 里会有 CoreWebView2File。这是唯一使用
            // AdditionalObjects 的场景，直接优先处理，不依赖 JSON kind 解析
            // （postMessageWithAdditionalObjects 的 message 序列化格式不稳定）。
            if (e.AdditionalObjects != null && e.AdditionalObjects.Count > 0)
            {
                HandleFileDrop(e);
                return;
            }

            string json = null;
            try { json = e.WebMessageAsJson; }
            catch { try { json = e.TryGetWebMessageAsString(); } catch { } }

            if (string.IsNullOrEmpty(json)) return;

            string kind = GetField(json, "kind");
            switch (kind)
            {
                case "ready":
                    // 页面加载完成后请求状态：修复"设备号不显示"的竞态。
                    // 之前 PushStatus 只在 BootDevice 完成时推一次，而那一刻
                    // 页面可能还没就绪，消息被静默丢弃 -> 输入框 > 后永远空着。
                    PushStatus(App.DEVN > 0, 0, null);
                    // 同时把 cmds.ini 里的自定义命令推给页面（ui.html 不再硬编码）
                    PushCommands();
                    // APK 管理的应用列表（用户录入的名称 + 包名）
                    PushApkApps();
                    break;

                case "cmd":
                    string txt = GetField(json, "data");
                    if (!string.IsNullOrEmpty(txt))
                    {
                        int src = 0;
                        string sraw = GetField(json, "src");
                        int.TryParse(sraw, out src);
                        // 需求1：槽位（哪个输入框）。默认 0，+号加出来的输入框带 slot。
                        int slot = 0;
                        string slraw = GetField(json, "slot");
                        int.TryParse(slraw, out slot);
                        SubmitCmd(txt, src, slot);
                    }
                    break;

                case "quick":
                    // 快捷指令页点击卡片触发：结果走反馈窗口（source=1），固定槽位 0
                    string qtxt = GetField(json, "data");
                    if (!string.IsNullOrEmpty(qtxt)) SubmitCmd(qtxt, 1, 0);
                    break;

                case "stop":
                    int stopSlot = 0;
                    string ssraw = GetField(json, "slot");
                    int.TryParse(ssraw, out stopSlot);
                    StopWorker(stopSlot);
                    break;

                case "copy":
                    string c = GetField(json, "data");
                    if (!string.IsNullOrEmpty(c))
                    {
                        try { Clipboard.SetText(c); } catch { }
                    }
                    break;

                case "theme":
                    // 页面切主题：同步系统标题栏深浅（只有 dark 用深色标题栏，
                    // light / eye 都是浅底，标题栏必须跟着变浅）。
                    string th = GetField(json, "data");
                    App.THEME = (th == "light" || th == "eye") ? th : "dark";
                    SetTitleBarDark(App.THEME == "dark");
                    ApplyChromeColor();   // A13：圆角四角露出的底色也要跟着换
                    // UI 测试模式（ProbeJs 非空）禁止落盘：测试页会来回切主题，
                    // 写进 ini 就把受版本控制的模板改脏了（实测污染过 adb_log_gui 那份）。
                    if (ProbeJs == null) SaveThemePreference(App.THEME);
                    break;

                // ---------------- 自定义 ADB 指令（2026-11-15）----------------
                // 数据是不透明 base64 blob，C# 只存取不解析；执行仍复用 case "quick"
                // 的 SubmitCmd 链路，因此命令的原生输出 / 失败提示会照常回到输出框。
                case "customlist":
                    try
                    {
                        _web.CoreWebView2.PostWebMessageAsJson(
                            "{\"kind\":\"customcmds\",\"data\":"
                            + Json(AdbLogExport.CustomStore.Load()) + "}");
                    }
                    catch { }
                    break;

                case "customsave":
                    AdbLogExport.CustomStore.Save(GetField(json, "data"));
                    break;

                case "accent":
                    // 2026-11-15：强调色与明暗主题分开持久化，不动标题栏。
                    // A17：白名单统一走 App.NormalizeAccent（唯一一份）。
                    // 原来这里自带一张 9 色旧表，16 色扩完只改了 Program.cs，
                    // 于是 cyan/teal/graphite/三白 保存时全被改写成 blue ——
                    // 用户看到的就是"强调色设置后重启回默认"。
                    App.ACCENT = App.NormalizeAccent(GetField(json, "data"));
                    if (ProbeJs == null) SaveAccentPreference(App.ACCENT);   // 同上：测试模式不落盘
                    break;

                // ---------------- 自绘标题栏 / 设置（2026-11-15） ----------------
                case "windrag":
                    try
                    {
                        if (WindowState == FormWindowState.Maximized)
                        {
                            // 最大化时拖动 = 先还原到原尺寸的一半，再跟着鼠标走
                            // （和 Windows 原生标题栏的手感一致）
                            Point cp = PointToClient(Cursor.Position);
                            double rx = (double)cp.X / Math.Max(1, ClientSize.Width);
                            WindowState = FormWindowState.Normal;
                            Location = new Point(
                                (int)(Cursor.Position.X - Width * rx),
                                Math.Max(0, Cursor.Position.Y - 16));
                        }
                        ReleaseCapture();
                        SendMessage(Handle, WM_NCLBUTTONDOWN, (IntPtr)HTCAPTION, IntPtr.Zero);
                    }
                    catch (Exception ex) { GuiEntry.Dump("windrag", ex); }
                    break;

                case "winresize2":
                    // 页面在四边/四角放了 5px 透明热区，按下后自己算位移，
                    // 把「方向 + 相对按下点的总位移」发过来，这里只负责套到窗口矩形上。
                    // 不用 NC 拖拽的原因见 _v12.js：无 WS_THICKFRAME 时系统不认。
                    try
                    {
                        string rdir = GetField(json, "dir");
                        int rdx = GetInt(json, "dx");
                        int rdy = GetInt(json, "dy");
                        if (GetField(json, "reset") == "1" || !_rzActive)
                        {
                            _rzRect = Bounds;
                            _rzDir = rdir;
                            _rzActive = true;
                        }
                        Rectangle r = _rzRect;
                        int minW = MinimumSize.Width, minH = MinimumSize.Height;

                        if (_rzDir == "n" || _rzDir == "s" || _rzDir == "nw"
                            || _rzDir == "ne" || _rzDir == "sw" || _rzDir == "se")
                        {
                            if (_rzDir == "n" || _rzDir == "nw" || _rzDir == "ne")
                            {
                                int ny = r.Y + rdy;
                                int nh = r.Bottom - ny;
                                if (nh >= minH) { r.Y = ny; r.Height = nh; }
                            }
                            else
                            {
                                int nh = _rzRect.Height + rdy;
                                if (nh >= minH) r.Height = nh;
                            }
                        }
                        if (_rzDir == "w" || _rzDir == "e" || _rzDir == "nw"
                            || _rzDir == "ne" || _rzDir == "sw" || _rzDir == "se")
                        {
                            if (_rzDir == "w" || _rzDir == "nw" || _rzDir == "sw")
                            {
                                int nx = r.X + rdx;
                                int nw = r.Right - nx;
                                if (nw >= minW) { r.X = nx; r.Width = nw; }
                            }
                            else
                            {
                                int nw = _rzRect.Width + rdx;
                                if (nw >= minW) r.Width = nw;
                            }
                        }
                        if (WindowState == FormWindowState.Normal) Bounds = r;
                    }
                    catch (Exception ex) { GuiEntry.Dump("winresize2", ex); }
                    break;

                case "winresizeend":
                    _rzActive = false;
                    break;

                case "winmin":
                    // A17：恢复"收起动效"，但**仍然不碰窗口尺寸** ——
                    // 动效做在页面内容层（scale .96 + 淡出，130ms），播完再最小化。
                    // A16 之所以把动效整段删掉，是因为那一版在改窗口尺寸；
                    // 这次改的只是渲染层，中断最多是"淡出没播完"，不会留下小窗口。
                    PlayOutThen(delegate
                    {
                        WindowState = FormWindowState.Minimized;
                    });
                    break;

                case "winmax":
                    WindowState = (WindowState == FormWindowState.Maximized)
                        ? FormWindowState.Normal : FormWindowState.Maximized;
                    PushWinState();
                    break;

                case "winclose":
                    // A17：关闭只做一次，且**立刻让窗口消失**。
                    // "偶发要点两次关闭"的根因不在页签按钮，而在 OnFormClosing：
                    //   停 track-devices 线程、CastStopAll、_worker[i].Abort() 都可能在
                    //   adb 的同步读上卡住，而这段全跑在 UI 线程 —— 窗口既不消失也不响应，
                    //   用户只能再点一次。第二次点击时窗口已经在关，才"看起来像"第二下生效。
                    // 现在：
                    //   ① 立刻播 130ms 收起动效（有反馈）；
                    //   ② 播完 Hide() —— 窗口和任务栏按钮当场消失，用户认为已关闭；
                    //   ③ 再 BeginInvoke 真正的 Close() 去跑清理；
                    //   ④ 起一个看门狗线程，2.5s 还没退就 Environment.Exit(0)，
                    //      不让"清理卡住"变成"关不掉"。
                    if (_closing)
                    {
                        try { Environment.Exit(0); } catch { }
                        break;
                    }
                    _closing = true;
                    PlayOutThen(delegate
                    {
                        try { Hide(); } catch { }
                        try
                        {
                            BeginInvoke((Action)delegate
                            {
                                try { Close(); } catch { }
                            });
                        }
                        catch { try { Close(); } catch { } }
                        StartExitWatchdog(2500);
                    });
                    break;

                // ---------------- A18：内嵌 scrcpy 投屏（每格一块） ----------------
                // 页面 -> 后端：scrcpyembed {data:"{slot,id}"}  启动并接管某格
                //              scrcpyembedstop {data:"{slot}"}  停某格
                //              castembedrect {data:"{slot,l,t,r,b}"}  某格区域比例
                //              castembedhide                       只要隐藏（切页 / 最小化）
                case "scrcpyembed":
                    ScrcpyEmbedStart(GetField(json, "data"));
                    break;

                case "scrcpyembedstop":
                    {
                        int ss = (int)JsonNum(GetField(json, "data"), "slot", 0);
                        ScrcpyEmbedStop(ss);
                    }
                    break;

                case "castembedrect":
                    ScrcpyEmbedPlace(GetField(json, "data"));
                    break;

                case "castembedhide":
                    ScrcpyEmbedHideAll();
                    break;

                // ---------------- A15：日志等级（设备端 persist.log.tag） ----------------
                // 协议：
                //   前端 -> 后端  logget                   只读
                //                logset{data:V|D|I|W|E}   写后回读
                //   后端 -> 前端  logtag{data:当前值}
                // 为什么要回读：setprop 在部分车机上是只读/被 SELinux 拦住，
                // 发出去不代表生效，必须读回来再告诉用户。
                case "logget":
                    RunLogTagJob(null);
                    break;

                case "logset":
                    RunLogTagJob((GetField(json, "data") ?? "").Trim().ToUpperInvariant());
                    break;

                // ---------------- A15：设备管理 ----------------
                //   前端 -> 后端  devlist / devswitch{data:serial} / devdisconnect{data:serial}
                //   后端 -> 前端  devlist{data:"serial|model|state|cur\n…"}
                case "devlist":
                    RunDeviceListJob();
                    break;

                case "devswitch":
                    DoDeviceSwitch(GetField(json, "data"));
                    break;

                case "devdisconnect":
                    DoDeviceDisconnect(GetField(json, "data"));
                    break;

                case "prefsave":
                    // 字体 / 字号 / 动效：和 accent 一样是不透明串，C# 只存取不解析
                    App.PREFS = GetField(json, "data");
                    // UI 测试模式不落盘（测试页会来回改字体/字号，写了就把 ini 弄脏）
                    if (ProbeJs == null) SaveIniKey("prefs", App.PREFS == null ? "" : App.PREFS);
                    break;

                // A14：字体大小（小 0.9 / 中 1.0 / 大 1.15）。
                // 用 WebView2 的 ZoomFactor 而不是逐条改 CSS 字号：
                // 整页等比放大并重新排版，标题栏/卡片/输出区一起跟随，
                // 也不会出现"某个组件忘了改"的半吊子效果。
                case "uizoom":
                    {
                        string zs = GetField(json, "data");
                        double z = 1.0;
                        if (!string.IsNullOrEmpty(zs))
                            double.TryParse(zs, System.Globalization.NumberStyles.Float,
                                            System.Globalization.CultureInfo.InvariantCulture, out z);
                        // 夹在 0.75~1.6：防手改 ini / 异常值把界面缩没
                        if (z < 0.75) z = 0.75;
                        if (z > 1.6) z = 1.6;
                        try { _web.ZoomFactor = z; } catch { }
                    }
                    break;

                // ---------------- 文本编辑器（2026-11-15）----------------
                case "textopen":
                    RunTextOpen();
                    break;

                case "textsave":
                    RunTextSave(json);
                    break;

                case "themeget":
                    // 页面启动时问一次当前主题（ini 里持久化的是三态字符串）。
                    // 顺手把标题栏也设对 —— 否则启动时内容是护眼/白天、标题栏还是黑的（用户反馈过）。
                    try
                    {
                        SetTitleBarDark(App.THEME == "dark");
                        _web.CoreWebView2.PostWebMessageAsJson(
                            "{\"kind\":\"theme\",\"name\":" + Json(App.THEME) + "}");
                        // 强调色单独回一条，让重启后按钮/进度条/选中态保持用户选的颜色
                        _web.CoreWebView2.PostWebMessageAsJson(
                            "{\"kind\":\"accent\",\"name\":" + Json(App.ACCENT) + "}");
                        // 字体 / 字号 / 动效偏好（base64 不透明串）
                        if (App.PREFS != null && App.PREFS.Length > 0)
                            _web.CoreWebView2.PostWebMessageAsJson(
                                "{\"kind\":\"prefs\",\"data\":" + Json(App.PREFS) + "}");
                        // 2026-11-17：版本水印。现场出现过"改了却看不到变化"，
                        // 根因是同机器上跑着别的目录里的旧副本（另一个 exe + 另一份 ui.html）。
                        // 把「程序时间 / 界面时间 / 运行目录」推到设置面板的「关于」里，
                        // 一眼就能判断当前窗口是哪一份，不用再猜。
                        try
                        {
                            _web.CoreWebView2.PostWebMessageAsJson(
                                "{\"kind\":\"build\",\"exe\":" + Json(StampOf(Application.ExecutablePath))
                                + ",\"ui\":" + Json(StampOf(_uiPath))
                                + ",\"dir\":" + Json(AppDomain.CurrentDomain.BaseDirectory) + "}");
                        }
                        catch { }
                    }
                    catch { }
                    break;

                // 问题3：root 指示按钮。
                //   rootprobe —— 只查询，不改变设备状态（页面首次显示时调一次）
                //   root      —— 真提权（用户点了红色按钮）
                // 两者都走后台线程：adb root 会让 adbd 重启并等最多 6 秒，
                // 在 UI 线程上做会把整个窗口冻住。
                case "rootprobe":
                    RunRootJob(false);
                    break;

                case "root":
                    RunRootJob(true);
                    break;

                // ---------------- APK 管理 ----------------
                // 列表的增删在 UI 线程上做（只是改一个几十行的小文件，毫秒级），
                // 真正要连设备的三个动作和版本查询才另起 worker。
                case "apklist":
                    PushApkApps();
                    break;

                case "apkadd":
                    string addName = GetField(json, "name");
                    string addPkg = GetField(json, "pkg");
                    string addErr = "";
                    bool addOk = App.ApkListAdd(addName, addPkg, out addErr);
                    PushApkAck(addOk, addOk ? "" : addErr, "add");
                    if (addOk) PushApkApps();
                    break;

                case "apkdel":
                    string delPkg = GetField(json, "pkg");
                    string delErr = "";
                    bool delOk = App.ApkListRemove(delPkg, out delErr);
                    PushApkAck(delOk, delOk ? "" : delErr, "del");
                    if (delOk) PushApkApps();
                    break;

                case "apkact":
                    RunApkAct(GetField(json, "pkg"), GetField(json, "act"));
                    break;

                case "apkquery":
                    RunApkQuery(GetField(json, "pkg"));
                    break;

                case "apkver":
                    RunApkVer();
                    break;

                case "apkfront":
                    RunApkFront();
                    break;

                // 原来的前台指令（:pkg now / :front / :fstop / :apk）
                // 卡片从快捷指令下架了，但从 APK 管理页仍然要能完整用
                case "apkcmd":
                    RunApkCmd(GetField(json, "cmd"));
                    break;

                // ---------------- 投屏 ----------------
                case "castlist": RunCastList(); break;
                case "caststart":
                    App.CastStart(GetInt(json, "slot"), GetInt(json, "id"));
                    PushCastStat(GetInt(json, "slot"));
                    break;
                case "caststop":
                    App.CastStop(GetInt(json, "slot"));
                    PushCastStat(GetInt(json, "slot"));
                    break;
                case "caststat":
                    PushCastStat(GetInt(json, "slot"));
                    break;
                case "casttap":
                    RunCastTap(GetInt(json, "slot"), GetInt(json, "x"), GetInt(json, "y"));
                    break;
                case "castrec":
                    RunCastRecord(GetInt(json, "slot"), GetInt(json, "id"), GetField(json, "on") == "1");
                    break;

                // ---------------- 录屏编码器 ffmpeg（R9）----------------
                // 四个动作分开是为了让界面能显示"正在查找/正在校验"，
                // 而不是点一下之后几秒钟毫无反应。
                case "ffmpegstat": RunFfmpegJob(0, ""); break;
                case "ffmpegauto": RunFfmpegJob(1, ""); break;
                case "ffmpegset": RunFfmpegJob(2, GetField(json, "path")); break;
                case "ffmpegpick": RunFfmpegJob(3, ""); break;

                // ---------------- 外挂 scrcpy（R10）----------------
                case "scrcpystat": RunScrcpyJob(0, 0, 0); break;
                case "scrcpyauto": RunScrcpyJob(1, 0, 0); break;
                case "scrcpypick": RunScrcpyJob(3, 0, 0); break;
                case "scrcpyset": RunScrcpyJob(2, 0, 0, GetField(json, "path")); break;
                case "scrcpyopen": RunScrcpyJob(4, GetInt(json, "id"), GetInt(json, "slot")); break;

                // ---------------- 文件管理 ----------------
                case "fslist":
                    RunFsList(GetField(json, "side"), GetField(json, "path"));
                    break;

                // 文件页搜索（左右各自独立：side=local 只搜电脑，side=dev 只搜设备）
                case "fssearch":
                    RunFsSearch(GetField(json, "side"), GetField(json, "root"),
                                GetField(json, "q"), GetInt(json, "seq"));
                    break;

                case "fssearchcancel":
                    App.FS_SEARCH_CANCEL = true;
                    break;

                case "fscopy":
                    RunFsCopy(GetField(json, "dir"), GetField(json, "dst"),
                              GetField(json, "src"));
                    break;

                case "fscancel":
                    App.FS_CANCEL = true;
                    try { App.KillRunning(0); } catch { }
                    break;

                case "fsop":
                    RunFsOp(GetField(json, "op"), GetField(json, "side"),
                            GetField(json, "path"), GetField(json, "name"));
                    break;

                // ---------------- 无线 adb ----------------
                case "wadb":
                    RunWadbJob(GetField(json, "act"), GetField(json, "host"));
                    break;
            }
        }

        // root 查询/提权的后台执行壳。
        // 单独抽出来是为了让 probe 和 elevate 共用同一套
        // 「跑完 → 回 UI 线程 → 推状态」流程，避免两边各写一份。
        private void RunRootJob(bool elevate)
        {
            Thread th = new Thread(new ThreadStart(delegate()
            {
                bool rooted = false;
                try
                {
                    rooted = elevate ? App.RootElevate() : App.RootProbe();
                }
                catch (Exception ex)
                {
                    GuiEntry.Dump(elevate ? "RootElevate" : "RootProbe", ex);
                    rooted = false;
                }

                FinishInvoke(delegate
                {
                    // 明确回一条 rootdone：页面据此解除"提权中"状态。
                    // 只靠 status 里的 rooted 字段不够 —— 提权失败时 rooted
                    // 仍然是 false，与"还没查过"无从区分，按钮会一直转圈。
                    try
                    {
                        _web.CoreWebView2.PostWebMessageAsJson(
                            "{\"kind\":\"rootdone\",\"elevate\":" + (elevate ? "true" : "false")
                            + ",\"rooted\":" + (rooted ? "true" : "false") + "}");
                    }
                    catch { }

                    // 提权会把 adbd 重启，重启后设备号/分辨率都还有效，
                    // 但为了保险重推一次完整状态（含 rooted 字段）
                    PushStatus(App.DEVN > 0, 0, elevate ? (rooted ? "已 root" : "提权失败") : null);
                });
            }));
            th.IsBackground = true;
            th.Start();
        }

        // 处理拖拽文件：从 AdditionalObjects 取 CoreWebView2File.Path，回传给页面
        private void HandleFileDrop(CoreWebView2WebMessageReceivedEventArgs e)
        {
            try
            {
                foreach (object obj in e.AdditionalObjects)
                {
                    CoreWebView2File f = obj as CoreWebView2File;
                    if (f != null && !string.IsNullOrEmpty(f.Path))
                    {
                        _web.CoreWebView2.PostWebMessageAsJson(
                            "{\"kind\":\"filePath\",\"data\":" + Json(f.Path) + "}");
                    }
                }
            }
            catch (Exception ex) { GuiEntry.Dump("fileDrop", ex); }
        }

        // 标题栏深浅跟随主题（深色=immersive dark，浅色=恢复默认）
        private void SetTitleBarDark(bool dark)
        {
            try
            {
                if (dark)
                {
                    int val = 1;
                    int hr = DwmSetWindowAttribute(Handle, DWMWA_USE_IMMERSIVE_DARK_MODE, ref val, sizeof(int));
                    // Win10 1809 之前属性号是 19；20/21 是新号。老系统上只试 20
                    // 会失败且不回退 —— 标题栏深浅就跟主题不同步了。
                    if (hr != 0)
                        DwmSetWindowAttribute(Handle, DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, ref val, sizeof(int));
                }
                else
                {
                    int val = 0;
                    int hr = DwmSetWindowAttribute(Handle, DWMWA_USE_IMMERSIVE_DARK_MODE, ref val, sizeof(int));
                    if (hr != 0)
                        DwmSetWindowAttribute(Handle, DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, ref val, sizeof(int));
                }
            }
            catch { }
        }

        // ---------------- 设备初始化（后台，分层加载） ----------------

        private void BootDevice()
        {
            Thread th = new Thread(new ThreadStart(delegate()
            {
                // ---- 第一层：轻量拿设备号（快，<1s），先显示出来 ----
                // 完整 InitEnv 里 AutoRoot/Probe/LoadDeviceInfo 会做多次 adb shell
                // 往返，累计好几秒。这段时间用户看到的是"设备号->空白"。
                // 所以先只跑一次 adb devices 拿到序列号，立即推给界面，
                // 用户一秒内就能看到"连上了哪台设备"。
                try
                {
                    string so = "", se = "";
                    int rc = App.AdbCall(new List<string> { "devices" }, out so, out se);
                    if (rc == 0)
                    {
                        // 解析 devices 输出，找 "device" 状态的序列号
                        string firstDev = "";
                        foreach (string line in so.Split('\n'))
                        {
                            string t = line.Trim();
                            if (t.EndsWith("\tdevice") || t.EndsWith(" device"))
                            {
                                int sp = t.IndexOf('\t');
                                if (sp < 0) sp = t.IndexOf(' ');
                                if (sp > 0) { firstDev = t.Substring(0, sp).Trim(); break; }
                            }
                        }
                        if (firstDev.Length > 0)
                        {
                            FinishInvoke(delegate
                            {
                                PushStatusEarly(firstDev);
                            });
                        }
                        else
                        {
                            // T4（2026-11-19）：无设备时原来一条 status 都不推，
                            // 前端只能干等 hideSplash 的兜底定时器（8 秒→5 秒也太久）。
                            // 这里立刻推一条 offline，前端 setStatus 会走 hideSplash，
                            // 实测 <1.5 秒进界面。
                            // 注意：_online=false 会把指令按钮置灰 —— 这是**正确行为**，
                            // 无设备本来就不该能操作，不是功能回退。
                            FinishInvoke(delegate
                            {
                                try
                                {
                                    _web.CoreWebView2.PostWebMessageAsJson(
                                        "{\"kind\":\"status\",\"dev\":\"\",\"online\":false,"
                                        + "\"soc\":\"\",\"res\":\"\",\"dir\":\"\",\"rooted\":null,"
                                        + "\"msg\":\"未检测到设备\"}");
                                }
                                catch (Exception ex) { GuiEntry.Dump("PushStatusEmpty", ex); }
                            });
                        }
                    }
                }
                catch { }

                // ---- 第二层：完整初始化（慢，后台跑完再补全 SOC/目录） ----
                bool ok = false;
                try { ok = App.InitEnv(); }
                catch (Exception ex) { GuiEntry.Dump("InitEnv", ex); ok = false; }

                if (!ok) App.OFFLINE = true;

                // 问题3：连上设备后先探一次 root 状态，让顶栏按钮一次就显示正确颜色。
                // 放在 InitEnv 之后（要有 CUR/OFFLINE 才判得准），后台线程里做，
                // 最坏 3 次 shell 往返（~0.5s），用户看不到卡顿。
                if (ok)
                {
                    try { App.RootProbe(); }
                    catch (Exception ex) { GuiEntry.Dump("RootProbe", ex); }
                }

                FinishInvoke(delegate { PushStatus(ok, 0, null); });

                // adb root 会让 adbd 重启，设备会消失 1~3 秒。如果 RootProbe 正好
                // 落在这个窗口里，会拿到"不是 root"，徽标就一直是红的，而实际
                // 后台已经提权成功 —— 用户必须手动点一下才变绿，这就是"已连上
                // 且已 root，顶部还显示未连接/未 root"的来源。
                // 所以再补一次"等设备回来 → 重新探测 → 推状态"的收尾。
                if (ok) SettleRootState();

                // 需求4：启动时的九项车机信息**不需要**在这里再推一次。
                // InitEnv 内部已经打印过（见 Adb.InitEnv 末尾的 _carPrinted 分支），
                // 而 InstallSink() 在构造时就把 Console 接到了 GuiSink 上，
                // 所以那批行会进队列、由 _tick 在页面就绪后自动推到前台。
                // 早先这里多调了一次 PushCarInfo()，结果是界面上九项出现两遍
                // （真窗口截图一眼就能看到 "车型 181" 上下各一份）。

                // 【需求6】启动事件监听：设备上线后自动重连，不再靠轮询。
                // 放在 InitEnv 之后启动，避免和首次初始化抢 adb。
                StartDeviceWatch();
            }));
            th.IsBackground = true;
            th.Start();
        }

        // 【需求6】启动 track-devices 监听：设备上线 -> 后台自动重连。
        //
        // 与"用户手动输入 r"走完全同一条路径（RetrySoft），
        // 所以结果、输出、状态刷新都一致，不存在两套逻辑分叉。
        private void StartDeviceWatch()
        {
            try
            {
                App.DeviceWatcher.Start(
                    // 重连实现：直接调 RetrySoft。它内部会 AutoRoot + RootProbe +
                    // 重取车机信息，所以徽标和九项信息都会自动更新。
                    (App.DeviceWatcher.ReconnectFn)delegate()
                    {
                        // 自动重连的输出归槽位 0（指令输入页）。
                        // CUR_SLOT 是全局的，可能残留着上一次快捷指令的槽位号，
                        // 不重置的话自动重连的输出会跑到快捷指令的反馈窗口里去。
                        App.CUR_SLOT = 0;
                        try { App.RetrySoftForWatch(); }
                        catch { return false; }

                        // 判成功只看两件事：拿到设备号、且不在离线态。
                        // 不用 CMD_OK —— 那个值是全局的，容易被别的命令改写。
                        return (App.DEVN > 0) && !App.OFFLINE;
                    },
                    // 成功后的输出：走 Console 转发到 GUI 输出区
                    delegate(string devs)
                    {
                        try
                        {
                            Console.WriteLine();
                            Console.WriteLine("  √ 检测到设备上线，已自动重连：" + devs);
                        }
                        catch { }
                        // 重连成功后必须重推状态：离线时我们把设备号清空、root 置灰了，
                        // 这里不推的话，界面会一直停在"未连接"。
                        FinishInvoke(delegate { PushStatus(App.DEVN > 0, 0, "已重连"); });

                        // 【2026-11-13】重连成功后还要把 root 状态重新探一次。
                        // 原因：onGone 把 ROOTED 清成了 false，而重连时 AutoRoot 往往
                        // 跑在 adbd 刚重启、还没就绪的窗口里，`adb root` 会失败，
                        // 于是 PushStatus 一直推 rooted:false —— 界面就出现
                        // "已自动重连，但 root 还是红的"。
                        // SettleRootState 会等 get-state 回到 device 再探，探完推 rootdone。
                        App.Trace("watcher: 重连后复核 root（当前 ROOTED=" + App.ROOTED + "）");
                        SettleRootState();
                    },
                    // 设备全部下线：立刻把界面切回离线态（root 胶囊置灰、设备号清掉）
                    delegate()
                    {
                        // 无线调试切 tcpip 时 adbd 会重启，USB 必然瞬断一次。
                        // 那不是真断开 —— 抑制窗口内忽略，否则 root 会闪灰、
                        // 输出区还会打一行唬人的"设备已断开"。
                        if (App.WadbSuppressed())
                        {
                            try { Console.WriteLine("  · 无线调试切换中，忽略一次设备瞬断"); }
                            catch { }
                            return;
                        }
                        App.DEVN = 0;
                        App.DEVID = "";
                        App.OFFLINE = true;
                        App.ROOTED = false;
                        App.ROOT_PROBED = false;
                        App.Trace("watcher: 设备全部下线 -> 界面切离线");
                        try
                        {
                            Console.WriteLine();
                            Console.WriteLine("  ! 设备已断开，等待重新连接 …");
                        }
                        catch { }
                        FinishInvoke(delegate { PushStatus(false, 0, "设备已断开"); });
                    });
            }
            catch (Exception ex)
            {
                GuiEntry.Dump("StartDeviceWatch", ex);
            }
        }

        // 跨线程回 UI 的兜底封装（窗口可能已关闭）
        private void FinishInvoke(MethodInvoker fn)
        {
            try
            {
                if (IsHandleCreated && !IsDisposed) BeginInvoke(fn);
            }
            catch { }
        }

        // 当前是否有槽位在执行（后台任务用它避让，避免抢 RUNNING_SLOTS）
        private bool AnyBusy()
        {
            for (int i = 0; i < MAX_SLOT; i++) { if (_busy[i]) return true; }
            return false;
        }

        // 启动收尾：等 adbd 回来后再确认一次 root 状态。
        // 只在"当前判定不是 root"时才有必要 —— 已经是 root 就直接返回，
        // 避免每次启动都多跑几次 shell。
        private void SettleRootState()
        {
            Thread th = new Thread(new ThreadStart(delegate()
            {
                try
                {
                    if (App.ROOTED) return;

                    // 用户正在跑命令时不要插一脚：AdbCall 会登记 RUNNING_SLOTS[slot]，
                    // 后台探测和用户命令撞在一起会让"停止"杀错进程。
                    // 先等空闲，再逐轮探测；期间一有命令开始就整个让位。
                    for (int w = 0; w < 20 && AnyBusy(); w++) Thread.Sleep(300);
                    if (AnyBusy()) return;

                    // 最多等 ~6 秒让设备重新出现在 adb 列表里
                    for (int i = 0; i < 12; i++)
                    {
                        if (AnyBusy()) return;
                        string so = "", se = "";
                        int rc = App.AdbCall(new List<string> { "get-state" }, out so, out se);
                        if (rc == 0 && so.Trim().ToLowerInvariant().StartsWith("device")) break;
                        if (i < 11) Thread.Sleep(500);
                    }
                    if (AnyBusy()) return;

                    bool rooted = false;
                    try { rooted = App.RootProbe(); }
                    catch (Exception ex) { GuiEntry.Dump("SettleRootProbe", ex); }
                    App.Trace("settle-root: RootProbe -> " + rooted);

                    FinishInvoke(delegate
                    {
                        // 明确回一条 rootdone，页面据此把徽标切成绿/红；
                        // 再推一次完整状态，保证设备号、分辨率等也是最新的。
                        try
                        {
                            _web.CoreWebView2.PostWebMessageAsJson(
                                "{\"kind\":\"rootdone\",\"elevate\":false,\"rooted\":"
                                + (rooted ? "true" : "false") + "}");
                        }
                        catch { }
                        PushStatus(App.DEVN > 0, 0, null);
                    });
                }
                catch { }
            }));
            th.IsBackground = true;
            th.Name = "settle-root";
            th.Start();
        }

        // 早期状态：只推设备号（SOC/目录等还在加载，留空）
        private void PushStatusEarly(string devId)
        {
            try
            {
                _web.CoreWebView2.PostWebMessageAsJson(
                    "{\"kind\":\"status\",\"dev\":" + Json(devId)
                    + ",\"online\":true,\"soc\":\"\",\"res\":\"\",\"dir\":\"\",\"rooted\":null,\"msg\":\"连接中…\"}");
            }
            catch { }
        }

        // 需求4：启动连上设备后，九项车机信息由 Adb.InitEnv 直接打印，
        // 经已挂好的 GuiSink 自动流到界面 —— 这里不再额外渲染一份。
        // （曾有 PushCarInfo 在此重复推送，导致九项显示两遍，已移除。）

        // ---------------- 命令执行 ----------------

        private void SubmitCmd(string raw, int source, int slot)
        {
            if (slot < 0) slot = 0;
            if (slot >= MAX_SLOT) slot = MAX_SLOT - 1;

            if (_busy[slot])
            {
                // 需求9·兜底：前端已有互斥，正常到不了这里；但若竞态漏网
                // 绝不能静默丢弃，否则前端占位行会永久"执行中"、互斥锁永不释放。
                try
                {
                    _web.CoreWebView2.PostWebMessageAsJson(
                        "{\"kind\":\"end\",\"ok\":false,\"ms\":0,\"feed\":null,\"busy\":true,\"slot\":" + slot + "}");
                }
                catch { }
                return;
            }

            string cmd = App.NormalizeLead(raw.Trim());
            if (cmd.Length == 0) return;

            // 写历史（复用命令行逻辑）
            App.Hist.Add(cmd);
            if (App.Hist.Count > 500) App.Hist.RemoveAt(0);
            App.AppendHistory(cmd);

            _cmdSource[slot] = source;   // 0=指令输入页 1=快捷指令页
            _lastCmd[slot] = cmd;        // 记录命令原文，供反馈窗口展示

            // 重置"展开命令"记录，本次执行若走自定义命令会重新填上（需求4）
            App.LAST_EXPANDED = "";

            // 每次新命令都清掉"用户主动停止"标记（需求2）
            _stopRequested[slot] = false;
            App.GUISTOP = false;

            // 回显给页面
            PushEcho(cmd, slot);
            PushBegin(slot);

            _busy[slot] = true;
            System.Diagnostics.Stopwatch sw = System.Diagnostics.Stopwatch.StartNew();

            _worker[slot] = new Thread(new ThreadStart(delegate()
            {
                // 需求1：标记当前 worker 线程的槽位，GuiSink 据此给输出行打槽位标记
                App.CUR_SLOT = slot;

                bool ok = true;
                try { App.Dispatch(cmd); ok = App.CMD_OK; }
                catch (Exception ex)
                {
                    ok = false;
                    try { Console.WriteLine("  \u00D7 内部错误：" + ex.Message); } catch { }
                }

                sw.Stop();
                long ms = sw.ElapsedMilliseconds;

                try
                {
                    BeginInvoke((MethodInvoker)delegate { PushEnd(ok, ms, slot); });
                }
                catch
                {
                    _busy[slot] = false;
                }
            }));
            _worker[slot].IsBackground = true;
            _worker[slot].SetApartmentState(ApartmentState.STA);
            _worker[slot].Start();
        }

        private void StopWorker(int slot)
        {
            if (slot < 0) slot = 0;
            if (slot >= MAX_SLOT) slot = MAX_SLOT - 1;
            _stopRequested[slot] = true;
            // 长等待命令（如 :sxlog 等设备重启 60s）靠这个标志提前退出，
            // kill adb 进程对纯 sleep 轮询没有用。
            App.GUISTOP = true;
            // 截帧录屏：置停止标志（不是 kill 进程），循环退出后自动编码。
            // 必须按槽位判断 —— 全局标志会把别的槽正在录的也一起停掉。
            if (App.REC_GRAB_RUNNING[slot])
            {
                App.StopRecGrab(slot);
                return;
            }
            // 只杀本槽的 adb 进程。原来杀 App.RUNNING（全局单例），
            // 结果点 A 槽的停止可能杀掉 B 槽正在跑的命令。
            if (!App.KillRunning(slot))
            {
                // 兜底：个别路径（如后台探测）没登记到槽位表，仍按全局引用收尾
                try
                {
                    if (App.RUNNING != null && !App.RUNNING.HasExited) App.RUNNING.Kill();
                }
                catch { }
            }
        }

        private void PushEcho(string cmd, int slot)
        {
            try
            {
                _web.CoreWebView2.PostWebMessageAsJson(
                    "{\"kind\":\"echo\",\"src\":" + _cmdSource[slot]
                    + ",\"slot\":" + slot
                    + ",\"data\":" + Json(cmd) + "}");
            }
            catch { }
        }

        private void PushBegin(int slot)
        {
            try { _web.CoreWebView2.PostWebMessageAsJson("{\"kind\":\"begin\",\"slot\":" + slot + "}"); }
            catch { }
        }

        private void PushEnd(bool ok, long ms, int slot)
        {
            _busy[slot] = false;

            // 输出可能还没刷完
            PumpOutput();

            try
            {
                string feed = "null";
                if (_cmdSource[slot] == 1)
                {
                    // 展示"实际执行的命令"：优先用展开后的完整命令（需求4）
                    string shown = string.IsNullOrEmpty(App.LAST_EXPANDED)
                        ? lastCmd(slot) : App.LAST_EXPANDED;
                    feed = "{\"time\":\"" + DateTime.Now.ToString("HH:mm:ss")
                         + "\",\"cmd\":" + Json(shown)
                         + ",\"ok\":" + (ok ? "true" : "false")
                         + ",\"ms\":" + ms + "}";
                }
                _web.CoreWebView2.PostWebMessageAsJson(
                    "{\"kind\":\"end\",\"ok\":" + (ok ? "true" : "false")
                    + ",\"ms\":" + ms + ",\"feed\":" + feed + ",\"slot\":" + slot + "}");
            }
            catch { }

            PushStatus(true, ms, ok ? "完成" : "失败");
        }

        private string lastCmd(int slot)
        {
            if (slot < 0 || slot >= MAX_SLOT) return "";
            return _lastCmd[slot];
        }

        // ---------------- 状态推送 ----------------

        // 把主题写回 ini（只改 theme= 那一行，其它原样保留）。
        // 没有 ini 文件（单 exe 目录）或没有这个键时什么都不做 —— 不新建、不破坏。
        private static void SaveThemePreference(string theme)
        {
            try
            {
                string p = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "adb_log_export.ini");
                if (!File.Exists(p)) return;
                string[] lines = File.ReadAllLines(p);
                bool found = false;
                for (int i = 0; i < lines.Length; i++)
                {
                    if (lines[i].TrimStart().StartsWith("theme=", StringComparison.OrdinalIgnoreCase))
                    {
                        lines[i] = "theme=" + theme;
                        found = true;
                        break;
                    }
                }
                if (found) File.WriteAllLines(p, lines, new UTF8Encoding(false));
            }
            catch (Exception ex) { App.Trace("theme: 保存失败 " + ex.Message); }
        }

        // 2026-11-15：强调色写回 ini 的 accent=。旧 ini 没有这个键时追加一行，
        // 不新建文件、不破坏其它键；找不到 ini（单 exe 目录）就静默跳过。
        private static void SaveAccentPreference(string accent)
        {
            try
            {
                string p = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "adb_log_export.ini");
                // A17：原来这里 ini 不存在就直接 return —— 单 exe 目录本来就可能没有
                // 配置文件，于是"选了颜色但没落盘"，重启又是默认色。改成没有就新建。
                string[] lines = File.Exists(p) ? File.ReadAllLines(p) : new string[0];
                bool found = false;
                for (int i = 0; i < lines.Length; i++)
                {
                    if (lines[i].TrimStart().StartsWith("accent=", StringComparison.OrdinalIgnoreCase))
                    {
                        lines[i] = "accent=" + accent;
                        found = true;
                        break;
                    }
                }
                if (!found)
                {
                    List<string> list = new List<string>(lines);
                    list.Add("accent=" + accent);
                    lines = list.ToArray();
                }
                File.WriteAllLines(p, lines, new UTF8Encoding(false));
            }
            catch (Exception ex) { App.Trace("accent: 保存失败 " + ex.Message); }
        }

        // 通用 ini 键写入：只改那一行，其它原样保留；没有这个键就追加。
        // 不新建 ini（单 exe 目录本来就没有配置文件，凭空造一个反而是垃圾）。
        private static void SaveIniKey(string key, string val)
        {
            try
            {
                string p = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "adb_log_export.ini");
                if (!File.Exists(p)) return;
                string[] lines = File.ReadAllLines(p);
                bool found = false;
                for (int i = 0; i < lines.Length; i++)
                {
                    if (lines[i].TrimStart().StartsWith(key + "=", StringComparison.OrdinalIgnoreCase))
                    {
                        lines[i] = key + "=" + val;
                        found = true;
                        break;
                    }
                }
                if (!found)
                {
                    List<string> list = new List<string>(lines);
                    list.Add(key + "=" + val);
                    lines = list.ToArray();
                }
                File.WriteAllLines(p, lines, new UTF8Encoding(false));
            }
            catch (Exception ex) { App.Trace(key + ": 保存失败 " + ex.Message); }
        }

        // ================= 文本编辑器：本地文件读写（2026-11-15） =================
        // 为什么要走 C# 而不是浏览器的 File API：
        //   页面是内嵌的，没有"打开/另存为"的系统对话框；而且编码（GBK）和
        //   换行符（CRLF/LF）必须原样保留 —— 用户拿它改 ini / 脚本，编码一乱
        //   就等于把这个文件改坏了。
        // 版本水印用：把文件时间压成 "MM-dd HH:mm"。
        // 用文件时间而不是编译期常量 —— 现场要判断的是"这个 exe / 这份 ui.html
        // 到底是哪一次产出的"，文件时间最直观，也不需要改两个 bat 去传宏。
        private static string StampOf(string path)
        {
            try
            {
                if (string.IsNullOrEmpty(path) || !File.Exists(path)) return "";
                return File.GetLastWriteTime(path).ToString("MM-dd HH:mm");
            }
            catch { return ""; }
        }

        private static string B64(string s)
        {            try { return Convert.ToBase64String(Encoding.UTF8.GetBytes(s == null ? "" : s)); }
            catch { return ""; }
        }

        private static string FromB64(string s)
        {
            try { return Encoding.UTF8.GetString(Convert.FromBase64String(s == null ? "" : s)); }
            catch { return ""; }
        }

        private const int TEXT_MAX = 2 * 1024 * 1024;   // 2MB：再大就不该用这个编辑器

        private void RunTextOpen()
        {
            string path = "";
            try
            {
                using (OpenFileDialog d = new OpenFileDialog())
                {
                    d.Title = "打开文本文件（最大 2 MB）";
                    d.Filter = "文本与配置|*.txt;*.log;*.json;*.xml;*.ini;*.cfg;*.conf;*.md;*.csv;"
                             + "*.bat;*.sh;*.prop;*.java;*.js;*.cs;*.py|所有文件 (*.*)|*.*";
                    d.CheckFileExists = true;
                    d.CheckPathExists = true;
                    if (d.ShowDialog(this) != DialogResult.OK) return;
                    path = d.FileName;
                }
            }
            catch (Exception ex)
            {
                GuiEntry.Dump("textopen 对话框", ex);
                PushRaw("{\"kind\":\"texterr\",\"text\":" + Json("打开文件失败：" + ex.Message) + "}");
                return;
            }

            // 读盘放后台：网络盘、大文件都会卡住 UI 线程（连带投屏掉帧）
            string p2 = path;
            Thread th = new Thread(new ThreadStart(delegate { ReadTextFile(p2); }));
            th.IsBackground = true;
            th.Start();
        }

        private void ReadTextFile(string path)
        {
            string name = "", enc = "UTF-8", eol = "CRLF", text = "";
            bool trunc = false;
            try
            {
                name = Path.GetFileName(path);
                byte[] all;
                using (FileStream fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                {
                    int len = (int)Math.Min(fs.Length, (long)TEXT_MAX);
                    all = new byte[len];
                    int off = 0;
                    while (off < len)
                    {
                        int r = fs.Read(all, off, len - off);
                        if (r <= 0) break;
                        off += r;
                    }
                    trunc = fs.Length > (long)TEXT_MAX;
                }

                if (all.Length >= 3 && all[0] == 0xEF && all[1] == 0xBB && all[2] == 0xBF)
                {
                    enc = "UTF-8 BOM";
                    text = new UTF8Encoding(false).GetString(all, 3, all.Length - 3);
                }
                else if (all.Length >= 2 && all[0] == 0xFF && all[1] == 0xFE)
                {
                    enc = "UTF-16 LE";
                    text = Encoding.Unicode.GetString(all, 2, all.Length - 2);
                }
                else
                {
                    // 先按严格 UTF-8 解，解不动再退 GBK —— 反过来做会把 UTF-8 中文变乱码
                    try
                    {
                        text = new UTF8Encoding(false, true).GetString(all);
                        enc = "UTF-8";
                    }
                    catch
                    {
                        try { text = Encoding.GetEncoding(936).GetString(all); enc = "GBK"; }
                        catch { text = Encoding.Default.GetString(all); enc = "ANSI"; }
                    }
                }

                eol = text.IndexOf("\r\n", StringComparison.Ordinal) >= 0
                    ? "CRLF" : (text.IndexOf('\n') >= 0 ? "LF" : "CRLF");
                // 统一成 \n 交给页面（textarea 只认 \n），保存时按 eol 还原
                text = text.Replace("\r\n", "\n").Replace("\r", "\n");
            }
            catch (Exception ex)
            {
                PushRaw("{\"kind\":\"texterr\",\"text\":" + Json("读取失败：" + ex.Message) + "}");
                return;
            }

            PushRaw("{\"kind\":\"textfile\",\"name\":" + Json(name)
                    + ",\"path\":" + Json(path)
                    + ",\"enc\":" + Json(enc)
                    + ",\"eol\":" + Json(eol)
                    + ",\"trunc\":" + (trunc ? "1" : "0")
                    + ",\"data\":" + Json(B64(text)) + "}");
        }

        private void RunTextSave(string json)
        {
            string path = GetField(json, "path");
            string enc = GetField(json, "enc");
            string eol = GetField(json, "eol");
            string name = GetField(json, "name");
            string text = FromB64(GetField(json, "data"));

            if (path == null || path.Length == 0)
            {
                try
                {
                    using (SaveFileDialog d = new SaveFileDialog())
                    {
                        d.Title = "保存文本文件";
                        d.Filter = "文本文件 (*.txt)|*.txt|所有文件 (*.*)|*.*";
                        if (name != null && name.Length > 0) d.FileName = name;
                        if (d.ShowDialog(this) != DialogResult.OK) return;
                        path = d.FileName;
                    }
                }
                catch (Exception ex)
                {
                    GuiEntry.Dump("textsave 对话框", ex);
                    PushRaw("{\"kind\":\"texterr\",\"text\":" + Json("保存失败：" + ex.Message) + "}");
                    return;
                }
            }

            try
            {
                string outText = text;
                if (eol == "CRLF") outText = outText.Replace("\r\n", "\n").Replace("\n", "\r\n");

                byte[] bytes;
                if (enc == "UTF-8 BOM")
                {
                    byte[] body = new UTF8Encoding(false).GetBytes(outText);
                    bytes = new byte[body.Length + 3];
                    bytes[0] = 0xEF; bytes[1] = 0xBB; bytes[2] = 0xBF;
                    Array.Copy(body, 0, bytes, 3, body.Length);
                }
                else if (enc == "UTF-16 LE")
                {
                    byte[] body = Encoding.Unicode.GetBytes(outText);
                    bytes = new byte[body.Length + 2];
                    bytes[0] = 0xFF; bytes[1] = 0xFE;
                    Array.Copy(body, 0, bytes, 2, body.Length);
                }
                else if (enc == "GBK")
                {
                    bytes = Encoding.GetEncoding(936).GetBytes(outText);
                }
                else
                {
                    bytes = new UTF8Encoding(false).GetBytes(outText);
                }

                File.WriteAllBytes(path, bytes);
                PushRaw("{\"kind\":\"textsaved\",\"path\":" + Json(path)
                        + ",\"name\":" + Json(Path.GetFileName(path))
                        + ",\"enc\":" + Json(enc == null || enc.Length == 0 ? "UTF-8" : enc)
                        + ",\"eol\":" + Json(eol == null || eol.Length == 0 ? "CRLF" : eol) + "}");
            }
            catch (Exception ex)
            {
                PushRaw("{\"kind\":\"texterr\",\"text\":" + Json("保存失败：" + ex.Message) + "}");
            }
        }

        private void PushStatus(bool online, long ms, string msg)
        {
            try
            {
                string dev = App.DEVN > 0 ? App.DEVID : "";
                string soc = App.DEV_SOC == null ? "" : App.DEV_SOC;
                // 问题7：分辨率随状态一起推。连上设备后指令输入页要显示它。
                string res = App.DEV_RES == null ? "" : App.DEV_RES;
                // 需求7：日志等级（persist.log.tag，V/D/I/W/E）
                string loglevel = App.DEV_LOGLEVEL == null ? "" : App.DEV_LOGLEVEL;
                // 目录：初始在 ROOT（没 cd）时不推目录，cd 到其它目录后才显示。
                // 这样提示符「没 cd 只显示设备号，cd 后显示设备号+目录」。
                string dir = "";
                if (App.CUR != null && !string.Equals(App.CUR, App.ROOT, StringComparison.Ordinal))
                    dir = App.CUR;
                string m = msg == null ? "就绪" : msg;

                _web.CoreWebView2.PostWebMessageAsJson(
                    "{\"kind\":\"status\",\"dev\":" + Json(dev)
                    // 只要确实知道一台设备，就不要因为某个调用方传了 false 就显示"未连接"。
                    // adbd 重启窗口里 online 会短暂为 false，界面不该跟着闪成离线态。
                    + ",\"online\":" + ((online || App.DEVN > 0) && dev.Length > 0 ? "true" : "false")
                    + ",\"soc\":" + Json(soc)
                    + ",\"res\":" + Json(res)
                    + ",\"loglevel\":" + Json(loglevel)
                    + ",\"dir\":" + Json(dir)
                    // 没探测过就别断言 false：那会把已经变绿的徽标打回红色。
                    // 只有 RootProbe 真跑过，ROOTED 才有意义。
                    + ",\"rooted\":" + (App.ROOT_PROBED ? (App.ROOTED ? "true" : "false") : "null")
                    + ",\"msg\":" + Json(m) + "}");
            }
            catch { }
        }

        // ---------------- 自定义命令推送（cmds.ini → 快捷指令页） ----------------
        // 页面不再需要为每条自定义命令改 ui.html：启动时推一次，页面把它们
        // 收进「自定义命令」分组（与内置卡片同 cmd 的会跳过，避免重复）。
        private void PushCommands()
        {
            try
            {
                List<App.CmdDef> list = App.CmdList();
                StringBuilder sb = new StringBuilder(1024 + list.Count * 120);
                sb.Append("{\"kind\":\"commands\",\"items\":[");
                bool first = true;
                for (int i = 0; i < list.Count; i++)
                {
                    App.CmdDef d = list[i];
                    if (d == null || string.IsNullOrEmpty(d.Name)) continue;
                    bool hasArg = HasArgPlaceholder(d.Run);
                    if (!first) sb.Append(',');
                    first = false;
                    sb.Append("{\"cmd\":").Append(Json(":" + d.Name))
                      .Append(",\"name\":").Append(Json(d.Name))
                      .Append(",\"desc\":").Append(Json(d.Desc))
                      .Append(",\"group\":").Append(Json(string.IsNullOrEmpty(d.Group) ? "其他" : d.Group))
                      .Append(",\"usage\":").Append(Json(d.Usage))
                      .Append(",\"arg\":").Append(hasArg ? "true" : "false")
                      .Append('}');
                }
                sb.Append("]}");
                _web.CoreWebView2.PostWebMessageAsJson(sb.ToString());
            }
            catch (Exception ex) { GuiEntry.Dump("PushCommands", ex); }
        }

        // ==================== APK 管理 ====================

        // 整份推：列表只有几十条，做增量同步省下的那点流量，
        // 不值一套 diff 逻辑带来的出错面（漏推一条用户就以为数据丢了）。
        private void PushApkApps()
        {
            try
            {
                List<App.ApkApp> list = App.ApkListSnapshot();
                StringBuilder sb = new StringBuilder(256 + list.Count * 80);
                sb.Append("{\"kind\":\"apkapps\",\"items\":[");
                for (int i = 0; i < list.Count; i++)
                {
                    if (i > 0) sb.Append(',');
                    sb.Append("{\"name\":").Append(Json(list[i].Name))
                      .Append(",\"pkg\":").Append(Json(list[i].Pkg))
                      .Append('}');
                }
                sb.Append("]}");
                _web.CoreWebView2.PostWebMessageAsJson(sb.ToString());
            }
            catch (Exception ex) { GuiEntry.Dump("PushApkApps", ex); }
        }

        private void PushApkAck(bool ok, string msg, string op)
        {
            try
            {
                _web.CoreWebView2.PostWebMessageAsJson(
                    "{\"kind\":\"apkack\",\"ok\":" + (ok ? "true" : "false")
                    + ",\"op\":" + Json(op)
                    + ",\"msg\":" + Json(msg) + "}");
            }
            catch { }
        }

        // 忙时拒绝：和 SubmitCmd 里那段完全同构，前端收到后会立刻收尾占位态
        private void PushBusyReject()
        {
            try
            {
                _web.CoreWebView2.PostWebMessageAsJson(
                    "{\"kind\":\"end\",\"ok\":false,\"ms\":0,\"feed\":null,\"busy\":true,\"slot\":0}");
            }
            catch { }
        }

        private delegate bool ApkJob();

        // 把「按包动作」套进和命令一样的 worker + begin/end 协议：
        //   · 输出源标记 3 → 页面把行塞进 APK 面板的结果区，不进反馈区
        //   · 共用 _busy[0] → 不会和快捷卡片同时抢 adb，也不会出现两条并发的 pull
        private void RunApkJob(ApkJob job, string label)
        {
            if (_busy[0]) { PushBusyReject(); return; }

            _cmdSource[0] = 3;             // 3 = APK 管理页
            _lastCmd[0] = label;
            _stopRequested[0] = false;

            PushBegin(0);
            _busy[0] = true;

            Stopwatch sw = Stopwatch.StartNew();
            _worker[0] = new Thread(new ThreadStart(delegate()
            {
                App.CUR_SLOT = 0;
                bool ok = false;
                try { ok = job(); }
                catch (Exception ex)
                {
                    try { Console.WriteLine("  \u00D7 内部错误：" + ex.Message); } catch { }
                    ok = false;
                }
                sw.Stop();
                long ms = sw.ElapsedMilliseconds;
                try
                {
                    BeginInvoke((MethodInvoker)delegate { PushEnd(ok, ms, 0); });
                }
                catch { _busy[0] = false; }
            }));
            _worker[0].IsBackground = true;
            _worker[0].SetApartmentState(ApartmentState.STA);
            _worker[0].Start();
        }

        private void RunApkAct(string pkg, string act)
        {
            if (string.IsNullOrEmpty(pkg))
            {
                PushApkAck(false, "没有选择应用", "act");
                return;
            }

            if (act == "clear")
            {
                RunApkJob(delegate { return App.ClearPkg(pkg); }, "清空数据 " + pkg);
            }
            else if (act == "kill")
            {
                RunApkJob(delegate { return App.KillPkg(pkg); }, "关闭进程 " + pkg);
            }
            else if (act == "export")
            {
                RunApkJob(delegate { return App.ExportPkg(pkg); }, "导出APK " + pkg);
            }
            else if (act == "uninstall")
            {
                // T8：不加二次确认弹层（用户明确要求），风险靠正反双判 + 明确提示兜
                RunApkJob(delegate { return App.UninstallPkg(pkg); }, "卸载APK " + pkg);
            }
            else
            {
                PushApkAck(false, "未知动作：" + act, "act");
            }
        }

        // 批量查版本：一次 adb 调用查全部，结果按结构化 JSON 推回，
        // 由页面决定怎么排版（名称/包名/版本/路径，放不下换行）。
        private void RunApkVer()
        {
            if (_busy[0]) { PushBusyReject(); return; }

            _cmdSource[0] = 3;
            _lastCmd[0] = "查询全部版本";
            _stopRequested[0] = false;

            PushBegin(0);
            _busy[0] = true;

            Stopwatch sw = Stopwatch.StartNew();
            _worker[0] = new Thread(new ThreadStart(delegate()
            {
                App.CUR_SLOT = 0;
                List<App.VerRow> rows = null;
                try
                {
                    List<App.ApkApp> apps = App.ApkListSnapshot();
                    List<App.VerPkg> targets = new List<App.VerPkg>();
                    for (int i = 0; i < apps.Count; i++)
                    {
                        App.VerPkg p = new App.VerPkg();
                        p.Pkg = apps[i].Pkg;
                        p.Alias = apps[i].Name;
                        targets.Add(p);
                    }
                    if (targets.Count > 0)
                    {
                        List<string> notes = null;
                        rows = App.QueryVersionRows(targets, out notes);
                    }
                }
                catch (Exception ex) { GuiEntry.Dump("RunApkVer", ex); }
                sw.Stop();
                long ms = sw.ElapsedMilliseconds;
                try
                {
                    BeginInvoke((MethodInvoker)delegate
                    {
                        PushApkVer(rows, ms);
                        PushEnd(rows != null, ms, 0);
                    });
                }
                catch { _busy[0] = false; }
            }));
            _worker[0].IsBackground = true;
            _worker[0].SetApartmentState(ApartmentState.STA);
            _worker[0].Start();
        }

        // 单点查询：选中应用 → 包名 / Activity / 路径 / 版本 / pid
        // 与 :front 的区别：那个查"当前前台"，这个查"你选中的那个包"，用 adb 直接取。
        private void RunApkQuery(string pkg)
        {
            if (string.IsNullOrEmpty(pkg)) return;
            // T7（2026-11-19）：前端现在允许**直接手输包名**，这条路原来完全没有校验，
            // 会把用户输入原样 ShQuote 塞进 shell。补一道与前端同口径的守卫
            // （≥3 字符、含点、不以点结尾、仅 a-zA-Z0-9._），非法就只提示、不落 shell。
            string perr = "";
            if (!App.ApkPkgValid(pkg, out perr))
            {
                PushApkAck(false, "包名不合法：" + perr + "（收到的值是「" + pkg + "」）", "query");
                return;
            }

            Thread th = new Thread(new ThreadStart(delegate()
            {
                string act = "";
                string ver = "";
                string path = "";
                string pid = "";
                try
                {
                    List<App.VerPkg> one = new List<App.VerPkg>();
                    App.VerPkg t = new App.VerPkg();
                    t.Pkg = pkg;
                    t.Alias = "";
                    one.Add(t);

                    List<string> notes = null;
                    List<App.VerRow> rows = App.QueryVersionRows(one, out notes);
                    if (rows != null && rows.Count > 0)
                    {
                        ver = rows[0].VerName;
                        path = rows[0].Path;
                        pid = rows[0].Pid;
                    }

                    // Activity：cmd package resolve-activity --brief <pkg>
                    string o = "";
                    string e = "";
                    App.ShellCall(App.CUR, "cmd package resolve-activity --brief " + App.ShQuote(pkg) + " 2>/dev/null", out o, out e);
                    string[] al = (o + "\n" + e).Split('\n');
                    for (int i = al.Length - 1; i >= 0; i--)
                    {
                        string l = al[i].Trim();
                        if (l.Length == 0) continue;
                        if (l.IndexOf('/') > 0) { act = l; break; }
                    }
                }
                catch (Exception ex) { GuiEntry.Dump("RunApkQuery", ex); }

                FinishInvoke(delegate
                {
                    try
                    {
                        _web.CoreWebView2.PostWebMessageAsJson(
                            "{\"kind\":\"apkdetail\",\"pkg\":" + Json(pkg)
                            + ",\"ver\":" + Json(ver)
                            + ",\"act\":" + Json(act)
                            + ",\"path\":" + Json(path)
                            + ",\"pid\":" + Json(pid) + "}");
                    }
                    catch { }
                });
            }));
            th.IsBackground = true;
            th.Start();
        }

        private void PushApkVer(List<App.VerRow> rows, long ms)
        {
            try
            {
                StringBuilder sb = new StringBuilder(512 + (rows == null ? 0 : rows.Count) * 200);
                sb.Append("{\"kind\":\"apkver\",\"ms\":").Append(ms).Append(",\"rows\":[");
                if (rows != null)
                {
                    for (int i = 0; i < rows.Count; i++)
                    {
                        if (i > 0) sb.Append(',');
                        App.VerRow r = rows[i];
                        sb.Append("{\"name\":").Append(Json(r.Alias))
                          .Append(",\"pkg\":").Append(Json(r.Pkg))
                          .Append(",\"ver\":").Append(Json(r.VerName))
                          .Append(",\"code\":").Append(Json(r.VerCode))
                          .Append(",\"path\":").Append(Json(r.Path))
                          .Append(",\"pid\":").Append(Json(r.Pid))
                          .Append(",\"ok\":").Append(r.Installed ? "true" : "false")
                          .Append('}');
                    }
                }
                sb.Append("]}");
                _web.CoreWebView2.PostWebMessageAsJson(sb.ToString());
            }
            catch (Exception ex) { GuiEntry.Dump("PushApkVer", ex); }
        }

        // ==================== 投屏 ====================
        //
        // 协议：
        //   前端 -> 后端  castlist / caststart{slot,id} / caststop{slot} / caststat{slot} / castrec{slot,id,on}
        //   后端 -> 前端  castdisplays{port,items[]} / caststat{slot,on,frames,lastMs,id,err} / castrec{ok,file,msg}
        //
        // 帧不走 JSON：浏览器直接连 127.0.0.1:<port>/live/<slot> 拿 multipart 流，
        // 后端只推状态。否则 5 路 × 3fps 的 base64 会把 UI 线程打满。

        private void PushCastStat(int slot)
        {
            try
            {
                bool on; long frames; long lastMs; int disp; string err;
                App.CastInfo(slot, out on, out frames, out lastMs, out disp, out err);
                _web.CoreWebView2.PostWebMessageAsJson(
                    "{\"kind\":\"caststat\",\"slot\":" + slot
                    + ",\"on\":" + (on ? "true" : "false")
                    + ",\"frames\":" + frames
                    + ",\"lastMs\":" + lastMs
                    + ",\"id\":" + disp
                    + ",\"err\":" + Json(err) + "}");
            }
            catch { }
        }

        // 点投屏 = 点设备：input tap x y。
        // 2026-11-15 流畅化（对齐前端的 25ms 节流）：
        //   1) 丢弃式 per-slot 队列：同一槽高频连点只保留最新一次，adb tap 进程不堆积；
        //      不同槽各自独立，不互相吞。_dict 覆盖写即"合并"。
        //   2) 单个后台 worker 串行执行所有 tap，绝不在 UI/消息线程跑（一次 tap 100~200ms）。
        //   3) 每次 tap 落地后 App.CastKick(slot) 立刻唤醒该槽采集循环抓一帧，
        //      画面马上反映点击结果，不用等 minGapMs 的帧间等待睡满。
        private struct TapPt { public int X; public int Y; }
        private static readonly object CAST_TAP_LK = new object();
        private static readonly Dictionary<int, TapPt> CAST_TAP_PEND = new Dictionary<int, TapPt>();
        private static bool _castTapBusy = false;

        private void RunCastTap(int slot, int x, int y)
        {
            if (slot < 0 || x < 0 || y < 0) return;
            lock (CAST_TAP_LK)
            {
                CAST_TAP_PEND[slot] = new TapPt { X = x, Y = y };   // 覆盖 = 合并同槽连点
                if (_castTapBusy) return;                             // worker 在跑，会顺手取走
                _castTapBusy = true;
            }
            ThreadPool.QueueUserWorkItem(delegate { CastTapWorker(); });
        }

        private static void CastTapWorker()
        {
            // ThreadPool 工作项里未捕获的异常 = 整个进程崩溃（.NET 2.0+ 行为）。
            // 兜底之外还必须复位 _castTapBusy，否则一旦异常逃出，
            // 以后所有点击都以为有 worker 在跑而不再起线程（点击永久失灵）。
            try
            {
            while (true)
            {
                int slot = -1;
                TapPt pt = new TapPt();
                lock (CAST_TAP_LK)
                {
                    if (CAST_TAP_PEND.Count == 0) { _castTapBusy = false; return; }
                    foreach (KeyValuePair<int, TapPt> kv in CAST_TAP_PEND)
                    {
                        slot = kv.Key; pt = kv.Value; break;          // 取一个待办
                    }
                    CAST_TAP_PEND.Remove(slot);
                }
                string o = "";
                string e = "";
                try
                {
                    App.AdbCall(new List<string> {
                        "shell", "input", "tap", pt.X.ToString(), pt.Y.ToString() }, out o, out e);
                }
                catch (Exception ex) { App.Trace("cast: tap 失败 " + ex.Message); }
                try { App.CastKick(slot); } catch { }                 // 立刻抓一帧
            }
            }
            catch (Exception ex)
            {
                App.Trace("cast: tap worker 崩溃 " + ex.Message);
                lock (CAST_TAP_LK) { _castTapBusy = false; }
            }
        }

        private void RunCastList()
        {
            Thread th = new Thread(new ThreadStart(delegate()
            {
                List<App.CastDisplay> list = new List<App.CastDisplay>();
                try { list = App.CastDisplays(); }
                catch (Exception ex) { GuiEntry.Dump("CastDisplays", ex); }

                App.CastServer.Start();

                FinishInvoke(delegate
                {
                    try
                    {
                        StringBuilder sb = new StringBuilder(256);
                        sb.Append("{\"kind\":\"castdisplays\",\"port\":").Append(App.CastServer.Port)
                          .Append(",\"items\":[");
                        for (int i = 0; i < list.Count; i++)
                        {
                            if (i > 0) sb.Append(',');
                            App.CastDisplay d = list[i];
                            sb.Append("{\"id\":").Append(d.Id)
                              .Append(",\"w\":").Append(d.W)
                              .Append(",\"h\":").Append(d.H)
                              .Append(",\"type\":").Append(Json(d.Type))
                              .Append(",\"active\":").Append(d.Active ? "true" : "false")
                              .Append('}');
                        }
                        sb.Append("]}");
                        _web.CoreWebView2.PostWebMessageAsJson(sb.ToString());
                    }
                    catch { }
                });
            }));
            th.IsBackground = true;
            th.Start();
        }

        private void RunCastRecord(int slot, int id, bool on)
        {
            Thread th = new Thread(new ThreadStart(delegate()
            {
                bool ok = false;
                string file = "";
                string msg = "";
                try
                {
                    if (on)
                    {
                        ok = App.CastRecordStart(slot, id, out msg);
                        if (ok) msg = "录制中（最长 60 秒，再点一次停止）";
                    }
                    else
                    {
                        string outFile = "";
                        string err = "";
                        ok = App.CastRecordStop(slot, out outFile, out err);
                        if (ok) { file = outFile; msg = "已保存：" + System.IO.Path.GetFileName(outFile); }
                        else msg = err;
                    }
                }
                catch (Exception ex) { msg = ex.Message; }

                FinishInvoke(delegate
                {
                    try
                    {
                        _web.CoreWebView2.PostWebMessageAsJson(
                            "{\"kind\":\"castrec\",\"ok\":" + (ok ? "true" : "false")
                            + ",\"slot\":" + slot
                            + ",\"file\":" + Json(file)
                            + ",\"msg\":" + Json(msg) + "}");
                    }
                    catch { }
                });
            }));
            th.IsBackground = true;
            th.Start();
        }

        // ==================== 录屏编码器 ffmpeg（R9） ====================
        //
        // 协议：
        //   前端 -> 后端  ffmpegstat / ffmpegauto / ffmpegpick / ffmpegset{path}
        //   后端 -> 前端  ffmpegstat{ok,path,source,version,err}
        //
        // 为什么要在后台线程跑：
        //   校验会真的启动一次 `ffmpeg -version`，约 100~300ms；四级查找在
        //   没命中的机器上要试十来个路径，能有 1 秒以上。放 UI 线程会让
        //   整个窗口卡住（包括投屏画面）。
        //
        // mode: 0=查缓存 1=强制重扫 2=指定路径（校验后写 ini） 3=弹选择框
        private void RunFfmpegJob(int mode, string arg)
        {
            string picked = arg == null ? "" : arg;
            int orig = mode;    // 选择框内部会把 mode 改成 2，req 仍要标成 pick

            // 选择框必须在 UI 线程弹 —— 这里正好是 UI 线程（WebMessage 回调）
            if (mode == 3)
            {
                try
                {
                    using (OpenFileDialog d = new OpenFileDialog())
                    {
                        d.Title = "选择 ffmpeg.exe（截帧录屏用它合成 mp4）";
                        d.Filter = "ffmpeg (ffmpeg.exe)|ffmpeg.exe|可执行文件 (*.exe)|*.exe|所有文件 (*.*)|*.*";
                        d.CheckFileExists = true;
                        d.CheckPathExists = true;

                        bool okNow;
                        string p0;
                        string s0;
                        string v0;
                        string line = Ffmpeg.StatusLine(out okNow, out p0, out s0, out v0);
                        try
                        {
                            d.InitialDirectory = okNow
                                ? Path.GetDirectoryName(p0)
                                : Path.Combine(Embed.DataDir(), "");
                        }
                        catch { }

                        if (d.ShowDialog(this) != DialogResult.OK) return;   // 取消：不推消息
                        picked = d.FileName;
                    }
                    mode = 2;
                }
                catch (Exception ex)
                {
                    GuiEntry.Dump("ffmpeg 选择框", ex);
                    PushFfmpegResult(false, "", "", "", "打开文件选择框失败：" + ex.Message, "pick");
                    return;
                }
            }

            string reqName = (orig == 3) ? "pick" : (orig == 2 ? "set" : (orig == 1 ? "auto" : "stat"));
            int m = mode;
            string target = picked;

            Thread th = new Thread(new ThreadStart(delegate()
            {
                if (m == 1) Ffmpeg.ClearCache();

                if (m == 2)
                {
                    string ver = "";
                    string err = "";
                    bool ok = Ffmpeg.Use(target, out ver, out err);
                    FinishInvoke(delegate
                    {
                        PushFfmpegResult(ok, ok ? target : "", "手动指定", ver, ok ? "" : err, reqName);
                    });
                    return;
                }

                bool okc;
                string path = "";
                string src = "";
                string ver2 = "";
                string line2 = "";
                try { line2 = Ffmpeg.StatusLine(out okc, out path, out src, out ver2); }
                catch (Exception ex) { okc = false; line2 = ex.Message; }

                string e2 = okc ? "" : line2;
                FinishInvoke(delegate { PushFfmpegResult(okc, path, src, ver2, e2, reqName); });
            }));
            th.IsBackground = true;
            th.Start();
        }

        private void PushFfmpegResult(bool ok, string path, string source, string version, string err, string req)
        {
            try
            {
                _web.CoreWebView2.PostWebMessageAsJson(
                    "{\"kind\":\"ffmpegstat\",\"ok\":" + (ok ? "true" : "false")
                    + ",\"path\":" + Json(path)
                    + ",\"source\":" + Json(source)
                    + ",\"version\":" + Json(version)
                    + ",\"req\":" + Json(req == null ? "" : req)
                    + ",\"err\":" + Json(err == null ? "" : err) + "}");
            }
            catch { }
        }

        // ==================== 外挂 scrcpy（R10） ====================
        //
        // 协议：
        //   前端 -> 后端  scrcpystat / scrcpyauto / scrcpypick / scrcpyset{path} / scrcpyopen{id,slot}
        //   后端 -> 前端  scrcpystat{ok,path,version,err,req} / scrcpyres{ok,msg,slot,id}
        //
        // mode: 0=查缓存 1=强制重扫 2=指定路径 3=弹选择框 4=开一个 scrcpy 窗口
        private void RunScrcpyJob(int mode, int displayId, int slot)
        {
            RunScrcpyJob(mode, displayId, slot, "");
        }

        private void RunScrcpyJob(int mode, int displayId, int slot, string arg)
        {
            string picked = arg == null ? "" : arg;
            int orig = mode;

            if (mode == 3)
            {
                try
                {
                    using (OpenFileDialog d = new OpenFileDialog())
                    {
                        d.Title = "选择 scrcpy.exe（可选：流畅投屏通道）";
                        d.Filter = "scrcpy (scrcpy.exe)|scrcpy.exe|可执行文件 (*.exe)|*.exe|所有文件 (*.*)|*.*";
                        d.CheckFileExists = true;
                        d.CheckPathExists = true;
                        try
                        {
                            string ver = "";
                            string le = "";
                            string cur = Scrcpy.Locate(out ver, out le);
                            d.InitialDirectory = cur.Length > 0
                                ? Path.GetDirectoryName(cur)
                                : Embed.DataDir();
                        }
                        catch { }
                        if (d.ShowDialog(this) != DialogResult.OK) return;
                        picked = d.FileName;
                    }
                    mode = 2;
                }
                catch (Exception ex)
                {
                    GuiEntry.Dump("scrcpy 选择框", ex);
                    PushScrcpyStat(false, "", "", "打开文件选择框失败：" + ex.Message, "pick");
                    return;
                }
            }

            string reqName = (orig == 3) ? "pick" : (orig == 2 ? "set" : (orig == 1 ? "auto" : "stat"));
            int m = mode;
            string target = picked;

            Thread th = new Thread(new ThreadStart(delegate()
            {
                if (m == 1) Scrcpy.ClearCache();

                if (m == 4)
                {
                    string err = "";
                    bool ok = false;
                    try { ok = Scrcpy.Launch(displayId, out err); }
                    catch (Exception ex) { err = "启动异常：" + ex.Message; }
                    string msg = ok
                        ? ("已用 scrcpy 打开屏 " + displayId + "（独立窗口，流畅；内置通道保持运行）")
                        : ("scrcpy 不可用，继续用内置截帧通道：" + err);
                    FinishInvoke(delegate { PushScrcpyRes(ok, msg, slot, displayId); });
                    return;
                }

                if (m == 2)
                {
                    string ver = "";
                    string err = "";
                    bool ok = Scrcpy.Use(target, out ver, out err);
                    FinishInvoke(delegate { PushScrcpyStat(ok, ok ? target : "", ver, ok ? "" : err, reqName); });
                    return;
                }

                bool okc;
                string path = "";
                string ver2 = "";
                string line = "";
                try { line = Scrcpy.StatusLine(out okc, out path, out ver2); }
                catch (Exception ex) { okc = false; line = ex.Message; }
                string e2 = okc ? "" : line;
                FinishInvoke(delegate { PushScrcpyStat(okc, path, ver2, e2, reqName); });
            }));
            th.IsBackground = true;
            th.Start();
        }

        private void PushScrcpyStat(bool ok, string path, string version, string err, string req)
        {
            try
            {
                _web.CoreWebView2.PostWebMessageAsJson(
                    "{\"kind\":\"scrcpystat\",\"ok\":" + (ok ? "true" : "false")
                    + ",\"path\":" + Json(path)
                    + ",\"version\":" + Json(version)
                    + ",\"req\":" + Json(req == null ? "" : req)
                    + ",\"err\":" + Json(err == null ? "" : err) + "}");
            }
            catch { }
        }

        private void PushScrcpyRes(bool ok, string msg, int slot, int id)
        {
            try
            {
                _web.CoreWebView2.PostWebMessageAsJson(
                    "{\"kind\":\"scrcpyres\",\"ok\":" + (ok ? "true" : "false")
                    + ",\"slot\":" + slot + ",\"id\":" + id
                    + ",\"msg\":" + Json(msg == null ? "" : msg) + "}");
            }
            catch { }
        }

        // ==================== A15：日志等级 / 设备管理 ====================
        //
        // 两个都是"顶栏徽章 → hover 看 / 点击管"的同一套交互，
        // 和无线 adb（wadb-pop）保持一致：点外面收起、不抢焦点。

        private void PushLogTag(string val)
        {
            try
            {
                _web.CoreWebView2.PostWebMessageAsJson(
                    "{\"kind\":\"logtag\",\"data\":" + Json(val == null ? "" : val) + "}");
            }
            catch { }
        }

        /// <summary>
        /// 读 / 写 persist.log.tag。setTo 为 null 时只读。
        /// 写完一定要回读：这个属性在部分车机上被 SELinux 拦住，
        /// setprop 返回成功不表示真的写进去了。
        /// </summary>
        private void RunLogTagJob(string setTo)
        {
            Thread th = new Thread(new ThreadStart(delegate
            {
                string val = "";
                try
                {
                    if (!string.IsNullOrEmpty(setTo))
                    {
                        string so, se;
                        App.ShellCall(App.CUR, "setprop persist.log.tag " + setTo, out so, out se);
                    }
                    string o = "", e = "";
                    App.ShellCall(App.CUR, "getprop persist.log.tag", out o, out e);
                    val = (o ?? "").Trim();
                    if (val.Length == 0) val = (e ?? "").Trim();
                }
                catch (Exception ex)
                {
                    val = "";
                    App.Trace("logtag 失败：" + ex.Message);
                }
                string v = val;
                FinishInvoke(delegate { PushLogTag(v); });
            }));
            th.IsBackground = true;
            th.Start();
        }

        private void PushDeviceList(string payload)
        {
            try
            {
                _web.CoreWebView2.PostWebMessageAsJson(
                    "{\"kind\":\"devlist\",\"data\":" + Json(payload == null ? "" : payload) + "}");
            }
            catch { }
        }

        /// <summary>
        /// 列设备：serial|model|state|是否当前，一行一台。
        /// 用文本行而不是 JSON —— 这里只有四个字段，C# 拼字符串比序列化省事，
        /// 前端 split('|') 也不会踩转义。
        /// </summary>
        private void RunDeviceListJob()
        {
            Thread th = new Thread(new ThreadStart(delegate
            {
                StringBuilder sb = new StringBuilder();
                try
                {
                    string o = "", e = "";
                    bool to = false;
                    List<string> argv = new List<string>();
                    argv.Add("devices");
                    argv.Add("-l");
                    App.RunRaw(argv, 8000, out o, out e, out to, true);
                    string all = (o ?? "") + "\n" + (e ?? "");
                    string cur = (!string.IsNullOrEmpty(App.SERIAL)) ? App.SERIAL : App.DEVID;

                    string[] lines = all.Replace("\r", "").Split('\n');
                    for (int i = 0; i < lines.Length; i++)
                    {
                        string ln = lines[i].Trim();
                        if (ln.Length == 0) continue;
                        if (ln.StartsWith("List of devices")) continue;
                        if (ln.StartsWith("*")) continue;          // daemon 提示
                        string[] tok = ln.Split(new char[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries);
                        if (tok.Length < 2) continue;
                        string s0 = tok[0];
                        string st = tok[1];
                        string model = "";
                        for (int k = 2; k < tok.Length; k++)
                        {
                            if (tok[k].StartsWith("model:"))
                            {
                                model = tok[k].Substring(6).Replace('_', ' ');
                                break;
                            }
                        }
                        bool isCur = (s0 == cur);
                        sb.Append(s0).Append('|').Append(model).Append('|')
                          .Append(st).Append('|').Append(isCur ? "1" : "0").Append('\n');
                    }
                }
                catch (Exception ex)
                {
                    App.Trace("devlist 失败：" + ex.Message);
                }
                string payload = sb.ToString();
                FinishInvoke(delegate { PushDeviceList(payload); });
            }));
            th.IsBackground = true;
            th.Start();
        }

        /// <summary>
        /// 切换当前设备。
        /// 除了改 SERIAL，还必须把按设备缓存的东西全部作废 —— 车机信息、
        /// 屏位、APK 列表都是上次那台设备的，不刷新会出现"换了设备还显示旧型号"。
        /// </summary>
        private void DoDeviceSwitch(string serial)
        {
            string s = (serial ?? "").Trim();
            if (s.Length == 0) return;
            App.SERIAL = s;
            App.SERIAL_OK = true;
            try { SaveIniKey("serial", s); } catch { }

            Thread th = new Thread(new ThreadStart(delegate
            {
                try { App.LoadCarInfo(); } catch { }
                FinishInvoke(delegate
                {
                    PushStatus(App.DEVN > 0, 0, null);
                    RunDeviceListJob();
                });
            }));
            th.IsBackground = true;
            th.Start();
        }

        /// <summary>
        /// 断开设备。USB 连接软件断不了（不存在 adb disconnect 的 USB 语义），
        /// 只对 TCP 序列号（含 ":"）执行；否则明确告诉用户去拔线，别假装成功。
        /// </summary>
        private void DoDeviceDisconnect(string serial)
        {
            string s = (serial ?? "").Trim();
            if (s.Length == 0) s = App.SERIAL;
            if (s.Length == 0) s = App.DEVID;

            Thread th = new Thread(new ThreadStart(delegate
            {
                string msg;
                try
                {
                    if (s.IndexOf(':') > 0)
                    {
                        string o = "", e = "";
                        bool to = false;
                        List<string> argv = new List<string>();
                        argv.Add("disconnect");
                        argv.Add(s);
                        App.RunRaw(argv, 8000, out o, out e, out to, true);
                        msg = "已断开无线设备 " + s;
                        App.SERIAL_OK = false;
                    }
                    else
                    {
                        msg = "USB 连接无法软件断开，请直接拔线（" + s + "）";
                    }
                }
                catch (Exception ex) { msg = "断开失败：" + ex.Message; }
                string m = msg;
                FinishInvoke(delegate
                {
                    PushStatus(App.DEVN > 0, 0, m);
                    RunDeviceListJob();
                });
            }));
            th.IsBackground = true;
            th.Start();
        }

        // ==================== 文件管理 ====================
        //
        // 协议：
        //   前端 -> 后端  fslist{side,path} / fscopy{dir,dst,src(换行分隔)} / fscancel / fsop{op,side,path,name}
        //   后端 -> 前端  fslist{side,path,parent,items[],err} / fsprog{done,total,name} / fsdone{...} / fsack{ok,msg}
        //
        // 为什么进度用单独消息而不是 console 行：文件页没有日志区，
        // 进度条要的是 done/total 两个数字，塞进文本行还得回头解析。

        private void PushFsList(string side, string path, string parent, List<App.FsEntry> items, string err)
        {
            try
            {
                StringBuilder sb = new StringBuilder(512 + items.Count * 120);
                sb.Append("{\"kind\":\"fslist\",\"side\":").Append(Json(side))
                  .Append(",\"path\":").Append(Json(path))
                  .Append(",\"parent\":").Append(Json(parent == null ? "" : parent))
                  .Append(",\"err\":").Append(Json(err))
                  .Append(",\"items\":[");
                for (int i = 0; i < items.Count; i++)
                {
                    if (i > 0) sb.Append(',');
                    App.FsEntry e = items[i];
                    sb.Append("{\"name\":").Append(Json(e.Name))
                      .Append(",\"path\":").Append(Json(e.Path))
                      .Append(",\"dir\":").Append(e.IsDir ? "true" : "false")
                      .Append(",\"link\":").Append(e.IsLink ? "true" : "false")
                      .Append(",\"size\":").Append(e.Size)
                      .Append(",\"time\":").Append(Json(e.Time))
                      .Append(",\"perm\":").Append(Json(e.Perm))
                      .Append(",\"sizeText\":").Append(Json(App.FsSizeText(e)))
                      .Append('}');
                }
                sb.Append("]}");
                _web.CoreWebView2.PostWebMessageAsJson(sb.ToString());
            }
            catch (Exception ex) { GuiEntry.Dump("PushFsList", ex); }
        }

        // 搜索：走后台线程，结果一次性回包（本地万级目录也就几百毫秒）
        // seq 由前端递增，用于丢弃"旧搜索"的迟到回包（用户改了关键词又敲了一次）
        private void RunFsSearch(string side, string root, string q, int seq)
        {
            Thread th = new Thread(new ThreadStart(delegate()
            {
                string err = "";
                List<App.FsEntry> items = new List<App.FsEntry>();
                bool truncated = false;
                long ms = 0;
                System.Diagnostics.Stopwatch sw = System.Diagnostics.Stopwatch.StartNew();
                App.FS_SEARCH_CANCEL = false;   // 每次新搜索先清标志
                try
                {
                    if (side == "dev")
                    {
                        // 设备：默认只在 /sdcard 下搜（/ 下 permission denied 太多且极慢）
                        items = App.FsDeviceSearch(root, q, 500, 6, out truncated, out err);
                    }
                    else
                    {
                        items = App.FsLocalSearch(root, q, 500, 8, out truncated, out err);
                    }
                }
                catch (Exception ex)
                {
                    err = ex.Message;
                    items = new List<App.FsEntry>();
                }
                sw.Stop();
                ms = sw.ElapsedMilliseconds;
                if (items == null) items = new List<App.FsEntry>();

                FinishInvoke(delegate { PushFsSearch(side, root, q, seq, items, truncated, err, ms); });
            }));
            th.IsBackground = true;
            th.Start();
        }

        private void PushFsSearch(string side, string root, string q, int seq,
                                  List<App.FsEntry> items, bool truncated, string err, long ms)
        {
            try
            {
                StringBuilder sb = new StringBuilder(512 + items.Count * 120);
                sb.Append("{\"kind\":\"fssearchdone\",\"side\":").Append(Json(side))
                  .Append(",\"root\":").Append(Json(root))
                  .Append(",\"q\":").Append(Json(q))
                  .Append(",\"seq\":").Append(seq)
                  .Append(",\"truncated\":").Append(truncated ? "true" : "false")
                  .Append(",\"ms\":").Append(ms)
                  .Append(",\"err\":").Append(Json(err))
                  .Append(",\"items\":[");
                for (int i = 0; i < items.Count; i++)
                {
                    if (i > 0) sb.Append(',');
                    App.FsEntry e = items[i];
                    sb.Append("{\"name\":").Append(Json(e.Name))
                      .Append(",\"path\":").Append(Json(e.Path))
                      .Append(",\"dir\":").Append(e.IsDir ? "true" : "false")
                      .Append(",\"link\":").Append(e.IsLink ? "true" : "false")
                      .Append(",\"size\":").Append(e.Size)
                      .Append(",\"time\":").Append(Json(e.Time))
                      .Append(",\"perm\":").Append(Json(e.Perm))
                      .Append(",\"sizeText\":").Append(Json(App.FsSizeText(e)))
                      .Append('}');
                }
                sb.Append("]}");
                _web.CoreWebView2.PostWebMessageAsJson(sb.ToString());
            }
            catch (Exception ex) { GuiEntry.Dump("PushFsSearch", ex); }
        }

        private void RunFsList(string side, string path)
            {
            Thread th = new Thread(new ThreadStart(delegate()
            {
                string err = "";
                string parent = "";
                List<App.FsEntry> items = null;
                try
                {
                    if (side == "dev")
                    {
                        items = App.FsDeviceList(path, out err);
                        parent = App.FsDeviceParent(path);
                    }
                    else
                    {
                        items = App.FsLocalList(path, out err);
                        parent = App.FsLocalParent(path);
                    }
                }
                catch (Exception ex)
                {
                    err = ex.Message;
                    items = new List<App.FsEntry>();
                }
                if (items == null) items = new List<App.FsEntry>();

                FinishInvoke(delegate { PushFsList(side, path, parent, items, err); });
            }));
            th.IsBackground = true;
            th.Start();
        }

        private void PushFsProgBytes(long sent, long total, string name)
        {
            try
            {
                _web.CoreWebView2.PostWebMessageAsJson(
                    "{\"kind\":\"fsprog\",\"done\":0,\"total\":1,\"name\":" + Json(name)
                    + ",\"bytes\":" + sent + ",\"bytesTotal\":" + total + "}");
            }
            catch { }
        }

        private void PushFsProg(int done, int total, string name)
        {
            try
            {
                _web.CoreWebView2.PostWebMessageAsJson(
                    "{\"kind\":\"fsprog\",\"done\":" + done + ",\"total\":" + total
                    + ",\"name\":" + Json(name) + "}");
            }
            catch { }
        }

        private void RunFsCopy(string dir, string dst, string srcJoined)
        {
            // src 用换行分隔（Windows 文件名不允许换行，设备侧极端情况忽略）
            List<string> src = new List<string>();
            if (!string.IsNullOrEmpty(srcJoined))
            {
                string[] parts = srcJoined.Split('\n');
                for (int i = 0; i < parts.Length; i++)
                {
                    string t = parts[i].Trim();
                    if (t.Length > 0) src.Add(t);
                }
            }
            if (src.Count == 0 || string.IsNullOrEmpty(dst))
            {
                try { _web.CoreWebView2.PostWebMessageAsJson("{\"kind\":\"fsack\",\"ok\":false,\"msg\":\"没有选择文件\"}"); }
                catch { }
                return;
            }

            Thread th = new Thread(new ThreadStart(delegate()
            {
                App.FS_CANCEL = false;
                List<string> failed = new List<string>();
                int okCount = 0;
                try
                {
                    List<string> errs = new List<string>();

                    // 单文件走"流式 + 字节进度"；目录仍交给 adb push/pull（按文件计数）
                    if (dir == "down" && src.Count == 1 && !App.FsDevIsDir(src[0]))
                    {
                        string name = App.LastSeg(src[0]);
                        long total = App.FsDevFileSize(src[0]);
                        try { Directory.CreateDirectory(dst); } catch { }
                        string target = Path.Combine(dst, name);
                        if (File.Exists(target) || Directory.Exists(target))
                            target = Path.Combine(dst, App.FsTimeStampName(name));

                        string e1 = "";
                        bool okOne = App.FsCopyDownStream(src[0], target, total,
                            delegate(long sent, long tot)
                            {
                                FinishInvoke(delegate { PushFsProgBytes(sent, tot, name); });
                            }, out e1);
                        if (okOne) okCount++;
                        else failed.Add(name + "：" + e1);
                    }
                    else if (dir != "down" && src.Count == 1 && File.Exists(src[0]))
                    {
                        string name = Path.GetFileName(src[0]);
                        long total = new FileInfo(src[0]).Length;
                        string target = App.JoinDev(dst, name);
                        if (App.FsDeviceExists(target)) target = App.JoinDev(dst, App.FsTimeStampName(name));

                        string e2 = "";
                        bool okOne = App.FsCopyUpStream(src[0], target, total,
                            delegate(long sent, long tot)
                            {
                                FinishInvoke(delegate { PushFsProgBytes(sent, tot, name); });
                            }, out e2);
                        if (okOne) okCount++;
                        else failed.Add(name + "：" + e2);
                    }
                    else if (dir == "down")
                    {
                        okCount = App.FsPull(src, dst, delegate(int d, int t, string n)
                        {
                            FinishInvoke(delegate { PushFsProg(d, t, n); });
                        }, out failed);
                    }
                    else
                    {
                        okCount = App.FsPush(src, dst, delegate(int d, int t, string n)
                        {
                            FinishInvoke(delegate { PushFsProg(d, t, n); });
                        }, out failed);
                    }
                }
                catch (Exception ex)
                {
                    failed.Add(ex.Message);
                    GuiEntry.Dump("RunFsCopy", ex);
                }

                bool cancel = App.FS_CANCEL;
                App.FS_CANCEL = false;

                FinishInvoke(delegate
                {
                    try
                    {
                        StringBuilder sb = new StringBuilder();
                        sb.Append("{\"kind\":\"fsdone\",\"dir\":").Append(Json(dir))
                          .Append(",\"dst\":").Append(Json(dst))
                          .Append(",\"count\":").Append(okCount)
                          .Append(",\"cancel\":").Append(cancel ? "true" : "false")
                          .Append(",\"failed\":[");
                        for (int i = 0; i < failed.Count && i < 5; i++)
                        {
                            if (i > 0) sb.Append(',');
                            sb.Append(Json(failed[i]));
                        }
                        sb.Append("]}");
                        _web.CoreWebView2.PostWebMessageAsJson(sb.ToString());
                    }
                    catch { }
                });
            }));
            th.IsBackground = true;
            th.Start();
        }

        private void RunFsOp(string op, string side, string path, string name)
        {
            Thread th = new Thread(new ThreadStart(delegate()
            {
                bool ok = false;
                string err = "";
                try
                {
                    bool dev = (side == "dev");
                    if (op == "mkdir")
                    {
                        string dir = path;
                        ok = dev ? App.FsDeviceMkdir(dir, name, out err) : App.FsLocalMkdir(dir, name, out err);
                    }
                    else if (op == "del")
                    {
                        List<string> one = new List<string>();
                        one.Add(path);
                        ok = dev ? App.FsDeviceDelete(one, out err) : App.FsLocalDelete(one, out err);
                    }
                    else if (op == "rename")
                    {
                        ok = dev ? App.FsDeviceRename(path, name, out err) : App.FsLocalRename(path, name, out err);
                    }
                    else
                    {
                        err = "未知操作：" + op;
                    }
                }
                catch (Exception ex) { err = ex.Message; }

                FinishInvoke(delegate
                {
                    try
                    {
                        _web.CoreWebView2.PostWebMessageAsJson(
                            "{\"kind\":\"fsack\",\"ok\":" + (ok ? "true" : "false")
                            + ",\"op\":" + Json(op) + ",\"side\":" + Json(side)
                            + ",\"msg\":" + Json(err) + "}");
                    }
                    catch { }
                });
            }));
            th.IsBackground = true;
            th.Start();
        }

        // 跑「原来的前台指令」：走和命令行完全相同的 Dispatch，
        // 所以 :pkg now / :front / :fstop / :apk 的行为、判定、提示一个字都不变，
        // 只是输出源标成 3（进 APK 面板，而不是反馈区）。
        private void RunApkCmd(string cmd)
        {
            string c = App.NormalizeLead(((cmd == null) ? "" : cmd).Trim());
            if (c.Length == 0)
            {
                PushApkAck(false, "没有指定命令", "cmd");
                return;
            }
            RunApkJob(delegate
            {
                App.Dispatch(c);
                return App.CMD_OK;
            }, c);
        }

        // 查当前前台：APK 面板里当"加入列表"的来源，等价于原来的 :pkg now
        private void RunApkFront()
        {
            RunApkJob(delegate
            {
                string pkg = App.QueryForegroundPkg();
                if (pkg.Length == 0)
                {
                    try { Console.WriteLine("  \u00D7 没有识别出前台应用（可能停在锁屏或系统界面）"); }
                    catch { }
                    return false;
                }
                try
                {
                    BeginInvoke((MethodInvoker)delegate
                    {
                        try
                        {
                            _web.CoreWebView2.PostWebMessageAsJson(
                                "{\"kind\":\"apkfront\",\"pkg\":" + Json(pkg) + "}");
                        }
                        catch { }
                    });
                }
                catch { }
                return true;
            }, "查前台应用");
        }

        // ---------------- 无线 adb ----------------
        // 连接要跑 adb tcpip（会让 adbd 重启）+ 等设备回来 + connect + 校验，
        // 全程可能 10 秒，必须放后台线程 —— 在 UI 线程上做窗口会直接卡住。
        private void RunWadbJob(string act, string host)
        {
            Thread th = new Thread(new ThreadStart(delegate()
            {
                bool ok = false;
                string ip = "";
                string err = "";
                try
                {
                    if (act == "disconnect")
                    {
                        try { Console.WriteLine(); Console.WriteLine("  无线调试：正在断开 …"); } catch { }
                        ok = App.WadbDisconnect(host, out err);
                        if (ok)
                        {
                            App.WADB_IP = "";
                            try { Console.WriteLine("  √ 已断开无线连接"); } catch { }
                        }
                        else
                        {
                            try { Console.WriteLine("  × " + err); } catch { }
                        }
                    }
                    else
                    {
                        try
                        {
                            Console.WriteLine();
                            Console.WriteLine("  无线调试：切换到 TCP 模式（adbd 会重启，USB 会瞬断 1~3 秒）…");
                        }
                        catch { }

                        ok = App.WadbConnect(host, out ip, out err);
                        if (ok)
                        {
                            try { Console.WriteLine("  √ 已连接 " + ip + "，可以拔掉 USB 了"); } catch { }
                        }
                        else
                        {
                            try { Console.WriteLine("  × " + err); } catch { }
                        }
                    }
                }
                catch (Exception ex)
                {
                    ok = false;
                    err = ex.Message;
                    GuiEntry.Dump("RunWadbJob", ex);
                }

                FinishInvoke(delegate
                {
                    PushWadb(ok, ip, err);
                    // 连接/断开都会改变设备列表，重推一次状态刷新徽章
                    PushStatus(App.DEVN > 0, 0, ok ? "无线已连接" : null);
                });
            }));
            th.IsBackground = true;
            th.Start();
        }

        private void PushWadb(bool ok, string ip, string msg)
        {
            try
            {
                _web.CoreWebView2.PostWebMessageAsJson(
                    "{\"kind\":\"wadb\",\"ok\":" + (ok ? "true" : "false")
                    + ",\"ip\":" + Json(ip)
                    + ",\"msg\":" + Json(msg) + "}");
            }
            catch { }
        }

        // run 里出现 $1..$9 / $* 就说明这条命令需要参数
        private static bool HasArgPlaceholder(string run)
        {
            if (string.IsNullOrEmpty(run)) return false;
            if (run.IndexOf("$*") >= 0) return true;
            for (int i = 1; i <= 9; i++)
            {
                if (run.IndexOf("$" + i) >= 0) return true;
            }
            return false;
        }

        // ---------------- 极简 JSON 辅助（避免引第三方库） ----------------

        // 数字字段：找不到 / 解析失败一律给 -1，让调用方自己判非法
        private static int GetInt(string json, string name)
        {
            string v = GetField(json, name);
            int n = 0;
            if (int.TryParse(v, out n)) return n;
            return -1;
        }

        // T1（2026-11-18）：原实现是"极简扫描"——跳过开头引号后一直取到下一个
        // `"` / `,` / `}`，**原样返回、不解转义**。后果不只是回显难看：
        //   ① 含双引号的命令被截断：`shell "settings delete global http_proxy"`
        //      到 C# 只剩 `shell \`（扫描器遇到 `\"` 里的 `"` 就停）；
        //   ② UNC 路径 `\\server\share` 变成 `\\\\server\share`，Windows 不一定纠得回来；
        //   ③ 回显（PushEcho 经 Json 再转义）与实际执行的字符串不是同一个来源。
        // 现在按 JSON 规则扫描 + 解码：遇 `\` 跳过一个字符（这样 `\"` 不会当成结束引号），
        // 取值后解 `\\ \" \/ \b \f \n \r \t \uXXXX`。
        // 注意：**调用点不许再自己解一次** —— 会二次解码（`C:\temp` 变 TAB）。
        internal static string GetField(string json, string name)
        {
            if (json == null) return "";
            string key = "\"" + name + "\":";
            int i = json.IndexOf(key, StringComparison.Ordinal);
            if (i < 0) return "";
            i += key.Length;
            while (i < json.Length && (json[i] == ' ' || json[i] == '\t'
                                       || json[i] == '\r' || json[i] == '\n')) i++;
            if (i >= json.Length) return "";

            // 非字符串值（数字 / true / false / null）：原样取到 , 或 }
            if (json[i] != '"')
            {
                int k = i;
                while (k < json.Length && json[k] != ',' && json[k] != '}') k++;
                return json.Substring(i, k - i).Trim();
            }

            i++;                                  // 跳过开引号
            StringBuilder sb = new StringBuilder();
            while (i < json.Length)
            {
                char c = json[i];
                if (c == '"') break;              // 未转义的引号 = 值结束
                if (c != '\\') { sb.Append(c); i++; continue; }
                i++;
                if (i >= json.Length) break;
                char e = json[i];
                switch (e)
                {
                    case '"': sb.Append('"'); break;
                    case '\\': sb.Append('\\'); break;
                    case '/': sb.Append('/'); break;
                    case 'b': sb.Append('\b'); break;
                    case 'f': sb.Append('\f'); break;
                    case 'n': sb.Append('\n'); break;
                    case 'r': sb.Append('\r'); break;
                    case 't': sb.Append('\t'); break;
                    case 'u':
                        if (i + 4 < json.Length)
                        {
                            try
                            {
                                sb.Append((char)Convert.ToInt32(json.Substring(i + 1, 4), 16));
                            }
                            catch { /* 非法 \u —— 保守丢弃这四个字符 */ }
                            i += 4;
                        }
                        break;
                    default:
                        // 非法转义：按字面保留（宁可多一个反斜杠，也不要吞掉用户输入）
                        sb.Append(e);
                        break;
                }
                i++;
            }
            return sb.ToString();
        }

        private static string Json(string s)
        {
            if (s == null) return "\"\"";
            StringBuilder sb = new StringBuilder(s.Length + 2);
            sb.Append('"');
            for (int i = 0; i < s.Length; i++)
            {
                char c = s[i];
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default:
                        if (c < 0x20) sb.Append("\\u").Append(((int)c).ToString("x4"));
                        else sb.Append(c);
                        break;
                }
            }
            sb.Append('"');
            return sb.ToString();
        }

        // ==================== A17：内嵌 scrcpy（投屏画在应用里，可点击） ====================
        //
        // 为什么这么做：内置抓帧通道是 screencap 轮询，单帧受"设备编码 / 链路带宽"限制，
        // 无线 adb 上只有 1~2fps，这是协议上限，怎么调都到不了 30fps。scrcpy 走的是
        // h264 视频流 + 客户端解码，30~60fps 且输入事件直连设备 —— 所以"高帧率 + 跟手"
        // 只能靠它。剩下的问题只是"别弹到应用外面去"，也就是把它的 SDL 窗口 SetParent
        // 到我们自己的一个 Panel 上。
        //
        // 层级关系：WebView2 和 Panel 都是 Form 的子窗口，按 z-order 排。
        // Panel 后创建 + BringToFront 就压在 WebView2 上方；页面只需要告诉我们
        // "那块区域在窗口里占多少比例"，剩下的定位由这里算。
        //
        // 为什么用比例而不是像素：页面受 ZoomFactor（字号设置 0.90/1.00/1.15）和
        // 系统 DPI 双重缩放，CSS px 换成客户区像素要乘两个系数，任一处不同步就错位；
        // 传 0~1 的比例则与缩放无关。

        // A18：内嵌 scrcpy 从"单屏全窗口"改成"每格一块"。
        // 投屏页 3×2 六格（主屏/副屏/后排屏/HUD/PHUD-B/PHUD-C），每格一个 scrcpy 进程、
        // 一个宿主 Panel、一套句柄/标题/轮询，下标即槽位（0..5）。
        private const int CAST_SLOTS = 6;
        private Panel[] _castHost;
        private Process[] _scProc;
        private System.Windows.Forms.Timer[] _scPoll;
        private IntPtr[] _scHwnd;
        private string[] _scTitle;
        private int[] _scSlotId;           // 每槽当前投的 displayId
        private double[] _embL, _embT, _embR, _embB;
        private int[] _scRetry;            // A21：每槽 scrcpy 启动失败重试计数（设备瞬间掉线时救一次）

        [System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
        private static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
        [System.Runtime.InteropServices.DllImport("user32.dll")]
        private static extern IntPtr SetParent(IntPtr hWndChild, IntPtr hWndNewParent);
        [System.Runtime.InteropServices.DllImport("user32.dll")]
        private static extern int GetWindowLong(IntPtr hWnd, int nIndex);
        [System.Runtime.InteropServices.DllImport("user32.dll")]
        private static extern int SetWindowLong(IntPtr hWnd, int nIndex, int dwNewLong);
        [System.Runtime.InteropServices.DllImport("user32.dll")]
        private static extern bool MoveWindow(IntPtr hWnd, int x, int y, int w, int h, bool repaint);

        private void ExecJs(string js)
        {
            try
            {
                if (_web != null && _web.CoreWebView2 != null)
                    _web.CoreWebView2.ExecuteScriptAsync(js);
            }
            catch { }
        }

        private void EnsureCastHosts()
        {
            if (_castHost != null) return;
            _castHost = new Panel[CAST_SLOTS];
            _scProc = new Process[CAST_SLOTS];
            _scPoll = new System.Windows.Forms.Timer[CAST_SLOTS];
            _scHwnd = new IntPtr[CAST_SLOTS];
            _scTitle = new string[CAST_SLOTS];
            _scSlotId = new int[CAST_SLOTS];
            _embL = new double[CAST_SLOTS]; _embT = new double[CAST_SLOTS];
            _embR = new double[CAST_SLOTS]; _embB = new double[CAST_SLOTS];
            _scRetry = new int[CAST_SLOTS];
            for (int i = 0; i < CAST_SLOTS; i++)
            {
                _castHost[i] = new Panel();
                _castHost[i].BackColor = Color.Black;
                _castHost[i].Visible = false;
                int si = i;   // 闭包捕获
                _castHost[i].Resize += delegate { ResizeEmbedded(si); };
                Controls.Add(_castHost[i]);
                _castHost[i].BringToFront();
                _embL[i] = 0.0; _embT[i] = 0.0; _embR[i] = 0.0; _embB[i] = 0.0;
            }
        }

        /// <summary>把内嵌窗口铺满宿主 Panel（scrcpy 的 SDL 窗口会自己把画面缩放到这个尺寸）。</summary>
        private void ResizeEmbedded(int slot)
        {
            try
            {
                if (slot < 0 || slot >= CAST_SLOTS) return;
                if (_scHwnd[slot] == IntPtr.Zero || _castHost[slot] == null) return;
                MoveWindow(_scHwnd[slot], 0, 0,
                    Math.Max(1, _castHost[slot].ClientSize.Width),
                    Math.Max(1, _castHost[slot].ClientSize.Height), true);
            }
            catch { }
        }

        /// <summary>页面回报某槽的区域比例 → 摆宿主 Panel。窗口尺寸变了也走这里。</summary>
        private void ScrcpyEmbedPlace(string data)
        {
            EnsureCastHosts();
            int slot = (int)JsonNum(data, "slot", 0);
            if (slot < 0 || slot >= CAST_SLOTS) slot = 0;
            _embL[slot] = JsonNum(data, "l", _embL[slot]);
            _embT[slot] = JsonNum(data, "t", _embT[slot]);
            _embR[slot] = JsonNum(data, "r", _embR[slot]);
            _embB[slot] = JsonNum(data, "b", _embB[slot]);
            // A19：区域退化成零（r<=l 或 b<=t，全屏时其它格发 0 区域）→ 隐藏该 Panel，
            // 而不是摆成 32px 残影浮在全屏画面上。
            if (_embR[slot] - _embL[slot] <= 0.001 || _embB[slot] - _embT[slot] <= 0.001)
            {
                if (_castHost[slot] != null) _castHost[slot].Visible = false;
                return;
            }
            Rectangle cr = ClientRectangle;
            int x = (int)Math.Round(cr.Width * _embL[slot]);
            int y = (int)Math.Round(cr.Height * _embT[slot]);
            int w = Math.Max(32, (int)Math.Round(cr.Width * (_embR[slot] - _embL[slot])));
            int h = Math.Max(32, (int)Math.Round(cr.Height * (_embB[slot] - _embT[slot])));
            _castHost[slot].Bounds = new Rectangle(x, y, w, h);
            _castHost[slot].Visible = true;
            _castHost[slot].BringToFront();
            ResizeEmbedded(slot);
        }

        private static double JsonNum(string json, string key, double dflt)
        {
            if (string.IsNullOrEmpty(json)) return dflt;
            int i = json.IndexOf("\"" + key + "\"", StringComparison.Ordinal);
            if (i < 0) return dflt;
            i = json.IndexOf(':', i);
            if (i < 0) return dflt;
            int j = i + 1;
            while (j < json.Length && (json[j] == ' ' || json[j] == '\t')) j++;
            int k = j;
            while (k < json.Length &&
                   (char.IsDigit(json[k]) || json[k] == '-' || json[k] == '.' || json[k] == 'e' || json[k] == 'E'))
                k++;
            if (k <= j) return dflt;
            double v;
            if (double.TryParse(json.Substring(j, k - j),
                    System.Globalization.NumberStyles.Float,
                    System.Globalization.CultureInfo.InvariantCulture, out v)) return v;
            return dflt;
        }

        private void ScrcpyEmbedStart(string data)
        {
            int slot = (int)JsonNum(data, "slot", 0);
            int id = (int)JsonNum(data, "id", 0);
            if (slot < 0 || slot >= CAST_SLOTS) slot = 0;

            ScrcpyEmbedStop(slot);

            EnsureCastHosts();
            _scRetry[slot] = 0;   // A21：每次用户主动开启都重置重试计数
            // 标题必须唯一：FindWindow 是按标题找的，多个实例同名会认错窗口
            _scTitle[slot] = "AdbToolCast_" + Process.GetCurrentProcess().Id + "_"
                           + Environment.TickCount.ToString();
            _scSlotId[slot] = id;

            string err = "";
            Process p = Scrcpy.LaunchEmbedded(id, _scTitle[slot], out err);
            if (p == null)
            {
                ExecJs("window.v17CastEmbedFail && window.v17CastEmbedFail(" + slot + "," + Json(err) + ")");
                return;
            }
            _scProc[slot] = p;
            _scHwnd[slot] = IntPtr.Zero;

            int tries = 0;
            int cs = slot;
            _scPoll[slot] = new System.Windows.Forms.Timer();
            _scPoll[slot].Interval = 120;
            _scPoll[slot].Tick += delegate
            {
                tries++;
                if (_scHwnd[cs] != IntPtr.Zero)
                {
                    _scPoll[cs].Stop();
                    return;
                }
                // 进程先退出了：设备可能瞬间掉线（无线 adb 常见），先自动重试一次，
                // 重试仍失败才把真实原因带回去、降级到内置通道。
                try
                {
                    if (_scProc[cs] == null || _scProc[cs].HasExited)
                    {
                        _scPoll[cs].Stop();
                        int exitCode = 0;
                        try { exitCode = _scProc[cs].ExitCode; } catch { }
                        string real = Scrcpy.EmbedErr(_scProc[cs] == null ? 0 : _scProc[cs].Id);
                        bool devDisconnect = real.IndexOf("disconnect", StringComparison.OrdinalIgnoreCase) >= 0
                                          || real.IndexOf("no device", StringComparison.OrdinalIgnoreCase) >= 0
                                          || real.IndexOf("not found", StringComparison.OrdinalIgnoreCase) >= 0;

                        // A21 自动重试：设备瞬间掉线是无线 adb 的常态，重试一次往往能救回来。
                        // 只在"设备掉线类"原因下重试（不是配置/版本错误），且每槽最多重试 2 次，
                        // 避免设备彻底拔掉时无限拉起 scrcpy。
                        if (devDisconnect && _scRetry[cs] < 2)
                        {
                            _scRetry[cs]++;
                            App.Trace("scrcpy embed: slot=" + cs + " 设备掉线，自动重试 "
                                      + _scRetry[cs] + "/2（" + real.Trim() + "）");
                            // 复用本次的 slot/id 重新启动，不重新走 ScrcpyEmbedStop 的整条链路
                            string err2 = "";
                            Process p2 = Scrcpy.LaunchEmbedded(_scSlotId[cs], _scTitle[cs], out err2);
                            if (p2 != null)
                            {
                                Scrcpy.ForgetEmbedErr(_scProc[cs] == null ? 0 : _scProc[cs].Id);
                                try { if (_scProc[cs] != null) _scProc[cs].Dispose(); } catch { }
                                _scProc[cs] = p2;
                                _scHwnd[cs] = IntPtr.Zero;
                                tries = 0;
                                _scPoll[cs].Start();   // 继续轮询等新进程的窗口
                                return;
                            }
                        }

                        string why = "scrcpy 启动后退出（退出码 " + exitCode + "）";
                        if (real.Length > 0)
                        {
                            // 把 scrcpy 自己打印的关键原因（如 "Device disconnected"）暴露给用户
                            string first = real;
                            int nl = first.IndexOf('\n');
                            if (nl > 0) first = first.Substring(0, nl);
                            why = "scrcpy 退出：" + first.Trim();
                        }
                        ExecJs("window.v17CastEmbedFail && window.v17CastEmbedFail(" + cs + "," + Json(why) + ")");
                        return;
                    }
                }
                catch { }

                IntPtr h = FindWindow(null, _scTitle[cs]);
                if (h == IntPtr.Zero)
                {
                    // 兜底：有的 scrcpy 版本会改窗口标题（或加后缀），按标题找不到时
                    // 用进程的主窗口句柄。内嵌模式已关掉控制台，所以主窗口就是视频窗。
                    try
                    {
                        if (_scProc[cs] != null) h = _scProc[cs].MainWindowHandle;
                    }
                    catch { }
                }
                if (h != IntPtr.Zero)
                {
                    AttachEmbedded(cs, h);
                    _scPoll[cs].Stop();
                    return;
                }
                // 8 秒还找不到窗口：多半是 scrcpy 版本太老，不认 --window-borderless
                if (tries > 66)
                {
                    _scPoll[cs].Stop();
                    ScrcpyEmbedStop(cs);
                    ExecJs("window.v17CastEmbedFail && window.v17CastEmbedFail(" + cs +
                           ",'没等到 scrcpy 窗口，请升级到 scrcpy 2.x/3.x 以上')");
                }
            };
            _scPoll[slot].Start();
        }

        /// <summary>把 scrcpy 的顶层窗口变成宿主 Panel 的子窗口，并去掉系统边框。</summary>
        private void AttachEmbedded(int slot, IntPtr h)
        {
            try
            {
                const int GWL_STYLE = -16;
                const int WS_CHILD = 0x40000000;
                const int WS_VISIBLE = 0x10000000;
                const int WS_CAPTION = 0x00C00000;
                const int WS_THICKFRAME = 0x00040000;
                const int WS_MINIMIZEBOX = 0x00020000;
                const int WS_MAXIMIZEBOX = 0x00010000;
                const int WS_SYSMENU = 0x00080000;

                int style = GetWindowLong(h, GWL_STYLE);
                style &= ~(WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU);
                // WS_POPUP 是 0x80000000，int 上是负数，用 unchecked 才不编译报错
                style &= ~unchecked((int)0x80000000);
                style |= WS_CHILD | WS_VISIBLE;
                SetWindowLong(h, GWL_STYLE, style);

                SetParent(h, _castHost[slot].Handle);
                _scHwnd[slot] = h;
                // A19（修复投屏默认全屏）：不要在这里立刻 Visible=true。
                // 此时 _embL/R/T/B 还是 0（EnsureCastHosts 初始化为零），若直接显示，
                // Panel 会以默认/错误坐标浮在窗口上（用户看到的"默认全屏"）。
                // 改为：仅当已收到页面 castembedrect 报来的有效小屏坐标时才显示，
                // 否则保持隐藏，等页面 v17CastEmbed 的 syncSlot 报到正确坐标后，
                // ScrcpyEmbedPlace 会自然把它 Visible=true 并摆到格子位置。
                if (_embR[slot] - _embL[slot] > 0.001 && _embB[slot] - _embT[slot] > 0.001)
                {
                    ScrcpyEmbedPlace("{\"slot\":" + slot + "}");
                }
                else
                {
                    _castHost[slot].Visible = false;
                }
                ResizeEmbedded(slot);
                ExecJs("window.v17CastEmbedReady && window.v17CastEmbedReady(" + slot + ")");
                App.Trace("scrcpy embed: slot=" + slot + " display=" + _scSlotId[slot]
                          + " 已接管 hwnd=" + h.ToString());
            }
            catch (Exception ex)
            {
                App.Trace("scrcpy embed: 接管失败 " + ex.Message);
            }
        }

        private void ScrcpyEmbedStop(int slot)
        {
            if (slot < 0 || slot >= CAST_SLOTS) return;
            try { if (_scPoll[slot] != null) { _scPoll[slot].Stop(); _scPoll[slot].Dispose(); _scPoll[slot] = null; } } catch { }
            try
            {
                if (_scHwnd[slot] != IntPtr.Zero)
                {
                    SetParent(_scHwnd[slot], IntPtr.Zero);
                    _scHwnd[slot] = IntPtr.Zero;
                }
            }
            catch { }
            try
            {
                if (_scProc[slot] != null && !_scProc[slot].HasExited) _scProc[slot].Kill();
            }
            catch { }
            try { if (_scProc[slot] != null) Scrcpy.ForgetEmbedErr(_scProc[slot].Id); } catch { }
            try { if (_scProc[slot] != null) _scProc[slot].Dispose(); } catch { }
            _scProc[slot] = null;
            try { if (_castHost[slot] != null) _castHost[slot].Visible = false; } catch { }
        }

        private void ScrcpyEmbedStopAll()
        {
            if (_castHost == null) return;
            for (int i = 0; i < CAST_SLOTS; i++) ScrcpyEmbedStop(i);
        }

        private void ScrcpyEmbedHideAll()
        {
            if (_castHost == null) return;
            for (int i = 0; i < CAST_SLOTS; i++)
                try { if (_castHost[i] != null) _castHost[i].Visible = false; } catch { }
        }

        // ---------------- 关闭清理 ----------------

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            _closing = true;          // A17：任何关闭路径都置位，避免重复进清理
            // A18：内嵌的 scrcpy 是外部进程，不主动杀会留在后台继续推流（每格一个）
            try { ScrcpyEmbedStopAll(); } catch { }
            try { _tick.Stop(); } catch { }

            // 【需求6】停掉 track-devices 监听线程。
            // IsBackground=true 保证进程能退出，但显式 Stop 能让 socket
            // 尽快释放，避免关窗瞬间还在跑的重连把状态写脏。
            try { App.DeviceWatcher.Stop(); } catch { }
            // 2026-11-15 闪退修复：关窗时显式停掉所有投屏采集线程与 adb 子进程，
            // 否则 CastLoop 可能赶在进程退出前又拉起一个 screencap（僵尸 adb 堆积）。
            try { App.CastStopAll(); } catch { }
            // 2026-11-17 O7：这里原来调 _worker[i].Abort()，换成协作式取消。
            //
            // 为什么必须换：ThreadAbortException 会被注入到**任意指令点**，
            // 可能正好在持锁、写文件、或 adb 的同步读中间 —— 现场表现是
            // 偶发 gui_error.log 里出现半截堆栈、或 ini 被写坏半行。
            // 而且 Abort 在 .NET Framework 上并不保证线程真的退出，
            // 真要停得住还得靠 Join / 看门狗，等于多背一层不确定性。
            //
            // 现在的顺序（和 StopWorker 完全一致，不另造机制）：
            //   ① 置本槽停止标记 + 杀掉本槽 adb 子进程（阻塞在 ReadLine 上的
            //      线程会立刻拿到 EOF 返回，这是能真正"叫醒"它的东西）
            //   ② 置 GUISTOP（纯 sleep 轮询的长等待命令靠它退出）
            //   ③ 给全部 worker 一个总预算 1.2s 体面退出（Join）
            //   ④ 超预算的不再硬杀 —— 它们都是 IsBackground=true，
            //      进程退出时随 CLR 一起收掉；winclose 路径另有 2.5s 看门狗兜底
            try
            {
                for (int i = 0; i < MAX_SLOT; i++)
                {
                    _stopRequested[i] = true;
                    try { App.KillRunning(i); } catch { }
                }
                App.GUISTOP = true;

                int budget = 1200;
                for (int i = 0; i < MAX_SLOT && budget > 0; i++)
                {
                    Thread th = _worker[i];
                    if (th == null || !th.IsAlive) continue;
                    long t0 = Environment.TickCount;
                    try { th.Join(budget); } catch { }
                    budget -= (int)(Environment.TickCount - t0);
                }
            }
            catch { }

            try
            {
                using (System.IO.StreamWriter so = new System.IO.StreamWriter(Console.OpenStandardOutput(), Encoding.UTF8))
                {
                    so.AutoFlush = true;
                    Console.SetOut(so);
                }
                App.GUI_COLOR_HOOK = null;
            }
            catch { }

            base.OnFormClosing(e);
        }
    }
}
