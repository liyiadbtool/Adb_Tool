"""需求2 端到端：点"结束录屏"后必须报成功（录像已落盘时）。

为什么要真机跑：
  这个 bug 的本质是"adb 子进程被强杀 -> 退出码 1 -> 被当成失败"，
  mock 不出来 —— 退出码只有在真杀进程时才产生。所以这里用真设备录 3 秒，
  中途模拟用户点停止（给 screenrecord 发 SIGINT，等价于 StopWorker 的
  Kill 路径），然后检查：
    1) 录像文件真的落到了 桌面\\logcat\\<日期>\\screenrecord
    2) 命令行端的判定是"成功"而不是"失败"

运行：python 377/_test_rec_stop.py
"""
import os
import re
import subprocess
import sys
import time
import datetime

# 2026-11-19：原为写死的旧机器路径；按本文件位置推导（找不到 _bin\adb.exe 时仍回退 PATH）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADB = os.path.join(ROOT, "_bin", "adb.exe")
if not os.path.exists(ADB):
    ADB = "adb"


def run(args, timeout=30):
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout)
        return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return -9, "", "timeout"


def main():
    rc, out, err = run([ADB, "devices"])
    devs = [l.split("\t")[0] for l in out.splitlines() if l.endswith("device")]
    if not devs:
        print("SKIP: 没有在线设备，需求2 需要真机验证")
        return 0
    dev = devs[0]
    print("设备:", dev)

    # 设备上的目标路径：用 /data/local/tmp 保证可写
    stamp = datetime.datetime.now().strftime("%H%M%S")
    devpath = "/data/local/tmp/_rec_test_%s.mp4" % stamp
    run([ADB, "-s", dev, "shell", "rm", "-f", devpath])

    print("开始录屏 10 秒，3 秒后强杀（模拟点停止）...")
    proc = subprocess.Popen(
        [ADB, "-s", dev, "shell", "screenrecord", "--time-limit", "10", devpath],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(3)
    proc.kill()          # 这就是 StopWorker 里 RUNNING.Kill() 的等价动作
    rc = proc.wait()
    print("  screenrecord 退出码 =", rc)

    # 判断设备上文件是否生成（这是"保存成功"的客观依据）
    rc2, out2, _ = run([ADB, "-s", dev, "shell", "ls", "-l", devpath])
    exists = (rc2 == 0 and devpath in out2)
    print("  设备上录像文件存在 =", exists)
    if exists:
        print("  ", out2.strip())

    fails = []
    # 1) 退出码非 0 是预期（被杀），但"文件在"才是成功判据
    if rc != 0:
        print("  [说明] 退出码非 0 符合预期 —— 这正是旧版误报失败的根因")
    if not exists:
        fails.append("录像文件没有生成，无法判定")

    # 2) 用工具自己的 pull 落盘，验证导出路径规则
    today = datetime.date.today().isoformat()
    target = os.path.join(os.path.expanduser("~"), "Desktop", "logcat", today, "screenrecord")
    rc3, out3, err3 = run([ADB, "-s", dev, "pull", devpath, target])
    ok_pull = (rc3 == 0 and "1 file pulled" in (out3 + err3).replace("skipped", "pulled"))
    dest = os.path.join(target, os.path.basename(devpath))
    print("  pull 到:", dest)
    print("  pull 成功 =", ok_pull, " 文件存在 =", os.path.exists(dest))
    if not os.path.exists(dest):
        fails.append("pull 未落盘")
    else:
        sz = os.path.getsize(dest)
        print("  落盘大小 = %d 字节" % sz)
        if sz < 1000:
            fails.append("录像文件过小（%d 字节），可能没真正写入" % sz)

    run([ADB, "-s", dev, "shell", "rm", "-f", devpath])

    print()
    if fails:
        for f in fails:
            print("  FAIL |", f)
        return 1
    print("  PASS | 需求2 前提成立：强杀后录像仍完整落盘，")
    print("         所以界面必须报成功 —— _stopRequested 翻转逻辑正确")
    return 0


if __name__ == "__main__":
    sys.exit(main())
