# -*- coding: utf-8 -*-
"""窗口行为冒烟测试（2026-11-15）：验证自绘标题栏改造后原生窗口能力没丢。

检查：
  1. 真的无边框（GWL_STYLE 里没有 WS_CAPTION）
  2. 初始尺寸 = ClientSize 1100x760（说明边框已去掉、内容没被裁）
  3. SetWindowPos 缩放生效（说明系统缩放路径还在）
  4. 最大化后不超过工作区（不盖任务栏）
  5. 还原后尺寸回到缩放值
  6. 全程进程存活、gui_error.log 无新增
"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes as wt

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()

user32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wt.UINT]
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.IsIconic.argtypes = [wt.HWND]
user32.IsIconic.restype = wt.BOOL
user32.IsWindowVisible.argtypes = [wt.HWND]
user32.SystemParametersInfoW.argtypes = [wt.UINT, wt.UINT, ctypes.c_void_p, wt.UINT]
user32.GetWindowTextLengthW.argtypes = [wt.HWND]
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]

GWL_STYLE = -16
WS_CAPTION = 0x00C00000
SW_MAXIMIZE, SW_MINIMIZE, SW_RESTORE = 3, 6, 9
SPI_GETWORKAREA = 0x0030

EXE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "adb_log_gui", "dist", "adb_Tool.exe")
# 2026-11-19：新包日志落在 exe 同级 log\，老包在 LocalAppData；
# 两边都认，否则会去比对**上一次**的旧日志而假绿。
_BESIDE = os.path.join(os.path.dirname(os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "adb_log_gui", "dist", "adb_Tool.exe"))), "log")
LOG = os.path.join(_BESIDE if os.path.isdir(_BESIDE) else
                   os.path.join(os.environ.get("LOCALAPPDATA", ""), "adb_Tool", "logs"),
                   "gui_error.log")


def find_window(pid=None):
    """按 PID 认领窗口；pid=None 时退化成"按标题找"（只给 kill_stale 用）。

    为什么必须认 PID：机器上可能同时存在别的 adb_Tool.exe 窗口（上一轮没退的、
    GUI 自检残留的、甚至用户自己开着的），它们的标题一模一样。以前取 found[0]，
    等于赌"我刚启动的那个排在最前面"——release 流程里连着起进程时就会赌输，
    抓到的是残留窗口：它带着标准标题栏（style=0x14cf0000 正是 WS_OVERLAPPEDWINDOW）、
    尺寸还停在上一轮被改过的 940x640，于是尺寸/边框断言集体红。
    窗口属于哪个进程是 GetWindowThreadProcessId 说了算，认它就不会错。"""
    user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, lp):
        h = int(hwnd)
        if not user32.IsWindowVisible(h):
            return True
        if pid is not None:
            wpid = wt.DWORD()
            user32.GetWindowThreadProcessId(h, ctypes.byref(wpid))
            if wpid.value != pid:
                return True
        n = user32.GetWindowTextLengthW(h)
        if n > 0:
            b = ctypes.create_unicode_buffer(n + 2)
            user32.GetWindowTextW(h, b, n + 2)
            # A17：窗口标题去掉了「网联服务_」前缀，只剩 Adb_Tool。
            # 这里按子串认，别再写死完整标题 —— 否则一次改名就让整套冒烟测试
            # 找不到窗口（表现是 rc=1 且一个字都不打印）。
            if u"Adb_Tool" in b.value:
                found.append(h)
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def rect(h):
    r = wt.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def workarea():
    r = wt.RECT()
    user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(r), 0)
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def kill_stale(timeout=12.0):
    """清掉"本目录 dist 里的那个 exe"的残留进程，别的一概不碰。

    为什么只按完整路径清：机器上常有别的 adb_Tool.exe 在跑 —— 用户开着的
    交付版（窗口标题是「网联服务_Adb_Tool_完整版_日期」）、GUI 自检的进程等，
    它们的标题前缀和我们一模一样。按镜像名 taskkill 会把人家的窗口一起关掉，
    那是真影响用户；按 PID 认领窗口（见 find_window）之后，残留窗口本来就
    影响不到断言，这里只负责"同一个可执行文件别叠两个实例"。"""
    ps = ("Get-Process adb_Tool -ErrorAction SilentlyContinue | "
          "Where-Object { $_.Path -eq '%s' } | Stop-Process -Force -ErrorAction SilentlyContinue"
          % EXE.replace("'", "''"))
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                   capture_output=True, timeout=60)
    # 等的是"这个路径的进程没了"，不是"窗口没了"——后者永远等不到（别人的窗口还在）。
    chk = ("@(Get-Process adb_Tool -ErrorAction SilentlyContinue | "
           "Where-Object { $_.Path -eq '%s' }).Count" % EXE.replace("'", "''"))
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", chk],
                           capture_output=True, text=True, timeout=60)
        if (r.stdout or "").strip() in ("0", ""):
            return True
        time.sleep(0.4)
    return False


def main():
    before = os.path.getsize(LOG) if os.path.exists(LOG) else 0
    kill_stale()
    p = subprocess.Popen([EXE], close_fds=True)
    rows = []

    def ok(name, cond, detail=""):
        rows.append((name, bool(cond), detail))

    try:
        h = None
        for _ in range(40):
            time.sleep(0.5)
            h = find_window(p.pid)
            if h:
                break
        ok("窗口出现（本进程 %d）" % p.pid, h is not None)
        if not h:
            raise SystemExit(1)
        time.sleep(2.5)

        st = user32.GetWindowLongW(h, GWL_STYLE)
        ok("无系统标题栏（WS_CAPTION 已去掉）", (st & WS_CAPTION) == 0, "style=0x%08x" % st)
        # 故意不加 WS_THICKFRAME：那会在无边框窗口外面长出一圈系统边框
        # （浅色主题下就是一圈深色描边）。缩放改由页面热区驱动，这里验最小化/还原。
        ok("没有残留的系统缩放边框（WS_THICKFRAME 不在）", (st & 0x00040000) == 0,
           "style=0x%08x" % st)
        # A15：点任务栏要能收起窗口。系统只在带 WS_MINIMIZEBOX 时才把任务栏点击
        # 翻译成 WM_SYSCOMMAND/SC_MINIMIZE；原来 style=0x16010000 缺这一位，
        # 于是"点任务栏没反应"。这一位必须有，且不能顺手把 WS_THICKFRAME 带回来。
        ok("带 WS_MINIMIZEBOX（点任务栏可收起）", (st & 0x00020000) != 0,
           "style=0x%08x" % st)

        x, y, w, hh = rect(h)
        ok("初始内容区 1100x760", (w, hh) == (1100, 760), "%dx%d" % (w, hh))

        user32.SetWindowPos(h, 0, 200, 160, 940, 640, 0x0004)   # SWP_NOZORDER
        time.sleep(1.2)
        x, y, w, hh = rect(h)
        ok("程序化缩放生效", (w, hh) == (940, 640), "%dx%d" % (w, hh))

        wa = workarea()
        user32.ShowWindow(h, SW_MAXIMIZE)
        time.sleep(1.5)
        x, y, w, hh = rect(h)
        ok("最大化后宽度不超工作区", w <= wa[2], "%d <= %d" % (w, wa[2]))
        ok("最大化后高度不超工作区（不盖任务栏）", hh <= wa[3], "%d <= %d" % (hh, wa[3]))

        user32.ShowWindow(h, SW_RESTORE)
        time.sleep(1.2)
        x, y, w, hh = rect(h)
        ok("还原后回到缩放尺寸", (w, hh) == (940, 640), "%dx%d" % (w, hh))

        user32.ShowWindow(h, SW_MINIMIZE)
        time.sleep(1.0)
        ok("最小化生效", bool(user32.IsIconic(h)))
        user32.ShowWindow(h, SW_RESTORE)
        time.sleep(1.0)
        ok("从最小化还原", not user32.IsIconic(h))
        ok("进程存活", p.poll() is None, str(p.poll()))
    finally:
        try:
            p.terminate()
        except Exception:
            pass
        # 等窗口真的消失再往下走：后面 verify_all 还会接着跑别的套件，
        # 留一个半死的窗口在那儿，下一轮又会被 EnumWindows 先抓走。
        for _ in range(25):
            time.sleep(0.2)
            if not find_window(p.pid):
                break

    after = os.path.getsize(LOG) if os.path.exists(LOG) else 0
    ok("无新增错误日志", after == before, "%d -> %d" % (before, after))

    fails = [r for r in rows if not r[1]]
    for n, c, d in rows:
        print("  %s | %s%s" % ("PASS" if c else "FAIL", n, (" | " + d) if d else ""))
    print("\n  窗口冒烟：通过 %d / %d" % (len(rows) - len(fails), len(rows)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
