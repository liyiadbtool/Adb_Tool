// ============================================================================
//  Top5.cs - 本机 TOP5 进程采集（2026-11-22 第 18 批 D3）
// ----------------------------------------------------------------------------
//  为什么单独一个文件（而不是放在 Diag.cs）：
//    Diag.cs 依赖 System.Windows.Forms 和 AdbLogExport.Gui（取日志目录），
//    而 CLI 版 build.bat 不链接 WinForms —— 放在那里 CLI 就编不过，
//    而 :top5 命令是 CLI 也要用的。
//    这里只用 WMI + Process/Environment，两边都能编。
// ============================================================================
using System;
using System.Collections.Generic;
using System.Text;

namespace AdbLogExport
{
    internal static class Top5
    {
        // ====================================================================
        //  2026-11-22（第 18 批 D3）：本机 TOP5 进程 + 剩余 CPU/内存
        // --------------------------------------------------------------------
        //  和 SampleSelf() 的区别：那个只看本工具自己，这里要看**全机**。
        //
        //  取法：
        //    · 全机 CPU%  → WMI Win32_PerfFormattedData_PerfOS_Processor (_Total)
        //    · 进程 CPU%  → WMI Win32_PerfFormattedData_PerfProc_Process
        //    · 进程内存   → Process.WorkingSet64（比 WMI 准，且快）
        //    · 剩余内存   → WMI Win32_OperatingSystem.FreePhysicalMemory
        //
        //  ★ 一个必须处理的坑：WMI 的 PercentProcessorTime 是"占**单核**百分比"，
        //    8 核机器上一个吃满 2 核的进程会显示 200。要除以核数换成"占全机"。
        //
        //  WMI 查询 200~500ms，调用方必须放后台线程（见 GuiWeb 的 top5 分支）。
        // ====================================================================
        internal static string HostTop5()
        {
            try
            {
                int cores = Environment.ProcessorCount;
                if (cores < 1) cores = 1;

                // ---- 进程内存 top5（GetProcesses 比 WMI 快且准）----
                var procs = System.Diagnostics.Process.GetProcesses();
                var memList = new List<object[]>();
                var cpuMap = new Dictionary<string, double>(StringComparer.OrdinalIgnoreCase);

                for (int i = 0; i < procs.Length; i++)
                {
                    try
                    {
                        var pr = procs[i];
                        long ws = 0;
                        try { ws = pr.WorkingSet64; } catch { }
                        if (ws > 0)
                            memList.Add(new object[] { pr.ProcessName, ws / 1048576.0 });
                    }
                    catch { }
                    finally
                    {
                        try { procs[i].Dispose(); } catch { }
                    }
                }
                memList.Sort(delegate(object[] a, object[] b)
                {
                    return ((double)b[1]).CompareTo((double)a[1]);
                });

                // ---- 进程 CPU top5（WMI）----
                double totalCpu = -1;
                try
                {
                    using (var searcher = new System.Management.ManagementObjectSearcher(
                        "SELECT Name, PercentProcessorTime FROM Win32_PerfFormattedData_PerfProc_Process"))
                    {
                        foreach (System.Management.ManagementObject mo in searcher.Get())
                        {
                            try
                            {
                                string nm = Convert.ToString(mo["Name"]);
                                if (string.IsNullOrEmpty(nm)) continue;
                                if (nm == "Idle" || nm == "_Total") continue;
                                object v = mo["PercentProcessorTime"];
                                if (v == null) continue;
                                // 去掉 "#1" "#2" 这种同名前缀（多实例进程）
                                string clean = nm;
                                int hash = clean.IndexOf('#');
                                if (hash > 0) clean = clean.Substring(0, hash);
                                double pct = Convert.ToDouble(v) / cores;
                                if (cpuMap.ContainsKey(clean)) cpuMap[clean] += pct;
                                else cpuMap[clean] = pct;
                            }
                            catch { }
                        }
                    }
                }
                catch { }

                // 全机占用：另查 OS_Processor 的 _Total
                try
                {
                    using (var searcher = new System.Management.ManagementObjectSearcher(
                        "SELECT PercentProcessorTime FROM Win32_PerfFormattedData_PerfOS_Processor WHERE Name='_Total'"))
                    {
                        foreach (System.Management.ManagementObject mo in searcher.Get())
                        {
                            object v = mo["PercentProcessorTime"];
                            if (v != null) totalCpu = Convert.ToDouble(v);
                        }
                    }
                }
                catch { }

                // 剩余内存
                double freeGB = -1;
                try
                {
                    using (var searcher = new System.Management.ManagementObjectSearcher(
                        "SELECT FreePhysicalMemory FROM Win32_OperatingSystem"))
                    {
                        foreach (System.Management.ManagementObject mo in searcher.Get())
                        {
                            object v = mo["FreePhysicalMemory"];
                            if (v != null) freeGB = Convert.ToDouble(v) / 1048576.0;   // kB → GB
                        }
                    }
                }
                catch { }

                // CPU 榜排序
                var cpuList = new List<KeyValuePair<string, double>>(cpuMap);
                cpuList.Sort(delegate(KeyValuePair<string, double> a, KeyValuePair<string, double> b)
                {
                    return b.Value.CompareTo(a.Value);
                });

                StringBuilder sb = new StringBuilder();
                sb.Append("{\"ok\":true");
                sb.Append(",\"cores\":").Append(cores);

                /* ★ 2026-11-23（第 22 批）：顺带返回**本应用自身**的 CPU/内存。
                   以前这部分只走 :diagsample（采样中才发），不点采样就永远显示 --。
                   用户问"为什么不显示当前应用占比的数据"——就是这个原因。
                   这里用"进程启动至今的平均占用"单次即可算出：
                     平均CPU% = 累计CPU时间 / (运行时长 × 核数) × 100
                   采样进行时页面会再用 diagsample 的瞬时值覆盖它，两者不冲突。 */
                try
                {
                    var self = System.Diagnostics.Process.GetCurrentProcess();
                    double cpuMs = self.TotalProcessorTime.TotalMilliseconds;
                    double lifeMs = (DateTime.Now - self.StartTime).TotalMilliseconds;
                    if (lifeMs < 1) lifeMs = 1;
                    double avgPct = cpuMs / (lifeMs * cores) * 100.0;
                    if (avgPct < 0) avgPct = 0;
                    if (avgPct > 100) avgPct = 100;
                    sb.Append(",\"selfCpu\":").Append(F1(avgPct));
                    sb.Append(",\"selfMem\":").Append(F1(self.WorkingSet64 / 1048576.0));
                    try { self.Dispose(); } catch { }
                }
                catch { }
                sb.Append(",\"totalCpu\":").Append(totalCpu < 0 ? "null" : F1(totalCpu));
                sb.Append(",\"freeCpu\":").Append(totalCpu < 0 ? "null" : F1(100.0 - totalCpu));
                sb.Append(",\"freeMem\":").Append(freeGB < 0 ? "null" : F1(freeGB));

                sb.Append(",\"cpu\":[");
                int nc = 0;
                for (int i = 0; i < cpuList.Count && nc < 5; i++)
                {
                    if (cpuList[i].Value < 0.05) continue;      // 0.05% 以下当作没占
                    if (nc > 0) sb.Append(',');
                    sb.Append("{\"n\":").Append(Json(cpuList[i].Key))
                      .Append(",\"v\":").Append(F1(cpuList[i].Value)).Append('}');
                    nc++;
                }
                sb.Append("],\"mem\":[");

                int nm2 = 0;
                for (int i = 0; i < memList.Count && nm2 < 5; i++)
                {
                    if (nm2 > 0) sb.Append(',');
                    sb.Append("{\"n\":").Append(Json(Convert.ToString(memList[i][0])))
                      .Append(",\"v\":").Append(F1((double)memList[i][1])).Append('}');
                    nm2++;
                }
                sb.Append("]}");
                return sb.ToString();
            }
            catch (Exception ex)
            {
                return "{\"ok\":false,\"err\":" + Json(Brief(ex)) + "}";
            }
        }

