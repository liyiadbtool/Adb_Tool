# -*- coding: utf-8 -*-
"""本轮出包后专项校验：U1-U6 同步、新 ico、/snap 端点、手册、cmds.ini。"""
import hashlib
import io
import os
import sys
import zipfile

ROOT = r"C:\Users\李亦\Desktop\Adb_Tool"
GUI = os.path.join(ROOT, "adb_log_gui")
RELEASE = os.path.join(ROOT, "release")

fails = []


def rd(p):
    with open(p, "rb") as f:
        return f.read()


def sha(b):
    return hashlib.sha256(b).hexdigest()[:16]


def ck(cond, msg):
    sys.stdout.write(("  [OK]   " if cond else "  [FAIL] ") + msg + "\n")
    if not cond:
        fails.append(msg)


sys.stdout.write("== U1-U4：ui.html 六处副本 ==\n")
u1 = rd(os.path.join(GUI, "webview2", "ui.html"))
sys.stdout.write("U1 源: %d B sha=%s\n" % (len(u1), sha(u1)))
for uid, p in [
    ("U2", os.path.join(GUI, "dist", "webview2", "ui.html")),
    ("U3", os.path.join(GUI, "dist_min", "webview2", "ui.html")),
]:
    ck(os.path.exists(p), uid + " 存在")
    if os.path.exists(p):
        b = rd(p)
        ck(b == u1, uid + " 与 U1 逐字节一致（%d B sha=%s）" % (len(b), sha(b)))

# 单文件版 exe 内嵌 ui.html：资源是原始字节，可直接搜关键新串
exe = rd(os.path.join(GUI, "dist_single", "adb_Tool.exe"))
sys.stdout.write("U4 单文件 exe: %d B sha=%s\n" % (len(exe), sha(exe)))
for token in [b"function castRefreshStripFrames", b"/snap/' + i",
              b"cast-thumb-stop", b"data-search=\"1\"",
              b"var THEME_ORDER = ['dark', 'light', 'eye'];",
              b'--accent:#0a84ff', b"Apple",
              # A15 层：内嵌 ui.html 必须真的带进去，不能只改了源文件忘了嵌
              b"V15 LAYER START", b"V15 JS START",
              b'id="a15-sec-display"', b'id="v15-lvdev"', b'id="v15-devrows"',
              b"v15-flip-next", b"--display-id 10", b":scrcpy 9"]:
    ck(token in exe, "U4 exe 内嵌 ui.html 含 " + token.decode("utf-8", "replace")[:44])
# A12 轮标记：自绘标题栏 / 字体层 / 设置抽屉 / 使用说明 / 文本页
for token in [b"V12 LAYER START", b"V12 FONTS START", b"V12 JS START",
              b'id="titlebar"', b'id="set-mask"', b'id="help-mask"',
              b'id="page-text"', b"fsColDown", b"fsSwapSides"]:
    ck(token in exe, "U4 exe 含 A12 标记 " + token.decode("utf-8", "replace")[:40])
# A13 轮标记：四圆点标题栏 / 即时 tooltip / 终端多行 / 输出区点空白收起
for token in [b"V13 LAYER START", b"V13 JS START",
              b'id="tb-status"', b'id="log-dot"',
              b"fbHeadToggle", b"txAutoGrow", b"tb-tip"]:
    ck(token in exe, "U4 exe 含 A13 标记 " + token.decode("utf-8", "replace")[:40])
# A14 轮标记：网联服务分组 / 自绘下拉浮层 / 字体大小（ZoomFactor）
for token in [b"V14 LAYER START", b"V14 JS START",
              b'id="set-fsize"', b"a14-selpop",
              b"--a14-card-edge", b"--a14-page",
              b"uizoom", b"SIZES"]:
    ck(token in exe, "U4 exe 含 A14 标记 " + token.decode("utf-8", "replace")[:40])
