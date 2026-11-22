// ============================================================================
//  Diag.cs - 环境诊断：本机信息采集（2026-11-22）
// ----------------------------------------------------------------------------
//  为什么单独一个文件：
//    这套采集只用 WMI + .NET 基础 API，和 adb 无关，也不依赖界面。
//    放在 GuiWeb.cs 里会让那个文件继续膨胀（已经 3000+ 行）。
//
//  用户要的字段（去掉了他明确不要的三项）：
//    要：CPU / GPU 之外的硬件 / 内存(要区分 DDR4 DDR5) / Windows 版本 /
//        分辨率 + 缩放 / 存储 / 设备名 / 系统类型
//    不要：磁盘健康、温度、GPU 占用（都已按需求移除）
//
//  坑位记录：
//    1) WMI 在某些精简系统 / 权限受限环境会抛 ManagementException 或干脆卡住。
//       所以每条查询都独立 try-catch，单条失败只让那一行显示"读取失败"，
//       绝不让整页崩掉。
//    2) SMBIOSMemoryType 是数字编码，不是字符串。DDR4=26, DDR5=34, DDR3=24。
//    3) 屏幕"英寸"要靠 EDID 解析，多显示器还有歧义 —— 用户已确认不做，
//       只显示分辨率 + 缩放比例。
// ============================================================================
using System;
using System.Collections.Generic;
using System.Drawing;          // Graphics.FromHwnd：读当前屏幕 DPI（算缩放比例）
using System.IO;
using System.Management;       // WMI：CPU / SMBIOS 内存代数 / OS Build
using System.Text;
using System.Windows.Forms;
using AdbLogExport.Gui;        // GuiEntry.LogDir() 在 AdbLogExport.Gui 命名空间下

namespace AdbLogExport
{
    internal static class Diag
    {
        // 一行诊断数据：标签 / 值 / 级别（级别用于前端上色："" | ok | warn | bad）
        internal sealed class Row
        {
            internal string K;
            internal string V;
            internal string Lv;
            internal Row(string k, string v) { K = k; V = v; Lv = ""; }
            internal Row(string k, string v, string lv) { K = k; V = v; Lv = lv; }
        }

