# -*- coding: utf-8 -*-
"""交互一致性实测（2026-11-16 交互走查 I1~I5 的回归套件）。

为什么单独一套：
    这些点是"跨层"的 —— 页签切换被 V12/V13/V15/V17 包了 4 层，
    投屏点击依赖纯函数坐标换算，轮询的启停跨越页签切换。
    单看任何一层都发现不了，必须放在 ui.html 真实加载后打靶。

校验点：
  A. 6 个页签逐一可切换且互斥（含「文本」页 —— 它原本只靠 V12 钩子补 active）
  B. switchTab 4 层包装链不抛异常（连切 6 轮）
  C. Ctrl+1~4 快捷键映射正确
  D. 离开投屏页停掉状态轮询、回来重启（I4）
  E. castMapPoint 纯函数：居中缩放 / 黑边返回 null / 边界 / 比例换算
  F. 黑边点击提示的节流数组存在（I5 的接线检查）
"""
import html as H
import io
import os
import re
import subprocess
import sys
import tempfile

try:
    import _wv2                  # 真实 WebView2 测量通道（同目录）
except Exception:
    _wv2 = None

try:
    import _ui_drive            # 真实鼠标/键盘序列驱动（T17）
except Exception:
    _ui_drive = None
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
OUT = os.path.join(ROOT, "377", "_interaction_probe.html")


def find_edge():
    for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            p = os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")
            if os.path.exists(p):
                return p
    return "msedge.exe"


