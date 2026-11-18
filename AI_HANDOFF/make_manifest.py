# -*- coding: utf-8 -*-
"""make_manifest.py —— 给交接包生成 MANIFEST.json（路径 + 大小 + sha256）。

用途：
  1. 换机器后 `verify_handoff.py` 用它确认"文件拷全了、没被截断"；
  2. 两台机器比对"到底哪几个文件不一样"。

什么时候重新生成：
  你改了源码并想让新旧两台机器对齐时 → 改了源码就跑一次（否则哈希会对不上，那是对的）。

用法：
    python AI_HANDOFF\\make_manifest.py
"""
import hashlib
import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "AI_HANDOFF", "MANIFEST.json")

# 参与清单的目录（只放"活"的源码/文档，不含产物）
INCLUDE_DIRS = ["_cs", "docs", "AI_HANDOFF", os.path.join("adb_log_gui", "webview2"), "377"]

# 单个文件也纳入
INCLUDE_FILES = [
    "verify_all.py",
    "release.py",
    "_check_build_list.js",
    "_check_features.js",
    "_check_features.json",
    "adb_log_gui/build_gui.bat",
    "adb_log_gui/make_min.bat",
    "adb_log_gui/adb_log_export.ini",
    "adb_log_gui/cmds.ini",
    "adb_log_export.ini",
    "cmds.ini",
    "HANDOFF.md",
]

# 不纳入的后缀 / 目录 / 具体名（产物、缓存、样本）
SKIP_EXT = (".exe", ".dll", ".zip", ".zst", ".png", ".jpg", ".jpeg", ".ico", ".log")
SKIP_DIR_NAMES = {"dist", "dist_min", "dist_single", "__pycache__", "_shots", "release",
                  "node_modules", ".git", "_feishu"}
# 按文件名排除（比对 basename，不是相对路径 —— 原来拿 rel 比，结果一个都没排掉，
# 连 MANIFEST.json 自己都被写进清单，导致 verify 永远报"1 个文件不一致"）
SKIP_FILES = {"MANIFEST.json", "verify_handoff.py", "make_manifest.py",
              ".adb_tool_history"}
# 根目录的 adb_log_export.ini 是**本机运行态**（.gitignore 里排除、每台机器 accent= 不同），
# 收进清单会让两台机器的哈希天然对不上，所以排除；adb_log_gui 下那份是构建用模板，仍保留。
SKIP_REL = {"adb_log_export.ini"}
# 377 下的测试页面每次跑测试都会从 ui.html 重新生成（.gitignore 已排除），
# 收进清单等于"跑一次测试就脏一次"，一律排除。
SKIP_377_PATTERNS = ("test_", "_test_", "_dbg")
SKIP_377_SUFFIX = "_probe.html"



def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def collect():
    out = []

    def add(full):
        rel = os.path.relpath(full, ROOT).replace("\\", "/")
        name = os.path.basename(full)
        if name in SKIP_FILES or rel in SKIP_REL:
            return
        if os.path.splitext(full)[1].lower() in SKIP_EXT:
            return
        # 377 下由 ui.html 派生的测试页面：每次跑测试都重新生成，不能进清单
        if rel.startswith("377/"):
            if name.startswith(SKIP_377_PATTERNS) and name.endswith(".html"):
                return
            if name.endswith(SKIP_377_SUFFIX):
                return
        try:
            st = os.stat(full)
        except OSError:
            return
        out.append({
            "path": rel,
            "size": st.st_size,
            "sha256": sha256(full),
        })

    for rel in INCLUDE_FILES:
        p = os.path.join(ROOT, rel.replace("/", os.sep))
        if os.path.exists(p):
            add(p)

    for d in INCLUDE_DIRS:
        base = os.path.join(ROOT, d)
        if not os.path.isdir(base):
            continue
        for cur, dirs, files in os.walk(base):
            dirs[:] = [x for x in dirs if x not in SKIP_DIR_NAMES]
            for f in files:
                add(os.path.join(cur, f))

    out.sort(key=lambda x: x["path"])
    return out


def main():
    files = collect()
    total = sum(x["size"] for x in files)
    data = {
        "project": "adb_Tool / 网联服务_Adb_Tool",
        "note": "源码与文档清单（不含 exe/dll/zip/图片等产物）。改了源码请重新运行本脚本。",
        "count": len(files),
        "totalBytes": total,
        "files": files,
    }
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(
        json.dumps(data, ensure_ascii=False, indent=1))
    print("MANIFEST.json: %d 个文件，%.2f MB" % (len(files), total / 1048576.0))
    print("写入：%s" % OUT)


if __name__ == "__main__":
    main()
