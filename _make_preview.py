# -*- coding: utf-8 -*-
"""A4 阶段 2 的组件状态墙：从 ui.html 抽出**真实 <style>** 嵌进非生产预览页。

不是手抄一份「看起来像」的 CSS —— 预览用的就是产品当前那一套令牌与八态规则。
产出：docs/COMPONENT-STATES.preview.html（标注非生产文件，不进任何成品包）
"""
import io
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
OUT = os.path.join(ROOT, "docs", "COMPONENT-STATES.preview.html")

with io.open(UI, "r", encoding="utf-8") as f:
    s = f.read()
style = s[s.index("<style>") + len("<style>"):s.index("</style>")]

STATES = [
    ("default", ""), ("hover", "is-hover"), ("focus-visible", "is-focus"),
    ("active", "is-active"), ("disabled", "is-disabled"),
    ("loading", "is-loading"), ("error", "is-error"), ("success", "is-success"),
]
VIEWS = ["loading", "empty", "error", "success", "disabled"]

COMPONENTS = [
    ("C-01 root 胶囊", '<span class="rootpill no">未 root</span>'),
    ("C-02 无线胶囊", '<span class="wadb-btn on">无线</span>'),
    ("C-03 日志等级徽章", '<span class="logpill" data-lv="W"><span class="lv">W</span></span>'),
    ("C-04 runchip", '<span class="runchip"><span>执行中 00:03</span></span>'),
    ("C-05 .tab 页签", '<button class="tab active">指令</button>'),
    ("C-06 .btn 主按钮", '<button class="btn primary">执行</button>'),
    ("C-07 .icon-btn", '<button class="icon-btn" title="主题">☾</button>'),
    ("C-09 quick-search", '<input class="qsearch-input" placeholder="搜索指令…">'),
    ("C-10 快捷卡片", '<div class="qcard"><div class="qt">一键截图</div></div>'),
    ("C-12 树节点", '<div class="fs-row dir"><span class="fs-arw">▸</span><span class="n">logcat</span></div>'),
    ("C-14 反馈表行", '<div class="fb-row"><span class="fb-meta">成功 · 12 ms</span></div>'),
    ("C-15 折叠栏", '<div class="fb-collapsed-bar">输出 · 3 条记录</div>'),
    ("C-19 弹层按钮", '<button class="btn ghost">取消</button>'),
    ("C-23 缩略条停止", '<button class="cast-thumb-stop" title="停止">×</button>'),
    ("C-24 搜索结果行", '<div class="fs-row" data-search="1"><span class="fs-arw">▸</span>report.docx</div>'),
]

parts = [
    u"<!DOCTYPE html>",
    u'<html lang="zh-CN" data-theme="dark">',
    u"<head><meta charset=\"utf-8\"><title>组件状态墙（非生产文件）</title>",
    u"<style>" + style + u"</style>",
    u"""<style>
  body{margin:0;padding:24px;font-family:var(--font-ui);background:var(--bg);color:var(--text);}
  h1{font-size:20px;margin:0 0 4px}h2{font-size:15px;margin:28px 0 10px}
  .note{color:var(--text-dim);font-size:12px;line-height:1.7;margin:0 0 18px}
  .warn{display:inline-block;padding:4px 10px;border:1px solid var(--err);
        color:var(--err);background:var(--err-soft);border-radius:6px;font-size:12px;margin-bottom:16px}
  table{border-collapse:collapse;width:100%;font-size:12px}
  th,td{border:1px solid var(--border);padding:8px;text-align:left;vertical-align:middle}
  th{background:var(--surface-2);color:var(--text-dim);font-weight:600;white-space:nowrap}
  td:first-child{white-space:nowrap;color:var(--text-dim)}
  .cell{min-height:44px;display:flex;align-items:center}
  .is-hover{filter:brightness(1.12)}
  .is-focus{outline:2px solid var(--accent);outline-offset:3px}
  .is-active{transform:scale(.97)}
  .is-disabled{opacity:.45;cursor:not-allowed;pointer-events:none}
  .is-loading{opacity:.7}
  .is-error{border-color:var(--err)!important;box-shadow:0 0 0 2px var(--err-soft)}
  .is-success{border-color:var(--ok)!important;box-shadow:0 0 0 2px var(--ok-soft)}
  .vstate{padding:10px;border:1px solid var(--border);border-radius:8px;background:var(--surface)}
  .vstate.err{color:var(--err)} .vstate.success{color:var(--ok)}
  .vstate.disabled{opacity:.45} .vstate.empty{color:var(--text-faint)}
  .themebar{position:sticky;top:0;z-index:5;background:var(--glass);padding:10px 0;margin-bottom:8px}
  .themebar button{margin-right:8px}
</style></head><body>""",
    u"<h1>adb_Tool · 组件状态墙</h1>",
    u'<div class="warn">非生产文件 · 仅用于审核，不进任何成品包</div>',
    u"""<p class="note">
  本页内嵌的是 <code>adb_log_gui/webview2/ui.html</code> 当前真实的 &lt;style&gt;，
  不是复刻版样式。切主题按钮改的是 <code>data-theme</code>，用于逐套核对三态。
  组件八态中 <code>hover / focus-visible / active / disabled / loading / error / success</code>
  由本页的 <code>.is-*</code> 类模拟（浏览器无法对同一个元素强制这些伪类），
  产品里对应的真实规则见 ui.html 的 Apple 覆盖层。
  生成：<code>python _make_preview.py</code>。
</p>""",
    u"""<div class="themebar">
  <button class="btn" onclick="document.documentElement.dataset.theme='dark'">dark</button>
  <button class="btn" onclick="document.documentElement.dataset.theme='light'">light</button>
  <button class="btn" onclick="document.documentElement.dataset.theme='eye'">eye</button>
</div>""",
    u"<h2>1. 组件八态（15 个代表组件 × 8 态）</h2>",
    u"<table><thead><tr><th>组件</th>" +
    u"".join(u"<th>%s</th>" % n for n, _ in STATES) + u"</tr></thead><tbody>",
]
for name, html in COMPONENTS:
    cells = []
    for _, cls in STATES:
        cells.append(u'<td><div class="cell %s">%s</div></td>' % (cls, html))
    parts.append(u"<tr><td>%s</td>%s</tr>" % (name, u"".join(cells)))
parts += [u"</tbody></table>", u"<h2>2. 视图五态</h2>",
          u"<table><thead><tr><th>状态</th><th>表现</th></tr></thead><tbody>"]
texts = {
    "loading": u"正在读取设备信息…", "empty": u"暂无记录",
    "error": u"读取失败：设备未连接，请检查 USB 调试",
    "success": u"已读取 9 项车机信息", "disabled": u"离线，功能不可用",
}
for v in VIEWS:
    parts.append(u'<tr><td>%s</td><td><div class="vstate %s">%s</div></td></tr>' %
                 (v, v, texts[v]))
parts += [u"</tbody></table>", u"</body></html>"]

with io.open(OUT, "w", encoding="utf-8", newline="") as f:
    f.write(u"\n".join(parts) + u"\n")
print("wrote %s (%d B, style %d B)" % (OUT, os.path.getsize(OUT), len(style)))
