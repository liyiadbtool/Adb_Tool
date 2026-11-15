# -*- coding: utf-8 -*-
"""阶段 3：内联 SVG Apple 单线化 + 品牌图形四处同源 + 多尺寸 ico 生成。
纯 Python 手写 PNG/ICO（环境无 Pillow / ImageMagick），零第三方依赖。"""
import io, math, os, re, struct, sys, zlib

ROOT = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
ICO1 = os.path.join(ROOT, "adb_log_gui", "adb_Tool.ico")
ICO2 = os.path.join(ROOT, "adb_log_gui", "icons", "adb_Tool.ico")
SVG = os.path.join(ROOT, "adb_log_gui", "icons", "svg", "Apple终端标识.svg")

with io.open(UI, "r", encoding="utf-8") as f:
    s = f.read()

fails = []
def rep(old, new, cnt=1, tag=u""):
    global s
    n = s.count(old)
    if n != cnt:
        fails.append(u"%s: 期望 %d 实际 %d" % (tag or old[:40], cnt, n))
        return
    s = s.replace(old, new, cnt)

# ---------------------------------------------------------------- 品牌几何（唯一事实源）
# 24×24 坐标系：圆角矩形 (2.75,4.5)-(21.25,19.5) r=4；> 折线；_ 底线；线宽 1.75
BRAND_24 = (u'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            u'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
            u'<rect x="2.75" y="4.5" width="18.5" height="15" rx="4"/>'
            u'<path d="M7.5 9.75l3.25 2.5-3.25 2.5"/>'
            u'<path d="M12.75 15.25h3.75"/></svg>')
BRAND_48 = (u'<svg viewBox="0 0 48 48" fill="none" stroke="currentColor" '
            u'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
            u'<g transform="scale(2)">'
            u'<rect x="2.75" y="4.5" width="18.5" height="15" rx="4"/>'
            u'<path d="M7.5 9.75l3.25 2.5-3.25 2.5"/>'
            u'<path d="M12.75 15.25h3.75"/></g></svg>')

# ---- 加载过渡层：黑猫 → 终端标识（48×48 单独一档） ----
rep(u'<svg viewBox="0 0 48 48" fill="none" stroke="#3fb99b" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">\n'
    u'      <path d="M8 20v10a6 6 0 006 6h20a6 6 0 006-6V20"/>\n'
    u'      <path d="M14 20l-2-9 9 5M34 20l2-9-9 5"/>\n'
    u'      <circle cx="19" cy="26" r="1.6" fill="#3fb99b" stroke="none"/>\n'
    u'      <circle cx="29" cy="26" r="1.6" fill="#3fb99b" stroke="none"/>\n'
    u'      <path d="M24 29l-1.2 1.4h2.4z" fill="#3fb99b"/>\n'
    u'    </svg>', BRAND_48, 1, u"加载层 SVG")
rep(u'<!-- 黑猫加载过渡层：黑猫 + 加载文字提醒，数据就绪后淡出 -->',
    u'<!-- 加载过渡层：Apple 单线终端标识（与 adb_Tool.ico 同源） -->', 1, u"加载层注释")

# ---- 顶栏品牌按钮 ----
rep(u'<!-- 黑猫标识：与应用图标（方案3）一致 -->',
    u'<!-- 品牌标识：Apple 单线终端，与应用图标 / 加载层 / 任务栏四处同源 -->', 1, u"顶栏注释")
rep(u'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">\n'
    u'        <path d="M4 10v5a3 3 0 003 3h10a3 3 0 003-3v-5"/>\n'
    u'        <path d="M7 10l-1-4.5 4.5 2.5M17 10l1-4.5-4.5 2.5"/>\n'
    u'        <circle cx="9.5" cy="13" r="0.9" fill="currentColor" stroke="none"/>\n'
    u'        <circle cx="14.5" cy="13" r="0.9" fill="currentColor" stroke="none"/>\n'
    u'        <path d="M12 14.5l-0.6 0.7h1.2z" fill="currentColor" stroke="none"/>\n'
    u'      </svg>', BRAND_24, 1, u"顶栏品牌 SVG")

