"""渲染 ui.html 并注入若干条记录，截图验证「表头 vs 记录」的列对齐。

为什么单独做这个脚本：
  PrintWindow 抓的是真实运行窗口，但它要连设备、要等 splash 退场，
  抓到的往往是加载遮罩；而"列是否对齐"是纯前端像素问题，
  直接把页面渲染出来、灌几条典型数据（短指令/长指令/大耗时数字），
  一次就能看清表头时间和记录时间是否成一条竖线。

做法：headless Edge --screenshot + 注入脚本（用 --virtual-time-budget 等 JS 跑完）。
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
OUT = os.path.join(HERE, "_shot_align.png")

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

# 注入：退场 splash + 灌入三条有代表性的记录
INJECT = r"""
<script>
(function(){
  function run(){
    // 1) 跳过启动遮罩，直接看主界面
    //    注意：.frame 初始是 opacity:0 + visibility:hidden，靠 .show 类才显示，
    //    光改 style.opacity 是不够的（visibility 还是 hidden，整块黑）。
    try{
      var sp = document.getElementById('splash');
      if(sp) sp.style.display = 'none';
      var fr = document.getElementById('frame') || document.querySelector('.frame');
      if(fr){ fr.classList.add('show'); fr.style.opacity = '1'; fr.style.visibility = 'visible'; }
    }catch(e){}
    // 2) 反馈区在「快捷指令」页（#page-quick），必须切过去才看得见
    try{ if(typeof switchTab === 'function') switchTab('quick'); }catch(e){}
    // 3) 反馈区高度放大一点，方便看列
    try{
      var fb = document.getElementById('feedback');
      if(fb) fb.style.height = '46%';
    }catch(e){}

    // 3) 三条典型记录：
    //    - 短指令、小耗时（1 ms）
    //    - 长指令（会被截到 2 行）
    //    - 大耗时（4 位数，验证右对齐）
    var data = [
      {time:'19:54:06', cmd:':car', ok:true, ms:186,
       out:[{level:0,text:'车型          181'},
            {level:0,text:'SOC 版本      GAC_T68_IDC_S1B3_261105_0745F_D'},
            {level:0,text:'MCU 版本      T68_IC2015_01_21.773_261105_R'},
            {level:0,text:'Android 版本  12'},
            {level:0,text:'VIN 码        LMGNA1S86R1S00331'},
            {level:0,text:'UUID          8545003ANB010000VD311000124091400N10001'},
            {level:0,text:'DID           3885895'},
            {level:0,text:'OPENID        6a29b54b'},
            {level:0,text:'屏幕分辨率    2560x1440'}]},
      {time:'19:54:11', cmd:'shell "dumpsys activity activities | grep -E \'mResumedActivity|topResumedActivity\' | head -5  # 这条故意写得很长用来验证两行截断效果"',
       ok:true, ms:147,
       out:[{level:0,text:'topResumedActivity=ActivityRecord{2a1f3c u0 com.gxatek.scene/.MainActivity t82}'}]},
      {time:'19:54:23', cmd:'pull /log/android_log/btsnoop', ok:false, ms:3241,
       out:[{level:2,text:'adb: error: failed to stat remote object \'/log/android_log/btsnoop\': No such file or directory'}]}
    ];
    for(var i=0;i<data.length;i++){
      try{ addFeed(data[i]); }catch(e){}
    }
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
    if not os.path.exists(UI):
        print("找不到 ui.html:", UI)
        return 1
    edge = find_edge()
    if not edge:
        print("找不到 Edge")
        return 1

    html = open(UI, encoding="utf-8").read()
    # 注入脚本必须放在 ui.html 自己的 script 之后（addFeed 已定义）
    idx = html.rfind("</body>")
    if idx < 0:
        print("ui.html 里没有 </body>")
        return 1
    patched = html[:idx] + INJECT + html[idx:]

    tmpdir = tempfile.mkdtemp(prefix="alignshot_")
    tmp_html = os.path.join(tmpdir, "ui_inject.html")
    open(tmp_html, "w", encoding="utf-8").write(patched)
    # 页面里若有相对路径资源，同级复制过去
    for name in os.listdir(os.path.dirname(UI)):
        s = os.path.join(os.path.dirname(UI), name)
        if os.path.isfile(s):
            try:
                shutil.copy2(s, tmpdir)
            except Exception:
                pass

    prof = os.path.join(tmpdir, "prof")
    cmd = [
        edge,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--window-size=1180,860",
        "--force-device-scale-factor=1",
        "--virtual-time-budget=3000",
        "--user-data-dir=" + prof,
        "--screenshot=" + OUT,
        "file:///" + tmp_html.replace("\\", "/"),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if not os.path.exists(OUT):
        print("截图失败")
        print(r.stdout[-2000:])
        print(r.stderr[-2000:])
        return 1
    print("saved", OUT, os.path.getsize(OUT), "bytes")
    shutil.rmtree(tmpdir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
