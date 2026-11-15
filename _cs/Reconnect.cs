// ============================================================================
//  Reconnect.cs — 断线重连的稳定性层（v7.13）
//
//  现场问题：拔线/息屏后再插上，工具经常"搜不到设备"，只能重开 exe 才好。
//
//  这不是单一 bug，而是四个独立原因叠在一起。v7.11/v7.12 只处理了"卡死"，
//  没处理"搜不到"，所以这次单独做一层：
//
//  原因 1：把单次 `adb devices` 的结果当成最终结论
//      USB 重新枚举需要时间（驱动重载 + adbd 重启 + adb server 轮询端口事件），
//      实测插上线到列表出现通常 1.5~6 秒，遇到车机 adbd 慢启动会更久。
//      旧代码 RetrySoft 是 800ms × 5 = 4 秒窗口，而且每次探测走的是
//      AdbCall（30 秒超时）—— 一旦 adb 卡住，一次就吃掉 30 秒，
//      用户看到的是"点了重连，卡了半天，然后说搜不到设备"。
//      → 本文件：渐进退避（250→1800ms）+ 单次探测有独立短上限。
//
//  原因 2：拔插后 adb 自己的传输层还挂着旧连接（offline / stale transport）
//      `adb devices` 会如实列出 offline，但工具没做任何处理，只是判定"没设备"。
//      adb 官方给了专用命令 `adb reconnect offline`，正是为这个场景设计的。
//      → 本文件：见到 offline 先 reconnect offline，而不是直接 kill-server。
//
//  原因 3：adb server 僵死时，"空列表"和"没插设备"长得一模一样
//      server 若握着失效句柄，`adb devices` 有的会挂住（超时），
//      有的会立刻回一个只有表头的空列表。后者最坑：工具认为"你没插设备"，
//      实际是 server 坏了。只有重启 server 才能让它重新枚举 USB。
//      → 本文件：空列表 + 已等待 >5 秒 + 用户主动重连时才重启 server；
//        连续两次探测超时则无条件重启（这是真的僵死）。
//
//  原因 4：kill-server / start-server 之间没有等待，也没有校验
//      Windows 上 5037 端口释放有延迟，进程退出也有延迟。旧代码
//      taskkill 之后固定 Sleep(400) 就 start-server，很容易撞上"端口占用"
//      起不来，或者起了一个坏 server，然后再也搜不到设备。
//      → 本文件：等端口真正释放 → 等 adb.exe 真正消失 → 起服务 →
//        校验 server 真活着（adb version 能回话）→ 才开始等设备。
//
//  另外补一条现场诊断：多个 adb 版本共存。
//      Windows 的 adb server 是全局共享的，第一个客户端启动它。
//      如果本机同时有 platform-tools 34 和某工具自带的 31，两边会互相
//      "server doesn't match this client; killing..."，表现就是随机断线、
//      隔一会儿搜不到设备。Diagnose() 专门把这件事摊开给用户看。
// ============================================================================
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net.Sockets;
using System.Text;
using System.Threading;

namespace AdbLogExport
{
    internal static partial class App
    {
        internal static class Rec
        {
            // ---- 探测结果分类 ----
            internal const int ST_OK = 0;         // 至少一台 device 态
            internal const int ST_NONE = 1;       // 列表里一条可用条目都没有
            internal const int ST_OFFLINE = 2;    // 只有 offline
            internal const int ST_UNAUTH = 3;     // 只有 unauthorized
            internal const int ST_NOADB = 4;      // adb 根本执行不起来
            internal const int ST_HANG = 5;       // devices 超时：server 僵死
            internal const int ST_VERSION = 6;    // client/server 版本冲突

            internal const int ADB_PORT = 5037;

            // 上一次 ResetServer 是否撞上"不可恢复"的情况（端口被非 adb 进程占着）。
            // 这种时候再等下去毫无意义，唯一出路是用户去关那个进程。
            internal static bool LAST_RESET_FATAL = false;

            // 单次探测快照。不写任何全局状态，避免后台线程和主线程抢 DEVN/DEVID。
            internal sealed class Snap
            {
                internal int state = ST_NONE;
                internal int rc;
                internal bool timedOut;
                internal string raw = "";
                internal int online;
                internal int offline;
                internal int unauth;
                internal string firstOnline = "";
                internal string firstBad = "";

                internal string StateName()
                {
                    if (state == ST_OK) return "在线";
                    if (state == ST_NONE) return "无设备";
                    if (state == ST_OFFLINE) return "offline";
                    if (state == ST_UNAUTH) return "未授权";
                    if (state == ST_NOADB) return "adb 不可用";
                    if (state == ST_HANG) return "adb 无响应";
                    if (state == ST_VERSION) return "adb 版本冲突";
                    return "未知";
                }
            }

            // ================================================================
            //  一、单次探测（绝不改全局状态）
            // ================================================================
            internal static Snap ScanOnce(int timeoutMs)
            {
                string o = "";
                string e = "";
                bool to = false;
                int rc = RunRaw(new List<string> { "devices" }, timeoutMs, out o, out e, out to, true);
                return Classify(MergeStream(o, e), rc, to);
            }

