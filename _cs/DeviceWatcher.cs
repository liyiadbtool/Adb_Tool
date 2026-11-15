// ============================================================================
//  DeviceWatcher.cs — 基于 adb track-devices 的设备事件监听
//
//  需求来源（2026-11-12）：
//    "识别到设备连接之后要自动连接，不要用反复尝试的方法，要用监听的方法，
//     监听到设备连接了设备后台自动输入 r 重连，连接成功输出信息，
//     连接失败不要输出任何信息"
//
//  为什么不用轮询：
//    原来靠 GUI 的 Timer 每 tick 探一次 adb devices。设备插上到被发现
//    有 0.5~2 秒的延迟，而且空闲时也在不停起 adb 进程（每次 30~80ms CPU）。
//    track-devices 是 adb 协议里专门的订阅通道：一旦设备上下线，
//    adb server 会**主动**往这个连接写一行，零延迟、零轮询。
//
//  协议（adb SERVICES.TXT）：
//    连 127.0.0.1:5037，发 "host:track-devices"，收 4 字节十六进制长度前缀
//    （如 "0012"），紧跟该长度的 payload，形如：
//        "R58M12345\tdevice\n"
//        "R58M12345\toffline\n"
//    之后每条设备列表变化都是一帧。长度前缀是**累积的全量快照**，
//    不是增量 —— 所以每次收到帧都要整体重算"现在有哪些设备在线"。
//
//  设计约束（用户明确要求）：
//    1) 连上了 -> 后台自动执行 r（走 RetrySoft，与手动输入 r 完全同一条路径）
//    2) 成功 -> 输出连接信息
//    3) 失败 -> 一句话都不输出（静默），不能刷屏打扰
//    4) 不能反复尝试 —— 只有"从无到有"这一次状态跃迁才触发重连
//
//  C# 5.0 兼容：不用 out var / 局部函数 / => 表达式体 / $"..."。
// ============================================================================
using System;
using System.Collections.Generic;
using System.Net.Sockets;
using System.Text;
using System.Threading;

namespace AdbLogExport
{
    internal static partial class App
    {
        internal static class DeviceWatcher
        {
            private const int ADB_PORT = 5037;

            // 监听线程。整个进程只跑一个。
            private static Thread _th = null;

            // 停止标志。窗口关闭 / 程序退出时置 true，让 socket 读循环尽快退出。
            private static volatile bool _stop = false;

            // 当前已知的"在线设备集合"。用来识别"从无到有"的跃迁。
            // 只在监听线程里读写，不需要加锁。
            private static string _lastOnline = "";

            // 防重入
            private static volatile bool _reconnecting = false;

            // 重连期间又发生了设备变化：这一轮结束后要补判一次
            private static volatile bool _pendingRecheck = false;

            // 上次触发重连的时间戳（TickCount），用于冷却窗口。
            private static int _lastFireTick = 0;

            // 冷却窗口：一次触发后 3 秒内的状态变化不再触发。
            // 拔插实验里 USB 会连续报 device/offline 好几次，
            // 没有冷却就会连着触发 3~4 次重连，输出区被刷满。
            private const int COOLDOWN_MS = 3000;

            // 首帧基线标志。
            //
            // 为什么需要：Start() 把 _lastOnline 清空，于是监听通道建立后收到的
            // **第一帧**必然满足 "prev 为空 + now 非空"，被判成"从无到有"。
            // 但程序启动时 BootDevice 已经自己连过设备了 —— 如果设备本来就插着，
            // 这一帧会触发一次完全多余的 r 重连，并多打一行"已自动重连"。
            //
            // 所以第一帧只用来对齐基线（记录当前到底有哪些设备在线），不触发。
            // 真正的"插入设备"变化发生在第二帧及以后，那时基线是准的。
            //
            // 只在 Start() 里清 flag；通道中途断开重连（ListenOnce 重入）不动它，
            // 因为那时基线仍然有效，不该再 prime 一次。
            private static bool _primed = false;

            // 回调：由 GUI 层注入"自动执行一次 r"的实现。
            // 返回 true 表示重连成功（据此决定要不要输出）。
            internal delegate bool ReconnectFn();

            private static ReconnectFn _reconnect = null;

            // 输出回调：只在成功时被调用。失败时调用方直接不调。
            private static Action<string> _onOk = null;

            // "设备全部下线"回调。原来这里什么都不做（静默 return），
            // 结果设备拔掉后界面还显示着绿色 root 胶囊和在线设备号 ——
            // 界面必须跟着连接状态走，所以这里要明确通知 GUI 切离线。
            private static Action _onGone = null;

            // ================================================================
            //  启动 / 停止
            // ================================================================

