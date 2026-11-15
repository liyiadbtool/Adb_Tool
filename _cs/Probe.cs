using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Threading;

namespace AdbLogExport
{
    // =========================================================================
    //  Bg —— 后台 adb 探测线程
    //
    //  为什么需要它（这是"息屏再亮屏后敲字不上屏、只能重开工具"的根因）：
    //
    //    息屏往往伴随系统挂起（Modern Standby / S0ix），USB 设备会被挂起甚至
    //    重新枚举。唤醒后 adb server 里握着的还是旧句柄，`adb devices` 会一直
    //    卡在 USB 传输层等下去。
    //
    //    旧代码把这个调用放在**输入线程**的空闲钩子里，而且 AdbCall 没有超时：
    //
    //        Console.KeyAvailable -> IdleHook -> AdbCall("devices") -> ReadToEnd()
    //                                                                   ↑ 卡死在这里
    //
    //    一卡住，ReadKey 再也执行不到，用户敲的字符只是堆在控制台输入缓冲区里，
    //    既不上屏也不执行 —— 表现就是"工具不可用"。杀掉重开相当于换了个新的
    //    adb 客户端，所以"重开就好"。
    //
    //  这里把探测整体搬到独立线程，UI 线程只做两件事：
    //      · Request()  发个信号"待会有空去看一眼设备"
    //      · TryTake()  取结果，**永远不阻塞**
    //  仍然由 UI 线程解析结果、改全局状态，避免多线程抢 DEVN/DEVID。
    // =========================================================================
    internal static partial class App
    {
        internal static class Bg
        {
            internal static int PROBE_TIMEOUT_MS = 4000;   // 单次 devices 探测上限（ini probe_ms）
            private const int LOOP_MS = 80;
            private const long WAKE_GAP_MS = 3000;        // Sleep(80) 花掉 3 秒 = 刚才睡过

            internal const int KIND_PROBE = 1;
            internal const int KIND_RECOVER = 2;

            private static readonly object _lk = new object();
            private static Thread _th;
            private static bool _started;

            private static int _want;            // 0=空闲 1=探测 2=恢复服务
            private static volatile bool _busy;
            private static string _text;         // null 表示没有新结果
            private static int _rc;
            private static int _kind;
            private static volatile bool _wake;

            internal static void Start()
            {
                lock (_lk)
                {
                    if (_started) return;
                    _started = true;
                }
                _th = new Thread(new ThreadStart(Loop));
                _th.IsBackground = true;
                _th.Name = "syn-bg-probe";
                _th.Start();
            }

            internal static bool Busy
            {
                get { return _busy; }
            }

            // 请求一次 devices 探测（已有请求就不重复排队）
            internal static void Request()
            {
                lock (_lk)
                {
                    if (_want == 0) _want = KIND_PROBE;
                }
            }

            // 请求恢复 adb 服务（kill-server / taskkill / start-server）
            internal static void RequestRecover()
            {
                lock (_lk) { _want = KIND_RECOVER; }
            }

            // 是否检测到"刚睡了一觉"
            internal static bool TakeWake()
            {
                if (!_wake) return false;
                _wake = false;
                return true;
            }

            internal static bool TryTake(out string text, out int rc, out int kind)
            {
                lock (_lk)
                {
                    if (_text == null)
                    {
                        text = null;
                        rc = 0;
                        kind = 0;
                        return false;
                    }
                    text = _text;
                    rc = _rc;
                    kind = _kind;
                    _text = null;
                    _rc = 0;
                    _kind = 0;
                    return true;
                }
            }