            // 纯函数：只根据"输出 + 退出码 + 是否超时"判定状态。
            // 抽出来是为了能脱离真机做自检（自检里直接喂文本）。
            internal static Snap Classify(string raw, int rc, bool timedOut)
            {
                Snap s = new Snap();
                s.rc = rc;
                s.timedOut = timedOut;
                s.raw = (raw == null) ? "" : raw;

                if (timedOut)
                {
                    s.state = ST_HANG;
                    return s;
                }

                // adb 不存在 / 启动失败
                if (rc == 9009
                    || (rc < 0 && s.raw.Trim().Length == 0)
                    || (rc < 0 && s.raw.IndexOf("adb 启动或读取失败") >= 0))
                {
                    s.state = ST_NOADB;
                    return s;
                }

                // 两台不同版本的 adb 抢 server 时的原话：
                //   adb server version (41) doesn't match this client (39); killing...
                if (s.raw.IndexOf("doesn't match this client") >= 0
                    || s.raw.IndexOf("does not match this client") >= 0)
                {
                    s.state = ST_VERSION;
                    return s;
                }

                ParseSnap(s);
                return s;
            }

            private static void ParseSnap(Snap s)
            {
                string[] lines = s.raw.Split('\n');
                for (int i = 0; i < lines.Length; i++)
                {
                    string t = lines[i].TrimEnd('\r').Trim();
                    if (t.Length == 0) continue;
                    if (t.StartsWith("List of devices")) continue;
                    if (t.StartsWith("*")) continue;              // daemon 提示行
                    if (t.StartsWith("adb server")) continue;

                    string[] f = t.Split(new char[] { '\t', ' ' }, StringSplitOptions.RemoveEmptyEntries);
                    if (f.Length < 2) continue;

                    string state = f[1];
                    if (state == "device")
                    {
                        s.online++;
                        if (s.firstOnline.Length == 0) s.firstOnline = f[0];
                    }
                    else if (state == "offline")
                    {
                        s.offline++;
                        if (s.firstBad.Length == 0) s.firstBad = f[0] + "=offline";
                    }
                    else if (state == "unauthorized")
                    {
                        s.unauth++;
                        if (s.firstBad.Length == 0) s.firstBad = f[0] + "=unauthorized";
                    }
                }

                if (s.online > 0) s.state = ST_OK;
                else if (s.unauth > 0) s.state = ST_UNAUTH;   // 未授权优先报：需要人去点允许
                else if (s.offline > 0) s.state = ST_OFFLINE;
                else s.state = ST_NONE;
            }

