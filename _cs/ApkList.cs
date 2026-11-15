// ============================================================================
//  ApkList.cs — APK 管理：用户维护的「名称 + 包名」列表
//
//  为什么要有这个文件：
//      GUI 的「APK 管理」页要让人自己录入应用（名称随便写，中文/英文都行），
//      关掉程序下次还在，还能删。原来唯一的持久化入口是 adb_log_export.ini 的
//      version_pkgs=包名=别名，只能手改 ini、界面上没法增删。
//
//  存哪里：
//      %LOCALAPPDATA%\adb_Tool\apk_apps.txt
//      和 gui_trace.log / WebView2 缓存同一个根 —— 可写数据一律进 LocalAppData，
//      不往 exe 同级写（Program Files 下会没权限）。
//      LOCALAPPDATA 取不到时退化为 exe 同级，至少不丢数据。
//
//  存成什么：
//      纯文本，一行一条「名称<TAB>包名」，UTF-8 无 BOM。
//      为什么不是 JSON：本工程锁 C# 5.0 且不许引 NuGet，现有 Json() 只能生成
//      不能解析；手写 JSON 解析器不值这个风险。TSV 解析十行就够，坏一行只丢
//      一行，用户还能拿记事本直接改。
//
//  和 version_pkgs 的关系（重要）：
//      列表文件**不存在**时，从 version_pkgs 导一次（别名当名称），之后这个文件
//      就是唯一可写源。不反向写回 ini —— ini 里有注释和用户的手写配置，重写会
//      把注释吃掉。迁移只发生一次：文件一旦存在（哪怕是空文件）就不再导入。
//
//  C# 5.0：不用插值字符串 / ?. / out var / 表达式体成员。
// ============================================================================
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

namespace AdbLogExport
{
    internal static partial class App
    {
        // 一条用户录入的应用
        internal class ApkApp
        {
            internal string Name = "";   // 用户输入的显示名（不限语种）
            internal string Pkg = "";    // Android 包名
        }

        private static readonly List<ApkApp> APK_ITEMS = new List<ApkApp>();
        private static readonly object APK_LK = new object();
        private static bool APK_LOADED = false;
        private static string APK_LOAD_ERR = "";

        // 自检专用：非空时用这个路径代替默认路径（绝不能污染用户的真实列表）
        internal static string APK_FILE_OVERRIDE = "";

        internal const int APK_NAME_MAX = 40;
        internal const int APK_PKG_MAX = 200;

        // ==================== 路径 ====================
        internal static string ApkListPath()
        {
            if (!string.IsNullOrEmpty(APK_FILE_OVERRIDE)) return APK_FILE_OVERRIDE;

            string root = "";
            try { root = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData); }
            catch { }
            if (string.IsNullOrEmpty(root))
            {
                try { root = Environment.GetEnvironmentVariable("LOCALAPPDATA"); }
                catch { }
            }
            if (string.IsNullOrEmpty(root)) root = ExeDir();   // 兜底：至少能落盘

            string dir = Path.Combine(root, "adb_Tool");
            try { Directory.CreateDirectory(dir); } catch { }
            return Path.Combine(dir, "apk_apps.txt");
        }

        // ==================== 校验 ====================
        // 名称：非空、≤40 字、不含制表符/换行（会把 TSV 弄坏）
        internal static bool ApkNameValid(string name, out string err)
        {
            err = "";
            string s = (name == null) ? "" : name.Trim();
            if (s.Length == 0) { err = "名称不能为空"; return false; }
            if (s.Length > APK_NAME_MAX) { err = "名称最长 " + APK_NAME_MAX + " 个字符"; return false; }
            for (int i = 0; i < s.Length; i++)
            {
                char c = s[i];
                if (c == '\t' || c == '\r' || c == '\n')
                {
                    err = "名称不能包含制表符或换行";
                    return false;
                }
            }
            return true;
        }

        // 包名：只允许字母数字点下划线，必须含点，不能以点开头/结尾。
        //
        // 【为什么必须白名单】包名会被拼进 shell：pm clear <pkg>。
        // 不做限制的话，一个 "a; reboot" 就能在设备上执行任意命令。
        // 这里按字符逐个查，不用正则 —— 少一层依赖，行为也更好预测。
        internal static bool ApkPkgValid(string pkg, out string err)
        {
            err = "";
            string s = (pkg == null) ? "" : pkg.Trim();
            if (s.Length == 0) { err = "包名不能为空"; return false; }
            if (s.Length < 3) { err = "包名太短，至少 3 个字符"; return false; }
            if (s.Length > APK_PKG_MAX) { err = "包名太长（超过 " + APK_PKG_MAX + " 字符）"; return false; }
            if (s.IndexOf('.') <= 0 || s[s.Length - 1] == '.')
            {
                err = "包名要写成 com.example.app 这种带点的形式";
                return false;
            }
            for (int i = 0; i < s.Length; i++)
            {
                char c = s[i];
                bool ok = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z')
                          || (c >= '0' && c <= '9') || c == '.' || c == '_';
                if (!ok)
                {
                    err = "包名只能包含字母、数字、点、下划线（不合法字符：" + c + "）";
                    return false;
                }
            }
            return true;
        }

