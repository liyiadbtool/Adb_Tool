// ============================================================================
//  LineEdit.cs — 行编辑：方向键历史、左右移动、Home/End、Ctrl+C、Tab 补全
//  仅在交互式终端（stdin 是控制台）时启用；重定向输入时退化为 Console.ReadLine
//
//  v6.5 关键修复（长命令刷屏）：
//   旧实现的 RedrawLine 只用 '\r' 回行首。命令超过窗口宽度后终端会折行，
//   '\r' 只回到【当前物理行】行首，于是每按一个键就把"提示符+命令"再打一遍，
//   屏幕上堆出一长串重复的提示符。
//
//   现在分两条路径：
//     · 行尾打字 / 行尾退格  -> 增量输出（\b 或直接写字符），完全不重绘
//     · 中间编辑 / 历史 / Delete -> 完整重绘，且用 SetCursorPosition 按逻辑行数回退
// ============================================================================
using System;
using System.Collections.Generic;
using System.Text;

namespace AdbLogExport
{
    internal static partial class App
    {
        // 读取一行。返回 null 表示输入结束（EOF）。
        //
        // 两条路径：
        //   · 编辑模式（默认）：ReadKey 循环，支持方向键 / Tab / 历史
        //   · 中文模式（:ime on）：Console.ReadLine，输入法可用
        //
        // 为什么必须二选一：ReadKey 是直接读控制台输入记录，**绕过了输入法的
        // 组字流程**，所以中文输入法在这条路径上敲拼音只会出字母，永远上不了屏。
        // Console.ReadLine 走 ReadConsole，输入法能正常挂上去，代价是拿不到方向键。
        // 这是 Windows 控制台的固有限制，不是能两全的东西。
        internal static string Read(string prompt)
        {
            bool interactive = false;
            try { interactive = !Console.IsInputRedirected; }
            catch { interactive = false; }

            if (!interactive || IME_ACTIVE)
            {
                DrawPrompt(prompt);

                string l = null;
                try { l = Console.ReadLine(); }
                catch { l = null; }
                EndInput();

                // 一次性模式：读完这一行立刻回编辑模式
                if (INPUT_MODE == 2) INPUT_MODE = 0;

                if (l == null)
                {
                    // Ctrl+C 打断 ReadLine 时也会返回 null。
                    // 交互式环境下把它当"取消本行"，只有真 EOF 才返回 null。
                    if (interactive && CTRL_C_PRESSED)
                    {
                        CTRL_C_PRESSED = false;
                        Console.WriteLine("^C");
                        return "";
                    }
                    return null;
                }

                CTRL_C_PRESSED = false;
                return l;
            }

            return InteractiveRead(prompt);
        }

        // 上次绘制内容的显示宽度（含 prompt），用于跨行重绘时回退正确行数
        private static int LAST_DRAWN = 0;

        // 控制台异常只提示一次，避免每 300ms 刷一行
        private static bool CONSOLE_WARNED = false;

        // 安全读键：控制台句柄失效（休眠唤醒 / 快速编辑抓取 / 窗口被重建）时
        // ReadKey 会抛异常，旧版直接把程序带走或卡在等待里。这里改成"修一下继续"。
        private static bool ReadKeySafe(string prompt, ref int promptW, out ConsoleKeyInfo k)
        {
            k = new ConsoleKeyInfo();
            try
            {
                k = Console.ReadKey(true);
                if (CONSOLE_WARNED) CONSOLE_WARNED = false;   // 恢复了，下次还能再提示
                return true;
            }
            catch (Exception)
            {
                ConsoleUtil.Recover();
                try
                {
                    Console.WriteLine();
                    if (ConsoleUtil.Healthy())
                        Warn("控制台输入已重置（刚才那一行已清空），请重新输入");
                    else
                        Warn("控制台句柄已失效，请关闭本窗口重新打开（Windows 控制台限制）");
                    DrawPrompt(prompt);
                    LAST_DRAWN = promptW;
                }
                catch { }
                return false;
            }
        }

