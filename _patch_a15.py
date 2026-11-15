# -*- coding: utf-8 -*-
"""A15 结构补丁：13 色色板 / 显示选项区 / 投屏（scrcpy）指令组。可反复跑（幂等）。

只动这三块，不碰既有 id / onclick / data-tab / kind。
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")

ORDER = ["blue", "cyan", "teal", "mint", "green", "yellow",
         "orange", "red", "pink", "purple", "indigo", "brown", "graphite"]
CN = {"blue": "蓝", "cyan": "青", "teal": "蓝绿", "mint": "薄荷",
      "green": "绿", "yellow": "黄", "orange": "橙", "red": "红",
      "pink": "粉", "purple": "紫", "indigo": "靛", "brown": "棕",
      "graphite": "石墨"}
SWATCH = {"blue": "#0A84FF", "cyan": "#64D2FF", "teal": "#40C8E0",
          "mint": "#63E6E2", "green": "#30D158", "yellow": "#FFD60A",
          "orange": "#FF9F0A", "red": "#FF453A", "pink": "#FF375F",
          "purple": "#BF5AF2", "indigo": "#5E5CE6", "brown": "#AC8E68",
          "graphite": "#AEAEB2"}


def dots():
    out = []
    for k in ORDER:
        sel = ' sel' if k == 'blue' else ''
        out.append('        <button class="accent-dot%s" data-accent="%s" '
                   'style="--dot:%s" title="%s" aria-label="%s色">%s</button>'
                   % (sel, k, SWATCH[k], CN[k], CN[k], CN[k]))
    return "\n".join(out)


DOTS = dots()

SCRS = u"""  // A15：投屏（scrcpy）—— 用户给的 6 个 display-id 固定映射。
  // 走内置 :scrcpy N，由 C# 拉起本地 scrcpy 进程（外部窗口），不是 adb 命令，
  // 所以不能写进 cmds.ini（那里只能发 adb 参数）。
  { name:'投屏（scrcpy）', color:'var(--accent)', items:[
    {name:'主屏投屏',    desc:'scrcpy --display-id 0（中控主屏）',  cmd:':scrcpy 0',  cat:'前排'},
    {name:'副屏投屏',    desc:'scrcpy --display-id 4（副驾屏）',    cmd:':scrcpy 4',  cat:'前排'},
    {name:'后排屏投屏',  desc:'scrcpy --display-id 1（后排屏）',    cmd:':scrcpy 1',  cat:'后排'},
    {name:'HUD 投屏',    desc:'scrcpy --display-id 3（HUD）',       cmd:':scrcpy 3',  cat:'抬头显示'},
    {name:'PHUD-B 投屏', desc:'scrcpy --display-id 9（PHUD-B）',    cmd:':scrcpy 9',  cat:'抬头显示'},
    {name:'PHUD-C 投屏', desc:'scrcpy --display-id 10（PHUD-C）',   cmd:':scrcpy 10', cat:'抬头显示'}
  ]},
"""

DISPLAY_SEC = u"""
      <!-- A15：显示选项（跟随系统 / 深黑 / 护眼强度）。内容由 _v15.js 填。 -->
      <section class="set-sec" id="a15-sec-display">
        <div class="set-h">显示 <span class="set-sub">跟随系统 · 深黑 · 护眼强度</span></div>
        <div class="set-seg" id="set-auto"></div>
        <div class="set-seg" id="set-oled"></div>
        <div class="set-seg" id="set-eyelevel"></div>
        <div class="set-fsize-hint" id="set-display-hint"></div>
      </section>
"""


def main():
    s = io.open(UI, encoding="utf-8").read()
    changed = []

    # ---- 1. 色板 9 → 13 ----
    pat = re.compile(r'(<span class="accent-pop-label">.*?</span>\n)(.*?)(\n      </div>\n      </section>)', re.S)
    m = pat.search(s)
    if not m:
        sys.exit("[FAIL] 找不到 accent-pop 色板块")
    s = s[:m.start(2)] + "<!-- A15:DOTS -->\n" + DOTS + s[m.end(2):]
    changed.append("色板 13 色")

    # ---- 2. 显示选项区（插在主题 section 之后，只插一次）----
    if "a15-sec-display" not in s:
        anchor = '<div class="set-seg" id="set-theme"></div>\n      </section>\n'
        if anchor not in s:
            sys.exit("[FAIL] 找不到主题 section 锚点")
        s = s.replace(anchor, anchor + DISPLAY_SEC, 1)
        changed.append("显示选项区")

    # ---- 3. 投屏指令组（放在网联服务组之后，只插一次）----
    if "投屏（scrcpy）" not in s:
        anchor2 = "  // 方控按键：独立分组（用户要求\"方控独立的页面\"）。"
        if anchor2 not in s:
            sys.exit("[FAIL] 找不到方控按键锚点")
        s = s.replace(anchor2, SCRS + anchor2, 1)
        changed.append("投屏指令组 6 条")

    io.open(UI, "w", encoding="utf-8", newline="").write(s)
    print("结构补丁完成：%s" % "、".join(changed))


if __name__ == "__main__":
    main()
