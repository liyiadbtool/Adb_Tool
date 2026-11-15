# -*- coding: utf-8 -*-
"""verify_handoff.py —— 交接包自检：环境够不够 + 文件全不全 + 哈希对不对。

用法（在项目根目录）：
    python AI_HANDOFF\\verify_handoff.py
    python AI_HANDOFF\\verify_handoff.py --fast     # 只检查，不跑 node 静态检查

退出码：0 = 全部必需项通过；1 = 有必需项缺失（会逐条说怎么办）。

为什么要有这个脚本：
    换机器最耗时的不是"跑不起来"，而是"不知道缺什么、也不知道缺了会怎样"。
    这里把每个依赖的**用途**和**缺失后果**都写出来，按提示装就行。
"""
import os
import platform
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HANDOFF = os.path.join(ROOT, "AI_HANDOFF")

ok_list = []
bad_list = []
warn_list = []


def ok(name, detail=""):
    ok_list.append((name, detail))


def bad(name, detail, fix):
    bad_list.append((name, detail, fix))


def warn(name, detail, fix):
    warn_list.append((name, detail, fix))


# ---------------------------------------------------------------- 1. 文件完整性

REQUIRED = [
    "verify_all.py",
    "release.py",
    "_check_build_list.js",
    "_check_features.js",
    "_check_features.json",
    "_cs/build.bat",
    "_cs/GuiWeb.cs",
    "_cs/GuiEntry.cs",
    "_cs/Embed.cs",
    "_cs/FileBrowser.cs",
    "_cs/Cast.cs",
    "_cs/Ffmpeg.cs",
    "_cs/Scrcpy.cs",
    "_cs/Render.cs",
    "_cs/Program.cs",
    "adb_log_gui/build_gui.bat",
    "adb_log_gui/make_min.bat",
    "adb_log_gui/webview2/ui.html",
    "adb_log_gui/webview2/Microsoft.Web.WebView2.Core.dll",
    "adb_log_gui/webview2/Microsoft.Web.WebView2.WinForms.dll",
    "adb_log_gui/webview2/WebView2Loader.dll",
    "adb_log_gui/adb_log_export.ini",
    "adb_log_gui/cmds.ini",
    "377/_test_file_ui.py",
    "377/_test_fs_search.py",
    "377/_test_cast_ui.py",
    "377/_check_ui.js",
    "docs/项目规则.md",
    "docs/用户使用手册.md",
    "docs/功能清单.md",
]


LATIN_HINT = set("\u00c0\u00c1\u00c2\u00c3\u00c4\u00c5\u00c6\u00c7\u00c8\u00c9\u00ca\u00cb"
                 "\u00cc\u00cd\u00ce\u00cf\u00d0\u00d1\u00d2\u00d3\u00d4\u00d5\u00d6\u00d8"
                 "\u00d9\u00da\u00db\u00dc\u00dd\u00de\u00df\u00e0\u00e1\u00e2\u00e3\u00e4"
                 "\u00e5\u00e6\u00e7\u00e8\u00e9\u00ea\u00eb\u00ec\u00ed\u00ee\u00ef\u00f0"
                 "\u00f1\u00f2\u00f3\u00f4\u00f5\u00f6\u00f8\u00f9\u00fa\u00fb\u00fc\u00fd")


def detect_mojibake():
    """识别"中文文件名被解压工具按 CP437/单字节解释成乱码"的情况。

    真实场景：Git Bash 的 unzip 不认 zip 里的 UTF-8 标记，会把
    docs\用户使用手册.md 解成 ÓÃ»§Ê¹ÓÃÊÖ²á.md —— 之后所有按路径找文件的检查都失败，
    但错误信息只会说"文件缺失"，人会以为包坏了。这里直接把原因点出来。
    """
    suspects = []
    for d in ("", "docs", "AI_HANDOFF", ".workbuddy"):
        base = os.path.join(ROOT, d) if d else ROOT
        if not os.path.isdir(base):
            continue
        for name in os.listdir(base):
            if not name.lower().endswith((".md", ".ini", ".py")):
                continue
            if any(ch in LATIN_HINT for ch in name):
                suspects.append(os.path.join(d, name) if d else name)
    if suspects:
        bad("文件名编码", "疑似中文文件名被解压工具打乱：%s" % ", ".join(suspects[:3]),
            "用 Windows 资源管理器 / 7-Zip 重新解压；"
            "不要用 Git Bash 的 unzip。已有目录可直接跑："
            "python -c \"import zipfile;zipfile.ZipFile(r'包.zip').extractall('.')\"")
    else:
        ok("文件名编码", "中文文件名正常")