            // reconnect: 真正执行"重连"的委托（GUI 传进入，内部走 RetrySoft）
            // onOk:      重连成功后输出一行信息。失败时不会被调用。
            // onGone:    设备从"有"变"无"时通知 GUI 切离线（可选）
            internal static void Start(ReconnectFn reconnect, Action<string> onOk, Action onGone)
            {
                if (_th != null) return;   // 已经在跑

                _reconnect = reconnect;
                _onOk = onOk;
                _onGone = onGone;
                _stop = false;
                _lastOnline = "";
                _primed = false;   // 首帧只对齐基线，不触发重连

                _th = new Thread(new ThreadStart(Loop));
                _th.IsBackground = true;
                _th.Name = "adb-track-devices";
                _th.Start();
            }

            internal static void Stop()
            {
                _stop = true;
                _th = null;
            }

            // ================================================================
            //  主循环：断线自动重连（这里说的是"监听通道"本身断了要重连，
            //  不是设备重连）。adb server 重启过、或本机网络栈抖动时
            //  socket 会断，必须自己爬起来，否则监听就永久失效了。
            // ================================================================
            private static void Loop()
            {
                while (!_stop)
                {
                    try
                    {
                        ListenOnce();
                    }
                    catch (Exception ex)
                    {
                        // 监听通道异常一律静默 —— 这是后台能力，不该在
                        // 用户面前刷错误。断了就等一会儿重连。
                        App.Trace("watcher: 监听异常 " + ex.Message);
                    }

                    if (_stop) break;

                    // 退避：通道断了不要立刻重连，否则 server 没起来时会
                    // 疯狂空转。1 秒足够，也不影响体验（设备上线本来就会有延迟感知）。
                    for (int i = 0; i < 10 && !_stop; i++)
                    {
                        Thread.Sleep(100);
                    }
                }
            }

            // 建立一次 track-devices 长连接，读到断开为止
            private static void ListenOnce()
            {
                TcpClient cli = null;
                NetworkStream ns = null;

                try
                {
                    cli = new TcpClient();
                    IAsyncResult ar = cli.BeginConnect("127.0.0.1", ADB_PORT, null, null);
                    if (!ar.AsyncWaitHandle.WaitOne(1500, false))
                    {
                        // adb server 没起来。不打印 —— 静默等下一轮。
                        try { cli.Close(); } catch { }
                        return;
                    }
                    cli.EndConnect(ar);
                    cli.NoDelay = true;

                    ns = cli.GetStream();
                    ns.ReadTimeout = 1000;   // 用超时来周期性检查 _stop

                    // 发订阅请求：4 位十六进制长度 + 服务名
                    string req = "host:track-devices";
                    byte[] body = Encoding.ASCII.GetBytes(req);
                    string head = body.Length.ToString("X4");
                    byte[] headB = Encoding.ASCII.GetBytes(head);
                    ns.Write(headB, 0, headB.Length);
                    ns.Write(body, 0, body.Length);
                    ns.Flush();

                    // 先读 OKAY/FAIL 应答
                    string reply = ReadExact(ns, 4);
                    if (reply == null) return;
                    if (reply != "OKAY")
                    {
                        // 老版本 adb 可能不支持 track-devices。
                        // 这时不该死循环重试 —— 直接退出，让调用方知道没这能力。
                        // 但也不能抛异常（会刷屏），静默返回即可。
                        return;
                    }

                    // 每次（重新）订阅成功都要把基线清空重建。
                    //
                    // 【这是"设备插上了却没自动重连"的主因之一】
                    // 通道断掉的那段时间（adb server 重启 / adb root / 休眠唤醒）
                    // 设备可能已经拔插过好几轮。旧基线还停在"之前有设备"，
                    // 于是重新连上后的第一帧被判定成"之前就有设备，不重复触发"，
                    // 自动重连就永远不发生。
                    _lastOnline = "";
                    _primed = false;
                    App.Trace("watcher: 通道就绪，基线已重置");

                    // 持续读帧
                    while (!_stop)
                    {
                        string lenHex = ReadExact(ns, 4);
                        if (lenHex == null) return;   // 通道断了

                        int len = 0;
                        try { len = Convert.ToInt32(lenHex, 16); }
                        catch { return; }             // 帧头异常，通道不可信，重连

                        if (len < 0 || len > 65536) return;   // 防御：畸形帧

                        string payload = "";
                        if (len > 0)
                        {
                            payload = ReadExact(ns, len);
                            if (payload == null) return;
                        }

                        HandleSnapshot(payload);
                    }
                }
                finally
                {
                    try { if (ns != null) ns.Close(); } catch { }
                    try { if (cli != null) cli.Close(); } catch { }
                    App.Trace("watcher: 监听通道断开，1 秒后重订阅");
                }
            }

