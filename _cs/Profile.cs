using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Text;

namespace AdbLogExport
{
    // ============================================================================
    //  Profile.cs — 配置文件导出 / 导入（策略 A：覆盖 + 自动备份）
    //
    //  解决什么：升级新版本后，自定义指令、APK 管理列表、界面偏好要重配一遍。
    //  导出成一个 .adtprofile（zip），新版本导入即恢复。
    //
    //  为什么用 zip：custom_cmds.b64 本来就是不透明二进制 blob，塞 JSON 还要再
    //  base64 一次；zip 直接存原字节，将来加内容也不用改格式。
    //
    //  为什么白名单导出：adb_path / scrpy_path 这类绝对路径换机器必崩；
    //  以后新增的敏感字段也不会被"顺手打包"。黑名单做不到这一点。
    //
    //  安全：导入前把现有文件复制成 .bak.<时间戳>，导坏了能手工回退；
    //  写入走"临时文件 + 替换"，中途失败不会把现有配置写坏。
    // ============================================================================
    internal static class Profile
    {
        internal const int SCHEMA = 1;
        private const long BLOB_MAX = 5 * 1024 * 1024;   // custom_cmds.b64 上限 5MB

        private static string IniPath
        {
            get { return Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "adb_log_export.ini"); }
        }

        private static string DataDir
        {
            get
            {
                string d = "";
                try
                {
                    d = Path.Combine(
                        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                        "adb_Tool");
                }
                catch { }
                if (string.IsNullOrEmpty(d)) d = Path.Combine(Path.GetTempPath(), "adb_Tool");
                try { if (!Directory.Exists(d)) Directory.CreateDirectory(d); } catch { }
                return d;
            }
        }