        private static int SafeWidth()
        {
            try
            {
                int w = Console.WindowWidth;
                if (w >= 20) return w;
            }
            catch { }
            return 100;
        }

        private static string InteractiveRead(string prompt)
        {
            // 读键期间把 Ctrl+C 变成普通按键：这样它只会"清空当前行"，
            // 而不会触发 CancelKeyPress 让程序退出。
            // 读取结束（进入 adb 操作）后恢复，长任务仍可用 Ctrl+C 中断子进程。
            bool oldTreat = false;
            try { oldTreat = Console.TreatControlCAsInput; Console.TreatControlCAsInput = true; }
            catch { }

            try
            {
                return InteractiveReadCore(prompt);
            }
            finally
            {
                try { Console.TreatControlCAsInput = oldTreat; } catch { }
            }
        }

        // ==================== 输入着色 ====================
        // 提示符用路径色、用户输入用最亮色、程序输出用默认灰：
        // 一屏里"我敲的"和"机器说的"靠亮度就能分开，不必再靠位置猜。
        // 着色只改颜色不改字符宽度，所以所有光标/行数计算都不受影响。
        private static void DrawPrompt(string prompt)
        {
            try
            {
                // 提示符分三段着色（v7.14）：
                //   设备号 -> 黄（和状态栏的 DEVID 同色，扫一眼就对上是哪台车机）
                //   目录   -> 青
                //   " > "  -> 灰（视觉上把"我在哪"和"在这里输入"分开）
                // 只改颜色不改字符，宽度与光标计算不受任何影响。
                //
                // 分段位置由 Prompt() 算好放在 PROMPT_DEV_AT / PROMPT_DIR_AT，
                // 但如果传进来的 prompt 不是刚算的那一个（例如 IdleHook 重画），
                // 就退回整段单色，绝不按错位的下标去切字符串。
                bool segmented = PROMPT_DEV_AT >= 0 && PromptMatches(prompt);

                if (segmented)
                {
                    int n = prompt.Length;
                    int i = 0;
                    while (i < n)
                    {
                        if (PROMPT_DEV_AT == i && PROMPT_DEV_LEN > 0)
                        {
                            UseWarn();
                            Console.Write(prompt.Substring(i, PROMPT_DEV_LEN));
                            i += PROMPT_DEV_LEN;
                        }
                        else if (PROMPT_DIR_AT == i && PROMPT_DIR_LEN > 0)
                        {
                            UsePath();
                            Console.Write(prompt.Substring(i, PROMPT_DIR_LEN));
                            i += PROMPT_DIR_LEN;
                        }
                        else if (i == n - 2 && prompt[i] == '>')
                        {
                            // 末尾的 "> "
                            UseDim();
                            Console.Write(prompt.Substring(i));
                            i = n;
                        }
                        else
                        {
                            int next = n - 2;
                            if (PROMPT_DEV_AT > i && PROMPT_DEV_AT < next) next = PROMPT_DEV_AT;
                            if (PROMPT_DIR_AT > i && PROMPT_DIR_AT < next) next = PROMPT_DIR_AT;
                            if (next <= i) next = n;
                            UsePrompt();
                            Console.Write(prompt.Substring(i, next - i));
                            i = next;
                        }
                    }
                }
                else
                {
                    // 路径用青色、末尾的 "> " 压灰：视觉上把"我在哪"和"在这里输入"分开，
                    // 光标落在最亮的输入色上，一眼知道下一个字符会出现在哪。
                    int i = prompt.LastIndexOf('>');
                    if (i >= 0)
                    {
                        UsePrompt();
                        Console.Write(prompt.Substring(0, i));
                        UseDim();
                        Console.Write(prompt.Substring(i));
                    }
                    else
                    {
                        UsePrompt();
                        Console.Write(prompt);
                    }
                }
            }
            catch { }
            UseInput();
        }

