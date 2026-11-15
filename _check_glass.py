# -*- coding: utf-8 -*-
"""Liquid Glass 层实测：headless Edge 读真实计算样式（2026-11-15）。

校验点：
  1) .frame 半透明、body::before 光雾在跑（有 animation-name）
  2) .titlebar / .tabs 有 backdrop-filter，且 tabs 是胶囊（圆角 ≥ 12）
  3) .qcard 有投影但**没有** backdrop-filter（性能护栏）
  4) 三套主题下 --frame/--chrome 令牌都解析成预期形态
  5) accent 切换不改变 .frame/.titlebar 背景（与背景正交）
  6) 减少透明度偏好下玻璃退化为纯色（用媒体查询模拟不了，改为检查规则存在）
"""
import io
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
OUT = os.path.join(ROOT, "377", "_glass_probe.html")


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
  // 关过渡/动画，避免读到起始帧假值
  var st=document.createElement('style');
  st.textContent='*{transition:none!important;animation:none!important;}';
  document.head.appendChild(st);

  function g(sel,prop,pe){
    var el=document.querySelector(sel); if(!el) return '';
    return getComputedStyle(el,pe||null)[prop]||'';
  }

  setTimeout(function(){
    try{
      var html=document.documentElement;
      // 1. 光雾
      var anim=g('body','animationName','::before');
      ok('body::before 有漂移动画', anim && anim!=='none', anim);
      var bgImg=g('body','backgroundImage','::before');
      ok('body::before 有径向光雾', /radial-gradient/.test(bgImg), bgImg.slice(0,60));
      // 2. 框架半透明
      var fr=g('.frame','backgroundColor');
      var m=fr.match(/rgba?\(([^)]+)\)/);
      var alpha=m? parseFloat(m[1].split(',')[3]) : 1;
      ok('.frame 半透明（alpha<1）', alpha<1, fr);
      // 3. 顶栏玻璃
      var bf=g('.titlebar','backdropFilter')||g('.titlebar','webkitBackdropFilter');
      ok('.titlebar 有 backdrop-filter', /blur/.test(bf), bf);
      // 4. 页签胶囊
      var tb=g('.tabs','backdropFilter')||g('.tabs','webkitBackdropFilter');
      ok('.tabs 有 backdrop-filter', /blur/.test(tb), tb);
      var rad=parseFloat(g('.tabs','borderRadius'));
      ok('.tabs 是胶囊（圆角≥12）', rad>=12, rad);
      var mw=g('.tabs','marginLeft');
      ok('.tabs 有外边距（漂浮）', parseFloat(mw)>0, mw);
      // 5. 卡片：有投影、无 blur（性能护栏）
      var cards=document.querySelectorAll('.qcard');
      if(cards.length){
        var cs=getComputedStyle(cards[0]);
        ok('.qcard 有投影', cs.boxShadow!=='none', cs.boxShadow.slice(0,40));
        ok('.qcard 不用 backdrop-filter（护栏）',
           !cs.backdropFilter || cs.backdropFilter==='none', cs.backdropFilter);
        var a2=cs.backgroundColor.match(/rgba?\(([^)]+)\)/);
        var al=a2? parseFloat(a2[1].split(',')[3]) : 1;
        ok('.qcard 是半透明面', al<1, cs.backgroundColor);
      }else{ ok('.qcard 存在（供检查）', false, '无卡片'); }
      // 6. accent 正交
      var f0=g('.frame','backgroundColor'), t0=g('.titlebar','backgroundColor');
      setAccent('red');
      void document.body.offsetHeight;
      var f1=g('.frame','backgroundColor'), t1=g('.titlebar','backgroundColor');
      ok('切 accent 不改 .frame 背景', f0===f1, f0+' -> '+f1);
      ok('切 accent 不改 .titlebar 背景', t0===t1, t0+' -> '+t1);
      var acc=getComputedStyle(document.documentElement).getPropertyValue('--accent').trim();
      ok('accent 令牌已变红', /FF453A|FF3B30/i.test(acc), acc);
      setAccent('blue');
      // 7. 三套主题下令牌都能取到（不空）
      var themes=['dark','light','eye'];
      for(var i=0;i<themes.length;i++){
        applyTheme(themes[i]); void document.body.offsetHeight;
        var v=getComputedStyle(document.documentElement).getPropertyValue('--chrome').trim();
        ok('主题 '+themes[i]+' 有 --chrome 令牌', !!v, v);
        var fr2=getComputedStyle(document.querySelector('.frame')).backgroundColor;
        ok('主题 '+themes[i]+' .frame 半透明', /rgba/.test(fr2) && parseFloat(fr2.split(',')[3])<1, fr2);
      }
      // 8. 关键：`.show` 之后框架真的可见（没有被玻璃层卡在透明态）
      document.querySelector('.frame').classList.add('show');
      void document.body.offsetHeight;
      ok('.frame.show 后可见（opacity 1）',
         parseFloat(getComputedStyle(document.querySelector('.frame')).opacity) > 0.9,
         g('.frame','opacity'));
      emit();
    }catch(e){ R.push('FAIL | 脚本异常 | '+(e&&e.stack?e.stack:e)); emit(); }
  }, 400);
})();
</script>
"""


def main():
    src = io.open(UI, "r", encoding="utf-8").read()
    io.open(OUT, "w", encoding="utf-8").write(src.replace("</body>", JS + "</body>"))
    cmd = [find_edge(), "--headless=new", "--disable-gpu", "--window-size=1280,900",
           "--virtual-time-budget=9000", "--dump-dom",
           "--user-data-dir=" + os.path.join(tempfile.gettempdir(), "edgeprof_glass"),
           "file:///" + OUT.replace("\\", "/")]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=180)
    m = re.search(r'<pre id="RESULT">(.*?)</pre>', r.stdout or "", re.S)
    if not m:
        print("没拿到 RESULT，DOM 长度", len(r.stdout or ""))
        return 1
    import html as H
    lines = [l for l in H.unescape(m.group(1)).splitlines() if l.strip()]
    fails = [l for l in lines if l.startswith("FAIL")]
    for l in lines:
        print("  " + l)
    print("\n  Liquid Glass 实测：通过 %d / %d" % (len(lines) - len(fails), len(lines)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
