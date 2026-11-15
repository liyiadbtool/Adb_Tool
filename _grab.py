# -*- coding: utf-8 -*-
"""抓取运行中窗口的像素并做颜色剖面（不依赖 PIL）。

用途：验证自绘标题栏/顶栏在深色与浅色主题下的实际渲染色，
因为本会话的图片通道不可用，只能靠数值 + ASCII 当"眼睛"。

用法：
  python _grab.py            # 抓当前窗口，打印剖面
  python _grab.py save x.bmp # 另存 bmp
"""
import ctypes
import os
import struct
import sys
from ctypes import wintypes as wt

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
user32.SetProcessDPIAware()

TITLE = u"网联服务_Adb_Tool"


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


# 64 位下必须显式声明签名，否则默认 int 装不下 HWND 会 OverflowError
user32.IsWindowVisible.argtypes = [wt.HWND]
user32.IsWindowVisible.restype = wt.BOOL
user32.GetWindowTextLengthW.argtypes = [wt.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.GetWindowRect.restype = wt.BOOL
user32.GetWindowDC.argtypes = [wt.HWND]
user32.GetWindowDC.restype = wt.HDC
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
user32.GetDC.argtypes = [wt.HWND]
user32.GetDC.restype = wt.HDC
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.SetForegroundWindow.restype = wt.BOOL
gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wt.HBITMAP
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.BitBlt.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         wt.HDC, ctypes.c_int, ctypes.c_int, wt.DWORD]
gdi32.GetDIBits.argtypes = [wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ctypes.c_void_p,
                            ctypes.POINTER(BITMAPINFO), wt.UINT]
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wt.HDC]



def find_window(title):
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, lp):
        hwnd = int(hwnd) if not isinstance(hwnd, int) else hwnd
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 2)
        user32.GetWindowTextW(hwnd, buf, n + 2)
        if title in buf.value:
            found.append((hwnd, buf.value))
        return True

    user32.EnumWindows(cb, 0)
    return found[0][0] if found else None


def grab(hwnd):
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    # 注意：不能抓窗口 DC —— WebView2 走 DirectComposition，窗口 DC 里没有它的像素，
    # 抓出来只有窗体底色（表现为"整窗纯色"的假象）。改抓整屏，再按窗口矩形裁。
    user32.SetForegroundWindow(hwnd)
    hdc = user32.GetDC(0)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    gdi32.BitBlt(mem, 0, 0, w, h, hdc, r.left, r.top, 0x00CC0020)

    bi = BITMAPINFO()
    bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.bmiHeader.biWidth = w
    bi.bmiHeader.biHeight = -h          # 负 = 自上而下
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 32
    bi.bmiHeader.biCompression = 0
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(0, hdc)
    return w, h, buf.raw, (r.left, r.top)


def px(data, w, x, y):
    i = (y * w + x) * 4
    return data[i + 2], data[i + 1], data[i]     # BGR -> RGB


def band(data, w, y0, y1, x0, x1):
    r = g = b = n = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            c = px(data, w, x, y)
            r += c[0]; g += c[1]; b += c[2]; n += 1
    return (r // n, g // n, b // n) if n else (0, 0, 0)


def save_bmp(path, w, h, data):
    row = ((w * 3 + 3) // 4) * 4
    pad = b"\x00" * (row - w * 3)
    body = bytearray()
    for y in range(h - 1, -1, -1):      # BMP 自下而上
        for x in range(w):
            b, g, r = px(data, w, x, y)[2], px(data, w, x, y)[1], px(data, w, x, y)[0]
            body += bytes((b, g, r))
        body += pad
    hdr = b"BM" + struct.pack("<IHHI", 54 + len(body), 0, 0, 54)
    info = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, len(body), 2835, 2835, 0, 0)
    with open(path, "wb") as f:
        f.write(hdr + info + bytes(body))


def main():
    hwnd = find_window(TITLE)
    if not hwnd:
        print("找不到窗口：", TITLE)
        return 2
    w, h, data, pos = grab(hwnd)
    print("窗口 %dx%d @ %s" % (w, h, pos))
    print("  y=2..6    (标题栏上沿)   ", band(data, w, 2, 6, w // 3, w // 2))
    print("  y=8..30   (标题栏文字区) ", band(data, w, 8, 30, w // 3, w // 2))
    print("  y=32..38  (标题栏下沿)   ", band(data, w, 32, 38, w // 3, w // 2))
    print("  y=44..52  (顶栏上沿)     ", band(data, w, 44, 52, w // 3, w // 2))
    print("  y=60..80  (顶栏内容)     ", band(data, w, 60, 80, w // 3, w // 2))
    print("  y=96..120 (页签带)       ", band(data, w, 96, 120, w // 3, w // 2))
    print("  y=200..240(内容区)       ", band(data, w, 200, 240, w // 2, w // 2 + 120))
    # 右上角窗口按钮区（关闭键悬停前应为透明）
    print("  窗口按钮区底色           ", band(data, w, 8, 30, w - 140, w - 110))
    if len(sys.argv) > 2 and sys.argv[1] == "save":
        save_bmp(sys.argv[2], w, h, data)
        print("  已保存", sys.argv[2])
    # 顶栏左侧状态胶囊所在行的 ASCII（验证布局是否还在）
    print("\n  顶部 0..130 行、左侧 0..520 列的灰度缩略：")
    ramp = " .:-=+*#%@"
    for y in range(0, min(130, h), 6):
        line = ""
        for x in range(0, min(520, w), 6):
            r, g, b = px(data, w, x, y)
            lum = (0.299 * r + 0.587 * g + 0.114 * b)
            line += ramp[min(9, int(lum / 25.6))]
        print("  " + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
