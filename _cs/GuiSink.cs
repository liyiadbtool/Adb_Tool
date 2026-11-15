// ============================================================================
//  GuiSink.cs - 控制台输出捕获
//
//  设计要点：
//    现有工具 379 处 Console.Write / WriteLine 分散在 12 个文件里，改写它们
//    风险高、收益低。这里用 TextWriter 子类接管 Console.Out / Error，把字符流
//    切行后抛给 GUI 线程。命令行行为完全不变 —— 只是"屏幕"换成了文本框。
//
//  颜色怎么来的：
//    原代码靠 Console.ForegroundColor（静态属性，TextWriter 拦不到 setter）。
//    但全部着色都经过 Render.Use(ConsoleColor) 这一个函数，于是在那里挂了
//    GUI_COLOR_HOOK —— 每次设色时同步告诉我们。切行时带上颜色，GUI 侧上色。
//    一行渲染代码都不用改，颜色信息也没丢。
//
//  行内 '\r' 的处理：
//    等待指示器（Adb.cs WaitHintStart）先写 " ..." 再擦除，中间夹 '\r'。
//    这种"同行动画"不能进日志，否则输出区里全是孤立的点。这里直接丢弃。
// ============================================================================
using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Text;

namespace AdbLogExport.Gui
{
    // 一行输出：文本 + 颜色 + 语义级别 + 来源槽位
    internal sealed class GuiLine
    {
        public string Text;
        public Color Fore;
        public int Level;      // 0=普通 1=成功 2=失败 3=警告 4=弱化 5=路径
        public int Slot;       // 需求1：来源输入框槽位（0/1/2），并行命令输出分流用

        public GuiLine(string text, Color fore, int level, int slot = 0)
        {
            Text = text;
            Fore = fore;
            Level = level;
            Slot = slot;
        }
    }

    internal sealed class GuiSink : TextWriter
    {
        private readonly Queue<GuiLine> _q = new Queue<GuiLine>();
        private readonly object _lk = new object();

        // 队列上限。生产端（adb 输出）一旦快于消费端（50ms 取一批），
        // 无上限就是一直堆到内存耗尽 —— `logcat -f`、大目录 pull 都很容易触发。
        // 超限时丢最早的并计数，下一次推送时告诉用户"丢了 N 行"，
        // 沉默截断比丢行更糟（用户会以为设备没输出）。
        private const int QUEUE_MAX = 50000;
        private int _dropped = 0;

        // 队列由空变非空时回调：GUI 用它在"有活干"的瞬间把定时器提速，
        // 这样空闲时不必维持 20 次/秒的唤醒。
        internal Action OnFirstLine;

        // 需求1（并行多命令）：下面的行装配状态改成 [ThreadStatic]，
        // 让每个 worker 线程各持一份行缓冲/颜色/状态机，并行写 Console 时
        // 不会互相串行内容或颜色。队列 _q 与锁 _lk 保持实例字段（共享、加锁）。
        [ThreadStatic] private static StringBuilder _cur;

        // 当前生效的颜色 / 级别（由 Install 挂钩后持续更新）
        [ThreadStatic] private static Color _curColor;
        [ThreadStatic] private static int _curLevel;

        // 输出行归属的槽位覆盖值。
        // 为什么需要：App.CUR_SLOT 是 [ThreadStatic]，只对 worker 线程有效；而
        // adb 的 OutputDataReceived 回调跑在 ThreadPool 线程上，那里的 CUR_SLOT
        // 永远是默认值 0 —— 于是 1/2 号槽的流式输出会被打上 0 号标记，显示到第一个
        // 输出区里（并行时表现为"输出串台"）。AdbCallStream 在 worker 线程上捕获
        // 真实槽位后，写 Console 前用 SlotHint 显式指定，这里优先采用它。
        [ThreadStatic] internal static int SlotHint = -1;

        // 丢弃"同行动画"残片
        [ThreadStatic] private static bool _dropAnim;
        [ThreadStatic] private static bool _pendingCr;   // 收到 '\r'，等下一个字符判定是 CRLF 还是动画

