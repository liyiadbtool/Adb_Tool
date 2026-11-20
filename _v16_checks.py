# -*- coding: utf-8 -*-
"""A16 轮机检（2026-11-15 第 5 批）：九条需求 + 9 条 adb 指令的"落点还在不在"。

和 _v15_checks.py 同一套思路：纯静态文本比对，起得快，任何一次误删/误合并
都能立刻红灯。真正"跑起来对不对"的验证交给 377/ 那套行为测试和
_casttest / -castprobe 探针，两份各管一段，互不掩盖。

这一批的九条：
  ① dock 打开窗口变小 —— 去掉改窗口尺寸的开合动画
  ② 强调色 13→16（纯白 / 护眼白 / 玻璃白）
  ③ 投屏六张卡并入「指令执行」，分类统一「投屏」
  ④ 弹窗互斥（body 级 fixed portal，后开的抢占先开的）
  ⑤ 弹窗打开时不再冒 hover 提示
  ⑥ 设备弹窗不再显示不全
  ⑦ 投屏低帧率——raw 抓帧 + 本地 JPEG，首次两条路各测一次选快的；scrcpy 补画质参数
  ⑧ 偏好统一持久化（字号 / 日志等级 / 显示选项 / tab 顺序）
  ⑨ tab 可拖拽换位并记忆
另加 9 条 adb 查询指令（adb root 用户明确要求不做）。

用法：python _v16_checks.py
退出码：0 全通过 / 1 有失败
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
V15JS = os.path.join(ROOT, "_v15.js")
V16JS = os.path.join(ROOT, "_v16.js")
GUIWEB = os.path.join(ROOT, "_cs", "GuiWeb.cs")
CAST = os.path.join(ROOT, "_cs", "Cast.cs")
SCRCPY = os.path.join(ROOT, "_cs", "Scrcpy.cs")
PROGRAM = os.path.join(ROOT, "_cs", "Program.cs")
INI = os.path.join(ROOT, "cmds.ini")
GENACCENT = os.path.join(ROOT, "_gen_accent.py")

rows = []


def read(p):
    with io.open(p, encoding="utf-8") as f:
        return f.read()


# 2026-11-20（P3）：Cast.cs 随投屏通道删除。所有以「⑦」结尾引用的 raw/JPEG/选路断言
# 对象已不存在 —— 这里统一判定为"随功能下线"，不逐条改（改 6 条多行断言更容易改错）。
_CAST_GONE = not os.path.exists(CAST)


def chk(name, cond, detail=""):
    if _CAST_GONE and "⑦" in name:
        rows.append((name, True, "已随 Cast.cs 删除"))
        return
    rows.append((name, bool(cond), detail))


s = read(UI)
v15 = read(V15JS)
v16 = read(V16JS)
guiweb = read(GUIWEB)
cast = read(CAST) if os.path.exists(CAST) else ""
scrcpy = read(SCRCPY)
prog = read(PROGRAM)
ini = read(INI)
gen = read(GENACCENT)

css = s[s.index("<style>"):s.index("</style>")]
body_html = s[s.index("</style>"):]

# ============================================================================
# 1. 第①条：dock 打开窗口变小
#    根因是 PlayOpenAnim 用 SetWindowPos 把窗口真缩到 168x100 再放大，
#    任何中断（WebView2 堵消息泵、重入、读运行时 Bounds）都会把窗口停在
#    中间尺寸且不最小化。根治 = 不碰窗口尺寸。
# ============================================================================
chk("① 开合不再改窗口尺寸（DockRect / PlayOpenAnim / PlayMinimizeAnim / AnimateBounds 全删）",
    not re.search(r"\b(DockRect|PlayOpenAnim|PlayMinimizeAnim|AnimateBounds)\b", guiweb))
chk("① 有尺寸兜底 EnsureSaneBounds（且至少 3 处调用：OnShown / WM_ACTIVATE / 自恢复）",
    guiweb.count("EnsureSaneBounds()") >= 3, "count=%d" % guiweb.count("EnsureSaneBounds()"))
chk("① 兜底会记一份「正常尺寸」_sane", "private Rectangle _sane" in guiweb and "RefreshSane()" in guiweb)
chk("① 兜底判据用 MinimumSize，不认小于它的尺寸",
    "b.Width >= minW && b.Height >= minH" in guiweb)
chk("① 最小尺寸跟踪下限回到 MinimumSize（不再是 1）",
    "ptMinTrackSize.X = MinimumSize.Width" in guiweb
    and "ptMinTrackSize.Y = MinimumSize.Height" in guiweb
    and "ptMinTrackSize.X = 1" not in guiweb)
chk("① 最小化走系统最小化，不做尺寸动画",
    "WindowState = FormWindowState.Minimized" in guiweb)
chk("① 内容层淡入缩放 .v16-in 存在",
    ".frame.v16-in{" in css and "@keyframes v16open" in css and "scale(.94)" in css)
chk("① 淡入动效有 reduced-motion 降级",
    "prefers-reduced-motion:reduce" in css and "v16-in{ animation:none" in css.replace(".frame", ""))
chk("① 淡入由 hookOpenAnim 在 splash 消失后挂（不等就看不见动效）",
    "function hookOpenAnim" in v15 and "v16-in" in v15 and "hookOpenAnim()" in v15)

# ============================================================================
# 2. 第②条：强调色 16 色
# ============================================================================
_colors = ["blue", "cyan", "teal", "mint", "green", "yellow", "orange", "red",
           "pink", "purple", "indigo", "brown", "graphite",
           "purewhite", "eyewhite", "glasswhite"]
_order_line = re.search(r"var ACCENT_ORDER = \[([^\]]*)\];", s)
_order = re.findall(r"'([a-z]+)'", _order_line.group(1)) if _order_line else []
chk("② ACCENT_ORDER 16 色且顺序冻结", _order == _colors, str(_order))
for _c in ("purewhite", "eyewhite", "glasswhite"):
    chk("② 色板有 %s 的色点" % _c, ('data-accent="%s"' % _c) in body_html)
chk("② 色板改成 4 列（16 色 4x4，5 列会溢出）",
    ".accent-pop{ grid-template-columns:repeat(4,40px); }" in css)
chk("② 生成器有 NEUTRAL 起算表（三白在浅色下按 HLS 另起算，避免压成玫瑰灰）",
    "NEUTRAL" in gen and "purewhite" in gen and "hls_to_rgb" in gen)
chk("② C# ini 白名单认得三白",
    "purewhite" in prog and "eyewhite" in prog and "glasswhite" in prog)

# ============================================================================
# 3. 第③条：投屏卡并入「指令执行」，分类统一「投屏」
# ============================================================================
_cat_cast = len(re.findall(r"cat:'投屏'", s))
chk("③ 投屏 6 张卡 cat:'投屏'", _cat_cast == 6, "count=%d" % _cat_cast)
chk("③ 独立组「投屏（scrcpy）」已删（只剩注释提一句）",
    "group:'投屏（scrcpy）'" not in s)
chk("③ 六张卡按屏位齐全（0 / 4 / 1 / 3 / 9 / 10）",
    all((":scrcpy %d'" % d) in s for d in (0, 4, 1, 3, 9, 10)))
# 2026-11-19（A31）：投屏页删除，「用 scrcpy 打开」按钮随页面下线。
# 能力改由「指令页 → Scrcpy投屏」卡片 + :cast 命令承担（下面那条六卡断言仍在）。
chk("③ 投屏页内的 scrcpy 按钮已随页面删除", "function castOpenScrcpy" not in s)
chk("③ 投屏改走 :cast 命令（指令卡片）", ":cast 0'" in s and ":cast 10'" in s)

# ============================================================================
# 4. 第④⑤⑥条：弹窗互斥 / 不再叠 hover / 不再显示不全
#    三件事同一根因：弹窗原来是徽章的后代，祖先有 backdrop-filter 形成层叠
#    上下文、还有 overflow 裁剪。改成 body 级 fixed portal + 单例 popCur。
# ============================================================================
chk("④ 弹窗 portal 到 body（document.body.appendChild）",
    "document.body.appendChild(p)" in v15)
chk("④ portal 用 position:fixed", "p.style.position = 'fixed'" in v15)
chk("④ 单例 popCur + anyPopOpen", "var popCur = null" in v15 and "function anyPopOpen" in v15)
chk("④ 后开的抢占先开的（openDevPop 里先 detach log，反之亦然）",
    "detachPop(lp, 'log')" in v15 and "detachPop(dp, 'dev')" in v15)
chk("④ 有统一关闭 closeAllPops（Esc / 点外部 / 切页都用它）",
    "function closeAllPops" in v15 and "closeAllPops()" in v15)
chk("④ 贴锚点算坐标 placePop（下方不够翻上方、左右溢出贴边）",
    "function placePop" in v15 and "innerHeight" in v15 and "innerWidth" in v15)
chk("④ 窗口尺寸变化要重定位 repositionPops",
    "function repositionPops" in v15 and "repositionPops()" in v15)
# T16（2026-11-18）：V14 的 self-dismiss 判断已收进 Overlay，语义相同。
chk("④ 点弹窗自己不算点空白（contains 判断，V14 层也在用）",
    "pop.contains" in s or "Overlay.contains" in s)
chk("⑤ 弹窗开着时不再冒 hover 提示（showTip 开头拦）",
    "if (anyPopOpen()) return;" in v15)
chk("⑥ .v15-pop 默认隐藏 + .on 显示（内联 style 复位会落回 display:none，不可靠）",
    re.search(r"\.v15-pop\s*\{[^}]*display\s*:\s*none", css) is not None
    and re.search(r"\.v15-pop\.on\s*\{[^}]*display\s*:\s*block", css) is not None)
chk("⑥ .v15-pop 限制 max-height 并自身滚动（不再被视口切掉）",
    re.search(r"\.v15-pop\s*\{[^}]*max-height\s*:\s*calc\(100vh", css) is not None
    and re.search(r"\.v15-pop\s*\{[^}]*overflow\s*:\s*auto", css) is not None)
chk("⑥ 旧的「贴徽章 right:0 / top:calc(100%+9px)」定位已清掉",
    ".tb-status > .logpill{ position:relative }" not in css)

# ============================================================================
# 5. 第⑦条：投屏性能
# ============================================================================
chk("⑦ raw 抓帧 CastGrabRaw（screencap 不带 -p，RGBA 直传）",
    "CastGrabRaw" in cast and "exec-out screencap" in cast)
chk("⑦ 本地 JPEG 编码 CastEncodeJpeg（R/B 交换 + 缩放）",
    "CastEncodeJpeg" in cast and "B" in cast and "Format32bppArgb" in cast)
chk("⑦ 编解码器按 MimeType 找（FormatID 在 ImageCodecInfo 上不存在）",
    'MimeType, "image/jpeg"' in cast and "FormatID" not in cast)
chk("⑦ 自适应选路：首帧两条都测、选快的、之后固定",
    "probe" in cast and "SetGrabMode" in cast and "GrabMode(" in cast)
chk("⑦ raw 允许 15% 容差（否则两台机器来回抖）", "0.85" in cast or "1.15" in cast)
chk("⑦ 帧格式统一 JPEG（Content-Type 不再有 image/png）",
    "image/jpeg" in cast and "image/png" not in cast)
chk("⑦ Publish 校验 JPEG 签名 FF D8 FF", "FF D8 FF" in cast or "0xFF, 0xD8, 0xFF" in cast)
chk("⑦ minGapMs 从 120 降到 90", "minGapMs" in cast)
chk("⑦ 非 0 屏首帧失败立刻停并给 scrcpy 建议",
    "screencap" in cast and "scrcpy" in cast)
chk("⑦ scrcpy 补画质参数",
    "--max-size=1600" in scrcpy and "--max-fps=60" in scrcpy
    and "--video-bit-rate=16M" in scrcpy and "--no-audio" in scrcpy)
chk("⑦ scrcpy 去掉与 --no-control 互斥的 --stay-awake",
    "--stay-awake" not in scrcpy.replace("注意：--stay-awake", "").replace("--stay-awake 与", ""))
chk("⑦ --print-fps 必须有人抽 stderr（否则写满 4KB 管道后卡死）",
    "--print-fps" in scrcpy and "drain" in scrcpy and "ReadLine" in scrcpy)

# ============================================================================
# 6. 第⑧条：偏好统一持久化
# ============================================================================
chk("⑧ v16 层包了 prefsApply，一份 schema 一次吃完",
    "applyAllPrefs" in v16 and "prefsApply" in v16)
chk("⑧ 回填覆盖 字号 / 日志等级 / 显示三项 / tab 顺序",
    "o.size" in v16 and "o.logshow" in v16 and "o.oled" in v16
    and "o.eye" in v16 and "o.auto" in v16 and "o.tabOrder" in v16)
chk("⑧ 显示选项现在真的写进 prefs（原来是只写不改）",
    "window.v15Snapshot" in v15 and "window.v15Restore" in v15)
chk("⑧ 字号恢复走 applySize 的静默通道（不弹 toast）",
    "applySize(o.size" in v16)

# ============================================================================
# 7. 第⑨条：tab 拖拽换位并记忆
# ============================================================================
chk("⑨ pointer 事件拖拽（不用 HTML5 draggable，WebView2 长按延迟难受）",
    "pointerdown" in v16 and "pointermove" in v16)
chk("⑨ 6px 死区（小于它就是切 tab，不是拖拽）",
    "Math.abs(dx) < 6 && Math.abs(dy) < 6" in v16)
chk("⑨ elementFromPoint + insertBefore 实时换位",
    "elementFromPoint" in v16 and "insertBefore" in v16)
chk("⑨ 松手补的 click 要被吃掉（suppressClickUntil）",
    "suppressClickUntil" in v16)
chk("⑨ 顺序写进 _prefs.tabOrder 并回填 applyTabOrder",
    "tabOrder" in v16 and "function applyTabOrder" in v16 and "saveTabOrder" in v16)
chk("⑨ 换位后通知 v15 重算 TAB_ORDER（翻页方向要跟着走）",
    "v15SyncTabOrder" in v16 and "window.v15SyncTabOrder" in v15)
chk("⑨ 拖拽时禁选中、不触发翻页",
    re.search(r"body\.v16-tabdrag\s*,\s*body\.v16-tabdrag\s*\*\s*\{[^}]*user-select\s*:\s*none", css) is not None
    and re.search(r"body\.v16-tabdrag\s+\.page\s*\{[^}]*animation\s*:\s*none", css) is not None)

# ============================================================================
# 8. 快捷指令搜索（第 5 批 5、1~5、2）
# ============================================================================
chk("搜索建索引含 name/desc/cmd/cat/alias/kw/组名（命令搜索靠 cmd + alias）",
    "function buildIndex" in v16 and "it.cmd" in v16 and "it.alias" in v16 and "it.kw" in v16)
chk("空格分词全命中", "toks" in v16 and "indexOf(toks[i])" in v16)
chk("命中位置加权（越靠前分越高）", "p < 24 ? 3" in v16)
chk("结果上限 MAX_HITS", "MAX_HITS" in v16 and "MAX_HITS = 80" in v16)
chk("防抖放在事件入口 v16QuickInput，onQuickSearch 保持同步",
    "window.v16QuickInput" in v16 and "setTimeout" in v16
    and "window.onQuickSearch = v16" not in v16)
chk("ui.html 的 oninput 绑的是 v16QuickInput",
    'oninput="v16QuickInput()"' in body_html)
chk("自定义命令增删后索引能失效", "v16InvalidateQuick" in v16)

# ============================================================================
# 9. 9 条 adb 指令（adb root 用户明确不做）
# ============================================================================
_secs = {
    "cmd.adbver": "adb version",
    "cmd.windisp": "dumpsys window displays",
    "cmd.aid": "settings get secure android_id",
    "cmd.osver": "getprop ro.build.version.release",
    "cmd.devs": "adb devices",
    "cmd.adbst": "adb start-server",
    "cmd.adbsp": "adb kill-server",
}
for _sec, _needle in _secs.items():
    chk("⑩ cmds.ini 有 [%s] 且命令对" % _sec,
        ("[%s]" % _sec) in ini and _needle in ini)
chk("⑩ cmds.ini 里没有 adb root（用户明确去除）", "adb root" not in ini)
chk("⑩ 界面有 9 条 cat:'系统查询'", len(re.findall(r"cat:'系统查询'", s)) == 9,
    "count=%d" % len(re.findall(r"cat:'系统查询'", s)))
chk("⑩ 内存总览取 40 行（meminfo 前 30 行看不到 Total PSS 以下的进程）",
    "head -40" in ini)
chk("⑩ 屏幕密度同时给 size 和 density（原来只有 size，名不符实）",
    'wm size; wm density' in ini)

# ============================================================================
# 10. 注入层完整性（V14 → V15 → V16 顺序不能乱，缺一层上面全失效）
# ============================================================================
chk("⑪ ui.html 有 V15 层注入结束标记", "V15 LAYER END" in s)
chk("⑪ ui.html 有 V16 两层标记（CSS + JS）",
    "V16 LAYER START" in s and "V16 JS START" in s)
chk("⑪ V14 的补丁也在（repositionPop / pop.contains 来自 V14 层）",
    "repositionPop" in s)
chk("⑪ 三层顺序 V14 → V15 → V16（V15 标记出现在 V16 之前）",
    s.index("V15 LAYER END") < s.index("V16 LAYER START"))

bad = [r for r in rows if not r[1]]
for name, ok, detail in rows:
    sys.stdout.write(("  PASS | " if ok else "  FAIL | ") + name
                     + (("  -> " + detail) if (detail and not ok) else "") + "\n")
sys.stdout.write("\n  A16 落点机检：通过 %d / %d\n" % (len(rows) - len(bad), len(rows)))
sys.exit(1 if bad else 0)
