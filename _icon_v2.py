# -*- coding: utf-8 -*-
"""应用图标 v2：车载中控 + 测试工程师 + 联网（2026-11-15）。

设计约束（Apple App Icon 惯例）：
  · 单一焦点图形、无文字、无细发丝线（16px 必须能读）
  · 深蓝对角渐变 + 左上柔光营造高级感；不描边不描外框（Windows 侧自带圆角蒙版）
  · 元素只用 4 个：中控屏面板 / 终端提示符 >_ / 顶部信号弧 / 中控台底座

纯 Python 手写 PNG/ICO（无 Pillow），analytic AA，7 档尺寸。
"""
import io
import math
import os
import struct
import sys
import zlib

ROOT = os.path.dirname(os.path.abspath(__file__))
ICO1 = os.path.join(ROOT, "adb_log_gui", "adb_Tool.ico")
ICO2 = os.path.join(ROOT, "adb_log_gui", "icons", "adb_Tool.ico")
SVG = os.path.join(ROOT, "adb_log_gui", "icons", "svg", "AdbTool-中控终端.svg")
PREVIEW = os.path.join(ROOT, "docs", "icon-preview.png")

# ---------------------------------------------------------------- 100×100 设计坐标
BG = (2.0, 2.0, 98.0, 98.0, 22.0)          # 底：圆角方（近似 Apple squircle）
PANEL = (13.0, 32.0, 87.0, 74.0, 10.0)     # 中控屏
LEDGE = (30.0, 79.0, 70.0, 83.5, 2.25)     # 中控台底座
CHEV = ((33.0, 46.0), (44.0, 53.0), (33.0, 60.0))
CURSOR = ((56.0, 60.0), (67.0, 60.0))
CROWN = (50.0, 29.5, (6.5, 11.0))          # 信号弧圆心 / 两层半径（含原点圆点）
C_W, C_STROKE = 5.8, 3.0                    # 提示符线宽 / 信号弧线宽

# A17：配色从"深蓝渐变"改成"黑白灰" —— 用户要求底色黑、整图只用黑白灰。
# 层次靠明度差撑：底 #2E2E2E→#050505（黑/深灰，严格中性，R=G=B），图形白，信号弧与底座用半透明白
# （压在黑底上就是中灰）。不再有彩色，任务栏/Alt+Tab/文件管理器里也不会跟
# 别的蓝色图标混在一起。
C_TOP = (0x2E, 0x2E, 0x2E)                 # 渐变起点（左上，深灰）
C_BOT = (0x05, 0x05, 0x05)                 # 渐变终点（右下，近黑）


def clamp01(t):
    return 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)


def rr_sdf(px, py, box):
    x0, y0, x1, y1, r = box
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    qx = abs(px - cx) - (x1 - x0) / 2.0 + r
    qy = abs(py - cy) - (y1 - y0) / 2.0 + r
    return math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - r


def seg_dist(px, py, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = dx * dx + dy * dy
    if L == 0.0:
        return math.hypot(px - a[0], py - a[1])
    t = max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / L))
    return math.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy))


def arc_dist(px, py, cx, cy, r, a0, a1):
    """圆弧（屏幕坐标，角度 0=右、PI/2=下）到点的距离。"""
    dx, dy = px - cx, py - cy
    ang = math.atan2(dy, dx)
    if ang < 0:
        ang += 2 * math.pi
    lo, hi = a0, a1
    if lo <= ang <= hi:
        return abs(math.hypot(dx, dy) - r)
    p0 = (cx + r * math.cos(lo), cy + r * math.sin(lo))
    p1 = (cx + r * math.cos(hi), cy + r * math.sin(hi))
    return min(math.hypot(px - p0[0], py - p0[1]), math.hypot(px - p1[0], py - p1[1]))


def over(dst, src, a):
    """straight-alpha over：dst 已是 [r,g,b] 0..1。"""
    a = clamp01(a)
    if a <= 0.0:
        return dst
    return [dst[i] + (src[i] - dst[i]) * a for i in range(3)]


