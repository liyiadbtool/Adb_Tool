// ============================================================================
//  Cast.cs — 多屏投屏（车机 5 块屏同时在工具里看）
//
//  为什么不用 ffmpeg / screenrecord：
//     实测这台车机（Android >10）上
//       · screenrecord 对主屏(0)、副驾(2) 输出 **0 字节**（保护面/编码器受限），
//         只有 800x480 那块能录；
//       · screencap -d N 三块屏都能出图，单帧 35~131 KB，2~4 fps。
//     而 screenrecord 出的是 h264，不转码浏览器播不了；转码就要 ffmpeg（105MB），
//     那就违背"最小包也要全功能"。
//     所以这里走 **screencap 轮询 + MJPEG 风格 multipart 转发**：
//     设备端出 PNG，本机原样转给浏览器 <img>，零依赖、零转码。
//     代价是帧率 2~4fps（够看画面/复现问题），不是视频级 30fps。
//
//  架构：
//     CastServer：127.0.0.1 上一个极简 HTTP（TcpListener 手写，避开 HttpListener 的 URL ACL），
//                 /live/<slot> 用 multipart/x-mixed-replace 持续推该槽最新一帧。
//     CastSlots ：每个槽一个线程，循环 `adb exec-out screencap -d <id> -p`，按节奏发布。
//     CastDisplays：从 dumpsys display 的 mViewports 解析 displayId/分辨率/类型。
// ============================================================================
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;                 // A16：raw 帧转 JPEG 用
using System.Drawing.Imaging;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;

namespace AdbLogExport
{
    internal static partial class App
    {
        // ==================== 屏位发现 ====================
        internal class CastDisplay
        {
            internal int Id = 0;
            internal int W = 0;
            internal int H = 0;
            internal string Type = "";      // INTERNAL / EXTERNAL
            internal bool Active = true;
            internal string UniqueId = "";
        }

        // 解析 dumpsys display 里的 mViewports=[DisplayViewport{...}, DisplayViewport{...}]
        // 一行里可能有多块屏，按 "DisplayViewport{" 切开逐个取字段。
        // 取不到的字段保持默认，绝不因为格式变化抛异常。
        internal static List<CastDisplay> CastParseDisplays(string dumpsys)
        {
            List<CastDisplay> list = new List<CastDisplay>();
            if (string.IsNullOrEmpty(dumpsys)) return list;

            // 只看 mViewports 那一行（其它行里的 DisplayViewport 是回显/历史，容易重复）
            int at = dumpsys.IndexOf("mViewports=[", StringComparison.Ordinal);
            string seg = (at >= 0) ? dumpsys.Substring(at) : dumpsys;
            int nl = seg.IndexOf('\n');
            if (nl > 0) seg = seg.Substring(0, nl);

            string[] parts = seg.Split(new string[] { "DisplayViewport{" }, StringSplitOptions.RemoveEmptyEntries);
            for (int i = 0; i < parts.Length; i++)
            {
                string p = parts[i];
                CastDisplay d = new CastDisplay();
                d.Id = IntField(p, "displayId=", -1);
                if (d.Id < 0) continue;
                d.W = IntField(p, "deviceWidth=", 0);
                d.H = IntField(p, "deviceHeight=", 0);
                d.Type = StrField(p, "type=", ',');
                d.UniqueId = StrField(p, "uniqueId='", '\'');
                d.Active = p.IndexOf("isActive=true", StringComparison.OrdinalIgnoreCase) >= 0;
                list.Add(d);
            }
            return list;
        }

        private static int IntField(string s, string key, int def)
        {
            int at = s.IndexOf(key, StringComparison.OrdinalIgnoreCase);
            if (at < 0) return def;
            int i = at + key.Length;
            int st = i;
            while (i < s.Length && s[i] >= '0' && s[i] <= '9') i++;
            if (i == st) return def;
            int v = 0;
            if (!int.TryParse(s.Substring(st, i - st), out v)) return def;
            return v;
        }

        private static string StrField(string s, string key, char stop)
        {
            int at = s.IndexOf(key, StringComparison.OrdinalIgnoreCase);
            if (at < 0) return "";
            int i = at + key.Length;
            int st = i;
            while (i < s.Length && s[i] != stop) i++;
            return s.Substring(st, i - st).Trim();
        }

        internal static List<CastDisplay> CastDisplays()
        {
            string o = "";
            string e = "";
            ShellCall(CUR, "dumpsys display 2>/dev/null", out o, out e);
            List<CastDisplay> list = CastParseDisplays(o + "\n" + e);
            // 只留真正能截的（分辨率有效）
            List<CastDisplay> ok = new List<CastDisplay>();
            for (int i = 0; i < list.Count; i++)
                if (list[i].W > 0 && list[i].H > 0) ok.Add(list[i]);
            return ok;
        }

        // ==================== 极简 HTTP（multipart 推流） ====================
        internal static class CastServer
        {
            internal const int MAX_SLOT = 8;

            private static TcpListener _lis = null;
            private static Thread _acceptTh = null;
            private static volatile bool _stop = false;
            internal static int Port = 0;

            private static byte[][] _buf = new byte[MAX_SLOT][];
            private static int[] _ver = new int[MAX_SLOT];
            private static object _lk = new object();

            internal static bool Running { get { return _lis != null && Port > 0; } }

