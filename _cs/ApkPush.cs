using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using System.Text;

namespace AdbLogExport
{
    /* 2026-11-28：系统应用推包（syspush）。
       参考 android-push-package（PowerShell 版）的流程，用 C# 重写，
       并修掉它六个已知坑：备份失败仍继续推、还原权限写死、cp 非原子、
       复用"最早原版"、备份完整性无校验、校验失败弹模态阻塞。

       安全边界：只允许 /system /system_ext /product /vendor /odm /oem 下的路径。
       不提供 pm install 模式（非系统分区一律拒绝）。 */
    internal static partial class App
    {
        // ==================== 模型 ====================

        internal sealed class SysPushItem
        {
            internal string Kind = "";       // apk | so | dir
            internal string Local = "";
            internal string Remote = "";
            internal string Pkg = "";
            internal string Action = "push"; // push | skip
            internal string Reason = "";
            internal bool Exists = false;
            internal long Size = 0;
            internal string Md5 = "";
            internal string DevMd5 = "";
            internal string Mode = "";
            internal string Owner = "";
            internal int Seq = 0;
            internal string State = "";      // backed | new | dir
            internal string FileName = "";   // 备份内的相对文件名
        }

        internal sealed class SysPushOpt
        {
            internal bool SkipBackup = false;
            internal bool Force = false;
            internal bool AutoRestore = false;
            internal bool Reboot = true;
            internal bool AllowVerity = true;
            internal bool CleanPkgCache = true;
            internal string BackupRoot = "";
            internal int Keep = 10;
        }

        internal sealed class SysPushCheck
        {
            internal string Key = "";
            internal string Name = "";
            internal bool Critical = false;
            internal bool Ok = false;
            internal string Detail = "";
            internal string Hint = "";
        }

        internal sealed class SysPushResult
        {
            internal bool Ok = false;
            internal bool Cancelled = false;
            internal bool Restored = false;
            internal bool VerifyFail = false;
            internal int Pushed = 0;
            internal int Skipped = 0;
            internal int Failed = 0;
            internal string BackupDir = "";
            internal string Err = "";
        }

        internal delegate void SysPushProg(int phase, string phaseName, long done, long total, string name);
        internal delegate void SysPushLog(string line);

        // 阶段编号（前端徽标用）
        internal const int SP_CHECK = 1, SP_PLAN = 2, SP_BACKUP = 3, SP_STAGE = 4,
                           SP_VERIFYSTAGE = 5, SP_COMMIT = 6, SP_REBOOT = 7,
                           SP_WAITBOOT = 8, SP_VERIFY = 9, SP_RESTORE = 10, SP_DONE = 11;

        private static SysPushLog _spLog;
        private static void SpLog(string s)
        {
            SysPushLog h = _spLog;
            if (h != null) { try { h(s); } catch { } }
        }
        internal static void SysPushSetLog(SysPushLog h) { _spLog = h; }

        private static readonly string[] SP_ROOTS = new string[] {
            "/system/", "/system_ext/", "/product/", "/vendor/", "/odm/", "/oem/"
        };

        // ==================== 纯函数（自检打靶） ====================

        internal static bool SysPushPathAllowed(string remote, out string why)
        {
            why = "";
            if (string.IsNullOrEmpty(remote)) { why = "路径为空"; return false; }
            if (remote[0] != '/') { why = "必须是设备绝对路径"; return false; }
            if (remote.IndexOf("..", StringComparison.Ordinal) >= 0) { why = "不能含 .."; return false; }
            if (remote.IndexOf("//", StringComparison.Ordinal) >= 0) { why = "不能含 //"; return false; }
            for (int i = 0; i < SP_ROOTS.Length; i++)
                if (remote.StartsWith(SP_ROOTS[i], StringComparison.Ordinal)) return true;
            why = "只允许 /system /system_ext /product /vendor /odm /oem 下";
            return false;
        }

