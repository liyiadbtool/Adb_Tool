// ============================================================================
//  PkgVer.cs — 批量版本查询
//
//  场景：刷机 / 升级后，一次确认多个关键包的版本是否符合预期。
//
//  配置（adb_log_export.ini）：
//      version_pkgs=com.a=座舱,com.b,com.c=语音
//      ↑ 逗号分隔；可写 包名=别名，别名显示在结果里
//
//  用法：
//      ver               查配置里的全部包
//      ver com.a com.b   只查指定包（不需要先配置）
//
//  性能要点：N 个包**只发一次 adb 调用**。
//  用设备端 for 循环 + echo 分段标记，一次 dumpsys 全部包，
//  比起逐个 dumpsys（N 次 adb 往返）快 N 倍。
// ============================================================================
using System;
using System.Collections.Generic;
using System.Text;

namespace AdbLogExport
{
    internal static partial class App
    {
        // 一个待查的包
        internal class VerPkg
        {
            internal string Pkg = "";
            internal string Alias = "";
        }

        // 一行查询结果
        internal class VerRow
        {
            internal string Alias = "";
            internal string Pkg = "";
            internal string VerName = "";
            internal string VerCode = "";
            internal string Update = "";
            internal string Path = "";
            internal bool Installed = false;
            // 进程号（可能多个，空格分隔）。取不到就是空串 —— 界面/表格据此决定不显示。
            internal string Pid = "";
        }

        // 一个 dumpsys 里的 Package [xxx] 块
        internal class VerEntry
        {
            internal string Pkg = "";
            internal string VerName = "";
            internal string VerCode = "";
            internal string Update = "";
            internal string Path = "";
        }

        private static readonly List<VerPkg> VER_PKGS = new List<VerPkg>();

        // ==================== 配置解析 ====================
        // 格式： com.a=别名,com.b,com.c=别名
        // 支持 ini 里写多行，累加（不会覆盖前面的）
        internal static void LoadVerPkgs(string v)
        {
            if (string.IsNullOrEmpty(v)) return;

            string[] parts = v.Split(',');
            for (int i = 0; i < parts.Length; i++)
            {
                string s = parts[i].Trim();
                if (s.Length == 0) continue;

                VerPkg p = new VerPkg();
                int eq = s.IndexOf('=');
                if (eq > 0)
                {
                    p.Pkg = s.Substring(0, eq).Trim();
                    p.Alias = s.Substring(eq + 1).Trim();
                }
                else
                {
                    p.Pkg = s;
                }

                if (p.Pkg.Length == 0) continue;

                // 去重
                bool dup = false;
                for (int k = 0; k < VER_PKGS.Count; k++)
                {
                    if (string.Equals(VER_PKGS[k].Pkg, p.Pkg, StringComparison.OrdinalIgnoreCase)) { dup = true; break; }
                }
                if (!dup) VER_PKGS.Add(p);
            }
        }

        // 供 ApkList 首次迁移用：返回配置里「包名 + 别名」的副本。
        // 用副本而不是直接暴露 VER_PKGS —— 迁移过程会做去重/校验，
        // 一旦它顺手改了原表，:pkg ver 的结果就会跟着变。
        internal static List<VerPkg> VerPkgsSnapshot()
        {
            List<VerPkg> copy = new List<VerPkg>();
            for (int i = 0; i < VER_PKGS.Count; i++)
            {
                VerPkg p = new VerPkg();
                p.Pkg = VER_PKGS[i].Pkg;
                p.Alias = VER_PKGS[i].Alias;
                copy.Add(p);
            }
            return copy;
        }

        // ==================== 执行 ====================
        private static void DoVersions(string argRaw)
        {
            DoVersions(argRaw, false);
        }

        // quiet=true 时不打 "→ ver ..."（now 已经打过自己的回显了）
        private static void DoVersions(string argRaw, bool quiet)
        {
            if (OFFLINE)
            {
                Warn("设备未连接，无法查询版本");
                Hint("输入 r 重连");
                return;
            }

            // 1. 确定目标包
            List<VerPkg> targets = new List<VerPkg>();
            string a = (argRaw == null) ? "" : argRaw.Trim();

            if (a.Length > 0)
            {
                // ver com.a com.b：只查指定的，别名从配置里找
                List<string> args = SplitArgs(a);
                for (int i = 0; i < args.Count; i++)
                {
                    string pkg = args[i].Trim();
                    if (pkg.Length == 0) continue;

                    VerPkg p = new VerPkg();
                    p.Pkg = pkg;

                    for (int k = 0; k < VER_PKGS.Count; k++)
                    {
                        if (string.Equals(VER_PKGS[k].Pkg, pkg, StringComparison.OrdinalIgnoreCase))
                        {
                            p.Alias = VER_PKGS[k].Alias;
                            break;
                        }
                    }
                    targets.Add(p);
                }
            }
            else
            {
                for (int i = 0; i < VER_PKGS.Count; i++) targets.Add(VER_PKGS[i]);
            }

            if (targets.Count == 0)
            {
                Fail("没有要查询的包");
                Hint("在 ini 里配置 version_pkgs=包名1=别名1,包名2  然后输入 ver");
                Hint("或直接指定：ver com.xxx.yyy");
                return;
            }

            // 2~3. 查询 + 解析（抽到 QueryVersionRows：GUI 的 APK 管理页要用同一套口径）
            List<string> notes = new List<string>();
            List<VerRow> rows = QueryVersionRows(targets, out notes);
            if (rows == null) return;      // 内部已经报过错

            // 4. 渲染：单个包给"键值块"（能放下完整路径），多个包用表格
            if (rows.Count == 1)
            {
                RenderPkgDetail(rows[0]);
            }
            else
            {
                RenderVerTable(rows);
            }

            // 5. 多版本 / 近似包的说明（不塞进表格，避免把列撑歪）
            if (notes.Count > 0)
            {
                for (int i = 0; i < notes.Count && i < 6; i++) Hint(notes[i]);
            }
            CMD_OK = true;
        }

