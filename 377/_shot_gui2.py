"""验证 WebView2 数据目录迁移后界面能否正常渲染。

与 _shot_gui.py 的差别（这就是它的存在理由）：
  _shot_gui.py 在窗口出现的那一刻就截图。WebView2 首帧渲染要 1~3 秒，
  而窗口是 WPF/WinForms 先建出来的，所以截到的是 "正在连接设备…" 加载层。
  这在本次改动前就存在（历史已知问题），不是回归。

  这里改成：
    1) 等窗口出现；
    2) 再等 WebView2 的子窗口 "Chrome_WidgetWin_*" 真正出现（这是渲染器起来了的信号）；
    3) 然后按 2s / 4s / 6s 连续截三张，取最后一张。

只在验证时用，不进发布物。
"""
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time

from PIL import ImageGrab

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
EXE = os.path.join(_ROOT, "adb_log_gui", "adb_Tool.exe")
OUTDIR = os.path.join(_HERE, "_shots")
os.makedirs(OUTDIR, exist_ok=True)

u = ctypes.windll.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)


def windows_of_pid(pid):
    hits = []

    def cb(hw, lp):
        if not u.IsWindowVisible(hw):
            return True
        pid_buf = wt.DWORD()
        u.GetWindowThreadProcessId(hw, ctypes.byref(pid_buf))
        if pid_buf.value != pid:
            return True
        n = u.GetWindowTextLengthW(hw)
        buf = ctypes.create_unicode_buffer(n + 1) if n else ctypes.create_unicode_buffer(1)
        if n:
            u.GetWindowTextW(hw, buf, n + 1)
        cls = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(hw, cls, 256)
        hits.append((hw, buf.value, cls.value))
        return True

    u.EnumWindows(WNDENUMPROC(cb), 0)
    return hits


print("exe", EXE)
p = subprocess.Popen([EXE], cwd=os.path.dirname(EXE))
print("pid", p.pid)

# --- 1) 等主窗口 ---
h = 0
title = ""
for _ in range(150):
    time.sleep(0.3)
    if p.poll() is not None:
        print("进程已退出 rc=", p.returncode)
        sys.exit(1)
    for hw, t, c in windows_of_pid(p.pid):
        # 主窗口有标题，WebView2 内部窗口标题可能为空
        if t and hw:
            h, title = hw, t
            break
    if h:
        break

if not h:
    print("没找到主窗口")
    p.terminate()
    sys.exit(1)
print("win", repr(title), "hwnd", h)

# --- 2) 等 WebView2 渲染器子窗口 ---
t0 = time.time()
renderer = None
while time.time() - t0 < 15:
    for hw, t, c in windows_of_pid(p.pid):
        if c.startswith("Chrome_WidgetWin"):
            renderer = (hw, c)
            break
    if renderer:
        break
    time.sleep(0.25)

print("WebView2 渲染器窗口:", renderer if renderer else "未出现（15s 超时）")
print("从启动到渲染器就绪: %.1fs" % (time.time() - t0))

# --- 3) 置顶 + 连续截图 ---
HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
SWP_NOMOVE, SWP_NOSIZE, SWP_SHOWWINDOW = 0x0002, 0x0001, 0x0040

u.ShowWindow(h, 9)
time.sleep(0.3)
u.SetWindowPos(h, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
u.SetForegroundWindow(h)
u.BringWindowToTop(h)

# 置顶可能"静默失败"：别的程序也置顶、或前台锁定策略拦住。截之前先确认
# 目标窗口真的是前台，不是的话反复抢一次。抢不到就别截 —— 截出来是别人的
# 窗口，比没有截图更误导（本次就踩到了：截到飞书窗口）。
fg = None
t1 = time.time()
while time.time() - t1 < 8:
    fg = u.GetForegroundWindow()
    if fg == h:
        break
    u.SetWindowPos(h, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
    u.SetForegroundWindow(h)
    u.BringWindowToTop(h)
    time.sleep(0.4)

print("前台窗口 == 本窗口 :", fg == h, "(fg=%s, h=%s)" % (fg, h))
if fg != h:
    print("[WARN] 抢不到前台，截图可能截到别的窗口")

r = wt.RECT()
u.GetWindowRect(h, ctypes.byref(r))
box = (r.left, r.top, r.right, r.bottom)
print("rect", box, "size", r.right - r.left, "x", r.bottom - r.top)

saved = []
for delay, tag in [(1.0, "a"), (2.0, "b"), (2.0, "c")]:
    time.sleep(delay)
    out = os.path.join(OUTDIR, "gui_%s.png" % tag)
    im = ImageGrab.grab(bbox=box, all_screens=True)
    im.save(out)
    saved.append((out, im.size))
    print("  shot", tag, out, im.size)

u.SetWindowPos(h, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)

p.terminate()
try:
    p.wait(timeout=5)
except Exception:
    p.kill()
print("closed")
print("最后一张:", saved[-1][0])
