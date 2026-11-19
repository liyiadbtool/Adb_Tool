// ============================================================================
//  TaskCmds.cs — 快捷指令扩展（2026-11-10 深夜轮）
//
//  本轮新增的 7 个快捷指令统一收敛到这里，按"做什么"分四类：
//
//   ① 导出类：:apk（前台 APK）、:pcm（PCM）、:dlog（Android 日志）、
//              :carplay（carplay 音频文件）
//       共同点：都要落到「桌面\logcat\<今天>\<分类>」目录，目录不存在就建。
//       全部复用 Adb.Export / CmdRegistry.OutDir 这两份既有逻辑，
//       不在这里另写一套路径规则 —— 三处路径一旦不同步就会出乱子。
//
//   ② 顺序执行类：:hicar、:carplayon
//       共同点：按顺序执行多条命令，某条失败**跳过继续**，最后汇总报告
//       "哪几条失败了"。复用 DoPreUpgrade 的思路，但把报告做得更明确。
//
//   ③ 静默截图：:shot 的底层实现（无感知，不弹任何 cmd/adb 黑窗）
//       截图命令带 `>` 本地重定向，老路径走 cmd.exe。cmd 里再启动的
//       adb.exe 是控制台程序，Windows 会给它补一个可见控制台窗口 ——
//       这就是"截图时黑框还在"的根因（之前只修了 cmd 这一层）。
//       正解：完全不经过 cmd，直接用 Process 拉起 adb.exe，
//       RedirectStandardOutput 拿 screencap 的 PNG 二进制，C# 自己写文件。
//
//   C# 5.0 兼容：不写 out var / 局部函数 / => / $"..."。
// ============================================================================
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading;

namespace AdbLogExport
{
    internal static partial class App
    {
        // ==================== 通用：离线守卫 ====================
        private static bool RequireDevice(string hint)
        {
            if (OFFLINE || DEVN == 0)
            {
                Warn("设备未连接，无法执行该操作");
                Hint("输入 :r 重连后再试" + (hint.Length > 0 ? "；" + hint : ""));
                return false;
            }
            return true;
        }

        // ==================== 通用：顺序执行 ====================
        // steps 里每条是一个「adbd 层的 argv」（与 AdbCall 一致）。
        // 逐条执行，失败**跳过继续**，最后汇总"失败了几条、分别是哪几条"。
        //
        // 为什么失败要跳过而不是中止：
        //   HiCarSDK / carplay 这类开关是一串独立的 setprop，
        //   中间某条失败（比如某个属性不存在）不该挡住后面的，
        //   而且必须让用户知道"到底哪条没生效"，才好针对性处理。
        //
        // 返回失败条数（0 = 全部成功）。
        private static int RunSteps(string title, List<string[]> steps)
        {
            int failCount = 0;
            List<string> failedCmds = new List<string>();

            UseDim();
            Console.WriteLine("  [顺序执行] " + title + "（共 " + steps.Count + " 条，失败自动跳过）");
            UseDefault();

            for (int i = 0; i < steps.Count; i++)
            {
                string[] argv = steps[i];
                string display = JoinArgv(argv);

                string o = "";
                string e = "";
                int rc = AdbCall(new List<string>(argv), out o, out e);
                string combined = (o + e).Trim();
                string first = FirstLine(combined);
                string low = combined.ToLowerInvariant();

                bool ok = (rc == 0)
                    && !low.Contains("error")
                    && !low.Contains("cannot")
                    && !low.Contains("fail")
                    && !low.Contains("denied")
                    && !low.Contains("not found")
                    && !low.Contains("no such");

                if (ok)
                {
                    UseOk();
                    Console.WriteLine("    \u221A [" + (i + 1) + "/" + steps.Count + "] " + display
                        + (first.Length > 0 ? "   → " + first : ""));
                    UseDefault();
                }
                else
                {
                    failCount++;
                    failedCmds.Add(display);
                    UseErr();
                    Console.WriteLine("    \u00D7 [" + (i + 1) + "/" + steps.Count + "] " + display
                        + (first.Length > 0 ? "   → " + first : "（退出码 " + rc + "）"));
                    UseDefault();
                }
            }

            if (failCount == 0)
            {
                Ok(title + "：全部 " + steps.Count + " 条执行成功");
            }
            else
            {
                Fail(title + "：有 " + failCount + " 条失败，其余已继续执行");
                for (int k = 0; k < failedCmds.Count; k++)
                {
                    Hint("  失败命令：" + failedCmds[k]);
                }
            }
            return failCount;
        }

        // 把 argv 拼成一条可读命令（adb 视角：adb <argv...>）
        private static string JoinArgv(string[] argv)
        {
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < argv.Length; i++)
            {
                if (i > 0) sb.Append(' ');
                string t = argv[i];
                if (t.IndexOf(' ') >= 0 || t.IndexOf('\t') >= 0)
                    sb.Append('"').Append(t).Append('"');
                else
                    sb.Append(t);
            }
            return sb.ToString();
        }

        // ==================== ① 导出类快捷指令 ====================

        // 需求1：导出前台 APK。
        //   1) 查前台包名（复用 PkgVer.QueryForegroundCands）
        //   2) pm path <pkg> 拿 apk 在设备上的路径
        //   3) pull 到 桌面\logcat\<今天>\APK
        private static void DoExportApk()
        {
            if (!RequireDevice("")) return;

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
                Hint("可能停在锁屏或系统界面；用 :front 看前台包名 / Activity / 路径");
                return;
            }

            string apkPath = QueryPkgPath(pkg);
            if (apkPath.Length == 0)
            {
                Fail("取不到 " + pkg + " 的 apk 路径（pm path 无结果）");
                Hint("系统应用或已卸载的应用没有可拉取的 apk");
                return;
            }

            // 落点：桌面\logcat\<今天>\APK\  （目录由 OutDir 即时创建）
            string target = OutDir("APK");

            Echo("export-apk", pkg + "  (" + apkPath + ")  →  " + target);
            Export(apkPath, LastSeg(apkPath), target);