# ---- theme-btn 初始 SVG：去掉硬编码绿 ----
rep(u'<button class="icon-btn" id="theme-btn" title="切换主题" onclick="toggleTheme()">\n'
    u'      <svg viewBox="0 0 24 24" fill="none" stroke="#3fb99b" stroke-width="2" stroke-linecap="round"><path d="M20.5 14.2A8.5 8.5 0 119.8 3.5a7 7 0 0010.7 10.7z"/></svg>',
    u'<button class="icon-btn" id="theme-btn" title="切换主题" onclick="toggleTheme()">\n'
    u'      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M20.5 14.2A8.5 8.5 0 119.8 3.5a7 7 0 0010.7 10.7z"/></svg>',
    1, u"theme-btn 初始 SVG")

# ---- THEME_ICON 三态：key / 语义 / 形状保留，颜色改 currentColor、线宽统一 ----
MOON = u'<path d="M20.5 14.2A8.5 8.5 0 119.8 3.5a7 7 0 0010.7 10.7z"/>'
SUN = u'<circle cx="12" cy="12" r="4.2"/><path d="M12 2.6v2.2M12 19.2v2.2M2.6 12h2.2M19.2 12h2.2M5.4 5.4l1.6 1.6M17 17l1.6 1.6M18.6 5.4L17 7M7 17l-1.6 1.6"/>'
EYE = u'<path d="M2.2 12S5.8 5.6 12 5.6 21.8 12 21.8 12 18.2 18.4 12 18.4 2.2 12 2.2 12z"/><circle cx="12" cy="12" r="3.1"/>'
def themed_svg(body):
    return (u'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" '
            u'stroke-linecap="round" stroke-linejoin="round">' + body + u'</svg>')
rep(u"  dark: '<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"#3fb99b\" stroke-width=\"2\" stroke-linecap=\"round\">" + MOON + u"</svg>',",
    u"  dark: '" + themed_svg(MOON) + u"',", 1, u"THEME_ICON.dark")
rep(u"  light: '<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"#e8a33d\" stroke-width=\"2\" stroke-linecap=\"round\">" + SUN + u"</svg>',",
    u"  light: '" + themed_svg(SUN) + u"',", 1, u"THEME_ICON.light")
rep(u"  eye:   '<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"#a8761f\" stroke-width=\"2\" stroke-linecap=\"round\">" + EYE + u"</svg>'",
    u"  eye:   '" + themed_svg(EYE) + u"'", 1, u"THEME_ICON.eye")

# ---- 16×16 小图标统一到 24×24 档（内部 scale(1.5)，视觉等价） ----
pat = re.compile(r'(<svg[^>]*?)viewBox="0 0 16 16"([^>]*?)>(.*?)</svg>')
n16 = len(pat.findall(s))
if n16 != 6:
    fails.append(u"16×16 SVG 期望 6 处，实际 %d 处" % n16)
else:
    s = pat.sub(lambda m: m.group(1) + u'viewBox="0 0 24 24"' + m.group(2) + u'>'
                + u'<g transform="scale(1.5)">' + m.group(3) + u'</g></svg>', s)

# ---- 全局：消灭内联 SVG 硬编码色 + 补 round join + 粗线收敛到 1.75 ----
s = s.replace(u'stroke="#3fb99b"', u'stroke="currentColor"')
s = s.replace(u'fill="#3fb99b"', u'fill="currentColor"')
s = s.replace(u'stroke-width="2.4"', u'stroke-width="1.75"')
s = s.replace(u'stroke-width="2.2"', u'stroke-width="1.75"')
s = re.sub(r'(<svg[^>]*stroke-linecap="round")(?!\s+stroke-linejoin)(>)',
           r'\1 stroke-linejoin="round"\2', s)

if fails:
    for f in fails:
        sys.stdout.write(u"FAIL " + f + u"\n")
    raise SystemExit(u"[ERROR] %d 处锚点异常，未写回" % len(fails))

with io.open(UI, "w", encoding="utf-8", newline="") as f:
    f.write(s)

