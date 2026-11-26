// ============================================================================
//  HeapDump.cs - 通用 Java 堆抓取（2026-11-22 第 14 批需求 1.11）
// ----------------------------------------------------------------------------
//  用户原本的需求是"上传地图的 heapdump"，讨论后决定做成**通用工具**：
//  任意进程都能抓，不局限地图。理由：
//    测试时临时怀疑某个 App 泄漏，不该为了抓一次还得改工具/记包名。
//
//  ★ 能力边界（必须说清楚，否则用户会拿它去 dump native 进程然后以为坏了）：
//    `am dumpheap` 只能抓 **Java/ART 堆**。
//    init / logd / [kworker] 这类 native 进程抓不了，会直接失败。
//    所以进程列表默认只显示"应用进程"（名字带 '.' 的），
//    native 进程要显式打开"显示全部"才看得到。
//
//  三个关键实现细节：
//
//  1) dump 可能几分钟，默认 30 秒超时会误杀
//     App.CALL_TIMEOUT_MS 默认 30 秒，大堆（几百 MB）根本不够。
//     这里临时放大到 10 分钟，finally 里恢复。
//     为什么敢改全局：dump 是独占的重操作，期间不会有别的命令并发。
//
//  2) 设备端文件必须放 /data/local/tmp
//     应用进程只有这个目录的写权限。放别处 dumpheap 会直接报错。
//
//  3) 拉完要删设备上的临时文件
//     一个 386MB 堆的 hprof 通常 300~500MB，不删几次就把车机塞满了。
// ============================================================================
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

namespace AdbLogExport
{
    internal static partial class App
    {
        // ====================================================================
        //  进程列表（供页面下拉用）
        // ====================================================================
        //
        //  返回 [ {pid, rss, name}, ... ]，按 RSS 倒序（内存占用大的在前）。
        //
        //  为什么按 RSS 倒序：用户原始需求是"疑似内存泄漏时抓 dump"，
        //  那最有用的信息就是"现在谁占内存最多"。打开就排第一，不用翻几百行。
        internal static List<string[]> ListProcRows(bool includeNative)
        {
            List<string[]> rows = new List<string[]>();

            string raw = "";
            // 先试 toybox 的格式化输出（Android 8+）
            string o = "", e = "";
            try
            {
                ShellCall(CUR, "ps -A -o PID,RSS,NAME 2>/dev/null", out o, out e);
                raw = (o ?? "").Trim();
            }
            catch { }

            bool formatted = raw.IndexOf("PID") >= 0 && raw.IndexOf("NAME") >= 0;
            if (formatted)
            {
                string[] lines = raw.Split('\n');
                for (int i = 0; i < lines.Length; i++)
                {
                    string line = lines[i].Trim();
                    if (line.Length == 0) continue;
                    if (line.StartsWith("PID")) continue;   // 表头
                    // PID  RSS  NAME（NAME 可能含空格，取剩下的全部）
                    string[] parts = line.Split(new char[] { ' ', '\t' },
                                                StringSplitOptions.RemoveEmptyEntries);
                    if (parts.Length < 3) continue;

                    string pid = parts[0];
                    string rss = parts[1];
                    string name = string.Join(" ", parts, 2, parts.Length - 2);

                    if (!IsAppProc(name, includeNative)) continue;
                    rows.Add(new string[] { pid, rss, name });
                }
            }
            else
            {
                // 兜底：老式 ps（列不固定，PID 在第 2 列，NAME 在最后一列）
                try
                {
                    o = ""; e = "";
                    ShellCall(CUR, "ps 2>/dev/null", out o, out e);
                    raw = (o ?? "").Trim();
                }
                catch { }

                string[] lines = raw.Split('\n');
                for (int i = 0; i < lines.Length; i++)
                {
                    string line = lines[i].Trim();
                    if (line.Length == 0) continue;
                    if (line.StartsWith("USER")) continue;
                    string[] parts = line.Split(new char[] { ' ', '\t' },
                                                StringSplitOptions.RemoveEmptyEntries);
                    if (parts.Length < 3) continue;

                    string pid = parts[1];
                    string name = parts[parts.Length - 1];
                    int p;
                    if (!int.TryParse(pid, out p)) continue;

                    if (!IsAppProc(name, includeNative)) continue;
                    rows.Add(new string[] { pid, "0", name });   // 老式 ps 拿不到 RSS
                }
            }

            // 按 RSS 倒序（数值解析失败当 0）
            rows.Sort(delegate(string[] a, string[] b)
            {
                long ra, rb;
                long.TryParse(a[1], out ra);
                long.TryParse(b[1], out rb);
                if (rb != ra) return rb.CompareTo(ra);
                return string.Compare(a[2], b[2], StringComparison.Ordinal);
            });

            return rows;
        }

