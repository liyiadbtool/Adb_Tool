// ============================================================================
//  CmdRegistry.cs — 命令注册表：让工具从"命令集"变成"编排器"
//
//  设计原则（这是整个扩展性的地基）：
//     自定义命令 = 一条带参数的模板，展开后重新走一遍 Dispatch。
//     所以它天然可调用任何已有命令（内置的、adb 的、shell 的、别的自定义命令）。
//
//     刻意【不】提供 if / for / while / 变量作用域 / 函数返回值 ——
//     一旦提供，就是在和 bash、PowerShell 竞争，必输。
//     需要逻辑 → 写 .bat / .ps1，用 type=local 挂进来。
//
//  定义格式（cmds.ini，扩展 ini 分节）：
//     [cmd.net]
//     desc  = 已建立的网络连接
//     group = 网络
//     usage = net
//     run   = shell netstat -anp | grep ESTAB
//
//  模板占位符：
//     $1..$9   位置参数      $*  全部参数原文      $0  命令名
//     $(date)  20261102      $(date-) 2026-11-02  $(time) 153012
//     $(serial) 设备号        $(cur) 当前目录       $(app) 目标包名
// ============================================================================
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

namespace AdbLogExport
{
    internal static partial class App
    {
        // 一条自定义命令的定义
        internal class CmdDef
        {
            internal string Name = "";
            internal string Desc = "";
            internal string Group = "其他";
            internal string Usage = "";
            internal string Run = "";
            internal string Type = "";      // 预留：auto / shell / adb / local
        }

        private static readonly Dictionary<string, CmdDef> CMDS =
            new Dictionary<string, CmdDef>(StringComparer.OrdinalIgnoreCase);

        // 保序，用于 help 与 cmds 列表
        private static readonly List<string> CMD_ORDER = new List<string>();

        // 给 GUI 用的只读快照：快捷指令页据此把 cmds.ini 里的自定义命令
        // 自动收进「自定义命令」分组，不用再去改 ui.html 里的硬编码列表。
        internal static List<CmdDef> CmdList()
        {
            List<CmdDef> r = new List<CmdDef>();
            for (int i = 0; i < CMD_ORDER.Count; i++)
            {
                CmdDef d;
                if (CMDS.TryGetValue(CMD_ORDER[i], out d) && d != null) r.Add(d);
            }
            return r;
        }

        // 递归保护：自定义命令可以调用自定义命令，但不能无限套
        private const int MAX_EXPAND_DEPTH = 8;
        private static int EXPAND_DEPTH = 0;

        // 目标包名（供 $(app) 使用，写在 ini 的 app 键）
        internal static string APP_PKG = "";

        // 最近一次自定义命令展开后的完整命令（供 GUI 反馈窗口展示实际执行内容）
        internal static string LAST_EXPANDED = "";

        internal static bool CMD_HELP_ONLY = false;

        // ==================== 一、加载 ====================
        internal static void LoadCmds()
        {
            // 2026-11-19：新布局把配置放 internal\；老布局仍在 exe 同级。
            // 顺序：internal 存在就用 internal（发布包），否则用 exe 同级（便携/源码）。
            string path = Path.Combine(ExeDir(), "internal", "cmds.ini");
            if (!File.Exists(path)) path = Path.Combine(ExeDir(), "cmds.ini");

            // 首次运行：把内置脚本包写成模板，用户可以直接改
            if (!File.Exists(path))
            {
                try { File.WriteAllText(path, DEFAULT_CMDS, new UTF8Encoding(false)); }
                catch { }
            }

            string[] lines;
            try
            {
                if (!File.Exists(path)) return;
                lines = File.ReadAllLines(path, Encoding.UTF8);
            }
            catch { return; }

            CmdDef cur = null;

            for (int i = 0; i < lines.Length; i++)
            {
                string s = lines[i].Trim();
                if (s.Length == 0) continue;
                if (s[0] == '#' || s[0] == ';') continue;

                // [cmd.名字]
                if (s[0] == '[' && s[s.Length - 1] == ']')
                {
                    string sec = s.Substring(1, s.Length - 2).Trim();
                    if (sec.Length > 4 && string.Equals(sec.Substring(0, 4), "cmd.", StringComparison.OrdinalIgnoreCase))
                    {
                        string name = sec.Substring(4).Trim();
                        if (name.Length == 0) { cur = null; continue; }

                        cur = new CmdDef();
                        cur.Name = name;

                        if (!CMDS.ContainsKey(name)) CMD_ORDER.Add(name);
                        CMDS[name] = cur;
                    }
                    else
                    {
                        cur = null;   // 不是 cmd.* 分节，忽略其内容
                    }
                    continue;
                }

                if (cur == null) continue;

                int eq = s.IndexOf('=');
                if (eq <= 0) continue;
                string k = s.Substring(0, eq).Trim().ToLowerInvariant();
                string v = s.Substring(eq + 1).Trim();

                if (k == "desc") cur.Desc = v;
                else if (k == "group") cur.Group = v;
                else if (k == "usage") cur.Usage = v;
                else if (k == "run") cur.Run = v;
                else if (k == "type") cur.Type = v;
            }
        }