def render(S):
    """多尺寸美术分级：≤32px 简化（Apple 对 16/32 单独出简化稿的惯例）。

    16px：底 + 屏面板 + 提示符（加粗）+ 底座 —— 只保留 1px 能表达的三块明度
    24/32px：补信号弧（加粗到 3.4，否则缩到 1px 以下变成噪点）
    48px+：完整细节（面板描边 / 柔光 / 细弧）
    """
    unit = 100.0 / S
    simple = S <= 32
    tiny = S <= 16
    panel_fill = 0.16 if not simple else 0.22
    stroke_w = C_W if S >= 48 else 6.8
    crown_w = 3.4 if simple else C_STROKE
    rows = bytearray()
    # 信号弧从"左"经"上"到"右"：PI -> 2PI（屏幕坐标 y 向下，2PI 即回到右）
    a0, a1 = math.pi, 2 * math.pi
    for y in range(S):
        rows.append(0)                                   # PNG filter none
        for x in range(S):
            ux, uy = (x + 0.5) * unit, (y + 0.5) * unit

            # --- 1. 底：对角渐变 ---
            t = clamp01((ux + uy) / 200.0)
            col = [C_TOP[i] / 255.0 + (C_BOT[i] - C_TOP[i]) / 255.0 * t for i in range(3)]
            # 左上柔光（高级感的来源：像玻璃受光）
            hd = math.hypot(ux - 26.0, uy - 8.0)
            ha = (0.26 if not simple else 0.22) * clamp01(1.0 - hd / 82.0) ** 1.7
            col = over(col, [1.0, 1.0, 1.0], ha)
            # 右下微暗，压住边角（A17：原来是 [0,0.05,0.30] 偏蓝，在灰度图里
            # 会留下一圈 15/255 的蓝调 —— 用户要求整图只用黑白灰，改纯黑压暗）
            sd = math.hypot(ux - 92.0, uy - 96.0)
            col = over(col, [0.0, 0.0, 0.0], 0.20 * clamp01(1.0 - sd / 70.0) ** 2.0)
            a_bg = clamp01(0.5 - rr_sdf(ux, uy, BG) / unit)

            # --- 2. 中控屏：玻璃面板 + 顶部内高光 ---
            dp = rr_sdf(ux, uy, PANEL)
            col = over(col, [1.0, 1.0, 1.0], clamp01(0.5 - dp / unit) * panel_fill)
            if S >= 48:
                rim = clamp01(0.5 - (abs(dp) - 1.35) / unit) * 0.30
                if rim > 0:
                    # 只在面板上半圈更亮（受光）
                    k = clamp01((72.0 - uy) / 42.0) * 0.55 + 0.45
                    col = over(col, [1.0, 1.0, 1.0], rim * k)

            # --- 3. 终端提示符 >_（唯一一级高光） ---
            dmin = min(seg_dist(ux, uy, CHEV[0], CHEV[1]),
                       seg_dist(ux, uy, CHEV[1], CHEV[2]),
                       seg_dist(ux, uy, CURSOR[0], CURSOR[1]))
            col = over(col, [1.0, 1.0, 1.0],
                       clamp01(0.5 - (dmin - stroke_w / 2.0) / unit))

            # --- 4. 信号弧（联网）：圆点 + 两层弧，从面板上沿升起 ---
            if not tiny:
                cx, cy, radii = CROWN
                dd = math.hypot(ux - cx, uy - cy) - 2.0            # 原点圆点
                a_dot = clamp01(0.5 - dd / unit) * 0.62
                if simple:
                    # 小尺寸只留一条更粗的弧：两条细弧在 32px 会糊成一团
                    da = arc_dist(ux, uy, cx, cy, 9.5, a0, a1)
                    w = 3.2
                else:
                    da = min(arc_dist(ux, uy, cx, cy, radii[0], a0, a1),
                             arc_dist(ux, uy, cx, cy, radii[1], a0, a1))
                    w = crown_w
                # 0.55 而非 0.72：弧必须比提示符暗一档，否则争焦点
                a_arc = clamp01(0.5 - (da - w / 2.0) / unit) * 0.55
                col = over(col, [1.0, 1.0, 1.0], max(a_dot, a_arc))

            # --- 5. 中控台底座 ---
            dl = rr_sdf(ux, uy, LEDGE)
            col = over(col, [1.0, 1.0, 1.0],
                       clamp01(0.5 - dl / unit) * (0.34 if not simple else 0.40))

            for ch in range(3):
                rows.append(int(col[ch] * 255.0 + 0.5))
            rows.append(int(a_bg * 255.0 + 0.5))
    return bytes(rows)


def chunk(t, d):
    return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)