        internal static string DefaultExportPath()
        {
            string desk = "";
            try { desk = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory); }
            catch { }
            if (string.IsNullOrEmpty(desk)) desk = DataDir;
            return Path.Combine(desk, "adb_Tool_配置_" + DateTime.Now.ToString("yyyyMMdd") + ".adtprofile");
        }

        /// <summary>程序版本（取程序集版本，没设就是 1.0.0.0）。只用于 manifest 标注。</summary>
        private static string AppVersion()
        {
            try { return System.Reflection.Assembly.GetExecutingAssembly().GetName().Version.ToString(); }
            catch { return ""; }
        }

        private static string ReadAllTextSafe(string p)
        {
            try { return File.Exists(p) ? File.ReadAllText(p, Encoding.UTF8) : ""; }
            catch { return ""; }
        }

        /// <summary>从 ini 里取 prefs= 那一行（不解析内容）。</summary>
        private static string ReadPrefsLine()
        {
            try
            {
                if (!File.Exists(IniPath)) return "";
                foreach (string ln in File.ReadAllLines(IniPath, Encoding.UTF8))
                {
                    string t = ln.TrimStart();
                    if (t.StartsWith("prefs=", StringComparison.OrdinalIgnoreCase))
                        return t.Substring(6);
                }
            }
            catch { }
            return "";
        }

        // ==================== 导出 ====================
        internal static bool Export(string path, out string msg)
        {
            msg = "";
            try
            {
                string dir = Path.GetDirectoryName(path);
                if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir)) Directory.CreateDirectory(dir);

                string tmp = path + ".tmp";
                if (File.Exists(tmp)) File.Delete(tmp);

                using (FileStream fs = new FileStream(tmp, FileMode.Create, FileAccess.Write))
                using (ZipArchive zip = new ZipArchive(fs, ZipArchiveMode.Create))
                {
                    string man = "{\"schema\":" + SCHEMA
                        + ",\"appVersion\":" + Json(AppVersion())
                        + ",\"exported\":\"" + DateTime.Now.ToString("yyyy-MM-ddTHH:mm:ss") + "\""
                        + ",\"machine\":" + Json(Environment.MachineName) + "}";
                    AddText(zip, "manifest.json", man);
                    AddText(zip, "prefs.txt", ReadPrefsLine());
                    AddFile(zip, "custom_cmds.b64", Path.Combine(DataDir, "custom_cmds.b64"));
                    AddFile(zip, "apk_apps.txt", App.ApkListPath());
                    AddText(zip, "README.txt",
                        "adb_Tool 配置文件\r\n"
                        + "包含：自定义指令、APK 管理列表、界面偏好\r\n"
                        + "不含：adb/scrcpy 路径、历史命令、设备别名、任何账号口令\r\n"
                        + "导入方式：设置 → 配置文件 → 导入配置（导入前会自动备份现有配置）\r\n");
                }

                if (File.Exists(path)) File.Delete(path);
                File.Move(tmp, path);
                FileInfo fi = new FileInfo(path);
                msg = "已导出：" + path + "（" + (fi.Length / 1024 + 1) + " KB）";
                return true;
            }
            catch (Exception ex)
            {
                msg = "导出失败：" + ex.Message;
                return false;
            }
        }

        private static void AddText(ZipArchive zip, string name, string text)
        {
            ZipArchiveEntry e = zip.CreateEntry(name, CompressionLevel.Optimal);
            using (Stream s = e.Open())
            {
                byte[] b = Encoding.UTF8.GetBytes(text ?? "");
                s.Write(b, 0, b.Length);
            }
        }

        private static void AddFile(ZipArchive zip, string name, string srcPath)
        {
            try
            {
                if (string.IsNullOrEmpty(srcPath) || !File.Exists(srcPath)) return;
                FileInfo fi = new FileInfo(srcPath);
                if (fi.Length > BLOB_MAX) return;      // 超大不打包，避免误带大文件
                ZipArchiveEntry e = zip.CreateEntry(name, CompressionLevel.Optimal);
                using (Stream s = e.Open())
                using (FileStream src = File.OpenRead(srcPath))
                    src.CopyTo(s);
            }
            catch { }
        }

        // ==================== 导入 ====================
        internal static bool Import(string path, out string msg)
        {
            msg = "";
            try
            {
                if (!File.Exists(path)) { msg = "文件不存在：" + path; return false; }

                string stamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
                int restored = 0;

                using (FileStream fs = File.OpenRead(path))
                using (ZipArchive zip = new ZipArchive(fs, ZipArchiveMode.Read))
                {
                    // 1) schema 校验：不能拿新版本的文件硬导进旧版本
                    ZipArchiveEntry man = zip.GetEntry("manifest.json");
                    if (man != null)
                    {
                        string js = ReadEntry(man);
                        int sc = JsonInt(js, "schema");
                        if (sc > SCHEMA)
                        {
                            msg = "该文件由更新版本的 adb_Tool 导出（schema " + sc
                                + "），请先升级应用";
                            return false;
                        }
                    }

                    // 2) 备份现有配置
                    Backup(Path.Combine(DataDir, "custom_cmds.b64"), stamp);
                    Backup(App.ApkListPath(), stamp);
                    Backup(IniPath, stamp);

                    // 3) 逐项恢复（缺项跳过，不整体失败）
                    ZipArchiveEntry cmds = zip.GetEntry("custom_cmds.b64");
                    if (cmds != null && WriteEntry(cmds, Path.Combine(DataDir, "custom_cmds.b64"))) restored++;

                    ZipArchiveEntry apk = zip.GetEntry("apk_apps.txt");
                    if (apk != null && WriteEntry(apk, App.ApkListPath())) restored++;

                    ZipArchiveEntry prefs = zip.GetEntry("prefs.txt");
                    if (prefs != null)
                    {
                        string pv = ReadEntry(prefs).Trim();
                        if (pv.Length > 0)
                        {
                            App.PREFS = pv;
                            if (WriteIniKey("prefs", pv)) restored++;
                        }
                    }
                }

                if (restored == 0) { msg = "文件里没有可导入的内容（格式不对？）"; return false; }

                msg = "已导入 " + restored + " 项配置（旧配置备份为 *.bak." + stamp
                    + "），重启应用后生效";
                return true;
            }
            catch (Exception ex)
            {
                msg = "导入失败：" + ex.Message;
                return false;
            }
        }

        private static string ReadEntry(ZipArchiveEntry e)
        {
            try
            {
                using (Stream s = e.Open())
                using (StreamReader r = new StreamReader(s, Encoding.UTF8))
                    return r.ReadToEnd();
            }
            catch { return ""; }
        }

        private static bool WriteEntry(ZipArchiveEntry e, string dest)
        {
            try
            {
                string dir = Path.GetDirectoryName(dest);
                if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir)) Directory.CreateDirectory(dir);
                string tmp = dest + ".tmp";
                using (Stream s = e.Open())
                using (FileStream o = new FileStream(tmp, FileMode.Create, FileAccess.Write))
                    s.CopyTo(o);
                if (File.Exists(dest)) File.Delete(dest);
                File.Move(tmp, dest);
                return true;
            }
            catch { return false; }
        }

        private static void Backup(string p, string stamp)
        {
            try
            {
                if (string.IsNullOrEmpty(p) || !File.Exists(p)) return;
                File.Copy(p, p + ".bak." + stamp, true);
            }
            catch { }
        }

        /// <summary>只改 ini 里的一个 key（不存在就追加），不碰其它行。</summary>
        private static bool WriteIniKey(string key, string val)
        {
            try
            {
                if (!File.Exists(IniPath)) return false;
                string[] lines = File.ReadAllLines(IniPath, Encoding.UTF8);
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
                    List<string> l2 = new List<string>(lines);
                    l2.Add(key + "=" + val);
                    lines = l2.ToArray();
                }
                File.WriteAllLines(IniPath, lines, new UTF8Encoding(false));
                return true;
            }
            catch { return false; }
        }

        // ---- 极简 JSON 辅助（只处理本文件写出的扁平常量，不引入依赖）----
        private static string Json(string s)
        {
            if (s == null) s = "";
            StringBuilder sb = new StringBuilder("\"");
            foreach (char c in s)
            {
                if (c == '"' || c == '\\') sb.Append('\\').Append(c);
                else if (c == '\n') sb.Append("\\n");
                else if (c == '\r') sb.Append("\\r");
                else sb.Append(c);
            }
            return sb.Append('"').ToString();
        }

        private static int JsonInt(string js, string key)
        {
            try
            {
                int i = js.IndexOf("\"" + key + "\"", StringComparison.Ordinal);
                if (i < 0) return 0;
                i = js.IndexOf(':', i);
                if (i < 0) return 0;
                i++;
                while (i < js.Length && (js[i] == ' ' || js[i] == '\t')) i++;
                int j = i;
                while (j < js.Length && (char.IsDigit(js[j]) || js[j] == '-')) j++;
                int v;
                return int.TryParse(js.Substring(i, j - i), out v) ? v : 0;
            }
            catch { return 0; }
        }

        /// <summary>:cfg info 用——报告各项是否存在与大小。</summary>
        internal static string Info()
        {
            StringBuilder sb = new StringBuilder();
            sb.AppendLine("配置文件（可导出项）：");
            sb.AppendLine("  自定义指令  " + SizeOf(Path.Combine(DataDir, "custom_cmds.b64")));
            sb.AppendLine("  APK 管理    " + SizeOf(App.ApkListPath()));
            string pv = ReadPrefsLine();
            sb.AppendLine("  界面偏好    " + (pv.Length == 0 ? "（无）" : pv.Length + " 字符"));
            sb.AppendLine("  存储目录    " + DataDir);
            return sb.ToString().TrimEnd();
        }

        private static string SizeOf(string p)
        {
            try
            {
                if (string.IsNullOrEmpty(p) || !File.Exists(p)) return "（无）";
                return (new FileInfo(p).Length / 1024 + 1) + " KB";
            }
            catch { return "（读不到）"; }
        }
    }
}