            internal static void Start()
            {
                if (Running) return;
                try
                {
                    _lis = new TcpListener(IPAddress.Loopback, 0);
                    _lis.Start();
                    Port = ((IPEndPoint)_lis.LocalEndpoint).Port;

                    _stop = false;
                    _acceptTh = new Thread(new ThreadStart(AcceptLoop));
                    _acceptTh.IsBackground = true;
                    _acceptTh.Name = "cast-http";
                    _acceptTh.Start();
                    App.Trace("cast: 本地流服务 127.0.0.1:" + Port);
                }
                catch (Exception ex)
                {
                    App.Trace("cast: 启动流服务失败 " + ex.Message);
                    _lis = null;
                    Port = 0;
                }
            }

            internal static void Stop()
            {
                _stop = true;
                try { if (_lis != null) _lis.Stop(); } catch { }
                _lis = null;
                Port = 0;
            }

            // 发布一帧（A16 起统一是 JPEG：raw 抓帧本地编码，见 CastGrabFrame）
            internal static void Publish(int slot, byte[] jpg)
            {
                // 只校验 JPEG 签名（FF D8 FF），不按体积卡：全黑小图可能只有几百字节，
                // 早先写成 "< 100 丢弃"，结果这类正常帧被静默丢掉。
                if (slot < 0 || slot >= MAX_SLOT || jpg == null || jpg.Length < 8) return;
                if (jpg[0] != 0xFF || jpg[1] != 0xD8 || jpg[2] != 0xFF) return;
                lock (_lk)
                {
                    _buf[slot] = jpg;
                    _ver[slot]++;
                }
            }

            internal static int Version(int slot)
            {
                lock (_lk) { return _ver[slot]; }
            }

            internal static int CurrentSlot { get { return 0; } }

            private static void AcceptLoop()
            {
                while (!_stop)
                {
                    TcpClient c = null;
                    try { c = _lis.AcceptTcpClient(); }
                    catch { if (_stop) return; Thread.Sleep(100); continue; }

                    TcpClient cc = c;
                    Thread th = new Thread(new ThreadStart(delegate { Serve(cc); }));
                    th.IsBackground = true;
                    th.Start();
                }
            }

            private static void Serve(TcpClient c)
            {
                NetworkStream ns = null;
                try
                {
                    c.NoDelay = true;
                    ns = c.GetStream();
                    ns.ReadTimeout = 5000;
                    ns.WriteTimeout = 10000;

                    // 读请求头（只需要第一行里的路径）
                    string req = ReadHead(ns);
                    if (req == null) return;

                    string path = PathOf(req);
                    // 去掉查询串：前端为了绕过缓存会加 ?t=时间戳，
                    // 早先没剥掉，slot 被解析成 "0?t=123" → 直接断开连接 → 画面空白。
                    int qm = path.IndexOf('?');
                    if (qm >= 0) path = path.Substring(0, qm);
                    int hash = path.IndexOf('#');
                    if (hash >= 0) path = path.Substring(0, hash);

                    // 2026-11-15：单帧快照端点（短连接，响应完立刻 Connection: close）。
                    // 底部缩略条原来也连 /live/<i> 长连接，每开一路就多占一条同源连接；
                    // 浏览器对同一 host 的并发连接有限，超过 2~3 路后缩略图拿不到连接就全黑。
                    // 缩略图只要"看一眼当前画面"，用最近一帧 PNG 的短请求即可，不占长连接池。
                    if (path.StartsWith("/snap/", StringComparison.OrdinalIgnoreCase))
                    {
                        int sslot = 0;
                        try { sslot = int.Parse(path.Substring(6).Trim()); }
                        catch { return; }
                        if (sslot < 0 || sslot >= MAX_SLOT) return;
                        byte[] snap;
                        lock (_lk) { snap = _buf[sslot]; }
                        if (snap == null || snap.Length < 8)
                        {
                            byte[] no = Encoding.ASCII.GetBytes(
                                "HTTP/1.1 204 No Content\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n");
                            ns.Write(no, 0, no.Length);
                            return;
                        }
                        byte[] sh = Encoding.ASCII.GetBytes(
                            "HTTP/1.1 200 OK\r\nContent-Type: image/jpeg\r\nContent-Length: "
                            + snap.Length + "\r\nCache-Control: no-store, no-cache, must-revalidate\r\n"
                            + "Connection: close\r\n\r\n");
                        ns.Write(sh, 0, sh.Length);
                        ns.Write(snap, 0, snap.Length);
                        ns.Flush();
                        return;
                    }

                    if (!path.StartsWith("/live/", StringComparison.OrdinalIgnoreCase))
                    {
                        byte[] body = Encoding.UTF8.GetBytes("cast server ok");
                        byte[] head = Encoding.ASCII.GetBytes(
                            "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: "
                            + body.Length + "\r\nConnection: close\r\n\r\n");
                        ns.Write(head, 0, head.Length);
                        ns.Write(body, 0, body.Length);
                        return;
                    }

                    int slot = 0;
                    try { slot = int.Parse(path.Substring(6).Trim()); }
                    catch { return; }
                    if (slot < 0 || slot >= MAX_SLOT) return;

                    byte[] h = Encoding.ASCII.GetBytes(
                        "HTTP/1.1 200 OK\r\n"
                        + "Content-Type: multipart/x-mixed-replace; boundary=frame\r\n"
                        + "Cache-Control: no-store, no-cache, must-revalidate\r\n"
                        + "Pragma: no-cache\r\nConnection: close\r\n\r\n");
                    ns.Write(h, 0, h.Length);
                    ns.Flush();

                    int last = -1;
                    while (!_stop)
                    {
                        int v = Version(slot);
                        if (v == last || v == 0) { Thread.Sleep(20); continue; }

                        byte[] frame;
                        lock (_lk)
                        {
                            frame = _buf[slot];
                            last = _ver[slot];
                        }
                        if (frame == null || frame.Length == 0) { Thread.Sleep(20); continue; }

                        string partHead = "--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                          + frame.Length + "\r\n\r\n";
                        byte[] ph = Encoding.ASCII.GetBytes(partHead);

                        ns.Write(ph, 0, ph.Length);
                        ns.Write(frame, 0, frame.Length);
                        ns.Write(new byte[] { 13, 10 }, 0, 2);
                        ns.Flush();
                    }
                }
                catch
                {
                    // 客户端断开 / 超时：静默结束这个连接
                }
                finally
                {
                    try { if (ns != null) ns.Close(); } catch { }
                    try { c.Close(); } catch { }
                }
            }