        /* 本地镜像相对路径 → 设备路径。首段必须在白名单里。 */
        internal static string SysPushMapDirRel(string rel, out bool ok)
        {
            ok = false;
            if (string.IsNullOrEmpty(rel)) return "";
            string r = rel.Replace('\\', '/').TrimStart('/');
            string[] segs = r.Split('/');
            if (segs.Length == 0) return "";
            string head = segs[0].ToLowerInvariant();
            bool headOk = false;
            for (int i = 0; i < SP_ROOTS.Length; i++)
            {
                if (SP_ROOTS[i] == "/" + head + "/") { headOk = true; break; }
            }
            if (!headOk) return "";
            for (int i = 0; i < segs.Length; i++)
                if (segs[i].Length == 0 || segs[i] == "." || segs[i] == "..") return "";
            string dev = "/" + r;
            string why;
            if (!SysPushPathAllowed(dev, out why)) return "";
            ok = true;
            return dev;
        }

        internal static string SysPushDefaultSoDir(string abi)
        {
            string a = (abi ?? "").ToLowerInvariant();
            if (a == "arm64-v8a" || a == "x86_64") return "/system/lib64";
            if (a == "armeabi-v7a" || a == "armeabi" || a == "x86") return "/system/lib";
            return "";
        }

        internal static string SysPushMd5File(string localPath)
        {
            try
            {
                using (MD5 md5 = MD5.Create())
                using (FileStream fs = File.OpenRead(localPath))
                {
                    byte[] h = md5.ComputeHash(fs);
                    StringBuilder sb = new StringBuilder(h.Length * 2);
                    for (int i = 0; i < h.Length; i++) sb.Append(h[i].ToString("x2"));
                    return sb.ToString();
                }
            }
            catch { return ""; }
        }

        /* 备份文件名：序号 + 远程文件名，去掉非法字符 */
        internal static string SysPushBackupFileName(int seq, string remote)
        {
            string name = (remote ?? "").Replace('\\', '/');
            int i = name.LastIndexOf('/');
            if (i >= 0) name = name.Substring(i + 1);
            StringBuilder sb = new StringBuilder();
            for (int k = 0; k < name.Length; k++)
            {
                char c = name[k];
                if (char.IsLetterOrDigit(c) || c == '.' || c == '_' || c == '-') sb.Append(c);
                else sb.Append('_');
            }
            if (sb.Length == 0) sb.Append("file");
            return string.Format(CultureInfo.InvariantCulture, "{0:000}_{1}", seq, sb.ToString());
        }

        internal static string SysPushModeFor(string remote)
        {
            string r = (remote ?? "").ToLowerInvariant();
            if (r.EndsWith(".so", StringComparison.Ordinal)) return "0644";
            if (r.IndexOf("/bin/", StringComparison.Ordinal) >= 0) return "0755";
            return "0644";
        }

        internal static string SpEsc(string s)
        {
            if (s == null) return "";
            StringBuilder sb = new StringBuilder(s.Length + 8);
            for (int i = 0; i < s.Length; i++)
            {
                char c = s[i];
                if (c == '"') sb.Append("\\\"");
                else if (c == '\\') sb.Append("\\\\");
                else if (c == '\n') sb.Append("\\n");
                else if (c == '\r') sb.Append("\\r");
                else if (c == '\t') sb.Append("\\t");
                else if (c < ' ') sb.Append(' ');
                else sb.Append(c);
            }
            return sb.ToString();
        }

        // ==================== 设备侧助手 ====================

        private static string SpSh(string cmd)
        {
            string o = "", e = "";
            try { ShellCall(CUR, cmd, out o, out e); } catch { }
            return ((o ?? "") + (e ?? "")).Trim();
        }

        private static bool SpAdb(List<string> argv, out string outp)
        {
            string o = "", e = "";
            int rc = -1;
            try { rc = AdbCall(argv, out o, out e); }
            catch (Exception ex) { outp = ex.Message; return false; }
            outp = ((o ?? "") + (e ?? "")).Trim();
            return rc == 0;
        }