            private static void Loop()
            {
                long prev = Environment.TickCount;

                while (true)
                {
                    try { Thread.Sleep(LOOP_MS); }
                    catch { }

                    long now = Environment.TickCount;
                    long gap = now - prev;
                    prev = now;
                    if (gap > WAKE_GAP_MS) _wake = true;

                    int job;
                    lock (_lk)
                    {
                        job = _want;
                        _want = 0;
                        if (job != 0) _busy = true;
                    }
                    if (job == 0) continue;

                    string o = "";
                    string e = "";
                    int rc = -1;
                    try
                    {
                        if (job == KIND_PROBE)
                        {
                            rc = AdbProbe(out o, out e);
                        }
                        else
                        {
                            rc = RecoverServer(out o, out e);
                            e = "";
                        }
                    }
                    catch (Exception ex)
                    {
                        o = "";
                        e = ex.Message;
                        rc = -1;
                    }

                    lock (_lk)
                    {
                        _text = MergeStream(o, e);
                        _rc = rc;
                        _kind = job;
                        _busy = false;
                    }
                }
            }
        }
    }

    // =========================================================================
    //  Clip —— 读剪贴板
    //
    //  为什么要自己读：conhost 的 Ctrl+V 粘贴只在"行输入"（ReadConsole）模式
    //  下由主机代劳；本工具是裸读键（ReadKey + KeyAvailable），这个便利拿不到。
    //  右键粘贴（QuickEdit）主机是会直接塞字符进来的，但 Ctrl+V 是肌肉记忆，
    //  自己实现一份更稳，也不受"控制台属性"影响。
    // =========================================================================
    internal static class WinClip
    {
        private const uint CF_UNICODETEXT = 13;

        [DllImport("user32.dll", SetLastError = true)]
        private static extern bool OpenClipboard(IntPtr hWndNewOwner);

        [DllImport("user32.dll", SetLastError = true)]
        private static extern bool CloseClipboard();

        [DllImport("user32.dll", SetLastError = true)]
        private static extern IntPtr GetClipboardData(uint uFormat);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern IntPtr GlobalLock(IntPtr hMem);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool GlobalUnlock(IntPtr hMem);

        // 拿不到就返回空串（别的程序正占着剪贴板时很常见，重试两次足够）
        internal static string GetText()
        {
            for (int i = 0; i < 3; i++)
            {
                try
                {
                    if (OpenClipboard(IntPtr.Zero))
                    {
                        try
                        {
                            IntPtr h = GetClipboardData(CF_UNICODETEXT);
                            if (h == IntPtr.Zero) return "";

                            IntPtr p = GlobalLock(h);
                            if (p == IntPtr.Zero) return "";
                            try { return Marshal.PtrToStringUni(p) ?? ""; }
                            finally { GlobalUnlock(h); }
                        }
                        finally { CloseClipboard(); }
                    }
                }
                catch { }

                System.Threading.Thread.Sleep(20);
            }
            return "";
        }
    }

    // =========================================================================
    //  ConsoleUtil —— 控制台模式管理
    //
    //  v7.12 修正：上一版为了躲"误点鼠标就假死"，把 QuickEdit 整个关掉了，
    //  结果把控制台自带的三个鼠标能力也一起关掉了：
    //      · 滚轮上滑看历史输出      → 关掉 QuickEdit 后 conhost 不再接管滚轮
    //      · 拖选文字 + 右键复制     → 选择模式本身就属于 QuickEdit
    //      · 右键粘贴 / Ctrl+V       → 同上，都是 conhost 的 QuickEdit 提供
    //  等于"用一种残疾换另一种残疾"，得不偿失。
    //
    //  现在改回：**默认打开 QuickEdit**（ini 里 quick_edit=0 可关）。
    //  "选择时键盘暂时不进程序"这个副作用用另外两个办法消化：
    //      · 选择进行中不打印任何东西（Program.IdleTick 先查 SelectionInProgress），
    //        免得把用户正在选的那段文字冲乱；
    //      · 选择结束后 conhost 自动把键盘还回来，不需要重开程序。
    //  真正会"永久假死"的 adb 无超时问题，已经在 v7.11 用 Probe.cs + 超时修掉了。
    // =========================================================================
    internal static class ConsoleUtil
    {
        private const int STD_INPUT_HANDLE = -10;
        private const uint ENABLE_QUICK_EDIT_MODE = 0x0040;
        private const uint ENABLE_EXTENDED_FLAGS = 0x0080;

