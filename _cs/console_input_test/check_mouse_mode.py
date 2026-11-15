# -*- coding: utf-8 -*-
"""
check_mouse_mode.py — 验证被测程序把控制台 QuickEdit 打开了。

为什么要单独验：滚轮上滑看历史 / 拖选复制 / 右键粘贴，三件事全部由
conhost 的 QuickEdit 提供。控制台的输入模式是整个控制台共享的，所以
只要新开一个控制台跑被测程序，再 AttachConsole 读一下输入模式，就能
确认用户拿到的那份 exe 到底开没开。

用法：python check_mouse_mode.py <exe路径>
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

ENABLE_MOUSE_INPUT = 0x0010
ENABLE_QUICK_EDIT_MODE = 0x0040
ENABLE_EXTENDED_FLAGS = 0x0080

k32.AttachConsole.argtypes = [wintypes.DWORD]
k32.AttachConsole.restype = wintypes.BOOL
k32.FreeConsole.argtypes = []
k32.FreeConsole.restype = wintypes.BOOL
k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                            ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                            wintypes.HANDLE]
k32.CreateFileW.restype = wintypes.HANDLE
k32.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
k32.GetConsoleMode.restype = wintypes.BOOL


def main():
    exe = sys.argv[1] if len(sys.argv) > 1 else r"..\..\adb_log_export.exe"
    exe = os.path.abspath(exe)

    proc = subprocess.Popen([exe], cwd=os.path.dirname(exe),
                            creationflags=CREATE_NEW_CONSOLE)
    time.sleep(1.6)                      # 等它初始化并落好控制台模式

    k32.FreeConsole()
    if not k32.AttachConsole(proc.pid):
        print("ATTACH FAIL", ctypes.get_last_error())
        proc.kill()
        return 2

    h_in = k32.CreateFileW("CONIN$", GENERIC_RW, FILE_SHARE_RW, None,
                           OPEN_EXISTING, 0, None)
    mode = wintypes.DWORD(0)
    if not k32.GetConsoleMode(h_in, ctypes.byref(mode)):
        print("GetConsoleMode FAIL", ctypes.get_last_error())
        proc.kill()
        return 2

    m = mode.value
    qe = bool(m & ENABLE_QUICK_EDIT_MODE)
    ext = bool(m & ENABLE_EXTENDED_FLAGS)
    mouse = bool(m & ENABLE_MOUSE_INPUT)

    print("控制台输入模式 = 0x%04X" % m)
    print("  QuickEdit  (滚轮上滑 / 拖选复制 / 右键粘贴) : %s" % ("ON" if qe else "OFF"))
    print("  扩展标志位 (QuickEdit 生效的前提)          : %s" % ("ON" if ext else "OFF"))
    print("  鼠标输入位 (由控制台属性决定，本工具不改)  : %s" % ("ON" if mouse else "OFF"))

    proc.kill()
    ok = qe and ext
    print("\n总体: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