# A16 轮标记：窗口不变形 / 弹窗 portal + 互斥 / 16 色 / 投屏 JPEG / tab 拖拽 / 9 条 adb
for token in [b"V16 LAYER START", b"V16 JS START",
              b"EnsureSaneBounds", b"RefreshSane",
              b"popCur", b"anyPopOpen", b"closeAllPops",
              b"purewhite", b"eyewhite", b"glasswhite",
              b"v16QuickInput", b"v16-tabdrag", b"castOpenScrcpy",
              b"CastGrabRaw", b"CastEncodeJpeg"]:
    ck(token in exe, "U4 exe 含 A16 标记 " + token.decode("utf-8", "replace")[:40])
# A17 轮标记：黑白灰图标 / 开合动效 / 强调色记忆 / 浅色边界 / 关闭看门狗 / scrcpy 内嵌
for token in [b"V17 LAYER START", b"V17 JS START",
              b"appmark-glyph", b"appmark-bg",
              b"ce-stage", b"cast-embed", b"cm-embed",
              b"v17CastEmbed", b"v17CastBuiltin", b"v17CastEmbedFail",
              b"StartExitWatchdog", b"ScrcpyEmbedPlace", b"LaunchEmbedded",
              b"v17open", b"winedge"]:
    ck(token in exe, "U4 exe 含 A17 标记 " + token.decode("utf-8", "replace")[:40])
# 无边框是代码而非字符串常量，不能靠搜 exe 字节；改为核源码 + 真机行为（_smoke_win.py 另有 12 项）
_gw = rd(os.path.join(ROOT, "_cs", "GuiWeb.cs"))
ck(b"FormBorderStyle.None" in _gw, "C# 源已设无边框（FormBorderStyle.None）")
ck(b"WM_NCLBUTTONDOWN" in _gw, "C# 源含原生拖动（WM_NCLBUTTONDOWN + HTCAPTION）")
ck(b"MaximizedBounds" in _gw, "C# 源含最大化工作区约束")
# A13：跨屏最大化改成每次 WM_GETMINMAXINFO 实时算（MaximizedBounds 会在 OnLoad 缓存笔记本屏尺寸）
ck(b"WM_GETMINMAXINFO" in _gw, "C# 源含跨屏最大化（WM_GETMINMAXINFO 按当前屏工作区回答）")
# A13：圆角双轨 —— Win11 走 DWM 抗锯齿，Win10 走 SetWindowRgn 兜底
ck(b"DWMWA_WINDOW_CORNER_PREFERENCE" in _gw, "C# 源含 Win11 DWM 圆角（DWMWA_WINDOW_CORNER_PREFERENCE）")
ck(b"SetWindowRgn" in _gw, "C# 源含 Win10 圆角兜底（SetWindowRgn）")
ck(b"/snap/" in exe, "U4 exe 含新编译的 /snap 端点（C# Cast.cs）")

sys.stdout.write("\n== ICO-01/02/03：应用图标 ==\n")
ico1 = rd(os.path.join(GUI, "adb_Tool.ico"))
ico2 = rd(os.path.join(GUI, "icons", "adb_Tool.ico"))
ck(ico1 == ico2, "源两份 ico 字节一致（%d B sha=%s）" % (len(ico1), sha(ico1)))
for name, p in [
    ("完整版", os.path.join(GUI, "dist", "adb_Tool.ico")),
    ("最小版", os.path.join(GUI, "dist_min", "adb_Tool.ico")),
    ("单文件版", os.path.join(GUI, "dist_single", "adb_Tool.ico")),
]:
    ck(os.path.exists(p) and rd(p) == ico1, name + " 外置 ico 与源一致")

sys.stdout.write("\n== 配置与手册 ==\n")
src_ini = rd(os.path.join(ROOT, "cmds.ini"))
for name, p in [
    ("打包源", os.path.join(GUI, "cmds.ini")),
    ("完整版", os.path.join(GUI, "dist", "cmds.ini")),
    ("最小版", os.path.join(GUI, "dist_min", "cmds.ini")),
]:
    ck(os.path.exists(p) and rd(p) == src_ini, name + " cmds.ini 与项目根一致")
ck(b"[cmd.stweak]" in exe, "单文件 exe 内嵌默认 ini 含 stweak")