        // 传进来的提示符是否就是 Prompt() 刚生成的那个（防止拿旧下标切新串）
        private static bool PromptMatches(string prompt)
        {
            if (string.IsNullOrEmpty(prompt)) return false;
            if (PROMPT_DEV_LEN <= 0 && PROMPT_DIR_LEN <= 0) return false;
            if (PROMPT_DEV_AT + PROMPT_DEV_LEN > prompt.Length) return false;
            if (PROMPT_DIR_AT >= 0 && PROMPT_DIR_AT + PROMPT_DIR_LEN > prompt.Length) return false;
            if (PROMPT_DIR_AT >= 0 && PROMPT_DIR_AT < PROMPT_DEV_AT) return false;
            return true;
        }

        private static void EndInput()
        {
            UseDefault();
        }

        private static string InteractiveReadCore(string prompt)
        {
            DrawPrompt(prompt);
            StringBuilder buf = new StringBuilder();
            int cur = 0;           // 光标位置（在 buf 中的索引）
            int histIdx = Hist.Count;

            int promptW = DispWidth(prompt);
            LAST_DRAWN = promptW;

            while (true)
            {
                // 空闲等待：不阻塞在 ReadKey 上，这样离线时能定时探测设备是否插上。
                // 只在"缓冲区为空"时给钩子机会 —— 有内容时不打断用户，避免把已输入的
                // 字符和探测输出搅在一起。
                ConsoleKeyInfo k;
                while (true)
                {
                    bool avail = false;
                    bool broken = false;
                    try { avail = Console.KeyAvailable; }
                    catch { broken = true; }

                    if (broken)
                    {
                        // 句柄失效（休眠唤醒 / 窗口重建）：修一下再等，
                        // 不能像旧版那样 avail=true 然后死循环 —— 那会疯狂空转。
                        ConsoleUtil.Recover();
                        if (!CONSOLE_WARNED)
                        {
                            CONSOLE_WARNED = true;
                            try
                            {
                                if (ConsoleUtil.Healthy())
                                    Warn("控制台输入异常，已尝试自动恢复；若仍打不出字，请关闭窗口重开");
                                else
                                    Warn("控制台句柄已失效，请关闭本窗口重新打开（Windows 控制台限制）");
                                DrawPrompt(prompt);
                                LAST_DRAWN = promptW;
                            }
                            catch { }
                        }
                        System.Threading.Thread.Sleep(300);
                        continue;
                    }

                    if (avail) break;

                    if (buf.Length == 0 && IdleHook != null)
                    {
                        string np = null;
                        try { np = IdleHook(prompt); } catch { np = null; }

                        if (np != null)
                        {
                            // 钩子已经把提示符那一行清掉并输出完（以换行结尾）。
                            // 它可能改了 OFFLINE 状态，所以提示符要用它返回的新值。
                            prompt = np;
                            promptW = DispWidth(prompt);
                            DrawPrompt(prompt);
                            LAST_DRAWN = promptW;
                        }
                    }

                    System.Threading.Thread.Sleep(70);
                }

                if (!ReadKeySafe(prompt, ref promptW, out k))
                {
                    // 控制台句柄出过问题，已经重置并重画提示符，这一行重新来
                    buf.Length = 0;
                    cur = 0;
                    continue;
                }

                // Tab：命令名补全（只在光标位于行尾、且还没输入空格时生效）
                if (k.Key == ConsoleKey.Tab)
                {
                    DoTabComplete(prompt, buf, ref cur);
                    continue;
                }

                if (k.Key == ConsoleKey.Enter)
                {
                    EndInput();
                    Console.WriteLine();
                    string result = buf.ToString();
                    if (result.Trim().Length > 0)
                    {
                        Hist.Add(result);
                        if (Hist.Count > 500) Hist.RemoveAt(0);
                    }
                    LAST_DRAWN = 0;
                    return result;
                }

                // Ctrl+C：清空当前行
                if (k.Key == ConsoleKey.C && k.Modifiers.HasFlag(ConsoleModifiers.Control))
                {
                    Console.WriteLine("^C");
                    buf.Length = 0;
                    cur = 0;
                    DrawPrompt(prompt);
                    LAST_DRAWN = promptW;
                    continue;
                }

                // Ctrl+D / Ctrl+Z：输入结束
                if ((k.Key == ConsoleKey.D || k.Key == ConsoleKey.Z) && k.Modifiers.HasFlag(ConsoleModifiers.Control))
                {
                    EndInput();
                    Console.WriteLine();
                    LAST_DRAWN = 0;
                    return null;
                }

                // 方向键历史
                if (k.Key == ConsoleKey.UpArrow)
                {
                    if (histIdx > 0)
                    {
                        histIdx--;
                        ReplaceLine(prompt, buf, ref cur, Hist[histIdx]);
                    }
                    continue;
                }
                if (k.Key == ConsoleKey.DownArrow)
                {
                    if (histIdx < Hist.Count)
                    {
                        histIdx++;
                        if (histIdx < Hist.Count) ReplaceLine(prompt, buf, ref cur, Hist[histIdx]);
                        else { ClearLine(prompt, buf, ref cur); }
                    }
                    continue;
                }

                // 左右移动
                if (k.Key == ConsoleKey.LeftArrow)
                {
                    if (cur > 0)
                    {
                        int wch = CharWidth(buf[cur - 1]);   // 中文要退 2 列
                        cur--;
                        MoveCursorLeft(prompt, buf, cur, wch);
                    }
                    continue;
                }
                if (k.Key == ConsoleKey.RightArrow)
                {
                    if (cur < buf.Length)
                    {
                        int wch = CharWidth(buf[cur]);       // 中文要进 2 列
                        cur++;
                        MoveCursorRight(prompt, buf, cur, wch);
                    }
                    continue;
                }

                // Home / End
                if (k.Key == ConsoleKey.Home)
                {
                    if (cur > 0) { cur = 0; RedrawLine(prompt, buf, cur); }
                    continue;
                }
                if (k.Key == ConsoleKey.End)
                {
                    if (cur < buf.Length) { cur = buf.Length; RedrawLine(prompt, buf, cur); }
                    continue;
                }

                // Backspace：行尾用增量擦除，中间删除才重绘
                // 关键：中文占 2 列，必须擦 2 列。以前固定 \b \b 只擦 1 列，
                // 汉字会剩半个字形在屏幕上，且缓冲区已空 —— 表现就是"删不掉"。
                if (k.Key == ConsoleKey.Backspace)
                {
                    if (cur > 0)
                    {
                        bool atEnd = (cur == buf.Length);
                        int wch = CharWidth(buf[cur - 1]);

                        buf.Remove(cur - 1, 1);
                        cur--;

                        if (atEnd && TryBackspaceColumns(wch))
                        {
                            // 增量搞定：宽度账要同步，否则后续重绘会算错行数
                            LAST_DRAWN -= wch;
                        }
                        else
                        {
                            RedrawLine(prompt, buf, cur);
                        }
                    }
                    continue;
                }

                // Delete：删除光标处字符，必须重绘
                if (k.Key == ConsoleKey.Delete)
                {
                    if (cur < buf.Length)
                    {
                        buf.Remove(cur, 1);
                        RedrawLine(prompt, buf, cur);
                    }
                    continue;
                }

                // Ctrl+V / Shift+Insert：自己读剪贴板插进来。
                // 裸读键模式下 conhost 不会替我们粘贴（它只服务 ReadLine 那条路），
                // 而"复制完按 Ctrl+V"是最基本的预期，必须自己补上。
                if ((k.Key == ConsoleKey.V && k.Modifiers.HasFlag(ConsoleModifiers.Control))
                    || (k.Key == ConsoleKey.Insert && k.Modifiers.HasFlag(ConsoleModifiers.Shift)))
                {
                    PasteClipboard(prompt, buf, ref cur, promptW);
                    continue;
                }

                // 普通字符
                char ch = k.KeyChar;
                if (ch != '\0')
                {
                    bool atEnd = (cur == buf.Length);
                    buf.Insert(cur, ch);
                    cur++;

                    // 行尾追加：直接写一个字符，完全不重绘（这是最常见的路径）
                    if (atEnd)
                    {
                        Console.Write(ch);
                        LAST_DRAWN = promptW + DispWidth(buf.ToString());
                    }
                    else
                    {
                        RedrawLine(prompt, buf, cur);
                    }
                }
            }
        }

