# -*- coding: utf-8 -*-
"""A15 轮机检（2026-11-15 第 4 批）：把这一批"看得见的改动"钉成断言。

为什么单独一份而不是塞进 _check_a14.py：
  A14 那份测的是「视觉终值」（浏览器里量对比度、量尺寸），属于**跑起来才对**的验证；
  这份测的是「落点还在不在」——纯静态文本比对，起得快，任何一次误删都能立刻红灯。
  两份各管一段，互不掩盖。

用法：python _v15_checks.py
退出码：0 全通过 / 1 有失败
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
GUIWEB = os.path.join(ROOT, "_cs", "GuiWeb.cs")
TASKS = os.path.join(ROOT, "_cs", "TaskCmds.cs")
SCRCPY = os.path.join(ROOT, "_cs", "Scrcpy.cs")
PREFIX = os.path.join(ROOT, "_cs", "Prefix.cs")
PROGRAM = os.path.join(ROOT, "_cs", "Program.cs")

rows = []


def read(p):
    with io.open(p, encoding="utf-8") as f:
        return f.read()


def chk(name, cond, detail=""):
    rows.append((name, bool(cond), detail))


s = read(UI)
css = s[s.index("<style>"):s.index("</style>")]
css_body = re.sub(r":root[^{]*\{[^}]*\}", "", css)
css_body = re.sub(r"/\*.*?\*/", "", css_body, flags=re.S)
guiweb = read(GUIWEB)
tasks = read(TASKS)
scrcpy = read(SCRCPY)
prefix = read(PREFIX)
program = read(PROGRAM)

# ---- 1. 强调色 16 色（A16 加三白）----
ORDER = ["blue", "cyan", "teal", "mint", "green", "yellow", "orange",
         "red", "pink", "purple", "indigo", "brown", "graphite",
         "purewhite", "eyewhite", "glasswhite"]
chk("ACCENT_ORDER 16 色且顺序冻结",
    "var ACCENT_ORDER = [%s];" % ",".join("'%s'" % c for c in ORDER) in s)
chk("16 个可点色点", len(re.findall(r'class="accent-dot[^"]*" data-accent=', s)) == 16,
    str(len(re.findall(r'class="accent-dot[^"]*" data-accent=', s))))
chk("48 条 主题×色 令牌规则",
    len(re.findall(r':root\[data-theme="\w+"\]\[data-accent="\w+"\]', css)) == 48)
chk("每个色点都有 --on-accent（勾的颜色按亮度自动选）",
    css.count("--on-accent:") >= 48, str(css.count("--on-accent:")))
chk("旧偏好 white/black 迁移到 graphite",
    "ACCENT_ALIAS" in s and "graphite" in s.split("ACCENT_ALIAS", 1)[1][:200])
chk("C# ini 白名单含 graphite 且兼容 white/black",
    "graphite" in program and "white" in program and "black" in program)

# ---- 2. 亮色系组件零硬编码色 ----
hard = re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)", css_body)
chk("组件样式零硬编码色（令牌定义段除外）", not hard, str(hard[:6]))
# 令牌要"每套主题都能落到值"，不能只在一个块里定义（另一套主题就会继承到空）。
def theme_tokens(names=("dark", "light", "eye")):
    out = {}
    for th in names:
        acc = set()
        for m in re.finditer(r':root\[data-theme="' + th + r'"\][^{]*\{([^}]*)\}', css):
            acc |= set(x.strip() for x in m.group(1).split(";") if ":" in x)
            acc |= set(re.findall(r"(--[\w-]+)\s*:", m.group(1)))
        out[th] = acc
    return out


TT = theme_tokens()
for tok in ("--v15-edge", "--v15-tabs-bg", "--v15-tab-idle", "--v15fold-a",
            "--v15fold-b", "--v15fold-c", "--swatch-ring", "--swatch-check-shadow"):
    miss = [th for th in ("dark", "light", "eye") if tok not in TT[th]]
    chk("令牌 " + tok + " 三套主题都能落到值", not miss, "缺：" + str(miss))

# ---- 3. 投屏六条指令 ----
DISPLAY = [("主屏投屏", "0"), ("副屏投屏", "4"), ("后排屏投屏", "1"),
           ("HUD 投屏", "3"), ("PHUD-B 投屏", "9"), ("PHUD-C 投屏", "10")]
for nm, did in DISPLAY:
    chk("投屏指令「%s」映射 :scrcpy %s" % (nm, did),
        ("name:'%s'" % nm) in s and ("cmd:':scrcpy %s'" % did) in s)
chk("Prefix 路由 :scrcpy", '"scrcpy"' in prefix and "DoScrcpy" in prefix)
chk("TaskCmds 有 DoScrcpy", "DoScrcpy" in tasks)
chk("scrcpy 支持 6 个屏名（含中文与短名）",
    all(k in tasks for k in ("主屏", "副屏", "后排屏", "PHUD-B", "PHUD-C", "HUD")))
_scrcpy_code = re.sub(r"^\s*//.*$", "", scrcpy, flags=re.M)
chk("--display-id 无条件传（主屏 0 也要传）",
    '" --display-id="' in _scrcpy_code and "if (displayId > 0)" not in _scrcpy_code)
chk("scrcpy 窗口标题带屏名", "--window-title" in scrcpy and "name" in scrcpy)
chk("scrcpy 探测覆盖 winget Packages", "Genymobile.scrcpy" in scrcpy)
chk("scrcpy 读注册表 PATH（装完不用重启）", "ReadEnvFromRegistry" in scrcpy)

# ---- 4. 日志等级 / 设备管理 ----
chk("日志等级五段 V/D/I/W/E",
    all(('data-lv="%s"' % lv) in s for lv in "VDIWE"))
chk("日志等级面板有设备端+本工具两排", 'id="v15-lvdev"' in s and 'id="v15-lvshow"' in s)
for k in ("logget", "logset", "devlist", "devswitch", "devdisconnect"):
    chk("C# 承接消息 " + k, ('case "%s"' % k) in guiweb)
chk("设备列表来自 adb devices -l",
    'argv.Add("devices")' in guiweb and 'argv.Add("-l")' in guiweb)
chk("断开只对 TCP 序列号发 adb disconnect", "adb disconnect" in guiweb)

# ---- 5. 翻页 / 字体 / 主题 ----
chk("翻页两侧 origin 不同（左下角 / 右下角）",
    "transform-origin:left bottom" in css and "transform-origin:right bottom" in css)
chk("翻页有 reduced-motion 降级",
    "prefers-reduced-motion:reduce" in css and "v15-flip-next" in css)
_groups = set(re.findall(r"group:'([^']+)'", s))
chk("字体表七分组（内置/中文系统/中文需装/西文系统/西文需装/等宽/其它）",
    len(_groups) >= 5, str(sorted(_groups)))
chk("字体安装检测用 canvas 测宽", "measureText" in s and "72px monospace" in s)
chk("OLED 纯黑变体", '[data-oled="1"]' in css and "--bg:#000000" in css)
chk("护眼三档", '[data-eyelevel="light"]' in css and '[data-eyelevel="deep"]' in css)
chk("跟随系统主题", "prefers-color-scheme" in s or "sysDark" in s)

# ---- 6. 窗口原生行为 ----
chk("窗口补 WS_MINIMIZEBOX", "WS_MINIMIZEBOX" in guiweb and "CreateParams" in guiweb)
chk("点任务栏兜底（Shell_TrayWnd）", "Shell_TrayWnd" in guiweb)
# A16：窗口不再改尺寸做动画，跟踪下限回到 MinimumSize
chk("最小尺寸跟踪下限回到 MinimumSize",
    "ptMinTrackSize.X = MinimumSize.Width" in guiweb)
chk("A16 开合不再改窗口尺寸（DockRect / PlayOpenAnim 已删）",
    "DockRect" not in guiweb and "PlayOpenAnim" not in guiweb)
chk("A16 有尺寸兜底 EnsureSaneBounds", "EnsureSaneBounds" in guiweb)
chk("原生启动层画新图标（不再是黑猫）",
    "SplashPaint" in guiweb and "DrawLogo" in guiweb and "DrawCat" not in guiweb)
chk("启动层颜色跟随强调色", "AccentColor" in guiweb)

# ---- 7. 搜索框白边 / 下拉浮层 ----
chk("搜索框外壳透明、只有 input 有凹陷面",
    ".qsearch{" in css and "background:transparent" in css
    and ".qsearch input{" in css and "var(--surface-2)" in css)
chk("浮层内滚动不再关闭", "pop.contains(ev.target)" in s)
chk("锚点滚出视口才关（否则重定位）", "repositionPop" in s)

bad = [r for r in rows if not r[1]]
for name, ok, detail in rows:
    sys.stdout.write(("  PASS | " if ok else "  FAIL | ") + name
                     + (("  -> " + detail) if (detail and not ok) else "") + "\n")
sys.stdout.write("\n  A15 落点机检：通过 %d / %d\n" % (len(rows) - len(bad), len(rows)))
sys.exit(1 if bad else 0)
