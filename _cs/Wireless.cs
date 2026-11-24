// ============================================================================
//  Wireless.cs — 无线 adb（adb over TCP）
//
//  为什么单独一个文件：这不是一条命令，而是一串有先后依赖、还会让设备"瞬断"的
//  操作。写在 GuiWeb 里会把消息处理搅乱，写在 Adb.cs 里又和"执行单条 adb"混在一起。
//
//  连接流程（顺序不能换）：
//      1) 确认现在有一台 USB 设备（tcpip 必须从本地连接发出去）
//      2) adb tcpip <port>       —— 让设备侧 adbd 开始监听 TCP
//         【坑】这一步会重启 adbd，USB 会掉线 1~3 秒。DeviceWatcher 看到"设备
//         全部下线"会推离线、把 root 置灰 —— 所以这里开一个抑制窗口，
//         窗口内那一次"全部下线"按瞬断处理，不当真断开。
//      3) 等 adb get-state 回到 device（USB 恢复）
//      4) 取设备 IP：ip -f inet addr 里第一个非 127.0.0.1 的地址
//         （不能只认 wlan0 —— 车机不少是 eth0）
//      5) adb connect ip:port
//      6) adb devices 里必须真的出现 "<ip:port>  device"，否则算失败
//         （connect 有时会打印 "connected to" 但设备马上又掉，不能只看那句话）
//
//  断开：adb disconnect <ip:port>；不带地址则断开全部 TCP 连接。
// ============================================================================
using System;
using System.Collections.Generic;
using System.Text;

namespace AdbLogExport
{
    internal static partial class App
    {
        // 抑制窗口：adbd 重启期间忽略 DeviceWatcher 的"全部下线"
        internal static DateTime WADB_SUPPRESS_UNTIL = DateTime.MinValue;

        internal static bool WadbSuppressed()
        {
            return DateTime.Now < WADB_SUPPRESS_UNTIL;
        }

        internal static void WadbSuppress(int seconds)
        {
            WADB_SUPPRESS_UNTIL = DateTime.Now.AddSeconds(seconds);
        }

        // 当前无线连接（ip:port），空 = 没连
        internal static string WADB_IP = "";

        internal const int WADB_PORT = 5555;

        // ==================== 心跳重连（2026-11-24）====================
        /* 为什么需要：无线 adb 在车机上是"会自己掉"的连接 —— WiFi 休眠、切 AP、
           系统回收 adbd 都会让 adb devices 里那条消失。原来只有 WadbSuppress
           在压告警，没有任何恢复动作，界面一直显示"已连接"，实际所有命令都失败。
           策略：每 15 秒查一次 devices；连续 2 次不在 → 主动 connect；
                 连续 5 次失败 → 放弃并明确报错（不无限重试掩盖真故障）。 */
        private static System.Threading.Timer _wadbBeat;
        private static readonly object _wadbBeatLock = new object();
        private static int _wadbMiss;
        private static int _wadbBeatBusy;
        private static string _wadbBeatTarget = "";

        internal static void WadbStopBeat()
        {
            lock (_wadbBeatLock)
            {
                if (_wadbBeat != null) { try { _wadbBeat.Dispose(); } catch { } _wadbBeat = null; }
                _wadbMiss = 0;
                _wadbBeatTarget = "";
            }
        }

        internal static void WadbStartBeat()
        {
            lock (_wadbBeatLock)
            {
                if (_wadbBeat != null) { try { _wadbBeat.Dispose(); } catch { } }
                _wadbBeatTarget = WADB_IP;
                _wadbMiss = 0;
                if (string.IsNullOrEmpty(_wadbBeatTarget)) return;
                _wadbBeat = new System.Threading.Timer(WadbBeatTick, null, 15000, 15000);
            }
        }

