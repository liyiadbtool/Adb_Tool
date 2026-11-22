"""case "run" 修复的端到端验证（2026-11-22 第 15 批）。

★ 这是这批最重要的测试。

背景：页面有 12 处 post('run', cmd, src)，但 C# 的 switch 里没有 case "run"，
命令被静默丢弃 —— 诊断页连通性、Fastbot 运行、APK 列表、文件 push 全都不工作。

本测试验证：加 case "run" 之后，命令**真的下发并拿到输出**。
用最小代价的连通性（src=20）作为探针 —— 它只跑一条 getprop，秒回。

同时也验证 diagcar（车机信息）不再卡在"正在读取"。
"""
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
EXE = os.path.join(ROOT, "adb_log_gui", "dist", "adb_Tool.exe")

PROBE = r"""
<script>
(function(){
  var out = {
    ok:false, stage:'init', err:null,
    linkLines:[], linkRendered:'',
    carStage:'', carRendered:'',
    sumText:''
  };
  function finish(){
    var pre = document.createElement('pre');
    pre.id = 'RESULT';
    pre.textContent = JSON.stringify(out);
    document.body.appendChild(pre);
  }

  try{
    window.chrome.webview.addEventListener('message', function(e){
      try{
        var m = (typeof e.data === 'string') ? JSON.parse(e.data) : e.data;
        if(!m) return;
        // ★ 输出行是**批量**发的：{kind:'lines', items:[{level,src,slot,text}]}
        //   （GuiWeb.PushLines）。单行 {src,text} 的写法收不到，之前探针就踩了这坑。
        if(m.kind === 'lines' && m.items){
          for(var ii=0; ii<m.items.length; ii++){
            var it = m.items[ii];
            if(it && it.src === 20 && it.text) out.linkLines.push(String(it.text));
          }
        }
        if(m.kind === 'diagcar'){
          out.carStage = m.online ? 'online' : 'offline';
        }
      }catch(err){}
    });
  }catch(e){ out.err = 'listen: ' + e; }

  setTimeout(function(){
    try{
      switchTab('diag');
      diagRefresh();
      out.stage = 'refreshed';
    }catch(e){ out.err = String(e); finish(); return; }

    // 等 10 秒：连通性一条 getprop 应该秒回，车机信息也就几秒
    var waited = 0;
    var iv = setInterval(function(){
      waited += 500;

      var lb = document.getElementById('diag-rows-link');
      var cb = document.getElementById('diag-rows-car');
      var sum = document.getElementById('diag-sum');
      out.linkRendered = lb ? lb.textContent.replace(/\s+/g,' ').slice(0,200) : '';
      out.carRendered  = cb ? cb.textContent.replace(/\s+/g,' ').slice(0,200) : '';
      out.sumText      = sum ? sum.textContent.replace(/\s+/g,' ').slice(0,200) : '';

      // 连通性渲染完成（不再是"采集设备连通性…"或"采集超时"）
      var linkDone = out.linkRendered &&
                     out.linkRendered.indexOf('采集设备连通性') < 0 &&
                     out.linkRendered.indexOf('采集超时') < 0;
      // 车机不再是"正在读取"
      var carDone = out.carRendered && out.carRendered.indexOf('正在读取') < 0;

      if(waited >= 6000 && linkDone && carDone){
        clearInterval(iv);
        out.ok = true;
        out.stage = 'done';
        finish();
        return;
      }
      if(waited >= 14000){
        clearInterval(iv);
        out.stage = 'timeout';
        out.err = '14 秒内未完成 linkDone=' + linkDone + ' carDone=' + carDone;
        finish();
      }
    }, 500);
  }, 2600);
})();
</script>
"""


def main():
    if not os.path.exists(EXE):
        print("  [SKIP] 找不到 exe，先跑 build_gui.bat")
        return 0

    src = open(UI, encoding="utf-8").read()
    tmp = os.path.join(tempfile.gettempdir(), "_b15_uitest.html")
    open(tmp, "w", encoding="utf-8", newline="").write(src.replace("</body>", PROBE + "</body>"))

    try:
        p = subprocess.run([EXE, "--uitest", tmp, "22000"],
                           capture_output=True, timeout=180)
        out = p.stdout.decode("utf-8", "replace")
        err = p.stderr.decode("utf-8", "replace")
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass

    i = out.find('{"ok"')
    if i < 0:
        print("!! 没拿到结果")
        print(out[:600])
        if err.strip():
            print("stderr:", err[:300])
        return 2

    try:
        data, _ = json.JSONDecoder().raw_decode(out[i:])
    except Exception as e:
        print("!! JSON 失败：%s" % e)
        print(out[i:i+400])
        return 2

    R = []

    def ok(name, cond, extra=""):
        R.append(("PASS" if cond else "FAIL") + " | " + name + ("" if cond else (" -> " + str(extra))))

    ok("流程跑完", data.get("stage") == "done", data.get("err") or data.get("stage"))

    # ★ 核心：src=20 的输出真的回来了
    lines = data.get("linkLines") or []
    ok("★ 收到 src=20 输出行（case run 生效）", len(lines) > 0, len(lines))

    joined = " ".join(lines)
    ok("★ 输出含 AUTH=", "AUTH=" in joined, joined[:150])
    ok("★ 输出含 MODEL=", "MODEL=" in joined, joined[:150])

    lr = data.get("linkRendered") or ""
    ok("连通性已渲染（不再是采集中）",
       lr and "采集设备连通性" not in lr and "采集超时" not in lr, lr[:120])
    ok("连通性显示了授权状态", "授权" in lr, lr[:150])
    ok("连通性显示了设备型号或 —", ("设备型号" in lr), lr[:150])

    cr = data.get("carRendered") or ""
    ok("★ 车机信息不再卡在正在读取", cr and "正在读取" not in cr, cr[:120])

    st = data.get("sumText") or ""
    ok("汇总条已渲染", st and "正在采集" not in st, st[:120])

    print("")
    print("=== 实际渲染结果 ===")
    print("  汇总条 : %s" % st)
    print("  连通性 : %s" % lr)
    print("  车机   : %s" % cr)
    if lines:
        print("  src=20 原始行：")
        for x in lines[:8]:
            print("    " + x.strip())
    print("")

    for line in R:
        print("  " + line)
    fail = sum(1 for x in R if x.startswith("FAIL"))
    print("")
    print("  case run 端到端：通过 %d / %d" % (len(R) - fail, len(R)))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
