# -*- coding: utf-8 -*-
"""A14 结构与行为实测（headless Edge）。

本文件覆盖 2026-11-15 第 2 批（网联服务分组）与第 3 批（8 条 UI 反馈）。
真跑页面，不信源码猜测。

网联服务：
  分组位置（紧跟「指令执行」）· 13 张卡片 · 分类小标题 ·
  AI智能推荐文案与双入口 · 三条导出走内置命令 · 两条 :url · 设备ID 卡片

UI 8 条：
  启动图标（含信号弧/底座）+ 跟随强调色 · 浅色边界对比度 · 标题栏图标尺寸 ·
  按钮有"面" · 下拉浮层在深色下不是白底 · 设置里两处中文已删 ·
  字体大小三段（小/中/大）与 uizoom 消息
"""
import io
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
OUT = os.path.join(ROOT, "377", "_a14_probe.html")


def find_edge():
    for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            p = os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")
            if os.path.exists(p):
                return p
    return "msedge.exe"


PRE = r"""<script>
window.__POST = [];
window.chrome = { webview: { postMessage: function(o){ window.__POST.push(o); } } };
window.confirm = function(){ return true; };
window.prompt = function(){ return 'DengXian'; };
window.alert = function(){};
</script>
"""

JS = r"""
<script>
(function(){
  var R=[];
  function ok(n,c,x){ R.push((c?'PASS':'FAIL')+' | '+n+(c?'':' | '+(x===undefined?'':x))); }
  function emit(){
    var p=document.createElement('pre'); p.id='RESULT';
    p.textContent=R.join('\n'); document.body.appendChild(p);
  }
  var st=document.createElement('style');
  st.textContent='*{transition:none!important;animation:none!important;}';
  document.head.appendChild(st);

  function g(sel,prop){ var el=document.querySelector(sel); if(!el) return '';
    return getComputedStyle(el)[prop]||''; }
  function posts(kind){ return (window.__POST||[]).filter(function(o){return o && o.kind===kind;}); }
  function idxOf(name){
    for(var i=0;i<quickGroups.length;i++) if(quickGroups[i].name === name) return i;
    return -1;
  }
  function hasChinese(t){ return /[\u4e00-\u9fa5]/.test(String(t||'')); }
  function parse(c){
    var s = String(c).trim();
    var h = s.match(/^#([0-9a-fA-F]{6})$/);
    if(h){
      var n = parseInt(h[1], 16);
      return { r:(n>>16)&255, g:(n>>8)&255, b:n&255, a:1 };
    }
    var m = s.match(/rgba?\(([^)]+)\)/);
    if(!m) return null;
    var p = m[1].split(',').map(function(x){ return parseFloat(x); });
    return { r:p[0], g:p[1], b:p[2], a:(p.length>3?p[3]:1) };
  }
  function overWhite(c){
    var o = parse(c); if(!o) return null;
    return { r:o.r*o.a+255*(1-o.a), g:o.g*o.a+255*(1-o.a), b:o.b*o.a+255*(1-o.a) };
  }
  function lum(o){
    function f(v){ v=v/255; return v<=0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); }
    return 0.2126*f(o.r) + 0.7152*f(o.g) + 0.0722*f(o.b);
  }
  function ratio(c){
    var o = overWhite(c); if(!o) return 0;
    return 1.05/(lum(o)+0.05);
  }
  function tok(name){
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }
  function isWhite(rgb){
    var o = parse(rgb);
    return !!o && o.r > 230 && o.g > 230 && o.b > 230;
  }
  function esc(k){ document.dispatchEvent(new KeyboardEvent('keydown', { key:'Escape', bubbles:true })); }

  function run(){
    /* ================= 一、网联服务分组 ================= */
    var qe = idxOf('指令执行'), ws = idxOf('网联服务');
    ok('存在「网联服务」分组', ws >= 0, ws);
    ok('紧跟在「指令执行」下面', ws === qe + 1, qe + ' -> ' + ws);
    if (ws < 0) return;

    var items = quickGroups[ws].items;
    ok('网联服务 13 条卡片', items.length === 13, items.length);

    var want = ['AI智能推荐后台','配置中心后台','支付宝后台','上传支付宝日志',
                '导出支付宝日志','导出微信小程序日志','导出车载微信日志',
                '打开星河云埋点','查询星河云埋点设置','设置星河云埋点true','查询设备ID',
                '打开星河埋点云','打开讯飞IOT云'];
    var names = items.map(function(it){ return it.name; });
    var miss = want.filter(function(w){ return names.indexOf(w) < 0; });
    ok('13 个卡片名齐全', miss.length === 0, miss.join(','));

    var cats = {};
    items.forEach(function(it){ if(it.cat) cats[it.cat]=1; });
    ok('按 4 个分类分组', Object.keys(cats).length === 4, Object.keys(cats).join('/'));

    function find(n){ for(var i=0;i<items.length;i++) if(items[i].name===n) return items[i]; return null; }
    ok('AI智能推荐 在网联服务里也有一张',
       !!find('AI智能推荐后台') && find('AI智能推荐后台').cmd === 'airec',
       find('AI智能推荐后台') && find('AI智能推荐后台').cmd);
    ok('三条导出走内置命令',
       (find('导出支付宝日志')||{}).cmd === ':wsalipay'
       && (find('导出微信小程序日志')||{}).cmd === ':wswmpf'
       && (find('导出车载微信日志')||{}).cmd === ':wswx',
       [find('导出支付宝日志'),find('导出微信小程序日志'),find('导出车载微信日志')]
         .map(function(x){ return x && x.cmd; }).join(','));
    ok('打开埋点走 :sxlog', (find('打开星河云埋点')||{}).cmd === ':sxlog',
       (find('打开星河云埋点')||{}).cmd);
    ok('查询设备ID 走 :wsdevid', (find('查询设备ID')||{}).cmd === ':wsdevid',
       (find('查询设备ID')||{}).cmd);
    var urls = items.filter(function(it){ return (it.cmd||'').indexOf(':url https://') === 0; });
    ok('两条云平台走 :url', urls.length === 2, urls.length);
    ok('讯飞 IOT 链接正确', urls.some(function(u){ return u.cmd.indexOf('link.xfyun.cn/logs') > 0; }));
    ok('埋点校验页链接正确', urls.some(function(u){ return u.cmd.indexOf('acquisition-center-front') > 0; }));

    switchTab('quick');
    var nav = document.querySelectorAll('#quick-nav .qnav-item');
    var hit = -1;
    for(var i=0;i<nav.length;i++) if(nav[i].textContent.indexOf('网联服务') >= 0) hit = i;
    ok('侧栏出现「网联服务」导航项', hit >= 0);
    if (hit >= 0){
      nav[hit].click();
      var cards = document.querySelectorAll('#quick-grid .qcard');
      ok('渲染出 13 张卡', cards.length === 13, cards.length);
      ok('渲染出 4 个分类小标题', document.querySelectorAll('#quick-grid .qcat').length === 4,
         document.querySelectorAll('#quick-grid .qcat').length);
      var nm = document.getElementById('quick-group-name');
      ok('分组标题是「网联服务」', nm && nm.textContent === '网联服务', nm && nm.textContent);
    }

    /* ================= 二、AI智能推荐文案（需求 2.1） ================= */
    var qeItems = quickGroups[qe].items, ai = null;
    for(var k=0;k<qeItems.length;k++) if(qeItems[k].name === 'AI智能推荐后台') ai = qeItems[k];
    ok('指令执行里 AI 卡片说明已改', ai && ai.desc === '进入AI智能推荐后台', ai && ai.desc);

    /* ================= 三、启动图标（需求 1） ================= */
    /* A17 起图标改了结构：图形只画一份，放在 body 顶部的 <defs id="appmark-glyph">，
       启动层和标题栏各用一个 <use> 引用它（同源 = 改一处两处一起变）。
       所以断言要分两段：外层 svg 看"黑底方 + use 引用对不对"，
       defs 里看"图形本体有没有画全"。 */
    var sp = document.querySelector('.splash .cat svg');
    ok('启动动画有图标', !!sp);
    if (sp){
      var use = sp.querySelector('use');
      ok('图标引用统一图形（use → #appmark-glyph）',
         !!use && (use.getAttribute('href') === '#appmark-glyph' ||
                   use.getAttributeNS('http://www.w3.org/1999/xlink', 'href') === '#appmark-glyph'),
         use ? use.getAttribute('href') : 'no-use');
      ok('图标自带黑底圆角方（1 个 rect）', sp.querySelectorAll('rect').length === 1,
         sp.querySelectorAll('rect').length);
    }
    var gl = document.getElementById('appmark-glyph');
    ok('图形本体存在（defs #appmark-glyph）', !!gl);
    if (gl){
      ok('图形含信号双弧 + 提示符 + 底座（path ≥ 4）', gl.querySelectorAll('path').length >= 4,
         gl.querySelectorAll('path').length);
      ok('图形含中控屏面板 + 底座（2 个 rect）', gl.querySelectorAll('rect').length === 2,
         gl.querySelectorAll('rect').length);
    }
    if (typeof applyAccent === 'function') applyAccent('green');
    var c1 = parse(g('.splash .cat','color')), c2 = parse(tok('--accent'));
    ok('启动图标颜色跟随强调色',
       !!c1 && !!c2 && Math.abs(c1.r-c2.r) < 6 && Math.abs(c1.g-c2.g) < 6 && Math.abs(c1.b-c2.b) < 6,
       g('.splash .cat','color') + ' vs ' + tok('--accent'));
    if (typeof applyAccent === 'function') applyAccent('blue');

    /* ================= 四、标题栏图标尺寸（需求 3） ================= */
    var lw = parseFloat(g('.tb-logo svg','width')) || 0;
    ok('标题栏图标 ≥ 20px（原来 15/18）', lw >= 20, lw);

    /* ================= 五、浅色边界对比度（需求 2 / 4） ================= */
    applyTheme('light');
    void document.body.offsetWidth;
    var lb = tok('--border');
    ok('白天模式边框对比度 ≥ 2.2:1', ratio(lb) >= 2.2, ratio(lb).toFixed(2) + ' (' + lb + ')');
    // 卡片真正的边框来自 .qcard 的 border-color（A11 玻璃层写的是 --edge，几乎透明），
    // 只测令牌不够，必须测计算后的边框色 + 卡片自身底色。
    var cardEdge = g('#page-quick .qcard','borderTopColor');
    var cardFace = g('#page-quick .qcard','backgroundColor');
    var re2 = cardEdge && cardFace ? (function(){
      var f = parse(cardEdge), b = parse(cardFace);
      if (!f || !b) return 0;
      var c = { r:f.r*f.a+b.r*(1-f.a), g:f.g*f.a+b.g*(1-f.a), b:f.b*f.a+b.b*(1-f.a) };
      var L1 = lum(c), L2 = lum(b);
      if (L1 < L2){ var t = L1; L1 = L2; L2 = t; }
      return (L1+0.05)/(L2+0.05);
    })() : 0;
    ok('白天卡片边框实测 ≥ 2.0:1', re2 >= 2.0, re2.toFixed(2) + ' (' + cardEdge + ')');
    var cmdC = g('#page-quick .qcard .qcmd','color');
    ok('白天卡片说明文字 ≥ 3.4:1', ratio(cmdC) >= 3.4, ratio(cmdC).toFixed(2) + ' (' + cmdC + ')');
    var btnBg = g('#page-quick .btn','backgroundColor');
    var cardBg = g('#page-quick .qcard','backgroundColor');
    ok('白天按钮有独立面（不等于卡片底色）', btnBg !== cardBg, btnBg + ' vs ' + cardBg);
    ok('左侧导航有选中项', document.querySelectorAll('#quick-nav .qnav-item.active').length === 1,
       document.querySelectorAll('#quick-nav .qnav-item.active').length);
    applyTheme('eye');
    void document.body.offsetWidth;
    ok('护眼模式边框对比度 ≥ 2.0:1', ratio(tok('--border')) >= 2.0,
       ratio(tok('--border')).toFixed(2));
    var eyeEdge = g('#page-quick .qcard','borderTopColor');
    var eyeFace = g('#page-quick .qcard','backgroundColor');
    var re3 = 0;
    (function(){
      var f = parse(eyeEdge), b = parse(eyeFace);
      if (!f || !b) return;
      var c = { r:f.r*f.a+b.r*(1-f.a), g:f.g*f.a+b.g*(1-f.a), b:f.b*f.a+b.b*(1-f.a) };
      var L1 = lum(c), L2 = lum(b);
      if (L1 < L2){ var t = L1; L1 = L2; L2 = t; }
      re3 = (L1+0.05)/(L2+0.05);
    })();
    ok('护眼卡片边框实测 ≥ 1.9:1', re3 >= 1.9, re3.toFixed(2) + ' (' + eyeEdge + ')');

    /* ================= 六、深色下拉浮层（需求 5 / 7） ================= */
    applyTheme('dark');
    openSettings();
    var sel = document.getElementById('set-font');
    ok('设置里有字体下拉', !!sel);
    if (sel){
      sel.dispatchEvent(new MouseEvent('mousedown', { bubbles:true, cancelable:true }));
      var pop = document.querySelector('.a14-selpop');
      ok('点开出的是自绘浮层（不是原生弹层）', !!pop);
      if (pop){
        ok('深色下浮层不是白底', !isWhite(g('.a14-selpop','backgroundColor')),
           g('.a14-selpop','backgroundColor'));
        ok('浮层列出全部字体', pop.querySelectorAll('.it').length >= 6,
           pop.querySelectorAll('.it').length);
        ok('浮层当前项有选中标记', pop.querySelectorAll('.it.on').length === 1);
        esc();
        ok('Esc 关闭浮层', !document.querySelector('.a14-selpop'));
      }
    }
    switchTab('text');
    var eol = document.getElementById('tx-eol');
    ok('文本页有换行下拉', !!eol);
    if (eol){
      eol.dispatchEvent(new MouseEvent('mousedown', { bubbles:true, cancelable:true }));
      var pop2 = document.querySelector('.a14-selpop');
      ok('换行下拉同样走自绘浮层', !!pop2);
      if (pop2){
        ok('深色下换行浮层不是白底', !isWhite(g('.a14-selpop','backgroundColor')),
           g('.a14-selpop','backgroundColor'));
        esc();
      }
    }
    switchTab('quick');

    /* ================= 七、去掉中文（需求 6） ================= */
    var pv = document.getElementById('set-font-preview');
    ok('字体预览无中文', pv && !hasChinese(pv.textContent), pv && pv.textContent);
    var abouts = document.querySelectorAll('.set-about'), cn = 0;
    for (var a=0;a<abouts.length;a++){
      if (abouts[a].className.indexOf('dim') >= 0) continue;  // dim 是"单机本地运行"说明行
      if (hasChinese(abouts[a].textContent)) cn++;
    }
    ok('关于区主名无中文', cn === 0, cn);

    /* ================= 八、字体大小（需求 8） ================= */
    openSettings();
    var box = document.getElementById('set-fsize');
    ok('设置里有字体大小区', !!box);
    if (box){
      var bs = box.querySelectorAll('button');
      ok('小/中/大三段', bs.length === 3, bs.length);
      var txt = '';
      for (var b=0;b<bs.length;b++) txt += bs[b].textContent;
      ok('文案是 小中大', txt.indexOf('小')>=0 && txt.indexOf('中')>=0 && txt.indexOf('大')>=0, txt);
      var before = posts('uizoom').length;
      bs[2].click();
      var got = posts('uizoom');
      ok('点「大」会发 uizoom', got.length > before, got.length);
      ok('「大」= 1.15', got.length && parseFloat(got[got.length-1].data) === 1.15,
         got.length && got[got.length-1].data);
      ok('偏好里记下 size=l', _prefs.size === 'l', _prefs.size);
      ok('「大」按钮进入选中态', bs[2].classList.contains('on'));
      bs[0].click();
      var got2 = posts('uizoom');
      ok('「小」= 0.9', parseFloat(got2[got2.length-1].data) === 0.9, got2[got2.length-1].data);
      ok('偏好里记下 size=s', _prefs.size === 's', _prefs.size);
      bs[1].click();
      ok('回到「中」= 1.0', parseFloat(posts('uizoom').slice(-1)[0].data) === 1.0);
    }
  }

  setTimeout(function(){
    try { run(); }
    catch(e){ ok('执行异常', false, e && (e.message + ' @ ' + String(e.stack||'').split('\n')[1])); }
    emit();
  }, 200);
})();
</script>
"""


def main():
    src = io.open(UI, encoding="utf-8").read()
    src = src.replace("<head>", "<head>\n" + PRE, 1)
    src = src.replace("</body>", JS + "</body>", 1)
    io.open(OUT, "w", encoding="utf-8").write(src)

    cmd = [find_edge(), "--headless=new", "--disable-gpu", "--window-size=1280,940",
           "--virtual-time-budget=20000", "--dump-dom",
           "--user-data-dir=" + os.path.join(tempfile.gettempdir(), "edgeprof_a14"),
           "file:///" + OUT.replace("\\", "/")]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=300)
    m = re.search(r'<pre id="RESULT">(.*?)</pre>', r.stdout or "", re.S)
    if not m:
        print("没拿到 RESULT，DOM 长度", len(r.stdout or ""))
        print((r.stderr or "")[:800])
        return 1
    import html as H
    lines = [l for l in H.unescape(m.group(1)).splitlines() if l.strip()]
    fails = [l for l in lines if l.startswith("FAIL")]
    for l in lines:
        print("  " + l)
    print("\n  A14 实测：通过 %d / %d" % (len(lines) - len(fails), len(lines)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