# ================================================================ ico 生成
BLUE = (10, 132, 255)   # Apple systemBlue dark
WHITE = (255, 255, 255)
SEGS = [((7.5, 9.75), (10.75, 12.25)),
        ((10.75, 12.25), (7.5, 14.75)),
        ((12.75, 15.25), (16.5, 15.25))]

def seg_dist(px, py, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = dx * dx + dy * dy
    if L == 0:
        return math.hypot(px - a[0], py - a[1])
    t = max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / L))
    return math.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy))

def rr_sdf(px, py, x0, y0, x1, y1, r):
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    qx = abs(px - cx) - (x1 - x0) / 2.0 + r
    qy = abs(py - cy) - (y1 - y0) / 2.0 + r
    return math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - r

def render(S):
    unit = 24.0 / S
    rows = bytearray()
    for y in range(S):
        rows.append(0)                       # PNG filter: none
        for x in range(S):
            ux, uy = (x + 0.5) * unit, (y + 0.5) * unit
            d_px = rr_sdf(ux, uy, 2.75, 4.5, 21.25, 19.5, 4.0) / unit
            a_bg = max(0.0, min(1.0, 0.5 - d_px))
            d_line = min(seg_dist(ux, uy, a, b) for a, b in SEGS)
            a_fg = max(0.0, min(1.0, 0.5 - (d_line - 0.875) / unit))
            for ch in range(3):
                rows.append(int(BLUE[ch] + (WHITE[ch] - BLUE[ch]) * a_fg + 0.5))
            rows.append(int(255 * a_bg + 0.5))
    return bytes(rows)

def chunk(t, d):
    return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)

def png(S, raw):
    ihdr = struct.pack('>IIBBBBB', S, S, 8, 6, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr)
            + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))

SIZES = [16, 24, 32, 48, 64, 128, 256]
imgs = [(sz, png(sz, render(sz))) for sz in SIZES]
off = 6 + 16 * len(imgs)
ico = bytearray(struct.pack('<HHH', 0, 1, len(imgs)))
for sz, b in imgs:
    ico += struct.pack('<BBBBHHII', sz % 256, sz % 256, 0, 0, 1, 32, len(b), off)
    off += len(b)
for sz, b in imgs:
    ico += b
ico = bytes(ico)

for p in (ICO1, ICO2):
    with open(p, 'wb') as f:
        f.write(ico)

# 可编辑 SVG 源（与 ico 同一几何）
with io.open(SVG, 'w', encoding='utf-8', newline='') as f:
    f.write(u'<?xml version="1.0" encoding="UTF-8"?>\n'
            u'<!-- adb_Tool 应用图标源：与 ui.html 顶栏 / 加载层 / 任务栏四处同源。\n'
            u'     24×24 坐标系，线宽 1.75，圆角矩形 r=4，终端提示符 >_。 -->\n'
            u'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="256" height="256">\n'
            u'  <rect x="2.75" y="4.5" width="18.5" height="15" rx="4" fill="#0A84FF"/>\n'
            u'  <g fill="none" stroke="#FFFFFF" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">\n'
            u'    <path d="M7.5 9.75l3.25 2.5-3.25 2.5"/>\n'
            u'    <path d="M12.75 15.25h3.75"/>\n'
            u'  </g>\n</svg>\n')

# 复核
hard = sorted(set(re.findall(r'(?:stroke|fill)="(#[0-9a-fA-F]{3,8})"', s)))
vb = sorted(set(re.findall(r'viewBox="([^"]+)"', s)))
cnt = struct.unpack('<H', ico[4:6])[0]
sys.stdout.write(u"OK 图标专项完成\n")
sys.stdout.write(u"内联 SVG 硬编码色残留: %s\n" % (hard or u"无"))
sys.stdout.write(u"viewBox 档位: %s\n" % ", ".join(vb))
sys.stdout.write(u"ico: %d B / %d 个尺寸 %s / 首帧 PNG 签名=%s\n" %
                 (len(ico), cnt, SIZES, imgs[0][1][:4] == b'\x89PNG'))
sys.stdout.write(u"同步: adb_log_gui/adb_Tool.ico + icons/adb_Tool.ico + icons/svg/Apple终端标识.svg\n")
