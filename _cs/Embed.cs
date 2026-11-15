// ============================================================================
//  Embed.cs - 单 exe 版：把"外置文件"变成"内嵌资源 + 外置优先"
//
//  为什么要有这个文件（R8）：
//    以前 adb_Tool.exe 必须带着 4 个 dll + webview2\ui.html + 2 个 ini 才能跑。
//    发给同事时经常出现"只拷了 exe，双击没反应 / 白屏"。
//    现在这些全部编译进 exe，**单个文件双击就能用**；同时保留外置优先，
//    开发和现场排障时改外部文件仍然立即生效。
//
//  外置优先的顺序（每一类都一样：先找外部，再退回内嵌）：
//    ui.html        exe\webview2\ui.html  ->  exe\ui.html  ->  释放内嵌到 %%LOCALAPPDATA%%\adb_Tool\ui
//    WebView2Loader  exe\WebView2Loader.dll  ->  exe\webview2\ ->  释放内嵌到 %%LOCALAPPDATA%%\adb_Tool\native
//    托管 DLL        exe\Xxx.dll（Assembly.LoadFrom）  ->  内嵌（Assembly.Load(byte[])）
//    ini            exe\adb_log_export.ini 存在就不动；不存在才写内嵌默认值
//
//  三条硬约束（踩过就知道为什么）：
//    1) AssemblyResolve 必须在**任何** WebView2 类型被碰到之前挂上，
//       所以放在 GuiEntry 的静态构造函数里（CLR 保证先执行它再执行 Main 体）。
//    2) 原生 WebView2Loader.dll 不能靠 AssemblyResolve —— 它不是托管程序集，
//       必须落盘 + SetDllDirectory 让它进 LoadLibrary 的搜索路径。
//    3) 内嵌资源只在"外部没有"时才用；否则开发期改了 ui.html 却不生效，
//       会以为是缓存问题，实际是读到了 exe 里的旧副本。
// ============================================================================
using System;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;

namespace AdbLogExport
{
    internal static class Embed
    {
        // 逻辑资源名 = build_gui.bat 里 /resource:"文件","这个名字" 的第二段。
        // 前缀统一用 adb. 便于 GetManifestResourceStream 精确定位（避免与
        // 编译器自动生成的 .resources / .Properties 撞名）。
        internal const string ResUiHtml = "adb.ui.html";
        internal const string ResCore = "adb.WebView2.Core.dll";
        internal const string ResForms = "adb.WebView2.WinForms.dll";
        internal const string ResLoader = "adb.WebView2Loader.dll";
        internal const string ResIni = "adb.default.ini";
        internal const string ResCmds = "adb.default.cmds.ini";

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool SetDllDirectory(string lpPathName);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern IntPtr LoadLibrary(string lpFileName);

        internal static string BaseDir
        {
            get { return AppDomain.CurrentDomain.BaseDirectory; }
        }

        // 可写数据目录：%%LOCALAPPDATA%%\adb_Tool（与 WebView2 缓存、日志同一处）。
        // 不放 exe 同级：包可能落在只读目录（光盘、共享盘、Program Files）。
        internal static string DataDir()
        {
            string root = "";
            try
            {
                root = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
                if (string.IsNullOrEmpty(root))
                    root = Environment.GetEnvironmentVariable("LOCALAPPDATA");
            }
            catch { }
            if (string.IsNullOrEmpty(root)) root = BaseDir;
            string d = Path.Combine(root, "adb_Tool");
            try { Directory.CreateDirectory(d); } catch { }
            return d;
        }

        // ---------------- 读取内嵌资源 ----------------

        internal static Stream Open(string name)
        {
            try { return Assembly.GetExecutingAssembly().GetManifestResourceStream(name); }
            catch { return null; }
        }

        internal static bool Has(string name)
        {
            Stream s = Open(name);
            if (s == null) return false;
            try { s.Close(); } catch { }
            return true;
        }

        internal static byte[] ReadBytes(string name)
        {
            Stream s = Open(name);
            if (s == null) return null;
            try
            {
                using (MemoryStream ms = new MemoryStream())
                {
                    byte[] buf = new byte[81920];
                    int n;
                    while ((n = s.Read(buf, 0, buf.Length)) > 0) ms.Write(buf, 0, n);
                    return ms.ToArray();
                }
            }
            catch { return null; }
            finally { try { s.Close(); } catch { } }
        }

        internal static string ReadText(string name)
        {
            byte[] b = ReadBytes(name);
            if (b == null) return "";
            // 内嵌的 ui.html / ini 都是 UTF-8；带不带 BOM 都要能读
            int off = 0;
            if (b.Length >= 3 && b[0] == 0xEF && b[1] == 0xBB && b[2] == 0xBF) off = 3;
            try { return Encoding.UTF8.GetString(b, off, b.Length - off); }
            catch { return ""; }
        }

        // ---------------- 托管 DLL：AssemblyResolve ----------------

        private static bool _hooked;

        internal static void HookAssemblyResolve()
        {
            if (_hooked) return;
            _hooked = true;

            AppDomain.CurrentDomain.AssemblyResolve +=
                delegate(object sender, ResolveEventArgs args)
                {
                    try
                    {
                        string simple = new AssemblyName(args.Name).Name;
                        string res = null;
                        if (simple == "Microsoft.Web.WebView2.Core") res = ResCore;
                        else if (simple == "Microsoft.Web.WebView2.WinForms") res = ResForms;
                        if (res == null) return null;

                        // 外置优先：exe 同级有同名 dll 就用它。
                        // 这样"补一个更新的 SDK dll 覆盖"仍然有效，也方便调试时
                        // 直接换 dll 观察行为，不必重新编译。
                        string ext = Path.Combine(BaseDir, simple + ".dll");
                        if (File.Exists(ext))
                        {
                            try { return Assembly.LoadFrom(ext); }
                            catch { }
                        }

                        byte[] b = ReadBytes(res);
                        if (b == null) return null;   // 非单文件构建：让 CLR 自己报错
                        return Assembly.Load(b);
                    }
                    catch { return null; }
                };
        }

