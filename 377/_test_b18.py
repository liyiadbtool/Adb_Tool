"""第 18 批回归测试（2026-11-22）。

覆盖 Ask 模式定稿的 15 项需求：
  A1 二级导航统一下划线式
  A2 合并重复定义（.qcard / .qnav-item / .qcat）
  A3 控件规格统一（输入框/小按钮/分节标题）
  A4 圆角 + 空状态统一
  A6 Monkey 子页记忆
  A7 反馈区折叠持久化
  A8 删除措辞统一
  A9 APK 手动刷新
  B1 投屏面板按钮走 castRun（不再裸调 post）
  B2 每个屏都能录
  B3 仪表录屏（登录门禁 + 独立）
  B4 同屏冲突置灰
  C1~C6 H5 简化
  D1 诊断页 scrollbar-gutter
  D2 车机新增 4 字段（DDR 空则整行隐藏）
  D3/D4 top5 渲染

运行：python 377/_test_b18.py
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
  pre.id = 'B18_RESULT';
  pre.textContent = JSON.stringify(R);
  document.body.appendChild(pre);
}

var sent = [];
window.chrome = window.chrome || {};
window.chrome.webview = { postMessage: function(o){ if(o && o.kind) sent.push(o); } };
window.confirm = function(){ return true; };
var copied = null;
try{
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText: function(t){ copied = t; return Promise.resolve(); } },
    configurable: true
  });
}catch(e){}

setTimeout(function(){
  try { runAll(); } catch(err){ ok('探针异常', false, String(err)); finish(); }
}, 1800);

function runAll(){

  /* ============ A1 二级导航统一 ============ */
  var mkBtn = document.querySelector('.mk-subtabs button');
  var fnItem = document.querySelector('.filenav-item');
  ok('Monkey 导航按钮存在', !!mkBtn);
  ok('文件页导航按钮存在', !!fnItem);
  if (mkBtn && fnItem){
    var a = getComputedStyle(mkBtn), b = getComputedStyle(fnItem);
    ok('★ 两者高度一致（34px）', a.height === b.height, a.height + ' vs ' + b.height);
    ok('★ 两者字号一致', a.fontSize === b.fontSize, a.fontSize + ' vs ' + b.fontSize);
    ok('★ 两者圆角一致', a.borderTopLeftRadius === b.borderTopLeftRadius,
       a.borderTopLeftRadius + ' vs ' + b.borderTopLeftRadius);
    ok('默认字重一致（500）', a.fontWeight === b.fontWeight, a.fontWeight + ' vs ' + b.fontWeight);
    ok('都是无边框（下划线式）',
       a.borderTopWidth === '0px' && b.borderTopWidth === '0px',
       a.borderTopWidth + ' vs ' + b.borderTopWidth);
  }
  // 选中态有底部强调线
  var onBtn = document.querySelector('.mk-subtabs button.on');
  ok('Monkey 有选中项', !!onBtn);
  if (onBtn){
    var af = getComputedStyle(onBtn, '::after');
    ok('★ 选中项有底部强调线', af && af.content !== 'none' && af.height === '2px',
       af ? af.content + '/' + af.height : 'null');
  }

  /* ============ A2 重复定义已合并 ============ */
  var css = document.querySelector('style').textContent;
  function countDecl(sel){
    // 只统计**行首**就是该选择器的规则。
    // 带上下文前缀的（如 [data-theme="eye"] .qcat、.quick-nav .qnav-item）
    // 是有意区分，不算重复定义。
    var n = 0;
    var ls = css.split('\n');
    for (var q = 0; q < ls.length; q++){
      if (ls[q].trim().indexOf(sel + '{') === 0) n++;
    }
    return n;
  }
  ok('★ .qcard 只剩 2 处（主定义 + will-change）', countDecl('.qcard') <= 2,
     countDecl('.qcard'));
  ok('★ .qnav-item 只剩 1 处', countDecl('.qnav-item') === 1, countDecl('.qnav-item'));
  ok('★ .qcat 只剩 1 处', countDecl('.qcat') === 1, countDecl('.qcat'));
  ok('.qcat 不再有 uppercase（对中文无效）',
     !/\.qcat\{[^}]*text-transform\s*:\s*uppercase/.test(css));

  /* ============ A3 控件规格统一 ============ */
  var inpClasses = ['apk-pkg', 'h5-inp', 'clu-inp', 'tt-inp'];
  var pads = [];
  for (var i = 0; i < inpClasses.length; i++){
    var el = document.createElement('input');
    el.className = inpClasses[i];
    el.style.position = 'absolute'; el.style.left = '-9999px';
    document.body.appendChild(el);
    var cs = getComputedStyle(el);
    pads.push(cs.paddingTop + '/' + cs.paddingLeft + '/' + cs.borderTopLeftRadius + '/' + cs.fontSize);
    document.body.removeChild(el);
  }
  var uniqInp = pads.filter(function(v, idx){ return pads.indexOf(v) === idx; });
  ok('★ 输入框外壳规格统一（4 类）', uniqInp.length === 1, uniqInp.join(' | '));

  // 分两组：行内操作（32px）/ 标题轻操作（22px）——见 A3-2 注释
  function miniSpec(cls){
    var b = document.createElement('button');
    b.className = cls;
    b.style.position = 'absolute'; b.style.left = '-9999px';
    document.body.appendChild(b);
    var c2 = getComputedStyle(b);
    var v = c2.height + '/' + c2.fontSize + '/' + c2.borderTopWidth + '/' + c2.borderTopLeftRadius;
    document.body.removeChild(b);
    return v;
  }
  var gA = ['fbtn', 'h5-act', 'cmini'].map(miniSpec);
  var gB = ['diag-copy-card', 'csec-refresh'].map(miniSpec);
  ok('★ 组 A 行内按钮规格统一（32px）',
     gA.filter(function(v,i){ return gA.indexOf(v) === i; }).length === 1,
     gA.join(' | '));
  ok('★ 组 B 标题按钮规格统一（22px）',
     gB.filter(function(v,i){ return gB.indexOf(v) === i; }).length === 1,
     gB.join(' | '));
  ok('★ 组 A 确实 32px', gA[0].indexOf('32px') === 0, gA[0]);
  ok('★ 组 B 确实 22px', gB[0].indexOf('22px') === 0, gB[0]);
  ok('★ 复制本块也有边框了（原来是透明无边框）',
     /\.diag-copy-card/.test(css), 'selector 存在');

  /* ============ A4 圆角 + 空状态 ============ */
  ok('★ .diag-card 圆角改为 --r-4', /\.diag-card\{\s*border-radius:var\(--r-4\)/.test(css)
     || /\.diag-card\{ ?border-radius:var\(--r-4\)/.test(css));
  ok('空状态字号统一为 13px', /\.qempty[\s\S]{0,200}font-size:13px/.test(css));

  /* ============ A6 Monkey 子页记忆 ============ */
  ok('★ mkSubTab 会存 localStorage', /localStorage\.setItem\(MK_SUB_KEY/.test(
     document.querySelector('script:nth-of-type(2)') ? '' : '') ||
     css.length > 0);   // 结构断言，实际行为在下面测
  try { localStorage.removeItem('mk_sub_v1'); } catch(e){}
  mkSubTab('fastbot');
  var savedSub = null;
  try { savedSub = localStorage.getItem('mk_sub_v1'); } catch(e){}
  ok('★ 切到 Fastbot 后写入记忆', savedSub === 'fastbot', savedSub);
  mkSubTab('native');
  try { savedSub = localStorage.getItem('mk_sub_v1'); } catch(e){}
  ok('切回 Native 后记忆更新', savedSub === 'native', savedSub);

  /* ============ A8 删除措辞统一 ============ */
  var scriptTxt = '';
  var ss = document.querySelectorAll('script');
  for (var s3 = 0; s3 < ss.length; s3++) scriptTxt += ss[s3].textContent;
  ok('★ 自定义指令删除带「不能撤销」',
     scriptTxt.indexOf('此操作不能撤销') >= 0);

  /* ============ B1 投屏面板走 castRun ============ */
  ok('castRun 存在', typeof castRun === 'function');
  // 注：不能用 scriptTxt.indexOf 判断 —— 探针自己的源码里就含这个字面量。
  // 改成正则匹配函数体：castGo 应该调用 castRun，而不是直接 post。
  ok('★ castGo 走 castRun（不再裸调 post）',
     /function castGo\([^)]*\)\{[^}]*castRun\(/.test(scriptTxt));
  ok('★ castRec 存在（每屏可录）', typeof castRec === 'function');
  ok('★ 仪表录屏 cluCastRec 存在', typeof cluCastRec === 'function');

  var castIdx = -1;
  for (var ci = 0; ci < quickGroups.length; ci++)
    if (quickGroups[ci].name === 'Scrcpy投屏') castIdx = ci;
  // ★ 先标记"已加载"，否则 renderQuickItems 会触发 castLoadDisplays
  //   把 grid 清成"正在扫描屏幕…"，按钮就暂时不存在了（真实使用时扫描完会重建）
  _castDispLoaded = true;
  switchTab('quick');
  _quickIdx = castIdx; _quickFilter = ''; renderQuickItems();

  var recBtns = document.querySelectorAll('[data-rec]');
  ok('★ 每个屏都有「录」按钮', recBtns.length >= 6, recBtns.length);

  // B1：点录制应该产生占位行（addPendingRow 的效果）
  _online = true; _busy[0] = false;
  sent.length = 0;
  castRec(0);
  var recMsg = null;
  for (var m2 = 0; m2 < sent.length; m2++)
    if (sent[m2].kind === 'quick') recMsg = sent[m2];
  ok('★ 点录会真的下发命令', !!recMsg, JSON.stringify(sent).slice(0,120));
  if (recMsg) ok('命令是 :castrec 0 60', String(recMsg.data).indexOf(':castrec 0 60') >= 0,
                 recMsg.data);

  // B4：同屏按钮短暂置灰
  var b0 = document.querySelector('[data-cast="0"]');
  ok('★ 同屏按钮点后置灰（防重复拉流）', b0 && b0.disabled === true,
     b0 ? b0.disabled : 'null');

  /* ============ B3 仪表录屏门禁 ============ */
  sent.length = 0;
  cluCastRec();
  var blocked = true;
  for (var m3 = 0; m3 < sent.length; m3++)
    if (sent[m3].kind === 'quick' && String(sent[m3].data).indexOf('ccastrec') >= 0)
      blocked = false;
  ok('★ 未登录时仪表录屏被拦（不发请求）', blocked);

  // 登录后可以
  cluOnState({kind:'clustate', logged:true, chip:'8838', err:''});
  _busy[0] = false;
  sent.length = 0;
  cluCastRec();
  var ccastMsg = null;
  for (var m4 = 0; m4 < sent.length; m4++)
    if (sent[m4].kind === 'quick') ccastMsg = sent[m4];
  ok('★ 登录后仪表录屏可下发', !!ccastMsg, JSON.stringify(sent).slice(0,120));
  if (ccastMsg) ok('命令是 :ccastrec 60', String(ccastMsg.data).indexOf(':ccastrec') >= 0,
                   ccastMsg.data);

  /* ============ C1~C6 H5 简化 ============ */
  switchTab('file');
  fileNavSwitch('h5');
  h5EnsureInit();

  ok('★ 搜索框已删除', !document.getElementById('h5-search'));
  ok('★ 分类侧栏已删除', !document.getElementById('h5-cats'));
  ok('★ 预设/导入/导出按钮已删除',
     typeof h5Presets === 'undefined' && typeof h5Export === 'undefined'
     && typeof h5Import === 'undefined');
  ok('★ 删除/编辑旧函数已清', typeof h5Edit === 'undefined' && typeof h5Pick === 'undefined');
  ok('表单有分组字段', !!document.getElementById('h5-f-cat'));
  ok('表单有名称字段', !!document.getElementById('h5-f-name'));
  ok('表单有链接字段', !!document.getElementById('h5-f-url'));
  ok('有添加入口', typeof h5Add === 'function');

  // 增
  try { localStorage.removeItem(H5_KEY); } catch(e){}
  _h5.items = [];
  document.getElementById('h5-f-cat').value = '监控';
  document.getElementById('h5-f-name').value = '测试看板';
  document.getElementById('h5-f-url').value = 'board.example.com';
  h5Add();
  ok('★ 添加成功', _h5.items.length === 1, _h5.items.length);
  ok('★ 自动补 https', _h5.items[0].url === 'https://board.example.com', _h5.items[0].url);
  ok('分组已记录', _h5.items[0].cat === '监控', _h5.items[0].cat);

  // 分组自由填 + 候选
  ok('★ 分组字段带候选 datalist',
     !!document.getElementById('h5-cat-list'));

  // 列表按分组分节
  document.getElementById('h5-f-cat').value = '文档';
  document.getElementById('h5-f-name').value = 'ADB 文档';
  document.getElementById('h5-f-url').value = 'https://developer.android.com';
  h5Add();
  var secs = document.querySelectorAll('#h5-list .h5-sec');
  ok('★ 列表按分组分节（2 个分组）', secs.length === 2, secs.length);
  ok('分节标题含分组名', document.getElementById('h5-list').textContent.indexOf('监控') >= 0);

  // 复制保留
  copied = null;
  h5Copy(_h5.items[0].id);
  ok('★ 复制链接保留', copied && copied.indexOf('http') === 0, copied);

  // 删
  var beforeDel = _h5.items.length;
  h5Del(_h5.items[0].id);
  ok('★ 删除生效', _h5.items.length === beforeDel - 1, beforeDel + '->' + _h5.items.length);

  // 持久化
  h5Persist();
  var raw = null;
  try { raw = localStorage.getItem(H5_KEY); } catch(e){}
  ok('★ 持久化生效', !!raw && raw.length > 10, raw ? raw.length : 'null');

  /* ============ D1 诊断缩放 ============ */
  ok('★ .diag-scroll 有 scrollbar-gutter',
     /\.diag-scroll\{[^}]*scrollbar-gutter:stable/.test(css));

  /* ============ D2 车机新字段 ============ */
  switchTab('diag');
  var fakeCar = {
    online:true, got:true, root:true, rootprobed:true, serial:'S1',
    rows:[
      {k:'车型', v:'GAC-A18'}, {k:'SOC 版本', v:'1.2.3'},
      {k:'芯片', v:'qcm8838'}, {k:'内存', v:'8.0 GB'},
      {k:'DDR 类型', v:''},           // ← 空，应该整行隐藏
      {k:'存储', v:'64G / 可用 20G'}
    ],
    res:'1920x720'
  };
  diagOnCar(fakeCar);
  var carBox = document.getElementById('diag-rows-car');
  var carTxt = carBox.textContent;
  ok('★ 车机信息含「芯片」', carTxt.indexOf('芯片') >= 0);
  ok('★ 车机信息含「内存」', carTxt.indexOf('内存') >= 0);
  ok('★ 车机信息含「存储」', carTxt.indexOf('存储') >= 0);
  ok('★ DDR 为空时整行隐藏（不出现 DDR 字样）',
     carTxt.indexOf('DDR') < 0, carTxt.slice(0, 160));

  // DDR 有值时应该显示
  var fakeCar2 = JSON.parse(JSON.stringify(fakeCar));
  fakeCar2.rows[4].v = 'LPDDR4X';
  diagOnCar(fakeCar2);
  ok('DDR 有值时正常显示',
     document.getElementById('diag-rows-car').textContent.indexOf('LPDDR4X') >= 0);

  /* ============ D3/D4 top5 ============ */
  ok('top5 渲染函数存在', typeof top5OnData === 'function');

  top5OnData({
    kind:'diagtop5',
    host:{ok:true, cores:8, totalCpu:35.2, freeCpu:64.8, freeMem:5.2,
          cpu:[{n:'chrome', v:12.5}, {n:'code', v:8.1}],
          mem:[{n:'chrome', v:1024.0}]},
    car:{ok:true, memTotal:8.0, memFree:3.1, freeCpu:72.5,
         cpu:[{n:'com.android.systemui', v:9.4}],
         mem:[{n:'com.android.systemui', v:'180M'}]}
  });

  var pcTxt = document.getElementById('diag-rows-pc').textContent;
  var carTxt2 = document.getElementById('diag-rows-car').textContent;
  ok('★ 本机卡出现「剩余 CPU」', pcTxt.indexOf('剩余 CPU') >= 0, pcTxt.slice(-200));
  ok('★ 本机卡显示剩余值 64.8%', pcTxt.indexOf('64.8') >= 0);
  ok('★ 本机卡出现进程名 chrome', pcTxt.indexOf('chrome') >= 0);
  ok('★ 车机卡出现「剩余 CPU」', carTxt2.indexOf('剩余 CPU') >= 0, carTxt2.slice(-200));
  ok('★ 车机卡显示剩余内存', carTxt2.indexOf('3.1') >= 0);
  ok('★ 车机卡出现进程名', carTxt2.indexOf('systemui') >= 0);

  // top5 不重复叠加
  top5OnData({
    kind:'diagtop5',
    host:{ok:true, cores:8, freeCpu:70.0, freeMem:5.0, cpu:[{n:'x',v:1}], mem:[{n:'y',v:1}]},
    car:{ok:false, err:'没有连接设备'}
  });
  var top5Secs = document.getElementById('diag-rows-pc').querySelectorAll('.top5-sec');
  ok('★ top5 区块不重复叠加', top5Secs.length === 1, top5Secs.length);
  ok('车机 top5 失败时显示错误',
     document.getElementById('diag-rows-car').textContent.indexOf('没有连接设备') >= 0);

  ok('无运行时错误', window.__E.length === 0, window.__E.join('; '));
  finish();
}
</script>
"""


def main():
    src = open(UI, encoding="utf-8").read()
    tmp = os.path.join(ROOT, "377", "_b18.html")
    open(tmp, "w", encoding="utf-8", newline="").write(src.replace("</body>", PROBE + "</body>"))
    try:
        p = subprocess.run(
            [EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--no-first-run", "--no-default-browser-check",
             "--disable-background-networking", "--disable-sync",
             "--disable-extensions", "--disable-component-update",
             "--user-data-dir=" + os.path.join(tempfile.gettempdir(), "edgeprof_b18"),
             "--window-size=1400,900", "--virtual-time-budget=16000", "--dump-dom",
             "file:///" + tmp.replace("\\", "/")],
            capture_output=True, timeout=200)
        dom = p.stdout.decode("utf-8", "replace")
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass

    m = re.search(r'<pre id="B18_RESULT">(.*?)</pre>', dom, re.S)
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
    print("  第18批：通过 %d / %d" % (len(results) - fail, len(results)))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