        // 查询一组包的版本，返回结构化结果（**不打印**任何东西）。
        //
        // 为什么抽出来：CLI 的 ver / :pkg ver 要把结果排版成表格，GUI 的
        // APK 管理页要把结果塞进自己的结果区（名称/包名/版本/路径四字段换行）。
        // 排版可以有两套，取数和解析必须只有一套，否则两边口径迟早会漂。
        //
        // 返回 null = 硬失败（设备不在线 / 设备完全无返回），调用方不要再渲染空表。
        internal static List<VerRow> QueryVersionRows(List<VerPkg> targets, out List<string> notes)
        {
            notes = new List<string>();
            if (targets == null || targets.Count == 0) return null;

            if (OFFLINE)
            {
                Warn("设备未连接，无法查询版本");
                Hint("输入 r 重连");
                return null;
            }

            // 组一条命令，一次 adb 调用查全部：
            // echo '##PKG:xxx' 作为分段标记，后面跟着该包的版本行
            StringBuilder cmd = new StringBuilder();
            for (int i = 0; i < targets.Count; i++)
            {
                cmd.Append("echo '##PKG:");
                cmd.Append(targets[i].Pkg);
                cmd.Append("'; ");
                cmd.Append("dumpsys package '");
                cmd.Append(targets[i].Pkg);
                // 连 Package [名字] 头一起取回来 —— 没有它就分不清"这段版本属于哪个包"
                cmd.Append("' 2>/dev/null | grep -E 'Package \\[|versionName=|versionCode=|lastUpdateTime=|codePath='; ");
            }

            string o = "";
            string e = "";
            int rc = ShellCall(CUR, cmd.ToString(), out o, out e);
            string outStr = o + "\n" + e;

            if (rc != 0 && outStr.Trim().Length == 0)
            {
                Fail("查询失败：设备无返回");
                Hint("输入 r 刷新后重试");
                return null;
            }

            // 解析：先按 Package [名字] 分段，再逐段取版本
            //
            // 为什么必须分段：dumpsys package <pkg> 是**子串匹配**，而且同一个包
            // 可能在 "Packages:" 与 "Hidden system packages:" 里各出现一次。
            // 不分段就会把两段的信息合并成一行，出现
            // "版本名是 A、版本码是 B" 这种自相矛盾的错行。
            List<VerEntry> entries = ParsePkgEntries(outStr);

            List<VerRow> rows = new List<VerRow>();
            for (int i = 0; i < targets.Count; i++)
            {
                string want = targets[i].Pkg;

                VerRow r = new VerRow();
                r.Pkg = want;
                r.Alias = (targets[i].Alias.Length > 0) ? targets[i].Alias : "";

                VerEntry pick = null;
                int extra = 0;

                for (int k = 0; k < entries.Count; k++)
                {
                    VerEntry en = entries[k];
                    if (!string.Equals(en.Pkg, want, StringComparison.Ordinal)) continue;

                    if (pick == null) { pick = en; continue; }

                    // 同名但内容不同 => 确实是"另一个版本"（隐藏系统包 / 多用户等）
                    if (!string.Equals(en.VerName, pick.VerName, StringComparison.Ordinal) ||
                        !string.Equals(en.VerCode, pick.VerCode, StringComparison.Ordinal))
                    {
                        extra++;
                        if (extra <= 3)
                        {
                            notes.Add(want + "  另有记录：" + DescribeEntry(en));
                        }
                    }
                }

                if (pick != null)
                {
                    r.VerName = pick.VerName;
                    r.VerCode = pick.VerCode;
                    r.Update = pick.Update;
                    r.Path = pick.Path;
                    r.Installed = (pick.VerName.Length > 0 || pick.VerCode.Length > 0);
                }

                if (!r.Installed)
                {
                    string near = NearMatches(entries, want);
                    if (near.Length > 0)
                        notes.Add("没有完全匹配的 " + want + "；dumpsys 返回的是：" + near);
                }
                else if (extra > 3)
                {
                    notes.Add(want + "  另有 " + extra + " 条记录（只显示前 3 条）");
                }

                rows.Add(r);
            }

            CMD_OK = true;
            AttachPids(rows);
            return rows;
        }

