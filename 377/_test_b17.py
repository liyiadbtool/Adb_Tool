"""第 17 批回归测试（2026-11-22）。

八项需求：
  1 芯片名去掉 T75/AHT
  2 投屏流程补缺口（动态列屏）—— C# 侧，本文件只验 UI
  3 仪表并入「指令 → Scrcpy投屏」，原 tab 删除
  4 终端不再被诊断页回显刷屏
  5 字体只列已安装
  6 UI 细节（字号无半像素 / 行高归并 / 对比度）
  7 首次字号=中
  8 H5 管理页（增删改查/分类/打开/复制/导入导出/预设）

运行：python 377/_test_b17.py
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
window.__E = [];
window.addEventListener('error', function(e){ window.__E.push(String(e.message)); });

var R = [];
function ok(n, c, e){ R.push((c?'PASS':'FAIL') + ' | ' + n + (c?'':' -> ' + (e===undefined?'':e))); }
function finish(){
  var pre = document.createElement('pre');
  pre.id = 'B17_RESULT';
  pre.textContent = JSON.stringify(R);
  document.body.appendChild(pre);
}

var sent = [];
window.chrome = window.chrome || {};
window.chrome.webview = { postMessage: function(o){ if(o && o.kind) sent.push(o); } };

/* 模拟 clipboard */
var copied = null;
try{
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText: function(t){ copied = t; return Promise.resolve(); } },
    configurable: true
  });
}catch(e){}
window.confirm = function(){ return true; };
window.prompt = function(){ return null; };

setTimeout(function(){
  try { runAll(); } catch(err){ ok('探针异常', false, String(err)); finish(); }
}, 1800);

function runAll(){

  /* ============ 1. 芯片名无 T75/AHT ============ */
  var chipSel = document.getElementById('clu-chip');
  ok('芯片下拉存在', !!chipSel);
  if (chipSel){
    var txt = chipSel.textContent;
    ok('★ 芯片名不含 T75', txt.indexOf('T75') < 0, txt);
    ok('★ 芯片名不含 AHT', txt.indexOf('AHT') < 0, txt);
    ok('有 8838 选项', txt.indexOf('8838') >= 0, txt);
    ok('有 8295 选项', txt.indexOf('8295') >= 0, txt);
  }

  /* ============ 3. 仪表并入投屏面板 ============ */
  ok('★ 原仪表页签已删除', !document.querySelector('[data-tab="cluster"]'));
  ok('★ 原仪表页容器已删除', !document.getElementById('page-cluster'));
  ok('投屏面板存在', !!document.getElementById('cast-panel'));

  // 找到「Scrcpy投屏」分组
  var castIdx = -1;
  for (var i = 0; i < quickGroups.length; i++)
    if (quickGroups[i].name === 'Scrcpy投屏') castIdx = i;
  ok('存在 Scrcpy投屏 分组', castIdx >= 0);
  ok('★ 该分组已是面板型', quickGroups[castIdx].panel === 'cast',
     quickGroups[castIdx].panel);

  switchTab('quick');
  _quickIdx = castIdx; _quickFilter = ''; renderQuickItems();
  ok('面板已显示', document.getElementById('cast-panel').style.display !== 'none',
     document.getElementById('cast-panel').style.display);
  ok('卡片网格已让位（不再同时显示）',
     document.getElementById('quick-grid').style.display === 'none');

  // 面板内三块分区
  var secs = document.querySelectorAll('#cast-panel .csec-t');
  var secTxt = '';
  for (var s2 = 0; s2 < secs.length; s2++) secTxt += secs[s2].textContent + '|';
  ok('有「屏幕投屏」分区', secTxt.indexOf('屏幕投屏') >= 0, secTxt);
  ok('有「仪表投屏」分区', secTxt.indexOf('仪表投屏') >= 0, secTxt);
  ok('有「其它」分区', secTxt.indexOf('其它') >= 0, secTxt);

  // 仪表控件在面板里（不是独立页）
  ok('芯片下拉在面板内',
     !!document.querySelector('#cast-panel #clu-chip'));
  ok('登录按钮在面板内',
     !!document.querySelector('#cast-panel #clu-login'));
  ok('投屏按钮在面板内',
     !!document.querySelector('#cast-panel #clu-cast-btn'));

  /* 门禁仍然生效 */
  ok('未登录时仪表投屏按钮禁用',
     document.getElementById('clu-cast-btn').disabled === true);

  /* ============ 2. 动态列屏（UI 侧） ============ */
  sent.length = 0;
  castLoadDisplays();
  var dispMsg = null;
  for (var d = 0; d < sent.length; d++) if (sent[d].kind === 'displays') dispMsg = sent[d];
  ok('★ 发出了列屏请求', !!dispMsg, JSON.stringify(sent).slice(0, 100));

  // 模拟 C# 回包
  castOnDisplays({kind:'displays', ok:true, list:[
    {id:0, w:1600, h:900}, {id:4, w:1920, h:720}
  ]});
  var grid = document.getElementById('cast-grid');
  var btns = grid.querySelectorAll('.cbtn');
  ok('按真实列表重建了按钮', btns.length === 2, btns.length);
  ok('按钮显示分辨率', grid.textContent.indexOf('1600×900') >= 0, grid.textContent.slice(0,80));

  // 拉不到时给提示，不崩
  castOnDisplays({kind:'displays', ok:false, err:'找不到 scrcpy'});
  ok('列屏失败时给提示', grid.textContent.indexOf('没扫到屏幕') >= 0,
     grid.textContent.slice(0,80));

  /* ============ 4. 终端回显不泄漏 ============ */
  // appendEcho 对 src=20 应直接 return（不往终端写）
  var logbox = document.getElementById('logbox-0');
  var before = logbox ? logbox.children.length : 0;
  if (typeof appendEcho === 'function'){
    appendEcho({kind:'echo', src:20, slot:0, data:'shell "echo AUTH=..."'});
  }
  var after = logbox ? logbox.children.length : 0;
  ok('★ src=20 的命令回显不进终端', after === before, before + ' -> ' + after);

  // 对照：src=0（终端自己敲的）应该进
  if (typeof appendEcho === 'function'){
    appendEcho({kind:'echo', src:0, slot:0, data:'adb devices'});
  }
  ok('src=0 的回显仍进终端', logbox.children.length > after,
     logbox.children.length + ' vs ' + after);

  /* 诊断页防重入 */
  var before2 = sent.filter(function(x){ return x.kind === 'run'; }).length;
  diagRefresh();
  diagRefresh();
  diagRefresh();
  var after2 = sent.filter(function(x){ return x.kind === 'run'; }).length;
  ok('★ 诊断页连续调用不重复发命令（防重入）', (after2 - before2) <= 1,
     (after2 - before2) + ' 次');

  /* ============ 5. 字体只列已安装 ============ */
  ok('字体列表已定义', typeof FONT_LIST !== 'undefined' && FONT_LIST.length > 0);

  /* ★ 注意：这个文件的 V14 字体层会在 buildFontSelect 时用 FONTS 表**重填** FONT_LIST，
     所以不能按 "FONT_LIST[0].probe" 断言（那是被覆盖的旧结构）。
     改成验证**行为**：给一个"只装了部分字体"的已安装列表，看下拉里有没有未装项。 */
  onFontList({kind:'fontlist', fonts:['Microsoft YaHei UI', 'SimSun', 'KaiTi', 'Inter']});
  buildFontSelect();
  var fsel = document.getElementById('set-font');
  var opts = [], names = [];
  if (fsel) for (var o = 0; o < fsel.options.length; o++){
    opts.push(fsel.options[o].value);
    names.push(fsel.options[o].textContent);
  }
  var allTxt = names.join('|');
  /* ★ 检测机制说明：V14 字体层用 canvas measureText 测真实系统字体
     （installed()），不吃我们传进来的 onFontList。所以断言只能基于
     "行为"而不是"某个具体字体在不在"：
       · 不能出现「（未安装）」字样（那就是没过滤掉）
       · 自定义入口必须在（always:true）
       · 列表不能为空
     具体哪些系统字体装了因机器而异，不写死。 */
  ok('★ 不再出现「（未安装）」字样', allTxt.indexOf('未安装') < 0, allTxt.slice(0, 120));
  ok('★ 自定义入口始终保留', opts.indexOf('custom') >= 0, opts.join(','));
  ok('字体下拉非空', opts.length > 0, opts.length);
  ok('内置字体在列表里', opts.indexOf('inter') >= 0 || opts.indexOf('mono-all') >= 0,
     opts.join(','));

  /* ============ 7. 首次字号 = 中 ============ */
  var html = document.documentElement;
  ok('★ 默认字号是「中」', html.getAttribute('data-fsize') === 'm',
     html.getAttribute('data-fsize'));

  /* ============ 8. H5 管理 ============ */
  switchTab('file');
  fileNavSwitch('h5');
  ok('H5 视图已激活',
     document.getElementById('fileview-h5').classList.contains('active'));

  // H5 页签按钮
  ok('有 H5 二级导航',
     !!document.querySelector('.filenav-item[data-fn="h5"]'));

  // 初始化
  h5EnsureInit();
  ok('H5 主体已渲染', !!document.getElementById('h5-list'));
  ok('有搜索框', !!document.getElementById('h5-search'));
  ok('有添加按钮入口', typeof h5OpenAdd === 'function');
  ok('有分类区', !!document.getElementById('h5-cats'));

  // 清空后测增删
  _h5.items = []; _h5.cat = ''; h5Save(); h5Render();

  /* 8.1 + 8.3 添加 */
  h5OpenAdd();
  document.getElementById('h5-f-name').value = '测试看板';
  document.getElementById('h5-f-url').value = 'board.example.com';   // 故意不写协议
  document.getElementById('h5-f-cat').value = '监控';
  h5Save();
  ok('★ 添加成功（1 条）', _h5.items.length === 1, _h5.items.length);
  ok('★ URL 自动补 https', _h5.items[0].url === 'https://board.example.com',
     _h5.items[0].url);
  ok('分类已记录', _h5.items[0].cat === '监控', _h5.items[0].cat);

  /* 查重 */
  h5OpenAdd();
  document.getElementById('h5-f-name').value = '重复的';
  document.getElementById('h5-f-url').value = 'https://board.example.com';
  h5Save();
  ok('★ 同一 URL 不重复添加', _h5.items.length === 1, _h5.items.length);

  /* 非法 URL */
  h5OpenAdd();
  document.getElementById('h5-f-name').value = 'x';
  document.getElementById('h5-f-url').value = 'ftp://a.b';
  h5Save();
  ok('非 http/https 被拒', _h5.items.length === 1, _h5.items.length);
  h5CloseForm();

  /* 8.3 分类过滤 */
  h5OpenAdd();
  document.getElementById('h5-f-name').value = '文档站';
  document.getElementById('h5-f-url').value = 'https://docs.example.com';
  document.getElementById('h5-f-cat').value = '文档';
  h5Save();
  ok('现在 2 条', _h5.items.length === 2, _h5.items.length);

  h5Pick('监控');
  var cards1 = document.querySelectorAll('#h5-list .h5-card').length;
  ok('★ 按分类过滤（监控 1 条）', cards1 === 1, cards1);
  h5Pick('');
  ok('切回全部显示 2 条',
     document.querySelectorAll('#h5-list .h5-card').length === 2);

  /* 8 搜索 */
  document.getElementById('h5-search').value = 'docs';
  h5Render();
  ok('搜索过滤生效', document.querySelectorAll('#h5-list .h5-card').length === 1,
     document.querySelectorAll('#h5-list .h5-card').length);
  document.getElementById('h5-search').value = '';
  h5Render();

  /* 8.2 打开（走 C# openurl 而不是 window.open） */
  sent.length = 0;
  var firstId = _h5.items[0].id;
  h5Open(firstId);
  var openMsg = null;
  for (var m = 0; m < sent.length; m++) if (sent[m].kind === 'openurl') openMsg = sent[m];
  ok('★ 打开走系统浏览器（openurl 消息）', !!openMsg, JSON.stringify(sent).slice(0,100));
  if (openMsg) ok('openurl 带正确 URL', openMsg.url.indexOf('http') === 0, openMsg.url);
  ok('打开后记录最近使用时间', !!_h5.items[0].last);

  /* 复制 */
  copied = null;
  h5Copy(firstId);
  ok('复制得到 URL', copied && copied.indexOf('http') === 0, copied);

  /* 8.5 增强：导出 */
  copied = null;
  h5Export();
  var jok = false;
  try { var jo = JSON.parse(copied); jok = jo.items && jo.items.length === 2; } catch(e){}
  ok('★ 导出 JSON 可解析且有 2 条', jok, copied ? copied.slice(0,60) : 'null');

  /* 8.5 增强：导入去重 */
  var beforeImp = _h5.items.length;
  window.prompt = function(){
    return JSON.stringify({ v:1, items: [
      { name:'新站', url:'https://new.example.com', cat:'新' },
      { name:'已有的', url:'https://board.example.com' }
    ]});
  };
  h5Import();
  ok('★ 导入只加新条目（已有的跳过）', _h5.items.length === beforeImp + 1,
     beforeImp + ' -> ' + _h5.items.length);

  /* 8.3 删除 */
  var delId = _h5.items[0].id;
  var cntBefore = _h5.items.length;
  h5Del(delId);
  ok('★ 删除生效', _h5.items.length === cntBefore - 1,
     cntBefore + ' -> ' + _h5.items.length);

  /* 持久化（localStorage） */
  // headless + file:// 下 localStorage 有时被禁用，这里区分"不可用"和"没写进去"
  // 显式再存一次，排除"前面几次操作把数组清空了"的干扰
  h5Persist();
  var raw = null, lsOk = true;
  try {
    localStorage.setItem('__probe__', '1');
    localStorage.removeItem('__probe__');
    raw = localStorage.getItem(H5_KEY);
  } catch(e){ lsOk = false; }
  // 诊断三连：数据在不在内存 / setItem 能不能往返 / 真实 key 有没有写进去
  ok('内存里还有数据', _h5.items.length > 0, _h5.items.length);
  var roundTrip = false;
  if (lsOk){
    try {
      localStorage.setItem('__rt__', 'abc');
      roundTrip = (localStorage.getItem('__rt__') === 'abc');
      localStorage.removeItem('__rt__');
    } catch(e){ roundTrip = false; }
  }
  if (!lsOk || !roundTrip){
    ok('localStorage 在本环境不可用（跳过持久化断言）', true);
  } else {
    ok('★ 数据已写入 localStorage（持久化）', !!raw && raw.length > 10,
       'raw=' + (raw === null ? 'null' : raw.length + '字符')
       + ' items=' + _h5.items.length + ' key=' + H5_KEY
       + ' json=' + JSON.stringify(_h5.items).length);
  }

  /* 8.5 增强：域名首字母 */
  ok('首字母提取正确', h5Initial('https://www.baidu.com/x') === 'B',
     h5Initial('https://www.baidu.com/x'));
  ok('域名提取去掉 www', h5Host('https://www.baidu.com/x') === 'baidu.com',
     h5Host('https://www.baidu.com/x'));

  ok('无运行时错误', window.__E.length === 0, window.__E.join('; '));
  finish();
}
</script>
"""


def main():
    src = open(UI, encoding="utf-8").read()
    tmp = os.path.join(ROOT, "377", "_b17.html")
    open(tmp, "w", encoding="utf-8", newline="").write(src.replace("</body>", PROBE + "</body>"))
    try:
        p = subprocess.run(
            [EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--no-first-run", "--no-default-browser-check",
             "--disable-background-networking", "--disable-sync",
             "--disable-extensions", "--disable-component-update",
             "--user-data-dir=" + os.path.join(tempfile.gettempdir(), "edgeprof_b17"),
             "--window-size=1400,900", "--virtual-time-budget=16000", "--dump-dom",
             "file:///" + tmp.replace("\\", "/")],
            capture_output=True, timeout=200)
        dom = p.stdout.decode("utf-8", "replace")
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass

    m = re.search(r'<pre id="B17_RESULT">(.*?)</pre>', dom, re.S)
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
    print("  第17批：通过 %d / %d" % (len(results) - fail, len(results)))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
