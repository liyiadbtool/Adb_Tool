// ============================================================================
//  Ffmpeg.cs - 录屏编码器的"找 + 验 + 记住"（R9）
//
//  背景：
//    车机屏幕带 FLAG_SECURE，screenrecord 录到 0 帧，只能走"截帧 + ffmpeg 合成"。
//    而 ffmpeg.exe 有 105MB，不可能塞进安装包（尤其是单文件版）。
//    所以改成：**用户自带**，工具负责自动找到它、验证它、并记住位置。
//
//  四级查找（顺序固定，先命中先用）：
//    1) ini 的 ffmpeg=（上次选过/手写的，最优先 —— 用户明确指定就该听他的）
//    2) exe 同级 ffmpeg.exe（绿色版最常见的摆法，含 exe\ffmpeg\bin\ffmpeg.exe）
//    3) PATH 里的 ffmpeg.exe（装过 gyan.dev / winget / scoop 的多半在这）
//    4) 常见安装位置（LocalAppData、C:\ffmpeg、Program Files、scoop、chocolatey）
//
//  为什么每一级都要"跑一次 -version"：
//    光看文件名不够。真实踩过：某机器上有个同名的 ffmpeg.exe 是坏文件（0 字节），
//    File.Exists 通过，编码时才报"不是有效的 Win32 程序"。
//    校验条件：进程能起、退出码 0、输出里有 "ffmpeg version"。
//    代价是每次约 100~300ms，所以命中的结果会缓存（ClearCache 可强制重来）。
//
//  本文件是纯逻辑，不碰 UI：GUI 和命令行都调它，避免"两处各写一套查找"。
// ============================================================================
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;

namespace AdbLogExport
{
    internal static class Ffmpeg
    {
        internal const string IniKey = "ffmpeg";

        // 来源级别：报告给用户看"从哪找到的"，出问题时能判断该改哪里
        internal const int LvIni = 1;
        internal const int LvExe = 2;
        internal const int LvPath = 3;
        internal const int LvCommon = 4;

        internal static string LevelText(int lv)
        {
            if (lv == LvIni) return "ini 配置";
            if (lv == LvExe) return "程序同级";
            if (lv == LvPath) return "系统 PATH";
            if (lv == LvCommon) return "常见安装位置";
            return "";
        }

        // 命中缓存：rec 命令每次编码都会问一次，没必要每次重新 -version
        private static string _cachedPath = null;
        private static string _cachedSrc = "";
        private static string _cachedVer = "";

        internal static void ClearCache()
        {
            _cachedPath = null;
            _cachedSrc = "";
            _cachedVer = "";
        }

        internal static string DefaultIniPath()
        {
            // 2026-11-19：新布局 internal\ 优先，其次 exe 同级（老布局/便携）
            string b = AppDomain.CurrentDomain.BaseDirectory;
            string p = Path.Combine(b, "internal", "adb_log_export.ini");
            if (File.Exists(p)) return p;
            return Path.Combine(b, "adb_log_export.ini");
        }

        // ---------------- 候选枚举 ----------------

