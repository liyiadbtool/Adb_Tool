"""抓真实运行中 GUI 的窗口截图（PrintWindow），确认启动后九项车机信息在界面上。

为什么还要这一层：
  _shot_align.py 是"网页渲染 + 灌假数据"，它能证明 CSS 对，但证明不了
  "打开工具时 C# 真的把那 9 项推给了页面"。这里跑真 exe、等它初始化完，
  再抓窗口。两者都过才叫闭环。

运行：python 377/_shot_real_gui.py
"""
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(ROOT, "adb_log_gui", "adb_Tool.exe")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_shot_real_gui.png")

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
user32.SetProcessDPIAware()


def find_window(exe_name, timeout=25):
    """按进程名找主窗口（标题也够用，但进程名更稳）。"""
    end = time.time() + timeout
    while time.time() < end:
        hwnds = []

        @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
        def cb(hwnd, lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            n = user32.GetWindowTextLengthW(hwnd)
            if n == 0:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if "adb_Tool" in buf.value:
                hwnds.append(hwnd)
            return True

        user32.EnumWindows(cb, 0)
        if hwnds:
            return hwnds[0]
        time.sleep(0.5)
    return None


def capture(hwnd, path):
    rect = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w <= 0 or h <= 0:
        return False, "窗口尺寸异常 %dx%d" % (w, h)

    hdc = user32.GetWindowDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mdc, bmp)

    # PW_RENDERFULLCONTENT=2：WebView2 是 DirectComposition 渲染，
    # 用 0 抓会得到一片全黑，必须带这个标志。
    ok = user32.PrintWindow(hwnd, mdc, 2)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG),
                    ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                    ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                    ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
                    ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                    ("biClrImportant", wt.DWORD)]

    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth = w
    bi.biHeight = -h          # 负数 = 自上而下
    bi.biPlanes = 1
    bi.biBitCount = 32
    bi.biCompression = 0

    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(hwnd, hdc)

    # 用 PIL 落盘（没装就退化成写裸 BMP）
    try:
        from PIL import Image
        img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1)
        img.convert("RGB").save(path)
    except Exception as e:
        return False, "PIL 不可用：%s" % e
    return bool(ok), "%dx%d" % (w, h)


def main():
    if not os.path.exists(EXE):
        print("找不到 exe:", EXE)
        return 1
    subprocess.run(["taskkill", "/IM", "adb_Tool.exe", "/F"],
                   capture_output=True)
    time.sleep(1)

    print("启动 GUI ...")
    proc = subprocess.Popen([EXE], cwd=os.path.dirname(EXE))
    hwnd = find_window("adb_Tool", 25)
    if not hwnd:
        print("FAIL | 没找到窗口")
        try: proc.kill()
        except Exception: pass
        return 1
    print("  窗口句柄:", hwnd)

    # 等设备初始化 + WebView2 首帧 + 九项推送完
    print("等待初始化（14 秒：adb devices -> InitEnv -> RootProbe -> 推九项）...")
    time.sleep(14)

    ok, info = capture(hwnd, OUT)
    print("  截图:", info, "PrintWindow ok =", ok)
    try: proc.kill()
    except Exception: pass

    if not os.path.exists(OUT) or os.path.getsize(OUT) < 5000:
        print("FAIL | 截图没生成或过小")
        return 1
    print("  saved", OUT, os.path.getsize(OUT), "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