        // ==================== 二、查询 ====================
        internal static bool HasCmd(string name)
        {
            return !string.IsNullOrEmpty(name) && CMDS.ContainsKey(name);
        }

        // 所有可补全的命令名（内置 + 自定义），用于 Tab 补全
        internal static List<string> AllCmdNames()
        {
            List<string> all = new List<string>();

            string[] builtin = new string[]
            {
                // 裸名白名单（设备语义）
                "cd", "pwd", "ls", "pull", "push", "adb", "shell",
                // : 前缀工具命令
                ":send", ":env", ":pkg", ":which", ":ime", ":h", ":cmds", ":ping",
                ":r", ":rl", ":rr", ":ri", ":rw", ":q",
                ":crash", ":shot",
                // adb 子命令（裸名可用）
                "devices", "install", "uninstall", "reboot",
                "forward", "reverse", "tcpip", "connect", "root", "remount",
                "version", "bugreport", "backup", "sideload", "exec-out"
            };
            for (int i = 0; i < builtin.Length; i++) all.Add(builtin[i]);
            for (int i = 0; i < CMD_ORDER.Count; i++) all.Add(CMD_ORDER[i]);
            return all;
        }

        // 前缀补全
        internal static List<string> CompleteCmd(string prefix)
        {
            List<string> r = new List<string>();
            if (string.IsNullOrEmpty(prefix)) return r;

            List<string> all = AllCmdNames();
            for (int i = 0; i < all.Count; i++)
            {
                if (all[i].Length >= prefix.Length &&
                    string.Equals(all[i].Substring(0, prefix.Length), prefix, StringComparison.OrdinalIgnoreCase))
                {
                    if (!r.Contains(all[i])) r.Add(all[i]);
                }
            }
            r.Sort(StringComparer.OrdinalIgnoreCase);
            return r;
        }

        // ==================== 三、执行 ====================
        // 命中返回 true（含执行失败），未命中返回 false 交给后续分支
        internal static bool TryRunCmd(string name, string argRaw)
        {
            CmdDef d;
            if (!CMDS.TryGetValue(name, out d)) return false;

            if (string.IsNullOrEmpty(d.Run))
            {
                Fail("命令 " + name + " 没有写 run 字段");
                return true;
            }

            // 参数保卫：模板里没有 $ 占位却传了参数，说明用户以为能传 ——
            // 以前是静默丢弃（用起来像"命令没生效"），现在必须明确报错。
            if (argRaw != null && argRaw.Trim().Length > 0 && d.Run.IndexOf("$") < 0)
            {
                Fail(":" + name + " 不接收参数（cmds.ini 里的 run 没有 $ 占位）");
                Hint("直接输入 :" + name + " 即可；要传参请在 run 里写 $1 / $*");
                return true;
            }

            if (EXPAND_DEPTH >= MAX_EXPAND_DEPTH)
            {
                Fail("命令嵌套超过 " + MAX_EXPAND_DEPTH + " 层，可能存在循环调用：" + name);
                Hint("检查 cmds.ini 里是否有 A 调用 B、B 又调用 A");
                return true;
            }

            string expanded = ExpandTemplate(d.Run, argRaw, name);

            // 记录本次展开后的完整命令（供 GUI 反馈窗口展示"实际执行的命令"）
            LAST_EXPANDED = expanded;

            // 需求4：只回显实际展开的命令，去掉命令名 + 中间的 →（原为 name → expanded）
            Echo("cmd", expanded);

            EXPAND_DEPTH++;
            try
            {
                Dispatch(expanded);
            }
            finally
            {
                EXPAND_DEPTH--;
            }
            return true;
        }