            if (CMD_OK)
            {
                Ok("前台 APK 已导出到 " + target);
            }
        }

        // 需求3：PCM 导出。底部说明文案是「工程模式->日志设置->audio->使能开关」，
        // 那是**前置操作提示**（让用户先去车上打开 PCM 采集开关），不是命令本身。
        // PCM 采集开关打开后，音频裸流落在 /data/ 下的固定目录，这里整体拉取。
        private static void DoExportPcm()
        {
            if (!RequireDevice("先到车上按提示打开 PCM 采集开关")) return;

            // PCM 采集的落点：不同车型/ROM 位置略有差异，这里覆盖最常用的两处。
            // 取不到就用第一处（导出空目录也会如实报错，不会假成功）。
            string[] cands = new string[]
            {
                "/data/local/tmp/pcm",
                "/sdcard/pcm",
                "/data/pcm"
            };

            string devPath = "";
            string o = "";
            string e = "";
            for (int i = 0; i < cands.Length; i++)
            {
                int rc = ShellCall(CUR, "ls -d " + cands[i] + " 2>/dev/null", out o, out e);
                string first = FirstLine((o + e).Trim());
                if (rc == 0 && first.Length > 0 && first.IndexOf("No such") < 0
                    && first.IndexOf("not found") < 0)
                {
                    devPath = cands[i];
                    break;
                }
            }

            if (devPath.Length == 0)
            {
                Fail("没找到 PCM 采集目录");
                Hint("请先在车上操作：工程模式 → 日志设置 → audio → 使能开关");
                Hint("打开开关后再导出；若目录不同，可直接用 pull <设备路径> 手动拉");
                return;
            }

            string target = OutDir("PCM");
            Echo("export-pcm", devPath + "  →  " + target);
            Export(devPath, LastSeg(devPath), target);
            if (CMD_OK) Ok("PCM 已导出到 " + target);
        }

        // 需求4：Android 日志导出（pull /log/android_log 到 logcat-日期）。
        // 【缺陷修复】/log/android_log 是活动日志目录，文件在设备侧实时轮转，
        // 逐文件 pull 会在中途遇到文件被删（remote open failed）而整体失败。
        // 这里强制走打包导出（tar.gz 原子快照），tar 对已消失文件只是跳过。
        private static void DoExportDlog()
        {
            if (!RequireDevice("")) return;

            string devPath = "/log/android_log";
            string target = OutDir("");   // 需求原话：导出到 logcat-日期 文件下（不套分类）

            Echo("export-dlog", devPath + "  →  " + target);
            Export(devPath, LastSeg(devPath), target, true);
            if (CMD_OK) Ok("Android 日志已导出到 " + target);
        }

        // 需求7：导出 carplay 音频文件（pull /data/carplay/records）。
        private static void DoExportCarplay()
        {
            if (!RequireDevice("")) return;

            string devPath = "/data/carplay/records";

            // 【需求4·修复】/data/carplay/records 是 carplay 连接并开始音频录制
            // 后才创建的目录。没连 iPhone / 没触发录制时目录不存在，直接 pull
            // 会报 "No such file or directory"，用户分不清是路径错还是没录制。
            // 这里先探测，不存在就给出明确指导，而不是甩一句晦涩的 adb 报错。
            string o = "";
            string e = "";
            int rc = ShellCall(CUR, "test -d '" + devPath + "' && echo Y || echo N", out o, out e);
            bool exists = (rc == 0 && string.Equals(FirstLine(o).Trim(), "Y", StringComparison.Ordinal));

            if (!exists)
            {
                Fail("carplay 音频目录不存在：" + devPath);
                Hint("这个目录在 carplay 连接并开始音频录制后才会创建");
                Hint("请先确认：① 打开「carplay 音频」开关 → ② iPhone 连上车机 carplay → ③ 触发一次通话/音频播放，再回来导出");
                Hint("若确定目录路径不同，可用 :front 查 carplay 包名，再 pull 实际路径");
                return;
            }

            string target = OutDir("carplay");

            Echo("export-carplay", devPath + "  →  " + target);
            Export(devPath, LastSeg(devPath), target);
            if (CMD_OK) Ok("carplay 音频已导出到 " + target);
        }

        // ==================== 需求（2026-11-12）：重启车机 ====================
        //
        // 用户给的命令就是 `adb reboot`。裸写 reboot 本来也能工作（它在
        // DEVICE_CMDS 里，会被识别成 adb 子命令直接透传），但透传路径有两个问题：
        //   1) reboot 一下发，设备立刻掉线，adb 往往来不及回一行输出 ——
        //      输出框里就是一片空白，用户不知道到底发出去没有；
        //   2) 没有二次确认的余地，误点就直接重启车机。
        // 所以做成内置命令：
        //   · 发之前先回显"正在重启 <设备号>"，让输出框有明确记录
        //   · 下发时不等 adb 返回（reboot 必然导致连接中断，等就是等超时）
        //   · 成功与否以"命令是否成功下发"为准，并提示后续要重新 :r 重连
        private static void DoReboot()
        {
            if (OFFLINE || DEVN == 0)
            {
                Warn("设备未连接，无法重启车机");
                Hint("输入 :r 重连后再试");
                return;
            }

            Echo("reboot", "重启车机 " + (DEVID.Length > 0 ? DEVID : "(当前设备)"));

            string o = "";
            string e = "";
            int rc = AdbCall(new List<string> { "reboot" }, out o, out e);

            string combined = (o + "\n" + e).Trim();
            string low = combined.ToLowerInvariant();

            // reboot 正常下发后 adb 通常会报 "error: device ... not found"
            // 或直接断开连接 —— 那不是失败，正是重启生效的表现。
            bool looksLikeDrop = low.IndexOf("not found") >= 0
                || low.IndexOf("closed") >= 0
                || low.IndexOf("offline") >= 0
                || low.IndexOf("connection") >= 0
                || low.IndexOf("protocol fault") >= 0;

            if (rc == 0 || looksLikeDrop || combined.Length == 0)
            {
                CMD_OK = true;
                UseOk();
                Console.WriteLine("  reboot 已下发，车机正在重启");
                UseDefault();
                Hint("等待 30~60 秒开机；设备重新上线后输入 :r 重连（或点顶部设备号刷新）");
                if (looksLikeDrop && combined.Length > 0)
                {
                    Hint("adb 回报「" + FirstLine(combined) + "」属正常现象：重启会立刻断开连接");
                }
                return;
            }

            CMD_OK = false;
            Fail("重启失败：" + FirstLine(combined));
            Hint("确认设备在线（devices）；必要时手动长按电源键重启");
        }

        // ==================== 需求（2026-11-12）：ANR / crash 日志导出 ====================
        //
        // 用户给的命令：
        //   导出 anr 日志    adb pull /data/anr               -> 桌面 logcat
        //   导出 crash 日志  adb pull /data/system/dropbox    -> 桌面 logcat
        //
        // 落点：桌面\logcat\yyyy-MM-dd\anr 与 ...\dropbox（OutDir 会把目录建好）。
        // 放在日期的子目录里而不是直接摊在日期层，是因为这两个目录一次能拉几十个
        // 文件，跟当天的截图/录屏混在一起就找不着了。
        //
        // 两个目录都**只有 root 可读**（drwx------ system system）。普通 adb shell
        // 进去会得到 "Permission denied"；pull 失败时报错信息又很绕（remote
        // open failed: Permission denied），用户分不清是"没有文件"还是"没权限"。
        // 所以先探测：目录在不在 / 能不能 ls 出来，把两种情况分开提示。
        //
        // 探测用一次 shell 往返完成三件事，避免三次 adb 调用：
        //     测试 -d 目录  →  A 表示存在
        //     ls 目录       →  能读到就说明有权限
        private static bool ProbeReadableDir(string devPath, out string reason)
        {
            reason = "";

            // test -d + ls 合并成一次 shell：输出以 ## 分段，便于解析
            string cmd = "echo '##D'; test -d '" + devPath + "' && echo Y || echo N; "
                       + "echo '##L'; ls '" + devPath + "' 2>&1 | head -20";

            string o = "";
            string e = "";
            ShellCall(CUR, cmd, out o, out e);
            string all = (o + "\n" + e);

            bool exists = false;
            StringBuilder lsOut = new StringBuilder();
            bool inLs = false;

            string[] lines = all.Replace("\r", "").Split('\n');
            for (int i = 0; i < lines.Length; i++)
            {
                string ln = lines[i].Trim();
                if (ln == "##D") { inLs = false; continue; }
                if (ln == "##L") { inLs = true; continue; }
                if (!inLs)
                {
                    if (ln == "Y") exists = true;
                    continue;
                }
                if (ln.Length > 0) lsOut.Append(ln).Append('\n');
            }

            if (!exists)
            {
                reason = "目录不存在：" + devPath;
                return false;
            }

            string lsText = lsOut.ToString().Trim();
            string low = lsText.ToLowerInvariant();

            if (lsText.Length == 0)
            {
                reason = "目录是空的：" + devPath;
                return false;
            }

            if (low.IndexOf("permission denied") >= 0 || low.IndexOf("opendir failed") >= 0)
            {
                reason = "没有读取权限（需要 root）：" + devPath;
                return false;
            }

            return true;
        }

        // 导出 ANR 日志：/data/anr -> 桌面\logcat\<今天>\anr
        private static void DoExportAnr()
        {
            if (!RequireDevice("")) return;

            string devPath = string.IsNullOrEmpty(JUMP_ANR) ? "/data/anr" : JUMP_ANR;
            string reason = "";
            if (!ProbeReadableDir(devPath, out reason))
            {
                Fail("ANR 日志导出中止 —— " + reason);
                if (reason.IndexOf("不存在") >= 0)
                {
                    Hint("设备上还没有产生过 ANR，或该机型把 ANR 落在别的目录");
                    Hint("可以先 cd @anr 进目录看一眼；或用 ls /data/anr 确认路径");
                }
                else if (reason.IndexOf("权限") >= 0)
                {
                    Hint("先点顶部 ROOT 按钮提权（adb root），再点一次「导出ANR日志」");
                    Hint("提权后 adbd 会重启，稍等设备重新上线即可");
                }
                else
                {
                    Hint("目录为空说明还没有 ANR 记录，复现一次 ANR 后再导出");
                }
                return;
            }

            string target = OutDir("anr");
            Echo("export-anr", devPath + "  →  " + target);
            // forceZip=true：ANR 目录里常有几十个 txt，逐文件 pull 慢且容易中断
            Export(devPath, LastSeg(devPath), target, true);
            if (CMD_OK) Ok("ANR 日志已导出到 " + target);
        }

        // 导出 crash 日志：/data/system/dropbox -> 桌面\logcat\<今天>\dropbox
        private static void DoExportDropbox()
        {
            if (!RequireDevice("")) return;

            string devPath = string.IsNullOrEmpty(JUMP_DROPBOX) ? "/data/system/dropbox" : JUMP_DROPBOX;
            string reason = "";
            if (!ProbeReadableDir(devPath, out reason))
            {
                Fail("crash 日志导出中止 —— " + reason);
                if (reason.IndexOf("不存在") >= 0)
                {
                    Hint("该机型可能把 dropbox 放在 /data/system/dropbox 之外");
                    Hint("可先用 cd @dropbox 尝试跳转确认路径");
                }
                else if (reason.IndexOf("权限") >= 0)
                {
                    Hint("先点顶部 ROOT 按钮提权（adb root），再点一次「导出crash日志」");
                }
                else
                {
                    Hint("dropbox 为空说明还没有崩溃记录，复现一次 crash 后再导出");
                }
                return;
            }

            string target = OutDir("dropbox");
            Echo("export-dropbox", devPath + "  →  " + target);
            // dropbox 里是 data_app_crash / system_app_anr 这类小文件，数量多，强制打包
            Export(devPath, LastSeg(devPath), target, true);
            if (CMD_OK) Ok("crash 日志已导出到 " + target);
        }

        // ==================== ② 顺序执行类快捷指令 ====================

        // 需求5：打开 HiCarSDK 日志（6 条，顺序执行，失败跳过并报告）。
        private static void DoHicarDebug()
        {
            if (!RequireDevice("")) return;

            List<string[]> steps = new List<string[]>();
            steps.Add(new string[] { "root" });
            steps.Add(new string[] { "remount" });
            steps.Add(new string[] { "shell", "setprop persist.vendor.hicarsdk.debug 1" });
            steps.Add(new string[] { "shell", "setprop persist.sys.hicarsdk.debug 1" });
            steps.Add(new string[] { "shell", "sync" });
            steps.Add(new string[] { "reboot" });

            int fail = RunSteps("打开 HiCarSDK 日志", steps);

            if (fail == 0)
            {
                Hint("设备即将重启；重启后 HiCarSDK 调试日志生效");
            }
            else
            {
                Hint("reboot 若已下发，设备会重启；其余失败项请按上面提示逐条排查");
            }
            CMD_OK = true;   // 顺序执行本身完成了（个别命令失败已如实报告）
        }

        // 需求6：打开 carplay 音频（2 条，顺序执行，失败跳过并报告）。
        private static void DoCarplayOn()
        {
            if (!RequireDevice("")) return;

            List<string[]> steps = new List<string[]>();
            steps.Add(new string[] { "shell", "setprop sys.carplay.debug.record.audio.input true" });
            steps.Add(new string[] { "shell", "setprop sys.carplay.debug.record.audio.output true" });

            int fail = RunSteps("打开 carplay 音频录制", steps);
            if (fail == 0)
            {
                Hint("音频录制已开启；导出用「导出 carplay 音频文件」");
            }
            CMD_OK = true;
        }

        // ==================== ⑤ 方控：强制重启（组合键）====================

        // 需求7：按「强制重启_组合键.bat」实现。
        //
        // 脚本逻辑（逐条对应）：
        //   inject-key -a down 503     按下电话键，不自动抬起
        //   inject-key -a down 520     按下星号键，不自动抬起
        //   timeout /t 20              两键同时按住 20 秒
        //   inject-key -a up 503       抬起
        //   inject-key -a up 520       抬起
        //
        // 两个关键点（脚本注释里也强调了，很容易写错）：
        //   1) 必须用 -a down / -a up，**不能用 -t**。
        //      -t 的语义是"N 毫秒后自动抬起"，它会在同一进程内把 down+up
        //      一个接一个发出去，两个键不可能同时处于按下状态 —— 而
        //      "同时按住"正是组合键触发强制重启的前提。
        //   2) 时长必须靠本地休眠控制，不能交给 -t。
        //
        // 参数：默认按住 20 秒，可用 :fkforce 25 改成 25 秒。
        // 安全：这条会真的强制重启车机，执行前要求确认（GUI 里由卡片提示）。
        private static void DoForceReboot(int holdSec)
        {
            if (OFFLINE || DEVN == 0)
            {
                Fail("设备未连接，无法下发强制重启组合键");
                Hint("输入 :r 重连后再试");
                return;
            }

            if (holdSec < 1) holdSec = 20;
            if (holdSec > 120) holdSec = 120;   // 上限 2 分钟，防止误输 2000 挂死

            const int KEY_CALL = 503;
            const int KEY_STAR = 520;

            Console.WriteLine();
            Warn("即将下发「强制重启」组合键：");
            Info("  电话键(" + KEY_CALL + ") + 星号键(" + KEY_STAR
                 + ") 同时按住 " + holdSec + " 秒");
            Hint("按住期间车机会自动强制重启；期间 adb 会断开，属正常现象");
            Console.WriteLine();

            // ---- 1/3 同时按下 ----
            Info("1/3 同时按下 电话键 + 星号键 …");
            bool down1 = InjectKeyAction("down", KEY_CALL);
            bool down2 = InjectKeyAction("down", KEY_STAR);

            if (!down1 || !down2)
            {
                // 有任何一个按下失败，必须把已按下的抬起来，
                // 否则会留下一个"卡住"的按键状态，影响后续所有测试。
                Warn("按下失败，正在回滚（抬起已按下的键）…");
                if (down1) InjectKeyAction("up", KEY_CALL);
                if (down2) InjectKeyAction("up", KEY_STAR);
                CMD_OK = false;
                Fail("组合键下发失败");
                Hint("确认设备在线且 car_service 可用");
                return;
            }

            // ---- 2/3 按住 ----
            Info("2/3 保持按住 " + holdSec + " 秒（车机应在此期间强制重启）…");
            System.Threading.Thread.Sleep(holdSec * 1000);

            // ---- 3/3 抬起 ----
            // 注意：如果车机已经重启，adb 会断开，这两条会失败 —— 那是**成功**
            // 的表现，不能当失败处理。所以这里不看返回值。
            Info("3/3 抬起 电话键 + 星号键 …");
            InjectKeyAction("up", KEY_CALL);
            InjectKeyAction("up", KEY_STAR);

            Console.WriteLine();
            Ok("组合键已下发完毕（按住 " + holdSec + " 秒）");
            Hint("若车机已开始重启，adb 会断开；等 30~60 秒后按 :r 重连");
            CMD_OK = true;
        }

        // ==================== ⑤.5 方控：单键长按（down → 按住 → up）====================
        // 需求（2026-11-12）：语音/通话支持「短按 + 长按」。
        //   短按 = 单击 inject-key（car_service 自动 down+up，见 cmds.ini 的 fkvoice/fkcall）；
        //   长按 = 手动 down 按住 N 毫秒再 up。
        // 复用 InjectKeyAction 与 DoForceReboot 的 down/按住/up + 回滚模式。
        private static void DoKeyHold(int keyCode, int holdMs)
        {
            if (OFFLINE || DEVN == 0)
            {
                Fail("设备未连接，无法下发长按");
                Hint("输入 :r 重连后再试");
                return;
            }
            if (holdMs < 200) holdMs = 3000;   // 兜底默认 3 秒（2026-11-18 由 4 秒下调）
            if (holdMs > 120000) holdMs = 120000;   // 上限 2 分钟

            Echo("inject-key", "-a down " + keyCode + " 按住 " + (holdMs / 1000) + " 秒");
            bool down = InjectKeyAction("down", keyCode);
            if (!down)
            {
                Warn("按下失败，未进入长按");
                CMD_OK = false;
                Fail("长按下发失败");
                return;
            }

            Info("保持按住 " + (holdMs / 1000) + " 秒 …");
            System.Threading.Thread.Sleep(holdMs);

            // 抬起：断线视作成功（车机可能因此重启/掉线），与 DoForceReboot 一致
            InjectKeyAction("up", keyCode);

            CMD_OK = true;
            Ok("长按已下发完毕（按住 " + (holdMs / 1000) + " 秒）");
        }

        // 方控单键**短按**：一条 inject-key 让 car_service 自己 down+up。
        // cmds.ini 里的 fk* 命令都是这么写的（`shell dumpsys car_service inject-key 520`），
        // 这里把内置命令也走同一条路径，保证"卡片上点一下"和"终端敲 :fksource"行为一致。
        private static void DoFkTap(int keyCode, string label)
        {
            if (OFFLINE || DEVN == 0)
            {
                Fail("设备未连接，无法下发" + label);
                Hint("输入 :r 重连后再试");
                return;
            }

            Echo("inject-key", label + " (" + keyCode + ")");
            string o = "";
            string e = "";
            int rc = ShellCall(CUR, "dumpsys car_service inject-key " + keyCode, out o, out e);

            string merged = (o + "\n" + e).Trim();
            if (merged.Length > 0)
            {
                string[] lines = merged.Split('\n');
                for (int i = 0; i < lines.Length; i++)
                {
                    string line = lines[i].TrimEnd('\r');
                    if (line.Trim().Length > 0) Info(line);
                }
            }

            bool looksLikeDrop = merged.ToLowerInvariant().IndexOf("offline") >= 0
                || merged.ToLowerInvariant().IndexOf("closed") >= 0;
            if (rc == 0 || looksLikeDrop)
            {
                Ok(label + " 已下发");
                CMD_OK = true;
            }
            else
            {
                CMD_OK = false;
                Fail(label + " 下发失败（退出码 " + rc + "）");
                Hint("确认 car_service 可用；可用 :fksource 单独验证 520 短按是否正常");
            }
        }

        // 单次 inject-key 动作（down 或 up）。
        // action = "down" / "up"
        // 返回是否成功。断线时返回 false，但调用方要按场景判断是否当失败。
        private static bool InjectKeyAction(string action, int keyCode)
        {
            string cmd = "dumpsys car_service inject-key -a " + action + " " + keyCode;
            Echo("inject-key", "-a " + action + " " + keyCode);

            string o = "";
            string e = "";
            int rc = ShellCall(CUR, cmd, out o, out e);

            string merged = (o + "\n" + e).Trim();
            string low = merged.ToLowerInvariant();

            if (merged.Length > 0)
            {
                string[] lines = merged.Split('\n');
                for (int i = 0; i < lines.Length; i++)
                {
                    string line = lines[i].TrimEnd('\r');
                    if (line.Trim().Length > 0) Info(line);
                }
            }

            // 断线也是"下发成功"的一种表现（车机在重启）
            bool looksLikeDrop = low.IndexOf("not found") >= 0
                || low.IndexOf("closed") >= 0
                || low.IndexOf("offline") >= 0
                || low.IndexOf("connection") >= 0;

            if (rc == 0) return true;
            if (looksLikeDrop) return true;

            // 明确报错才算失败
            if (low.IndexOf("error") >= 0 || low.IndexOf("exception") >= 0
                || low.IndexOf("fail") >= 0)
            {
                return false;
            }
            return rc == 0;
        }

        // ==================== ③ 手车互联：CarPlay 认证属性 ====================

        // CarPlay 认证（CERT）属性名。true = 已认证/放行，false = 未认证。
        // 用常量集中一处，避免三处（设置/查询/提示）各写一遍拼错。
        private const string CARPLAY_CERT_PROP = "persist.connectivityphone.carplay.CERT";

        // 需求2：设置 CarPlay 认证属性。
        //   adb shell setprop persist.connectivityphone.carplay.CERT true|false
        //
        // 为什么设完要回读：
        //   setprop 返回 0 不代表属性真的写进去了。persist.* 属性的写入要过
        //   property_service，权限不够时 setprop 可能成功返回但值没变
        //   （SELinux 拦掉时就这样，不报错）。所以必须 getprop 复核一次，
        //   否则用户会以为设置成功了、实际没生效 —— 这正是"静音不生效"
        //   那类问题的同款陷阱。
        private static void DoCarplayCertSet(bool value)
        {
            if (!RequireDevice("")) return;

            string want = value ? "true" : "false";
            Echo("setprop", CARPLAY_CERT_PROP + " " + want);

            string o = "";
            string e = "";
            int rc = ShellCall(CUR, "setprop " + CARPLAY_CERT_PROP + " " + want, out o, out e);

            // 回读
            string got = "";
            string ge = "";
            ShellCall(CUR, "getprop " + CARPLAY_CERT_PROP, out got, out ge);
            got = (got + ge).Trim();

            if (got.Length == 0)
            {
                CMD_OK = false;
                Fail("设置后回读为空，属性可能没写进去");
                Hint("persist.* 属性需要一定权限；可先 :root 提权后重试");
                return;
            }

            if (string.Equals(got, want, StringComparison.OrdinalIgnoreCase))
            {
                CMD_OK = true;
                Ok("CarPlay 认证属性已设为 " + want);
                Hint("属性：" + CARPLAY_CERT_PROP + " = " + got);
                if (!value)
                {
                    Hint("已关闭认证。断开并重连 CarPlay 后生效");
                }
                else
                {
                    Hint("已开启认证。断开并重连 CarPlay 后生效");
                }
            }
            else
            {
                CMD_OK = false;
                Fail("设置未生效：期望 " + want + "，实际 " + got);
                Hint("多半是权限问题，先 :root 再试");
            }
        }

        // 需求3：查询 CarPlay 认证属性。
        //   adb shell getprop persist.connectivityphone.carplay.CERT
        //
        // 空值也要讲清楚："属性不存在"和"属性为空"是两件事，
        // 直接打一个空行会让用户不知道该干什么。
        private static void DoCarplayCertGet()
        {
            if (!RequireDevice("")) return;

            Echo("getprop", CARPLAY_CERT_PROP);

            string o = "";
            string e = "";
            ShellCall(CUR, "getprop " + CARPLAY_CERT_PROP, out o, out e);
            string val = (o + e).Trim();

            CMD_OK = true;

            if (val.Length == 0)
            {
                Info("（空）该属性当前没有设置值");
                Hint("可用「CarPlay认证-开启」或「CarPlay认证-关闭」写入");
                return;
            }

            if (string.Equals(val, "true", StringComparison.OrdinalIgnoreCase))
            {
                Ok("CarPlay 认证：" + val + "（已开启）");
            }
            else if (string.Equals(val, "false", StringComparison.OrdinalIgnoreCase))
            {
                Warn("CarPlay 认证：" + val + "（已关闭）");
            }
            else
            {
                Info("CarPlay 认证：" + val + "（非 true/false 的取值）");
            }
        }

        // ==================== ④ 手车互联：清除 HiCar 历史设备 ====================

        // 需求4：清除 HiCar 历史设备。
        //   命令：hdc shell bm clean -d -n com.huawei.hmos.hicar
        //
        // 这条走 hdc 而不是 adb —— 用户已确认车机上装了 hdc。
        // bm clean 的参数含义：
        //   -d    清数据（data）
        //   -n    按包名指定
        //   com.huawei.hmos.hicar  HarmonyOS HiCar 的包名
        //
        // 注意：清除后 HiCar 里已配对的历史手机列表会消失，需要重新配对。
        // 这点必须提示，否则用户以为是"清缓存"，结果要重新连手机。
        private static void DoClearHicarDevices()
        {
            // 这条不依赖 adb 连接，但依赖 hdc 通道可用
            if (!HdcAvailable())
            {
                CMD_OK = false;
                Fail("hdc 不可用：" + (HDC_ERR.Length > 0 ? HDC_ERR : "未知原因"));
                Hint("1) 确认车机已装 hdc（用户已确认装了）");
                Hint("2) 确认 hdc.exe 在 PATH 或 exe 同级目录");
                Hint("3) 也可在 ini 里指定：hdc=D:\\path\\to\\hdc.exe");
                return;
            }

            Console.WriteLine();
            Info("正在清除 HiCar 历史设备 …");
            Echo("hdc shell", "bm clean -d -n com.huawei.hmos.hicar");

            bool ok = HdcShell("bm clean -d -n com.huawei.hmos.hicar");

            if (ok)
            {
                CMD_OK = true;
                Ok("HiCar 历史设备已清除");
                Hint("下次使用 HiCar 需要用手机重新配对");
            }
            else
            {
                CMD_OK = false;
                Fail("清除失败");
                Hint("可能原因：包名不对 / hdc 设备未授权 / 系统版本不支持 bm clean");
                Hint("可用 :hdclist 查看 hdc 当前连接的设备");
            }
        }

        // hdc 设备列表（排查用）。hdc list targets
        private static void DoHdcList()
        {
            if (!HdcAvailable())
            {
                CMD_OK = false;
                Fail("hdc 不可用：" + (HDC_ERR.Length > 0 ? HDC_ERR : "未知原因"));
                Hint("确认 hdc.exe 在 PATH 或 exe 同级目录，或在 ini 里配 hdc=");
                return;
            }

            Echo("hdc", "list targets");

            string o = "";
            string e = "";
            int rc = RunHdcRaw(new List<string> { "list", "targets" }, 10000, out o, out e);
            string merged = (o + "\n" + e).Trim();

            CMD_OK = (rc == 0);

            if (merged.Length == 0)
            {
                Warn("hdc 没有列出任何设备");
                Hint("[Empty] 表示 hdc 服务在跑但没连设备");
                Hint("检查 USB 线 / 车机上是否开启了 hdc 调试");
                return;
            }

            string[] lines = merged.Split('\n');
            for (int i = 0; i < lines.Length; i++)
            {
                string line = lines[i].TrimEnd('\r');
                if (line.Trim().Length > 0) Info(line);
            }
        }

        // ==================== ③ 静默截图（无感知）====================
        //   直接 Process 启动 adb.exe，RedirectStandardOutput 捕获 screencap
        //   的 PNG 二进制流，C# 落盘。子进程 stdout 被重定向后不需要控制台，
        //   自然不会弹黑框（这是与「cmd /c adb ... > file」的本质区别）。
        //
        // 落点与 :shot 一致：桌面\logcat\<今天>\screencap\shot_<HHmmss>.png
        private static void DoShotSilent()
        {
            if (!RequireDevice("")) return;

            string dir = OutDir("shot");
            string file = Path.Combine(dir, "shot_" + DateTime.Now.ToString("HHmmss") + ".png");

            // 构造 argv：adb [-s serial] exec-out screencap -p
            List<string> argv = new List<string>();
            argv.Add("exec-out");
            argv.Add("screencap");
            argv.Add("-p");

            string serial = "";
            if (!string.IsNullOrEmpty(SERIAL) && SERIAL_OK) serial = SERIAL;
            else serial = DEVID;

            Echo("shot", "screencap -p  →  " + file);

            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = ADB;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            psi.RedirectStandardOutput = true;
            psi.RedirectStandardError = true;
            psi.RedirectStandardInput = true;

            // 手动拼参数（.NET Framework 没有 ArgumentList）
            StringBuilder args = new StringBuilder();
            if (serial.Length > 0) args.Append(" -s ").Append(serial);
            for (int i = 0; i < argv.Count; i++)
            {
                args.Append(' ').Append(argv[i]);
            }
            psi.Arguments = args.ToString();

            bool ok = false;
            string errText = "";

            try
            {
                using (Process p = new Process())
                {
                    p.StartInfo = psi;
                    p.Start();
                    try { p.StandardInput.Close(); } catch { }

                    // 同步读 stdout 二进制 + stderr 文本（用后台线程读 stderr 避免管道阻塞）
                    StringBuilder se = new StringBuilder();
                    Thread errThread = new Thread(new ThreadStart(delegate()
                    {
                        try
                        {
                            string line;
                            while ((line = p.StandardError.ReadLine()) != null)
                            {
                                lock (se) { se.AppendLine(line); }
                            }
                        }
                        catch { }
                    }));
                    errThread.IsBackground = true;
                    errThread.Start();

                    using (Stream src = p.StandardOutput.BaseStream)
                    {
                        using (FileStream dst = new FileStream(file, FileMode.Create, FileAccess.Write))
                        {
                            byte[] buf = new byte[65536];
                            int n;
                            while ((n = src.Read(buf, 0, buf.Length)) > 0)
                            {
                                dst.Write(buf, 0, n);
                            }
                        }
                    }

                    p.WaitForExit();
                    lock (se) { errText = se.ToString(); }

                    ok = (p.ExitCode == 0);
                }
            }
            catch (Exception ex)
            {
                errText = ex.Message;
                ok = false;
            }

            // 落盘校验：PNG 至少要有个头（8 字节签名），否则视为失败
            if (ok)
            {
                try
                {
                    if (!File.Exists(file)) ok = false;
                    else
                    {
                        long len = new FileInfo(file).Length;
                        if (len < 8) ok = false;
                        else
                        {
                            byte[] head = new byte[8];
                            using (FileStream fs = new FileStream(file, FileMode.Open, FileAccess.Read))
                            {
                                if (fs.Read(head, 0, 8) != 8) ok = false;
                            }
                            // PNG 签名：89 50 4E 47 0D 0A 1A 0A
                            if (!(head[0] == 0x89 && head[1] == 0x50 && head[2] == 0x4E && head[3] == 0x47))
                                ok = false;
                        }
                    }
                }
                catch { ok = false; }
            }

            if (ok)
            {
                CMD_OK = true;
                long size = 0;
                try { size = new FileInfo(file).Length; } catch { }
                Ok("截图已保存：" + file + (size > 0 ? "（" + size + " 字节）" : ""));
            }
            else
            {
                CMD_OK = false;
                // 半截文件不留在磁盘上，避免用户误以为是成功产物
                try { if (File.Exists(file)) File.Delete(file); } catch { }
                string detail = FirstLine(errText.Trim());
                Fail("截图失败" + (detail.Length > 0 ? "：" + detail : ""));
                Hint("确认设备在线（:r）、screencap 可用；必要时改用 :shot 走重定向路径");
            }
        }

        // ==================== ④ 截帧录屏（屏幕受 FLAG_SECURE 保护时的兜底）====================
        // 车机屏幕带 FLAG_SECURE，screenrecord / scrcpy 都取不到帧（实测录到 0 帧）。
        // screencap 是直接读 framebuffer，能绕过保护，所以用「连拍帧 + ffmpeg 合成 mp4」。
        // 帧率约 3fps（screencap 单张 ~300ms），够 bug 复现，不是流畅录像。
        // 录屏的停止标志/运行标志都按槽位分开：原来各是一个全局量，
        // 三个输入框并行时，停 1 号槽会把 2 号槽的录屏一起停掉。
        private static readonly bool[] _recGrabStop = new bool[App.SLOT_COUNT];
        internal static readonly bool[] REC_GRAB_RUNNING = new bool[App.SLOT_COUNT];

        private static int RecSlotSafe(int s)
        {
            if (s < 0) s = 0;
            if (s >= App.SLOT_COUNT) s = App.SLOT_COUNT - 1;
            return s;
        }

        internal static void StopRecGrab(int slot)
        {
            // 负数 = 全停（退出程序等场景）；具体槽位只停自己。
            if (slot < 0)
            {
                for (int i = 0; i < App.SLOT_COUNT; i++) _recGrabStop[i] = true;
                return;
            }
            _recGrabStop[RecSlotSafe(slot)] = true;
        }

        internal static void DoRecGrab(string arg)
        {
            if (!RequireDevice("")) return;

            int slot = RecSlotSafe(App.CUR_SLOT);   // 本槽的停止标志只影响本槽
            int maxSec = 0;   // 0 = 无限，靠 toggle 停止；>0 = 到时自动停止
            string a = (arg == null) ? "" : arg.Trim();
            if (a.Length > 0) { int.TryParse(a, out maxSec); if (maxSec < 1) maxSec = 0; }

            string outDir = OutDir("rec");
            string ts = DateTime.Now.ToString("HHmmss");
            string frameDir = Path.Combine(Path.GetTempPath(), "adb_tool_rec_" + ts);
            string outMp4 = Path.Combine(outDir, "rec_" + ts + ".mp4");
            try { Directory.CreateDirectory(frameDir); } catch { }

            Echo("rec", "截帧录屏（screencap ~3fps" + (maxSec > 0 ? "，" + maxSec + " 秒" : "") + "）→ " + outMp4);
            Info("车机屏幕受 FLAG_SECURE 保护，screenrecord 取不到帧，改用截帧合成");

            _recGrabStop[slot] = false;
            REC_GRAB_RUNNING[slot] = true;
            DateTime t0 = DateTime.Now;
            int n = 0;
            try
            {
                while (!_recGrabStop[slot])
                {
                    string fname = Path.Combine(frameDir, "frame_" + n.ToString("D6") + ".png");
                    if (GrabOneFrame(fname)) n++;
                    if (maxSec > 0 && (DateTime.Now - t0).TotalSeconds >= maxSec) break;
                    System.Threading.Thread.Sleep(50);   // 让 screencap 自身 ~320ms 定节奏，约 3fps
                }
            }
            finally
            {
                REC_GRAB_RUNNING[slot] = false;
            }

            if (n <= 0)
            {
                CMD_OK = false;
                Fail("没有截到任何帧（设备可能已断开）");
                try { Directory.Delete(frameDir, true); } catch { }
                return;
            }

            Info("共截到 " + n + " 帧，正在用 ffmpeg 合成 mp4 …");
            bool enc = EncodeFrames(frameDir, outMp4);
            try { Directory.Delete(frameDir, true); } catch { }

            if (enc && File.Exists(outMp4) && new FileInfo(outMp4).Length > 0)
            {
                CMD_OK = true;
                long sz = new FileInfo(outMp4).Length;
                string sizeStr = sz >= 1024 * 1024 ? (sz / 1024 / 1024) + " MB" : (sz / 1024) + " KB";
                Ok("录屏完成：" + outMp4 + "（" + n + " 帧，" + sizeStr + "）");
                Hint("约 3fps；如需流畅录像，需车机侧关闭 FLAG_SECURE 后走原生 screenrecord");
            }
            else
            {
                CMD_OK = false;
                Fail("ffmpeg 合成失败：" + outMp4);
                Hint("点「投屏」页右上角的「选择…」指定 ffmpeg.exe，或把它放到程序同级目录");
            }
        }

        // 截一帧 PNG 到指定路径（与 DoShotSilent 同一条 exec-out screencap 二进制通道）
        private static bool GrabOneFrame(string file)
        {
            List<string> argv = new List<string>();
            argv.Add("exec-out");
            argv.Add("screencap");
            argv.Add("-p");

            string serial = "";
            if (!string.IsNullOrEmpty(SERIAL) && SERIAL_OK) serial = SERIAL;
            else if (!string.IsNullOrEmpty(DEVID)) serial = DEVID;

            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = ADB;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            psi.RedirectStandardOutput = true;
            psi.RedirectStandardError = true;
            psi.RedirectStandardInput = true;

            StringBuilder args = new StringBuilder();
            if (serial.Length > 0) args.Append(" -s ").Append(serial);
            for (int i = 0; i < argv.Count; i++) args.Append(' ').Append(argv[i]);
            psi.Arguments = args.ToString();

            try
            {
                using (Process p = new Process())
                {
                    p.StartInfo = psi;
                    p.Start();
                    try { p.StandardInput.Close(); } catch { }

                    using (Stream src = p.StandardOutput.BaseStream)
                    using (FileStream dst = new FileStream(file, FileMode.Create, FileAccess.Write))
                    {
                        byte[] buf = new byte[65536];
                        int rd;
                        while ((rd = src.Read(buf, 0, buf.Length)) > 0) dst.Write(buf, 0, rd);
                    }
                    p.WaitForExit();
                    if (p.ExitCode != 0) { try { File.Delete(file); } catch { } return false; }
                }
                return new FileInfo(file).Length > 8;
            }
            catch
            {
                try { File.Delete(file); } catch { }
                return false;
            }
        }

        // 用 ffmpeg 把 frame_%06d.png 合成为 mp4
        private static bool EncodeFrames(string frameDir, string outMp4)
        {
            string ff = ResolveFfmpeg();
            if (ff.Length == 0 || !File.Exists(ff))
            {
                // 把"找过哪些地方"一并打出来：只说"找不到"用户不知道下一步做什么
                string src = "";
                string ver = "";
                string why = "";
                Ffmpeg.LocateFresh(out src, out ver, out why);
                Console.WriteLine("  \u00D7 找不到可用的 ffmpeg.exe");
                if (why.Length > 0) Console.WriteLine("    " + why);
                Console.WriteLine("    车机屏幕受 FLAG_SECURE 保护，screenrecord 取不到帧，");
                Console.WriteLine("    截帧录屏必须靠 ffmpeg 合成 mp4。GUI 里可在「投屏」页点「选择…」指定。");
                return false;
            }

            string pattern = Path.Combine(frameDir, "frame_%06d.png");
            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = ff;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            psi.RedirectStandardError = true;
            psi.Arguments = "-y -framerate 3 -i \"" + pattern + "\" -c:v libx264 -pix_fmt yuv420p -preset veryfast \"" + outMp4 + "\"";

            try
            {
                using (Process p = Process.Start(psi))
                {
                    string err = p.StandardError.ReadToEnd();
                    p.WaitForExit();
                    if (p.ExitCode != 0)
                    {
                        string fl = FirstLine(err);
                        Console.WriteLine("  \u00D7 ffmpeg：" + (fl.Length > 0 ? fl : "退出码 " + p.ExitCode));
                        return false;
                    }
                    return true;
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine("  \u00D7 ffmpeg 执行异常：" + ex.Message);
                return false;
            }
        }

        // 定位 ffmpeg：统一走 Ffmpeg.Locate 的四级查找（ini → 同级 → PATH → 常见位置），
        // 并且每一级都校验过 `-version`。
        // 原来这里只有 "ini 配置 + exe 同级" 两级，用户装了 ffmpeg 但没配 ini 就
        // 只能看到"找不到 ffmpeg.exe"，还得自己猜该放哪。
        private static string ResolveFfmpeg()
        {
            string src = "";
            string ver = "";
            string err = "";
            return Ffmpeg.Locate(out src, out ver, out err);
        }

        // ==================== :ffmpeg 查看 / 指定 ====================
        // 三种用法：
        //   :ffmpeg                    看状态（路径 / 来源 / 版本）
        //   :ffmpeg auto               强制重新查找（忽略缓存）
        //   :ffmpeg <路径>             校验并写进 ini（下次自动记住）
        internal static void DoFfmpeg(string arg)
        {
            string a = (arg == null) ? "" : arg.Trim();

            bool force = string.Equals(a, "auto", StringComparison.OrdinalIgnoreCase);
            if (a.Length > 0 && !force)
            {
                string ver = "";
                string err = "";
                if (Ffmpeg.Use(a, out ver, out err))
                {
                    CMD_OK = true;      // Dispatch 入口默认置 false，成功必须显式置回
                    Ok("已设置 ffmpeg" + (ver.Length > 0 ? "（版本 " + ver + "）" : ""));
                    Info("路径：" + a);
                    Info("已写入 ini 的 ffmpeg=，下次启动自动使用");
                }
                else
                {
                    CMD_OK = false;
                    Fail(err.Length > 0 ? err : "设置失败");
                    Hint("路径要指向 ffmpeg.exe 本体，不是所在目录（目录也可以，会自动补）");
                }
                return;
            }

            if (force) Ffmpeg.ClearCache();

            bool ok;
            string path = "";
            string src = "";
            string ver2 = "";
            string line = Ffmpeg.StatusLine(out ok, out path, out src, out ver2);

            if (ok)
            {
                CMD_OK = true;
                Ok("ffmpeg 可用");
                Info("路径：" + path);
                Info("来源：" + src + (ver2.Length > 0 ? "（版本 " + ver2 + "）" : ""));
                Info("截帧录屏（:rec）会用它合成 mp4");
            }
            else
            {
                CMD_OK = false;
                Fail("没找到可用的 ffmpeg.exe");
                if (line.Length > 0) Info(line);
                Hint("把 ffmpeg.exe 放到程序同级目录，或 :ffmpeg <完整路径> 指定，");
                Hint("GUI 也可以在「投屏」页点「选择…」直接选文件");
            }
        }

        // ==================== 网联服务（A14 / 2026-11-15）====================
        //
        // 用户第 2 批需求：在「指令」页新增「网联服务」分组，共 13 条。
        // 其中纯 shell 的 6 条已写进 cmds.ini（改命令不用改程序），
        // 留在这里的 4 类是 ini 表达不了的：
        //   1) 三个导出 —— 要控制落点分类目录、强制打包、以及多路径的主备选择
        //   2) :sxlog  —— 要重启 + 等设备上线（最多 60s）再跑后续命令
        //   3) :wsdevid —— 一组取值命令，逐条回显
        //   4) :url    —— 调桌面系统浏览器
        //
        // 落点统一：桌面\logcat\<今天>\<分类>\<名字>
        // 分类沿用 OutDir 的口径（未知分类原样当目录名），和 anr / dropbox 的做法一致。

        // :wsalipay   导出支付宝日志
        //   设备：/data/data/com.alipay.arome.app/files/applog（需 root）
        //   落点：桌面\logcat\<今天>\alipay\applog
        private static void DoExportAlipayLog()
        {
            if (!RequireDevice("")) return;

            string dev = "/data/data/com.alipay.arome.app/files/applog";
            string target = OutDir("alipay");

            Echo("export", dev + "  →  " + target);
            CMD_OK = false;
            Export(dev, "applog", target, true);

            if (CMD_OK)
            {
                Ok("支付宝日志已导出到 " + JoinWin(target, "applog"));
            }
            else
            {
                Hint("这个目录普通权限读不到，需要 root：先 :root 再重试");
                Hint("也可以先在车机上把「支付宝后台→上传日志」跑一遍，目录才会生成");
            }
        }

        // :wswmpf    导出微信小程序日志
        //   用户给了两个路径，其实在绝大多数设备上是同一块存储
        //   （/sdcard 就是 /storage/emulated/0 的软链），全拉一遍等于传两遍。
        //   所以按「主 + 备」处理：先 /sdcard，失败才换 /storage/emulated/0。
        //   两个落点名分别叫 xlog_sdcard / xlog_storage —— 万一两个都拉到过，
        //   目录也不会互相覆盖（用户明确要求规避重名）。
        private static void DoExportWmpfLog()
        {
            if (!RequireDevice("")) return;

            string target = OutDir("wmpf");
            string[] remotes = new string[]
            {
                "/sdcard/Android/data/com.tencent.wmpf/files/xlog",
                "/storage/emulated/0/Android/data/com.tencent.wmpf/files/xlog"
            };
            string[] names = new string[] { "xlog_sdcard", "xlog_storage" };

            for (int i = 0; i < remotes.Length; i++)
            {
                Echo("export", remotes[i] + "  →  " + target);
                CMD_OK = false;
                Export(remotes[i], names[i], target, true);

                if (CMD_OK)
                {
                    Ok("微信小程序日志已导出到 " + JoinWin(target, names[i]));
                    if (i == 0)
                        Info("两个路径指向同一块存储，已跳过第二个（内容相同，省一次传输）");
                    return;
                }

                if (i + 1 < remotes.Length)
                    Hint("这个路径没拉到，换另一个再试：" + remotes[i + 1]);
            }

            CMD_OK = false;
            Fail("两个路径都没导出来");
            Hint("确认车机上装的是微信小程序（com.tencent.wmpf）且跑过至少一次");
        }

        // :wswx      导出车载微信日志
        //   两个**不同**的目录，都要拉，落点名天然不同（log / autowechat），不冲突。
        //   落点：桌面\logcat\<今天>\wxmsg\log 与 ...\wxmsg\autowechat
        private static void DoExportWxMsgLog()
        {
            if (!RequireDevice("")) return;

            string target = OutDir("wxmsg");
            string[] remotes = new string[]
            {
                "/sdcard/Android/data/com.tencent.mm/files/log",
                "/sdcard/Android/data/com.tencent.mm/files/tencent/autowechat/com.tencent.mm"
            };
            string[] names = new string[] { "log", "autowechat" };
            bool any = false;

            for (int i = 0; i < remotes.Length; i++)
            {
                Echo("export", remotes[i] + "  →  " + target);
                CMD_OK = false;
                Export(remotes[i], names[i], target, true);
                if (CMD_OK)
                {
                    any = true;
                    Ok("已导出到 " + JoinWin(target, names[i]));
                }
                else
                {
                    // 一条失败不影响下一条：车载微信没跑过时 log 目录可能还不存在
                    Warn("这个路径没拉到：" + remotes[i]);
                }
            }

            CMD_OK = any;
            if (any) Ok("车载微信日志导出结束，目录：" + target);
            else
            {
                Fail("车载微信日志一条都没导出来");
                Hint("确认车机上装的是车载微信（com.tencent.mm）且登录过一次");
            }
        }

        // :sxlog     打开星河云埋点（重启 + 等上线 + 回读）
        //
        // 用户给的顺序：
        //   setprop datacenter.debug true
        //   setprop log.privacy true
        //   adb reboot
        //   -- 设备重启上线后（最多等 60s）--
        //   settings put global privacy_enabled true
        //   getprop persist.sys.navi.did
        //   settings get secure android_id
        //
        // 为什么必须内置：中间要等设备重启，cmds.ini 一条 run 只能是一行命令。
        private static void DoSxTraceOn()
        {
            if (!RequireDevice("")) return;

            bool ok1 = ShellStep("setprop persist.sys.gxatek.datacenter.debug true",
                                 "打开数据中台上报（datacenter.debug=true）");
            bool ok2 = ShellStep("setprop persist.log.privacy true",
                                 "打开隐私日志（log.privacy=true）");

            if (!ok1 || !ok2)
            {
                Warn("有两个属性没设成功，重启后埋点可能仍不生效");
                Hint("这两个 setprop 需要 root：先 :root 再重试");
            }

            // ---- 重启 ----
            Echo("reboot", "重启车机（埋点属性要重启才生效）");
            string ro = "";
            string re = "";
            AdbCall(new List<string> { "reboot" }, out ro, out re);
            Info("reboot 已下发，等待设备重新上线（最多 60 秒）…");

            // ---- 等上线 ----
            int waited = WaitBoot(60);
            if (waited < 0)
            {
                CMD_OK = false;
                Fail("等待被中断（已停止）");
                Hint("设备若已重启完成，可直接 :sxlog get 回读，或用 :r 重连");
                return;
            }
            if (waited == 0)
            {
                CMD_OK = false;
                Fail("等了 60 秒设备仍未上线");
                Hint("检查 USB/网络连接，输入 :r 重连后再 :sxlog set");
                return;
            }

            Ok("设备已上线（等了 " + waited + " 秒）");

            // ---- 后续三条 ----
            bool ok3 = ShellStep("settings put global privacy_enabled true",
                                 "打开隐私开关（privacy_enabled=true）");

            Echo("read", "读设备标识");
            string did = ShellValue("getprop persist.sys.navi.did");
            string aid = ShellValue("settings get secure android_id");

            UseOk();
            Console.WriteLine("  navi.did      : " + (did.Length > 0 ? did : "(空)"));
            Console.WriteLine("  android_id    : " + (aid.Length > 0 ? aid : "(空)"));
            UseDefault();

            // 回读一次隐私开关，确认真的写进去了（写入不等于生效）
            string pv = ShellValue("settings get global privacy_enabled");
            Echo("read", "privacy_enabled = " + (pv.Length > 0 ? pv : "(空)"));

            CMD_OK = ok3;
            if (ok3 && pv == "1") Ok("星河云埋点已打开（privacy_enabled=1），设备标识见上");
            else if (ok3) Warn("写入成功但回读是「" + pv + "」，请手动确认 :sxlog get");
            else Fail("privacy_enabled 没写进去，需要 root：先 :root 再 :sxlog set");
        }

        // :sxlog get   只回读当前埋点设置（不重启）
        private static void DoSxTraceGet()
        {
            if (!RequireDevice("")) return;
            string pv = ShellValue("settings get global privacy_enabled");
            string d1 = ShellValue("getprop persist.sys.gxatek.datacenter.debug");
            string d2 = ShellValue("getprop persist.log.privacy");
            Echo("read", "privacy_enabled=" + pv + "  datacenter.debug=" + d1 + "  log.privacy=" + d2);
            CMD_OK = true;
            Ok(pv == "1" && d1 == "true" && d2 == "true"
               ? "星河云埋点：已开启"
               : "星河云埋点：未完全开启（privacy_enabled=" + pv + "）");
        }

        // :castrec <屏号> [秒]   投屏并录制到 桌面\logcat\<日期>\screenrecord
        //
        // 投屏页要删掉，页内那个「录制」按钮随之消失；能力用这条命令保留，
        // 底层从"Cast.cs 逐帧截图 + ffmpeg 合成"换成 scrcpy 原生 h264 录制。
        private static void DoCastRec(string argRaw)
        {
            if (!RequireDevice("")) return;

            string a = (argRaw == null ? "" : argRaw).Trim();
            int id = 0, sec = 60;
            string[] parts = a.Split(new char[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries);
            if (parts.Length == 0)
            {
                Info("用法：:castrec <屏号> [秒数]");
                Hint("屏号：0 主屏 · 1 后排 · 3 HUD · 4 副驾 · 9 PHUD-B · 10 PHUD-C");
                Hint("默认录 60 秒，文件落在 桌面\\logcat\\<日期>\\screenrecord\\");
                return;
            }
            if (!int.TryParse(parts[0], out id) || id < 0)
            {
                Fail("屏号要是数字：" + parts[0]);
                return;
            }
            if (parts.Length > 1 && !int.TryParse(parts[1], out sec)) sec = 60;
            if (sec <= 0 || sec > 1800) { Fail("秒数范围 1~1800"); return; }

            string dir = OutDir("screenrecord");
            string file = Path.Combine(dir, "cast" + id + "_"
                          + DateTime.Now.ToString("HHmmss") + ".mp4");

            string err = "";
            if (!Scrcpy.LaunchRecord(id, "屏 " + id, file, sec, out err))
            {
                Fail("scrcpy 启动失败：" + err);
                Hint("确认已安装 scrcpy：:scrcpystat");
                return;
            }
            CMD_OK = true;   // 只是"已启动"，不是失败；窗口关掉后 scrcpy 自己写盘
            Ok("已开始录制屏 " + id + "（" + sec + " 秒后自动停止）");
            Hint("文件：" + file);
        }

        // :qnxlog [路径]   导出 QNX 日志（默认 /share/log）到 桌面\logcat\<日期>\qnx
        //
        // 车机是 QNX + Android 双系统，QNX 侧日志通过共享目录 /share/log 暴露给 Android。
        // 这里不用 tar：pull 目录 adb 会自己递归，而且能边拉边看进度。
        private static void DoQnxLog(string argRaw)
        {
            if (!RequireDevice("")) return;

            string src = (argRaw == null ? "" : argRaw).Trim();
            if (src.Length == 0) src = "/share/log";
            if (!src.StartsWith("/", StringComparison.Ordinal))
            {
                Fail("路径要以 / 开头：" + src);
                Hint("默认是 /share/log，一般不用带参数");
                return;
            }

            // 先判类型：目录 / 文件 / 不存在。三者处理方式不同，也避免拉一个空目录
            string kind = ShellValue("if [ -d " + src + " ]; then echo dir; elif [ -f "
                                     + src + " ]; then echo file; else echo none; fi");
            kind = (kind ?? "").Trim();
            if (kind == "none" || kind.Length == 0)
            {
                Fail("设备上没有 " + src);
                Hint("确认是 QNX 项目；可以试 :ls /share 看有哪些目录");
                return;
            }

            string dst = OutDir("qnx");
            Echo("pull", src + "  →  " + dst);

            string o = "", e = "";
            int rc = AdbCall(new List<string> { "pull", src, dst }, out o, out e);
            string all = (o + "\n" + e).Trim();
            CMD_OK = (rc == 0);
            if (CMD_OK)
            {
                Ok("QNX 日志已导出：" + dst);
                // adb pull 的进度行很长，只回显最后一行（通常是 "1 file pulled..."）
                string last = all.Length > 0 ? all.Substring(all.LastIndexOf('\n') + 1).Trim() : "";
                if (last.Length > 0) Hint(last);
            }
            else
            {
                Fail("导出失败（rc=" + rc + "）");
                if (all.Length > 0) Hint(FirstLine(all));
                Hint("QNX 共享目录有时只有 root 可读：先 :root 再试");
            }
        }

        // :proxydel   删除代理：三个键分别删、分别回显
        //
        // 为什么不在 cmds.ini 里写一条 `a; b; c`：那样只有一段合并输出，
        // 某个键没删掉时看不出是哪一条。分三次 ShellStep 才能逐条对账。
        private static void DoProxyDel()
        {
            if (!RequireDevice("")) return;
            CMD_OK = true;
            string[] keys = new string[]
            {
                "http_proxy",
                "global_http_proxy_host",
                "global_http_proxy_port"
            };
            for (int i = 0; i < keys.Length; i++)
            {
                if (!ShellStep("settings delete global " + keys[i], "删除 " + keys[i]))
                    CMD_OK = false;
            }
            // 双判：删完回读一次，只删 http_proxy 会留下 host/port 残值
            string left = ShellValue("settings get global http_proxy");
            if (left != null && left.Trim().Length > 0 && left.Trim() != "null")
            {
                Warn("http_proxy 回读仍是「" + left.Trim() + "」，可能被系统策略写回");
                CMD_OK = false;
            }
            else if (CMD_OK) Ok("三个代理键已删除，回读 http_proxy = null");
        }

        // :sxlog set   只写 privacy_enabled=true（不重启、不动属性）
        private static void DoSxTraceSet()
        {
            if (!RequireDevice("")) return;
            if (!ShellStep("settings put global privacy_enabled true", "privacy_enabled=true"))
            {
                Fail("写入失败，需要 root：先 :root 再重试");
                return;
            }
            string pv = ShellValue("settings get global privacy_enabled");
            // 2026-11-19：原来只认 "1"，但这台车机回读的是字符串 "true" ——
            // 写入成功也被判成失败（用户反馈「打红星但还是 true」）。
            // Settings 的值在不同 ROM 上可能是 1 / true / on，三种都算开。
            CMD_OK = PrivacyOn(pv);
            if (CMD_OK) Ok("privacy_enabled = " + pv + "（已回读确认）");
            else Warn("写入后回读是「" + pv + "」，可能被系统策略覆盖");
        }

        /// <summary>privacy_enabled 的回读值是否代表"已开启"（1 / true / on，大小写不敏感）。</summary>
        internal static bool PrivacyOn(string v)
        {
            if (v == null) return false;
            string t = v.Trim().ToLowerInvariant();
            return t == "1" || t == "true" || t == "on";
        }

        // :wsdevid   查询设备 ID（DID + android_id）
        private static void DoDeviceId()
        {
            if (!RequireDevice("")) return;

            Echo("read", "查设备标识");
            string did = ShellValue("getprop persist.sys.navi.did");
            string aid = ShellValue("settings get secure android_id");
            string uuid = ShellValue("getprop persist.sys.navi.uuid");

            UseOk();
            Console.WriteLine("  navi.did      : " + (did.Length > 0 ? did : "(空)"));
            Console.WriteLine("  android_id    : " + (aid.Length > 0 ? aid : "(空)"));
            Console.WriteLine("  navi.uuid     : " + (uuid.Length > 0 ? uuid : "(空)"));
            UseDefault();

            CMD_OK = did.Length > 0 || aid.Length > 0;
            if (!CMD_OK) Hint("三项都取不到：确认设备在线（devices），属性可能未烧录");
        }

        // :url <地址>    用桌面系统默认浏览器打开链接
        //
        // 为什么放内置：车机上的 am start 是"在车机上打开"，用户要的是
        // "在电脑上打开"——这对排查云端页面（埋点校验页 / 讯飞 IOT）才有意义。
        private static void DoOpenUrl(string argRaw)
        {
            string u = (argRaw == null ? "" : argRaw).Trim();
            if (u.Length == 0)
            {
                Fail("要给一个网址");
                Hint("例：:url https://link.xfyun.cn/logs");
                return;
            }

            // 允许省略 scheme，别因为少打 https:// 就报错
            if (!u.StartsWith("http://", StringComparison.OrdinalIgnoreCase)
                && !u.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
            {
                u = "https://" + u;
            }

            Echo("open", u);
            try
            {
                System.Diagnostics.ProcessStartInfo psi =
                    new System.Diagnostics.ProcessStartInfo(u);
                psi.UseShellExecute = true;
                System.Diagnostics.Process.Start(psi);
                CMD_OK = true;
                Ok("已用系统浏览器打开：" + u);
            }
            catch (Exception ex)
            {
                CMD_OK = false;
                Fail("打开失败：" + ex.Message);
                Hint("把地址复制到浏览器手动打开：" + u);
            }
        }

        // ---- 上面用到的小工具 ----

        // :scrcpy <屏号|名称>   用外挂 scrcpy 开一个独立投屏窗口
        //
        // 为什么不走 cmds.ini：那条路只发 adb 参数，而 scrcpy 是电脑上的
        // 独立进程（自己开 SDL 窗口渲染视频流），必须由本程序直接拉起。
        //
        // 屏位映射按用户 2026-11-15 给的清单，不要自己推断：
        //   主屏 0 · 后排屏 1 · HUD 3 · 副屏 4 · PHUD-B 9 · PHUD-C 10
        // 注意副屏是 4 —— 早前按 dumpsys 猜的 2 是旧车型的编号，这里以实车为准。
        private static void DoScrcpy(string argRaw)
        {
            string a = (argRaw == null ? "" : argRaw).Trim();
            if (a.Length == 0)
            {
                Info("用法：:scrcpy <屏号|名称>");
                Hint("主屏 0 · 后排屏 1 · HUD 3 · 副屏 4 · PHUD-B 9 · PHUD-C 10");
                return;
            }

            int id = -1;
            string name = "";
            switch (a.ToLowerInvariant())
            {
                case "主屏": case "main": case "center": id = 0; name = "主屏"; break;
                case "后排": case "后排屏": case "rear": id = 1; name = "后排屏"; break;
                case "hud": id = 3; name = "HUD"; break;
                case "副屏": case "副驾": case "cluster": case "passenger": id = 4; name = "副屏"; break;
                case "phud-b": case "phudb": case "phud_b": id = 9; name = "PHUD-B"; break;
                case "phud-c": case "phudc": case "phud_c": id = 10; name = "PHUD-C"; break;
            }
            if (id < 0)
            {
                if (!int.TryParse(a, out id) || id < 0)
                {
                    Fail("不认识这个屏：" + a);
                    Hint("可用：主屏 0 / 后排屏 1 / HUD 3 / 副屏 4 / PHUD-B 9 / PHUD-C 10");
                    return;
                }
                name = "屏 " + id;
            }

            Echo("scrcpy", "--display-id=" + id + "  (" + name + ")");
            CMD_OK = false;
            string err = "";
            bool ok = false;
            try { ok = Scrcpy.Launch(id, name, out err); }
            catch (Exception ex) { err = "启动异常：" + ex.Message; }

            if (ok)
            {
                CMD_OK = true;
                Ok("已打开 scrcpy 窗口：「" + name + "」display-id=" + id);
                Hint("只投屏不接管输入（--no-control），不会误触车机");
            }
            else
            {
                Fail("scrcpy 启动失败：" + err);
                Hint("到「投屏」页点「重新查找」或「选择…」指定 scrcpy.exe");
            }
        }

        // 跑一条设备 shell 并回显结果；返回是否成功（rc==0 且没有报错关键字）
        private static bool ShellStep(string inner, string desc)
        {
            Echo("shell", inner);
            string o = "";
            string e = "";
            int rc = ShellCall(CUR, inner, out o, out e);
            string combined = (o + "\n" + e).Trim();
            string low = combined.ToLowerInvariant();

            bool bad = low.Contains("error") || low.Contains("denied")
                    || low.Contains("cannot") || low.Contains("not found")
                    || low.Contains("fail");

            if (rc == 0 && !bad)
            {
                UseOk();
                Console.WriteLine("  \u221A " + desc
                    + (combined.Length > 0 ? "：" + FirstLine(combined) : ""));
                UseDefault();
                return true;
            }

            UseErr();
            Console.WriteLine("  \u00D7 " + desc
                + (combined.Length > 0 ? "：" + FirstLine(combined) : "（无输出）"));
            UseDefault();
            return false;
        }

        // 跑一条设备 shell，只取第一行值（查询类用）
        private static string ShellValue(string inner)
        {
            string o = "";
            string e = "";
            try { ShellCall(CUR, inner, out o, out e); } catch { }
            string v = FirstLine((o + "\n" + e).Trim());
            return v == null ? "" : v.Trim();
        }

        // 等设备重启回来：每 2 秒问一次，总上限 maxSec 秒。
        //   返回 实际等待秒数（>0 表示上线）；0 表示超时；-1 表示用户点了停止。
        private static int WaitBoot(int maxSec)
        {
            int waited = 0;
            while (waited < maxSec)
            {
                if (GUISTOP)
                {
                    GUISTOP = false;
                    return -1;
                }

                System.Threading.Thread.Sleep(2000);
                waited += 2;

                if (GUISTOP)
                {
                    GUISTOP = false;
                    return -1;
                }

                string o = "";
                string e = "";
                int rc = AdbCall(new List<string> { "get-state" }, out o, out e);
                if (rc != 0) continue;

                string st = (o + e).Trim().ToLowerInvariant();
                if (st.IndexOf("device") < 0) continue;

                // 光 get-state 回来还不够：刚起来时 settings 还没就绪，
                // 再确认一次 boot_completed，避免后面 settings put 白写。
                string bc = ShellValue("getprop sys.boot_completed");
                if (bc == "1") return waited;
            }
            return 0;
        }
    }
}