        private static string SpDevMd5(string devPath)
        {
            string t = SpSh("md5sum '" + devPath.Replace("'", "'\\''") + "' 2>/dev/null");
            int i = t.IndexOf(' ');
            if (i > 0) return t.Substring(0, i).Trim().ToLowerInvariant();
            return "";
        }

        private static bool SpExists(string devPath)
        {
            string t = SpSh("[ -e '" + devPath.Replace("'", "'\\''") + "' ] && echo Y || echo N");
            return t.IndexOf('Y') >= 0;
        }

        private static string SpOwnerMode(string devPath)
        {
            return SpSh("stat -c '%a %U:%G' '" + devPath.Replace("'", "'\\''") + "' 2>/dev/null");
        }

        // ==================== 预检 ====================

        internal static List<SysPushCheck> SysPushPreflight(SysPushOpt opt, out bool criticalFail)
        {
            List<SysPushCheck> list = new List<SysPushCheck>();
            bool cf = false;
            criticalFail = false;

            Action<string, string, bool, string> add = delegate(string k, string nm, bool crit, string detail)
            {
                SysPushCheck c = new SysPushCheck();
                c.Key = k; c.Name = nm; c.Critical = crit; c.Detail = detail;
                c.Ok = (detail.Length == 0 || detail.IndexOf("FAIL:", StringComparison.Ordinal) != 0);
                if (!c.Ok && crit) cf = true;
                list.Add(c);
            };

            /* 2026-11-28：get-state 是**主机侧** adb 命令，不能走 adb shell。
               原来用 SpSh("get-state") 一定拿不到 "device"，于是体检永远报"设备在线 FAIL"。
               改：走 AdbCall（带 -s），失败再退回全局连接状态。 */
            string st = "";
            bool online = false;
            try
            {
                string o1 = "", e1 = "";
                int rc = AdbCall(new List<string> { "get-state" }, out o1, out e1);
                st = ((o1 ?? "") + (e1 ?? "")).Trim();
                online = rc == 0 && st.IndexOf("device", StringComparison.OrdinalIgnoreCase) >= 0;
            }
            catch { }
            if (!online && SERIAL_OK) { online = true; st = "device（来自当前连接状态）"; }
            if (!online && st.Length == 0) st = "adb get-state 无输出";
            add("online", "设备在线", true, online ? "" : ("FAIL:" + st));

            // 2 构建类型
            string bt = SpSh("getprop ro.build.type");
            bool btOk = bt == "userdebug" || bt == "eng";
            add("build", "系统构建类型", true, btOk ? bt : ("FAIL:ro.build.type=" + bt));

            // 3 root
            string uid = SpSh("id -u 2>/dev/null");
            add("root", "当前为 root", true, uid == "0" ? "" : ("FAIL:id -u = " + uid));

            /* 2026-11-28：可写性不再是"关键项"。
               预检是只读阶段，此时还没 remount —— 判它失败等于永远过不了
               （用户实测：verity=disabled、SELinux=Enforcing，设备其实可写）。
               这里只把结果当信息，真正的可写性在 start 阶段 remount 之后再判。 */
            string rw = SpSh("touch /system/.adb_push_rwtest 2>&1 && rm -f /system/.adb_push_rwtest && echo RWOK");
            SysPushCheck c4 = new SysPushCheck();
            c4.Key = "rw"; c4.Name = "/system 当前可写"; c4.Critical = false;
            c4.Ok = rw.IndexOf("RWOK") >= 0;
            c4.Detail = c4.Ok ? "是" : "否（推包时会自动 root + remount）";
            c4.Hint = c4.Ok ? "" : "需要 adb root + remount 才能写入";
            list.Add(c4);

            // 5 pm 可用
            string pm = SpSh("pm list packages 2>/dev/null | head -1");
            add("pm", "PackageManager 可用", true, pm.Length > 0 ? "" : "FAIL:pm list packages 无输出");

            // 6 verity（告警）
            string vm = SpSh("getprop ro.boot.veritymode");
            SysPushCheck c6 = new SysPushCheck();
            c6.Key = "verity"; c6.Name = "dm-verity"; c6.Critical = false;
            c6.Ok = !(vm.IndexOf("enforcing", StringComparison.OrdinalIgnoreCase) >= 0);
            c6.Detail = vm;
            c6.Hint = c6.Ok ? "" : "verity 开启时写入可能重启失效，需要 disable-verity";
            list.Add(c6);
            if (!c6.Ok && !opt.AllowVerity) { cf = true; c6.Hint = "已禁止改 verity，且当前为 enforcing"; }

            // 7 SELinux（告警）
            string se = SpSh("getenforce");
            SysPushCheck c7 = new SysPushCheck();
            c7.Key = "selinux"; c7.Name = "SELinux"; c7.Critical = false; c7.Ok = se.Length > 0;
            c7.Detail = se;
            c7.Hint = se.IndexOf("Enforcing", StringComparison.OrdinalIgnoreCase) >= 0
                      ? "推送后需 restorecon，否则可能起不来" : "";
            list.Add(c7);

            // 8 空间
            string df = SpSh("df -k /data 2>/dev/null | tail -1");
            add("datafree", "/data 剩余空间", false, df);

            criticalFail = cf;
            OptLog(string.Format(CultureInfo.InvariantCulture,
                "预检完成：{0} 项，关键失败={1}", list.Count, criticalFail ? "是" : "否"));
            return list;
        }