        // 选择进行中（QuickEdit 拖选/按住鼠标）：此时键盘事件被 conhost 拦着，
        // 程序读不到键。用来判断"要不要暂停输出"，不是用来判断死活的。
        private const uint CONSOLE_SELECTION_IN_PROGRESS = 0x0001;

        [StructLayout(LayoutKind.Sequential)]
        private struct COORD
        {
            public short X;
            public short Y;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct SMALL_RECT
        {
            public short Left;
            public short Top;
            public short Right;
            public short Bottom;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct CONSOLE_SELECTION_INFO
        {
            public uint dwFlags;
            public COORD dwSelectionAnchor;
            public SMALL_RECT srSelection;
        }

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern IntPtr GetStdHandle(int nStdHandle);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool GetConsoleMode(IntPtr hConsoleHandle, out uint lpMode);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool SetConsoleMode(IntPtr hConsoleHandle, uint dwMode);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool FlushConsoleInputBuffer(IntPtr hConsoleInput);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool GetConsoleSelectionInfo(out CONSOLE_SELECTION_INFO lpConsoleSelectionInfo);

        internal static bool Ready = false;

        // 是否允许鼠标选中/复制/右键粘贴（ini quick_edit，默认 1）
        internal static bool QuickEdit = true;

        internal static void Init()
        {
            Apply(false);
        }

        // 唤醒/异常后用：重新落模式并清空输入缓冲
        internal static void Recover()
        {
            Apply(true);
        }

        // ini 里改了 quick_edit 之后重新落一次
        internal static void Refresh()
        {
            Apply(false);
        }

        // 用户是不是正在拖选/选好了文字还没松手。
        // Win10 1809+ 才有这个 API，取不到就当作"没在选择"，不影响主流程。
        private static int _selSupported = 1;      // 老系统没这个导出函数，失败一次就别再试

        internal static bool SelectionInProgress()
        {
            if (_selSupported == 0) return false;
            try
            {
                CONSOLE_SELECTION_INFO si;
                if (!GetConsoleSelectionInfo(out si)) return false;
                return (si.dwFlags & CONSOLE_SELECTION_IN_PROGRESS) != 0;
            }
            catch
            {
                _selSupported = 0;                  // Win10 1809 之前 / 精简系统
                return false;
            }
        }

        private static void Apply(bool flush)
        {
            try
            {
                IntPtr hIn = GetStdHandle(STD_INPUT_HANDLE);
                uint mode;
                if (hIn != IntPtr.Zero && GetConsoleMode(hIn, out mode))
                {
                    // 必须在 ENABLE_EXTENDED_FLAGS 下改 QuickEdit，否则这个位会被忽略
                    uint m = mode | ENABLE_EXTENDED_FLAGS;
                    if (QuickEdit) m = m | ENABLE_QUICK_EDIT_MODE;
                    else m = m & ~ENABLE_QUICK_EDIT_MODE;

                    if (m != mode) SetConsoleMode(hIn, m);
                    Ready = true;
                }
                else
                {
                    Ready = false;      // 输入被重定向（管道/文件），不用管
                }

                if (flush && hIn != IntPtr.Zero) FlushConsoleInputBuffer(hIn);
            }
            catch
            {
                Ready = false;
            }
        }

        // 当前是否真的开着 QuickEdit（ini 被改坏时用它兜底）
        internal static bool QuickEditActive()
        {
            try
            {
                IntPtr hIn = GetStdHandle(STD_INPUT_HANDLE);
                uint mode;
                if (hIn == IntPtr.Zero || !GetConsoleMode(hIn, out mode)) return false;
                return (mode & ENABLE_QUICK_EDIT_MODE) != 0;
            }
            catch { return false; }
        }

        // 句柄是否还活着：窗口被关掉/控制台重建后这里会抛
        internal static bool Healthy()
        {
            try
            {
                return Console.WindowWidth > 0 && Console.WindowHeight > 0;
            }
            catch
            {
                return false;
            }
        }
    }
}
