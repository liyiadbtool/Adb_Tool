// ============================================================================
//  MapCmds.cs - 智驾出行相关命令（2026-11-22 第 14 批需求 1.1 ~ 1.14）
// ----------------------------------------------------------------------------
//  用户给了一批"智驾/地图"排障动作，这里是它们的实现。
//
//  几条设计说明：
//
//  1) findstr → 设备端 grep
//     用户给的原始命令是 `adb shell dumpsys package xxx | findstr versionName`。
//     findstr 是 Windows 命令，在工具的 shell 封装里不可用，统一改成 grep
//     （用户在第 12 批已确认这个改法）。
//
//  2) 地图包名集中在 MAP_PKG
//     高德/地图相关命令都围绕同一个包，写死一次，改包名只改一处。
//
//  3) pm clear 是"清全部数据"不是"清缓存"
//     `pm clear` 会清掉应用的全部私有数据：登录态、收藏地点、离线地图包、设置。
//     用户说的"清理地图缓存"实际用的是这个命令，所以执行前把影响打在输出里，
//     免得有人以为是清个临时文件。
//
//  4) 切换繁体要 stop; start，会重启 Android 框架
//     这是正常现象（所有 App 退出、桌面重绘，10~30 秒），不是故障。
//     执行前打提示，避免测试中途被吓一跳。
// ============================================================================
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

namespace AdbLogExport
{
    internal static partial class App
    {
        // 地图（高德定制）包名。地图相关命令都用这一个，改包名只改这里。
        internal const string MAP_PKG = "space.syncore.cockpit.map";

        // ====================================================================
        //  1.3 查询地图版本（版本 / 路径 / PID / Activity）
        // ====================================================================
        //
        //  用户要求查 4 项，不止 versionName：
        //    · 版本    dumpsys package | grep versionName / versionCode
        //    · 路径    pm path
        //    · PID     pidof
        //    · Activity  cmd package resolve-activity --brief（取启动 Activity）
        //
        //  为什么 Activity 取"启动 Activity"而不是"当前 Activity"：
        //    `dumpsys activity activities | grep mResumedActivity` 只能拿到前台界面，
        //    地图不在前台时查不到 —— 而这个查询经常在排查"地图起不来"时用，
        //    那时候地图恰恰不在前台。所以取启动 Activity 更可靠（总能查到）。
        internal static void DoMapInfo()
        {
            if (!RequireDevice("")) return;

            Info("查询地图信息：" + MAP_PKG);
            Blank();

            // ---- 是否安装 ----
            string pmPath = ShellCapture("pm path " + MAP_PKG);
            if (pmPath.IndexOf("package:", StringComparison.Ordinal) < 0)
            {
                Fail("地图未安装：" + MAP_PKG);
                Hint("包名可能不对，或这台车机没装高德定制版地图");
                return;
            }

            // ---- 版本 ----
            string verOut = ShellCapture("dumpsys package " + MAP_PKG + " | grep -E 'versionName|versionCode'");
            string verName = FirstMatch(verOut, @"versionName=(\S+)");
            string verCode = FirstMatch(verOut, @"versionCode=(\d+)");
            if (verName.Length == 0 && verCode.Length == 0)
            {
                // 有些 ROM 的 dumpsys 输出格式不同，兜底用 dumpsys package 全量里找
                string all = ShellCapture("dumpsys package " + MAP_PKG);
                verName = FirstMatch(all, @"versionName=(\S+)");
                verCode = FirstMatch(all, @"versionCode=(\d+)");
            }
            Ok("  版本      " + (verName.Length > 0 ? verName : "（未取到）")
                + (verCode.Length > 0 ? "  (" + verCode + ")" : ""));

            // ---- 路径 ----
            // pm path 可能有多行（split APK），全列出来
            string[] pathLines = pmPath.Split('\n');
            bool first = true;
            for (int i = 0; i < pathLines.Length; i++)
            {
                string l = pathLines[i].Trim();
                if (l.Length == 0) continue;
                if (l.StartsWith("package:")) l = l.Substring("package:".Length).Trim();
                if (first)
                {
                    Ok("  路径      " + l);
                    first = false;
                }
                else Ok("            " + l);   // 多 split 时对齐续行
            }

            // ---- PID ----
            string pid = ShellCapture("pidof " + MAP_PKG).Trim();
            if (pid.Length == 0)
            {
                // pidof 在部分 toybox 版本上没有，退回 ps
                string psOut = ShellCapture("ps -A -o PID,NAME 2>/dev/null | grep " + EscapeGrep(MAP_PKG));
                pid = FirstMatch(psOut, @"^\s*(\d+)");
            }
            if (pid.Length > 0)
                Ok("  PID       " + pid);
            else
                Warn("  PID       未运行（进程没起来）");

            // ---- Activity ----
            string act = ShellCapture(
                "cmd package resolve-activity --brief -c android.intent.category.LAUNCHER " + MAP_PKG);
            // 输出形如：priority=0 ... \n space.syncore.cockpit.map/xxx.MainActivity
            string actName = "";
            string[] al = act.Split('\n');
            for (int i = 0; i < al.Length; i++)
            {
                string l = al[i].Trim();
                if (l.IndexOf('/') > 0 && l.IndexOf('=') < 0 && !l.StartsWith("priority")
                    && !l.StartsWith("packageName"))
                {
                    actName = l;
                    break;
                }
            }
            if (actName.Length > 0) Ok("  Activity  " + actName);
            else
            {
                // 兜底：从 dumpsys package 里找第一个 Activity 声明
                string dump = ShellCapture("dumpsys package " + MAP_PKG + " | grep -m1 -E 'Activity' ");
                Warn("  Activity  未直接取到" + (dump.Trim().Length > 0 ? "（原始：" + FirstLine(dump).Trim() + "）" : ""));
            }

            Blank();
            Hint("停止进程：:mapstop    清理数据：:mapclear");
        }

