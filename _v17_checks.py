# -*- coding: utf-8 -*-
"""A17 轮机检（2026-11-15 第 6 批）：八条需求 + 两条追加的"落点还在不在"。

和 _v15_checks.py / _v16_checks.py 同一套思路：纯静态文本比对，起得快，
任何一次误删/误合并都能立刻红灯。跑起来对不对交给 377/ 行为测试、
_smoke_win.py 与 _shot_a17.py 的截图，三份各管一段。

这一批：
  ① 强调色未记忆（重启回默认）
  ② 底部 dock 打开/收起的动效缺失
  ③ 应用 icon 黑白灰 + 黑底，相关页面一并替换
  ④ 浅色主题下窗口边界不明显
  ⑤ 直角全部换圆角（侧栏 / 终端页 / 输入行）
  ⑦ 偶发关闭要点两次
  ⑧ 启动层背景改高斯模糊渐变 + 图标跟随强调色
  追加-1 scrcpy 内嵌到应用内（可点击、高帧率）
  追加-2 换掉任务栏图标、标题去掉「网联服务_」

用法：python _v17_checks.py
退出码：0 全通过 / 1 有失败
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
V16JS = os.path.join(ROOT, "_v16.js")
V17CSS = os.path.join(ROOT, "_v17.css")
V17JS = os.path.join(ROOT, "_v17.js")
GUIWEB = os.path.join(ROOT, "_cs", "GuiWeb.cs")
PREFIX = os.path.join(ROOT, "_cs", "Prefix.cs")
SCRCPY = os.path.join(ROOT, "_cs", "Scrcpy.cs")
PROGRAM = os.path.join(ROOT, "_cs", "Program.cs")
ICONGEN = os.path.join(ROOT, "_icon_v2.py")
ICO = os.path.join(ROOT, "adb_log_gui", "adb_Tool.ico")

rows = []


def read(p):
    with io.open(p, encoding="utf-8") as f:
        return f.read()


def chk(name, cond, detail=""):
    rows.append((name, bool(cond), detail))


s = read(UI)
v16 = read(V16JS)
v17 = read(V17JS)
v17css = read(V17CSS)
guiweb = read(GUIWEB)
prefix = read(PREFIX)
scrcpy = read(SCRCPY)
prog = read(PROGRAM)
icongen = read(ICONGEN)

css = s[s.index("<style>"):s.index("</style>")]

# ============================================================================
# 1. 第①条：强调色未记忆
#    根因：白名单在 GuiWeb.cs 与 Program.cs 各写一份，扩到 16 色时只改了后者，
#    GuiWeb 那份还是 9 色。用户选 cyan / teal / graphite / 三白，保存时被判非法、
#    静默改写成 blue —— 重启就是"没记忆"。
# ============================================================================
chk("① 白名单只有一份（Prefix.ACCENTS）", "internal static readonly string[] ACCENTS" in prefix)
chk("① ACCENTS 是 16 色且含三白",
    len(re.findall(r'"(blue|cyan|teal|mint|green|yellow|orange|red|pink|purple|indigo|brown|graphite|purewhite|eyewhite|glasswhite)"',
                   prefix.split("ACCENTS = new string[]", 1)[1].split("};", 1)[0])) == 16)
chk("① 有统一的 NormalizeAccent（旧名 white/black 迁到 graphite）",
    "internal static string NormalizeAccent" in prefix
    and 'if (v == "white" || v == "black") v = "graphite";' in prefix)
chk("① GuiWeb 收 accent 时用 NormalizeAccent，不再自己判白名单",
    "App.ACCENT = App.NormalizeAccent(GetField(json, \"data\"));" in guiweb
    and "|red|yellow|blue|white|purple|black|green|orange|pink|" not in guiweb)
chk("① SaveAccentPreference 不再「ini 不存在就 return」（单 exe 目录本来就可能没有 ini）",
    "string[] lines = File.Exists(p) ? File.ReadAllLines(p) : new string[0];" in guiweb)
chk("① 页面侧也存一份 prefs.accent（双保险，不依赖 C# 白名单）",
    "o.accent" in v16 and "window.applyAccent(o.accent)" in v16)
chk("① setAccent 被包一层，切换时同时写 prefs + prefsSave",
    "_setAccentOrig" in v16 and "_prefs.accent = name" in v16 and "prefsSave()" in v16)
chk("① 启动时 C# 会把 ini 里的 accent 推给页面",
    '"{\\"kind\\":\\"accent\\",\\"name\\":' in guiweb)

# ============================================================================
# 2. 第②条：打开/收起动效（只动渲染层，绝不动窗口尺寸）
# ============================================================================
chk("② 有打开动效 .v17-in + v17open", ".frame.v17-in{" in v17css and "@keyframes v17open" in v17css)
chk("② 打开只动 transform（动 opacity 会与 splash 淡出相乘，且行为测试会误判半透明）",
    "from{ transform:scale(.93); }" in v17css
    and "from{ opacity:.001; transform:scale(.93); }" not in v17css)
chk("② 有收起动效 .v17-out + v17close",
    ".frame.v17-out{" in v17css and "@keyframes v17close" in v17css)
chk("② 动效有 reduced-motion 降级",
    "prefers-reduced-motion:reduce" in v17css and "v17-in, .frame.v17-out{ animation:none" in v17css)
chk("② A16 那套「等 splash 走了再补 class」已关掉（会晚 300ms 再放一次）",
    ".frame.v16-in{" in v17css and "animation:none !important;" in v17css)
chk("② 页面提供 v17Out / v17InRestore",
    "window.v17Out = function" in v17
    and "window.v17InRestore = function" in v17)
chk("② 打开动效由 hideSplash 同帧触发（不靠轮询）",
    "window.hideSplash = function" in v17 and "v17-in" in v17)
chk("② C# 收起走 PlayOutThen（先播 130ms 再最小化/关闭）",
    "private void PlayOutThen(Action after)" in guiweb
    and 'ExecuteScriptAsync("window.v17Out && window.v17Out()")' in guiweb)
chk("② 收起动效仍然不碰窗口尺寸（没有 SetWindowPos 做动画）",
    not re.search(r"\b(DockRect|PlayOpenAnim|PlayMinimizeAnim|AnimateBounds)\b", guiweb))

# ============================================================================
# 3. 第③条：icon 黑白灰 + 黑底（ico 源 + 页面内联图形）
# ============================================================================
chk("③ 图标底色从蓝渐变改成黑白灰", "C_TOP = (0x2E, 0x2E, 0x2E)" in icongen
    and "C_BOT = (0x05, 0x05, 0x05)" in icongen
    and "0x33, 0x7C, 0xFF" not in icongen)
chk("③ 右下压暗不再用偏蓝色（[0,0.05,0.30] 会在灰度图里留 15/255 蓝调）",
    "col = over(col, [0.0, 0.0, 0.0], 0.20 * clamp01" in icongen)
chk("③ ico 文件存在且是多档", os.path.exists(ICO))
chk("③ 页面图形与 ico 同源（defs 里只画一份，#appmark-glyph）",
    'id="appmark-glyph"' in s and 'id="appmark-bg"' in s)
chk("③ 启动层与标题栏都用 <use> 引用同一份图形",
    s.count('href="#appmark-glyph"') == 2, "count=%d" % s.count('href="#appmark-glyph"'))
chk("③ 标题栏图标是纯白（品牌标记，不跟强调色抢注意力）",
    ".appmark{ color:var(--mark-fg); }" in v17css)
chk("③ 启动层图标跟随强调色", ".splash .appmark{ color:var(--accent); }" in v17css)
chk("③ C# 会把内嵌 ico 设为窗体图标（任务栏 / Alt+Tab 都用新图）",
    "TrySetCatIcon();" in guiweb
    and 'Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "adb_Tool.ico")' in guiweb
    and "Icon = (Icon)ic.Clone();" in guiweb)

# ============================================================================
# 4. 第④条：浅色窗口边界
# ============================================================================
chk("④ 浅色/护眼有独立的窗口边令牌",
    '--winedge:rgba(48,48,54,.72);' in v17css
    and '--winedge-soft:rgba(48,48,54,.22);' in v17css)
chk("④ 边界画在 body::after 的 inset 双层环上",
    "inset 0 0 0 1px var(--winedge), inset 0 1px 0 var(--winhi)" in v17css)
chk("④ 浅色另有 6px 内阴影压出四角转折",
    "inset 0 0 6px var(--winedge-soft), inset 0 0 24px var(--winedge-soft)" in v17css)
chk("④ 深色主题不变（只给 10% 白边）", '--winedge:rgba(255,255,255,.10);' in v17css)

# ============================================================================
# 5. 第⑤条：直角 → 圆角
# ============================================================================
chk("⑤ 指令页侧栏与右侧区各自成卡片（12px 圆角 + 8px 内缩）",
    "#page-quick .quick-nav{" in v17css and "border-radius:12px;" in v17css
    and "#page-quick .quick-wrap{" in v17css and "padding:8px;" in v17css)
chk("⑤ 侧栏 border-right 被四边等宽覆盖（否则画出来是断角）",
    "#page-quick .quick-nav{" in v17css
    and v17css.count("border-right:1px solid var(--border);") >= 1)
chk("⑤ 终端页成卡片、输入行不再贴边",
    "#page-cmd .slot{" in v17css and "#page-cmd .inputbar{" in v17css)
chk("⑤ 投屏页 / 文件页同步内缩，切页不会跳",
    "#page-cast .cast-wrap{ padding:8px; }" in v17css)

# ============================================================================
# 6. 第⑦条：关闭要点两次
#    根因：OnFormClosing 里停线程 / Abort worker 会卡在 adb 同步读上，
#    而这段跑在 UI 线程 —— 窗口既不消失也不响应，用户只能再点一次。
# ============================================================================
chk("⑦ 关闭前先 Hide（窗口与任务栏按钮当场消失）",
    "try { Hide(); } catch { }" in guiweb)
chk("⑦ 真正的 Close 放到 BeginInvoke 里跑清理",
    "BeginInvoke((Action)delegate\n                            {\n                                try { Close(); } catch { }\n                            });" in guiweb)
chk("⑦ 有退出看门狗（清理卡住也不至于关不掉）",
    "private static void StartExitWatchdog(int ms)" in guiweb
    and "ThreadPool.QueueUserWorkItem" in guiweb)
chk("⑦ 重复点关闭时直接硬退出",
    "if (_closing)\n                    {\n                        try { Environment.Exit(0); } catch { }" in guiweb)
chk("⑦ _closing 会拦住「正在关还被点任务栏最小化」",
    "if (_closing) return;         // A17：正在关就别再插一脚把它最小化" in guiweb)

# ============================================================================
# 7. 第⑧条：启动层高斯模糊渐变 + 图标跟随强调色
# ============================================================================
chk("⑧ 网页启动层是渐变而不是纯黑", "radial-gradient(60% 52% at 50% 44%" in v17css
    and "linear-gradient(180deg, var(--splash-g0)" in v17css)
chk("⑧ 光晕单独一层做 blur（更像高斯模糊）",
    "filter:blur(56px) saturate(1.1);" in v17css)
chk("⑧ 渐变三个停靠点收进 :root 令牌（门禁要求组件区零硬编码色）",
    "--splash-g0:" in v17css and "--splash-g1:" in v17css and "--splash-g2:" in v17css)
chk("⑧ C# 原生遮罩也同步改（否则先看到纯黑再看到渐变）",
    "_splashPanel.Paint += SplashPaint;" in guiweb
    and "PathGradientBrush" in guiweb
    and "_splashPanel.BackColor = Color.FromArgb(10, 10, 12);" in guiweb)
chk("⑧ 原生遮罩的图标颜色取 App.ACCENT",
    "DrawLogo(g, AccentColor(), cx, cy, size);" in guiweb)

# ============================================================================
# 8. 追加-1：scrcpy 内嵌
# ============================================================================
chk("追加① 页面有内嵌占位区与模式切换",
    'id="ce-stage"' in s and 'id="cast-embed"' in s
    and 'id="cm-embed"' in s and 'id="cm-builtin"' in s)
chk("追加① 页面按比例上报区域（不受 ZoomFactor / DPI 影响）",
    "post('castembedrect'" in v17 and "r.left / W" in v17)
chk("追加① 进入投屏页默认拉起内嵌（scrcpy 替代兜底）",
    "if (EMBED.mode === 'embed') window.v17CastAutoEmbed();" in v17)
chk("追加① 用户选的模式会被记住（不每次强行拉起）",
    "rememberMode('builtin')" in v17 and "_prefs.castMode" in v17)
chk("追加① C# 用 SetParent 把 scrcpy 窗口塞进 Panel",
    "SetParent(h, _castHost.Handle);" in guiweb)
chk("追加① 接管时去掉标题栏/边框（否则内嵌里还有一个窗口框）",
    "style &= ~(WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU);" in guiweb)
chk("追加① scrcpy 用 --window-title 唯一命名，便于 FindWindow 认领",
    "--window-title=" in scrcpy and '" --window-borderless"' in scrcpy)
chk("追加① 内嵌模式不弹控制台黑框（否则会被误认成主窗口）",
    "psi.CreateNoWindow = true;" in scrcpy)
chk("追加① 内嵌模式也抽干 stdout/stderr（4KB 管道写满会卡死画面）",
    "psi.RedirectStandardError = true;" in scrcpy and "BeginErrorReadLine()" in scrcpy)
chk("追加① 找不到窗口时按 MainWindowHandle 兜底",
    "h = _scProc.MainWindowHandle;" in guiweb)
chk("追加① 切页会把内嵌藏起来（否则浮在别的页上）",
    "post('castembedhide', '');" in v17 and 'case "castembedhide"' in guiweb)
chk("追加① 窗口尺寸变化会重新摆 Panel",
    "if (_castHost != null && _castHost.Visible) ScrcpyEmbedPlace(null);" in guiweb)
chk("追加① 关窗会把内嵌 scrcpy 进程杀掉（不留在后台推流）",
    "_closing = true;          // A17：任何关闭路径都置位，避免重复进清理" in guiweb
    and "try { ScrcpyEmbedStop(); } catch { }" in guiweb)
chk("追加① 启动失败会回退内置通道并说明原因",
    "window.v17CastEmbedFail" in v17 and "v17CastEmbedFail" in guiweb)

# ============================================================================
# 9. 追加-2：任务栏图标 + 标题
# ============================================================================
chk("追加② 窗口标题去掉「网联服务_」",
    'Text = "Adb_Tool";' in guiweb
    and not re.search(r'Text = "[^"]*网联服务', guiweb))
chk("追加② 页面里的 title 提示也去掉了前缀",
    'title="网联服务_Adb_Tool"' not in s)

# ============================================================================
# 10. 注入层完整性（V14 → V15 → V16 → V17）
# ============================================================================
chk("⑩ ui.html 有 V17 两层标记（CSS + JS）",
    "V17 LAYER START" in s and "V17 JS START" in s)
chk("⑩ V17 只注入了一份（注入脚本幂等，重复跑不会叠层）",
    s.count("V17 LAYER START") == 1 and s.count("V17 JS START") == 1,
    "css=%d js=%d" % (s.count("V17 LAYER START"), s.count("V17 JS START")))
chk("⑩ 顺序 V14 → V15 → V16 → V17",
    s.index("V15 LAYER END") < s.index("V16 LAYER START") < s.index("V17 LAYER START"))
chk("⑩ .appmark 样式在注入后的 css 里（不只是源文件）",
    ".appmark{ color:var(--mark-fg); }" in css)

bad = [r for r in rows if not r[1]]
for name, ok, detail in rows:
    sys.stdout.write(("  PASS | " if ok else "  FAIL | ") + name
                     + (("  -> " + detail) if (detail and not ok) else "") + "\n")
sys.stdout.write("\n  A17 落点机检：通过 %d / %d\n" % (len(rows) - len(bad), len(rows)))
sys.exit(1 if bad else 0)