            private static string ReadHead(NetworkStream ns)
            {
                byte[] b = new byte[1];
                StringBuilder sb = new StringBuilder();
                DateTime end = DateTime.Now.AddSeconds(5);
                while (DateTime.Now < end)
                {
                    int r;
                    try { r = ns.Read(b, 0, 1); }
                    catch { return null; }
                    if (r <= 0) return null;
                    sb.Append((char)b[0]);
                    string s = sb.ToString();
                    if (s.EndsWith("\r\n\r\n")) return s;
                    if (s.Length > 8192) return s;
                }
                return sb.ToString();
            }

            private static string PathOf(string head)
            {
                int sp1 = head.IndexOf(' ');
                if (sp1 <= 0) return "";
                int sp2 = head.IndexOf(' ', sp1 + 1);
                if (sp2 <= sp1) return "";
                return head.Substring(sp1 + 1, sp2 - sp1 - 1);
            }
        }

        // ==================== 每个槽的采集 ====================
        internal class CastSlot
        {
            internal int Slot;
            internal int DisplayId;
            internal volatile bool Stop;
            internal Thread Th;
            internal long Frames;          // 累计帧数
            internal long LastMs;          // 上一帧耗时
            internal string Err = "";
            // 2026-11-15：点击画面后立刻唤醒采集循环抓一帧，不等 sleep 走完
            internal AutoResetEvent Kick = new AutoResetEvent(false);
        }

        private static CastSlot[] CAST = new CastSlot[CastServer.MAX_SLOT];
        private static readonly object CAST_LK = new object();

        internal static bool CastIsRunning(int slot)
        {
            lock (CAST_LK) { return CAST[slot] != null; }
        }

        internal static void CastStart(int slot, int displayId)
        {
            if (slot < 0 || slot >= CastServer.MAX_SLOT) return;
            CastServer.Start();
            CastStop(slot);

            CastSlot s = new CastSlot();
            s.Slot = slot;
            s.DisplayId = displayId;

            lock (CAST_LK) { CAST[slot] = s; }

            // 2026-11-15 闪退修复：采集线程未捕获异常会终止整个 CLR 进程。
            // 兜住后置 Stop/Err，让界面显示"已停止 + 原因"而不是窗口消失。
            s.Th = new Thread(new ThreadStart(delegate
            {
                try { CastLoop(s); }
                catch (Exception ex)
                {
                    s.Stop = true;
                    s.Err = "采集线程异常：" + ex.Message;
                    App.Trace("cast: CastLoop 崩溃 slot=" + slot + " " + ex);
                }
            }));
            s.Th.IsBackground = true;
            s.Th.Name = "cast-" + slot;
            s.Th.Start();
            App.Trace("cast: 槽 " + slot + " 开始投 displayId=" + displayId);
        }

        internal static void CastStop(int slot)
        {
            if (slot < 0 || slot >= CastServer.MAX_SLOT) return;
            CastSlot s = null;
            lock (CAST_LK)
            {
                s = CAST[slot];
                CAST[slot] = null;
            }
            if (s != null)
            {
                s.Stop = true;
                try { s.Kick.Set(); } catch { }   // 唤醒 WaitOne，别让循环睡满一个周期才退出
                App.Trace("cast: 槽 " + slot + " 停止（已投 " + s.Frames + " 帧）");
            }
        }

        // 供 GUI 查状态：是否在投、已投多少帧、最近单帧耗时、错误
        internal static void CastInfo(int slot, out bool running, out long frames,
                                      out long lastMs, out int displayId, out string err)
        {
            running = false; frames = 0; lastMs = 0; displayId = -1; err = "";
            if (slot < 0 || slot >= CastServer.MAX_SLOT) return;
            lock (CAST_LK)
            {
                CastSlot s = CAST[slot];
                if (s == null) return;
                running = !s.Stop;
                frames = s.Frames;
                lastMs = s.LastMs;
                displayId = s.DisplayId;
                err = s.Err == null ? "" : s.Err;
            }
        }

        internal static void CastStopAll()
        {
            for (int i = 0; i < CastServer.MAX_SLOT; i++) CastStop(i);
            CastServer.Stop();
        }

        // 2026-11-15 点击流畅化：GUI 侧每完成一次 input tap 就调用一次。
        // 立刻唤醒该槽采集循环的帧间等待（CastLoop 里的 Kick.WaitOne），
        // 马上抓下一帧把点击结果推给浏览器，不用等 minGapMs 睡满。
        // 只 Set 一个 AutoResetEvent，零 adb 开销；槽没开 / 已停时静默忽略。
        internal static void CastKick(int slot)
        {
            if (slot < 0 || slot >= CastServer.MAX_SLOT) return;
            CastSlot s = null;
            lock (CAST_LK) { s = CAST[slot]; }
            if (s != null && !s.Stop) { try { s.Kick.Set(); } catch { } }
        }

