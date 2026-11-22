"""智驾出行 + 定时框布局 + 搜索修复 回归测试（2026-11-22 第 14 批）。

覆盖：
  1. 智驾出行 17 张卡（10 新实现 + 6 复用 + heapdump）
  2. 带输入框的卡片（地图激活 / 设置时间）渲染出 .qinp
  3. 「切换繁体」在指令执行和智驾出行两处都有
  4. 定时框改成一行两列（grid）+ 无宽度溢出（上一版左右各撑出 15px 被裁）
  5. ★ 搜索时定时框必须隐藏 —— 第 12 批的 bug：
     renderSearchResults 有两份，改的是被覆盖的那份，实际没生效
  6. HeapDump 浮层能打开、能渲染列表
  7. 带输入框的卡片空值被拦截

运行：python 377/_test_drive.py
"""
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")


def _find_edge():
    for c in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
        if os.path.exists(c):
            return c
    return "msedge.exe"


EDGE = _find_edge()

PROBE = r"""
<script>
window.__E=[];
window.addEventListener('error', function(e){ window.__E.push(String(e.message)); });

/* R / ok / done 放全局。
   done() 可能在 setTimeout 之外被调用，放内部会访问不到 R。 */
var R = [];
function ok(n, c, e){
  R.push((c?'PASS':'FAIL') + ' | ' + n + (c?'':' -> ' + (e===undefined?'':e)));
}
function finish(){
  var pre = document.createElement('pre');
  pre.id = 'DRIVE_RESULT';
  pre.textContent = JSON.stringify(R);
  document.body.appendChild(pre);
}

/* 记录页面发出的消息（headless Edge 没有 chrome.webview，这里造一个） */
var heapSent = 0, runSent = 0;
window.chrome = window.chrome || {};
window.chrome.webview = { postMessage: function(o){
  if(!o) return;
  if(o.kind === 'heaplist') heapSent++;
  // 卡片执行走的是 post('quick', cmd)，不是 post('run') —— 见 runQuickAt 末尾
  if(o.kind === 'quick') runSent++;
}};

setTimeout(function(){
  try { runAll(); } catch(err) {
    ok('探针异常', false, String(err));
    finish();
  }
}, 1800);

function runAll(){

  /* ---------- 1. 智驾出行 17 张卡 ---------- */
  var driveIdx = -1;
  for(var i=0;i<quickGroups.length;i++) if(quickGroups[i].name==='智驾出行') driveIdx=i;
  ok('存在智驾出行分组', driveIdx >= 0);
  if(driveIdx < 0){ finish(); return; }

  var drive = quickGroups[driveIdx];
  var names = drive.items.map(function(x){return x.name;});
  ok('智驾出行 18 张卡', drive.items.length === 18, drive.items.length + ' :: ' + names.join(','));

  var want = ['查询地图信息','停止地图进程','清理地图数据','地图激活',
              '导出全日志','导出日志（不含高德/QNX）','导出 QNX 日志',
              '导出微信小程序日志','导出高德日志','抓 Java 堆（heapdump）',
              '触控点打开','触控点关闭','开启坐标','关闭坐标',
              '切换繁体','修改系统时间','设置时间','恢复系统时间'];
  want.forEach(function(n){
    ok('含卡片：' + n, names.indexOf(n) >= 0);
  });

  /* ---------- 2. 带输入框的卡片 ---------- */
  _quickIdx = driveIdx; _quickFilter = ''; renderQuickItems();
  var grid = document.getElementById('quick-grid');
  var inpCards = grid.querySelectorAll('.qcard.hasinp');
  ok('有输入框的卡片 2 个（地图激活/设置时间）', inpCards.length === 2, inpCards.length);
  var inpEls = grid.querySelectorAll('.qcard .qinp');
  ok('输入框元素渲染 2 个', inpEls.length === 2, inpEls.length);
  if(inpEls.length) ok('输入框有 placeholder',
                       !!inpEls[0].getAttribute('placeholder'),
                       inpEls[0].getAttribute('placeholder'));
  ok('卡片总数 = items 数', grid.querySelectorAll('.qcard').length === drive.items.length,
     grid.querySelectorAll('.qcard').length);

  /* ---------- 3. 切换繁体两处都有 ---------- */
  var execIdx = -1;
  for(var j=0;j<quickGroups.length;j++) if(quickGroups[j].name==='指令执行') execIdx=j;
  var execNames = execIdx>=0 ? quickGroups[execIdx].items.map(function(x){return x.name;}) : [];
  ok('切换繁体在智驾出行', names.indexOf('切换繁体') >= 0);
  ok('切换繁体在指令执行', execNames.indexOf('切换繁体') >= 0);

  /* ---------- 4. 定时框两列布局 ---------- */
  var vrIdx = -1;
  for(var k=0;k<quickGroups.length;k++) if(quickGroups[k].name==='语音助手') vrIdx=k;
  ok('存在语音助手分组', vrIdx >= 0);
  _quickIdx = vrIdx; renderQuickItems();

  var row2 = document.getElementById('tt-row2');
  ok('两列容器存在', !!row2);
  ok('语音助手分组显示两列容器', row2 && row2.style.display !== 'none',
     row2 ? row2.style.display : 'null');

  if(row2){
    var cs = getComputedStyle(row2);
    ok('容器是 grid', cs.display === 'grid', cs.display);
    ok('宽屏 2 列', (cs.gridTemplateColumns.match(/px/g)||[]).length === 2, cs.gridTemplateColumns);

    var logBox = document.getElementById('tt-log-box');
    var crashBox = document.getElementById('tt-crash-box');
    ok('两个框都存在', !!logBox && !!crashBox);

    var r2 = row2.getBoundingClientRect();
    var lb = logBox.getBoundingClientRect();
    var cb = crashBox.getBoundingClientRect();

    /* ★ 上一版 bug：左右各撑出 15px 被父容器裁掉 */
    ok('导出框未溢出容器左侧', lb.left >= r2.left - 1,
       'box=' + lb.left.toFixed(1) + ' row=' + r2.left.toFixed(1));
    ok('导出框未溢出容器右侧', lb.right <= r2.right + 1,
       'box=' + lb.right.toFixed(1) + ' row=' + r2.right.toFixed(1));
    ok('异常框未溢出容器', cb.left >= r2.left - 1 && cb.right <= r2.right + 1,
       cb.left.toFixed(1) + '~' + cb.right.toFixed(1));
    ok('两个框等宽', Math.abs(lb.width - cb.width) < 1.5,
       lb.width.toFixed(1) + ' vs ' + cb.width.toFixed(1));

    /* 关键文字没被裁（上一版"间隔"变"隔"） */
    var logTxt = logBox.textContent;
    ok('文字完整：定时导出日志', logTxt.indexOf('定时导出日志') >= 0, logTxt.slice(0,40));
    ok('文字完整：间隔', logTxt.indexOf('间隔') >= 0);
    ok('文字完整：未启动', logTxt.indexOf('未启动') >= 0);

    ok('导出框无横向溢出', logBox.scrollWidth <= logBox.clientWidth + 2,
       'scrollW=' + logBox.scrollWidth + ' clientW=' + logBox.clientWidth);
  }

  /* ---------- 5. ★ 搜索时定时框必须隐藏 ---------- */
  ok('搜索前定时框可见', document.getElementById('tt-row2').style.display !== 'none');

  var sEl = document.getElementById('quick-search');
  if(sEl) sEl.value = '坐标';
  _quickFilter = '坐标';
  renderQuickItems();

  ok('标题变搜索结果',
     document.getElementById('quick-group-name').textContent === '搜索结果',
     document.getElementById('quick-group-name').textContent);
  ok('★ 搜索后定时框已隐藏（第12批 bug 修复）',
     document.getElementById('tt-row2').style.display === 'none',
     document.getElementById('tt-row2').style.display);
  ok('搜索后语音面板隐藏',
     document.getElementById('vr-panel').style.display === 'none');
  ok('搜索结果有卡片',
     document.querySelectorAll('#quick-grid .qcard').length > 0,
     document.querySelectorAll('#quick-grid .qcard').length);

  if(sEl) sEl.value = '';
  _quickFilter = '';
  _quickIdx = vrIdx;
  renderQuickItems();
  ok('清搜索后定时框恢复',
     document.getElementById('tt-row2').style.display !== 'none',
     document.getElementById('tt-row2').style.display);

  /* ---------- 6. HeapDump 浮层 ---------- */
  ok('浮层元素存在', !!document.getElementById('heap-mask'));
  ok('浮层默认隐藏', document.getElementById('heap-mask').style.display === 'none');

  openHeapDump();
  ok('打开后显示', document.getElementById('heap-mask').style.display === 'flex',
     document.getElementById('heap-mask').style.display);
  ok('打开时发了 heaplist', heapSent > 0, heapSent);

  heapOnList({kind:'heaplist', ok:true, rows:[
    {pid:'1234', rss:'395264', name:'space.syncore.cockpit.map'},
    {pid:'890',  rss:'120000', name:'com.android.systemui'},
    {pid:'77',   rss:'2048',   name:'com.example.small'}
  ]});
  var rows = document.querySelectorAll('#heap-list .heap-row');
  ok('列表渲染 3 行', rows.length === 3, rows.length);
  ok('第一行是内存最大的',
     rows[0] && rows[0].textContent.indexOf('space.syncore.cockpit.map') >= 0);
  ok('显示 MB', rows[0] && /MB|GB/.test(rows[0].textContent));
  ok('显示 PID', rows[0] && rows[0].textContent.indexOf('PID 1234') >= 0);

  var hs = document.getElementById('heap-search');
  hs.value = 'systemui';
  heapFilter();
  ok('过滤生效', document.querySelectorAll('#heap-list .heap-row').length === 1,
     document.querySelectorAll('#heap-list .heap-row').length);

  hs.value = '';
  heapFilter();
  heapPick('1234');
  ok('选中显示进程名',
     document.getElementById('heap-sel').textContent.indexOf('space.syncore.cockpit.map') >= 0);
  ok('dump 按钮可用', document.getElementById('heap-go').disabled === false);

  closeHeapDump();
  ok('关闭后隐藏', document.getElementById('heap-mask').style.display === 'none');

  /* ---------- 7. 空输入拦截 ---------- */
  // headless 里默认 _online=false，卡片执行会被"设备未连接"直接拦掉，
  // 测不出输入框逻辑。这里显式置 true。
  _online = true;
  _quickIdx = driveIdx; _quickFilter = ''; renderQuickItems();
  var actJ = -1;
  for(var m=0;m<drive.items.length;m++){
    if(drive.items[m].name === '地图激活') actJ = m;
  }
  ok('找到地图激活卡片', actJ >= 0, actJ);

  var before = runSent;
  if(actJ >= 0) runQuick(actJ);
  ok('空输入被拦截（不发命令）', runSent === before, runSent - before);

  /* ---------- 8. 输入有值时应发命令 ---------- */
  var inp = grid ? grid.querySelector('.qcard.hasinp .qinp') : null;
  if(inp && actJ >= 0){
    inp.value = 'A1B2C3';
    var before2 = runSent;
    runQuick(actJ);
    ok('填值后能执行', runSent > before2, runSent - before2);
  }

  ok('无运行时错误', window.__E.length === 0, window.__E.join('; '));

  finish();
}
</script>
"""


