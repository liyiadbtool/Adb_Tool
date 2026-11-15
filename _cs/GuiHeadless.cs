// ============================================================================
//  GuiHeadless.cs - GUI 无头执行模式（--exec / --exec-file）
//
//  为什么需要它：
//    需求第 4 条要求"指令输入窗口完全保留当前工具的能力"。这句话怎么证明？
//    靠人点按钮截图不算证明 —— 得能**程序化**地把同一串命令分别喂给两个版本，
//    比对它们的输出。命令行版有 stdin 可以做这件事，GUI 版没有控制台输入，
//    于是这里补一个无头执行通道。
//
//  关键点（否则这个"证明"是假的）：
//    走的必须是 GUI 真实的管道 —— GuiBoot 初始化 + GuiSink 接管 Console +
//    App.Dispatch 分派，而不是另写一条直通路径。否则测的是新代码，不是界面用的
//    那条路。字形/颜色也照常经 GuiSink 出来，所以比对的不只是文字，还有着色级别。
//
//  用法：
//    adb_log_gui.exe --exec ":h" "ls" ":env"
//    adb_log_gui.exe --exec-file cmds.txt
//  输出：每行渲染成 "L<级别> <文本>"，写到 stdout，退出码 = 全部命令是否都成功。
// ============================================================================
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

namespace AdbLogExport.Gui
{
    internal static class GuiHeadless
    {
        /// <summary>参数里是否带 --exec / --exec-file。</summary>
        internal static bool HasFlag(string[] args)
        {
            if (args == null) return false;
            for (int i = 0; i < args.Length; i++)
            {
                if (Match(args[i])) return true;
            }
            return false;
        }

        /// <summary>参数里是否带 --selfcheck。</summary>
        internal static bool HasSelfCheck(string[] args)
        {
            if (args == null) return false;
            for (int i = 0; i < args.Length; i++)
            {
                if (string.Equals(args[i], "--selfcheck", StringComparison.OrdinalIgnoreCase)
                    || string.Equals(args[i], "-selfcheck", StringComparison.OrdinalIgnoreCase))
                    return true;
            }
            return false;
        }

        private static bool Match(string a)
        {
            return string.Equals(a, "--exec", StringComparison.OrdinalIgnoreCase)
                || string.Equals(a, "-exec", StringComparison.OrdinalIgnoreCase)
                || string.Equals(a, "--exec-file", StringComparison.OrdinalIgnoreCase)
                || string.Equals(a, "-exec-file", StringComparison.OrdinalIgnoreCase);
        }

        // 以 - 开头的一律当选项，不当命令。
        // 设备的 shell 参数里确实可能有 -l / -a 这种，但它们是"命令的一部分"，
        // 应当和命令写在同一个参数里（--exec "ls -l"），不会被拆成独立 argv。
        private static bool IsOption(string a)
        {
            return a != null && a.Length > 0 && a[0] == '-';
        }

