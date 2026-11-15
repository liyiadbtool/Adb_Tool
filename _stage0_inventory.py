# -*- coding: utf-8 -*-
"""阶段 0（只读）：生成功能不变量快照 + 盘点统计。不改 ui.html。"""
import io, os, re, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
DOCS = os.path.join(ROOT, "docs")

with io.open(UI, "r", encoding="utf-8") as f:
    s = f.read()

style_s = s.index("<style>")
style_e = s.index("</style>")
css = s[style_s:style_e]
js = s[style_e:]

kinds = sorted(set(re.findall(r"case\s+'([a-zA-Z]+)'\s*:", js)))
onclicks = sorted(set(re.findall(r'onclick="([A-Za-z_$][\w$]*)\s*\(', s)))
ids = sorted(set(re.findall(r'\sid="([A-Za-z][\w-]*)"', s)))
tabs = re.findall(r'data-tab="([^"]+)"', s)
pages = re.findall(r'id="(page-[\w-]+)"', s)
theme_order = re.search(r"var THEME_ORDER\s*=\s*\[([^\]]+)\]", js)
theme_icons = re.findall(r"^\s*(dark|light|eye)\s*:", js, re.M)
hexes = re.findall(r"#[0-9a-fA-F]{3,8}\b", css)
hex_c = {}
for h in hexes:
    hex_c[h.lower()] = hex_c.get(h.lower(), 0) + 1
svg_count = len(re.findall(r"<svg", s))
svg_hard = re.findall(r'(?:stroke|fill)="(#[0-9a-fA-F]{3,8})"', s)

lines = [
    u"# FUNCTION-INVARIANTS · 功能不变量快照（阶段 0 基线）",
    u"",
    u"> 生成：2026-11-15；源：`adb_log_gui/webview2/ui.html`（%d 行 / %d B）" % (s.count("\n") + 1, len(s.encode("utf-8"))),
    u"> 用途：Apple UI 换肤期间作为 diff 基线。**本文件列出的任何一项都不允许改动。**",
    u"> 说明：附带 md（`adb_Tool-Apple-UI替换-提示词与Skill组合.md`）的盘点是旧版快照，",
    u"> 以本文件与当前源码为准。差异见 `UI-RESKIN-INVENTORY.md`。",
    u"",
    u"## 1. 消息协议（onMessage 的 case）",
    u"",
    u"共 %d 个：`%s`" % (len(kinds), u"` `".join(kinds)),
    u"",
    u"## 2. onclick 绑定的函数（%d 个）" % len(onclicks),
    u"",
    u"`" + u"` `".join(onclicks) + u"`",
    u"",
    u"## 3. 静态 DOM id（%d 个）" % len(ids),
    u"",
    u"`" + u"` `".join(ids) + u"`",
    u"",
    u"## 4. 页签与页面",
    u"",
    u"- data-tab: `%s`" % "`, `".join(tabs),
    u"- #page-*: `%s`" % "`, `".join(pages),
    u"- THEME_ORDER: `%s`" % (theme_order.group(1).strip() if theme_order else u"未找到"),
    u"- THEME_TITLE / THEME_ICON 的 key: `%s`" % "`, `".join(sorted(set(theme_icons))[:6]),
    u"",
    u"## 5. 冻结的其它项",
    u"",
    u"- `post(kind,data,src,slot)` / `postObj(o)` / `ready()` 的 `{kind:'ready'}`",
    u"- `window.chrome.webview.postMessage` / `postMessageWithAdditionalObjects('fileDrop',[files[0]])`",
    u"- `sendCmd` / `switchTab` / `applyTheme` / `toggleTheme` / `castToggle` / `castTap` 等函数体",
    u"- `:h` / `:shot` / `:front` / `:car` / `:sid` 等命令串、`cmds.ini` 全部 `[cmd.*]` 段",
    u"- 快捷键 Ctrl+K / Ctrl+1..4 / Alt+↓ / ↑↓ 历史 / Enter / Esc",
    u"- 行为常量：最多 3 槽、输出 12 段、34px 折叠栏、树 500 项分页、400ms 完成态、",
    u"  8 秒加载兜底、CAST_SLOTS=6、`/live/<i>` 流端口与 multipart 协议",
    u"- `adb_log_export.ini` 的 `theme=` 持久化、`GuiWeb.cs` 的 ShowIcon / ApplyDarkTitleBar / TrySetCatIcon",
    u"",
    u"## 6. 表现层基线（允许改，改完需复核）",
    u"",
    u"- `<style>` 段：第 %d–%d 行" % (s[:style_s].count("\n") + 1, s[:style_e].count("\n") + 1),
    u"- CSS 硬编码色值：%d 处 / %d 个不同值" % (len(hexes), len(hex_c)),
    u"- 高频硬编码色：%s" % ", ".join(u"%s×%d" % (k, v) for k, v in sorted(hex_c.items(), key=lambda x: -x[1])[:12]),
    u"- 内联 `<svg>`：%d 处；其中带硬编码 stroke/fill 的色值：%s" % (svg_count, ", ".join(sorted(set(svg_hard))) or u"无"),
    u"",
    u"## 7. 本轮新增（不属于冻结项，属用户明确要求）",
    u"",
    u"- 底部缩略条：改单帧短连接（新增 `/snap/<slot>` 端点），并补每路「停止」按钮",
    u"- 文件搜索结果：去掉「进入 ⤵」按钮，点击行即展开进入树状结构",
    u"",
]

out = os.path.join(DOCS, "FUNCTION-INVARIANTS.md")
with io.open(out, "w", encoding="utf-8", newline="") as f:
    f.write(u"\n".join(lines) + u"\n")

sys.stdout.write("kinds=%d onclicks=%d ids=%d tabs=%s pages=%s\n" %
                 (len(kinds), len(onclicks), len(ids), tabs, pages))
sys.stdout.write("css_hex=%d unique=%d svg=%d svg_hard=%s\n" %
                 (len(hexes), len(hex_c), svg_count, sorted(set(svg_hard))))
sys.stdout.write("top_hex=%s\n" % sorted(hex_c.items(), key=lambda x: -x[1])[:12])
sys.stdout.write("wrote %s\n" % out)
