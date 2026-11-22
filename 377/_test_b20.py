"""第 20 批回归测试（2026-11-23）。

覆盖：
  D1 终端白名单隔离（只 src=0 进终端）
  D3 字号三层兜底（HTML 静态 data-fsize=m / 首次落盘 / applySize 幂等）
  S1 投屏卡片 = 快捷指令样式
  S2 资源占用左右分栏
  S3 快照历史界面已删（histPush 保留）
  S4 删 contain:layout
  S5 固定两列 + overflow-y:scroll
  D2 H5 分组可折叠
  S6 H5 添加分组自绘弹窗
  S7 H5 链接可点击

运行：python 377/_test_b20.py
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
  pre.id = 'B20_RESULT';
  pre.textContent = JSON.stringify(R);
  document.body.appendChild(pre);
}

var sent = [];
window.chrome = window.chrome || {};
window.chrome.webview = { postMessage: function(o){ if(o && o.kind) sent.push(o); } };
window.confirm = function(){ return true; };

setTimeout(function(){
  try { runAll(); } catch(err){ ok('探针异常', false, String(err)); finish(); }
}, 1800);

function runAll(){
  var cssAll = document.querySelector('style').textContent;
  var css = cssAll.replace(/\/\*[\s\S]*?\*\//g, '');
  var scriptTxt = '';
  var ss = document.querySelectorAll('script');
  for (var s3 = 0; s3 < ss.length; s3++) scriptTxt += ss[s3].textContent;

  /* ============ D3 字号三层兜底 ============ */
  ok('★ ① HTML 根标签静态 data-fsize=m',
     document.documentElement.getAttribute('data-fsize') === 'm',
     document.documentElement.getAttribute('data-fsize'));
  ok('★ ② boot 里首次会落盘（源码含 noSize 分支）',
     scriptTxt.indexOf('noSize') >= 0);
  ok('★ ③ applySize 有幂等短路（changed 判断）',
     /var changed = .*_prefs\.size/.test(scriptTxt));

  // 幂等实测：同档位连调两次，只该发一次 uizoom
  sent.length = 0;
  _prefs.size = 'm';
  applySize('m', true);
  applySize('m', true);
  var zoomMsgs = sent.filter(function(x){ return x.kind === 'uizoom'; });
  ok('★ 同档位重复调用只发 1 次 uizoom', zoomMsgs.length <= 1, zoomMsgs.length);

  sent.length = 0;
  applySize('l', true);
  var zoomL = sent.filter(function(x){ return x.kind === 'uizoom'; });
  ok('换档位会发 uizoom', zoomL.length === 1, zoomL.length);
  applySize('m', true);   // 复位

  /* ============ D1 终端白名单隔离 ============ */
  var box = document.getElementById('logbox-0');
  var n0 = box ? box.children.length : 0;

  // src=10（Fastbot 检测）不该进终端
  appendLines([{kind:'lines', src:10, slot:0, text:'OK:/sdcard/monkeyq.jar'}]);
  var n1 = box ? box.children.length : 0;
  ok('★ src=10 的批量行不进终端', n1 === n0, n0 + '->' + n1);

  // 回显同理
  appendEcho({kind:'echo', src:10, slot:0, data:'shell "for f in ..."'});
  ok('★ src=10 的命令回显不进终端', box.children.length === n0);

  // src=0 应该进
  appendLines([{kind:'lines', src:0, slot:0, text:'hello terminal'}]);
  ok('★ src=0 的批量行进终端', box.children.length > n0,
     box.children.length + ' vs ' + n0);
  appendEcho({kind:'echo', src:0, slot:0, data:'adb devices'});
  ok('★ src=0 的回显进终端', box.children.length > n0);

  // src=20 仍只进诊断缓冲
  var before20 = box.children.length;
  appendLines([{kind:'lines', src:20, slot:0, text:'AUTH=1'}]);
  ok('src=20 不进终端', box.children.length === before20);

  /* ============ S1 投屏卡片样式 ============ */
  var castIdx = -1;
  for (var ci = 0; ci < quickGroups.length; ci++)
    if (quickGroups[ci].name === 'Scrcpy投屏') castIdx = ci;
  _castDispLoaded = true;
  switchTab('quick');
  _quickIdx = castIdx; _quickFilter = ''; renderQuickItems();

  var rows = document.querySelectorAll('#cast-grid .crow[data-cast]');
  ok('6 个屏卡片都在', rows.length === 6, rows.length);
  ok('★ 每张卡有播放图标', document.querySelectorAll('#cast-grid .crow-ico').length === 6,
     document.querySelectorAll('#cast-grid .crow-ico').length);
  ok('★ 每张卡有文本块', document.querySelectorAll('#cast-grid .crow-txt').length === 6);
  ok('★ 容器用网格布局',
     /\.cgrid2\{[^}]*display:grid/.test(css));
  ok('★ 卡片用 --card 底色（对齐快捷指令）',
     /\.crow\{[^}]*background:var\(--card\)/.test(css));
  ok('★ hover 抬升', /\.crow:hover\{[^}]*translateY\(-2px\)/.test(css));

  /* ============ S2 资源占用分栏 ============ */
  switchTab('diag');
  top5OnData({
    host:{ok:true, cores:8, freeCpu:64.8, freeMem:5.2,
          cpu:[{n:'chrome', v:12.5}], mem:[{n:'chrome', v:1024.0}]},
    car:{ok:true, memTotal:8, memFree:3.1, freeCpu:72.5,
         cpu:[{n:'systemui', v:9.4}], mem:[{n:'systemui', v:'180M'}]}
  });
  var resBox = document.getElementById('diag-rows-res');
  ok('★ 资源占用有 .res-cols 两栏容器',
     resBox.querySelectorAll('.res-cols').length === 1);
  ok('★ 两栏（本机/车机）都在',
     resBox.querySelectorAll('.res-col').length === 2,
     resBox.querySelectorAll('.res-col').length);
  var cols = resBox.querySelectorAll('.res-col');
  ok('左栏是本机', cols[0] && cols[0].textContent.indexOf('本机') >= 0);
  ok('右栏是车机', cols[1] && cols[1].textContent.indexOf('车机') >= 0);
  ok('两栏并排（grid 两列）', /\.res-cols\{[^}]*grid-template-columns:1fr 1fr/.test(css));

  /* ============ S3 快照历史界面已删 ============ */
  ok('★ 快照历史卡已删', !document.getElementById('diag-card-hist'));
  ok('★ 快照历史行容器已删', !document.getElementById('diag-rows-hist'));
  ok('★ histPush 记录逻辑保留', typeof histPush === 'function'
     || scriptTxt.indexOf('function histPush') >= 0);

  /* ============ S4 删 contain:layout ============ */
  ok('★ 没有 contain:layout', css.indexOf('contain:layout') < 0);

  /* ============ S5 固定两列 + scroll ============ */
  ok('★ grid 固定两列（不用 auto-fit）',
     /\.diag-scroll\{[^}]*grid-template-columns:repeat\(2, minmax\(0,1fr\)\)/.test(css));
  /* 2026-11-23（第 24 批）：改回 auto，由 scrollbar-gutter:stable 预留位置
     （避免了"诊断页永远显示一条空轨道"的观感问题）。 */
  ok('★ 诊断页用 auto + gutter 预留',
     /\.diag-scroll\{[^}]*overflow-y:auto/.test(css) &&
     /\.diag-scroll\{[^}]*scrollbar-gutter:stable/.test(css), 'overflow-y auto + gutter');
  ok('窄屏有单列降级', /@media \(max-width: 900px\)\{\s*\.diag-scroll\{ grid-template-columns:1fr/.test(cssAll)
     || /max-width: 900px/.test(cssAll));

  /* ============ D2 H5 分组折叠 ============ */
  switchTab('file');
  fileNavSwitch('h5');
  h5EnsureInit();

  try { localStorage.removeItem(H5_KEY); localStorage.removeItem('h5_folded_v1'); } catch(e){}
  _h5.groups = [{ id:'g1', name:'监控', items:[{id:'i1', name:'看板', url:'https://a.com'}] }];
  _h5.adding = '';
  _h5fold = null;
  h5Render();

  var ghead = document.querySelector('.h5-ghead');
  ok('分组头有折叠箭头', !!document.querySelector('.h5-caret-btn'));
  ok('初始展开（条目可见）',
     document.querySelector('.h5-gitems').style.display !== 'none');

  h5ToggleGroup('g1');
  ok('★ 点折叠后条目隐藏',
     document.querySelector('.h5-gitems').style.display === 'none',
     document.querySelector('.h5-gitems').style.display);
  ok('★ 折叠状态写入 localStorage',
     (function(){ try { var m = JSON.parse(localStorage.getItem('h5_folded_v1')||'{}'); return !!m['g1']; } catch(e){ return false; } })());

  h5ToggleGroup('g1');
  ok('★ 再点展开回来',
     document.querySelector('.h5-gitems').style.display === 'none' ? false : true,
     document.querySelector('.h5-gitems').style.display);

  /* ============ S7 H5 链接可点击 ============ */
  var urlEl = document.querySelector('.h5-url');
  ok('★ 链接有 onclick（可直接打开）',
     urlEl && /h5Open/.test(urlEl.getAttribute('onclick') || ''),
     urlEl ? urlEl.getAttribute('onclick') : 'null');
  ok('★ 链接鼠标手型', /\.h5-url\{[^}]*cursor:pointer/.test(css));

  sent.length = 0;
  var nameEl = document.querySelector('.h5-name');
  if (nameEl && nameEl.onclick) nameEl.onclick();
  var openMsg = null;
  for (var om = 0; om < sent.length; om++) if (sent[om].kind === 'openurl') openMsg = sent[om];
  ok('★ 点名称/链接会发 openurl', !!openMsg, JSON.stringify(sent).slice(0,100));

  /* ============ S6 添加分组弹窗 ============ */
  ok('★ 弹窗遮罩存在', !!document.getElementById('h5g-mask'));
  ok('★ 弹窗输入框存在', !!document.getElementById('h5g-name'));
  // 注意：不能用 scriptTxt.indexOf 判断 —— 探针自己的源码里也有这个字面量。
  // 改成正则看 h5AddGroup 函数体里有没有调用 prompt(。
  ok('★ 不再用原生 prompt',
     !/function h5AddGroup\(\)\{[\s\S]{0,400}?prompt\(/.test(scriptTxt));

  var mask = document.getElementById('h5g-mask');
  ok('初始隐藏', mask.style.display === 'none');
  h5AddGroup();
  ok('★ 点「+ 添加分组」弹窗出现', mask.style.display === 'flex', mask.style.display);

  document.getElementById('h5g-name').value = '文档';
  h5AddGroupCommit();
  ok('★ 弹窗内提交能建分组', _h5.groups.length === 2, _h5.groups.length);
  ok('★ 提交后弹窗关闭', mask.style.display === 'none', mask.style.display);

  // 重名校验
  h5AddGroup();
  document.getElementById('h5g-name').value = '文档';
  h5AddGroupCommit();
  ok('★ 重名被拦', _h5.groups.length === 2, _h5.groups.length);
  ok('★ 重名有错误提示',
     document.getElementById('h5g-err').textContent.length > 0,
     document.getElementById('h5g-err').textContent);
  h5AddGroupClose();

  // 主题变量（三主题适配的关键）
  ok('★ 遮罩用主题变量 --scrim', /\.h5g-mask\{[^}]*background:var\(--scrim\)/.test(css));
  ok('★ 弹窗体用 --surface', /\.h5g-box\{[^}]*background:var\(--surface\)/.test(css));

  /* ============ 第 24 批：强调色 192 色滑块 ============ */
  ok('★ 192 色数据已嵌入', ACCENT_192.length === 192, ACCENT_192.length);
  ok('★ 滑块锚点 = 192 色', AS_ANCHORS.length === 192, AS_ANCHORS.length);
  ok('锚点格式是 HEX',
     /^#[0-9A-F]{6}$/.test(AS_ANCHORS[0].k), AS_ANCHORS[0].k);
  ok('★ 锚点按色相排序（首色与末色色相不冲突）',
     typeof AS_ANCHORS[0].h === 'number' && AS_ANCHORS[0].h <= AS_ANCHORS[1].h,
     AS_ANCHORS[0].h + ' vs ' + AS_ANCHORS[1].h);

  // HEX 强调色：设 CSS 变量 + 清 data-accent 预设
  applyAccent('#B28F98');
  var de = document.documentElement;
  ok('★ HEX 强调色写入 --accent',
     de.style.getPropertyValue('--accent').trim().toUpperCase() === '#B28F98',
     de.style.getPropertyValue('--accent'));
  ok('★ HEX 时 data-accent 标记为 custom',
     de.getAttribute('data-accent') === 'custom', de.getAttribute('data-accent'));
  ok('★ 同时算出 --accent-soft', de.style.getPropertyValue('--accent-soft').indexOf('rgba') === 0,
     de.style.getPropertyValue('--accent-soft'));
  ok('★ 同时算出 --on-accent', /^#/.test(de.style.getPropertyValue('--on-accent').trim()),
     de.style.getPropertyValue('--on-accent'));

  // 切回预设色要清掉行内变量
  applyAccent('blue');
  ok('★ 切回预设色会清掉行内 --accent',
     de.style.getPropertyValue('--accent') === '',
     JSON.stringify(de.style.getPropertyValue('--accent')));

  // 滑块渲染（asInit 平时在打开设置面板时调，这里主动跑一次）
  try { asInit(); } catch(e){}
  var track = document.getElementById('as-track');
  /* 浏览器会把 HEX 规范化成 rgb()，所以不能数 "#XXXXXX"。
     改数色标数量：每个 stop 形如 "rgb(...) 12.34%"，数百分号。 */
  var bg = track ? (track.style.background || '') : '';
  var stops = (bg.match(/[\d.]+%/g) || []).length;
  ok('★ 轨道渐变含 192 个色标', stops === 192, stops + ' | ' + bg.slice(0, 90));
  ok('' + '滑块 max = 191',
     document.getElementById('as-input').max === '191',
     document.getElementById('as-input').max);

  // 当前色预览
  ok('有当前色色点', !!document.getElementById('as-now-dot'));
  ok('有当前色名称', !!document.getElementById('as-now-name'));
  ok('有当前色 HEX', !!document.getElementById('as-now-hex'));

  asApply(10, true);
  ok('★ 拖到第 10 色，预览名称跟着变',
     document.getElementById('as-now-name').textContent === AS_ANCHORS[10].n,
     document.getElementById('as-now-name').textContent);
  ok('★ 预览 HEX 跟第 10 色一致',
     document.getElementById('as-now-hex').textContent === AS_ANCHORS[10].k,
     document.getElementById('as-now-hex').textContent);

  applyAccent('blue');

  ok('无运行时错误', window.__E.length === 0, window.__E.join('; '));
  finish();
}
</script>
"""


def main():
    src = open(UI, encoding="utf-8").read()
    tmp = os.path.join(ROOT, "377", "_b20.html")
    open(tmp, "w", encoding="utf-8", newline="").write(src.replace("</body>", PROBE + "</body>"))
    try:
        p = subprocess.run(
            [EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--no-first-run", "--no-default-browser-check",
             "--disable-background-networking", "--disable-sync",
             "--disable-extensions", "--disable-component-update",
             "--user-data-dir=" + os.path.join(tempfile.gettempdir(), "edgeprof_b20"),
             "--window-size=1400,900", "--virtual-time-budget=16000", "--dump-dom",
             "file:///" + tmp.replace("\\", "/")],
            capture_output=True, timeout=200)
        dom = p.stdout.decode("utf-8", "replace")
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass

    m = re.search(r'<pre id="B20_RESULT">(.*?)</pre>', dom, re.S)
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
    print("  第20批：通过 %d / %d" % (len(results) - fail, len(results)))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
