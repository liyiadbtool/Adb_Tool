// ============================================================================
//  AdbCmd.cs — adb 层子命令的直接输入（v6.1 新增）
//
//  解决的问题：
//     旧版把"未识别输入"一律拼成  adb shell "cd <CUR> && <输入>"，
//     于是 adb devices / adb install / adb reboot 这类 **adb 层**命令
//     会被送进设备 shell，报 "adb: not found" —— adb 命令根本用不了。
//
//  本文件补上这一层，规则如下（全部不破坏原有 adb/shell 输入）：
//     ① adb <子命令> ...      显式前缀，零歧义，一律走 adb
//     ② <裸白名单子命令>       如 devices / install / reboot，也走 adb
//     ③ adb shell <命令>      剥掉 shell 前缀，等价于直接输入命令（保持当前目录）
//     ④ 含 > >> < | 的        交给 cmd /c 本地执行，支持重定向（screencap 存图等）
//
//  为什么要"白名单"而不是"全放行"：
//     pm / am / dumpsys / getprop / screencap / input 这些是**设备命令**，
//     本来就该走 shell（现状已正确）；如果也当 adb 子命令，反而会坏掉。
//     白名单只收"设备 shell 上不存在或极少使用"的那些。
// ============================================================================
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;

namespace AdbLogExport
{
    internal static partial class App
    {
        // adb 专属子命令白名单（设备 shell 上不存在或极少用）
        // 注意：不要往里加 pm / am / wm / dumpsys / settings / content / input /
        //       screencap / screenrecord / getprop / setprop / monkey —— 那些是设备命令
        private static readonly string[] ADB_SUBCMDS = new string[]
        {
            "devices",
            "connect", "disconnect", "pair",
            "forward", "reverse", "tcpip", "usb",
            "install", "uninstall", "install-multiple", "install-multi",
            "bugreport", "backup", "restore", "sideload",
            "wait-for-device", "get-state", "get-serialno", "get-devpath",
            "start-server", "kill-server", "version",
            "exec-out", "exec-in",
            "root", "unroot", "remount", "disable-verity", "enable-verity",
            "reboot", "reboot-bootloader",
            "mdns", "jdwp", "attach", "detach"
        };

        internal static bool IsAdbSubcmd(string c)
        {
            if (string.IsNullOrEmpty(c)) return false;
            for (int i = 0; i < ADB_SUBCMDS.Length; i++)
            {
                if (string.Equals(ADB_SUBCMDS[i], c, StringComparison.OrdinalIgnoreCase)) return true;
            }
            return false;
        }

        // ==================== ① adb 前缀 ====================
        private static void DoAdbPrefix(string argRaw)
        {
            string t = (argRaw == null) ? "" : argRaw.Trim();
            if (t.Length == 0) { AdbUsage(); return; }

            List<string> toks = SplitArgs(t);
            if (toks.Count == 0) { AdbUsage(); return; }

            // 解析前导 -s <serial>
            string explicitSerial = null;
            int i = 0;
            while (i + 1 < toks.Count && string.Equals(toks[i], "-s", StringComparison.OrdinalIgnoreCase))
            {
                explicitSerial = toks[i + 1];
                i += 2;
            }
            if (i >= toks.Count) { AdbUsage(); return; }

            string sub = toks[i];
            List<string> rest = new List<string>();
            for (int k = i + 1; k < toks.Count; k++) rest.Add(toks[k]);

            // 离线时只放行"能连上设备"或"不依赖设备"的 adb 子命令
            if (OFFLINE)
            {
                string s0 = sub.ToLowerInvariant();
                bool okOffline =
                    s0 == "devices" || s0 == "connect" || s0 == "disconnect" ||
                    s0 == "pair" || s0 == "tcpip" || s0 == "usb" ||
                    s0 == "version" || s0 == "start-server" || s0 == "kill-server" ||
                    s0 == "get-state" || s0 == "wait-for-device" || s0 == "mdns";

                if (!okOffline)
                {
                    Warn("设备未连接，adb " + s0 + " 需要设备在线");
                    Hint("输入 r 重连；或先用 adb devices 看设备列表");
                    return;
                }
            }

            string bak = SERIAL;
            if (explicitSerial != null) SERIAL = explicitSerial;
            try
            {
                // 顺序很重要，这里踩过坑：
                //   adb shell "ls > /sdcard/a"   -> 引号内的 > 是【设备侧】
                //   adb shell getprop | findstr x -> 引号外的 | 是【本地管道】
                // 所以先按"引号外是否出现 > < |"判断走不走本地，
                // 再决定是否走 shell 路由。反过来就会把本地的 | 塞进设备 shell。
                if (HasLocalRedir(t))
                {
                    RunLocalShell(BuildAdbLine(t));
                    return;
                }

                // shell 路由：按原文截取 shell 之后的内容，保留用户引号语义
                if (string.Equals(sub, "shell", StringComparison.OrdinalIgnoreCase))
                {
                    RunAdbShell(AfterToken(t, i + 1));
                    return;
                }

                RunAdbSub(sub, rest);
            }
            finally
            {
                SERIAL = bak;
            }
        }

