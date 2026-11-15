"""ui.html 真实渲染验证：启动 GUI → 等加载 → 截窗口 → 关闭。

为什么要这样做：
  ui.html 是 WebView2 里跑的，静态检查（_check_ui.js）只能保证语法和引用，
  证明不了"打开是不是白屏""按钮颜色对不对""分栏比例是不是真的生效"。
  这里真的把它跑起来截图，用眼睛确认。

只在验证时用，不进发布物。
"""
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time

from PIL import ImageGrab

_HERE = os.path.dirname(os.path.abspath(__file__))   # 377/
_ROOT = os.path.dirname(_HERE)                       # 项目根
EXE = os.path.join(_ROOT, "adb_log_gui", "adb_Tool.exe")
OUT = os.path.join(_HERE, "_shot_gui.png")

u = ctypes.windll.user32

# 1) 起进程
p = subprocess.Popen([EXE], cwd=os.path.dirname(EXE))
print("pid", p.pid)

# 2) 等主窗口出现。
#    注意：不能靠"窗口标题 == adb_Tool"来全局搜 —— 这台机器上同时可能开着
#    别的同名窗口，也可能搜到 WebView2 的内部窗口。按**进程 PID**过滤最稳。
h = 0
for _ in range(120):
    time.sleep(0.4)
    if p.poll() is not None:
        print("进程已退出 rc=", p.returncode)
        sys.exit(1)
    hits = []

    def cb(hw, lp):
        if not u.IsWindowVisible(hw):
            return True
        n = u.GetWindowTextLengthW(hw)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(hw, buf, n + 1)
            pid = wt.DWORD()
            u.GetWindowThreadProcessId(hw, ctypes.byref(pid))
            if pid.value == p.pid:
                hits.append((hw, buf.value))
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    u.EnumWindows(WNDENUMPROC(cb), 0)
    if hits:
        h = hits[0][0]
        print("win", hits[0][1])
        break

if not h:
    print("没找到窗口")
    p.terminate()
    sys.exit(1)
print("hwnd", h)

# 3) 提到前台。
#    SetForegroundWindow 在很多情况下会"静默失败"（Windows 的前台锁定策略：
#    只有当前持有前台权的进程才能切换前台）。实测直接调用无效，截出来的是
#    别的窗口。可靠做法是 SetWindowPos 置顶（HWND_TOPMOST），
#    截完再取消置顶，这样不需要抢前台权。
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_SHOWWINDOW = 0x0040

u.ShowWindow(h, 9)   # SW_RESTORE（最小化过的要先还原）
time.sleep(0.4)
u.SetWindowPos(h, HWND_TOPMOST, 0, 0, 0, 0,
               SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
u.SetForegroundWindow(h)
u.BringWindowToTop(h)
time.sleep(0.6)

# 4) 只截窗口区域
r = wt.RECT()
u.GetWindowRect(h, ctypes.byref(r))
box = (r.left, r.top, r.right, r.bottom)
print("rect", box)
im = ImageGrab.grab(bbox=box, all_screens=True)
im.save(OUT)
print("saved", OUT, im.size)

# 取消置顶，别把用户桌面搞乱
u.SetWindowPos(h, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)

# 5) 关掉（验证完不留后台进程）
p.terminate()
try:
    p.wait(timeout=5)
except Exception:
    p.kill()
print("closed")
