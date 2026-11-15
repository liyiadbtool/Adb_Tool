"""用 PrintWindow 抓 adb_Tool 窗口（不依赖前台/不被遮挡）。

Screen grab 会抓到"压在上面"的别的窗口，即便 SetWindowPos(HWND_TOPMOST)
在这台机器上也不生效（前台锁定策略）。PrintWindow 是让目标窗口自己往
HDC 上画一遍，跟遮挡无关，是抓后台窗口最可靠的方式。
PW_RENDERFULLCONTENT (0x2) 是 Win8.1+ 的 flag，DirectComposition 内容
（WebView2 就属于这种）只有带上它才不是黑块。
"""
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time

from PIL import Image

_HERE = os.path.dirname(os.path.abspath(__file__))   # 377/
_ROOT = os.path.dirname(_HERE)                       # 项目根
EXE = os.path.join(_ROOT, "adb_log_gui", "adb_Tool.exe")
OUT = os.path.join(_HERE, "_shot_gui.png")

u = ctypes.windll.user32
gdi = ctypes.windll.gdi32

PW_RENDERFULLCONTENT = 0x00000002

p = subprocess.Popen([EXE], cwd=os.path.dirname(EXE))
print("pid", p.pid)

h = 0
for _ in range(150):
    time.sleep(0.4)
    if p.poll() is not None:
        print("进程退出 rc=", p.returncode)
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
                hits.append(hw)
        return True

    u.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)(cb), 0)
    if hits:
        h = hits[0]
        break

if not h:
    print("没找到窗口")
    p.terminate()
    sys.exit(1)

# 给页面充分时间：WebView2 初始化 + 导航 + ready→status 推送 + splash 淡出
time.sleep(6.0)

r = wt.RECT()
u.GetWindowRect(h, ctypes.byref(r))
w = r.right - r.left
ht = r.bottom - r.top
print("rect", r.left, r.top, w, ht)

hdc_win = u.GetWindowDC(h)
hdc_mem = gdi.CreateCompatibleDC(hdc_win)
hbmp = gdi.CreateCompatibleBitmap(hdc_win, w, ht)
gdi.SelectObject(hdc_mem, hbmp)

ok = u.PrintWindow(h, hdc_mem, PW_RENDERFULLCONTENT)
print("PrintWindow", ok)

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
        ("biPlanes", wt.WORD), ("biBitCount", wt.WORD),
        ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
        ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG),
        ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD),
    ]

bi = BITMAPINFOHEADER()
bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
bi.biWidth = w
bi.biHeight = -ht          # 负数 = 自上而下，省一次翻转
bi.biPlanes = 1
bi.biBitCount = 32
bi.biCompression = 0

buf = ctypes.create_string_buffer(w * ht * 4)
gdi.GetDIBits(hdc_mem, hbmp, 0, ht, buf, ctypes.byref(bi), 0)
im = Image.frombuffer("RGBA", (w, ht), buf, "raw", "BGRA", 0, 1).convert("RGB")
im.save(OUT)
print("saved", OUT, im.size)

# 统计非黑像素比例：Black 说明 PrintWindow 没截到内容（WebView2 常见坑）
px = im.load()
nonblack = 0
step = 7
total = 0
for y in range(0, ht, step):
    for x in range(0, w, step):
        total += 1
        c = px[x, y]
        if c[0] + c[1] + c[2] > 40:
            nonblack += 1
print("非黑像素占比 %.1f%%" % (nonblack * 100.0 / max(total, 1)))

gdi.DeleteObject(hbmp)
gdi.DeleteDC(hdc_mem)
u.ReleaseDC(h, hdc_win)

p.terminate()
try:
    p.wait(timeout=5)
except Exception:
    p.kill()
print("closed")