        public override Encoding Encoding { get { return Encoding.UTF8; } }

        // 需求1：[ThreadStatic] 的行缓冲每线程默认 null，这里按需惰性初始化。
        private static StringBuilder Cur
        {
            get
            {
                if (_cur == null) _cur = new StringBuilder();
                return _cur;
            }
        }

        internal int Pending
        {
            get { lock (_lk) { return _q.Count; } }
        }

        // ---------------- 颜色同步 ----------------

        // 由 Render.Use() 调用：把 ConsoleColor 翻成 RGB，并推断语义级别
        internal void SyncColor(ConsoleColor c)
        {
            _curColor = ToRgb(c);
            _curLevel = ToLevel(c);
        }

        private static int ToLevel(ConsoleColor c)
        {
            switch (c)
            {
                case ConsoleColor.Green: return 1;
                case ConsoleColor.DarkGreen: return 1;
                case ConsoleColor.Red: return 2;
                case ConsoleColor.DarkRed: return 2;
                case ConsoleColor.Yellow: return 3;
                case ConsoleColor.DarkYellow: return 3;
                case ConsoleColor.Cyan: return 5;
                case ConsoleColor.DarkCyan: return 5;
                case ConsoleColor.Gray: return 4;
                case ConsoleColor.DarkGray: return 4;
                default: return 0;
            }
        }

        private static Color ToRgb(ConsoleColor c)
        {
            switch (c)
            {
                case ConsoleColor.Black: return Color.FromArgb(30, 30, 30);
                case ConsoleColor.DarkBlue: return Color.FromArgb(0, 55, 218);
                case ConsoleColor.DarkGreen: return Color.FromArgb(16, 124, 16);
                case ConsoleColor.DarkCyan: return Color.FromArgb(0, 108, 108);
                case ConsoleColor.DarkRed: return Color.FromArgb(168, 0, 0);
                case ConsoleColor.DarkMagenta: return Color.FromArgb(136, 23, 152);
                case ConsoleColor.DarkYellow: return Color.FromArgb(160, 96, 0);
                case ConsoleColor.Gray: return Color.FromArgb(96, 96, 96);
                case ConsoleColor.DarkGray: return Color.FromArgb(128, 128, 128);
                case ConsoleColor.Blue: return Color.FromArgb(0, 90, 200);
                case ConsoleColor.Green: return Color.FromArgb(16, 124, 16);
                case ConsoleColor.Cyan: return Color.FromArgb(0, 120, 130);
                case ConsoleColor.Red: return Color.FromArgb(196, 20, 20);
                case ConsoleColor.Magenta: return Color.FromArgb(168, 30, 180);
                case ConsoleColor.Yellow: return Color.FromArgb(180, 120, 0);
                case ConsoleColor.White: return Color.FromArgb(20, 20, 20);
                default: return Color.Empty;
            }
        }

        // ---------------- TextWriter 重载 ----------------
        //
        // 逐个字符走同一个 Feed()：Write(char) 和 Write(string) 必须是同一套语义，
        // 否则"分块写"和"逐字写"出来不一样，这本身就是个 bug 源。

        public override void Write(char c) { Feed(c); }

        public override void Write(string s)
        {
            if (string.IsNullOrEmpty(s)) return;
            // 快路径：整段不含换行/回车，且不在"动画残片"状态里，直接进缓冲。
            // 原来无论多大一段都逐字符走状态机，大目录 ls / 批量日志时
            // 上百万次虚调用全是纯开销。含换行时仍走状态机（CRLF、动画都要判）。
            if (!_pendingCr && !_dropAnim
                && s.IndexOf('\r') < 0 && s.IndexOf('\n') < 0)
            {
                Cur.Append(s);
                return;
            }
            for (int i = 0; i < s.Length; i++) Feed(s[i]);
        }

        public override void WriteLine(string s) { Write(s); FlushLine(); }
        public override void WriteLine() { FlushLine(); }

