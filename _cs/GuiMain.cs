// ============================================================================
//  GuiMain.cs - 主窗体
//
//  布局（自上而下）：
//    ① 顶栏  设备号 + 车型 + 环境（灰色状态条）
//    ② Tab   指令输入 / 快捷指令
//    ③ 内容区
//         Tab1：输出区（占主区 3/4）+ 输入行
//         Tab2：快捷指令占位区 + 反馈窗口（占窗口高 1/4）
//    ④ 底栏  在线设备数 / 当前目录 / 耗时
//
//  线程模型：
//    Dispatch 会同步阻塞（adb 往返几百毫秒到几十秒），绝不能跑在 UI 线程上。
//    所以命令在后台线程执行，输出经 GuiSink 队列回到 UI 线程定时器消费。
//    同一时刻只允许一条命令在跑，避免 adb 并发冲突。
// ============================================================================
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace AdbLogExport.Gui
{
    internal sealed class GuiMain : Form
    {
        // ---------- 主题色 ----------
        private static readonly Color C_BG = Color.FromArgb(250, 250, 250);
        private static readonly Color C_PANEL = Color.White;
        private static readonly Color C_LINE = Color.FromArgb(222, 222, 222);
        private static readonly Color C_TEXT = Color.FromArgb(24, 24, 24);   // 主文字更深，更清晰
        private static readonly Color C_SUB = Color.FromArgb(92, 92, 92);    // 次文字提深
        private static readonly Color C_HINT = Color.FromArgb(122, 122, 122); // 弱文字提深，不再发虚
        private static readonly Color C_DEV = Color.FromArgb(160, 104, 0);
        private static readonly Color C_DIR = Color.FromArgb(0, 96, 96);
        private static readonly Color C_OK = Color.FromArgb(16, 112, 16);
        private static readonly Color C_ERR = Color.FromArgb(180, 18, 18);
        private static readonly Color C_WARN = Color.FromArgb(150, 90, 0);
        private static readonly Color C_DIM = Color.FromArgb(118, 118, 118); // 弱化文字提深

        // 字体：文字清晰第一要求 —— 字号整体比早期版本放大一档，
        // 界面 10f 起步、等宽 10.5f、小字 9.5f，对比度也相应提高。
        // 早期 9f/9.5f/8.5f 在高分屏或车载屏上偏小，用户看着费劲。
        private static readonly Font F_UI = new Font("Microsoft YaHei UI", 10f);
        private static readonly Font F_MONO = new Font("Consolas", 10.5f);
        private static readonly Font F_SMALL = new Font("Microsoft YaHei UI", 9.5f);

        // ---------- 顶栏 ----------
        private Panel _top;
        private Label _lbTitle, _lbDev, _lbEnv;
        private Panel _dot;

        // ---------- Tab ----------
        private Panel _tabBar;
        private TabBtn _tabCmd, _tabQuick;

        // ---------- Tab1 指令输入 ----------
        private Panel _pageCmd;
        private RichTextBox _out;         // 大输出区
        private Panel _inputBar;
        private Label _lbPromptDev, _lbPromptDir, _lbGt;
        private TextBox _input;
        private Button _btnRun, _btnStop, _btnClear, _btnCopy;

        // ---------- Tab2 快捷指令 ----------
        private Panel _pageQuick;
        private Panel _quickTop;          // 预留区
        private Panel _quickFeed;         // 反馈窗口（占窗口高 1/4）
        private ListView _feed;
        private ListViewItem _feedEmptyRow;   // 反馈窗口的空状态占位行

        // ---------- 底栏 ----------
        private Panel _bottom;
        private Label _lbStatus, _lbStatusRight;

        // ---------- 运行时 ----------
        private GuiSink _sink;
        private System.Windows.Forms.Timer _tick;
        private Thread _worker;
        private volatile bool _busy = false;

        // 当前正在执行的命令来自哪个页签：
        //    0 = 指令输入页（结果看上方大输出区，不写反馈窗口）
        //    1 = 快捷指令页（结果才写进反馈窗口）
        //
        // 为什么要区分：反馈窗口归"快捷指令"页独有。早期版本里 AddFeed 在每次
        // 命令结束时无条件写入一个共用的列表，于是"指令输入"页敲的 ls / :which
        // 也全流进了快捷指令页的反馈 —— 两个页签的执行结果混在一起。
        // 需求明确要求两边互不串扰，所以这里记下来源，EndWork 只把结果
        // 写进来源页签自己的那份历史。
        private volatile int _cmdSource = 0;
        // 历史直接用 App.Hist（命令行版 LoadHistory 填好的那一份），
        // 不再自建 _history —— 自建的结果是"命令行敲过的命令，GUI 里按 ↑ 翻不到"，
        // 而 GuiBoot 里那句 LoadHistory() 也就白读了。
        private int _histIdx = -1;
        private string _histDraft = "";
        private long _lastMs = 0;

        // 反馈窗口高度 = 窗口高 1/4（含标题区），按 design 要求固定比例
        private const double FEED_RATIO = 0.25;

        internal GuiMain()
        {
            try
            {
                BuildUi();
                InstallSink();
                BootDevice();
            }
            catch (Exception ex)
            {
                GuiEntry.Dump("GuiMain 构造", ex);
                throw;
            }
        }

        // ==================== 一、界面搭建 ====================

        private void BuildUi()
        {
            Text = "adb_log_export  GUI";
            StartPosition = FormStartPosition.CenterScreen;
            ClientSize = new Size(1080, 720);
            MinimumSize = new Size(820, 560);
            BackColor = C_BG;
            Font = F_UI;

            // ---- 顶栏 ----
            _top = new Panel();
            _top.Dock = DockStyle.Top;
            _top.Height = 46;
            _top.BackColor = C_PANEL;
            _top.Paint += delegate(object s, PaintEventArgs e)
            {
                using (Pen p = new Pen(C_LINE))
                    e.Graphics.DrawLine(p, 0, _top.Height - 1, _top.Width, _top.Height - 1);
            };

            _dot = new Panel();
            _dot.Size = new Size(8, 8);
            _dot.Location = new Point(16, 18);
            _dot.BackColor = C_HINT;

            _lbTitle = new Label();
            _lbTitle.Text = "adb_log_export";
            _lbTitle.Font = new Font("Microsoft YaHei UI", 10.5f, FontStyle.Bold);
            _lbTitle.ForeColor = C_TEXT;
            _lbTitle.AutoSize = true;
            _lbTitle.Location = new Point(32, 12);

            _lbDev = new Label();
            _lbDev.Text = "正在检测设备 …";
            _lbDev.ForeColor = C_SUB;
            _lbDev.AutoSize = true;
            _lbDev.Location = new Point(150, 14);

            _lbEnv = new Label();
            _lbEnv.Text = "";
            _lbEnv.ForeColor = C_HINT;
            _lbEnv.AutoSize = true;
            _lbEnv.Anchor = AnchorStyles.Top | AnchorStyles.Right;

            _top.Controls.Add(_dot);
            _top.Controls.Add(_lbTitle);
            _top.Controls.Add(_lbDev);
            _top.Controls.Add(_lbEnv);

            // ---- Tab 栏 ----
            _tabBar = new Panel();
            _tabBar.Dock = DockStyle.Top;
            _tabBar.Height = 40;
            _tabBar.BackColor = C_BG;
            _tabBar.Paint += delegate(object s, PaintEventArgs e)
            {
                using (Pen p = new Pen(C_LINE))
                    e.Graphics.DrawLine(p, 0, _tabBar.Height - 1, _tabBar.Width, _tabBar.Height - 1);
            };

            _tabCmd = new TabBtn("指令输入");
            _tabCmd.Location = new Point(8, 4);
            _tabCmd.Click += delegate { SwitchTab(0); };

            _tabQuick = new TabBtn("快捷指令");
            _tabQuick.Location = new Point(8 + 96, 4);
            _tabQuick.Click += delegate { SwitchTab(1); };

            _tabBar.Controls.Add(_tabCmd);
            _tabBar.Controls.Add(_tabQuick);

            // ---- 底栏（先 Dock Bottom，保证内容区正确填充）----
            _bottom = new Panel();
            _bottom.Dock = DockStyle.Bottom;
            _bottom.Height = 30;
            _bottom.BackColor = C_BG;
            _bottom.Paint += delegate(object s, PaintEventArgs e)
            {
                using (Pen p = new Pen(C_LINE))
                    e.Graphics.DrawLine(p, 0, 0, _bottom.Width, 0);
            };

            _lbStatus = new Label();
            _lbStatus.Text = "就绪";
            _lbStatus.ForeColor = C_SUB;
            _lbStatus.Font = F_SMALL;
            _lbStatus.AutoSize = true;
            _lbStatus.Location = new Point(12, 5);

            _lbStatusRight = new Label();
            _lbStatusRight.Text = "";
            _lbStatusRight.ForeColor = C_HINT;
            _lbStatusRight.Font = F_SMALL;
            _lbStatusRight.AutoSize = true;
            _lbStatusRight.Anchor = AnchorStyles.Top | AnchorStyles.Right;

            _bottom.Controls.Add(_lbStatus);
            _bottom.Controls.Add(_lbStatusRight);

            // ---- Tab1 指令输入页 ----
            _pageCmd = new Panel();
            _pageCmd.Dock = DockStyle.Fill;
            _pageCmd.BackColor = C_PANEL;

            // 输入行先 Dock Bottom（顺序很重要：先占底的）
            _inputBar = new Panel();
            _inputBar.Dock = DockStyle.Bottom;
            _inputBar.Height = 48;
            _inputBar.BackColor = C_BG;
            _inputBar.Paint += delegate(object s, PaintEventArgs e)
            {
                using (Pen p = new Pen(C_LINE))
                    e.Graphics.DrawLine(p, 0, 0, _inputBar.Width, 0);
            };

            _lbPromptDev = new Label();
            _lbPromptDev.Text = "";
            _lbPromptDev.Font = F_MONO;
            _lbPromptDev.ForeColor = C_DEV;
            _lbPromptDev.AutoSize = true;
            _lbPromptDev.Location = new Point(12, 13);

            _lbPromptDir = new Label();
            _lbPromptDir.Text = "";
            _lbPromptDir.Font = F_MONO;
            _lbPromptDir.ForeColor = C_DIR;
            _lbPromptDir.AutoSize = true;

            _lbGt = new Label();
            _lbGt.Text = " > ";
            _lbGt.Font = F_MONO;
            _lbGt.ForeColor = C_HINT;
            _lbGt.AutoSize = true;

            _input = new TextBox();
            _input.Font = F_MONO;
            _input.BorderStyle = BorderStyle.FixedSingle;
            _input.BackColor = C_PANEL;
            _input.ForeColor = C_TEXT;
            _input.Anchor = AnchorStyles.Left | AnchorStyles.Right | AnchorStyles.Top;

            _btnRun = MakeButton("执行");
            _btnRun.Click += delegate { RunCurrent(); };

            _btnStop = MakeButton("停止");
            _btnStop.ForeColor = C_ERR;
            _btnStop.Enabled = false;
            _btnStop.Click += delegate { StopCurrent(); };

            _btnClear = MakeButton("清屏");
            _btnClear.Click += delegate { _out.Clear(); };

            _btnCopy = MakeButton("复制");
            _btnCopy.Click += delegate { CopySelection(); };

            _inputBar.Controls.Add(_lbPromptDev);
            _inputBar.Controls.Add(_lbPromptDir);
            _inputBar.Controls.Add(_lbGt);
            _inputBar.Controls.Add(_input);
            _inputBar.Controls.Add(_btnRun);
            _inputBar.Controls.Add(_btnStop);
            _inputBar.Controls.Add(_btnClear);
            _inputBar.Controls.Add(_btnCopy);

            // 输出区最后 Dock Fill，填满剩余
            _out = new RichTextBox();
            _out.Dock = DockStyle.Fill;
            _out.BorderStyle = BorderStyle.None;
            _out.BackColor = C_PANEL;
            _out.ForeColor = C_TEXT;
            _out.Font = F_MONO;
            _out.ReadOnly = true;
            _out.WordWrap = false;
            _out.ScrollBars = RichTextBoxScrollBars.Both;
            _out.DetectUrls = false;
            _out.HideSelection = false;

            _pageCmd.Controls.Add(_out);
            _pageCmd.Controls.Add(_inputBar);

            // ---- Tab2 快捷指令页 ----
            _pageQuick = new Panel();
            _pageQuick.Dock = DockStyle.Fill;
            _pageQuick.BackColor = C_PANEL;
            _pageQuick.Visible = false;

            _quickFeed = new Panel();
            _quickFeed.Dock = DockStyle.Bottom;     // 底部的反馈窗口
            _quickFeed.BackColor = C_PANEL;
            _quickFeed.Paint += delegate(object s, PaintEventArgs e)
            {
                using (Pen p = new Pen(C_LINE))
                    e.Graphics.DrawLine(p, 0, 0, _quickFeed.Width, 0);
            };

            // 反馈窗口的标题条：不写标题的话，这一块只是一张表，
            // 用户不知道"这里是反馈"。同时把占比写出来，让 1/4 这个约定可见。
            Panel feedHead = new Panel();
            feedHead.Dock = DockStyle.Top;
            feedHead.Height = 26;
            feedHead.BackColor = C_PANEL;
            feedHead.Paint += delegate(object s, PaintEventArgs e)
            {
                using (Pen p = new Pen(C_LINE))
                    e.Graphics.DrawLine(p, 0, feedHead.Height - 1, feedHead.Width, feedHead.Height - 1);
            };

            Label feedTitle = new Label();
            feedTitle.Text = "执行反馈";
            feedTitle.Font = new Font("Microsoft YaHei UI", 10f, FontStyle.Bold);
            feedTitle.ForeColor = C_TEXT;
            feedTitle.AutoSize = true;
            feedTitle.Tag = "feedTitle";
            feedHead.Controls.Add(feedTitle);

            Label feedHint = new Label();
            feedHint.Text = "最近 200 条 · 双击可复制指令";
            feedHint.Font = F_SMALL;
            feedHint.ForeColor = C_HINT;
            feedHint.AutoSize = true;
            feedHint.Tag = "feedHint";
            feedHead.Controls.Add(feedHint);

            // 标题条内部排版：左标题、右提示，随宽度右对齐
            feedHead.Resize += delegate
            {
                feedTitle.Location = new Point(12, (feedHead.Height - feedTitle.Height) / 2);
                feedHint.Location = new Point(
                    Math.Max(12 + feedTitle.Width + 16, feedHead.Width - feedHint.Width - 12),
                    (feedHead.Height - feedHint.Height) / 2);
            };

            _feed = new ListView();
            _feed.Dock = DockStyle.Fill;
            _feed.View = View.Details;
            _feed.FullRowSelect = true;
            _feed.HeaderStyle = ColumnHeaderStyle.Nonclickable;
            _feed.BorderStyle = BorderStyle.None;
            _feed.Font = F_MONO;
            _feed.BackColor = C_PANEL;
            _feed.ForeColor = C_TEXT;
            _feed.Columns.Add("时间", 76, HorizontalAlignment.Left);
            _feed.Columns.Add("指令", 300, HorizontalAlignment.Left);
            _feed.Columns.Add("结果", 620, HorizontalAlignment.Left);
            _feed.Columns.Add("耗时", 70, HorizontalAlignment.Right);
            _feed.DoubleClick += delegate { CopyFeed(); };

            _quickFeed.Controls.Add(_feed);
            // Dock 顺序：先加 Fill 的列表，再加 Top 的标题条，
            // 否则标题条会被 Fill 抢占的区域盖住（WinForms 的 Dock 按 z 序反向占位）。
            _quickFeed.Controls.Add(feedHead);

            // 建好就铺一条空状态，别让用户第一次看到纯白面板
            SeedFeedPlaceholder();

            _quickTop = new Panel();
            _quickTop.Dock = DockStyle.Fill;
            _quickTop.BackColor = Color.FromArgb(247, 247, 247);

            Label ph = new Label();
            ph.Text = "快捷指令区（预留）";
            ph.Font = new Font("Microsoft YaHei UI", 11f, FontStyle.Bold);
            ph.ForeColor = C_SUB;
            ph.AutoSize = true;
            ph.Tag = "ph";
            _quickTop.Controls.Add(ph);

            Label ph2 = new Label();
            ph2.Text = "后续可放常用指令卡片、一键导出、批量操作";
            ph2.Font = F_SMALL;
            ph2.ForeColor = C_HINT;
            ph2.AutoSize = true;
            ph2.Tag = "ph2";
            _quickTop.Controls.Add(ph2);

            Label ph3 = new Label();
            ph3.Text = "提示：此区域内任何指令执行后，结果都会出现在下方反馈窗口";
            ph3.Font = F_SMALL;
            ph3.ForeColor = C_HINT;
            ph3.AutoSize = true;
            ph3.Tag = "ph3";
            _quickTop.Controls.Add(ph3);

            _quickTop.Resize += delegate { CenterPlaceholder(); };
            CenterPlaceholder();

            _pageQuick.Controls.Add(_quickTop);
            _pageQuick.Controls.Add(_quickFeed);

            // ---- 装配 ----
            Controls.Add(_pageCmd);
            Controls.Add(_pageQuick);
            Controls.Add(_tabBar);
            Controls.Add(_top);
            Controls.Add(_bottom);

            SwitchTab(0);

            // ---- 布局跟随 ----
            Resize += delegate { DoLayout(); };
            DoLayout();

            // ---- 键盘 ----
            _input.KeyDown += InputKeyDown;

            // ---- 定时器：消费输出队列 ----
            _tick = new System.Windows.Forms.Timer();
            _tick.Interval = 60;
            _tick.Tick += delegate { PumpOutput(); };
            _tick.Start();
        }

        private static Button MakeButton(string text)
        {
            Button b = new Button();
            b.Text = text;
            b.Font = F_UI;
            b.FlatStyle = FlatStyle.Flat;
            b.FlatAppearance.BorderColor = C_LINE;
            b.FlatAppearance.BorderSize = 1;
            b.BackColor = C_PANEL;
            b.ForeColor = C_TEXT;
            b.Size = new Size(60, 28);
            b.Cursor = Cursors.Hand;
            return b;
        }

        private void CenterPlaceholder()
        {
            Label a = null, b = null, c = null;
            foreach (Control k in _quickTop.Controls)
            {
                if ((string)k.Tag == "ph") a = k as Label;
                else if ((string)k.Tag == "ph2") b = k as Label;
                else if ((string)k.Tag == "ph3") c = k as Label;
            }
            if (a == null) return;
            int total = a.Height + 6 + (b != null ? b.Height : 0) + 14 + (c != null ? c.Height : 0);
            // 垂直居中：可用高度减去整块文字高度，再折半。
            // 原先写的是 (cy - total) / 2，其中 cy 本身已经是"高度的一半"，
            // 于是算出来只有正确位置的一半 —— 占位文字贴在偏上 1/3 处，
            // 看起来像"没对齐"，在大窗口下尤其明显。
            int y = (_quickTop.Height - total) / 2;
            a.Location = new Point((_quickTop.Width - a.Width) / 2, Math.Max(8, y));
            if (b != null) b.Location = new Point((_quickTop.Width - b.Width) / 2, a.Bottom + 6);
            if (c != null) c.Location = new Point((_quickTop.Width - c.Width) / 2, a.Bottom + 6 + (b != null ? b.Height : 0) + 14);
        }

        // ==================== 二、布局计算 ====================

        private void DoLayout()
        {
            int w = ClientSize.Width;
            int h = ClientSize.Height;

            // 顶栏右侧环境标签
            _lbEnv.Location = new Point(w - _lbEnv.Width - 16, 14);
            _lbStatusRight.Location = new Point(w - _lbStatusRight.Width - 12, 5);

            // ---- Tab1 输入行 ----
            int x = 12;
            _lbPromptDev.Location = new Point(x, 15);
            x += _lbPromptDev.Width;
            _lbPromptDir.Location = new Point(x, 15);
            x += _lbPromptDir.Width;
            _lbGt.Location = new Point(x, 15);
            x += _lbGt.Width;

            int btnW = 60;
            int gap = 6;
            int rightEdge = _inputBar.Width - 12;
            // 按钮在 48px 输入行里垂直居中：(48-28)/2 ≈ 10
            int btnY = 10;
            _btnCopy.Location = new Point(rightEdge - btnW, btnY);
            _btnClear.Location = new Point(_btnCopy.Left - gap - btnW, btnY);
            _btnStop.Location = new Point(_btnClear.Left - gap - btnW, btnY);
            _btnRun.Location = new Point(_btnStop.Left - gap - btnW, btnY);

            int inputW = _btnRun.Left - gap - x;
            if (inputW < 120) inputW = 120;
            _input.Location = new Point(x, 10);
            _input.Width = inputW;
            _input.Height = 28;

            // ---- Tab2 反馈窗口高度 = 窗口高 1/4 ----
            int feedH = (int)Math.Round(h * FEED_RATIO);
            if (feedH < 120) feedH = 120;
            if (feedH > h - 160) feedH = Math.Max(100, h - 160);
            _quickFeed.Height = feedH;

            // 列表列宽自适应
            if (_feed.Columns.Count == 4)
            {
                int avail = _feed.ClientSize.Width;
                int w1 = 76, w4 = 70, w2 = Math.Max(140, (int)(avail * 0.30));
                int w3 = Math.Max(120, avail - w1 - w2 - w4 - 24);
                _feed.Columns[0].Width = w1;
                _feed.Columns[1].Width = w2;
                _feed.Columns[2].Width = w3;
                _feed.Columns[3].Width = w4;
            }
        }

        // ==================== 三、Tab 切换 ====================

        private void SwitchTab(int idx)
        {
            bool cmd = (idx == 0);
            _pageCmd.Visible = cmd;
            _pageQuick.Visible = !cmd;
            _tabCmd.Active = cmd;
            _tabQuick.Active = !cmd;
            if (cmd)
            {
                _input.Focus();
                _input.Select(_input.TextLength, 0);
            }
            DoLayout();
        }

        // ==================== 四、输出接管 ====================

        private void InstallSink()
        {
            _sink = new GuiSink();
            Console.SetOut(_sink);
            Console.SetError(_sink);

            // 颜色旁路：Render.Use() 每次设色都会通知这里
            App.GUI_COLOR_HOOK = delegate(ConsoleColor c) { _sink.SyncColor(c); };
        }

        // 定时把队列里的行刷到界面上
        private void PumpOutput()
        {
            if (_sink == null) return;
            bool needScroll = false;
            int n = _sink.Drain(delegate(GuiLine l)
            {
                AppendLine(l);
                needScroll = true;
            });
            if (needScroll) ScrollToEnd();
        }

        private void AppendLine(GuiLine l)
        {
            if (string.IsNullOrEmpty(l.Text))
            {
                _out.AppendText(Environment.NewLine);
                return;
            }

            Color fore = l.Fore;
            if (fore.IsEmpty) fore = C_TEXT;

            // 原工具的提示符行（含 "ef2e593d:/xx >"）在 GUI 里由输入行自己显示，
            // 输出区不该再出现一遍，否则每条命令前面都多一行噪音。
            if (l.Text.IndexOf(" > ", StringComparison.Ordinal) >= 0
                && l.Text.TrimStart().Length > 3
                && l.Text.TrimStart()[0] != '\u2192'
                && l.Text.TrimStart()[0] != '\u221A'
                && l.Text.TrimStart()[0] != '\u00D7'
                && l.Text.TrimStart()[0] != '!'
                && l.Text.TrimStart()[0] != '-'
                && !char.IsDigit(l.Text.TrimStart()[0]))
            {
                int at = l.Text.IndexOf(" > ", StringComparison.Ordinal);
                string after = l.Text.Substring(at + 3);
                if (after.Trim().Length == 0) return;      // 纯提示符行，丢弃
            }

            _out.SelectionStart = _out.TextLength;
            _out.SelectionLength = 0;
            _out.SelectionColor = fore;
            _out.AppendText(l.Text);
            _out.AppendText(Environment.NewLine);
            _out.SelectionStart = _out.TextLength;
            _out.SelectionColor = C_TEXT;
        }

        private void ScrollToEnd()
        {
            try
            {
                _out.SelectionStart = _out.TextLength;
                _out.SelectionLength = 0;
                _out.ScrollToCaret();
            }
            catch { }
        }

        // ==================== 五、命令执行 ====================

        private void InputKeyDown(object sender, KeyEventArgs e)
        {
            if (e.KeyCode == Keys.Enter)
            {
                e.SuppressKeyPress = true;
                RunCurrent();
                return;
            }
            if (e.KeyCode == Keys.Up)
            {
                e.SuppressKeyPress = true;
                NavigateHistory(-1);
                return;
            }
            if (e.KeyCode == Keys.Down)
            {
                e.SuppressKeyPress = true;
                NavigateHistory(1);
                return;
            }
            if (e.Control && e.KeyCode == Keys.L)
            {
                e.SuppressKeyPress = true;
                _out.Clear();
                return;
            }
        }

        private void NavigateHistory(int dir)
        {
            List<string> hist = App.Hist;
            if (hist.Count == 0) return;

            if (_histIdx < 0)
            {
                _histDraft = _input.Text;
                _histIdx = hist.Count;
            }

            int next = _histIdx + dir;
            if (next >= hist.Count) next = hist.Count;
            if (next < 0) next = 0;

            _histIdx = next;
            if (_histIdx == hist.Count) _input.Text = _histDraft;
            else _input.Text = hist[_histIdx];
            _input.Select(_input.TextLength, 0);
        }

        private void RunCurrent()
        {
            if (_busy)
            {
                AppendLine(new GuiLine("  ! 上一条命令还在执行，请先等它结束或点「停止」", C_WARN, 3));
                ScrollToEnd();
                return;
            }

            // 输入预处理必须与命令行版逐字一致（Program.MainLoop 的 679 行）：
            //     line = NormalizeLead(line.Trim());
            // 少这一步的后果不是"少个锦上添花的功能"：中文输入法下 : 会打成全角 ：
            // （U+FF1A），命令行认 :h / :q，GUI 会当成未知命令 —— 同一串输入两种结果，
            // 那就是"能力没保留"。所以这里照抄同一行。
            string cmd = App.NormalizeLead(_input.Text.Trim());
            if (cmd.Length == 0) return;

            _input.Clear();
            _histIdx = -1;
            _histDraft = "";
            // 用命令行版的同一个函数写历史：落盘的是同一个 .adb_tool_history 文件，
            // 于是"命令行敲过的命令，GUI 按 ↑ 能翻到；GUI 敲过的，命令行也能翻到"。
            App.Hist.Add(cmd);
            if (App.Hist.Count > 500) App.Hist.RemoveAt(0);
            App.AppendHistory(cmd);

            // 回显：GUI 里没有提示符行，手动打一条，便于回溯
            EchoCommand(cmd);

            StartWork(cmd, 0);   // 来源 = 指令输入页
        }

        private void EchoCommand(string cmd)
        {
            _out.SelectionStart = _out.TextLength;
            _out.SelectionColor = C_HINT;
            string p = App.PromptBody(App.PROMPT_MODE,
                string.IsNullOrEmpty(App.DEVID) ? "(无设备)" : App.DEVID,
                App.CUR, App.ROOT);
            _out.AppendText(p + " > ");
            _out.SelectionColor = C_TEXT;
            _out.AppendText(cmd + Environment.NewLine);
            _out.SelectionStart = _out.TextLength;
            _out.SelectionColor = C_TEXT;
            ScrollToEnd();
        }

        private void StartWork(string cmd, int source)
        {
            _cmdSource = source;   // 记录来源页签，供 EndWork 分流
            _busy = true;
            _btnRun.Enabled = false;
            _btnStop.Enabled = true;
            _lbStatus.Text = "执行中 …";
            _lbStatus.ForeColor = C_SUB;

            Stopwatch sw = Stopwatch.StartNew();
            _worker = new Thread(new ThreadStart(delegate()
            {
                bool ok = true;
                try
                {
                    App.Dispatch(cmd);
                    ok = App.CMD_OK;
                }
                catch (Exception ex)
                {
                    ok = false;
                    try
                    {
                        Console.WriteLine("  \u00D7 内部错误：" + ex.Message);
                    }
                    catch { }
                }
                sw.Stop();
                long ms = sw.ElapsedMilliseconds;

                try
                {
                    BeginInvoke((MethodInvoker)delegate { EndWork(cmd, ok, ms); });
                }
                catch { }
            }));
            _worker.IsBackground = true;
            _worker.SetApartmentState(ApartmentState.STA);
            _worker.Start();
        }

        private void EndWork(string cmd, bool ok, long ms)
        {
            _busy = false;
            _btnRun.Enabled = true;
            _btnStop.Enabled = false;
            _lastMs = ms;

            // 输出可能还没刷完，强制推一次
            PumpOutput();

            UpdateStatus(ok, ms);
            UpdatePrompt();

            // 反馈窗口归"快捷指令"页独有：只有从快捷指令页触发的命令才写进来。
            // 指令输入页（source=0）的结果看上方大输出区，不进这里的列表 ——
            // 否则两页的执行结果混在一起，违背"互不串扰"的要求。
            if (_cmdSource == 1) AddFeed(cmd, ok, ms);

            _input.Focus();
        }

        private void StopCurrent()
        {
            try
            {
                if (App.RUNNING != null && !App.RUNNING.HasExited)
                {
                    App.RUNNING.Kill();
                    AppendLine(new GuiLine("  ! 已中止当前 adb 进程", C_WARN, 3));
                    ScrollToEnd();
                }
                else
                {
                    AppendLine(new GuiLine("  ! 当前没有可中止的进程", C_HINT, 4));
                    ScrollToEnd();
                }
            }
            catch (Exception ex)
            {
                AppendLine(new GuiLine("  \u00D7 中止失败：" + ex.Message, C_ERR, 2));
                ScrollToEnd();
            }
        }

        private void CopySelection()
        {
            try
            {
                string s = _out.SelectedText;
                if (string.IsNullOrEmpty(s)) s = _out.Text;
                if (s.Length > 0) Clipboard.SetText(s);
                _lbStatus.Text = string.IsNullOrEmpty(_out.SelectedText) ? "已复制全部输出" : "已复制选中内容";
            }
            catch { }
        }

        // ==================== 六、状态刷新 ====================

        private void UpdatePrompt()
        {
            string dev = string.IsNullOrEmpty(App.DEVID) ? "(无设备)" : App.DEVID;
            string dir = App.PromptDirFor(App.CUR, App.ROOT);
            if (App.OFFLINE) dev = "离线 " + dev;

            _lbPromptDev.Text = dev;
            _lbPromptDir.Text = string.IsNullOrEmpty(dir) ? "" : ":" + dir;
            _lbPromptDir.Visible = dir.Length > 0;
            DoLayout();
        }

        private void UpdateStatus(bool ok, long ms)
        {
            _dot.BackColor = App.OFFLINE ? C_WARN : (App.DEVN > 0 ? C_OK : C_HINT);

            string devText;
            if (App.DEVN > 0)
                devText = App.DEVID + " · 在线 1 台";
            else if (App.OFFLINE)
                devText = "无设备 · 离线模式";
            else
                devText = App.DEVID + " · " + App.DEVN + " 台在线";

            if (!string.IsNullOrEmpty(App.DEV_SOC))
                devText += " · " + App.DEV_SOC;

            _lbDev.Text = devText;

            _lbStatus.Text = (ok ? "完成" : "失败") + " · " + ms + " ms";
            _lbStatus.ForeColor = ok ? C_SUB : C_ERR;
            _lbStatusRight.Text = "目录 " + App.CUR;
            DoLayout();
        }

        private void AddFeed(string cmd, bool ok, long ms)
        {
            if (_feed.Items.Count > 200) _feed.Items.RemoveAt(0);

            // 首次记录时清掉"还没有记录"的空状态提示，
            // 否则它会一直躺在列表第一行冒充一条真实记录。
            if (_feedEmptyRow != null)
            {
                _feed.Items.Remove(_feedEmptyRow);
                _feedEmptyRow = null;
            }

            ListViewItem it = new ListViewItem(DateTime.Now.ToString("HH:mm:ss"));
            it.SubItems.Add(cmd.Length > 120 ? cmd.Substring(0, 117) + "..." : cmd);
            it.SubItems.Add(ok ? "成功" : "失败");
            it.SubItems.Add(ms + " ms");
            it.ForeColor = ok ? C_TEXT : C_ERR;
            it.Tag = cmd;
            _feed.Items.Add(it);
            it.EnsureVisible();
        }

        // 反馈窗口的空状态：一条灰色占位行，说明这个窗口是干什么用的。
        // 没有它的话，刚打开快捷指令页看到的是一片纯白，用户不知道这里会有内容。
        private void SeedFeedPlaceholder()
        {
            if (_feed.Items.Count > 0) return;

            ListViewItem it = new ListViewItem("");
            it.SubItems.Add("（暂无记录）");
            it.SubItems.Add("在「指令输入」页执行指令后，这里会列出每次的执行结果");
            it.SubItems.Add("");
            it.ForeColor = C_HINT;
            it.Tag = null;              // 双击不复制
            _feed.Items.Add(it);
            _feedEmptyRow = it;
        }

        private void CopyFeed()
        {
            try
            {
                if (_feed.SelectedItems.Count == 0) return;
                string cmd = _feed.SelectedItems[0].Tag as string;
                if (!string.IsNullOrEmpty(cmd)) Clipboard.SetText(cmd);
                _lbStatus.Text = "已复制该条指令";
            }
            catch { }
        }

        // ==================== 七、启动 ====================

        private void BootDevice()
        {
            // 设备初始化会阻塞（adb devices 可能几秒），放后台
            Thread th = new Thread(new ThreadStart(delegate()
            {
                GuiEntry.Trace("BootDevice 线程开始");
                bool ok = false;
                try
                {
                    ok = App.InitEnv();
                    GuiEntry.Trace("InitEnv 返回 " + ok);

                    // 【必须补】与 Program.Main 对齐：InitEnv 失败要显式置 OFFLINE。
                    //
                    // Main 里是 if (!InitEnv()) { OFFLINE = true; OfflineBanner(); }。
                    // GuiMain 早期只看了返回值、没改 OFFLINE，于是 Dispatch 开头那个
                    // "离线闸门"整段被跳过 —— 无设备时敲 ls 不再是
                    //     ! 设备未连接。输入 :r 重连、:h 看帮助
                    // 而是直接把 adb 的原始报错（no devices/emulators found）抛给用户。
                    // 表现上就是"界面版比命令行版少了离线保护"，属于能力差异。
                    if (!ok) App.OFFLINE = true;
                }
                catch (Exception ex)
                {
                    GuiEntry.Dump("InitEnv", ex);
                    ok = false;
                }

                try
                {
                    BeginInvoke((MethodInvoker)delegate
                    {
                        GuiEntry.Trace("BootDevice 回到 UI");
                        PumpOutput();
                        UpdateStatus(ok, 0);
                        UpdatePrompt();
                        _lbStatus.Text = ok ? "设备已就绪" : "未连接设备 · 可输入 :r 重连";
                        _lbStatus.ForeColor = ok ? C_SUB : C_WARN;
                        _input.Focus();
                    });
                }
                catch (Exception ex)
                {
                    GuiEntry.Dump("BootDevice.BeginInvoke", ex);
                }
            }));
            th.IsBackground = true;
            th.Start();
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            try { _tick.Stop(); } catch { }

            // 恢复标准输出，避免退出时后台线程写已释放的 sink
            try
            {
                StreamWriter so = new StreamWriter(Console.OpenStandardOutput(), Encoding.UTF8);
                so.AutoFlush = true;
                Console.SetOut(so);
                App.GUI_COLOR_HOOK = null;
            }
            catch { }

            // 2026-11-17 O7：与 GuiWeb 同步，不再用 Thread.Abort（见 GuiWeb.OnFormClosing 的说明）。
            // 这个窗体自 A12 起已不是运行时界面（真正在跑的是 GuiWeb + WebView2），
            // 但保留同样的收尾方式，避免以后有人复用这个类又把 Abort 带回来。
            try
            {
                if (_worker != null && _worker.IsAlive)
                {
                    try { App.GUISTOP = true; App.KillRunning(0); } catch { }
                    try { _worker.Join(1200); } catch { }
                }
            }
            catch { }

            base.OnFormClosing(e);
        }

        // ==================== 八、自检支持（GuiSelfCheck 专用）====================
        //
        // 只暴露"读几何/切换状态"的能力，不给外部改控件的手段 —— 自检要能
        // 断言真实布局，所以这些访问器读的都是活控件，不是快照。

        internal void RunSelfCheckBody(StringBuilder sb)
        {
            GuiSelfCheck.Body(this, sb);
        }

        internal Panel GetTopBar() { return _top; }
        internal Panel GetTabBar() { return _tabBar; }
        internal Panel GetBottomBar() { return _bottom; }
        internal Panel GetPageCmd() { return _pageCmd; }
        internal Panel GetPageQuick() { return _pageQuick; }
        internal RichTextBox GetOutputBox() { return _out; }
        internal Panel GetInputBar() { return _inputBar; }
        internal TextBox GetInputBox() { return _input; }
        internal Panel GetFeedPanel() { return _quickFeed; }
        internal Panel GetQuickTop() { return _quickTop; }
        internal ListView GetFeedList() { return _feed; }

        // 历史句柄：自检要验证"GUI 用的是命令行那一份，不是自建的"
        internal List<string> GetHistory() { return App.Hist; }

        // 反馈隔离的自检入口：走与 EndWork 相同的分流逻辑，但不碰设备。
        // source=0（指令输入页）不应写反馈窗口；source=1（快捷指令页）才写。
        // 把这段独立出来，是为了让"两页结果互不串扰"这个需求能被无头断言锁定。
        internal void RecordCmdResultForTest(string cmd, bool ok, int source)
        {
            if (source == 1) AddFeed(cmd, ok, 0);
        }

        // 反馈列表里"真实记录"的行数（不含占位行）。给自检断言隔离效果用。
        internal int FeedRealCount()
        {
            int n = 0;
            for (int i = 0; i < _feed.Items.Count; i++)
                if (_feed.Items[i].Tag != null) n++;
            return n;
        }

        internal Button[] GetInputButtons()
        {
            return new Button[] { _btnRun, _btnStop, _btnClear, _btnCopy };
        }

        internal void SwitchTabForCheck(int idx)
        {
            SwitchTab(idx);
        }
    }

    // ==================== Tab 按钮（自绘，做出"下边框高亮"的页签感）====================

    internal sealed class TabBtn : Control
    {
        private bool _active = false;

        internal TabBtn(string text)
        {
            SetStyle(ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint
                | ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, true);
            Text = text;
            Font = new Font("Microsoft YaHei UI", 10f);
            Size = new Size(92, 28);
            Cursor = Cursors.Hand;
        }

        internal bool Active
        {
            get { return _active; }
            set { _active = value; Invalidate(); }
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            g.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;

            Color bg = _active ? Color.White : Color.FromArgb(240, 240, 240);
            using (SolidBrush b = new SolidBrush(bg)) g.FillRectangle(b, 0, 0, Width, Height);

            Color fg = _active ? Color.FromArgb(32, 32, 32) : Color.FromArgb(120, 120, 120);
            using (SolidBrush b = new SolidBrush(fg))
            {
                StringFormat sf = new StringFormat();
                sf.Alignment = StringAlignment.Center;
                sf.LineAlignment = StringAlignment.Center;
                g.DrawString(Text, Font, b, new Rectangle(0, 0, Width, Height), sf);
            }

            if (_active)
            {
                using (Pen p = new Pen(Color.FromArgb(32, 32, 32), 2f))
                    g.DrawLine(p, 0, Height - 1, Width, Height - 1);
            }
        }

        protected override void OnMouseEnter(EventArgs e)
        {
            if (!_active) { BackColor = Color.FromArgb(232, 232, 232); Invalidate(); }
            base.OnMouseEnter(e);
        }

        protected override void OnMouseLeave(EventArgs e)
        {
            Invalidate();
            base.OnMouseLeave(e);
        }
    }
}
