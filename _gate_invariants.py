# -*- coding: utf-8 -*-
"""阶段 6 · 门禁 1/3 只读对照：把 FUNCTION-INVARIANTS.md 基线与当前源码逐项比对。

项目不是 git 仓库，无法用 git diff，所以用「解析基线清单 + 解析当前源码」做等价核验。
只读：除输出 docs/INVARIANT-DIFF.md 外不改任何文件。
用法：python _gate_invariants.py
"""
import io
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
BASE = os.path.join(ROOT, "docs", "FUNCTION-INVARIANTS.md")
OUT = os.path.join(ROOT, "docs", "INVARIANT-DIFF.md")


def read(path, binary=False):
    mode = "rb" if binary else "r"
    kw = {} if binary else {"encoding": "utf-8"}
    with io.open(path, mode, **kw) as f:
        return f.read()


def ticks(line):
    return re.findall(r"`([^`]+)`", line)


def section_lines(md, title):
    out = []
    hit = False
    for ln in md.splitlines():
        if ln.startswith("## "):
            if hit:
                break
            hit = ln.startswith(title)
            continue
        if hit and ln.strip():
            out.append(ln)
    return out


def ico_sizes(data):
    if len(data) < 6:
        return []
    _, typ, cnt = struct.unpack("<HHH", data[:6])
    if typ != 1:
        return []
    sizes = []
    for i in range(cnt):
        off = 6 + i * 16
        if off + 16 > len(data):
            break
        w, h = data[off], data[off + 1]
        sizes.append(w or 256 if w == 0 else w)
    return sizes


s = read(UI)
md = read(BASE)
css = s[s.index("<style>"):s.index("</style>")]
js = s[s.index("</style>"):]

cur = {
    "kinds": sorted(set(re.findall(r"case\s+'([a-zA-Z]+)'\s*:", js))),
    "onclicks": sorted(set(re.findall(r'onclick="([A-Za-z_$][\w$]*)\s*\(', s))),
    "ids": sorted(set(re.findall(r'\sid="([A-Za-z][\w-]*)"', s))),
    "tabs": re.findall(r'data-tab="([^"]+)"', s),
    "pages": re.findall(r'id="(page-[\w-]+)"', s),
}

kinds_line = [l for l in section_lines(md, "## 1.") if l.startswith("共 ")]
base = {
    "kinds": ticks(kinds_line[0]) if kinds_line else [],
    "onclicks": ticks(section_lines(md, "## 2.")[0]),
    "ids": ticks(section_lines(md, "## 3.")[0]),
    "tabs": ticks([l for l in section_lines(md, "## 4.") if l.startswith("- data-tab")][0]),
    "pages": ticks([l for l in section_lines(md, "## 4.") if l.startswith("- #page-*")][0]),
}

rows = []
fails = []


def chk(name, cond, detail=""):
    rows.append((name, "PASS" if cond else "FAIL", detail))
    if not cond:
        fails.append(name)


