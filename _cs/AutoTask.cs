// ============================================================================
//  AutoTask.cs - 定时任务引擎（2026-11-22 第 12 批需求 2.1 / 2.2）
// ----------------------------------------------------------------------------
//  用户给了两个 bat，要变成界面里的功能：
//    pull_log-iflytek-system.bat  每 30 分钟导出一次日志
//    check_crash.bat              每 30 分钟扫异常，**有新增才导出**
//
//  界面要求：
//    · 间隔可输入（不是写死 30 分钟）
//    · 开始之后有「暂停」按钮
//    · 导出到桌面 logcat
//
//  设计要点：
//
//  1) 一个引擎跑两种模式，而不是写两套循环。
//     两种模式的差别只有「每轮干什么」，循环骨架（暂停/恢复/停止/倒计时）
//     完全一样。分开写必然出现"一个能暂停一个不能"这种不一致。
//
//  2) 暂停 = 冻结倒计时，不是空转。
//     暂停时剩余秒数不减，恢复后从暂停那一刻继续。
//     如果只是"跳过执行但照常计时"，用户暂停 20 分钟回来发现马上又跑一轮，
//     完全不符合预期。
//
//  3) 等待必须分段 + 可中断。
//     Thread.Sleep(30 * 60 * 1000) 会让"停止"按钮失灵 30 分钟 ——
//     只能等这一觉睡完才看得到标志位。所以按 1 秒一片切。
//
//  4) 导出路径沿用工具的既有口径：桌面\logcat\<日期>\<时间戳>_Log
//     （和 :shot / :rec / :dlog 一致，用户找文件不用换地方）
// ============================================================================
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Threading;

namespace AdbLogExport
{
    internal static class AutoTask
    {
        // ---- 两种模式 ----
        internal const int ModeLog = 1;     // 定时导出日志
        internal const int ModeCrash = 2;   // 定时监听异常

        // ---- 状态（供 UI 查询/显示）----
        internal static bool Running = false;
        internal static bool Paused = false;
        internal static int CurMode = 0;
        internal static int IntervalMin = 30;
        internal static string LastDir = "";
        internal static int Round = 0;          // 已执行轮次
        internal static int RemainSec = 0;      // 距下一轮还剩多少秒

        private static Thread _th = null;
        private static volatile bool _stopReq = false;
        private static volatile bool _pauseReq = false;
        private static Action<string, string> _report;   // (text, level)

        // ====================================================================
        //  对外接口
        // ====================================================================

        /// <summary>启动。已启动时先停掉旧的（避免两个线程同时拉日志）。</summary>
        internal static bool Start(int mode, int intervalMin, Action<string, string> report)
        {
            Stop();                      // 幂等：先确保没有旧线程
            if (mode != ModeLog && mode != ModeCrash) return false;
            if (intervalMin < 1) intervalMin = 1;
            if (intervalMin > 720) intervalMin = 720;

            CurMode = mode;
            IntervalMin = intervalMin;
            Round = 0;
            RemainSec = 0;
            LastDir = "";
            _stopReq = false;
            _pauseReq = false;
            _report = report;
            Running = true;
            Paused = false;

            _th = new Thread(Loop);
            _th.IsBackground = true;
            _th.Start();
            return true;
        }

        internal static void Pause()
        {
            if (!Running) return;
            _pauseReq = true;
            Paused = true;
        }

        internal static void Resume()
        {
            if (!Running) return;
            _pauseReq = false;
            Paused = false;
        }

        internal static void Stop()
        {
            _stopReq = true;
            _pauseReq = false;
            try
            {
                if (_th != null && _th.IsAlive)
                {
                    // 正常情况 1 秒内就退出了（sleep 是 1 秒一片，
                    // 每个 pull 前也检查了 _stopReq）。
                    // 不用 Thread.Abort —— 它会在任意指令处抛 ThreadAbortException，
                    // 可能把 Directory.CreateDirectory 之类的调用打断在半路。
                    // 线程是 IsBackground，真卡在 adb 调用上也不会吊住进程退出。
                    _th.Join(3000);
                }
            }
            catch { }
            _th = null;
            Running = false;
            Paused = false;
            RemainSec = 0;
        }

