# -*- coding: utf-8 -*-
"""
test_input_features.py — 验证"键盘能上屏 + Ctrl+V 能粘贴"。

复现方式与 drive_console.py 一致：新开控制台跑被测程序，AttachConsole 后
直接往它的输入缓冲区写按键记录，再读它的屏幕缓冲区判断结果。
区别是这里会先写一段文字到剪贴板，再发 Ctrl+V，验证 conhost 的粘贴通道
在工具里是通的（右键粘贴走的是同一条通道）。
"""

import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
u32 = ctypes.WinDLL("user32", use_last_error=True)

CREATE_NEW_CONSOLE = 0x00000010
GENERIC_RW = 0xC0000000
FILE_SHARE_RW = 0x00000003
OPEN_EXISTING = 3

VK_RETURN = 13
VK_BACK = 8
VK_V = 0x56
LEFT_CTRL_PRESSED = 0x0008
CF_UNICODETEXT = 13

k32.AttachConsole.argtypes = [wintypes.DWORD]
k32.AttachConsole.restype = wintypes.BOOL
k32.FreeConsole.argtypes = []
k32.FreeConsole.restype = wintypes.BOOL
k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                            ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                            wintypes.HANDLE]
k32.CreateFileW.restype = wintypes.HANDLE
k32.WriteConsoleInputW.argtypes = [wintypes.HANDLE, ctypes.c_void_p,
                                   wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
k32.WriteConsoleInputW.restype = wintypes.BOOL
k32.GetConsoleScreenBufferInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
k32.GetConsoleScreenBufferInfo.restype = wintypes.BOOL


class KEY_EVENT_RECORD(ctypes.Structure):
    _fields_ = [("bKeyDown", wintypes.BOOL),
                ("wRepeatCount", wintypes.WORD),
                ("wVirtualKeyCode", wintypes.WORD),
                ("wVirtualScanCode", wintypes.WORD),
                ("UnicodeChar", wintypes.WCHAR),
                ("dwControlKeyState", wintypes.DWORD)]


class INPUT_RECORD(ctypes.Structure):
    _fields_ = [("EventType", wintypes.WORD),
                ("_pad", wintypes.WORD),
                ("KeyEvent", KEY_EVENT_RECORD)]


class COORD(ctypes.Structure):
    _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]


class SMALL_RECT(ctypes.Structure):
    _fields_ = [("Left", wintypes.SHORT), ("Top", wintypes.SHORT),
                ("Right", wintypes.SHORT), ("Bottom", wintypes.SHORT)]


class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
    _fields_ = [("dwSize", COORD), ("dwCursorPosition", COORD),
                ("wAttributes", wintypes.WORD), ("srWindow", SMALL_RECT),
                ("dwMaximumWindowSize", COORD)]


# COORD 定义在下面，这里补上真实签名（按值传坐标，和 drive_console.py 一致）
k32.ReadConsoleOutputCharacterW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR,
                                            wintypes.DWORD, COORD,
                                            ctypes.POINTER(wintypes.DWORD)]


def set_clipboard(text):
    GMEM_MOVEABLE = 0x0002
    k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    k32.GlobalAlloc.restype = wintypes.HGLOBAL
    k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalUnlock.restype = wintypes.BOOL
    u32.OpenClipboard.argtypes = [wintypes.HWND]
    u32.OpenClipboard.restype = wintypes.BOOL
    u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    u32.SetClipboardData.restype = wintypes.HANDLE

    data = ctypes.create_unicode_buffer(text)
    size = ctypes.sizeof(data)
    u32.OpenClipboard(None)
    try:
        u32.EmptyClipboard()
        h = k32.GlobalAlloc(GMEM_MOVEABLE, size)
        p = k32.GlobalLock(h)
        ctypes.memmove(p, data, size)
        k32.GlobalUnlock(h)
        if not u32.SetClipboardData(CF_UNICODETEXT, h):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        u32.CloseClipboard()


def open_console_files():
    h_in = k32.CreateFileW("CONIN$", GENERIC_RW, FILE_SHARE_RW, None,
                           OPEN_EXISTING, 0, None)
    h_out = k32.CreateFileW("CONOUT$", GENERIC_RW, FILE_SHARE_RW, None,
                            OPEN_EXISTING, 0, None)
    if h_in in (None, -1) or h_out in (None, -1):
        raise OSError("打开 CONIN$/CONOUT$ 失败")
    return h_in, h_out


def send_keys(h_in, events):
    n = len(events)
    arr = (INPUT_RECORD * n)()
    for i, (down, vk, ch, ctrl) in enumerate(events):
        arr[i].EventType = 1
        arr[i].KeyEvent.bKeyDown = down
        arr[i].KeyEvent.wRepeatCount = 1
        arr[i].KeyEvent.wVirtualKeyCode = vk
        arr[i].KeyEvent.UnicodeChar = ch
        arr[i].KeyEvent.dwControlKeyState = ctrl
    written = wintypes.DWORD(0)
    if not k32.WriteConsoleInputW(h_in, arr, n, ctypes.byref(written)):
        raise ctypes.WinError(ctypes.get_last_error())
    return written.value


def type_text(h_in, text):
    ev = []
    for ch in text:
        ev.append((1, 0, ch, 0))
        ev.append((0, 0, ch, 0))
    return send_keys(h_in, ev)


