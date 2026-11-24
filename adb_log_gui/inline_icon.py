# -*- coding: utf-8 -*-
"""
inline_icon.py —— 把 adb_Tool.ico 内联进 ui.html（一次生成，永久生效）

为什么需要它：
  标题栏 / 加载页的图标原来是 ui.html 里**手工复刻的 SVG**，和 adb_Tool.ico
  是两份独立的图形数据 —— 换 ico 时页面上不变，用户会以为"图标换不了"。

  直接 <img src="adb_Tool.ico"> 也不行：页面是 file:// 加载的，
  WebView2 里取不到同目录的 ico，显示成裂图（实测过）。

  所以改成"构建期内联"：把这个 ico 里最大的一帧转成 base64，写进 ui.html
  的 <style id="appicon-style"> 里，页面用 background-image 显示 ——
  不依赖任何文件读取，WebView2 一定能画出来。

用法（换图标后跑一次，或让 build_gui.bat 自动调用）：
    python adb_log_gui/inline_icon.py

只改 ui.html 里两个标记之间的内容，其余部分不动。幂等：重复跑结果一致。
"""
import base64
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ICO = os.path.join(HERE, "adb_Tool.ico")
UI = os.path.join(HERE, "webview2", "ui.html")

BEGIN = "/*APPICON:BEGIN*/"
END = "/*APPICON:END*/"


def biggest_png_frame(ico_path):
    """从 .ico 里挑出最大的 PNG 帧，返回原始 PNG 字节。

    .ico 的目录项里，宽高为 0 表示 256。帧数据可能是 PNG（Vista+），
    也可能是 BMP（很老的图标）—— 这里只处理 PNG，BMP 会让用户重新导出。
    """
    data = open(ico_path, "rb").read()
    if len(data) < 6:
        raise ValueError("ico 文件太小")
    count = struct.unpack("<H", data[4:6])[0]

    best = None
    best_size = -1
    for i in range(count):
        off = 6 + i * 16
        w, h, _, _, _, bpp, size, data_off = struct.unpack(
            "<BBBBHHII", data[off:off + 16])
        w = w or 256
        frame = data[data_off:data_off + size]
        if frame[:4] != b"\x89PNG":
            continue                      # 跳过 BMP 帧
        if w > best_size:
            best_size = w
            best = frame
    if best is None:
        raise ValueError("ico 里没有 PNG 帧（可能是老式 BMP 图标），"
                         "请用现代工具重新导出")
    return best, best_size


def main():
    if not os.path.exists(ICO):
        print("找不到 %s" % ICO)
        return 1
    if not os.path.exists(UI):
        print("找不到 %s" % UI)
        return 1

    png, size = biggest_png_frame(ICO)
    b64 = base64.b64encode(png).decode("ascii")
    css = (BEGIN + "\n"
           "/* 由 inline_icon.py 自动生成，勿手改。源文件：adb_log_gui/adb_Tool.ico（%d×%d） */\n"
           ".appmark-img{background-image:url(\"data:image/png;base64,%s\");}\n"
           % (size, size, b64)
           + END)

    html = open(UI, encoding="utf-8").read()
    pat = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.S)
    if not pat.search(html):
        print("ui.html 里找不到 APPICON 标记，没法注入")
        return 1

    new_html = pat.sub(lambda m: css, html)
    if new_html != html:
        open(UI, "w", encoding="utf-8", newline="\n").write(new_html)
        print("已内联图标：%d×%d，base64 %d 字符" % (size, size, len(b64)))
    else:
        print("图标未变化，无需改动")
    return 0


if __name__ == "__main__":
    sys.exit(main())