        // ==================== 四、模板展开 ====================
        internal static string ExpandTemplate(string tpl, string argRaw, string cmdName)
        {
            if (string.IsNullOrEmpty(tpl)) return "";

            List<string> args = SplitArgs(argRaw == null ? "" : argRaw);

            StringBuilder sb = new StringBuilder();
            int i = 0;

            while (i < tpl.Length)
            {
                char ch = tpl[i];

                if (ch == '$' && i + 1 < tpl.Length && tpl[i + 1] == '(')
                {
                    int close = tpl.IndexOf(')', i + 2);
                    if (close > 0)
                    {
                        string fn = tpl.Substring(i + 2, close - i - 2).Trim().ToLowerInvariant();
                        sb.Append(EvalFunc(fn, args));
                        i = close + 1;
                        continue;
                    }
                }

                if (ch == '$' && i + 1 < tpl.Length)
                {
                    char n = tpl[i + 1];

                    if (n >= '1' && n <= '9')
                    {
                        int idx = n - '1';
                        if (idx < args.Count) sb.Append(args[idx]);
                        i += 2;
                        continue;
                    }
                    if (n == '*')
                    {
                        sb.Append(argRaw == null ? "" : argRaw.Trim());
                        i += 2;
                        continue;
                    }
                    if (n == '0')
                    {
                        sb.Append(cmdName);
                        i += 2;
                        continue;
                    }
                }

                sb.Append(ch);
                i++;
            }

            return sb.ToString();
        }

        private static string EvalFunc(string fn, List<string> args)
        {
            if (fn == "date") return DateTime.Now.ToString("yyyyMMdd");
            if (fn == "date-") return DateTime.Now.ToString("yyyy-MM-dd");
            if (fn == "time") return DateTime.Now.ToString("HHmmss");
            if (fn == "datetime") return DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss");
            if (fn == "serial") return string.IsNullOrEmpty(DEVID) ? "device" : DEVID;
            if (fn == "cur") return CUR;
            if (fn == "app") return string.IsNullOrEmpty(APP_PKG) ? "" : APP_PKG;
            if (fn == "desktop") return DesktopPath();
            if (fn == "argc") return args.Count.ToString();
            // 分类导出目录（需求：导出按 日期/分类 两级存放）
            //   $(out:shot)   -> 桌面\logcat\2026-11-10\screencap
            //   $(out:rec)    -> 桌面\logcat\2026-11-10\screenrecord
            //   $(out:hci)    -> 桌面\logcat\2026-11-10\HCI
            //   $(out)        -> 桌面\logcat\2026-11-10        （不带分类）
            //
            // 用"精确等于 out"或"out: 前缀"判断，不要直接 StartsWith("out")——
            // 那样以后加个 $(output) / $(outfile) 之类的函数会被这里先截走。
            if (fn == "out")
            {
                return OutDir("");
            }
            if (fn.StartsWith("out:", StringComparison.Ordinal))
            {
                string kind = fn.Substring(4).Trim();
                return OutDir(kind);
            }
            return "";
        }

        // 桌面物理路径（供 $(desktop) 使用，导出日志到桌面用）
        private static string DesktopPath()
        {
            try
            {
                string d = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
                return string.IsNullOrEmpty(d) ? "C:\\" : d;
            }
            catch { return "C:\\"; }
        }

        // ==================== 分类导出目录 ====================
        //
        // 需求（2026-11-10 晚）：导出的文件原来全丢在 桌面\logcat 一个平铺目录里，
        // 时间一长几千个文件混在一起，找一次截图要翻半天。
        // 改成两级：桌面\logcat\2026-11-10\screencap
        //                        └─日期─┘ └─分类─┘
        //
        // 分类名用英文，是固定的三种：
        //   screencap    截图（shot）
        //   screenrecord 录屏（rec）
        //   HCI          HCI 蓝牙日志（hci）
        // 其它类型走 logcat 根（kind 为空就只到日期层）。
        //
        // 目录在这里**即时创建**：调用方拿到路径就直接写文件，
        // 如果目录不存在，重定向（`> path`）会直接失败。
        // CreateDirectory 对已存在的目录是幂等的，反复调用无害。
        /* ===== 2026-11-25：指令级自定义导出路径 =====
           规则（用户确认的 A 方案，严格互斥）：
             设了自定义 → 只写自定义目录，默认目录**完全不碰**（连目录都不建）
             没设       → 只写默认目录
             自定义不可写 → 回退默认，只写一份
           存储：%LOCALAPPDATA%\adb_Tool\export_paths.json  { "apk": "D:////导出" }
           变量：${date} ${kind} ${serial} ${pkg} */
        [System.ThreadStatic] internal static string CUR_EXPORT_ID = "";

