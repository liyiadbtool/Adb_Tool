"""表头 vs 记录 的列对齐断言（字形级，多窗口宽度）。

为什么需要这一层：
  _test_ui_behavior.py 用元素盒量，能证明"盒子对齐"；但用户抱怨的是
  "看起来对不上"，取决于**文字字形**的实际位置。这里用 Range 取字形盒
  （selectNodeContents + getBoundingClientRect），在 4 种窗口宽度下
  逐一断言，偏差 > 1.5px 直接 FAIL。

对齐规则（与 CSS 一一对应）：
  时间  左对齐（HH:mm:ss 等宽，左边界对齐）
  状态  居中（徽章 text-align:center）
  耗时  右对齐（位数不同也要右侧齐）
  指令  左对齐
  输出  左对齐

运行：python 377/_measure_text_align.py    退出码 0 = 全部对齐
"""
import os
import shutil
import subprocess
import sys
import tempfile

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
    var R=[], BAD=0;
    function ck(name, cond, extra){
      if(!cond) BAD++;
      R.push((cond?'PASS':'FAIL')+' | '+name+(cond?'':' | '+extra));
    }
    try{
      var sp=document.getElementById('splash'); if(sp) sp.style.display='none';
      var fr=document.getElementById('frame');
      if(fr){fr.classList.add('show');fr.style.opacity='1';fr.style.visibility='visible';}
      if(typeof switchTab==='function') switchTab('quick');
    }catch(e){ R.push('setup err '+e); }

    // 两条记录：一条位数最少（8 ms），一条位数最多（3241 ms），覆盖右对齐极值
    addFeed({time:'19:54:06',cmd:'getprop ro.build.version.release',ok:true,ms:8,
             out:[{level:0,text:'13'}]});
    addFeed({time:'19:54:23',cmd:'pull /log/android_log/btsnoop',ok:false,ms:3241,
             out:[{level:2,text:'err'}]});

    // 字形盒：Range 量的是真实文字范围，不是元素盒
    function tb(el){
      if(!el) return null;
      var rg=document.createRange(); rg.selectNodeContents(el);
      var b=rg.getBoundingClientRect();
      return (b.width>0)?b:null;
    }
    var head=document.querySelector('.fb-head');
    var rows=document.querySelectorAll('.fb-row');
    var r=rows[rows.length-1], r2=rows[rows.length-2];

    ck('表头 时间/状态/耗时/指令/输出 齐全',
       !!(head.querySelector('.h-t')&&head.querySelector('.h-b')&&head.querySelector('.h-d')
          &&head.querySelector('.h-c')&&head.querySelector('.h-s')),
       '缺标签');

    var d=function(a,b){ return Math.abs(a-b); };
    var hT=tb(head.querySelector('.h-t')), rT=tb(r.querySelector('.fb-meta .t'));
    var hB=tb(head.querySelector('.h-b')), rB=tb(r.querySelector('.fb-meta .badge'));
    var hD=tb(head.querySelector('.h-d')), rD=tb(r.querySelector('.fb-meta .d'));
    var hC=tb(head.querySelector('.h-c')), rC=tb(r.querySelector('.c'));
    var hS=tb(head.querySelector('.h-s')), rS=tb(r.querySelector('.fb-right'));

    ck('时间列左边界对齐', d(hT.left,rT.left)<=1.5, d(hT.left,rT.left).toFixed(2));
    ck('状态列居中对齐', d((hB.left+hB.right)/2,(rB.left+rB.right)/2)<=1.5,
       d((hB.left+hB.right)/2,(rB.left+rB.right)/2).toFixed(2));
    ck('耗时列右边界对齐', d(hD.right,rD.right)<=1.5, d(hD.right,rD.right).toFixed(2));
    ck('指令列左边界对齐', d(hC.left,rC.left)<=1.5, d(hC.left,rC.left).toFixed(2));
    ck('输出列左边界对齐', d(hS.left,rS.left)<=1.5, d(hS.left,rS.left).toFixed(2));

    // 同列不同位数也要齐（这才是"对齐"的真正含义）
    var t1=tb(r2.querySelector('.fb-meta .d')), t2=tb(r.querySelector('.fb-meta .d'));
    ck('耗时 8ms 与 3241ms 右边界一致', d(t1.right,t2.right)<=1.5, d(t1.right,t2.right).toFixed(2));
    var m1=tb(r2.querySelector('.fb-meta .t')), m2=tb(r.querySelector('.fb-meta .t'));
    ck('两条时间左边界一致', d(m1.left,m2.left)<=1.5, d(m1.left,m2.left).toFixed(2));

    // 字符限制：长指令截到 2 行
    addFeed({time:'10:00:03',cmd:'x'.repeat(400),ok:true,ms:3,out:[{level:0,text:'y'.repeat(400)}]});
    var all=document.querySelectorAll('.fb-row');
    var lr=all[all.length-1];
    var cEl=lr.querySelector('.c'), oEl=lr.querySelector('.fb-right');
    var lh=parseFloat(getComputedStyle(cEl).lineHeight)||18;
    ck('400 字符指令被限制在 2 行内', cEl.clientHeight<=lh*2+2, cEl.clientHeight+'px / lh '+lh);
    ck('长指令有 title 可看全文', cEl.title.length===400, String(cEl.title.length));
    ck('长输出区限高 200px', Math.abs(parseFloat(getComputedStyle(oEl).maxHeight)-200)<1,
       getComputedStyle(oEl).maxHeight);

    var pre=document.createElement('pre'); pre.id='MEASURE';
    pre.textContent='BAD='+BAD+'\n'+R.join('\n');
    document.body.appendChild(pre);
  }
  if(document.readyState==='complete') setTimeout(run,200);
  else window.addEventListener('load',function(){setTimeout(run,200);});
})();
</script>
"""


def run_at(width, height=860):
    html = open(UI, encoding="utf-8").read()
    i = html.rfind("</body>")
    if i < 0:
        return -1, "ui.html 里没有 </body>"
    tmp = tempfile.mkdtemp(prefix="mta_")
    p = os.path.join(tmp, "m.html")
    open(p, "w", encoding="utf-8").write(html[:i] + INJECT + html[i:])
    for n in os.listdir(os.path.dirname(UI)):
        s = os.path.join(os.path.dirname(UI), n)
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
           "--dump-dom", "file:///" + p.replace("\\", "/")]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    o = r.stdout
    a = o.find('<pre id="MEASURE">')
    if a < 0:
        shutil.rmtree(tmp, ignore_errors=True)
        return -1, "没拿到 MEASURE（DOM 长度 %d）" % len(o)
    a = o.find('>', a) + 1
    b = o.find('</pre>', a)
    txt = o[a:b].replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    shutil.rmtree(tmp, ignore_errors=True)
    bad = 0
    for line in txt.splitlines():
        if line.startswith('BAD='):
            try:
                bad = int(line[4:].strip())
            except ValueError:
                bad = 1
    return bad, txt


def main():
    if not os.path.exists(EDGE):
        print("找不到 Edge，跳过")
        return 0
    if not os.path.exists(UI):
        print("找不到 ui.html:", UI)
        return 1

    total_bad = 0
    for w in (900, 1180, 1440, 1920):
        bad, txt = run_at(w)
        print("=" * 72)
        print("窗口宽度 %d px" % w)
        for line in txt.splitlines():
            if line.startswith('BAD='):
                continue
            print("  " + line)
        total_bad += bad if bad > 0 else (1 if bad < 0 else 0)
    print("=" * 72)
    if total_bad == 0:
        print("  列对齐与字符限制：4 种宽度全部通过")
        return 0
    print("  失败 %d 项" % total_bad)
    return 1


if __name__ == "__main__":
    sys.exit(main())
