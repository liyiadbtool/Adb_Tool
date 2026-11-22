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
  // 2026-11-19：投屏页已删除（A31），页面清单去掉 cast
  // 2026-11-21（第 7 批需求3）：ui / text 不再是独立一级页面，
  // 内容搬进 #page-file 的三个子视图（fileview-data / fileview-ui / fileview-text）。
  var PAGES = ['cmd','quick','file'];
  var FILEVIEWS = ['data','ui','text'];
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
      // 2026-11-19：投屏页已删除（改外部 scrcpy 窗口），页签 6 → 5
      // 2026-11-21（第 7 批需求3）：UI / 文本并入文件页，一级页签只剩三个
      // 2026-11-22（第 10 批需求）：末尾新增「Monkey」稳定性测试页。
      // 前三个的顺序仍然冻结，只在尾部追加，不影响既有习惯。
      // 2026-11-22（第 11 批需求）：末尾再追加「诊断」页。
      // 顺序仍然冻结在前，只在尾部追加，不影响既有习惯。
      // 2026-11-22（第 17 批）：仪表页签已删除（并入「指令 → Scrcpy投屏」面板）
      ok('页签顺序为 指令→终端→文件→Monkey→诊断',
         order.join(',') === 'quick,cmd,file,monkey,diag', order.join(','));
      ok('第一个页签文字是「指令」', tabs[0].textContent.trim() === '指令', tabs[0].textContent);
      ok('第二个页签文字是「终端」', tabs[1].textContent.trim() === '终端', tabs[1].textContent);
      ok('第三个页签文字是「文件」', tabs[2].textContent.trim() === '文件',
         tabs[2] ? tabs[2].textContent : 'no-tab');
      // 文件页内三个二级分组
      for (var fv = 0; fv < FILEVIEWS.length; fv++){
        ok('fileview-' + FILEVIEWS[fv] + ' 存在',
           !!document.getElementById('fileview-' + FILEVIEWS[fv]));
      }
      ok('文件页导航有 4 个分组（数据/UI/文本/H5）',
         document.querySelectorAll('.filenav-item').length  === 4,
         document.querySelectorAll('.filenav-item').length);
      ok('文件页默认显示「数据互传」',
         document.getElementById('fileview-data')
         && document.getElementById('fileview-data').classList.contains('active'));
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

      // 2026-11-19（A31）：投屏页删除，castHasDisplay / castRow 等随页面一起下线；
      // 改成反向断言，防止哪天又把整页塞回来。
      ok('投屏页相关函数已随页面删除',
         typeof castHasDisplay === 'undefined' && typeof castRow === 'undefined'
         && typeof castToggle === 'undefined');

      // 5) UI 比对（2026-11-21 起并入文件页）：switchTab('ui') 应归一化到
      //    「文件页 + fileview-ui 子视图」，其它一级页面全部隐藏。
      switchTab('ui');
      var fileVisible = PAGES.filter(function(q){
        var e = document.getElementById('page-' + q);
        return e && getComputedStyle(e).display !== 'none';
      });
      ok('switchTab(ui) 归一化到文件页且只有文件页可见',
         fileVisible.length === 1 && fileVisible[0] === 'file', fileVisible.join(','));
      ok('文件页内切换到 UI 比对子视图',
         document.getElementById('fileview-ui')
         && document.getElementById('fileview-ui').classList.contains('active'));
      ok('数据互传子视图已隐藏',
         document.getElementById('fileview-data')
         && !document.getElementById('fileview-data').classList.contains('active'));
      ok('UI 比对子视图有开始对比/打开结果图按钮',
         !!document.getElementById('ui-open-result'));
      switchTab('text');
      ok('switchTab(text) 切到文本阅读子视图',
         document.getElementById('fileview-text')
         && document.getElementById('fileview-text').classList.contains('active'));
      ok('文本阅读子视图有编辑器',
         !!document.getElementById('tx-edit'));

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
        "--user-data-dir=", "--no-first-run", "--no-default-browser-check", "--disable-background-networking", "--disable-sync", "--disable-extensions", "--disable-component-update" + prof,
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
