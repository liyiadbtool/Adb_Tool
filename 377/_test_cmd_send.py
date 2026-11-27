# -*- coding: utf-8 -*-
"""终端"发送指令"最小回归（2026-11-27 事故后加的守卫）

背景：重构 run()/_runSubmit 时漏了 fromQuick 声明，导致回车/按钮全部失效，
但当时所有测试都在测新功能，没人测"单行回车能不能发出去"。

本脚本只做一条断言：
    在终端页输入单行命令并触发 run(0) → _busy[0] 必须变 true（= post 发出去了）

用法：python _test_cmd_send.py
退出码：0 通过，1 失败
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
EXE = os.path.join(ROOT, "adb_log_gui", "dist", "adb_Tool.exe")

PROBE = """
<pre id="RESULT">pending</pre>
<script>
var R={};
setTimeout(function(){ try{ switchTab('cmd'); }catch(e){} },800);
setTimeout(function(){
  try{
    var inp=document.getElementById('cmd-input-0');
    if(!inp){ R.error='no-input'; }
    else {
      inp.value='adb devices';
      run(0);
      R.busy = _busy[0];
      R.cleared = (inp.value === '');
      // 再测一次键盘回车路径
      inp.value='echo hi';
      inp.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));
      R.busyEnter = _busy[0];
    }
  }catch(e){ R.error = e.message; }
  document.getElementById('RESULT').textContent = JSON.stringify(R);
},2000);
</script>
"""


def main():
    if not os.path.isfile(EXE):
        print("找不到 exe：%s" % EXE)
        return 1
    html = open(UI, encoding="utf-8").read()
    tmp = os.path.join(tempfile.gettempdir(), "_probe_cmd_send.html")
    open(tmp, "w", encoding="utf-8", newline="\n").write(html.replace("</body>", PROBE + "</body>"))

    try:
        out = subprocess.run([EXE, "--uitest", tmp, "4200"],
                             capture_output=True, timeout=90)
        text = (out.stdout or b"").decode("utf-8", "replace").strip().splitlines()
        line = text[-1].strip() if text else ""
    finally:
        try:
            subprocess.run(["taskkill", "/F", "/IM", "adb_Tool.exe"],
                           capture_output=True, timeout=15)
        except Exception:
            pass
        try:
            os.remove(tmp)
        except Exception:
            pass

    if not line.startswith("{"):
        print("FAIL 没有拿到探针结果：%r" % line[:120])
        return 1

    import json, re
    m = re.search(r"\{.*\}", line)          # 输出后面可能带 BOM/其他字符
    raw = m.group(0) if m else line
    try:
        r = json.loads(raw)
    except Exception as e:
        print("FAIL 结果不是 JSON：%s" % e)
        return 1

    ok = (r.get("busy") is True
          and r.get("cleared") is True
          and r.get("busyEnter") is True
          and not r.get("error"))
    if ok:
        print("PASS 终端发送链路正常（busy=%s cleared=%s enter=%s）"
              % (r.get("busy"), r.get("cleared"), r.get("busyEnter")))
        return 0
    print("FAIL %s" % r)
    return 1


if __name__ == "__main__":
    sys.exit(main())
