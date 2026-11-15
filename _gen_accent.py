# -*- coding: utf-8 -*-
"""生成 16 色强调色 × 3 套明暗的语义令牌覆盖层（Apple 系统色板 + WCAG 自动校验）。

产物直接写回 ui.html 的 <style> 末尾，用 ACCENT LAYER 标记包裹，可重复执行。

A17 变更（相对 A9 的 9 色）：
  · 按 Apple system* 语义色扩到 13 色，补 cyan / teal / mint / indigo / brown。
  · A16 再加三白（纯白 / 护眼白 / 玻璃白），共 16 色。
  · 「白」「黑」合并成 graphite（石墨）—— 原来 white 在深色是 #F5F5F7、浅色
    变 #8E8E93，同一个名字两副面孔，用户点白色色点在浅色下得到灰色，很反直觉。
    graphite 才是 Apple 的中性强调色。老偏好里的 white/black 由前端迁移到 graphite。
  · --on-accent 不再手写：按亮度自动在「白字 / 近黑字」里选对比度更高的那个。
    27 条手工值里已经出现不一致（浅色 red 用深字、blue 用白字），39 条更容易填错。
  · 色板 9 → 13 个点，改 5 列布局。

规则（沿用）：
  - 每个 --accent 同时满足：对表面 ≥3:1（非文本）、对 --on-accent ≥4.5:1（文本）。
  - 组件只引用 --accent / --accent-soft / --on-accent，不出现硬编码色。
"""
import colorsys
import io
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
OUT_TXT = os.path.join(ROOT, "docs", "ACCENT-CONTRAST.md")

# 顺序按色相环排（冷 → 暖 → 中性），色板从左到右读起来是一条光谱
ORDER = ["blue", "cyan", "teal", "mint", "green", "yellow",
         "orange", "red", "pink", "purple", "indigo", "brown", "graphite",
         "purewhite", "eyewhite", "glasswhite"]
CN = {"blue": "蓝", "cyan": "青", "teal": "蓝绿", "mint": "薄荷",
      "green": "绿", "yellow": "黄", "orange": "橙", "red": "红",
      "pink": "粉", "purple": "紫", "indigo": "靛", "brown": "棕",
      "graphite": "石墨", "purewhite": "纯白", "eyewhite": "护眼白",
      "glasswhite": "玻璃白"}

# Apple 官方 system* 色（sRGB 近似）：light / dark
APPLE = {
    "blue":     ("#007AFF", "#0A84FF"),
    "cyan":     ("#32ADE6", "#64D2FF"),
    "teal":     ("#30B0C7", "#40C8E0"),
    "mint":     ("#00C7BE", "#63E6E2"),
    "green":    ("#34C759", "#30D158"),
    "yellow":   ("#FFCC00", "#FFD60A"),
    "orange":   ("#FF9500", "#FF9F0A"),
    "red":      ("#FF3B30", "#FF453A"),
    "pink":     ("#FF2D55", "#FF375F"),
    "purple":   ("#AF52DE", "#BF5AF2"),
    "indigo":   ("#5856D6", "#5E5CE6"),
    "brown":    ("#A2845E", "#AC8E68"),
    "graphite": ("#8E8E93", "#AEAEB2"),
    # A16：用户要的三种白。深色下就是白本身；浅色 / 护眼下由 adapt() 压到
    # "刚好 3:1" 的银灰 —— 白色对白底是 1:1，不压就不是颜色了。
    # 三个起点亮度略不同，压完之后自然分成三档灰，用户仍能分辨。
    # A19（修复）：深色主题下三白统一改成"接近纯白的中性灰白"，去掉冷/暖调。
    #   原 glasswhite #E9E9EE 带冷蓝灰调，画在深色 #appmark-bg 上视觉显蓝，
    #   是"加载动画图标显蓝"的元凶。改中性灰白后不再偏蓝。
    "purewhite": ("#FFFFFF", "#F2F2F2"),
    "eyewhite":  ("#F5F5F5", "#F0F0F0"),
    "glasswhite": ("#E6E6E6", "#E6E6E6"),
}
# 三套明暗的表面色（与 ui.html :root 定义一致）
SURFACE = {"dark": ("#1c1c1e", "#ffffff", "#1d1d1f"),
           "light": ("#ffffff", "#ffffff", "#1d1d1f"),
           "eye":   ("#fffdf7", "#fffdf7", "#3b352c")}