            // ================================================================
            //  二、等设备上线（分级恢复）
            //
            //  budgetMs     总预算。到了就返回 false，绝不无限等。
            //  allowRecover 是否允许"重启 adb 服务"这一档。
            //               用户主动点重连 = true；后台空闲探测 = false
            //               （后台乱杀 server 会打断同一台电脑上别的 adb 使用者）。
            //  verbose      是否允许往控制台写字。**后台线程必须传 false**。
            // ================================================================
            internal static bool WaitDevice(int budgetMs, bool allowRecover, bool verbose)
            {
                long t0 = Environment.TickCount;

                bool didReconnect = false;
                bool didRecover = false;
                bool justRecovered = false;   // 上一轮刚重启过服务：下一轮要给它足够时间
                int hangStreak = 0;
                int step = 0;
                string lastNote = "";

                // 渐进退避：前几轮密一点（刚插上线最常见），后面放宽，别空转刷进程
                int[] gaps = new int[] { 250, 350, 500, 700, 900, 1100, 1400, 1800 };

                while (true)
                {
                    long spent = Environment.TickCount - t0;

                    // 首次探测给长一点：server 没起来时 adb 会自己拉起来，要几秒。
                    // 刚重启过服务的那一轮更长 —— 此时 server 正在枚举 USB，
                    // devices 会阻塞好几秒，等短了就会误判成"无响应"。
                    int perTry;
                    if (justRecovered) { perTry = 10000; justRecovered = false; }
                    else if (step == 0) { perTry = 3500; }
                    else { perTry = 2200; }
                    Snap s = ScanOnce(perTry);
                    step++;

                    if (s.state == ST_OK)
                    {
                        ParseDevices(s.raw);
                        ReportDevNotes();
                        return DEVN > 0;
                    }

                    if (s.state == ST_NOADB) return false;      // adb 都没有，重试无意义

                    lastNote = Note(lastNote, NoteOf(s, verbose));

                    // --- 版本冲突：adb 自己会杀掉旧 server 重启，给它一次机会 ---
                    if (s.state == ST_VERSION)
                    {
                        if (!didRecover)
                        {
                            didRecover = true;
                            if (verbose) Hint("检测到 adb 客户端与 server 版本不一致（多半是两套 adb 共存），正在重建服务 ...");
                            Thread.Sleep(700);                  // 让 adb 自己的 kill 生效
                            continue;
                        }
                        return false;
                    }

                    // --- 超时：连续两次才算僵死，单次可能只是 server 正在启动 ---
                    if (s.state == ST_HANG)
                    {
                        hangStreak++;
                        // 留 6 秒余量：救完还得有时间重新探一次，否则救了也白救
                        if (hangStreak >= 2 && !didRecover
                            && (Environment.TickCount - t0) < budgetMs - 6000)
                        {
                            didRecover = true;
                            if (verbose) Warn("adb 连续无响应，正在重启 adb 服务 ...");
                            ResetServer(verbose);
                            if (LAST_RESET_FATAL) break;   // 端口被别人占着，等也没用
                            justRecovered = true;
                            hangStreak = 0;
                            continue;
                        }
                    }
                    else
                    {
                        hangStreak = 0;
                    }

                    // --- offline：先 reconnect，代价比重启 server 小得多 ---
                    if (s.state == ST_OFFLINE && !didReconnect)
                    {
                        didReconnect = true;
                        ReconnectOffline(verbose);
                        continue;
                    }

                    // --- 未授权：只能等人去点，重试再多次也没用 ---
                    if (s.state == ST_UNAUTH && verbose)
                    {
                        Hint("设备已识别但未授权：请在车机弹出的「允许 USB 调试」上点允许"
                             + (s.firstBad.Length > 0 ? "（" + s.firstBad + "）" : ""));
                    }

                    // --- 空列表 + 等够了 + 允许恢复：重启 server 让它重新枚举 USB ---
                    // 为什么空列表也要重启：server 握着失效句柄时，devices 会
                    // 立刻回一个空表头，和"真没插设备"完全一样，只有重启能区分。
                    if (allowRecover && !didRecover && s.state == ST_NONE && spent >= 5000
                        && spent < budgetMs - 6000)
                    {
                        didRecover = true;
                        if (verbose)
                        {
                            Warn("等了 " + (spent / 1000) + " 秒仍没有设备，重启 adb 服务重新枚举 USB ...");
                        }
                        ResetServer(verbose);
                        if (LAST_RESET_FATAL) break;
                        justRecovered = true;
                        continue;
                    }

                    long left = budgetMs - (Environment.TickCount - t0);
                    if (left <= 0) break;

                    int g = gaps[step - 1 < gaps.Length ? step - 1 : gaps.Length - 1];
                    if (g > left) g = (int)left;
                    Thread.Sleep(g);
                }

                // 超预算了：把最后一次看到的真实状态落到全局，避免上层用陈旧值
                Snap last = ScanOnce(2000);
                if (last.state == ST_OK) { ParseDevices(last.raw); return DEVN > 0; }
                if (last.state != ST_HANG) ParseDevices(last.raw);
                return false;
            }

            // 只在状态变化时返回新提示，避免每轮刷同一句话
            private static string NoteOf(Snap s, bool verbose)
            {
                if (!verbose) return "";
                if (s.state == ST_NONE) return "仍在等待设备上线 ...";
                if (s.state == ST_OFFLINE) return "设备处于 offline（拔插残留），正在重新建立连接 ...";
                if (s.state == ST_UNAUTH) return "";
                if (s.state == ST_HANG) return "adb 无响应，正在尝试恢复 ...";
                return "";
            }

            private static string Note(string last, string now)
            {
                if (now == null || now.Length == 0) return last;
                if (now == last) return last;
                Hint(now);
                return now;
            }

            // ================================================================
            //  三、单项恢复动作
            // ================================================================

            // adb reconnect offline —— 官方用来清 stale transport 的命令。
            // 比 kill-server 温和：不打断别的 adb 客户端，也不用重等 USB 枚举。
            internal static bool ReconnectOffline(bool verbose)
            {
                string o = "";
                string e = "";
                bool to = false;
                int rc = RunRaw(new List<string> { "reconnect", "offline" }, 3500,
                    out o, out e, out to, true);

                bool ok = (!to && rc == 0);
                if (verbose)
                {
                    if (ok) Hint("已对 offline 设备发起重连（adb reconnect offline）");
                    else if (to) Hint("重连请求超时，继续等设备 ...");
                }
                return ok;
            }