        // ---------------- 字符状态机 ----------------
        //
        // 这里唯一容易搞错的是 '\r' 的两种含义，必须靠**向后看一个字符**区分：
        //   · "\r\n"  —— 普通换行（Console.WriteLine / 文本文件行尾）
        //   · "\r..." —— 回车重写，即 Adb.cs 的等待动画（先写 " ..." 再擦）
        // 早期版本把 '\r' 一律当成动画起点，后果有两个：
        //   1) CRLF 里的 '\r' 会置上丢弃标志，而 '\n' 只管换行不清标志，
        //      于是下一行开头的缩进空格被当成动画残片吃掉 —— 缩进没了；
        //   2) 若一行以 "\r\n" 结尾且后接 " ..."，真实内容会被误吞。
        // 现在 '\r' 先进 _pendingCr 悬置，看到下一个字符才能定性。
        private void Feed(char c)
        {
            if (_pendingCr)
            {
                _pendingCr = false;
                if (c == '\n') { FlushLine(); return; }   // CRLF：就是换行，不是动画
                _dropAnim = true;                          // 后面跟的不是换行 -> 动画
            }

            if (c == '\n') { FlushLine(); return; }
            if (c == '\r') { _pendingCr = true; return; }

            if (_dropAnim)
            {
                if (c == ' ' || c == '.') return;          // 动画残片，丢掉
                _dropAnim = false;
            }
            Cur.Append(c);
        }

        // ---------------- 行装配 ----------------

        private void FlushLine()
        {
            string text = Cur.ToString();
            Cur.Length = 0;
            int slot = (SlotHint >= 0) ? SlotHint : App.CUR_SLOT;
            bool first = false;
            lock (_lk)
            {
                if (_q.Count == 0) first = true;
                // 超限丢最早的行，保证内存有界；丢弃数在下次 Drain 时上报
                while (_q.Count >= QUEUE_MAX) { _q.Dequeue(); _dropped++; }
                _q.Enqueue(new GuiLine(text, _curColor, _curLevel, slot));
            }
            // 回调放在锁外：GUI 侧会 BeginInvoke 到 UI 线程，锁内调用容易互相等
            if (first && OnFirstLine != null)
            {
                try { OnFirstLine(); } catch { }
            }
        }

        // GUI 定时器调用：把队列交给 UI（一次最多 200 行，避免一次性塞太多卡界面）
        internal int Drain(Action<GuiLine> onLine)
        {
            return Drain(onLine, 200);
        }

        // max < 0 表示不限量。--exec 这类"跑完就退出"的场景必须不限量：
        // 一次 ls 大目录轻松超 200 行，若沿用定时器的节流上限，
        // 后面的行还没取出来进程就退出了 —— 输出被静默截断。
        internal int Drain(Action<GuiLine> onLine, int max)
        {
            int n = 0;
            while (max < 0 || n < max)
            {
                GuiLine l;
                lock (_lk)
                {
                    if (_q.Count == 0) break;
                    l = _q.Dequeue();
                }
                if (onLine != null) onLine(l);
                n++;
            }
            return n;
        }

        // 批量取行：一次加锁把最多 max 行搬进 dest。
        // 原来 Drain 每取一行加一次锁（200 行 = 200 次 lock），而取出来的行
        // 最终还是被同一个循环逐条处理 —— 锁粒度过细，纯开销。
        internal int DrainTo(List<GuiLine> dest, int max)
        {
            if (dest == null) return 0;
            int n = 0;
            lock (_lk)
            {
                while ((max < 0 || n < max) && _q.Count > 0)
                {
                    dest.Add(_q.Dequeue());
                    n++;
                }
            }
            return n;
        }

        // 取走并清零"因超限被丢弃"的行数，让 GUI 能明确告诉用户发生过截断
        internal int TakeDropped()
        {
            lock (_lk) { int d = _dropped; _dropped = 0; return d; }
        }

        internal void Clear()
        {
            lock (_lk) { _q.Clear(); _dropped = 0; }
            Cur.Length = 0;
        }
    }
}
