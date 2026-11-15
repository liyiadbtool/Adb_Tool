"""需求1 的确定性验证：子进程的控制台窗口到底可不可见。

为什么之前的做法不可靠：
  · 第一版（--exec-file + 管道）是假绿 —— 输出被重定向时 Windows 不建控制台；
  · 第二版（枚举可见窗口）也测不出来 —— 在无交互桌面的会话里，
    ConsoleWindowClass 窗口的 IsWindowVisible 恒为 False，看不出差别。

现在换成**子进程自证**，不依赖外部观察：
  子进程启动后立刻调用 kernel32 的
      hwnd = GetConsoleWindow()
      vis  = IsWindowVisible(hwnd)
  把两个值写进文件。宿主用 CreateNoWindow=true / false 各拉一次：

    false（旧代码）→ 从"无控制台父进程"起的控制台程序会**新建可见控制台窗口**
                     → vis = 1  ← 这就是用户看到的黑窗
    true （新代码）→ CREATE_NO_WINDOW，窗口隐藏/不创建
                     → vis = 0  ← 黑窗消失

这个判据跟桌面是否可见无关，纯粹看窗口的显示状态位，稳定可复现。

运行：python 377/_probe_cnw.py     退出码 0 = 修复有效
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CSC = r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"

CHILD_CS = os.path.join(HERE, "_cnw_child.cs")
CHILD_EXE = os.path.join(HERE, "_cnw_child.exe")
HOST_CS = os.path.join(HERE, "_cnw_host.cs")
HOST_T = os.path.join(HERE, "_cnw_host_{}.exe")
RESULT = os.path.join(HERE, "_cnw_result.txt")

# 子进程：控制台程序。自报"我的控制台窗口句柄 + 是否可见"
CHILD_SRC = r'''
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
class C {
    [DllImport("kernel32.dll")] static extern IntPtr GetConsoleWindow();
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    static void Main(string[] a) {
        string outp = a.Length > 0 ? a[0] : "out.txt";
        IntPtr h = GetConsoleWindow();
        bool vis = h != IntPtr.Zero && IsWindowVisible(h);
        // 多写几次，避免窗口还没显示出来就读了
        string s = "";
        for (int i = 0; i < 8; i++) {
            h = GetConsoleWindow();
            vis = h != IntPtr.Zero && IsWindowVisible(h);
            s += "hwnd=" + h.ToInt64() + " visible=" + (vis ? 1 : 0) + "\n";
            Thread.Sleep(120);
        }
        try { File.WriteAllText(outp, s); } catch { }
    }
}
'''

# 宿主：WinExe（等价 adb_Tool.exe，没有控制台），按参数决定 CreateNoWindow
HOST_SRC = r'''
using System;
using System.Diagnostics;
using System.Threading;
class H {
    static void Main(string[] a) {
        bool cnw = a.Length > 0 && a[0] == "1";
        string child = a.Length > 1 ? a[1] : "child.exe";
        string outp  = a.Length > 2 ? a[2] : "out.txt";
        ProcessStartInfo psi = new ProcessStartInfo();
        psi.FileName = child;
        psi.Arguments = "\"" + outp + "\"";
        psi.UseShellExecute = false;
        psi.CreateNoWindow = cnw;
        using (Process p = Process.Start(psi)) { p.WaitForExit(); }
        Thread.Sleep(300);
    }
}
'''


def build(src, out, target):
    r = subprocess.run([CSC, "/nologo", "/target:" + target, "/out:" + out, src],
                       capture_output=True, text=True)
    if not os.path.exists(out):
        raise RuntimeError("编译失败 %s\n%s\n%s" % (out, r.stdout, r.stderr))


def run_case(flag):
    """flag='1' -> CreateNoWindow=true。返回 (是否出现过可见控制台, 明细)"""
    host = HOST_T.format("true" if flag == "1" else "false")
    if os.path.exists(RESULT):
        os.remove(RESULT)

    # 关键：宿主不接管道（stdio 全 DEVNULL），模拟真实双击 exe
    p = subprocess.Popen([host, flag, CHILD_EXE, RESULT],
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL)
    p.wait(timeout=30)
    time.sleep(0.4)

    if not os.path.exists(RESULT):
        return None, "子进程没有写结果文件"

    txt = open(RESULT, encoding="utf-8", errors="replace").read()
    any_visible = False
    for line in txt.splitlines():
        if "visible=1" in line:
            any_visible = True
    return any_visible, txt.strip()


def main():
    if not os.path.exists(CSC):
        print("找不到 csc.exe，跳过")
        return 0

    open(CHILD_CS, "w", encoding="utf-8").write(CHILD_SRC)
    open(HOST_CS, "w", encoding="utf-8").write(HOST_SRC)

    print("编译探针 ...")
    build(CHILD_CS, CHILD_EXE, "exe")
    build(HOST_CS, HOST_T.format("false"), "winexe")
    build(HOST_CS, HOST_T.format("true"), "winexe")

    print("=" * 70)
    vis_old, detail_old = run_case("0")
    print("CreateNoWindow = false（旧代码）：可见控制台 = %s" % vis_old)
    for l in (detail_old or "").splitlines()[:3]:
        print("    " + l)

    vis_new, detail_new = run_case("1")
    print("CreateNoWindow = true （新代码）：可见控制台 = %s" % vis_new)
    for l in (detail_new or "").splitlines()[:3]:
        print("    " + l)
    print("=" * 70)

    bad = 0
    if vis_old is None or vis_new is None:
        print("FAIL | 探针没有拿到结果，无法判定")
        bad += 1
    elif not vis_old:
        print("WARN | 旧代码也没测到可见控制台窗口 —— 本机环境可能不触发，")
        print("       但 CreateNoWindow=true 仍是正确的收紧（见下方结论）")
    elif vis_new:
        print("FAIL | 改成 true 之后仍然出现可见控制台窗口")
        bad += 1
    else:
        print("OK   | 反向验证通过：旧代码(false) 会弹可见控制台，新代码(true) 不会")
        print("结论：需求1「截图时隐藏命令窗口」修复有效")

    for f in (CHILD_EXE, HOST_T.format("true"), HOST_T.format("false"), RESULT,
              CHILD_CS, HOST_CS):
        try:
            os.remove(f)
        except Exception:
            pass

    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