            // 重启 adb 服务：kill-server -> 等端口释放 -> 需要就硬杀 -> start-server -> 校验
            internal static bool ResetServer(bool verbose)
            {
                string o = "";
                string e = "";
                bool to = false;
                LAST_RESET_FATAL = false;

                // ---- 0. 先看 5037 上蹲的是不是 adb ----
                // 如果是别的程序（代理、杀软、占位脚本、其他工具的服务），
                // kill-server 和 start-server 全是白费，直接说清楚。
                int owner0 = PortOwnerPid();
                string owner0Name = ProcName(owner0);
                if (owner0 > 0 && owner0Name.Length > 0
                    && !string.Equals(owner0Name, "adb.exe", StringComparison.OrdinalIgnoreCase))
                {
                    LAST_RESET_FATAL = true;
                    if (verbose)
                    {
                        Warn("5037 端口被 " + owner0Name + "（PID " + owner0 + "）占着，不是 adb");
                        Hint("adb 服务起不来，重启也没用。关掉这个进程后按 :rr");
                    }
                    return false;
                }

                // ---- 1. 先礼 ----
                RunRaw(new List<string> { "kill-server" }, 2500, out o, out e, out to, true);

                // ---- 2. 等 5037 真正空出来 ----
                // Windows 上进程退出与端口释放不是同时完成的，立刻 start-server
                // 经常撞上"端口被占用"，起一个坏 server —— 这正是重连后搜不到设备的原因之一。
                bool freed = WaitPort(false, 2000);

                // ---- 3. 端口还在 -> 先按 adb 清一遍，再看是不是被别的程序占了 ----
                if (!freed)
                {
                    KillAdbProcs();
                    WaitNoAdbProc(1500);
                    freed = WaitPort(false, 1500);
                }

                // ---- 4. 端口仍被占：不是 adb 的问题，再起也没用，直接说清楚 ----
                //
                // 这一步是 v7.13 加的。旧版在这种情况下会老实 start-server 三次，
                // 每次都卡满超时，用户等 30 多秒只得到一句"服务重启未成功"。
                if (!freed)
                {
                    int pid = PortOwnerPid();
                    string who = ProcName(pid);
                    if (verbose)
                    {
                        if (pid > 0)
                        {
                            Warn("5037 端口被占用，占用者：" + (who.Length > 0 ? who : "未知进程")
                                 + "（PID " + pid + "）");
                            Hint("adb 服务起不来。关掉这个进程后按 :rr");
                        }
                        else
                        {
                            Warn("5037 端口一直被占用，adb 服务起不来");
                            Hint("用 netstat -ano | findstr 5037 看是谁占的，关掉后按 :rr");
                        }
                    }
                    return false;
                }

                // ---- 5. 起服务（5 秒上限；正常 <1 秒，卡住就是卡住，多等无益）----
                bool up = false;
                for (int i = 0; i < 2 && !up; i++)
                {
                    o = "";
                    e = "";
                    to = false;
                    RunRaw(new List<string> { "start-server" }, 5000, out o, out e, out to, true);
                    up = WaitPort(true, 1500);
                    if (!up) Thread.Sleep(250);
                }
                if (!up)
                {
                    if (verbose) Hint("adb 服务没能起来（start-server 失败）");
                    return false;
                }

                // ---- 6. 校验服务能不能回话 ----
                // 两个坑都在这里踩过：
                //  a) 不能用 `adb version` 校验 —— 纯本地操作，不连 server，
                //     端口上蹲着别的程序也照样成功，会得出"服务已重启"的假结论。
                //  b) 刚起来的 server 要在 Windows 上重新枚举 USB，这期间 `devices`
                //     会**阻塞**几秒（不是立刻返回空表）。给 2.5 秒就判死；
                //     上层看到"无响应"又会再杀一次服务，形成 杀→起→杀 的死循环，
                //     设备永远连不上 —— 这正是"重连后搜不到设备"最典型的形态。
                // 所以：超时只当作"还在枚举"，不算失败；只要端口在监听就算起来了。
                o = "";
                e = "";
                to = false;
                int rc = RunRaw(new List<string> { "devices" }, 8000, out o, out e, out to, true);
                bool responsive = !to && rc == 0;

                if (verbose)
                {
                    if (responsive) Hint("adb 服务已重启");
                    else Hint("adb 服务已启动，设备还在重新枚举，继续等 ...");
                }
                return true;
            }

            // 谁在监听 5037。返回 0 表示查不到。
            // 用 netstat 而不是 P/Invoke GetExtendedTcpTable：后者要手写一长串
            // 结构体布局，跨 32/64 位容易出错，而 netstat 是系统自带、输出稳定。
            internal static int PortOwnerPid()
            {
                try
                {
                    ProcessStartInfo psi = new ProcessStartInfo();
                    psi.FileName = "netstat";
                    psi.Arguments = "-ano";
                    psi.UseShellExecute = false;
                    psi.CreateNoWindow = true;
                    psi.RedirectStandardOutput = true;
                    psi.RedirectStandardError = true;

                    using (Process p = new Process())
                    {
                        p.StartInfo = psi;
                        if (!p.Start()) return 0;

                        StringBuilder sb = new StringBuilder();
                        p.OutputDataReceived += delegate(object s, DataReceivedEventArgs ev)
                        {
                            if (ev.Data == null) return;
                            string t = ev.Data;
                            if (t.IndexOf(":5037") < 0) return;
                            if (t.IndexOf("LISTENING", StringComparison.OrdinalIgnoreCase) < 0) return;
                            lock (sb) { sb.AppendLine(t); }
                        };
                        p.BeginOutputReadLine();
                        p.BeginErrorReadLine();
                        if (!p.WaitForExit(3000)) { try { p.Kill(); } catch { } return 0; }
                        try { p.WaitForExit(); } catch { }

                        string txt;
                        lock (sb) { txt = sb.ToString(); }
                        string[] lines = txt.Split('\n');
                        for (int i = 0; i < lines.Length; i++)
                        {
                            string[] f = lines[i].Trim().Split(new char[] { ' ', '\t' },
                                StringSplitOptions.RemoveEmptyEntries);
                            if (f.Length < 5) continue;
                            int pid;
                            if (int.TryParse(f[f.Length - 1], out pid) && pid > 0) return pid;
                        }
                        return 0;
                    }
                }
                catch { return 0; }
            }