        // 抓一帧：screencap -d <id> -p（PNG 原样）
        internal static bool CastGrabPng(int displayId, out byte[] png, out long ms)
        {
            png = null;
            ms = 0;
            long t0 = Environment.TickCount;

            string serial = "";
            if (!string.IsNullOrEmpty(SERIAL) && SERIAL_OK) serial = SERIAL;
            else serial = DEVID;
            // 组装：adb [-s serial] exec-out screencap -d N -p
            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = ADB;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            psi.RedirectStandardOutput = true;
            psi.RedirectStandardError = true;
            psi.RedirectStandardInput = true;

            StringBuilder args = new StringBuilder();
            if (serial.Length > 0) args.Append(" -s ").Append(serial);
            args.Append(" exec-out screencap -d ").Append(displayId).Append(" -p");
            psi.Arguments = args.ToString();

            try
            {
                using (Process p = new Process())
                {
                    p.StartInfo = psi;
                    p.Start();
                    // 2026-11-15 卡死/闪退修复：原实现直接 CopyTo —— adb 卡住时
                    // 该线程永久阻塞，投屏帧再也不更新，screencap 子进程越积越多。
                    // 改成：后台线程拷贝 + 主线 WaitForExit(8s) 超时 Kill，
                    // 截断的输出会被下面的 PNG 头校验判掉，不会推坏图。
                    using (MemoryStream msBuf = new MemoryStream(256 * 1024))
                    {
                        Thread cp = new Thread((ThreadStart)delegate
                        {
                            try { p.StandardOutput.BaseStream.CopyTo(msBuf); } catch { }
                        });
                        cp.IsBackground = true;
                        Thread ce = new Thread((ThreadStart)delegate
                        {
                            try { p.StandardError.ReadToEnd(); } catch { }
                        });
                        ce.IsBackground = true;
                        cp.Start();
                        ce.Start();
                        if (!p.WaitForExit(8000))
                        {
                            try { p.Kill(); } catch { }
                            App.Trace("cast: screencap 超时被杀 displayId=" + displayId);
                        }
                        if (!cp.Join(1000)) { /* 拷贝线程随进程退出自然结束 */ }
                        if (!ce.Join(300)) { }
                        png = msBuf.ToArray();
                    }
                }
            }
            catch (Exception ex)
            {
                App.Trace("cast: screencap 失败 " + ex.Message);
                png = null;
            }

            ms = Environment.TickCount - t0;
            // PNG 头校验：不是 PNG 就当失败（避免把错误文本当图片推给浏览器）
            if (png == null || png.Length < 8
                || png[0] != 0x89 || png[1] != 0x50 || png[2] != 0x4E || png[3] != 0x47)
            {
                png = null;
                return false;
            }
            return true;
        }

        // ==================== A16：raw 抓帧 + 本地转 JPEG ====================
        // 用户反馈"投屏低帧率、卡顿"。实测日志（gui_trace.log）三次投屏：
        //   511s/789 帧 = 1.54fps、407s/648 = 1.59fps、49s/73 = 1.49fps。
        // 单帧 670ms 里绝大部分花在**设备端 PNG 编码** —— `-p` 让弱 CPU 的车机
        // 压 PNG，一块 1920x720 的屏要 400ms 上下，这是协议层的天花板，
        // 不换抓帧方式再怎么调参数都没用。
        //
        // 现在改成两步：
        //   ① 设备端 `screencap -d N`（**不带 -p**）直接吐原始 RGBA，
        //      设备只做一次内存拷贝，编码耗时从 ~400ms 降到 ~20ms；
        //   ② 本机 System.Drawing 缩到 1280 宽、转 JPEG q72 再推给浏览器
        //      （JPEG 比 PNG 小一半，WebView2 解码也快得多）。
        // 实测（Android 14 手机，无线 adb）：png 656ms / raw 734ms —— 无线链路上
        // raw 的 5.7MB 传输反而更慢，所以不写死，改成首次抓帧两条都测、选快的。
        // USB3 下 raw 通常明显赢。真正的 30fps 要走 h264 + MSE，用户已明确不做。
        internal static bool CastGrabRaw(int displayId, out int w, out int h,
                                         out byte[] rgba, out long ms)
        {
            w = 0; h = 0; rgba = null; ms = 0;
            long t0 = Environment.TickCount;

            string serial = "";
            if (!string.IsNullOrEmpty(SERIAL) && SERIAL_OK) serial = SERIAL;
            else serial = DEVID;

            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = ADB;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            psi.RedirectStandardOutput = true;
            psi.RedirectStandardError = true;
            psi.RedirectStandardInput = true;

            StringBuilder args = new StringBuilder();
            if (serial.Length > 0) args.Append(" -s ").Append(serial);
            args.Append(" exec-out screencap -d ").Append(displayId);
            psi.Arguments = args.ToString();

            byte[] data = null;
            try
            {
                using (Process p = new Process())
                {
                    p.StartInfo = psi;
                    p.Start();
                    using (MemoryStream buf = new MemoryStream(4 * 1024 * 1024))
                    {
                        Thread cp = new Thread((ThreadStart)delegate
                        {
                            try { p.StandardOutput.BaseStream.CopyTo(buf); } catch { }
                        });
                        cp.IsBackground = true;
                        Thread ce = new Thread((ThreadStart)delegate
                        {
                            try { p.StandardError.ReadToEnd(); } catch { }
                        });
                        ce.IsBackground = true;
                        cp.Start(); ce.Start();
                        if (!p.WaitForExit(8000))
                        {
                            try { p.Kill(); } catch { }
                            App.Trace("cast: raw 抓帧超时 displayId=" + displayId);
                        }
                        if (!cp.Join(1500)) { }
                        if (!ce.Join(300)) { }
                        data = buf.ToArray();
                    }
                }
            }
            catch (Exception ex)
            {
                App.Trace("cast: raw 抓帧失败 " + ex.Message);
                return false;
            }

            ms = Environment.TickCount - t0;
            if (data == null || data.Length < 16) return false;

            // header: width(4) height(4) format(4) [colorSpace(4)]
            int ww = BitConverter.ToInt32(data, 0);
            int hh = BitConverter.ToInt32(data, 4);
            int fmt = BitConverter.ToInt32(data, 8);
            if (ww <= 0 || hh <= 0 || ww > 8192 || hh > 8192) return false;
            if (fmt != 1) return false;      // 只认 RGBA_8888，其它格式退回 PNG 通道

            // 头部长度按"总长度 - 像素字节数"反推：有的 ROM 是 12 字节，
            // 新版本多一个 colorSpace 变成 16 字节。硬编码 12 会在 16 的地方错一行。
            long need = (long)ww * hh * 4L;
            int hdr = (int)(data.Length - need);
            if (hdr < 12 || hdr > 32) return false;

            w = ww; h = hh;
            rgba = new byte[need];
            Buffer.BlockCopy(data, hdr, rgba, 0, (int)need);
            return true;
        }

