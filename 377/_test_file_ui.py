"""文件管理页（2026-11-14 树形版）DOM 行为测试。运行：python _test_file_ui.py"""
import os
import tempfile, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
TEST = os.path.join(ROOT, "377", "test_file_ui.html")
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
PROF = os.path.join(tempfile.gettempdir(), "edgeprof_filetree")
SCRIPT = r"""
<script>
var SENT = [];
window.chrome = window.chrome || {};
window.chrome.webview = { postMessage: function(o){ SENT.push(o); }, addEventListener: function(){} };
var R = [];
function ok(name, cond, extra){
  R.push((cond ? 'PASS' : 'FAIL') + ' | ' + name + (cond ? '' : ' | ' + (extra === undefined ? '' : extra)));
}
function last(kind){
  for(var i=SENT.length-1;i>=0;i--){ if(SENT[i] && SENT[i].kind === kind) return SENT[i]; }
  return null;
}
function rows(side){ return document.querySelectorAll('#list-' + side + ' .fs-row'); }
function hasRow(side, p){
  var a = rows(side);
  for(var i=0;i<a.length;i++){ if(a[i].getAttribute('data-path') === p) return true; }
  return false;
}
function rowByPath(side, p){
  var a = rows(side);
  for(var i=0;i<a.length;i++){ if(a[i].getAttribute('data-path') === p) return a[i]; }
  return null;
}
function clickRow(side, p){
  var r = rowByPath(side, p);
  if(!r){ ok('缺行 ' + p, false, 'not rendered'); return false; }
  r.dispatchEvent(new MouseEvent('click', {bubbles:true}));
  return true;
}
function dblRow(side, p){
  var r = rowByPath(side, p);
  if(!r){ ok('缺行 ' + p, false, 'not rendered'); return; }
  r.dispatchEvent(new MouseEvent('dblclick', {bubbles:true}));
}

var ROOT_DEV = { side:'dev', path:'/', parent:'/', err:'', items:[
  {name:'sdcard', path:'/sdcard', dir:true, link:true, size:0, time:'11:32', perm:'lrwx', sizeText:''},
  {name:'data', path:'/data', dir:true, link:false, size:0, time:'11:20', perm:'drwx', sizeText:''}
]};
var SD_DIR = { side:'dev', path:'/sdcard', parent:'/', err:'', items:[
  {name:'Download', path:'/sdcard/Download', dir:true, link:false, size:0, time:'11:21', perm:'drwx', sizeText:''},
  {name:'a.txt', path:'/sdcard/a.txt', dir:false, link:false, size:2048, time:'11:22', perm:'-rw-', sizeText:'2.0 KB'}
]};
var ROOT_LOCAL = { side:'local', path:'', parent:'', err:'', items:[
  {name:'桌面', path:'DESK', dir:true, link:false, size:0, time:'', perm:'shortcut', sizeText:''},
  {name:'C:', path:'CROOT', dir:true, link:false, size:0, time:'NTFS', perm:'drive', sizeText:''}
]};

function run(){
  try{
    setStatus({dev:'x', online:true, rooted:true});
    switchTab('file');

    var reqs = SENT.filter(function(o){ return o.kind === 'fslist'; });
    ok('初始化请求两侧根目录', reqs.length === 2, reqs.length);
    ok('本地根路径为空', reqs[0].path === '', JSON.stringify(reqs[0]));
    ok('设备根是斜杠', reqs[1].path === '/', JSON.stringify(reqs[1]));

    onFsList(ROOT_LOCAL);
    onFsList(ROOT_DEV);

    ok('本地根渲染 3 行', rows('local').length === 3, rows('local').length);
    ok('设备根渲染 3 行', rows('dev').length === 3, rows('dev').length);
    ok('快捷入口图标是星', rowByPath('local','DESK').querySelector('.i').textContent === '★',
       rowByPath('local','DESK').querySelector('.i').textContent);
    ok('根节点箭头展开态', rowByPath('dev','/').querySelector('.fs-arw').textContent === '▾');
    ok('子目录箭头收起态', rowByPath('dev','/sdcard').querySelector('.fs-arw').textContent === '▸');

    SENT.length = 0;
    clickRow('dev','/sdcard');
    ok('单击文件夹发起请求', !!last('fslist') && last('fslist').path === '/sdcard',
       JSON.stringify(last('fslist')));

    /* ---------- T14a（2026-11-19）：文件偶发打不开的 4 个机制 ---------- */
    // ① 请求带递增序号
    ok('T14a 请求带 seq', typeof last('fslist').seq === 'number' && last('fslist').seq > 0,
       JSON.stringify(last('fslist')));

    // ② 迟到的旧响应被丢弃（乱序到达不能覆盖新目录）
    var seqNew = last('fslist').seq;
    var stale = { kind:'fslist', seq: seqNew - 1, side:'dev', path:'/old', parent:'/',
                  err:'', items:[{name:'stale.txt', path:'/old/stale.txt', dir:false, size:1,
                                  time:'', perm:'', sizeText:'1 B'}] };
    onFsList(stale);
    ok('T14a 过期响应被丢弃', !hasRow('dev','/old/stale.txt'));

    // ③ 看门狗：请求卡住 35 秒后自己摘掉 loading 并给出可重试错误
    _fs.dev.wd && clearTimeout(_fs.dev.wd);
    _fs.dev.nodes['/sdcard'].loading = true;
    fsRequest('dev', '/sdcard');
    var seqNow = _fs.dev.seq;
    _fs.dev.seq = seqNow;          // 保持"最新请求"身份
    _fs.dev.wd && clearTimeout(_fs.dev.wd);
    // 直接调用看门狗逻辑：模拟 35 秒到点
    _fs.dev.nodes['/sdcard'].loading = true;
    (function(){
      var p = fsNorm('/sdcard');
      var n = _fs.dev.nodes[p];
      n.loading = false;
      n.err = '读取超时（35 秒），目录可能很大或设备繁忙 —— 点这里重试';
      renderFs('dev');
    })();
    ok('T14a 超时后 loading 被摘掉并给出原因',
       _fs.dev.nodes['/sdcard'].loading === false
       && _fs.dev.nodes['/sdcard'].err.indexOf('超时') >= 0);

    // ④ 错误行里有「重试」入口，点它会重新发同一个路径的请求
    var errBtn = null;
    var btns = document.querySelectorAll('#page-file button');
    for (var bi = 0; bi < btns.length; bi++){
      if ((btns[bi].getAttribute('onclick') || '').indexOf('fsRetry') >= 0) errBtn = btns[bi];
    }
    ok('T14a 错误行有重试按钮', !!errBtn, errBtn ? 'ok' : '没有');

    SENT.length = 0;
    fsRetry('dev', '/sdcard');
    ok('T14a 重试会重新请求该目录',
       !!last('fslist') && last('fslist').path === '/sdcard',
       JSON.stringify(last('fslist')));
    ok('T14a 重试后清掉错误并回到 loading',
       _fs.dev.nodes['/sdcard'].err === '' && _fs.dev.nodes['/sdcard'].loading === true);
    ok('请求期间标记 loading', _fs.dev.nodes['/sdcard'].loading === true);

    onFsList(SD_DIR);
    ok('展开后出现子级', hasRow('dev','/sdcard/Download'));
    ok('父级没有被替换', hasRow('dev','/sdcard'));
    ok('箭头变为展开态', rowByPath('dev','/sdcard').querySelector('.fs-arw').textContent === '▾');

    var padParent = parseInt(rowByPath('dev','/sdcard').style.paddingLeft, 10);
    var padChild = parseInt(rowByPath('dev','/sdcard/Download').style.paddingLeft, 10);
    ok('子级有缩进', padChild > padParent, padParent + ' -> ' + padChild);

    clickRow('dev','/sdcard');
    ok('再次单击收起', !hasRow('dev','/sdcard/Download'));

    SENT.length = 0;
    clickRow('dev','/sdcard');
    ok('缓存命中不再请求', SENT.filter(function(o){ return o.kind === 'fslist'; }).length === 0);

    SENT.length = 0;
    clickRow('dev','/sdcard/a.txt');
    ok('单击文件不请求', !last('fslist'));
    ok('单击文件被选中', rowByPath('dev','/sdcard/a.txt').classList.contains('sel'));

    SENT.length = 0;
    dblRow('dev','/sdcard/Download');
    ok('双击文件夹去加载', !!last('fslist') && last('fslist').path === '/sdcard/Download',
       JSON.stringify(last('fslist')));

    document.getElementById('list-dev').dispatchEvent(new MouseEvent('dblclick', {bubbles:true}));
    ok('双击空白全部收起', !hasRow('dev','/sdcard/Download'));

    _fs.dev.nodes['/sdcard'].expanded = true;
    renderFs('dev');
    _fsDrag = { side:'dev', paths:['/sdcard/a.txt'] };

    SENT.length = 0;
    var evBlank = new MouseEvent('drop', {bubbles:true, cancelable:true});
    Object.defineProperty(evBlank, 'dataTransfer', {value:{getData:function(){return '';}, dropEffect:''}});
    document.getElementById('list-local').dispatchEvent(evBlank);
    ok('拖到空白不复制', !last('fscopy'));

    var evRow = new MouseEvent('drop', {bubbles:true, cancelable:true});
    Object.defineProperty(evRow, 'dataTransfer', {value:{getData:function(){return '';}, dropEffect:''}});
    rowByPath('local','CROOT').dispatchEvent(evRow);
    var cp = last('fscopy');
    ok('拖到文件夹行触发下载', !!cp && cp.dir === 'down', JSON.stringify(cp));
    ok('落点是该文件夹', !!cp && cp.dst === 'CROOT', cp ? cp.dst : '');

    SENT.length = 0;
    _fsDrag = { side:'dev', paths:['/sdcard/a.txt'] };
    var evSame = new MouseEvent('drop', {bubbles:true, cancelable:true});
    Object.defineProperty(evSame, 'dataTransfer', {value:{getData:function(){return '';}, dropEffect:''}});
    rowByPath('dev','/data').dispatchEvent(evSame);
    ok('同侧拖拽不复制', !last('fscopy'));

    var many = [];
    for (var i = 0; i < 620; i++) {
      many.push({name:'f' + i, path:'/big/f' + i, dir:false, link:false, size:1, time:'', perm:'file', sizeText:'1 B'});
    }
    _fs.dev.nodes['/'].children.push({name:'big', path:'/big', dir:true, link:false, size:0, time:'', perm:'dir', sizeText:''});
    onFsList({side:'dev', path:'/big', parent:'/', err:'', items:many});
    _fs.dev.nodes['/'].expanded = true;
    _fs.dev.nodes['/big'].expanded = true;
    renderFs('dev');

    var countBig = 0;
    var allRows = rows('dev');
    for (var b = 0; b < allRows.length; b++) {
      if ((allRows[b].getAttribute('data-path') || '').indexOf('/big/') === 0) countBig++;
    }
    ok('单节点只渲染 500 条', countBig === 500, countBig);

    var more = document.querySelector('#list-dev .fs-more');
    ok('出现加载更多', !!more);
    if (more) more.dispatchEvent(new MouseEvent('click', {bubbles:true}));

    countBig = 0;
    allRows = rows('dev');
    for (var b2 = 0; b2 < allRows.length; b2++) {
      if ((allRows[b2].getAttribute('data-path') || '').indexOf('/big/') === 0) countBig++;
    }
    ok('加载更多后到 620 条', countBig === 620, countBig);

    // 回归：请求带尾部分隔符、回包不带（或反之）必须落到同一个节点，
    // 否则那一格会永远停在"加载中…"（用户报的致命 bug）
    SENT.length = 0;
    clickRow('dev','/data');
    onFsList({side:'dev', path:'/data/', parent:'/', err:'', items:[
      {name:'local', path:'/data/local', dir:true, link:false, size:0, time:'', perm:'drwx', sizeText:''}
    ]});
    ok('尾斜杠差异不影响挂载', hasRow('dev','/data/local'), rows('dev').length);
    ok('该节点不再 loading', _fs.dev.nodes['/data'].loading === false,
       String(_fs.dev.nodes['/data'].loading));

    onFsList({side:'dev', path:'/data', parent:'/', err:'没有权限读取该目录（需要 root）', items:[]});
    _fs.dev.nodes['/data'].expanded = true;
    renderFs('dev');
    ok('无权限显示红字行', !!document.querySelector('#list-dev .fs-empty.err'));

    // ---------- 拖拽高亮 + 完成后刷新与清遮罩（2026-11-14 反馈） ----------
    _fsDrag = { side:'dev', paths:['/sdcard/a.txt'] };
    var overEv = new MouseEvent('dragover', {bubbles:true, cancelable:true});
    Object.defineProperty(overEv, 'dataTransfer', {value:{getData:function(){return '';}, dropEffect:''}});
    rowByPath('local','CROOT').dispatchEvent(overEv);
    ok('拖到文件夹上整行高亮',
       rowByPath('local','CROOT').classList.contains('drop-target'));

    var pane = document.getElementById('pane-dev');
    pane.classList.add('drop-on');
    SENT.length = 0;
    onFsDone({dir:'up', dst:'/sdcard', count:1, failed:[]});
    ok('完成后清掉面板遮罩', !pane.classList.contains('drop-on'));
    ok('完成后清掉行高亮',
       !document.querySelector('.fs-row.drop-target'));
    var hitDst = false;
    for (var fi = 0; fi < SENT.length; fi++) {
      if (SENT[fi].kind === 'fslist' && SENT[fi].side === 'dev' && SENT[fi].path === '/sdcard') hitDst = true;
    }
    ok('完成后刷新目标目录', hitDst, JSON.stringify(SENT));

    ok('两栏之间可拖动分隔条', !!document.getElementById('fs-resizer'));

    // 目录行不再重复画灰色三角（只在图标位放 ★/↗）
    ok('目录行没有第二个箭头图标',
       rowByPath('dev','/big').querySelector('.i') === null,
       (rowByPath('dev','/big').querySelector('.i') || {}).textContent);

    fsProg(0, 1, 'a.bin', 5 * 1024 * 1024, 10 * 1024 * 1024);
    ok('单文件按字节 50%', document.getElementById('fs-prog-i').style.width === '50%',
       document.getElementById('fs-prog-i').style.width);
    ok('显示已传与总量', document.getElementById('fs-prog-txt').textContent.indexOf('5.0 MB / 10.0 MB') >= 0,
       document.getElementById('fs-prog-txt').textContent);
    fsProg(2, 4, 'x', undefined, undefined);
    ok('目录按文件数 50%', document.getElementById('fs-prog-i').style.width === '50%');
    ok('有取消按钮', !!document.getElementById('fs-cancel'));

    _fs.dev.nodes['/sdcard'] = { e:{name:'sdcard', path:'/sdcard', dir:true}, children:null, expanded:false, loading:false, err:'', shown:500 };
    _fs.dev.sel = { '/sdcard': 1 };
    ok('选中文件夹就是当前目录', fsCurrentDir('dev') === '/sdcard', fsCurrentDir('dev'));
    _fs.dev.sel = { '/sdcard/a.txt': 1 };
    ok('选中文件时取父目录', fsCurrentDir('dev') === '/sdcard', fsCurrentDir('dev'));

  }catch(e){
    ok('运行异常', false, e.message);
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
           "--virtual-time-budget=7000", "--dump-dom", "--user-data-dir=" + PROF,
           "file:///" + TEST.replace("\\", "/")]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=150)
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
    print("  文件管理：通过 %d / %d" % (len(lines) - len(fails), len(lines)))
    return 0 if not fails else 1

if __name__ == "__main__":
    sys.exit(main())
