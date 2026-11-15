# -*- coding: utf-8 -*-
"""
drive_console.py — 在真实控制台窗口里"敲键盘"，验证唤醒后输入是否还能上屏。

原理：
  1) 用 CREATE_NEW_CONSOLE 启动被测程序，它拥有自己的控制台窗口
  2) 本进程 FreeConsole 后 AttachConsole 到它，直接往它的输入缓冲区写按键记录
  3) 读它的屏幕缓冲区，看字符有没有被回显、命令有没有被执行

这样不依赖鼠标键盘，也不抢用户焦点。
"""

import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

k32 = ctypes.WinDLL("kernel32", use_last_error=True)


CREATE_NEW_CONSOLE = 0x00000010
GENERIC_RW = 0xC0000000
FILE_SHARE_RW = 0x00000003
OPEN_EXISTING = 3

VK_RETURN = 13
VK_BACK = 8


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



# 64 位下必须声明 argtypes/restype，否则句柄和 pid 会被截断
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
k32.ReadConsoleOutputCharacterW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR,
                                            wintypes.DWORD, COORD,
                                            ctypes.POINTER(wintypes.DWORD)]
k32.ReadConsoleOutputCharacterW.restype = wintypes.BOOL
k32.GetConsoleScreenBufferInfo.argtypes = [wintypes.HANDLE,
                                           ctypes.POINTER(CONSOLE_SCREEN_BUFFER_INFO)]
k32.GetConsoleScreenBufferInfo.restype = wintypes.BOOL


def open_console_files():
    h_in = k32.CreateFileW("CONIN$", GENERIC_RW, FILE_SHARE_RW, None, OPEN_EXISTING, 0, None)
    h_out = k32.CreateFileW("CONOUT$", GENERIC_RW, FILE_SHARE_RW, None, OPEN_EXISTING, 0, None)
    if h_in in (None, -1) or h_out in (None, -1):
        raise OSError("打开 CONIN$/CONOUT$ 失败")
    return h_in, h_out


def send_keys(h_in, events):
    n = len(events)
    arr = (INPUT_RECORD * n)()
    for i, (down, vk, ch) in enumerate(events):
        arr[i].EventType = 1  # KEY_EVENT
        arr[i].KeyEvent.bKeyDown = down
        arr[i].KeyEvent.wRepeatCount = 1
        arr[i].KeyEvent.wVirtualKeyCode = vk
        arr[i].KeyEvent.UnicodeChar = ch
        arr[i].KeyEvent.dwControlKeyState = 0
    written = wintypes.DWORD(0)
    ok = k32.WriteConsoleInputW(h_in, arr, n, ctypes.byref(written))
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    return written.value


def type_text(h_in, text):
    ev = []
    for ch in text:
        ev.append((1, 0, ch))
        ev.append((0, 0, ch))
    return send_keys(h_in, ev)


def press(h_in, vk, ch):
    return send_keys(h_in, [(1, vk, ch), (0, vk, ch)])


def screen_buffer_info(h_out):
    info = CONSOLE_SCREEN_BUFFER_INFO()
    k32.GetConsoleScreenBufferInfo(h_out, ctypes.byref(info))
    return info


def read_all(h_out, max_lines=200):
    info = screen_buffer_info(h_out)
    width = info.dwSize.X
    height = min(info.dwSize.Y, max_lines)
    top = max(0, height - 60)
    lines = []
    buf = ctypes.create_unicode_buffer(width)
    n = wintypes.DWORD(0)
    for y in range(top, height):
        k32.ReadConsoleOutputCharacterW(h_out, buf, width, COORD(0, y), ctypes.byref(n))
        lines.append(buf.value[:n.value].rstrip())
    return lines


def screen_text(h_out):
    return "\n".join(read_all(h_out))


def cleanup(proc):
    try:
        k32.FreeConsole()
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass


def main():
    exe = sys.argv[1]
    cwd = os.path.dirname(os.path.abspath(exe))

    proc = subprocess.Popen([exe], cwd=cwd, creationflags=CREATE_NEW_CONSOLE)
    time.sleep(1.0)

    k32.FreeConsole()
    if not k32.AttachConsole(proc.pid):
        print("ATTACH FAIL", ctypes.get_last_error())
        cleanup(proc)
        return 2

    h_in, h_out = open_console_files()
    print("attached to pid", proc.pid)

    # 1) 等初始化跑完（adb 是"卡死"的，这里会等它超时进离线模式）
    deadline = time.time() + 25
    while time.time() < deadline:
        if ">" in screen_text(h_out):
            break
        time.sleep(0.4)

    # 2) 再等一会儿：让后台探活超时并触发自动急救
    time.sleep(7)
    txt = screen_text(h_out)
    recovered = ("adb 无响应" in txt) or ("重启 adb" in txt)
    print("[结果] 卡死被检测到并自动急救: %s" % ("YES" if recovered else "NO"))

    # 3) 关键验证：adb 还卡着的时候敲字，必须立刻回显
    t0 = time.time()
    type_text(h_in, "hello")
    echoed = False
    while time.time() - t0 < 3:
        if "hello" in screen_text(h_out):
            echoed = True
            break
        time.sleep(0.05)
    print("[结果] 敲字回显: %s (%.2fs)" % ("YES" if echoed else "NO", time.time() - t0))

    # 4) 再验证命令真的被执行：回车后应出现帮助里的独有字样
    press(h_in, VK_RETURN, "\r")
    ran = False
    t1 = time.time()
    while time.time() - t1 < 8:
        if "设备未连接。输入" in screen_text(h_out):
            ran = True
            break
        time.sleep(0.1)
    print("[结果] 命令被执行: %s (%.2fs)" % ("YES" if ran else "NO", time.time() - t1))

    print("\n--- 屏幕末尾 ---")
    print("\n".join(read_all(h_out)[-26:]))

    cleanup(proc)
    ok = echoed and ran and recovered
    print("\n总体: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
