# -*- coding: utf-8 -*-
"""A13 轮 ui.html 结构补丁（幂等）。

做五件事：
  1) 标题栏重组：删品牌文字 / 四点收进 #tb-status / 齿轮与运行指示并入右侧 /
     整个 .topbar 删除（页签直接贴标题栏）
  2) 日志胶囊里补一个圆点（原来只有文字，没有点）
  3) 侧栏「指令」小标题删除
  4) 终端 input -> textarea（多行），四个按钮去中文只留 icon
  5) 输出区表头加「点击空白收起」热区与提示
  6) 帮助文档同步（顶栏胶囊 -> 四圆点；删掉"拖到边缘可分屏"这句不实描述）

已经打过就直接跳过（靠 V13:TITLEBAR 标记判断）。
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")

s = io.open(UI, encoding="utf-8").read()
if u"<!-- V13:TITLEBAR START -->" in s:
    sys.stdout.write("[skip] 已是 A13 结构，跳过\n")
    sys.exit(0)


def cut(src, start_mark, end_mark, what):
    """返回 [start_mark, end_mark) 之间的文本（含 start_mark，不含 end_mark）。"""
    i = src.find(start_mark)
    if i < 0:
        raise SystemExit("[FAIL] 找不到起点：" + what)
    j = src.find(end_mark, i)
    if j < 0:
        raise SystemExit("[FAIL] 找不到终点：" + what)
    return src[i:j]


# ---------- 切出要保留的碎片 ----------
titlebar_blk = cut(s, u'  <div class="titlebar" id="titlebar">', u'  <div class="topbar">',
                   u"标题栏块")
topbar_blk = cut(s, u'  <div class="topbar">', u'\n\n  <!-- 页签：座椅按钮样式 -->',
                 u"顶栏块")

tb_logo = cut(titlebar_blk, u'      <span class="tb-logo"', u'      <span class="tb-name">',
              u"logo")
tb_btns = cut(titlebar_blk, u'    <div class="tb-btns">',
              u'\n  </div>\n  <!-- V12:TITLEBAR END -->', u"窗口按钮组").rstrip() + u'\n'

root_pill = cut(topbar_blk, u'    <!-- root 指示按钮', u'    <!-- 无线 adb：ROOT 右边', u"root 胶囊")
wadb_blk = cut(topbar_blk, u'    <!-- 无线 adb：ROOT 右边', u'    <!-- 需求7：设备日志等级徽章', u"无线块")
log_pill = cut(topbar_blk, u'    <!-- 需求7：设备日志等级徽章', u'    <div class="device" id="dev-badge">', u"日志胶囊")
dev_badge = cut(topbar_blk, u'    <div class="device" id="dev-badge">', u'    <div class="spacer"></div>', u"设备徽章")
runchip = cut(topbar_blk, u'    <!-- 运行指示：点击停止', u'    <span class="tb-sep"></span>', u"运行指示")
set_btn = cut(topbar_blk, u'    <!-- 设置入口（2026-11-15）', u'\n  </div>',
              u"设置按钮").rstrip() + u'\n'

# 日志胶囊补一个圆点（现在只有 .ltag / .lv 两段文字，没有点）
if u'id="log-dot"' not in log_pill:
    log_pill = log_pill.replace(
        u'<span class="ltag">日志</span><span class="lv" id="log-lv"></span>',
        u'<span class="ltag">日志</span><span class="lv" id="log-lv"></span>'
        u'<span class="dot" id="log-dot"></span>', 1)

NEW_TITLEBAR = (
    u'  <!-- V13:TITLEBAR START -->\n'
    u'  <!-- 自绘标题栏（A13）：品牌文字已删，左侧只留 logo + 四个状态圆点；\n'
    u'       齿轮与运行指示并入右侧；原来独立的 .topbar 整行删除，页签直接贴标题栏。 -->\n'
    u'  <div class="titlebar" id="titlebar">\n'
    u'    <div class="tb-drag" onmousedown="tbDrag(event)" ondblclick="tbMax()">\n'
    + tb_logo +
    u'      <span class="tb-sub" id="tb-sub"></span>\n'
    u'    </div>\n'
    u'\n'
    u'    <!-- 四个状态圆点：只画点不写字，语义靠 hover 即时 tooltip（见 _v13.js） -->\n'
    u'    <div class="tb-status" id="tb-status">\n'
    + root_pill +
    wadb_blk +
    log_pill +
    dev_badge +
    u'    </div>\n'
    u'\n'
    u'    <!-- 主要拖拽区：圆点右侧到运行指示之间的整段空白 -->\n'
    u'    <div class="tb-drag tb-drag-mid" onmousedown="tbDrag(event)" ondblclick="tbMax()"></div>\n'
    u'\n'
    u'    <div class="tb-right">\n'
    + runchip +
    u'      <span class="tb-sep"></span>\n'
    + set_btn +
    u'    </div>\n'
    u'\n'
    + tb_btns +
    u'  </div>\n'
    u'  <!-- V13:TITLEBAR END -->\n'
)

# ---------- 1) 用新标题栏替换 [旧标题栏 + 旧顶栏] ----------
i = s.find(u'  <!-- V12:TITLEBAR START -->')
j = s.find(u'\n\n  <!-- 页签：座椅按钮样式 -->', i)
assert i > 0 and j > i, "标题栏/顶栏边界定位失败"
s = s[:i] + NEW_TITLEBAR + s[j + 2:]
sys.stdout.write("  [OK] 标题栏重组 + 顶栏删除\n")

# ---------- 3) 侧栏「指令」小标题 ----------
OLD_QNAV = u"""  var html = '<div class="qnav-title">指令</div>';"""
if OLD_QNAV in s:
    s = s.replace(OLD_QNAV, u"""  // A13：侧栏顶部的小标题「指令」已删（用户要求），导航直接贴顶
  var html = '';""", 1)
    sys.stdout.write("  [OK] 侧栏「指令」标题删除\n")

# ---------- 4) 终端输入区 ----------
OLD_INPUT = (u"""    +     '<input id="cmd-input-' + n + '" placeholder="输入指令，回车执行" """
             u"""oninput="updateCopyBtn(' + n + ')" onkeydown="onInputKey(event,' + n + ')">'""")
