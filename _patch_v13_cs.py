# -*- coding: utf-8 -*-
"""A13 轮 C# 补丁（幂等）。

改三处：
  1) Adb.cs  LoadDeviceInfo：日志等级独立读取（修「一直未设置」的根因）
  2) GuiWeb.cs  WM_GETMINMAXINFO：最大化按当前屏工作区实时算（修 27 寸屏不铺满）
  3) GuiWeb.cs  圆角双轨：Win11 走 DWM CornerPreference，Win10 走 SetWindowRgn
     配套：窗体底色跟主题、最大化时取消圆角、DPI 变化重设
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
CS = os.path.join(ROOT, "_cs")


def rd(p):
    return io.open(p, "r", encoding="utf-8").read()


def wr(p, s):
    io.open(p, "w", encoding="utf-8", newline="").write(s)


def sub(src, old, new, what):
    if old not in src:
        raise SystemExit("[FAIL] 锚点未命中：" + what)
    return src.replace(old, new, 1)


# ============ 1) Adb.cs：日志等级独立读取 ============
p = os.path.join(CS, "Adb.cs")
s = rd(p)

OLD_HEAD = u"""            DEV_SOC = "";
            DEV_PLAT = "";
            DEV_RES = "";
            DEV_LOGLEVEL = "";

            if (!LoadCarInfo()) return;
"""
NEW_HEAD = u"""            DEV_SOC = "";
            DEV_PLAT = "";
            DEV_RES = "";
            DEV_LOGLEVEL = "";

            // ---- A13 修复：日志等级必须独立读取，不能挂在 LoadCarInfo 之后 ----
            // 原实现是 `if (!LoadCarInfo()) return;` 再读 persist.log.tag。但车机
            // 属性全空的设备（手机、或属性未配）会让 LoadCarInfo() 返回 false 直接
            // 早退，下面那次 getprop 永远执行不到 —— 表现就是界面恒显示「日志 未设置」。
            // 日志等级和车机信息没有任何依赖关系，不该被它连坐。
            {
                string lo = "";
                string le = "";
                try { ShellCall(CUR, "getprop persist.log.tag", out lo, out le); }
                catch { }
                string lv = FirstLine((lo + le).Trim());
                if (lv.Length > 0) DEV_LOGLEVEL = lv;
            }

            if (!LoadCarInfo()) return;
"""
if u"A13 修复：日志等级必须独立读取" not in s:
    s = sub(s, OLD_HEAD, NEW_HEAD, "Adb.LoadDeviceInfo 头部")
else:
    sys.stdout.write("  [skip] Adb.cs 已含 A13 修复\n")

# 去掉原来藏在 LoadCarInfo 之后的那一段（已上移，留着会重复执行一次 adb）
OLD_TAIL = u"""            // 需求7：日志等级（persist.log.tag，值 V/D/I/W/E）。
            // 单独一次 getprop，值非空才记入，否则留空不显示。
            {
                string o = "";
                string e = "";
                ShellCall(CUR, "getprop persist.log.tag", out o, out e);
                string lv = FirstLine((o + e).Trim());
                if (lv.Length > 0) DEV_LOGLEVEL = lv;
            }
"""
if OLD_TAIL in s:
    s = s.replace(OLD_TAIL, u"""            // 日志等级已在方法开头独立读过（见 A13 修复），这里不再重复执行 adb。