        // ==================== 读取 ====================
        // 懒加载：第一次用的时候读盘，读不到就按「文件不存在」处理（会触发迁移）。
        // 解析规则：跳过空行 / # 注释 / 缺制表符的行；名称或包名非法的行也跳过，
        // 但不影响其它行 —— 手工编辑写坏了不该让整个列表消失。
        internal static void ApkListEnsureLoaded()
        {
            lock (APK_LK)
            {
                if (APK_LOADED) return;
                APK_LOADED = true;
                APK_LOAD_ERR = "";

                string path = ApkListPath();
                bool exists = false;
                try { exists = File.Exists(path); } catch { }

                if (!exists)
                {
                    // 首次：从 version_pkgs 迁移（可能为空，那也照样建一个空文件，
                    // 用「文件存在」来标记迁移已完成，避免每次启动都再导一遍）
                    APK_ITEMS.Clear();
                    List<VerPkg> src = VerPkgsSnapshot();
                    for (int i = 0; i < src.Count; i++)
                    {
                        string nm = (src[i].Alias != null && src[i].Alias.Trim().Length > 0)
                                    ? src[i].Alias.Trim() : src[i].Pkg;
                        string err = "";
                        if (!ApkNameValid(nm, out err)) continue;
                        if (!ApkPkgValid(src[i].Pkg, out err)) continue;
                        if (ApkIndexOfName(nm) >= 0) continue;
                        if (ApkIndexOfPkg(src[i].Pkg) >= 0) continue;
                        ApkApp a = new ApkApp();
                        a.Name = nm;
                        a.Pkg = src[i].Pkg.Trim();
                        APK_ITEMS.Add(a);
                    }
                    ApkListSaveLocked(APK_ITEMS, out APK_LOAD_ERR);
                    return;
                }

                string[] lines;
                try { lines = File.ReadAllLines(path, Encoding.UTF8); }
                catch (Exception ex) { APK_LOAD_ERR = ex.Message; return; }

                APK_ITEMS.Clear();
                for (int i = 0; i < lines.Length; i++)
                {
                    string raw = lines[i];
                    if (raw == null) continue;
                    string s = raw.Trim();
                    if (s.Length == 0) continue;
                    if (s[0] == '#' || s[0] == ';') continue;

                    int tab = s.IndexOf('\t');
                    if (tab <= 0 || tab >= s.Length - 1) continue;   // 缺字段，跳过

                    string nm = s.Substring(0, tab).Trim();
                    string pkg = s.Substring(tab + 1).Trim();
                    string err = "";
                    if (!ApkNameValid(nm, out err)) continue;
                    if (!ApkPkgValid(pkg, out err)) continue;

                    // 文件被手动改出重复项：保留第一条，后面的丢弃（下拉里出现两个
                    // 一模一样的名字，用户根本没法选）
                    if (ApkIndexOfName(nm) >= 0) continue;
                    if (ApkIndexOfPkg(pkg) >= 0) continue;

                    ApkApp a = new ApkApp();
                    a.Name = nm;
                    a.Pkg = pkg;
                    APK_ITEMS.Add(a);
                }
            }
        }

        // 快照：返回副本，调用方随便改都不会影响内部状态
        internal static List<ApkApp> ApkListSnapshot()
        {
            ApkListEnsureLoaded();
            lock (APK_LK)
            {
                List<ApkApp> copy = new List<ApkApp>();
                for (int i = 0; i < APK_ITEMS.Count; i++)
                {
                    ApkApp a = new ApkApp();
                    a.Name = APK_ITEMS[i].Name;
                    a.Pkg = APK_ITEMS[i].Pkg;
                    copy.Add(a);
                }
                return copy;
            }
        }

        internal static int ApkListCount()
        {
            ApkListEnsureLoaded();
            lock (APK_LK) { return APK_ITEMS.Count; }
        }

        internal static string ApkListErrorMessage()
        {
            ApkListEnsureLoaded();
            return APK_LOAD_ERR;
        }

        // 只用下标查找，调用方必须已经持有 APK_LK
        private static int ApkIndexOfName(string name)
        {
            for (int i = 0; i < APK_ITEMS.Count; i++)
            {
                if (string.Equals(APK_ITEMS[i].Name, name, StringComparison.OrdinalIgnoreCase))
                    return i;
            }
            return -1;
        }

        private static int ApkIndexOfPkg(string pkg)
        {
            for (int i = 0; i < APK_ITEMS.Count; i++)
            {
                if (string.Equals(APK_ITEMS[i].Pkg, pkg, StringComparison.OrdinalIgnoreCase))
                    return i;
            }
            return -1;
        }

