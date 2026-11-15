// ============================================================================
//  FileBrowser.cs — 文件管理页的后端：本地/设备双栏 + 双向复制 + 增删改
//
//  为什么单独一个文件：
//     它不是"一条命令"，而是一组围绕文件系统的操作（列目录 / 拷入 / 拷出 /
//     新建 / 删除 / 重命名），还要带进度和取消。塞进 Adb.cs 会把命令分派搅乱。
//
//  几个必须守住的点：
//     1) 设备侧列目录用 `ls -la`，解析时按"固定 8 列 + 名字可能带空格"处理：
//        maxsplit=7，第 8 段整段都是名字。android 的 toybox 输出是
//        "perm links owner group size date time name"。
//     2) 所有拼进 shell 的路径都要单引号转义（文件名里带 ' 是真会遇到的）。
//     3) 同名一律"加时间戳改名"，不覆盖 —— 用户明确要求，也更安全。
//     4) 拷大文件时逐个文件推进度，并支持取消（置 FS_CANCEL + 杀掉 adb 子进程）。
//
//  C# 5.0：不用 $"" / ?. / out var / 表达式体成员。
// ============================================================================
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;

namespace AdbLogExport
{
    internal static partial class App
    {
        internal class FsEntry
        {
            internal string Name = "";
            internal string Path = "";     // 完整路径（设备侧是 /xxx，本地是 C:\xxx）
            internal bool IsDir = false;
            internal bool IsLink = false;
            internal long Size = 0;
            internal string Time = "";     // "2026-11-13 11:20"
            internal string Perm = "";     // "drwxr-xr-x"
        }

        // 复制过程中的取消标志（跨线程）
        internal static volatile bool FS_CANCEL = false;

        // ==================== 解析：设备 ls -la ====================
        // 一行示例：
        //   drwxr-xr-x  5 root root    4096 2026-11-13 11:20 acc
        //   -rw-r--r--  1 root root     123 2026-11-13 11:20 my log.txt
        //   lrwxrwxrwx  1 root root       7 2026-11-13 11:20 link -> /data
        // 返回 false 表示这行不是文件条目（total / 空行 / 畸形）。
        internal static bool FsParseLsLine(string line, string dir, out FsEntry entry)
        {
            entry = null;
            if (string.IsNullOrEmpty(line)) return false;

            string s = line.TrimEnd('\r', '\n');
            if (s.Length < 10) return false;
            string t = s.Trim();
            if (t.Length == 0) return false;
            if (t.StartsWith("total ", StringComparison.OrdinalIgnoreCase)) return false;

            char c0 = s[0];
            if (c0 != 'd' && c0 != '-' && c0 != 'l' && c0 != 'c' && c0 != 'b' && c0 != 's' && c0 != 'p')
                return false;

            // 最多切 8 段：前 7 段固定，第 8 段是名字（允许含空格）
            string[] p = SplitN(s, 8);
            if (p.Length < 8) return false;

            FsEntry e = new FsEntry();
            e.Perm = p[0];
            e.IsDir = (p[0].Length > 0 && p[0][0] == 'd');
            e.IsLink = (p[0].Length > 0 && p[0][0] == 'l');

            long size = 0;
            long.TryParse(p[4].Trim(), out size);
            e.Size = size;
            e.Time = (p[5].Trim() + " " + p[6].Trim()).Trim();

            string name = p[7].Trim();
            if (name.Length == 0) return false;
            if (name == "." || name == "..") return false;

            // 软链：名字后面会跟 " -> /target"
            if (e.IsLink)
            {
                int arrow = name.IndexOf(" -> ", StringComparison.Ordinal);
                if (arrow > 0) name = name.Substring(0, arrow).Trim();
            }
            if (name.Length == 0) return false;

            e.Name = name;
            e.Path = JoinDev(dir, name);
            entry = e;
            return true;
        }

        internal static List<FsEntry> FsParseLsOutput(string text, string dir)
        {
            List<FsEntry> list = new List<FsEntry>();
            if (string.IsNullOrEmpty(text)) return list;

            string[] lines = text.Split('\n');
            for (int i = 0; i < lines.Length; i++)
            {
                FsEntry e = null;
                if (FsParseLsLine(lines[i], dir, out e) && e != null) list.Add(e);
            }
            return list;
        }