        // ---------------- 原生 DLL：WebView2Loader ----------------

        /// <summary>
        /// 保证 WebView2Loader.dll 可被 LoadLibrary 找到，返回它所在目录。
        /// 返回空串表示既没有外置也没有内嵌（单文件构建失败），
        /// 调用方不必中断 —— WebView2 初始化会给出更具体的错误。
        /// </summary>
        internal static string PrepareNativeLoader()
        {
            // 1) 外置：exe 同级（发布包）/ webview2 子目录（源码目录）
            string[] ext = new string[]
            {
                Path.Combine(BaseDir, "WebView2Loader.dll"),
                Path.Combine(BaseDir, "webview2", "WebView2Loader.dll")
            };
            for (int i = 0; i < ext.Length; i++)
            {
                if (!File.Exists(ext[i])) continue;
                string dir = Path.GetDirectoryName(ext[i]);
                try { SetDllDirectory(dir); } catch { }
                return dir;
            }

            // 2) 内嵌：释放到 LocalAppData\native 后显式加载。
            //    不释放到 exe 同级：exe 可能位于只读目录。
            byte[] data = ReadBytes(ResLoader);
            if (data == null) return "";

            string outDir = Path.Combine(DataDir(), "native");
            string outFile = Path.Combine(outDir, "WebView2Loader.dll");
            try
            {
                Directory.CreateDirectory(outDir);
                // 长度不一致才重写：每次启动都覆盖会让杀软的"文件频繁变化"告警变多
                bool need = true;
                try
                {
                    if (File.Exists(outFile) && new FileInfo(outFile).Length == data.Length) need = false;
                }
                catch { }
                if (need)
                {
                    // 先写临时文件再覆盖：本进程可能已经加载过旧文件（第二次启动场景）
                    string tmp = outFile + ".tmp";
                    File.WriteAllBytes(tmp, data);
                    try { File.Copy(tmp, outFile, true); }
                    catch { try { File.Delete(outFile); File.Copy(tmp, outFile, true); } catch { } }
                    try { File.Delete(tmp); } catch { }
                }
            }
            catch { return ""; }

            try { SetDllDirectory(outDir); } catch { }
            // 显式按全路径加载一次：之后 WebView2 以裸名 P/Invoke 时会复用这个模块，
            // 不依赖搜索路径的细节（不同 Windows 版本 SafeDllSearchMode 行为有差异）。
            try { LoadLibrary(outFile); } catch { }
            return outDir;
        }

        // ---------------- ui.html ----------------

        /// <summary>
        /// 定位界面文件：外置优先，其次把内嵌的 ui.html 释放出来。
        /// 返回的文件一定存在（除非构建时既没外置也没内嵌）。
        /// </summary>
        internal static string PrepareUiHtml()
        {
            string p1 = Path.Combine(BaseDir, "webview2", "ui.html");
            if (File.Exists(p1)) return p1;

            string p2 = Path.Combine(BaseDir, "ui.html");
            if (File.Exists(p2)) return p2;

            // 开发期兜底：仓库里 ui_draft\index.html
            string pd = Path.Combine(BaseDir, "ui_draft", "index.html");
            if (File.Exists(pd)) return pd;

            byte[] data = ReadBytes(ResUiHtml);
            if (data == null) return p1;      // 交给调用方报"找不到界面文件"

            string[] dirs = new string[]
            {
                Path.Combine(DataDir(), "ui"),
                Path.Combine(Path.GetTempPath(), "adb_Tool_ui")
            };
            for (int i = 0; i < dirs.Length; i++)
            {
                try
                {
                    Directory.CreateDirectory(dirs[i]);
                    string f = Path.Combine(dirs[i], "ui.html");
                    // 内容长度一致就当作同一版本：不重写 => 文件时间戳稳定 =>
                    // GuiWeb 里那个 ?v=mtime 的缓存键也不会每次变（省一次全量重解析）
                    bool need = true;
                    try
                    {
                        if (File.Exists(f) && new FileInfo(f).Length == data.Length) need = false;
                    }
                    catch { }
                    if (need) File.WriteAllBytes(f, data);
                    return f;
                }
                catch { }
            }
            return p1;
        }

        // ---------------- 配置文件默认值 ----------------

        /// <summary>
        /// ini 缺失时写一份内嵌默认值。**已存在就绝不覆盖** ——
        /// 用户的 adb 路径、serial、root 开关都在里面。
        /// </summary>
        internal static void EnsureIniDefaults()
        {
            WriteIfMissing("adb_log_export.ini", ResIni);
            WriteIfMissing("cmds.ini", ResCmds);
        }

        private static void WriteIfMissing(string fileName, string resName)
        {
            try
            {
                string p = Path.Combine(BaseDir, fileName);
                if (File.Exists(p)) return;
                byte[] b = ReadBytes(resName);
                if (b == null || b.Length == 0) return;
                File.WriteAllBytes(p, b);
            }
            catch { }   // 只读目录 / 无权限：忽略，程序用内置默认值继续跑
        }
    }
}
