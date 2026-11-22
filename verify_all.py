# -*- coding: utf-8 -*-
"""verify_all.py — 交付前的一键总检查（规则 B6 的执行入口）

【三档策略（2026-11-21 整改）】

    python verify_all.py --fast    日常档，~5 秒
        只跑「静态 + 不变量 + CLI 自检」五件事，全部毫秒级：
          编译列表 / 功能清单 / ui.html 静态自检 / 功能不变量 / CLI 自检
        改一行代码就能立刻验证，不打断思路。
        能挡住的问题：新增 .cs 没进 bat、删了 DOM id、破坏冻结层、
        语法错误、C# 逻辑断言红 —— 覆盖 90% 的低级错误。

    python verify_all.py           常规档，~90 秒
        在 --fast 基础上补「真实 exe / 真实浏览器」的行为套件：
          配置导入导出（起 20+ 次 exe）、页面结构、窗口与记录、
          文件管理、APK、交互一致性、A32 动效、UI 比对 等
        功能改完、准备提交时跑这一档。

    python verify_all.py --full    全量档，~5 分钟
        再加最重的两套：_test_ux（185 秒，逐像素比对输出区）、
        A14/A15/A16/A17 落点机检、v12/v13 结构行为。
        发包前跑一次。

为什么要分档（实测数据）：
    _test_ux           185 秒   ← 单套就超过其它所有之和 4 倍
    _test_profile       62 秒   ← 起 20+ 次子进程
    其余每套            6~20 秒
    静态四项            < 1.5 秒
  原来 --fast 把 _test_profile 也算进去，导致"日常档"要 69 秒 —— 名不副实。
  现在真日常档 5 秒，需要重的再往上加，而不是每次都全跑。

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

# ---- 常规档：真实 exe / 真实浏览器的行为套件（共 ~90 秒）----
# 这些是"功能是否真的还能用"的主力，功能改完必须跑。
EDGE_TESTS = [
    ("_test_structure.py", "页面结构"),
    ("_test_ui_behavior.py", "窗口与记录"),
    ("_test_src_route.py", "输出路由"),
    ("_test_busy_lock.py", "并发互斥"),
    ("_test_batch_ui.py", "批量输出"),
    ("_test_apk_ui.py", "APK 管理"),
    ("_test_wadb_ui.py", "无线 adb"),
    ("_test_file_ui.py", "文件管理"),
    ("_test_fs_search.py", "文件搜索与监听"),
    ("_test_interaction.py", "交互一致性（页签/轮询/投屏坐标）"),
    ("_test_a32_motion.py", "A32 动效三件套（玻璃胶囊/原位放大/Dock）"),
    ("_test_ui_compare.py", "UI 比对（真实导入图片/抗锯齿/结构比对）"),
    ("_test_settings_panel.py", "设置面板（滑动条/五档字号/问号按钮）"),
    ("_test_settings_layout.py", "设置面板布局（自适应/并排/导航宽度）"),
    ("_test_monkey.py", "Monkey 稳定性测试页"),
    ("_test_fastbot.py", "Fastbot 子页（部署/配置/解析）"),
    ("_test_diag.py", "诊断页（adb/本机/车机/采样/复制）"),
    # 2026-11-22：诊断页端到端 —— 走 --uitest 在**真实 WebView2** 里跑，
    # 真的触发 C# 的 WMI 采集并断言回包字段。
    # 上面那条只验证渲染层（喂造数据），这条才验证 C# 采集链路。
    # 没编译过时自行 SKIP（返回 0），不影响 --fast 档。
    ("_test_diag_e2e.py", "诊断页端到端（真实 WMI 采集）"),
    # 2026-11-22：诊断页布局专项（量尺寸，专治"显示不全"）
    ("_test_diag_ui.py", "诊断页布局（两列/复制/进度条/折叠）"),
    # 2026-11-22：定时任务（页面状态机 + 真实 C# 引擎）
    ("_test_autotask.py", "定时任务（按钮状态机）"),
    ("_test_autotask_e2e.py", "定时任务端到端（真实引擎）"),
    # 2026-11-22：12 条新指令的真实执行（喂 stdin 给 CLI 版）
    ("_test_newcmds.py", "新指令端到端（12 条）"),
    # 2026-11-22 第 14 批：智驾出行 + 定时框布局 + 搜索修复
    ("_test_drive.py", "智驾出行/两列布局/搜索隐藏"),
    ("_test_drive_e2e.py", "智驾端到端（真实进程列表）"),
    # 2026-11-22 第 15 批：case run + 诊断页 6 项增强
    ("_test_b15.py", "第15批（case run/汇总条/diff/复制格式）"),
    ("_test_run_e2e.py", "case run 端到端（连通性真数据）"),
    # 2026-11-22 第 16 批：仪表投屏 + 参数输入归拢
    ("_test_cluster.py", "仪表投屏（门禁/芯片/投屏参数）"),
]

# ---- 全量档专属：重型套件（--full 才跑）----
# 降频理由（不是功能不重要，而是"每轮都跑不划算"）：
#   _test_ux        185 秒，逐像素比对输出区渲染，改动不涉及输出区时收益低
#   _v15/v16/v17    各 5~15 秒，是历史轮次的"落点机检"，随功能演进已稳定
#   _check_v12/v13  headless 起窗，与前两档的套件覆盖面有重叠
HEAVY_TESTS = [
    ("_test_ux.py", "交互与输出区（逐像素，185s）"),
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


def _summary(tag):
    """统一输出汇总表。"""
    print("")
    print("=" * 66)
    bad = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print(("  %-30s %s   %s" % (name, "PASS" if ok else "FAIL", detail)))
    print("=" * 66)
    print("  [%s] 合计 %d 项，失败 %d 项" % (tag, len(results), len(bad)))
    return 0 if not bad else 1


def _cli_selftest():
    """C# 逻辑断言（-selftest），三档共用。"""
    exe = os.path.join(ROOT, "adb_log_export.exe")
    if not os.path.exists(exe):
        record("CLI 自检", False, "缺 adb_log_export.exe")
        return
    p = subprocess.run([exe, "-selftest"], cwd=ROOT, capture_output=True, timeout=300)
    txt = p.stdout.decode("gbk", "replace")
    ok_n = txt.count("[OK]")
    fail_n = txt.count("[FAIL]")
    record("CLI 自检", fail_n == 0 and ok_n > 0, "断言 %d 条，失败 %d" % (ok_n, fail_n))