# 色板展示用固定识别色（不随主题变，用户才能稳定辨认 13 个选项）
SWATCH = {"blue": "#0A84FF", "cyan": "#64D2FF", "teal": "#40C8E0",
          "mint": "#63E6E2", "green": "#30D158", "yellow": "#FFD60A",
          "orange": "#FF9F0A", "red": "#FF453A", "pink": "#FF375F",
          "purple": "#BF5AF2", "indigo": "#5E5CE6", "brown": "#AC8E68",
          "graphite": "#AEAEB2",
          "purewhite": "#F2F2F2", "eyewhite": "#F0F0F0", "glasswhite": "#E6E6E6"}


def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def hexs(t):
    return "#%02X%02X%02X" % tuple(max(0, min(255, int(round(c)))) for c in t)


def lum(h):
    def f(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb(h)
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ratio(a, b):
    l1, l2 = sorted([lum(a), lum(b)], reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def shift(h, dl):
    r, g, b = [c / 255.0 for c in rgb(h)]
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
    ll = max(0.0, min(1.0, ll + dl))
    r, g, b = colorsys.hls_to_rgb(hh, ll, ss)
    return hexs((r * 255, g * 255, b * 255))


def desat(h, k):
    r, g, b = [c / 255.0 for c in rgb(h)]
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
    r, g, b = colorsys.hls_to_rgb(hh, ll, ss * k)
    return hexs((r * 255, g * 255, b * 255))


# 这三个是"白"而不是"彩"：压暗时必须先去色，否则那点暖/冷调会被放大成
# 土黄 / 紫灰（实测 #FFFDF5 压到 3:1 变成了 #B48800，完全不是白）。
# 三个"白"在浅色 / 护眼下必须先落到一个中性色相再压暗：
#   直接用白色压暗，那点 1% 的暖/冷调会被放大成土黄 / 玫瑰灰（实测 #FFFDF5 → #AA8E8E）。
# 所以给定 (色相, 饱和度)，在 L=0.62 处起算，再由循环压到刚好 3:1（护眼 4.5:1）。
# 深色主题不参与这一步 —— 那里就是本来的白。
NEUTRAL = {"purewhite": (0, 0.0), "eyewhite": (42, 0.10), "glasswhite": (220, 0.08)}


def setsat(h, k):
    r, g, b = [c / 255.0 for c in rgb(h)]
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
    r, g, b = colorsys.hls_to_rgb(hh, ll, k)
    return hexs((r * 255, g * 255, b * 255))


def adapt(base, theme, name):
    """返回 (accent, on-accent, 对表面对比度, 文字对比度, 调整说明)"""
    surface, on_light, on_dark = SURFACE[theme]
    note = ""
    if name in NEUTRAL and theme != "dark":
        hue, sat = NEUTRAL[name]
        if sat <= 0:
            base = "#FFFFFF"                       # 纯白：正灰，无色相
        else:
            rr, gg, bb = colorsys.hls_to_rgb(hue / 360.0, 0.62, sat)
            base = hexs((rr * 255, gg * 255, bb * 255))
    # 护眼底偏暖：轻微降饱和，避免高饱和色在暖白上刺眼
    if theme == "eye":
        base = desat(base, 0.82)
        note = "护眼降饱和"

    def best_on(c):
        a, b = on_light, on_dark
        return (a, ratio(c, a)) if ratio(c, a) >= ratio(c, b) else (b, ratio(c, b))

    c = base
    # 单循环同时满足两个约束，避免「先修 3:1 再修 4.5:1」把前一个破坏掉。
    # 浅底一律压暗（同时提高对白底的 3:1 与白字 4.5:1）；深底一律提亮（同理）。
    dl = -0.015 if lum(surface) > 0.4 else 0.015
    moved = 0
    for _ in range(120):
        on, cr = best_on(c)
        rb = ratio(c, surface)
        if rb >= 3.0 and cr >= 4.5:
            break
        c = shift(c, dl)
        moved += 1
    on, cr = best_on(c)
    if moved and not note:
        note = "压暗 / 提亮 %d 档" % moved
    elif moved:
        note += " · 调 %d 档" % moved
    return c, on, ratio(c, surface), cr, note


def build():
    css, report = [], []
    report += [
        "# 强调色（accent）16 色 × 3 套明暗 · Apple 语义色与对比度核验",
        "",
        "> 生成：`python _gen_accent.py`。色值取自 Apple `system*` 明暗配对；",
        "> `--on-accent` 按亮度自动选「白字 / 近黑字」中对比度更高的一个；",
        "> 所有 `--accent` 自动满足「对表面 ≥3:1」与「其上文字 ≥4.5:1」(WCAG 2.2 AA)。",
        "> 组件只引用 `--accent` / `--accent-soft` / `--on-accent`，不写死颜色。",
        "",
        "| 颜色 | 主题 | --accent | --on-accent | 对表面 | 文字 | 调整 |",
        "|---|---|---|---|---:|---:|---|",
    ]
    for th in ["dark", "light", "eye"]:
        for name in ORDER:
            base = APPLE[name][0 if th != "dark" else 1]
            acc, on, r_bg, r_tx, note = adapt(base, th, name)
            alpha = ".16" if th == "dark" else ".10"
            r, g, b = rgb(acc)
            soft = "rgba(%d,%d,%d,%s)" % (r, g, b, alpha)
            sel = ':root[data-theme="%s"][data-accent="%s"]' % (th, name)
            css.append("%s{ --accent:%s; --accent-soft:%s; --on-accent:%s; }" %
                       (sel, acc, soft, on))
            report.append("| %s | %s | `%s` | `%s` | %.2f:1 | %.2f:1 | %s |" %
                          (CN[name], th, acc, on, r_bg, r_tx, note or "—"))
        css.append("")
    return "\n".join(css), "\n".join(report) + "\n"


ACCENT_CSS, CONTRAST_MD = build()

# ---- 视觉增强（只改 <style>，不动 DOM / JS / id / onclick / kind）----
VISUAL = r"""
/* ---- 强调色切换器（顶栏 chrome + 设置面板共用一份）---- */
.accent-pick{position:relative;display:inline-flex;flex:0 0 auto;}
.accent-btn{position:relative;}
.accent-btn .acur{
  position:absolute;right:5px;bottom:5px;width:8px;height:8px;border-radius:50%;
  background:var(--accent);box-shadow:0 0 0 2px var(--surface);
}
.accent-pop{
  position:absolute;right:0;top:calc(100% + 8px);z-index:90;
  display:grid;grid-template-columns:repeat(4,40px);gap:8px;
  padding:12px;border:1px solid var(--border-strong);border-radius:var(--r-md);
  background:var(--glass);
  -webkit-backdrop-filter:blur(20px) saturate(180%);
  backdrop-filter:blur(20px) saturate(180%);
  box-shadow:var(--shadow-lg);
  animation:apple-in var(--dur) var(--ease) both;
}
.accent-dot{
  width:40px;height:40px;border-radius:50%;cursor:pointer;
  border:1px solid var(--border-strong);background:var(--dot);
  display:flex;align-items:center;justify-content:center;
  font-size:0;color:transparent;
  transition:transform var(--dur-fast) var(--ease),box-shadow var(--dur-fast) var(--ease);
  position:relative;
}
/* 浅色系色点（黄/薄荷/青/石墨）在任何底色上都要有可见轮廓 */
.accent-dot[data-accent="yellow"],.accent-dot[data-accent="mint"],
.accent-dot[data-accent="cyan"],.accent-dot[data-accent="graphite"],
.accent-dot[data-accent="purewhite"],.accent-dot[data-accent="eyewhite"],
.accent-dot[data-accent="glasswhite"]{
  box-shadow:inset 0 0 0 1px var(--swatch-ring);
}
@media (hover:hover){ .accent-dot:hover{transform:scale(1.08);} }
.accent-dot:active{transform:scale(.94);}
.accent-dot:focus-visible{outline:2px solid var(--accent);outline-offset:3px;}
/* 选中态：外圈 + 勾，不靠加粗描边（浅色下看不出来） */
.accent-dot.sel{
  box-shadow:0 0 0 2px var(--surface),0 0 0 4px var(--accent);
}
.accent-dot.sel::after{
  content:"";
  position:absolute;left:50%;top:50%;
  width:9px;height:5px;margin:-4px 0 0 -5px;
  border-left:2px solid var(--on-accent);border-bottom:2px solid var(--on-accent);
  transform:rotate(-45deg);
  filter:drop-shadow(0 0 1px var(--swatch-check-shadow));
}
.accent-pop-label{
  grid-column:1 / -1;font-size:11px;color:var(--text-faint);
  padding:0 2px 2px;letter-spacing:.3px;
}
@media (prefers-reduced-transparency:reduce){
  .accent-pop{-webkit-backdrop-filter:none;backdrop-filter:none;background:var(--surface);}
}
"""

# ---- 让「整体看下来有变化」的 Apple 化增强，全部基于语义令牌 ----
ENHANCE = r"""
/* ---- Apple 化增强：层级 / 分段控件 / 实心主按钮 / 卡片抬升 ---- */
.topbar{height:56px;gap:12px;padding:0 20px;}
.tabs{
  height:56px;gap:0;padding:0 20px;
  background:var(--surface);
}
.tabs .tab{
  height:36px;padding:0 20px;border:1px solid transparent;border-radius:var(--r-pill);
  background:transparent;color:var(--text-dim);font-weight:500;
}
.tabs .tab + .tab{margin-left:6px;}
.tabs .tab.active{
  background:var(--accent);border-color:var(--accent);color:var(--on-accent);
  font-weight:600;box-shadow:var(--shadow-sm);
}
@media (hover:hover){
  .tabs .tab:hover:not(.active){background:var(--accent-soft);color:var(--accent);}
}
.btn.primary{
  background:var(--accent);border-color:var(--accent);color:var(--on-accent);font-weight:600;
  box-shadow:var(--shadow-sm);
}
@media (hover:hover){
  .btn.primary:hover:not(:disabled){filter:brightness(1.08);border-color:var(--accent);}
}
.qcard{
  border-radius:var(--r-md);box-shadow:var(--shadow-sm);
  padding:14px 16px;background:var(--surface);
}
@media (hover:hover){
  .qcard:hover{border-color:var(--accent);box-shadow:var(--shadow-md);transform:translateY(-1px);}
}
.qcard .qname{font-weight:600;letter-spacing:.1px;}
.qcat{font-size:11px;letter-spacing:1.1px;text-transform:uppercase;}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;}
.fs-row.sel,.quick-nav .qnav.sel{
  background:var(--accent-soft);color:var(--accent);
}
input[type=range]{accent-color:var(--accent);}
input[type=radio],input[type=checkbox]{accent-color:var(--accent);}
"""

LAYER = ("\n/* === ACCENT LAYER START === */\n"
         "/* 生成：python _gen_accent.py · 13 色强调色 × dark/light/eye 语义令牌，"
         "WCAG 对比度自动校验，勿手改本段 */\n"
         + ACCENT_CSS + VISUAL + ENHANCE +
         "/* === ACCENT LAYER END === */\n")


def main():
    s = io.open(UI, "r", encoding="utf-8").read()
    pat = re.compile(r"\n/\* === ACCENT LAYER START === \*/.*?/\* === ACCENT LAYER END === \*/\n", re.S)
    if pat.search(s):
        s = pat.sub(LAYER, s, count=1)
        act = "替换"
    else:
        s = s.replace("</style>", LAYER + "</style>", 1)
        act = "插入"
    io.open(UI, "w", encoding="utf-8", newline="").write(s)
    io.open(OUT_TXT, "w", encoding="utf-8", newline="").write(CONTRAST_MD)
    print("OK %s CSS 覆盖层；%d 条主题×色规则；对比度表 -> docs/ACCENT-CONTRAST.md" %
          (act, len(ORDER) * 3))


if __name__ == "__main__":
    main()
