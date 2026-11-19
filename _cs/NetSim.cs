using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Text;
using System.Threading;

namespace AdbLogExport
{
    /// <summary>
    /// 弱网模拟（PC 端代理）。
    ///
    /// 为什么不用设备端 tc netem：
    ///   实测这台车机内核没编 sch_netem —— 连 `tc qdisc add dev lo root netem` 都报
    ///   "RTNETLINK answers: No such file or directory"，tbf 同样失败。
    ///   参考工具（SynTestUtil）走的是 PC 端 mitmproxy + 车机 http_proxy 指向 PC，
    ///   不需要 root、不依赖内核模块，所以它稳定可用。这里用**内置代理**对齐这条路：
    ///   不引入 Python/mitmproxy，直接在本进程里做 TCP 转发 + 上下行整形。
    ///
    /// 能力边界（与参考工具一致）：
    ///   · 只影响走 HTTP(S) 代理的流量（浏览器/App 的 HTTP 请求）；
    ///   · UDP / 直连 socket 不受影响；
    ///   · 丢包是"整块丢弃"，不是真正的 TCP 丢包。
    /// </summary>
    internal static class NetSim
    {
        internal static int Port = 8888;

        // 上下行分别是两套参数（对齐参考工具的 UPLOAD_* / DOWNLOAD_*）
        internal static int UpRateKbps, DownRateKbps;
        internal static int UpDelayMs, DownDelayMs;
        internal static int UpLossPct, DownLossPct;

        internal static volatile bool Running;
        private static TcpListener _srv;
        private static Thread _accept;
        private static readonly List<TcpClient> _conns = new List<TcpClient>();
        private static readonly object _lock = new object();
        private static Random _rnd = new Random();

        internal static long UpBytes, DownBytes;
        internal static int ConnTotal, ConnActive;

        internal static Action<string> OnLog;

        private static void Log(string s)
        {
            Action<string> h = OnLog;
            if (h != null) { try { h(s); } catch { } }
        }

        /// <summary>取本机局域网 IPv4（车机要能访问到的那一个）。</summary>
        internal static string LocalIp()
        {
            string best = "";
            try
            {
                NetworkInterface[] nis = NetworkInterface.GetAllNetworkInterfaces();
                for (int i = 0; i < nis.Length; i++)
                {
                    NetworkInterface ni = nis[i];
                    if (ni.OperationalStatus != OperationalStatus.Up) continue;
                    if (ni.NetworkInterfaceType == NetworkInterfaceType.Loopback) continue;
                    IPInterfaceProperties props = ni.GetIPProperties();
                    bool hasGw = false;
                    try { hasGw = props.GatewayAddresses.Count > 0; } catch { }
                    foreach (UnicastIPAddressInformation ua in props.UnicastAddresses)
                    {
                        if (ua.Address.AddressFamily != AddressFamily.InterNetwork) continue;
                        string s = ua.Address.ToString();
                        if (s.StartsWith("169.254.")) continue;
                        if (hasGw) return s;          // 有网关的优先（真正的局域网口）
                        if (best.Length == 0) best = s;
                    }
                }
            }
            catch { }
            return best;
        }

        internal static bool Start(int port, int upRate, int downRate,
                                  int upDelay, int downDelay, int upLoss, int downLoss)
        {
            if (Running) Stop();
            try
            {
                Port = (port <= 0) ? 8888 : port;
                UpRateKbps = upRate; DownRateKbps = downRate;
                UpDelayMs = upDelay; DownDelayMs = downDelay;
                UpLossPct = upLoss; DownLossPct = downLoss;
                UpBytes = DownBytes = 0; ConnTotal = 0; ConnActive = 0;

                _srv = new TcpListener(IPAddress.Any, Port);
                _srv.Start();
                Running = true;

                _accept = new Thread(AcceptLoop);
                _accept.IsBackground = true;
                _accept.Start();

                Log("代理已启动，监听 0.0.0.0:" + Port);
                Log("网络参数：上行 " + upRate + "kbps / " + upDelay + "ms / " + upLoss + "%，"
                    + "下行 " + downRate + "kbps / " + downDelay + "ms / " + downLoss + "%");
                return true;
            }
            catch (Exception ex)
            {
                Running = false;
                Log("启动失败：" + ex.Message + "（端口 " + Port + " 可能被占用）");
                return false;
            }
        }

        internal static void Stop()
        {
            Running = false;
            try { if (_srv != null) _srv.Stop(); } catch { }
            _srv = null;
            lock (_lock)
            {
                for (int i = 0; i < _conns.Count; i++)
                {
                    try { _conns[i].Close(); } catch { }
                }
                _conns.Clear();
            }
            ConnActive = 0;
            Log("代理已停止");
        }