        // 空白切分，但只切 n-1 次（剩下的整段保留）
        private static string[] SplitN(string s, int n)
        {
            List<string> parts = new List<string>(n);
            int i = 0;
            while (i < s.Length && parts.Count < n - 1)
            {
                while (i < s.Length && (s[i] == ' ' || s[i] == '\t')) i++;
                if (i >= s.Length) break;
                int st = i;
                while (i < s.Length && s[i] != ' ' && s[i] != '\t') i++;
                parts.Add(s.Substring(st, i - st));
            }
            while (i < s.Length && (s[i] == ' ' || s[i] == '\t')) i++;
            if (i < s.Length) parts.Add(s.Substring(i));
            return parts.ToArray();
        }

        internal static string JoinDev(string dir, string name)
        {
            if (string.IsNullOrEmpty(dir) || dir == "/") return "/" + name;
            return dir.TrimEnd('/') + "/" + name;
        }

        // shell 单引号转义：a'b -> 'a'\''b'
        internal static string ShQuote(string s)
        {
            if (s == null) s = "";
            return "'" + s.Replace("'", "'\\''") + "'";
        }

        // ==================== 列目录 ====================
        internal static List<FsEntry> FsDeviceList(string path, out string err)
        {
            err = "";
            List<FsEntry> list = new List<FsEntry>();
            if (string.IsNullOrEmpty(path)) path = "/";

            // 路径末尾补斜杠：/sdcard 这类本身是软链，不带斜杠时 ls 会把"链接本身"
            // 当成目标列出来，结果只得到一行 "/sdcard -> /storage/...".
            string lsPath = path;
            if (!lsPath.EndsWith("/", StringComparison.Ordinal)) lsPath += "/";

            string o = "";
            string e = "";
            ShellCall(CUR, "ls -la " + ShQuote(lsPath) + " 2>&1", out o, out e);
            string outStr = (o + "\n" + e);

            string low = outStr.ToLowerInvariant();
            if (low.IndexOf("permission denied") >= 0)
            {
                err = "没有权限读取该目录（需要 root，点顶部 root 提权后再试）";
                return list;
            }
            if (low.IndexOf("no such file") >= 0)
            {
                err = "目录不存在：" + path;
                return list;
            }
            if (low.IndexOf("not a directory") >= 0)
            {
                err = "这不是目录：" + path;
                return list;
            }
            if (low.IndexOf("inaccessible") >= 0 || low.IndexOf("not found") >= 0)
            {
                err = "读取失败：" + FirstLine(outStr.Trim());
                return list;
            }

            list = FsParseLsOutput(outStr, path);

            // 目录在前、文件在后，各自按名称排序（与资源管理器一致）
            list.Sort(delegate(FsEntry a, FsEntry b)
            {
                if (a.IsDir != b.IsDir) return a.IsDir ? -1 : 1;
                return string.Compare(a.Name, b.Name, StringComparison.OrdinalIgnoreCase);
            });
            return list;
        }

        // 「此电脑」层级顶部的快捷入口：桌面 / 下载 / 文档。
        // 为什么用 SpecialFolder 而不是拼路径：
        //   · 桌面可能被 OneDrive 重定向（路径在 Users\xxx\OneDrive\桌面）
        //   · 中文系统的实际文件夹名是 Desktop/Downloads/Documents，显示名才本地化
        // 取不到或不存在就跳过，绝不因为某个目录缺失而少列盘符。
        internal static List<FsEntry> FsLocalShortcuts()
        {
            List<FsEntry> list = new List<FsEntry>();

            AddShortcut(list, "桌面", Environment.GetFolderPath(Environment.SpecialFolder.Desktop));
            AddShortcut(list, "下载",
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Downloads"));
            AddShortcut(list, "文档", Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments));

            return list;
        }

        private static void AddShortcut(List<FsEntry> list, string name, string path)
        {
            if (string.IsNullOrEmpty(path)) return;
            try
            {
                if (!Directory.Exists(path)) return;
            }
            catch { return; }

            FsEntry e = new FsEntry();
            e.Name = name;
            e.Path = path;
            e.IsDir = true;
            e.Perm = "shortcut";      // UI 据此画 ★，并知道它不是盘符
            list.Add(e);
        }

