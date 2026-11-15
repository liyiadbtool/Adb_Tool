# -*- coding: utf-8 -*-
"""A14 结构补丁：启动图标 / 标题栏图标 / 设置面板文案与字体大小行。幂等。"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")

# 与 adb_Tool.ico 同源的线稿：中控屏 + 提示符 >_ + 信号双弧 + 底座
ICON = (u'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" '
        u'stroke-linecap="round" stroke-linejoin="round">'
        u'<path d="M6.6 4.6a8 8 0 0 1 10.8 0"/>'
        u'<path d="M8.9 6.6a4.5 4.5 0 0 1 6.2 0"/>'
        u'<rect x="2.6" y="8" width="18.8" height="10.6" rx="2.9"/>'
        u'<path d="M7.3 11.8l2.9 2.1-2.9 2.1"/>'
        u'<path d="M12.5 16h3.3"/>'
        u'<path d="M9.1 20.9h5.8"/>'
        u'</svg>')

s = io.open(UI, encoding="utf-8").read()
n = 0


def sub(old, new, why):
    global s, n
    if old not in s:
        sys.stdout.write("  [SKIP] %s（锚点已变或已改）\n" % why)
        return
    if s.count(old) != 1:
        sys.exit("[FAIL] %s 锚点不唯一：%d" % (why, s.count(old)))
    s = s.replace(old, new, 1)
    n += 1
    sys.stdout.write("  [OK]   %s\n" % why)


# ---- 1. 启动动画图标（需求1）：换成与 ico 同源的最新图标 ----
sub(
    u'<svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.75" '
    u'stroke-linecap="round" stroke-linejoin="round"><g transform="scale(2)">'
    u'<rect x="2.9" y="7.1" width="18.2" height="11.2" rx="3.1"/>'
    u'<path d="M7.5 10.6l3.1 2.2-3.1 2.2"/><path d="M13.4 15h3.2"/></g></svg>',
    ICON,
    u"启动动画图标 → 最新中控屏图标")

# ---- 2. 标题栏 logo（需求3：太小）----
sub(
    u'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" '
    u'stroke-linecap="round" stroke-linejoin="round">'
    u'<rect x="2.9" y="7.1" width="18.2" height="11.2" rx="3.1"/>'
    u'<path d="M7.5 10.6l3.1 2.2-3.1 2.2"/><path d="M13.4 15h3.2"/></svg>',
    ICON,
    u"标题栏 logo 图标 → 同上（尺寸由 CSS 按 --tb-h 派生）")

# ---- 3. 字体预览文案去中文（需求6）----
sub(
    u'<div class="set-preview" id="set-font-preview">车载语音测试 · Adb_Tool 12345 ABCdef</div>',
    u'<div class="set-preview" id="set-font-preview">Adb_Tool 12345 ABCdef</div>',
    u"字体预览文案去掉中文前缀")

# ---- 4. 关于描述去中文（需求6）----
sub(
    u'<div class="set-about">adb_Tool · 车载语音与功能测试工具</div>',
    u'<div class="set-about">adb_Tool</div>',
    u"关于里的中文描述去掉")

# ---- 5. 字体大小行（需求8）----
sub(
    u'        <div class="set-preview" id="set-font-preview">Adb_Tool 12345 ABCdef</div>\n'
    u'      </section>',
    u'        <div class="set-preview" id="set-font-preview">Adb_Tool 12345 ABCdef</div>\n'
    u'\n'
    u'        <!-- A14：字体大小（小/中/大）—— 用 WebView2 缩放整页等比放大，\n'
    u'             按钮由 _v14.js 的 buildSizeSeg() 建，避免 html 里写三段重复标记 -->\n'
    u'        <div class="set-fsize-row">\n'
    u'          <div class="set-h">字体大小 <span class="set-sub">整页跟随缩放，含标题栏与输出区</span></div>\n'
    u'          <div class="set-seg" id="set-fsize"></div>\n'
    u'          <div class="set-fsize-hint">改完立即生效，下次启动保持（小 90% / 中 100% / 大 115%）。</div>\n'
    u'        </div>\n'
    u'      </section>',
    u"字体区块新增「字体大小」分段控件")

io.open(UI, "w", encoding="utf-8", newline="").write(s)
sys.stdout.write("A14 结构补丁完成：%d 处，%.1f KB\n" % (n, len(s) / 1024.0))