        // ====================================================================
        //  1.4 停止地图进程
        // ====================================================================
        internal static void DoMapStop()
        {
            if (!RequireDevice("")) return;
            Info("停止地图进程：" + MAP_PKG);
            string o = ShellCapture("am force-stop " + MAP_PKG);
            if (o.Trim().Length > 0) Hint("  " + FirstLine(o).Trim());

            // 复核：force-stop 后 pidof 应该为空
            System.Threading.Thread.Sleep(600);
            string pid = ShellCapture("pidof " + MAP_PKG).Trim();
            if (pid.Length == 0) Ok("✓ 地图进程已停止");
            else Warn("进程仍在运行（PID " + pid + "），可能被系统自动拉起");
        }

        // ====================================================================
        //  1.5 清理地图缓存
        // ====================================================================
        //
        //  ★ 这不是"清缓存"。
        //    pm clear 清的是应用**全部私有数据**：登录态、收藏地点、
        //    离线地图包、个人设置 —— 全没。用户给的就是这条命令，
        //    所以照做，但执行前把影响打出来。
        internal static void DoMapClear()
        {
            if (!RequireDevice("")) return;

            Info("清理地图数据：pm clear " + MAP_PKG);
            Warn("  注意：pm clear 会清除该应用**全部私有数据**");
            Hint("  包括：登录态 / 收藏地点 / 离线地图 / 个人设置");
            Hint("  （不是只清临时缓存，清完要重新登录并重新下载离线包）");

            string o = ShellCapture("pm clear " + MAP_PKG);
            string r = o.Trim();
            if (r.IndexOf("Success", StringComparison.OrdinalIgnoreCase) >= 0)
                Ok("✓ 已清理（" + FirstLine(r).Trim() + "）");
            else if (r.Length > 0)
                Warn("结果：" + FirstLine(r).Trim());
            else
                Ok("已下发清理命令（无输出）");
        }