        // 跳过前 skipCount 个 token，返回剩余原文（保留用户原始引号与空格）
        private static string AfterToken(string s, int skipCount)
        {
            if (string.IsNullOrEmpty(s)) return "";
            int i = 0;
            int n = s.Length;
            int skipped = 0;

            while (skipped < skipCount && i < n)
            {
                while (i < n && (s[i] == ' ' || s[i] == '\t')) i++;
                if (i >= n) return "";
                bool inq = false;
                while (i < n)
                {
                    char ch = s[i];
                    if (ch == '"') { inq = !inq; i++; continue; }
                    if (!inq && (ch == ' ' || ch == '\t')) break;
                    i++;
                }
                skipped++;
            }

            while (i < n && (s[i] == ' ' || s[i] == '\t')) i++;
            return (i < n) ? s.Substring(i) : "";
        }

        // 执行 adb shell <内部命令>：保持当前目录
        private static void RunAdbShell(string innerRaw)
        {
            string inner = Util.Unquote((innerRaw == null) ? "" : innerRaw.Trim());
            if (inner.Length == 0)
            {
                Info("不支持交互式 shell（本工具自身就是交互界面）");
                Hint("直接输入命令即可，路径已自动相对当前目录 " + CUR);
                return;
            }

            // 显式写了 shell，用户已经知道会去设备侧执行 —— 不再回显（少一行噪音）
            string combined = "";
            int rc = ShellCallStream(CUR, inner, out combined);
            if (rc != 0)
            {
                CMD_OK = false;
                if (rc > 0)
                {
                    Fail(ExplainError(combined));
                    string tip = BuildTip(combined);
                    if (tip.Length > 0) Hint("建议：" + tip);
                    else Hint("当前目录可能已失效，输入 r 刷新；或检查命令参数");
                }
                else
                {
                    Info("命令已中断");
                }
            }
            else
            {
                CMD_OK = true;
            }
        }

        // ==================== ② 裸白名单子命令 ====================
        private static void DoAdbBare(string sub, string argRaw)
        {
            string t = (argRaw == null) ? "" : argRaw.Trim();

            // 这是"被接管"的场景：设备上没有 devices/install 这类子命令，
            // 用户敲裸名时工具把它路由到了 adb 层 —— 必须回显，让归属可见。
            Echo("adb", sub + (t.Length > 0 ? " " + t : ""));

            if (HasLocalRedir(t))
            {
                RunLocalShell(BuildAdbLine(sub + (t.Length > 0 ? " " + t : "")));
                return;
            }

            List<string> rest = SplitArgs(t);
            RunAdbSub(sub, rest);
        }