NEW_INPUT = (u"""    // A13：单行 input 换成 textarea —— Shift+Enter 换行，Enter 逐行顺序执行\n"""
             u"""    +     '<textarea id="cmd-input-' + n + '" rows="1" spellcheck="false" """
             u"""placeholder="输入指令，回车执行；Shift+回车换行（多行按顺序逐条执行）" """
             u"""oninput="updateCopyBtn(' + n + ');txAutoGrow(' + n + ')" """
             u"""onkeydown="onInputKey(event,' + n + ')"></textarea>'""")
if OLD_INPUT in s:
    s = s.replace(OLD_INPUT, NEW_INPUT, 1)
    sys.stdout.write("  [OK] 终端输入改 textarea\n")
else:
    raise SystemExit("[FAIL] 终端 input 锚点未命中")

OLD_BTNS = (
    u"""    +   '<button class="btn primary" id="btn-run-' + n + '" onclick="run(' + n + ')">' + _ICON_RUN + '执行</button>'\n"""
    u"""    +   '<button class="btn" id="btn-stop-' + n + '" onclick="stop(' + n + ')" disabled>' + _ICON_STOP + '停止</button>'\n"""
    u"""    +   '<button class="btn ghost" onclick="clearLog(' + n + ')">' + _ICON_CLEAR + '清屏</button>'\n"""
    u"""    +   '<button class="btn ghost" id="btn-copy-' + n + '" onclick="copyCmd(' + n + ')" title="复制选中内容；没有选中时复制本槽最近一条输出">' + _ICON_COPY + '复制</button>'\n"""
)
NEW_BTNS = (
    u"""    // A13：四个按钮去掉中文只留 icon，省下的宽度全给输入框。\n"""
    u"""    // 纯图标必须带 title + aria-label，否则没法辨认、读屏也读不出。\n"""
    u"""    +   '<button class="btn primary" id="btn-run-' + n + '" onclick="run(' + n + ')" title="执行（Enter）" aria-label="执行">' + _ICON_RUN + '</button>'\n"""
    u"""    +   '<button class="btn" id="btn-stop-' + n + '" onclick="stop(' + n + ')" disabled title="停止（Esc）" aria-label="停止">' + _ICON_STOP + '</button>'\n"""
    u"""    +   '<button class="btn ghost" onclick="clearLog(' + n + ')" title="清屏" aria-label="清屏">' + _ICON_CLEAR + '</button>'\n"""
    u"""    +   '<button class="btn ghost" id="btn-copy-' + n + '" onclick="copyCmd(' + n + ')" title="复制：有选中复制选中，否则复制本槽最近一条输出" aria-label="复制">' + _ICON_COPY + '</button>'\n"""
)
if OLD_BTNS in s:
    s = s.replace(OLD_BTNS, NEW_BTNS, 1)
    sys.stdout.write("  [OK] 终端四按钮图标化\n")
else:
    raise SystemExit("[FAIL] 终端按钮锚点未命中")

# ---------- 5) 输出区表头热区 ----------
OLD_HEAD = u"""          <div class="fb-head">"""
NEW_HEAD = u"""          <!-- A13：点表头空白 = 收起（按钮不拦，见 fbHeadToggle） -->
          <div class="fb-head" onclick="fbHeadToggle(event)">"""