def main():
    mode = "fast" if "--fast" in sys.argv else ("full" if "--full" in sys.argv else "normal")

    # ======================================================================
    # 日常档（5 秒）：全是毫秒级静态检查 + C# 逻辑断言
    # ======================================================================
    if mode == "fast":
        print("== [fast] 静态四项 + CLI（不启动浏览器 / 不起子进程）==")
        run(["node", os.path.join(ROOT, "_check_build_list.js")], ROOT, 60,
            "编译列表（两个 bat 覆盖所有 .cs）", r"编译列表(完整|有 \d+ 处问题)")
        run(["node", os.path.join(ROOT, "_check_features.js")], ROOT, 60,
            "功能清单落点", r"功能清单机检(通过|失败)（?\d* ?项?）?")
        run(["node", os.path.join(ROOT, "377", "_check_ui.js")], os.path.join(ROOT, "377"), 90,
            "ui.html 静态自检", r"静态自检(全部通过|失败 \d+ 项)")
        run([PY, os.path.join(ROOT, "_gate_invariants.py")], ROOT, 120,
            "功能不变量对照", r"合计 \d+ 项，失败 \d+ 项")
        _cli_selftest()
        print("")
        print("  提示：日常档不验证真实行为。功能改完请跑 `python verify_all.py`（~90 秒）；")
        print("        发包前跑 `python verify_all.py --full`（~5 分钟）。")
        return _summary("fast")

    # ======================================================================
    # 常规档 / 全量档 共用的静态层
    # ======================================================================
    print("== 1/4 静态检查 ==")
    run(["node", os.path.join(ROOT, "_check_build_list.js")], ROOT, 60,
        "编译列表（两个 bat 覆盖所有 .cs）", r"编译列表(完整|有 \d+ 处问题)")
    run(["node", os.path.join(ROOT, "_check_features.js")], ROOT, 60,
        "功能清单落点", r"功能清单机检(通过|失败)（?\d* ?项?）?")
    run(["node", os.path.join(ROOT, "377", "_check_ui.js")], os.path.join(ROOT, "377"), 90,
        "ui.html 静态自检", r"静态自检(全部通过|失败 \d+ 项)")
    run([PY, os.path.join(ROOT, "_gate_invariants.py")], ROOT, 120,
        "功能不变量对照", r"合计 \d+ 项，失败 \d+ 项")

    # ======================================================================
    # 常规档：真实行为套件（浏览器 + 真实 exe）
    # ======================================================================
    print("== 2/4 页面结构与功能套件 ==")
    for script, label in EDGE_TESTS:
        # 2026-11-22：去掉原来套件间的 sleep(1.2)。
        # 当时加它是因为多套共用 edgeprof_beh 会撞锁；现在各套件已用独立 profile
        # （见各 _test_*.py 的 PROF 定义），串行跑不再争抢，13 套共省约 16 秒。
        ok, _ = run([PY, os.path.join(ROOT, "377", script)], os.path.join(ROOT, "377"), 120,
                    label, r"通过 \d+ / \d+")
        if not ok:
            # 只有真的失败才重试一次（撞锁是偶发，等 2 秒基本能好）。
            print("        ↑ 重试一次（无头浏览器可能瞬时锁住）")
            time.sleep(2.5)
            results.pop()
            run([PY, os.path.join(ROOT, "377", script)], os.path.join(ROOT, "377"), 120,
                label, r"通过 \d+ / \d+")

    # 配置文件导入导出：起 12 次 exe，每次 ~5.8 秒（WebView2 初始化），合计约 70 秒。
    # 基准测过：单次 exe 启动就是 5.8 秒，没法再压缩。
    # 所以它不进常规档（否则常规档从 90 秒变 160 秒），只在 --full 跑。
    # 注意：这是**真实功能验证**，曾靠它发现 ini 路径 / prefs 校验两个缺陷，
    # 动过 _cs/Profile.cs 或设置页导出导入按钮时必须单独跑一次：
    #     python 377/_test_profile.py
    if mode == "full":
        print("== 3/5 配置文件导入导出（起真实 exe，~70s）==")
        run([PY, os.path.join(ROOT, "377", "_test_profile.py")], ROOT, 200,
            "配置文件导入导出", r"通过 \d+ / \d+")
    else:
        print("== 3/4 配置文件导入导出：跳过（~70s，仅 --full 跑）==")
        print("       动过 Profile.cs 请手动跑：python 377/_test_profile.py")

    # ======================================================================
    # 全量档专属：重型套件 + 历史落点机检
    # ======================================================================
    if mode == "full":
        print("== 4/5 重型套件（--full 专属）==")
        for script, label in HEAVY_TESTS:
            ok, _ = run([PY, os.path.join(ROOT, "377", script)], os.path.join(ROOT, "377"), 300,
                        label, r"通过 \d+ / \d+")
            if not ok:
                print("        ↑ 重试一次（无头浏览器可能瞬时锁住）")
                time.sleep(2)
                results.pop()
                run([PY, os.path.join(ROOT, "377", script)], os.path.join(ROOT, "377"), 300,
                    label, r"通过 \d+ / \d+")

        print("== 5/5 历史落点机检（--full 专属）==")
        # 这些是 A12~A17 各轮改造的"落点"断言，随功能演进已稳定。
        # 保留在 --full，防的是"老功能被新改动悄悄带坏"，不必每轮都跑。
        for script, label in (("_check_v12.py", "v12 结构行为"),
                              ("_check_v13.py", "v13 圆点与终端"),
                              ("_check_a14.py", "a14 网联服务与UI")):
            # headless Edge 共用 profile，连着起会撞锁 —— 起前留 1.5 秒
            time.sleep(1.5)
            ok, _ = run([PY, os.path.join(ROOT, script)], ROOT, 300, label, r"通过 \d+ / \d+")
            if not ok:
                print("        ↑ 重试一次（headless 浏览器可能锁住 profile）")
                time.sleep(3.0)
                results.pop()
                run([PY, os.path.join(ROOT, script)], ROOT, 300, label, r"通过 \d+ / \d+")

        for script, label in (("_v15_checks.py", "A15 落点机检"),
                              ("_v16_checks.py", "A16 落点机检"),
                              ("_v17_checks.py", "A17 落点机检")):
            run([PY, os.path.join(ROOT, script)], ROOT, 120, label, r"通过 \d+ / \d+")

    print("== CLI 自检 ==")
    _cli_selftest()

    if mode != "full":
        print("")
        print("  提示：本档未跑 _test_ux（185s）与历史落点机检。发包前跑 `--full`。")

    return _summary(mode)


if __name__ == "__main__":
    sys.exit(main())
