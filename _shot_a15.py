# -*- coding: utf-8 -*-
"""给 A15 这批改动拍图（headless Edge），只作人工核对用，不参与门禁。

用途：确认「13 色色板 / 投屏六条 / 日志等级浮层 / 设备管理浮层 / OLED / 护眼深」
       这六处在真实渲染下的样子对不对（对比度、边界、截断）。
用法：python _shot_a15.py
产物：docs/shots/a15-*.png
"""
import io
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
OUTDIR = os.path.join(ROOT, "docs", "shots")

# 让页面以为自己在 WebView2 里：否则 postMessage 那条桥会抛异常，初始化半途而废
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


# (文件名, 主题, 强调色, 要做的事)
CASES = [
    ("a15-dark-cast", "dark", "blue", "cast"),
    ("a15-light-cast", "light", "blue", "cast"),
    ("a15-dark-settings", "dark", "purple", "settings"),
    ("a15-light-settings", "light", "green", "settings"),
    ("a15-dark-oled", "dark", "teal", "oled"),
    ("a15-eye-deep", "eye", "orange", "eyedeep"),
]

BOOT = u"""
<script>
setTimeout(function(){
  try{
    /* 关掉过渡与动画：.frame 的淡入没走完就截图，整张图会发灰 */
    var st=document.createElement('style');
    st.textContent='*,*::before,*::after{transition:none!important;animation:none!important;}';
    document.head.appendChild(st);
    void document.body.offsetWidth;

    applyTheme('%(theme)s');
    if (typeof applyAccent === 'function') applyAccent('%(accent)s');

    var what = '%(what)s';
    if (what === 'oled'){ document.documentElement.setAttribute('data-oled','1'); }
    if (what === 'eyedeep'){ document.documentElement.setAttribute('data-eyelevel','deep'); }

    /* 投屏那组：找 name 以「投屏」开头的分组 */
    var gi=-1;
    for (var k=0;k<quickGroups.length;k++){
      if (quickGroups[k].name.indexOf('投屏') === 0) gi=k;
    }
    if (what === 'cast' && gi >= 0) switchQuickGroup(gi);
    switchTab('quick');

    if (what === 'settings'){ openSettings(); }
    /* 徽章平时要等设备连上才显示；截图没有真机，先手动放出来再开浮层 */
    if (what === 'logpop' || what === 'devpop'){
      var lb=document.getElementById('log-pill'); if(lb) lb.style.display='';
      var db=document.getElementById('dev-badge'); if(db) db.style.display='';
    }
    if (what === 'logpop' && typeof openLogPop === 'function') openLogPop();
    if (what === 'devpop' && typeof openDevPop === 'function') openDevPop();
    if (what === 'oled' && gi >= 0) switchQuickGroup(gi);

    var fr=document.getElementById('frame'); if(fr) fr.classList.add('show');
    var sp=document.getElementById('splash'); if(sp){ sp.classList.add('hide'); sp.classList.add('gone'); }
    void document.body.offsetWidth;
  }catch(e){ document.title='ERR '+e.message; }
}, 500);
</script>"""


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    src = io.open(UI, encoding="utf-8").read().replace("<head>", "<head>\n" + PRE, 1)
    ok = 0
    for name, theme, accent, what in CASES:
        boot = BOOT % {"theme": theme, "accent": accent, "what": what}
        page = src.replace("</body>", boot + "</body>", 1)
        tmp = os.path.join(tempfile.gettempdir(), "a15shot.html")
        io.open(tmp, "w", encoding="utf-8").write(page)
        png = os.path.join(OUTDIR, name + ".png")
        cmd = [find_edge(), "--headless=new", "--disable-gpu", "--hide-scrollbars",
               "--window-size=1280,820", "--virtual-time-budget=4500",
               "--screenshot=" + png,
               "--user-data-dir=" + os.path.join(tempfile.gettempdir(), "edgeprof_shot15"),
               "file:///" + tmp.replace("\\", "/")]
        subprocess.run(cmd, capture_output=True, timeout=180)
        exists = os.path.exists(png)
        ok += 1 if exists else 0
        print(("  OK   " if exists else "  FAIL ") + png)
    print("\n  %d / %d 张" % (ok, len(CASES)))
    return 0 if ok == len(CASES) else 1


if __name__ == "__main__":
    sys.exit(main())