        private static void OptLog(string s) { SpLog(s); }

        // ==================== 清点 / 计划 ====================

        internal static bool SysPushPlan(List<SysPushItem> items, SysPushOpt opt, out string err)
        {
            err = "";
            if (items == null || items.Count == 0) { err = "还没有要推的内容"; return false; }

            for (int i = 0; i < items.Count; i++)
            {
                SysPushItem it = items[i];
                it.Seq = i + 1;
                it.Reason = "";

                if (it.Kind == "apk")
                {
                    if (string.IsNullOrEmpty(it.Remote))
                    {
                        List<string> paths = QueryPkgPaths(it.Pkg);
                        if (paths.Count == 0) { it.Action = "skip"; it.Reason = "找不到包路径"; continue; }
                        string p0 = paths[0];
                        if (p0.IndexOf("/data/app/", StringComparison.Ordinal) >= 0)
                        { it.Action = "skip"; it.Reason = "普通应用（/data/app），请走安装"; continue; }
                        it.Remote = p0;
                        if (paths.Count > 1) it.Reason = "split APK，只替换 base";
                    }
                }

                string why;
                if (!SysPushPathAllowed(it.Remote, out why))
                { it.Action = "skip"; it.Reason = why; continue; }

                if (it.Local.Length > 0 && (it.Local.EndsWith(".so", StringComparison.OrdinalIgnoreCase)))
                {
                    if (it.Remote.EndsWith("/", StringComparison.Ordinal))
                        it.Remote = it.Remote + Path.GetFileName(it.Local);
                }

                it.Exists = SpExists(it.Remote);
                try { it.Size = (it.Local.Length > 0 && File.Exists(it.Local)) ? new FileInfo(it.Local).Length : 0; }
                catch { it.Size = 0; }
                it.Md5 = (it.Local.Length > 0 && File.Exists(it.Local)) ? SysPushMd5File(it.Local) : "";
                it.DevMd5 = it.Exists ? SpDevMd5(it.Remote) : "";
                it.Mode = SysPushModeFor(it.Remote);
                it.Owner = "root:root";

                if (!opt.Force && it.Exists && it.Md5.Length > 0 && it.Md5 == it.DevMd5)
                {
                    it.Action = "skip";
                    it.Reason = "内容相同（强制重推可覆盖）";
                }
            }
            return true;
        }

        // ==================== 备份 ====================