        // 极简 JSON 字符串转义（Diag.cs 不是 GuiWeb，拿不到那边的 Json()）
        private static string Json(string v)
        {
            if (v == null) return "\"\"";
            StringBuilder b = new StringBuilder("\"");
            for (int i = 0; i < v.Length; i++)
            {
                char c = v[i];
                if (c == '"') b.Append("\\\"");
                else if (c == '\\') b.Append("\\\\");
                else if (c == '\n') b.Append("\\n");
                else if (c == '\r') b.Append("\\r");
                else if (c == '\t') b.Append("\\t");
                else if (c < ' ') b.Append(' ');
                else b.Append(c);
            }
            b.Append('"');
            return b.ToString();
        }

        // 异常摘要：只留首句（Diag.cs 里那个是私有的，这里自带一份）
        private static string Brief(Exception ex)
        {
            if (ex == null) return "未知";
            string m = ex.Message ?? "";
            int i = m.IndexOf('\n');
            if (i > 0) m = m.Substring(0, i);
            if (m.Length > 60) m = m.Substring(0, 60) + "…";
            return m;
        }

        // 保留 1 位小数的数字串（不带引号，直接进 JSON）
        private static string F1(double v)
        {
            if (double.IsNaN(v) || double.IsInfinity(v)) v = 0;
            return v.ToString("0.0", System.Globalization.CultureInfo.InvariantCulture);
        }
    }
}
