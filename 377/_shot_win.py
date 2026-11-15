"""抓取 GUI 窗口内容，用于验证 WebView2 数据目录迁移后界面渲染正常。

为什么不用原来那套 ImageGrab：
  ImageGrab 抓的是"屏幕这块矩形"，要求目标窗口真的在最前面。而
  SetForegroundWindow 在非交互会话里会被 Windows 的前台锁定策略拒绝
  （实测 GetForegroundWindow 一直返回别的窗口），于是截出来是遮挡在
  上面的飞书窗口 —— 比没截图更误导。

  改用 PrintWindow + PW_RENDERFULLCONTENT(2)：让目标窗口把自己画到内存
  DC 上，不需要它在前台，也不受遮挡影响。这个标志是 Win8.1 起支持的，
  对 WebView2 这类 DirectComposition 渲染的窗口是必须的
  （不带它只会画出一块黑）。

只在验证时用，不进发布物。
"""
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time

from PIL import Image

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
EXE = os.path.join(_ROOT, "adb_log_gui", "adb_Tool.exe")
SRC = sys.argv[1] if len(sys.argv) > 1 else "adb_log_gui"   # 可选：指定跑哪个目录的 exe
if SRC != "adb_log_gui":
    EXE = os.path.join(_ROOT, SRC, "adb_Tool.exe")

OUTDIR = os.path.join(_HERE, "_shots")
os.makedirs(OUTDIR, exist_ok=True)

u = ctypes.windll.user32
gdi = ctypes.windll.gdi32
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

PW_RENDERFULLCONTENT = 0x00000002


def windows_of_pid(pid):
    hits = []

    def cb(hw, lp):
        if not u.IsWindowVisible(hw):
            return True
        pb = wt.DWORD()
        u.GetWindowThreadProcessId(hw, ctypes.byref(pb))
        if pb.value != pid:
            return True
        n = u.GetWindowTextLengthW(hw)
        buf = ctypes.create_unicode_buffer(n + 1)
        if n:
            u.GetWindowTextW(hw, buf, n + 1)
        cls = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(hw, cls, 256)
        hits.append((hw, buf.value, cls.value))
        return True

    u.EnumWindows(WNDENUMPROC(cb), 0)
    return hits


def grab(hwnd, path):
    r = wt.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    w, hgt = r.right - r.left, r.bottom - r.top
    if w <= 0 or hgt <= 0:
        return None, (w, hgt)

    hdc = u.GetWindowDC(hwnd)
    mdc = gdi.CreateCompatibleDC(hdc)
    bmp = gdi.CreateCompatibleBitmap(hdc, w, hgt)
    gdi.SelectObject(mdc, bmp)

    ok = u.PrintWindow(hwnd, mdc, PW_RENDERFULLCONTENT)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG),
                    ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                    ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                    ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
                    ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                    ("biClrImportant", wt.DWORD)]

    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth, bi.biHeight = w, -hgt      # 负高度 = 自上而下
    bi.biPlanes, bi.biBitCount = 1, 32
    bi.biCompression = 0

    buf = ctypes.create_string_buffer(w * hgt * 4)
    gdi.GetDIBits(mdc, bmp, 0, hgt, buf, ctypes.byref(bi), 0)

    im = Image.frombuffer("RGBA", (w, hgt), buf, "raw", "BGRA", 0, 1).convert("RGB")
    im.save(path)

    gdi.DeleteObject(bmp)
    gdi.DeleteDC(mdc)
    u.ReleaseDC(hwnd, hdc)
    return im.size, (w, hgt)


print("exe", EXE)
p = subprocess.Popen([EXE], cwd=os.path.dirname(EXE))
print("pid", p.pid)

h, title = 0, ""
for _ in range(150):
    time.sleep(0.3)
    if p.poll() is not None:
        print("进程已退出 rc=", p.returncode)
        sys.exit(1)
    for hw, t, c in windows_of_pid(p.pid):
        if t:
            h, title = hw, t
            break
    if h:
        break

if not h:
    print("没找到主窗口")
    p.terminate()
    sys.exit(1)
print("win", repr(title), "hwnd", h)

# 等 WebView2 首帧。渲染器窗口名里带 Chrome_WidgetWin，但它在某些版本里
# 是 IsWindowVisible=False 的（被宿主窗口覆盖），所以这里只做提示、不做门禁。
t0 = time.time()
seen = None
while time.time() - t0 < 12:
    for hw, t, c in windows_of_pid(p.pid):
        if c.startswith("Chrome_WidgetWin") or "Chrome" in c:
            seen = c
            break
    if seen:
        break
    time.sleep(0.25)
print("WebView2 子窗口: %s（耗时 %.1fs）" % (seen or "未探测到", time.time() - t0))

# 给页面足够时间跑完 splash 过渡，然后连抓三张，最后一张最可信
saved = []
for delay, tag in [(3.0, "a"), (2.5, "b"), (2.5, "c")]:
    time.sleep(delay)
    out = os.path.join(OUTDIR, "guiwin_%s.png" % tag)
    size, raw = grab(h, out)
    saved.append((out, size))
    print("  shot", tag, out, size, "raw=%sx%s" % raw)

p.terminate()
try:
    p.wait(timeout=5)
except Exception:
    p.kill()
print("closed")
print("最后一张:", saved[-1][0])