        // ==================== 统一执行 ====================
        private static void RunAdbSub(string sub, List<string> rest)
        {
            string s = sub.ToLowerInvariant();

            // ---- adb shell ... => 保持当前目录，等价于直接输入该命令 ----
            if (s == "shell")
            {
                RunAdbShell(JoinTokens(rest));
                return;
            }

            // ---- devices：美化输出，标出当前使用的设备 ----
            if (s == "devices")
            {
                ShowDevices(rest);
                return;
            }

            // ---- install 系列：先确认 apk 存在，别让 adb 报晦涩的错 ----
            if (s == "install" || s == "install-multiple" || s == "install-multi")
            {
                if (rest.Count == 0)
                {
                    Fail("用法：install <apk 路径>    例：install D:\\app.apk");
                    return;
                }
                string apk = Util.Unquote(rest[0]);
                if (!File.Exists(apk))
                {
                    Fail("找不到文件：" + apk);
                    Hint("可以把 apk 拖进窗口，或写完整路径（含空格请用引号包住）");
                    return;
                }
            }

            // ---- reboot：不再二次确认 ----
            // 原生 adb reboot 从不询问；确认框在单人高频工具里只会训练盲敲，
            // 还给虚假安全感。改为"执行后明确报告状态"（可预期 > 可确认）。
            bool isReboot = (s == "reboot" || s == "reboot-bootloader");

            // ---- 真正执行 ----
            List<string> argv = new List<string>();
            argv.Add(s);
            for (int i = 0; i < rest.Count; i++) argv.Add(rest[i]);

            string o = "";
            string e = "";
            int rc = AdbCall(argv, out o, out e);
            string combined = o + e;

            if (combined.Length > 0) Console.Write(EnsureEndsNewline(combined));

            if (rc != 0)
            {
                CMD_OK = false;
                Fail(ExplainError(combined));
                string tip = BuildTip(combined);
                if (tip.Length > 0) Hint("建议：" + tip);
                return;
            }

            CMD_OK = true;

            // reboot 没有输出，必须补一句状态，否则用户不知道到底执行了没有
            if (isReboot)
            {
                Ok("已发送重启指令，设备将断开数秒");
                Hint("重新连接后输入 :r 刷新；当前目录可能已失效");
                ScanDev();
                return;
            }

            // 会影响设备连接的 adb 命令，执行完顺手刷新设备状态
            if (s == "start-server" || s == "kill-server" || s == "connect" || s == "disconnect")
            {
                ScanDev();
                if (DEVN > 0) Info("当前在线设备：" + DEVN + " 台（" + DEVID + "）");
                else Info("当前没有在线设备");
            }
        }

        // ==================== devices 美化 ====================
        private static void ShowDevices(List<string> rest)
        {
            List<string> argv = new List<string>();
            argv.Add("devices");
            bool longMode = false;
            for (int i = 0; i < rest.Count; i++)
            {
                argv.Add(rest[i]);
                if (string.Equals(rest[i], "-l", StringComparison.OrdinalIgnoreCase)) longMode = true;
            }

            string o = "";
            string e = "";
            int rc = AdbCall(argv, out o, out e);
            if (rc != 0)
            {
                Fail("查询设备失败（退出码 " + rc + "）");
                Hint("确认 adb 可用：adb version；必要时输入 rr 重启 adb 服务");
                return;
            }

            string all = o + e;
            string[] lines = all.Split('\n');

            int online = 0;
            int other = 0;
            string firstOnline = "";
            Console.WriteLine();

            for (int i = 0; i < lines.Length; i++)
            {
                string t = lines[i].TrimEnd('\r').Trim();
                if (t.Length == 0) continue;
                if (t.StartsWith("List of devices")) continue;

                string[] f = t.Split(new char[] { '\t', ' ' }, StringSplitOptions.RemoveEmptyEntries);
                if (f.Length < 2) continue;

                string id = f[0];
                string state = f[1];

                if (state == "device")
                {
                    online++;
                    if (firstOnline.Length == 0) firstOnline = id;
                    bool isCurrent = false;
                    if (!string.IsNullOrEmpty(SERIAL)) isCurrent = string.Equals(SERIAL, id, StringComparison.OrdinalIgnoreCase);
                    else if (online == 1) isCurrent = true;

                    string mark = isCurrent ? "  <= 当前使用" : "";
                    Console.WriteLine("  [在线] " + id + mark);
                    if (longMode && f.Length > 2)
                    {
                        StringBuilder extra = new StringBuilder();
                        for (int k = 2; k < f.Length; k++)
                        {
                            if (k > 2) extra.Append(' ');
                            extra.Append(f[k]);
                        }
                        Console.WriteLine("          " + extra.ToString());
                    }
                }
                else
                {
                    other++;
                    Console.WriteLine("  [" + state + "] " + id);
                }
            }

            Console.WriteLine();

            if (online == 0)
            {
                Fail("没有在线的设备");
                Hint("检查数据线、USB 调试开关、手机上的授权弹窗");
                CMD_OK = false;
                return;
            }

            Ok("在线 " + online + " 台" + (other > 0 ? "，异常 " + other + " 台" : ""));

            // 顺手同步全局状态，避免后续命令用到过期信息
            ScanDev();
        }

