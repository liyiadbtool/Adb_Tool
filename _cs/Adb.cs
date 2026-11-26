// ============================================================================
//  Adb.cs — adb 调用层与核心命令实现（cd / ls / pull / push / 透传 / 导出）
//  与 Program.cs 通过 partial class App 合并编译
//
//  v6.2 视觉与感知层改造：
//     1) AdbCallStream 收集输出 —— 失败时能提炼设备原话，不再只报退出码
//     2) 300ms 等待指示 —— 超过阈值才显示，避免快速命令闪烁
//     3) ls -1pF 三档降级 —— 一次调用拿到 目录/可执行/链接 标记并分色
//     4) cd 后是否自动列目录由 CD_LS 控制
//     5) 长输出（>20 行）结尾补「共 N 行」，让用户知道有没有被截断
//
//  注意：为兼容系统自带 csc.exe（.NET 4.x 的 C# 5.0 编译器），
//        全程只用 C# 5.0 语法：不写 out var / out _ / 局部函数 / => 表达式体。
// ============================================================================
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading;

namespace AdbLogExport
{
    internal static partial class App
    {
        // 当前正在运行的 adb 子进程（供 Ctrl+C 中断用）
        // RUNNING 保留给"只有一个前台进程"的场景（CLI / 旧 WinForms 版）；
        // RUNNING_SLOTS 是按槽位的进程表，GUI 三槽并行时"停止"必须只杀本槽。
        // 原来只维护 RUNNING 一个引用：任何一个槽的命令结束都会把它置空，
        // 另一槽还在跑的进程就此"失联"（点停止没反应），而新的命令又会覆盖它
        // （点停止杀掉的是别人）。两个槽各记一份才谈得上并行。
        internal static Process RUNNING = null;

        /* 2026-11-24（长驻命令独立槽位）：
           monkey / logcat -f / scrcpy-server 这类命令会持续输出几分钟到几小时，
           原来占用普通槽位 → _busy[slot] 一直为真 → 用户在这个槽发任何命令都被
           "忙"挡掉（终端一片空白，看起来像 adb 挂了）；而且同槽重发会被 B1 杀掉。
           现在给它们一个**独立通道**：不占 0/1/2 号槽，用户随时可以继续操作。 */
        internal static Process PERSIST_RUNNING = null;
        [System.ThreadStatic] internal static bool PERSIST_CHANNEL = false;
        internal static readonly Process[] RUNNING_SLOTS = new Process[SLOT_COUNT];

        private static int CurSlotSafe()
        {
            int s = App.CUR_SLOT;
            if (s < 0) s = 0;
            if (s >= SLOT_COUNT) s = SLOT_COUNT - 1;
            return s;
        }

        // 杀掉指定槽位正在跑的 adb 进程；返回是否真的杀了一个。
        internal static bool KillRunning(int slot)
        {
            if (slot < 0 || slot >= SLOT_COUNT) return false;
            Process p = RUNNING_SLOTS[slot];
            if (p == null) return false;
            bool killed = false;
            try
            {
                if (!p.HasExited) { p.Kill(); killed = true; }
            }
            catch { }
            return killed;
        }

        internal static bool KillAllRunning()
        {
            bool any = false;
            for (int i = 0; i < SLOT_COUNT; i++) { if (KillRunning(i)) any = true; }
            if (RUNNING != null)
            {
                try { if (!RUNNING.HasExited) { RUNNING.Kill(); any = true; } }
                catch { }
            }
            return any;
        }

        // 等待指示状态（跨线程）
        private static volatile bool WAIT_DONE = true;
        private static volatile bool WAIT_SHOWN = false;
        private static int WAIT_COL = -1;      // 等待指示写在第几列
        private static int WAIT_TOP = -1;      // 以及第几行
        private static volatile bool SILENT = false;   // 后台探测：不显示等待指示

        // ==================== 一、等待指示 ====================
        // adb 单次往返 100~300ms。超过阈值才显示，避免快命令闪一下反而更烦
        private static void WaitHintStart()
        {
            if (SILENT) return;              // 后台探活不该在提示符上闪点
            if (WAIT_HINT_MS <= 0) return;
            WAIT_DONE = false;
            WAIT_SHOWN = false;

            Thread th = new Thread(new ThreadStart(delegate()
            {
                try { Thread.Sleep(WAIT_HINT_MS); } catch { }
                if (WAIT_DONE) return;
                UseDim();
                try
                {
                    WAIT_TOP = Console.CursorTop;
                    WAIT_COL = Console.CursorLeft;
                    Console.Write(" ...");
                }
                catch { }
                WAIT_SHOWN = true;
                UseDefault();
            }));
            th.IsBackground = true;
            th.Start();
        }

        // 幂等：已清理过就不再动
        // 收等待指示：只擦自己写的那 4 个字符，**绝不能 \r 回行首**。
        // 提示符可能就在同一行左边（空闲探测就是这种情况），回行首会把用户
        // 正在输入的命令擦掉 —— 这正是"输入位置错乱"的根因。
        private static void WaitHintStop()
        {
            WAIT_DONE = true;
            if (!WAIT_SHOWN) return;
            WAIT_SHOWN = false;

            try
            {
                // 只有在同一行、且列号有效时才按列擦；否则宁可不擦，也不能误伤
                if (WAIT_COL >= 0 && Console.CursorTop == WAIT_TOP)
                {
                    Console.SetCursorPosition(WAIT_COL, WAIT_TOP);
                    Console.Write("    ");
                    Console.SetCursorPosition(WAIT_COL, WAIT_TOP);
                }
            }
            catch { }
            WAIT_COL = -1;
            WAIT_TOP = -1;
        }

        // ==================== 二、底层 adb 调用 ====================
        // 默认超时：任何普通命令最多等这么久，到点连进程一起收掉。
        // 为什么要给默认值：旧版 ReadToEnd() 没有上限，息屏唤醒后 adb 卡在
        // USB 传输层时会**永久**挂住整个界面（见 Probe.cs 的说明）。
        // 0 = 不限制（保留给极端场景），ini 里 timeout_ms 可改。
        internal static int CALL_TIMEOUT_MS = 30000;
        private static int TIMEOUT_STREAK = 0;   // 连续超时计数（B6 自愈）
        internal static DateTime LAST_OK_TS = DateTime.MinValue;   // 最近一次 adb 成功时间（用于跳过探测）

        // 统一执行入口：异步读两个流，避免"先读 stdout 再读 stderr"的管道死锁
        // （子进程 stderr 写满 4K 而我们正阻塞在 stdout 上时就死锁）。
        // quiet=true 时不碰控制台（等待指示、当前行），专供后台线程使用。
        internal static int RunRaw(List<string> argv, int timeoutMs,
            out string stdout, out string stderr, out bool timedOut, bool quiet)
        {
            stdout = "";
            stderr = "";
            timedOut = false;

            ProcessStartInfo psi = BuildPsi(argv);
            if (psi == null) { stderr = "无法构造命令行"; return 9009; }

            StringBuilder so = new StringBuilder();
            StringBuilder se = new StringBuilder();
            object lk2 = new object();
            int slot = CurSlotSafe();   // 调用发生在 worker 线程，这里取到的才是真实槽位

            using (Process p = new Process())
            {
                p.StartInfo = psi;

                p.OutputDataReceived += new DataReceivedEventHandler(delegate(object s, DataReceivedEventArgs ev)
                {
                    if (ev.Data == null) return;
                    lock (lk2) { so.AppendLine(ev.Data); }
                });

                p.ErrorDataReceived += new DataReceivedEventHandler(delegate(object s, DataReceivedEventArgs ev)
                {
                    if (ev.Data == null) return;
                    lock (lk2) { se.AppendLine(ev.Data); }
                });

                try { p.Start(); }
                catch (Exception ex) { stderr = ex.Message; return 9009; }

                try { p.StandardInput.Close(); } catch { }   // 让 adb 立刻读到 EOF

                if (PERSIST_CHANNEL)
                {
                    // 长驻命令：只记独立引用，不碰槽位表，也不影响 _busy
                    Process prevP = PERSIST_RUNNING;
                    if (prevP != null) { try { if (!prevP.HasExited) prevP.Kill(); } catch { } }
                    PERSIST_RUNNING = p;
                }
                else if (!quiet)
                {
                    /* 2026-11-24（B1）：覆盖前先收尸。
                       同槽再起一条命令时，旧进程的引用会被直接冲掉 ——
                       那条命令继续跑、继续往输出队列写，但"停止"永远杀不到它。
                       这里先杀掉同槽残留，保证任何时刻一个槽只有一条在跑。 */
                    Process prev = RUNNING_SLOTS[slot];
                    if (prev != null)
                    {
                        try { if (!prev.HasExited) prev.Kill(); } catch { }
                    }
                    RUNNING = p;
                    RUNNING_SLOTS[slot] = p;
                    WaitHintStart();
                }

                try
                {
                    p.BeginOutputReadLine();
                    p.BeginErrorReadLine();

                    bool exited;
                    if (timeoutMs > 0) exited = p.WaitForExit(timeoutMs);
                    else { p.WaitForExit(); exited = true; }

                    if (!exited)
                    {
                        timedOut = true;
                        try { p.Kill(); } catch { }
                        // 只等 800ms：TerminateProcess 基本是立即生效的，
                        // 等太久（原来 2 秒）会让"卡住的 adb"每次都多付 2 秒，
                        // 重连时连续几次探测叠起来就是十几秒的白等。
                        try { p.WaitForExit(800); } catch { }
                    }
                    else
                    {
                        // 文档要求：异步读之后再来一次无参 WaitForExit，等缓冲区读完
                        try { p.WaitForExit(); } catch { }
                    }

                    lock (lk2)
                    {
                        stdout = so.ToString();
                        stderr = se.ToString();
                    }

                    if (timedOut) return 124;
                    bool hasExited = false;
                    try { hasExited = p.HasExited; } catch { }
                    if (!hasExited) return -1;
                    return p.ExitCode;
                }
                catch (Exception ex)
                {
                    stdout = "";
                    // 带上真实原因：旧版固定写"已中断"，导致"adb.exe 不存在"和
                    // "命令被 Ctrl+C 打断"在诊断时完全分不开。
                    stderr = "adb 启动或读取失败：" + ex.Message;
                    return -1;
                }
                finally
                {
                    if (!quiet)
                    {
                        WaitHintStop();
                        // 只清自己那一格：别的槽还在跑，不能替它把引用抹掉
                        if (PERSIST_RUNNING == p) PERSIST_RUNNING = null;
                        if (slot >= 0 && slot < SLOT_COUNT && RUNNING_SLOTS[slot] == p) RUNNING_SLOTS[slot] = null;
                        if (RUNNING == p) RUNNING = null;
                    }
                }
            }
        }

        // 收集模式：需要解析输出时用（cd / ls / devices / root / probe / 发送）
        /* 2026-11-24（B3）：按命令类型给超时，不再一律 30 秒。
           30 秒对"下发即返回"的命令足够，但 push/pull/install/bugreport/logcat -f
           这类搬运型命令经常跑几十秒到几分钟，超时会被 kill 并只拿到半截输出，
           上层若只看输出就会把半截数据当完整结果。 */
        private static int TimeoutFor(List<string> argv)
        {
            if (argv == null || argv.Count == 0) return CALL_TIMEOUT_MS;
            string sub = "";
            for (int i = 0; i < argv.Count; i++)
            {
                string a = (argv[i] ?? "").ToLowerInvariant();
                if (a == "-s") { i++; continue; }          // 跳过序列号
                sub = a; break;
            }
            /* 2026-11-25：设备离线时一律 3 秒超时。
               离线状态下 adb 会阻塞到 transport 超时（可长达 30~60 秒），
               表现为"命令一直在加载"。有 3 秒上限就能快速失败。 */
            if (DEVID == null || DEVID.Length == 0 || DEVN == 0) return 3000;
            if (sub == "push" || sub == "pull" || sub == "install" || sub == "uninstall") return 180000;
            if (sub == "bugreport" || sub == "backup" || sub == "restore") return 600000;
            if (sub == "shell" && argv.Count > 1)
            {
                string body = (argv[argv.Count - 1] ?? "").ToLowerInvariant();
                if (body.Contains("logcat")) return 600000;      // logcat -f / -d 大缓冲
                if (body.Contains("bugreport")) return 600000;
                if (body.Contains("dumpsys")) return 60000;       // meminfo 全量偏慢
                if (body.Contains("screencap") || body.Contains("screenrecord")) return 120000;
                if (body.Contains("am force-stop") || body.Contains("pm ")) return 60000;
            }
            return CALL_TIMEOUT_MS;
        }

        /* 2026-11-26（W-03/R2 单一出口）：设备号该不该加的判定，全项目只此一处。
           原来 BuildPsi 与 RunAdbRawEx 各写一份 isGlobal 白名单，
           新增全局命令（如 track-devices）时只改一处，另一处会误带 -s 报错。 */
        private static readonly string[] GLOBAL_SUBS = new string[] {
            "devices", "version", "connect", "disconnect", "pair", "mdns",
            "start-server", "kill-server", "track-devices", "wait-for-device"
        };

        internal static bool IsGlobalSub(string sub)
        {
            if (string.IsNullOrEmpty(sub)) return false;
            string s0 = sub.Trim().ToLowerInvariant();
            for (int i = 0; i < GLOBAL_SUBS.Length; i++)
                if (GLOBAL_SUBS[i] == s0) return true;
            return false;
        }