        // 把剪贴板内容插到光标处。
        // 只取第一行：本工具是单行编辑，多行硬塞进来会变成"半条命令+一堆换行"，
        // 反而更糟；明确提示"只取了第一行"，不静默丢内容。
        private static void PasteClipboard(string prompt, StringBuilder buf, ref int cur, int promptW)
        {
            string txt = WinClip.GetText();
            if (txt == null || txt.Length == 0)
            {
                return;                       // 剪贴板是空的/被别的程序占着：什么都不做
            }

            txt = txt.Replace("\r\n", "\n").Replace('\r', '\n');

            int nl = txt.IndexOf('\n');
            bool multi = nl >= 0;
            if (multi) txt = txt.Substring(0, nl);

            // 制表符在终端里宽度不定，统一换成 4 个空格，光标账才不会算歪；
            // 其余控制字符（^ 之类）直接丢掉，塞进去只会让行编辑错乱。
            StringBuilder clean = new StringBuilder(txt.Length);
            for (int i = 0; i < txt.Length; i++)
            {
                char c = txt[i];
                if (c == '\t') clean.Append("    ");
                else if (c >= ' ') clean.Append(c);
            }
            txt = clean.ToString();

            if (txt.Length == 0 && !multi) return;

            bool atEnd = (cur == buf.Length);
            buf.Insert(cur, txt);
            cur += txt.Length;

            if (atEnd)
            {
                Console.Write(txt);
                LAST_DRAWN = promptW + DispWidth(buf.ToString());
            }
            else
            {
                RedrawLine(prompt, buf, cur);
            }

            if (multi)
            {
                Console.WriteLine();
                Hint("粘贴内容有多行，只取第一行；其余请逐行粘贴");
                DrawPrompt(prompt);
                LAST_DRAWN = promptW + DispWidth(buf.ToString());
            }
        }

