# -*- coding: utf-8 -*-
r"""
package.py —— 打自包含绿色包（双击即用，不依赖目标机器装 SDK）

为什么需要它：
  以前发包是"dist 打 zip 再手工塞 scrcpy"，结果漏过 fastbot —— 别人解压后
  点「一键部署」报"找不到 fastbot 目录"。这里把"必须随包带走的东西"写成
  清单并逐项校验，缺一个就直接失败，不再靠人记。

包内必须包含：
  adb_Tool.exe            主程序
  internal\ui.html        界面
  internal\adb_Tool.ico   标题栏 / 加载页图标（构建期内联，同时留一份）
  fastbot\*.jar           Fastbot 引擎（一键部署用）
  fastbot\libs\<abi>\*.so 四个架构的原生库
  platform-tools\adb.exe  adb（目标机器没装 SDK 也能用）
  platform-tools\*.dll    adb 依赖

用法：
    python package.py                 # 生成 release\\adb_Tool_<日期>_<时间>.zip
    python package.py --no-scrcpy     # 不带 scrcpy（体积小）
"""
import datetime
import os
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "adb_log_gui", "dist")
RELEASE = os.path.join(ROOT, "release")
STAGE = os.path.join(RELEASE, "_stage_pkg")

# 必须存在的文件（相对 dist 的路径）
REQUIRED = [
    "adb_Tool.exe",
    os.path.join("internal", "ui.html"),
    os.path.join("internal", "adb_Tool.ico"),
    "monkeyq.jar",                       # 兜底：老布局
]
REQUIRED_DIRS = [
    "fastbot",
    os.path.join("fastbot", "libs"),
    "platform-tools",
]
REQUIRED_GLOBS = [
    (os.path.join("fastbot", "libs", "arm64-v8a"), ".so"),
    (os.path.join("fastbot", "libs", "armeabi-v7a"), ".so"),
]


# 2026-11-26（W-20/R10）：打包排除编译临时文件，避免包内文件数抖动
SKIP_EXT = (".tmp", ".obj", ".pdb", ".ilk")


def _skip_temp(name):
    n = (name or "").lower()
    return any(n.endswith(e) for e in SKIP_EXT)


def check_dist():
    """逐项校验 dist 是否自包含；返回错误列表（空 = 通过）。"""
    errs = []
    if not os.path.isdir(DIST):
        return ["dist 目录不存在，先跑 build_gui.bat"]

    for f in REQUIRED:
        p = os.path.join(DIST, f)
        if f == "monkeyq.jar":
            # 兼容两种布局：fastbot\monkeyq.jar 或 根目录
            if not (os.path.exists(os.path.join(DIST, "fastbot", "monkeyq.jar"))
                    or os.path.exists(p)):
                errs.append("缺 Fastbot 引擎：fastbot\\monkeyq.jar")
            continue
        if not os.path.exists(p):
            errs.append("缺文件：" + f)

    for d in REQUIRED_DIRS:
        if not os.path.isdir(os.path.join(DIST, d)):
            errs.append("缺目录：" + d)

    for sub, ext in REQUIRED_GLOBS:
        d = os.path.join(DIST, sub)
        if os.path.isdir(d) and not any(x.endswith(ext) for x in os.listdir(d)):
            errs.append("缺原生库：%s\\*%s" % (sub, ext))

    if not os.path.exists(os.path.join(DIST, "platform-tools", "adb.exe")):
        errs.append("缺 adb：platform-tools\\adb.exe（目标机器没装 SDK 就打不开设备）")

    return errs


def main():
    no_scrcpy = "--no-scrcpy" in sys.argv
    errs = check_dist()
    if errs:
        print("打包中止，dist 不自包含：")
        for e in errs:
            print("  - " + e)
        return 1

    if os.path.exists(STAGE):
        shutil.rmtree(STAGE)
    shutil.copytree(DIST, STAGE)

    # scrcpy 可选：只有本机装了才带
    if not no_scrcpy:
        cands = [
            r"C:\Users\SunWwei\AppData\Local\Microsoft\WinGet\Packages"
            r"\Genymobile.scrcpy_Microsoft.Winget.Source_8wekyb3d8bbwe\scrcpy-win64-v5.0.1",
            os.path.join(ROOT, "scrcpy"),
        ]
        for c in cands:
            if os.path.isfile(os.path.join(c, "scrcpy.exe")):
                shutil.copytree(c, os.path.join(STAGE, "scrcpy"))
                print("已带 scrcpy：" + c)
                break

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    out = os.path.join(RELEASE, "adb_Tool_%s.zip" % stamp)
    if os.path.exists(out):
        os.remove(out)

    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for r, _, fs in os.walk(STAGE):
            for f in fs:
                if _skip_temp(f):        # 2026-11-26（R10）：临时文件不进包
                    continue
                p = os.path.join(r, f)
                try:
                    z.write(p, os.path.relpath(p, STAGE).replace("\\", "/"))
                    n += 1
                except Exception:
                    pass

    # 打包后自检：关键项真的进包了
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        must = ["platform-tools/adb.exe", "fastbot/monkeyq.jar", "internal/ui.html"]
        missing = [m for m in must if m not in names]
    if missing:
        print("打包完成但缺关键项：%s" % missing)
        return 1

    size = os.path.getsize(out) / 1048576.0
    print("打包完成：%s" % out)
    print("  %d 个文件，%.1f MB" % (n, size))
    shutil.rmtree(STAGE, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