def main():
    src = open(UI, encoding="utf-8").read()
    tmp = os.path.join(ROOT, "377", "_drive.html")
    open(tmp, "w", encoding="utf-8", newline="").write(src.replace("</body>", PROBE + "</body>"))
    try:
        p = subprocess.run(
            [EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--no-first-run", "--no-default-browser-check",
             "--disable-background-networking", "--disable-sync",
             "--disable-extensions", "--disable-component-update",
             "--user-data-dir=" + os.path.join(tempfile.gettempdir(), "edgeprof_drive"),
             "--window-size=1400,900", "--virtual-time-budget=14000", "--dump-dom",
             "file:///" + tmp.replace("\\", "/")],
            capture_output=True, timeout=180)
        dom = p.stdout.decode("utf-8", "replace")
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass

    m = re.search(r'<pre id="DRIVE_RESULT">(.*?)</pre>', dom, re.S)
    if not m:
        print("!! 探针未返回")
        for mm in re.finditer(r"(Uncaught[^<\n]{0,220})", dom):
            print("   ", mm.group(1))
        return 2

    results = json.loads(m.group(1))
    for line in results:
        print("  " + line)
    fail = sum(1 for r in results if r.startswith("FAIL"))
    print("")
    print("  智驾出行/布局/搜索：通过 %d / %d" % (len(results) - fail, len(results)))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
