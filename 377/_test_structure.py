"""页面结构检查（_test_structure.py）

为什么单独一条：
    单页功能的测试都过了，也可能"整页空白" —— 因为我们踩过：
    #page-file 被插到 #feedback 之前，而 feedback 属于 #page-quick，
    于是文件页嵌进了快捷指令页容器里，切过去一片空。
    这类问题只有"检查 DOM 父子关系 + 切换后是否真的可见"才能发现。

检查项：
    1) 五个 #page-*（cmd/quick/file/cast/ui）都是 .main 的直接子节点
    2) 五个页签都能切，切换后只有目标页 display 不是 none
    3) 每个页面的关键容器存在且尺寸 > 0
    4) #feedback 属于快捷指令页（这是现状，写下来防止被搬走）

运行：python _test_structure.py
"""
import os
import tempfile
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
TEST = os.path.join(ROOT, "377", "test_structure.html")
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
JS = r"""
<style>*,*::before,*::after{transition:none !important;animation:none !important;}</style>
<script>
(function(){
  var R = [];
  function ok(name, cond, extra){
    R.push((cond ? 'PASS' : 'FAIL') + ' | ' + name + (cond ? '' : ' | ' + (extra===undefined?'':extra)));
  }
  var PAGES = ['cmd','quick','file','cast','ui'];
  var KEY = {
    cmd:   ['slots', 'cmd-input-0', 'logbox-0'],
    quick: ['quick-grid', 'feedback'],
    file:  ['pane-local', 'pane-dev', 'list-local'],
    cast:  ['cast-grid', 'cast-cell-0'],
    ui:    ['ui-design-path', 'ui-real-path', 'ui-resultbox']
  };

  function run(){
    try{
      setStatus({dev:'x', online:true, rooted:true});
      var main = document.querySelector('.main');
      ok('存在 .main 容器', !!main);

      // 0) 页签顺序与默认页（2026-11-14 需求：指令在前、默认落在指令）
      var tabs = document.querySelectorAll('.tabs .tab');
      var order = [];
      for (var ti = 0; ti < tabs.length; ti++) order.push(tabs[ti].getAttribute('data-tab'));
      // 2026-11-15 第二轮：末尾追加「文本」页（需求 4），顺序仍是前五个冻结
      ok('页签顺序为 指令→终端→文件→投屏→UI→文本',
         order.join(',') === 'quick,cmd,file,cast,ui,text', order.join(','));
      ok('第一个页签文字是「指令」', tabs[0].textContent.trim() === '指令', tabs[0].textContent);
      ok('第二个页签文字是「终端」', tabs[1].textContent.trim() === '终端', tabs[1].textContent);
      ok('第五个页签文字是「UI」', tabs[4].textContent.trim() === 'UI',
         tabs[4] ? tabs[4].textContent : 'no-tab');
      ok('默认激活的是「指令」页',
         document.getElementById('page-quick').classList.contains('active')
         && !document.getElementById('page-cmd').classList.contains('active'));

      // 1) 父子关系
      PAGES.forEach(function(p){
        var el = document.getElementById('page-' + p);
        ok('page-' + p + ' 存在', !!el);
        ok('page-' + p + ' 是 .main 的直接子节点',
           !!el && el.parentElement === main,
           el && el.parentElement ? (el.parentElement.className || el.parentElement.id) : 'null');
      });

      // feedback 属于快捷指令页（现状，防止被搬到别处）
      var fb = document.getElementById('feedback');
      ok('#feedback 属于 #page-quick',
         !!fb && !!fb.parentElement && fb.parentElement.id === 'page-quick',
         fb && fb.parentElement ? (fb.parentElement.id || fb.parentElement.className) : 'null');

      // 2) 切换：只有一个页可见
      PAGES.forEach(function(p){
        switchTab(p);
        var visible = PAGES.filter(function(q){
          var e = document.getElementById('page-' + q);
          return e && getComputedStyle(e).display !== 'none';
        });
        ok('切到 ' + p + ' 后只有它可见', visible.length === 1 && visible[0] === p,
           visible.join(','));
      });

      // 3) 每个页的关键容器存在且尺寸正常
      PAGES.forEach(function(p){
        switchTab(p);
        KEY[p].forEach(function(id){
          var e = document.getElementById(id);
          if (!e) { ok(p + ' 的 #' + id + ' 存在', false, 'missing'); return; }
          var r = e.getBoundingClientRect();
          ok(p + ' 的 #' + id + ' 有实际尺寸', r.width > 0 && r.height > 0,
             Math.round(r.width) + 'x' + Math.round(r.height));
        });
      });

      // 3b) 输出区默认收起 → #fb-table 尺寸为 0 是预期，展开后才该有尺寸
      switchTab('quick');
      if (window.fbSetCollapsed) window.fbSetCollapsed(false);
      var t = document.getElementById('fb-table');
      var tr = t ? t.getBoundingClientRect() : {width:0, height:0};
      ok('展开后 #fb-table 有实际尺寸', tr.width > 0 && tr.height > 0,
         Math.round(tr.width) + 'x' + Math.round(tr.height));
      if (window.fbSetCollapsed) window.fbSetCollapsed(true);

      // 3c) 未投屏时 #cast-img-0 是 0x0 属正常，只要求存在且未激活
      var ci = document.getElementById('cast-img-0');
      ok('未投屏时 #cast-img-0 存在且未激活',
         !!ci && !ci.classList.contains('on'), ci ? ci.className : 'missing');

      // 4) 页面高度要撑满（整页空白时高度是 0）
      switchTab('cast');
      var pc = document.getElementById('page-cast');
      var r2 = pc.getBoundingClientRect();
      ok('投屏页撑满可用高度', r2.height > 300, Math.round(r2.height));
      // 2026-11-15：前排/后排/刷新位三个按钮已删除，能力内建进「主屏」「后排屏」固定格子。
      // 断言「旧按钮不再回来」比断言「新按钮存在」更能防回归。
      ok('前排投屏按钮已删除', !document.getElementById('cast-front-btn'));
      ok('后排投屏按钮已删除', !document.getElementById('cast-rear-btn'));
      ok('刷新屏位按钮已删除', !document.getElementById('cast-refresh-btn'));
      ok('内建屏位映射纯函数存在',
         typeof castDefaultId === 'function' && typeof castHasDisplay === 'function');
      ok('castDefaultId 六格固定屏位映射（主屏0/副屏4/后排1/HUD3/PHUD-B9/PHUD-C10）',
         castDefaultId(0) === 0 && castDefaultId(1) === 4 &&
         castDefaultId(2) === 1 && castDefaultId(3) === 3 &&
         castDefaultId(4) === 9 && castDefaultId(5) === 10);
      ok('castHasDisplay 命中与缺失',
         castHasDisplay([{id:0},{id:1}], 1) === true &&
         castHasDisplay([{id:0}], 1) === false &&
         castHasDisplay([], 0) === false);
      ok('旧的一键前后排函数已移除', typeof castRow === 'undefined' && typeof castRowId === 'undefined');

      // 5) UI 对比页（投屏右侧）：是 .main 直接子节点，且切过去有实际尺寸
      var pui = document.getElementById('page-ui');
      ok('page-ui 存在且是 .main 的直接子节点',
         !!pui && pui.parentElement === main,
         pui && pui.parentElement ? (pui.parentElement.className || pui.parentElement.id) : 'null');
      switchTab('ui');
      var uiVisible = PAGES.filter(function(q){
        var e = document.getElementById('page-' + q);
        return e && getComputedStyle(e).display !== 'none';
      });
      ok('切到 UI 后只有 UI 页可见',
         uiVisible.length === 1 && uiVisible[0] === 'ui', uiVisible.join(','));
      ok('UI 页有开始对比/打开结果图按钮',
         !!document.getElementById('ui-open-result'));

      switchTab('cmd');

      // 投屏页会起一个 1s 轮询定时器；不关掉的话 --dump-dom 会一直等它，
      // 表现为"无头浏览器超时"（踩过）。
      try {
        if (typeof _cast !== 'undefined' && _cast.timer) {
          clearInterval(_cast.timer);
          _cast.timer = null;
        }
      } catch (e2) {}
    }catch(e){
      ok('结构检查异常', false, e.message);
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
    src = open(UI, encoding="utf-8").read()
    open(TEST, "w", encoding="utf-8").write(src.replace("</body>", JS + "</body>"))

    prof = os.path.join(os.environ["TEMP"], "edgeprof_struct_%d" % int(time.time()))
    cmd = [
        EDGE, "--headless=new", "--disable-gpu",
        "--window-size=1100,760",
        "--virtual-time-budget=6000",
        "--dump-dom",
        "--user-data-dir=" + prof,
        "file:///" + TEST.replace("\\", "/"),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=150)
    m = re.search(r'<pre id="RESULT">(.*?)</pre>', r.stdout or "", re.S)
    if not m:
        print("没拿到 RESULT")
        return 1

    lines = [l for l in m.group(1).split("\n") if l.strip()]
    fails = [l for l in lines if l.startswith("FAIL")]
    for l in lines:
        print("  " + l)
    print("")
    print("  页面结构：通过 %d / %d" % (len(lines) - len(fails), len(lines)))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