# A9 追加轮（2026-11-15 第三批）：用户显式要求新增「9 色强调色切换器」。
# 契约口径：冻结层禁止删除 / 改名，允许新增，但新增项必须逐条登记在这里，
# 未登记的新增仍然判失败 —— 既不让门禁形同虚设，也不把合法追加误判成违约。
A9_ADDS = {
    "kinds": set(["accent", "customcmds"]),
    "onclicks": set([
        # 9 色强调色
        "accentPopClick", "toggleAccentPop",
        # 自定义 ADB 指令
        "openCustomMgr", "closeCustomMgr", "cmBackdrop", "cmNew", "cmSave",
        "cmAddStep", "cmDelStep", "cmDel", "cmEdit",
    ]),
    "ids": set([
        # 9 色强调色
        "accent-btn", "accent-pick", "accent-pop",
        # 自定义 ADB 指令
        "custom-panel", "custom-mgr", "cm-grid", "cm-list", "cm-name",
        "cm-desc", "cm-steps", "cm-err",
    ]),
}
# A12 追加轮（2026-11-15 第二轮）：自绘标题栏 / 设置抽屉 / 文本页 / 帮助 / 文件页增强。
# 本轮含**用户明确要求的功能迁移**：顶栏的主题按钮、强调色按钮、品牌按钮
# 全部收进设置抽屉（需求 5）。所以这里同时登记「新增」和「经批准删除」——
# 删除必须逐条写理由，不能因为"反正门禁会过"就悄悄抹掉功能。
A12_ADDS = {
    "kinds": set(["winstate", "prefs", "textfile", "textsaved", "texterr"]),
    "onclicks": set([
        # 自绘标题栏
        "tbDrag", "tbMin", "tbMax", "tbClose", "appClose", "toggleSettings", "closeSettings",
        "setThemeByName",
        # 使用说明
        "openHelp", "closeHelp", "helpGo",
        # 文本编辑器
        "txNew", "txOpen", "txSave", "txFindOpen", "txFindNext", "txFindClose",
        "txReplaceOne", "txReplaceAll", "txGoto", "txSetEnc", "txSetEol",
        "txToggleWrap", "txZoom", "txUndoRedo", "txSyncCaret", "txSelect", "txClose",
        # 文件页
        "fsSwapSides", "fsColDown", "fsColReset",
        # 结果图空态
        "uiResultImgErr",
    ]),
    "ids": set([
        "titlebar", "tb-sub", "tb-min", "tb-max", "tb-close", "settings-btn",
        "set-mask", "set-theme", "set-font", "set-font-preview",
        "help-mask", "help-toc", "help-doc", "help-search",
        "page-text", "tx-tabs", "tx-find", "tx-find-i", "tx-repl-i", "tx-find-n",
        "tx-case", "tx-repl-one", "tx-repl-all", "tx-body", "tx-gutter", "tx-edit",
        "tx-enc", "tx-eol", "tx-wrap-btn", "tx-zoom-val",
        "tx-st-pos", "tx-st-sel", "tx-st-len", "tx-st-enc", "tx-st-eol", "tx-st-font",
        "fs-swap",
    ]),
}
# 经批准删除（功能迁移，不是丢功能）：
#   theme-btn / toggleTheme   → 主题切换搬进设置抽屉（需求 5）
#   accent-btn / accent-pick / toggleAccentPop / accentPopClick 色板搬到设置内联网格（需求 5）
#   sendCmd                   → 原品牌按钮「:h」入口移除，帮助改成独立面板（需求 7）
A12_REMOVED = {
    "kinds": set(),
    "onclicks": set(["toggleTheme", "sendCmd", "toggleAccentPop"]),
    "ids": set(["theme-btn", "accent-btn", "accent-pick"]),
}

# A18 经批准删除（scrcpy 内嵌从"单屏全窗口"改成"每格一块"，功能迁移不是丢功能）：
#   scrcpyOpen   → 每格的「外部」按钮删掉，scrcpy 直接内嵌到格子本身（castToggle 里 if(_sc.ok) 走 v17CastEmbed）
#   cast-embed / ce-stage / ce-hint / cm-embed / cm-builtin / cast-mode  → 单屏全窗口宿主整体撤销，六格各自宿主
A18_REMOVED = {
    "kinds": set(),
    "onclicks": set(["scrcpyOpen", "v17CastBuiltin", "castOpenScrcpy"]),
    "ids": set(["cast-embed", "ce-stage", "ce-hint", "cm-embed", "cm-builtin", "cast-mode"]),
}
# A31（2026-11-19）：删除「投屏」页签。
# 理由：页内嵌 scrcpy 窗口在 5.0.1 上不重绘（黑屏），且原生窗口压住 WebView2
# 吞掉 DOM 点击（取消按钮点不动）——实测无解。改为「指令页 → Scrcpy投屏」外部窗口。
A31_REMOVED = {
    "kinds": set(),
    "onclicks": set([
        "castToggle", "castMaxToggle", "castRecord", "castStartFromStrip",
        "scrcpyAuto", "scrcpyPick", "scrcpyOpen",
        "ffmpegAuto", "ffmpegPick",
    ]),
    "ids": set([
        "page-cast", "cast-grid", "cast-strip", "cast-fps", "cast-hint",
        "sc-dot", "sc-enc", "sc-txt", "ff-dot", "ff-enc", "ff-txt",
    ]),
}
A31_TAB_REMOVED = ["cast"]
A31_PAGE_REMOVED = ["page-cast"]

