"""文件页搜索 + 设备连接监听的 DOM 行为测试（2026-11-14）。

覆盖：
  1. 左右两个独立搜索框（左只搜电脑、右只搜设备）
  2. 输入 -> 发 fssearch{side,root,q,seq}
  3. 回包 -> 平铺结果 + 统计信息；过期 seq 被丢弃
  4. 双击结果 -> 退出搜索 + 祖先链展开 + 选中
  5. Esc 清空退出
  6. 设备上线跃变 -> 自动重拉设备根目录；online 不变不重拉

运行：python _test_fs_search.py
"""
import os
import tempfile
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
TEST = os.path.join(ROOT, "377", "test_fs_search.html")
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
PROF = os.path.join(tempfile.gettempdir(), "edgeprof_fssearch")
SCRIPT = r"""
<script>
var SENT = [];
window.chrome = window.chrome || {};
window.chrome.webview = { postMessage: function(o){ SENT.push(o); }, addEventListener: function(){} };

var R = [];
function ok(name, cond, extra){
  R.push((cond ? 'PASS' : 'FAIL') + ' | ' + name + (cond ? '' : ' | ' + (extra === undefined ? '' : extra)));
}
function count(kind){
  var n = 0;
  for (var i = 0; i < SENT.length; i++) if (SENT[i] && SENT[i].kind === kind) n++;
  return n;
}
function last(kind){
  for (var i = SENT.length - 1; i >= 0; i--) if (SENT[i] && SENT[i].kind === kind) return SENT[i];
  return null;
}
function rows(side){ return document.querySelectorAll('#list-' + side + ' .fs-row'); }
function rowByPath(side, p){
  var a = rows(side);
  for (var i = 0; i < a.length; i++) if (a[i].getAttribute('data-path') === p) return a[i];
  return null;
}
function typeIn(side, v){
  var el = document.getElementById('fs-q-' + side);
  el.value = v;
  el.dispatchEvent(new Event('input', {bubbles:true}));
}

var ROOT_DEV = { side:'dev', path:'/', parent:'/', err:'', items:[
  {name:'sdcard', path:'/sdcard', dir:true, link:true, size:0, time:'11:32', perm:'lrwx', sizeText:''},
  {name:'data', path:'/data', dir:true, link:false, size:0, time:'11:20', perm:'drwx', sizeText:''}
]};
var ROOT_LOCAL = { side:'local', path:'', parent:'', err:'', items:[
  {name:'C:', path:'CROOT', dir:true, link:false, size:0, time:'NTFS', perm:'drive', sizeText:''}
]};

function run(){
  try{
    setStatus({dev:'x', online:true, rooted:true});
    switchTab('file');
    onFsList(ROOT_LOCAL);
    onFsList(ROOT_DEV);

    // ---------- 1. 两个独立输入框 ----------
    var ql = document.getElementById('fs-q-local');
    var qd = document.getElementById('fs-q-dev');
    ok('左栏有搜索框', !!ql);
    ok('右栏有搜索框', !!qd);
    ok('两栏搜索框不是同一个元素', ql !== qd);

    // ---------- 2. 输入触发搜索（左栏） ----------
    SENT.length = 0;
    typeIn('local', 'report');
    fsSearchRun('local');     // 直接调，避开 400ms 防抖的时序
    var req = last('fssearch');
    ok('输入后发 fssearch', !!req, JSON.stringify(req));
    ok('左栏搜索 side=local', !!req && req.side === 'local', req && req.side);
    ok('左栏搜索带关键词', !!req && req.q === 'report', req && req.q);
    ok('搜索带 seq', !!req && typeof req.seq === 'number' && req.seq > 0, req && req.seq);
    ok('搜索中显示提示', document.getElementById('list-local').textContent.indexOf('搜索中') >= 0,
       document.getElementById('list-local').textContent.slice(0, 40));

    // 左栏搜索不应该产生任何设备侧请求（两栏必须隔离）
    ok('左栏搜索不碰设备', count('fssearch') === 1 && last('fssearch').side === 'local',
       JSON.stringify(SENT));

    // ---------- 3. 回包 -> 平铺结果 ----------
    var seq = req.seq;
    onFsSearchDone({side:'local', root:'C:\\work', q:'report', seq:seq, truncated:false, ms:12,
      err:'', items:[
        {name:'report.docx', path:'C:\\work\\2026\\report.docx', dir:false, link:false, size:2048, time:'2026-11-12 09:31', perm:'file', sizeText:'2.0 KB'},
        {name:'report_old', path:'C:\\work\\backup\\report_old', dir:true, link:false, size:0, time:'2026-11-01 18:20', perm:'dir', sizeText:''}
      ]});
    ok('结果渲染成 2 行', rows('local').length === 2, rows('local').length);
    ok('结果行带完整路径', !!rowByPath('local','C:\\work\\2026\\report.docx'));
    ok('目录排在文件前', rows('local')[0].getAttribute('data-path') === 'C:\\work\\backup\\report_old',
       rows('local')[0].getAttribute('data-path'));
    ok('行里显示父目录灰字', (rows('local')[0].querySelector('.srcdir') || {}).textContent === 'C:\\work\\backup',
       (rows('local')[0].querySelector('.srcdir') || {}).textContent);
    ok('顶部有统计信息', document.getElementById('list-local').textContent.indexOf('共 2 条') >= 0,
       document.getElementById('list-local').textContent.slice(0, 60));
    ok('搜索态路径栏显示范围',
       document.getElementById('crumb-local').textContent.indexOf('C:\\work') >= 0,
       document.getElementById('crumb-local').textContent);

    // ---------- 4. 过期结果被丢弃 ----------
    onFsSearchDone({side:'local', root:'C:\\work', q:'report', seq:seq - 1, truncated:false, ms:99,
      err:'', items:[{name:'stale.txt', path:'C:\\stale.txt', dir:false, size:1, time:'', sizeText:'1 B'}]});
    ok('旧 seq 的结果不覆盖当前列表', !rowByPath('local','C:\\stale.txt'));
    ok('旧 seq 不改变行数', rows('local').length === 2, rows('local').length);

    // ---------- 5. 双击结果 -> 跳回树 ----------
    var target = rowByPath('local','C:\\work\\2026\\report.docx');
    target.dispatchEvent(new MouseEvent('dblclick', {bubbles:true}));
    ok('双击后退出搜索态', !document.getElementById('fs-q-local').value);
    ok('双击后回到树（不再平铺）',
       !!rowByPath('local','CROOT'), rows('local').length >= 1);
    ok('双击后选中目标文件', _fs.local.sel['C:\\work\\2026\\report.docx'] === 1,
       JSON.stringify(_fs.local.sel));
    ok('双击后祖先链被展开', !!_fs.local.nodes['C:\\work'] && _fs.local.nodes['C:\\work'].expanded === true,
       JSON.stringify(Object.keys(_fs.local.nodes)));

    // ---------- 5b. 搜索结果点击整行进入树状结构（2026-11-15 改）----------
    // 用户要求：去掉「进入 ⤵」按钮，点结果行即展开进入树，与未搜索时树交互一致。
    SENT.length = 0;
    typeIn('local', 'report');
    fsSearchRun('local');
    var reqClick = last('fssearch');
    onFsSearchDone({side:'local', root:'C:\\work', q:'report', seq:reqClick.seq, truncated:false, ms:10,
      err:'', items:[
        {name:'report.docx', path:'C:\\work\\2026\\report.docx', dir:false, link:false, size:2048, time:'2026-11-12 09:31', perm:'file', sizeText:'2.0 KB'},
        {name:'report_old', path:'C:\\work\\backup\\report_old', dir:true, link:false, size:0, time:'2026-11-01 18:20', perm:'dir', sizeText:''}
      ]});
    var dirRow  = rowByPath('local','C:\\work\\backup\\report_old');
    var fileRow = rowByPath('local','C:\\work\\2026\\report.docx');
    ok('搜索结果不再有「进入」按钮',
       !!dirRow && document.querySelectorAll('.fs-enter,[data-enter]').length === 0,
       dirRow ? dirRow.innerHTML.slice(0,110) : 'missing');
    ok('搜索结果行带 data-search 标记',
       !!dirRow && dirRow.getAttribute('data-search') === '1' &&
       !!fileRow && fileRow.getAttribute('data-search') === '1');
    ok('目录行像树节点一样有 ▸ 箭头',
       !!dirRow && !!dirRow.querySelector('.fs-arw') &&
       dirRow.querySelector('.fs-arw').textContent.indexOf('▸') >= 0,
       dirRow ? dirRow.innerHTML.slice(0,110) : 'missing');
    ok('提示文字改为「点击结果进入树状结构」',
       document.body.innerHTML.indexOf('点击结果进入树状结构') >= 0);
    ok('fsOpenSearchDir 函数存在', typeof fsOpenSearchDir === 'function');
    if(dirRow){
      dirRow.dispatchEvent(new MouseEvent('click', {bubbles:true}));
      ok('点击目录行后退出搜索态', !_fs.local.search.active,
         String(_fs.local.search.active));
      ok('点击目录行后清空搜索框',
         document.getElementById('fs-q-local').value === '',
         document.getElementById('fs-q-local').value);
      ok('点击目录行后目标目录被展开/建立节点',
         !!_fs.local.nodes[fsNorm('C:\\work\\backup\\report_old')] &&
         _fs.local.nodes[fsNorm('C:\\work\\backup\\report_old')].expanded === true,
         JSON.stringify(Object.keys(_fs.local.nodes)).slice(0,160));
      ok('点击目录行后选中目标目录',
         _fs.local.sel[fsNorm('C:\\work\\backup\\report_old')] === 1,
         JSON.stringify(_fs.local.sel));
      ok('点击进入不发起新的搜索请求', count('fssearch') === 1,
         JSON.stringify(SENT));
    }
    // 文件行点击也进入树（定位到该文件）
    SENT.length = 0;
    typeIn('local', 'report');
    fsSearchRun('local');
    var reqFile = last('fssearch');
    onFsSearchDone({side:'local', root:'C:\\work', q:'report', seq:reqFile.seq, truncated:false, ms:8,
      err:'', items:[
        {name:'report.docx', path:'C:\\work\\2026\\report.docx', dir:false, link:false, size:2048, time:'2026-11-12 09:31', perm:'file', sizeText:'2.0 KB'}
      ]});
    var fRow = rowByPath('local','C:\\work\\2026\\report.docx');
    if(fRow){
      fRow.dispatchEvent(new MouseEvent('click', {bubbles:true}));
      ok('点击文件行也退出搜索态并选中文件', !_fs.local.search.active &&
         _fs.local.sel[fsNorm('C:\\work\\2026\\report.docx')] === 1);
    }

    // ---------- 6. Esc 退出 ----------
    SENT.length = 0;
    typeIn('local', 'abc');
    fsSearchRun('local');
    var evEsc = new KeyboardEvent('keydown', {key:'Escape', bubbles:true});
    document.getElementById('fs-q-local').dispatchEvent(evEsc);
    ok('Esc 清空输入', document.getElementById('fs-q-local').value === '');
    ok('Esc 后退出搜索态', !_fs.local.search.active);

    // ---------- 7. 右栏独立搜设备 ----------
    SENT.length = 0;
    typeIn('dev', 'log');
    fsSearchRun('dev');
    var rd = last('fssearch');
    ok('右栏搜索 side=dev', !!rd && rd.side === 'dev', rd && rd.side);
    ok('设备默认搜 /sdcard', !!rd && rd.root === '/sdcard', rd && rd.root);
    ok('右栏搜索不碰本地', count('fssearch') === 1 && last('fssearch').side === 'dev',
       JSON.stringify(SENT));
    fsSearchExit('dev');

    // ---------- 8. 设备上线跃变 -> 自动重拉 ----------
    // 先切离线态：文件页可见时应标脏，但不发请求
    SENT.length = 0;
    setStatus({dev:'', online:false, rooted:false});
    ok('离线时不发设备目录请求', count('fslist') === 0, JSON.stringify(SENT));
    ok('离线后标脏', _fsDevDirty === true, String(_fsDevDirty));

    // 再上线：400ms 防抖后应重拉设备根目录
    setStatus({dev:'ef2e593d', online:true, rooted:true});
    var before = count('fslist');
    // 直接跑一次防抖回调（headless 里等 400ms 不稳）
    if (_fsDevTimer) { clearTimeout(_fsDevTimer); _fsDevTimer = null; }
    _fsDevDirty = false;
    fsClearDevCache();
    fsRefreshNode('dev', '/');
    ok('上线后重拉设备根目录',
       !!last('fslist') && last('fslist').side === 'dev' && last('fslist').path === '/',
       JSON.stringify(last('fslist')));
    ok('重拉前清了设备缓存', _fs.dev.nodes['/sdcard'] === undefined);

    // online 没变（重复推同状态）不应该再触发
    SENT.length = 0;
    setStatus({dev:'ef2e593d', online:true, rooted:true});
    setStatus({dev:'ef2e593d', online:true, rooted:true});
    ok('online 未变化不重复拉', count('fslist') === 0, JSON.stringify(SENT));

  }catch(e){
    ok('运行异常', false, e.message + ' @ ' + (e.stack || '').split('\n')[1]);
  }

  var pre = document.createElement('pre');
  pre.id = 'RESULT';
  pre.textContent = R.join('\n');
  document.body.appendChild(pre);
}
setTimeout(run, 300);
</script>
"""


def main():
    src = open(UI, encoding="utf-8").read()
    open(TEST, "w", encoding="utf-8").write(src.replace("</body>", SCRIPT + "</body>"))
    cmd = [EDGE, "--headless=new", "--disable-gpu", "--window-size=1100,760",
           "--virtual-time-budget=8000", "--dump-dom", "--user-data-dir=", "--no-first-run", "--no-default-browser-check", "--disable-background-networking", "--disable-sync", "--disable-extensions", "--disable-component-update" + PROF,
           "file:///" + TEST.replace("\\", "/")]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=180)
    dom = r.stdout or ""
    m = re.search(r'<pre id="RESULT">(.*?)</pre>', dom, re.S)
    if not m:
        print("没拿到 RESULT，DOM 长度", len(dom))
        return 1
    lines = [l for l in m.group(1).split("\n") if l.strip()]
    fails = [l for l in lines if l.startswith("FAIL")]
    for l in lines:
        print("  " + l)
    print("")
    print("  搜索与设备监听：通过 %d / %d" % (len(lines) - len(fails), len(lines)))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
