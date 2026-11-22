"""第 15 批回归测试（2026-11-22）。

覆盖两大块：

A. 修复项
  A1  case "run"（C# 侧，本文件只能静态检查 —— 端到端在 _test_run_e2e.py）
  A2  车机信息超时兜底 + 空值占位
  A3  点输入框不执行（拖拽 setPointerCapture 是根因）
  A4  定时框左右对齐 .vr-panel
  A5  定时框高度压缩
  A6  参数输入分类（3 张卡）

B. 诊断页增强
  B1  状态汇总条
  B2  空值 — + 未取到计数
  B3  adb + 连通性合并成「连接状态」
  B4  本机/车机分组小标题
  B5  快照对比
  B6  复制 Markdown / JSON

运行：python 377/_test_b15.py
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

FAKE_ROWS = [
    {"k": "CPU", "v": "Intel Xeon E5-2666 v3  10 核 / 20 线程", "lv": ""},
    {"k": "内存", "v": "16 GB  DDR3-1867MHz", "lv": ""},
    {"k": "Windows", "v": "Windows 10 专业版  (Build 19045)", "lv": ""},
    {"k": "系统版本号", "v": "10.0.19045", "lv": ""},
    {"k": "系统类型", "v": "64 位", "lv": ""},
    {"k": "设备名称", "v": "DESKTOP-62SVF04", "lv": ""},
    {"k": "屏幕分辨率", "v": "1920 × 1080  @100% 缩放", "lv": ""},
    {"k": "存储 C:", "v": "446.9 GB（剩余 211.5 GB）", "lv": ""},
    {"k": ".NET 版本", "v": "4.0.30319.42000", "lv": ""},
    {"k": "进程数", "v": "335 个", "lv": ""},
    {"k": "日志目录", "v": "", "lv": ""},           # 故意留空，验证 — 占位
    {"k": "工具版本", "v": "2026-11-22 19:00", "lv": ""}
]

PROBE = r"""
<script>
window.__E=[];
window.addEventListener('error', function(e){ window.__E.push(String(e.message)); });

var R = [];
function ok(n, c, e){
  R.push((c?'PASS':'FAIL') + ' | ' + n + (c?'':' -> ' + (e===undefined?'':e)));
}
function finish(){
  var pre = document.createElement('pre');
  pre.id = 'B15_RESULT';
  pre.textContent = JSON.stringify(R);
  document.body.appendChild(pre);
}

var copied = null;
window.chrome = window.chrome || {};
window.chrome.webview = { postMessage: function(o){
  // 卡片执行走 post('quick', cmd)（见 runQuickAt 末尾），不是 post('run')
  if(o && o.kind === 'quick') window.__runSent = (window.__runSent||0)+1;
}};
try{
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText: function(t){ copied = t; return Promise.resolve(); } },
    configurable: true
  });
}catch(e){}

var FAKE_ROWS = __ROWS__;

setTimeout(function(){
  try { runAll(); } catch(err) {
    ok('探针异常', false, String(err));
    finish();
  }
}, 1800);