        private static void AcceptLoop()
        {
            while (Running)
            {
                TcpClient c = null;
                try { c = _srv.AcceptTcpClient(); }
                catch { break; }
                ConnTotal++;
                lock (_lock) { _conns.Add(c); }
                Thread t = new Thread(delegate() { Handle(c); });
                t.IsBackground = true;
                t.Start();
            }
        }

        private static void Handle(TcpClient client)
        {
            ConnActive++;
            TcpClient up = null;
            try
            {
                client.NoDelay = true;
                NetworkStream cs = client.GetStream();
                cs.ReadTimeout = 30000;

                // ---- 读请求头（到空行为止）----
                byte[] head = ReadHeader(cs);
                if (head == null || head.Length == 0) return;
                string text = Encoding.ASCII.GetString(head);
                string firstLine = text.Split('\n')[0].Trim();
                string[] parts = firstLine.Split(' ');
                if (parts.Length < 3) return;
                string method = parts[0];

                string host;
                int hostPort;
                byte[] toSend;

                if (method.Equals("CONNECT", StringComparison.OrdinalIgnoreCase))
                {
                    // HTTPS 隧道：不解析内容，纯转发
                    ParseHostPort(parts[1], 443, out host, out hostPort);
                    up = new TcpClient();
                    up.NoDelay = true;
                    up.Connect(host, hostPort);
                    byte[] ok = Encoding.ASCII.GetBytes("HTTP/1.1 200 Connection Established\r\n\r\n");
                    cs.Write(ok, 0, ok.Length);
                    toSend = null;
                }
                else
                {
                    // 普通 HTTP：把绝对 URI 改写成 origin-form 再转发
                    string uri = parts[1];
                    if (uri.StartsWith("http://", StringComparison.OrdinalIgnoreCase))
                    {
                        string rest = uri.Substring(7);
                        int slash = rest.IndexOf('/');
                        string hostPart = (slash < 0) ? rest : rest.Substring(0, slash);
                        string pathPart = (slash < 0) ? "/" : rest.Substring(slash);
                        ParseHostPort(hostPart, 80, out host, out hostPort);
                        string newHead = method + " " + pathPart + " "
                                       + string.Join(" ", parts, 2, parts.Length - 2);
                        toSend = Encoding.ASCII.GetBytes(newHead + "\r\n");
                    }
                    else
                    {
                        // 不是代理式请求（罕见）：直接按 Host 头转发
                        host = HeaderValue(text, "Host");
                        int idx = host.IndexOf(':');
                        if (idx > 0) { int.TryParse(host.Substring(idx + 1), out hostPort); host = host.Substring(0, idx); }
                        else hostPort = 80;
                        if (string.IsNullOrEmpty(host)) return;
                        toSend = Encoding.ASCII.GetBytes(firstLine + "\r\n");
                    }

                    // 除首行外的其余头原样带上
                    int nl = text.IndexOf("\r\n");
                    if (nl >= 0)
                    {
                        string restHead = text.Substring(nl + 2);
                        int blank = restHead.IndexOf("\r\n\r\n");
                        if (blank >= 0) restHead = restHead.Substring(0, blank + 2);
                        if (restHead.Length > 0)
                        {
                            byte[] rb = Encoding.ASCII.GetBytes(restHead);
                            byte[] merged = new byte[toSend.Length + rb.Length];
                            Buffer.BlockCopy(toSend, 0, merged, 0, toSend.Length);
                            Buffer.BlockCopy(rb, 0, merged, toSend.Length, rb.Length);
                            toSend = merged;
                        }
                    }

                    up = new TcpClient();
                    up.NoDelay = true;
                    up.Connect(host, hostPort);
                    if (toSend != null && toSend.Length > 0) up.GetStream().Write(toSend, 0, toSend.Length);
                    Log("转发 " + method + " " + host + ":" + hostPort);
                }

                NetworkStream us = up.GetStream();
                // 上行 = 客户端→服务器，下行 = 服务器→客户端（与面板列一致）
                Thread t1 = new Thread(delegate() { Pump(cs, us, true, true); });
                Thread t2 = new Thread(delegate() { Pump(us, cs, false, false); });
                t1.IsBackground = true; t2.IsBackground = true;
                t1.Start(); t2.Start();
                t1.Join(); t2.Join();
            }
            catch (Exception ex)
            {
                // 连接级异常很常见（客户端取消、目标拒绝），不当作错误刷屏
                Log("连接结束：" + Short(ex.Message));
            }
            finally
            {
                try { if (up != null) up.Close(); } catch { }
                try { client.Close(); } catch { }
                lock (_lock) { _conns.Remove(client); }
                ConnActive--;
            }
        }