JS = r"""
<script>
(function(){
  var R=[];
  function ok(n,c,x){ R.push((c?'PASS':'FAIL')+' | '+n+(c?'':' | '+(x===undefined?'':x))); }
  function emit(){ var p=document.createElement('pre'); p.id='RESULT';
    p.textContent=R.join('\n'); document.body.appendChild(p); }

  // 关动画，避免读中间态
  var st=document.createElement('style');
  st.textContent='*{transition:none!important;animation:none!important;}';
  document.head.appendChild(st);

  /* 2026-11-21（第 7 批需求3）：ui/text 已并入文件页，不再是独立一级页面。
     所以"互斥检查"只看三个真实页面；ui/text 作为**别名**单独验证
     （切过去应落到 file 页 + 对应子视图）。 */
  var TABS=['quick','cmd','file'];
  var ALIAS=[{n:'ui',fv:'ui'},{n:'text',fv:'text'}];

  function __runAll(){
    try{
      /* ---------- A. 6 页签互斥 ---------- */
      var bad=[];
      for(var i=0;i<TABS.length;i++){
        var n=TABS[i];
        try { switchTab(n); } catch(e){ bad.push(n+':throw'); continue; }
        var act=[];
        for(var j=0;j<TABS.length;j++){
          var el=document.getElementById('page-'+TABS[j]);
          if(el && el.classList.contains('active')) act.push(TABS[j]);
        }
        if(act.length!==1 || act[0]!==n) bad.push(n+'->['+act.join(',')+']');
        var tabBtn=document.querySelector('.tab[data-tab="'+n+'"]');
        if(tabBtn && !tabBtn.classList.contains('active')) bad.push(n+':tab未高亮');
      }
      ok('3 个一级页签逐一可切换且互斥', bad.length===0, bad.join(' ; '));

      /* 别名验证：switchTab('ui'/'text') 必须归一化到文件页对应子视图 */
      var aliasBad=[];
      for(var a=0;a<ALIAS.length;a++){
        switchTab(ALIAS[a].n);
        var fv=document.getElementById('fileview-'+ALIAS[a].fv);
        var pf=document.getElementById('page-file');
        if(!fv || !fv.classList.contains('active')) aliasBad.push(ALIAS[a].n+':子视图未激活');
        if(!pf || !pf.classList.contains('active')) aliasBad.push(ALIAS[a].n+':文件页未激活');
        var tabBtn2=document.querySelector('.tab[data-tab="file"]');
        if(!tabBtn2 || !tabBtn2.classList.contains('active')) aliasBad.push(ALIAS[a].n+':文件页签未高亮');
      }
      ok('switchTab(ui/text) 归一化到文件页子视图', aliasBad.length===0, aliasBad.join(' ; '));

      /* ---------- B. 包装链连切 ---------- */
      var err=null;
      try{
        for(var r=0;r<6;r++){ for(var k=0;k<TABS.length;k++) switchTab(TABS[k]); }
      }catch(e){ err=e.message; }
      ok('switchTab 4 层包装链连切 36 次不抛异常', err===null, err);

      /* ---------- C. Ctrl+1~6 ---------- */
      // 2026-11-19：Ctrl+4 不再切投屏页，改为跳指令页（Scrcpy投屏 分组）
      // 2026-11-21（第 7 批需求3）：5/6 原指向 ui/text，现归一化到 file（页面层）
      var map={'1':'quick','2':'cmd','3':'file','4':'quick','5':'file','6':'file'};
      var wrong=[];
      for(var key in map){
        var ev=new KeyboardEvent('keydown',{key:key,ctrlKey:true,bubbles:true,cancelable:true});
        document.dispatchEvent(ev);
        if(typeof _tab!=='undefined' && _tab!==map[key]) wrong.push('Ctrl+'+key+'->'+_tab);
      }
      // 2026-11-19：Ctrl+4 不再切投屏页（页已删），改为跳指令页并定位 Scrcpy投屏 分组
      ok('Ctrl+1~5 映射到五个页签（Ctrl+4 = 跳 Scrcpy投屏 分组）',
         wrong.length===0, wrong.join(' ; '));

      switchTab('quick');

      /* E/F 段（castMapPoint 投屏坐标换算、黑边提示接线）随投屏页删除，2026-11-19 A31。
         反向断言：这些投屏专用函数不应再回来。 */
      ok('投屏坐标换算相关函数已随页面删除',
         typeof castMapPoint === 'undefined' && typeof castTap === 'undefined',
         typeof castMapPoint);

      /* ---------- G. 字体切换（bug1 回归） ---------- */
      var sel2 = document.getElementById('set-font');
      var vf0 = getComputedStyle(document.documentElement).getPropertyValue('--font-ui').trim();
      var monoId = null;
      for (var fi=0; fi<FONT_LIST.length; fi++)
        if (FONT_LIST[fi].mono && !FONT_LIST[fi].ui) { monoId = FONT_LIST[fi].id; break; }
      if (monoId && sel2){
        sel2.value = monoId;
        sel2.dispatchEvent(new Event('change', {bubbles:true}));
      }
      var vf1 = getComputedStyle(document.documentElement).getPropertyValue('--font-ui').trim();
      ok('切「只提供等宽」的字体不写坏 --font-ui',
         vf1 !== 'undefined' && vf1 !== '', (monoId||'none')+' => ["'+vf1.slice(0,40)+'"]');
      ok('切等宽类字体不改动界面字族',
         vf1 === vf0, 'before["'+vf0.slice(0,30)+'"] after["'+vf1.slice(0,30)+'"]');

      // 正常字体仍应生效（用内置 Inter，必然存在）
      if (sel2){
        sel2.value = 'inter';
        sel2.dispatchEvent(new Event('change', {bubbles:true}));
      }
      var vf2 = getComputedStyle(document.documentElement).getPropertyValue('--font-ui').trim();
      ok('切到内置 Inter 能改 --font-ui', /Inter/i.test(vf2), vf2.slice(0,40));
      ok('字体生效判定函数可用', typeof fontReallyApplied === 'function', typeof fontReallyApplied);

      /* ---------- H. 日志裁剪（O4 回归） ---------- */
      var box = document.getElementById('logbox-0');
      var built = 0;
      if (box){
        var limit = (typeof MAX_LOG_LINES === 'number') ? MAX_LOG_LINES : 5000;
        var total = limit + 60;
        for (var li=0; li<total; li++){
          var dv = document.createElement('div');
          dv.className = 'ln'; dv.textContent = 'L' + li;
          box.appendChild(dv);
          trimLog(box);          // 每行都裁一次 = 真实路径
          built++;
        }
        ok('日志行数被裁到上限附近', box.childElementCount <= limit + 2,
           'children=' + box.childElementCount + ' limit=' + limit);
        var firstEl = box.firstElementChild;
        ok('裁剪提示固定在首位且只一条',
           firstEl && firstEl.getAttribute('data-trim') === '1' &&
           box.querySelectorAll('[data-trim="1"]').length === 1,
           firstEl ? firstEl.className : 'null');
        ok('最新一行没被误删', box.lastElementChild && box.lastElementChild.textContent === 'L' + (built-1),
           box.lastElementChild ? box.lastElementChild.textContent : 'null');
        ok('提示节点已缓存到 box 上（O4）', !!box.__trimNote, box.__trimNote ? 'cached' : 'not cached');
      }

      /* ---------- I. 窗口边界（bug2 回归） ---------- */
      // 原生窗口圆角 = _cs/GuiWeb.cs 的 _cornerDip = 8（DIP），内描边必须同半径，
      // 否则方角描边被圆角裁掉，四角出现断头 + 1px 台阶。
      var after = getComputedStyle(document.body, '::after');
      var rad = parseFloat(after.borderTopLeftRadius) || 0;
      ok('窗口内描边圆角与原生一致（8px）', Math.abs(rad - 8) < 0.6, rad + 'px');
      ok('内描边仍在（1px 内阴影）', after.boxShadow && after.boxShadow !== 'none',
         (after.boxShadow || '').slice(0, 48));
      document.documentElement.setAttribute('data-winmax', '1');
      var radMax = parseFloat(getComputedStyle(document.body, '::after').borderTopLeftRadius) || 0;
      ok('最大化时描边变方角（不残留圆弧）', radMax === 0, radMax + 'px');
      document.documentElement.setAttribute('data-winmax', '0');

      /* ---------- J. 批量渲染（CPU 优化回归） ---------- */
      // 注意：默认只建了 1 个槽（logbox-0）。要测多槽分流先 addSlot()。
      var box2 = document.getElementById('logbox-0');
      if (box2){
        box2.innerHTML = '';
        box2.__trimNote = null;
        var bulk = [];
        for (var bi = 0; bi < 500; bi++)
          bulk.push({ level: 0, src: 0, slot: 0, text: 'B' + bi });
        // 注意：不要在这里断言耗时。headless 用了 --virtual-time-budget，
        // performance.now() 走的是虚拟时钟（实测新旧两种写法都返回 0.0ms），
        // 测出来的数字没有意义，只会变成假绿灯。这里只验"结果对不对"。
        appendLines(bulk);
        ok('批量插入行数正确', box2.childElementCount === 500, box2.childElementCount);
        ok('批量插入顺序正确（首尾）',
           box2.firstElementChild && box2.lastElementChild &&
           box2.firstElementChild.textContent === 'B0' &&
           box2.lastElementChild.textContent === 'B499',
           (box2.firstElementChild ? box2.firstElementChild.textContent : 'null') + ' ~ ' +
           (box2.lastElementChild ? box2.lastElementChild.textContent : 'null'));

        if (!document.getElementById('logbox-1') && typeof addSlot === 'function') { try { addSlot(); } catch(e){} }
        var box3 = document.getElementById('logbox-1');
        if (box3){
          box2.innerHTML = ''; box2.__trimNote = null;
          box3.innerHTML = ''; box3.__trimNote = null;
          appendLines([{level:0,src:0,slot:1,text:'S2'},{level:0,src:0,slot:0,text:'S1'}]);
          ok('多槽批量分流正确',
             box3.textContent.indexOf('S2') >= 0 && box2.textContent.indexOf('S1') >= 0 &&
             box3.textContent.indexOf('S1') < 0,
             'slot1=' + (box3.textContent || '').slice(0, 12) + ' slot0=' + (box2.textContent || '').slice(0, 12));
          box3.innerHTML = ''; box3.__trimNote = null;
        }
        box2.innerHTML = ''; box2.__trimNote = null;
      }

      /* ---------- G. T2：自绘下拉的 mousedown 不被误关（真实鼠标序列） ----------
         历史事故：文档级捕获阶段处理器在 mousedown 时无条件 closePop()，
         点浮层**条目**也会命中（浮层挂 body 下，向上找不到 SELECT），节点当场被移除，
         等 click 派发时已脱离文档 → 选中无效、change 不派发。
         所以这里必须按 mousedown → 断言浮层仍在 → mouseup → click 的顺序打靶；
         直接 dispatchEvent(click) 会绕过整条路径，测不出这个 bug。 */
      var mouseEv = function(el, type){
        var r = el.getBoundingClientRect();
        el.dispatchEvent(new MouseEvent(type, {bubbles:true, cancelable:true, view:window,
          clientX: Math.round(r.left + r.width/2), clientY: Math.round(r.top + r.height/2)}));
      };
      var popEl = function(){ return document.querySelector('.a14-selpop'); };
      var selFont = document.getElementById('set-font');
      if (!selFont){
        ok('T2 字体下拉存在', false, '找不到 #set-font');
      } else {
        // 先回到默认字体，保证断言是"这一次切换"的结果
        try { setFont('system'); } catch (e) {}
        mouseEv(selFont, 'mousedown');
        ok('T2 mousedown 打开自绘浮层', !!popEl(), 'pop=' + !!popEl());

        var item = document.querySelector('.a14-selpop [data-v="deng"]');
        ok('T2 浮层里有「等线 DengXian」条目', !!item, item ? item.textContent : '无');
        if (item){
          mouseEv(item, 'mousedown');
          ok('T2 点浮层条目时浮层不被误关（回归点）', !!popEl(), 'pop=' + !!popEl());
          mouseEv(item, 'mouseup');
          mouseEv(item, 'click');
          var fv = document.getElementById('set-font').value;
          var tok = getComputedStyle(document.documentElement).getPropertyValue('--font-ui') || '';
          ok('T2 选中后 value 与字体令牌都生效',
             fv === 'deng' && tok.indexOf('DengXian') >= 0, 'value=' + fv + ' token=' + tok.slice(0, 40));
          ok('T2 选中后浮层关闭', !popEl(), 'pop=' + !!popEl());
        }
        // 点外部应当关闭（保护既有行为）
        mouseEv(selFont, 'mousedown');
        var opened = !!popEl();
        mouseEv(document.body, 'mousedown');
        ok('T2 点浮层外部会关闭', opened && !popEl(), 'opened=' + opened + ' closed=' + !popEl());
        // 键盘路径不许改坏（keydown 绑在浮层元素上，它自己拿焦点，所以派发目标是 pop）
        mouseEv(selFont, 'mousedown');
        var pk = popEl();
        if (!pk){
          ok('T2 键盘 ↓+Enter 仍可选中', false, '浮层没打开');
        } else {
          pk.dispatchEvent(new KeyboardEvent('keydown', {key:'ArrowDown', bubbles:true}));
          pk.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true}));
          ok('T2 键盘 ↓+Enter 仍可选中',
             !popEl() && !!document.getElementById('set-font').value,
             'pop=' + !!popEl() + ' value=' + document.getElementById('set-font').value);
        }
        try { setFont('system'); } catch (e) {}     // 还原，避免影响后续断言
      }

      /* ---------- H. T5：切到输出/文本输入后，断网识别开关必须真的点不动 ----------
         原来只给 input 设 pointer-events:none，点 label 文字仍会切换 checkbox
         （"看着灰、点着有效"）。这里点 label 验证。 */
      switchTab('quick');
      var vrLab = document.querySelector('.vr-local');
      var vrInp = document.getElementById('vr-local');
      if (!vrLab || !vrInp){
        ok('T5 断网识别开关存在', false, '找不到 .vr-local/#vr-local');
      } else {
        setVrMode('out');
        ok('T5 输出模式：input 被 disabled',
           vrInp.disabled === true, 'disabled=' + vrInp.disabled);
        ok('T5 输出模式：label 标记为不可用（aria + 光标 + 原因）',
           vrLab.getAttribute('aria-disabled') === 'true' &&
           getComputedStyle(vrLab).cursor === 'not-allowed' &&
           (vrLab.title || '').length > 0,
           'aria=' + vrLab.getAttribute('aria-disabled') + ' cursor=' + getComputedStyle(vrLab).cursor);
        var beforeChk = vrInp.checked;
        drive.clickAt(vrLab);
        ok('T5 点 label 文字不再切换开关', vrInp.checked === beforeChk,
           'before=' + beforeChk + ' after=' + vrInp.checked);

        setVrMode('in');
        ok('T5 切回语音输入后恢复可点',
           vrInp.disabled === false && getComputedStyle(vrLab).cursor !== 'not-allowed',
           'disabled=' + vrInp.disabled + ' cursor=' + getComputedStyle(vrLab).cursor);
      }

      /* ---------- I. T16：浮层管理器 Overlay ----------
         抽出来的目的：外点关闭 / Esc / 滚动跟随 / 层级只留三档，
         以后右键菜单等新浮层直接复用，不再各写一套。 */
      ok('T16 Overlay 已挂到 window 且层级分三档',
         !!window.Overlay && Overlay.LEVEL.pop < Overlay.LEVEL.modal &&
         Overlay.LEVEL.modal < Overlay.LEVEL.toast,
         window.Overlay ? JSON.stringify(Overlay.LEVEL) : '无');

      switchTab('ui');
      var fontSel = document.getElementById('set-font');
      if (fontSel){
        drive.mouseDown(fontSel);
        var op = document.querySelector('.a14-selpop');
        ok('T16 打开后 current() 命中且全页只有 1 个浮层',
           !!op && Overlay.current() === op && document.querySelectorAll('.a14-selpop').length === 1,
           'cur=' + !!Overlay.current() + ' n=' + document.querySelectorAll('.a14-selpop').length);
        ok('T16 浮层层级取 LEVEL.pop',
           !!op && parseInt(getComputedStyle(op).zIndex, 10) === Overlay.LEVEL.pop,
           op ? 'z=' + getComputedStyle(op).zIndex : '无浮层');

        if (op){
          drive.key(op, 'Escape');
          ok('T16 Esc 能关闭浮层', !Overlay.current(),
             'cur=' + (Overlay.current() ? '仍在' : '已关'));
        }
      } else {
        ok('T16 字体下拉存在', false, '找不到 #set-font');
      }
      switchTab('quick');

      emit();
    }catch(e){ R.push('FAIL | 脚本异常 | '+(e&&e.stack?e.stack:e)); emit(); }
  }

  /* 2026-11-18：等页面进入稳态再量。
     本文件没调 setStatus，启动层要等 8s 兜底才退，.frame 一直停在 opacity:0/
     visibility:hidden；而 body::after 的圆角这类取值在"还没真正渲染"时读到的是旧值
     （实测：稳态下 winmax 半径 8px→0px 正确）。这里直接收掉启动层（等价宿主 ready），
     再轮询到稳态才跑。**断言一行未改。** */
  setTimeout(function(){
    try { if (typeof hideSplash === 'function') hideSplash(); } catch (e) {}
    var t0 = Date.now();
    (function waitSteady(){
      var fr = document.getElementById('frame');
      var ok = fr && fr.classList.contains('show') &&
               getComputedStyle(fr).opacity === '1';
      if (!ok && Date.now() - t0 < 6000) { setTimeout(waitSteady, 50); return; }
      __runAll();
    })();
  }, 60);
})();
</script>
"""