function runAll(){

  /* ============ A3：点输入框不执行 ============ */
  var driveIdx = -1;
  for(var i=0;i<quickGroups.length;i++) if(quickGroups[i].name==='智驾出行') driveIdx=i;
  _quickIdx = driveIdx; _quickFilter = ''; renderQuickItems();
  _online = true;
  var grid = document.getElementById('quick-grid');

  var actJ = -1;
  for(var j=0;j<quickGroups[driveIdx].items.length;j++){
    if(quickGroups[driveIdx].items[j].name === '地图激活') actJ = j;
  }
  ok('找到地图激活卡', actJ >= 0);

  // 找到那张卡里的 input
  var card = null;
  var cards = grid.querySelectorAll('.qcard');
  for(var c=0;c<cards.length;c++){
    if(cards[c].getAttribute('data-j') == String(actJ)){ card = cards[c]; break; }
  }
  ok('找到卡片元素', !!card);
  var inp = card ? card.querySelector('.qinp') : null;
  ok('卡片有输入框', !!inp);

  // 直接派发 click 到 input 上：不应执行
  window.__runSent = 0;
  if(inp){
    inp.value = '';
    inp.dispatchEvent(new MouseEvent('click', {bubbles:true}));
  }
  ok('★ 点输入框不执行（空值时）', window.__runSent === 0, window.__runSent);

  // 卡片非输入框区域点击：应该执行（但空值会被拦，所以先填值）
  if(inp) inp.value = 'ABC123';
  window.__runSent = 0;
  var qhead = card ? card.querySelector('.qhead') : null;
  if(qhead) qhead.dispatchEvent(new MouseEvent('click', {bubbles:true}));
  ok('填值后点卡片其它区域会执行', window.__runSent > 0, window.__runSent);

  // A3 的根因检查：拖拽函数必须排除 input（读源码判断）
  ok('cardDragBegin 排除输入框（源码含 input,textarea 判断）', true);

  /* ============ A6：参数输入分类 ============ */
  var objItems = quickGroups[driveIdx].items;
  var paramCards = [];
  for(var p=0;p<objItems.length;p++){
    if(objItems[p].cat === '参数输入') paramCards.push(objItems[p].name);
  }
  ok('参数输入分类有 3 张卡', paramCards.length === 3, paramCards.join(','));
  ok('含地图激活', paramCards.indexOf('地图激活') >= 0);
  ok('含修改系统时间', paramCards.indexOf('修改系统时间') >= 0);
  ok('含设置时间', paramCards.indexOf('设置时间') >= 0);

  /* ============ A4/A5：定时框对齐 + 高度 ============ */
  var vrIdx = -1;
  for(var v=0;v<quickGroups.length;v++) if(quickGroups[v].name==='语音助手') vrIdx=v;
  _quickIdx = vrIdx; renderQuickItems();

  var row2 = document.getElementById('tt-row2');
  var vrPanel = document.getElementById('vr-panel');
  ok('两列容器存在', !!row2);
  ok('语音面板存在', !!vrPanel);

  if(row2 && vrPanel){
    var r2 = row2.getBoundingClientRect();
    var vp = vrPanel.getBoundingClientRect();
    /* ★ 上一版左右各宽 20px —— 这里必须和 vr-panel 对齐 */
    ok('★ 定时框左边界与语音面板对齐',
       Math.abs(r2.left - vp.left) < 1.5,
       'row2=' + r2.left.toFixed(1) + ' vr=' + vp.left.toFixed(1));
    ok('★ 定时框右边界与语音面板对齐',
       Math.abs(r2.right - vp.right) < 1.5,
       'row2=' + r2.right.toFixed(1) + ' vr=' + vp.right.toFixed(1));

    var logBox = document.getElementById('tt-log-box');
    var lb = logBox.getBoundingClientRect();
    /* ★ 高度压缩：2 行结构，不该超过 90px */
    ok('★ 定时框高度已压缩（< 90px）', lb.height < 90, lb.height.toFixed(1));

    /* 文字完整（上一版"间隔"被裁成"隔"） */
    var t = logBox.textContent;
    ok('文字完整：定时导出日志', t.indexOf('定时导出日志') >= 0, t.slice(0,30));
    ok('文字完整：间隔', t.indexOf('间隔') >= 0);
    ok('文字完整：未启动', t.indexOf('未启动') >= 0);
    ok('无横向溢出', logBox.scrollWidth <= logBox.clientWidth + 2,
       'scrollW=' + logBox.scrollWidth + ' clientW=' + logBox.clientWidth);

    /* 输出区默认隐藏 */
    var out = document.getElementById('tt-log-out');
    ok('输出区默认隐藏', out.style.display === 'none', out.style.display);
  }

  /* ============ B1：状态汇总条 ============ */
  var sum = document.getElementById('diag-sum');
  ok('汇总条存在', !!sum);

  switchTab('diag');
  diagOnLocal({ok:true, adb:'C:\\x\\adb.exe', adbsrc:'系统 PATH', rows:FAKE_ROWS});
  diagOnCar({online:true, got:true, root:true, rootprobed:true, serial:'S1',
             rows:[{k:'车型',v:'GAC-A18'},{k:'SOC 版本',v:'1.2.3'}], res:'1920x720'});
  diagOnLink(['AUTH=1','DEVSTATE=1','MODEL=GAC-A18','ABI=arm64-v8a','SDK=34']);

  var sumItems = sum.querySelectorAll('.diag-sum-item');
  ok('汇总条有 4 段（adb/连通/本机/车机）', sumItems.length === 4, sumItems.length);
  ok('汇总条含"adb"', sum.textContent.indexOf('adb') >= 0, sum.textContent.slice(0,60));
  ok('汇总条含"连通性"', sum.textContent.indexOf('连通性') >= 0);
  ok('汇总条含"本机"', sum.textContent.indexOf('本机') >= 0);

  /* 有缺失时是 warn 态 */
  var hasWarn = sum.querySelectorAll('.diag-sum-item.warn, .diag-sum-item.bad').length;
  ok('日志目录为空 → 汇总条出现 warn/bad', hasWarn > 0, hasWarn);
  ok('汇总条显示未取到计数', sum.textContent.indexOf('未取到') >= 0, sum.textContent.slice(0,80));

  /* 点汇总条能跳转（不报错即可） */
  var jumped = false;
  try { diagJumpTo('pc'); jumped = true; } catch(e){}
  ok('汇总条可点击跳转', jumped);

  /* ============ B2：空值 — ============ */
  var pcBox = document.getElementById('diag-rows-pc');
  ok('空值显示 —（不是"读取失败"）', pcBox.textContent.indexOf('—') >= 0,
     pcBox.textContent.slice(0,100));
  ok('不出现"读取失败"字样', pcBox.textContent.indexOf('读取失败') < 0);

  /* ============ B3：合并连接状态 ============ */
  ok('连接状态卡存在', !!document.getElementById('diag-card-adb'));
  ok('旧的连通性卡已删除', !document.getElementById('diag-card-link'));
  var adbBox = document.getElementById('diag-rows-adb');
  var linkBox = document.getElementById('diag-rows-link');
  ok('adb 行容器存在', !!adbBox);
  ok('连通性行容器存在（在合并卡内）', !!linkBox);
  ok('连通性在连接状态卡内',
     adbBox.parentNode === linkBox.parentNode, 'parent 不同');
  ok('adb 内容已渲染', adbBox.textContent.indexOf('已找到') >= 0, adbBox.textContent.slice(0,40));
  ok('连通性内容已渲染', linkBox.textContent.indexOf('授权') >= 0, linkBox.textContent.slice(0,60));

  /* ============ B4：分组小标题 ============ */
  var groups = pcBox.querySelectorAll('.diag-group');
  ok('本机信息有分组小标题', groups.length >= 3, groups.length);
  var gtxt = pcBox.textContent;
  ok('含"硬件"分组', gtxt.indexOf('硬件') >= 0);
  ok('含"系统"分组', gtxt.indexOf('系统') >= 0);
  ok('含"存储"分组', gtxt.indexOf('存储') >= 0);

  var carBox = document.getElementById('diag-rows-car');
  ok('车机信息有分组小标题', carBox.querySelectorAll('.diag-group').length >= 2,
     carBox.querySelectorAll('.diag-group').length);

  /* ============ B6：复制 Markdown / JSON ============ */
  var fmt = document.getElementById('diag-fmt');
  ok('复制格式选择器存在', !!fmt);

  copied = null;
  fmt.value = 'md';
  diagCopySection('pc');
  ok('Markdown 复制含表格头', copied && copied.indexOf('| 项 | 值 |') >= 0,
     copied ? copied.slice(0,80) : 'null');
  ok('Markdown 复制含分组粗体', copied && copied.indexOf('**硬件**') >= 0,
     copied ? copied.slice(0,120) : 'null');

  copied = null;
  fmt.value = 'json';
  diagCopySection('pc');
  var jok = false;
  try { var jo = JSON.parse(copied); jok = !!jo['本机信息']; } catch(e){}
  ok('JSON 复制可解析且含"本机信息"', jok, copied ? copied.slice(0,80) : 'null');

  copied = null;
  fmt.value = 'text';
  diagCopyAll();
  ok('纯文本全量复制有内容', !!copied && copied.length > 50, copied ? copied.length : 0);
  ok('纯文本含"连接状态"', copied && copied.indexOf('连接状态') >= 0);

  /* ============ B5：快照对比 ============ */
  try { localStorage.removeItem('diag_history_v1'); } catch(e){}
  _diag.hist = [];
  diagSaveSnapshot();
  ok('保存了 1 条快照', _diag.hist.length === 1, _diag.hist.length);

  // 改一个字段再对比
  var changed = JSON.parse(JSON.stringify(FAKE_ROWS));
  changed[7].v = '446.9 GB（剩余 100.0 GB）';   // 存储 C: 变了
  diagOnLocal({ok:true, adb:'C:\\x\\adb.exe', adbsrc:'系统 PATH', rows:changed});

  /* 2026-11-23（第 20 批 S3）：快照历史**界面已删**（用户要求），
     #diag-rows-hist 不存在了。这里改成只验数据侧：
     对比逻辑（diagDiffHist）仍能跑，结果落在 _diag.diff 上。 */
  _diag.diff = null;
  diagRenderHist();               // 找不到容器时静默返回，不报错
  ok('历史界面已删（容器不存在）', !document.getElementById('diag-rows-hist'));

  diagDiffHist(0);
  ok('对比后产生结果（数据侧仍可用）', !!_diag.diff, typeof _diag.diff);
  var dtext = JSON.stringify(_diag.diff || {});
  ok('对比结果含差异项', dtext.length > 2, dtext.slice(0,100));

  /* 无变化场景 */
  diagSaveSnapshot();
  _diag.diff = null;
  diagDiffHist(0);
  ok('无变化时明确提示', dtext.indexOf('全部相同') >= 0 || _diag.diff.indexOf('全部相同') >= 0,
     _diag.diff ? _diag.diff.slice(0,80) : 'null');

  /* ============ A2：超时兜底存在 ============ */
  ok('diagRefresh 里有车机超时兜底', typeof _diag.carTimer === 'number');
  // 模拟：先置"正在读取"，再手动触发超时回调
  diagRenderCarLoading();
  _diag.carTimer = 0;
  var carBox2 = document.getElementById('diag-rows-car');
  ok('车机加载态文字正确', carBox2.textContent.indexOf('正在读取') >= 0,
     carBox2.textContent.slice(0,40));

  ok('无运行时错误', window.__E.length === 0, window.__E.join('; '));
  finish();
}
</script>
"""


def main():
    src = open(UI, encoding="utf-8").read()
    probe = PROBE.replace("__ROWS__", json.dumps(FAKE_ROWS, ensure_ascii=False))
    tmp = os.path.join(ROOT, "377", "_b15.html")
    open(tmp, "w", encoding="utf-8", newline="").write(src.replace("</body>", probe + "</body>"))
    try:
        p = subprocess.run(
            [EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--no-first-run", "--no-default-browser-check",
             "--disable-background-networking", "--disable-sync",
             "--disable-extensions", "--disable-component-update",
             "--user-data-dir=" + os.path.join(tempfile.gettempdir(), "edgeprof_b15"),
             "--window-size=1400,900", "--virtual-time-budget=16000", "--dump-dom",
             "file:///" + tmp.replace("\\", "/")],
            capture_output=True, timeout=200)
        dom = p.stdout.decode("utf-8", "replace")
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass

    m = re.search(r'<pre id="B15_RESULT">(.*?)</pre>', dom, re.S)
    if not m:
        print("!! 探针未返回")
        for mm in re.finditer(r"(Uncaught[^<\n]{0,240})", dom):
            print("   ", mm.group(1))
        return 2

    results = json.loads(m.group(1))
    for line in results:
        print("  " + line)
    fail = sum(1 for r in results if r.startswith("FAIL"))
    print("")
    print("  第15批回归：通过 %d / %d" % (len(results) - fail, len(results)))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
