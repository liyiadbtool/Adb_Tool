"""渲染语音助手页（page-vr），截图检查布局是否美观合理（需求10）。"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
OUT = os.path.join(HERE, "_shot_vr.png")

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

INJECT = r"""
<script>
(function(){
  function run(){
    try{
      var sp = document.getElementById('splash');
      if(sp) sp.style.display = 'none';
      var fr = document.getElementById('frame');
      if(fr){ fr.classList.add('show'); fr.style.opacity = '1'; fr.style.visibility = 'visible'; }
    }catch(e){}
    try{ if(typeof switchTab === 'function') switchTab('vr'); }catch(e){}
    try{ if(typeof pickZone === 'function') pickZone(1); }catch(e){}
    // 灌一条发送结果
    try{
      var log = document.getElementById('vr-log');
      var empty = document.getElementById('vr-log-empty');
      if(empty) empty.style.display = 'none';
      var h = document.createElement('div'); h.className='vr-head-row';
      h.textContent = '20:30:00  → 发送到 [副驾]：打开车窗';
      log.appendChild(h);
      var l1 = document.createElement('div'); l1.className='vr-line c-ok';
      l1.textContent = '√ 识别已下发：打开车窗 [副驾(1)]';
      log.appendChild(l1);
      var l2 = document.createElement('div'); l2.className='vr-line c-dim';
      l2.textContent = '  URI：sr://syncore.vpa.sr/test?text=...';
      log.appendChild(l2);
    }catch(e){}
  }
  if(document.readyState === 'complete') setTimeout(run, 120);
  else window.addEventListener('load', function(){ setTimeout(run, 120); });
})();
</script>
"""


def find_edge():
    for p in EDGE_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def main():
    edge = find_edge()
    if not edge:
        print("找不到 Edge")
        return 1
    html = open(UI, encoding="utf-8").read()
    idx = html.rfind("</body>")
    patched = html[:idx] + INJECT + html[idx:]

    tmpdir = tempfile.mkdtemp(prefix="vrshot_")
    tmp_html = os.path.join(tmpdir, "ui_inject.html")
    open(tmp_html, "w", encoding="utf-8").write(patched)
    for name in os.listdir(os.path.dirname(UI)):
        s = os.path.join(os.path.dirname(UI), name)
        if os.path.isfile(s):
            try: shutil.copy2(s, tmpdir)
            except Exception: pass

    prof = os.path.join(tmpdir, "prof")
    cmd = [
        edge, "--headless=new", "--disable-gpu",
        "--window-size=1180,820", "--force-device-scale-factor=1",
        "--virtual-time-budget=4000", "--screenshot=" + OUT,
        "--user-data-dir=" + prof,
        "file:///" + tmp_html.replace("\\", "/"),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    print(r.stdout[-300:] if r.stdout else "")
    if os.path.exists(OUT):
        print("saved", OUT, os.path.getsize(OUT), "bytes")
        return 0
    print("截图失败")
    return 1


if __name__ == "__main__":
    sys.exit(main())