            internal static string ProcName(int pid)
            {
                if (pid <= 0) return "";
                try
                {
                    Process p = Process.GetProcessById(pid);
                    return p.ProcessName + ".exe";
                }
                catch { return ""; }
            }

            // 端口探活：wantOpen=true 等它能连上，false 等它断开
            internal static bool WaitPort(bool wantOpen, int ms)
            {
                long t0 = Environment.TickCount;
                while (true)
                {
                    if (PortOpen(350) == wantOpen) return true;
                    if (Environment.TickCount - t0 >= ms) return false;
                    Thread.Sleep(120);
                }
            }

            internal static bool PortOpen(int ms)
            {
                try
                {
                    using (TcpClient c = new TcpClient())
                    {
                        IAsyncResult ar = c.BeginConnect("127.0.0.1", ADB_PORT, null, null);
                        if (!ar.AsyncWaitHandle.WaitOne(ms, false)) return false;
                        c.EndConnect(ar);
                        return true;
                    }
                }
                catch
                {
                    return false;
                }
            }

            // 有几个**活着**的 adb 进程（-1 = 查不到，权限不足或 WMI 异常）
            //
            // 为什么要过滤掉 Threads.Count == 0：
            // Windows 上 Process.Start 出来的 adb 客户端如果在 USB 里卡死被 Kill，
            // 或者创建它的进程没释放句柄，进程会变成"僵尸" —— 已经没有任何线程，
            // 但仍在进程表里。真机上见过一次攒了 50 多个的。
            // 这种僵尸不占端口也不影响 adb，但会让"adb 进程数"严重虚高，
            // 把人往"多版本冲突"的方向带偏。所以只数活的。
            internal static int AdbProcCount()
            {
                try
                {
                    Process[] ps = Process.GetProcessesByName("adb");
                    int n = 0;
                    for (int i = 0; i < ps.Length; i++)
                    {
                        try { if (ps[i].Threads.Count > 0) n++; }
                        catch { n++; }        // 读不到线程数就当作活着（宁可多算）
                    }
                    return n;
                }
                catch { return -1; }
            }

            internal static int ZombieAdbCount()
            {
                try
                {
                    Process[] ps = Process.GetProcessesByName("adb");
                    int n = 0;
                    for (int i = 0; i < ps.Length; i++)
                    {
                        try { if (ps[i].Threads.Count == 0) n++; }
                        catch { }
                    }
                    return n;
                }
                catch { return 0; }
            }

            // 硬杀。注意：这会把同一台电脑上别的 adb 工具的服务一起收掉 ——
            // 但它们本来就被同一个 server 卡着，重启对大家都是好事。
            internal static void KillAdbProcs()
            {
                try
                {
                    ProcessStartInfo t = new ProcessStartInfo();
                    t.FileName = "taskkill";
                    t.Arguments = "/F /IM adb.exe /T";
                    t.UseShellExecute = false;
                    t.CreateNoWindow = true;
                    // 不重定向输出：taskkill 输出极小，而重定向就得 ReadToEnd，
                    // 那正是 v7.11 修掉的"无超时读管道"死锁来源。让它在控制台外自己跑完即可。
                    using (Process p = Process.Start(t))
                    {
                        if (p != null)
                        {
                            try { p.WaitForExit(4000); } catch { }
                        }
                    }
                }
                catch { }
            }

            // 等 adb.exe 真的消失。等不到也无所谓，后面的端口判断才是准的。
            internal static bool WaitNoAdbProc(int ms)
            {
                long t0 = Environment.TickCount;
                while (true)
                {
                    int n = AdbProcCount();
                    if (n == 0) return true;
                    if (Environment.TickCount - t0 >= ms) return false;
                    Thread.Sleep(150);
                }
            }

            // ================================================================
            //  四、现场诊断（搜不到设备时给用户看的"体检报告"）
            // ================================================================

            // 本机发现的 adb 副本
            internal sealed class AdbCopy
            {
                internal string path = "";
                internal string ver = "";
                internal bool used;          // 是不是本工具正在用的这个
            }

