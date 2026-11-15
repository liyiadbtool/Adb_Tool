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
                // 没有 USB 也可能只是"已经连过无线" —— 那就直接 connect 试试
                if (hostIp.Length == 0)
                {
                    err = "没有可用的 USB 设备，也取不到设备 IP；请先插 USB，或手动填 IP";
                    return false;
                }
            }

            WadbSuppress(14);   // adbd 要重启，先挡住这次"瞬断"

            if (usb.Length > 0)
            {
                string so = "";
                string se = "";
                int rc = AdbCall(new List<string> { "tcpip", port.ToString() }, out so, out se);
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
                    int r2 = AdbCall(new List<string> { "get-state" }, out st, out ste);
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
            return true;
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
            WADB_IP = "";
            return true;
        }

        // ==================== 取 IP ====================
        internal static string WadbDetectIp()
        {
            // ip 优先（toybox 自带）；老 ROM 没有 ip 时退到 ifconfig
            string so = "";
            string se = "";
            AdbCall(new List<string> { "shell", "ip -f inet addr 2>/dev/null" }, out so, out se);
            string ip = ParseFirstIp(so);
            if (ip.Length > 0) return ip;

            so = ""; se = "";
            AdbCall(new List<string> { "shell", "ifconfig 2>/dev/null" }, out so, out se);
            return ParseFirstIp(so);
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