        // 本地列目录：path 为空 = "此电脑"（快捷入口 + 盘符）
        internal static List<FsEntry> FsLocalList(string path, out string err)
        {
            err = "";
            List<FsEntry> list = new List<FsEntry>();
            if (string.IsNullOrEmpty(path))
            {
                try
                {
                    DriveInfo[] ds = DriveInfo.GetDrives();
                    for (int i = 0; i < ds.Length; i++)
                    {
                        FsEntry e = new FsEntry();
                        e.Name = ds[i].Name.TrimEnd('\\');
                        e.Path = ds[i].Name;
                        e.IsDir = true;
                        e.Perm = "drive";
                        try
                        {
                            if (ds[i].IsReady)
                            {
                                e.Size = ds[i].TotalSize;
                                e.Time = ds[i].DriveFormat;
                            }
                        }
                        catch { }
                        list.Add(e);
                    }
                    list.Sort(delegate(FsEntry a, FsEntry b)
                    {
                        return string.Compare(a.Name, b.Name, StringComparison.OrdinalIgnoreCase);
                    });

                    // 快捷入口固定排在最前（顺序：桌面 / 下载 / 文档），后面才是盘符
                    List<FsEntry> sc = FsLocalShortcuts();
                    if (sc.Count > 0) list.InsertRange(0, sc);
                }
                catch (Exception ex) { err = ex.Message; }
                return list;
            }

            try
            {
                DirectoryInfo di = new DirectoryInfo(path);
                if (!di.Exists) { err = "目录不存在：" + path; return list; }

                DirectoryInfo[] dirs = di.GetDirectories();
                for (int i = 0; i < dirs.Length; i++)
                {
                    FsEntry e = new FsEntry();
                    e.Name = dirs[i].Name;
                    e.Path = dirs[i].FullName;
                    e.IsDir = true;
                    e.Perm = "dir";
                    try { e.Time = dirs[i].LastWriteTime.ToString("yyyy-MM-dd HH:mm"); } catch { }
                    try
                    {
                        if ((dirs[i].Attributes & FileAttributes.ReparsePoint) != 0) e.IsLink = true;
                    }
                    catch { }
                    list.Add(e);
                }

                FileInfo[] files = di.GetFiles();
                for (int i = 0; i < files.Length; i++)
                {
                    FsEntry e = new FsEntry();
                    e.Name = files[i].Name;
                    e.Path = files[i].FullName;
                    e.IsDir = false;
                    e.Perm = "file";
                    try { e.Size = files[i].Length; } catch { }
                    try { e.Time = files[i].LastWriteTime.ToString("yyyy-MM-dd HH:mm"); } catch { }
                    list.Add(e);
                }

                list.Sort(delegate(FsEntry a, FsEntry b)
                {
                    if (a.IsDir != b.IsDir) return a.IsDir ? -1 : 1;
                    return string.Compare(a.Name, b.Name, StringComparison.OrdinalIgnoreCase);
                });
            }
            catch (UnauthorizedAccessException)
            {
                err = "没有权限访问该目录";
            }
            catch (Exception ex) { err = ex.Message; }
            return list;
        }

        internal static string FsLocalParent(string path)
        {
            if (string.IsNullOrEmpty(path)) return null;      // 已经是"此电脑"
            try
            {
                DirectoryInfo di = new DirectoryInfo(path);
                if (di.Parent == null) return "";             // 盘符根 -> 此电脑
                return di.Parent.FullName;
            }
            catch { return ""; }
        }

        internal static string FsDeviceParent(string path)
        {
            if (string.IsNullOrEmpty(path) || path == "/") return "/";
            return NormPath(path + "/..");
        }

        // ==================== 拷入设备（电脑 -> 设备）====================
        // progress 回调：done / total / 当前名字
        internal static int FsPush(List<string> localPaths, string devDir,
                                   Action<int, int, string> progress, out List<string> failed)
        {
            failed = new List<string>();
            if (localPaths == null || localPaths.Count == 0) return 0;
            int done = 0;
            int total = localPaths.Count;

            for (int i = 0; i < localPaths.Count; i++)
            {
                if (FS_CANCEL) break;
                string src = localPaths[i];
                string name = Path.GetFileName(src.TrimEnd('\\'));
                if (string.IsNullOrEmpty(name)) continue;

                string target = JoinDev(devDir, name);
                if (FsDeviceExists(target)) target = JoinDev(devDir, FsTimeStampName(name));

                List<string> argv = new List<string>();
                argv.Add("push");
                argv.Add(src);
                argv.Add(target);

                string combined = "";
                int rc = AdbCallStream(argv, out combined);
                if (rc == 0) done++;
                else failed.Add(name + "：" + FirstLine(combined));

                if (progress != null) progress(i + 1, total, name);
            }
            return done;
        }

        // ==================== 拷出到电脑（设备 -> 电脑）====================
        internal static int FsPull(List<string> devPaths, string localDir,
                                   Action<int, int, string> progress, out List<string> failed)
        {
            failed = new List<string>();
            if (devPaths == null || devPaths.Count == 0) return 0;
            int done = 0;
            int total = devPaths.Count;

            try { Directory.CreateDirectory(localDir); } catch { }

            for (int i = 0; i < devPaths.Count; i++)
            {
                if (FS_CANCEL) break;
                string src = devPaths[i];
                string name = LastSeg(src);
                if (string.IsNullOrEmpty(name) || name == "/") continue;

                string target = Path.Combine(localDir, name);
                if (File.Exists(target) || Directory.Exists(target))
                    target = Path.Combine(localDir, FsTimeStampName(name));

                List<string> argv = new List<string>();
                argv.Add("pull");
                argv.Add(src);
                argv.Add(target);

                string combined = "";
                int rc = AdbCallStream(argv, out combined);
                if (rc == 0) done++;
                else failed.Add(name + "：" + FirstLine(combined));

                if (progress != null) progress(i + 1, total, name);
            }
            return done;
        }