        // 行尾退格：用 "退格 空格 退格" 擦掉一个字符。
        // 光标已经在行首（跨行折返）时返回 false，交给完整重绘处理。
        // 擦掉 w 列（w = 被删字符的显示宽度：英文 1、中文 2）
        private static bool TryBackspaceColumns(int w)
        {
            if (w < 1) w = 1;

            try
            {
                // 需要回退 w 列，跨行时增量做不到（\b 不出本行），交给重绘
                if (Console.CursorLeft < w) return false;

                for (int i = 0; i < w; i++) Console.Write('\b');
                for (int i = 0; i < w; i++) Console.Write(' ');
                for (int i = 0; i < w; i++) Console.Write('\b');
                return true;
            }
            catch { return false; }
        }

        // ==================== 跨行安全的重绘 ====================
        // 先用 LAST_DRAWN 算出"上次内容占了几行"，回到逻辑行首，再整体重画。
        private static void RedrawLine(string prompt, StringBuilder buf, int cur)
        {
            int w = SafeWidth();
            int promptW = DispWidth(prompt);
            string text = buf.ToString();

            int oldRows = (LAST_DRAWN > 0) ? (LAST_DRAWN / w) : 0;

            // 回到逻辑行首
            bool moved = false;
            if (oldRows > 0)
            {
                try
                {
                    int top = Console.CursorTop - oldRows;
                    if (top >= 0)
                    {
                        Console.SetCursorPosition(0, top);
                        moved = true;
                    }
                }
                catch { moved = false; }
            }
            if (!moved) Console.Write('\r');

            // 整行重画（末尾多一个空格，吃掉可能残留的旧字符）
            DrawPrompt(prompt);
            Console.Write(text);
            Console.Write(' ');
            EndInput();

            int newTotal = promptW + DispWidth(text);

            // 清残留：旧内容比新内容长时，用空格覆盖差额（单行内有效）
            int pad = LAST_DRAWN - newTotal;
            if (pad > 0)
            {
                int n = (pad > w - 2) ? (w - 2) : pad;
                for (int i = 0; i < n; i++) Console.Write(' ');
            }

            // 把光标移到 cur 对应的位置
            if (cur < text.Length)
            {
                int absCol = promptW + DispWidth(text.Substring(0, cur));
                int totalRows = newTotal / w;
                int targetRow = absCol / w;
                int targetCol = absCol % w;
                try
                {
                    int top = Console.CursorTop - (totalRows - targetRow);
                    if (top >= 0) Console.SetCursorPosition(targetCol, top);
                }
                catch { }
            }
            else
            {
                // 光标在末尾：把多写的那个空格和填充吃掉
                try
                {
                    int back = 1 + ((pad > 0) ? Math.Min(pad, w - 2) : 0);
                    if (back > 0)
                    {
                        int left = Console.CursorLeft;
                        int top = Console.CursorTop;
                        if (left >= back)
                        {
                            Console.SetCursorPosition(left - back, top);
                        }
                        else
                        {
                            // 跨行回退，简化处理：回到当前行首
                            Console.Write('\r');
                        }
                    }
                }
                catch { }
            }

            LAST_DRAWN = newTotal;
        }

