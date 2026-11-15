// ============================================================================
//  GuiSelfCheck.cs - GUI 布局自检
//
//  为什么需要它：
//    GUI 的正确性很大一部分是"比例和位置对不对"，靠人眼看截图既慢又不可回归。
//    这里构造出真的窗体、走真的布局代码，然后按可判定的数学关系断言：
//      · 输出区是否占主区 3/4
//      · 反馈窗口是否占窗口高 1/4
//      · 两个 Tab 是否互斥显示
//      · 输入框/按钮是否重叠、是否越界
//    全部通过则退出码 0，否则 1 —— 可以直接进 CI。
//
//  刻意不依赖 Application.Run：构造 + PerformLayout 就够，窗口从不显示，
//  所以在没有桌面的环境里也能跑。
// ============================================================================
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Reflection;
using System.Text;
using System.Windows.Forms;

namespace AdbLogExport.Gui
{
    internal static class GuiSelfCheck
    {
        private static int _fail = 0;
        private static StringBuilder _log = new StringBuilder();

        // ------------------------------------------------------------------
        //  为什么不能直接用 Control.Visible 做断言：
        //    WinForms 的 Visible **getter 会沿父链继承** ——
        //      public bool Visible { get { return GetVisibleCore(); } }
        //      GetVisibleCore(): if (parent == null || !parent.Visible) return false;
        //    自检刻意不显示窗体（否则需要桌面、会闪窗、无法进 CI），
        //    于是父窗体 Visible=false，所有子控件一律返回 false：
        //      "隐藏" 的断言全过（因为本来就是 false），
        //      "显示" 的断言全挂（设了 true 也读成 false）。
        //    这不是布局错了，是断言读错了对象。
        //
        //  正确做法：读控件**自身**的状态位 STATE_VISIBLE，不看父链。
        //  Control 的 State 位定义（.NET Framework 参考源 Control.cs）：
        //      STATE_VISIBLE = 0x00000002   STATE_ENABLED = 0x00000004
        //  用反射取 internal 的 GetState(int)，取不到就退回 Visible（真机运行时两者等价）。
        // ------------------------------------------------------------------

        private const int STATE_VISIBLE = 0x00000002;

        private static readonly MethodInfo MI_GETSTATE = typeof(Control).GetMethod(
            "GetState", BindingFlags.Instance | BindingFlags.NonPublic,
            null, new Type[] { typeof(int) }, null);

        /// <summary>读控件自身的 visible 状态位，忽略父链继承。</summary>
        private static bool OwnVisible(Control c)
        {
            if (c == null) return false;
            if (MI_GETSTATE != null)
            {
                try { return (bool)MI_GETSTATE.Invoke(c, new object[] { STATE_VISIBLE }); }
                catch { }
            }
            return c.Visible;
        }

        private static void Line(string s)
        {
            _log.AppendLine(s);
        }

        private static List<string> SafeHist(GuiMain f)
        {
            try { return f.GetHistory(); }
            catch { return null; }
        }

        private static void Check(string name, bool cond, string actual)
        {
            if (cond)
            {
                Line("  [OK]   " + name);
            }
            else
            {
                Line("  [FAIL] " + name + "   （实际：" + actual + "）");
                _fail++;
            }
        }

        internal static int Run()
        {
            Line("== GUI 布局自检 ==");
            Line("");

            GuiMain f = null;
            try
            {
                f = new GuiMain();
            }
            catch (Exception ex)
            {
                Line("  [FAIL] 窗体构造异常：" + ex);
                Dump();
                return 1;
            }

            try
            {
                // 跑一次真实布局。窗口不显示，但布局代码是同一份。
                f.PerformLayout();
                f.RunSelfCheckBody(_log);
            }
            catch (Exception ex)
            {
                Line("  [FAIL] 自检过程异常：" + ex);
                _fail++;
            }
            finally
            {
                try { f.Dispose(); } catch { }
            }

            Line("");
            Line(_fail == 0 ? "  自检全部通过" : "  自检失败 " + _fail + " 项");
            Dump();
            return _fail == 0 ? 0 : 1;
        }

        private static void Dump()
        {
            try
            {
                // 落点与 gui_trace.log 一致：%LOCALAPPDATA%\adb_Tool\logs。
                // 不让运行期文件出现在发布目录里（发布包要能只读运行、要能直接拷给别人）。
                string p = System.IO.Path.Combine(
                    GuiEntry.LogDir(), "gui_selfcheck.log");
                System.IO.File.WriteAllText(p, _log.ToString(), new UTF8Encoding(true));
            }
            catch { }

            // 同时写一份到 stdout：命令行重定向时直接能看到
            try { Console.WriteLine(_log.ToString()); }
            catch { }
        }

        // ---------------- 供窗体调用的断言体 ----------------