# 页签 / 页面允许"追加"（顺序不能变，新页签必须在这里登记）
A12_TAB_ADD = ["text"]
A12_PAGE_ADD = ["page-text"]

# A13 轮新增（自绘标题栏四点 / 输出区点空白收起），逐项登记而不是放宽断言：
#   tb-status    四圆点容器（原 .topbar 里的 root/无线/日志/设备 徽章搬进标题栏）
#   log-dot      日志胶囊里新补的等级圆点（V/D/I/W/E 五色，靠 data-lv 驱动）
#   fbHeadToggle 输出区表头点击 —— 收起态点空白展开、展开态点空白收起
A13_ADDS = {
    "kinds": set(),
    "onclicks": set(["fbHeadToggle"]),
    "ids": set(["log-dot", "tb-status"]),
}

# A14 轮新增（设置里的字体大小三段 + 自绘下拉浮层），逐项登记：
#   setSize   字体大小按钮（小/中/大）→ 前端发 uizoom，C# 设 WebView2 ZoomFactor
#   set-fsize 那三个按钮的容器
# 说明：下拉浮层是 JS 动态建的 div（.a14-selpop），没有 id / onclick，不进基线。
A14_ADDS = {
    "kinds": set(),
    "onclicks": set(["setSize"]),
    "ids": set(["set-fsize"]),
}

# A15 轮新增（2026-11-15 第四批）：显示选项 / 日志等级面板 / 设备管理面板。
# 说明：日志等级与设备的**回推**走的是 window.v15Msg 覆写，没有新增 onMessage kind，
#       通讯用的是既有 post2/kind 通道（logget / logset / devlist / devswitch / devdisconnect
#       由 C# 侧 case 承接），所以 kinds 一项为 0 新增。
# A16（2026-11-15 第 5 批）：投屏页新增「用 scrcpy 打开」入口。
# 只新增一个 onclick，没有新 DOM id、没有新后端消息类型 ——
# 偏好持久化 / tab 拖拽 / 搜索索引全部在前端层内完成，不扩协议。
A16_ADDS = {
    "kinds": set(),
    "onclicks": set(["castOpenScrcpy"]),
    "ids": set(),
}

# A17（2026-11-15 第 6 批）：内嵌 scrcpy 投屏（A18 起改为"每格一块"）。
# A18 把单屏全窗口的宿主（#cast-embed / #ce-stage / #cm-embed / #cm-builtin）整个撤掉，
# 改成投屏页 3×2 六格各自宿主（格子自带的 .cast-view 就是画面区，C# 按格比例 SetParent）。
# 保留的契约：4 个 kind 不变（scrcpyembed 现在带 {slot,id} / scrcpyembedstop 带 {slot}
# / castembedrect 带 {slot,l,t,r,b} / castembedhide 整体隐藏），
# 页面入口函数换成 v17CastEmbed(slot,id) / v17CastEmbedStop(slot)。
# 图标图形（#appmark-glyph / #appmark-bg）两条 id 不是"节点"而是 SVG defs 里的
# 引用目标：改一处，启动层与标题栏一起变，所以必须登记、不能被当成随手写的 id 删掉。
A17_ADDS = {
    "kinds": set(["scrcpyembed", "scrcpyembedstop", "castembedrect", "castembedhide"]),
    "onclicks": set(["v17CastEmbed", "v17CastEmbedStop", "castBuiltinFallback"]),
    "ids": set(["appmark-bg", "appmark-glyph"]),
}

A15_ADDS = {
    "kinds": set(),
    "onclicks": set(),
    "ids": set([
        # 设置 · 显示选项（主题跟随系统 / OLED 纯黑 / 护眼三档）
        "a15-sec-display", "set-auto", "set-display-hint", "set-eyelevel", "set-oled",
        # 日志等级面板
        "v15-lvdev", "v15-lvshow", "v15-lvstate",
        # 设备管理面板
        "v15-devh", "v15-devrows", "v15-devrefresh", "v15-devoff",
    ]),
}