            // 扫出机器上所有 adb.exe。
            //
            // 为什么要干这事：Windows 的 adb server 是全局唯一的（5037 端口），
            // 谁先连上就由谁的客户端启动。机器上要是躺着三四份 adb.exe
            // （SDK 一份、platform-tools 解压一份、用户目录一份、别的工具自带一份），
            // 各工具各用各的，就会反复出现
            //     adb server version (41) doesn't match this client (39); killing...
            // 表现为：用着好好的突然断线，再连就搜不到设备，重开工具又好了。
            // 这不是代码 bug，是环境问题 —— 但用户无从得知，所以直接列给他看。
            internal static List<AdbCopy> FindAllAdb()
            {
                List<AdbCopy> list = new List<AdbCopy>();
                List<string> dirs = new List<string>();
                List<string> seenDir = new List<string>();

                // PATH 各目录（顺序即搜索顺序，第一个命中的就是正在用的）
                string pathEnv = Environment.GetEnvironmentVariable("PATH");
                if (!string.IsNullOrEmpty(pathEnv))
                {
                    string[] parts = pathEnv.Split(';');
                    for (int i = 0; i < parts.Length; i++)
                    {
                        string d = parts[i].Trim().Trim('"');
                        if (d.Length == 0) continue;
                        string key = d.ToLowerInvariant();
                        if (seenDir.Contains(key)) continue;
                        seenDir.Add(key);
                        dirs.Add(d);
                    }
                }

                // 常见位置（不管在不在 PATH）
                string[] envs = { "ANDROID_HOME", "ANDROID_SDK_ROOT", "ANDROID_SDK_HOME" };
                for (int i = 0; i < envs.Length; i++)
                {
                    string root = Environment.GetEnvironmentVariable(envs[i]);
                    if (!string.IsNullOrEmpty(root)) dirs.Add(root.TrimEnd('\\') + "\\platform-tools");
                }
                string local = Environment.GetEnvironmentVariable("LOCALAPPDATA");
                if (!string.IsNullOrEmpty(local)) dirs.Add(local + "\\Android\\Sdk\\platform-tools");
                string user = Environment.GetEnvironmentVariable("USERPROFILE");
                if (!string.IsNullOrEmpty(user)) dirs.Add(user);
                dirs.Add("C:\\platform-tools");
                dirs.Add("D:\\platform-tools");

                List<string> seenFile = new List<string>();
                for (int i = 0; i < dirs.Count && list.Count < 6; i++)
                {
                    string cand;
                    try { cand = Path.Combine(dirs[i], "adb.exe"); }
                    catch { continue; }
                    try { if (!File.Exists(cand)) continue; }
                    catch { continue; }

                    string full;
                    try { full = Path.GetFullPath(cand); } catch { full = cand; }
                    string key = full.ToLowerInvariant();
                    if (seenFile.Contains(key)) continue;
                    seenFile.Add(key);

                    AdbCopy c = new AdbCopy();
                    c.path = full;
                    c.used = string.Equals(full, ADB, StringComparison.OrdinalIgnoreCase);
                    c.ver = ReadAdbVersion(full);
                    list.Add(c);
                }
                return list;
            }

            // 只问客户端版本，不会启动 server（adb version 是纯本地操作）
            private static string ReadAdbVersion(string exe)
            {
                if (string.IsNullOrEmpty(exe)) return "";
                try
                {
                    ProcessStartInfo psi = new ProcessStartInfo();
                    psi.FileName = exe;
                    psi.Arguments = "version";
                    psi.UseShellExecute = false;
                    psi.CreateNoWindow = true;
                    psi.RedirectStandardOutput = true;
                    psi.RedirectStandardError = true;
                    psi.StandardOutputEncoding = new UTF8Encoding(false);
                    psi.StandardErrorEncoding = new UTF8Encoding(false);

                    using (Process p = new Process())
                    {
                        p.StartInfo = psi;
                        if (!p.Start()) return "";
                        // 读流会阻塞，交给异步；这里只要几行文本，同步读也快，
                        // 但为了不重犯"无超时读管道"的老错，还是用异步 + 限时
                        StringBuilder sb = new StringBuilder();
                        p.OutputDataReceived += delegate(object s, DataReceivedEventArgs ev)
                        {
                            if (ev.Data == null) return;
                            lock (sb) { if (sb.Length < 400) sb.AppendLine(ev.Data); }
                        };
                        p.BeginOutputReadLine();
                        p.BeginErrorReadLine();
                        if (!p.WaitForExit(3000)) { try { p.Kill(); } catch { } return ""; }
                        try { p.WaitForExit(); } catch { }

                        string txt;
                        lock (sb) { txt = sb.ToString(); }
                        string[] lines = txt.Split('\n');
                        for (int i = 0; i < lines.Length; i++)
                        {
                            string t = lines[i].Trim();
                            // 第二行通常就是 "Version 37.0.0-14910828"
                            if (t.StartsWith("Version ") && t.Length > 8) return t.Substring(8).Trim();
                        }
                        if (lines.Length > 0 && lines[0].IndexOf("1.0.4") > 0) return lines[0].Trim();
                        return "";
                    }
                }
                catch { return ""; }
            }