        private static void WadbBeatTick(object state)
        {
            if (System.Threading.Interlocked.Exchange(ref _wadbBeatBusy, 1) == 1) return;
            try
            {
                string target = _wadbBeatTarget;
                if (string.IsNullOrEmpty(target)) { WadbStopBeat(); return; }

                List<string> list = WadbList();
                bool online = false;
                for (int i = 0; i < list.Count; i++)
                    if (string.Equals(list[i], target, StringComparison.OrdinalIgnoreCase)) { online = true; break; }

                if (online)
                {
                    if (_wadbMiss > 0) Ok("无线连接已恢复：" + target);
                    _wadbMiss = 0;
                    return;
                }

                _wadbMiss++;
                if (_wadbMiss == 2)
                    Warn("无线连接疑似断开（" + target + "），正在尝试重连 …");

                if (_wadbMiss < 2) return;

                if (_wadbMiss > 5)
                {
                    Fail("无线连接恢复失败（已重试 4 次）：" + target
                        + "  —— 请检查车机 WiFi，或在界面上重新连接");
                    WadbStopBeat();
                    return;
                }

                string so = ""; string se = "";
                // 2026-11-24（B2）：必须用 quiet 版本。
                // AdbCall 会写 RUNNING_SLOTS[slot]，心跳每 15 秒一次，
                // 可能覆盖主命令的进程引用 → 用户点"停止"杀的是心跳、主命令还在跑。
                AdbCallQuiet(new List<string> { "connect", target }, out so, out se);
                // 结果下一拍用 devices 判定，这里不重复查询（省一次 adb 往返）
            }
            catch (Exception ex) { AdbLogExport.Gui.GuiEntry.Dump("wadb-beat", ex); }
            finally { System.Threading.Interlocked.Exchange(ref _wadbBeatBusy, 0); }
        }

        // ==================== 状态 ====================
        // 从 adb devices 里找出 TCP 条目（序列号带冒号且状态是 device）
        internal static string WadbCurrent()
        {
            List<string> list = WadbList();
            return list.Count > 0 ? list[0] : "";
        }

        internal static List<string> WadbList()
        {
            List<string> found = new List<string>();
            string so = "";
            string se = "";
            int rc = AdbCall(new List<string> { "devices" }, out so, out se);
            if (rc != 0) return found;

            string[] lines = (so + "\n" + se).Split('\n');
            for (int i = 0; i < lines.Length; i++)
            {
                string s = lines[i].Trim();
                if (s.Length == 0) continue;
                if (s.StartsWith("List of devices", StringComparison.OrdinalIgnoreCase)) continue;

                int tab = s.IndexOf('\t');
                if (tab <= 0) tab = s.IndexOf(' ');
                if (tab <= 0) continue;

                string serial = s.Substring(0, tab).Trim();
                string state = s.Substring(tab).Trim();
                if (serial.IndexOf(':') < 0) continue;          // 没有冒号 = USB 序列号
                if (state.IndexOf("device", StringComparison.OrdinalIgnoreCase) < 0) continue;
                if (state.IndexOf("offline", StringComparison.OrdinalIgnoreCase) >= 0) continue;

                found.Add(serial);
            }
            return found;
        }