# A27（2026-11-17）：版本水印。
#   build        C# 在 themeget 时推出的新消息：「程序时间 / 界面时间 / 运行目录」。
#                为什么要它：现场出现过"改了却看不到变化"，根因是同机器上还开着
#                别的目录里的旧副本（另一个 exe + 另一份 ui.html）。有了这条，
#                「我在看哪一份」不用再靠猜，也不用问开发者。
#   build-stamp  设置 → 关于 里显示这三项的那一行（原先是写死的 "v8.3 · 2026-11-15"，
#                时间永远停在过去，反而误导）。
A27_ADDS = {
    "kinds": set(["build"]),
    "onclicks": set(),
    "ids": set(["build-stamp"]),
}

# A29（2026-11-19）：T7 APK 包名输入框。
#   apk-pkg-input   手输包名的输入框（与下拉互为备份，输入框优先）
#   apk-pkg-hint    右侧校验提示（非法红字 / 合法打勾 + 命中的中文名）
#   apk-btn-fillfront 「填入」：把当前前台包名写进输入框
#   三个 onclick 都是新增函数：输入校验 / 回车查询 / 粘贴剥 package: 前缀
A29_ADDS = {
    "kinds": set(),
    "onclicks": set(["apkPkgInput", "apkPkgKey", "apkPkgPaste", "apkFillFront"]),
    "ids": set(["apk-pkg-input", "apk-pkg-hint", "apk-btn-fillfront",
              "apk-btn-uninstall"]),
}

# A30（2026-11-19）：T14a 文件偶发打不开。
#   fsRetry  错误行里的一键重试（重新读取该目录）
#   另外三处是行为改造、没有新增 DOM：请求序号（丢过期响应）、超时自动重试一次、
#   35 秒加载看门狗。
A30_ADDS = {
    # T3 改向（2026-11-19）：网络模拟改走 PC 端内置代理。
    #   netsimlog    代理流水日志（对应参考工具的"弱网环境脚本生成中…"）
    #   netsimstat   实时上下行字节/连接数
    #   netsimstate  代理启停状态
    # 发送侧的 netsimstart / netsimstop 不在此列（这里统计的是页面**接收**的 kind）
    "kinds": set(["netsimlog", "netsimstat", "netsimstate"]),
    # T14b：文件交互第一批新增的内联 onclick（右键菜单/排序/路径编辑都是函数调用，
    # 菜单项本身是动态节点，不进静态扫描）
    "onclicks": set(["fsRetry", "fsPathEdit", "fsPathDone"]),
    # T3：代理状态与实时流量显示
    # R2/R5（2026-11-19）：新增两条网联服务卡片，没有新 id；但 :proxydel 是内置命令，
    # 门禁的 kind/onclick 都扫不到，靠 _check_a14 的卡片断言覆盖。
    "ids": set(["ns-state", "ns-stat"]),
}

labels = {
    "kinds": "onMessage 的 kind（基线 %d）" % len(base["kinds"]),
    "onclicks": "onclick 绑定函数（基线 %d）" % len(base["onclicks"]),
    "ids": "静态 DOM id（基线 %d）" % len(base["ids"]),
    "tabs": "data-tab 页签顺序",
    "pages": "#page-* 页面集合",
}
for k in ("kinds", "onclicks", "ids"):
    a, b = set(base[k]), set(cur[k])
    removed = sorted(a - b)
    added = sorted(b - a)
    unreg = [x for x in added
             if x not in A9_ADDS[k] and x not in A12_ADDS[k]
             and x not in A13_ADDS[k] and x not in A14_ADDS[k]
             and x not in A15_ADDS[k] and x not in A16_ADDS[k]
             and x not in A17_ADDS[k] and x not in A27_ADDS[k]
             and x not in A29_ADDS[k] and x not in A30_ADDS[k]]
    bad_rm = [x for x in removed if x not in A12_REMOVED[k]
              and x not in A18_REMOVED[k] and x not in A31_REMOVED[k]]
    ok = (not bad_rm) and (not unreg)
    chk(labels[k], ok,
        "基线 %d / 当前 %d；新增 %s；经批准删除 %s；违约删除 %s；未登记新增 %s" %
        (len(a), len(b), added or "无", removed or "无", bad_rm or "无", unreg or "无"))