            internal static string Diagnose()
            {
                StringBuilder sb = new StringBuilder();
                LAST_SCAN_STATE = ST_NONE;
                LAST_SCAN_ONLINE = 0;
                LAST_SCAN_OFFLINE = 0;
                LAST_SCAN_UNAUTH = 0;

                sb.AppendLine("  adb 路径   " + (string.IsNullOrEmpty(ADB) ? "(未设置)" : ADB));
                try
                {
                    if (ADB.IndexOf('\\') >= 0 || ADB.IndexOf('/') >= 0)
                        sb.AppendLine("  adb 存在   " + (System.IO.File.Exists(ADB) ? "是" : "否"));
                }
                catch { }

                // 版本（同时把 "Installed as" 抓出来，能看出 client 是哪个文件）
                string o = "";
                string e = "";
                bool to = false;
                int rc = RunRaw(new List<string> { "version" }, 4000, out o, out e, out to, true);
                if (to) sb.AppendLine("  版本       (超时，adb 无响应)");
                else if (rc != 0) sb.AppendLine("  版本       (执行失败 rc=" + rc + ")");
                else
                {
                    string[] lines = (o + "\n" + e).Split('\n');
                    for (int i = 0; i < lines.Length; i++)
                    {
                        string t = lines[i].Trim();
                        if (t.Length == 0) continue;
                        if (t.StartsWith("Android Debug Bridge version")) sb.AppendLine("  版本       " + t);
                        else if (t.StartsWith("Installed as")) sb.AppendLine("  实际文件   " + t.Substring(12).Trim());
                    }
                }

                // 本机有几份 adb（多版本共存 = 随机断线的头号环境原因）
                List<AdbCopy> copies = FindAllAdb();
                LAST_ADB_COPIES = copies.Count;
                LAST_ADB_MIXED_VER = false;
                if (copies.Count > 1)
                {
                    sb.AppendLine("  本机 adb   发现 " + copies.Count + " 份：");
                    string v0 = "";
                    for (int i = 0; i < copies.Count; i++)
                    {
                        sb.AppendLine("             " + (copies[i].used ? "* " : "  ")
                            + copies[i].ver + "  " + copies[i].path);
                        if (copies[i].ver.Length > 0)
                        {
                            if (v0.Length == 0) v0 = copies[i].ver;
                            else if (v0 != copies[i].ver) LAST_ADB_MIXED_VER = true;
                        }
                    }
                    if (!LAST_ADB_MIXED_VER)
                        sb.AppendLine("             （版本一致，暂不会互相踢掉；建议长期只留一份，减少踩坑）");
                }

                // adb 进程数 + 各自路径（多版本共存一眼就能看出来）
                try
                {
                    Process[] ps = Process.GetProcessesByName("adb");
                    int live = 0;
                    int dead = 0;
                    StringBuilder lines2 = new StringBuilder();
                    for (int i = 0; i < ps.Length; i++)
                    {
                        bool alive = true;
                        try { alive = ps[i].Threads.Count > 0; } catch { }
                        if (!alive) { dead++; continue; }
                        live++;
                        if (live <= 4)
                        {
                            string path = "";
                            try { path = ps[i].MainModule.FileName; }
                            catch { path = "(取不到路径，可能需要管理员)"; }
                            lines2.AppendLine("             pid " + ps[i].Id + "  " + path);
                            if (live == 1) LAST_FIRST_PROC_PATH = path;
                        }
                    }
                    sb.AppendLine("  adb 进程   " + live + " 个"
                        + (dead > 0 ? "（另有 " + dead + " 个已退出的残留对象，不影响使用）" : ""));
                    sb.Append(lines2.ToString());
                }
                catch
                {
                    sb.AppendLine("  adb 进程   (查询失败)");
                }

                // 5037 端口
                sb.AppendLine("  5037 端口  " + (PortOpen(300) ? "在监听" : "未监听（server 没起来）"));

                // 环境变量
                string ah = Environment.GetEnvironmentVariable("ANDROID_HOME");
                string asr = Environment.GetEnvironmentVariable("ANDROID_SDK_ROOT");
                if (!string.IsNullOrEmpty(ah) || !string.IsNullOrEmpty(asr))
                {
                    sb.AppendLine("  ANDROID_HOME   " + (ah == null ? "" : ah));
                    sb.AppendLine("  SDK_ROOT       " + (asr == null ? "" : asr));
                }

                // 当前设备状态
                Snap s = ScanOnce(3000);
                LAST_SCAN_STATE = s.state;
                LAST_SCAN_ONLINE = s.online;
                LAST_SCAN_OFFLINE = s.offline;
                LAST_SCAN_UNAUTH = s.unauth;
                sb.AppendLine("  设备状态   " + s.StateName()
                    + "（在线 " + s.online + " / offline " + s.offline + " / 未授权 " + s.unauth + "）");
                if (s.raw.Trim().Length > 0)
                {
                    string[] dl = s.raw.Trim().Replace("\r\n", "\n").Split('\n');
                    for (int i = 0; i < dl.Length; i++)
                        sb.AppendLine("             " + dl[i].TrimEnd('\r'));
                }

                return sb.ToString();
            }

            // Diagnose 顺带留下的结论素材（只给主线程的 DoDiag 用）
            internal static int LAST_SCAN_STATE = ST_NONE;
            internal static int LAST_SCAN_ONLINE = 0;
            internal static int LAST_SCAN_OFFLINE = 0;
            internal static int LAST_SCAN_UNAUTH = 0;
            internal static int LAST_ADB_COPIES = 0;
            internal static bool LAST_ADB_MIXED_VER = false;
            internal static string LAST_FIRST_PROC_PATH = "";
        }

