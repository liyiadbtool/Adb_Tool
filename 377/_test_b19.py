"""第 19 批回归测试（2026-11-22）。

覆盖：
  A1 6 个默认屏全部显示（扫描只补分辨率）
  A2 未检测到的屏按钮不置灰
  A3 整行可点即投屏（无 [投][录] 双按钮）
  A4 无刷新按钮
  A5 无「取消全部投屏」
  A6 无仪表「录 60s」
  B1 页切换只淡入（无位移）+ diag 改 Grid
  B2 剩余CPU/内存/top5 在「资源占用」卡（不在本机/车机卡）
  B3 采样 3 秒
  B4 未检测显示 --
  C1 初始只有「+ 添加分组」
  C2 分组容器式
  C3 条目行 名称/链接/打开/复制/删除
  C4 旧数据迁移

运行：python 377/_test_b19.py
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
  pre.id = 'B19_RESULT';
  pre.textContent = JSON.stringify(R);
  document.body.appendChild(pre);
}

var sent = [];
window.chrome = window.chrome || {};
window.chrome.webview = { postMessage: function(o){ if(o && o.kind) sent.push(o); } };
window.confirm = function(){ return true; };
window.prompt = function(){ return '监控'; };

setTimeout(function(){
  try { runAll(); } catch(err){ ok('探针异常', false, String(err)); finish(); }
}, 1800);

function runAll(){
  var cssAll = document.querySelector('style').textContent;
  // 剥掉注释再断言：注释里常引用历史值（比如"原来用的是 width:calc(50% - 6px)"），
  // 不剥会把解释文字误判成实际声明。
  var css = cssAll.replace(/\/\*[\s\S]*?\*\//g, '');
  var scriptTxt = '';
  var ss = document.querySelectorAll('script');
  for (var s3 = 0; s3 < ss.length; s3++) scriptTxt += ss[s3].textContent;

  /* ============ A1 6 个默认屏全部显示 ============ */
  var castIdx = -1;
  for (var ci = 0; ci < quickGroups.length; ci++)
    if (quickGroups[ci].name === 'Scrcpy投屏') castIdx = ci;
  _castDispLoaded = true;   // 避免自动扫屏打乱
  switchTab('quick');
  _quickIdx = castIdx; _quickFilter = ''; renderQuickItems();

  var rows = document.querySelectorAll('#cast-grid .crow');
  ok('★ 默认 6 个屏全部显示', rows.length === 6, rows.length);

  // 模拟：只扫到 display 0（emulator 的情况）
  castOnDisplays({kind:'displays', ok:true, list:[{id:0,w:1600,h:900}]});
  var rows2 = document.querySelectorAll('#cast-grid .crow');
  ok('★ 扫到 1 块屏后仍显示 6 行（不覆盖）', rows2.length === 6, rows2.length);

  var r0 = document.querySelector('#cast-grid .crow[data-cast="0"] .crow-sub');
  ok('display 0 补上真实分辨率', r0 && r0.textContent.indexOf('1600×900') >= 0,
     r0 ? r0.textContent : 'null');

  var r4 = document.querySelector('#cast-grid .crow[data-cast="4"] .crow-sub');
  ok('display 4 标「未检测到」', r4 && r4.textContent.indexOf('未检测到') >= 0,
     r4 ? r4.textContent : 'null');

  /* A2 未检测到不置灰 */
  var b4 = document.querySelector('#cast-grid .crow[data-cast="4"]');
  ok('★ 未检测到的按钮不置灰', b4 && b4.disabled === false, b4 ? b4.disabled : 'null');

  /* A1 计划外屏追加 */
  castOnDisplays({kind:'displays', ok:true, list:[{id:0,w:1600,h:900},{id:7,w:1920,h:720}]});
  var extra = document.querySelectorAll('#cast-grid .crow--extra');
  ok('★ 计划外屏（display 7）自动追加', extra.length === 1, extra.length);

  /* A3 整行可点，无 [投][录] 双按钮 */
  ok('★ 无 [投][录] 小按钮', document.querySelectorAll('#cast-grid .cmini').length === 0);
  ok('★ 整行是 button 且 onclick 投屏',
     document.querySelector('#cast-grid .crow').tagName === 'BUTTON'
     && /castGo/.test(document.querySelector('#cast-grid .crow').getAttribute('onclick') || ''));
  // 第 20 批：行结构改成"图标 + 文本块"，选择器从 .crow b 变成 .crow-txt b
  ok('★ 名称不被压成竖排（white-space:nowrap）',
     /\.crow-txt b\{[^}]*white-space:nowrap/.test(css));

  /* A4/A5/A6 已删的入口 */
  ok('★ 无刷新按钮', !document.getElementById('cast-refresh'));
  ok('★ 无「取消全部投屏」', typeof castStopAll === 'undefined');
  ok('★ 无仪表「录 60s」', !document.getElementById('clu-rec-btn'));
  ok('★ 无 castRec（录屏 UI 入口已移除）', typeof castRec === 'undefined');

  /* ============ B1 缩放 ============ */
  ok('★ 页动画改为淡入（pageFade 存在）', /@keyframes pageFade/.test(css));
  ok('★ pageIn 的位移已删除', !/@keyframes pageIn/.test(css));
  ok('★ 无 translateY(4px) 的页面动画',
     !/\.page\{[^}]*translateY/.test(css));
  // 第 20 批：auto-fit 会因 15px 滚动条在阈值处跳列，改成**固定两列**
  ok('★ diag-scroll 用固定两列 Grid',
     /\.diag-scroll\{[^}]*grid-template-columns:repeat\(2,/.test(css),
     'grid repeat(2)');
  // 只查**属性声明**，注释里提到这个词不算（注释是在解释历史）
  ok('★ diag-card 不再用 calc(50% - 6px)',
     !/width\s*:\s*calc\(50% ?- ?6px\)/.test(css));

  /* ============ B2 资源占用卡 ============ */
  ok('★ 资源占用卡存在', !!document.getElementById('diag-card-res'));
  ok('资源占用卡整行宽',
     document.getElementById('diag-card-res').classList.contains('diag-card--wide'));

  // 本机/车机信息卡里不应再有 top5
  switchTab('diag');
  var fakeCar = {online:true, got:true, root:true, rootprobed:true, serial:'S1',
                 rows:[{k:'车型',v:'GAC'}], res:'1920x720'};
  diagOnCar(fakeCar);
  var carTxt = document.getElementById('diag-rows-car').textContent;
  ok('★ 车机信息卡里没有「剩余 CPU」', carTxt.indexOf('剩余 CPU') < 0, carTxt.slice(0,80));

  /* ============ B3/B4 采样渲染 ============ */
  top5OnData({
    host:{ok:true, cores:8, freeCpu:64.8, freeMem:5.2,
          cpu:[{n:'chrome', v:12.5}], mem:[{n:'chrome', v:1024.0}]},
    car:{ok:false, err:'没有连接设备'}
  });
  var resTxt = document.getElementById('diag-rows-res').textContent;
  ok('★ 资源占用里有本机剩余 CPU', resTxt.indexOf('剩余 CPU') >= 0, resTxt.slice(0,120));
  ok('★ 本机剩余 CPU 显示 64.8%', resTxt.indexOf('64.8') >= 0);
  ok('★ 本机剩余内存 5.2 GB', resTxt.indexOf('5.2') >= 0);
  ok('★ 车机未检测显示 --', resTxt.indexOf('--') >= 0, resTxt.slice(-160));
  ok('★ 车机失败原因也显示', resTxt.indexOf('没有连接设备') >= 0);

  // 采样间隔 3 秒
  ok('★ 采样间隔常量为 3000', scriptTxt.indexOf('DIAG_SAMPLE_MS = 3000') >= 0);

  /* ============ C1~C4 H5 ============ */
  switchTab('file');
  fileNavSwitch('h5');
  h5EnsureInit();

  ok('★ 初始只有「+ 添加分组」按钮', /h5AddGroup/.test(scriptTxt));
  ok('★ 旧表单已删', !document.getElementById('h5-f-name')
     && !document.getElementById('h5-f-url'));

  // C1 初始无分组
  try { localStorage.removeItem(H5_KEY); } catch(e){}
  _h5.groups = []; _h5.adding = '';
  h5Render();
  var bodyTxt = document.getElementById('h5-body').textContent;
  ok('★ 空状态提示添加分组', bodyTxt.indexOf('添加分组') >= 0, bodyTxt.slice(0,80));
  ok('★ 空状态没有分组块', document.querySelectorAll('.h5-group').length === 0);

  // C2 添加分组
  // 第 20 批：改成自绘弹窗，不再走 prompt 桩
  h5AddGroup();
  document.getElementById('h5g-name').value = '监控';
  h5AddGroupCommit();
  ok('★ 添加分组成功', _h5.groups.length === 1, _h5.groups.length);
  ok('分组名正确', _h5.groups[0].name === '监控', _h5.groups[0].name);
  h5Render();
  ok('★ 渲染出分组头', !!document.querySelector('.h5-ghead'));
  ok('★ 分组头有「+ 添加」',
     document.querySelector('.h5-ghead').textContent.indexOf('添加') >= 0);

  // C3 行内添加条目
  var gid = _h5.groups[0].id;
  h5StartAdd(gid);
  ok('★ 行内输入行出现', !!document.getElementById('h5-new-name')
     && !!document.getElementById('h5-new-url'));
  document.getElementById('h5-new-name').value = '测试看板';
  document.getElementById('h5-new-url').value = 'board.example.com';
  h5CommitAdd(gid);
  ok('★ 条目已加入', _h5.groups[0].items.length === 1, _h5.groups[0].items.length);
  ok('★ URL 自动补 https', _h5.groups[0].items[0].url === 'https://board.example.com',
     _h5.groups[0].items[0].url);

  h5Render();
  var itemEl = document.querySelector('.h5-item');
  ok('★ 条目行有名称', itemEl && itemEl.textContent.indexOf('测试看板') >= 0);
  ok('★ 条目行有链接', itemEl && itemEl.textContent.indexOf('board.example.com') >= 0);
  var acts = itemEl.querySelectorAll('.h5-acts button');
  ok('★ 条目行有 打开/复制/删除 三个按钮', acts.length === 3, acts.length);
  var actTxt = itemEl.querySelector('.h5-acts').textContent;
  ok('含「打开」', actTxt.indexOf('打开') >= 0, actTxt);
  ok('含「复制」', actTxt.indexOf('复制') >= 0);
  ok('含「删除」', actTxt.indexOf('删除') >= 0);

  // 删除条目
  var iid = _h5.groups[0].items[0].id;
  h5DelItem(gid, iid);
  ok('★ 删除条目生效', _h5.groups[0].items.length === 0, _h5.groups[0].items.length);

  // 删除分组
  h5DelGroup(gid);
  ok('★ 删除分组生效', _h5.groups.length === 0, _h5.groups.length);

  /* C4 旧格式迁移 */
  var legacy = [
    {id:'a1', name:'旧1', url:'https://a.com', cat:'监控'},
    {id:'a2', name:'旧2', url:'https://b.com', cat:'监控'},
    {id:'a3', name:'旧3', url:'https://c.com', cat:'文档'}
  ];
  try { localStorage.setItem(H5_KEY, JSON.stringify(legacy)); } catch(e){}
  _h5.groups = [];
  h5Load();
  ok('★ 旧扁平数据迁成 2 个分组', _h5.groups.length === 2, _h5.groups.length);
  ok('★ 同 cat 的条目归到一组', _h5.groups[0].items.length === 2,
     _h5.groups[0].items.length);
  ok('★ 迁移不丢 URL', _h5.groups[0].items[0].url === 'https://a.com',
     _h5.groups[0].items[0].url);

  ok('无运行时错误', window.__E.length === 0, window.__E.join('; '));
  finish();
}
</script>
"""


def main():
    src = open(UI, encoding="utf-8").read()
    tmp = os.path.join(ROOT, "377", "_b19.html")
    open(tmp, "w", encoding="utf-8", newline="").write(src.replace("</body>", PROBE + "</body>"))
    try:
        p = subprocess.run(
            [EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--no-first-run", "--no-default-browser-check",
             "--disable-background-networking", "--disable-sync",
             "--disable-extensions", "--disable-component-update",
             "--user-data-dir=" + os.path.join(tempfile.gettempdir(), "edgeprof_b19"),
             "--window-size=1400,900", "--virtual-time-budget=16000", "--dump-dom",
             "file:///" + tmp.replace("\\", "/")],
            capture_output=True, timeout=200)
        dom = p.stdout.decode("utf-8", "replace")
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass

    m = re.search(r'<pre id="B19_RESULT">(.*?)</pre>', dom, re.S)
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
    print("  第19批：通过 %d / %d" % (len(results) - fail, len(results)))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
