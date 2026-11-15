// ============================================================================
//  Common.cs — 两个工具共用的纯函数工具（无状态，可被任意入口类复用）
//  日志工具(App) 与 中文发送工具(SendApp) 都会编译进本文件。
//
//  注意：为兼容系统自带 csc.exe（.NET 4.x 的 C# 5.0 编译器），
//        全程只用 C# 5.0 语法：不写 out var / out _ / 局部函数 / => 表达式体。
// ============================================================================
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;

namespace AdbLogExport
{
    // Util 是纯静态工具类，不持有跨命令状态（状态各自放在 App / SendApp 里）
    internal static class Util
    {
        // ==================== 控制台 ====================
        // 设置控制台标题。失败（如重定向环境）静默忽略。
        internal static void SetTitle(string title)
        {
            try { Console.Title = title; }
            catch { }
        }

        // 按任意键退出（交互式）；输入被重定向时不阻塞
        internal static void Pause()
        {
            Console.WriteLine();
            Console.Write("  按任意键退出 ...");
            try { Console.ReadKey(true); }
            catch { }
            Console.WriteLine();
        }

        // 控制台宽度：取不到返回默认值
        internal static int ConsoleWidth(int def)
        {
            try
            {
                int w = Console.WindowWidth;
                if (w > 0) return w;
            }
            catch { }
            return def;
        }

        // ==================== 文本编码识别 ====================
        // 检测字节流编码：优先 BOM，否则尝试 UTF-8 严格校验，再退回 GBK(936)。
        // 返回：解码后的完整文本。
        internal static string DecodeText(byte[] bytes)
        {
            // 1. BOM 检测
            if (bytes.Length >= 3 && bytes[0] == 0xEF && bytes[1] == 0xBB && bytes[2] == 0xBF)
                return Encoding.UTF8.GetString(bytes, 3, bytes.Length - 3);
            if (bytes.Length >= 2 && bytes[0] == 0xFF && bytes[1] == 0xFE)
                return Encoding.Unicode.GetString(bytes, 2, bytes.Length - 2);
            if (bytes.Length >= 2 && bytes[0] == 0xFE && bytes[1] == 0xFF)
            {
                // UTF-16 BE：翻转后按 Unicode 解码
                byte[] flipped = new byte[bytes.Length - 2];
                for (int i = 2; i + 1 < bytes.Length; i += 2)
                {
                    flipped[i - 2] = bytes[i + 1];
                    flipped[i - 1] = bytes[i];
                }
                return Encoding.Unicode.GetString(flipped);
            }

            // 2. 无 BOM：尝试严格 UTF-8（失败会抛异常，则退回 GBK）
            try
            {
                Encoding utf8 = new UTF8Encoding(false, true);
                return utf8.GetString(bytes);
            }
            catch (DecoderFallbackException)
            {
                return Encoding.GetEncoding(936).GetString(bytes);
            }
        }

        // ==================== URL 编码 ====================
        // 与 bat 版 [uri]::EscapeDataString 等价：空格->%20，中文->UTF-8 百分号编码。
        // 但 .NET 的 Uri.EscapeDataString 不编码 ! * ' ( ) 这五个字符，
        // 与 JavaScript encodeURIComponent 一致，对 scheme URI 而言是安全的。
        internal static string EscapeData(string s)
        {
            if (s == null) return "";
            return Uri.EscapeDataString(s);
        }

        // ==================== 进程调用（adb）====================
        // Windows 命令行参数转义：把单个参数包进引号，内部引号翻倍
        internal static string QuoteArg(string a)
        {
            if (a.Length == 0) return "\"\"";
            if (a.IndexOfAny(new char[] { ' ', '\t', '"' }) < 0) return a;
            return "\"" + a.Replace("\"", "\\\"") + "\"";
        }

        // 通用外部命令执行：返回 exit code，输出写入 stdout / stderr。
        internal static int Run(string exe, List<string> argv, out string stdout, out string stderr)
        {
            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = exe;
            psi.UseShellExecute = false;
            psi.RedirectStandardOutput = true;
            psi.RedirectStandardError = true;
            psi.CreateNoWindow = true;
            psi.StandardOutputEncoding = new UTF8Encoding(false);
            psi.StandardErrorEncoding = new UTF8Encoding(false);

            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < argv.Count; i++)
            {
                if (i > 0) sb.Append(' ');
                sb.Append(QuoteArg(argv[i]));
            }
            psi.Arguments = sb.ToString();

            using (Process p = new Process())
            {
                p.StartInfo = psi;
                try { p.Start(); }
                catch (Exception ex)
                {
                    stdout = "";
                    stderr = ex.Message;
                    return 9009;
                }
                string o = p.StandardOutput.ReadToEnd();
                string e = p.StandardError.ReadToEnd();
                p.WaitForExit();
                stdout = o;
                stderr = e;
                return p.ExitCode;
            }
        }

        // 去掉字符串最外层一对引号（"C:\my dir" => C:\my dir）
        internal static string Unquote(string s)
        {
            if (s == null) return "";
            s = s.Trim();
            if (s.Length >= 2 && s[0] == '"' && s[s.Length - 1] == '"')
                return s.Substring(1, s.Length - 2).Trim();
            return s;
        }
    }
}