        /// <summary>
        /// RGBA 原始缓冲 → 缩放到 maxW 宽 → JPEG。返回 null 表示失败。
        /// 注意 Android 给的是 R,G,B,A 字节序，而 GDI+ 的 Format32bppArgb 在内存里
        /// 是 B,G,R,A —— 必须先交换 R/B，否则整屏会偏蓝。
        /// </summary>
        internal static byte[] CastEncodeJpeg(int w, int h, byte[] rgba, int maxW, int quality)
        {
            if (rgba == null || w <= 0 || h <= 0) return null;
            if (rgba.Length < w * h * 4) return null;
            try
            {
                int n = w * h * 4;
                byte[] bgra = new byte[n];
                for (int i = 0; i < n; i += 4)
                {
                    byte r = rgba[i];
                    bgra[i] = rgba[i + 2];
                    bgra[i + 1] = rgba[i + 1];
                    bgra[i + 2] = r;
                    bgra[i + 3] = rgba[i + 3];
                }

                System.Runtime.InteropServices.GCHandle pin =
                    System.Runtime.InteropServices.GCHandle.Alloc(
                        bgra, System.Runtime.InteropServices.GCHandleType.Pinned);
                try
                {
                    using (Bitmap src = new Bitmap(w, h, w * 4,
                               System.Drawing.Imaging.PixelFormat.Format32bppArgb,
                               pin.AddrOfPinnedObject()))
                    {
                        int tw = w, th = h;
                        if (maxW > 0 && w > maxW)
                        {
                            tw = maxW;
                            th = (int)((long)h * maxW / w);
                            if (th < 1) th = 1;
                        }
                        using (Bitmap dst = new Bitmap(tw, th,
                                   System.Drawing.Imaging.PixelFormat.Format24bppRgb))
                        {
                            using (Graphics g = Graphics.FromImage(dst))
                            {
                                // 双线性足够：投屏是"看清画面"，不是出图，
                                // HighQualityBicubic 会白花 20ms/帧。
                                g.InterpolationMode =
                                    System.Drawing.Drawing2D.InterpolationMode.Bilinear;
                                g.PixelOffsetMode =
                                    System.Drawing.Drawing2D.PixelOffsetMode.HighSpeed;
                                g.SmoothingMode =
                                    System.Drawing.Drawing2D.SmoothingMode.None;
                                g.DrawImage(src, 0, 0, tw, th);
                            }
                            return EncodeJpeg(dst, quality);
                        }
                    }
                }
                finally { pin.Free(); }
            }
            catch (Exception ex)
            {
                App.Trace("cast: JPEG 编码失败 " + ex.Message);
                return null;
            }
        }

        private static byte[] EncodeJpeg(Bitmap bmp, int quality)
        {
            ImageCodecInfo jpg = null;
            ImageCodecInfo[] all = ImageCodecInfo.GetImageEncoders();
            for (int i = 0; i < all.Length; i++)
            {
                if (string.Equals(all[i].MimeType, "image/jpeg", StringComparison.OrdinalIgnoreCase))
                { jpg = all[i]; break; }
            }
            if (jpg == null) return null;
            EncoderParameters ep = new EncoderParameters(1);
            ep.Param[0] = new EncoderParameter(System.Drawing.Imaging.Encoder.Quality,
                                               (long)quality);
            using (MemoryStream ms = new MemoryStream(256 * 1024))
            {
                bmp.Save(ms, jpg, ep);
                return ms.ToArray();
            }
        }

        /// <summary>
        /// 统一出口：优先 raw→JPEG；raw 失败（老 ROM / 非 RGBA）才退回 PNG 抓帧，
        /// 并把 PNG 也重编码成 JPEG —— 保证推给浏览器的永远是同一种格式，
        /// MIME 才不会一半 png 一半 jpeg。
        /// </summary>
        // 最近一帧走的哪条路（仅供诊断输出）
        internal static string LastGrabPath = "";

        // 每个屏走哪条抓帧路：raw 还是 png。A16 实测结论 ——
        //   raw  = 设备几乎不耗 CPU，但要把 w*h*4 字节整体搬过来；
        //   png  = 只搬几十 KB，但弱 CPU 的车机压 PNG 要 600ms 上下。
        // 谁快完全取决于链路：USB3 上 raw 明显赢（1600x900 约 150ms），
        // 无线 adb 上传输只有 8MB/s，raw 反而更慢。所以第一次抓帧时两条都测一次，
        // 选快的用，之后固定 —— 不猜、不写死。
        private static readonly Dictionary<int, string> _grabMode =
            new Dictionary<int, string>();
        private static readonly object _grabLk = new object();