        // ==================== 连接 ====================
        // host 为空 = 自动取设备 IP；host 可带端口（1.2.3.4:5556），不带则用 5555
        internal static bool WadbConnect(string hostRaw, out string ip, out string err)
        {
            ip = "";
            err = "";

            string host = (hostRaw == null) ? "" : hostRaw.Trim();
            int port = WADB_PORT;
            string hostIp = host;

            int colon = host.IndexOf(':');
            if (colon > 0)
            {
                hostIp = host.Substring(0, colon).Trim();
                string ps = host.Substring(colon + 1).Trim();
                int p = 0;
                if (int.TryParse(ps, out p) && p > 0 && p < 65536) port = p;
                else { err = "端口不合法：" + ps; return false; }
            }

            if (hostIp.Length > 0 && !LooksLikeIp(hostIp))
            {
                err = "IP 格式不对：" + hostIp;
                return false;
            }

            // 1) 有没有本地（USB）设备可以发 tcpip
            string usb = WadbUsbSerial();
            if (usb.Length == 0)
            {
                // 没有 USB 也可能只是"已经连过无线" —— 那就直接 connect 试试。
                // 2026-11-24：先把上次连成功的地址拿来用（WADB_IP），
                // 否则纯无线场景（USB 已拔、想重连）会被"请先插 USB"卡死。
                if (hostIp.Length == 0 && (WADB_IP ?? "").Length > 0)
                {
                    string last = WADB_IP.Trim();
                    int c2 = last.IndexOf(':');
                    if (c2 > 0)
                    {
                        hostIp = last.Substring(0, c2).Trim();
                        int p2 = 0;
                        if (int.TryParse(last.Substring(c2 + 1).Trim(), out p2) && p2 > 0) port = p2;
                    }
                    else hostIp = last;
                }
                if (hostIp.Length == 0)
                {
                    err = "没有可用的 USB 设备，也取不到设备 IP；请先插 USB，或手动填 IP";
                    return false;
                }
            }

            // adbd 重启才有长瞬断；纯 connect 不该压 14 秒（会盖住真故障）
            if (usb.Length > 0) WadbSuppress(14); else WadbSuppress(3);

            if (usb.Length > 0)
            {
                string so = "";
                string se = "";
                // 2026-11-24：必须带 -s。多设备在线（USB + 已连无线）时
                // 不指定序列号，adb 直接报 "more than one device/emulator"，
                // 用户看到的是"adb tcpip 失败"，其实只是没指名道姓。
                int rc = AdbCall(new List<string> { "-s", usb, "tcpip", port.ToString() }, out so, out se);
                string low = (so + " " + se).ToLowerInvariant();
                if (rc != 0 && low.IndexOf("restarting") < 0)
                {
                    WadbSuppress(2);
                    err = "adb tcpip 失败：" + FirstLine((so + " " + se).Trim());
                    return false;
                }

                // 3) 等 USB 回来（最多 ~8 秒）
                bool back = false;
                for (int i = 0; i < 16; i++)
                {
                    string st = "";
                    string ste = "";
                    int r2 = AdbCall(new List<string> { "-s", usb, "get-state" }, out st, out ste);
                    if (r2 == 0 && st.Trim().ToLowerInvariant().StartsWith("device"))
                    {
                        back = true;
                        break;
                    }
                    System.Threading.Thread.Sleep(500);
                }
                if (!back)
                {
                    WadbSuppress(2);
                    err = "adbd 重启后设备没有回来（USB 被拔掉，或这台 ROM 不支持 tcpip）";
                    return false;
                }
            }

            // 4) 没给 IP 就自己找
            if (hostIp.Length == 0)
            {
                hostIp = WadbDetectIp();
                if (hostIp.Length == 0)
                {
                    WadbSuppress(2);
                    err = "取不到设备 IP（ip/ifconfig 都没给出可用的内网地址），请手动填";
                    return false;
                }
            }

            string target = hostIp + ":" + port;

            // 5) 连接
            string co = "";
            string ce = "";
            AdbCall(new List<string> { "connect", target }, out co, out ce);
            string clow = (co + " " + ce).ToLowerInvariant();

            // 6) 以 devices 为准（"connected to" 之后又掉线的情况真实存在）
            bool ok = false;
            List<string> got = WadbList();
            for (int i = 0; i < got.Count; i++)
            {
                if (string.Equals(got[i], target, StringComparison.OrdinalIgnoreCase)) { ok = true; break; }
            }

            if (!ok)
            {
                WadbSuppress(2);
                err = (clow.IndexOf("cannot") >= 0 || clow.IndexOf("failed") >= 0)
                    ? ("连接失败：" + FirstLine((co + " " + ce).Trim()))
                    : ("连接后设备没有出现在 adb devices 里（" + target + "）");
                return false;
            }

            WADB_IP = target;
            ip = target;
            WadbSuppress(3);   // 留一点余量给设备列表刷新
            WadbStartBeat();   // 2026-11-24：连上就开始心跳，掉线自动重连
            return true;
        }

        /* ===== P7（2026-11-24）：Android 11+ 的无线调试配对 =====
           新系统把无线调试改成了"配对码"流程：
             adb pair <ip>:<配对端口> <6 位码>   → 成功后
             adb connect <ip>:<连接端口>         ← 注意端口不是同一个
           原来的 tcpip 5555 在部分 ROM 上已被禁用，只留这条路。
           这里只做"配对"这一步；连接仍走 WadbConnect（端口由用户填）。 */
        internal static bool WadbPair(string hostRaw, string code, out string err)
        {
            err = "";
            string host = (hostRaw == null) ? "" : hostRaw.Trim();
            string pin = (code == null) ? "" : code.Trim().Replace(" ", "");
            if (host.Length == 0) { err = "请填配对地址（车机上「无线调试 → 使用配对码配对」显示的那串 ip:端口）"; return false; }
            if (pin.Length < 4) { err = "配对码不合法（应为 6 位数字）"; return false; }

            int colon = host.IndexOf(':');
            if (colon <= 0) { err = "配对地址必须带端口，例如 192.168.1.7:37000"; return false; }
            string ipOnly = host.Substring(0, colon).Trim();
            if (!LooksLikeIp(ipOnly)) { err = "IP 格式不对：" + ipOnly; return false; }

            string so = ""; string se = "";
            // 配对超时很短（车机上只有几十秒有效），先压住瞬断告警
            WadbSuppress(6);
            int rc = AdbCall(new List<string> { "pair", host, pin }, out so, out se);
            string low = (so + " " + se).ToLowerInvariant();

            if (low.IndexOf("successfully paired") >= 0)
            {
                Ok("配对成功：" + host);
                Hint("接下来用「连接」填同一台设备的**连接端口**（不是配对端口），形如 " + ipOnly + ":5555");
                return true;
            }

            if (low.IndexOf("cannot") >= 0 || low.IndexOf("failed") >= 0 || rc != 0)
            {
                err = "配对失败：" + FirstLine((so + " " + se).Trim());
                Hint("常见原因：配对码过期（重开车机配对弹窗）、地址填的是连接端口而不是配对端口、手机/车机不在同一网段");
                return false;
            }

            // 有些版本只打印 "Enter pairing code"，无明确成功字样 —— 让 devices 说话
            err = "配对未确认：" + FirstLine((so + " " + se).Trim());
            return false;
        }

