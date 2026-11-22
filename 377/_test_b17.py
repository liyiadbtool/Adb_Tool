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
  var btns = grid.querySelectorAll('.crow');   // 第 18 批 B2：改成行式（含投/录两个按钮）
  ok('按真实列表重建了行', btns.length === 2, btns.length);
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
  /* 2026-11-22（第 18 批 C1~C6）：H5 已按截图大幅简化
     （删搜索/预设/导入导出/分类侧栏/卡片网格），
     详细的增删改查/持久化断言见 _test_b18.py，这里只验证结构在位。 */
  switchTab('file');
  fileNavSwitch('h5');
  ok('H5 视图已激活',
     document.getElementById('fileview-h5').classList.contains('active'));
  ok('有 H5 二级导航',
     !!document.querySelector('.filenav-item[data-fn="h5"]'));

  h5EnsureInit();
  ok('H5 表单在（分组/名称/链接）',
     !!document.getElementById('h5-f-cat')
     && !!document.getElementById('h5-f-name')
     && !!document.getElementById('h5-f-url'));
  ok('有添加按钮', typeof h5Add === 'function');
  ok('列表容器在', !!document.getElementById('h5-list'));

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