# 页签 / 页面：顺序冻结，允许在末尾追加（必须登记）
# 2026-11-19：删页签会破坏"前缀相同"的比较，先把经批准删除的项从两侧摘掉
_base_t = [t for t in base["tabs"] if t not in A31_TAB_REMOVED]
_cur_t = [t for t in cur["tabs"] if t not in A31_TAB_REMOVED]
tabs_ok = _cur_t[:len(_base_t)] == _base_t and \
          set(_cur_t[len(_base_t):]) <= set(A12_TAB_ADD)
chk(labels["tabs"], tabs_ok, "基线 %s / 当前 %s" % (base["tabs"], cur["tabs"]))
_base_p = [p for p in base["pages"] if p not in A31_PAGE_REMOVED]
_cur_p = [p for p in cur["pages"] if p not in A31_PAGE_REMOVED]
pages_ok = _cur_p[:len(_base_p)] == _base_p and \
           set(_cur_p[len(_base_p):]) <= set(A12_PAGE_ADD)
chk(labels["pages"], pages_ok, "基线 %s / 当前 %s" % (base["pages"], cur["pages"]))

# ---- 冻结字符串锚点 ----
frozen = [
    ("post() 签名（v12 起多一个 extra 字段包）", "function post(kind, data, src, slot, extra){"),
    ("postObj() 签名", "function postObj(o){"),
    ("sendCmd() 签名", "function sendCmd(cmd){"),
    ("switchTab() 签名", "function switchTab(name){"),
    ("applyTheme() 签名", "function applyTheme(name){"),
    ("toggleTheme() 签名", "function toggleTheme(){"),
    ("WebView2 消息桥", "window.chrome.webview.postMessage(o)"),
    ("ready() 回包", "{kind:'ready'}"),
    ("文件拖放桥", "postMessageWithAdditionalObjects('fileDrop', [files[0]])"),
    ("THEME_ORDER 冻结", "var THEME_ORDER = ['dark', 'light', 'eye'];"),
]
for name, anchor in frozen:
    chk(name, anchor in s, anchor[:48])

# ---- 表现层：只允许改的部分，需给出复核结论 ----
brand = ["#3fb99b", "#e8a33d", "#a8761f"]
brand_hit = [c for c in brand if c.lower() in s.lower()]
chk("三处旧品牌硬编码色全文件清零", not brand_hit, str(brand_hit))
svg_hard = sorted(set(re.findall(r'(?:stroke|fill)="(#[0-9a-fA-F]{3,8})"', s)))
chk("内联 SVG 硬编码 stroke/fill = 0", not svg_hard, str(svg_hard))
# 组件样式必须零硬编码色；只有令牌「定义段」（:root...{}，含 27 条 accent 矩阵）
# 允许出现字面色值，这跟原三套 :root[data-theme] 定义语义色是同一性质。
css_body = re.sub(r":root[^{]*\{[^}]*\}", "", css)
css_body = re.sub(r"/\*.*?\*/", "", css_body, flags=re.S)
hard = re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)", css_body)
chk("组件样式零硬编码色（令牌定义段除外）", not hard, str(hard[:6]))

roles = ["--bg", "--surface", "--surface-2", "--border", "--border-strong",
         "--text", "--text-dim", "--text-faint", "--accent", "--accent-soft",
         "--ok", "--err", "--lv-v", "--lv-d", "--lv-i", "--lv-w", "--lv-e"]
for th in ("dark", "light", "eye"):
    m = re.search(r':root\[data-theme="' + th + r'"\]\s*\{([^}]+)\}', css)
    body = m.group(1) if m else ""
    miss = [r for r in roles if (r + ":") not in body]
    chk("主题 %s 的 17 个语义令牌齐备" % th, not miss, "缺：" + str(miss) if miss else "17/17")

for pref in ("prefers-reduced-motion", "prefers-reduced-transparency", "prefers-contrast"):
    chk("无障碍降级 " + pref, pref in css)
chk("键盘焦点 :focus-visible", ":focus-visible" in css)