if OLD_HEAD in s:
    s = s.replace(OLD_HEAD, NEW_HEAD, 1)
    s = s.replace(
        u"""            <div class="h-s">输出</div>\n            <div class="fb-acts">""",
        u"""            <div class="h-s">输出</div>\n"""
        u"""            <span class="fb-head-hint">点击空白处收起</span>\n"""
        u"""            <div class="fb-acts">""", 1)
    sys.stdout.write("  [OK] 输出区表头热区\n")
else:
    raise SystemExit("[FAIL] fb-head 锚点未命中")

# ---------- 6) 帮助文档同步 ----------
OLD_HELP = (
    u"""    '<p>顶栏左侧四个胶囊是状态：<code>root</code> / <code>无线</code> / <code>日志</code> / 设备号。' +\n"""
    u"""    '点 root 可一键提权，点无线可切 TCP 连接，点日志显示当前日志等级。</p>' },\n"""
)
NEW_HELP = (
    u"""    '<p>标题栏左边四个<strong>圆点</strong>是状态灯，没有文字：' +\n"""
    u"""    '<code>root</code> / <code>无线</code> / <code>日志</code> / <code>设备</code>。' +\n"""
    u"""    '鼠标停上去会浮出说明。点第一个提权 root，点第二个开无线连接，点第四个数设备号。</p>' },\n"""
)
if OLD_HELP in s:
    s = s.replace(OLD_HELP, NEW_HELP, 1)

OLD_TABLE = (
    u"""    '<table><tr><th>元素</th><th>含义</th><th>可点吗</th></tr>' +\n"""
    u"""    '<tr><td><code>root</code></td><td>绿=已 root，红=未 root，灰=离线</td><td>点一下执行 <code>adb root</code> 提权</td></tr>' +\n"""
    u"""    '<tr><td><code>无线</code></td><td>是否走 TCP 连接</td><td>点开填 IP，留空自动取设备 IP</td></tr>' +\n"""
    u"""    '<tr><td><code>日志</code></td><td>当前 log 等级 V/D/I/W/E</td><td>只读</td></tr>' +\n"""
    u"""    '<tr><td>设备号</td><td>序列号 + SoC + 分辨率</td><td>只读</td></tr>' +\n"""
    u"""    '<tr><td>执行中</td><td>有命令在跑，带计时</td><td>点一下停止</td></tr>' +\n"""
    u"""    '<tr><td>⚙ 设置</td><td>主题 / 强调色 / 字体 / 关闭</td><td>点开设置抽屉</td></tr></table>' +\n"""
    u"""    '<p>标题栏右上角是最小化 / 最大化 / 关闭。标题栏空白处可拖动窗口，' +\n"""
    u"""    '双击最大化，拖到屏幕边缘可分屏 —— 和普通窗口一致。</p>' },\n"""
)
NEW_TABLE = (
    u"""    '<table><tr><th>圆点</th><th>含义</th><th>可点吗</th></tr>' +\n"""
    u"""    '<tr><td>① root</td><td>亮=已 root（跟随强调色），灰=未 root，更浅=离线</td><td>点一下执行 <code>adb root</code> 提权</td></tr>' +\n"""
    u"""    '<tr><td>② 无线</td><td>亮=已走 TCP 连接（跟随强调色），灰=未连接</td><td>点开填 IP，留空自动取设备 IP</td></tr>' +\n"""
    u"""    '<tr><td>③ 日志</td><td>按等级上色：V 白 / D 蓝 / I 绿 / W 黄 / E 红，深灰=未设置</td><td>只读，悬停显示等级名</td></tr>' +\n"""
    u"""    '<tr><td>④ 设备</td><td>绿=在线，红=离线，灰=未知</td><td>只读，悬停显示序列号 / SoC / 分辨率</td></tr>' +\n"""
    u"""    '<tr><td>执行中</td><td>有命令在跑，带计时</td><td>点一下停止</td></tr>' +\n"""
    u"""    '<tr><td>⚙ 设置</td><td>主题 / 强调色 / 字体 / 关闭</td><td>点开设置抽屉</td></tr></table>' +\n"""
    u"""    '<p>标题栏最右是最小化 / 最大化 / 关闭。标题栏空白处可拖动窗口，双击最大化。</p>' +\n"""
    u"""    '<p>注：本版本为了支持自绘标题栏去掉了系统边框，因此<strong>拖到屏幕边缘不会自动分屏</strong>；' +\n"""
    u"""    '需要并排对比时请用 <kbd>Win</kbd>+<kbd>←/→</kbd> 或手动拖拽调宽（四边四角都能拖）。</p>' },\n"""
)
if OLD_TABLE in s:
    s = s.replace(OLD_TABLE, NEW_TABLE, 1)
    sys.stdout.write("  [OK] 帮助文档同步四圆点\n")
else:
    sys.stdout.write("  [WARN] 帮助表格锚点未命中（不影响功能）\n")

io.open(UI, "w", encoding="utf-8", newline="").write(s)
sys.stdout.write("ui.html 结构补丁完成，%.1f KB\n" % (len(s) / 1024.0))