        /// <summary>本机所有 adb 调用共用的设备号决策：全局命令返回空，否则 SERIAL→DEVID。</summary>
        internal static string PickSerialFor(string adbArgsOrSub)
        {
            string t = (adbArgsOrSub ?? "").TrimStart();
            string sub = t.Split(' ')[0];
            if (IsGlobalSub(sub)) return "";
            return (!string.IsNullOrEmpty(SERIAL) && SERIAL_OK) ? SERIAL
                 : ((!string.IsNullOrEmpty(DEVID)) ? DEVID : "");
        }

        internal static int AdbCall(List<string> argv, out string stdout, out string stderr)
        {
            bool to = false;
            int ms = TimeoutFor(argv);
            int rc = RunRaw(argv, ms, out stdout, out stderr, out to, false);

            /* 2026-11-24（A4）：管道命令的退出码不可信。
               `dumpsys package X | grep versionName` 里 grep 无匹配返回 1，
               但主命令是成功的、数据也已输出。这里只在**管道命令 + 有输出 +
               stderr 为空**三条同时成立时把 rc 归零，避免把失败伪装成成功。
               注意：不做任何额外进程/IO，纯字符串判断，不影响执行速度。 */
            if (rc != 0 && !to && (stdout ?? "").Trim().Length > 0
                && (stderr ?? "").Trim().Length == 0)
            {
                bool pipe = false;
                for (int i = 0; i < argv.Count; i++)
                {
                    string a = argv[i] ?? "";
                    if (a.IndexOf('|') >= 0) { pipe = true; break; }
                }
                if (pipe) rc = 0;
            }
            if (to)
            {
                stderr = ((stderr == null) ? "" : stderr)
                       + "\n[超时] adb 在 " + (ms / 1000) + " 秒内没有返回";
                rc = 124;

                /* 2026-11-25（B6）：连续两次超时 → 自动重启 adb 服务。
                   只"报超时"不修复的话，server 握着一个失效的 USB 句柄时，
                   之后每条命令都会超时，用户只能手动杀掉重开。
                   这里在后台线程重启，避免阻塞当前调用栈。 */
                if (++TIMEOUT_STREAK >= 2)
                {
                    TIMEOUT_STREAK = 0;
                    try
                    {
                        Thread thFix = new Thread(new ThreadStart(delegate()
                        {
                            try
                            {
                                Rec.ResetServer(false);
                                Warn("adb 连续超时，已自动重启 adb 服务");
                            }
                            catch { }
                        }));
                        thFix.IsBackground = true;
                        thFix.Start();
                    }
                    catch { }
                }
            }
            else if (rc == 0) { TIMEOUT_STREAK = 0; LAST_OK_TS = DateTime.Now; }
            return rc;
        }

        // 静默调用：后台探测用，不显示等待指示，也不干扰当前行
        internal static int AdbCallQuiet(List<string> argv, out string stdout, out string stderr)
        {
            bool old = SILENT;
            SILENT = true;
            try { return AdbCall(argv, out stdout, out stderr); }
            finally { SILENT = old; }
        }

        // 轻量探活：只跑一次 devices，短超时，不碰控制台。
        // 后台线程和"没有读键循环"的 IME 模式都用它，保证最长 4 秒一定返回。
        internal static int AdbProbe(out string stdout, out string stderr)
        {
            bool to = false;
            int rc = RunRaw(new List<string> { "devices" }, Bg.PROBE_TIMEOUT_MS,
                out stdout, out stderr, out to, true);
            return to ? 124 : rc;
        }

        // 带超时的收集调用（保留原签名，内部走同一套实现）
        internal static int AdbCallTimeout(List<string> argv, int timeoutMs, out string stdout, out string stderr)
        {
            bool to = false;
            int rc = RunRaw(argv, timeoutMs, out stdout, out stderr, out to, false);
            return to ? 124 : rc;
        }

        // ==================== 二点五、adb 服务急救 ====================
        // 唤醒后 adb server 可能握着已经失效的 USB 句柄，此后所有命令都卡住。
        // 用户平时的办法是"杀掉重开"，这里把它自动化。
        //
        // v7.13：具体步骤搬到 Rec.ResetServer（Reconnect.cs），那里补了三件旧版没有的事：
        //   · kill-server 之后**等 5037 端口真的释放**再 start-server
        //     （旧版固定 Sleep(400) 就起，经常撞端口占用，起个坏 server）
        //   · taskkill 之后**等 adb.exe 真的消失**
        //   · start-server 之后用 `adb version` **校验服务真能回话**
        // 这里只负责把过程收集成文本给控制台层显示。
        internal static int RecoverServer(out string stdout, out string stderr)
        {
            // verbose=false：本方法在后台探测线程里跑，绝不能往控制台写字
            bool ok = Rec.ResetServer(false);

            StringBuilder sb = new StringBuilder();
            sb.AppendLine("[恢复] adb 服务重启" + (ok ? "成功" : "未完成"));

            string o = "";
            string e = "";
            bool to = false;
            int rc = RunRaw(new List<string> { "devices" }, 5000, out o, out e, out to, true);
            sb.AppendLine("[恢复] devices    rc=" + rc + (to ? "（超时）" : ""));
            if (!string.IsNullOrEmpty(o))
                sb.AppendLine("  " + o.Trim().Replace("\r\n", "\n  ").Replace("\n", "\n  "));

            stdout = sb.ToString();
            stderr = "";
            return ok ? 0 : 1;
        }

        // 流式模式：输出边产生边显示。同时收集起来，失败时用于提炼原因。
        internal static int AdbCallStream(List<string> argv, out string combined)
        {
            combined = "";
            ProcessStartInfo psi = BuildPsi(argv);
            if (psi == null) return 9009;

            StringBuilder so = new StringBuilder();
            StringBuilder se = new StringBuilder();
            object lk = new object();
            int lines = 0;
            int slot = CurSlotSafe();   // worker 线程上的真实槽位（回调线程读不到 CUR_SLOT）

            using (Process p = new Process())
            {
                p.StartInfo = psi;

                p.OutputDataReceived += new DataReceivedEventHandler(delegate(object sender, DataReceivedEventArgs ev)
                {
                    if (ev.Data == null) return;
                    WaitHintStop();          // 首个输出到达就先清掉等待指示
                    // 这行跑在 ThreadPool 线程上，CUR_SLOT 在这里无意义，
                    // 必须显式告诉 GuiSink 这一行属于哪个槽位。
                    MarkSlot(slot);
                    try { Console.WriteLine(ev.Data); } catch { }
                    finally { MarkSlot(-1); }
                    lock (lk) { so.AppendLine(ev.Data); lines++; }                });

                p.ErrorDataReceived += new DataReceivedEventHandler(delegate(object sender, DataReceivedEventArgs ev)
                {
                    if (ev.Data == null) return;
                    WaitHintStop();
                    MarkSlot(slot);
                    try { Console.Error.WriteLine(ev.Data); } catch { }
                    finally { MarkSlot(-1); }
                    lock (lk) { se.AppendLine(ev.Data); lines++; }
                });

                try { p.Start(); }
                catch (Exception ex)
                {
                    WaitHintStop();
                    Console.Error.WriteLine(ex.Message);
                    return 9009;
                }

                try { p.StandardInput.Close(); } catch { }   // 同上：别让 adb 抢控制台输入

                Stopwatch sw = Stopwatch.StartNew();

                RUNNING = p;
                RUNNING_SLOTS[slot] = p;
                WaitHintStart();
                p.BeginOutputReadLine();
                p.BeginErrorReadLine();

                try
                {
                    p.WaitForExit();
                    WaitHintStop();

                    lock (lk)
                    {
                        combined = so.ToString() + "\n" + se.ToString();
                        // 长输出补个止点：让用户知道"输出完了"而不是"还在刷"
                        if (lines > 20)
                        {
                            UseDim();
                            Console.WriteLine("  \u00B7 共 " + lines + " 行 \u00B7 " + FmtDur(sw.ElapsedMilliseconds));
                            UseDefault();
                        }
                    }
                    return p.ExitCode;
                }
                catch (Exception)
                {
                    WaitHintStop();
                    try { p.Kill(); } catch { }
                    return -1;
                }
                finally
                {
                    WAIT_DONE = true;
                    if (RUNNING_SLOTS[slot] == p) RUNNING_SLOTS[slot] = null;
                    if (RUNNING == p) RUNNING = null;
                }
            }
        }

        // 耗时格式化：不足 1 秒用毫秒，否则一位小数
        internal static string FmtDur(long ms)
        {
            if (ms < 1000) return ms + "ms";
            return (ms / 1000.0).ToString("0.0") + "s";
        }

        // 构造 ProcessStartInfo：拼 -s <serial> + argv，逐个做引号转义
        private static ProcessStartInfo BuildPsi(List<string> argv)
        {
            if (argv == null) return null;

            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = ADB;
            psi.UseShellExecute = false;
            psi.RedirectStandardOutput = true;
            psi.RedirectStandardError = true;
            // 关键：子进程绝不能继承本工具的 stdin。
            // `adb shell xxx` 会把 stdin 转给设备侧 shell，如果它继承了控制台输入，
            // 键盘输入就会被 adb 吃掉 —— 表现正是"敲字不上屏"，而且只有杀掉重开才好。
            // 这里一律给一个空管道并立刻关掉，adb 立刻读到 EOF，不会抢按键。
            psi.RedirectStandardInput = true;
            psi.CreateNoWindow = true;
            psi.StandardOutputEncoding = new UTF8Encoding(false);
            psi.StandardErrorEncoding = new UTF8Encoding(false);

            // .NET Framework 没有 ArgumentList（那是 .NET Core 才有），
            // 只能拼 Arguments 字符串，并手动做引号转义
            // 优先用 ini 的 serial；没填就锁定当前探测到的设备号。
            // 为什么必须锁定：adb 自己的传输列表里可能残留 tcp/offline 条目，
            // 不指定 -s 时 adb 会判定"more than one device" —— 明明只有一台。
            //
            // 但全局命令（devices / version / 服务管理 / 无线连接）不能带 -s，
            // 它们本来就是对整个 adb 服务生效的。
            string sub0 = (argv.Count > 0) ? argv[0].ToLowerInvariant() : "";
            bool isGlobal = (sub0 == "devices" || sub0 == "version"
                || sub0 == "start-server" || sub0 == "kill-server"
                || sub0 == "connect" || sub0 == "disconnect" || sub0 == "pair" || sub0 == "mdns");

            // ini 里填的 serial 只有在当前确实在线时才用；
            // 否则（换了一台设备、那台已拔掉）会一直报 "device 'xxx' not found"，
            // 这正是"换设备后到处报错"的来源 —— 见 ParseDevices 里的 SERIAL_OK。
            string pin;
            if (isGlobal) pin = "";
            else if (!string.IsNullOrEmpty(SERIAL) && SERIAL_OK) pin = SERIAL;
            else pin = DEVID;

            // 调用方已自带 -s（存活探测、显式指定设备）时不再重复拼
            if (argv.Count > 0 && argv[0] == "-s") pin = "";

            List<string> full = new List<string>();
            if (!string.IsNullOrEmpty(pin)) { full.Add("-s"); full.Add(pin); }
            foreach (string a in argv) full.Add(a);

            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < full.Count; i++)
            {
                if (i > 0) sb.Append(' ');
                sb.Append(Util.QuoteArg(full[i]));
            }
            psi.Arguments = sb.ToString();

            if (VERBOSE) Console.WriteLine("  [adb] " + psi.Arguments);
            return psi;
        }

        // shell 命令（收集模式）：cd '<cur>' && <cmd>
        internal static int ShellCall(string cur, string cmd, out string stdout, out string stderr)
        {
            string full = "cd '" + cur + "' && " + cmd;
            return AdbCall(new List<string> { "shell", full }, out stdout, out stderr);
        }

        // shell 命令（流式模式）
        internal static int ShellCallStream(string cur, string cmd, out string combined)
        {
            string full = "cd '" + cur + "' && " + cmd;
            return AdbCallStream(new List<string> { "shell", full }, out combined);
        }

        // 合并 stdout+stderr 用于诊断
        private static string MergeStream(string stdout, string stderr)
        {
            StringBuilder sb = new StringBuilder();
            if (!string.IsNullOrEmpty(stdout)) sb.Append(stdout);
            if (!string.IsNullOrEmpty(stderr))
            {
                if (sb.Length > 0 && !stdout.EndsWith("\n")) sb.Append('\n');
                sb.Append(stderr);
            }
            return sb.ToString();
        }

        // ==================== 三、cd ====================
        private static void DoCd(string argRaw)
        {
            string arg = argRaw.Trim();
            if (arg.Length == 0) { CdDo("~"); return; }

            List<string> args = SplitArgs(arg);
            if (args.Count == 0) { CdDo("~"); return; }
            string target = args[0];

            // cd @logs / cd @anr —— 跳转点是数据，复用 cd 的语义
            if (target.Length > 1 && target[0] == '@')
            {
                string jp = JumpPath(target.Substring(1).ToLowerInvariant());
                if (jp.Length == 0)
                {
                    Fail("没有这个跳转点：" + target);
                    Hint("可用：@logs @res @anr @dropbox（配在 ini 的 jump_*）");
                    return;
                }
                target = jp;
            }

            if (target == "-")
            {
                if (string.IsNullOrEmpty(OLDPWD))
                {
                    Fail("还没有上一个目录");
                    Hint("先 cd 进任意目录，再用 cd - 返回");
                }
                else
                {
                    CdDo(OLDPWD);
                }
                return;
            }
            CdDo(target);
        }