# ---- 应用图标 ----
ico1 = read(os.path.join(ROOT, "adb_log_gui", "adb_Tool.ico"), True)
ico2 = read(os.path.join(ROOT, "adb_log_gui", "icons", "adb_Tool.ico"), True)
chk("ICO-01 / ICO-02 字节一致", ico1 == ico2, "%d / %d B" % (len(ico1), len(ico2)))
sizes = ico_sizes(ico1)
chk("ICO 多尺寸齐备（16/24/32/48/64/128/256）",
    sizes == [16, 24, 32, 48, 64, 128, 256], str(sizes))
chk("可编辑 SVG 源存在（图标 v2：车载中控终端）",
    os.path.isfile(os.path.join(ROOT, "adb_log_gui", "icons", "svg", "AdbTool-中控终端.svg")))

# ---- 本轮 3 个追加需求（A9）落点 ----
# 2026-11-20（P3）：Cast.cs 已随投屏通道删除；下面两条断言改为"必须已删"，
# 所以这里读不到就是预期状态，用空串而不是抛异常。
_cast_path = os.path.join(ROOT, "_cs", "Cast.cs")
cast = read(_cast_path) if os.path.exists(_cast_path) else ""
bugs = [
    # 2026-11-20（P3）：Cast.cs 删除后 /snap 端点不复存在 —— 改为反向校验
    ("缩略条 /snap 单帧端点已随 Cast.cs 删除", "/snap/" not in cast),
    ("前端缩略条走 /snap + 1 秒轮询", "function castRefreshStripFrames" in s
     and "/snap/' + i" in s and "castRefreshStripFrames();" in s),
    ("缩略条每路停止按钮", "cast-thumb-stop" in s and "closest('[data-stop]')" in s),
    ("搜索结果点击整行进树", 'data-search="1"' in s and "function fsOpenSearchDir" in s),
    # 去掉注释再判：注释里记录「原按钮已删」是允许的，不算残留实现
    ("旧的「进入 ⤵」按钮已删", all(t not in re.sub(
        r"/\*.*?\*/", "", re.sub(r"^\s*//.*$", "", s, flags=re.M), flags=re.S)
        for t in ("fs-enter", "data-enter", "进入 ⤵"))),
    ("搜索态 dblclick 兼容", "if (s && s.active) {" in s and "justRevealed" in s),
]
# A31：投屏页整体删除，这两条 A9 断言的对象已不存在 —— 改成反向校验，
# 确认它们确实被删干净（而不是放水放过）。
A31_RETIRED = set(["前端缩略条走 /snap + 1 秒轮询", "缩略条每路停止按钮"])
for name, cond in bugs:
    if name in A31_RETIRED:
        chk("A31 · 已随投屏页删除 · " + name, not cond)
    else:
        chk("A9 追加轮 · " + name, cond)

# ---- A9 第三批：9 色强调色切换器（与明暗主题正交）----
guiweb = read(os.path.join(ROOT, "_cs", "GuiWeb.cs"))
prefix = read(os.path.join(ROOT, "_cs", "Prefix.cs"))
program = read(os.path.join(ROOT, "_cs", "Program.cs"))
ini_root = read(os.path.join(ROOT, "adb_log_export.ini"))
ini_gui = read(os.path.join(ROOT, "adb_log_gui", "adb_log_export.ini"))
acc_rules = re.findall(r':root\[data-theme="\w+"\]\[data-accent="\w+"\]', css)
acc_feats = [
    # A15 轮把 9 色扩到 13 色（用户要求「参考 Apple UI 多给些颜色」）：
    # 顺序按色相环排（冷 → 暖 → 中性），white/black 合并进 graphite 并做了偏好迁移。
    # A16 轮再补三白（纯白 / 护眼白 / 玻璃白）→ 16 色。深色下就是白本身，
    # 浅色 / 护眼下由生成器压成"刚好 3:1"的中性灰（白色对白底是 1:1，不压不是颜色）。
    ("16 色顺序冻结（色相环 + 三白）",
     "var ACCENT_ORDER = ['blue','cyan','teal','mint','green','yellow','orange',"
     "'red','pink','purple','indigo','brown','graphite',"
     "'purewhite','eyewhite','glasswhite'];" in s),
    ("48 条 主题×色 令牌规则齐备", len(acc_rules) == 48),
    ("色板 16 个可点色点",
     len(re.findall(r'class="accent-dot[^"]*" data-accent=', s)) == 16),
    ("切色只改 data-accent，不改 data-theme",
     "document.documentElement.setAttribute('data-accent', name)" in s),
    ("前端回传 accent 消息", "post('accent', name)" in s and "case 'accent':" in s),
    ("后端接收并持久化 accent", 'case "accent":' in guiweb and "SaveAccentPreference" in guiweb),
    ("启动时回传 accent", "Json(App.ACCENT)" in guiweb),
    ("ini 两个源都有 accent= 键", ("accent=" in ini_root and "accent=" in ini_gui)),
    ("ACCENT 状态字段与 ini 解析", "internal static string ACCENT" in prefix and 'case "accent":' in program),
    ("对比度表已生成", os.path.isfile(os.path.join(ROOT, "docs", "ACCENT-CONTRAST.md"))),
]
for name, cond in acc_feats:
    chk("A9 追加轮 · 13 色强调色 · " + name, cond)