        /// <summary>单向转发：限速 + 首包延迟 + 按块丢包。</summary>
        private static void Pump(NetworkStream src, NetworkStream dst, bool isUp, bool closeDst)
        {
            byte[] buf = new byte[4096];
            int rate = isUp ? UpRateKbps : DownRateKbps;
            int delay = isUp ? UpDelayMs : DownDelayMs;
            int loss = isUp ? UpLossPct : DownLossPct;
            double bytesPerSec = rate > 0 ? rate * 1000.0 / 8.0 : 0;   // kbps → B/s
            bool delayDone = false;
            System.Diagnostics.Stopwatch sw = System.Diagnostics.Stopwatch.StartNew();
            long budget = 0;

            try
            {
                while (true)
                {
                    int n = src.Read(buf, 0, buf.Length);
                    if (n <= 0) break;

                    // 往返延迟：方向上首次数据前等一次（近似 RTT，不是逐包）
                    if (delay > 0 && !delayDone)
                    {
                        delayDone = true;
                        Thread.Sleep(delay);
                    }

                    // 丢包：整块丢弃（与参考工具"整请求丢弃"同粒度）
                    if (loss > 0 && _rnd.Next(100) < loss) continue;

                    if (bytesPerSec > 0)
                    {
                        // 令牌桶：按累计时间给出可发送额度
                        budget = (long)(sw.Elapsed.TotalSeconds * bytesPerSec) - (isUp ? UpBytes : DownBytes)
                               + GetDirBytes(isUp);
                        if (n > budget)
                        {
                            int waitMs = (int)((n - budget) * 1000.0 / bytesPerSec);
                            if (waitMs > 0) Thread.Sleep(Math.Min(waitMs, 2000));
                        }
                    }

                    dst.Write(buf, 0, n);
                    dst.Flush();
                    if (isUp) Interlocked.Add(ref UpBytes, n);
                    else Interlocked.Add(ref DownBytes, n);
                }
            }
            catch { }
            finally
            {
                try { if (closeDst) dst.Close(); } catch { }
            }
        }

        private static long GetDirBytes(bool isUp)
        {
            return isUp ? Interlocked.Read(ref UpBytes) : Interlocked.Read(ref DownBytes);
        }

        private static byte[] ReadHeader(NetworkStream s)
        {
            MemoryStream ms = new MemoryStream();
            int b, prev = -1;
            while ((b = s.ReadByte()) >= 0)
            {
                ms.WriteByte((byte)b);
                if (b == '\n' && prev == '\r') break;          // 只读到第一行结束
                if (b == '\n') break;
                prev = b;
                if (ms.Length > 65536) break;
            }
            // 继续把剩下到空行的头读掉
            if (ms.Length == 0) return null;
            byte[] firstLine = ms.ToArray();
            MemoryStream all = new MemoryStream();
            all.Write(firstLine, 0, firstLine.Length);
            int state = 0;
            while (true)
            {
                b = s.ReadByte();
                if (b < 0) break;
                all.WriteByte((byte)b);
                if (b == '\n')
                {
                    state++;
                    if (state >= 1 && all.Length >= 2)
                    {
                        byte[] arr = all.ToArray();
                        int len = arr.Length;
                        if (len >= 2 && arr[len - 2] == '\r' && arr[len - 1] == '\n' && len >= 2)
                        {
                            // 空行判定：前一行也是空
                            if (len >= 4 && arr[len - 4] == '\r' && arr[len - 3] == '\n') break;
                        }
                    }
                }
                if (all.Length > 65536) break;
            }
            return all.ToArray();
        }

        private static void ParseHostPort(string s, int defPort, out string host, out int port)
        {
            host = s; port = defPort;
            int i = s.LastIndexOf(':');
            if (i > 0)
            {
                int p;
                if (int.TryParse(s.Substring(i + 1), out p)) { host = s.Substring(0, i); port = p; }
            }
            // IPv6 字面量 [::1]:80 的极简处理
            if (host.StartsWith("[") && host.EndsWith("]")) host = host.Substring(1, host.Length - 2);
        }

        private static string HeaderValue(string head, string name)
        {
            string[] lines = head.Split('\n');
            for (int i = 0; i < lines.Length; i++)
            {
                string l = lines[i].Trim();
                int c = l.IndexOf(':');
                if (c <= 0) continue;
                if (l.Substring(0, c).Equals(name, StringComparison.OrdinalIgnoreCase))
                    return l.Substring(c + 1).Trim();
            }
            return "";
        }

        private static string Short(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            s = s.Replace("\r", " ").Replace("\n", " ");
            return s.Length > 80 ? s.Substring(0, 80) + "…" : s;
        }
    }
}