        internal static int Run(string[] args)
        {
            // ---- 1. 收集要执行的命令 ----
            // 两种写法：
            //    --exec "cmd1" "cmd2" ...        后面所有非选项参数都当命令
            //    --exec-file cmds.txt            一行一条，# 开头为注释
            // 早期版本每条 --exec 只吃一个参数，于是 --exec ":h" ":which ls"
            // 里的第二条被静默丢弃 —— 命令"没执行"，看起来像功能缺失。
            List<string> cmds = new List<string>();
            for (int i = 0; i < args.Length; i++)
            {
                string a = args[i];
                if (!Match(a)) continue;

                bool isFile = a.ToLowerInvariant().IndexOf("file") >= 0;
                if (isFile)
                {
                    if (i + 1 >= args.Length)
                    {
                        Console.Error.WriteLine("缺少 --exec-file 的路径参数");
                        return 2;
                    }
                    string p = args[++i];
                    try
                    {
                        string[] lines = File.ReadAllLines(p, Encoding.UTF8);
                        for (int k = 0; k < lines.Length; k++)
                        {
                            string l = lines[k].Trim();
                            if (l.Length == 0 || l.StartsWith("#")) continue;
                            cmds.Add(l);
                        }
                    }
                    catch (Exception ex)
                    {
                        Console.Error.WriteLine("读不了命令文件：" + ex.Message);
                        return 2;
                    }
                    continue;
                }

                // --exec：把紧随其后的参数收进来，遇到选项即止
                int j = i + 1;
                if (j >= args.Length || IsOption(args[j]))
                {
                    Console.Error.WriteLine("缺少 --exec 的命令参数");
                    return 2;
                }
                while (j < args.Length && !IsOption(args[j]))
                {
                    cmds.Add(args[j]);
                    j++;
                }
                i = j - 1;
            }

            if (cmds.Count == 0)
            {
                Console.Error.WriteLine("没有要执行的命令");
                return 2;
            }

            // ---- 2. 用 GUI 的真实初始化 ----
            // 与 GuiEntry.Main 走的是同一个 GuiBoot，所以 ini / adb 路径 /
            // 自定义命令 / 主题色 全部与界面一致。
            try
            {
                App.GuiBoot(null);
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine("GuiBoot 失败：" + ex.Message);
                return 2;
            }

            // ---- 3. 挂上真实的 GuiSink ----
            // 这一步是整个验证的关键：命令的输出经 Console 写入 GuiSink，
            // 再被切成"行 + 颜色 + 级别"。界面显示用的就是这套，一个字节都不绕。
            GuiSink sink = new GuiSink();
            Console.SetOut(sink);
            Console.SetError(sink);
            App.GUI_COLOR_HOOK = delegate(ConsoleColor c) { sink.SyncColor(c); };

            // ---- 3.5 同步做设备初始化 ----
            // 界面上这一步是 BootDevice() 在后台线程里跑的；--exec 模式没有消息循环，
            // 没人等那个线程，设备命令就会全部落在"未连接"上（测出来的等价性是假的）。
            // 所以这里同步调一次同一个 InitEnv —— 依然是共用的那段代码。
            // 失败时按 Program.Main 的做法置 OFFLINE：否则离线闸门被跳过，
            // --exec 测出来的行为会与界面不一致（界面走 BootDevice，也会置 OFFLINE）。
            try
            {
                if (!App.InitEnv()) App.OFFLINE = true;
            }
            catch (Exception ex) { try { Console.WriteLine("  ! 设备初始化异常：" + ex.Message); } catch { } }

            // ---- 4. 逐条执行 ----
            // 等价于界面上依次输入并回车；预处理也与界面一致（Trim + NormalizeLead）。
            StringBuilder csb = new StringBuilder();
            LineBuf buf = new LineBuf(csb);
            buf.Attach(sink);
            bool allOk = true;

            for (int i = 0; i < cmds.Count; i++)
            {
                string raw = cmds[i].Trim();
                if (raw.Length == 0) continue;

                buf.Begin(raw);

                bool ok = true;
                try
                {
                    App.Dispatch(App.NormalizeLead(raw));
                    ok = App.CMD_OK;
                }
                catch (Exception ex)
                {
                    ok = false;
                    try { Console.WriteLine("  \u00D7 内部错误：" + ex.Message); } catch { }
                }

                buf.End(ok);
                if (!ok) allOk = false;
            }

            // ---- 5. 落盘 + stdout ----
            // 设备初始化在 GUI 里是后台线程，--exec 模式下没人等它，
            // 所以这里补一次同步探测，让 ls / pull 这类设备命令有设备可用。
            Flush(sink, csb);
            WriteOut(csb);
            return allOk ? 0 : 1;
        }

        /// <summary>把 sink 里剩下的行全部取出来（不限量，避免截断）。</summary>
        private static void Flush(GuiSink sink, StringBuilder sb)
        {
            sink.Drain(delegate(GuiLine l) { SinkLine(sb, l); }, -1);
        }

        // 行格式：L<级别> <文本>。级别是 GUI 着色的语义标签
        // （1=成功 2=失败 3=警告 4=弱化 5=路径 0=普通），
        // 带上它才能验证"颜色语义也没丢"，而不只是文字一致。
        private static void SinkLine(StringBuilder sb, GuiLine l)
        {
            sb.Append("L").Append(l.Level).Append(' ').AppendLine(l.Text);
        }

        private static void WriteOut(StringBuilder sb)
        {
            try
            {
                Stream stdout = Console.OpenStandardOutput();
                byte[] b = new UTF8Encoding(false).GetBytes(sb.ToString());
                stdout.Write(b, 0, b.Length);
                stdout.Flush();
            }
            catch { }
        }

        /// <summary>每条命令执行前后各抽一次 sink，避免行序错乱。</summary>
        private sealed class LineBuf
        {
            private readonly StringBuilder _sb;
            private GuiSink _sink;

            internal LineBuf(StringBuilder sb) { _sb = sb; }

            internal void Attach(GuiSink s) { _sink = s; }

            internal void Begin(string cmd)
            {
                Drain();
                _sb.Append("### ").AppendLine(cmd);
            }

            internal void End(bool ok)
            {
                Drain();
                _sb.Append("### rc=").Append(ok ? "0" : "1").AppendLine();
            }

            private void Drain()
            {
                GuiSink s = _sink;
                if (s == null) return;
                s.Drain(delegate(GuiLine l) { SinkLine(_sb, l); }, -1);
            }
        }
    }
}
