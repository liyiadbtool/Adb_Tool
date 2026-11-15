using System;
using System.IO;
using System.Text;

namespace AdbLogExport
{
    // 2026-11-15：用户自定义 ADB 指令的持久化。
    //
    // 约定（先定协议再写实现）：
    //   前端把整份配置 JSON.stringify 后做 base64，作为一个不透明字符串传过来；
    //   C# 只负责原样存 / 取，完全不解析内容。这样 C# 5.0 不需要引入 JSON 库，
    //   也不会因为配置里出现引号 / 逗号 / 花括号被 GetField() 截断。
    //   落点与 apk_apps.txt 一致：%LOCALAPPDATA%\adb_Tool\custom_cmds.b64
    internal static class CustomStore
    {
        private const long MAX_LEN = 512 * 1024;   // 512 KB 上限，防止误写超大内容

        private static string Dir()
        {
            // 注意：Path.Combine("", "adb_Tool") 返回的是相对路径 "adb_Tool"（非空），
            // 所以必须先判「基目录」是否为空再拼接 —— 直接判 Combine 的结果永远为假，
            // 会在 LocalApplicationData 拿不到时把文件落到进程当前目录。
            string d = "";
            try
            {
                string baseDir = Environment.GetFolderPath(
                    Environment.SpecialFolder.LocalApplicationData);
                if (!string.IsNullOrEmpty(baseDir))
                    d = Path.Combine(baseDir, "adb_Tool");
            }
            catch { }
            if (string.IsNullOrEmpty(d)) d = Path.Combine(Path.GetTempPath(), "adb_Tool");
            try { if (!Directory.Exists(d)) Directory.CreateDirectory(d); } catch { }
            return d;
        }

        private static string FilePath()
        {
            return Path.Combine(Dir(), "custom_cmds.b64");
        }

        internal static string Load()
        {
            try
            {
                string p = FilePath();
                if (!File.Exists(p)) return "";
                return File.ReadAllText(p, Encoding.UTF8).Trim();
            }
            catch (Exception ex) { App.Trace("custom: 读取失败 " + ex.Message); return ""; }
        }

        internal static bool Save(string b64)
        {
            try
            {
                if (b64 == null) b64 = "";
                if (b64.Length > MAX_LEN) return false;
                File.WriteAllText(FilePath(), b64, new UTF8Encoding(false));
                return true;
            }
            catch (Exception ex) { App.Trace("custom: 保存失败 " + ex.Message); return false; }
        }
    }
}