        private static void CdDo(string target)
        {
            if (string.IsNullOrEmpty(target)) return;
            string cdarg = target.Trim();
            if (cdarg.Length == 0) return;

            string cdold = CUR;
            string o = "";
            string e = "";

            // ~ / ~/xxx 必须**不加引号**：加引号后设备端 shell 不再做波浪号展开，
            // 会当成名为 "~" 的普通目录 -> "No such file"（v7.14 真机复现）。
            string cdsh;
            if (cdarg == "~")
            {
                cdsh = "cd ~ && pwd -P";
            }
            else if (cdarg.Length > 1 && cdarg[0] == '~' && (cdarg[1] == '/' || cdarg[1] == '\\'))
            {
                string rest = cdarg.Substring(1);
                if (rest.IndexOf('\'') >= 0) cdsh = "cd \"" + rest + "\" && pwd -P";
                else cdsh = "cd ~'" + rest + "' && pwd -P";
            }
            else
            {
                cdsh = "cd '" + cdarg + "' && pwd -P";
            }

            int rc = ShellCall(CUR, cdsh, out o, out e);
            string outStr = MergeStream(o, e);
            string newcur = FirstLine(outStr);

            if (rc != 0 || string.IsNullOrEmpty(newcur) || !newcur.StartsWith("/"))
            {
                PEND_K = "CD";
                PEND_R = DevAbs(cdarg);
                string low = outStr.ToLowerInvariant();
                if (low.Contains("permission denied")) { Fail("进入失败：Permission denied"); Hint("该目录需要 root，输入 r 重新连接会自动获取 root 权限"); return; }
                if (low.Contains("no such file")) { Fail("进入失败：目录不存在 '" + cdarg + "'"); Hint("用 ls 查看当前目录内容，或输入 r 重连后重试"); return; }
                if (low.Contains("not a directory")) { Fail("进入失败：'" + cdarg + "' 不是目录"); Hint("该路径是文件；用 lsf 查看同目录下的文件，或换一个目录"); return; }
                if (low.Contains("not found")) { CMD_OK = false; Fail("进入失败：设备连接中断"); Hint("输入 rl 重试上次操作，或输入 r 刷新回到根目录"); return; }
                Fail("进入失败：" + cdarg);
                Hint("用 ls 查看当前有哪些目录，或输入 r 重连后再试");
                return;
            }

            CUR = NormPath(newcur);
            OLDPWD = cdold;
            PEND_K = "";
            CMD_OK = true;
            UpdateTitle();   // 标题栏常驻当前路径，提示符才能保持短

            if (cdarg.StartsWith("..")) Ok("已返回上级：" + CUR);
            else if (cdarg == "~") Ok("已回到家目录：" + CUR);
            else Ok("已进入 " + CUR);

            // cd 只负责"换目录"，不顺手 ls。
            // 旧行为会在 cd 之后自动列一遍目录，把上一屏的输出冲掉；
            // 用户要的语义就是"我只想换目录，想看在敲 ls"。
            if (CD_LISTS_AFTER) LsAfterCd();
        }

        // cd 之后是否自动列目录（CD_LS 可关，避免长 ls 冲掉上下文）
        private static void LsAfterCd()
        {
            if (!CD_LS)
            {
                Info("输入 ls 查看本目录内容");
                return;
            }
            Console.WriteLine();
            LsRender(CUR, "a");
        }

        // ==================== 四、跳转 ====================
        private static void DoJump(string target, string name, string argRaw)
        {
            if (argRaw.Trim().Length > 0) { DoPass(name, argRaw); return; }
            if (string.IsNullOrEmpty(target)) { Fail("没有配置 " + name + " 的目标目录"); Hint("在 ini 里把 jump_res / jump_log 填上路径，然后输入 ri 重连"); return; }
            if (string.Equals(CUR, target, StringComparison.OrdinalIgnoreCase))
            {
                Info("已在 " + target + "，未跳转");
                return;
            }
            CdDo(target);
        }

        // ==================== 五、logcat 兜底 ====================
        private static void DoLogcat(string argRaw)
        {
            if (argRaw.Trim().Length > 0) { DoPass("logcat", argRaw); return; }
            Info("已自动加 -d：导出现有缓冲区后返回");
            Hint("要看实时日志请自己带参数，例如 logcat -v time（用 Ctrl+C 结束）");
            DoPass("logcat", "-d");
        }

        // ==================== 六、ls / lsf ====================
        private static void DoLs(string argRaw, bool filesOnly)
        {
            string arg = argRaw.Trim();
            if (arg.Length == 0) { LsRender(CUR, filesOnly ? "f" : "a"); return; }
            // 带选项（ls -l / -la）原样透传；lsf 无 - 选项，直接当路径渲染
            if (!filesOnly && arg[0] == '-') { DoPass("ls", argRaw); return; }
            LsRender(arg, filesOnly ? "f" : "a");
        }

        // ls 类型分类：0=目录 1=可执行 2=链接/特殊 3=普通 4=隐藏
        internal static int ParseLsSuffix(string name)
        {
            if (string.IsNullOrEmpty(name)) return 3;
            char last = name[name.Length - 1];
            if (last == '/') return 0;
            if (last == '*') return 1;
            if (last == '@' || last == '|' || last == '=') return 2;
            if (name[0] == '.') return 4;
            return 3;
        }

        // 剥离类型后缀（/ * @ | =），只留文件名
        private static string StripLsSuffix(string raw)
        {
            if (string.IsNullOrEmpty(raw)) return raw;
            char last = raw[raw.Length - 1];
            if (last == '/' || last == '*' || last == '@' || last == '|' || last == '=')
                return raw.Substring(0, raw.Length - 1);
            return raw;
        }

        private static bool BadLsOption(string s)
        {
            if (string.IsNullOrEmpty(s)) return false;
            return s.IndexOf("invalid option", StringComparison.OrdinalIgnoreCase) >= 0
                || s.IndexOf("unknown option", StringComparison.OrdinalIgnoreCase) >= 0
                || s.IndexOf("illegal option", StringComparison.OrdinalIgnoreCase) >= 0;
        }

        // 三档降级：-1pF（带分类后缀） -> -1p（只标目录） -> -1（裸）
        private static int LsCall(string lsp, out string outStr)
        {
            string e = "";
            int rc = ShellCall(CUR, "ls -1pF '" + lsp + "' 2>&1", out outStr, out e);
            if (BadLsOption(outStr))
                rc = ShellCall(CUR, "ls -1p '" + lsp + "' 2>&1", out outStr, out e);
            if (BadLsOption(outStr))
                rc = ShellCall(CUR, "ls -1 '" + lsp + "' 2>&1", out outStr, out e);
            return rc;
        }

        // 渲染 ls 结果（横向多列，按类型着色）
        private static void LsRender(string lsp, string mode)
        {
            if (string.IsNullOrEmpty(lsp)) lsp = CUR;
            string lshead = (string.Equals(lsp, CUR, StringComparison.OrdinalIgnoreCase)) ? "" : lsp;

            EnsureWidth();

            string outStr = "";
            string errDummy = "";
            int rc;

            if (mode == "f")
            {
                rc = ShellCall(CUR, "find '" + lsp + "' -maxdepth 1 -type f 2>&1", out outStr, out errDummy);
            }
            else
            {
                rc = LsCall(lsp, out outStr);
            }

            if (string.IsNullOrEmpty(outStr))
            {
                Fail("查询失败：设备连接中断");
                Hint("输入 rl 重试上次操作，或输入 r 刷新回到根目录");
                CMD_OK = false;
                return;
            }

            // 快路径：rc==0 且输出非空则跳过诊断
            if (!(rc == 0 && outStr.Trim().Length > 0))
            {
                string low = outStr.ToLowerInvariant();
                if (low.Contains("permission denied")) { Fail("列目录失败：Permission denied"); Hint("该目录需要 root，输入 r 重新连接会自动获取 root 权限"); return; }
                if (low.Contains("no such file")) { Fail("路径不存在：" + lsp); Hint("用 ls 查看当前目录内容，或输入 r 重连后重试"); return; }
                if (low.Contains("error: device") || low.Contains("device not found") || low.Contains("error: closed")) { Fail("查询失败：设备连接中断"); Hint("输入 rl 重试上次操作，或输入 r 刷新回到根目录"); CMD_OK = false; return; }
                if (low.Contains("command not found")) { Fail("设备上没有 find 命令，无法列出文件"); Hint("改用 ls 查看全部内容，或用 ls -l 查看详情"); return; }
                if (rc != 0)
                {
                    Fail("查询失败：未拿到任何结果（退出码 " + rc + "）");
                    Hint("设备可能已断开或 adb 异常，输入 rl 重试，r 刷新回目录");
                    PEND_K = "LS";
                    CMD_OK = false;
                    return;
                }
            }

            // 解析条目：剥掉类型后缀，记录分类用于着色
            List<string> items = new List<string>();
            List<int> classes = new List<int>();
            string[] rawLines = outStr.Split('\n');

            foreach (string line in rawLines)
            {
                string name = line.TrimEnd('\r').Trim();
                if (name.Length == 0) continue;

                int cls;
                if (mode == "f")
                {
                    name = LastSeg(name);
                    cls = 3;
                }
                else
                {
                    cls = ParseLsSuffix(name);
                    name = StripLsSuffix(name);
                }

                if (name.Length == 0) continue;
                if (string.Equals(name, lsp, StringComparison.OrdinalIgnoreCase)) continue;
                items.Add(name);
                classes.Add(cls);
            }

            if (items.Count == 0)
            {
                if (rc != 0)
                {
                    Fail("查询失败：未拿到任何结果（退出码 " + rc + "）");
                    Hint("设备可能已断开或 adb 异常，输入 rl 重试，r 刷新回目录");
                    PEND_K = "LS";
                    CMD_OK = false;
                    return;
                }
                if (lshead.Length > 0) { Console.WriteLine(); Console.WriteLine("  " + lshead); }
                Console.WriteLine("  （空）");
                return;
            }

            // 求最长显示宽度
            int maxl = 0;
            for (int i = 0; i < items.Count; i++)
            {
                int w = DispWidth(items[i]);
                if (w > maxl) maxl = w;
            }

            int cw = maxl + LS_GAP;
            if (cw < 4) cw = 4;
            int avail = LSW - 2;
            if (avail < cw) avail = cw;
            int nc = avail / cw;
            if (nc < 1) nc = 1;
            if (LS_MAXCOL > 0 && nc > LS_MAXCOL) nc = LS_MAXCOL;

            if (lshead.Length > 0) { Console.WriteLine(); Console.WriteLine("  " + lshead); }

            // 横向排布：等宽列，逐项输出以便按类型着色
            int col = 0;
            for (int i = 0; i < items.Count; i++)
            {
                if (col > 0) Console.Write(' ');
                WriteItem(items[i], classes[i]);

                int pad = cw - DispWidth(items[i]);
                if (pad < 0) pad = 0;

                col++;
                bool rowEnd = (col >= nc) || (i == items.Count - 1);
                if (rowEnd)
                {
                    Console.WriteLine();
                    col = 0;
                }
                else
                {
                    for (int k = 0; k < pad; k++) Console.Write(' ');
                }
            }

            // 统计行弱化（灰色），不抢主体内容
            UseDim();
            Console.WriteLine("  共 " + items.Count + " 项 · 目录 " + CountClass(classes, 0) + " · 文件 " + CountClass(classes, 3));
            UseDefault();
        }

        // 按分类输出条目颜色：目录青、可执行绿、链接洋红、隐藏灰、普通文件默认
        private static void WriteItem(string name, int cls)
        {
            if (!LS_COLOR) { Console.Write(name); return; }
            if (cls == 0) W(name, ConsoleColor.Cyan);
            else if (cls == 1) W(name, ConsoleColor.Green);
            else if (cls == 2) W(name, ConsoleColor.Magenta);
            else if (cls == 4) W(name, ConsoleColor.DarkGray);
            else Console.Write(name);
        }

        private static int CountClass(List<int> classes, int target)
        {
            int n = 0;
            for (int i = 0; i < classes.Count; i++) if (classes[i] == target) n++;
            return n;
        }

        // ==================== 七、pull / push ====================
        private static void DoPull(string argRaw)
        {
            List<string> args = SplitArgs(argRaw);
            if (args.Count == 0) { PullUsage(); return; }
            if (args.Count == 1)
            {
                if (IsWinPath(args[0])) { Export(CUR, LastSeg(CUR), args[0]); return; }
                Fail("还差一个电脑路径");
                Hint("例：pull 351 D:\\log");
                return;
            }
            string rmt = DevAbs(args[0]);
            string rms = LastSeg(rmt);
            Export(rmt, rms, args[1]);
        }

        private static void PullUsage()
        {
            Console.WriteLine("  用法：pull 设备路径 电脑路径");
            Console.WriteLine("        例：pull 351 D:\\log     （把设备上的 351 导出到 D:\\log）");
            Console.WriteLine("        简写：pull D:\\log       （把当前目录导出到 D:\\log）");
        }

        private static void DoPush(string argRaw)
        {
            List<string> args = SplitArgs(argRaw);
            if (args.Count == 0) { PushUsage(); return; }
            if (args.Count == 1) { PushDo(args[0], CUR); return; }
            PushDo(args[0], DevAbs(args[1]));
        }

        private static void PushUsage()
        {
            Console.WriteLine("  用法：push 电脑路径 设备路径");
            Console.WriteLine("        例：push D:\\fix.sh /data/local/tmp/");
            Console.WriteLine("        简写：push D:\\fix.sh    （推到当前目录）");
        }

        private static void PushDo(string local, string remote)
        {
            if (!File.Exists(local))
            {
                Fail("推送失败：本地文件不存在 " + local);
                return;
            }
            Echo("push", local + " -> " + remote);

            string combined = "";
            int rc = AdbCallStream(new List<string> { "push", local, remote }, out combined);
            if (rc != 0)
            {
                CMD_OK = false;
                if (rc < 0) { Info("推送已中断"); return; }
                Fail("推送失败：" + ExplainError(combined));
                return;
            }
            PEND_K = "";
            CMD_OK = true;
            Ok("推送完成");
        }