        // ==================== 本地重定向支持 ====================
        // 只认【引号外】的 > >> < | ：引号内属于设备侧语义
        //   adb exec-out screencap -p > a.png   -> 本地（引号外）
        //   adb shell "ls > /sdcard/a"          -> 设备侧（引号内，不触发）
        private static bool HasLocalRedir(string s)
        {
            if (string.IsNullOrEmpty(s)) return false;
            bool inq = false;
            for (int i = 0; i < s.Length; i++)
            {
                char ch = s[i];
                if (ch == '"') { inq = !inq; continue; }
                if (inq) continue;
                if (ch == '>' || ch == '<' || ch == '|') return true;
            }
            return false;
        }

        // 引号外查找指定字符，返回下标；找不到返回 -1
        internal static int IndexOfOutsideQuotes(string s, char target)
        {
            if (string.IsNullOrEmpty(s)) return -1;
            bool inq = false;
            for (int i = 0; i < s.Length; i++)
            {
                char ch = s[i];
                if (ch == '"') { inq = !inq; continue; }
                if (!inq && ch == target) return i;
            }
            return -1;
        }

        // 拼出一条完整本地命令行：<adb> [-s serial] <用户原文>
        private static string BuildAdbLine(string rest)
        {
            StringBuilder sb = new StringBuilder();
            if (ADB.IndexOf(' ') >= 0 && !ADB.StartsWith("\"")) sb.Append('"').Append(ADB).Append('"');
            else sb.Append(ADB);
            if (!string.IsNullOrEmpty(SERIAL)) sb.Append(" -s ").Append(SERIAL);
            if (!string.IsNullOrEmpty(rest)) sb.Append(' ').Append(rest);
            return sb.ToString();
        }

        // 用 cmd /c 执行：> 重定向由 cmd 处理
        //
        // 【需求1·截图时不要弹黑窗】这里原来写 CreateNoWindow = false，
        // 意思是"让子进程用父进程的控制台"。命令行版没问题（本来就有控制台），
        // 但 GUI 版是 WinExe、根本没有控制台 —— 于是 Windows 给这个子进程
        // **新建一个控制台窗口**，用户每点一次一键截图就闪一个黑框出来。
        //
        // 改成 CreateNoWindow = true 后，子进程没有窗口。
        // 输出会不会丢？不会 —— GUI 版的 stdout 早被 GuiSink（TextWriter 子类）
        // 接管了，是进程内对象，跟有没有控制台窗口无关。
        //
        // 唯一要注意的是重定向：UseShellExecute=false + CreateNoWindow=true 时
        // 子进程没有控制台，cmd 的 `>` 重定向依然由 cmd 自己处理（这是 cmd 的
        // 语法，不是外壳功能），所以 `adb exec-out screencap -p > a.png` 照常生效。
        // 构造 cmd.exe 的参数串。抽成独立纯函数是为了能被 SelfTest 断言覆盖 ——
        // 引号层数光靠肉眼看代码看不出来，必须让机器盯着。
        //
        // 为什么是 `/s /c "整行"` 而不是 `/c 整行`：
        //   cmd.exe 的引号剥离规则（见 `cmd /?`）——
        //     规则1：整行"恰好两个引号"、两引号之间无特殊字符、中间有空格、
        //            且第一段是可执行文件名 —— 才保留引号；
        //     规则2：其余情况一律【剥掉行首第一个引号 + 行尾最后一个引号】。
        //   一旦 adb 安装路径里有空格，命令行就会成为
        //     "C:\Program Files\...\adb.exe" shell "cd '/' && getprop" | findstr x
        //   共 4 个引号 → 命中规则2 → 首引号与行尾引号被剥掉，整行解析错位。
        //   加 /s 后 cmd 只剥掉"我们自己加的这对最外层引号"，内层引号原样保留。
        //
        // 诚实说明：这个 bug 在【当前这台机器上】没有暴露，因为本机 adb 路径
        // 不含空格（C:\Users\...\platform-tools\adb.exe），cmd 恰好没触发规则2。
        // 它修的是"路径带空格就全盘失效"的隐患，不是零输出的根因 ——
        // 零输出的根因在 RunLocalShell 没有重定向子进程输出，见那里的注释。
        internal static string BuildCmdArgs(string cmdLine)
        {
            if (cmdLine == null) cmdLine = "";
            return "/s /c \"" + cmdLine + "\"";
        }