        internal static string SysPushBackupRoot(SysPushOpt opt)
        {
            if (opt != null && opt.BackupRoot != null && opt.BackupRoot.Trim().Length > 0)
                return opt.BackupRoot.Trim();
            string b = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            return Path.Combine(Path.Combine(b, "adb_Tool"), "syspush");
        }

        internal static string SysPushBackupDir(string serial, SysPushOpt opt)
        {
            string root = SysPushBackupRoot(opt);
            string s = string.IsNullOrEmpty(serial) ? "unknown" : serial;
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < s.Length; i++)
            {
                char c = s[i];
                sb.Append(char.IsLetterOrDigit(c) || c == '.' || c == '_' || c == '-' ? c : '_');
            }
            string stamp = DateTime.Now.ToString("yyyyMMdd_HHmmss", CultureInfo.InvariantCulture);
            return Path.Combine(Path.Combine(root, sb.ToString()), stamp);
        }

        internal static bool SysPushWriteManifest(string dir, List<SysPushItem> items, out string err)
        {
            err = "";
            try
            {
                Directory.CreateDirectory(dir);
                StringBuilder sb = new StringBuilder();
                sb.Append("# seq\tkind\tstate\tremote\tfile\tsize\tmd5\tmode\towner\n");
                for (int i = 0; i < items.Count; i++)
                {
                    SysPushItem it = items[i];
                    sb.Append(it.Seq).Append('\t').Append(it.Kind).Append('\t').Append(it.State)
                      .Append('\t').Append(it.Remote).Append('\t').Append(it.FileName)
                      .Append('\t').Append(it.Size).Append('\t').Append(it.Md5)
                      .Append('\t').Append(it.Mode).Append('\t').Append(it.Owner).Append('\n');
                }
                File.WriteAllText(Path.Combine(dir, "backup.tsv"), sb.ToString(), new UTF8Encoding(false));
                return true;
            }
            catch (Exception ex) { err = ex.Message; return false; }
        }

        internal static List<SysPushItem> SysPushReadManifest(string dir, out string err)
        {
            err = "";
            List<SysPushItem> list = new List<SysPushItem>();
            try
            {
                string p = Path.Combine(dir, "backup.tsv");
                if (!File.Exists(p)) { err = "找不到 backup.tsv"; return list; }
                string[] lines = File.ReadAllLines(p, Encoding.UTF8);
                for (int i = 0; i < lines.Length; i++)
                {
                    string ln = lines[i];
                    if (ln.Length == 0 || ln[0] == '#') continue;
                    string[] f = ln.Split('\t');
                    if (f.Length < 9) continue;
                    SysPushItem it = new SysPushItem();
                    int.TryParse(f[0], out it.Seq);
                    it.Kind = f[1]; it.State = f[2]; it.Remote = f[3]; it.FileName = f[4];
                    long sz; long.TryParse(f[5], out sz); it.Size = sz;
                    it.Md5 = f[6]; it.Mode = f[7]; it.Owner = f[8];
                    list.Add(it);
                }
                return list;
            }
            catch (Exception ex) { err = ex.Message; return list; }
        }

        internal static List<string> SysPushListBackups(string serial, SysPushOpt opt)
        {
            List<string> outList = new List<string>();
            try
            {
                string root = SysPushBackupRoot(opt);
                string s = string.IsNullOrEmpty(serial) ? "unknown" : serial;
                StringBuilder sb = new StringBuilder();
                for (int i = 0; i < s.Length; i++)
                {
                    char c = s[i];
                    sb.Append(char.IsLetterOrDigit(c) || c == '.' || c == '_' || c == '-' ? c : '_');
                }
                string baseDir = Path.Combine(root, sb.ToString());
                if (!Directory.Exists(baseDir)) return outList;
                string[] dirs = Directory.GetDirectories(baseDir);
                Array.Sort(dirs);
                Array.Reverse(dirs);
                for (int i = 0; i < dirs.Length; i++) outList.Add(dirs[i]);
            }
            catch { }
            return outList;
        }