        // ------------------------------------------------------------------
        //  本机信息
        // ------------------------------------------------------------------
        internal static List<Row> CollectLocal()
        {
            var list = new List<Row>();

            // ---- CPU ----
            try
            {
                using (var q = new ManagementObjectSearcher(
                    "SELECT Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed FROM Win32_Processor"))
                {
                    foreach (ManagementObject o in q.Get())
                    {
                        string name = S(o, "Name");
                        string cores = S(o, "NumberOfCores");
                        string threads = S(o, "NumberOfLogicalProcessors");
                        string mhz = S(o, "MaxClockSpeed");
                        string v = name;
                        if (!string.IsNullOrEmpty(cores))
                            v += "  " + cores + " 核";
                        if (!string.IsNullOrEmpty(threads))
                            v += " / " + threads + " 线程";
                        if (!string.IsNullOrEmpty(mhz))
                        {
                            int m;
                            if (int.TryParse(mhz, out m))
                                v += "  @" + (m / 1000.0).ToString("0.0") + "GHz";
                        }
                        list.Add(new Row("CPU", v.Trim()));
                        break;   // 多路服务器也只显示第一路，够用
                    }
                }
            }
            catch (Exception ex) { list.Add(new Row("CPU", "读取失败：" + Brief(ex), "warn")); }

            // ---- 内存总量 + DDR 代数 ----
            try
            {
                long totalBytes = 0;
                var types = new List<string>();
                var speeds = new List<string>();
                using (var q = new ManagementObjectSearcher(
                    "SELECT Capacity,SMBIOSMemoryType,Speed FROM Win32_PhysicalMemory"))
                {
                    foreach (ManagementObject o in q.Get())
                    {
                        string cap = S(o, "Capacity");
                        long b;
                        if (long.TryParse(cap, out b)) totalBytes += b;

                        string t = MemoryTypeName(S(o, "SMBIOSMemoryType"));
                        if (!string.IsNullOrEmpty(t) && !types.Contains(t)) types.Add(t);

                        string sp = S(o, "Speed");
                        if (!string.IsNullOrEmpty(sp) && !speeds.Contains(sp)) speeds.Add(sp);
                    }
                }
                if (totalBytes > 0)
                {
                    string v = FmtGB(totalBytes);
                    if (types.Count > 0) v += "  " + string.Join("+", types.ToArray());
                    if (speeds.Count > 0)
                    {
                        var mhz = new List<string>();
                        for (int i = 0; i < speeds.Count; i++)
                        {
                            int sp;
                            if (int.TryParse(speeds[i], out sp) && sp > 0)
                                mhz.Add(sp.ToString());
                        }
                        if (mhz.Count > 0) v += "-" + string.Join("/", mhz.ToArray()) + "MHz";
                    }
                    list.Add(new Row("内存", v));
                }
                else list.Add(new Row("内存", "读取失败", "warn"));
            }
            catch (Exception ex) { list.Add(new Row("内存", "读取失败：" + Brief(ex), "warn")); }

            // ---- 操作系统 ----
            try
            {
                string caption = "", version = "", build = "";
                using (var q = new ManagementObjectSearcher(
                    "SELECT Caption,Version,BuildNumber FROM Win32_OperatingSystem"))
                {
                    foreach (ManagementObject o in q.Get())
                    {
                        caption = S(o, "Caption");
                        version = S(o, "Version");
                        build = S(o, "BuildNumber");
                        break;
                    }
                }
                // Caption 形如 "Microsoft Windows 11 专业版"
                string cap = caption.Replace("Microsoft ", "").Trim();
                string v = cap;
                if (!string.IsNullOrEmpty(build)) v += "  (Build " + build + ")";
                list.Add(new Row("Windows", v.Trim()));
                if (!string.IsNullOrEmpty(version))
                    list.Add(new Row("系统版本号", version));
            }
            catch (Exception ex) { list.Add(new Row("Windows", "读取失败：" + Brief(ex), "warn")); }

            // ---- 系统类型 / 设备名 ----
            try
            {
                bool is64 = Environment.Is64BitOperatingSystem;
                list.Add(new Row("系统类型", is64 ? "64 位" : "32 位"));
            }
            catch { list.Add(new Row("系统类型", "未知")); }

            try { list.Add(new Row("设备名称", Environment.MachineName)); }
            catch { list.Add(new Row("设备名称", "未知")); }

            // ---- 分辨率 + 缩放（用户确认：不做英寸）----
            try
            {
                Screen sc = Screen.PrimaryScreen;
                if (sc != null)
                {
                    int w = sc.Bounds.Width, h = sc.Bounds.Height;
                    string v = w + " × " + h;

                    // 缩放：进程已声明 Per-Monitor V2，因此 DpiX 就是当前屏的真实 DPI。
                    try
                    {
                        using (var g = Graphics.FromHwnd(IntPtr.Zero))
                        {
                            float dpi = g.DpiX;
                            if (dpi > 0)
                            {
                                int pct = (int)Math.Round(dpi / 96.0 * 100);
                                v += "  @" + pct + "% 缩放";
                            }
                        }
                    }
                    catch { }
                    list.Add(new Row("屏幕分辨率", v));

                    if (Screen.AllScreens.Length > 1)
                        list.Add(new Row("显示器数量", Screen.AllScreens.Length + " 个"));
                }
                else list.Add(new Row("屏幕分辨率", "读取失败", "warn"));
            }
            catch (Exception ex) { list.Add(new Row("屏幕分辨率", "读取失败：" + Brief(ex), "warn")); }

            // ---- 存储 ----
            try
            {
                var drives = DriveInfo.GetDrives();
                int n = 0;
                for (int i = 0; i < drives.Length; i++)
                {
                    DriveInfo d = drives[i];
                    try
                    {
                        if (d.DriveType != DriveType.Fixed || !d.IsReady) continue;
                        long total = d.TotalSize;
                        long free = d.TotalFreeSpace;
                        string v = FmtGB(total) + "（剩余 " + FmtGB(free) + "）";
                        string lv = "";
                        // 剩余不足 10% 标黄，不足 5% 标红 —— 磁盘满会让 adb 拉文件失败
                        if (total > 0)
                        {
                            double ratio = (double)free / (double)total;
                            if (ratio < 0.05) lv = "bad";
                            else if (ratio < 0.10) lv = "warn";
                        }
                        list.Add(new Row("存储 " + d.Name.TrimEnd('\\'), v, lv));
                        n++;
                        if (n >= 4) break;   // 最多列 4 个盘，再多就淹没界面了
                    }
                    catch { }
                }
                if (n == 0) list.Add(new Row("存储", "未找到固定磁盘", "warn"));
            }
            catch (Exception ex) { list.Add(new Row("存储", "读取失败：" + Brief(ex), "warn")); }

            // ---- 运行时 ----
            try { list.Add(new Row(".NET 版本", Environment.Version.ToString())); }
            catch { }

            // ---- 进程数（工具侧观察系统是否卡顿）----
            try
            {
                int pc = 0;
                try { pc = System.Diagnostics.Process.GetProcesses().Length; } catch { }
                if (pc > 0) list.Add(new Row("进程数", pc + " 个"));
            }
            catch { }

            // ---- 本工具日志目录大小 ----
            try
            {
                string dir = GuiEntry.LogDir();
                if (!string.IsNullOrEmpty(dir) && Directory.Exists(dir))
                {
                    long bytes = DirSize(dir);
                    int files = DirFileCount(dir);
                    list.Add(new Row("日志目录", FmtSize(bytes) + "（" + files + " 个文件）"));
                }
            }
            catch { }

            // ---- 工具自身版本（现场排查"改了没生效"最有效的一条）----
            try
            {
                string exe = Application.ExecutablePath;
                if (File.Exists(exe))
                {
                    DateTime t = File.GetLastWriteTime(exe);
                    list.Add(new Row("工具版本", t.ToString("yyyy-MM-dd HH:mm")));
                }
            }
            catch { }

            return list;
        }