        // ====================================================================
        //  主循环
        // ====================================================================
        private static void Loop()
        {
            try
            {
                Say("任务已启动（间隔 " + IntervalMin + " 分钟）", "ok");

                while (!_stopReq)
                {
                    // 暂停时不清倒计时，也不执行
                    if (_pauseReq)
                    {
                        Thread.Sleep(300);
                        continue;
                    }

                    Round++;
                    Say("──── 第 " + Round + " 轮 ────", "");

                    try
                    {
                        if (CurMode == ModeLog) DoLogExport();
                        else DoCrashScan();
                    }
                    catch (Exception ex)
                    {
                        Say("本轮出错：" + Brief(ex), "bad");
                    }

                    if (_stopReq) break;

                    // 倒计时（分段，保证暂停/停止能及时响应）
                    RemainSec = IntervalMin * 60;
                    while (RemainSec > 0 && !_stopReq)
                    {
                        if (_pauseReq)
                        {
                            Thread.Sleep(300);
                            continue;   // 暂停：剩余秒数不递减
                        }
                        Thread.Sleep(1000);
                        RemainSec--;
                    }
                    RemainSec = 0;
                }

                Say("任务已停止", "");
            }
            catch (Exception ex)
            {
                Say("任务异常退出：" + Brief(ex), "bad");
            }
            finally
            {
                Running = false;
                Paused = false;
            }
        }

        // ====================================================================
        //  模式 1：定时导出日志
        //  对应 pull_log-iflytek-system.bat
        // ====================================================================
        //
        //  原脚本导 6 个目录。这里保持完全一致 —— 用户现场就是按这个清单取证的，
        //  少导一个可能导致事后查不到某个模块的日志。
        private static readonly string[] LOG_PULLS = new string[]
        {
            "/data/anr",
            "/data/tombstones",
            "/data/system/dropbox",
            "/data/misc/perfetto-traces",
            "/sdcard/iflytek_log",
            "/log/android_log/androidlog"
        };

        private static void DoLogExport()
        {
            string dir = MakeStampDir("_Log");
            Say("导出到：" + dir, "");
            LastDir = dir;

            // root：anr / tombstones / dropbox 都是 root 才能读的
            Say("  adb root", "");
            ShellQuick("root");
            Thread.Sleep(700);   // root 后 adbd 会重连，等一下

            int okN = 0, failN = 0;
            for (int i = 0; i < LOG_PULLS.Length; i++)
            {
                if (_stopReq) { Say("  已请求停止，中断导出", "warn"); return; }

                string remote = LOG_PULLS[i];
                Say("  pull " + remote, "");
                string err = "";
                bool ok = PullTo(remote, dir, out err);
                if (ok)
                {
                    okN++;
                }
                else
                {
                    failN++;
                    // 目录不存在是常态（不是每台车都有 perfetto 日志），
                    // 所以降级为提示，不算失败
                    Say("    跳过（" + BriefText(err) + "）", "warn");
                }
            }

            Say("  导出完成：成功 " + okN + " 项，跳过 " + failN + " 项", okN > 0 ? "ok" : "warn");
        }

        // ====================================================================
        //  模式 2：定时监听异常（有新增才导出）
        //  对应 check_crash.bat
        // ====================================================================
        //
        //  原脚本的三个扫描 + 指纹比对逻辑：
        //    ls /data/system/dropbox | grep app_crash
        //    ls /data/anr | grep anr
        //    ls /data/tombstones | grep -E 'tombstone_[0-9]+$'
        //    把三份列表拼起来当"指纹"，和上次比；一样就跳过，不一样才导出。
        //
        //  为什么用指纹而不是计数：崩溃文件可能被系统轮转删除，
        //  只看数量会漏（删一个又新增一个，数量不变但内容变了）。
        private static string _lastFp = "";

        private static void DoCrashScan()
        {
            Say("  扫描异常文件…", "");
            ShellQuick("root");
            Thread.Sleep(500);

            string crashList = ShellValue("ls /data/system/dropbox 2>/dev/null | grep app_crash");
            string anrList = ShellValue("ls /data/anr 2>/dev/null | grep anr");
            string tombList = ShellValue("ls /data/tombstones 2>/dev/null | grep -E 'tombstone_[0-9]+$'");

            int nCrash = CountLines(crashList);
            int nAnr = CountLines(anrList);
            int nTomb = CountLines(tombList);
            int total = nCrash + nAnr + nTomb;

            Say("  anr=" + nAnr + "  crash=" + nCrash + "  tombstone=" + nTomb,
                total > 0 ? "warn" : "ok");

            if (total == 0)
            {
                Say("  [OK] 没有异常文件", "ok");
                return;
            }

            // 指纹 = 三份列表拼起来
            string fp = crashList + "\n--\n" + anrList + "\n--\n" + tombList;
            if (fp == _lastFp)
            {
                Say("  [无新增] 和上次扫描一样，跳过导出", "");
                return;
            }

            // 有变化 → 导出
            string name = Stamp() + "-Found" + nAnr + "_anr_" + nCrash + "_crash_" + nTomb + "_tombstone";
            string dir = MakeDir(name);
            Say("  [有新增] 导出到：" + dir, "warn");
            LastDir = dir;

            string[] pulls = { "/data/anr", "/data/system/dropbox", "/data/tombstones", "/data/misc/perfetto-traces" };
            for (int i = 0; i < pulls.Length; i++)
            {
                if (_stopReq) { Say("  已请求停止，中断导出", "warn"); return; }
                string err = "";
                PullTo(pulls[i], dir, out err);
            }

            _lastFp = fp;
            Say("  [完成] 已导出，下轮只报新增", "ok");
        }