        // ==================== 八、透传 ====================
        private static void DoPass(string cmd, string argRaw)
        {
            string full = cmd;
            if (!string.IsNullOrEmpty(argRaw)) full = cmd + " " + argRaw;

            // 透传是**默认路径**，语义就是"照原样执行"，回显没有新增信息。
            // 只在输入被工具接管时回显（:which 之外，见 Dispatch 里的 Echo 调用点），
            // 否则每条命令多一行，一次会话能多出 30% 的噪音。

            // 内层双引号转义，保住外层引号
            string escaped = full.Replace("\"", "\\\"");

            string combined = "";
            int rc = ShellCallStream(CUR, escaped, out combined);

            if (rc != 0)
            {
                CMD_OK = false;
                if (rc < 0)
                {
                    Info("命令已中断");
                    return;
                }
                // 不要只说退出码 —— 把设备原话提炼出来
                Fail(ExplainError(combined));
                string tip = BuildTip(combined);
                if (tip.Length > 0) Hint("建议：" + tip);
                else Hint("检查命令拼写与参数；Windows 命令（findstr / find / dir）不能在设备上直接用");
            }
            else
            {
                CMD_OK = true;

                // 成功但一个字都没输出时给个回执。
                // 否则屏幕上只有下一行提示符，和"命令根本没执行"长得一模一样
                // —— am force-stop / setprop / pm install 这类命令都是静默的。
                if (combined.Trim().Length == 0)
                {
                    UseDim();
                    Console.WriteLine("  \u00B7 完成（无输出）");
                    UseDefault();
                }
            }
        }

        // 从输出里提炼一句人话；拿不到就给通用的
        private static string ExplainError(string output)
        {
            string msg = BuildErrMsg(output);
            if (string.IsNullOrEmpty(msg) || msg == "设备无返回信息")
                return "命令执行失败（设备没有返回具体原因）";
            return msg;
        }

        // ==================== 九、导出（直接输入电脑路径）====================
        private static void Export(string devPath, string devName, string localPath)
        {
            Export(devPath, devName, localPath, false);
        }

        // forceZip=true：强制打包导出（跳过 ShouldZip 的文件数判断）。
        // 用于「活动日志目录」这类导出——文件在设备侧实时轮转，逐文件 pull
        // 会在中途遇到文件被删/替换（remote open failed），整体失败。
        // 打包是原子操作，tar 对已消失的文件只是跳过警告，不会中断。
        private static void Export(string devPath, string devName, string localPath, bool forceZip)
        {
            string erl = localPath.Trim();
            if (erl.Length == 0) { Fail("导出失败：没有指定电脑上的目标路径"); Hint("例如输入 C:\\XX 或 D:\\log"); return; }

            // 用户手输路径时很容易打出 "logcat\\2026-11-13"（两个反斜杠）。
            // Windows 能接受，但显示出来很脏，也会影响后面的"末段"判断 —— 先规范化。
            erl = NormalizeWinPath(erl);

            // 去掉末尾多余分隔符（保留盘符根 C:\）
            bool erlEndsSep = (erl.EndsWith("\\") || erl.EndsWith("/"));
            if (erlEndsSep && erl.Length > 3) erl = erl.TrimEnd('\\', '/');
            if (erl.Length == 2 && erl[1] == ':') erl = erl + "\\";

            // 【v7.15 修复 BUG-04】先判断"用户给的是目录还是文件"，再决定要不要拼源名。
            //
            // 旧版无条件按目录处理（末段 != 源名就追加源名），于是
            //     pull xxx.zst C:\_t9\one.zst
            // 被拼成 C:\_t9\one.zst\xxx.zst —— 用户想起个新文件名都做不到。
            //
            // 判定规则（宁可有扩展名，也不误判目录）：
            //   · 末尾带分隔符            -> 目录
            //   · 已存在的目录            -> 目录
            //   · 末段含 '.'（像扩展名）  -> 文件
            //   · 其它                    -> 目录（C:\out 这种）
            string lastSegOfTarget = LastSegWin(erl);
            bool targetIsFile = false;
            if (!erlEndsSep)
            {
                try
                {
                    if (!Directory.Exists(erl) && lastSegOfTarget.IndexOf('.') > 0)
                        targetIsFile = true;
                }
                catch { }
            }

            bool devIsDir = IsDevDir(devPath);

            // 单文件导出：目标按"文件名"解释，不追加源名
            if (!devIsDir && targetIsFile)
            {
                ExportOneFile(devPath, erl);
                return;
            }

            // 单文件导出：目标按"目录"解释，落点 = 目录 + 源文件名
            //
            // 【v7.15 修复 BUG-04b】旧版先按"末段 != 源名就追加源名"把 etarget 算成
            // C:\_t10\<源名>，走到下面单文件分支时又拼了一次 srcName，
            // 于是落点变成 _t10\<源名>\<源名>（多一层同名目录）。
            // 现在单文件的两条路都在这里一次算清最终文件路径，直接返回，
            // 不再参与 UniqueTarget、打包、文件数统计这些"目录才有意义"的逻辑。
            if (!devIsDir)
            {
                string srcName1 = LastSeg(devPath);
                if (srcName1.Length == 0 || srcName1 == "/") srcName1 = devName;
                ExportOneFile(devPath, JoinWin(erl, srcName1));
                return;
            }

            string etarget;
            if (EXPORT_FLAT)
            {
                etarget = erl;
            }
            else
            {
                // 末段与源同名就不再套一层（用户已经写到这一层了）
                string lname = LastSegWin(erl);
                if (string.Equals(lname, devName, StringComparison.OrdinalIgnoreCase))
                    etarget = erl;
                else
                    etarget = JoinWin(erl, devName);
            }

            // 不询问：目标已存在且非空时，自动换一个带时间戳的目录。
            // 原则是「可恢复 > 可确认」—— 连选错的机会都不给，比事后问一句更可靠。
            string asked = etarget;
            etarget = UniqueTarget(etarget);

            // 【v7.15 修复 BUG-06】记录本次导出**之前**目标目录是否已经存在。
            // 失败时如果这个目录是我新建的、而且里面什么都没有，就删掉它。
            // 否则用户会看到一个"_t11"这样的空目录，很容易误以为导出成功了。
            bool targetExistedBefore = false;
            try { targetExistedBefore = Directory.Exists(etarget); } catch { targetExistedBefore = true; }

            Echo("export", devPath + " -> " + etarget);
            if (!string.Equals(asked, etarget, StringComparison.OrdinalIgnoreCase))
            {
                Hint("目标已存在，自动写到新目录（不覆盖）：" + etarget);
            }

            // 自动打包：目录 + 文件数超阈值时，设备端先 tar 成一个文件再 pull。
            // 小文件多的时候 adb pull 是逐个传的（每个文件都有协议往返），
            // 打包后只传 1 个文件，通常快一个数量级。
            // forceZip：强制打包（活动日志目录导出用，避开文件轮转竞态）。
            if (EXPORT_ZIP > 0 && (forceZip || ShouldZip(devPath)))
            {
                if (ExportZipped(devPath, devName, etarget)) return;
                Info("改为普通导出（逐文件拉取）");
            }

            // 目标已存在时已在上面换成了时间戳目录，这里不再询问、也不会覆盖
            //
            // 【v7.15 关键修复：导出目录双嵌套】
            //
            // adb pull 的语义是"目标若已存在目录，就在它下面再建一层源目录名"：
            //     mkdir out && adb pull /data/anr out   ->  out/anr/...
            // 旧版先 CreateDirectory(etarget) 再 pull(devPath, etarget)，
            // 于是 etarget 已存在 -> adb 又套一层同名目录 -> out/288/288/。
            // 实测复现：`pull C:\_t_pull`（在 288 里）得到 _t_pull/288/288/62 个文件。
            //
            // 正确做法：不要预建 etarget，让 adb 自己建。
            //   · 目录：pull 到 etarget 的父目录，adb 会建出 ...\<源末段>
            //   · 文件：pull 到 etarget 的父目录也需要改名，所以走单独分支
            // 这样无论 export_flat 与否，落点都只由 etarget 决定，不会多一层。
            string etargetParent = ParentOfWin(etarget);

            try
            {
                if (!Directory.Exists(etargetParent)) Directory.CreateDirectory(etargetParent);
            }
            catch
            {
                Fail("导出失败：无法创建目录 " + etargetParent);
                Hint("检查路径拼写、盘符权限，或换一个目录");
                return;
            }

            string combined = "";
            int rc;

            string srcName = LastSeg(devPath);
            if (string.IsNullOrEmpty(srcName) || srcName == "/") srcName = "";

            // 走到这里一定是目录导出（单文件两条路已在上面 return）。
            //
            // 约定：**etarget 就是最终落点**，不多一层也不少一层。
            //
            // adb pull 的落点规则（实测）：
            //   目标不存在         -> 目标被当作新名字，内容直接进目标
            //   目标是已存在目录   -> 在它下面再建一层源目录名
            //
            // 所以目录导出最简单的做法是：**不要预建 etarget**，
            // 直接 pull(devPath, etarget)，adb 会把 devPath 的内容放进 etarget。
            // 旧版预建了 etarget，于是触发"再建一层"，得到 out/288/288。
            //
            // 兜底：万一 adb 版本行为不同（落到了 etarget/<srcName>），
            // pull 完做一次落点校正，把内容上移一层并删掉空壳。
            rc = AdbCallStream(new List<string> { "pull", devPath, etarget }, out combined);

            if (rc == 0 && srcName.Length > 0 && Directory.Exists(etarget))
            {
                // 校正：如果 etarget 下只有一个同名子目录，说明 adb 多套了一层
                string inner = JoinWin(etarget, srcName);
                if (!string.Equals(inner.TrimEnd('\\'), etarget.TrimEnd('\\'), StringComparison.OrdinalIgnoreCase)
                    && Directory.Exists(inner))
                {
                    try
                    {
                        if (Directory.GetFileSystemEntries(etarget).Length == 1)
                        {
                            MoveDirContents(inner, etarget);
                            TryDeleteDir(inner);
                        }
                    }
                    catch { }
                }
            }

            if (rc != 0)
            {
                // 用户 Ctrl+C 中断：保持原样（这不是失败，也不是部分成功）
                if (rc < 0)
                {
                    PEND_K = "PULL"; PEND_R = devPath; PEND_N = devName; PEND_A = erl;
                    CMD_OK = false;
                    Info("导出已中断");
                    CleanupFailedTarget(etarget, targetExistedBefore);
                    return;
                }

                // 【关键口径】目录 pull 的返回码只反映"有没有任何一个文件失败"。
                // 活动日志目录里文件在实时轮转，拷到一半被删是常态（remote open failed），
                // 89% 已经落地却报"导出失败"，用户会以为整次白干了。
                // 已经落了文件就按"部分成功"报，并把失败的那几个单独补拉一次。
                int landed = CountLocalFiles(etarget);
                List<string> bad = ParsePullFailures(combined);

                if (landed > 0)
                {
                    int fixedCount = RetryFailedPulls(bad, etarget, 20);
                    landed = CountLocalFiles(etarget);
                    int left = bad.Count - fixedCount;

                    if (left <= 0)
                    {
                        PEND_K = "";
                        CMD_OK = true;
                        Ok("导出完成（" + landed + " 个文件"
                           + (fixedCount > 0 ? "，其中 " + fixedCount + " 个补拉成功" : "") + "）");
                        return;
                    }

                    PEND_K = "PULL"; PEND_R = devPath; PEND_N = devName; PEND_A = erl;
                    CMD_OK = true;      // 部分成功不是失败：不能让界面整条标红
                    Warn("部分成功：已导出 " + landed + " 个文件，" + left + " 个没拉下来");
                    for (int i = 0; i < bad.Count && i < 5; i++)
                        Hint("  失败：" + ShortPath(bad[i], 60));
                    if (bad.Count > 5) Hint("  另有 " + (bad.Count - 5) + " 个失败文件未列出");
                    Hint("失败的多半是正在写入/轮转的日志；改用 :dlog 会先在设备端打包再拉，最稳");
                    return;
                }

                PEND_K = "PULL"; PEND_R = devPath; PEND_N = devName; PEND_A = erl;
                CMD_OK = false;
                Fail("导出失败：" + ExplainError(combined));
                CleanupFailedTarget(etarget, targetExistedBefore);
                Hint("输入 rl 可自动重试本次导出；先确认目录是否存在、是否需要 root");
                return;
            }

            int fn = 0;
            try { fn = Directory.GetFiles(etarget, "*", SearchOption.AllDirectories).Length; }
            catch { fn = -1; }

            // 【v7.15 修复 BUG-05】旧版 fn 取不到时是 -1，却照样打印"导出完成（-1 个文件）"。
            // -1 只表示"数不出来"（权限/瞬时空目录），不是"没导出"，不能当失败，
            // 更不能原样显示给用户。
            if (fn == 0)
            {
                Fail("导出失败：没有取到任何文件");
                CleanupFailedTarget(etarget, targetExistedBefore);
                Hint("确认该目录里确实有文件，可用 lsf 查看同目录下的文件");
                return;
            }
            PEND_K = "";
            CMD_OK = true;
            if (fn > 0) Ok("导出完成（" + fn + " 个文件）");
            else Ok("导出完成（文件数未能统计，请到目标目录确认）");
        }

