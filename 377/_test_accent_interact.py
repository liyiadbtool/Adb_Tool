# -*- coding: utf-8 -*-
"""运行时验证：按钮交互态（选中/激活/hover/焦点）是否跟随强调色 var(--accent)。

验证点（本轮 A20 修改）：
  1. .qnav-item.active       背景/文字 = accent 系
  2. .set-seg button.on       背景 = accent, 文字 = on-accent
  3. .tx-tab.on               背景 = accent-soft, 文字 = accent
  4. .theme-card.on           背景 = accent, 文字 = on-accent, 无 ::before/::after 重叠
  5. .tab.active              背景 = accent, 文字 = on-accent（回归，不应退化）
"""
import os, re, subprocess, time, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, 'adb_log_gui', 'webview2', 'ui.html')
SRC = open(UI, encoding='utf-8').read()

JS = r'''
<style>*,*::before,*::after{transition:none!important;animation:none!important;}</style>
<script>
(function(){
function rgb(v){ if(!v) return ''; var m=v.match(/[\d.]+/g); if(!m||m.length<3) return v; return [m[0],m[1],m[2]].join(','); }
function run(){
  var out=[];
  var root=document.documentElement;
  root.setAttribute('data-theme','dark');
  root.setAttribute('data-accent','blue');
  var cs=getComputedStyle(root);
  out.push('--accent='+cs.getPropertyValue('--accent').trim());
  out.push('--on-accent='+cs.getPropertyValue('--on-accent').trim());

  function probe(sel, what){
    var el=document.querySelector(sel);
    if(!el){ out.push(what+'=NO_ELEMENT'); return; }
    var s=getComputedStyle(el);
    out.push(what+'.bg='+s.backgroundColor);
    out.push(what+'.color='+s.color);
    out.push(what+'.border='+s.borderColor);
  }

  // 1. qnav-item.active
  var q=document.querySelector('.qnav-item.active');
  if(q){ var qs=getComputedStyle(q); out.push('qnav.active.bg='+qs.backgroundColor); out.push('qnav.active.color='+qs.color); }
  else out.push('qnav.active=NO_ELEMENT');

  // 2. set-seg button.on
  var seg=document.querySelector('.set-seg button.on');
  if(seg){ var ss=getComputedStyle(seg); out.push('setseg.on.bg='+ss.backgroundColor); out.push('setseg.on.color='+ss.color); }
  else out.push('setseg.on=NO_ELEMENT');

  // 3. tx-tab.on
  var tx=document.querySelector('.tx-tab.on');
  if(tx){ var ts=getComputedStyle(tx); out.push('txtab.on.bg='+ts.backgroundColor); out.push('txtab.on.color='+ts.color); }
  else out.push('txtab.on=NO_ELEMENT');

  // 4. theme-card.on
  var tc=document.querySelector('.theme-card.on');
  if(tc){ var tcs=getComputedStyle(tc); out.push('themecard.on.bg='+tcs.backgroundColor); out.push('themecard.on.color='+tcs.color);
    var be=getComputedStyle(tc,'::before'); var af=getComputedStyle(tc,'::after');
    out.push('themecard.before.content='+JSON.stringify(be.content));
    out.push('themecard.after.content='+JSON.stringify(af.content));
  } else out.push('themecard.on=NO_ELEMENT');

  // 5. tab.active
  probe('.tab.active','tab.active');

  var pre=document.createElement('pre'); pre.id='R'; pre.textContent=out.join('\n');
  document.body.appendChild(pre);
}
setTimeout(run, 400);
})();
</script>
'''

def run():
    test = SRC.replace('</body>', JS + '</body>')
    tp = os.path.join(ROOT, '377', '_t_accent_interact.html')
    open(tp, 'w', encoding='utf-8').write(test)
    prof = os.path.join(os.environ.get('TEMP', ROOT), 'edge_accent_interact_%d' % int(time.time()))
    EDGE = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
    if not os.path.exists(EDGE):
        EDGE = r'C:\Program Files\Microsoft\Edge\Application\msedge.exe'
    cmd = [EDGE, '--headless=new', '--disable-gpu', '--window-size=1200,800',
           '--virtual-time-budget=6000', '--dump-dom', '--user-data-dir=' + prof,
           'file:///' + tp.replace('\\', '/')]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
    m = re.search(r'<pre id="R">(.*?)</pre>', r.stdout or '', re.S)
    return m.group(1) if m else ('NOT FOUND\n' + (r.stdout or '')[-500:] + '\nSTDERR:' + (r.stderr or '')[-500:])

if __name__ == '__main__':
    print(run())