def press(h_in, vk, ch):
    return send_keys(h_in, [(1, vk, ch, 0), (0, vk, ch, 0)])


def ctrl_v(h_in):
    # Ctrl+V：conhost 自己会读剪贴板并把字符塞进输入缓冲区（右键粘贴同一条通道）
    return send_keys(h_in, [(1, VK_V, "\x16", LEFT_CTRL_PRESSED),
                            (0, VK_V, "\x16", LEFT_CTRL_PRESSED)])


def read_all(h_out, max_lines=200):
    info = CONSOLE_SCREEN_BUFFER_INFO()
    k32.GetConsoleScreenBufferInfo(h_out, ctypes.byref(info))
    width = info.dwSize.X
    height = min(info.dwSize.Y, max_lines)
    top = max(0, height - 60)
    lines = []
    buf = ctypes.create_unicode_buffer(width)
    n = wintypes.DWORD(0)
    for y in range(top, height):
        k32.ReadConsoleOutputCharacterW(h_out, buf, width, COORD(0, y),
                                        ctypes.byref(n))
        lines.append(buf.value[:n.value].rstrip())
    return lines


def screen_text(h_out):
    return "\n".join(read_all(h_out))


def last_line(h_out):
    """当前光标那一行 —— 判断"输入有没有上屏"只看这一行，
    否则屏幕上任何一处出现同样的字母都会造成假通过。"""
    info = CONSOLE_SCREEN_BUFFER_INFO()
    k32.GetConsoleScreenBufferInfo(h_out, ctypes.byref(info))
    width = info.dwSize.X
    y = info.dwCursorPosition.Y
    buf = ctypes.create_unicode_buffer(width)
    n = wintypes.DWORD(0)
    k32.ReadConsoleOutputCharacterW(h_out, buf, width, COORD(0, y), ctypes.byref(n))
    return buf.value[:n.value].rstrip()


def wait_for_input(h_out, needle, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if needle in last_line(h_out):
            return True
        time.sleep(0.05)
    return False


def wait_for(h_out, needle, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if needle in screen_text(h_out):
            return True
        time.sleep(0.1)
    return False


def main():
    exe = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else r"..\..\adb_log_export.exe")
    proc = subprocess.Popen([exe], cwd=os.path.dirname(exe),
                            creationflags=CREATE_NEW_CONSOLE)
    time.sleep(1.2)

    k32.FreeConsole()
    if not k32.AttachConsole(proc.pid):
        print("ATTACH FAIL", ctypes.get_last_error())
        proc.kill()
        return 2

    h_in, h_out = open_console_files()
    if not wait_for(h_out, ">", 40):
        print("[FAIL] 等不到提示符")
        print("\n".join(read_all(h_out)[-20:]))
        proc.kill()
        return 1

    ok = True

    # 1) 键盘能上屏（只看光标所在行）
    type_text(h_in, "hel")
    typed = wait_for_input(h_out, "hel", 3)
    print("[1] 键盘回显: %s" % ("YES" if typed else "NO"))
    ok = ok and typed

    # 2) 退格能删掉（走的是同一套行编辑逻辑）
    for _ in range(3):
        press(h_in, VK_BACK, "\b")
    time.sleep(0.3)
    gone = "hel" not in last_line(h_out)
    print("[2] 退格删除: %s" % ("YES" if gone else "NO"))
    ok = ok and gone

    # 3) Ctrl+V 粘贴（右键粘贴走的是同一条 conhost 通道）
    #    用一个屏幕上绝不会出现的串，避免"别处碰巧有 h"造成假通过
    set_clipboard("zz42")
    ctrl_v(h_in)
    pasted = wait_for_input(h_out, "zz42", 3)
    print("[3] Ctrl+V 粘贴: %s" % ("YES" if pasted else "NO"))
    ok = ok and pasted

    # 4) 多行粘贴：只取第一行，并且明确提示，不静默吞内容
    for _ in range(8):
        press(h_in, VK_BACK, "\b")
    set_clipboard("aa42\r\nbb43")
    ctrl_v(h_in)
    # 粘贴后提示会把提示符顶到下一行，所以这里按整屏判断：
    # "aa42" 出现过、"bb43" 一次都不许出现
    wait_for(h_out, "aa42", 3)
    txt_all = screen_text(h_out)
    single = ("aa42" in txt_all) and ("bb43" not in txt_all)
    warned = wait_for(h_out, "只取第一行", 3)
    print("[4] 多行只取首行: %s / 有提示: %s" % ("YES" if single else "NO",
                                                "YES" if warned else "NO"))
    ok = ok and single and warned

    # 5) 清干净后敲 h 回车，验证命令真的执行
    for _ in range(8):
        press(h_in, VK_BACK, "\b")
    time.sleep(0.2)
    type_text(h_in, "h")
    time.sleep(0.2)
    press(h_in, VK_RETURN, "\r")
    ran = wait_for(h_out, "跳转点", 8)
    print("[5] 命令执行: %s" % ("YES" if ran else "NO"))
    ok = ok and ran

    print("\n--- 屏幕末尾 ---")
    print("\n".join(read_all(h_out)[-12:]))

    proc.kill()
    print("\n总体: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