        // 路径规范化：把连续的 "\" 压成一个（UNC 前缀 \\server 保留）。
        // 用户手输 "Desktop\logcat\\2026-11-13" 很常见，Windows 能跑但显示脏。
        internal static string NormalizeWinPath(string p)
        {
            if (string.IsNullOrEmpty(p)) return p;
            bool unc = p.StartsWith("\\\\", StringComparison.Ordinal);
            string body = unc ? p.Substring(2) : p;
            while (body.IndexOf("\\\\", StringComparison.Ordinal) >= 0)
                body = body.Replace("\\\\", "\\");
            return unc ? "\\\\" + body : body;
        }

        private static int CountLocalFiles(string dir)
        {
            try
            {
                if (!Directory.Exists(dir)) return 0;
                return Directory.GetFiles(dir, "*", SearchOption.AllDirectories).Length;
            }
            catch { return 0; }
        }

        // 从 adb pull 的输出里挖出"哪些远端文件没拉下来"。
        // 两种已知格式：
        //   adb: error: failed to copy '/log/x.txt' to 'C:\...': remote open failed
        //   adb: error: failed to stat remote object '/log/y.txt': No such file
        internal static List<string> ParsePullFailures(string output)
        {
            List<string> list = new List<string>();
            if (string.IsNullOrEmpty(output)) return list;

            string[] lines = output.Split('\n');
            for (int i = 0; i < lines.Length; i++)
            {
                string s = lines[i].TrimEnd('\r').Trim();
                if (s.Length == 0) continue;
                if (s.IndexOf("failed to copy", StringComparison.OrdinalIgnoreCase) < 0
                    && s.IndexOf("failed to stat", StringComparison.OrdinalIgnoreCase) < 0)
                    continue;

                int a = s.IndexOf('\'');
                if (a < 0) continue;
                int b = s.IndexOf('\'', a + 1);
                if (b <= a + 1) continue;

                string remote = s.Substring(a + 1, b - a - 1).Trim();
                if (remote.Length == 0) continue;
                if (list.IndexOf(remote) >= 0) continue;
                list.Add(remote);
            }
            return list;
        }

        // 只重试失败的几个文件（单文件 pull，落点是目录，名字自动沿用远端末段）。
        // 上限 max 防止"几万个失败"把导出拖成半小时。
        private static int RetryFailedPulls(List<string> bad, string localDir, int max)
        {
            if (bad == null || bad.Count == 0) return 0;
            int n = (bad.Count < max) ? bad.Count : max;

            int ok = 0;
            for (int i = 0; i < n; i++)
            {
                string combined = "";
                int rc = AdbCallStream(new List<string> { "pull", bad[i], localDir }, out combined);
                if (rc == 0) ok++;
            }
            return ok;
        }

        // 单文件导出：dst 是**完整目标文件名**（已经是文件，不是目录）
        private static void ExportOneFile(string devPath, string dst)
        {
            // BUG-06 同类问题：失败时不要留下"我新建的空目录 + 半截文件"
            string dp = ParentOfWin(dst);
            bool parentExistedBefore = false;
            try { parentExistedBefore = Directory.Exists(dp); } catch { parentExistedBefore = true; }
            bool fileExistedBefore = false;
            try { fileExistedBefore = File.Exists(dst); } catch { fileExistedBefore = true; }

            string combined = "";
            int rc = ExportOneFileCore(devPath, dst, out combined);

            if (rc != 0)
            {
                PEND_K = "PULL"; PEND_R = devPath; PEND_N = LastSeg(devPath);
                PEND_A = dp;
                CMD_OK = false;

                // adb 失败时可能在目标处留下 0 字节文件，删掉（原本不存在的才删）
                try
                {
                    if (!fileExistedBefore && File.Exists(dst) && new FileInfo(dst).Length == 0)
                        File.Delete(dst);
                }
                catch { }
                CleanupFailedTarget(dp, parentExistedBefore);

                if (rc < 0) { Info("导出已中断"); return; }
                Fail("导出失败：" + ExplainError(combined));
                Hint("输入 rl 可自动重试本次导出；先确认文件是否存在、是否需要 root");
                return;
            }

            long size = 0;
            try { size = new FileInfo(dst).Length; } catch { }

            PEND_K = "";
            CMD_OK = true;
            Ok("导出完成：" + dst + (size > 0 ? "（" + FormatSize(size) + "）" : ""));
        }

        // 单文件导出的公共实现。dst 必须是最终文件名，返回 adb 的退出码。
        private static int ExportOneFileCore(string devPath, string dst, out string combined)
        {
            string dp = ParentOfWin(dst);
            try
            {
                if (dp.Length > 0 && !Directory.Exists(dp)) Directory.CreateDirectory(dp);
            }
            catch
            {
                combined = "无法创建目录 " + dp;
                return 1;
            }

            // 目标已存在就当覆盖（单文件导出，用户已经指名道姓）
            try { if (File.Exists(dst)) File.Delete(dst); } catch { }

            Echo("export", devPath + " -> " + dst);
            return AdbCallStream(new List<string> { "pull", devPath, dst }, out combined);
        }

        // Windows 路径拼接：目录 + 文件名，处理好末尾分隔符与正/反斜杠。
        // v7.15 抽出来是为了让"单文件落点"这条规则**只有一份实现**：
        // 导出的真实路径和自检里的断言走同一个函数，避免"测的是测试代码"。
        private static string JoinWin(string dir, string name)
        {
            if (string.IsNullOrEmpty(dir)) return name == null ? "" : name;
            if (string.IsNullOrEmpty(name)) return dir;
            string d = dir.TrimEnd('\\', '/');
            if (d.Length == 0) d = dir.Substring(0, 1);          // 用户传了 "\" 或 "/"
            if (d.Length == 2 && d[1] == ':') d = d + "\\";       // C: -> C:\
            return d + "\\" + name.TrimStart('\\', '/');
        }

        // Windows 路径最后一段：C:\a\b => b   C:/a/b => b   C:\ => ""
        //
        // 【v7.15 修复】旧版只认反斜杠。用户写 C:/out/288（正斜杠在 Windows
        // 和 cmd/PowerShell 里都合法）时，LastSegWin 返回整串 "C:/out/288"，
        // 于是 Export 判定"末段与源目录名不同"，又追加了一层 288
        // -> C:/out/288/288。判定必须同时认两种分隔符。
        private static string LastSegWin(string p)
        {
            if (string.IsNullOrEmpty(p)) return "";
            string t = p.TrimEnd('\\', '/');
            if (t.Length == 0) return "";
            if (t.Length == 2 && t[1] == ':') return "";      // C: 这种盘符根
            int i = t.LastIndexOfAny(new char[] { '\\', '/' });
            if (i < 0) return t;
            return t.Substring(i + 1);
        }

        // ==================== 导出落点辅助（v7.15）====================

        private static string Stamp()
        {
            return DateTime.Now.ToString("HHmmss") + "_" + Environment.TickCount.ToString();
        }

        // 把 from 目录里的**内容**移动进 to（不是把 from 整个搬进 to）。
        // 只在"adb 落点与我指定的路径不一致"时用来纠正，因此必须吃掉同名目录那一层。
        private static int MoveDirContents(string from, string to)
        {
            try
            {
                if (!Directory.Exists(from)) return -1;
                if (!Directory.Exists(to)) Directory.CreateDirectory(to);

                foreach (string f in Directory.GetFiles(from))
                {
                    string dst = JoinWin(to, Path.GetFileName(f));
                    if (File.Exists(dst)) { try { File.Delete(dst); } catch { } }
                    File.Move(f, dst);
                }
                foreach (string d in Directory.GetDirectories(from))
                {
                    string name = Path.GetFileName(d);
                    string dst = JoinWin(to, name);
                    if (Directory.Exists(dst))
                    {
                        // 递归合并（同名子目录继续往下并）
                        MoveDirContents(d, dst);
                    }
                    else
                    {
                        Directory.Move(d, dst);
                    }
                }
                return 0;
            }
            catch { return -1; }
        }

        private static void TryDeleteDir(string p)
        {
            try
            {
                if (Directory.Exists(p) && Directory.GetFileSystemEntries(p).Length == 0)
                    Directory.Delete(p);
            }
            catch { }
        }

        // 导出失败后清理"我自己建出来但一个文件都没拿到"的空目录。
        //
        // 约束（不可放宽）：
        //   · 只在 targetExistedBefore == false 时动手 —— 用户原本就有的目录绝不动
        //   · 只删**空**目录，且只删 etarget 这一层，不递归、不碰父目录
        //   · 任何异常都吞掉，清理失败不影响错误提示的展示
        //   · 最外层兜底：绝不删盘符根（C:\）和长度 <= 3 的路径
        private static void CleanupFailedTarget(string etarget, bool targetExistedBefore)
        {
            if (targetExistedBefore) return;
            if (string.IsNullOrEmpty(etarget)) return;

            string t = etarget.TrimEnd('\\', '/');
            if (t.Length <= 3) return;                       // C:\ 或 D:\ 之类
            if (t.Length == 2 && t[1] == ':') return;

            try
            {
                if (!Directory.Exists(t)) return;
                if (Directory.GetFileSystemEntries(t).Length != 0) return;
                Directory.Delete(t);
            }
            catch { return; }
            Info("已清掉本次新建的空目录：" + t);
        }

        // ==================== 打包导出 ====================
        // 是否值得打包：必须是目录，且（总是打包 或 文件数达到阈值）
        private static bool ShouldZip(string devPath)
        {
            if (!IsDevDir(devPath)) return false;
            if (EXPORT_ZIP == 1) return true;

            int n = CountDevFiles(devPath);
            if (n <= 0) return false;
            return n >= EXPORT_ZIP_MIN;
        }

        private static bool IsDevDir(string p)
        {
            string o = "";
            string e = "";
            ShellCall(CUR, "test -d '" + p + "' && echo Y || echo N", out o, out e);
            return string.Equals(FirstLine(o).Trim(), "Y", StringComparison.Ordinal);
        }

        private static int CountDevFiles(string p)
        {
            string o = "";
            string e = "";
            ShellCall(CUR, "find '" + p + "' -type f 2>/dev/null | wc -l", out o, out e);
            string s = FirstLine(o).Trim();

            int n = 0;
            if (int.TryParse(s, out n)) return n;
            return 0;
        }

        // 设备端 tar -> pull 单个包 -> 删设备临时文件
        private static bool ExportZipped(string devPath, string devName, string etarget)
        {
            string ts = DateTime.Now.ToString("yyyyMMdd_HHmmss");
            string tmp = "/data/local/tmp/adbexp_" + ts + ".tar.gz";

            string parent = ParentOf(devPath);
            string baseName = LastSeg(devPath);
            if (string.IsNullOrEmpty(baseName) || baseName == "/") baseName = ".";

            // cd 到父目录再 tar 相对路径，避免包里嵌套绝对路径
            string tarCmd = "cd '" + parent + "' && tar -czf '" + tmp + "' '" + baseName + "'";

            Info("设备端打包中（文件多时会比逐文件拉取快很多）...");
            string o = "";
            string e = "";
            int rc = ShellCall(CUR, tarCmd, out o, out e);

            // 【缺陷修复】活动日志目录里文件在实时轮转，tar 读到一半遇到文件
            // 被删会返回非 0（toybox tar 有时还不给 stderr）。这种竞态是偶发的，
            // 重试一次通常就过了 —— 比直接回退到逐文件拉取（更危险）可靠得多。
            if (rc != 0)
            {
                try { Thread.Sleep(400); } catch { }
                o = ""; e = "";
                rc = ShellCall(CUR, tarCmd, out o, out e);
            }

            if (rc != 0)
            {
                string low = (o + e).ToLowerInvariant();
                string first = FirstLine(o + e);
                if (low.IndexOf("tar: not found", StringComparison.Ordinal) >= 0 ||
                    low.IndexOf("not found", StringComparison.Ordinal) >= 0)
                    Warn("设备上没有 tar 命令，无法打包");
                else if (first.Length == 0)
                    // toybox tar 对"文件正在轮转被删"这类竞态有时静默失败（无输出），
                    // 不是真缺 tar，也不是语法错，直接提示转逐文件导出即可。
                    Warn("设备端打包失败（日志文件轮转中），改为逐文件导出");
                else
                    Warn("设备端打包失败：" + first);
                return false;
            }

            // 本地目标：与目录同级，名字带时间戳
            string zipDir = ParentOfWin(etarget);
            string zipPath = zipDir + "\\" + SanitizeName(devName) + "_" + ts + ".tar.gz";

            try
            {
                if (!Directory.Exists(zipDir)) Directory.CreateDirectory(zipDir);
            }
            catch
            {
                Fail("导出失败：无法创建目录 " + zipDir);
                CleanupDevTmp(tmp);
                return false;
            }

            Console.WriteLine("  -> " + zipPath);
            string combined = "";
            rc = AdbCallStream(new List<string> { "pull", tmp, zipPath }, out combined);

            CleanupDevTmp(tmp);

            if (rc != 0)
            {
                CMD_OK = false;
                if (rc < 0) { Info("导出已中断"); return false; }
                Fail("打包导出失败：" + ExplainError(combined));
                return false;
            }

            long size = 0;
            try { size = new FileInfo(zipPath).Length; } catch { }

            PEND_K = "";
            CMD_OK = true;

            Console.WriteLine();
            Ok("已打包导出：" + zipPath);
            Hint("大小 " + FormatSize(size) + "，用 7-Zip / WinRAR / tar 解压即可");
            Hint("想直接导出成文件夹请把 ini 的 export_zip 设为 0");
            return true;
        }

        private static void CleanupDevTmp(string tmp)
        {
            string o = "";
            string e = "";
            ShellCall(CUR, "rm -f '" + tmp + "'", out o, out e);
        }

