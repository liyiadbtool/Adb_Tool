# -*- coding: utf-8 -*-
"""make_handoff.py —— 生成「AI 交接包」：可移植的源码 + 文档 + 提示词 + 自检脚本。

为什么要这个脚本而不是手工拷：
    手工拷必然会有一次漏掉某个 .cs 或某个 ini，然后换机器编译失败、
    或者更糟——编译"成功"但某个文件没参与编译（真出过）。
    这里用显式白名单 + 排除规则，保证每次打出来的包内容一致、可复现。

用法（项目根目录）：
    python make_handoff.py                # 生成 AI_HANDOFF 清单 + release/AI交接包_<日期>.zip
    python make_handoff.py --no-zip       # 只准备目录，不打 zip

产物：
    release/AI交接包_Adb_Tool_<日期>.zip
        解压后就是一个能直接编译的完整项目，根目录里多了 AI_HANDOFF/ 教程与提示词。

包含：_cs / docs / 377（测试脚本）/ adb_log_gui（构建脚本+webview2+ini）/ AI_HANDOFF / .workbuddy/memory / 根目录脚本与配置
排除：exe、dll（除了 WebView2 SDK 必需的那几个）、zip、dist*、release、ffmpeg、日志样本、另一子项目 SynTestLite
"""
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
STAGE = os.path.join(ROOT, "release", "_handoff_stage")
RELEASE = os.path.join(ROOT, "release")
TAG = datetime.now().strftime("%Y%m%d")

SKIP_DIR_NAMES = {
    "dist", "dist_min", "dist_single", "release", "__pycache__", "node_modules",
    ".git", "_shots", "377", "syntest_rebuild", "ui_draft", "build", "build_cli",
}
SKIP_EXT = {".exe", ".zip", ".zst", ".png", ".jpg", ".jpeg", ".gif", ".log",
            ".pdb", ".obj", ".tmp"}
# 需要保留的 dll（编译引用 / 运行加载），其余 dll 一律不带
KEEP_DLL = {
    "microsoft.web.webview2.core.dll",
    "microsoft.web.webview2.winforms.dll",
    "webview2loader.dll",
}

ROOT_FILES = [
    "verify_all.py", "release.py", "make_handoff.py",
    "_check_build_list.js", "_check_features.js", "_check_features.json", "_check.js",
    "adb_log_export.ini", "cmds.ini", "adb_log_export.bat", "release.bat",
    "adb_send_chinese.bat", "adb_send_chinese.ini",
    "HANDOFF.md",
    "docs/项目规则.md", "docs/功能清单.md", "docs/用户使用手册.md",
    "docs/AI协作指南_提示语与实现步骤.md",
    # 以下是需求/分析的背景资料，AI 读了对"为什么这么做"有帮助
    "需求与架构梳理_20261102.md", "需求讨论纪要.md",
    "SynTestUtil功能逆向与需求源_20261103.md", "SynTestUtil源码级解析_20261104.md",
    "息屏唤醒输入失效_分析与修复_20261104.md",
]

DIRS = ["_cs", "docs", "377", os.path.join("adb_log_gui", "webview2"),
        "adb_log_gui", "AI_HANDOFF", os.path.join(".workbuddy", "memory")]

# 377 下额外排除"生成物"
SKIP_FILE_PREFIX = ("test_",)      # 377/test_*.html 是跑测试时生成的页面
SKIP_FILE_SUFFIX = (".html",)


def keep_file(full, rel):
    name = os.path.basename(full).lower()
    ext = os.path.splitext(name)[1]
    if ext in SKIP_EXT:
        return False
    if ext == ".dll" and name not in KEEP_DLL:
        return False
    # 377 目录里只带脚本，不带生成的测试页
    rel_norm = rel.replace("\\", "/")
    if rel_norm.startswith("377/") and name.endswith(SKIP_FILE_SUFFIX):
        return False
    if rel_norm.startswith("377/") and name.startswith(SKIP_FILE_PREFIX) and name.endswith(".html"):
        return False
    return True


def copy_tree(src_dir, dst_dir, rel_base):
    for cur, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIR_NAMES]
        for f in files:
            full = os.path.join(cur, f)
            rel = os.path.relpath(full, ROOT)
            if not keep_file(full, rel):
                continue
            target = os.path.join(dst_dir, os.path.relpath(full, src_dir))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(full, target)


def main():
    no_zip = "--no-zip" in sys.argv

    if os.path.isdir(STAGE):
        shutil.rmtree(STAGE)
    os.makedirs(STAGE)

    print("[1/4] 复制源码与文档 ...")
    for rel in ROOT_FILES:
        src = os.path.join(ROOT, rel.replace("/", os.sep))
        if not os.path.exists(src):
            print("        [skip] 缺失 %s" % rel)
            continue
        dst = os.path.join(STAGE, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)

    for d in DIRS:
        src = os.path.join(ROOT, d)
        if not os.path.isdir(src):
            print("        [skip] 缺失目录 %s" % d)
            continue
        copy_tree(src, os.path.join(STAGE, d), d)

    print("[2/4] 生成 MANIFEST.json ...")
    mf = os.path.join(STAGE, "AI_HANDOFF", "make_manifest.py")
    if os.path.exists(mf):
        r = subprocess.run([sys.executable, mf], cwd=STAGE,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        print("        " + (r.stdout or r.stderr or "").strip().replace("\n", "\n        "))
    else:
        print("        [WARN] 没有 make_manifest.py，跳过清单")

    # 统计
    total = 0
    n = 0
    for cur, dirs, files in os.walk(STAGE):
        for f in files:
            total += os.path.getsize(os.path.join(cur, f))
            n += 1
    print("[3/4] 暂存目录：%d 个文件，%.2f MB" % (n, total / 1048576.0))

    if no_zip:
        print("       --no-zip：跳过打包。目录：%s" % STAGE)
        return 0

    zip_path = os.path.join(RELEASE, "AI交接包_Adb_Tool_%s.zip" % TAG)
    if os.path.exists(zip_path):
        os.remove(zip_path)
    print("[4/4] 打 zip ...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for cur, dirs, files in os.walk(STAGE):
            for f in files:
                full = os.path.join(cur, f)
                rel = os.path.relpath(full, STAGE).replace("\\", "/")
                z.write(full, rel)

    print("")
    print("=" * 72)
    print("  交接包：%s" % zip_path)
    print("  体积  ：%.2f MB（%d 个文件）" % (os.path.getsize(zip_path) / 1048576.0, n))
    print("=" * 72)
    print("  用法：解压到另一台机器的可写目录，然后")
    print("        python AI_HANDOFF\\verify_handoff.py")
    print("        cd adb_log_gui && cmd /c \"set NO_PAUSE=1 && build_gui.bat\"")
    print("        cd .. && python verify_all.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