lines = [
    u"# 门禁 1 · 功能不变量对照表（阶段 6）",
    u"",
    u"> 生成：`python _gate_invariants.py`（只读，重复运行结果一致）。",
    u"> 项目**不是 git 仓库**，无法用 `git diff`；本表用「阶段 0 快照 vs 当前源码逐项解析」等价核验。",
    u"> 基线：`docs/FUNCTION-INVARIANTS.md`；被检源码：`adb_log_gui/webview2/ui.html`、`_cs/Cast.cs`、`*.ico`。",
    u"",
    u"| 核验项 | 结论 | 说明 |",
    u"|---|---|---|",
]
for n, r, d in rows:
    lines.append(u"| %s | %s | %s |" % (n, r, d.replace("|", "\\|")))
lines += [u"", u"**合计 %d 项，失败 %d 项。**" % (len(rows), len(fails))]
if fails:
    lines.append(u"失败项：" + u"、".join(fails))
lines += [
    u"",
    u"## 判定",
    u"",
    u"- 冻结层（kind / onclick / DOM id / 页签 / 页面 / 消息桥 / THEME_ORDER）："
    + (u"**0 删除 / 0 改名**；新增项均已登记" if all(r[1] == "PASS" for r in rows[:5] + rows[5:15])
       else u"**存在未登记改动，需回滚**"),
    u"- 允许层（`<style>` 语义令牌、内联 SVG 图形与颜色、图标文件）：已改，见 `COVERAGE.md`。",
    u"- 追加轮（3 个交互缺陷 + 强调色切换器）：**超出 A10「纯换肤」范围**，"
    u"属用户本轮显式要求，按 A9 处理并在 `UI-RESKIN-INVENTORY.md` 追加 ID、重算分母。",
    u"- A15 轮（显示选项 / 日志等级 / 设备管理）：新增 12 个静态 id，全部逐条登记在 `A15_ADDS`；"
    u"**0 个 new kind**——回推走 `window.v15Msg` 覆写 + C# 既有 post 通道，未扩消息契约。",
    u"- 本轮新增：`accent` kind、3 个 DOM id、2 个 onclick、13×3 条语义令牌规则；"
    u"改动落在 `ui.html` 的渲染/事件函数、`_cs/Cast.cs` 的 `/snap` 端点、"
    u"`_cs/GuiWeb.cs` / `Prefix.cs` / `Program.cs` 的 accent 持久化、以及 ini **新增** `accent=` 键。",
    u"- 仍未触碰：`post()` 签名、既有 28 个 kind、既有 onclick、命令串、"
    u"既有 ini key、`THEME_ORDER`、三套明暗主题取值、快捷键与 DOM 层级。",
    u"",
]
with io.open(OUT, "w", encoding="utf-8", newline="") as f:
    f.write(u"\n".join(lines) + u"\n")

for n, r, d in rows:
    if r == "FAIL":
        sys.stdout.write("FAIL | %s | %s\n" % (n, d))
sys.stdout.write("合计 %d 项，失败 %d 项 -> %s\n" % (len(rows), len(fails), OUT))
sys.exit(1 if fails else 0)