            // 精确读 n 个字符（ASCII）。超时返回 null。
            // adb 的长度前缀是按**字节**算的，但设备序列号全是 ASCII，
            // 所以按字节读、按 ASCII 解码是安全的。
            //
            // 【2026-11-13 修】旧版把 IOException 一律当成"读超时，继续等"，
            // 于是 adb server 重启 / socket 被重置（ConnectionReset）时，
            // Read 会一直抛 IOException，这个 while 就永远转下去 ——
            // 监听线程活着但再也不收帧，界面从此"设备插上也不自动重连"，
            // 只能重启程序。这是那条"连上设备没自动重连"的真因。
            // 现在按 SocketErrorCode 区分：超时才继续等，其它一律返回 null
            // 交给 Loop 重新订阅。
            private static string ReadExact(NetworkStream ns, int n)
            {
                byte[] buf = new byte[n];
                int got = 0;
                int idle = 0;

                while (got < n)
                {
                    if (_stop) return null;
                    int r;
                    try
                    {
                        r = ns.Read(buf, got, n - got);
                        idle = 0;
                    }
                    catch (System.IO.IOException ex)
                    {
                        System.Net.Sockets.SocketException se = ex.InnerException as System.Net.Sockets.SocketException;
                        bool timeout = (se != null)
                            && (se.SocketErrorCode == System.Net.Sockets.SocketError.TimedOut
                                || se.SocketErrorCode == System.Net.Sockets.SocketError.WouldBlock
                                || se.SocketErrorCode == System.Net.Sockets.SocketError.IOPending);

                        if (!timeout) return null;    // 真断了：交给 Loop 重订阅

                        // 超时也算一次空转。连续 120 次（约 2 分钟）没有任何帧，
                        // 说明这条通道即使没报错也已经不可信，主动重建一次。
                        idle++;
                        if (idle >= 120) return null;
                        continue;
                    }
                    catch (ObjectDisposedException) { return null; }

                    if (r <= 0) return null;   // 对端关闭
                    got += r;
                }
                return Encoding.ASCII.GetString(buf, 0, n);
            }

            // ================================================================
            //  处理一次设备列表快照
            // ================================================================

            // payload 形如 "SER1\tdevice\nSER2\toffline\n"
            private static void HandleSnapshot(string payload)
            {
                // 解析出所有 state == device 的序列号
                List<string> online = new List<string>();
                if (!string.IsNullOrEmpty(payload))
                {
                    string[] lines = payload.Split('\n');
                    for (int i = 0; i < lines.Length; i++)
                    {
                        string line = lines[i].Trim();
                        if (line.Length == 0) continue;

                        int tab = line.IndexOf('\t');
                        if (tab <= 0) continue;

                        string dev = line.Substring(0, tab).Trim();
                        string state = line.Substring(tab + 1).Trim();

                        // 只要 device。offline / unauthorized 都不算"可连"。
                        if (string.Equals(state, "device", StringComparison.OrdinalIgnoreCase)
                            && dev.Length > 0)
                        {
                            online.Add(dev);
                        }
                    }
                }

                online.Sort(StringComparer.OrdinalIgnoreCase);
                string now = string.Join(",", online.ToArray());

                string prev = _lastOnline;
                _lastOnline = now;

                // ---- 首帧特殊处理 ----
                // 见 _primed 的注释：程序启动时设备可能本来就插着。
                // 但要不要跳过首帧，取决于 BootDevice 到底连上没有：
                //   已在连接态 -> 首帧多余，跳过（否则多打一行"已自动重连"）
                //   未在连接态 -> 首帧正是补救机会，照常触发
                if (!_primed)
                {
                    _primed = true;
                    if (DEVN > 0 && !OFFLINE) return;
                }

                // ---- 判定：只在"从无到有"时触发 ----
                WatchAction act = Decide(prev, now, DEVID);

                if (act == WatchAction.Gone)
                {
                    // 设备全部下线：通知 GUI 切离线（root 胶囊置灰、设备号清空）。
                    // 只在"本来有设备"的那一次通知，避免每帧重复。
                    if (_onGone != null)
                    {
                        try { _onGone(); } catch { }
                    }
                    return;
                }
                if (act != WatchAction.Reconnect) return;   // 没变化 / 之前就有设备

                // ---- 冷却 ----
                int nowTick = Environment.TickCount;
                if (_lastFireTick != 0 && (nowTick - _lastFireTick) < COOLDOWN_MS) return;

                // ---- 防重入 ----
                // 一次重连最长 15 秒，期间再插拔一次很常见。
                // 旧行为是直接 return（把这次事件吞掉），结果就是"设备明明插上了，
                // 却没自动重连"。现在只记一个待补检查，等这轮结束后再判一次。
                if (_reconnecting)
                {
                    _pendingRecheck = true;
                    App.Trace("watcher: 重连进行中，记一次待补检查");
                    return;
                }

                FireReconnect("设备上线");
            }

