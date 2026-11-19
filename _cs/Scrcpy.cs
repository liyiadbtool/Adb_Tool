// ============================================================================
//  Scrcpy.cs - 外挂 scrcpy：探针 → 接入 → 降级（R10）
//
//  为什么要它：
//    内置投屏是"adb exec-out screencap 连续抓帧"，受限于单张 ~300ms，
//    实际只有 3fps 左右。够看画面、够定位 bug，但不算可用。
//    scrcpy 走的是 h264 视频流，几十 fps，还能带键盘鼠标。
//
//  为什么是"外挂"而不是集成进界面：
//    scrcpy 的视频是自己开 SDL 窗口渲染的，没有稳定的"把画面塞进别人窗口"
//    的接口。硬做成内嵌要么自己实现 h264 解码 + D3D 渲染（几十天），
//    要么截它的窗口再贴图（掉帧、无法交互）。所以这里的设计是：
//    **有 scrcpy 就单独开它的窗口，没有就用内置截帧通道**，两条路互不影响。
//
//  三级降级：
//    1) 找到且校验通过 → 点「外部」按钮开 scrcpy 窗口（流畅 + 可操作）
//    2) 找到但启动失败（版本不支持 --display-id、缺 dll 等）→ 把 stderr 前几行
//       原样抛给界面，内置通道继续用
//    3) 没找到 → 界面显示"未找到"，点按钮给出引导（选文件 / 忽略继续用内置）
// ============================================================================
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading;

namespace AdbLogExport
{
    internal static class Scrcpy
    {
        internal const string IniKey = "scrcpy";

        internal const int LvIni = 1;
        internal const int LvExe = 2;
        internal const int LvPath = 3;
        internal const int LvCommon = 4;

        internal static string LevelText(int lv)
        {
            if (lv == LvIni) return "ini 配置";
            if (lv == LvExe) return "程序同级";
            if (lv == LvPath) return "系统 PATH";
            if (lv == LvCommon) return "常见位置";
            return "";
        }

        private static string _cachedPath;
        private static string _cachedVer = "";

        // A21：内嵌 scrcpy 的 stderr 累积器（按 pid 存），失败时把真实原因带回去。
        // 之前 BeginErrorReadLine 只 += delegate{} 空处理，scrcpy 启动后立刻退出
        // （最常见是"Device disconnected"）时，原因被吞掉，用户只看到"scrcpy 连接中"
        // 却不知道是设备掉线。现在失败路径能读到 scrcpy 自己打印的原因。
        private static readonly System.Collections.Concurrent.ConcurrentDictionary<int, System.Text.StringBuilder>
            _embedErr = new System.Collections.Concurrent.ConcurrentDictionary<int, System.Text.StringBuilder>();

        /// <summary>取某 pid 的内嵌 scrcpy stderr 前几行（用于失败诊断）。</summary>
        internal static string EmbedErr(int pid)
        {
            System.Text.StringBuilder sb;
            if (_embedErr.TryGetValue(pid, out sb) && sb != null)
            {
                string s = sb.ToString();
                if (s.Length > 500) s = s.Substring(s.Length - 500);
                return s.Trim();
            }
            return "";
        }

        internal static void ForgetEmbedErr(int pid)
        {
            System.Text.StringBuilder sb;
            _embedErr.TryRemove(pid, out sb);
        }

        internal static void ClearCache()
        {
            _cachedPath = null;
            _cachedVer = "";
        }

        internal static string DefaultIniPath()
        {
            return Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "adb_log_export.ini");
        }

