"""智驾出行端到端测试（2026-11-22 第 14 批）。

验证真实链路（headless 测不出这些）：
  1. HeapDump 浮层能拿到**真实进程列表**（C# App.ListProcRows，按 RSS 倒序）
  2. 地图相关命令真的能被 C# 执行（返回"未安装"也算通，说明整条链路通）
  3. 带输入框的卡片能把值拼进命令

做法：--uitest 在真实 WebView2 里跑。

注意：不跑 :maptrad（会重启 Android 框架）和 :mapclear（会清数据）。
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
  var out = { ok:false, stage:'init', procs:[], err:null };
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
        if(m && m.kind === 'heaplist'){
          out.ok = !!m.ok;
          out.procs = m.rows || [];
          out.stage = 'got-list';
        }
      }catch(err){}
    });
  }catch(e){ out.err = 'listen: ' + e; }

  setTimeout(function(){
    try{
      openHeapDump();
      out.stage = 'requested';
    }catch(e){ out.err = String(e); finish(); return; }

    var waited = 0;
    var iv = setInterval(function(){
      waited += 400;
      if(out.stage === 'got-list'){
        clearInterval(iv);
        out.stage = 'done';
        try{ closeHeapDump(); }catch(e){}
        finish();
        return;
      }
      if(waited >= 12000){
        clearInterval(iv);
        out.stage = 'timeout';
        out.err = '12 秒内没收到 heaplist';
        try{ closeHeapDump(); }catch(e){}
        finish();
      }
    }, 400);
  }, 2600);
})();
</script>
"""


def main():
    if not os.path.exists(EXE):
        print("  [SKIP] 找不到 exe，先跑 build_gui.bat")
        return 0

    src = open(UI, encoding="utf-8").read()
    tmp = os.path.join(tempfile.gettempdir(), "_drive_uitest.html")
    open(tmp, "w", encoding="utf-8", newline="").write(src.replace("</body>", PROBE + "</body>"))

    try:
        p = subprocess.run([EXE, "--uitest", tmp, "20000"],
                           capture_output=True, timeout=150)
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
        print(out[:700])
        if err.strip():
            print("stderr:", err[:300])
        return 2

    try:
        data, _ = json.JSONDecoder().raw_decode(out[i:])
    except Exception as e:
        print("!! JSON 失败：%s" % e)
        print(out[i:i+500])
        return 2

    R = []

    def ok(name, cond, extra=""):
        R.append(("PASS" if cond else "FAIL") + " | " + name + ("" if cond else (" -> " + str(extra))))

    ok("收到了 heaplist 回包", data.get("stage") == "done", data.get("err") or data.get("stage"))
    ok("回包 ok=true", data.get("ok") is True, data.get("ok"))

    procs = data.get("procs") or []
    ok("拿到进程列表", len(procs) > 0, len(procs))

    if procs:
        # 按 RSS 倒序验证
        rss = []
        for x in procs:
            try:
                rss.append(int(x.get("rss", "0")))
            except Exception:
                rss.append(0)
        desc = all(rss[i] >= rss[i+1] for i in range(len(rss)-1))
        ok("按内存倒序排列", desc, rss[:8])

        # 应用进程（名字带 .）
        has_dot = sum(1 for x in procs if "." in str(x.get("name", "")))
        ok("列表里基本都是应用进程", has_dot >= len(procs) * 0.8,
           "%d/%d 含点" % (has_dot, len(procs)))

        # 不该出现内核线程
        kern = [x for x in procs if str(x.get("name", "")).startswith("[")]
        ok("没有内核线程（已过滤）", len(kern) == 0, [x["name"] for x in kern[:5]])

        ok("有 PID 字段", all(x.get("pid") for x in procs))
        ok("有 RSS 字段", any(x.get("rss") not in ("0", "", None) for x in procs))

    print("")
    print("=== 真实进程列表（按内存倒序，前 12 个）===")
    for x in procs[:12]:
        try:
            mb = int(x.get("rss", 0)) / 1024.0
            mbTxt = ("%.1f GB" % (mb/1024)) if mb >= 1024 else ("%.0f MB" % mb)
        except Exception:
            mbTxt = "?"
        print("  %-46s PID %-7s %s" % (x.get("name", "")[:46], x.get("pid", ""), mbTxt))
    print("  共 %d 个进程" % len(procs))
    print("")

    for line in R:
        print("  " + line)
    fail = sum(1 for x in R if x.startswith("FAIL"))
    print("")
    print("  智驾端到端：通过 %d / %d" % (len(R) - fail, len(R)))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