        // 是否算"应用进程"：
        //   应用进程名一般是包名（含 '.'），如 space.syncore.cockpit.map
        //   native/内核线程名字是 [kworker/0:1]、init、logd 这种，没有 '.' 或以 '[' 开头
        private static bool IsAppProc(string name, bool includeNative)
        {
            if (string.IsNullOrEmpty(name)) return false;
            if (includeNative) return true;
            if (name.StartsWith("[")) return false;
            return name.IndexOf('.') > 0;
        }

        // ====================================================================
        //  抓堆（CLI 入口也走这里）
        // ====================================================================
        //
        //  arg 支持三种：
        //    纯数字      当 PID 用，如 1234
        //    包名        如 space.syncore.cockpit.map → pidof 拿 PID
        //    关键字      如 map → ps | grep 拿第一个匹配
        internal static void DoHeapDump(string arg)
        {
            if (!RequireDevice("")) return;

            string a = (arg == null ? "" : arg.Trim());

            Info("抓 Java 堆（heapdump）");
            SayDumpHint();

            // ---- 解析目标 ----
            string pid = "";
            string label = "";

            if (a.Length == 0)
            {
                // 没参数：默认地图（这是最常用的场景）
                Info("未指定进程，使用默认目标（地图）");
                a = MAP_PKG;
            }

            int dummy;
            if (int.TryParse(a, out dummy) && a.Length <= 6)
            {
                pid = a;
                label = "PID " + a;
            }
            else
            {
                // 先当包名 pidof
                string p = ShellCapture("pidof " + a).Trim();
                if (p.Length > 0)
                {
                    pid = p.Split(' ')[0];   // 多进程时取第一个
                    label = a;
                }
                else
                {
                    // 再当关键字，ps | grep
                    string psOut = ShellCapture("ps -A -o PID,NAME 2>/dev/null | grep " + EscapeGrep(a));
                    string[] ls = psOut.Split('\n');
                    for (int i = 0; i < ls.Length; i++)
                    {
                        string line = ls[i].Trim();
                        if (line.Length == 0) continue;
                        string[] parts = line.Split(new char[] { ' ', '\t' },
                                                    StringSplitOptions.RemoveEmptyEntries);
                        if (parts.Length < 2) continue;
                        int pp;
                        if (!int.TryParse(parts[0], out pp)) continue;
                        pid = parts[0];
                        label = string.Join(" ", parts, 1, parts.Length - 1);
                        break;
                    }
                }
            }

            if (pid.Length == 0)
            {
                Fail("找不到进程：" + a);
                Hint("确认包名/进程名是否正确，或进程没在跑");
                return;
            }

            Ok("  目标：" + label + "  （PID " + pid + "）");
            Blank();

            // ---- dump ----
            string stamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
            // 文件名里只保留安全的字符（包名有 '.'，可以用）
            string safeName = Sanitize(label);
            string remote = "/data/local/tmp/" + safeName + "_" + stamp + ".hprof";

            Info("① dump 到设备：" + remote);
            Warn("  这一步可能要几十秒到几分钟（取决于堆大小），请耐心等");

            // 大堆 dump 会超过默认 30 秒超时，临时放大到 10 分钟
            int oldTimeout = CALL_TIMEOUT_MS;
            string dumpOut = "";
            try
            {
                CALL_TIMEOUT_MS = 600000;
                string o = "", e = "";
                ShellCall(CUR, "am dumpheap " + pid + " " + remote, out o, out e);
                dumpOut = ((o ?? "") + (e ?? "")).Trim();
            }
            finally
            {
                CALL_TIMEOUT_MS = oldTimeout;   // 一定恢复，否则后面所有命令都变超长等待
            }

            if (dumpOut.Length > 0) Hint("  " + FirstLine(dumpOut).Trim());

            // 复核设备上是否真的有文件
            string sz = ShellCapture("ls -l " + remote + " 2>/dev/null").Trim();
            if (sz.Length == 0 || sz.IndexOf("No such file", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                Fail("dump 失败：设备上没有生成文件");
                Hint("  可能原因：");
                Hint("   · 目标不是 Java 进程（am dumpheap 只能抓 ART 堆）");
                Hint("   · 该进程拒绝了 dump（debuggable=false 的应用可能拒绝）");
                Hint("   · 磁盘空间不足");
                return;
            }
            long devSize = ParseLsSize(sz);
            Ok("  设备上已生成：" + (devSize > 0 ? FmtMB(devSize) : "大小未知"));

            // ---- 拉到桌面 ----
            string dir;
            try { dir = OutDirFor("heapdump", "heapdump"); }
            catch { dir = Path.Combine(DesktopPath(), "logcat", "heapdump"); }
            try { Directory.CreateDirectory(dir); } catch { }

            string localFile = Path.Combine(dir, safeName + "_" + stamp + ".hprof");
            Info("② 拉取到：" + localFile);

            // 磁盘空间检查（文件可能几百 MB，不够会拉到一半失败）
            if (devSize > 0 && !HasFreeSpace(dir, devSize))
            {
                Fail("桌面所在磁盘空间不足（需要约 " + FmtMB(devSize) + "）");
                Hint("  请清理磁盘后重试；设备上的临时文件已保留：" + remote);
                return;
            }

            int oldTimeout2 = CALL_TIMEOUT_MS;
            try
            {
                CALL_TIMEOUT_MS = 600000;   // pull 大文件同样要放宽
                string o = "", e = "";
                ShellCall(CUR, "pull " + remote + " \"" + dir + "\"", out o, out e);
                string all = ((o ?? "") + (e ?? ""));
                if (all.IndexOf("error", StringComparison.OrdinalIgnoreCase) >= 0
                    || all.IndexOf("failed", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    Warn("  pull 输出：" + FirstLine(all).Trim());
                }
            }
            finally
            {
                CALL_TIMEOUT_MS = oldTimeout2;
            }

            // ---- 复核本地文件 ----
            if (File.Exists(localFile))
            {
                long ls = 0;
                try { ls = new FileInfo(localFile).Length; } catch { }
                Ok("✓ 已保存：" + FmtMB(ls));
            }
            else
            {
                Warn("本地没找到预期文件名，检查目录：" + dir);
            }

            // ---- 清理设备临时文件 ----
            Info("③ 清理设备临时文件");
            ShellCapture("rm -f " + remote);
            Ok("  已清理（避免占满车机存储）");

            Blank();
            Ok("完成。文件在：" + dir);
            Hint("可用 Android Studio 的 Profiler 或 MAT 打开 .hprof 分析");
        }

        private static void SayDumpHint()
        {
            Hint("只能抓 Java/ART 堆；native 进程抓不了");
        }

        // 路径/文件名清洗：只保留字母数字和 . _ -（防止包名里的奇怪字符破坏 shell）
        private static string Sanitize(string s)
        {
            if (string.IsNullOrEmpty(s)) return "proc";
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < s.Length && sb.Length < 60; i++)
            {
                char c = s[i];
                if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z')
                    || (c >= '0' && c <= '9') || c == '.' || c == '_' || c == '-')
                    sb.Append(c);
                else if (c == ' ' || c == ':') sb.Append('_');
            }
            return sb.Length == 0 ? "proc" : sb.ToString();
        }