def png(S, raw):
    ihdr = struct.pack('>IIBBBBB', S, S, 8, 6, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr)
            + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def preview_sheet(cache):
    """256 大字 + 128 / 64 / 32 / 16 对照，浅底与深底各一组。"""
    W, H = 760, 420
    px = bytearray(W * H * 4)
    for i in range(W * H):                       # 浅底 #F2F2F7
        px[i * 4:i * 4 + 4] = bytes((242, 242, 247, 255))

    def put(x0, y0, img, S):
        for yy in range(S):
            for xx in range(S):
                i = ((y0 + yy) * W + (x0 + xx)) * 4
                j = (yy * S + xx) * 4
                a = img[j + 3] / 255.0
                for c in range(3):
                    px[i + c] = int(img[j + c] * a + px[i + c] * (1 - a))
                px[i + 3] = 255

    put(24, 24, cache[256], 256)
    y = 40
    for sz in (128, 64, 32, 16):
        put(310, y, cache[sz], sz)
        put(470, y + (128 - sz) // 2, cache[sz], sz)
        y += sz + 15

    for yy in range(300, 400):                   # 深底 #1C1C1E
        for xx in range(24, 736):
            i = (yy * W + xx) * 4
            px[i:i + 4] = bytes((28, 28, 30, 255))
    x = 40
    for sz in (16, 32, 64, 128):
        put(x, 350 - sz // 2, cache[sz], sz)
        x += sz + 26
    return raw_png(W, H, bytes(px))


def raw_png(W, H, raw):
    ihdr = struct.pack('>IIBBBBB', W, H, 8, 6, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr)
            + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


SIZES = [16, 24, 32, 48, 64, 128, 256]
RAW = {}
imgs = []
for sz in SIZES:
    raw = render(sz)
    RAW[sz] = raw
    imgs.append((sz, png(sz, raw)))

off = 6 + 16 * len(imgs)
ico = bytearray(struct.pack('<HHH', 0, 1, len(imgs)))
for sz, b in imgs:
    ico += struct.pack('<BBBBHHII', sz % 256, sz % 256, 0, 0, 1, 32, len(b), off)
    off += len(b)
for sz, b in imgs:
    ico += b
ico = bytes(ico)

for p in (ICO1, ICO2):
    d = os.path.dirname(p)
    if not os.path.isdir(d):
        os.makedirs(d)
    with open(p, 'wb') as f:
        f.write(ico)

with io.open(SVG, 'w', encoding='utf-8', newline='') as f:
    f.write(u'<?xml version="1.0" encoding="UTF-8"?>\n'
            u'<!-- adb_Tool 应用图标源：车载中控屏 + 终端提示符 + 信号弧。\n'
            u'     与 adb_log_gui/adb_Tool.ico、顶栏/加载层内联 SVG 同源。\n'
            u'     100×100 坐标系：圆角方 r22 / 中控屏 (13,32)-(87,74) r10 /\n'
            u'     提示符线宽 5.8 / 信号弧 r9、r16 线宽 3 / 底座 (30,79)-(70,83.5) r2.25 -->\n'
            u'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="512" height="512">\n'
            u'  <defs>\n'
            u'    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">\n'
            u'      <stop offset="0" stop-color="#2E2E2E"/>\n'
            u'      <stop offset="1" stop-color="#050505"/>\n'
            u'    </linearGradient>\n'
            u'    <radialGradient id="hl" cx="0.26" cy="0.08" r="0.82">\n'
            u'      <stop offset="0" stop-color="#FFFFFF" stop-opacity="0.26"/>\n'
            u'      <stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/>\n'
            u'    </radialGradient>\n'
            u'  </defs>\n'
            u'  <rect x="2" y="2" width="96" height="96" rx="22" fill="url(#bg)"/>\n'
            u'  <rect x="2" y="2" width="96" height="96" rx="22" fill="url(#hl)"/>\n'
            u'  <rect x="13" y="32" width="74" height="42" rx="10" fill="#FFFFFF" fill-opacity="0.16"\n'
            u'        stroke="#FFFFFF" stroke-opacity="0.30" stroke-width="1.35"/>\n'
            u'  <g fill="none" stroke="#FFFFFF" stroke-width="5.8" stroke-linecap="round" stroke-linejoin="round">\n'
            u'    <path d="M33 46 L44 53 L33 60"/>\n'
            u'    <path d="M56 60 H67"/>\n'
            u'  </g>\n'
            u'  <g fill="none" stroke="#FFFFFF" stroke-opacity="0.55" stroke-width="3" stroke-linecap="round">\n'
            u'    <path d="M41 27 A9 9 0 0 1 59 27"/>\n'
            u'    <path d="M34 27 A16 16 0 0 1 66 27"/>\n'
            u'  </g>\n'
            u'  <rect x="30" y="79" width="40" height="4.5" rx="2.25" fill="#FFFFFF" fill-opacity="0.34"/>\n'
            u'</svg>\n')

with open(PREVIEW, 'wb') as f:
    f.write(preview_sheet(RAW))

cnt = struct.unpack('<H', ico[4:6])[0]
sys.stdout.write(u"ico: %d B / %d 档 %s / 首帧 PNG 签名=%s\n"
                 % (len(ico), cnt, SIZES, imgs[0][1][:4] == b'\x89PNG'))
sys.stdout.write(u"写出: %s\n      %s\n      %s\n      %s\n" % (ICO1, ICO2, SVG, PREVIEW))