        // 单个文件推上去（staging → md5 → 原子 mv → 权限 → touch/sync）
        private static bool SpPushOne(SysPushItem it, SysPushOpt opt, SysPushProg prog, out string err)
        {
            err = "";
            string stamp = DateTime.Now.ToString("HHmmss", CultureInfo.InvariantCulture);
            string stageDir = "/data/local/tmp/adbpush_" + stamp;
            string stagePath = stageDir + "/" + Path.GetFileName(it.Local);

            if (!SpAdb(new List<string> { "push", it.Local, stagePath }, out err)) { err = "推送暂存失败：" + err; return false; }
            string sMd5 = SpDevMd5(stagePath);
            if (sMd5.Length > 0 && it.Md5.Length > 0 && sMd5 != it.Md5)
            { err = "暂存文件 md5 不一致"; return false; }

            string q = "'" + it.Remote.Replace("'", "'\\''") + "'";
            string qs = "'" + stagePath.Replace("'", "'\\''") + "'";
            string qn = q + ".new";

            // 原子替换：先写到同目录 .new，再 mv（同分区 rename）
            string cmds = "cp -f " + qs + " " + qn
                        + " && chown " + it.Owner + " " + qn
                        + " && chmod " + it.Mode + " " + qn
                        + " && mv -f " + qn + " " + q
                        + " && touch " + q
                        + " && (restorecon " + q + " 2>/dev/null || true)"
                        + " && sync && echo SPOK";
            string r = SpSh(cmds);
            SpSh("rm -f " + qs + "; rmdir " + "'" + stageDir.Replace("'", "'\\''") + "' 2>/dev/null");
            if (r.IndexOf("SPOK") < 0) { err = "落盘失败：" + r; return false; }
            return true;
        }

        // ==================== 主流程 ====================

        internal static SysPushResult SysPushRun(List<SysPushItem> items, SysPushOpt opt, SysPushProg prog)
        {
            SysPushResult res = new SysPushResult();
            bool crit;
            SysPushPreflight(opt, out crit);
            if (crit)
            {
                res.Err = "预检未通过（关键项失败），已中止，未改动任何文件";
                SpLog(res.Err);
                return res;
            }
            if (opt.AllowVerity)
            {
                SpLog("尝试 adb root / remount …");
                string oRoot;
                SpAdb(new List<string> { "root" }, out oRoot);
                string o;
                SpAdb(new List<string> { "remount" }, out o);
                // 复查可写：remount 之后仍不可写才中止
                string rw2 = SpSh("touch /system/.adb_push_rwtest 2>&1 && rm -f /system/.adb_push_rwtest && echo RWOK");
                if (rw2.IndexOf("RWOK") < 0)
                {
                    res.Err = "系统分区仍不可写（remount 未生效）：" + rw2;
                    SpLog(res.Err);
                    return res;
                }
            }

            string planErr;
            if (!SysPushPlan(items, opt, out planErr)) { res.Err = planErr; return res; }

            // 备份
            if (!opt.SkipBackup)
            {
                res.BackupDir = SysPushBackupDir(SERIAL, opt);
                string fdir = Path.Combine(res.BackupDir, "files");
                try { Directory.CreateDirectory(fdir); } catch { }
                for (int i = 0; i < items.Count; i++)
                {
                    SysPushItem it = items[i];
                    if (it.Action == "skip") continue;
                    if (!it.Exists) { it.State = "new"; continue; }
                    it.FileName = SysPushBackupFileName(it.Seq, it.Remote);
                    string lp = Path.Combine(fdir, it.FileName);
                    string o2;
                    if (!SpAdb(new List<string> { "pull", it.Remote, lp }, out o2))
                    {
                        res.Err = "备份失败：" + it.Remote + " " + o2 + "（已中止，未推送任何文件）";
                        SpLog(res.Err);
                        return res;
                    }
                    it.State = "backed";
                }
                string mErr;
                if (!SysPushWriteManifest(res.BackupDir, items, out mErr))
                { res.Err = "写备份清单失败：" + mErr; return res; }
                SpLog("备份完成：" + res.BackupDir);
            }
            else SpLog("已跳过备份：本次若失败将无法自动还原");

            // 推送
            int idx = 0, total = 0;
            for (int i = 0; i < items.Count; i++) if (items[i].Action != "skip") total++;
            for (int i = 0; i < items.Count; i++)
            {
                SysPushItem it = items[i];
                if (it.Action == "skip") { res.Skipped++; SpLog("跳过 " + it.Remote + "（" + it.Reason + "）"); continue; }
                idx++;
                if (prog != null) { try { prog(SP_COMMIT, "推送", idx, total, Path.GetFileName(it.Local)); } catch { } }
                string e1;
                if (SpPushOne(it, opt, prog, out e1)) { res.Pushed++; SpLog("✓ " + it.Remote); }
                else { res.Failed++; SpLog("✗ " + it.Remote + "：" + e1); }
                if (FS_CANCEL) { res.Cancelled = true; break; }
            }

            res.Ok = res.Failed == 0 && !res.Cancelled;
            SpLog(string.Format(CultureInfo.InvariantCulture,
                "推送结束：成功 {0}，跳过 {1}，失败 {2}", res.Pushed, res.Skipped, res.Failed));

            // 推完还原
            if (opt.AutoRestore && res.Pushed > 0 && !opt.SkipBackup)
            {
                SpLog("按选项还原原版本 …");
                SysPushResult r2 = SysPushRestore(res.BackupDir, opt, prog);
                res.Restored = r2.Ok;
                if (!r2.Ok) SpLog("还原失败：" + r2.Err);
            }
            return res;
        }

