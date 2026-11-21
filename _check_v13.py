# -*- coding: utf-8 -*-
"""A13 结构与行为实测（headless Edge）。

真跑页面，不信源码猜测。覆盖：
  标题栏重组（四点 / 无品牌文字 / 无 .topbar）· 圆点尺寸与配色 · 即时 tooltip ·
  点圆点不触发拖窗口 · 终端 textarea 多行逐条顺序执行 · 四个纯图标按钮 ·
  输出区点空白收起/展开 · 侧栏小标题已删
"""
import io
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
OUT = os.path.join(ROOT, "377", "_v13_probe.html")


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
  function emit(){ var p=document.createElement('pre'); p.id='RESULT';
    p.textContent=R.join('\n'); document.body.appendChild(p); }
  var st=document.createElement('style');
  st.textContent='*{transition:none!important;animation:none!important;}';
  document.head.appendChild(st);

  function g(sel,prop){ var el=document.querySelector(sel); if(!el) return '';
    return getComputedStyle(el)[prop]||''; }
  function posts(kind){ return (window.__POST||[]).filter(function(o){return o && o.kind===kind;}); }
  function clr(){ window.__POST.length = 0; }

  setTimeout(function(){
   try{
    /* ---------- 1. 标题栏结构 ---------- */
    ok('标题栏存在', !!document.getElementById('titlebar'));
    ok('.topbar 已删除', document.querySelectorAll('.topbar').length === 0);
    ok('品牌文字已删（无 .tb-name）', document.querySelectorAll('.tb-name').length === 0);
    var box = document.getElementById('tb-status');
    ok('四个状态点容器存在', !!box);
    var ids = ['root-pill','wadb-btn','log-pill','dev-badge'];
    var allin = !!box;
    for (var i=0;i<ids.length;i++){
      var el = document.getElementById(ids[i]);
      if (!el || !box || !box.contains(el)) allin = false;
    }
    ok('四个点都在 #tb-status 内', allin);
    ok('设备点在容器内', !!(box && box.contains(document.getElementById('dev-badge'))));

    /* ---------- 2. 圆点尺寸与隐藏文字 ---------- */
    var dh = parseFloat(g('.tb-status .rdot','width')) || 0;
    ok('圆点直径 9px', Math.abs(dh-9) < 0.6, dh);
    var hit = parseFloat(g('#root-pill','width')) || 0;
    ok('命中区 ≥24px', hit >= 24, hit);
    var hid = ['.tb-status .rtxt', '.tb-status .ltag', '.tb-status #wadb-txt',
               '.tb-status .device .id'];
    var allHidden = true, bad = '';
    for (var k=0;k<hid.length;k++){
      var d = g(hid[k],'display');
      if (d !== 'none') { allHidden = false; bad += hid[k] + '=' + d + ' '; }
    }
    ok('点内文字全部隐藏', allHidden, bad);
    ok('日志胶囊有圆点', !!document.getElementById('log-dot'));

    /* ---------- 3. 配色：root / 无线 / 日志 / 设备 ---------- */
    var accent = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim();
    var rp = document.getElementById('root-pill');
    rp.classList.remove('no','off','disabled','busy'); rp.classList.add('yes');
    var cYes = g('.tb-status .rootpill.yes .rdot','backgroundColor');
    rp.classList.remove('yes'); rp.classList.add('no');
    var cNo = g('.tb-status .rootpill.no .rdot','backgroundColor');
    ok('root 已 root 用强调色（与未 root 不同）', cYes !== cNo, cYes + ' vs ' + cNo);
    rp.classList.remove('no'); rp.classList.add('off');

    var wb = document.getElementById('wadb-btn');
    wb.classList.remove('on');
    var wOff = g('.tb-status .wadb-btn .wdot','backgroundColor');
    wb.classList.add('on');
    var wOn = g('.tb-status .wadb-btn.on .wdot','backgroundColor');
    ok('无线已连接用强调色（与未连接不同）', wOn !== wOff, wOn + ' vs ' + wOff);
    wb.classList.remove('on');

    var lp = document.getElementById('log-pill');
    lp.style.display = '';
    var cols = {}, lvs = ['V','D','I','W','E'], uniq = {};
    for (var m=0;m<lvs.length;m++){
      lp.setAttribute('data-lv', lvs[m]);
      cols[lvs[m]] = g('.tb-status .logpill[data-lv="'+lvs[m]+'"] .dot','backgroundColor');
      uniq[cols[lvs[m]]] = 1;
    }
    ok('日志五级颜色互不相同', Object.keys(uniq).length === 5, JSON.stringify(cols));
    ok('V 级在深色下是白/近白', /255,\s*255,\s*255/.test(cols['V']), cols['V']);
    lp.setAttribute('data-lv','none');
    var cNone = g('.tb-status .logpill[data-lv="none"] .dot','backgroundColor');
    ok('未设置时是灰（不同于五级）', Object.keys(uniq).indexOf(cNone) < 0, cNone);

    /* ---------- 4. 即时 tooltip（异步：代码里有 60ms 防抖，这里先触发） ---------- */
    lp.setAttribute('data-lv','I');
    lp.title = '日志等级：Info';
    (function hover(el){
      var e = document.createEvent('MouseEvents');
      e.initEvent('mouseenter', true, false); el.dispatchEvent(e);
    })(document.getElementById('root-pill'));

    /* ---------- 5. 点圆点不拖窗口（mousedown 不能冒到 .tb-drag） ---------- */
    var leaked = false;
    var drag = document.querySelector('.tb-drag');
    var spy = function(){ leaked = true; };
    drag.addEventListener('mousedown', spy);
    var me = document.createEvent('MouseEvents');
    me.initEvent('mousedown', true, true);
    document.getElementById('root-pill').dispatchEvent(me);
    drag.removeEventListener('mousedown', spy);
    ok('点 root 点不会触发拖窗口', !leaked);

    /* ---------- 6. 标题栏尺寸自适应 ---------- */
    var th = parseFloat(g('.titlebar','height')) || 0;
    ok('标题栏高度在 38~54 之间', th >= 37.5 && th <= 54.5, th);
    var bw = parseFloat(g('.tb-btn','width')) || 0;
    ok('窗口按钮宽度按标题栏派生', Math.abs(bw - th*1.22) < 2, bw + ' vs ' + th);

    /* ---------- 7. 终端：textarea + 纯图标按钮 ---------- */
    var ta = document.getElementById('cmd-input-0');
    ok('终端输入是 textarea', !!ta && ta.tagName === 'TEXTAREA', ta ? ta.tagName : 'null');
    ok('终端输入 1 行起', !!ta && ta.rows === 1, ta ? ta.rows : '');

    var iconsOnly = true, tbad = '', cnt = 0;
    var bar = document.querySelector('#slot-0 .inputbar');
    var all = bar ? bar.querySelectorAll('button') : [];
    for (var b=0;b<all.length;b++){
      // #btn-add 是"新增输入框"的 ＋ 号，不属于那四个操作按钮，单独放过
      if (all[b].id === 'btn-add') continue;
      cnt++;
      var txt = (all[b].textContent||'').trim();
      if (txt.length) { iconsOnly = false; tbad += '['+txt+'] '; }
      if (!all[b].getAttribute('title')) { iconsOnly = false; tbad += 'noTitle '; }
      if (!all[b].querySelector('svg')) { iconsOnly = false; tbad += 'noIcon '; }
    }
    ok('执行/停止/清屏/复制只有图标且有 title', iconsOnly && cnt === 4, cnt + ' ' + tbad);
    var addb = document.getElementById('btn-add');
    ok('新增槽位按钮有 title', !!(addb && addb.getAttribute('title')));

    /* ---------- 8. Shift+Enter 换行 ---------- */
    clr();
    ta.value = 'echo a';
    ta.selectionStart = ta.selectionEnd = ta.value.length;
    var kev = new KeyboardEvent('keydown', {key:'Enter', shiftKey:true, bubbles:true, cancelable:true});
    ta.dispatchEvent(kev);
    ok('Shift+Enter 插入换行', ta.value.indexOf('\n') >= 0, JSON.stringify(ta.value));
    ok('Shift+Enter 不执行', posts('cmd').length === 0, posts('cmd').length);

    /* ---------- 9. Enter 单行执行 ---------- */
    clr();
    ta.value = 'echo single';
    ta.selectionStart = ta.selectionEnd = ta.value.length;
    ta.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true, cancelable:true}));
    var p1 = posts('cmd');
    ok('Enter 单行直接执行', p1.length === 1 && /single/.test(p1[0].data||''),
       p1.length ? p1[0].data : 'none');

    /* ---------- 10. 多行逐条顺序执行 ---------- */
    if (window.endRun) window.endRun({slot:0});
    clr();
    ta.value = 'echo one\necho two\necho three';
    window.run(0);
    var first = posts('cmd');
    ok('多行只先发第一条', first.length === 1 && /one/.test(first[0].data||''),
       first.length + ' ' + (first[0] ? first[0].data : ''));
    clr();
    window.endRun({slot:0});
    setTimeout(function(){
     try{
      var second = posts('cmd');
      ok('第一条结束后自动发第二条', second.length === 1 && /two/.test(second[0].data||''),
         second.length + ' ' + (second[0] ? second[0].data : ''));
      clr();
      window.endRun({slot:0});
      setTimeout(function(){
       try{
        var third = posts('cmd');
        ok('第三条也顺序发出', third.length === 1 && /three/.test(third[0].data||''),
           third.length + ' ' + (third[0] ? third[0].data : ''));
        clr();
        window.endRun({slot:0});
        var fourth = posts('cmd');
        ok('队列跑完不再多发', fourth.length === 0, fourth.length);

        /* ---------- 11. 输出区热区 ---------- */
        var fb = document.getElementById('feedback');
        fb.classList.remove('collapsed');
        ok('fbHeadToggle 已挂', typeof window.fbHeadToggle === 'function');
        var head = document.querySelector('.fb-head');
        var ce = document.createEvent('MouseEvents');
        ce.initEvent('click', true, true);
        head.dispatchEvent(ce);
        ok('点表头空白收起', fb.classList.contains('collapsed'),
           fb.className);

        fb.classList.remove('collapsed');
        var act = document.querySelector('.fb-acts button');
        var ce2 = document.createEvent('MouseEvents');
        ce2.initEvent('click', true, true);
        if (act) act.dispatchEvent(ce2);
        ok('点表头按钮不收起', !fb.classList.contains('collapsed'), fb.className);

        var barC = document.getElementById('fb-collapsed-bar');
        ok('折叠栏可点（cursor:pointer）', g('.fb-collapsed-bar','cursor') === 'pointer',
           g('.fb-collapsed-bar','cursor'));

        /* ---------- 12. tooltip 落地（前面已派发 mouseenter，60ms 防抖早已过） ---------- */
        var tip = document.querySelector('.tb-tip');
        ok('root 悬停出现 tooltip', !!(tip && tip.classList.contains('show')),
           tip ? tip.className : 'no-el');
        ok('tooltip 文案含 root', !!(tip && /root/i.test(tip.textContent)),
           tip ? tip.textContent : '');

        /* ---------- 13. 侧栏小标题已删 ---------- */
        ok('侧栏「指令」小标题已删', document.querySelectorAll('#quick-nav .qnav-title').length === 0);
        ok('侧栏仍有导航项', document.querySelectorAll('#quick-nav .qnav-item').length > 0);

        emit();
       }catch(e){ R.push('FAIL | 内层异常 | '+(e&&e.message)); emit(); }
      }, 60);
     }catch(e){ R.push('FAIL | 中层异常 | '+(e&&e.message)); emit(); }
    }, 60);

   }catch(e){
    R.push('FAIL | 脚本异常 | '+(e && e.message));
    emit();
   }
  }, 900);
})();
</script>
"""


def main():
    src = io.open(UI, encoding="utf-8").read()
    src = src.replace("<head>", "<head>\n" + PRE, 1)
    src = src.replace("</body>", JS + "</body>", 1)
    io.open(OUT, "w", encoding="utf-8").write(src)

    cmd = [find_edge(), "--headless=new", "--disable-gpu", "--window-size=1280,940",
               "--no-first-run", "--no-default-browser-check",
               "--disable-background-networking", "--disable-sync",
               "--disable-extensions", "--disable-component-update",
           "--virtual-time-budget=15000", "--dump-dom",
           "--user-data-dir=" + os.path.join(tempfile.gettempdir(), "edgeprof_v13_%d" % os.getpid()),
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
    print("\n  A13 实测：通过 %d / %d" % (len(lines) - len(fails), len(lines)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
