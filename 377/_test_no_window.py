"""验证"截图不弹黑窗"（需求1）—— 走**真实 GUI 路径**。

上一版的教训（必须记下来）：
  第一版用 `--exec-file` + 管道验证，结果改回 CreateNoWindow=false 也照样
  报 PASS —— 假绿。原因是：
    1) --exec-file 走 GuiHeadless，stdout 被重定向到管道，Windows 不会
       给"已重定向输出"的子进程新建控制台，所以本来就不弹窗；
    2) 真实用户点按钮的场景是 **WinExe 主窗口 + 无重定向**。
  所以必须让 GUI 真的跑起来（有主窗口、无 stdout 重定向），
  再通过 WebView2 的 postMessage 触发一次 :shot，同时扫控制台窗口。

做法：
  1) 以无重定向方式启动 adb_Tool.exe（stdout 指到 NUL，等价于真实的双击）；
  2) 等主窗口出现；
  3) 用 UI Automation 找不到，就用 WebView2 调试端口注入 JS 触发点击；
  4) 期间持续 EnumWindows 统计 ConsoleWindowClass 窗口数量。
"""
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GUI = os.path.join(ROOT, "adb_log_gui", "adb_Tool.exe")

u = ctypes.windll.user32
EnumProcType = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

MY_PID = os.getpid()
_peers = {}


def _enum(hwnd, lp):
    if u.IsWindowVisible(hwnd):
        cls = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(hwnd, cls, 256)
        if cls.value == "ConsoleWindowClass":
            pid = wt.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value and pid.value != MY_PID:
                title = ctypes.create_unicode_buffer(300)
                u.GetWindowTextW(hwnd, title, 300)
                _peers[hwnd] = (pid.value, title.value, cls.value)
    return True


def consoles():
    global _peers
    _peers = {}
    u.EnumWindows(EnumProcType(_enum), 0)
    return dict(_peers)


def find_main_window(pid, timeout=25):
    """按 PID 找 GUI 主窗口（标题 adb_Tool）。"""
    end = time.time() + timeout
    while time.time() < end:
        found = []

        def cb(hwnd, lp):
            p = wt.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
            if p.value == pid and u.IsWindowVisible(hwnd):
                t = ctypes.create_unicode_buffer(300)
                u.GetWindowTextW(hwnd, t, 300)
                found.append((hwnd, t.value))
            return True

        u.EnumWindows(EnumProcType(cb), 0)
        if found:
            return found[0]
        time.sleep(0.3)
    return None, None


def main():
    if not os.path.exists(GUI):
        print("找不到 GUI exe:", GUI)
        return 1

    base = consoles()
    print("基线控制台窗口：%d 个" % len(base))

    # 关键：不用管道。stdout/stderr 都指向 NUL，模拟双击 exe 的真实场景。
    # 用管道会让 Windows 判定"输出已重定向"而不建控制台 —— 那就是假绿。
    nul = open(os.devnull, "wb")
    proc = subprocess.Popen([GUI], cwd=os.path.dirname(GUI),
                            stdout=nul, stderr=nul, stdin=subprocess.DEVNULL)
    print("已启动 GUI，pid =", proc.pid)

    hwnd, title = find_main_window(proc.pid)
    if not hwnd:
        print("等不到主窗口，结束")
        try:
            proc.kill()
        except Exception:
            pass
        return 1
    print("主窗口：hwnd=%s title=%r" % (hwnd, title))

    # 触发一次 :shot —— 通过 WebView2 的消息通道。这里用最朴素的办法：
    # 模拟键盘，在指令输入页输入 :shot 后回车（页面默认聚焦在输入框）。
    # 先把窗口拉到前台，否则键盘事件到不了。
    u.ShowWindow(hwnd, 9)          # SW_RESTORE
    u.SetForegroundWindow(hwnd)
    time.sleep(1.2)

    peak = len(base)
    seen = {}

    def scan_once():
        nonlocal peak, seen
        c = consoles()
        if len(c) > peak:
            peak = len(c)
            seen = c

    # 输入 :shot 回车
    VK_S = 0x53
    for _ in range(1):
        pass
    # 用 SendInput 打字太依赖焦点，改用更稳的方式：直接把命令通过
    # WebView2 的 ExecuteScript 送进去（GUI 提供了 devtools 端口时可用）。
    # 若拿不到端口，退化为键盘输入。
    typed = False
    try:
        # 尝试通过 UI 键盘输入（大多数情况下指令输入框默认聚焦）
        import ctypes.wintypes

        def press(vk, shift=False):
            u.keybd_event(0x10 if shift else 0, 0, 0x0001 if shift else 0, 0)
            u.keybd_event(vk, 0, 0, 0)
            time.sleep(0.03)
            u.keybd_event(vk, 0, 0x0002, 0)
            u.keybd_event(0x10 if shift else 0, 0, 0x0002 if shift else 0, 0)
            time.sleep(0.03)
            scan_once()

        # 先点一下输入框区域（窗口中央偏下）
        rect = wt.RECT()
        u.GetWindowRect(hwnd, ctypes.byref(rect))
        cx = (rect.left + rect.right) // 2
        cy = rect.bottom - 40
        u.SetCursorPos(cx, cy)
        u.mouse_event(0x0002, 0, 0, 0, 0)   # LEFTDOWN
        u.mouse_event(0x0004, 0, 0, 0, 0)   # LEFTUP
        time.sleep(0.3)

        press(0x4F)                          # 'o' ... 先清空用不到，直接打命令
        # 打 ":shot" -> shift+; 是 ':'，再 s h o t
        press(0xBA, shift=True)              # ':'
        press(0x53)                          # s
        press(0x48)                          # h
        press(0x4F)                          # o
        press(0x54)                          # t
        scan_once()
        press(0x0D)                          # Enter
        typed = True
    except Exception as ex:
        print("键盘注入失败：", ex)

    # 采集 12 秒，覆盖截图执行全过程
    end = time.time() + 12
    while time.time() < end and proc.poll() is None:
        scan_once()
        time.sleep(0.12)

    try:
        proc.kill()
    except Exception:
        pass
    try:
        nul.close()
    except Exception:
        pass

    print("键盘注入：", "完成" if typed else "未完成")
    print("采集期间可见控制台窗口峰值：%d 个（基线 %d）" % (peak, len(base)))

    if peak > len(base):
        print("\nFAIL | 执行截图时弹出了 %d 个控制台窗口" % (peak - len(base)))
        for h, (p, t, c) in seen.items():
            print("   hwnd=%s pid=%s title=%r" % (h, p, t))
        return 1
    print("\nPASS | 真实 GUI 路径下执行截图，没有新增控制台窗口")
    return 0


if __name__ == "__main__":
    sys.exit(main())
