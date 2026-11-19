# -*- coding: utf-8 -*-
"""编译 CLI 与 GUI 两端，并回显关键错误行。"""
import subprocess, os, sys, re

# 2026-11-19：原为写死的旧机器路径（C:\Users\zuo20\...），换机必挂；按本文件位置推导
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run(bat, cwd, title):
    print("=" * 70)
    print("BUILD:", title)
    print("=" * 70)
    p = subprocess.run(
        ["cmd", "/c", bat],
        cwd=cwd,
        input=b"\r\n",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    out = p.stdout.decode("gbk", "replace")
    bad = [l for l in out.splitlines()
           if re.search(r"error|错误|CS\d{4}|Exception|拒绝访问|另一个程序正在使用", l, re.I)]
    tail = out.strip().splitlines()[-25:]
    print("\n".join(tail))
    if bad:
        print("---- ERROR LINES ----")
        for l in bad[:40]:
            print(l)
    print("EXIT:", p.returncode)
    return p.returncode, bad

os.chdir(ROOT)
rc1, bad1 = run(r"build.bat", os.path.join(ROOT, "_cs"), "CLI")
rc2, bad2 = run(r"build_gui.bat", os.path.join(ROOT, "adb_log_gui"), "GUI")

# 产物时间戳校验：csc 被占用时会打 "拒绝访问" 却仍然报 Compile success，
# 退出码 0 —— 这是最坑的一类假成功（改了代码，跑的还是旧 exe）。
import time
stale = []
for exe in [os.path.join(ROOT, "adb_log_export.exe"),
            os.path.join(ROOT, "adb_log_gui", "adb_Tool.exe")]:
    if not os.path.exists(exe):
        stale.append(exe + " 不存在")
        continue
    age = time.time() - os.path.getmtime(exe)
    print("%-14s 距今 %5.1f 秒" % (os.path.basename(exe), age))
    if age > 300:
        stale.append(exe + " 未更新")

print()
print("RESULT: cli=%d gui=%d errors=%d stale=%d" % (
    rc1, rc2, len(bad1) + len(bad2), len(stale)))
for s in stale:
    print("  STALE:", s)
ok = (rc1 == 0 and rc2 == 0 and not bad1 and not bad2 and not stale)
sys.exit(0 if ok else 1)
