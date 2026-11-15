"""批量输出帧（性能优化）的 DOM 行为测试。

为什么要单独一层：
  优化把"每行一条消息"改成了"每 tick 一条批量消息"，页面侧新增了
  appendLines() 与两处 DOM 上限裁剪。这些行为在源码静态检查里看不出来
  （_check_ui.js 只能看文本），必须真的跑起来数节点。

运行：python _test_batch_ui.py
"""
import os
import tempfile
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
TEST = os.path.join(ROOT, "377", "test_batch.html")
def _find_edge():
    """跨机器找 Edge：优先环境变量，再试两个默认安装位置。
    原先写死 C:/Program Files (x86)/...，换台机器/换用户名就跑不了。"""
    cands = []
    for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            cands.append(os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"))
    cands.append(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
    cands.append(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")
    for c in cands:
        try:
            if c and os.path.exists(c):
                return c
        except Exception:
            pass
    return "msedge.exe"   # 交给 PATH


EDGE = _find_edge()
PROF = os.path.join(tempfile.gettempdir(), "edgeprof_batch")
BATCH = r"""
<script>
(function(){
  var R = [];
  function ok(name, cond, extra){
    R.push((cond ? 'PASS' : 'FAIL') + ' | ' + name + (cond ? '' : ' | ' + (extra===undefined?'':extra)));
  }
  function mk(n, src, prefix){
    var a = [];
    for(var i=0;i<n;i++) a.push({level:0, src:src, slot:0, text:prefix+i});
    return a;
  }
  function run(){
    try{
      buildSlots();
      var box = document.getElementById('logbox-0');
      ok('槽位输出区存在', !!box);

      // ---- 1. 批量帧：500 行一次进来 ----
      appendLines(mk(500, 0, 'L'));
      var n500 = box.querySelectorAll('.ln').length;
      ok('批量 500 行全部落地', n500 === 500, n500);
      ok('批量后停在底部',
         Math.abs((box.scrollHeight - box.clientHeight) - box.scrollTop) < 3,
         (box.scrollHeight - box.clientHeight) + ' vs ' + box.scrollTop);

      // ---- 2. 上限裁剪：再来 6000 行 ----
      appendLines(mk(6000, 0, 'M'));
      var nAll = box.querySelectorAll('.ln').length;
      ok('超出 5000 行被裁剪', nAll <= 5001, nAll);
      ok('有且只有一条截断提示',
         box.querySelectorAll('[data-trim="1"]').length === 1,
         box.querySelectorAll('[data-trim="1"]').length);
      ok('截断提示在顶部', box.firstElementChild &&
         box.firstElementChild.getAttribute('data-trim') === '1');
      ok('最新一行还在（丢的是最早的）',
         box.textContent.indexOf('M5999') >= 0);
      ok('最早一行已被丢弃', box.textContent.indexOf('L0') < 0);

      // ---- 3. 单行消息仍然兼容 ----
      appendLine({level:1, src:0, slot:0, text:'single-line-ok'});
      ok('单行消息仍兼容', box.textContent.indexOf('single-line-ok') >= 0);

      // ---- 4. 反馈区分流：src=1 进右栏而不是日志区 ----
      switchTab('quick');
      addPendingRow(':h');
      var before = box.querySelectorAll('.ln').length;
      appendLines(mk(30, 1, 'OUT'));
      var right = document.querySelector('.fb-row .fb-right');
      ok('src=1 进反馈区右栏', !!right && right.textContent.indexOf('OUT29') >= 0);
      ok('src=1 不落进日志区', box.querySelectorAll('.ln').length === before);

      // ---- 5. 反馈区上限 1000 条 ----
      for(var k=0;k<1100;k++) addPendingRow(':t' + k);
      var rows = document.querySelectorAll('.fb-row').length;
      ok('反馈区上限 1000 条', rows <= 1000, rows);
      ok('保留的是较新的记录',
         (document.getElementById('fb-table').textContent.indexOf(':t0') < 0));

      // ---- 6. 空 items 不炸 ----
      var threw = false;
      try { appendLines([]); appendLines(null); } catch(e){ threw = true; }
      ok('空批量帧安全', !threw);
    }catch(e){
      ok('运行异常', false, e.message);
    }
    var pre = document.createElement('pre');
    pre.id = 'RESULT';
    pre.textContent = R.join('\n');
    document.body.appendChild(pre);
  }
  setTimeout(run, 300);
})();
</script>
"""


def main():
    win = os.environ.get("UI_WIN", "1100,760")
    src = open(UI, encoding="utf-8").read()
    out = src.replace("</body>", BATCH + "</body>")
    open(TEST, "w", encoding="utf-8").write(out)

    url = "file:///" + TEST.replace("\\", "/")
    cmd = [
        EDGE, "--headless=new", "--disable-gpu",
        "--window-size=" + win,
        "--virtual-time-budget=8000",
        "--dump-dom",
        "--user-data-dir=" + PROF,
        url,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=120)
    dom = r.stdout or ""
    m = re.search(r'<pre id="RESULT">(.*?)</pre>', dom, re.S)
    if not m:
        print("没拿到 RESULT，DOM 长度", len(dom))
        print(dom[:800])
        return 1

    lines = [l for l in m.group(1).split("\n") if l.strip()]
    fails = [l for l in lines if l.startswith("FAIL")]
    for l in lines:
        print("  " + l)
    print("")
    print("  批量输出：通过 %d / %d" % (len(lines) - len(fails), len(lines)))
    if fails:
        print("  有 %d 项失败" % len(fails))
        return 1
    print("  批量输出行为全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