        // ====================================================================
        //  辅助
        // ====================================================================

        // 桌面\logcat\<日期>\<时间戳>_Log
        private static string MakeStampDir(string suffix)
        {
            return MakeDir(Stamp() + suffix);
        }

        // 桌面\logcat\<日期>\<name>
        private static string MakeDir(string name)
        {
            string baseDir;
            try { baseDir = App.OutDir(""); }
            catch { baseDir = Path.Combine(DesktopPath(), "logcat"); }

            string dir = Path.Combine(baseDir, name);
            try { Directory.CreateDirectory(dir); } catch { }
            return dir;
        }

        private static string DesktopPath()
        {
            try
            {
                string d = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
                return string.IsNullOrEmpty(d) ? "C:\\" : d;
            }
            catch { return "C:\\"; }
        }

        // 2026-11-22 16-30-05（避免文件名里出现冒号 —— Windows 不允许）
        private static string Stamp()
        {
            DateTime t = DateTime.Now;
            return t.ToString("yyyy-MM-dd") + " " + t.ToString("HH-mm-ss");
        }

        // 执行一条 adb 命令，不关心输出
        private static void ShellQuick(string cmd)
        {
            string o = "", e = "";
            try { App.ShellCall(App.CUR, cmd, out o, out e); } catch { }
        }

        // 取一条 adb shell 的输出（完整，不只第一行 —— 列文件要全部）
        private static string ShellValue(string cmd)
        {
            string o = "", e = "";
            try
            {
                App.ShellCall(App.CUR, cmd, out o, out e);
                return (o ?? "") + (e ?? "");
            }
            catch { return ""; }
        }

        // adb pull <remote> <dir>，返回是否成功
        private static bool PullTo(string remote, string dir, out string err)
        {
            err = "";
            string o = "", e = "";
            try
            {
                int rc = App.ShellCall(App.CUR, "pull " + remote + " \"" + dir + "\"", out o, out e);
                string all = (o ?? "") + (e ?? "");
                // pull 失败时输出里会带 "does not exist" / "No such file" / "error"
                if (all.IndexOf("No such file", StringComparison.OrdinalIgnoreCase) >= 0
                    || all.IndexOf("does not exist", StringComparison.OrdinalIgnoreCase) >= 0
                    || all.IndexOf("error:", StringComparison.OrdinalIgnoreCase) >= 0
                    || all.IndexOf("failed", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    err = all;
                    return false;
                }
                return rc == 0;
            }
            catch (Exception ex)
            {
                err = ex.Message;
                return false;
            }
        }

        private static int CountLines(string s)
        {
            if (string.IsNullOrEmpty(s)) return 0;
            int n = 0;
            string[] lines = s.Split('\n');
            for (int i = 0; i < lines.Length; i++)
            {
                string l = lines[i].Trim();
                // 过滤掉 shell 报错行（ls 目录不存在时会输出 ls: ...: No such file）
                if (l.Length == 0) continue;
                if (l.StartsWith("ls:")) continue;
                n++;
            }
            return n;
        }

        private static string Brief(Exception ex)
        {
            string m = (ex.Message ?? "").Replace("\r", "").Replace("\n", " ");
            return m.Length > 80 ? m.Substring(0, 80) + "…" : m;
        }

        private static string BriefText(string s)
        {
            string m = (s ?? "").Replace("\r", "").Replace("\n", " ").Trim();
            if (m.Length > 70) m = m.Substring(0, 70) + "…";
            return m.Length == 0 ? "未知原因" : m;
        }

        // 上报一行日志（level: "" | ok | warn | bad）
        private static void Say(string text, string level)
        {
            try
            {
                Action<string, string> r = _report;
                if (r != null) r(text, level);
            }
            catch { }
        }
    }
}