        // ------------------------------------------------------------------
        //  本工具自身资源占用（用户要求：只在点「开始采样」时才测）
        // ------------------------------------------------------------------
        //
        //  CPU 占用必须用「两次采样的差值」算，不能只看一次：
        //    cpu% = Δ(进程 CPU 时间) / Δ(墙钟时间) / 逻辑核数 × 100
        //  所以这里用静态字段记住上一次的时间点。第一次调用返回 -1
        //  （还没有基准），页面显示「测量中…」。
        //
        //  为什么要除以核数：Process.TotalProcessorTime 是所有线程在**所有核**上
        //  的累计，不除核数在多核机器上会算出 800% 这种数字。
        private static DateTime _lastWall = DateTime.MinValue;
        private static TimeSpan _lastCpu = TimeSpan.Zero;

        internal static void ResetSample()
        {
            _lastWall = DateTime.MinValue;
            _lastCpu = TimeSpan.Zero;
        }

        // 返回 "cpu百分比|内存MB"，cpu 为 -1 表示还没有基准
        internal static string SampleSelf()
        {
            try
            {
                using (var p = System.Diagnostics.Process.GetCurrentProcess())
                {
                    DateTime now = DateTime.UtcNow;
                    TimeSpan cpu = p.TotalProcessorTime;
                    long mem = p.WorkingSet64;

                    double pct = -1;
                    if (_lastWall != DateTime.MinValue)
                    {
                        double wallMs = (now - _lastWall).TotalMilliseconds;
                        double cpuMs = (cpu - _lastCpu).TotalMilliseconds;
                        if (wallMs > 50)
                        {
                            int cores = Environment.ProcessorCount;
                            if (cores < 1) cores = 1;
                            pct = cpuMs / wallMs / cores * 100.0;
                            if (pct < 0) pct = 0;
                            if (pct > 100) pct = 100;
                        }
                    }
                    _lastWall = now;
                    _lastCpu = cpu;

                    string cpuText = pct < 0 ? "-1" : pct.ToString("0.0");
                    return cpuText + "|" + (mem / 1024 / 1024);
                }
            }
            catch { return "-1|0"; }
        }