        // 给每行挂上进程号（一次 ps 全部搞定，别每个包发一次 adb）
        internal static void AttachPids(List<VerRow> rows)
        {
            if (rows == null || rows.Count == 0) return;

            string o = "";
            string e = "";
            ShellCall(CUR, "ps -A -o PID,NAME 2>/dev/null", out o, out e);
            string txt = o + "\n" + e;
            if (txt.Trim().Length == 0 || txt.IndexOf("PID", StringComparison.OrdinalIgnoreCase) < 0)
            {
                // 老 ROM 不支持 -o：退回完整 ps，名字在最后一列
                ShellCall(CUR, "ps -A 2>/dev/null", out o, out e);
                txt = o + "\n" + e;
            }

            if (VERBOSE)
            {
                // 排查"没有 pid"用：把 ps 的前几行打出来，看格式是否符合预期
                string[] dbg = txt.Split('\n');
                int shown = 0;
                for (int i = 0; i < dbg.Length && shown < 5; i++)
                {
                    if (dbg[i].Trim().Length == 0) continue;
                    Console.WriteLine("  [ps] " + dbg[i].Trim());
                    shown++;
                }
            }

            Dictionary<string, List<string>> map = new Dictionary<string, List<string>>(StringComparer.Ordinal);
            string[] lines = txt.Split('\n');
            for (int i = 0; i < lines.Length; i++)
            {
                string line = lines[i].Trim();
                if (line.Length == 0) continue;
                if (line.StartsWith("PID", StringComparison.OrdinalIgnoreCase)) continue;

                string pid, name;
                if (!SplitPsLine(line, out pid, out name)) continue;
                if (name.Length == 0) continue;

                if (!map.ContainsKey(name)) map[name] = new List<string>();
                map[name].Add(pid);
            }

            for (int r = 0; r < rows.Count; r++)
            {
                VerRow row = rows[r];
                if (row.Pkg.Length == 0) continue;
                List<string> pids = new List<string>();

                foreach (KeyValuePair<string, List<string>> kv in map)
                {
                    if (kv.Key == row.Pkg || kv.Key.StartsWith(row.Pkg + ":", StringComparison.Ordinal))
                    {
                        for (int k = 0; k < kv.Value.Count; k++) pids.Add(kv.Value[k]);
                    }
                }
                if (pids.Count > 0) row.Pid = string.Join(" ", pids.ToArray());
            }

            // 兜底：ps 的 NAME 被截断或格式不同的 ROM 上，上面会一个都匹配不到。
            // 用 pidof 再补一遍（一次 shell 循环搞定所有包，别一个包一次 adb）。
            List<VerRow> missing = new List<VerRow>();
            for (int r = 0; r < rows.Count; r++)
                if (rows[r].Pid.Length == 0 && rows[r].Pkg.Length > 0) missing.Add(rows[r]);
            if (missing.Count == 0) return;

            StringBuilder cmd = new StringBuilder();
            for (int i = 0; i < missing.Count; i++)
                cmd.Append("echo \"@").Append(missing[i].Pkg).Append(" $(pidof ")
                   .Append(missing[i].Pkg).Append(" 2>/dev/null)\"; ");

            string po = "";
            string pe = "";
            ShellCall(CUR, cmd.ToString(), out po, out pe);
            string[] pl = (po + "\n" + pe).Split('\n');
            for (int i = 0; i < pl.Length; i++)
            {
                string line = pl[i].Trim();
                if (!line.StartsWith("@", StringComparison.Ordinal)) continue;
                int sp = line.IndexOf(' ');
                if (sp <= 1) continue;
                string pkg = line.Substring(1, sp - 1).Trim();
                string pidTxt = line.Substring(sp + 1).Trim();
                if (pidTxt.Length == 0) continue;
                for (int r = 0; r < missing.Count; r++)
                {
                    if (missing[r].Pkg == pkg) { missing[r].Pid = pidTxt; break; }
                }
            }
        }

        // 排查用：:pid <包名|空> —— 打印 ps 样本与该包的匹配结果
        internal static void DoPidTest(string pkg)
        {
            if (OFFLINE) { Warn("设备未连接"); return; }
            if (pkg == null) pkg = "";
            pkg = pkg.Trim();
            if (pkg.Length == 0) pkg = QueryForegroundPkg();

            string o = "";
            string e = "";
            ShellCall(CUR, "ps -A -o PID,NAME 2>/dev/null | head -6", out o, out e);
            Console.WriteLine();
            UseDim();
            Console.WriteLine("  ps 样本：");
            UseDefault();
            string[] sample = (o + "\n" + e).Split('\n');
            for (int i = 0; i < sample.Length; i++)
                if (sample[i].Trim().Length > 0) Console.WriteLine("    " + sample[i].Trim());

            if (pkg.Length == 0) { Warn("没有包名可测（前台也识别不出来）"); return; }

            List<VerRow> one = new List<VerRow>();
            VerRow r = new VerRow();
            r.Pkg = pkg;
            r.Installed = true;
            one.Add(r);
            AttachPids(one);

            Console.WriteLine();
            if (r.Pid.Length > 0) Ok("匹配到 pid：" + r.Pid + "   （" + pkg + "）");
            else
            {
                Warn("没有匹配到 pid：" + pkg);
                Hint("应用可能没在运行；或 ps 的 NAME 与包名不一致");
            }
            CMD_OK = true;
        }