        internal static void Body(GuiMain f, StringBuilder output)
        {
            // 追加到调用方的缓冲区：标题由 Run() 先写好，这里接着往里写
            StringBuilder prev = _log;
            if (output != null) _log = output;

            try
            {
                BodyCore(f);
            }
            finally
            {
                _log = prev;
            }
        }

        private static void BodyCore(GuiMain f)
        {

            Rectangle cr = f.ClientRectangle;
            Line("  窗体客户区：" + cr.Width + " x " + cr.Height);

            // ---- 1. 顶栏 / Tab / 底栏 ----
            Panel top = f.GetTopBar();
            Panel tab = f.GetTabBar();
            Panel bottom = f.GetBottomBar();

            Check("顶栏存在且高度合理", top != null && top.Height >= 36 && top.Height <= 60,
                top == null ? "null" : top.Height.ToString());
            Check("Tab 栏存在", tab != null && tab.Height >= 28 && tab.Height <= 50,
                tab == null ? "null" : tab.Height.ToString());
            Check("底栏存在且高度合理", bottom != null && bottom.Height >= 20 && bottom.Height <= 40,
                bottom == null ? "null" : bottom.Height.ToString());

            // ---- 2. 两个 Tab 互斥 ----
            Panel pCmd = f.GetPageCmd();
            Panel pQuick = f.GetPageQuick();
            Check("指令输入页存在", pCmd != null, pCmd == null ? "null" : "ok");
            Check("快捷指令页存在", pQuick != null, pQuick == null ? "null" : "ok");

            f.SwitchTabForCheck(0);
            f.PerformLayout();
            bool cmdVisible = OwnVisible(pCmd);
            bool quickHidden = !OwnVisible(pQuick);
            Check("切到 Tab1：指令输入页显示", cmdVisible,
                "cmd=" + OwnVisible(pCmd) + " quick=" + OwnVisible(pQuick)
                + "（窗体未显示，按自身状态位判定）");
            Check("切到 Tab1：快捷指令页隐藏", quickHidden,
                "quick=" + OwnVisible(pQuick));

            f.SwitchTabForCheck(1);
            f.PerformLayout();
            Check("切到 Tab2：快捷指令页显示", OwnVisible(pQuick),
                "quick=" + OwnVisible(pQuick) + " cmd=" + OwnVisible(pCmd));
            Check("切到 Tab2：指令输入页隐藏", !OwnVisible(pCmd),
                "cmd=" + OwnVisible(pCmd));

            // ---- 3. Tab1：输出区与输入行 ----
            f.SwitchTabForCheck(0);
            f.PerformLayout();

            RichTextBox outBox = f.GetOutputBox();
            Panel inBar = f.GetInputBar();
            Check("输出区存在", outBox != null, outBox == null ? "null" : "ok");
            Check("输入行存在", inBar != null && inBar.Height >= 36 && inBar.Height <= 70,
                inBar == null ? "null" : inBar.Height.ToString());

            if (outBox != null && inBar != null && pCmd.Height > 0)
            {
                int pageH = pCmd.Height;
                int outH = outBox.Height;
                int barH = inBar.Height;
                double ratio = (double)outH / pageH;

                Line("  指令输入页高=" + pageH + "  输出区高=" + outH
                     + "  输入行高=" + barH + "  输出占比=" + ratio.ToString("0.000"));

                // 输出区应占主区约 3/4（扣除输入行后基本就是全部剩余空间）
                Check("输出区占主区 >= 70%", ratio >= 0.70, ratio.ToString("0.000"));
                Check("输出区与输入行不重叠",
                    outBox.Bottom <= inBar.Top + 1,
                    "outBottom=" + outBox.Bottom + " inTop=" + inBar.Top);
            }

            // 输入框与按钮不重叠、不越界
            TextBox inp = f.GetInputBox();
            if (inp != null && inBar != null)
            {
                Check("输入框在输入行内", inp.Left >= 0 && inp.Right <= inBar.Width + 1,
                    "L=" + inp.Left + " R=" + inp.Right + " barW=" + inBar.Width);
                Check("输入框宽度 >= 120", inp.Width >= 120, inp.Width.ToString());

                Button[] btns = f.GetInputButtons();
                if (btns != null && btns.Length == 4)
                {
                    bool overlap = false;
                    for (int i = 0; i < btns.Length - 1; i++)
                    {
                        if (btns[i].Left < btns[i + 1].Right && btns[i + 1].Left < btns[i].Right)
                            overlap = true;
                    }
                    Check("四个按钮互不重叠", !overlap, overlap ? "有重叠" : "ok");

                    bool inside = true;
                    for (int i = 0; i < btns.Length; i++)
                    {
                        if (btns[i].Left < 0 || btns[i].Right > inBar.Width + 1) inside = false;
                    }
                    Check("四个按钮都在输入行内", inside, inside ? "ok" : "越界");

                    Check("输入框右边界在按钮左侧",
                        inp.Right <= btns[btns.Length - 1].Left,
                        "inpR=" + inp.Right + " btnL=" + btns[btns.Length - 1].Left);
                }
            }

            // ---- 4. Tab2：反馈窗口占窗口高 1/4 ----
            f.SwitchTabForCheck(1);
            f.PerformLayout();

            Panel feed = f.GetFeedPanel();
            Check("反馈窗口存在", feed != null, feed == null ? "null" : "ok");
            if (feed != null)
            {
                double fr = (double)feed.Height / cr.Height;
                Line("  反馈窗口高=" + feed.Height + "  窗口高=" + cr.Height
                     + "  占比=" + fr.ToString("0.000"));
                // 允许 ±6% 的浮动（有最小/最大高度夹取）
                Check("反馈窗口约占窗口高 1/4（0.19~0.31）",
                    fr >= 0.19 && fr <= 0.31, fr.ToString("0.000"));
            }

            Panel qTop = f.GetQuickTop();
            Check("快捷指令占位区存在", qTop != null, qTop == null ? "null" : "ok");
            if (qTop != null && feed != null)
            {
                Check("占位区与反馈窗口不重叠",
                    qTop.Bottom <= feed.Top + 1,
                    "qTopBottom=" + qTop.Bottom + " feedTop=" + feed.Top);
                Check("占位区高度 > 0", qTop.Height > 0, qTop.Height.ToString());
            }

            ListView lv = f.GetFeedList();
            Check("反馈列表存在且有 4 列", lv != null && lv.Columns.Count == 4,
                lv == null ? "null" : lv.Columns.Count.ToString());

            // ---- 4.5 反馈隔离：两页结果互不串扰 ----
            //
            // 需求：指令输入的报错/成功不要进快捷指令的反馈窗口，反之亦然。
            // 走与 EndWork 相同的分流逻辑验证：
            //   source=0（指令输入页）-> 反馈列表真实行数不变
            //   source=1（快捷指令页）-> 反馈列表真实行数 +1
            if (f != null)
            {
                int before = f.FeedRealCount();
                f.RecordCmdResultForTest("ls", true, 0);        // 指令输入页
                f.RecordCmdResultForTest(":which ls", true, 0); // 指令输入页
                int afterCmd = f.FeedRealCount();
                Check("反馈隔离：指令输入页结果不写反馈",
                    afterCmd == before, before + " -> " + afterCmd);

                f.RecordCmdResultForTest("pull D:\\logs", true, 1); // 快捷指令页
                int afterQuick = f.FeedRealCount();
                Check("反馈隔离：快捷指令页结果写入反馈",
                    afterQuick == before + 1, before + " -> " + afterQuick);
            }

            // ---- 5. 输出着色器 ----
            GuiSink sk = new GuiSink();
            sk.SyncColor(ConsoleColor.Green);
            sk.Write("ok line\n");
            sk.SyncColor(ConsoleColor.Red);
            sk.Write("bad line\n");
            List<GuiLine> got = new List<GuiLine>();
            sk.Drain(delegate(GuiLine l) { got.Add(l); });

            Check("输出捕获：采到 2 行", got.Count == 2, got.Count.ToString());
            if (got.Count == 2)
            {
                Check("输出捕获：成功行级别=1", got[0].Level == 1, got[0].Level.ToString());
                Check("输出捕获：失败行级别=2", got[1].Level == 2, got[1].Level.ToString());
                Check("输出捕获：颜色非空", !got[0].Fore.IsEmpty, got[0].Fore.ToString());
                Check("输出捕获：文本正确", got[0].Text == "ok line", got[0].Text);
            }

            // 行内回车（等待动画）应被丢弃
            GuiSink sk2 = new GuiSink();
            sk2.Write("abc\r ...");
            List<GuiLine> g2 = new List<GuiLine>();
            sk2.Write("\n");
            sk2.Drain(delegate(GuiLine l) { g2.Add(l); });
            Check("输出捕获：丢弃同行动画", g2.Count == 1 && g2[0].Text == "abc",
                g2.Count == 0 ? "(none)" : g2[0].Text);

            // ---- 6. 输入预处理与命令行版等价 ----
            //
            // 需求第 4 条是"指令输入窗口完全保留当前工具的能力"。
            // 这一条最容易被破坏的地方不是命令逻辑（那部分是共用的 Dispatch），
            // 而是**命令送进 Dispatch 之前的预处理**：命令行版做的是
            //     line = NormalizeLead(line.Trim());
            // GUI 若漏掉 NormalizeLead，中文输入法下打的「：h」就会被判成未知命令 ——
            // 同一条命令两种结果，能力就没保住。
            // 下面直接调同一个函数，锁死"两端预处理必须一致"这个契约。
            Check("预处理：半角命令原样通过",
                App.NormalizeLead("  ls  ".Trim()) == "ls",
                App.NormalizeLead("  ls  ".Trim()));
            Check("预处理：全角冒号 :h 归一化",
                App.NormalizeLead("\uFF1Ah") == ":h",
                App.NormalizeLead("\uFF1Ah"));
            Check("预处理：全角冒号 :q 归一化",
                App.NormalizeLead("\uFF1Aq") == ":q",
                App.NormalizeLead("\uFF1Aq"));
            Check("预处理：全角叹号 !cmd 归一化",
                App.NormalizeLead("\uFF01ls") == "!ls",
                App.NormalizeLead("\uFF01ls"));
            // 反例：要发出去的中文不能被改（否则"发消息"功能就坏了）
            Check("预处理：普通中文文本不被改写",
                App.NormalizeLead("你好！") == "你好！",
                App.NormalizeLead("你好！"));
            Check("预处理：带空格的路径不被改写",
                App.NormalizeLead("cd /sdcard/my dir") == "cd /sdcard/my dir",
                App.NormalizeLead("cd /sdcard/my dir"));

            // 历史必须是共用的那一份：GUI 若能自建一份，就会出现
            // "命令行敲过、GUI 翻不到"的分叉
            List<string> gh = SafeHist(f);
            Check("历史与命令行共用同一份", gh != null && ReferenceEquals(gh, App.Hist),
                gh == null ? "null" : "count=" + gh.Count);

            // ---- 7. 窗口缩放后的鲁棒性 ----
            f.ClientSize = new Size(820, 560);
            f.PerformLayout();
            f.SwitchTabForCheck(1);
            f.PerformLayout();
            if (feed != null)
            {
                double fr2 = (double)feed.Height / f.ClientRectangle.Height;
                Check("小窗口下反馈窗口仍约 1/4",
                    fr2 >= 0.18 && fr2 <= 0.33, fr2.ToString("0.000"));
            }
            if (inp != null)
            {
                Check("小窗口下输入框仍可点（宽 >= 100）", inp.Width >= 100, inp.Width.ToString());
            }

            f.ClientSize = new Size(1400, 900);
            f.PerformLayout();
            f.SwitchTabForCheck(0);
            f.PerformLayout();
            if (outBox != null && inBar != null && pCmd.Height > 0)
            {
                double r3 = (double)outBox.Height / pCmd.Height;
                Check("大窗口下输出区仍占主区 >= 70%", r3 >= 0.70, r3.ToString("0.000"));
            }

            // ---- 8. scrcpy 探测（A15） ----
            //
            // 用户装 winget 版 scrcpy 后最容易踩的坑：装是装好了，工具却说"找不到"。
            // 两个原因，都在这里锁死：
            //   1) winget 只改**注册表** PATH，运行中的进程环境变量不刷新；
            //   2) 包落在 Packages\Genymobile.scrcpy_*\scrcpy-win64-vX.Y\，
            //      而 WinGet\Links 里不一定有 shim（5.0.1 实测就没有）。
            List<int> candLvls = null;
            List<string> candList = Scrcpy.Candidates(out candLvls);
            bool hasPkg = false;
            for (int i = 0; i < candList.Count; i++)
            {
                if (candList[i].IndexOf("Genymobile.scrcpy", StringComparison.OrdinalIgnoreCase) >= 0
                    && candList[i].EndsWith("scrcpy.exe", StringComparison.OrdinalIgnoreCase))
                { hasPkg = true; break; }
            }
            Check("scrcpy 探测覆盖 winget Packages 目录", hasPkg,
                hasPkg ? "已覆盖" : candList.Count + " 个候选里没有 winget 包路径");

            HashSet<string> uniq = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            bool dup = false;
            for (int i = 0; i < candList.Count; i++) if (!uniq.Add(candList[i])) dup = true;
            Check("scrcpy 候选无重复（进程 PATH 与注册表 PATH 必然重叠）", !dup,
                "候选 " + candList.Count + " 个 / 去重后 " + uniq.Count + " 个");
            Check("scrcpy 候选等级与候选数一一对应",
                candLvls != null && candLvls.Count == candList.Count,
                candLvls == null ? "null" : candLvls.Count + " / " + candList.Count);
            Check("scrcpy 版本号解析（5.0.1 形制）",
                Scrcpy.ParseVersion("scrcpy 5.0.1 <https://github.com/Genymobile/scrcpy>") == "5.0.1",
                Scrcpy.ParseVersion("scrcpy 5.0.1 <https://github.com/Genymobile/scrcpy>"));
        }
    }
}
