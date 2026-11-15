# -*- coding: utf-8 -*-
"""读三套主题下关键文本/边界的实际对比度（headless）。只用于自查。"""
import io, os, re, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
PRE = r"""<script>window.chrome={webview:{postMessage:function(){}}};</script>"""
JS = r"""
<script>
setTimeout(function(){
  var st=document.createElement('style');
  st.textContent='*{transition:none!important;animation:none!important;}';
  document.head.appendChild(st);
  var out=[];
  function parse(c){
    var s=String(c).trim();
    var h=s.match(/^#([0-9a-fA-F]{6})$/);
    if(h){var n=parseInt(h[1],16);return {r:(n>>16)&255,g:(n>>8)&255,b:n&255,a:1};}
    var m=s.match(/rgba?\(([^)]+)\)/); if(!m) return null;
    var p=m[1].split(',').map(parseFloat);
    return {r:p[0],g:p[1],b:p[2],a:(p.length>3?p[3]:1)};
  }
  function blend(f,b){ // f over b
    var F=parse(f),B=parse(b); if(!F||!B) return null;
    return {r:F.r*F.a+B.r*(1-F.a), g:F.g*F.a+B.g*(1-F.a), b:F.b*F.a+B.b*(1-F.a)};
  }
  function lum(o){function f(v){v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4);}
    return 0.2126*f(o.r)+0.7152*f(o.g)+0.0722*f(o.b);}
  function ratio(fg,bg){var F=parse(fg),B=parse(bg); if(!F||!B) return 0;
    var c=blend(fg,bg); var L1=lum(c),L2=lum(B);
    if(L1<L2){var t=L1;L1=L2;L2=t;}
    return (L1+0.05)/(L2+0.05);}
  function cs(sel,prop){var el=document.querySelector(sel); if(!el) return '';
    return getComputedStyle(el)[prop]||'';}
  var themes=['dark','light','eye'];
  for(var t=0;t<themes.length;t++){
    applyTheme(themes[t]);
    void document.body.offsetWidth;   // 强制回流，把过渡值刷掉
    var page=cs('body','backgroundColor');
    var tabT=cs('.tab:not(.active)','color'), tabB=cs('.tab:not(.active)','backgroundColor');
    var qn=cs('.qnav-item:not(.active)','color'), qnB=page;
    var cmd=cs('.qcard .qcmd','color'), cardBg=cs('.qcard','backgroundColor');
    var cnt=cs('.qnav-item .qcnt','color');
    var name=cs('.qcard .qname','color');
    var bgInfo = 'bg: body='+cs('body','backgroundColor')
      +' frame='+cs('.frame','backgroundColor')
      +' quick='+((document.getElementById('page-quick')||{}).id ? getComputedStyle(document.getElementById('page-quick')).backgroundColor : '-')
      +' qbody='+cs('.quick-body','backgroundColor')
      +' grid='+cs('#quick-grid','backgroundColor')
      +' nav='+cs('#quick-nav','backgroundColor')
      +' card='+cs('.qcard','backgroundColor')
      +' page='+cs('.page.active','backgroundColor')
      +' wrap='+cs('.quick-wrap','backgroundColor');
    out.push(bgInfo);
    out.push(themes[t]
      +' | 卡片名 '+ratio(name,cardBg).toFixed(2)
      +' | 卡片说明 '+ratio(cmd,cardBg).toFixed(2)
      +' | 页签未选 '+ratio(tabT,tabB).toFixed(2)
      +' | 导航未选 '+ratio(qn,qnB).toFixed(2)
      +' | 导航计数 '+ratio(cnt,qnB).toFixed(2)
      +' | 卡片边框 '+ratio(cs('.qcard','borderTopColor'),cardBg).toFixed(2)
      +' | 页面底 '+page
      +' || border='+cs('.qcard','borderTopColor')
      +' faint='+cs('.qcard .qcmd','color')
      +' tokborder='+getComputedStyle(document.documentElement).getPropertyValue('--border').trim()
      +' tokfaint='+getComputedStyle(document.documentElement).getPropertyValue('--text-faint').trim());
  }
  var pre=document.createElement('pre'); pre.id='RESULT'; pre.textContent=out.join('\n');
  document.body.appendChild(pre);
},300);
</script>"""

src = io.open(UI, encoding="utf-8").read().replace("<head>", "<head>\n" + PRE, 1)
page = src.replace("</body>", JS + "</body>", 1)
tmp = os.path.join(tempfile.gettempdir(), "probe_c.html")
io.open(tmp, "w", encoding="utf-8").write(page)
for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
    base = os.environ.get(env)
    if base:
        exe = os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")
        if os.path.exists(exe):
            break
r = subprocess.run([exe, "--headless=new", "--disable-gpu", "--window-size=1280,820",
                    "--virtual-time-budget=8000", "--dump-dom",
                    "--user-data-dir=" + os.path.join(tempfile.gettempdir(), "edgeprof_c"),
                    "file:///" + tmp.replace("\\", "/")],
                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
m = re.search(r'<pre id="RESULT">(.*?)</pre>', r.stdout or "", re.S)
import html as H
print(H.unescape(m.group(1)) if m else "no result")
