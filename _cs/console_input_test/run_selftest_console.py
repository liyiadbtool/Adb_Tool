import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(os.path.dirname(os.path.dirname(HERE)), "adb_log_export.exe")
OUT = os.path.join(HERE, "_selftest.txt")

if os.path.exists(OUT):
    os.remove(OUT)

# 关键：用新控制台启动，stdio 仍然是真控制台，GetConsoleMode 才拿得到句柄；
# 输出重定向到文件，方便事后读取（自测在真控制台里才不会跳过鼠标检查项）。
with open(OUT, "wb") as f:
    p = subprocess.Popen([EXE, "-selftest"], stdout=f, stderr=subprocess.STDOUT,
                         creationflags=0x00000010)
    p.wait(timeout=180)

time.sleep(0.5)
txt = open(OUT, "rb").read().decode("gbk", "replace")

keep = []
for line in txt.splitlines():
    if ("QuickEdit" in line or "选择状态" in line or "ConsoleUtil" in line
            or line.startswith("==") or "自检" in line):
        keep.append(line)
print("\n".join(keep))
print("---- 尾部 ----")
print("\n".join(txt.splitlines()[-6:]))