        internal static bool WadbDisconnect(string hostRaw, out string err)
        {
            err = "";
            string host = (hostRaw == null) ? "" : hostRaw.Trim();
            if (host.Length == 0) host = WadbCurrent();
            if (host.Length == 0) host = WADB_IP;

            string so = "";
            string se = "";
            List<string> argv = new List<string>();
            argv.Add("disconnect");
            if (!string.IsNullOrEmpty(host)) argv.Add(host);

            int rc = AdbCall(argv, out so, out se);
            if (rc != 0)
            {
                err = "断开失败：" + FirstLine((so + " " + se).Trim());
                return false;
            }

            /* 2026-11-24：adb disconnect 对"本来就没连"的目标也返回成功，
               所以不能只看退出码。断开后再查一次 devices：目标仍在列表里
               （常见于 offline 条目）才算真失败。 */
            if (!string.IsNullOrEmpty(host))
            {
                List<string> still = WadbList();
                for (int i = 0; i < still.Count; i++)
                {
                    if (string.Equals(still[i], host, StringComparison.OrdinalIgnoreCase))
                    {
                        err = "命令返回成功，但 " + host + " 仍在设备列表里（可能是 offline 残留），建议执行 adb disconnect 或重启 adb";
                        return false;
                    }
                }
            }
            WADB_IP = "";
            WadbStopBeat();
            return true;
        }

        // ==================== 取 IP ====================
        /// <summary>本机（PC）所有 IPv4 地址的 /24 前缀，用于挑"能连通"的设备地址。</summary>
        private static List<string> LocalPrefixes()
        {
            var list = new List<string>();
            try
            {
                var nics = System.Net.NetworkInformation.NetworkInterface.GetAllNetworkInterfaces();
                for (int i = 0; i < nics.Length; i++)
                {
                    try
                    {
                        var ua = nics[i].GetIPProperties().UnicastAddresses;
                        for (int k = 0; k < ua.Count; k++)
                        {
                            var a = ua[k].Address;
                            if (a == null) continue;
                            if (a.AddressFamily != System.Net.Sockets.AddressFamily.InterNetwork) continue;
                            string t = a.ToString();
                            int dot = t.LastIndexOf('.');
                            if (dot > 0) list.Add(t.Substring(0, dot));
                        }
                    }
                    catch { }
                }
            }
            catch { }
            return list;
        }

        /// <summary>把一段 ip 输出解析成候选列表（跳过回环 / 链路本地）。</summary>
        private static List<string> ParseAllIps(string text)
        {
            var got = new List<string>();
            if (string.IsNullOrEmpty(text)) return got;
            string[] lines = text.Split('\n');
            for (int i = 0; i < lines.Length; i++)
            {
                string s2 = lines[i].Trim();
                int at = s2.IndexOf("inet ", StringComparison.OrdinalIgnoreCase);
                if (at < 0) continue;
                string rest = s2.Substring(at + 5).Trim();
                int sp = rest.IndexOf(' ');
                string addr = (sp > 0) ? rest.Substring(0, sp) : rest;
                if (addr.StartsWith("addr:", StringComparison.OrdinalIgnoreCase)) addr = addr.Substring(5);
                int slash = addr.IndexOf('/');
                if (slash > 0) addr = addr.Substring(0, slash);
                if (!LooksLikeIp(addr)) continue;
                if (addr.StartsWith("127.")) continue;
                if (addr.StartsWith("169.254.")) continue;
                if (!got.Contains(addr)) got.Add(addr);
            }
            return got;
        }

