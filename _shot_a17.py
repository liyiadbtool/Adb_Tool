# -*- coding: utf-8 -*-
"""给 A17 这批改动拍图（headless Edge），只作人工核对用，不参与门禁。

重点核对：
  1. 直角 → 圆角：左侧分组侧栏 / 终端页整块 / 底部输入行（截图红框那三处）；
  2. 浅色主题下的窗口边界（1px 实边 + 内高光 + 内阴影）；
  3. 新图标（黑白灰 + 黑底）在标题栏里的观感；
  4. 启动层：高斯模糊渐变背景 + 图标跟随强调色。

用法：python _shot_a17.py
产物：docs/shots/a17-*.png
"""
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


# (文件名, 主题, 强调色, 动作)
CASES = [
    ("a17-light-quick", "light", "blue", "quick"),
    ("a17-light-cmd", "light", "blue", "cmd"),
    ("a17-dark-quick", "dark", "blue", "quick"),
    ("a17-titlebar-mark", "light", "graphite", "quick"),
    ("a17-cast-embed", "dark", "teal", "cast"),
    ("a17-splash-accent", "dark", "purple", "splash"),
]

BOOT = u"""
<script>
setTimeout(function(){
  try{
    /* 关掉过渡与动画：否则淡入没走完就截图，整张图会发灰 */
    var st=document.createElement('style');
    st.textContent='*,*::before,*::after{transition:none!important;animation:none!important;}';
    document.head.appendChild(st);
    void document.body.offsetWidth;

    applyTheme('%(theme)s');
    if (typeof applyAccent === 'function') applyAccent('%(accent)s');

    var what = '%(what)s';

    if (what === 'splash'){
      /* 启动层：背景要保持渐变，图标要跟着强调色 —— 所以这里不隐藏 splash */
      var sp0=document.getElementById('splash');
      if (sp0){ sp0.classList.remove('hide'); sp0.classList.remove('gone'); }
      if (typeof hideSplash === 'function') hideSplash = function(){};
      var fr0=document.getElementById('frame'); if(fr0) fr0.classList.remove('show');
      document.title = 'splash';
      return;
    }

    var fr=document.getElementById('frame'); if(fr) fr.classList.add('show');
    var sp=document.getElementById('splash'); if(sp){ sp.classList.add('hide'); sp.classList.add('gone'); }

    if (what === 'cmd'){
      switchTab('cmd');
    } else if (what === 'cast'){
      switchTab('cast');
      /* 内嵌态：把网格与缩略条藏掉，只留 #cast-embed 这个占位框 */
      var em=document.getElementById('cast-embed');
      if (em) em.style.display = '';
      var g=document.getElementById('cast-grid'); if(g) g.style.display='none';
      var s=document.getElementById('cast-strip'); if(s) s.style.display='none';
      var h=document.getElementById('ce-hint');
      if (h) h.textContent = '画面已接管 · 鼠标点击 / 拖动直接作用在车机上';
      var b=document.getElementById('cm-embed'); if(b) b.classList.add('on');
      var b2=document.getElementById('cm-builtin'); if(b2) b2.classList.remove('on');
    } else {
      switchTab('quick');
      switchQuickGroup(0);
    }

    void document.body.offsetWidth;
    document.title = 'ok ' + what;
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
        tmp = os.path.join(tempfile.gettempdir(), "a17shot.html")
        io.open(tmp, "w", encoding="utf-8").write(page)
        png = os.path.join(OUTDIR, name + ".png")
        cmd = [find_edge(), "--headless=new", "--disable-gpu", "--hide-scrollbars",
               "--window-size=1280,820", "--virtual-time-budget=5000",
               "--screenshot=" + png,
               "--user-data-dir=" + os.path.join(tempfile.gettempdir(), "edgeprof_shot17"),
               "file:///" + tmp.replace("\\", "/")]
        subprocess.run(cmd, capture_output=True, timeout=180)
        exists = os.path.exists(png)
        ok += 1 if exists else 0
        print(("  OK   " if exists else "  FAIL ") + png)
    print("\n  %d / %d 张" % (ok, len(CASES)))
    return 0 if ok == len(CASES) else 1


if __name__ == "__main__":
    sys.exit(main())