        private static string GrabMode(int displayId)
        {
            lock (_grabLk)
            {
                string m;
                return _grabMode.TryGetValue(displayId, out m) ? m : "";
            }
        }
        private static void SetGrabMode(int displayId, string m)
        {
            lock (_grabLk) { _grabMode[displayId] = m; }
        }

        // raw 一条路：取原始 RGBA → 本地缩放 → JPEG
        private static bool GrabRawJpeg(int displayId, out byte[] jpg, out long ms)
        {
            jpg = null;
            int w, h; byte[] rgba;
            if (!CastGrabRaw(displayId, out w, out h, out rgba, out ms)) return false;
            jpg = CastEncodeJpeg(w, h, rgba, 1280, 72);
            if (jpg == null || jpg.Length == 0) { jpg = null; return false; }
            LastGrabPath = "raw " + w + "x" + h + " → JPEG";
            return true;
        }

        // png 一条路：设备压 PNG（体积小）→ 本地解码 → 统一成 JPEG
        private static bool GrabPngJpeg(int displayId, out byte[] jpg, out long ms)
        {
            jpg = null;
            byte[] png;
            if (!CastGrabPng(displayId, out png, out ms)) return false;
            jpg = JpegFromPng(png);
            if (jpg == null) return false;
            LastGrabPath = "png → JPEG（传输小，设备编码慢）";
            return true;
        }

        private static byte[] JpegFromPng(byte[] png)
        {
            try
            {
                using (MemoryStream src = new MemoryStream(png))
                using (Bitmap bmp = new Bitmap(src))
                {
                    int tw = bmp.Width, th = bmp.Height;
                    if (bmp.Width > 1280)
                    {
                        tw = 1280;
                        th = (int)((long)bmp.Height * 1280 / bmp.Width);
                    }
                    if (tw != bmp.Width || th != bmp.Height)
                    {
                        using (Bitmap dst = new Bitmap(tw, th,
                                   System.Drawing.Imaging.PixelFormat.Format24bppRgb))
                        {
                            using (Graphics g = Graphics.FromImage(dst))
                            {
                                g.InterpolationMode =
                                    System.Drawing.Drawing2D.InterpolationMode.Bilinear;
                                g.DrawImage(bmp, 0, 0, tw, th);
                            }
                            return EncodeJpeg(dst, 72);
                        }
                    }
                    return EncodeJpeg(bmp, 72);
                }
            }
            catch (Exception ex)
            {
                App.Trace("cast: PNG 转 JPEG 失败 " + ex.Message);
                return null;
            }
        }

        /// <summary>
        /// 抓一帧并统一成 JPEG。probe=true 时两条路都测一次并选快的（每个屏只做一次）。
        /// </summary>
        internal static bool CastGrabFrame(int displayId, out byte[] jpg, out long ms)
        {
            return CastGrabFrame(displayId, out jpg, out ms, false);
        }

        internal static bool CastGrabFrame(int displayId, out byte[] jpg, out long ms, bool probe)
        {
            string mode = GrabMode(displayId);

            if (probe || mode.Length == 0)
            {
                byte[] a = null, b = null;
                long am = 0, bm = 0;
                bool okA = GrabRawJpeg(displayId, out a, out am);
                bool okB = GrabPngJpeg(displayId, out b, out bm);

                if (!okA && !okB) { jpg = null; ms = 0; return false; }
                if (okA && !okB) { SetGrabMode(displayId, "raw"); jpg = a; ms = am; return true; }
                if (!okA && okB) { SetGrabMode(displayId, "png"); jpg = b; ms = bm; return true; }

                // 两条都通：raw 允许 15% 的容差，超过才切 png
                bool useRaw = am <= (long)(bm * 1.15);
                SetGrabMode(displayId, useRaw ? "raw" : "png");
                App.Trace("cast: display=" + displayId + " 探测 raw=" + am + "ms png=" + bm
                          + "ms → 选 " + (useRaw ? "raw" : "png"));
                jpg = useRaw ? a : b;
                ms = useRaw ? am : bm;
                return true;
            }

            if (mode == "png") return GrabPngJpeg(displayId, out jpg, out ms);
            return GrabRawJpeg(displayId, out jpg, out ms);
        }

        private static void CastLoop(CastSlot s)
        {
            // A16：raw 抓帧单帧约 120~200ms，帧间只补 90ms，不再硬等 120ms。
            // 原来 120ms 是在 PNG 400ms/帧的前提下定的，现在会把帧率压回 3fps。
            int minGapMs = 90;
            int fails = 0;      // 连续失败计数：设备掉线时别无限空转
            bool firstTry = true;

            while (!s.Stop)
            {
                byte[] jpg = null;
                long ms = 0;
                bool ok = CastGrabFrame(s.DisplayId, out jpg, out ms, firstTry);
                if (ok && !s.Stop)
                {
                    CastServer.Publish(s.Slot, jpg);
                    s.Frames++;
                    s.LastMs = ms;
                    s.Err = "";
                    fails = 0;
                    firstTry = false;
                }
                else if (!s.Stop)
                {
                    fails++;
                    // A16：非 0 屏第一帧就失败 → 立刻停，别重试 5 次让用户白等 3 秒。
                    // screencap -d 只对默认 display 可靠，副屏 / HUD / PHUD 在定制
                    // ROM 上基本抓不到，这是已知限制 —— 与其转圈，不如直接指路。
                    if (firstTry && s.DisplayId > 0)
                    {
                        s.Err = "该屏不能用 screencap 采集，请用 scrcpy 外部窗口"
                              + "（指令页 → 投屏）";
                        s.Stop = true;
                        App.Trace("cast: display " + s.DisplayId + " 首帧失败，直接停止");
                        break;
                    }
                    s.Err = "采集失败（该屏可能受保护或已离线）";
                    if (fails >= 5) { s.Stop = true; s.Err = "设备离线或该屏不可采集，已停止"; break; }
                    s.Kick.WaitOne(600);
                    continue;
                }

                // 单帧够久就不补等待；太快才补一点，避免把 adb 通道打满
                // （日志抓取、文件传输共用同一个 adb server）。
                long wait = minGapMs - ms;
                if (wait > 0) s.Kick.WaitOne((int)wait);
            }
        }

