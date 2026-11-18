# -*- coding: utf-8 -*-
"""377/_wv2.py —— 在**真实 WebView2** 里跑测试页，替代 `msedge --headless --dump-dom`。

为什么要这个通道（2026-11-18 实测）：
  换机后 `_test_ui_behavior` / `_test_ux` / `_test_interaction` 共 9 条断言变红。
  用 msedge headless 查下去发现两类现象：
    1) `--virtual-time-budget` 下 CSS 动画 currentTime 恒为 0，`.frame` 上
       `fill:backwards` 的入场动画把 opacity 钉在 0 —— 凡是量可见性/几何/焦点的
       断言都在测"隐藏态页面"；
    2) 根元素(html/body)与伪元素(::after)的 getComputedStyle 返回不更新的快照
       （现场插 `!important` 新规则读数纹丝不动，而新建 div 正常）。
  这两条都可能只是 headless 的实现差异，所以需要一个"同一渲染器"的对照通道：
  用 adb_Tool.exe 的 `--uitest`（复刻自检的离屏窗口 + ExecuteScriptAsync 链路）
  加载同一份测试页，量到的就是用户在 WebView2 里看到的东西。

用法（测试里只需替换取 DOM 的那一步）：
    import _wv2
    dom = _wv2.dump_dom(TEST, wait_ms=3000)     # 返回含 <pre id="RESULT"> 的文本
    # 之后的 re.search(r'<pre id="RESULT">(.*?)</pre>', dom, re.S) 完全不用改

也可以直接用命令行看一份页面：
    python 377/_wv2.py 377/test_ux.html 3000

注意：
  · 页面必须自己把结论写进 `<pre id="RESULT">`（现有 377 用例都满足）；
  · 返回 `__NO_RESULT__` 表示页面没跑起来（脚本异常/加载失败），与"断言失败"区分；
  · 真实 WebView2 是**实时时钟**，动画会正常播完，等待时间按最慢的用例给。
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 优先级：dist（打包后的完整目录）→ 仓库根的 adb_log_gui
_EXE_CANDIDATES = [
    os.path.join(ROOT, "adb_log_gui", "dist", "adb_Tool.exe"),
    os.path.join(ROOT, "adb_log_gui", "adb_Tool.exe"),
]

NO_RESULT = "__NO_RESULT__"


def find_exe():
    for p in _EXE_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def dump(html_path, wait_ms=3000, timeout=180):
    """跑页面，返回 `<pre id="RESULT">` 里的文本；拿不到返回 NO_RESULT。"""
    exe = find_exe()
    if not exe:
        raise RuntimeError("找不到 adb_Tool.exe，先跑 adb_log_gui\\build_gui.bat")
    if not os.path.exists(html_path):
        raise RuntimeError("测试页不存在：" + html_path)

    cmd = [exe, "--uitest", os.path.abspath(html_path), str(int(wait_ms))]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return NO_RESULT

    text = (r.stdout or b"").decode("utf-8", "replace")
    # GUI 进程的 stdout 可能带 BOM，去掉再判断
    text = text.lstrip("\ufeff").strip()
    return text if text else NO_RESULT


def dump_dom(html_path, wait_ms=3000, timeout=180):
    """兼容旧解析：包成 `<pre id="RESULT">…</pre>`，现有正则一行都不用改。"""
    text = dump(html_path, wait_ms=wait_ms, timeout=timeout)
    return '<pre id="RESULT">' + text + "</pre>"


def _main(argv):
    if len(argv) < 2:
        print("用法: python 377/_wv2.py <测试页.html> [等待毫秒]")
        return 2
    path = argv[1]
    wait = int(argv[2]) if len(argv) > 2 else 3000
    exe = find_exe()
    print("exe = %s" % exe)
    print("page = %s   wait = %dms" % (path, wait))
    print("-" * 60)
    print(dump(path, wait_ms=wait))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