def check_files():
    missing = []
    for rel in REQUIRED:
        p = os.path.join(ROOT, rel.replace("/", os.sep))
        if not os.path.exists(p):
            missing.append(rel)
    if missing:
        bad("关键文件", "缺 %d 个：%s" % (len(missing), ", ".join(missing[:6])),
            "重新解压完整包（不要只拷 exe / 只拷 _cs 目录）")
    else:
        ok("关键文件", "29 个必需文件齐全")

    # ui.html 大小兜底：被截断/被替换成占位页时最容易发现
    ui = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
    if os.path.exists(ui):
        mb = os.path.getsize(ui) / 1024.0
        if mb < 100:
            bad("ui.html", "只有 %.0f KB（正常约 250 KB）" % mb,
                "ui.html 不完整，重新解压；它被截断时表现为界面白屏")
        else:
            ok("ui.html", "%.0f KB" % mb)

    detect_mojibake()


# ---------------------------------------------------------------- 2. 工具链

def check_python():
    v = sys.version.split()[0]
    if sys.version_info < (3, 6):
        bad("Python", "版本 %s 太旧" % v, "装 3.9+（测试脚本与打包脚本都用它）")
    else:
        ok("Python", v)


def check_node():
    exe = shutil.which("node")
    if not exe:
        bad("Node.js", "找不到 node",
            "装 Node 18+；只用于静态检查（编译列表/功能清单/ui.html 自检），"
            "不装则 verify_all 里那 3 项必定失败")
        return
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20)
        ok("Node.js", (r.stdout or "").strip())
    except Exception as e:
        warn("Node.js", "存在但运行异常：%s" % e, "重装 Node")


def check_csc():
    cands = [
        r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
        r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe",
    ]
    for c in cands:
        if os.path.exists(c):
            ok("csc 编译器", c)
            return
    bad(".NET Framework 4.x", "找不到 csc.exe",
        "启用 .NET Framework 4.x（Win10/11 一般自带；被精简的系统需手动装）")