        // 设备路径的父目录：/a/b/c => /a/b   /a => /
        private static string ParentOf(string p)
        {
            string t = p.TrimEnd('/');
            int i = t.LastIndexOf('/');
            if (i <= 0) return "/";
            return t.Substring(0, i);
        }

        // 目标目录已存在且非空时，派生一个带时间戳的新目录（绝不覆盖）
        private static string UniqueTarget(string p)
        {
            bool exists = false;
            bool nonEmpty = false;
            try
            {
                exists = Directory.Exists(p);
                if (exists) nonEmpty = Directory.GetFileSystemEntries(p).Length > 0;
            }
            catch { return p; }

            if (!exists || !nonEmpty) return p;

            string stamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
            string cand = p + "_" + stamp;
            int i = 2;
            while (Directory.Exists(cand))
            {
                cand = p + "_" + stamp + "_" + i;
                i++;
            }
            return cand;
        }

        // Windows 路径的父目录：D:\a\b => D:\a   D:/a/b => D:/a   D:\ => D:\
        // v7.15：同时认正反斜杠（正斜杠在 Windows 上合法，用户经常混写）
        private static string ParentOfWin(string p)
        {
            if (string.IsNullOrEmpty(p)) return "";
            string t = p.TrimEnd('\\', '/');
            if (t.Length <= 2) return t.Substring(0, Math.Min(2, t.Length)) + "\\";
            int i = t.LastIndexOfAny(new char[] { '\\', '/' });
            if (i <= 0) return t.Substring(0, 2) + "\\";
            if (i == 2) return t.Substring(0, 3);
            return t.Substring(0, i);
        }

        // 文件名里不能出现的字符替换成下划线
        private static string SanitizeName(string n)
        {
            if (string.IsNullOrEmpty(n)) return "export";
            StringBuilder sb = new StringBuilder(n.Length);
            char[] bad = new char[] { '\\', '/', ':', '*', '?', '"', '<', '>', '|' };
            for (int i = 0; i < n.Length; i++)
            {
                char c = n[i];
                bool hit = false;
                for (int k = 0; k < bad.Length; k++)
                {
                    if (c == bad[k]) { hit = true; break; }
                }
                sb.Append(hit ? '_' : c);
            }
            return sb.ToString();
        }

        private static string FormatSize(long b)
        {
            if (b < 1024) return b + " B";
            if (b < 1024 * 1024) return (b / 1024) + " KB";
            if (b < 1024L * 1024 * 1024) return (b / (1024 * 1024)) + " MB";
            return (b / (1024L * 1024 * 1024)) + " GB";
        }

        // ==================== 十、刷新 / 重连 ====================
        //
        // v7.13：这里原来是"800ms × 5 次 = 4 秒内搜不到就判定失败"，
        // 而且每次探测走 ScanDev -> AdbCall（30 秒超时）。真机上拔插一次，
        // 车机 adbd 重启 + USB 重新枚举经常要 3~6 秒，4 秒窗口根本不够；
        // 一旦 adb 卡住，一次探测就吃掉 30 秒，用户看到的是"点了重连，卡住，
        // 然后说搜不到设备"。
        //
        // 现在统一交给 Rec.WaitDevice：渐进退避 + 自动 reconnect offline +
        // 超时就重启服务，全程有上限，绝不无限等。
        private static void RetrySoft()
        {
            Console.WriteLine("  [刷新] 等待设备上线（最多 15 秒，会自动处理 offline 残留）...");

            bool ok = Rec.WaitDevice(15000, true, true);

            if (!ok || DEVN == 0)
            {
                Fail("刷新失败：15 秒内设备仍未上线");
                Hint("先看体检报告，再按提示处理：");
                Console.Write(Rec.Diagnose());
                Hint("常见处理：车机上点「允许 USB 调试」；换一根数据线；关掉其他占用 adb 的软件后按 :rr");
                return;
            }

            AutoRoot();
            // 2026-11-21：刷新**不再重置当前目录**。
            // 原来这里写死 CUR = ROOT + 末尾 LsAfterCd()，用户只是想重连，结果目录被
            // 拽回根目录、还多打印一屏 ls —— 用户原话"仅显示要输出的信号，不要再执行 cd"。
            // 只在当前目录确实失效（设备重启/目录被删）时才回退。
            if (!DirStillValid()) CUR = ROOT;
            OLDPWD = "";
            Probe();
            CMD_OK = true;
            OFFLINE = false;
            Ok("已刷新" + (CUR == ROOT ? "，当前目录 " + CUR : ""));

            // 【需求3】刷新要把车机信息重新取一遍并输出。
            // 用户原话："r 指令刷新的时候要把打开应用要获取的数据和执行的执行都操作下输出显示"
            // —— 也就是刷新的语义不只是"重连 adb"，还要把打开工具时自动采集的
            // 那批数据（9 项车机信息）重新查一次，并把查询过程显示出来。
            RenderCarInfoOnRefresh();
            // 2026-11-21：不再 LsAfterCd() —— 没 cd 就不该 ls
        }

        // 【需求6】自动重连专用：与 RetrySoft 同一条路径，但**失败完全静默**。
        //
        // 用户要求："监听到设备连接了设备后台自动输入 r 重连，连接成功输出信息，
        //            连接失败不要输出任何信息"
        //
        // 为什么不能直接复用 RetrySoft：
        //   它在失败时会 Fail(...) + Hint(...) + 打印体检报告，一共十几行。
        //   自动重连是后台能力，设备刚插上 N 毫秒内连接不稳定是常态，
        //   每次都甩一屏红字，用户会以为工具坏了。
        //
        // 成功路径保持完整输出（含九项车机信息），因为那是用户想看到的结果。
        /// <summary>当前目录是否还能用（刷新时决定要不要回退到 ROOT）。
        /// 故意不查设备：多一次 shell 往返既慢又可能失败，失败会把用户目录误重置。
        /// 只做本地合法性判断 —— 路径真失效时后续命令自己会报错，用户 cd 一下即可。</summary>
        private static bool DirStillValid()
        {
            return !string.IsNullOrEmpty(CUR) && CUR.StartsWith("/", StringComparison.Ordinal);
        }

        internal static void RetrySoftForWatch()
        {
            bool ok = Rec.WaitDevice(15000, true, true);
            if (!ok || DEVN == 0) return;      // 静默失败

            AutoRoot();
            if (!DirStillValid()) CUR = ROOT;   // 2026-11-21：同上，别重置目录
            OLDPWD = "";
            Probe();
            CMD_OK = true;
            OFFLINE = false;

            Ok("已自动重连");
            RenderCarInfoOnRefresh();
        }

        // 刷新/重连后统一输出车机信息（需求3）。
        // 这里必须"先显示正在查什么、再显示查到的值"，因为断链重连后
        // 用户最关心的就是"设备到底是不是原来那台、关键参数对不对"，
        // 只给结论不给过程会让人怀疑数据是缓存的旧值。
        internal static void RenderCarInfoOnRefresh()
        {
            Console.WriteLine();
            Console.WriteLine("  [刷新] 重新读取车机信息 ...");

            if (OFFLINE || DEVN == 0)
            {
                Warn("设备不在线，跳过车机信息采集");
                return;
            }

            bool got = LoadCarInfo();
            if (!got)
            {
                // 采集全空：可能是刚连上还没就绪，也可能属性全没配
                Warn("车机信息读取为空（设备可能尚未就绪，可再按一次 r）");
                return;
            }

            // 2026-11-23（第 21 批）：GUI 模式下**不打印命令回显**。
            //
            // 现象：用户在 GUI 的终端页看到
            //   $ adb shell getprop sys.product.gacvehicleplatform/ro.product...
            //   $ adb shell wm size
            //   （然后是车机信息表格）
            // 原因：这段"把执行的命令列出来"是给 CLI 看的，
            //       而 GUI 也复用了 RetryRefresh()，Console 输出被 GuiSink
            //       捕获后当成终端行渲染 —— 终端页于是混进了页面功能的数据。
            // 处理：只跳过这两行"过程回显"，下面的 RenderCarInfo 表格照常输出
            //       （用户要的是"保留结果，不显示长命令"）。
            if (!App.GUI_MODE)
            {
                UseDim();
                Console.Write("  $ adb shell getprop ");
                Console.Write(string.Join("/", new string[]
                {
                    "sys.product.gacvehicleplatform",
                    "ro.product.version.short_name",
                    "sys.vehicle.mcu.version",
                    "ro.build.version.release",
                    "persist.sys.vehicle.vin",
                    "persist.sys.navi.uuid",
                    "persist.sys.navi.did",
                    "persist.sys.navi.openid"
                }));
                Console.WriteLine();
                UseDim();
                Console.WriteLine("  $ adb shell wm size");
                UseDefault();
                Console.WriteLine();
            }

            // 再输出 9 项取值（对齐成列）
            RenderCarInfo(false, false);
            Ok("车机信息已刷新（" + CAR_TOTAL + " 项）");
        }

        private static void RetryHard()
        {
            Console.WriteLine("  [重连] 正在重启 adb 服务（清掉僵死的 server 和残留传输）...");
            bool ok = Rec.ResetServer(true);
            if (!ok)
            {
                Warn("adb 服务启动不顺利，继续尝试连接设备 ...");
            }

            Console.WriteLine("  [重连] 等待设备重新枚举（最多 20 秒）...");
            // allowRecover=false：服务刚刚重启过，这里只负责等。
            // 如果这里还允许自动重启，会变成 "重启→等不到→再重启" 的循环，
            // 每轮都把刚开始枚举的 server 又打掉，设备永远上不来。
            bool dev = Rec.WaitDevice(20000, false, true);

            if (!dev || DEVN == 0)
            {
                Fail("重连完成，但设备仍未上线");
                Hint("体检报告：");
                Console.Write(Rec.Diagnose());
                Hint("按体检结果处理；确认 adb devices 在命令行能列出来之后再按 :r");
                return;
            }

            AutoRoot();
            CUR = ROOT;
            OLDPWD = "";
            Probe();
            CMD_OK = true;
            OFFLINE = false;
            Ok("已重连：" + DEVID + "，当前目录 " + CUR);

            // 需求3：重连同样要把车机信息重新取一遍
            RenderCarInfoOnRefresh();

            LsAfterCd();
        }

        // rl = 重试。三档，按"用户想要的强度"排列：
        //   1) 有结构化的待重试项（cd/ls/pull 失败时留下的现场）-> 用原参数重做
        //   2) 上一条命令失败过 -> 原样重跑它
        //   3) 上一条命令成功 -> 仍然重跑它（多数人敲 rl 就是想"再来一次"）
        // 旧实现只认第 1 档，所以设备在线、命令也成功时敲 rl 会回一句"没有可重试的操作"，
        // 看起来像功能坏了 —— 这次把 2/3 补上。
        private static void RetryLast()
        {
            // 离线时先连设备：没设备就没有可重试的对象
            if (OFFLINE)
            {
                Console.WriteLine("  [重试] 设备当前离线，先尝试连接 ...");
                if (!InitEnv())
                {
                    OFFLINE = true;
                    Fail("仍然没有可用设备");
                    Hint("检查数据线/USB 调试授权；连上后会自动连接，也可输入 :rr 重启 adb 服务");
                    return;
                }
            }

            // ---- 1) 结构化重试：还原现场（cd / ls / 导出）----
            if (!string.IsNullOrEmpty(PEND_K))
            {
                Console.WriteLine("  [重试] 准备重做上次失败的操作 ...");
                // 设备掉线后常常要 3~6 秒才重新枚举出来，给足窗口并顺带清 offline
                if (!Rec.WaitDevice(12000, true, true) || DEVN == 0)
                {
                    Fail("重试失败：12 秒内设备仍未上线");
                    Hint("看体检报告定位：");
                    Console.Write(Rec.Diagnose());
                    Hint("也可直接按 :rr 重启 adb 服务");
                    return;
                }

                AutoRoot();
                CMD_OK = true;

                string k = PEND_K.ToUpperInvariant();
                if (k == "CD") { Console.WriteLine("  重做上次操作：cd " + PEND_R); CdDo(PEND_R); }
                else if (k == "LS") { Console.WriteLine("  重做上次操作：ls"); LsRender(CUR, "a"); }
                else if (k == "PULL") { Console.WriteLine("  重做上次操作：导出 " + PEND_R + " -> " + PEND_A); Export(PEND_R, PEND_N, PEND_A); }
                return;
            }

            // ---- 2)/3) 重跑上一条命令 ----
            string target = "";
            bool wasFail = false;

            if (!string.IsNullOrEmpty(LAST_FAIL_CMD)) { target = LAST_FAIL_CMD; wasFail = true; }
            else if (!string.IsNullOrEmpty(LAST_CMD)) { target = LAST_CMD; }

            if (target.Length == 0)
            {
                Console.WriteLine("  没有可重试的操作");
                Hint("先执行一条命令，再敲 rl；查看帮助用 :h");
                return;
            }

            string low = target.Trim().ToLowerInvariant();
            if (low == "rl" || low == ":rl")
            {
                Console.WriteLine("  上一条就是 rl，没有更早的操作可重试");
                return;
            }

            if (wasFail) Console.WriteLine("  [重试] 重跑上次失败的命令：" + target);
            else Console.WriteLine("  [重试] 上一条没有失败，重跑：" + target);

            Dispatch(target);
        }

        private static void DoRewidth()
        {
            LSW = 0;
            EnsureWidth();
            Info("窗口宽度已重取：" + LSW + " 列");
        }

        private static void DoInit()
        {
            Console.WriteLine("  [初始化] 重新检测环境 ...");
            if (InitEnv())
                Ok("已初始化，当前目录 " + CUR);
            else
                Console.WriteLine("  初始化未完成，设备不在线，可稍后输入 ri 重试");
        }