        // ------------------------------------------------------------------
        //  辅助
        // ------------------------------------------------------------------

        // WMI 字段安全取值：属性不存在或为 null 都返回空串
        private static string S(ManagementObject o, string prop)
        {
            try
            {
                object v = o[prop];
                return v == null ? "" : v.ToString().Trim();
            }
            catch { return ""; }
        }

        // SMBIOSMemoryType 是数字，转成人能看懂的 DDR 代数。
        // 编码来源：SMBIOS spec 7.18.2 Memory Type
        private static string MemoryTypeName(string code)
        {
            if (string.IsNullOrEmpty(code)) return "";
            int c;
            if (!int.TryParse(code, out c)) return "";
            switch (c)
            {
                case 20: return "DDR";
                case 21: return "DDR2";
                case 22: return "DDR2 FB-DIMM";
                case 24: return "DDR3";
                case 26: return "DDR4";
                case 27: return "LPDDR";
                case 28: return "LPDDR2";
                case 29: return "LPDDR3";
                case 30: return "LPDDR4";
                case 34: return "DDR5";
                case 35: return "LPDDR5";
                default: return "";   // 未知就别乱猜，宁可不显示
            }
        }

        private static string FmtGB(long bytes)
        {
            if (bytes <= 0) return "0";
            double gb = bytes / 1024.0 / 1024.0 / 1024.0;
            // 32GB 这种整数不显示小数；19.5GB 这种保留一位
            if (Math.Abs(gb - Math.Round(gb)) < 0.05) return ((long)Math.Round(gb)) + " GB";
            return gb.ToString("0.#") + " GB";
        }

        private static string FmtSize(long bytes)
        {
            if (bytes < 1024) return bytes + " B";
            if (bytes < 1024 * 1024) return (bytes / 1024.0).ToString("0.#") + " KB";
            if (bytes < 1024L * 1024 * 1024) return (bytes / 1024.0 / 1024.0).ToString("0.#") + " MB";
            return (bytes / 1024.0 / 1024.0 / 1024.0).ToString("0.##") + " GB";
        }

        // 目录体积递归统计。刻意不用 LINQ —— 大目录下 EnumerateFiles 递归
        // 遇到无权限子目录会抛异常中断统计，这里逐层 try 跳过。
        private static long DirSize(string dir)
        {
            long total = 0;
            try
            {
                foreach (string f in Directory.GetFiles(dir))
                {
                    try { total += new FileInfo(f).Length; } catch { }
                }
                foreach (string d in Directory.GetDirectories(dir))
                {
                    try { total += DirSize(d); } catch { }
                }
            }
            catch { }
            return total;
        }

        private static int DirFileCount(string dir)
        {
            int n = 0;
            try
            {
                n += Directory.GetFiles(dir).Length;
                foreach (string d in Directory.GetDirectories(dir))
                {
                    try { n += DirFileCount(d); } catch { }
                }
            }
            catch { }
            return n;
        }

        // 异常摘要：只留消息首句，避免 WMI 的长篇堆栈塞满界面
        private static string Brief(Exception ex)
        {
            string m = ex.Message ?? "";
            int i = m.IndexOf('\n');
            if (i > 0) m = m.Substring(0, i);
            if (m.Length > 60) m = m.Substring(0, 60) + "…";
            return m;
        }
    }
}
