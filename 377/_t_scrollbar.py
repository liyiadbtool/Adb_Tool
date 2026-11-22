import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = r"C:\Users\李亦\Desktop\Adb_Tool"
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

PROBE = r"""
<script>
window.__E=[];window.addEventListener('error',e=>window.__E.push(String(e.message)));
setTimeout(function(){
  var R=[];
  function ok(n,c,e){R.push((c?'PASS':'FAIL')+' | '+n+(c?'':' -> '+(e===undefined?'':e)));}

  try{ switchTab('quick'); }catch(e){}

  var nav=document.querySelector('.quick-nav');
  ok('左导航存在', !!nav);
  if(nav){
    var cs=getComputedStyle(nav);
    ok('overflow-x 为 hidden（横向滚动已禁）', cs.overflowX==='hidden', cs.overflowX);
    ok('overflow-y 仍可滚', cs.overflowY==='auto', cs.overflowY);
    // 实测：无横向溢出
    var over = nav.scrollWidth - nav.clientWidth;
    ok('无横向溢出（scrollWidth<=clientWidth）', over<=0,
       'over='+over+' scrollW='+nav.scrollWidth+' clientW='+nav.clientWidth);
  }

  // 通用规则覆盖到其他容器
  // quick-grid 不在名单里：它是 grid 容器，靠 minmax(0,1fr) 约束列宽，
  // 不需要也不应该加 overflow-x:hidden（会让 overflow-y 变成 auto）。
  var sels=['.mk-list','.apk-list','.fs-list','.mk-out','.logbox','.quick-scroll'];
  var bad=[];
  sels.forEach(function(s){
    var el=document.querySelector(s);
    if(!el) return;
    var v=getComputedStyle(el).overflowX;
    if(v!=='hidden') bad.push(s+'='+v);
  });
  ok('容器型列表均禁止横滚', bad.length===0, bad.join(' '));

  ok('无运行时错误', window.__E.length===0, window.__E.join('; '));

  var pre=document.createElement('pre'); pre.id='R'; pre.textContent=JSON.stringify(R);
  document.body.appendChild(pre);
}, 1800);
</script>
"""


def main():
    src = open(UI, encoding="utf-8").read()
    tmp = os.path.join(ROOT, "377", "_sb.html")
    open(tmp, "w", encoding="utf-8", newline="").write(src.replace("</body>", PROBE + "</body>"))
    try:
        p = subprocess.run(
            [EDGE, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-first-run",
             "--disable-background-networking", "--disable-sync", "--disable-extensions",
             "--user-data-dir=" + os.path.join(tempfile.gettempdir(), "ep_sb"),
             "--window-size=1280,900", "--virtual-time-budget=12000", "--dump-dom",
             "file:///" + tmp.replace("\\", "/")],
            capture_output=True, timeout=150)
        dom = p.stdout.decode("utf-8", "replace")
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass
    m = re.search(r'<pre id="R">(.*?)</pre>', dom, re.S)
    if not m:
        print("探针未返回")
        return 2
    for line in json.loads(m.group(1)):
        print("  " + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