        private static void WatchDev()
        {
            string o = "";
            string e = "";
            // 只做"还在不在"的判断，用短超时探活；真卡住也不该拖着界面
            int rc = AdbProbe(out o, out e);
            if (rc != 0) { CMD_OK = false; return; }

            // 先记旧值，再重新解析（ParseDevices 会重置并重算 DEVN/DEVID）
            string oldid = DEVID;
            int oldn = DEVN;

            ParseDevices(MergeStream(o, e));
            ReportDevNotes();

            if (DEVN == 0) { CMD_OK = false; return; }
            if (DEVID == oldid && DEVN == oldn) { CMD_OK = true; return; }

            Console.WriteLine();
            if (!string.IsNullOrEmpty(oldid) && oldid != DEVID) Warn("设备已切换：" + oldid + " -> " + DEVID);
            else Ok("设备重新上线：" + DEVID);

            AutoRoot();
            string o2 = "";
            string e2 = "";
            ShellCall(CUR, "ls -d '" + CUR + "' 2>&1", out o2, out e2);
            string low = o2.ToLowerInvariant();
            if (low.Contains("no such file") || low.Contains("permission denied"))
            {
                CUR = ROOT;
                Warn("新设备上没有原路径，已回到 " + CUR);
            }
            Probe();
            LoadDeviceInfo();
            RenderDeviceInfo();
            Ok("已自动刷新，当前目录 " + CUR);
            LsAfterCd();
        }

        // ==================== 十一、初始化 ====================
        // v8.0：改 internal 供 GUI 入口复用（保持行为不变）
        internal static bool InitEnv()
        {
            PEND_K = ""; PEND_R = ""; PEND_N = ""; PEND_A = "";
            PERMOK = true;
            OLDPWD = "";
            CUR = ROOT;
            LSW = 0;

            EnsureWidth();

            string vso = "";
            string vse = "";
            int vrc = AdbCall(new List<string> { "version" }, out vso, out vse);
            if (vrc != 0)
            {
                Console.WriteLine();
                Console.WriteLine("[错误] 无法执行 adb：" + ADB);
                Console.WriteLine("       请安装 Android platform-tools 并加入 PATH；");
                Console.WriteLine("       或在 ini 里把 adb 设为 adb.exe 的完整路径");
                return false;
            }

            ScanDev();
            ReportDevNotes();

            if (DEVN == 0)
            {
                Console.WriteLine();
                Console.WriteLine("[错误] 没有检测到在线的设备");
                if (DEVOTHER > 0)
                {
                    // 有记录但状态不对：最常见的两种是拔线残留(offline) 和没点授权(unauthorized)
                    Console.WriteLine("       列表里有 " + DEVOTHER + " 条记录但不可用：");
                    Console.WriteLine("         offline       -> 设备已断开，或 adb 服务还没回收旧连接");
                    Console.WriteLine("         unauthorized  -> 设备上还没点\"允许调试\"");
                    Console.WriteLine("       先输入 devices 看原始状态；残留条目可用 rr 重启 adb 服务清掉");
                }
                else
                {
                    Console.WriteLine("       1. 用数据线连接设备，确认已打开 USB 调试");
                    Console.WriteLine("       2. 在手机上的\"允许调试\"弹窗选始终允许");
                    Console.WriteLine("       3. 可在命令行执行 adb devices 确认状态为 device");
                }
                return false;
            }
            if (DEVN > 1 && string.IsNullOrEmpty(SERIAL))
            {
                Console.WriteLine();
                Console.WriteLine("[错误] 检测到 " + DEVN + " 台设备，无法确定使用哪一台");
                StringBuilder dl = new StringBuilder();
                for (int i = 0; i < DEV_LIST.Count; i++)
                {
                    if (i > 0) dl.Append("  ");
                    dl.Append(DEV_LIST[i]);
                }
                if (dl.Length > 0) Console.WriteLine("       在线序列号：" + dl.ToString());
                Console.WriteLine("       在 ini 里填 serial=<序列号> 指定一台；或只保留一台设备");
                return false;
            }

            AutoRoot();
            CUR = ROOT;
            Probe();
            LoadDeviceInfo();
            CMD_OK = true;
            OFFLINE = false;

            // 需求4：打开工具就把九项车机信息查出来输出。
            // 只在**首次连上**时打印一次（_carPrinted），否则 r/reconnect 内部的
            // InitEnv 也会走到这里，和 RenderCarInfoOnRefresh 打成两份重复输出。
            // 刷新路径的输出由 RenderCarInfoOnRefresh 负责（它还会带上"正在查什么"）。
            if (!_carPrinted && CAR_HAS_DATA())
            {
                Console.WriteLine();
                RenderCarInfo(false, false);
                _carPrinted = true;
            }

            StatusBar();
            return true;
        }

        // 车机信息是否取到了任意一项（全空说明设备没就绪，打印也没意义）
        private static bool CAR_HAS_DATA()
        {
            for (int i = 0; i < CAR_VALS.Length; i++)
                if (!string.IsNullOrEmpty(CAR_VALS[i])) return true;
            return !string.IsNullOrEmpty(CAR_RES);
        }

        // 启动块是否已经打印过车机信息（防止 r 刷新时重复打印）
        private static bool _carPrinted = false;

        private static void ScanDev()
        {
            // v7.13：这里原来用 AdbCall（超时 30 秒）。断线时 adb 卡在 USB 传输层
            // 是常态，一次探测就吃掉 30 秒；而调用方（Dispatch 的离线闸门、
            // 首启 InitEnv）后面紧跟的是 "DEVN == 0 ?" 判断 —— 卡完还拿旧值。
            // 现在用 4 秒上限，并且**探测失败就明确把状态清成"无设备"**，
            // 宁可让用户重新点一次，也不要拿着陈旧状态去做决定。
            string o = "";
            string e = "";
            bool to = false;
            // 2.5 秒：正常的 devices 300ms 内就回来了，等更久只说明确实卡住。
            // 启动时这一段是同步的，等满 4 秒会让"双击 exe → 看到界面"明显变慢。
            int ms = Bg.PROBE_TIMEOUT_MS > 2500 ? 2500 : Bg.PROBE_TIMEOUT_MS;
            int rc = RunRaw(new List<string> { "devices" }, ms,
                out o, out e, out to, true);

            // 【v7.15 修复 BUG-07】启动竞态：adb server 正在重建时会误判"无设备"。
            //
            // 复现场景：刚执行过 `adb kill-server`（或 adb 服务被别的软件杀掉）后
            // 立刻启动本工具。此时 adb 客户端会自己把 server 拉起来，但 USB 重新
            // 枚举 + adbd 握手要好几秒，第一次 `devices` 很可能直接超时。
            // 旧版一次超时就清零 DEVN，于是界面报"没有检测到在线的设备"、
            // 进入离线模式 —— 明明线插着，用户看到的就是"搜不到设备"。
            // 实测 10 次冷启动里有 1 次命中（约 10%）。
            //
            // 只对"超时"重试一次（rc != 0 这种 adb 缺失/参数错误重试也没用），
            // 且第二次给更长的时间 —— 第一次超时往往正处在 server 启动窗口里。
            if (to)
            {
                RunRaw(new List<string> { "start-server" }, 8000,
                    out o, out e, out to, true);

                o = "";
                e = "";
                to = false;
                rc = RunRaw(new List<string> { "devices" }, ms * 2,
                    out o, out e, out to, true);
            }

            if (to || rc != 0)
            {
                // adb 不可用：清空在线状态，避免上层误以为设备还在
                DEVN = 0;
                DEVID = "";
                DEVOTHER = 0;
                DEV_LIST.Clear();
                SERIAL_OK = false;
                return;
            }

            ParseDevices(MergeStream(o, e));
            ReportDevNotes();
        }

        // ==================== 设备解析与"到底用哪一台" ====================
        // 这里有三个坑，任何一个没堵住都会在"换设备"时误报多台：
        //   1) 同一序列号出现两行（adb root 重启 adbd 的瞬间、USB 与 tcp 并存）
        //      —— 按序列号去重即可；
        //   2) 上一台设备的条目还挂在列表里（A 拔掉立刻插 B，adb 尚未回收该传输）
        //      —— 序列号不同，去重救不了，必须**逐个探活**才能剔除；
        //   3) 同一台设备同时有 USB 和 tcp 两条传输（192.168.x.x:5555）
        //      —— 序列号也不同，按"USB 优先"折叠成一台。
        // 另外 ini 的 serial 可能与当前设备不符（换了机器但配置没改），
        // 这时不能死用它，否则每条命令都 device not found —— 见 SERIAL_OK。
        internal static bool SERIAL_OK = false;              // ini 的 serial 当前是否在线
        internal static List<string> STALE_DEVS = new List<string>();  // 探活失败的陈旧条目
        internal static int DEV_TCP_IGNORED = 0;             // 被折叠掉的同机 tcp 传输数
        internal static List<string> DEV_LIST = new List<string>();    // 当前确认在线的序列号
        internal static int DEV_OFFLINE_TCP = 0;             // 列表里残留的 tcp 条目（之前 adb connect 留下的）
        internal static int DEV_UNAUTH = 0;                  // 未授权条目数（需要人去点"允许"）
        private static bool SERIAL_WARNED = false;
        private static bool STALE_REPORTED = false;
        private static bool TCP_HINT_SHOWN = false;

        // tcp 传输的序列号形如 192.168.1.7:5555；USB 序列号没有冒号
        private static bool IsTcpSerial(string serial)
        {
            return serial.IndexOf(':') >= 0;
        }

        // 探活：真的问一句"你现在是什么状态"。带超时，拔掉的条目不会把界面卡住。
        private static bool DeviceAlive(string serial)
        {
            List<string> a = new List<string>();
            a.Add("-s");
            a.Add(serial);
            a.Add("get-state");

            string o = "";
            string e = "";
            int rc = AdbCallTimeout(a, 1500, out o, out e);
            if (rc != 0) return false;

            string t = (o + " " + e).Trim().ToLowerInvariant();
            return t.StartsWith("device");
        }

        private static void ParseDevices(string text)
        {
            DEVN = 0; DEVID = ""; DEVOTHER = 0; DEV_UNAUTH = 0;
            DEV_TCP_IGNORED = 0;
            DEV_OFFLINE_TCP = 0;
            STALE_DEVS.Clear();
            DEV_LIST.Clear();

            Dictionary<string, string> map = new Dictionary<string, string>(StringComparer.Ordinal);
            List<string> order = new List<string>();
            List<string> cand = new List<string>();     // device 态候选
            List<string> other = new List<string>();    // offline / unauthorized

            string[] lines = text.Split('\n');
            for (int i = 0; i < lines.Length; i++)
            {
                string t = lines[i].TrimEnd('\r').Trim();
                if (t.Length == 0) continue;
                if (t.StartsWith("List of devices")) continue;
                if (t.StartsWith("*")) continue;              // adb 守护进程提示行

                string[] f = t.Split(new char[] { '\t', ' ' }, StringSplitOptions.RemoveEmptyEntries);
                if (f.Length < 2) continue;

                string serial = f[0];
                string state = f[1];
                if (state != "device" && state != "offline" && state != "unauthorized") continue;

                if (map.ContainsKey(serial))
                {
                    // 同号多条：device 态优先
                    if (state == "device") map[serial] = state;
                    continue;
                }

                map[serial] = state;
                order.Add(serial);
            }

            for (int i = 0; i < order.Count; i++)
            {
                if (map[order[i]] == "device") cand.Add(order[i]);
                else other.Add(order[i]);
            }

            DEVOTHER = other.Count;

            // 未授权单独计数：它和 offline 的处理方式完全不同 ——
            // offline 能靠 reconnect 自动救回来，unauthorized 只能等人去车机上点允许。
            DEV_UNAUTH = 0;
            for (int i = 0; i < other.Count; i++)
            {
                if (map[other[i]] == "unauthorized") DEV_UNAUTH++;
            }

            for (int i = 0; i < other.Count; i++)
            {
                if (IsTcpSerial(other[i])) DEV_OFFLINE_TCP++;
            }

            // ini 填的 serial 是否仍然在线（决定 BuildPsi 用不用它）
            SERIAL_OK = (!string.IsNullOrEmpty(SERIAL) && map.ContainsKey(SERIAL) && map[SERIAL] == "device");

            if (cand.Count == 0) return;

            if (cand.Count == 1)
            {
                DEVID = cand[0];
                DEVN = 1;
                DEV_LIST.Add(cand[0]);
                return;
            }

            // ---- 多于一个：先剔除"列表里还在、实际已拔掉"的陈旧条目 ----
            List<string> alive = new List<string>();
            for (int i = 0; i < cand.Count; i++)
            {
                if (DeviceAlive(cand[i])) alive.Add(cand[i]);
                else STALE_DEVS.Add(cand[i]);
            }

            if (alive.Count == 1)
            {
                DEVID = alive[0];
                DEVN = 1;
                DEV_LIST.Add(alive[0]);
                return;
            }

            // ---- 同一台设备的 USB + tcp 两条传输：USB 优先，折叠成一台 ----
            List<string> usb = new List<string>();
            for (int i = 0; i < alive.Count; i++)
            {
                if (!IsTcpSerial(alive[i])) usb.Add(alive[i]);
            }

            if (usb.Count == 1)
            {
                DEVID = usb[0];
                DEVN = 1;
                DEV_TCP_IGNORED = alive.Count - 1;
                DEV_LIST.Add(usb[0]);
                return;
            }

            // ---- 确实是多台不同设备 ----
            DEVID = (usb.Count > 0) ? usb[0] : alive[0];
            DEVN = alive.Count;
            for (int i = 0; i < alive.Count; i++) DEV_LIST.Add(alive[i]);
        }

