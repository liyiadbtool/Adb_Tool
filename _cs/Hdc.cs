// ============================================================================
//  Hdc.cs — hdc（HarmonyOS Device Connector）执行通道
//
//  需求来源（2026-11-12）：
//    "清除hicar历史设备，命令 hdc shell bm clean -d -n com.huawei.hmos.hicar"
//    用户确认："车机装了 hdc"
//
//  为什么需要单独一个通道：
//    本工具其余命令都走 adb（`ADB` 变量指向 adb.exe）。hdc 是鸿蒙那一套的
//    调试桥，命令名和协议都不同（hdc shell xxx / hdc file send 等），
//    不能复用 AdbCall。
//
//  hdc 从哪来（按优先级）：
//    1) ini 里的 hdc= 配置（用户可指定绝对路径）
//    2) exe 同级目录的 hdc.exe（随发布包一起拷进去）
//    3) 系统 PATH 里的 hdc
//    找不到就报错并给出获取方式，绝不静默失败 —— 静默失败会让用户
//    以为"点了没反应"。
//
//  C# 5.0 兼容：不用 out var / 局部函数 / => 表达式体 / $"..."。
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
        // hdc 可执行文件路径。由 ResolveHdc() 惰性解析并缓存。
        internal static string HDC = "";

        // 已经解析过（避免每次都跑一遍文件存在性检查）
        private static bool HDC_RESOLVED = false;

        // 上一次解析失败的原因（给 Hint 用）
        private static string HDC_ERR = "";

        // ---------------- 解析 hdc 路径 ----------------

        internal static string ResolveHdc()
        {
            if (HDC_RESOLVED && !string.IsNullOrEmpty(HDC)) return HDC;
            HDC_RESOLVED = true;
            HDC_ERR = "";

            // 1) ini 显式配置
            if (!string.IsNullOrEmpty(HDC) && File.Exists(HDC)) return HDC;

            // 2) exe 同级（发布包自带）
            try
            {
                string exeDir = Path.GetDirectoryName(
                    System.Reflection.Assembly.GetExecutingAssembly().Location);
                if (!string.IsNullOrEmpty(exeDir))
                {
                    string local = Path.Combine(exeDir, "hdc.exe");
                    if (File.Exists(local)) { HDC = local; return HDC; }
                }
            }
            catch { }

            // 3) PATH
            try
            {
                string pathVar = Environment.GetEnvironmentVariable("PATH");
                if (!string.IsNullOrEmpty(pathVar))
                {
                    string[] parts = pathVar.Split(';');
                    for (int i = 0; i < parts.Length; i++)
                    {
                        string p = parts[i].Trim();
                        if (p.Length == 0) continue;
                        try
                        {
                            string cand = Path.Combine(p, "hdc.exe");
                            if (File.Exists(cand)) { HDC = cand; return HDC; }
                        }
                        catch { }
                    }
                }
            }
            catch { }

            // 4) 兜底：直接写 "hdc"，让系统自己找（可能是 .bat 包装或别名）
            //    这一条是有意保留的：有些环境把 hdc 做成了包装脚本，
            //    File.Exists 找不到，但命令行能跑。
            HDC = "hdc";
            return HDC;
        }

        // hdc 是否可用。用一个极轻的命令验证（hdc -v）。
        // 返回 false 时 HDC_ERR 里有原因。
        internal static bool HdcAvailable()
        {
            string exe = ResolveHdc();
            string o = "";
            string e = "";
            int rc = RunHdcRaw(new List<string> { "-v" }, 5000, out o, out e);

            if (rc == 0) return true;

            // rc != 0 也可能是 -v 不被这个版本支持（有些版本要 hdc version）。
            // 再试一次更宽松的写法。
            o = "";
            e = "";
            rc = RunHdcRaw(new List<string> { "version" }, 5000, out o, out e);
            if (rc == 0) return true;

            string msg = (o + " " + e).ToLowerInvariant();
            if (msg.IndexOf("not recognized") >= 0
                || msg.IndexOf("不是内部或外部命令") >= 0
                || msg.IndexOf("no such file") >= 0
                || msg.IndexOf("cannot find") >= 0)
            {
                HDC_ERR = "找不到 hdc 可执行文件";
            }
            else
            {
                HDC_ERR = "hdc 调用失败";
            }
            return false;
        }

        // ---------------- 执行 ----------------

        // 跑一条 hdc 命令。args 是参数数组（不含 "hdc" 本身）。
        // 返回进程退出码；stdout/stderr 分别回传。
        //
        // 与 AdbCall 的实现策略一致：Process + 异步读两个流，避免
        // 管道缓冲区写满导致互锁（只读 stdout 不读 stderr 的经典死锁）。
        internal static int RunHdcRaw(List<string> args, int timeoutMs,
                                      out string stdout, out string stderr)
        {
            stdout = "";
            stderr = "";

            string exe = ResolveHdc();

            ProcessStartInfo si = new ProcessStartInfo();
            si.FileName = exe;
            si.UseShellExecute = false;
            si.CreateNoWindow = true;
            si.RedirectStandardOutput = true;
            si.RedirectStandardError = true;
            si.RedirectStandardInput = true;
            si.StandardOutputEncoding = Encoding.UTF8;
            si.StandardErrorEncoding = Encoding.UTF8;

            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < args.Count; i++)
            {
                if (i > 0) sb.Append(' ');
                sb.Append(QuoteArg(args[i]));
            }
            si.Arguments = sb.ToString();

            Process p = null;
            try
            {
                p = Process.Start(si);
            }
            catch (Exception ex)
            {
                stderr = "无法启动 hdc：" + ex.Message;
                return -1;
            }

            if (p == null)
            {
                stderr = "无法启动 hdc（Process.Start 返回 null）";
                return -1;
            }

            // 异步收集，避免死锁
            StringBuilder so = new StringBuilder();
            StringBuilder se = new StringBuilder();
            p.OutputDataReceived += delegate(object s, DataReceivedEventArgs ev)
            {
                if (ev.Data != null) { lock (so) { so.AppendLine(ev.Data); } }
            };
            p.ErrorDataReceived += delegate(object s, DataReceivedEventArgs ev)
            {
                if (ev.Data != null) { lock (se) { se.AppendLine(ev.Data); } }
            };

            try { p.BeginOutputReadLine(); p.BeginErrorReadLine(); } catch { }
            try { p.StandardInput.Close(); } catch { }

            bool exited = p.WaitForExit(timeoutMs);
            if (!exited)
            {
                try { p.Kill(); } catch { }
                try { p.WaitForExit(1000); } catch { }
                lock (so) { stdout = so.ToString(); }
                lock (se) { stderr = se.ToString(); }
                if (stderr.Length == 0) stderr = "hdc 执行超时（" + timeoutMs + "ms）";
                return -2;
            }

            // 给异步读取回调一点时间把尾巴刷完
            try { p.WaitForExit(); } catch { }

            lock (so) { stdout = so.ToString(); }
            lock (se) { stderr = se.ToString(); }
            return p.ExitCode;
        }

        // 单参数加引号（只在含空格/特殊字符时加）
        private static string QuoteArg(string a)
        {
            if (string.IsNullOrEmpty(a)) return "\"\"";
            bool need = false;
            for (int i = 0; i < a.Length; i++)
            {
                char c = a[i];
                if (c == ' ' || c == '\t' || c == '"' || c == '&' || c == '|'
                    || c == '<' || c == '>' || c == '^' || c == '(' || c == ')')
                {
                    need = true;
                    break;
                }
            }
            if (!need) return a;
            return "\"" + a.Replace("\"", "\\\"") + "\"";
        }

        // 跑一条 hdc shell 命令并把输出打到界面上。
        // 返回是否成功（rc == 0）。
        internal static bool HdcShell(string cmd)
        {
            Echo("hdc shell", cmd);

            string o = "";
            string e = "";
            int rc = RunHdcRaw(new List<string> { "shell", cmd }, 20000, out o, out e);

            string merged = (o + "\n" + e).Trim();
            if (merged.Length > 0)
            {
                string[] lines = merged.Split('\n');
                for (int i = 0; i < lines.Length; i++)
                {
                    string line = lines[i].TrimEnd('\r');
                    if (line.Trim().Length > 0) Info(line);
                }
            }

            if (rc == 0) return true;

            // hdc 的错误有时是文本而非退出码，补一层文本识别
            string low = merged.ToLowerInvariant();
            if (low.IndexOf("error") >= 0 || low.IndexOf("fail") >= 0
                || low.IndexOf("not found") >= 0 || low.IndexOf("no device") >= 0)
            {
                return false;
            }
            return rc == 0;
        }
    }
}