        private static Dictionary<string, string> _exportPaths = null;
        private static string ExportPathsFile()
        {
            string dir = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "adb_Tool");
            try { Directory.CreateDirectory(dir); } catch { }
            return Path.Combine(dir, "export_paths.json");
        }
        private static Dictionary<string, string> ExportPaths()
        {
            if (_exportPaths != null) return _exportPaths;
            var map = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            try
            {
                string f = ExportPathsFile();
                if (File.Exists(f))
                {
                    string txt = File.ReadAllText(f, Encoding.UTF8);
                    // 极简解析：{"k":"v",...}，避免引入 json 依赖
                    var ms = System.Text.RegularExpressions.Regex.Matches(txt, "\"([^\"]+)\"\\s*:\\s*\"((?:[^\"\\\\]|\\\\.)*)\"");
                    for (int i = 0; i < ms.Count; i++)
                        map[ms[i].Groups[1].Value] = System.Text.RegularExpressions.Regex.Unescape(ms[i].Groups[2].Value);
                }
            }
            catch { }
            _exportPaths = map;
            return map;
        }
        internal static void SetExportPath(string cmdId, string path)
        {
            var map = ExportPaths();
            if (string.IsNullOrEmpty(path)) map.Remove(cmdId ?? "");
            else map[cmdId] = path;
            try
            {
                var sb = new StringBuilder("{");
                bool first = true;
                foreach (var kv in map)
                {
                    if (!first) sb.Append(",");
                    first = false;
                    sb.Append("\"").Append(kv.Key.Replace("\\", "\\\\").Replace("\"", "\\\""))
                      .Append("\":\"").Append(kv.Value.Replace("\\", "\\\\").Replace("\"", "\\\""))
                      .Append("\"");
                }
                sb.Append("}");
                File.WriteAllText(ExportPathsFile(), sb.ToString(), Encoding.UTF8);
            }
            catch { }
        }
        internal static string GetExportPath(string cmdId)
        {
            if (string.IsNullOrEmpty(cmdId)) return "";
            string v;
            return ExportPaths().TryGetValue(cmdId, out v) ? (v ?? "") : "";
        }
        private static string ExpandOutVars(string p, string kind)
        {
            if (string.IsNullOrEmpty(p)) return p;
            return p.Replace("${date}", DateTime.Now.ToString("yyyy-MM-dd"))
                    .Replace("${kind}", OutKindFolder(kind))
                    .Replace("${serial}", DEVID ?? "")
                    .Replace("${pkg}", "");
        }

        /// <summary>唯一的取目录入口：自定义与默认二选一，绝不两者都写。</summary>
        internal static string OutDirFor(string cmdId, string kind)
        {
            string custom = GetExportPath(cmdId);
            if (!string.IsNullOrEmpty(custom))
            {
                string path = ExpandOutVars(custom.Trim(), kind);
                try
                {
                    Directory.CreateDirectory(path);
                    return path;                       // 用了自定义就不再碰默认目录
                }
                catch
                {
                    Warn("自定义导出路径不可用，已回退默认：" + path);
                }
            }
            return DefaultOutDir(kind);
        }

        internal static string OutDir(string kind)
        {
            return OutDirFor(CUR_EXPORT_ID, kind);
        }

        private static string DefaultOutDir(string kind)
        {
            string root = Path.Combine(DesktopPath(), "logcat");

            // 日期层：用本地时间，yyyy-MM-dd（与用户口径一致）
            string day = DateTime.Now.ToString("yyyy-MM-dd");
            string dir = Path.Combine(root, day);

            string sub = OutKindFolder(kind);
            if (sub.Length > 0) dir = Path.Combine(dir, sub);

            try { Directory.CreateDirectory(dir); }
            catch { /* 建不出来就返回路径，让调用方报错，别在这吞掉 */ }

            return dir;
        }

        // 分类关键字 → 目录名。接受几种常见写法，避免调用方记不住。
        internal static string OutKindFolder(string kind)
        {
            if (string.IsNullOrEmpty(kind)) return "";
            string k = kind.Trim().ToLowerInvariant();

            if (k == "shot" || k == "screencap" || k == "screenshot" || k == "截图")
                return "screencap";
            if (k == "rec" || k == "screenrecord" || k == "video" || k == "录屏")
                return "screenrecord";
            if (k == "hci" || k == "btsnoop" || k == "bluetooth" || k == "蓝牙")
                return "HCI";
            // 未知类型：原样当目录名（小写化会破坏大小写，这里保留原文）
            return kind.Trim();
        }

