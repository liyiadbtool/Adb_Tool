"""在指定宽度下精确测量表头各标签与记录各字段的边界，判断是否成列。

为什么需要：截图只能目测，而 1~2px 的错位肉眼看不出来，却正是用户
抱怨"没对齐"的原因。这里把 getBoundingClientRect 的数字打出来，
表格宽度也在几个常见窗口宽度下各测一遍（百分比分栏在窄窗口更容易错）。
"""
import os
import subprocess
import sys
import tempfile
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
def _find_edge():
    """跨机器找 Edge：优先环境变量，再试两个默认安装位置。
    原先写死 C:/Program Files (x86)/...，换台机器/换用户名就跑不了。"""
    cands = []
    for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            cands.append(os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"))
    cands.append(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
    cands.append(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")
    for c in cands:
        try:
            if c and os.path.exists(c):
                return c
        except Exception:
            pass
    return "msedge.exe"   # 交给 PATH


EDGE = _find_edge()
INJECT = r"""
<script>
(function(){
  function run(){
    var R = [];
    function line(s){ R.push(s); }
    try{
      var sp = document.getElementById('splash'); if(sp) sp.style.display='none';
      var fr = document.getElementById('frame');
      if(fr){ fr.classList.add('show'); fr.style.opacity='1'; fr.style.visibility='visible'; }
      if(typeof switchTab==='function') switchTab('quick');
      var fb = document.getElementById('feedback'); if(fb) fb.style.height='46%';
    }catch(e){ line('setup err '+e); }

    var data = [
      {time:'09:05:07', cmd:'getprop ro.build.version.release', ok:true, ms:8,
       out:[{level:0,text:'13'}]},
      {time:'19:54:23', cmd:'pull /log/android_log/btsnoop', ok:false, ms:3241,
       out:[{level:2,text:'err'}]}
    ];
    for(var i=0;i<data.length;i++){ try{ addFeed(data[i]); }catch(e){ line('addFeed err '+e); } }

    var head = document.querySelector('.fb-head');
    var rows = document.querySelectorAll('.fb-row');
    var r  = rows[rows.length-1];              // 用 3241ms 这条（耗时位数最多）
    var r2 = rows[rows.length-2];              // 8ms 这条（位数最少）

    function g(el){ return el ? el.getBoundingClientRect() : null; }
    function fmt(b){ return b ? (b.left.toFixed(1)+'~'+b.right.toFixed(1)+' w'+b.width.toFixed(1)) : 'null'; }

    var pairs = [
      ['时间', head.querySelector('.h-t'),  r.querySelector('.fb-meta .t')],
      ['状态', head.querySelector('.h-b'),  r.querySelector('.fb-meta .badge')],
      ['耗时', head.querySelector('.h-d'),  r.querySelector('.fb-meta .d')],
      ['指令', head.querySelector('.h-c'),  r.querySelector('.c')],
      ['输出', head.querySelector('.h-s'),  r.querySelector('.fb-right')]
    ];
    line('viewport '+window.innerWidth+'x'+window.innerHeight);
    for(var k=0;k<pairs.length;k++){
      var name=pairs[k][0], hb=g(pairs[k][1]), rb=g(pairs[k][2]);
      if(!hb||!rb){ line(name+' 缺节点'); continue; }
      var dl = Math.abs(hb.left-rb.left), dr = Math.abs(hb.right-rb.right);
      line(name+'\t表头 '+fmt(hb)+'\t记录 '+fmt(rb)+
           '\t左偏 '+dl.toFixed(2)+'\t右偏 '+dr.toFixed(2)+
           ((dl<=1 && dr<=1)?'\tOK':'  <== 错位'));
    }
    // 耗时列两种位数是否右对齐（1位 vs 4位）
    var d1 = g(r2.querySelector('.fb-meta .d')), d4 = g(r.querySelector('.fb-meta .d'));
    line('耗时右对齐(8ms vs 3241ms) 左差 '+Math.abs(d1.left-d4.left).toFixed(2)+
         ' 右差 '+Math.abs(d1.right-d4.right).toFixed(2));

    // 长指令截断高度
    var lr = rows[rows.length-1];
    var cEl = lr.querySelector('.c');
    var lh = parseFloat(getComputedStyle(cEl).lineHeight)||18;
    line('指令高度 '+cEl.clientHeight+'px 行高 '+lh+'px 行数 '+(cEl.clientHeight/lh).toFixed(2));

    var pre = document.createElement('pre');
    pre.id='MEASURE';
    pre.textContent = R.join('\n');
    document.body.appendChild(pre);
  }
  if(document.readyState==='complete') setTimeout(run,150);
  else window.addEventListener('load', function(){ setTimeout(run,150); });
})();
</script>
"""


def run_at(width, height=860):
    html = open(UI, encoding="utf-8").read()
    i = html.rfind("</body>")
    patched = html[:i] + INJECT + html[i:]
    tmp = tempfile.mkdtemp(prefix="measure_")
    p = os.path.join(tmp, "m.html")
    open(p, "w", encoding="utf-8").write(patched)
    for name in os.listdir(os.path.dirname(UI)):
        s = os.path.join(os.path.dirname(UI), name)
        if os.path.isfile(s):
            try:
                shutil.copy2(s, tmp)
            except Exception:
                pass
    cmd = [EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars",
           "--window-size=%d,%d" % (width, height),
           "--force-device-scale-factor=1",
           "--virtual-time-budget=3000",
           "--user-data-dir=" + os.path.join(tmp, "prof"),
           "--dump-dom",
           "file:///" + p.replace("\\", "/")]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    out = r.stdout
    a = out.find('<pre id="MEASURE">')
    if a < 0:
        shutil.rmtree(tmp, ignore_errors=True)
        return "宽度 %d: 没拿到 MEASURE\n" % width
    a = out.find('>', a) + 1
    b = out.find('</pre>', a)
    txt = out[a:b]
    txt = txt.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    shutil.rmtree(tmp, ignore_errors=True)
    return txt


def main():
    ok = True
    for w in (900, 1180, 1440, 1920):
        print("=" * 70)
        txt = run_at(w)
        print(txt)
        if "<== 错位" in txt:
            ok = False
    print("=" * 70)
    print("全部宽度列对齐通过" if ok else "存在错位，见上面的 <== 错位")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