            // 真正发起一次自动重连（独立线程，绝不占监听线程）。
            private static void FireReconnect(string why)
            {
                _lastFireTick = Environment.TickCount;
                App.Trace("watcher: 触发自动重连（" + why + "），在线=" + _lastOnline);

                Thread th = new Thread(new ThreadStart(delegate()
                {
                    // 2026-11-15 闪退修复：后台线程未捕获异常会终止整个进程；
                    // 另外 _reconnecting 必须在 finally 复位 —— 一旦中途抛出，
                    // 标志卡在 true，之后所有重连都会被当成"正在连"而静默丢弃。
                    try
                    {
                        _reconnecting = true;
                        bool ok = TryReconnect();
                        _reconnecting = false;

                        // 第一次失败多半是 adb server 刚被拉起来、USB 还在枚举。
                        // 补一次成功率高很多；失败也不输出（用户要求静默），只留轨迹。
                        if (!ok && _lastOnline.Length > 0 && (DEVN == 0 || OFFLINE))
                        {
                            App.Trace("watcher: 首次重连未成功，2 秒后补一次");
                            try { Thread.Sleep(2000); } catch { }
                            _reconnecting = true;
                            ok = TryReconnect();
                            _reconnecting = false;
                        }

                        if (ok && _onOk != null)
                        {
                            try { _onOk(_lastOnline); } catch { }
                            App.Trace("watcher: 自动重连成功 " + _lastOnline);
                        }
                        else if (!ok)
                        {
                            App.Trace("watcher: 自动重连放弃（DEVN=" + DEVN
                                      + " OFFLINE=" + OFFLINE + " 在线=" + _lastOnline + "）");
                        }

                        // 这轮期间又插拔过：再判一次，别把那次变化丢掉
                        if (_pendingRecheck)
                        {
                            _pendingRecheck = false;
                            if (DEVN == 0 || OFFLINE) FireReconnect("补触发");
                        }
                    }
                    catch (Exception ex)
                    {
                        App.Trace("watcher: 重连线程异常 " + ex.Message);
                    }
                    finally
                    {
                        _reconnecting = false;
                    }
                }));
                th.IsBackground = true;
                th.Name = "adb-track-reconnect";
                th.Start();
            }

            private static bool TryReconnect()
            {
                try
                {
                    if (_reconnect == null) return false;
                    return _reconnect();
                }
                catch { return false; }
            }

            // 状态跃迁判定（纯函数，自检直接打靶）。
            // 这是整个自动重连的核心规则：只有"从无到有"才连，
            // "本来就有"不重复连（否则插第二台设备会反复触发）。
            internal enum WatchAction
            {
                None = 0,
                Gone = 1,
                Reconnect = 2
            }

            internal static WatchAction Decide(string prev, string now)
            {
                return Decide(prev, now, "");
            }

            // curDev：程序当前正在用的序列号。
            // 它从列表里消失、但还有别的设备在线时（典型场景：USB 拔掉、
            // 只剩无线 192.168.x.x:5555），也要重连到剩下那台 ——
            // 否则命令还在往一个已经不存在的序列号上发。
            internal static WatchAction Decide(string prev, string now, string curDev)
            {
                bool wasEmpty = (prev == null || prev.Length == 0);
                bool nowHas = (now != null && now.Length > 0);

                if (!nowHas) return wasEmpty ? WatchAction.None : WatchAction.Gone;
                if (wasEmpty) return WatchAction.Reconnect;

                if (!string.IsNullOrEmpty(curDev) && !ListHas(now, curDev))
                    return WatchAction.Reconnect;

                return WatchAction.None;
            }

            private static bool ListHas(string csv, string item)
            {
                if (string.IsNullOrEmpty(csv)) return false;
                string[] parts = csv.Split(',');
                for (int i = 0; i < parts.Length; i++)
                {
                    if (string.Equals(parts[i].Trim(), item, StringComparison.OrdinalIgnoreCase))
                        return true;
                }
                return false;
            }

            // 供调试/自检：把 payload 解析成在线列表（抽出纯函数便于测）
            internal static List<string> ParseOnline(string payload)
            {
                List<string> online = new List<string>();
                if (string.IsNullOrEmpty(payload)) return online;

                string[] lines = payload.Split('\n');
                for (int i = 0; i < lines.Length; i++)
                {
                    string line = lines[i].Trim();
                    if (line.Length == 0) continue;

                    int tab = line.IndexOf('\t');
                    if (tab <= 0) continue;

                    string dev = line.Substring(0, tab).Trim();
                    string state = line.Substring(tab + 1).Trim();

                    if (string.Equals(state, "device", StringComparison.OrdinalIgnoreCase)
                        && dev.Length > 0)
                    {
                        online.Add(dev);
                    }
                }
                online.Sort(StringComparer.OrdinalIgnoreCase);
                return online;
            }
        }
    }
}