        internal static string WadbDetectIp()
        {
            // ip 优先（toybox 自带）；老 ROM 没有 ip 时退到 ifconfig
            string so = "";
            string se = "";
            AdbCall(new List<string> { "shell", "ip -f inet addr 2>/dev/null" }, out so, out se);
            var cands = ParseAllIps(so);
            if (cands.Count == 0)
            {
                so = ""; se = "";
                AdbCall(new List<string> { "shell", "ifconfig 2>/dev/null" }, out so, out se);
                cands = ParseAllIps(so);
            }
            if (cands.Count == 0) return "";

            /* 2026-11-24：车机常有多网口（以太网 192.168.1.x / 4G 10.x / 热点 192.168.43.x），
               ip 命令的输出顺序不稳定，取"第一个"经常拿到 PC 根本路由不到的 4G 地址，
               connect 必然超时。这里优先选与 PC 同 /24 网段的地址。 */
            List<string> mine = LocalPrefixes();
            for (int i = 0; i < cands.Count; i++)
            {
                string t = cands[i];
                int dot = t.LastIndexOf('.');
                if (dot <= 0) continue;
                string pfx = t.Substring(0, dot);
                if (mine.Contains(pfx)) return t;
            }
            return cands[0];
        }

        // 从 "inet 192.168.1.7/24 brd ..." 里取第一个非回环地址
        internal static string ParseFirstIp(string text)
        {
            if (string.IsNullOrEmpty(text)) return "";

            string[] lines = text.Split('\n');
            for (int i = 0; i < lines.Length; i++)
            {
                string s = lines[i].Trim();
                int at = s.IndexOf("inet ", StringComparison.OrdinalIgnoreCase);
                if (at < 0) continue;

                string rest = s.Substring(at + 5).Trim();
                int sp = rest.IndexOf(' ');
                string addr = (sp > 0) ? rest.Substring(0, sp) : rest;
                // 老 ifconfig 的写法是 "inet addr:192.168.0.9"，多一个前缀
                if (addr.StartsWith("addr:", StringComparison.OrdinalIgnoreCase))
                    addr = addr.Substring(5);
                int slash = addr.IndexOf('/');
                if (slash > 0) addr = addr.Substring(0, slash);

                if (!LooksLikeIp(addr)) continue;
                if (addr.StartsWith("127.")) continue;            // 回环
                if (addr.StartsWith("169.254.")) continue;        // 链路本地，连不通
                return addr;
            }
            return "";
        }

        // 只校验 IPv4 形状（不做 DNS / 主机名解析：车载网络里填主机名几乎没人用）
        internal static bool LooksLikeIp(string s)
        {
            if (string.IsNullOrEmpty(s)) return false;
            string[] parts = s.Split('.');
            if (parts.Length != 4) return false;
            for (int i = 0; i < 4; i++)
            {
                if (parts[i].Length == 0 || parts[i].Length > 3) return false;
                for (int k = 0; k < parts[i].Length; k++)
                {
                    if (parts[i][k] < '0' || parts[i][k] > '9') return false;
                }
                int v = 0;
                if (!int.TryParse(parts[i], out v)) return false;
                if (v < 0 || v > 255) return false;
            }
            return true;
        }

        // 当前 USB 序列号（不带冒号的那条）
        internal static string WadbUsbSerial()
        {
            string so = "";
            string se = "";
            int rc = AdbCall(new List<string> { "devices" }, out so, out se);
            if (rc != 0) return "";

            string[] lines = (so + "\n" + se).Split('\n');
            for (int i = 0; i < lines.Length; i++)
            {
                string s = lines[i].Trim();
                if (s.Length == 0 || s.StartsWith("List of devices", StringComparison.OrdinalIgnoreCase)) continue;
                int tab = s.IndexOf('\t');
                if (tab <= 0) tab = s.IndexOf(' ');
                if (tab <= 0) continue;
                string serial = s.Substring(0, tab).Trim();
                string state = s.Substring(tab).Trim();
                if (serial.IndexOf(':') >= 0) continue;
                if (state.ToLowerInvariant() != "device") continue;
                return serial;
            }
            return "";
        }
    }
}