def check_edge():
    cands = []
    for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            cands.append(os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"))
    cands.append(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
    for c in cands:
        if os.path.exists(c):
            ok("Microsoft Edge", c)
            return
    bad("Microsoft Edge", "找不到 msedge.exe",
        "装 Edge（11 个 DOM 测试套件靠它无头跑；测试脚本会自动找，不用改代码）")


def check_webview2():
    """WebView2 Runtime：注册表里两个位置任一有 pv 即可。没有则界面起不来。"""
    try:
        import winreg
    except Exception:
        warn("WebView2 Runtime", "无法检查（非 Windows 或 winreg 不可用）", "确认已装 Evergreen Runtime")
        return

    keys = [
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
        (winreg.HKEY_CURRENT_USER,
         r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
    ]
    for root, path in keys:
        try:
            with winreg.OpenKey(root, path) as k:
                pv, _ = winreg.QueryValueEx(k, "pv")
                if pv:
                    ok("WebView2 Runtime", str(pv))
                    return
        except Exception:
            continue
    bad("WebView2 Runtime", "注册表里没找到",
        "装 Microsoft Edge WebView2 Runtime（Evergreen，约 2MB 安装器）；"
        "缺了的表现是双击后白屏或窗口一闪")


def check_adb():
    exe = shutil.which("adb")
    if not exe:
        warn("adb", "PATH 里没有 adb",
             "把 adb 放进 PATH，或在 adb_log_export.ini 里配 adb=完整路径；"
             "没有它程序能启动，但所有设备功能不可用")
        return
    ok("adb", exe)


def check_ffmpeg_scrcpy():
    """可选组件：只影响录屏/流畅投屏，不影响编译与测试。"""
    for name in ("ffmpeg.exe", "scrcpy.exe"):
        found = None
        p = os.path.join(ROOT, name)
        if os.path.exists(p):
            found = p
        else:
            found = shutil.which(name)
        if found:
            ok(name + "（可选）", found)
        else:
            warn(name + "（可选）", "未找到",
                 "不影响编译/测试；需要录屏 → 投屏页「选择…」指定 ffmpeg；"
                 "需要流畅投屏 → 指定 scrcpy")


# ---------------------------------------------------------------- 2.5 构建产物

def check_build_outputs():
    """两个 exe 是编译产物，交接包里不带。第一次跑 verify_all 前必须先编出来，
    否则「CLI 自检」一项必定失败（那不代表包坏了）。"""
    cli = os.path.join(ROOT, "adb_log_export.exe")
    gui = os.path.join(ROOT, "adb_log_gui", "adb_Tool.exe")
    gui_new = os.path.join(ROOT, "adb_log_gui", "adb_Tool_new.exe")

    if os.path.exists(cli):
        ok("CLI 已编译", "%.0f KB" % (os.path.getsize(cli) / 1024.0))
    else:
        warn("CLI 未编译", "adb_log_export.exe 不存在",
             "先跑 _cs\\build.bat 编出 CLI（verify_all 的「CLI 自检」需要它）")

    gui_bin = gui if os.path.exists(gui) else (gui_new if os.path.exists(gui_new) else None)
    if gui_bin:
        mb = os.path.getsize(gui_bin) / 1048576.0
        if mb < 1.0:
            bad("GUI 体积可疑", "%.2f MB（含内嵌资源应约 1.4 MB）" % mb,
                "重新编译 GUI；300KB 左右说明 /resource 段没生效")
        else:
            ok("GUI 已编译", "%.2f MB · %s" % (mb, os.path.basename(gui_bin)))
    else:
        warn("GUI 未编译", "adb_log_gui\\adb_Tool.exe 不存在",
             "先跑 adb_log_gui\\build_gui.bat（记得带 NO_PAUSE=1）")


# ---------------------------------------------------------------- 3. 哈希校验

def check_manifest():
    import hashlib
    import json

    mf = os.path.join(HANDOFF, "MANIFEST.json")
    if not os.path.exists(mf):
        warn("MANIFEST", "没有清单文件", "运行 python AI_HANDOFF\\make_manifest.py 生成（可选）")
        return
    try:
        data = json.load(open(mf, encoding="utf-8"))
    except Exception as e:
        warn("MANIFEST", "读取失败：%s" % e, "重新生成清单")
        return

    files = data.get("files", [])
    bad_files = []
    for item in files:
        rel = item.get("path", "")
        p = os.path.join(ROOT, rel.replace("/", os.sep))
        if not os.path.exists(p):
            bad_files.append(rel + "（缺失）")
            continue
        h = hashlib.sha256()
        try:
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
        except Exception:
            bad_files.append(rel + "（读不了）")
            continue
        if item.get("sha256") and h.hexdigest() != item["sha256"]:
            bad_files.append(rel + "（内容不一致）")

    if bad_files:
        bad("MANIFEST 哈希", "%d 个文件不一致：%s" % (len(bad_files), ", ".join(bad_files[:5])),
            "文件被改过或没拷全；如果是你自己改的代码，重新生成清单即可")
    else:
        ok("MANIFEST 哈希", "%d 个文件一致" % len(files))


# ---------------------------------------------------------------- 4. 静态检查（可选）

def run_static():
    checks = [
        ("编译列表", [shutil.which("node") or "node", os.path.join(ROOT, "_check_build_list.js")]),
        ("功能清单", [shutil.which("node") or "node", os.path.join(ROOT, "_check_features.js")]),
        ("ui.html 自检", [shutil.which("node") or "node", os.path.join(ROOT, "377", "_check_ui.js")]),
    ]
    for name, cmd in checks:
        cwd = os.path.dirname(cmd[1])
        try:
            r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=120)
            if r.returncode == 0:
                ok("静态检查 · " + name)
            else:
                tail = (r.stdout or r.stderr or "").strip().splitlines()[-1:] or [""]
                bad("静态检查 · " + name, tail[0], "看完整输出：node %s" % os.path.basename(cmd[1]))
        except Exception as e:
            warn("静态检查 · " + name, "跑不起来：%s" % e, "确认 node 可用")


# ---------------------------------------------------------------- 输出

def main():
    fast = "--fast" in sys.argv

    print("=" * 74)
    print("  交接包自检 · %s" % platform.platform())
    print("  项目根目录：%s" % ROOT)
    print("=" * 74)

    print("\n[1/4] 文件完整性")
    check_files()

    print("\n[2/4] 工具链")
    check_python()
    check_node()
    check_csc()
    check_edge()
    check_webview2()
    check_adb()
    check_ffmpeg_scrcpy()

    print("\n[2.5/4] 构建产物")
    check_build_outputs()

    print("\n[3/4] 哈希校验")
    check_manifest()

    if fast:
        print("\n[4/4] 静态检查（--fast 已跳过）")
    else:
        print("\n[4/4] 静态检查")
        run_static()

    # 汇总
    print("\n" + "-" * 74)
    for n, d in ok_list:
        print("  [OK]   %-22s %s" % (n, d))

    for n, d, fix in warn_list:
        print("  [!!]   %-22s %s" % (n, d))
        print("         → %s" % fix)

    for n, d, fix in bad_list:
        print("  [XX]   %-22s %s" % (n, d))
        print("         → %s" % fix)

    print("-" * 74)
    print("  通过 %d 项 / 警告 %d 项 / 必须修 %d 项" %
          (len(ok_list), len(warn_list), len(bad_list)))

    if bad_list:
        print("\n  先修上面标 [XX] 的项，再执行：python verify_all.py")
        return 1

    print("\n  环境就绪。下一步（顺序不能反）：")
    print("    1) cd _cs && build.bat                （编 CLI，自检需要）")
    print("    2) cd ..\\adb_log_gui && build_gui.bat （编 GUI，记得 NO_PAUSE=1）")
    print("    3) cd .. && python verify_all.py      （必须 16 项 0 失败）")
    print("    4) python release.py                  （出 3 个包）")
    print("    5) 把 AI_HANDOFF/01_AI_PROMPT.md 第 1 节发给 AI")
    return 0


if __name__ == "__main__":
    sys.exit(main())
