# -*- coding: utf-8 -*-
"""给 A14 的界面改动拍几张图（headless Edge），用于人工核对对比度与图标。
不参与门禁，只是自查工具：python _shot_a14.py"""
import io
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
OUTDIR = os.path.join(ROOT, "docs", "shots")
PRE = r"""<script>
window.chrome = { webview: { postMessage: function(){} } };
window.confirm = function(){ return true; };
window.prompt = function(){ return 'DengXian'; };
</script>"""


def find_edge():
    for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            p = os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")
            if os.path.exists(p):
                return p
    return "msedge.exe"


CASES = [
    ("a14-dark-wsvc", "dark", "quick"),
    ("a14-light-wsvc", "light", "quick"),
    ("a14-eye-wsvc", "eye", "quick"),
    ("a14-dark-settings", "dark", "settings"),
    ("a14-light-settings", "light", "settings"),
]


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    src = io.open(UI, encoding="utf-8").read().replace("<head>", "<head>\n" + PRE, 1)
    for name, theme, what in CASES:
        boot = u"""
<script>
setTimeout(function(){
  try{
    /* 关掉所有过渡与动画：否则 .frame 的淡入还没走完就截图，整张图会发灰 */
    var st=document.createElement('style');
    st.textContent='*,*::before,*::after{transition:none!important;animation:none!important;}';
    document.head.appendChild(st);
    void document.body.offsetWidth;
    applyTheme('%s');
    if (typeof applyAccent === 'function') applyAccent('blue');
    var i=-1;
    for(var k=0;k<quickGroups.length;k++) if(quickGroups[k].name==='网联服务') i=k;
    if(i>=0){ switchQuickGroup(i); }
    switchTab('quick');
    if('%s'==='settings'){ openSettings(); }
    var fr=document.getElementById('frame'); if(fr) fr.classList.add('show');
    var sp=document.getElementById('splash'); if(sp){ sp.classList.add('hide'); sp.classList.add('gone'); }
    void document.body.offsetWidth;
  }catch(e){ document.title='ERR '+e.message; }
}, 400);
</script>""" % (theme, what)
        page = src.replace("</body>", boot + "</body>", 1)
        tmp = os.path.join(tempfile.gettempdir(), "a14shot.html")
        io.open(tmp, "w", encoding="utf-8").write(page)
        png = os.path.join(OUTDIR, name + ".png")
        cmd = [find_edge(), "--headless=new", "--disable-gpu", "--hide-scrollbars",
               "--window-size=1280,820", "--virtual-time-budget=4000",
               "--screenshot=" + png,
               "--user-data-dir=" + os.path.join(tempfile.gettempdir(), "edgeprof_shot"),
               "file:///" + tmp.replace("\\", "/")]
        subprocess.run(cmd, capture_output=True, timeout=180)
        print("  " + ("OK  " if os.path.exists(png) else "FAIL") + " " + png)
    return 0


if __name__ == "__main__":
    sys.exit(main())