        // a.txt -> a_20261113_112030.txt（同名不覆盖，用户明确要求）
        internal static string FsTimeStampName(string name)
        {
            string stamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
            int dot = name.LastIndexOf('.');
            if (dot > 0 && dot > name.Length - 12)
                return name.Substring(0, dot) + "_" + stamp + name.Substring(dot);
            return name + "_" + stamp;
        }

        internal static bool FsDeviceExists(string devPath)
        {
            string o = "";
            string e = "";
            ShellCall(CUR, "[ -e " + ShQuote(devPath) + " ] && echo 1 || echo 0", out o, out e);
            return (o + e).IndexOf('1') >= 0;
        }

        // 文件名/文件夹名校验（不能用 ApkNameValid：那个限 40 字，且不挡 Windows 非法字符）
        internal static bool FsNameValid(string name, out string err)
        {
            err = "";
            string s = (name == null) ? "" : name.Trim();
            if (s.Length == 0) { err = "名称不能为空"; return false; }
            if (s.Length > 120) { err = "名称最长 120 个字符"; return false; }
            if (s == "." || s == "..") { err = "不能使用 . 或 .."; return false; }
            const string bad = "/\\:*?\"<>|";
            for (int i = 0; i < s.Length; i++)
            {
                char c = s[i];
                if (c < 0x20) { err = "名称不能包含控制字符"; return false; }
                if (bad.IndexOf(c) >= 0) { err = "名称不能包含 / \\ : * ? \" < > |"; return false; }
            }
            return true;
        }

        // JSON 字符串反转义。前端 JSON.stringify 发来的 Windows 路径里反斜杠是 "\\"，
        // 不还原会被当成"双反斜杠路径"，Directory.Exists 必然 false
        // —— 表现就是本地目录永远"加载中"（真实事故）。
        internal static string JsonUnescape(string s)
        {
            if (string.IsNullOrEmpty(s) || s.IndexOf('\\') < 0) return s;
            StringBuilder sb = new StringBuilder(s.Length);
            for (int i = 0; i < s.Length; i++)
            {
                char c = s[i];
                if (c != '\\' || i + 1 >= s.Length) { sb.Append(c); continue; }
                char nx = s[i + 1];
                if (nx == '\\') { sb.Append('\\'); i++; }
                else if (nx == '"') { sb.Append('"'); i++; }
                else if (nx == 'n') { sb.Append('\n'); i++; }
                else if (nx == 'r') { sb.Append('\r'); i++; }
                else if (nx == 't') { sb.Append('\t'); i++; }
                else if (nx == 'u' && i + 5 < s.Length)
                {
                    int code = 0;
                    bool ok = int.TryParse(s.Substring(i + 2, 4),
                        System.Globalization.NumberStyles.HexNumber, null, out code);
                    if (ok) { sb.Append((char)code); i += 5; }
                    else sb.Append(c);
                }
                else sb.Append(c);
            }
            return sb.ToString();
        }

        // ==================== 流式传输（字节级进度） ====================
        // 为什么要自己写：
        //   `adb push/pull` 不输出中间进度，只有结束时一行；单文件 200MB 时
        //   进度条从 0% 直接跳 100%，用户不知道还要等多久，也不能中途取消。
        //   走 exec-in/exec-out 自己搬运字节，才能做到"按字节推进度 + 随时取消"。
        //   目录仍交给 adb push/pull（递归自己写容易踩符号链接/权限的坑）。

        internal static bool FsDevIsDir(string devPath)
        {
            string o = "";
            string e = "";
            ShellCall(CUR, "[ -d " + ShQuote(devPath) + " ] && echo 1 || echo 0", out o, out e);
            return (o + e).IndexOf('1') >= 0;
        }

        internal static long FsDevFileSize(string devPath)
        {
            string o = "";
            string e = "";
            ShellCall(CUR, "stat -c %s " + ShQuote(devPath) + " 2>/dev/null", out o, out e);
            long n = 0;
            if (long.TryParse((o + e).Trim(), out n)) return n;
            return 0;
        }

