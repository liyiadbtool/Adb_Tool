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
setTimeout(function(){
  var R=[];
  function ok(n,c,e){R.push((c?'PASS':'FAIL')+' | '+n+(c?'':' -> '+(e===undefined?'':e)));}
  try{ switchTab('quick'); }catch(e){}

  var nav=document.querySelector('.quick-nav');
  R.push('nav clientW='+nav.clientWidth+' scrollW='+nav.scrollWidth);

  // 列出 nav 的直接子元素宽度
  var kids = nav.children;
  for(var i=0;i<kids.length;i++){
    var k=kids[i];
    var r=k.getBoundingClientRect();
    R.push('  子['+i+'] '+k.tagName+'.'+(k.className||'')+
           ' w='+Math.round(r.width)+' scrollW='+k.scrollWidth+
           ' clientW='+k.clientWidth);
  }

  // 找 scrollWidth 超过 nav 宽度的后代
  var all = nav.querySelectorAll('*');
  var wide = [];
  for(var j=0;j<all.length;j++){
    var el=all[j];
    // offsetWidth 超过 nav clientWidth 的，或者 scrollWidth 特别大的
    if(el.scrollWidth > nav.clientWidth + 2 && el.children.length===0){
      var rr=el.getBoundingClientRect();
      wide.push(el.tagName+'.'+(el.className||'')+
                ' text="'+String(el.textContent||'').trim().slice(0,20)+'"'+
                ' w='+Math.round(rr.width)+' scrollW='+el.scrollWidth);
    }
  }
  ok('nav 内无超宽叶子节点', wide.length===0, wide.slice(0,6).join(' || '));

  // 每个 nav item 的宽度
  var items = nav.querySelectorAll('.qnav-item,.filenav-item');
  var overs=[];
  for(var m=0;m<items.length;m++){
    var it=items[m];
    if(it.scrollWidth > it.clientWidth + 1){
      overs.push('"'+(it.textContent||'').trim().slice(0,14)+'" sw='+it.scrollWidth+' cw='+it.clientWidth);
    }
  }
  ok('导航项无内部溢出', overs.length===0, overs.slice(0,6).join(' || '));

  var pre=document.createElement('pre'); pre.id='R'; pre.textContent=JSON.stringify(R);
  document.body.appendChild(pre);
}, 1800);
</script>
"""


def main():
    src = open(UI, encoding="utf-8").read()
    tmp = os.path.join(ROOT, "377", "_sd.html")
    open(tmp, "w", encoding="utf-8", newline="").write(src.replace("</body>", PROBE + "</body>"))
    try:
        p = subprocess.run(
            [EDGE, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-first-run",
             "--disable-background-networking", "--disable-sync", "--disable-extensions",
             "--user-data-dir=" + os.path.join(tempfile.gettempdir(), "ep_sd"),
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