        private static void RunLocalShell(string cmdLine)
        {
            Console.WriteLine("  $ " + cmdLine);

            string comspec = Environment.GetEnvironmentVariable("COMSPEC");
            if (string.IsNullOrEmpty(comspec)) comspec = "cmd.exe";

            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = comspec;

            // 引号层：见 BuildCmdArgs 的说明（/s /c 是为了防"路径带空格"）。
            psi.Arguments = BuildCmdArgs(cmdLine);
            psi.UseShellExecute = false;
            // 需求1：不弹黑窗。GUI（WinExe）没有控制台，false 会让每个子进程
            // 新建一个控制台窗口 —— 截图/录屏时黑框乱闪。
            psi.CreateNoWindow = true;

            // 【2026-11-12 修复】必须重定向子进程的输出，否则 GUI 版静默丢结果。
            //
            // 原来的问题（真机实测）：
            //     getprop | findstr navi   -> 打印了 `$ ...adb.exe shell ... | findstr navi`
            //                                 然后一行结果都没有，退出码却是 0
            //     adb devices | findstr device -> 同样零输出
            // 排查时最容易被误判成"引号拼错了"，但用 ProcessStartInfo 逐字节
            // 复现 argv 后确认 adb 收到的参数完全正确：
            //     ARGV=["shell", "cd '/' && getprop"]
            // 也就是说命令跑对了，只是【输出没人接】。
            //
            // 原因：GUI 版是 winexe，本身没有控制台；而且启动时
            //     Console.SetOut(new GuiSink())
            // 把 stdout 换成了一个内存里的 TextWriter。子进程通过 CreateProcess
            // 继承的是【操作系统句柄】，拿不到这个内存对象 —— 于是 cmd 把输出
            // 写到"没有接收方"的地方，直接丢弃。退出码仍是 0，所以看起来"成功"。
            //
            // 修法：自己开管道把子进程的 stdout/stderr 读回来，逐行写进 Console，
            // 这样输出才会落进 GuiSink / 控制台。与 AdbCallStream 的处理方式一致。
            //
            // 顺带的好处：cmd 内部用 `>` 重定向到文件时（exec-out screencap -p > a.png），
            // 那份输出本来就不经过 stdout，重定向成空管道不影响它，截图照常落盘。
            psi.RedirectStandardOutput = true;
            psi.RedirectStandardError = true;
            psi.StandardOutputEncoding = new UTF8Encoding(false);
            psi.StandardErrorEncoding = new UTF8Encoding(false);

            try
            {
                using (Process p = Process.Start(psi))
                {
                    // 逐行转发，而不是先读完再整体写：截图/大输出时不会憋住内存，
                    // 用户也能像在 cmd 里那样边跑边看到。
                    // C# 5.0 限制，这里用 delegate 而不是 lambda。
                    p.OutputDataReceived += new DataReceivedEventHandler(
                        delegate(object sender, DataReceivedEventArgs ev)
                        {
                            if (ev.Data == null) return;
                            try { Console.WriteLine(ev.Data); } catch { }
                        });
                    p.ErrorDataReceived += new DataReceivedEventHandler(
                        delegate(object sender, DataReceivedEventArgs ev)
                        {
                            if (ev.Data == null) return;
                            try { Console.Error.WriteLine(ev.Data); } catch { }
                        });

                    p.BeginOutputReadLine();
                    p.BeginErrorReadLine();

                    p.WaitForExit();

                    // 第二次 WaitForExit 是 .NET 的既定用法：等异步读取把管道里
                    // 剩下的行全部回调完，否则最后几行偶尔会丢。
                    p.WaitForExit();

                    if (p.ExitCode != 0)
                    {
                        CMD_OK = false;
                        Fail("命令返回非 0（退出码 " + p.ExitCode + "）");
                    }
                    else
                    {
                        CMD_OK = true;
                    }
                }
            }
            catch (Exception ex)
            {
                CMD_OK = false;
                Fail("执行失败：" + ex.Message);
            }
        }

        // ==================== 裸命令的本地管道 ====================
        // getprop | findstr navi  -> 用户想【本地】过滤（findstr 是 Windows 命令）
        // ps | grep xxx           -> 设备侧过滤（grep 是设备命令）
        // 判据：管道右侧第一个 token 是不是 Windows 专有命令
        private static readonly string[] WIN_PIPE_CMDS = new string[]
        {
            "findstr", "findstr.exe", "find", "find.exe",
            "sort", "sort.exe", "more", "more.com"
        };

