# -*- coding: utf-8 -*-
"""给 A16 这批改动拍图（headless Edge），只作人工核对用，不参与门禁。

重点核对三件事（都是用户截图里的真实故障）：
  1. 日志等级浮层 / 设备管理浮层不再被 tab 栏或祖先 overflow 裁掉；
  2. 两个浮层互斥：先开日志再开设备，只应剩设备；
  3. 浮层打开后 hover 提示不再叠在下面。

用法：python _shot_a16.py
产物：docs/shots/a16-*.png
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
    ("a16-light-logpop", "light", "blue", "logpop"),
    ("a16-dark-devpop", "dark", "teal", "devpop"),
    ("a16-dark-exclusive", "dark", "purple", "both"),
    ("a16-light-quick", "light", "green", "quick"),
    ("a16-light-search", "light", "green", "search"),
    ("a16-eye-deep", "eye", "orange", "eyedeep"),
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
    if (what === 'eyedeep'){ document.documentElement.setAttribute('data-eyelevel','deep'); }

    var fr=document.getElementById('frame'); if(fr) fr.classList.add('show');
    var sp=document.getElementById('splash'); if(sp){ sp.classList.add('hide'); sp.classList.add('gone'); }

    switchTab('quick');
    if (what === 'quick' || what === 'eyedeep' || what === 'search'){
      /* 「指令执行」组（第一组）：投屏六条已并进来，看组内小标题是否为「投屏」 */
      switchQuickGroup(0);
    }
    if (what === 'search'){
      /* 命令搜索：卡片名叫「重启车机」，命令是 adb reboot —— 搜 reboot 必须命中 */
      var qi = document.getElementById('quick-search');
      if (qi){
        qi.value = 'reboot';
        /* onQuickSearch 是同步的（防抖只在 v16QuickInput 这个事件入口），截图可直接调 */
        if (typeof onQuickSearch === 'function') onQuickSearch();
      }
    }

    /* 徽章平时要等设备连上才显示；截图没有真机，先把整个状态区放出来，
       否则徽章的 rect 全是 0，浮层会被算到左上角，看不出真实定位。 */
    var ts=document.querySelector('.tb-status'); if(ts) ts.style.display='flex';
    var lb=document.getElementById('log-pill'); if(lb) lb.style.display='';
    var db=document.getElementById('dev-badge'); if(db) db.style.display='';

    if (what === 'logpop' && lb) lb.click();
    if (what === 'devpop' && db) db.click();
    if (what === 'both'){
      /* 互斥验证：先开日志，再开设备 —— 只应剩设备那一个 */
      if (lb) lb.click();
      if (db) db.click();
    }

    void document.body.offsetWidth;

    /* 把互斥结果写到标题上，方便用 OCR/肉眼一眼确认 */
    setTimeout(function(){
      var lp=document.getElementById('v15-logpop');
      var dp=document.getElementById('v15-devpop');
      var s=function(n){ return (n && n.classList.contains('on')) ? 'open' : 'closed'; };
      document.title = 'logpop=' + s(lp) + ' devpop=' + s(dp);
    }, 120);
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
        tmp = os.path.join(tempfile.gettempdir(), "a16shot.html")
        io.open(tmp, "w", encoding="utf-8").write(page)
        png = os.path.join(OUTDIR, name + ".png")
        cmd = [find_edge(), "--headless=new", "--disable-gpu", "--hide-scrollbars",
               "--window-size=1280,820", "--virtual-time-budget=5000",
               "--screenshot=" + png,
               "--user-data-dir=" + os.path.join(tempfile.gettempdir(), "edgeprof_shot16"),
               "file:///" + tmp.replace("\\", "/")]
        subprocess.run(cmd, capture_output=True, timeout=180)
        exists = os.path.exists(png)
        ok += 1 if exists else 0
        print(("  OK   " if exists else "  FAIL ") + png)
    print("\n  %d / %d 张" % (ok, len(CASES)))
    return 0 if ok == len(CASES) else 1


if __name__ == "__main__":
    sys.exit(main())