        // ls -l 输出里取文件大小（第 5 列，字节）
        private static long ParseLsSize(string lsLine)
        {
            try
            {
                string[] parts = lsLine.Split(new char[] { ' ', '\t' },
                                              StringSplitOptions.RemoveEmptyEntries);
                // ls -l: -rw-r--r-- 1 root root 395264 2026-11-22 18:00 /path
                //        0        1 2    3    4      5
                if (parts.Length >= 5)
                {
                    long n;
                    if (long.TryParse(parts[4], out n)) return n;
                }
            }
            catch { }
            return 0;
        }

        private static string FmtMB(long bytes)
        {
            if (bytes <= 0) return "0 MB";
            double mb = bytes / 1024.0 / 1024.0;
            if (mb >= 1024) return (mb / 1024.0).ToString("0.##") + " GB";
            return mb.ToString("0.#") + " MB";
        }

        // 磁盘剩余空间是否够（留 10% 余量）
        private static bool HasFreeSpace(string dir, long needBytes)
        {
            try
            {
                string root = Path.GetPathRoot(Path.GetFullPath(dir));
                if (string.IsNullOrEmpty(root)) return true;
                DriveInfo di = new DriveInfo(root);
                return di.AvailableFreeSpace > needBytes * 1.1;
            }
            catch { return true; }   // 查不出来就不拦（宁可试一下）
        }

        // 注：DesktopPath() 已在 CmdRegistry.cs 里定义（App 的 partial class 共用），
        // 这里不再重复定义 —— 重复会报 CS0111 成员已定义。
    }
}