        // ps 一行：兼容 "1234 com.x" 和 "u0_a4 1234 ... com.x" 两种版式
        internal static bool SplitPsLine(string line, out string pid, out string name)
        {
            pid = "";
            name = "";
            string[] parts = line.Split(new char[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries);
            if (parts.Length < 2) return false;

            int tmp;
            if (int.TryParse(parts[0], out tmp))
            {
                pid = parts[0];
                name = parts[parts.Length - 1];
                return true;
            }

            for (int i = 0; i < parts.Length; i++)
            {
                if (int.TryParse(parts[i], out tmp)) { pid = parts[i]; break; }
            }
            name = parts[parts.Length - 1];
            return pid.Length > 0;
        }

        // ==================== 解析辅助 ====================
        // 把 "Package [com.x]" 到下一个 "Package [" 之间的版本行归为一条记录。
        // 没有这个分段，子串匹配 + 隐藏系统包会让两段信息合并成一行。
        internal static List<VerEntry> ParsePkgEntries(string text)
        {
            List<VerEntry> list = new List<VerEntry>();
            if (string.IsNullOrEmpty(text)) return list;

            VerEntry cur = null;
            string[] lines = text.Split('\n');

            for (int i = 0; i < lines.Length; i++)
            {
                string line = lines[i].TrimEnd('\r').Trim();
                if (line.Length == 0) continue;

                if (line.StartsWith("Package ["))
                {
                    int close = line.IndexOf(']');
                    string name = (close > 9) ? line.Substring(9, close - 9).Trim() : "";

                    cur = new VerEntry();
                    cur.Pkg = name;
                    list.Add(cur);
                    continue;
                }

                if (cur == null) continue;

                if (line.StartsWith("versionName="))
                {
                    cur.VerName = line.Substring(12).Trim();
                }
                else if (line.StartsWith("versionCode="))
                {
                    string rest = line.Substring(12).Trim();
                    int sp = rest.IndexOf(' ');
                    cur.VerCode = (sp > 0) ? rest.Substring(0, sp) : rest;
                }
                else if (line.StartsWith("lastUpdateTime="))
                {
                    cur.Update = line.Substring(15).Trim();
                }
                else if (line.StartsWith("codePath="))
                {
                    cur.Path = line.Substring(9).Trim();
                }
            }

            return list;
        }

        // 一条记录的简短描述，用于"另有记录"提示
        private static string DescribeEntry(VerEntry en)
        {
            StringBuilder sb = new StringBuilder();
            sb.Append("版本码 ");
            sb.Append(en.VerCode.Length > 0 ? en.VerCode : "?");
            if (en.VerName.Length > 0) sb.Append(" / ").Append(en.VerName);
            if (en.Update.Length > 0) sb.Append(" / ").Append(en.Update);
            return sb.ToString();
        }

        // 没找到完全匹配时，列出 dumpsys 实际返回了哪些包（最多 3 个）
        private static string NearMatches(List<VerEntry> entries, string want)
        {
            StringBuilder sb = new StringBuilder();
            int n = 0;

            for (int i = 0; i < entries.Count; i++)
            {
                string p = entries[i].Pkg;
                if (p.Length == 0) continue;
                if (string.Equals(p, want, StringComparison.Ordinal)) continue;

                if (n >= 3) { sb.Append(" …"); break; }
                if (n > 0) sb.Append("   ");
                sb.Append(p);
                n++;
            }

            return sb.ToString();
        }

        // 单个包：键值块。
        // 表格塞不下完整路径（/data/app/~~xxx==/包名-yyy==/base.apk 常常 60+ 字符），
        // 单查时用竖排布局，路径才能原样显示、能直接复制。
        private static void RenderPkgDetail(VerRow r)
        {
            Console.WriteLine();

            // 不再重复打印包名：上面刚输入的那一行就是包名，回车后又打一遍纯属噪音。
            // 别名是配置里额外带的信息，保留。
            if (r.Alias.Length > 0) Kv("别名", r.Alias);

            if (!r.Installed)
            {
                UseErr();
                Console.WriteLine("    未安装");
                UseDefault();

                string low = r.Pkg.ToLowerInvariant();
                if (low.StartsWith("ro.") || low.StartsWith("persist.")
                    || low.StartsWith("sys.") || low.StartsWith("debug."))
                {
                    Hint("这看起来是系统属性名，不是包名：取属性请用 getprop " + r.Pkg);
                }
                else
                {
                    Hint("确认包名拼写；用 :cmds 里的 apps 可以列出第三方应用");
                }
                Console.WriteLine();
                return;
            }

            Kv("版本名", r.VerName);
            Kv("版本码", r.VerCode);
            Kv("更新时间", r.Update);
            Kv("安装路径", r.Path);
            // 单包详情也要 pid（用户要求：有进程才显示）
            if (r.Pid.Length > 0) Kv("进程号", r.Pid);

            Console.WriteLine();
        }

        // 一行 "标签   值"，标签列按显示宽度对齐（中文算 2 列）
        private static void Kv(string k, string v)
        {
            const int LW = 10;

            UseDim();
            Console.Write("    " + PadRight(k, LW));
            UseDefault();

            Console.WriteLine((v != null && v.Length > 0) ? v : "-");
        }

        // 直接输入包名 => 版本 + 路径（等价于 :pkg ver <包名>）
        internal static void DoPkgLookup(string pkg)
        {
            DoVersions(pkg, true);
        }

        private static void RenderVerTable(List<VerRow> rows)
        {
            const int GAP = 2;        // 列间隔固定 2 列
            const int TIME_W = 19;    // 2026-11-01 08:34:01

            bool hasAlias = false;
            for (int i = 0; i < rows.Count; i++)
            {
                if (rows[i].Alias.Length > 0) { hasAlias = true; break; }
            }

            // 1. 列宽 = max(表头, 所有单元格)，再按内容类型设上限
            int wAlias = DispWidth("别名");
            int wPkg = DispWidth("包名");
            int wVer = DispWidth("版本名");

            for (int i = 0; i < rows.Count; i++)
            {
                VerRow r = rows[i];
                int a = DispWidth(r.Alias);
                int p = DispWidth(r.Pkg);
                int v = DispWidth(r.VerName);
                if (a > wAlias) wAlias = a;
                if (p > wPkg) wPkg = p;
                if (v > wVer) wVer = v;
            }

            // 版本名**绝不截断**：像 3.6.8.0-201-202610292156-991a935f-RELEASE
            // 这种带构建号的能到 40+ 列，截掉尾部就分不清是哪个构建。
            if (wVer > 80) wVer = 80;
            if (wAlias > 14) wAlias = 14;

            // 2. 包名列吃掉剩余空间（窗口窄时优先压缩它）
            int avail = LSW - 2;

            // 先按"带更新时间"算；包名压到 18 列仍放不下时，把更新时间挪到下一行，
            // 用行数换宽度 —— 宁可多一行，也不截断版本名。
            bool showTime = true;
            int pkgMax = avail - (TIME_W + GAP * 3 + wVer + (hasAlias ? wAlias : 0));
            if (pkgMax < 18)
            {
                showTime = false;
                pkgMax = avail - (GAP * 2 + wVer + (hasAlias ? wAlias : 0));
            }
            if (pkgMax > 44) pkgMax = 44;
            if (pkgMax < 18) pkgMax = 18;
            if (wPkg > pkgMax) wPkg = pkgMax;

            // 3. 表头 + 分隔线
            Console.WriteLine();

            StringBuilder head = new StringBuilder("  ");
            if (hasAlias) head.Append(PadCell("别名", wAlias)).Append(new string(' ', GAP));
            head.Append(PadCell("包名", wPkg)).Append(new string(' ', GAP));
            head.Append(PadCell("版本名", wVer));
            if (showTime)
            {
                head.Append(new string(' ', GAP));
                head.Append("更新时间");
            }

            UseDim();
            Console.WriteLine(head.ToString());
            // 分隔线按"显示宽度"算（中文占 2 列，不能用字符数）
            Console.WriteLine("  " + new string('-', DispWidth(head.ToString())));
            UseDefault();

            int installed = 0;

            // 4. 数据行
            for (int i = 0; i < rows.Count; i++)
            {
                VerRow r = rows[i];

                StringBuilder sb = new StringBuilder("  ");
                if (hasAlias) sb.Append(PadCell(r.Alias, wAlias)).Append(new string(' ', GAP));
                sb.Append(PadCell(r.Pkg, wPkg)).Append(new string(' ', GAP));

                if (!r.Installed)
                {
                    Console.Write(sb.ToString());
                    UseErr();
                    Console.WriteLine("未安装");
                    UseDefault();
                    continue;
                }

                installed++;

                Console.Write(sb.ToString());
                UseOk();
                Console.Write(PadCell(r.VerName, wVer));
                UseDefault();
                if (r.Pid.Length > 0)
                {
                    // 有进程才显示；没有就整段不出现（不留 "pid -" 这种占位）
                    Console.Write(new string(' ', GAP));
                    UseDim();
                    Console.Write("pid " + r.Pid);
                    UseDefault();
                }

                if (showTime)
                {
                    Console.Write(new string(' ', GAP));
                    UseDim();
                    Console.WriteLine(r.Update);
                    UseDefault();
                }
                else
                {
                    // 宽度不够：时间另起一行，缩进对齐到包名列
                    Console.WriteLine();
                    UseDim();
                    Console.WriteLine("    " + r.Update);
                    UseDefault();
                }
            }

            Console.WriteLine();

            if (installed == 0)
            {
                Fail("一个都没安装");
                Hint("确认包名是否正确；可用 apps 列出第三方应用");
            }
            else if (installed < rows.Count)
            {
                Warn("共 " + rows.Count + " 个：已安装 " + installed + "，未安装 " + (rows.Count - installed));
            }
            // 全部安装时不打"√ 共 N 个，全部已安装"：表格里已经有 N 行，
            // 再补一句只是重复确认，属于纯噪音。
        }

        // 单元格：先按宽度截断（超长加 ..），再补空格对齐
        private static string PadCell(string s, int width)
        {
            return PadRight(FitWidth(s, width), width);
        }

        // 超过 max 列就截断，末尾补 ".."（用 ASCII 点，宽度可控）
        internal static string FitWidth(string s, int max)
        {
            if (string.IsNullOrEmpty(s)) return "";
            if (max <= 0) return "";
            if (DispWidth(s) <= max) return s;

            int w = 0;
            for (int i = 0; i < s.Length; i++)
            {
                w += CharWidth(s[i]);
                if (w > max - 2) return s.Substring(0, i) + "..";
            }
            return s;
        }

        // ==================== 当前前台应用 ====================
        // v7.2 重写。旧实现有三个坑：
        //   1) 先查 dumpsys window。mFocusedApp 是"最近获得焦点的任务"，
        //      有悬浮窗 / 输入法弹出 / 多显示时常常不是真正前台；
        //      真正可靠的是 dumpsys activity 里的 topResumedActivity。
        //   2) 拿到第一行就返回。多显示设备每个 display 各有一份 focus，
        //      第一条往往不是你想看的那块屏。
        //   3) 完全不看 display 号 —— 座舱这种多屏设备必然误判。
        // 现在：一次调用取三处证据，按可信度分级；多屏时全部列出而不是猜一个。
        internal class FgCand
        {
            internal string Pkg = "";
            internal int Display = -1;
            internal string Source = "";
            internal int Tier = 9;
            internal string Raw = "";
        }

        // 【2026-11-14】:pkg now 已移除，功能并入 :front。保留一个迁移提示。
        internal static void DoNowRetired()
        {
            Fail(":pkg now 已移除");
            Hint("改用 :front —— 查前台包名 / Activity / 路径，并带 pid");
            CMD_OK = false;
        }

        internal static void DoNowLegacy(string argRaw)
        {
            if (OFFLINE)
            {
                Warn("设备未连接，无法查询前台应用");
                Hint("输入 :r 重连");
                return;
            }

            string a = (argRaw == null) ? "" : argRaw.Trim().ToLowerInvariant();
            bool rawMode = a.IndexOf("-r", StringComparison.Ordinal) >= 0;

            // 不再回显、也不再单独打"前台应用 xxx"标题：
            // 下面的版本表就是答案，多显示时会列出每一块屏的包，标题反而重复。
            List<FgCand> cands = QueryForegroundCands();

            if (rawMode) { ShowFgRaw(cands); return; }

            if (cands.Count == 0)
            {
                Fail("没有识别出前台应用");
                Hint("可能停在锁屏或系统界面；用 now -r 看原始输出，或 :pkg ver <包名> 直接查");
                return;
            }

            // 只取可信度最高的一级（Tier 越小越可信）
            int best = 9;
            for (int i = 0; i < cands.Count; i++)
            {
                if (cands[i].Tier < best) best = cands[i].Tier;
            }

            List<FgCand> top = new List<FgCand>();
            for (int i = 0; i < cands.Count; i++)
            {
                if (cands[i].Tier != best) continue;
                if (ExistsPkg(top, cands[i].Pkg)) continue;
                top.Add(cands[i]);
            }

            // 只有一台/一块屏时，把"是哪个包"单独说一句 ——
            // 下面的详情块不再重复包名，没有这句就不知道在看谁。
            // 多显示时不打这句：表格里每行都是包名，再列一遍是噪音。
            if (top.Count == 1)
            {
                Console.WriteLine();
                UseDim();
                Console.Write("  前台  ");
                UseDefault();
                UsePath();
                Console.WriteLine(top[0].Pkg);
                UseDefault();
            }

            // 多个就一起查版本，反正只有一次 adb 调用
            StringBuilder q = new StringBuilder();
            for (int i = 0; i < top.Count; i++)
            {
                if (i > 0) q.Append(' ');
                q.Append(top[i].Pkg);
            }

            DoVersions(q.ToString(), true);
        }

        // 一键查询前台应用包名：完整包名 + Activity + 路径，不截断（需求2.2）
        internal static void DoFront()
        {
            if (OFFLINE)
            {
                Warn("设备未连接，无法查询前台应用");
                Hint("输入 :r 重连");
                return;
            }

            List<FgCand> cands = QueryForegroundCands();
            if (cands.Count == 0)
            {
                Fail("没有识别出前台应用");
                Hint("可能停在锁屏或系统界面；输入 :pkg now 看版本表");
                return;
            }

            int best = 9;
            for (int i = 0; i < cands.Count; i++) if (cands[i].Tier < best) best = cands[i].Tier;

            FgCand top = cands[0];
            for (int i = 0; i < cands.Count; i++) if (cands[i].Tier == best) { top = cands[i]; break; }

            string pkg = top.Pkg;
            string cmp = ExtractComponent(top.Raw);
            string path = QueryPkgPath(pkg);

            CMD_OK = true;

            // pid：有进程才显示，没有就不出现（用户要求）
            List<VerRow> pidRows = new List<VerRow>();
            VerRow pr = new VerRow();
            pr.Pkg = pkg;
            pr.Installed = true;
            pidRows.Add(pr);
            AttachPids(pidRows);

            UseOk();
            Console.WriteLine("  包名      " + pkg);
            if (cmp.Length > 0) Console.WriteLine("  Activity  " + cmp);
            if (path.Length > 0) Console.WriteLine("  路径      " + path);
            if (pr.Pid.Length > 0) Console.WriteLine("  pid       " + pr.Pid);
            UseDefault();
        }

        // 一键清理前台应用（需求2.1）
        //
        // 【2026-11-12 变更】用户确认：这里的"清理"要用 `pm clear` 而不是 `am force-stop`。
        // 两者语义差别很大，不能混：
        //   am force-stop <pkg>   只杀进程，应用数据完整保留，下次启动还是原来的状态
        //   pm clear <pkg>        清空该应用全部数据（/data/data/<pkg> + 缓存 + 授权），
        //                         应用退回"刚安装"的状态，首次启动向导会重新走一遍
        // 测试场景要的就是后者：验证首启流程 / 复现初始化才出现的缺陷。
        //
        // 【坑】pm clear 失败时**不一定**返回非 0 退出码。
        // 实测 ROM 上有两种情况：
        //   · 包名不存在            -> 输出 "Failed"，rc 仍为 0
        //   · 系统级包不允许清数据   -> 输出 "Failed"
        // 只判 rc != 0 会把失败当成功，用户以为清干净了、实际数据还在，
        // 后续复现结论全错。所以这里必须同时校验输出里有没有 "Failed"/
        // "Exception"/"denied" 这类字样，并把 "Success" 当作成功的正向证据。
        internal static void DoFstop()
        {
            if (OFFLINE)
            {
                Warn("设备未连接，无法清理前台应用");
                Hint("输入 :r 重连");
                return;
            }

            List<FgCand> cands = QueryForegroundCands();
            string pkg = "";
            if (cands.Count > 0)
            {
                int best = 9;
                for (int i = 0; i < cands.Count; i++) if (cands[i].Tier < best) best = cands[i].Tier;
                for (int i = 0; i < cands.Count; i++) if (cands[i].Tier == best) { pkg = cands[i].Pkg; break; }
            }

            if (pkg.Length == 0)
            {
                Fail("没有识别出前台应用");
                Hint("可能停在锁屏或系统界面");
                return;
            }

            // 判定与提示统一走 ClearPkg：CLI 的 :fstop（清前台）和 APK 管理页的
            // 「清空数据」（清选中项）必须是同一套口径，否则同一个包两边结论会不一致。
            ClearPkg(pkg);
        }

        // 一键 Kill 前台应用：adb shell kill -9 <pid>
        // 与 :fstop（pm clear 清数据）区分：这里只杀进程，不动数据。
        internal static void DoKillFront()
        {
            if (OFFLINE)
            {
                Warn("设备未连接，无法 Kill 前台应用");
                Hint("输入 :r 重连");
                return;
            }

            string pkg = QueryForegroundPkg();
            if (pkg.Length == 0)
            {
                Fail("没有识别出前台应用");
                Hint("可能停在锁屏或系统界面；输入 :pkg now 看一眼");
                return;
            }

            // 复用批量版本的取 pid 逻辑（ps 一次搞定）
            List<VerRow> one = new List<VerRow>();
            VerRow r = new VerRow();
            r.Pkg = pkg;
            r.Installed = true;
            one.Add(r);
            AttachPids(one);

            if (r.Pid.Length == 0)
            {
                Warn("前台应用 " + pkg + " 没有运行中的进程");
                Hint("可能已经退到后台被回收；用 :pkg now 确认");
                return;
            }

            Info("Kill 前台进程：" + pkg);
            Info("  pid " + r.Pid);

            string o = "";
            string e = "";
            int rc = ShellCall(CUR, "kill -9 " + r.Pid + " 2>&1", out o, out e);
            string low = (o + " " + e).ToLowerInvariant();

            if (low.IndexOf("not permitted", StringComparison.Ordinal) >= 0
                || low.IndexOf("operation not allowed", StringComparison.Ordinal) >= 0)
            {
                Fail("kill 失败：权限不足");
                Hint("普通 shell 杀不了别的应用；点顶部 root 提权后再试");
                CMD_OK = false;
                return;
            }

            System.Threading.Thread.Sleep(300);

            // 复核：pid 还在不在
            List<VerRow> again = new List<VerRow>();
            VerRow r2 = new VerRow();
            r2.Pkg = pkg;
            r2.Installed = true;
            again.Add(r2);
            AttachPids(again);

            if (r2.Pid.Length == 0) Ok("已 kill：" + pkg + "（进程已消失）");
            else Warn("已执行 kill，但进程仍在：" + r2.Pid + "（可能被系统/服务拉起）");
            CMD_OK = true;
            if (rc != 0 && low.Trim().Length > 0) Hint("命令返回：" + FirstLine(low.Trim()));
        }

        // 查询系统深色模式设置：settings get global day_night_auto_mode
        internal static void DoSysNight()
        {
            if (OFFLINE)
            {
                Warn("设备未连接");
                Hint("输入 :r 重连");
                return;
            }

            string o = "";
            string e = "";
            ShellCall(CUR, "settings get global day_night_auto_mode 2>&1", out o, out e);
            string v = FirstLine((o + "\n" + e).Trim());

            CMD_OK = true;
            Console.WriteLine();
            UseDim();
            Console.Write("  系统主题  ");
            UseDefault();

            if (v.Length == 0 || v.Equals("null", StringComparison.OrdinalIgnoreCase))
            {
                UseDim();
                Console.WriteLine("未设置（设备返回：" + (v.Length == 0 ? "空" : v) + "）");
                UseDefault();
                return;
            }

            UsePath();
            if (v == "0") Console.WriteLine("日间（0）");
            else if (v == "1") Console.WriteLine("夜间（1）");
            else if (v == "2") Console.WriteLine("自动（2）");
            else Console.WriteLine("设备返回：" + v);
            UseDefault();
        }

        // 当前前台包名（挑 tier 最小的那条），取不到返回 ""。
        // 原来这段逻辑在 DoExportApk / DoFstop 里各抄了一份，APK 管理页
        // 「查前台」又要用一次 —— 收到一处，避免三份判断慢慢漂。
        internal static string QueryForegroundPkg()
        {
            List<FgCand> cands = QueryForegroundCands();
            if (cands.Count == 0) return "";

            int best = 9;
            for (int i = 0; i < cands.Count; i++) if (cands[i].Tier < best) best = cands[i].Tier;
            for (int i = 0; i < cands.Count; i++) if (cands[i].Tier == best) return cands[i].Pkg;
            return "";
        }

        // 从原始行提取完整组件名（包名/Activity），取不到返回 ""
        internal static string ExtractComponent(string line)
        {
            if (string.IsNullOrEmpty(line)) return "";
            for (int i = 0; i < line.Length; i++)
            {
                if (line[i] != '/') continue;
                int s = i - 1;
                while (s >= 0 && IsPkgChar(line[s])) s--;
                s++;
                if (s >= i) continue;
                string p = line.Substring(s, i - s);
                if (p.Length < 3 || p.IndexOf('.') <= 0 || IsAllDigits(p)) continue;
                int e = i + 1;
                while (e < line.Length && IsPkgChar(line[e])) e++;
                if (e <= i + 1) continue;
                return line.Substring(s, e - s);
            }
            return "";
        }

        // 查包路径（pm path），取不到返回 ""
        private static string QueryPkgPath(string pkg)
        {
            string o = "";
            string e = "";
            int rc = ShellCall(CUR, "pm path " + pkg + " 2>/dev/null", out o, out e);
            string all = (o + e).Trim();
            if (rc == 0 && all.StartsWith("package:", StringComparison.Ordinal))
                return all.Substring("package:".Length).Trim();
            return "";
        }

        private static bool ExistsPkg(List<FgCand> list, string pkg)
        {
            for (int i = 0; i < list.Count; i++)
            {
                if (string.Equals(list[i].Pkg, pkg, StringComparison.Ordinal)) return true;
            }
            return false;
        }

        // 一次 adb 调用，把三处证据全取回来
        private static List<FgCand> QueryForegroundCands()
        {
            List<FgCand> list = new List<FgCand>();

            StringBuilder sb = new StringBuilder();
            sb.Append("echo '##ACT'; dumpsys activity activities 2>/dev/null | grep -E 'topResumedActivity|mResumedActivity'; ");
            sb.Append("echo '##WIN'; dumpsys window 2>/dev/null | grep -E 'mCurrentFocus|mFocusedApp|mDisplayId='; ");
            sb.Append("echo '##OLD'; dumpsys activity 2>/dev/null | grep -E 'mFocusedActivity'; ");

            string o = "";
            string e = "";
            ShellCall(CUR, sb.ToString(), out o, out e);

            string[] lines = (o + "\n" + e).Split('\n');

            string sec = "";
            int disp = -1;

            for (int i = 0; i < lines.Length; i++)
            {
                string line = lines[i].TrimEnd('\r').Trim();
                if (line.Length == 0) continue;

                if (line.StartsWith("##"))
                {
                    sec = line.Substring(2).Trim().ToUpperInvariant();
                    disp = -1;
                    continue;
                }

                int d = ParseIntAfter(line, "mDisplayId=");
                if (d >= 0) disp = d;

                string pkg = ExtractPkg(line);
                if (pkg.Length == 0) continue;

                FgCand c = new FgCand();
                c.Pkg = pkg;
                c.Display = disp;
                c.Raw = line;

                if (sec == "ACT")
                {
                    if (line.IndexOf("topResumedActivity", StringComparison.Ordinal) >= 0)
                    {
                        c.Tier = 1;
                        c.Source = "topResumedActivity";
                    }
                    else
                    {
                        c.Tier = 3;
                        c.Source = "mResumedActivity";
                    }
                }
                else if (sec == "WIN")
                {
                    if (line.IndexOf("mCurrentFocus", StringComparison.Ordinal) >= 0)
                    {
                        c.Tier = 2;
                        c.Source = "mCurrentFocus";
                    }
                    else
                    {
                        c.Tier = 4;
                        c.Source = "mFocusedApp";
                    }
                }
                else
                {
                    c.Tier = 5;
                    c.Source = "mFocusedActivity";
                }

                list.Add(c);
            }

            return list;
        }

        // 列出全部证据，用于排查"前台识别不对"
        private static void ShowFgRaw(List<FgCand> cands)
        {
            Console.WriteLine();

            if (cands.Count == 0)
            {
                Fail("三处证据都没有拿到包名");
                Hint("在窗口里直接跑：dumpsys window | grep mCurrentFocus   把输出发我");
                return;
            }

            UseDim();
            Console.WriteLine("  识别到的证据（Tier 越小越可信）：");
            UseDefault();

            for (int i = 0; i < cands.Count && i < 20; i++)
            {
                UseDim();
                Console.Write("    [" + cands[i].Tier + "] ");
                UseDefault();
                Console.Write(cands[i].Pkg);
                UseDim();
                Console.WriteLine("   " + cands[i].Raw);
                UseDefault();
            }

            Console.WriteLine();
            Hint("1=topResumedActivity 2=mCurrentFocus 3=mResumedActivity 4=mFocusedApp 5=mFocusedActivity");
        }

        // 取 "key=数字" 里的数字，取不到返回 -1
        private static int ParseIntAfter(string line, string key)
        {
            int i = line.IndexOf(key, StringComparison.Ordinal);
            if (i < 0) return -1;

            i += key.Length;
            int s = i;
            while (i < line.Length && line[i] >= '0' && line[i] <= '9') i++;
            if (i == s) return -1;

            int v;
            if (int.TryParse(line.Substring(s, i - s), out v)) return v;
            return -1;
        }

        // 抓 "<包名>/<组件>" 里的包名：从 '/' 向左吃字母数字下划线和点
        internal static string ExtractPkg(string line)
        {
            if (string.IsNullOrEmpty(line)) return "";

            for (int i = 0; i < line.Length; i++)
            {
                if (line[i] != '/') continue;

                int s = i - 1;
                while (s >= 0 && IsPkgChar(line[s])) s--;
                s++;

                if (s >= i) continue;

                string p = line.Substring(s, i - s);
                // 包名至少要有点号、长度合理、不能是纯数字
                if (p.Length >= 3 && p.IndexOf('.') > 0 && !IsAllDigits(p)) return p;
            }
            return "";
        }

        private static bool IsPkgChar(char c)
        {
            return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z')
                || (c >= '0' && c <= '9') || c == '_' || c == '.';
        }

        private static bool IsAllDigits(string s)
        {
            for (int i = 0; i < s.Length; i++)
            {
                char c = s[i];
                if (c < '0' || c > '9') return false;
            }
            return s.Length > 0;
        }
    }
}