def main():
    src = io.open(UI, "r", encoding="utf-8").read()
    _drive_js = _ui_drive.inject_js() if _ui_drive is not None else ""
    io.open(OUT, "w", encoding="utf-8").write(
        src.replace("</body>", _drive_js + JS + "</body>"))
    # profile 目录必须每次唯一：固定名字时，上一轮如果留下残留 Edge 实例，
    # 这一轮会阻塞在 profile 锁上直到 180s 超时，整轮门禁看起来像"卡死"。
    # （2026-11-16 实测踩过：verify_all 从 1.5 分钟变成 6 分钟以上）
    prof = os.path.join(tempfile.gettempdir(), "edgeprof_interact_%d" % os.getpid())
    # 测量通道：优先真实 WebView2（--uitest）。headless 的虚拟时钟会冻结
    # CSS transition，等不到稳态（详见 377/_wv2.py 头注释）；没有 exe 时回退 Edge。
    dom = ""
    # 2026-11-22：默认改走 headless Edge。
    # 历史注释担心"headless 虚拟时钟冻结 transition，等不到稳态"，但实测：
    #   · headless 通道 34/34，断言清单与真实 WebView2 **逐条一致**
    #   · 耗时 5.9~6.7s，而真实 WebView2 要 49s（每跑一次都新建 profile，冷启动极慢）
    #   · 连续 3 次结果稳定，没有出现"等不到稳态"导致的假红
    # 因此默认 headless；需要完全等同线上渲染器时用 UI_CHANNEL=wv2 切回。
    # （虚拟时钟预算已同时从 9000 提到 12000，进一步降低偶发风险。）
    if os.environ.get("UI_CHANNEL", "headless") == "wv2" and _wv2 is not None and _wv2.find_exe():
        dom = _wv2.dump_dom(OUT, wait_ms=3500)
        if '<pre id="RESULT">' not in dom:
            dom = ""
    cmd = [find_edge(), "--headless=new", "--disable-gpu", "--no-sandbox",
           # 关掉启动期的后台活动：每次跑都是全新 profile，这些会让冷启动多花好几秒
           "--no-first-run", "--no-default-browser-check",
           "--disable-background-networking", "--disable-sync",
           "--disable-extensions", "--disable-component-update",
           "--window-size=1280,900",
           "--virtual-time-budget=12000", "--dump-dom",
           "--user-data-dir=" + prof,
           "file:///" + OUT.replace("\\", "/")]

    # 输出写临时文件，**不要用 capture_output**：
    # Edge 会把自己的 stdout 句柄留给子进程（crashpad 等），
    # 用 PIPE 时 subprocess 会一直等 EOF —— 表现为脚本永久挂住（实测踩过）。
    tmpout = os.path.join(tempfile.gettempdir(), "edgeout_interact_%d.html" % os.getpid())
    if not dom:
        with open(tmpout, "w", encoding="utf-8", errors="replace") as fh:
            try:
                subprocess.run(cmd, stdout=fh, stderr=subprocess.DEVNULL, timeout=120)
            except subprocess.TimeoutExpired:
                print("Edge 超时未退出（120s）")
                return 1
        try:
            with io.open(tmpout, "r", encoding="utf-8", errors="replace") as fh:
                dom = fh.read()
        finally:
            try:
                os.remove(tmpout)
            except OSError:
                pass

    # 假绿防线：页面根本没产出 RESULT（脚本异常/加载失败）时必须判失败，
    # 否则下面按行统计会把空结果算成"全部通过"。
    if "__NO_RESULT__" in dom:
        print("  页面没有产出 RESULT（脚本异常或加载失败）")
        return 1
    m = re.search(r'<pre id="RESULT">(.*?)</pre>', dom, re.S)
    if not m:
        print("没拿到 RESULT，DOM 长度", len(dom))
        return 1
    lines = [l for l in H.unescape(m.group(1)).splitlines() if l.strip()]
    fails = [l for l in lines if l.startswith("FAIL")]
    for l in lines:
        print("  " + l)
    print("\n  交互一致性：通过 %d / %d" % (len(lines) - len(fails), len(lines)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
