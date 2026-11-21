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
import io
import os
import re
import subprocess
import sys
import tempfile

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


def _kill_leftover():
    """清掉上一轮没退干净的实例。

    为什么需要：--uitest 用的是 exe 默认的 WebView2 配置目录，多个实例同时跑
    会互相等锁 —— 表现是"单独跑 20 秒，进全量门禁就 240 秒超时"（实测踩过）。
    只杀本工具自己的进程，不碰用户的其他窗口。"""
    try:
        subprocess.run(["taskkill", "/F", "/IM", "adb_Tool.exe"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    except Exception:
        pass


def dump(html_path, wait_ms=3000, timeout=45):
    """跑页面，返回 `<pre id="RESULT">` 里的文本；拿不到返回 NO_RESULT。"""
    exe = find_exe()
    if not exe:
        raise RuntimeError("找不到 adb_Tool.exe，先跑 adb_log_gui\\build_gui.bat")
    if not os.path.exists(html_path):
        raise RuntimeError("测试页不存在：" + html_path)

    _kill_leftover()
    cmd = [exe, "--uitest", os.path.abspath(html_path), str(int(wait_ms))]

    # 必须落文件，不能用管道：exe 的 WebView2 子进程会继承 stdout 句柄，
    # 用 PIPE 时要等到子进程也退出才 EOF —— 表现为"exe 4 秒就跑完了，
    # 读的一方却一直挂着"（与 _test_interaction.py 注释里记的 Edge 坑同源）。
    fd, out_path = tempfile.mkstemp(prefix="uitest_out_", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", errors="replace") as fh:
            try:
                subprocess.run(cmd, stdout=fh, stderr=subprocess.DEVNULL,
                               timeout=timeout)
            except subprocess.TimeoutExpired:
                _kill_leftover()
        try:
            with io.open(out_path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            text = ""
    finally:
        try:
            os.remove(out_path)
        except OSError:
            pass

    # GUI 进程的 stdout 可能带 BOM，去掉再判断
    text = text.replace("\ufeff", "").strip()   # BOM 位置不固定，直接全删
    return text if text else NO_RESULT


def dump_dom(html_path, wait_ms=3000, timeout=45):
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
