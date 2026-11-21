# -*- coding: utf-8 -*-
"""verify_all.py — 交付前的一键总检查（规则 B6 的执行入口）

顺序刻意从"便宜"到"贵"：
    1. 编译列表完整（静态，毫秒级）
    2. 功能清单落点（静态）
    3. ui.html 静态自检
    4. 页面结构（无头浏览器，检查四个页面父子关系/可见性）
    5. 功能行为套件（10 个 DOM 测试）
    6. CLI 自检（纯逻辑断言）
    7. GUI 自检（起一次真实窗口，--fast 可跳过）

用法：
    python verify_all.py            # 全量
    python verify_all.py --fast     # 跳过 GUI 自检

约定：任何一项失败，退出码非 0；release.py 会据此拒绝打包。
"""
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
GUI_DIR = os.path.join(ROOT, "adb_log_gui")
PY = sys.executable
EDGE_TESTS = [
    ("_test_structure.py", "页面结构"),
    ("_test_ui_behavior.py", "窗口与记录"),
    ("_test_ux.py", "交互与输出区"),
    ("_test_src_route.py", "输出路由"),
    ("_test_busy_lock.py", "并发互斥"),
    ("_test_batch_ui.py", "批量输出"),
    ("_test_apk_ui.py", "APK 管理"),
    ("_test_wadb_ui.py", "无线 adb"),
    ("_test_file_ui.py", "文件管理"),
    ("_test_fs_search.py", "文件搜索与监听"),
    ("_test_interaction.py", "交互一致性（页签/轮询/投屏坐标）"),
]

results = []


def _log_dir(exe_path):
    """日志可能落两处：exe 同级 log\\（新包），或 %LOCALAPPDATA%\\adb_Tool\\logs（旧包/只读目录）。"""
    beside = os.path.join(os.path.dirname(os.path.abspath(exe_path)), "log")
    if os.path.isdir(beside):
        return beside
    return os.path.join(os.environ.get("LOCALAPPDATA", ""), "adb_Tool", "logs")


def record(name, ok, detail):
    results.append((name, ok, detail))
    print(("  [OK]   " if ok else "  [XX]   ") + name + "  " + detail)


def run(cmd, cwd, timeout, name, pick=None):
    t0 = time.time()
    # 2026-11-19：起 node / msedge 偶尔会瞬时 PermissionError [WinError 5]
    # （安全软件扫描可执行文件的窗口期），单独跑却永远正常。
    # 这种不该算门禁失败 —— 重试一次再判。
    p = None
    # 2026-11-19：这个瞬时锁（安全软件扫描 node.exe 的窗口）实测能持续 5~10 秒，
    # 0.6 秒两次重试不够用 —— 今天连着误报三次。改成 3 次、间隔 2.5 秒。
    for attempt in (1, 2, 3):
        try:
            p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=timeout)
            break
        except subprocess.TimeoutExpired:
            # 2026-11-19：headless Edge 偶发在**并发跑门禁**时卡住（单独跑同样脚本 5 秒过）。
            # 直接判失败会误伤；超时也重试，连续三次超时才算真失败。
            if attempt == 3:
                record(name, False, "超时 %ds（重试 3 次仍失败）" % timeout)
                return False, ""
            print("        （%s 超时 %ds，重试 %d/3）" % (name, timeout, attempt))
            time.sleep(2.0)
        except OSError as ex:
            if attempt == 3:
                record(name, False, "无法启动 %s（%s）" % (cmd[0], ex))
                return False, ""
            time.sleep(2.5)
    out = (p.stdout or "") + (p.stderr or "")
    ok = (p.returncode == 0)
    detail = ""
    if pick:
        m = re.search(pick, out)
        if m:
            detail = m.group(0).strip()
    if not detail:
        detail = "rc=%d" % p.returncode
    if not ok:
        # 失败时把子进程原始输出留一份：这里只打一行汇总，
        # 具体是哪几条断言红的全在 out 里，丢掉就只能靠运气复现。
        try:
            safe = re.sub(r"[^\w\u4e00-\u9fa5]+", "_", name)
            with open(os.path.join(ROOT, "_fail_%s.log" % safe), "w",
                      encoding="utf-8") as f:
                f.write(out)
        except OSError:
            pass
    record(name, ok, detail)
    return ok, out