        // ====================================================================
        //  1.7 导出全日志（系统 / 高德 / QNX / ANR / dropbox）
        // ====================================================================
        //
        //  对应用户给的脚本。原脚本第一行 `@echo reboot` ——
        //  那是"关闭回显 + 打印 reboot"，**不是真的重启**。
        //  真重启的话后面的 adb pull 全会失败，所以这里只打一行提示，不重启。
        //
        //  目录结构（沿用工具的既有口径）：
        //    桌面\logcat\<日期>\log_<时间戳>\
        //        ├ bllog2\        ← /data/misc/bllog（脚本里单独建的子目录）
        //        ├ anr\
        //        ├ tombstones\
        //        ├ dropbox\
        //        ├ slog2\         ← QNX
        //        ├ androidlog\
        //        └ bllog\         ← 高德 autonavi
        private static readonly string[][] FULL_LOG_PULLS = new string[][]
        {
            // { 设备路径, 本地子目录（空=直接放根） }
            new string[] { "/data/anr",                        "anr" },
            new string[] { "/data/tombstones",                  "tombstones" },
            new string[] { "/data/system/dropbox",              "dropbox" },
            new string[] { "/share/log/slog2",                  "slog2" },      // QNX
            new string[] { "/log/android_log/androidlog",       "androidlog" },
            new string[] { "/sdcard/autonavi/navi/logs/bllog",  "bllog" },      // 高德
            new string[] { "/data/misc/bllog",                  "bllog2" }      // 高德（misc）
        };

        // 1.8 用的子集：不含高德、不含 QNX
        private static readonly string[][] SYS_LOG_PULLS = new string[][]
        {
            new string[] { "/data/anr",                        "anr" },
            new string[] { "/data/tombstones",                  "tombstones" },
            new string[] { "/data/system/dropbox",              "dropbox" },
            new string[] { "/log/android_log/androidlog",       "androidlog" }
        };

        internal static void DoFullLog() { DoLogBundle(FULL_LOG_PULLS, "log", "全日志（系统+高德+QNX+ANR）"); }
        internal static void DoSysLog()  { DoLogBundle(SYS_LOG_PULLS,  "logcat", "日志（不含高德/QNX）"); }