""", 1)
wr(p, s)
sys.stdout.write("  [OK] Adb.cs 日志等级独立读取\n")


# ============ 2+3) GuiWeb.cs ============
p = os.path.join(CS, "GuiWeb.cs")
s = rd(p)

# --- 2a) OnLoad 里追加圆角 / 底色初始化 ---
OLD = u"""        protected override void OnLoad(EventArgs e)
        {
            base.OnLoad(e);
            UpdateMaximizedBounds();
        }"""
NEW = u"""        protected override void OnLoad(EventArgs e)
        {
            base.OnLoad(e);
            UpdateMaximizedBounds();

            // ---- A13：圆角 + 窗体底色 ----
            // 圆角要在句柄就绪后才能设；底色必须在圆角之前定好，
            // 否则裁掉四角的一瞬间会露出构造时那个深色底。
            ApplyChromeColor();
            TryDwmCorner();
            ApplyWindowCorner();
        }"""
if u"TryDwmCorner();" not in s:
    s = sub(s, OLD, NEW, "OnLoad")
else:
    sys.stdout.write("  [skip] OnLoad 已含圆角初始化\n")

# --- 2b) OnResize 里重设圆角（窗口尺寸变了，region 必须跟着重画）---
OLD = u"""        protected override void OnResize(EventArgs e)
        {
            base.OnResize(e);
            PushWinState();
        }"""
NEW = u"""        protected override void OnResize(EventArgs e)
        {
            base.OnResize(e);
            PushWinState();

            // region 是按像素矩形生成的，窗口一变就必须重设，否则四角会残留旧曲线。
            // 最大化时这里会走「取消圆角」分支，正好避免全屏出现圆角。
            ApplyWindowCorner();
        }"""
if u"ApplyWindowCorner();\n        }" not in s or u"protected override void OnResize" not in s:
    pass
if u"// region 是按像素矩形生成的" not in s:
    s = sub(s, OLD, NEW, "OnResize")
else:
    sys.stdout.write("  [skip] OnResize 已含圆角重设\n")

# --- 2c) 插入圆角 / 最大化 / 底色 的实现块 ---
ANCHOR = u"""        protected override void OnLoad(EventArgs e)"""
BLOCK = u"""        // ================= A13：圆角窗口 + 跨屏最大化 =================
        //
        // 为什么圆角要分两条路：
        //   Win11 有 DWMWA_WINDOW_CORNER_PREFERENCE，交给 DWM 画，边缘是抗锯齿的；
        //   Win10 没有这个属性，只能 SetWindowRgn 按像素裁，边缘必然有 1px 台阶。
        //   这不是"没做好"，是系统能力差异 —— WebView2 不支持透明分层窗口，
        //   所以 Win10 上不存在第二条能出抗锯齿的路。
        [System.Runtime.InteropServices.DllImport("user32.dll")]
        private static extern int SetWindowRgn(IntPtr hWnd, IntPtr hRgn, bool bRedraw);

        [System.Runtime.InteropServices.DllImport("gdi32.dll")]
        private static extern IntPtr CreateRoundRectRgn(
            int x1, int y1, int x2, int y2, int w, int h);

        [System.Runtime.InteropServices.DllImport("dwmapi.dll")]
        private static extern int DwmGetWindowAttribute(
            IntPtr hwnd, int attr, out int val, int size);

        private const int DWMWA_WINDOW_CORNER_PREFERENCE = 33;
        private const int DWMWCP_ROUND = 2;      // 标准圆角（系统设置页同款）
        private const int DWMWCP_ROUNDSMALL = 3; // 小圆角

        private const int WM_GETMINMAXINFO = 0x0024;
        private const int WM_DPICHANGED = 0x02E0;

        private bool _dwmCorner = false;   // DWM 圆角是否接管（true 时不再设 region）
        private int _cornerDip = 8;        // 圆角半径（DIP，按 DPI 换算成像素）

        [System.Runtime.InteropServices.StructLayout(
            System.Runtime.InteropServices.LayoutKind.Sequential)]
        private struct POINTAPI { public int X; public int Y; }

        [System.Runtime.InteropServices.StructLayout(
            System.Runtime.InteropServices.LayoutKind.Sequential)]
        private struct MINMAXINFO
        {
            public POINTAPI ptReserved;
            public POINTAPI ptMaxSize;       // 最大化时的宽高
            public POINTAPI ptMaxPosition;   // 最大化时的左上角
            public POINTAPI ptMinTrackSize;
            public POINTAPI ptMaxTrackSize;
        }

        // 窗体底色跟主题 —— 圆角裁开四角后，露出来的就是这层颜色。
        // 不跟着主题的话，白天/护眼主题下四角会露出构造时写死的深色块。
        private void ApplyChromeColor()
        {
            try
            {
                if (App.THEME == "light") BackColor = Color.FromArgb(254, 254, 255);
                else if (App.THEME == "eye") BackColor = Color.FromArgb(255, 251, 240);
                else BackColor = Color.FromArgb(13, 17, 23);
            }
            catch { }
        }

        // Win11：交给 DWM 画抗锯齿圆角。返回非 0 说明系统不支持（Win10），
        // 之后统一走 region 兜底。
        private void TryDwmCorner()
        {
            try
            {
                int build = Environment.OSVersion.Version.Build;
                if (build < 22000) { _dwmCorner = false; return; }

                int v = DWMWCP_ROUND;
                int hr = DwmSetWindowAttribute(
                    Handle, DWMWA_WINDOW_CORNER_PREFERENCE, ref v, sizeof(int));
                _dwmCorner = (hr == 0);

                // 读回校验：属性没被采纳时（部分无边框窗口会被忽略）退回 region。
                if (_dwmCorner)
                {
                    int back = -1;
                    if (DwmGetWindowAttribute(
                            Handle, DWMWA_WINDOW_CORNER_PREFERENCE, out back, sizeof(int)) == 0)
                    {
                        if (back != DWMWCP_ROUND && back != DWMWCP_ROUNDSMALL) _dwmCorner = false;
                    }
                }
            }
            catch { _dwmCorner = false; }
        }

        // 按当前尺寸 / DPI / 窗口状态重设圆角。三种情况：
        //   · 最大化或全屏  -> 取消圆角（全屏圆角是错的，而且尺寸变化会闪）
        //   · DWM 已接管     -> 什么都不做，交给系统（Win11，抗锯齿）
        //   · 其余            -> SetWindowRgn 按像素裁（Win10，1px 台阶）
        private void ApplyWindowCorner()
        {
            try
            {
                if (!IsHandleCreated) return;

                if (WindowState != FormWindowState.Normal)
                {
                    SetWindowRgn(Handle, IntPtr.Zero, true);
                    return;
                }
                if (_dwmCorner) return;

                int dpi = 96;
                try { dpi = DeviceDpi; } catch { }
                int r = (int)Math.Round(_cornerDip * (dpi / 96.0));
                if (r < 2) r = 2;

                // 宽高 +1：CreateRoundRectRgn 的右/下边界是开区间，不加会在右边和下边
                // 各少 1px，表现为窗口右下角有一条 1px 的缝。
                IntPtr h = CreateRoundRectRgn(0, 0, Width + 1, Height + 1, r * 2, r * 2);

                // SetWindowRgn 会接管这个 region 的所有权，系统负责释放 ——
                // 这里绝对不能再 DeleteObject，否则重复释放直接崩。
                SetWindowRgn(Handle, h, true);
            }
            catch { }
        }

        // 最大化尺寸实时算：不用 MaximizedBounds。
        // MaximizedBounds 是"设一次就一直用"的缓存，窗口拖到另一块屏（不同分辨率/
        // 不同 DPI）后它还是老值 —— 这就是"接 27 寸屏后最大化没铺满"的根因。
        // WM_GETMINMAXINFO 每次最大化都会问一遍，在这里按当前屏工作区回答即可。
        protected override void WndProc(ref Message m)
        {
            try
            {
                if (m.Msg == WM_GETMINMAXINFO)
                {
                    Rectangle wa = Screen.FromHandle(Handle).WorkingArea;
                    MINMAXINFO mmi = (MINMAXINFO)m.GetLParam(typeof(MINMAXINFO));
                    mmi.ptMaxPosition.X = wa.Left;
                    mmi.ptMaxPosition.Y = wa.Top;
                    mmi.ptMaxSize.X = wa.Width;
                    mmi.ptMaxSize.Y = wa.Height;
                    // 最小/最大跟踪尺寸保持系统默认（这里填 0 会被系统当成"无限制"）
                    System.Runtime.InteropServices.Marshal.StructureToPtr(
                        mmi, m.LParam, false);
                    return;
                }
                if (m.Msg == WM_DPICHANGED)
                {
                    // 拖到另一块 DPI 不同的屏：圆角像素半径要按新 DPI 重算
                    base.WndProc(ref m);
                    ApplyWindowCorner();
                    return;
                }
            }
            catch { }
            base.WndProc(ref m);
        }

"""
if u"// ================= A13：圆角窗口 + 跨屏最大化 =================" not in s:
    s = sub(s, ANCHOR, BLOCK + ANCHOR, "GuiWeb 圆角块插入")
else:
    sys.stdout.write("  [skip] 圆角块已存在\n")

# --- 2d) 切主题时同步窗体底色 ---
OLD = u"""                    App.THEME = (th == "light" || th == "eye") ? th : "dark";
                    SetTitleBarDark(App.THEME == "dark");
                    SaveThemePreference(App.THEME);"""
NEW = u"""                    App.THEME = (th == "light" || th == "eye") ? th : "dark";
                    SetTitleBarDark(App.THEME == "dark");
                    ApplyChromeColor();   // A13：圆角四角露出的底色也要跟着换
                    SaveThemePreference(App.THEME);"""
if u"ApplyChromeColor();   // A13" not in s:
    s = sub(s, OLD, NEW, 'case "theme"')
else:
    sys.stdout.write("  [skip] theme 已同步底色\n")

wr(p, s)
sys.stdout.write("  [OK] GuiWeb.cs 最大化 / 圆角 / 底色\n")
sys.stdout.write("\nC# 补丁完成\n")