        // ==================== 五、命令发现 ====================
        // cmds 命令：按分组列出所有自定义命令
        internal static void ListCmds()
        {
            if (CMD_ORDER.Count == 0)
            {
                Info("没有自定义命令。cmds.ini 不存在或为空");
                Hint("在同目录建一个 cmds.ini，格式见 h 里的说明");
                return;
            }

            Console.WriteLine();

            List<string> groups = new List<string>();
            for (int i = 0; i < CMD_ORDER.Count; i++)
            {
                CmdDef d = CMDS[CMD_ORDER[i]];
                if (!groups.Contains(d.Group)) groups.Add(d.Group);
            }
            groups.Sort(StringComparer.OrdinalIgnoreCase);

            for (int g = 0; g < groups.Count; g++)
            {
                Console.WriteLine("  [" + groups[g] + "]");
                for (int i = 0; i < CMD_ORDER.Count; i++)
                {
                    CmdDef d = CMDS[CMD_ORDER[i]];
                    if (d.Group != groups[g]) continue;

                    UsePath();
                    Console.Write("    " + d.Name);
                    UseDefault();

                    int pad = 18 - DispWidth(d.Name);
                    for (int k = 0; k < pad; k++) Console.Write(' ');

                    UseDim();
                    if (CmdBareOk(d.Name))
                        Console.WriteLine(d.Desc);
                    else
                        Console.WriteLine(d.Desc + "   [只能用 :" + d.Name + "，裸名属于设备]");
                    UseDefault();
                }
                Console.WriteLine();
            }

            UseDim();
            Console.WriteLine("  共 " + CMD_ORDER.Count + " 条 · 定义文件：" + Path.Combine(ExeDir(), "cmds.ini"));
            UseDefault();
        }

        // 单条命令的用法
        internal static void CmdUsage(string name)
        {
            CmdDef d;
            if (!CMDS.TryGetValue(name, out d))
            {
                Fail("没有这个命令：" + name);
                Hint("输入 cmds 查看全部自定义命令");
                return;
            }

            Console.WriteLine();
            Console.WriteLine("  " + d.Name + "  —— " + d.Desc);
            if (!string.IsNullOrEmpty(d.Usage))
            {
                UseDim();
                Console.WriteLine("  用法：" + d.Usage);
                UseDefault();
            }
            UseDim();
            Console.WriteLine("  展开：" + d.Run);
            UseDefault();
            Console.WriteLine();
        }

        // ==================== 六、内置脚本包 ====================
        // 只在 cmds.ini 不存在时生成一份最小模板；完整版见项目根目录的 cmds.ini
        //
        // 重要：run 里若要写设备侧管道，必须用双引号包住整条命令 ——
        //   shell "dumpsys meminfo | head -30"      ← | 在引号内 => 设备侧  ✓
        //   shell dumpsys meminfo | head -30        ← | 在引号外 => 本地管道 ✗
        private const string DEFAULT_CMDS =
"# ============================================================================\n" +
"#  cmds.ini — 自定义命令（DIY 指令）\n" +
"#  格式：[cmd.命令名]，下面跟 desc / group / usage / run\n" +
"#  run 里可以调用任何已有命令（内置的、adb 的、shell 的、别的自定义命令）\n" +
"#\n" +
"#  占位符：$1..$9 位置参数   $* 全部参数   $0 命令名\n" +
"#          $(date) 20261102  $(date-) 2026-11-02  $(time) 153012\n" +
"#          $(serial) 设备号   $(cur) 当前目录   $(app) ini 里的 app\n" +
"#          $(desktop)         桌面路径\n" +
"#          $(out:shot)        桌面\\logcat\\<今天>\\screencap      （截图）\n" +
"#          $(out:rec)         桌面\\logcat\\<今天>\\screenrecord  （录屏）\n" +
"#          $(out:hci)         桌面\\logcat\\<今天>\\HCI           （蓝牙日志）\n" +
"#          $(out)             桌面\\logcat\\<今天>                （不分分类）\n" +
"#          注：$(out:*) 会把目录建好再返回路径，可直接用于 > 重定向\n" +
"#\n" +
"#  【管道注意】run 里写设备侧管道要用双引号包住整条命令：\n" +
"#      run = shell \"dumpsys meminfo | head -30\"\n" +
"#    否则 | 会被当成本地管道。\n" +
"#\n" +
"#  【命名注意】别用设备上已有的命令名（kill / clear / ping / ps / top ...），\n" +
"#  否则会抢掉透传，想用设备原版得写 !kill。\n" +
"#\n" +
"#  超过 5 行的逻辑请写成 .bat / .ps1，不要在这里堆\n" +
"# ============================================================================\n" +
"\n" +
"[cmd.l]\n" +
"desc = 列目录（ls 简写）\n" +
"group = 别名\n" +
"run = ls\n" +
"\n" +
"[cmd.crash]\n" +
"desc = 崩溃日志缓冲区\n" +
"group = 日志\n" +
"run = logcat -d -b crash\n";
    }
}