def main():
    fast = "--fast" in sys.argv

    # 2026-11-20：日常档。改一行代码就等 2 分钟不现实，所以给一条 10 秒的路：
    #   编译列表（漏文件是真实事故）+ 功能清单 + ui 语法 + 功能不变量 + CLI 自检
    # 这四个覆盖"编译能过 / 界面能解析 / 冻结层不破 / 逻辑断言"，已经能挡住 90% 的低级错误。
    # 全量档（页面结构、交互套件、A15~A17 落点）留到发包前跑。
    if fast:
        print("== [fast] 编译列表 ==")
        run(["node", os.path.join(ROOT, "_check_build_list.js")], ROOT, 60,
            "编译列表（两个 bat 覆盖所有 .cs）", r"编译列表(完整|有 \d+ 处问题)")
        print("== [fast] 功能清单 ==")
        run(["node", os.path.join(ROOT, "_check_features.js")], ROOT, 60,
            "功能清单落点", r"功能清单机检(通过|失败)（?\d* ?项?）?")
        print("== [fast] ui.html 静态自检 ==")
        run(["node", os.path.join(ROOT, "377", "_check_ui.js")], os.path.join(ROOT, "377"), 90,
            "ui.html 静态自检", r"静态自检(全部通过|失败 \d+ 项)")
        print("== [fast] 功能不变量 ==")
        run([PY, os.path.join(ROOT, "_gate_invariants.py")], ROOT, 120,
            "功能不变量对照", r"合计 \d+ 项，失败 \d+ 项")
        # 2026-11-21：配置文件导出/导入（Profile.cs）。
        # 新增理由：这个功能此前**零自动化覆盖**，靠手工造数据实测才发现两个
        # 真实缺陷（ini 路径没跟随 internal 布局 / prefs 导入不校验）。
        # 它不依赖浏览器、约 15 秒，所以放进日常档，防止再次静默回归。
        print("== [fast] 配置文件导入导出 ==")
        run([PY, os.path.join(ROOT, "377", "_test_profile.py")], ROOT, 180,
            "配置文件导入导出", r"通过 \d+ / \d+")
        print("== [fast] CLI 自检 ==")
        _exe = os.path.join(ROOT, "adb_log_export.exe")
        if not os.path.exists(_exe):
            record("CLI 自检", False, "缺 adb_log_export.exe")
        else:
            _p = subprocess.run([_exe, "-selftest"], cwd=ROOT, capture_output=True, timeout=300)
            _t = _p.stdout.decode("gbk", "replace")
            record("CLI 自检", _t.count("[FAIL]") == 0 and _t.count("[OK]") > 0,
                   "断言 %d 条，失败 %d" % (_t.count("[OK]"), _t.count("[FAIL]")))
        print("")
        print("=" * 66)
        _bad = [r for r in results if not r[1]]
        for _n, _ok, _d in results:
            print(("  %-30s %s   %s" % (_n, "PASS" if _ok else "FAIL", _d)))
        print("=" * 66)
        print("  [fast] 合计 %d 项，失败 %d 项" % (len(results), len(_bad)))
        return 0 if not _bad else 1

    print("== 1/7 编译列表 ==")
    run(["node", os.path.join(ROOT, "_check_build_list.js")], ROOT, 60,
        "编译列表（两个 bat 覆盖所有 .cs）", r"编译列表(完整|有 \d+ 处问题)")

    print("== 2/7 功能清单 ==")
    run(["node", os.path.join(ROOT, "_check_features.js")], ROOT, 60,
        "功能清单落点", r"功能清单机检(通过|失败)（?\d* ?项?）?")

    print("== 3/7 ui.html 静态自检 ==")
    run(["node", os.path.join(ROOT, "377", "_check_ui.js")], os.path.join(ROOT, "377"), 90,
        "ui.html 静态自检", r"静态自检(全部通过|失败 \d+ 项)")

    print("== 4-5/7 页面结构与功能套件 ==")
    for script, label in EDGE_TESTS:
        ok, _ = run([PY, os.path.join(ROOT, "377", script)], os.path.join(ROOT, "377"), 240,
                    label, r"通过 \d+ / \d+")
        if not ok:
            # 无头浏览器偶发启动失败（profile 锁 / 瞬时拒绝访问），重试一次再判红。
            # 只对浏览器套件重试；逻辑类套件失败就是真失败，重试没意义。
            print("        ↑ 重试一次（无头浏览器可能瞬时锁住）")
            time.sleep(2)
            results.pop()
            run([PY, os.path.join(ROOT, "377", script)], os.path.join(ROOT, "377"), 240,
                label, r"通过 \d+ / \d+")

    print("== 5.5/7 根目录 DOM 实测 ==")
    # 这几套不在 377/ 下（它们是按主题分文件维护的独立套件）：
    #   _gate_invariants.py 冻结层对照（kind / onclick / DOM id / 页签 / 页面 / 消息桥）
    #   _v15_checks.py      A15 落点（投屏六条、日志等级、设备管理、窗口原生行为）
    #   _v16_checks.py      A16 落点（窗口不变形、弹窗 portal/互斥、16 色、投屏链路、偏好、tab 拖拽、9 条 adb）
    #   _v17_checks.py      A17 落点（强调色记忆、开合动效、黑白灰图标、浅色边界、圆角、关闭一次、启动层渐变、scrcpy 内嵌）
    #   _check_v12.py      自绘标题栏 / 设置 / 字体 / 帮助 / 文本页 / 文件页
    #   _check_v13.py      四状态圆点 / 标题栏重组 / 终端多行顺序执行 / 输出区热区
    #   _check_a14.py      网联服务分组 13 条 / 启动图标 / 浅色对比度 / 下拉浮层 / 字体大小
    #   _check_accent_dom   16 色强调色与三套明暗的正交性
    #   _check_glass.py     Liquid Glass 计算样式与性能护栏
    #   _smoke_win.py       真机起窗：无边框、缩放、最大化不盖任务栏、无错误日志
    for script, label in (("_check_v12.py", "v12 结构行为"),
                          ("_check_v13.py", "v13 圆点与终端"),
                          ("_check_a14.py", "a14 网联服务与UI"),
                          # 2026-11-20 门禁瘦身：accent_dom / glass / smoke_win 已下线
                          # （一次性 UI 改造验证 + 起窗实测，改为手动抽查）
                          ):
        # 2026-11-20：这几套都是 headless Edge，共用同一个 profile。
        # 连着起会撞锁 —— 实测 v12 超时 300s、单独跑 5 秒过。
        # 所以：起之前留 1.5 秒让上一个浏览器退干净，失败再重试一次。
        time.sleep(1.5)
        ok, _ = run([PY, os.path.join(ROOT, script)], ROOT, 300, label, r"通过 \d+ / \d+")
        if not ok:
            print("        ↑ 重试一次（headless 浏览器可能锁住 profile）")
            time.sleep(3.0)
            results.pop()
            run([PY, os.path.join(ROOT, script)], ROOT, 300, label, r"通过 \d+ / \d+")

    print("== 5.6/7 冻结层与 A15/A16 落点 ==")
    run([PY, os.path.join(ROOT, "_v15_checks.py")], ROOT, 120,
        "A15 落点机检", r"通过 \d+ / \d+")
    run([PY, os.path.join(ROOT, "_v16_checks.py")], ROOT, 120,
        "A16 落点机检", r"通过 \d+ / \d+")
    run([PY, os.path.join(ROOT, "_v17_checks.py")], ROOT, 120,
        "A17 落点机检", r"通过 \d+ / \d+")
    run([PY, os.path.join(ROOT, "_gate_invariants.py")], ROOT, 120,
        "功能不变量对照", r"合计 \d+ 项，失败 \d+ 项")

    # 2026-11-21：配置文件导入导出（见 fast 档同名段落的说明）
    run([PY, os.path.join(ROOT, "377", "_test_profile.py")], ROOT, 180,
        "配置文件导入导出", r"通过 \d+ / \d+")

    print("== 6/7 CLI 自检 ==")
    exe = os.path.join(ROOT, "adb_log_export.exe")
    if not os.path.exists(exe):
        record("CLI 自检", False, "缺 adb_log_export.exe")
    else:
        p = subprocess.run([exe, "-selftest"], cwd=ROOT, capture_output=True, timeout=300)
        txt = p.stdout.decode("gbk", "replace")
        ok_n = txt.count("[OK]")
        fail_n = txt.count("[FAIL]")
        record("CLI 自检", fail_n == 0 and ok_n > 0, "断言 %d 条，失败 %d" % (ok_n, fail_n))

    # 2026-11-20 门禁瘦身：GUI 自检（18 条）下线 —— 与「页面结构 / 窗口与记录」
    # 覆盖面重叠，且要起一次真实窗口（约 10~20 秒）。需要时手动跑：
    #   adb_log_gui\dist\adb_Tool.exe --selfcheck

    print("")
    print("=" * 66)
    bad = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print(("  %-30s %s   %s" % (name, "PASS" if ok else "FAIL", detail)))
    print("=" * 66)
    print("  合计 %d 项，失败 %d 项" % (len(results), len(bad)))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
