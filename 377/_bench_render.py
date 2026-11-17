# -*- coding: utf-8 -*-
"""渲染基准（真实时钟）：逐行追加 vs DocumentFragment 批量追加。

为什么单独一个脚本、且**不用 --virtual-time-budget**：
    虚拟时钟下 performance.now() 不前进（实测新旧写法都返回 0.0ms），
    用它测出来的"提速 N 倍"是假的。这里让 Edge 用真实时钟，
    在 DOMContentLoaded 里同步跑完并把结果写进 <pre>，load 之后 dump-dom 取出。

口径：
    old  = 逐行 createElement + appendChild + trimLog（A26 之前的真实路径）
    new  = 一次 Fragment 插入 + 一次 trimLog（A26 之后的路径）
    两组都用同一份 trimLog，所以差异只来自"追加策略"。
    另外各测一次"已在 5000 行上限时"的最坏情况 —— logcat 持续刷就是稳态。

用法：
    python 377/_bench_render.py            # 默认 500 / 2000 / 稳态
"""
import io
import os
import re
import subprocess
import sys
import tempfile
import html as H

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
OUT = os.path.join(ROOT, "377", "_bench_probe.html")

JS = r"""
<script>
document.addEventListener('DOMContentLoaded', function(){
  var R = [];
  function mk(n){
    var box = document.getElementById('bench-box');
    box.innerHTML = '';
    box.__trimNote = null;
    var d;
    for (var i = 0; i < n; i++){          // 预热到上限，模拟 logcat 稳态
      d = document.createElement('div');
      d.className = 'ln'; d.textContent = 'w' + i;
      box.appendChild(d);
    }
    trimLog(box);
    return box;
  }
  function oldWay(box, n){
    var t = performance.now();
    for (var i = 0; i < n; i++){
      var d = document.createElement('div');
      d.className = 'ln'; d.textContent = 'o' + i;
      box.appendChild(d);
      trimLog(box);                        // 旧路径：每行一次
    }
    return performance.now() - t;
  }
  function newWay(box, n){
    var t = performance.now();
    var frag = document.createDocumentFragment();
    for (var i = 0; i < n; i++){
      var d = document.createElement('div');
      d.className = 'ln'; d.textContent = 'n' + i;
      frag.appendChild(d);
    }
    box.appendChild(frag);
    trimLog(box);                          // 新路径：一次
    return performance.now() - t;
  }
  var box = document.createElement('div');
  box.id = 'bench-box';
  box.style.cssText = 'position:absolute;left:-9999px;width:600px;height:200px;overflow:auto';
  document.body.appendChild(box);

  var cases = [500, 2000];
  for (var c = 0; c < cases.length; c++){
    var n = cases[c];
    mk(5000);
    var a = oldWay(box, n);
    mk(5000);
    var b = newWay(box, n);
    R.push('N=' + n + '  上限态 old=' + a.toFixed(1) + 'ms  new=' + b.toFixed(1) + 'ms  ' +
           '提速 ' + (b > 0 ? (a / b).toFixed(1) : '-') + 'x  行数=' + box.childElementCount);
  }
  // 空箱（冷启动第一条命令）也测一次，反映"首屏"体验
  mk(0);
  var a0 = oldWay(box, 500);
  mk(0);
  var b0 = newWay(box, 500);
  R.push('N=500  空箱 old=' + a0.toFixed(1) + 'ms  new=' + b0.toFixed(1) + 'ms  ' +
         '提速 ' + (b0 > 0 ? (a0 / b0).toFixed(1) : '-') + 'x');

  var p = document.createElement('pre');
  p.id = 'RESULT';
  p.textContent = R.join('\n');
  document.body.appendChild(p);
});
</script>
"""


def find_edge():
    for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            p = os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")
            if os.path.exists(p):
                return p
    return "msedge.exe"


def main():
    src = io.open(UI, "r", encoding="utf-8").read()
    io.open(OUT, "w", encoding="utf-8").write(src.replace("</body>", JS + "</body>"))
    prof = os.path.join(tempfile.gettempdir(), "edgeprof_bench_%d" % os.getpid())
    tmpout = os.path.join(tempfile.gettempdir(), "bench_out_%d.html" % os.getpid())

    # 关键：**不加** --virtual-time-budget（会冻结 performance.now）
    cmd = [find_edge(), "--headless=new", "--disable-gpu", "--no-sandbox",
           "--no-first-run", "--disable-background-networking", "--disable-sync",
           "--disable-extensions", "--disable-component-update",
           "--window-size=1280,900", "--dump-dom",
           "--user-data-dir=" + prof, "file:///" + OUT.replace("\\", "/")]

    with open(tmpout, "w", encoding="utf-8", errors="replace") as fh:
        try:
            subprocess.run(cmd, stdout=fh, stderr=subprocess.DEVNULL, timeout=150)
        except subprocess.TimeoutExpired:
            print("Edge 超时（150s）")
            return 1

    dom = ""
    try:
        with io.open(tmpout, "r", encoding="utf-8", errors="replace") as fh:
            dom = fh.read()
    finally:
        try:
            os.remove(tmpout)
        except OSError:
            pass

    m = re.search(r'<pre id="RESULT">(.*?)</pre>', dom, re.S)
    if not m:
        print("没拿到 RESULT，DOM 长度", len(dom))
        return 1
    print("== 渲染基准（真实时钟） ==")
    for line in H.unescape(m.group(1)).splitlines():
        if line.strip():
            print("  " + line.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