        // 两种导出的共同骨架。抽出来是因为差别只有"拉哪几个目录"和"目录名前缀"。
        private static void DoLogBundle(string[][] pulls, string prefix, string label)
        {
            if (!RequireDevice("")) return;

            Info("导出" + label);
            Blank();

            // root + remount（anr/tombstones/dropbox 都要 root 才能读）
            Info("① adb root");
            HostCapture("root");
            System.Threading.Thread.Sleep(800);
            Info("② adb remount");
            string rm = HostCapture("remount");
            if (rm.Trim().Length > 0) Hint("  " + FirstLine(rm).Trim());

            // 建目录
            string stamp = DateTime.Now.ToString("yyyy-MM-dd HH-mm-ss");
            string rootDir = Path.Combine(OutDir(""), prefix + "_" + stamp);
            try { Directory.CreateDirectory(rootDir); } catch { }
            Ok("③ 导出目录：" + rootDir);
            Blank();

            int okN = 0, skipN = 0;
            for (int i = 0; i < pulls.Length; i++)
            {
                string remote = pulls[i][0];
                string sub = pulls[i][1];

                string target = rootDir;
                if (sub != null && sub.Length > 0)
                {
                    target = Path.Combine(rootDir, sub);
                    try { Directory.CreateDirectory(target); } catch { }
                }

                Info("   pull " + remote);
                string o = ShellCapture("pull " + remote + " \"" + target + "\"");
                string all = o;
                if (all.IndexOf("No such file", StringComparison.OrdinalIgnoreCase) >= 0
                    || all.IndexOf("does not exist", StringComparison.OrdinalIgnoreCase) >= 0
                    || all.IndexOf("error:", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    skipN++;
                    Warn("     跳过（目录不存在或无权限）");
                }
                else okN++;
            }

            Blank();
            Ok("导出完成：成功 " + okN + " 项，跳过 " + skipN + " 项");
            Ok("目录：" + rootDir);
        }

        // ====================================================================
        //  1.10 切换繁体（zh-HK）
        // ====================================================================
        //
        //  用户给的命令：setprop persist.sys.locale zh-HK; stop; start
        //
        //  ★ stop; start 会重启 Android 框架：
        //    所有应用退出、桌面重绘，约 10~30 秒。这是正常的语言切换流程，
        //    不是故障。执行前必须提示，否则测试中途会被吓一跳。
        //
        //  另外 stop/start 之后 adb 连接可能短暂断一下，
        //  后续命令要等设备回来（用 WaitBoot 的思路）。
        internal static void DoSwitchTraditional()
        {
            if (!RequireDevice("")) return;

            Info("切换语言 → 繁体中文（zh-HK）");
            Warn("  ⚠ 即将重启 Android 框架（stop; start）");
            Hint("  所有应用会退出、桌面重绘，约 10~30 秒，属正常现象");
            Blank();

            Info("① setprop persist.sys.locale zh-HK");
            ShellCapture("setprop persist.sys.locale zh-HK");

            // 回读确认（setprop 静默失败很常见）
            string cur = ShellCapture("getprop persist.sys.locale").Trim();
            if (cur == "zh-HK") Ok("  已设置（回读：" + cur + "）");
            else Warn("  回读不一致：期望 zh-HK，实际 " + (cur.Length == 0 ? "（空）" : cur));

            Info("② 重启框架（stop → start）");
            Hint("  正在重启，界面会黑一下…");
            ShellCapture("stop");
            System.Threading.Thread.Sleep(1200);
            ShellCapture("start");

            // 等设备回来
            Info("③ 等待设备恢复…");
            int waited = 0;
            bool back = false;
            while (waited < 60)
            {
                System.Threading.Thread.Sleep(2000);
                waited += 2;
                string st = ShellCapture("getprop sys.boot_completed").Trim();
                if (st == "1") { back = true; break; }
            }
            if (back) Ok("✓ 框架已恢复（等待 " + waited + " 秒）");
            else Warn("  60 秒内未检测到 boot_completed，请手动确认设备状态");

            Info("④ 当前语言：" + ShellCapture("getprop persist.sys.locale").Trim());
        }

        // ====================================================================
        //  1.13 修改系统时间（前置准备 + 设置）
        //  1.14 恢复系统时间
        // ====================================================================
        //
        //  用户原脚本只有"disable + 打开设置"，**缺了真正改时间**的三步
        //  （关自动同步 / date / hwclock -w）。这里补齐。
        //
        //  为什么两层都要关：
        //    · pm disable com.gxa.car.timesync   —— 禁用车厂的时间同步 App
        //    · settings put global auto_time 0   —— 关系统的自动时间开关
        //    只做其中一个，另一个仍可能把时间改回去。
        //
        //  date 的两种格式：
        //    标准  MMDDhhmmCCYY.ss  → 112218002026.00
        //    可读  2026-11-22 18:00:00（部分 ROM 支持）
        //  先试标准，失败再试可读，最后回读确认。

        internal static void DoTimePrepare()
        {
            if (!RequireDevice("")) return;

            Info("准备修改系统时间（前置）");
            Warn("  ⚠ 将禁用工程模式与时间同步");
            Hint("  用完请点「恢复系统时间」把两个包重新启用");
            Blank();

            Info("① adb root");
            HostCapture("root");
            System.Threading.Thread.Sleep(800);

            Info("② adb remount");
            string rm = HostCapture("remount");
            if (rm.Trim().Length > 0) Hint("  " + FirstLine(rm).Trim());

            Info("③ 禁用工程模式 com.android.engmode");
            string o1 = ShellCapture("pm disable com.android.engmode");
            if (o1.Trim().Length > 0) Hint("  " + FirstLine(o1).Trim());

            Info("④ 禁用时间同步 com.gxa.car.timesync");
            string o2 = ShellCapture("pm disable com.gxa.car.timesync");
            if (o2.Trim().Length > 0) Hint("  " + FirstLine(o2).Trim());

            Info("⑤ 关系统自动时间 / 自动时区");
            ShellCapture("shell settings put global auto_time 0");
            ShellCapture("shell settings put global auto_time_zone 0");

            Blank();
            Ok("前置完成。现在可以直接改时间，或点「设置时间」输一个时间");
            Hint("恢复：点「恢复系统时间」");
        }

        // 设置时间。param 由页面传进来（如 "2026-11-22 18:00:00"）。
        internal static void DoSetTime(string param)
        {
            if (!RequireDevice("")) return;

            string raw = (param == null ? "" : param).Trim();
            if (raw.Length == 0)
            {
                Warn("没有传入时间");
                Hint("格式：2026-11-22 18:00:00");
                return;
            }

            DateTime dt;
            string[] fmts = new string[]
            {
                "yyyy-MM-dd HH:mm:ss", "yyyy-MM-dd HH:mm", "yyyy-MM-dd",
                "yyyy/MM/dd HH:mm:ss", "yyyy/MM/dd HH:mm",
                "yyyyMMddHHmmss", "yyyyMMddHHmm"
            };
            if (!DateTime.TryParseExact(raw, fmts, null,
                    System.Globalization.DateTimeStyles.None, out dt))
            {
                // 再试宽松解析（用户可能写 2026-11-22 18:00）
                if (!DateTime.TryParse(raw, out dt))
                {
                    Fail("时间格式不认识：" + raw);
                    Hint("请用 2026-11-22 18:00:00 这种格式");
                    return;
                }
            }

            Info("设置系统时间 → " + dt.ToString("yyyy-MM-dd HH:mm:ss"));
            Blank();

            // 标准格式 MMDDhhmmCCYY.ss
            string standard = dt.ToString("MMddHHmmyyyy") + ".00";
            Info("① adb shell date \"" + standard + "\"");
            string o1 = ShellCapture("date " + standard);

            // 回读，不一致再试可读格式
            System.Threading.Thread.Sleep(300);
            string now = ShellCapture("date").Trim();
            if (!TimeLooksLike(now, dt))
            {
                string readable = dt.ToString("yyyy-MM-dd HH:mm:ss");
                Info("② 标准格式未生效，改用可读格式：" + readable);
                string o2 = ShellCapture("date \"" + readable + "\"");
                if (o2.Trim().Length > 0) Hint("  " + FirstLine(o2).Trim());
                System.Threading.Thread.Sleep(300);
                now = ShellCapture("date").Trim();
            }

            if (TimeLooksLike(now, dt)) Ok("✓ 时间已设置（设备当前：" + now + "）");
            else Warn("设置后回读不一致，设备当前：" + (now.Length == 0 ? "（空）" : now));

            // 写硬件时钟 —— 不写的话重启会丢
            Info("② hwclock -w（写硬件时钟）");
            string hw = ShellCapture("hwclock -w");
            string hwt = hw.Trim();
            if (hwt.Length == 0 || hwt.IndexOf("No such file", StringComparison.OrdinalIgnoreCase) < 0)
                Ok("  已写入硬件时钟");
            else
                Warn("  写入失败（本机可能没有 RTC）：" + FirstLine(hwt).Trim());
            Hint("  没有 RTC 的机器重启后时间会恢复，属正常");
        }

        internal static void DoTimeRestore()
        {
            if (!RequireDevice("")) return;

            Info("恢复系统时间同步");
            Blank();

            Info("① 启用工程模式 com.android.engmode");
            string o1 = ShellCapture("pm enable com.android.engmode");
            if (o1.Trim().Length > 0) Hint("  " + FirstLine(o1).Trim());

            Info("② 启用时间同步 com.gxa.car.timesync");
            string o2 = ShellCapture("pm enable com.gxa.car.timesync");
            if (o2.Trim().Length > 0) Hint("  " + FirstLine(o2).Trim());

            Info("③ 恢复系统自动时间 / 自动时区");
            ShellCapture("shell settings put global auto_time 1");
            ShellCapture("shell settings put global auto_time_zone 1");

            Blank();
            Ok("✓ 已恢复。设备会自行通过网络校时");
            Hint("若时间仍不对，可在车机设置里手动开一次「自动设置时间」");
        }

        // ====================================================================
        //  1.12 地图激活（激活码由页面输入）
        // ====================================================================
        //
        //  流程：
        //    setprop sys.vehicle.hardware.map.active.code <激活码>
        //    am force-stop <地图包>        ← 让地图重新读取激活码
        internal static void DoMapActivate(string code)
        {
            if (!RequireDevice("")) return;

            string c = (code == null ? "" : code).Trim();
            if (c.Length == 0)
            {
                Warn("没有输入激活码");
                Hint("在卡片输入框里填激活码（数字 + 26 字母）");
                return;
            }
            // 只允许字母数字 —— 用户要求"支持数字和26字母"
            for (int i = 0; i < c.Length; i++)
            {
                char ch = c[i];
                bool okch = (ch >= '0' && ch <= '9')
                         || (ch >= 'a' && ch <= 'z')
                         || (ch >= 'A' && ch <= 'Z');
                if (!okch)
                {
                    Fail("激活码只能包含数字和字母，发现非法字符：" + ch);
                    return;
                }
            }

            Info("地图激活");
            Info("① setprop sys.vehicle.hardware.map.active.code " + c);
            ShellCapture("setprop sys.vehicle.hardware.map.active.code " + c);

            // 回读确认
            System.Threading.Thread.Sleep(250);
            string cur = ShellCapture("getprop sys.vehicle.hardware.map.active.code").Trim();
            if (cur == c) Ok("  ✓ 已写入（回读：" + cur + "）");
            else Warn("  回读不一致：期望 " + c + "，实际 " + (cur.Length == 0 ? "（空）" : cur));

            Info("② 重启地图进程让激活码生效");
            string o = ShellCapture("am force-stop " + MAP_PKG);
            if (o.Trim().Length > 0) Hint("  " + FirstLine(o).Trim());
            Ok("✓ 已完成。请手动打开地图确认激活状态");
        }

        // ====================================================================
        //  辅助
        // ====================================================================

        // 跑设备 shell 并返回完整输出（stdout+stderr）
        /* 2026-11-27（D9）：root / remount 是主机端 adb 命令，不能进设备 shell。 */
        private static string HostCapture(string cmd)
        {
            string o = "", e = "";
            try { AdbCall(new List<string> { cmd }, out o, out e); } catch { }
            return ((o ?? "") + (e ?? "")).Trim();
        }

        private static string ShellCapture(string cmd)
        {
            string o = "", e = "";
            try
            {
                ShellCall(CUR, cmd, out o, out e);
                return ((o ?? "") + (e ?? "")).Trim();
            }
            catch { return ""; }
        }

        // 正则取第一个分组
        private static string FirstMatch(string text, string pattern)
        {
            if (string.IsNullOrEmpty(text)) return "";
            try
            {
                System.Text.RegularExpressions.Match m =
                    System.Text.RegularExpressions.Regex.Match(text, pattern,
                        System.Text.RegularExpressions.RegexOptions.Multiline);
                return m.Success && m.Groups.Count > 1 ? m.Groups[1].Value.Trim() : "";
            }
            catch { return ""; }
        }

        // grep 参数转义：包名里有 '.'，当正则用会变通配符
        private static string EscapeGrep(string s)
        {
            if (s == null) return "";
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < s.Length; i++)
            {
                char c = s[i];
                if (c == '.' || c == '[' || c == ']' || c == '\\' || c == '*' || c == '^'
                    || c == '$' || c == '+' || c == '?' || c == '(' || c == ')' || c == '|')
                    sb.Append('\\');
                sb.Append(c);
            }
            return sb.ToString();
        }

        // 回读的 date 输出形如 "Sun Nov 22 18:00:00 CST 2026"
        // 只比较到分钟就够（秒可能因为往返延迟差几秒）
        private static bool TimeLooksLike(string deviceDate, DateTime want)
        {
            if (string.IsNullOrEmpty(deviceDate)) return false;
            // 取 "HH:mm" 两段比对
            string[] tokens = deviceDate.Split(new char[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries);
            for (int i = 0; i < tokens.Length; i++)
            {
                string t = tokens[i];
                if (t.Length == 8 && t[2] == ':' && t[5] == ':')
                {
                    string hm = t.Substring(0, 5);
                    if (hm == want.ToString("HH:mm")) return true;
                }
            }
            return false;
        }
    }
}