        /// <summary>
        /// 按优先级列出所有候选路径（去重、保序）。levels 与之一一对应。
        /// 只做"路径存在性"以外的事情交给 Locate —— 单独暴露出来是为了
        /// 在找不到时能告诉用户"我一共找过这 12 个地方"。
        /// </summary>
        internal static List<string> Candidates(out List<int> levels)
        {
            List<string> list = new List<string>();
            // out 参数不能被匿名方法捕获（CS1628），先记在局部变量里，最后再赋值
            List<int> lvls = new List<int>();
            Dictionary<string, bool> seen = new Dictionary<string, bool>(StringComparer.OrdinalIgnoreCase);

            string baseDir = AppDomain.CurrentDomain.BaseDirectory;

            Action<string, int> add = delegate(string p, int lv)
            {
                if (string.IsNullOrEmpty(p)) return;
                string full;
                try { full = Path.GetFullPath(p); }
                catch { return; }
                if (seen.ContainsKey(full)) return;
                seen[full] = true;
                list.Add(full);
                lvls.Add(lv);
            };

            // 1) ini 明确配置
            string cfg = App.FFMPEG;
            if (!string.IsNullOrEmpty(cfg))
            {
                string c = cfg.Trim().Trim('"');
                // 默认值 "ffmpeg.exe" 是"没配"的意思，不算用户指定
                if (c.Length > 0 && !string.Equals(c, "ffmpeg.exe", StringComparison.OrdinalIgnoreCase))
                {
                    if (!Path.IsPathRooted(c)) c = Path.Combine(baseDir, c);
                    // 允许只写到目录：自动补 ffmpeg.exe
                    try
                    {
                        if (Directory.Exists(c)) c = Path.Combine(c, "ffmpeg.exe");
                    }
                    catch { }
                    add(c, LvIni);
                }
            }

            // 2) exe 同级
            add(Path.Combine(baseDir, "ffmpeg.exe"), LvExe);
            add(Path.Combine(baseDir, "ffmpeg", "bin", "ffmpeg.exe"), LvExe);
            add(Path.Combine(baseDir, "bin", "ffmpeg.exe"), LvExe);

            // 3) PATH
            try
            {
                string pathEnv = Environment.GetEnvironmentVariable("PATH");
                if (!string.IsNullOrEmpty(pathEnv))
                {
                    string[] parts = pathEnv.Split(';');
                    for (int i = 0; i < parts.Length; i++)
                    {
                        string d = parts[i].Trim().Trim('"');
                        if (d.Length == 0) continue;
                        add(Path.Combine(d, "ffmpeg.exe"), LvPath);
                    }
                }
            }
            catch { }

            // 4) 常见位置
            string local = "";
            try { local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData); } catch { }
            string pf = "";
            try { pf = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles); } catch { }
            string pf86 = "";
            try { pf86 = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86); } catch { }
            string user = "";
            try { user = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile); } catch { }

            if (!string.IsNullOrEmpty(local))
            {
                // 工具自己的数据目录：文档里推荐"把 ffmpeg.exe 放这儿"
                add(Path.Combine(local, "adb_Tool", "ffmpeg.exe"), LvCommon);
                add(Path.Combine(local, "adb_Tool", "ffmpeg", "bin", "ffmpeg.exe"), LvCommon);
                add(Path.Combine(local, "Microsoft", "WinGet", "Links", "ffmpeg.exe"), LvCommon);
            }
            add(@"C:\ffmpeg\bin\ffmpeg.exe", LvCommon);
            add(@"C:\ffmpeg\ffmpeg.exe", LvCommon);
            if (!string.IsNullOrEmpty(pf)) add(Path.Combine(pf, "ffmpeg", "bin", "ffmpeg.exe"), LvCommon);
            if (!string.IsNullOrEmpty(pf86)) add(Path.Combine(pf86, "ffmpeg", "bin", "ffmpeg.exe"), LvCommon);
            if (!string.IsNullOrEmpty(user)) add(Path.Combine(user, "scoop", "shims", "ffmpeg.exe"), LvCommon);
            add(@"C:\ProgramData\chocolatey\bin\ffmpeg.exe", LvCommon);

            levels = lvls;
            return list;
        }

        // ---------------- 查找 ----------------

        /// <summary>
        /// 四级查找，命中返回完整路径，否则返回空串。
        /// 命中结果会缓存；想强制重扫用 LocateFresh。
        /// </summary>
        internal static string Locate(out string source, out string version, out string err)
        {
            if (_cachedPath != null)
            {
                source = _cachedSrc;
                version = _cachedVer;
                err = "";
                return _cachedPath;
            }
            return LocateFresh(out source, out version, out err);
        }

        internal static string LocateFresh(out string source, out string version, out string err)
        {
            source = "";
            version = "";
            err = "";

            List<int> lvs;
            List<string> cands = Candidates(out lvs);
            int tried = 0;
            List<string> bad = new List<string>();

            for (int i = 0; i < cands.Count; i++)
            {
                bool exists = false;
                try { exists = File.Exists(cands[i]); }
                catch { }
                if (!exists) continue;

                tried++;
                string ver = "";
                string e = "";
                if (Validate(cands[i], out ver, out e))
                {
                    _cachedPath = cands[i];
                    _cachedSrc = LevelText(lvs[i]);
                    _cachedVer = ver;
                    source = _cachedSrc;
                    version = ver;
                    return cands[i];
                }
                bad.Add(cands[i] + "（" + e + "）");
            }

            // 没找到：把"找过哪里"说清楚，用户才知道下一步该做什么。
            // 只说"找不到"会让人反复点重试。
            StringBuilder sb = new StringBuilder();
            sb.Append("没有可用的 ffmpeg.exe（检查了 ").Append(cands.Count).Append(" 个位置");
            if (tried > 0) sb.Append("，其中 ").Append(tried).Append(" 个存在但校验失败");
            sb.Append("）。");
            sb.Append("把 ffmpeg.exe 放到程序同级目录，或点「选择…」手动指定。");
            if (bad.Count > 0) sb.Append(" 失败明细：").Append(string.Join("；", bad.ToArray()));
            err = sb.ToString();
            return "";
        }

        // ---------------- 校验 ----------------

        /// <summary>
        /// 跑 `ffmpeg -version` 验证这是真的 ffmpeg。
        /// 不用 File.Exists 就完事：同名坏文件 / 0 字节 / 别的程序改名都会在这里被挡掉。
        /// </summary>
        internal static bool Validate(string path, out string version, out string err)
        {
            version = "";
            err = "";
            if (string.IsNullOrEmpty(path) || !File.Exists(path))
            {
                err = "文件不存在";
                return false;
            }

            try
            {
                ProcessStartInfo psi = new ProcessStartInfo();
                psi.FileName = path;
                psi.Arguments = "-version";
                psi.UseShellExecute = false;
                psi.CreateNoWindow = true;
                psi.RedirectStandardOutput = true;
                psi.RedirectStandardError = true;

                using (Process p = new Process())
                {
                    p.StartInfo = psi;
                    try { p.Start(); }
                    catch (Exception ex)
                    {
                        err = "无法运行（" + FirstLine(ex.Message) + "）";
                        return false;
                    }

                    string o = "";
                    string e = "";
                    try { o = p.StandardOutput.ReadToEnd(); } catch { }
                    try { e = p.StandardError.ReadToEnd(); } catch { }

                    if (!p.WaitForExit(6000))
                    {
                        try { p.Kill(); } catch { }
                        err = "运行超时（可能不是 ffmpeg）";
                        return false;
                    }
                    if (p.ExitCode != 0)
                    {
                        err = "退出码 " + p.ExitCode;
                        return false;
                    }

                    string all = o + "\n" + e;
                    string ver = ParseVersion(all);
                    if (ver.Length == 0)
                    {
                        err = "输出里没有 ffmpeg 版本信息（不是 ffmpeg？）";
                        return false;
                    }
                    version = ver;
                    return true;
                }
            }
            catch (Exception ex)
            {
                err = FirstLine(ex.Message);
                return false;
            }
        }

        /// <summary>
        /// 从 `ffmpeg -version` 的输出里抠版本号。纯函数，便于自检。
        /// 典型首行：ffmpeg version 6.1.1-full_build-www.gyan.dev Copyright (c) ...
        /// 也见过：ffmpeg version N-109000-g1234567 Copyright ...
        /// </summary>
        internal static string ParseVersion(string output)
        {
            if (string.IsNullOrEmpty(output)) return "";
            string low = output.ToLowerInvariant();
            int i = low.IndexOf("ffmpeg version ");
            if (i < 0) return "";
            int s = i + "ffmpeg version ".Length;
            int e = s;
            while (e < output.Length)
            {
                char c = output[e];
                if (c == ' ' || c == '\r' || c == '\n' || c == '\t') break;
                e++;
            }
            if (e <= s) return "";
            string v = output.Substring(s, e - s).Trim();
            // 太长的当噪声（版本号不会超过 40 字符）
            if (v.Length > 40) return "";
            return v;
        }

        // ---------------- 应用 / 持久化 ----------------

        /// <summary>
        /// 校验并采用这个 ffmpeg：成功则写回 ini（下次自动记住）并立即生效。
        /// GUI 的「选择…」和命令行的 `:ffmpeg 路径` 都走这里，保证行为一致。
        /// </summary>
        internal static bool Use(string path, out string version, out string err)
        {
            version = "";
            err = "";
            string p = (path == null) ? "" : path.Trim().Trim('"');
            if (p.Length == 0) { err = "路径为空"; return false; }

            try
            {
                if (Directory.Exists(p)) p = Path.Combine(p, "ffmpeg.exe");
                if (!Path.IsPathRooted(p)) p = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, p);
                p = Path.GetFullPath(p);
            }
            catch (Exception ex) { err = "路径无效：" + ex.Message; return false; }

            string ver = "";
            string ve = "";
            if (!Validate(p, out ver, out ve))
            {
                err = "不是可用的 ffmpeg：" + ve;
                return false;
            }

            string se = "";
            if (!SaveKey(IniKey, p, out se))
            {
                // 写 ini 失败不算致命：本次会话仍然用它，只是下次要重新选
                err = "已生效，但保存配置失败：" + se;
            }

            ClearCache();
            _cachedPath = p;
            _cachedSrc = LevelText(LvIni);
            _cachedVer = ver;
            App.FFMPEG = p;
            version = ver;
            return true;
        }

        /// <summary>
        /// 改写 ini 里的一个键：保留其它行与注释顺序，只替换值（没有就追加）。
        /// 不整文件重写的原因是 ini 里有大量用户手写注释，重排会让人找不到东西。
        /// </summary>
        internal static bool SaveKey(string key, string value, out string err)
        {
            return SaveKeyTo(DefaultIniPath(), key, value, out err);
        }

        /// <summary>
        /// 改写指定 ini 文件里的一个键。抽出来是为了让自检能在临时文件上跑，
        /// 不去动用户真正的 adb_log_export.ini。
        /// </summary>
        internal static bool SaveKeyTo(string iniPath, string key, string value, out string err)
        {
            err = "";
            string p = iniPath;
            try
            {
                List<string> lines = new List<string>();
                if (File.Exists(p))
                {
                    string[] old = File.ReadAllLines(p, Encoding.UTF8);
                    for (int i = 0; i < old.Length; i++) lines.Add(old[i]);
                }

                bool done = false;
                for (int i = 0; i < lines.Count; i++)
                {
                    string s = lines[i].Trim();
                    if (s.Length == 0 || s[0] == '#' || s[0] == ';' || s[0] == '[') continue;
                    int eq = s.IndexOf('=');
                    if (eq <= 0) continue;
                    string k = s.Substring(0, eq).Trim();
                    if (!string.Equals(k, key, StringComparison.OrdinalIgnoreCase)) continue;
                    lines[i] = key + "=" + value;
                    done = true;
                    break;
                }

                if (!done)
                {
                    if (lines.Count > 0 && lines[lines.Count - 1].Trim().Length > 0) lines.Add("");
                    lines.Add("# 录屏编码器（点界面上的「选择…」会自动写入这一行）");
                    lines.Add(key + "=" + value);
                }

                // 保留 BOM：其它工具（记事本）靠它判断 UTF-8
                File.WriteAllLines(p, lines.ToArray(), new UTF8Encoding(true));
                return true;
            }
            catch (Exception ex)
            {
                err = ex.Message;
                return false;
            }
        }

        // ---------------- 给界面用的一行状态 ----------------

        internal static string StatusLine(out bool ok, out string path, out string source, out string version)
        {
            string src = "";
            string ver = "";
            string e = "";
            string p = Locate(out src, out ver, out e);
            path = p;
            source = src;
            version = ver;
            ok = (p.Length > 0);
            if (!ok) return e;
            return p + "（" + src + (ver.Length > 0 ? "，" + ver : "") + "）";
        }

        private static string FirstLine(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            int i = s.IndexOfAny(new char[] { '\r', '\n' });
            if (i < 0) return s.Trim();
            return s.Substring(0, i).Trim();
        }
    }
}