        // 电脑 -> 设备（单文件流式）。progress(sent, total)
        internal static bool FsCopyUpStream(string localFile, string devTarget, long total,
                                            Action<long, long> progress, out string err)
        {
            err = "";
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo();
                psi.FileName = ADB;
                psi.UseShellExecute = false;
                psi.CreateNoWindow = true;
                psi.RedirectStandardInput = true;
                psi.RedirectStandardOutput = true;
                psi.RedirectStandardError = true;

                string serial = (!string.IsNullOrEmpty(SERIAL) && SERIAL_OK) ? SERIAL : DEVID;
                StringBuilder args = new StringBuilder();
                if (serial.Length > 0) args.Append(" -s ").Append(serial);
                args.Append(" exec-in \"cat > ").Append(devTarget.Replace("\"", "\\\"")).Append("\"");
                psi.Arguments = args.ToString();

                using (Process p = new Process())
                {
                    p.StartInfo = psi;
                    p.Start();

                    long sent = 0;
                    using (FileStream fs = new FileStream(localFile, FileMode.Open, FileAccess.Read, FileShare.Read))
                    {
                        byte[] buf = new byte[64 * 1024];
                        int n;
                        while ((n = fs.Read(buf, 0, buf.Length)) > 0)
                        {
                            if (FS_CANCEL)
                            {
                                try { p.Kill(); } catch { }
                                err = "已取消";
                                return false;
                            }
                            p.StandardInput.BaseStream.Write(buf, 0, n);
                            p.StandardInput.BaseStream.Flush();
                            sent += n;
                            if (progress != null) progress(sent, total);
                        }
                    }

                    try { p.StandardInput.Close(); } catch { }

                    string errtxt = "";
                    try { errtxt = p.StandardError.ReadToEnd(); } catch { }
                    if (!p.WaitForExit(600000)) { try { p.Kill(); } catch { } err = "超时"; return false; }
                    if (p.ExitCode != 0)
                    {
                        err = "传输失败：" + FirstLine(errtxt.Trim());
                        return false;
                    }
                    return true;
                }
            }
            catch (Exception ex)
            {
                err = "传输异常：" + ex.Message;
                return false;
            }
        }

