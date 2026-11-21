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

        // ini 的位置有两套布局（2026-11-19 起发布包改成 exe + internal\）：
        //   发布包：<exe目录>\internal\adb_log_export.ini
        //   源码/便携：<exe目录>\adb_log_export.ini
        //
        // 2026-11-21 修复：原来只拼 BaseDirectory，发布包里 ini 在 internal 下，
        // 于是 WriteIniKey 找不到文件、静默返回 false —— 表现为"导入显示 3 项、
        // 实际 prefs 没写进去"（界面偏好导入无效，且不报错）。
        // 现在与 CmdRegistry / Ffmpeg 保持同一套"先 internal 再根目录"的顺序。
        private static string IniPath
        {
            get
            {
                string baseDir = AppDomain.CurrentDomain.BaseDirectory;
                string p = Path.Combine(baseDir, "internal", "adb_log_export.ini");
                if (File.Exists(p)) return p;
                return Path.Combine(baseDir, "adb_log_export.ini");
            }
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
                bool prefsSkipped = false;   // prefs 损坏时置位，用于给出准确提示

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
                            // 2026-11-21 修复：原来不校验就写 ini。
                            // prefs 是前端 JSON 的 base64，导入一个损坏/伪造的文件
                            // （如 "eyJ0ZXN0IjoidHJ1ZSJ9" = {"test":"true"}）会把
                            // 用户真实的界面偏好**永久覆盖**成垃圾值。前端 parsePrefs
                            // 虽有 try/catch 不会崩，但偏好已丢 —— 静默数据损坏，必须拦。
                            // 校验：能 base64 解出、且解出的是 {...} 对象才算合法。
                            if (!IsValidPrefs(pv))
                            {
                                prefsSkipped = true;
                            }
                            else
                            {
                                App.PREFS = pv;
                                if (WriteIniKey("prefs", pv)) restored++;
                            }
                        }
                    }
                }

                if (restored == 0)
                {
                    msg = prefsSkipped
                        ? "文件里的界面偏好数据已损坏（不是合法的 base64 JSON），已跳过，其它项也没有可导入内容"
                        : "文件里没有可导入的内容（格式不对？）";
                    return false;
                }

                msg = "已导入 " + restored + " 项配置（旧配置备份为 *.bak." + stamp
                    + "），重启应用后生效";
                if (prefsSkipped)
                    msg += "；界面偏好数据损坏已跳过（原偏好保持不变）";
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

        // ==================== prefs 合法性校验（2026-11-21）====================
        //
        // prefs.txt 里存的是前端 `btoa(unescape(encodeURIComponent(JSON.stringify(o))))`
        // 得到的串，解码后必须是一个 JSON **对象**（以 { 开头、以 } 结尾）。
        //
        // 为什么必须校验：导入是"覆盖"语义。一个损坏的 .adtprofile（手工改过、
        // 或别的程序生成）如果带着垃圾 prefs，会把用户真实的界面偏好永久写坏。
        // 前端 parsePrefs 的 try/catch 只能保证"不崩"，保证不了"偏好不丢"。
        //
        // 只做形状判断，不解析具体字段 —— C# 5.0 不引 JSON 库，
        // 而"是不是一个对象 + 有没有认识的字段"这两条就足以挡住垃圾数据。
        //
        // 2026-11-21 补充：光判"是不是对象"挡不住 {"test":"true"} 这种
        // 结构合法但字段全不认识的垃圾。所以再加一条：**必须至少包含一个
        // 已知的偏好键**（与前端 applyAllPrefs 认识的字段保持一致）。
        // 这样"别人的配置"或"乱改的文件"都被拦下，不会覆盖真实偏好。
        private static readonly string[] KNOWN_PREF_KEYS = new string[]
        {
            "font", "custom", "size", "accent", "accentByDevice",
            "logshow", "logShow", "oled", "eye", "auto",
            "uiSplit", "navOrder", "tabOrder"
        };

        private static bool IsValidPrefs(string b64)
        {
            if (string.IsNullOrEmpty(b64)) return false;
            try
            {
                // 长度粗判：合法 prefs 至少十几个字符；过长直接拒（防误把大文件塞进来）
                if (b64.Length < 8 || b64.Length > 64 * 1024) return false;

                byte[] raw = Convert.FromBase64String(b64);   // 不是合法 base64 会抛异常
                if (raw.Length == 0) return false;

                string js = Encoding.UTF8.GetString(raw).Trim();
                if (js.Length < 2) return false;

                // 必须是一个 JSON 对象：首尾是花括号。
                // 数组 / 裸字符串 / HTML 之类一律拒绝。
                if (js[0] != '{' || js[js.Length - 1] != '}') return false;

                // 必须含至少一个已知偏好键，否则视为"不是本工具的偏好"
                for (int i = 0; i < KNOWN_PREF_KEYS.Length; i++)
                {
                    // 按 "key": 的形式找，避免子串误命中（如 size 命中 resize）
                    if (js.IndexOf("\"" + KNOWN_PREF_KEYS[i] + "\"", StringComparison.Ordinal) >= 0)
                        return true;
                }
                return false;
            }
            catch
            {
                // Base64 解码失败 / UTF8 非法 → 视为损坏
                return false;
            }
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