        internal static bool IsLocalPipe(string line)
        {
            int p = IndexOfOutsideQuotes(line, '|');
            if (p < 0) return false;

            string right = line.Substring(p + 1).Trim();
            if (right.Length == 0) return false;

            int e = 0;
            while (e < right.Length && right[e] != ' ' && right[e] != '\t') e++;
            string first = right.Substring(0, e);

            for (int i = 0; i < WIN_PIPE_CMDS.Length; i++)
            {
                if (string.Equals(WIN_PIPE_CMDS[i], first, StringComparison.OrdinalIgnoreCase)) return true;
            }
            return false;
        }

        // 执行 "<设备命令> | <本地过滤器>"
        //
        // 【2026-11-12 修复记录】这里以前表现为：`getprop | findstr navi` 明明
        // 设备上有 10 条命中，工具却 **rc=0 且一行不输出**（不报错，比报错更难查）。
        //
        // 排查时走过一段弯路，值得留档：
        //   · 第一反应是"引号拼错了"——因为手工在 cmd 里粘这条命令能出结果，
        //     用 argv 形式跑 adb 也正常，只有工具跑不出来。
        //   · 于是去改拼法、加 ^ 转义、加 /s，一度以为修好了。
        //   · 但用 ProcessStartInfo 逐字节复现 argv 之后真相才出来：
        //         ARGV=["shell", "cd '/' && getprop"]      ← 完全正确
        //     命令本身跑得没问题，问题是【输出没人接】。
        //
        // 真正的原因在 RunLocalShell：它 Process.Start 时没重定向子进程输出。
        // GUI 版是 winexe，没有控制台，且 Console.SetOut 换成了内存里的 GuiSink；
        // 子进程继承的是操作系统句柄，拿不到那个内存对象 —— cmd 的输出被直接丢弃，
        // 退出码仍是 0。所以这里一行业务逻辑都不用改，修的是 RunLocalShell。
        //
        // 结论：本方法保持原拼法。不要为了"躲开 cmd"而改成 argv 形式 ——
        // `| findstr` 是 cmd 的管道语法，绕开 cmd 管道就永远到不了 findstr。
        internal static void RunShellPipe(string line)
        {
            int p = IndexOfOutsideQuotes(line, '|');
            if (p < 0) { DoPass(line, ""); return; }

            string left = line.Substring(0, p).Trim();
            string right = line.Substring(p + 1).Trim();
            if (left.Length == 0) { AdbUsage(); return; }

            Echo("shell", left + " | " + right + "   （本地过滤）");

            string inner = "cd '" + CUR + "' && " + left;

            StringBuilder sb = new StringBuilder();
            if (ADB.IndexOf(' ') >= 0 && !ADB.StartsWith("\"")) sb.Append('"').Append(ADB).Append('"');
            else sb.Append(ADB);
            if (!string.IsNullOrEmpty(SERIAL)) sb.Append(" -s ").Append(SERIAL);
            sb.Append(" shell \"").Append(inner.Replace("\"", "\\\"")).Append("\" | ").Append(right);

            RunLocalShell(sb.ToString());
        }

        // 拼回一行用于回显（不加引号，保持可读）
        private static string JoinWithSpace(List<string> toks)
        {
            if (toks == null || toks.Count == 0) return "";
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < toks.Count; i++)
            {
                sb.Append(' ');
                sb.Append(toks[i]);
            }
            return sb.ToString();
        }

        // 把分词结果拼回一行（含空格的重新加引号）
        private static string JoinTokens(List<string> toks)
        {
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < toks.Count; i++)
            {
                if (i > 0) sb.Append(' ');
                string t = toks[i];
                if (t.Length == 0) { sb.Append("\"\""); continue; }
                if (t.IndexOf(' ') >= 0 || t.IndexOf('\t') >= 0)
                {
                    sb.Append('"').Append(t).Append('"');
                }
                else
                {
                    sb.Append(t);
                }
            }
            return sb.ToString();
        }

        private static void AdbUsage()
        {
            Console.WriteLine("  用法：adb <子命令> [参数]      例：adb devices / adb install D:\\a.apk");
            Console.WriteLine("        也可以直接输入子命令       例：devices / install D:\\a.apk");
            Console.WriteLine("        adb shell <命令>           与直接输入命令等价（保持当前目录）");
            Console.WriteLine("  支持本地重定向，例如：adb exec-out screencap -p > shot.png");
            Console.WriteLine("  常用：devices  install  uninstall  forward  reverse  tcpip  reboot  root  version");
        }
    }
}
