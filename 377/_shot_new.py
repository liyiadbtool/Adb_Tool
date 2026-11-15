# -*- coding: utf-8 -*-
"""本轮改动的可视化验证：截图确认
   1) 方控按键独立分组（9 张卡 + 三个分类小标题）
   2) 语音助手页输入区不再吸顶、可整体滚动
   3) 输出区展开 / 收起两种形态（折叠栏 + 记录条数）
只在验证时用，不进发布物。
"""
import os
import tempfile
import re
import subprocess
import sys

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
PROF = os.path.join(tempfile.gettempdir(), "edgeprof_shotnew")
SHOT_DIR = os.path.join(HERE, "_shots")
os.makedirs(SHOT_DIR, exist_ok=True)

# 每个场景：注入一段脚本准备界面状态，然后单独截图
SCENES = {
    "1_fk_group": r"""
      switchTab('quick');
      var i=-1; for(var k=0;k<quickGroups.length;k++){ if(quickGroups[k].name==='方控按键'){i=k;break;} }
      switchQuickGroup(i);
      addFeed({time:'10:00:01', cmd:':fkvolup', ok:true, ms:120, out:[{level:0,text:'Succeeded'}]});
      addFeed({time:'10:00:02', cmd:':fkmute',  ok:true, ms:95,  out:[{level:0,text:'Succeeded'}]});
    """,
    "2_vr_scroll": r"""
      switchTab('quick');
      var i=-1; for(var k=0;k<quickGroups.length;k++){ if(quickGroups[k].name==='语音助手'){i=k;break;} }
      switchQuickGroup(i);
      var sc=document.getElementById('quick-scroll'); sc.scrollTop=0;
      addFeed({time:'10:00:01', cmd:':vr sr 打开车窗 -a 0', ok:true, ms:210, out:[{level:0,text:'√ 识别已下发'}]});
    """,
    "3_vr_scrolled": r"""
      switchTab('quick');
      var i=-1; for(var k=0;k<quickGroups.length;k++){ if(quickGroups[k].name==='语音助手'){i=k;break;} }
      switchQuickGroup(i);
      var sc=document.getElementById('quick-scroll'); sc.scrollTop=200;
      addFeed({time:'10:00:01', cmd:':vr sr 打开车窗 -a 0', ok:true, ms:210, out:[{level:0,text:'√ 识别已下发'}]});
    """,
    "4_fb_collapsed": r"""
      switchTab('quick');
      var i=-1; for(var k=0;k<quickGroups.length;k++){ if(quickGroups[k].name==='指令执行'){i=k;break;} }
      switchQuickGroup(i);
      addFeed({time:'10:00:01', cmd:':anrlog', ok:true, ms:1800, out:[{level:0,text:'√ ANR 日志已导出到 桌面\\logcat\\2026-11-12\\anr'}]});
      addFeed({time:'10:00:02', cmd:':dropboxlog', ok:true, ms:2100, out:[{level:0,text:'√ crash 日志已导出到 桌面\\logcat\\2026-11-12\\dropbox'}]});
      addFeed({time:'10:00:03', cmd:':reboot', ok:true, ms:240, out:[{level:0,text:'reboot 已下发，车机正在重启'}]});
      // 模拟拖到底：直接加收起态
      var fb=document.getElementById('feedback');
      fb.classList.add('collapsed'); fb.style.height='34px';
      if(window.fbRefreshCount) window.fbRefreshCount();
    """,
}

PREP = r"""
<script>
(function(){
  function hideSplash(){
    try{
      if(typeof setStatus==='function'){
        setStatus({dev:'311b4567',online:true,soc:'8295',res:'2880x1620',dir:'/',rooted:true,loglevel:'V',msg:'ok'});
      }
      var sp=document.getElementById('splash');
      if(sp){ sp.classList.add('gone'); sp.style.display='none'; }
      var fr=document.getElementById('frame');
      if(fr){ fr.classList.add('show'); fr.style.opacity='1'; fr.style.visibility='visible'; }
    }catch(e){}
  }
  function run(){ hideSplash(); setTimeout(function(){ SCENE_BODY }, 60); }
  if(document.readyState==='complete') setTimeout(run, 150);
  else window.addEventListener('load', function(){ setTimeout(run, 150); });
})();
</script>
"""


def shoot(name, body, win="1200,820"):
    out_png = os.path.join(SHOT_DIR, name + ".png")
    html = os.path.join(HERE, "_tmp_scene.html")
    src = open(UI, encoding="utf-8").read()
    prep = PREP.replace("SCENE_BODY", body)
    open(html, "w", encoding="utf-8").write(src.replace("</body>", prep + "</body>"))
    url = "file:///" + html.replace("\\", "/")
    cmd = [EDGE, "--headless=new", "--disable-gpu",
           "--window-size=" + win,
           "--virtual-time-budget=4000",
           "--user-data-dir=" + PROF,
           "--screenshot=" + out_png,
           url]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    ok = os.path.exists(out_png) and os.path.getsize(out_png) > 5000
    print(("  OK  " if ok else "  FAIL") + "  " + name + "  -> " + out_png
          + ("  (%d bytes)" % os.path.getsize(out_png) if ok else "  " + (r.stderr or "")[:200]))
    return ok


def main():
    allok = True
    for name in ["1_fk_group", "2_vr_scroll", "3_vr_scrolled", "4_fb_collapsed"]:
        allok = shoot(name, SCENES[name]) and allok
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