        // ==================== 流服务自测（-casttest） ====================
        // 只测"服务能不能用真 socket 拉出一帧" —— 不依赖设备，也不依赖浏览器。
        internal static int CastSelfTest()
        {
            int fail = 0;
            Console.WriteLine();
            Console.WriteLine("== 投屏流服务自测 ==");

            CastServer.Start();
            if (!CastServer.Running)
            {
                Console.WriteLine("  [FAIL] 服务未启动");
                return 1;
            }
            Console.WriteLine("  [OK]   监听 127.0.0.1:" + CastServer.Port);

            // A16：帧格式统一成 JPEG，自测的假帧也跟着换。
            // 顺手让这条自测真的走一遍 raw→JPEG 编码器（造 64x32 的纯色 RGBA），
            // 这样 CAST 编码链路里最容易出问题的 R/B 交换、缩放、Encoder 查找都覆盖到了。
            int tw = 64, th = 32;
            byte[] rgba = new byte[tw * th * 4];
            for (int i = 0; i < rgba.Length; i += 4)
            {
                rgba[i] = 0x20; rgba[i + 1] = 0x80; rgba[i + 2] = 0xC0; rgba[i + 3] = 0xFF;
            }
            byte[] frame = CastEncodeJpeg(tw, th, rgba, 0, 72);
            if (frame == null || frame.Length < 4)
            {
                Console.WriteLine("  [FAIL] raw → JPEG 编码失败（自测造帧都没出来）");
                CastServer.Stop();
                return 1;
            }
            Console.WriteLine("  [OK]   raw → JPEG 编码器可用（" + frame.Length + " 字节）");
            CastServer.Publish(0, frame);

            string head = Fetch(CastServer.Port, "/live/0");
            if (head.Contains("multipart/x-mixed-replace")) Console.WriteLine("  [OK]   返回 multipart 流");
            else { Console.WriteLine("  [FAIL] 不是 multipart：" + Brief(head)); fail++; }

            if (head.Contains("Content-Type: image/jpeg")) Console.WriteLine("  [OK]   分片声明 image/jpeg（A16 起帧格式统一为 JPEG）");
            else { Console.WriteLine("  [FAIL] 分片类型不对：" + Brief(head)); fail++; }

            if (head.Contains("Content-Length: " + frame.Length))
                Console.WriteLine("  [OK]   分片长度与帧一致");
            else { Console.WriteLine("  [FAIL] 分片长度不符"); fail++; }

            // 带查询串（前端真实用法）必须同样可用
            string headQ = Fetch(CastServer.Port, "/live/0?t=123456");
            if (headQ.Contains("Content-Length: " + frame.Length))
                Console.WriteLine("  [OK]   带 ?t= 查询串也能取帧");
            else { Console.WriteLine("  [FAIL] 带查询串取不到帧：" + Brief(headQ)); fail++; }

            // 未发布帧的槽位不能崩
            string head2 = Fetch(CastServer.Port, "/live/7");
            if (head2.Contains("multipart")) Console.WriteLine("  [OK]   空槽位也能建连");
            else { Console.WriteLine("  [FAIL] 空槽位建连异常：" + Brief(head2)); fail++; }

            CastServer.Stop();
            Console.WriteLine();
            Console.WriteLine(fail == 0 ? "  投屏自检通过" : "  投屏自检失败 " + fail + " 项");
            return fail == 0 ? 0 : 1;
        }

        // 真机探针：验证"截帧 → 发布 → HTTP 取回"整条链路
        internal static int CastProbe(int displayId)
        {
            Console.WriteLine();
            Console.WriteLine("== 投屏真机探针：displayId=" + displayId + " ==");

            byte[] frame = null;
            long ms = 0;
            bool ok = CastGrabFrame(displayId, out frame, out ms);
            if (!ok)
            {
                Console.WriteLine("  [FAIL] 截帧失败（该屏可能受保护/离线）");
                return 1;
            }
            Console.WriteLine("  [OK]   截帧 " + frame.Length + " 字节，耗时 " + ms + " ms"
                              + "（" + LastGrabPath + "）");

            CastServer.Start();
            CastServer.Publish(0, frame);
            string head = Fetch(CastServer.Port, "/live/0");
            CastServer.Stop();

            bool hasLen = head.Contains("Content-Length: " + frame.Length);
            Console.WriteLine(hasLen ? "  [OK]   流服务转发帧长度一致" : "  [FAIL] 转发的帧长度不一致");
            Console.WriteLine(hasLen ? "" : "         " + Brief(head));
            Console.WriteLine("  估算帧率：" + (ms > 0 ? (1000.0 / ms).ToString("0.0") : "?") + " fps");
            return hasLen ? 0 : 1;
        }

