"""诊断：WinExe 拉起 cmd 子进程时，到底新建了什么窗口？

背景：用 `ConsoleWindowClass` 检测黑窗抓不到东西（Windows 11 起，
控制台可能由 Windows Terminal / OpenConsole 宿主，类名不再是 ConsoleWindowClass）。
这里不预设类名，把执行期间**所有新出现的可见顶层窗口**列出来看。

目的只是搞清真实机制，得出可靠的检测判据。
"""
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CS = os.path.join(HERE, "_probe_cnw.cs")
EXE_T = os.path.join(HERE, "_probe_cnw_{}.exe")
CSC = r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"

SRC = r'''
using System;
using System.Diagnostics;
using System.Threading;
class P {
    static void Main(string[] a) {
        bool cnw = a.Length > 0 && a[0] == "1";
        ProcessStartInfo psi = new ProcessStartInfo();
        psi.FileName = Environment.GetEnvironmentVariable("COMSPEC");
        if (string.IsNullOrEmpty(psi.FileName)) psi.FileName = "cmd.exe";
        psi.Arguments = "/c ping -n 4 127.0.0.1 > nul";
        psi.UseShellExecute = false;
        psi.CreateNoWindow = cnw;
        using (Process p = Process.Start(psi)) { p.WaitForExit(); }
        Thread.Sleep(2500);
    }
}
'''

u = ctypes.windll.user32
EnumProcType = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def all_windows():
    """返回 {hwnd: (pid, class, title, visible)}  —— 包含不可见窗口"""
    out = {}

    def cb(hwnd, lp):
        pid = wt.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        cls = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(hwnd, cls, 256)
        t = ctypes.create_unicode_buffer(300)
        u.GetWindowTextW(hwnd, t, 300)
        out[hwnd] = (pid.value, cls.value, t.value, bool(u.IsWindowVisible(hwnd)))
        return True

    u.EnumWindows(EnumProcType(cb), 0)
    return out


def run(flag):
    exe = EXE_T.format("true" if flag == "1" else "false")
    r = subprocess.run([CSC, "/nologo", "/target:winexe", "/out:" + exe, CS],
                       capture_output=True, text=True)
    if not os.path.exists(exe):
        raise RuntimeError("编译失败 " + (r.stdout or "") + (r.stderr or ""))

    before = all_windows()
    p = subprocess.Popen([exe, flag], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)

    neww = {}
    end = time.time() + 6
    while time.time() < end and p.poll() is None:
        cur = all_windows()
        for h, v in cur.items():
            if h not in before:
                neww[h] = v
        time.sleep(0.05)
    try:
        p.kill()
    except Exception:
        pass
    time.sleep(0.4)
    return neww


def main():
    open(CS, "w", encoding="utf-8").write(SRC)

    for label, flag in (("CreateNoWindow=false", "0"), ("CreateNoWindow=true", "1")):
        print("=" * 70)
        print(label)
        nw = run(flag)
        if not nw:
            print("  没有新窗口")
        for h, (pid, cls, title, vis) in nw.items():
            print("  hwnd=%-10s pid=%-8s visible=%-5s class=%-30r title=%r"
                  % (h, pid, vis, cls, title))

    for t in ("true", "false"):
        try:
            os.remove(EXE_T.format(t))
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
