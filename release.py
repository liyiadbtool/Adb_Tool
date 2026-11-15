# -*- coding: utf-8 -*-
"""一键出两个交付物：本地可运行包 + 可直接分享的压缩包。

用法（在项目根目录）：
    python release.py             # 编译 → 全量检查 → 完整包 + 最小包 → 两个 zip
    python release.py --no-build  # 不重新编译，只打包（改完 UI 想快速出包时用）
    python release.py --no-verify # 跳过 verify_all（应急用，交付前必须补跑）

为什么默认要跑 verify_all：
    单项测试全绿、但整页空白的事故发生过（#page-file 插错父容器）。
    规则写进 docs/项目规则.md 只能靠人记，挂在打包入口才真的执行。

产出：
    adb_log_gui\\dist\\                          本地完整包（含 ffmpeg，可录屏）
    adb_log_gui\\dist_min\\                      最小包（不含 ffmpeg）
    adb_log_gui\\dist_single\\                   单文件版（只有一个 exe，资源全内嵌）
    release\\网联服务_Adb_Tool_完整版_<日期>.zip   分享用（含 ffmpeg，~100MB）
    release\\网联服务_Adb_Tool_最小版_<日期>.zip   分享用（~0.4MB）
    release\\网联服务_Adb_Tool_单文件版_<日期>.zip 单文件版（~1.4MB）

为什么又多一个单文件版：
    最小版仍然是"exe + 3 个 dll + webview2\\ui.html + 2 个 ini"，发给别人时
    经常出现只拷了 exe，双击没反应/白屏。单文件版把 dll、界面、默认配置
    全部编进 exe（见 _cs/Embed.cs），拷一个文件就能跑。ffmpeg 依旧外置
    （105MB 不可能打进去），需要录屏的人点「投屏」页的「选择…」指一下即可。

为什么两个 zip：
    完整版给"要录屏的同事"，最小版给"只要命令/日志/APK 的人"。
    两者解压即用，都不需要装 .NET（系统自带）。

为什么不把 ffmpeg 打进最小包：
    它一个文件就 105MB，占整个包的 99%。而录屏只是可选功能，
    缺了它程序会在点"一键录屏"时明确提示，其它功能完全不受影响。
"""
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
GUI = os.path.join(ROOT, "adb_log_gui")
DIST = os.path.join(GUI, "dist")
DIST_MIN = os.path.join(GUI, "dist_min")
DIST_SINGLE = os.path.join(GUI, "dist_single")
RELEASE = os.path.join(ROOT, "release")
MANUAL = os.path.join(ROOT, "docs", "用户使用手册.md")

TAG = datetime.now().strftime("%Y%m%d")


def run(cmd, cwd, what):
    print("[build] %s ..." % what)
    env = dict(os.environ)
    env["NO_PAUSE"] = "1"
    # build_gui.bat / make_min.bat 末尾有 pause，NO_PAUSE=1 时会被替换成 rem
    p = subprocess.run("cmd /c " + cmd, cwd=cwd, env=env,
                       capture_output=True, text=True, encoding="gbk", errors="replace")
    out = (p.stdout or "") + (p.stderr or "")
    if p.returncode != 0 or "ERROR" in out.upper():
        print(out[-1500:])
        raise SystemExit("[ERROR] %s 失败（退出码 %s）" % (what, p.returncode))
    for line in out.splitlines():
        if "Compile success" in line or "Package ready" in line or "Minimal package ready" in line:
            print("        " + line.strip())


def put_manual(folder):
    """把手册以中文名放进包里；顺手删掉旧的 manual.md（如果有）。"""
    if not os.path.isdir(folder):
        return
    if os.path.exists(MANUAL):
        shutil.copy2(MANUAL, os.path.join(folder, "使用手册.md"))
    old = os.path.join(folder, "manual.md")
    if os.path.exists(old):
        os.remove(old)


def build_single():
    """单文件版：只放一个 exe + 手册。资源都在 exe 里（R8）。"""
    src_exe = os.path.join(DIST, "adb_Tool.exe")
    if not os.path.exists(src_exe):
        raise SystemExit("[ERROR] 缺少 %s，请先编译" % src_exe)
    if os.path.isdir(DIST_SINGLE):
        shutil.rmtree(DIST_SINGLE)
    os.makedirs(DIST_SINGLE)
    shutil.copy2(src_exe, os.path.join(DIST_SINGLE, "adb_Tool.exe"))
    # 2026-11-15：窗口图标走外置优先（GuiWeb.cs TrySetCatIcon 读 exe 同级 ico）。
    # 单文件版虽然把资源都编进 exe，也要带上这份外置 ico，保证四处同源。
    ico = os.path.join(GUI, "adb_Tool.ico")
    if os.path.isfile(ico):
        shutil.copy2(ico, os.path.join(DIST_SINGLE, "adb_Tool.ico"))
    put_manual(DIST_SINGLE)
    return DIST_SINGLE


