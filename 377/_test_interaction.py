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

  var TABS=['quick','cmd','file','cast','ui','text'];

  setTimeout(function(){
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
      ok('6 个页签逐一可切换且互斥', bad.length===0, bad.join(' ; '));

      /* ---------- B. 包装链连切 ---------- */
      var err=null;
      try{
        for(var r=0;r<6;r++){ for(var k=0;k<TABS.length;k++) switchTab(TABS[k]); }
      }catch(e){ err=e.message; }
      ok('switchTab 4 层包装链连切 36 次不抛异常', err===null, err);

      /* ---------- C. Ctrl+1~6 ---------- */
      var map={'1':'quick','2':'cmd','3':'file','4':'cast','5':'ui','6':'text'};
      var wrong=[];
      for(var key in map){
        var ev=new KeyboardEvent('keydown',{key:key,ctrlKey:true,bubbles:true,cancelable:true});
        document.dispatchEvent(ev);
        if(typeof _tab!=='undefined' && _tab!==map[key]) wrong.push('Ctrl+'+key+'->'+_tab);
      }
      ok('Ctrl+1~6 映射到六个页签', wrong.length===0, wrong.join(' ; '));

      /* ---------- D. 投屏轮询启停 ---------- */
      switchTab('cast');
      var hasOn = (typeof _cast!=='undefined') && _cast.timer;
      switchTab('quick');
      var hasOff = (typeof _cast!=='undefined') && !_cast.timer;
      ok('进投屏页启动状态轮询', !!hasOn, hasOn?'':'timer 未创建');
      ok('离开投屏页停掉轮询（I4）', !!hasOff, hasOff?'':'timer 未清理');
      switchTab('cast');
      var hasAgain = (typeof _cast!=='undefined') && !!_cast.timer;
      ok('再次进入投屏页轮询可重启', !!hasAgain, hasAgain?'':'重启失败');
      switchTab('quick');

      /* ---------- E. castMapPoint 纯函数 ---------- */
      var rect={left:100,top:50,width:400,height:300};
      // 图 800x600 放进 400x300：正好等比，无黑边
      var c=castMapPoint(300,200,rect,800,600,800,600);
      ok('等比铺满：中心点映射到设备中心',
         c && Math.abs(c.x-400)<=1 && Math.abs(c.y-300)<=1, c?c.x+','+c.y:null);
      // 图 800x400 放进 400x300：上下留黑边（dh=200, oy=50+50=100）
      var lb=castMapPoint(300,60,rect,800,400,800,400);
      ok('黑边区域返回 null（不误发 tap）', lb===null, lb?lb.x+','+lb.y:'');
      var inb=castMapPoint(300,250,rect,800,400,800,400);
      ok('黑边内画面区域可映射', inb && inb.x>=0 && inb.y>=0, inb?inb.x+','+inb.y:null);
      // 设备分辨率与图片分辨率不同：按设备分辨率换算（同样取画面中心）
      var sc=castMapPoint(300,200,rect,800,600,1920,1080);
      ok('设备分辨率 != 图片分辨率时按设备换算',
         sc && Math.abs(sc.x-960)<=2 && Math.abs(sc.y-540)<=2, sc?sc.x+','+sc.y:null);
      // 右边界：clientX=500 正好是 rect 右边（px=1），允许等于 devW（边界含端点）
      var edge=castMapPoint(500,200,rect,800,600,1920,1080);
      ok('右边界点映射到 devW（含端点，不越界）',
         edge && edge.x===1920, edge?edge.x:null);
      ok('退化参数（rect 为空）返回 null', castMapPoint(0,0,null,800,600,800,600)===null);

      /* ---------- F. I5 接线 ---------- */
      ok('黑边提示节流数组已接线',
         typeof _castTapEdgeNote!=='undefined' && _castTapEdgeNote.length===6,
         typeof _castTapEdgeNote);
      ok('castTap 内已调用 toast 提示黑边',
         /castTapEdgeNote\[i\]/.test(document.documentElement.innerHTML) ||
         /_castTapEdgeNote/.test(window.castTap ? window.castTap.toString() : ''),
         '未找到接线');

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

      emit();
    }catch(e){ R.push('FAIL | 脚本异常 | '+(e&&e.stack?e.stack:e)); emit(); }
  }, 500);
})();
</script>
"""


def main():
    src = io.open(UI, "r", encoding="utf-8").read()
    io.open(OUT, "w", encoding="utf-8").write(src.replace("</body>", JS + "</body>"))
    # profile 目录必须每次唯一：固定名字时，上一轮如果留下残留 Edge 实例，
    # 这一轮会阻塞在 profile 锁上直到 180s 超时，整轮门禁看起来像"卡死"。
    # （2026-11-16 实测踩过：verify_all 从 1.5 分钟变成 6 分钟以上）
    prof = os.path.join(tempfile.gettempdir(), "edgeprof_interact_%d" % os.getpid())
    cmd = [find_edge(), "--headless=new", "--disable-gpu", "--no-sandbox",
           # 关掉启动期的后台活动：每次跑都是全新 profile，这些会让冷启动多花好几秒
           "--no-first-run", "--no-default-browser-check",
           "--disable-background-networking", "--disable-sync",
           "--disable-extensions", "--disable-component-update",
           "--window-size=1280,900",
           "--virtual-time-budget=9000", "--dump-dom",
           "--user-data-dir=" + prof,
           "file:///" + OUT.replace("\\", "/")]

    # 输出写临时文件，**不要用 capture_output**：
    # Edge 会把自己的 stdout 句柄留给子进程（crashpad 等），
    # 用 PIPE 时 subprocess 会一直等 EOF —— 表现为脚本永久挂住（实测踩过）。
    tmpout = os.path.join(tempfile.gettempdir(), "edgeout_interact_%d.html" % os.getpid())
    with open(tmpout, "w", encoding="utf-8", errors="replace") as fh:
        try:
            subprocess.run(cmd, stdout=fh, stderr=subprocess.DEVNULL, timeout=120)
        except subprocess.TimeoutExpired:
            print("Edge 超时未退出（120s）")
            return 1
    dom = ""
    try:
        with io.open(tmpout, "r", encoding="utf-8", errors="replace") as fh:
            dom = fh.read()
    finally:
        try:
            os.remove(tmpout)
        except OSError:
            pass

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
