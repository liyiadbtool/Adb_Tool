# -*- coding: utf-8 -*-
"""16 色强调色的 DOM 实测门禁（无头 Edge）。

验证：16 色令牌互异 / 三套明暗下切色不改背景 / 按钮·页签·滑块跟随 /
色板交互可用 / 非法值回退。运行：python _check_accent_dom.py
"""
import html
import io
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
TEST = os.path.join(tempfile.gettempdir(), "adb_accent_check.html")


def find_edge():
    for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            p = os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")
            if os.path.exists(p):
                return p
    for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if os.path.exists(p):
            return p
    return "msedge.exe"


JS = r"""
<script>
(function(){
  var R=[];
  function ok(n,c,x){ R.push((c?'PASS':'FAIL')+' | '+n+(c?'':' | '+(x===undefined?'':x))); }
  function g(sel,p){ var e=document.querySelector(sel); if(!e) return '<MISSING '+sel+'>';
    return getComputedStyle(e)[p]; }
  var kill=document.createElement('style');
  kill.textContent='*,*::before,*::after{transition:none !important;animation:none !important;}';
  document.head.appendChild(kill);
  var names=['blue','cyan','teal','mint','green','yellow','orange','red','pink','purple','indigo','brown','graphite','purewhite','eyewhite','glasswhite'];
  function bgSnapshot(){
    return [g('body','backgroundColor'),g('.frame','backgroundColor'),
            g('.topbar','backgroundColor'),g('body','color')].join('|');
  }
  document.documentElement.dataset.theme='dark';
  var vals={};
  names.forEach(function(n){
    applyAccent(n);
    vals[n]=getComputedStyle(document.documentElement).getPropertyValue('--accent').trim();
  });
  ok('16 色令牌值互不相同', (function(){var s={};for(var k in vals)s[vals[k]]=1;
     return Object.keys(vals).length===16 && Object.keys(s).length>=15;})(), JSON.stringify(vals));
  ['dark','light','eye'].forEach(function(th){
    document.documentElement.dataset.theme=th;
    applyAccent('blue'); var before=bgSnapshot();
    applyAccent('pink'); var after=bgSnapshot();
    ok(th+' 切色前后背景/文字不变', before===after, before+' -> '+after);
  });
  document.documentElement.dataset.theme='dark';
  applyAccent('blue');
  var b1=g('.tab.active','backgroundColor'), b2=g('.btn.primary','backgroundColor'),
      b3=g('input[type=range]','accentColor');
  applyAccent('red');
  var r1=g('.tab.active','backgroundColor'), r2=g('.btn.primary','backgroundColor'),
      r3=g('input[type=range]','accentColor');
  ok('选中页签跟随 accent', b1!==r1, b1+' -> '+r1);
  ok('主按钮填充跟随 accent', b2!==r2, b2+' -> '+r2);
  ok('滑块 accent-color 跟随', b3!==r3, b3+' -> '+r3);
  ok('accent-soft 也跟随',
     getComputedStyle(document.documentElement).getPropertyValue('--accent-soft').trim().indexOf('255, 69, 58')>=0 ||
     getComputedStyle(document.documentElement).getPropertyValue('--accent-soft').trim().indexOf('255,69,58')>=0);
  // 2026-11-15 第二轮：色板从顶栏浮层搬进设置抽屉（需求 5），
  // 交互随之变成「打开设置 → 直接点色点」，不再有弹出/关闭动作。
  openSettings();
  var dots=document.querySelectorAll('.set-panel .accent-dot');
  ok('设置里 16 色色板都在', dots.length===16, String(dots.length));
  var dot=document.querySelector('.set-panel .accent-dot[data-accent="green"]');
  ok('色点可见（在设置面板内）', !!dot && getComputedStyle(dot).display!=='none');
  accentPopClick({target:dot,stopPropagation:function(){}});
  ok('点色点后 data-accent=green',
     document.documentElement.getAttribute('data-accent')==='green');
  ok('点色点后选中态打勾', dot.classList.contains('sel'));
  closeSettings();
  applyAccent('nope');
  ok('非法色回退 blue', document.documentElement.getAttribute('data-accent')==='blue');
  var pre=document.createElement('pre');pre.id='RESULT';pre.textContent=R.join('\n');
  document.body.appendChild(pre);
})();
</script>
"""


def main():
    src = io.open(UI, "r", encoding="utf-8").read()
    io.open(TEST, "w", encoding="utf-8").write(src.replace("</body>", JS + "</body>"))
    cmd = [find_edge(), "--headless=new", "--disable-gpu", "--window-size=1100,760",
           "--virtual-time-budget=6000", "--dump-dom",
           "--user-data-dir=" + os.path.join(tempfile.gettempdir(), "edgeprof_accent_check"),
           "file:///" + TEST.replace("\\", "/")]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=120)
    m = re.search(r'<pre id="RESULT">(.*?)</pre>', r.stdout or "", re.S)
    if not m:
        print("没拿到 RESULT，DOM 长度", len(r.stdout or ""))
        return 1
    out = html.unescape(m.group(1))
    print(out)
    fails = [l for l in out.splitlines() if l.startswith("FAIL")]
    print("16 色强调色 DOM 实测：通过 %d / %d" % (len(out.splitlines()) - len(fails), len(out.splitlines())))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