        // ====================================================================
        //  :diag —— 把"为什么搜不到设备"直接说成一句人话
        // ====================================================================
        internal static void DoDiag()
        {
            Console.WriteLine();
            Console.WriteLine("  ── adb 连接体检 ─────────────────────────────");
            Console.Write(Rec.Diagnose());
            Console.WriteLine("  ── 结论 ─────────────────────────────────────");

            int st = Rec.LAST_SCAN_STATE;
            int procs = Rec.AdbProcCount();
            bool port = Rec.PortOpen(300);

            // 这一条放在最前面：只要机器上有多份不同版本的 adb，
            // 后面所有"搜不到设备"都可能只是它的症状。
            if (Rec.LAST_ADB_MIXED_VER)
            {
                Warn("本机有 " + Rec.LAST_ADB_COPIES + " 份不同版本的 adb.exe —— 这是随机断线的常见原因");
                Hint("Windows 的 adb 服务是全局共享的（5037 端口），谁先启动就听谁的；");
                Hint("两个版本轮流接管时会互相 kill，表现就是隔一阵断线、再连搜不到设备。");
                Hint("处理：只留一份 adb（建议 PATH 里那一份），把其余的改名或从 PATH 移走，");
                Hint("然后按 :rr 让这一份接管服务。带 * 的是本工具当前在用的。");
                Console.WriteLine();
            }

            if (st == Rec.ST_OK)
            {
                Ok("设备在线：" + DEVID + (DEVN > 1 ? "（共 " + DEVN + " 台）" : ""));
                if (DEVN > 1) Hint("多台在线时用 ini 的 serial 固定一台，避免每条命令都要猜");
                if (Rec.LAST_FIRST_PROC_PATH.Length > 0 && ADB.Length > 0
                    && !string.Equals(Rec.LAST_FIRST_PROC_PATH, ADB, StringComparison.OrdinalIgnoreCase)
                    && Rec.LAST_FIRST_PROC_PATH.IndexOf("adb.exe", StringComparison.OrdinalIgnoreCase) > 0)
                {
                    Hint("注意：当前 adb 服务（5037）是由另一个 adb.exe 启动的：");
                    Hint("  " + Rec.LAST_FIRST_PROC_PATH);
                    Hint("本工具用的是 " + ADB);
                    Hint("版本一致时没问题；一旦不一致就会互踢。想彻底稳定就统一成一份，然后按 :rr。");
                }
                return;
            }

            if (st == Rec.ST_NOADB)
            {
                Fail("adb 根本执行不起来");
                Hint("把 adb.exe 放到本程序同目录，或在 ini 里把 adb 写成完整路径");
                return;
            }

            if (st == Rec.ST_UNAUTH || Rec.LAST_SCAN_UNAUTH > 0)
            {
                Fail("设备已识别，但未授权 USB 调试");
                Hint("在车机弹出的「允许 USB 调试」上点允许（勾上一律允许）");
                Hint("如果车机没弹窗：拔掉数据线重插，或在车机开发者选项里撤销授权后重插");
                return;
            }

            if (st == Rec.ST_OFFLINE || Rec.LAST_SCAN_OFFLINE > 0)
            {
                Fail("设备处于 offline：adb 里还挂着失效的旧连接");
                Hint("按 :r 刷新（内部会先 adb reconnect offline，比重启服务温和）");
                Hint("还不行动再按 :rr 重启 adb 服务");
                return;
            }

            if (st == Rec.ST_HANG || !port)
            {
                Fail("adb 服务没起来 / 无响应（5037 端口" + (port ? "在监听但不回话" : "未监听") + "）");
                if (procs > 0)
                    Hint("检测到 " + procs + " 个 adb.exe 进程，可能有僵死的残留，按 :rr 清理重启");
                else
                    Hint("按 :rr 重启 adb 服务");
                Hint("若提示端口被占用：关掉其他 adb 工具（别的助手/IDE）后再试");
                return;
            }

            // 服务正常、也没有 offline/未授权，但列表是空的
            Fail("adb 服务正常，但列表里一台设备都没有");
            Hint("按可能性排查：");
            Hint("1. 数据线只充电不传数据 —— 换一根，或换一个 USB 口（优先主板后置口）");
            Hint("2. 车机没开 USB 调试 —— 开发者选项里打开「USB 调试」");
            Hint("3. 车机 adbd 没起来 —— 重启车机后再插");
            Hint("4. 本机 USB 驱动异常 —— 设备管理器里看有没有黄色感叹号，重装 Google USB Driver");
            if (procs > 1)
            {
                Hint("5. 本机有 " + procs + " 个 adb.exe 在跑：多套 adb 会互抢 5037 端口，"
                     + "表现为随机断线、时不时搜不到设备。统一用同一个 adb 后再试");
            }
        }
    }
}