        // 只提示一次：陈旧条目、ini serial 失效
        internal static void ReportDevNotes()
        {
            if (!STALE_REPORTED && STALE_DEVS.Count > 0)
            {
                STALE_REPORTED = true;
                StringBuilder sb = new StringBuilder();
                for (int i = 0; i < STALE_DEVS.Count && i < 3; i++)
                {
                    if (i > 0) sb.Append(", ");
                    sb.Append(STALE_DEVS[i]);
                }
                Hint("已忽略 " + STALE_DEVS.Count + " 条失效的设备记录（" + sb.ToString()
                    + "）：列表里还在，实际已断开");
            }

            if (DEV_OFFLINE_TCP > 0 && !TCP_HINT_SHOWN)
            {
                TCP_HINT_SHOWN = true;
                Hint("列表里有 " + DEV_OFFLINE_TCP + " 条无线调试残留条目（形如 192.168.x.x:5555），"
                    + "输入 adb disconnect 或 :rr 可清掉");
            }

            if (!string.IsNullOrEmpty(SERIAL) && !SERIAL_OK && DEVID.Length > 0)
            {
                if (!SERIAL_WARNED)
                {
                    SERIAL_WARNED = true;
                    Warn("ini 的 serial=" + SERIAL + " 不在线，已临时改用 " + DEVID);
                    Hint("要固定用它就把 ini 的 serial 改成 " + DEVID + "；留空则自动跟随当前设备");
                }
            }
            else if (!string.IsNullOrEmpty(SERIAL) && SERIAL_OK)
            {
                SERIAL_WARNED = false;
            }
        }

        // ==================== 设备身份 ====================
        // 连上设备就报两个值：SOC 平台 + 车型。
        // 一次 shell 调用取三个属性（车型优先用 gacvehicleplatform，
        // 老机型没有这个键时退回 ro.oem.product.name）。
        internal static string DEV_SOC = "";
        internal static string DEV_PLAT = "";

        // 屏幕分辨率（问题7：连上设备后要在指令输入页显示）。
        // 形如 "1080x1920"，取 wm size 的 Physical/Override 一行。
        // 取不到就留空，界面不显示 —— 不显示总比显示 "-" 好。
        internal static string DEV_RES = "";

        // 设备日志等级（需求7：顶部状态栏显示在 ROOT 后面）。
        // 取 persist.log.tag，值 V/D/I/W/E（对应 logcat Verbose/Debug/Info/Warning/Error）。
        // 取不到留空，界面不显示。
        internal static string DEV_LOGLEVEL = "";

        // 车型 / SOC / 分辨率现在统一走 CarInfo.LoadCarInfo（9 项一次取回），
        // 这里只做"把结果映射到旧的三个字段"的桥接，避免改动所有既有引用。
        private static void LoadDeviceInfo()
        {
            DEV_SOC = "";
            DEV_PLAT = "";
            DEV_RES = "";
            DEV_LOGLEVEL = "";

            // ---- A13 修复：日志等级必须独立读取，不能挂在 LoadCarInfo 之后 ----
            // 原实现是 `if (!LoadCarInfo()) return;` 再读 persist.log.tag。但车机
            // 属性全空的设备（手机、或属性未配）会让 LoadCarInfo() 返回 false 直接
            // 早退，下面那次 getprop 永远执行不到 —— 表现就是界面恒显示「日志 未设置」。
            // 日志等级和车机信息没有任何依赖关系，不该被它连坐。
            {
                string lo = "";
                string le = "";
                try { ShellCall(CUR, "getprop persist.log.tag", out lo, out le); }
                catch { }
                string lv = FirstLine((lo + le).Trim());
                if (lv.Length > 0) DEV_LOGLEVEL = lv;
            }

            if (!LoadCarInfo()) return;

            // 车型：优先 sys.product.gacvehicleplatform（新车型都有），
            // 老机型没这个键时退回 ro.oem.product.name。
            DEV_PLAT = CAR_VALS[0];
            if (DEV_PLAT.Length == 0)
            {
                string o = "";
                string e = "";
                ShellCall(CUR, "getprop ro.oem.product.name", out o, out e);
                DEV_PLAT = (o + e).Trim();
            }
            DEV_SOC = CAR_VALS[1];
            DEV_RES = CAR_RES;

            // 日志等级已在方法开头独立读过（见 A13 修复），这里不再重复执行 adb。
        }

        // 从 `wm size` 的输出里抽出 "1080x1920"。
        // 输出可能是（多行，已用 tr 压成以 ';' 分隔）：
        //   Physical size: 1080x1920
        //   Override size: 720x1280        <- 有覆盖时以 Override 为准（实际生效值）
        // 也可能整段是 "not found" / 空 —— 一律返回 ""。
        internal static string ParseWmSize(string raw)
        {
            if (string.IsNullOrEmpty(raw)) return "";

            string phys = "";
            string over = "";

            // 兼容两种分隔：换行（tr 不可用）和 ';'（压平后）
            string[] lines = raw.Replace(';', '\n').Split('\n');
            for (int i = 0; i < lines.Length; i++)
            {
                string t = lines[i].Trim();
                if (t.Length == 0) continue;

                if (t.StartsWith("Physical size:", StringComparison.Ordinal))
                {
                    if (phys.Length == 0) phys = t.Substring("Physical size:".Length).Trim();
                }
                else if (t.StartsWith("Override size:", StringComparison.Ordinal))
                {
                    if (over.Length == 0) over = t.Substring("Override size:".Length).Trim();
                }
            }

            string pick = over.Length > 0 ? over : phys;
            if (pick.Length == 0) return "";
            // 只接受 "数字x数字"，其它形态（not found、权限报错）一律当没有
            int x = pick.IndexOf('x');
            if (x <= 0 || x >= pick.Length - 1) return "";
            for (int i = 0; i < pick.Length; i++)
            {
                if (i == x) continue;
                if (pick[i] < '0' || pick[i] > '9') return "";
            }
            return pick;
        }

        // 按 ##0 ##1 ##2 ... 分段，每段取第一条非空内容。
        // n = 期望的段数。段数不够时尾部补 ""（不断链、不抛异常）。
        //
        // 与旧 ParseMarkedText 的区别：这里按"标记出现顺序"计数，
        // 不关心标记后面跟的数字是多少 —— 因为 shell 里的 echo '##3'
        // 可能被设备侧 sh 回显、也可能部分标记丢失，按顺序切更稳。
        internal static string[] ParseMarkedTextN(string text, int n)
        {
            string[] r = new string[n];
            for (int i = 0; i < n; i++) r[i] = "";
            if (string.IsNullOrEmpty(text)) return r;

            string[] lines = text.Split('\n');
            int cur = -1, seen = 0;

            for (int i = 0; i < lines.Length; i++)
            {
                string t = lines[i].TrimEnd('\r').Trim();
                if (t.Length == 0) continue;

                if (t.StartsWith("##", StringComparison.Ordinal))
                {
                    cur = seen;
                    seen++;
                    continue;
                }

                if (cur >= 0 && cur < n && r[cur].Length == 0) r[cur] = t;
            }
            return r;
        }

        // 按 ##1 ##2 ##3 分段取第一条非空内容
        private static string[] ParseMarkedText(string text, int n)
        {
            return ParseMarkedTextN(text, n);
        }

        private static void RenderDeviceInfo()
        {
            if (DEV_SOC.Length == 0 && DEV_PLAT.Length == 0) return;

            // 需求4：九项车机信息已经完整打印过时，这里不再重复打车型/SOC/分辨率。
            // 这三项本来就是九项的子集，连着两处一起显示会让人以为"刷新了两次"
            // 或者"数据不一致"。_carPrinted 为 false（离线、或九项全空）时才用这行兜底。
            if (_carPrinted) return;

            UseDim();
            Console.Write("  车型  ");
            UseDefault();
            Console.Write(DEV_PLAT.Length > 0 ? DEV_PLAT : "-");

            UseDim();
            Console.Write("        SOC  ");
            UseDefault();
            Console.Write(DEV_SOC.Length > 0 ? DEV_SOC : "-");

            // 问题7：分辨率也打一行，用户开日志就能核对推上去的值对不对。
            // 取不到时不打，避免出现 "分辨率 -" 这种没信息量的噪音。
            if (DEV_RES.Length > 0)
            {
                UseDim();
                Console.Write("        分辨率  ");
                UseDefault();
                Console.Write(DEV_RES);
            }
            Console.WriteLine();
        }

        private static void AutoRoot()
        {
            // 【需求5】原来这里 `if (!AUTO_ROOT) return;` 一走了之，完全不回写 ROOTED。
            //
            // 后果：r 刷新时其实已经 adb root 成功了，但界面 root 徽标读的是
            // App.ROOTED（只有 RootProbe/RootElevate 会写），所以徽标一直是红的，
            // 用户必须手动点一下 root 按钮才变绿 —— 就是"这样很傻"的现场。
            //
            // 现在两条路都走通：
            //   AUTO_ROOT 关掉 -> 至少探一次真实状态（不改设备，只读 id -u）
            //   AUTO_ROOT 打开 -> 先 adb root，再探一次，把结果写进 ROOTED
            if (!AUTO_ROOT)
            {
                // 没开自动提权也要把状态探准，否则徽标永远是上次的旧值
                try { RootProbe(); }
                catch { }
                return;
            }
            string o = "";
            string e = "";
            AdbCall(new List<string> { "root" }, out o, out e);
            if (o.ToLowerInvariant().Contains("restarting adbd as root"))
                System.Threading.Thread.Sleep(1000);

            int t;
            for (t = 0; t < RECONN_TRY; t++)
            {
                string st = "";
                string se = "";
                AdbCall(new List<string> { "get-state" }, out st, out se);
                if (st.Trim().ToLowerInvariant() == "device") break;
                if (t < RECONN_TRY - 1) System.Threading.Thread.Sleep(800);
            }

            string low = o.ToLowerInvariant();
            if (low.Contains("cannot run as root"))
            {
                Warn("adb root 失败：adbd cannot run as root in production builds");
                Hint("普通 shell 权限可能读不到部分日志目录，需要换 userdebug/eng 版本");
            }
            else if (low.Contains("more than one device"))
            {
                Warn("adb root 失败：连接了多台设备，无法确定使用哪一台");
                Hint("在 ini 里填写 serial（用 adb devices 查看序列号），然后输入 ri");
            }
            else if (low.Contains("error:"))
            {
                Warn("adb root 未成功：设备返回了错误");
                Hint("可能仍可用普通权限读取部分目录，请以实际操作结果为准");
            }

            // 【需求5】最后一步：以设备实际回话为准，把状态写进 ROOTED。
            //
            // 不看 adb 的口头回执，只认 `id -u` 是不是 0 —— adb root 可能回
            // "adbd is already running as root"（本来就是 root），也可能回
            // "restarting adbd as root"（刚重启），两种都算成功，
            // 而 "cannot run as root" 算失败。统一靠 RootProbe 判定最稳。
            try { RootProbe(); }
            catch { }
        }

        private static void Probe()
        {
            string o = "";
            string e = "";
            ShellCall(CUR, "ls -d '" + CUR + "' 2>&1", out o, out e);
            string low = o.ToLowerInvariant();
            PERMOK = !(low.Contains("permission denied") || low.Contains("no such file"));
        }

        // ==================== 十二、窗口宽度 ====================
        private static void EnsureWidth()
        {
            if (LSW > 0) return;
            int w = Util.ConsoleWidth(0);
            if (w >= 40) { LSW = w; return; }
            LSW = LS_WIDTH;
        }

        /* 2026-11-25（需求）：一键截图并立即打开。
           跟现有截图同一目录（桌面\logcat\<日期>\screencap），用 exec-out 保证 PNG 字节
           不被 shell 的换行转换破坏；写盘后等文件够大再打开，避免打开半张图。 */
                internal static void DoShotOpen()
        {
            if (!RequireDevice("")) return;

            /* 2026-11-26（R1 复用优先）：不再自己拼命令行。
               旧实现走"先把 PNG 当文本读一遍 + 再 cmd 重定向"，两头都不对：
               PNG 是二进制，文本通道会损坏；第二次重定向的引号又把路径切错。
               现在直接复用已验证可用的 DoShotSilent()，再取新增的那张图打开。 */
            string dir = OutDir("shot");
            DateTime t0 = DateTime.Now.AddSeconds(-2);
            var before = new System.Collections.Generic.HashSet<string>();
            try
            {
                foreach (string f0 in System.IO.Directory.GetFiles(dir, "*.png"))
                    before.Add(f0);
            }
            catch { }

            DoShotSilent();

            string newest = null;
            DateTime newestT = DateTime.MinValue;
            try
            {
                foreach (string f1 in System.IO.Directory.GetFiles(dir, "*.png"))
                {
                    if (before.Contains(f1)) continue;
                    var fi = new System.IO.FileInfo(f1);
                    if (fi.LastWriteTime >= t0 && fi.LastWriteTime > newestT && fi.Length > 10240)
                    {
                        newest = f1; newestT = fi.LastWriteTime;
                    }
                }
            }
            catch { }

            if (newest == null) { Warn("截图已执行，但没找到新生成的文件（可看输出栏）"); return; }

            try
            {
                System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
                {
                    FileName = newest,
                    UseShellExecute = true          // 系统默认看图程序
                });
                Ok("已打开：" + System.IO.Path.GetFileName(newest));
            }
            catch (Exception ex)
            {
                Warn("文件已保存，但打开失败：" + ex.Message);
            }
        }
    }
}