        // 设备 -> 电脑（单文件流式）。total 用 stat 取到的字节数
        internal static bool FsCopyDownStream(string devSrc, string localTarget, long total,
                                              Action<long, long> progress, out string err)
        {
            err = "";
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo();
                psi.FileName = ADB;
                psi.UseShellExecute = false;
                psi.CreateNoWindow = true;
                psi.RedirectStandardOutput = true;
                psi.RedirectStandardError = true;

                string serial = (!string.IsNullOrEmpty(SERIAL) && SERIAL_OK) ? SERIAL : DEVID;
                StringBuilder args = new StringBuilder();
                if (serial.Length > 0) args.Append(" -s ").Append(serial);
                args.Append(" exec-out \"cat ").Append(devSrc.Replace("\"", "\\\"")).Append("\"");
                psi.Arguments = args.ToString();

                using (Process p = new Process())
                {
                    p.StartInfo = psi;
                    p.Start();

                    long got = 0;
                    using (FileStream fs = new FileStream(localTarget, FileMode.Create, FileAccess.Write, FileShare.None))
                    {
                        byte[] buf = new byte[64 * 1024];
                        int n;
                        while ((n = p.StandardOutput.BaseStream.Read(buf, 0, buf.Length)) > 0)
                        {
                            if (FS_CANCEL)
                            {
                                try { p.Kill(); } catch { }
                                try { fs.Close(); } catch { }
                                try { File.Delete(localTarget); } catch { }
                                err = "已取消";
                                return false;
                            }
                            fs.Write(buf, 0, n);
                            got += n;
                            if (progress != null) progress(got, total);
                        }
                    }

                    string errtxt = "";
                    try { errtxt = p.StandardError.ReadToEnd(); } catch { }
                    if (!p.WaitForExit(600000)) { try { p.Kill(); } catch { } err = "超时"; return false; }
                    if (p.ExitCode != 0)
                    {
                        err = "传输失败：" + FirstLine(errtxt.Trim());
                        return false;
                    }
                    return true;
                }
            }
            catch (Exception ex)
            {
                err = "传输异常：" + ex.Message;
                return false;
            }
        }

        // ==================== 搜索 ====================
        // 需求（2026-11-14）：文件页左右各一个搜索框，左边只搜电脑、右边只搜设备。
        //
        // 为什么是"递归搜索"而不是"过滤已加载的树"：
        //   树是懒加载的，用户没展开过的目录根本不在内存里，过滤只能搜到"眼前这几个"，
        //   与"搜索"的预期不符。所以走后端递归（本地 BFS / 设备 find），
        //   前端只负责展示平铺结果。
        //
        // 三条约束：
        //   1) 深度上限（默认本地 8 / 设备 6）—— 防止有人在 C:\ 上搜 "a" 卡死机器；
        //   2) 条数上限（500）—— 结果多了渲染不动，超了标 truncated 让用户加关键词；
        //   3) 无权限目录**跳过继续**，不能让一个 System Volume Information 打断整次搜索。

        private const int SearchMaxDefault = 500;

        // 搜索取消标志：**不能**复用 FS_CANCEL —— 那个是文件传输的，
        // 用户在搜索框按 Esc 把一个正在跑的上传掐掉，属于莫名其妙的破坏。
        internal static volatile bool FS_SEARCH_CANCEL = false;

        // 本地递归搜索。root 为空表示"此电脑"（搜所有固定盘）
        internal static List<FsEntry> FsLocalSearch(string root, string q, int limit, int maxDepth,
                                                   out bool truncated, out string err)
        {
            err = "";
            truncated = false;
            List<FsEntry> list = new List<FsEntry>();
            if (string.IsNullOrEmpty(q) || q.Trim().Length == 0) return list;
            if (limit <= 0) limit = SearchMaxDefault;
            if (maxDepth <= 0) maxDepth = 8;

            string needle = q.Trim();

            // 起点集合：指定目录就搜它，否则搜所有就绪的固定盘
            List<string> roots = new List<string>();
            if (!string.IsNullOrEmpty(root))
            {
                roots.Add(root);
            }
            else
            {
                try
                {
                    DriveInfo[] ds = DriveInfo.GetDrives();
                    for (int i = 0; i < ds.Length; i++)
                    {
                        try
                        {
                            if (ds[i].IsReady && ds[i].DriveType == DriveType.Fixed)
                                roots.Add(ds[i].Name);
                        }
                        catch { }
                    }
                }
                catch (Exception ex) { err = ex.Message; }
            }

            for (int r = 0; r < roots.Count; r++)
            {
                if (FS_SEARCH_CANCEL) break;
                // 队列：目录 + 深度（广度优先，浅层的命中先出来）
                Queue<string> qd = new Queue<string>();
                Queue<int> ql = new Queue<int>();
                qd.Enqueue(roots[r]);
                ql.Enqueue(0);

                while (qd.Count > 0)
                {
                    if (FS_SEARCH_CANCEL) break;
                    string dir = qd.Dequeue();
                    int depth = ql.Dequeue();

                    string[] subs = null;
                    try { subs = Directory.GetDirectories(dir); }
                    catch { subs = null; }

                    if (subs != null)
                    {
                        for (int i = 0; i < subs.Length; i++)
                        {
                            if (FS_SEARCH_CANCEL) break;
                            string name = "";
                            try { name = Path.GetFileName(subs[i]); }
                            catch { }
                            if (name.Length == 0) continue;

                            if (name.IndexOf(needle, StringComparison.OrdinalIgnoreCase) >= 0)
                            {
                                if (list.Count >= limit) { truncated = true; SortEntries(list); return list; }
                                FsEntry e = new FsEntry();
                                e.Name = name;
                                e.Path = subs[i];
                                e.IsDir = true;
                                e.Perm = "dir";
                                try { e.Time = Directory.GetLastWriteTime(subs[i]).ToString("yyyy-MM-dd HH:mm"); } catch { }
                                try
                                {
                                    if ((File.GetAttributes(subs[i]) & FileAttributes.ReparsePoint) != 0) e.IsLink = true;
                                }
                                catch { }
                                list.Add(e);
                            }

                            // 不往符号链接里钻：Windows 上有自引用链接，会无限深
                            if (depth + 1 < maxDepth && !IsReparse(subs[i]))
                            {
                                qd.Enqueue(subs[i]);
                                ql.Enqueue(depth + 1);
                            }
                        }
                    }

                    string[] files = null;
                    try { files = Directory.GetFiles(dir); }
                    catch { files = null; }
                    if (files == null) continue;

                    for (int i = 0; i < files.Length; i++)
                    {
                        if (FS_SEARCH_CANCEL) break;
                        string name = "";
                        try { name = Path.GetFileName(files[i]); }
                        catch { }
                        if (name.Length == 0) continue;
                        if (name.IndexOf(needle, StringComparison.OrdinalIgnoreCase) < 0) continue;

                        if (list.Count >= limit) { truncated = true; SortEntries(list); return list; }
                        FsEntry e = new FsEntry();
                        e.Name = name;
                        e.Path = files[i];
                        e.IsDir = false;
                        e.Perm = "file";
                        try { e.Size = new FileInfo(files[i]).Length; } catch { }
                        try { e.Time = File.GetLastWriteTime(files[i]).ToString("yyyy-MM-dd HH:mm"); } catch { }
                        list.Add(e);
                    }
                }
            }

            SortEntries(list);
            return list;
        }

        private static bool IsReparse(string path)
        {
            try { return (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0; }
            catch { return true; }   // 拿不到属性就当作不可进入，避免卡住
        }

        // 设备递归搜索：用 find，目录与文件各查一次（顺带拿到类型，不用再 stat）
        internal static List<FsEntry> FsDeviceSearch(string root, string q, int limit, int maxDepth,
                                                     out bool truncated, out string err)
        {
            err = "";
            truncated = false;
            List<FsEntry> list = new List<FsEntry>();
            if (string.IsNullOrEmpty(q) || q.Trim().Length == 0) return list;
            if (string.IsNullOrEmpty(root)) root = "/sdcard";
            if (limit <= 0) limit = SearchMaxDefault;
            if (maxDepth <= 0) maxDepth = 6;

            string pattern = "*" + GlobEscape(q.Trim()) + "*";
            // head -n limit+1：多取一条用来判断"是否被截断"，比再遍历一次省事
            string pick = " 2>/dev/null | head -n " + (limit + 1);

            // 【必须加 -H】实测（Android 12 / toybox 0.8.4）：
            //   `/sdcard` 是软链，`find /sdcard ...` **一条都不返回**（toybox find
            //   默认不跟随命令行给的软链）；`find -H /sdcard ...` 才正常遍历。
            //   这个坑不修的话，设备侧搜索永远是"没有匹配项"，看起来像搜索坏了。
            string o1 = "";
            string e1 = "";
            ShellCall(CUR, "find -H " + ShQuote(root) + " -maxdepth " + maxDepth
                       + " -type d -iname " + ShQuote(pattern) + pick, out o1, out e1);

            string o2 = "";
            string e2 = "";
            ShellCall(CUR, "find -H " + ShQuote(root) + " -maxdepth " + maxDepth
                       + " -type f -iname " + ShQuote(pattern) + pick, out o2, out e2);

            string allErr = (e1 == null ? "" : e1) + " " + (e2 == null ? "" : e2);
            string lowErr = allErr.ToLowerInvariant();

            // find 不可用（个别裁剪系统把它裁掉了）
            if (lowErr.IndexOf("not found") >= 0 && lowErr.IndexOf("no such file") < 0)
            {
                err = "设备上的 find 不可用，无法递归搜索（可以直接在树里点进去看）";
                return list;
            }
            if (lowErr.IndexOf("no such file or directory") >= 0
                && (o1 == null || o1.Trim().Length == 0) && (o2 == null || o2.Trim().Length == 0))
            {
                err = "目录不存在：" + root;
                return list;
            }

            Dictionary<string, bool> seen = new Dictionary<string, bool>(StringComparer.Ordinal);
            string[] lines1 = (o1 == null ? "" : o1).Split('\n');
            string[] lines2 = (o2 == null ? "" : o2).Split('\n');
            AddFindLines(lines1, true, ref list, limit, ref truncated, seen);
            if (!truncated) AddFindLines(lines2, false, ref list, limit, ref truncated, seen);

            SortEntries(list);
            if (list.Count == 0 && err.Length == 0 && allErr.Trim().Length > 0)
                err = "搜索失败：" + FirstLine(allErr.Trim());
            return list;
        }

        private static void AddFindLines(string[] lines, bool isDir, ref List<FsEntry> list,
                                         int limit, ref bool truncated, Dictionary<string, bool> seen)
        {
            for (int i = 0; i < lines.Length; i++)
            {
                string p = lines[i] == null ? "" : lines[i].Trim();
                if (p.Length == 0) continue;
                if (seen.ContainsKey(p)) continue;
                if (list.Count >= limit) { truncated = true; return; }
                seen[p] = true;

                string name = p;
                int sl = p.LastIndexOf('/');
                if (sl >= 0 && sl < p.Length - 1) name = p.Substring(sl + 1);

                FsEntry e = new FsEntry();
                e.Name = name;
                e.Path = p;
                e.IsDir = isDir;
                e.Perm = isDir ? "dir" : "file";
                // 设备侧不额外 stat：一次 find 一条要几十毫秒，500 条会把界面拖死。
                // 想看大小/时间就双击结果跳回树里（那里有完整信息）。
                e.Size = 0;
                e.Time = "";
                list.Add(e);
            }
        }

        // find -iname 里 * ? [ ] 是通配符，用户输入要当字面量：加反斜杠转义
        private static string GlobEscape(string s)
        {
            StringBuilder sb = new StringBuilder(s.Length + 8);
            for (int i = 0; i < s.Length; i++)
            {
                char c = s[i];
                if (c == '*' || c == '?' || c == '[' || c == ']' || c == '\\') sb.Append('\\');
                sb.Append(c);
            }
            return sb.ToString();
        }

        private static void SortEntries(List<FsEntry> list)
        {
            list.Sort(delegate(FsEntry a, FsEntry b)
            {
                if (a.IsDir != b.IsDir) return a.IsDir ? -1 : 1;
                return string.Compare(a.Name, b.Name, StringComparison.OrdinalIgnoreCase);
            });
        }

        // ==================== 增删改 ====================
        internal static bool FsDeviceMkdir(string dir, string name, out string err)
        {
            err = "";
            if (!FsNameValid(name, out err)) return false;
            string target = JoinDev(dir, name);
            string o = "";
            string e = "";
            int rc = ShellCall(CUR, "mkdir -p " + ShQuote(target) + " 2>&1", out o, out e);
            string low = (o + " " + e).ToLowerInvariant();
            if (rc != 0 || low.IndexOf("denied") >= 0 || low.IndexOf("read-only") >= 0)
            {
                err = "新建失败：" + FirstLine((o + " " + e).Trim());
                return false;
            }
            return true;
        }

        internal static bool FsDeviceDelete(List<string> paths, out string err)
        {
            err = "";
            for (int i = 0; i < paths.Count; i++)
            {
                string o = "";
                string e = "";
                int rc = ShellCall(CUR, "rm -rf " + ShQuote(paths[i]) + " 2>&1", out o, out e);
                string low = (o + " " + e).ToLowerInvariant();
                if (rc != 0 || low.IndexOf("denied") >= 0 || low.IndexOf("read-only") >= 0)
                {
                    err = "删除失败：" + FirstLine((o + " " + e).Trim());
                    return false;
                }
            }
            return true;
        }

        internal static bool FsDeviceRename(string path, string newName, out string err)
        {
            err = "";
            if (!FsNameValid(newName, out err)) return false;
            string target = JoinDev(FsDeviceParent(path), newName);
            string o = "";
            string e = "";
            int rc = ShellCall(CUR, "mv " + ShQuote(path) + " " + ShQuote(target) + " 2>&1", out o, out e);
            string low = (o + " " + e).ToLowerInvariant();
            if (rc != 0 || low.IndexOf("denied") >= 0 || low.IndexOf("cross-device") >= 0)
            {
                err = "重命名失败：" + FirstLine((o + " " + e).Trim());
                return false;
            }
            return true;
        }

        internal static bool FsLocalMkdir(string dir, string name, out string err)
        {
            err = "";
            if (!FsNameValid(name, out err)) return false;
            try
            {
                Directory.CreateDirectory(Path.Combine(dir, name));
                return true;
            }
            catch (Exception ex) { err = "新建失败：" + ex.Message; return false; }
        }

        internal static bool FsLocalDelete(List<string> paths, out string err)
        {
            err = "";
            for (int i = 0; i < paths.Count; i++)
            {
                try
                {
                    if (Directory.Exists(paths[i])) Directory.Delete(paths[i], true);
                    else if (File.Exists(paths[i])) File.Delete(paths[i]);
                }
                catch (Exception ex) { err = "删除失败：" + ex.Message; return false; }
            }
            return true;
        }

        internal static bool FsLocalRename(string path, string newName, out string err)
        {
            err = "";
            if (!FsNameValid(newName, out err)) return false;
            try
            {
                string parent = Path.GetDirectoryName(path);
                string target = Path.Combine(parent, newName);
                if (File.Exists(target) || Directory.Exists(target))
                {
                    err = "同目录下已存在 " + newName;
                    return false;
                }
                if (Directory.Exists(path)) Directory.Move(path, target);
                else File.Move(path, target);
                return true;
            }
            catch (Exception ex) { err = "重命名失败：" + ex.Message; return false; }
        }

        // 大小显示（与 ls -l 的字节数对齐，不改变原值）
        internal static string FsSizeText(FsEntry e)
        {
            if (e.IsDir) return "";
            long n = e.Size;
            if (n < 1024) return n + " B";
            if (n < 1024L * 1024) return (n / 1024.0).ToString("0.0") + " KB";
            if (n < 1024L * 1024 * 1024) return (n / 1048576.0).ToString("0.0") + " MB";
            return (n / 1073741824.0).ToString("0.00") + " GB";
        }
    }
}