def make_zip(src, zip_path, rename=None):
    if os.path.exists(zip_path):
        os.remove(zip_path)
    n = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(src):
            for f in files:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, src).replace("\\", "/")
                if rename and rel in rename:
                    rel = rename[rel]
                z.write(full, rel)
                n += 1
    return n


def folder_size(path):
    total = 0
    for root, dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def mb(n):
    return "%.2f MB" % (n / 1048576.0)


def main():
    no_build = "--no-build" in sys.argv

    if not no_build:
        run("build_gui.bat", GUI, "编译 GUI + 打完整包 dist")
        run("make_min.bat", GUI, "打最小包 dist_min")
    else:
        print("[skip] --no-build：沿用现有 dist / dist_min")

    # ---- 全量检查门禁：不通过就不打包 ----
    if "--no-verify" in sys.argv:
        print("[skip] --no-verify：跳过全量检查（交付前请补跑 python verify_all.py）")
    else:
        print("[verify] 跑 verify_all.py（编译列表 / 功能清单 / 结构 / 10 套件 / 双自检）…")
        p = subprocess.run([sys.executable, os.path.join(ROOT, "verify_all.py")],
                           cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        # 只打最后三行会丢掉具体是哪一项红的 —— 失败时把完整输出落到文件里，
        # 排查时不用再"手跑一遍看看能不能复现"（往往就复现不出来了）。
        vlog = os.path.join(ROOT, "_release_verify.log")
        try:
            with open(vlog, "w", encoding="utf-8") as f:
                f.write(p.stdout or "")
                if p.stderr:
                    f.write("\n--- stderr ---\n" + p.stderr)
        except Exception:
            vlog = None
        tail = [l for l in (p.stdout or "").splitlines() if l.strip()][-3:]
        for l in tail:
            print("        " + l)
        if p.returncode != 0:
            print("")
            if vlog:
                print("  完整输出已写入：%s" % vlog)
            print("  检查未通过，已中止打包。完整输出：python verify_all.py")
            raise SystemExit("[ERROR] verify_all 失败")

    for folder in (DIST, DIST_MIN):
        if not os.path.isdir(folder):
            raise SystemExit("[ERROR] 缺少目录 %s，请先不带 --no-build 跑一次" % folder)
        put_manual(folder)

    build_single()

    os.makedirs(RELEASE, exist_ok=True)

    full_zip = os.path.join(RELEASE, "网联服务_Adb_Tool_完整版_%s.zip" % TAG)
    min_zip = os.path.join(RELEASE, "网联服务_Adb_Tool_最小版_%s.zip" % TAG)
    single_zip = os.path.join(RELEASE, "网联服务_Adb_Tool_单文件版_%s.zip" % TAG)

    print("[pack] 完整版 zip ...")
    make_zip(DIST, full_zip)
    print("[pack] 最小版 zip ...")
    make_zip(DIST_MIN, min_zip, rename={"manual.md": "使用手册.md"})
    print("[pack] 单文件版 zip ...")
    make_zip(DIST_SINGLE, single_zip)

    # 顺手把上一次日期的旧包清掉，避免 release 目录越堆越乱
    for f in os.listdir(RELEASE):
        p = os.path.join(RELEASE, f)
        if not os.path.isfile(p) or not f.endswith(".zip"):
            continue
        if f in (os.path.basename(full_zip), os.path.basename(min_zip),
                 os.path.basename(single_zip)):
            continue
        try:
            os.remove(p)
        except OSError:
            pass

    rows = [
        ("本地完整包（含 ffmpeg）", DIST, folder_size(DIST), None),
        ("本地最小包（不含 ffmpeg）", DIST_MIN, folder_size(DIST_MIN), None),
        ("分享：完整版 zip", full_zip, os.path.getsize(full_zip), None),
        ("分享：最小版 zip", min_zip, os.path.getsize(min_zip), None),
        ("本地单文件版（仅 exe）", DIST_SINGLE, folder_size(DIST_SINGLE), None),
        ("分享：单文件版 zip", single_zip, os.path.getsize(single_zip), None),
    ]

    print("")
    print("=" * 72)
    print("交付物（%s）" % datetime.now().strftime("%Y-%m-%d %H:%M"))
    print("-" * 72)
    for name, path, size, _ in rows:
        print("  %-26s %10s  %s" % (name, mb(size), path))
    print("=" * 72)
    print("  本地使用：双击 dist\\adb_Tool.exe")
    print("  分享给同事：优先发 单文件版 zip（一个 exe，最不容易出错）")
    print("              需要开箱即用录屏的发 完整版 zip（内含 ffmpeg）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