        internal static List<string> Candidates(out List<int> levels)
        {
            List<string> list = new List<string>();
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

            string cfg = App.SCRCPY;
            if (!string.IsNullOrEmpty(cfg))
            {
                string c = cfg.Trim().Trim('"');
                if (c.Length > 0 && !string.Equals(c, "scrcpy.exe", StringComparison.OrdinalIgnoreCase))
                {
                    if (!Path.IsPathRooted(c)) c = Path.Combine(baseDir, c);
                    try { if (Directory.Exists(c)) c = Path.Combine(c, "scrcpy.exe"); }
                    catch { }
                    add(c, LvIni);
                }
            }

            // 绿色版通常是 scrcpy-win64-v2.x\scrcpy.exe，用户会把整个目录解到旁边
            add(Path.Combine(baseDir, "scrcpy.exe"), LvExe);
            add(Path.Combine(baseDir, "scrcpy", "scrcpy.exe"), LvExe);

            try
            {
                // A15：PATH 除了读进程环境变量，还要读注册表里的 User / Machine PATH。
                // 原因：winget 装完只改注册表，已经在跑的进程（本工具）环境变量不会刷新，
                // 于是"刚装好却提示找不到"——这是用户最常踩的坑，必须在代码里兜住。
                List<string> pathDirs = new List<string>();
                string pathEnv = Environment.GetEnvironmentVariable("PATH");
                if (!string.IsNullOrEmpty(pathEnv)) pathDirs.AddRange(pathEnv.Split(';'));

                string regPath = "";
                try { regPath = ReadEnvFromRegistry("Path"); } catch { }
                if (!string.IsNullOrEmpty(regPath)) pathDirs.AddRange(regPath.Split(';'));

                for (int i = 0; i < pathDirs.Count; i++)
                {
                    string d = pathDirs[i].Trim().Trim('"');
                    if (d.Length == 0) continue;
                    add(Path.Combine(d, "scrcpy.exe"), LvPath);
                }
            }
            catch { }

            // A15：winget 的 portable 包落在 Packages\Genymobile.scrcpy_*\scrcpy-win64-vX.Y.Z\，
            // 而 WinGet\Links 里不一定有 shim（实测 5.0.1 就没有）。所以直接扫包目录。
            string local = "";
            try { local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData); } catch { }
            string user = "";
            try { user = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile); } catch { }

            if (!string.IsNullOrEmpty(local))
            {
                add(Path.Combine(local, "adb_Tool", "scrcpy.exe"), LvCommon);
                add(Path.Combine(local, "Microsoft", "WinGet", "Links", "scrcpy.exe"), LvCommon);
                try
                {
                    string pkgs = Path.Combine(local, "Microsoft", "WinGet", "Packages");
                    if (Directory.Exists(pkgs))
                    {
                        string[] dirs = Directory.GetDirectories(pkgs, "Genymobile.scrcpy*");
                        Array.Sort(dirs, StringComparer.OrdinalIgnoreCase);
                        Array.Reverse(dirs);   // 新版本在前
                        for (int i = 0; i < dirs.Length; i++)
                        {
                            add(Path.Combine(dirs[i], "scrcpy.exe"), LvCommon);
                            string[] sub = null;
                            try { sub = Directory.GetDirectories(dirs[i], "scrcpy-win*"); } catch { }
                            if (sub != null)
                            {
                                Array.Sort(sub, StringComparer.OrdinalIgnoreCase);
                                Array.Reverse(sub);
                                for (int k = 0; k < sub.Length; k++)
                                    add(Path.Combine(sub[k], "scrcpy.exe"), LvCommon);
                            }
                        }
                    }
                }
                catch { }
            }
            if (!string.IsNullOrEmpty(user)) add(Path.Combine(user, "scoop", "shims", "scrcpy.exe"), LvCommon);
            add(@"C:\scrcpy\scrcpy.exe", LvCommon);
            add(@"C:\ProgramData\chocolatey\bin\scrcpy.exe", LvCommon);

            levels = lvls;
            return list;
        }

        internal static string Locate(out string version, out string err)
        {
            if (_cachedPath != null)
            {
                version = _cachedVer;
                err = "";
                return _cachedPath;
            }
            return LocateFresh(out version, out err);
        }

        internal static string LocateFresh(out string version, out string err)
        {
            version = "";
            err = "";

            List<int> lvs;
            List<string> cands = Candidates(out lvs);
            for (int i = 0; i < cands.Count; i++)
            {
                bool exists = false;
                try { exists = File.Exists(cands[i]); }
                catch { }
                if (!exists) continue;

                string ver = "";
                string e = "";
                if (Validate(cands[i], out ver, out e))
                {
                    _cachedPath = cands[i];
                    _cachedVer = ver;
                    version = ver;
                    return cands[i];
                }
            }

            err = "没有可用的 scrcpy.exe（检查了 " + cands.Count + " 个位置）。"
                + "有它就多一条流畅通道；没有也不影响内置投屏。";
            return "";
        }

        /// <summary>
        /// 校验：跑 `scrcpy --version`（scrcpy 会把版本打到 stdout）。
        /// 注意 scrcpy.exe 在没装 adb 的机器上仍能打印版本，所以这个校验是安全的。
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
                psi.Arguments = "--version";
                psi.UseShellExecute = false;
                psi.CreateNoWindow = true;
                psi.RedirectStandardOutput = true;
                psi.RedirectStandardError = true;

                using (Process p = new Process())
                {
                    p.StartInfo = psi;
                    try { p.Start(); }
                    catch (Exception ex) { err = "无法运行（" + FirstLine(ex.Message) + "）"; return false; }

                    string o = "";
                    string e = "";
                    try { o = p.StandardOutput.ReadToEnd(); } catch { }
                    try { e = p.StandardError.ReadToEnd(); } catch { }

                    if (!p.WaitForExit(6000))
                    {
                        try { p.Kill(); } catch { }
                        err = "运行超时（可能不是 scrcpy）";
                        return false;
                    }

                    string ver = ParseVersion(o + "\n" + e);
                    if (ver.Length == 0)
                    {
                        err = "输出里没有 scrcpy 版本（不是 scrcpy？）";
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

        /// <summary>从 --version 输出里取版本号。常见：`scrcpy 2.4 <https://github.com/...>`</summary>
        internal static string ParseVersion(string output)
        {
            if (string.IsNullOrEmpty(output)) return "";
            string low = output.ToLowerInvariant();
            int i = low.IndexOf("scrcpy ");
            if (i < 0) return "";
            int s = i + "scrcpy ".Length;
            int e = s;
            while (e < output.Length)
            {
                char c = output[e];
                if (c == ' ' || c == '\r' || c == '\n' || c == '\t' || c == '<') break;
                e++;
            }
            if (e <= s) return "";
            string v = output.Substring(s, e - s).Trim();
            if (v.Length > 30) return "";
            // 版本号至少要有一个数字，防止把 "scrcpy by rom1v" 当成版本
            bool digit = false;
            for (int k = 0; k < v.Length; k++) if (v[k] >= '0' && v[k] <= '9') { digit = true; break; }
            return digit ? v : "";
        }

        internal static bool Use(string path, out string version, out string err)
        {
            version = "";
            err = "";
            string p = (path == null) ? "" : path.Trim().Trim('"');
            if (p.Length == 0) { err = "路径为空"; return false; }

            try
            {
                if (Directory.Exists(p)) p = Path.Combine(p, "scrcpy.exe");
                if (!Path.IsPathRooted(p)) p = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, p);
                p = Path.GetFullPath(p);
            }
            catch (Exception ex) { err = "路径无效：" + ex.Message; return false; }

            string ver = "";
            string ve = "";
            if (!Validate(p, out ver, out ve)) { err = "不是可用的 scrcpy：" + ve; return false; }

            string se = "";
            if (!Ffmpeg.SaveKey(IniKey, p, out se)) err = "已生效，但保存配置失败：" + se;

            ClearCache();
            _cachedPath = p;
            _cachedVer = ver;
            App.SCRCPY = p;
            version = ver;
            return true;
        }

        /// <summary>
        /// 给指定 display 开一个 scrcpy 窗口。
        /// 失败不抛异常 —— 调用方只会拿到一条可读的 err，然后继续用内置通道（降级）。
        /// </summary>
        internal static bool Launch(int displayId, out string err)
        {
            return Launch(displayId, "", out err);
        }

        /// <summary>
        /// 开一个 scrcpy 窗口投指定屏。name 只用于窗口标题（主屏 / 后排屏 / PHUD-B…）。
        /// A15 修了两处：
        ///   1) 原来 `if (displayId > 0)` 才带 --display-id，于是 0（主屏）反而不传参 ——
        ///      主屏是用户列的第一个，必须显式传 0，否则 scrcpy 用"默认屏"，语义不清。
        ///   2) 标题原来写死 "屏 N"，6 个窗口在任务栏里分不清谁是谁。
        /// </summary>
        internal static bool Launch(int displayId, string name, out string err)
        {
            err = "";
            string ver = "";
            string le = "";
            string exe = Locate(out ver, out le);
            if (exe.Length == 0) { err = le; return false; }

            string serial = (!string.IsNullOrEmpty(App.SERIAL) && App.SERIAL_OK) ? App.SERIAL : App.DEVID;

            if (string.IsNullOrEmpty(name)) name = "屏 " + displayId;

            StringBuilder a = new StringBuilder();
            if (!string.IsNullOrEmpty(serial)) a.Append("-s ").Append(serial).Append(' ');
            // --no-control：只投屏不接管输入。测试场景下误触会改车机状态，风险太大。
            a.Append("--no-control");
            a.Append(" --display-id=").Append(displayId);
            a.Append(" --window-title=\"adb_Tool · ").Append(name).Append('"');
            // ---- A16：画质 / 性能参数（原来一个都没传，全靠 scrcpy 默认值）----
            // 车机屏常见 1920x720 / 2560x1440，按原生尺寸编码压力大，降边最有效；
            // 30fps 是"够看清"的性价比点，60 留给高刷屏；16M 码率保证文字不糊。
            a.Append(" --max-size=1600");
            a.Append(" --max-fps=60");
            a.Append(" --video-bit-rate=16M");
            // scrcpy 5 默认会采设备音频（Android 11+），投屏不需要，省一路带宽
            a.Append(" --no-audio");
            // 注意：--stay-awake 与 --no-control 互斥，实测 scrcpy 5.0.1 会直接报
            // "Cannot request to stay awake if control is disabled" 然后退出。
            // 所以不能加；要防息屏请用系统设置里的"充电时不休眠"。
            // 让 scrcpy 把实时帧率打到 stderr —— 以后"卡不卡"有数据可看，
            // 不用再靠感觉。读取在下面的 drain 线程里（不读会堵死管道）。
            a.Append(" --print-fps");

            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = exe;
            psi.Arguments = a.ToString();
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            psi.RedirectStandardOutput = true;
            psi.RedirectStandardError = true;

            try
            {
                Process p = new Process();
                p.StartInfo = psi;
                p.Start();

                // A16：--print-fps 每秒往 stderr 写一行。原来 stderr 只是"启动了但没读"，
                // Windows 管道缓冲只有 4KB，写满之后 scrcpy 会**阻塞在写往 stderr**上 ——
                // 表现就是"投屏几分钟后画面卡死"。所以必须有人一直在抽这个管道，
                // 顺手把 fps 行写进 trace，卡不卡有据可查。
                StringBuilder errAcc = new StringBuilder();
                Thread drain = new Thread((ThreadStart)delegate
                {
                    try
                    {
                        string ln;
                        while ((ln = p.StandardError.ReadLine()) != null)
                        {
                            if (errAcc.Length < 8000) errAcc.AppendLine(ln);
                            if (ln.IndexOf("fps", StringComparison.OrdinalIgnoreCase) >= 0)
                                App.Trace("scrcpy fps: " + ln.Trim());
                        }
                    }
                    catch { }
                });
                drain.IsBackground = true;
                drain.Start();

                Thread drainOut = new Thread((ThreadStart)delegate
                {
                    try { p.StandardOutput.ReadToEnd(); } catch { }
                });
                drainOut.IsBackground = true;
                drainOut.Start();

                // 给 2 秒看它会不会立刻退出：老版本没有 --display-id 会马上报错退出，
                // 这种情况必须把原因带回去（否则用户只看到"闪一下没了"）。
                bool exited = p.WaitForExit(2000);
                if (exited)
                {
                    try { drain.Join(600); } catch { }
                    string errtxt = errAcc.ToString();
                    err = "scrcpy 启动后立即退出（退出码 " + p.ExitCode + "）：" + FirstLine(errtxt.Trim());
                    if (err.IndexOf("unrecognized", StringComparison.OrdinalIgnoreCase) >= 0
                        || err.IndexOf("unknown option", StringComparison.OrdinalIgnoreCase) >= 0)
                        err += " —— 这个版本可能不支持 --display-id，请升级 scrcpy 2.x";
                    return false;
                }
                App.Trace("scrcpy: 已启动 display=" + displayId + " pid=" + p.Id
                          + " exe=" + exe);
                return true;
            }
            catch (Exception ex)
            {
                err = "启动 scrcpy 失败：" + ex.Message;
                return false;
            }
        }

        /// <summary>
        /// A17：启动一个**可交互**的 scrcpy 窗口，供 SetParent 嵌进应用内使用。
        ///
        /// 与 Launch() 的三点差别（写在方法上，免得以后被"统一"掉）：
        ///   1) **不带 --no-control** —— 内嵌的核心诉求就是"能点、跟手"。
        ///      外部窗口那条路故意不接管输入（怕误触改车机状态），内嵌这条路是用户
        ///      明确要的交互，所以反过来：必须接管。
        ///   2) 带 --window-borderless —— 我们自己做描边和圆角，系统标题栏留着会露出两层。
        ///   3) 窗口标题由调用方给，且**唯一**（含 pid/tick），FindWindow 才找得准；
        ///      找到之后立刻 SetParent，标题对用户不可见。
        /// </summary>
        internal static Process LaunchEmbedded(int displayId, string title, out string err)
        {
            err = "";
            string ver = "";
            string le = "";
            string exe = Locate(out ver, out le);
            if (exe.Length == 0) { err = le; return null; }

            string serial = (!string.IsNullOrEmpty(App.SERIAL) && App.SERIAL_OK) ? App.SERIAL : App.DEVID;

            StringBuilder a = new StringBuilder();
            if (!string.IsNullOrEmpty(serial)) a.Append("-s ").Append(serial).Append(' ');
            a.Append("--display-id=").Append(displayId);
            a.Append(" --window-title=\"").Append(title).Append('"');
            a.Append(" --window-borderless");
            // S4（2026-11-19）：内嵌是**多格并发**（最多 6 格同时投），不能按单窗口的
            // 1600/60fps/16M 给 —— 6 路一起会把设备硬编和 USB 带宽全吃满，
            // 结果是每路都掉帧。这里降到 1280/30fps/8M：
            //   · 实测主屏 1280 下 scrcpy 可稳 30fps（打满 --max-fps）
            //   · 8M 对 1280 宽足够，文字不糊
            //   · 6 路合计约 48Mbps ≈ 6MB/s，USB2 也在余量内
            // 单窗「外部」模式仍用 1600/60/16M（见上面的非内嵌分支），要高清就看外部窗口。
            a.Append(" --max-size=1280");
            a.Append(" --max-fps=30");
            a.Append(" --video-bit-rate=8M");
            a.Append(" --no-audio");
            // 内嵌时不打 --print-fps：帧率数字对用户没意义，而且 stderr 每秒一行
            // 在高帧率下会放大到几十行/秒，白白占管道带宽。

            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = exe;
            psi.Arguments = a.ToString();
            psi.UseShellExecute = false;
            // 内嵌模式绝不能弹黑框：scrcpy 是控制台程序，CreateNoWindow=false 会
            // 先闪一个 cmd 窗口，而且那个控制台是**进程的第一个顶层窗口** ——
            // 后面按标题 / MainWindowHandle 找窗口时容易认错。
            psi.CreateNoWindow = true;
            // 但输出必须有人读：Windows 管道 4KB 写满后 scrcpy 会阻塞在写 stderr 上，
            // 表现就是"投屏几分钟后画面卡死"。起两个后台线程抽干。
            psi.RedirectStandardError = true;
            psi.RedirectStandardOutput = true;

            try
            {
                Process p = new Process();
                p.StartInfo = psi;
                p.Start();
                try
                {
                    System.Text.StringBuilder errAcc = new System.Text.StringBuilder();
                    _embedErr[p.Id] = errAcc;
                    p.ErrorDataReceived += delegate(object s, DataReceivedEventArgs ea)
                    {
                        if (ea.Data != null)
                        {
                            if (errAcc.Length < 8000) errAcc.AppendLine(ea.Data);
                            if (ea.Data.IndexOf("fps", StringComparison.OrdinalIgnoreCase) >= 0
                                || ea.Data.IndexOf("disconnect", StringComparison.OrdinalIgnoreCase) >= 0
                                || ea.Data.IndexOf("ERROR", StringComparison.OrdinalIgnoreCase) >= 0
                                || ea.Data.IndexOf("WARN", StringComparison.OrdinalIgnoreCase) >= 0)
                                App.Trace("scrcpy embed[" + p.Id + "]: " + ea.Data.Trim());
                        }
                    };
                    p.OutputDataReceived += delegate(object s, DataReceivedEventArgs ea)
                    {
                        if (ea.Data != null && errAcc.Length < 8000) errAcc.AppendLine(ea.Data);
                    };
                    p.BeginErrorReadLine();
                    p.BeginOutputReadLine();
                }
                catch { }
                App.Trace("scrcpy embed: pid=" + p.Id + " display=" + displayId + " title=" + title);
                return p;
            }
            catch (Exception ex)
            {
                err = "启动内嵌 scrcpy 失败：" + ex.Message;
                return null;
            }
        }

        internal static string StatusLine(out bool ok, out string path, out string version)
        {
            string ver = "";
            string e = "";
            string p = Locate(out ver, out e);
            path = p;
            version = ver;
            ok = (p.Length > 0);
            if (!ok) return e;
            return p + "（" + ver + "）";
        }

        /// <summary>
        /// 从注册表读 PATH（用户 + 系统），并展开 %VAR%。
        /// 为什么不只用 Environment.GetEnvironmentVariable("PATH")：
        /// winget / 安装器改的是注册表，**运行中的进程**读到的还是启动那一刻的旧 PATH。
        /// 用户刚装完 scrcpy 回来点「外部投屏」却提示找不到，根因就在这里。
        /// </summary>
        private static string ReadEnvFromRegistry(string name)
        {
            StringBuilder sb = new StringBuilder();
            string[] keys = new string[]
            {
                @"Environment",
                @"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
            };
            for (int i = 0; i < keys.Length; i++)
            {
                try
                {
                    Microsoft.Win32.RegistryKey root = (i == 0)
                        ? Microsoft.Win32.Registry.CurrentUser
                        : Microsoft.Win32.Registry.LocalMachine;
                    using (Microsoft.Win32.RegistryKey k = root.OpenSubKey(keys[i]))
                    {
                        if (k == null) continue;
                        object v = k.GetValue(name, null);
                        string sv = (v == null) ? "" : v.ToString();
                        if (sv.Length == 0) continue;
                        if (sb.Length > 0) sb.Append(';');
                        sb.Append(sv);
                    }
                }
                catch { }
            }
            string s = sb.ToString();
            if (s.Length == 0) return "";
            try { s = Environment.ExpandEnvironmentVariables(s); } catch { }
            return s;
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