        // ==================== 增删 ====================
        internal static bool ApkListAdd(string name, string pkg, out string err)
        {
            err = "";
            string nm = (name == null) ? "" : name.Trim();
            string pk = (pkg == null) ? "" : pkg.Trim();

            if (!ApkNameValid(nm, out err)) return false;
            if (!ApkPkgValid(pk, out err)) return false;

            ApkListEnsureLoaded();
            lock (APK_LK)
            {
                int byName = ApkIndexOfName(nm);
                if (byName >= 0)
                {
                    err = "名称「" + nm + "」已经存在（对应 " + APK_ITEMS[byName].Pkg + "）";
                    return false;
                }
                int byPkg = ApkIndexOfPkg(pk);
                if (byPkg >= 0)
                {
                    err = "包名 " + pk + " 已经在列表里（名称：" + APK_ITEMS[byPkg].Name + "）";
                    return false;
                }

                // 先改副本再落盘：写失败就不提交，内存和磁盘保持一致
                List<ApkApp> next = ApkListSnapshotLocked();
                ApkApp a = new ApkApp();
                a.Name = nm;
                a.Pkg = pk;
                next.Add(a);

                string saveErr = "";
                if (!ApkListSaveLocked(next, out saveErr))
                {
                    err = "保存失败：" + saveErr;
                    return false;
                }
                ApkListCommitLocked(next);
                return true;
            }
        }

        internal static bool ApkListRemove(string pkg, out string err)
        {
            err = "";
            string pk = (pkg == null) ? "" : pkg.Trim();
            if (pk.Length == 0) { err = "没有指定包名"; return false; }

            ApkListEnsureLoaded();
            lock (APK_LK)
            {
                int idx = ApkIndexOfPkg(pk);
                if (idx < 0) { err = "列表里没有 " + pk; return false; }

                List<ApkApp> next = ApkListSnapshotLocked();
                next.RemoveAt(idx);

                string saveErr = "";
                if (!ApkListSaveLocked(next, out saveErr))
                {
                    err = "保存失败：" + saveErr;
                    return false;
                }
                ApkListCommitLocked(next);
                return true;
            }
        }

        // 改名（管理列表以后要用；先提供出来，避免以后再动文件格式）
        internal static bool ApkListRename(string pkg, string newName, out string err)
        {
            err = "";
            string pk = (pkg == null) ? "" : pkg.Trim();
            string nm = (newName == null) ? "" : newName.Trim();
            if (!ApkNameValid(nm, out err)) return false;

            ApkListEnsureLoaded();
            lock (APK_LK)
            {
                int idx = ApkIndexOfPkg(pk);
                if (idx < 0) { err = "列表里没有 " + pk; return false; }

                int dup = ApkIndexOfName(nm);
                if (dup >= 0 && dup != idx)
                {
                    err = "名称「" + nm + "」已经被 " + APK_ITEMS[dup].Pkg + " 占用";
                    return false;
                }

                List<ApkApp> next = ApkListSnapshotLocked();
                next[idx].Name = nm;

                string saveErr = "";
                if (!ApkListSaveLocked(next, out saveErr))
                {
                    err = "保存失败：" + saveErr;
                    return false;
                }
                ApkListCommitLocked(next);
                return true;
            }
        }

        // ==================== 落盘 ====================
        // 先写 .tmp 再替换：中途断电/崩溃不会留下半截文件把整个列表读废。
        private static bool ApkListSaveLocked(List<ApkApp> items, out string err)
        {
            err = "";
            string path = ApkListPath();
            string tmp = path + ".tmp";

            StringBuilder sb = new StringBuilder();
            sb.Append("# adb_Tool 应用列表（一行一条：名称<TAB>包名，可直接编辑）");
            sb.Append("\r\n");
            for (int i = 0; i < items.Count; i++)
            {
                sb.Append(items[i].Name);
                sb.Append('\t');
                sb.Append(items[i].Pkg);
                sb.Append("\r\n");
            }

            try
            {
                string dir = Path.GetDirectoryName(path);
                if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);

                File.WriteAllText(tmp, sb.ToString(), new UTF8Encoding(false));

                if (File.Exists(path))
                {
                    // File.Replace 同卷原子替换；目标被占用时退回覆盖写。
                    try
                    {
                        File.Replace(tmp, path, null);
                    }
                    catch
                    {
                        File.Copy(tmp, path, true);
                        try { File.Delete(tmp); } catch { }
                    }
                }
                else
                {
                    File.Move(tmp, path);
                }
                return true;
            }
            catch (Exception ex)
            {
                err = ex.Message;
                try { if (File.Exists(tmp)) File.Delete(tmp); } catch { }
                return false;
            }
        }

        private static List<ApkApp> ApkListSnapshotLocked()
        {
            List<ApkApp> copy = new List<ApkApp>();
            for (int i = 0; i < APK_ITEMS.Count; i++)
            {
                ApkApp a = new ApkApp();
                a.Name = APK_ITEMS[i].Name;
                a.Pkg = APK_ITEMS[i].Pkg;
                copy.Add(a);
            }
            return copy;
        }

        private static void ApkListCommitLocked(List<ApkApp> next)
        {
            APK_ITEMS.Clear();
            for (int i = 0; i < next.Count; i++) APK_ITEMS.Add(next[i]);
        }

        // 自检用：丢掉内存状态，下次访问重新读盘
        internal static void ApkListResetForTest()
        {
            lock (APK_LK)
            {
                APK_ITEMS.Clear();
                APK_LOADED = false;
                APK_LOAD_ERR = "";
            }
        }
    }
}
