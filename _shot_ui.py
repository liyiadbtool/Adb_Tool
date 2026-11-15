# -*- coding: utf-8 -*-
"""用无头 Edge 给 UI 拍照并做像素解剖（2026-11-15）。

为什么不用屏幕抓图：窗口可能被别的窗口挡住、DPI 虚拟化、WebView2 走
DirectComposition —— 抓出来经常是"整窗纯色"的假象。
无头截图渲染的就是页面本身，颜色/布局是真值。

用法：
  python _shot_ui.py            # 深/浅/护眼 三张，打印标题栏色带
  python _shot_ui.py dark       # 只拍某套主题
"""
import html
import io
import os
import re
import struct
import subprocess
import sys
import tempfile
import zlib

ROOT = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
SHOT = os.path.join(ROOT, "_shot")


def find_edge():
    for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            p = os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")
            if os.path.exists(p):
                return p
    return "msedge.exe"


def decode_png(path):
    d = open(path, "rb").read()
    assert d[:8] == b"\x89PNG\r\n\x1a\n", "不是 PNG"
    pos, idat, plte = 8, b"", None
    w = h = ct = None
    while pos < len(d):
        ln = struct.unpack(">I", d[pos:pos + 4])[0]
        typ = d[pos + 4:pos + 8]
        body = d[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h, bd, ct, comp, filt, inter = struct.unpack(">IIBBBBB", body)
        elif typ == b"IDAT":
            idat += body
        elif typ == b"PLTE":
            plte = body
        elif typ == b"IEND":
            break
        pos += 12 + ln
    raw = zlib.decompress(idat)
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ct]
    stride = w * ch
    out = bytearray(h * stride)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        f = raw[p]; p += 1
        line = bytearray(raw[p:p + stride]); p += stride
        if f == 1:
            for i in range(ch, stride):
                line[i] = (line[i] + line[i - ch]) & 255
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif f == 3:
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
        elif f == 4:
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                b = prev[i]
                c = prev[i - ch] if i >= ch else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return w, h, ch, bytes(out), plte, ct


def px(img, x, y):
    w, h, ch, data, plte, ct = img
    i = (y * w + x) * ch
    if ct == 3:
        k = data[i]
        return plte[k * 3], plte[k * 3 + 1], plte[k * 3 + 2]
    if ch >= 3:
        return data[i], data[i + 1], data[i + 2]
    v = data[i]
    return v, v, v


def band(img, y0, y1, x0, x1):
    r = g = b = n = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            c = px(img, x, y)
            r += c[0]; g += c[1]; b += c[2]; n += 1
    return (r // n, g // n, b // n) if n else (0, 0, 0)


SETUP = """<script>
(function(){
  function apply(){
    var sp=document.getElementById('splash'); if(sp) sp.style.display='none';
    var f=document.querySelector('.frame'); if(f) f.classList.add('show');
    try{ applyTheme('%s'); }catch(e){}
    try{ buildThemeSeg(); }catch(e){}
  }
  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded', apply);
  else apply();
  setTimeout(apply, 120);
})();
</script>"""


def shot(theme):
    src = io.open(UI, encoding="utf-8").read()
    out_html = os.path.join(tempfile.gettempdir(), "_shot_%s.html" % theme)
    io.open(out_html, "w", encoding="utf-8").write(
        src.replace("</body>", (SETUP % theme) + "</body>", 1))
    png = os.path.join(SHOT, "ui_%s.png" % theme)
    if not os.path.isdir(SHOT):
        os.makedirs(SHOT)
    cmd = [find_edge(), "--headless=new", "--disable-gpu", "--hide-scrollbars",
           "--window-size=1100,760", "--virtual-time-budget=4000",
           "--screenshot=" + png,
           "--user-data-dir=" + os.path.join(tempfile.gettempdir(), "edgeprof_shot"),
           "file:///" + out_html.replace("\\", "/")]
    subprocess.run(cmd, capture_output=True, timeout=180)
    if not os.path.exists(png):
        return None
    return png


def report(theme, png):
    img = decode_png(png)
    w, h = img[0], img[1]
    print("== %s  %dx%d  %s" % (theme, w, h, png))
    rows = [("标题栏 y=6..34", 6, 34), ("顶栏 y=44..70", 44, 70),
            ("页签 y=96..124", 96, 124), ("内容 y=200..260", 200, 260)]
    for name, y0, y1 in rows:
        print("   %-16s" % name, band(img, y0, y1, 700, 900))
    print("   标题栏左侧带文字   ", band(img, 8, 32, 20, 260))
    return img


def ascii_top(img, rows=26, cols=96):
    w, h = img[0], img[1]
    ramp = " .:-=+*#%@"
    step_x = max(1, w // cols)
    step_y = max(1, 130 // rows)
    print("   顶部 0..130 行的缩略（x 全宽）：")
    for y in range(0, 130, step_y):
        line = ""
        for x in range(0, w, step_x):
            r, g, b = px(img, x, y)
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            line += ramp[min(9, int(lum / 25.6))]
        print("   " + line)


def main():
    themes = [sys.argv[1]] if len(sys.argv) > 1 else ["dark", "light", "eye"]
    for t in themes:
        png = shot(t)
        if not png:
            print("截图失败:", t)
            continue
        img = report(t, png)
        if t == "dark":
            ascii_top(img)
    return 0


if __name__ == "__main__":
    sys.exit(main())