        // 诊断用的常驻流服务：起服务 + 持续采指定屏，打印端口后挂着。
        // 用途：用浏览器直接访问 http://127.0.0.1:<port>/live/0 验证"到底是不是浏览器那侧不显示"。
        internal static void CastServe(string idsCsv, int seconds)
        {
            CastServer.Start();
            string[] parts = (idsCsv == null ? "0" : idsCsv).Split(',');
            for (int k = 0; k < parts.Length && k < CastServer.MAX_SLOT; k++)
            {
                int did = 0;
                if (!int.TryParse(parts[k].Trim(), out did)) continue;
                CastStart(k, did);
            }
            Console.WriteLine("PORT=" + CastServer.Port);
            Console.WriteLine("URL=http://127.0.0.1:" + CastServer.Port + "/live/0");
            Console.WriteLine("（" + seconds + " 秒后自动退出）");

            int waited = 0;
            while (waited < seconds * 10)
            {
                Thread.Sleep(100);
                waited++;
            }
            CastStopAll();
        }

        private static string Brief(string s)
        {
            if (string.IsNullOrEmpty(s)) return "(空)";
            s = s.Replace("\r", " ").Replace("\n", " ");
            return s.Length > 90 ? s.Substring(0, 90) : s;
        }

        private static string Fetch(int port, string path)
        {
            try
            {
                using (TcpClient c = new TcpClient())
                {
                    c.Connect(IPAddress.Loopback, port);
                    NetworkStream ns = c.GetStream();
                    ns.ReadTimeout = 3000;
                    byte[] req = Encoding.ASCII.GetBytes(
                        "GET " + path + " HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n");
                    ns.Write(req, 0, req.Length);
                    // 头部和第一帧分片可能落在不同的 TCP 段里，单次 Read 只能拿到头部。
                    // 这里循环读，直到拿到分片头（Content-Length）或 1.5 秒超时。
                    byte[] buf = new byte[16384];
                    int total = 0;
                    DateTime end = DateTime.Now.AddMilliseconds(1500);
                    while (DateTime.Now < end && total < buf.Length)
                    {
                        int r;
                        try { r = ns.Read(buf, total, buf.Length - total); }
                        catch { break; }
                        if (r <= 0) break;
                        total += r;
                        string sofar = Encoding.ASCII.GetString(buf, 0, total);
                        if (sofar.IndexOf("Content-Length:", StringComparison.Ordinal) >= 0
                            && total > 120) break;
                    }
                    if (total <= 0) return "";
                    return Encoding.ASCII.GetString(buf, 0, total);
                }
            }
            catch (Exception ex) { return "ERR " + ex.Message; }
        }

        // ==================== 录制（按钮触发，不参与投屏链路） ====================
        private static Process CAST_REC = null;
        private static int CAST_REC_SLOT = -1;
        private static string CAST_REC_FILE = "";
        private static DateTime CAST_REC_T0;

        internal static bool CastRecordStart(int slot, int displayId, out string err)
        {
            err = "";
            CastRecordStop(slot);

            string dev = "/sdcard/adtool_cast_" + slot + "_" + DateTime.Now.ToString("HHmmss") + ".mp4";

            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = ADB;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            psi.RedirectStandardOutput = true;
            psi.RedirectStandardError = true;

            string serial = (!string.IsNullOrEmpty(SERIAL) && SERIAL_OK) ? SERIAL : DEVID;
            StringBuilder args = new StringBuilder();
            if (serial.Length > 0) args.Append(" -s ").Append(serial);
            // 180s 是 screenrecord 的硬上限；先给 60s 播着，到点自动结束
            args.Append(" shell screenrecord --display-id=").Append(displayId)
                .Append(" --bit-rate=6000000 --time-limit=60 ").Append(dev);
            psi.Arguments = args.ToString();

            try
            {
                Process p = new Process();
                p.StartInfo = psi;
                p.Start();
                CAST_REC = p;
                CAST_REC_SLOT = slot;
                CAST_REC_FILE = dev;
                CAST_REC_T0 = DateTime.Now;
                App.Trace("cast: 开始录制 slot=" + slot + " display=" + displayId);
                return true;
            }
            catch (Exception ex)
            {
                err = "录制启动失败：" + ex.Message;
                return false;
            }
        }

        internal static void CastRecordStop(int slot)
        {
            string f = "";
            string e = "";
            CastRecordStop(slot, out f, out e);
        }

        // 停止录制：杀掉 adb shell（screenrecord 随之结束），再把文件拉回来
        internal static bool CastRecordStop(int slot, out string outFile, out string err)
        {
            outFile = "";
            err = "";
            if (CAST_REC == null || CAST_REC_SLOT != slot) return false;

            try
            {
                try { CAST_REC.Kill(); } catch { }
                try { CAST_REC.WaitForExit(3000); } catch { }
                // screenrecord 被 SIGKILL 时 moov 可能没写完，给 1 秒让它落盘
                Thread.Sleep(300);

                string dir = OutDir("rec");
                string local = Path.Combine(dir, "cast_" + slot + "_" + DateTime.Now.ToString("HHmmss") + ".mp4");

                List<string> argv = new List<string>();
                argv.Add("pull");
                argv.Add(CAST_REC_FILE);
                argv.Add(local);

                string combined = "";
                int rc = AdbCallStream(argv, out combined);

                string rmOut = "";
                string rmErr = "";
                AdbCall(new List<string> { "shell", "rm -f " + ShQuote(CAST_REC_FILE) }, out rmOut, out rmErr);

                if (rc == 0 && File.Exists(local) && new FileInfo(local).Length > 1024)
                {
                    outFile = local;
                    return true;
                }
                err = "录制文件为空（该屏可能不支持 screenrecord）";
                return false;
            }
            catch (Exception ex)
            {
                err = "停止录制失败：" + ex.Message;
                return false;
            }
            finally
            {
                CAST_REC = null;
                CAST_REC_SLOT = -1;
            }
        }
    }
}
