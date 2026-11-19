# -*- coding: utf-8 -*-
"""探针 v2：用与 scrcpy 客户端完全相同的参数启动 server，dump 握手字节。

从设备 ps 里抓到的真实命令（scrcpy 5.0.1）：
  app_process / com.genymobile.scrcpy.Server 5.0.1 scid=<8hex> log_level=info \
      audio=false max_size=640 max_fps=10 control=false
socket 名 = localabstract:scrcpy_<scid>
"""
import os
import random
import socket
import subprocess
import sys
import time

ADB = r"D:\Sdk\platform-tools\adb.exe"
JAR_LOCAL = (r"C:\Users\SunWwei\AppData\Local\Microsoft\WinGet\Packages"
             r"\Genymobile.scrcpy_Microsoft.Winget.Source_8wekyb3d8bbwe\scrcpy-win64-v5.0.1\scrcpy-server")


def sh(args, timeout=30):
    p = subprocess.run([ADB] + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return (p.stdout or "") + (p.stderr or "")


def main():
    did = sys.argv[1] if len(sys.argv) > 1 else "0"
    scid = "%08x" % random.getrandbits(32)
    port = 28300 + int(did)
    sockname = "scrcpy_" + scid

    sh(["push", JAR_LOCAL, "/data/local/tmp/scrcpy-server.jar"])
    sh(["forward", "tcp:%d" % port, "localabstract:%s" % sockname])

    cmd = ("CLASSPATH=/data/local/tmp/scrcpy-server.jar app_process / "
           "com.genymobile.scrcpy.Server 5.0.1 scid=%s log_level=info "
           "audio=false max_size=640 max_fps=10 control=false display_id=%s" % (scid, did))
    print("[start]", cmd)
    p = subprocess.Popen([ADB, "shell", cmd], stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True,
                         encoding="utf-8", errors="replace")
    time.sleep(1.6)

    s = socket.create_connection(("127.0.0.1", port), timeout=10)
    s.settimeout(5)
    buf = b""
    try:
        while len(buf) < 2048:
            b = s.recv(2048)
            if not b:
                break
            buf += b
    except socket.timeout:
        pass
    print("[recv] %d 字节" % len(buf))
    print("  hex :", buf[:80].hex(" "))
    print("  repr:", repr(buf[:80]))
    s.close()

    # 收 server 的 stdout，看有没有报错
    time.sleep(0.5)
    try:
        p.terminate()
    except Exception:
        pass
    out = ""
    try:
        out = p.stdout.read() or ""
    except Exception:
        pass
    for line in (out or "").splitlines()[:6]:
        print("  [server]", line[:100])


if __name__ == "__main__":
    main()