manual = rd(os.path.join(ROOT, "docs", "用户使用手册.md"))
for t in [u"Apple UI 全面替换", u"16. Apple UI", u"/snap/", u"单击结果行",
          u"## 20. 设置面板", u"## 21. 使用说明面板", u"## 22. 文本页",
          u"JetBrains Mono", u"编码原样保留"]:
    ck(t.encode("utf-8") in manual, "源手册含「%s」" % t)

sys.stdout.write("\n== 三个 zip ==\n")
def _latest_zip(kind):
    """按 kind 找最新的 zip，不硬编码日期。

    原来这里写死 `..._20261115.zip`，出包日期一变就整段红 —— 那是测试的 bug 不是包的 bug。
    A17 顺手修掉：A17 之后 zip 名也去掉了「网联服务_」前缀，所以匹配用 Adb_Tool_<kind>_*.zip。
    """
    import glob
    cand = sorted(glob.glob(os.path.join(RELEASE, "Adb_Tool_%s_*.zip" % kind)))
    if not cand:                       # 兼容旧包（改动前生成的）
        cand = sorted(glob.glob(os.path.join(RELEASE, "*Adb_Tool_%s_*.zip" % kind)))
    return cand[-1] if cand else ""


for name, kind, need_ini, need_ffmpeg in [
    ("完整版", "完整版", True, True),
    ("最小版", "最小版", True, False),
    ("单文件版", "单文件版", False, False),
]:
    p = _latest_zip(kind)
    if not os.path.exists(p):
        ck(False, name + " zip 存在")
        continue
    with zipfile.ZipFile(p) as z:
        names = z.namelist()
        sys.stdout.write("  %s: %d 个文件 / %.2f MB\n" %
                         (name, len(names), os.path.getsize(p) / 1048576.0))
        ck("adb_Tool.exe" in names, name + " 含 adb_Tool.exe")
        ck("使用手册.md" in names, name + " 含 使用手册.md")
        if need_ini:
            # 2026-11-19：发布包改成 exe + internal\ + log\ 的结构，
            # 老包（平铺 / webview2\）仍然兼容，两种路径都认。
            ini_rel = "internal/cmds.ini" if "internal/cmds.ini" in names else "cmds.ini"
            ui_rel = "internal/ui.html" if "internal/ui.html" in names else "webview2/ui.html"
            ico_rel = "internal/adb_Tool.ico" if "internal/adb_Tool.ico" in names else "adb_Tool.ico"
            ck(ini_rel in names and z.read(ini_rel) == src_ini,
               name + " 内 cmds.ini 与源一致（" + ini_rel + "）")
            ck(ui_rel in names and z.read(ui_rel) == u1,
               name + " 内 ui.html 与 U1 一致（" + ui_rel + "）")
            ck(ico_rel in names and z.read(ico_rel) == ico1,
               name + " 内 ico 与源一致（" + ico_rel + "）")
        if need_ffmpeg:
            ck("ffmpeg.exe" in names, name + " 含 ffmpeg.exe")
        if "使用手册.md" in names:
            m = z.read("使用手册.md")
            ck(u"Apple UI 全面替换".encode("utf-8") in m, name + " 内手册为 Apple 版")
            ck(u"16. Apple UI".encode("utf-8") in m, name + " 内手册含 §16")
            # A15（2026-11-15 第四批）：手册必须带上本轮的「显示选项 / 日志等级 /
            # 设备管理 / 投屏指令」四块，否则用户拿到包不知道这些功能存在。
            ck(u"26. 显示选项".encode("utf-8") in m, name + " 内手册含 §26（A15）")
            # A16（2026-11-15 第五批）：窗口变形 / 弹窗互斥 / 投屏提速 / 偏好记忆 / tab 拖拽
            ck(u"27. 窗口变形".encode("utf-8") in m, name + " 内手册含 §27（A16）")
            # A17（2026-11-15 第六批）：图标重做 / 开合动效 / 强调色记忆 / 内嵌投屏
            ck(u"28. 图标重做".encode("utf-8") in m, name + " 内手册含 §28（A17）")

sys.stdout.write("\n结论：%s（%d 项失败）\n" %
                 ("全部通过" if not fails else "有失败", len(fails)))
raise SystemExit(0 if not fails else 1)
