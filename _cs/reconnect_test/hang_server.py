# -*- coding: utf-8 -*-
"""
hang_server.py — 假 adb server：占住 5037 端口，收下连接但永不回应。

用途：复现"adb server 僵死"这款最典型的故障，验证工具不会假死、
并且能明确告诉用户"端口被谁占着"。

跑法（单独开一个窗口）：
    python hang_server.py            # 默认占 120 秒

然后在另一个窗口跑：
    adb_log_export.exe      再输入 :r 或 :rr
    SynTestLite_cli.exe dev rr

期望：
    · 工具不会卡死，20 秒内给出结论
    · 提示"5037 端口被 python.exe（PID xxxx）占着，不是 adb"，而不是
      "服务重启未成功"这种没有下一步的话

注意：跑完记得关掉本脚本（或等它自己退出），否则真 adb 起不来。
"""

import socket
import sys
import time

PORT = 5037
SECONDS = 120


def main():
    seconds = SECONDS
    if len(sys.argv) > 1:
        try:
            seconds = int(sys.argv[1])
        except ValueError:
            pass

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", PORT))
    s.listen(32)
    s.settimeout(1.0)

    print("listening on 127.0.0.1:%d for %d s" % (PORT, seconds), flush=True)

    conns = []
    end = time.time() + seconds
    while time.time() < end:
        try:
            c, _addr = s.accept()
            conns.append(c)        # 收下，但一个字都不回
        except socket.timeout:
            continue

    try:
        s.close()
    except Exception:
        pass
    print("done", flush=True)


if __name__ == "__main__":
    main()