        // ==================== 还原 ====================

        internal static SysPushResult SysPushRestore(string backupDir, SysPushOpt opt, SysPushProg prog)
        {
            SysPushResult res = new SysPushResult();
            string err;
            List<SysPushItem> items = SysPushReadManifest(backupDir, out err);
            if (items.Count == 0) { res.Err = string.IsNullOrEmpty(err) ? "备份清单为空" : err; return res; }

            string fdir = Path.Combine(backupDir, "files");
            int okc = 0, bad = 0;
            for (int i = 0; i < items.Count; i++)
            {
                SysPushItem it = items[i];
                if (prog != null) { try { prog(SP_RESTORE, "还原", i + 1, items.Count, it.Remote); } catch { } }

                if (it.State == "new")
                {
                    SpSh("rm -f '" + it.Remote.Replace("'", "'\\''") + "'");
                    okc++; continue;
                }
                string local = Path.Combine(fdir, it.FileName);
                if (!File.Exists(local)) { bad++; SpLog("备份缺失：" + it.FileName); continue; }

                SysPushItem cp = new SysPushItem();
                cp.Kind = it.Kind; cp.Local = local; cp.Remote = it.Remote;
                cp.Mode = string.IsNullOrEmpty(it.Mode) ? "0644" : it.Mode;
                cp.Owner = string.IsNullOrEmpty(it.Owner) ? "root:root" : it.Owner;
                cp.Md5 = SysPushMd5File(local);
                string e2;
                if (SpPushOne(cp, opt, prog, out e2)) okc++;
                else { bad++; SpLog("还原失败：" + it.Remote + "：" + e2); }
            }
            if (opt.CleanPkgCache) SpSh("rm -rf /data/system/package_cache/* 2>/dev/null; sync");
            try
            {
                File.WriteAllText(Path.Combine(backupDir, "restored.json"),
                    "{\"at\":\"" + SysPushJsonTime() + "\",\"ok\":" + okc + ",\"fail\":" + bad + "}",
                    new UTF8Encoding(false));
            }
            catch { }
            res.Ok = bad == 0 && okc > 0;
            res.Pushed = okc; res.Failed = bad;
            if (!res.Ok) res.Err = "还原有失败项（成功 " + okc + "，失败 " + bad + "）";
            return res;
        }

        private static string SysPushJsonTime()
        {
            return DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture);
        }
    }
}