        private static void ReplaceLine(string prompt, StringBuilder buf, ref int cur, string text)
        {
            buf.Length = 0;
            buf.Append(text);
            cur = text.Length;
            RedrawLine(prompt, buf, cur);
        }

        private static void ClearLine(string prompt, StringBuilder buf, ref int cur)
        {
            buf.Length = 0;
            cur = 0;
            RedrawLine(prompt, buf, cur);
        }

        // 左右移动：仅在单行内用光标 API；跨行时重绘（罕见）
        private static void MoveCursorLeft(string prompt, StringBuilder buf, int cur, int wch)
        {
            if (wch < 1) wch = 1;
            try
            {
                if (Console.CursorLeft >= wch)
                {
                    Console.SetCursorPosition(Console.CursorLeft - wch, Console.CursorTop);
                    return;
                }
            }
            catch { }
            RedrawLine(prompt, buf, cur);
        }

        private static void MoveCursorRight(string prompt, StringBuilder buf, int cur, int wch)
        {
            if (wch < 1) wch = 1;
            try
            {
                // 右侧还有字符才移动；行尾不越界
                int w = SafeWidth();
                int target = DispWidth(prompt) + DispWidth(buf.ToString().Substring(0, cur));
                if (target <= LAST_DRAWN && Console.CursorLeft + wch < w)
                {
                    Console.SetCursorPosition(Console.CursorLeft + wch, Console.CursorTop);
                    return;
                }
            }
            catch { }
            RedrawLine(prompt, buf, cur);
        }

        // Tab 补全：只补命令名（第一个词），且只在光标位于行尾时生效。
        // 唯一候选直接补上并加空格；多候选则列出后重绘当前行。
        private static void DoTabComplete(string prompt, StringBuilder buf, ref int cur)
        {
            string line = buf.ToString();

            if (cur != line.Length) return;      // 只补行尾
            if (line.Length == 0) return;

            int sp = line.IndexOf(' ');
            if (sp >= 0) return;                 // 已经在输参数了，只补第一个词

            List<string> cands = CompleteCmd(line);
            if (cands.Count == 0) return;

            if (cands.Count == 1)
            {
                buf.Length = 0;
                buf.Append(cands[0]);
                buf.Append(' ');
                cur = buf.Length;
                RedrawLine(prompt, buf, cur);
                return;
            }

            // 多候选：候选属"机器给的信息"，用辅助色，别和用户输入抢亮度
            Console.WriteLine();
            UseDim();
            for (int i = 0; i < cands.Count; i++)
            {
                Console.Write(cands[i]);
                if (i < cands.Count - 1) Console.Write("   ");
            }
            Console.WriteLine();
            UseDefault();
            DrawPrompt(prompt);
            Console.Write(line);
            EndInput();
            LAST_DRAWN = DispWidth(prompt) + DispWidth(line);
        }
    }
}
