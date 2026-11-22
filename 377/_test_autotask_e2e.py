"""定时任务端到端测试（2026-11-22 第 12 批需求 2.1 / 2.2）。

为什么需要它：
  _test_autotask.py 验证的是页面按钮状态机（造消息喂进去）。
  它证明不了 C# 的 AutoTask.cs 真能跑：线程能不能起、日志能不能推回页面、
  暂停/停止能不能响应。

  这个脚本走 --uitest，在**真实 WebView2** 里加载 ui.html，
  真的点「开始」让 C# 引擎跑一轮，然后验证页面收到了真实日志。

用 mode 2（监听异常）而不是 mode 1（导出日志），原因：
  · mode 2 每轮只做 3 次 ls，几秒内就能看到结果
  · mode 1 要 pull 6 个目录，可能拉几十 MB，测试会很慢
  · 两者共用同一个引擎骨架，验一个就够
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
  var out = { ok:false, stage:'init', logs:[], states:[], err:null };
  function done(){
    var pre = document.createElement('pre');
    pre.id = 'RESULT';
    pre.textContent = JSON.stringify(out);
    document.body.appendChild(pre);
  }

  // 先挂监听，再启动 —— 否则可能漏掉最早几行日志
  var _origOn = window.onMessage;
  function collect(msg){
    if(!msg) return;
    if(msg.kind === 'autolog') out.logs.push(msg.text + '|' + (msg.lv||''));
    if(msg.kind === 'autostate') out.states.push(msg.state + '|r' + (msg.round||0));
  }
  // 直接拦截 postWebMessage 的落点：C# 用 PostWebMessageAsJson，
  // 页面侧最终会走 chrome.webview 的 message 事件。
  try{
    window.chrome.webview.addEventListener('message', function(e){
      try{
        var m = (typeof e.data === 'string') ? JSON.parse(e.data) : e.data;
        collect(m);
      }catch(err){}
    });
  }catch(e){ out.err = 'addEventListener: ' + e; }

  setTimeout(function(){
    try{
      switchTab('quick');
      // 定位到语音助手分组（定时任务框只在那显示）
      for(var i=0;i<quickGroups.length;i++){
        if(quickGroups[i].name === '语音助手'){ _quickIdx = i; break; }
      }
      renderQuickItems();
      out.stage = 'ui-ready';

      // 用 mode 2，间隔 1 分钟
      document.getElementById('tt-crash-min').value = '1';
      ttStart(2);
      out.stage = 'started';
    }catch(e){ out.err = String(e); done(); return; }

    // 等 9 秒：够引擎跑完第一轮扫描并把日志推回来
    var waited = 0;
    var iv = setInterval(function(){
      waited += 500;
      if(out.logs.length > 0 && waited >= 8000){
        clearInterval(iv);
        out.ok = true;
        out.stage = 'got-logs';

        // 验证暂停
        try{
          ttTogglePause(2);
          out.pausedBtn = document.getElementById('tt-crash-pause').textContent;
          out.pausedState = document.getElementById('tt-crash-state').textContent;
        }catch(e){}

        setTimeout(function(){
          // 验证恢复 + 停止
          try{
            ttTogglePause(2);
            out.resumedState = document.getElementById('tt-crash-state').textContent;
            ttStop(2);
            out.stoppedBtnDisabled =
              document.getElementById('tt-crash-start').disabled === false;
          }catch(e){}
          out.stage = 'done';
          done();
        }, 2500);
        return;
      }
      if(waited >= 14000){
        clearInterval(iv);
        out.stage = 'timeout';
        out.err = '14 秒内没收到 autolog（logs=' + out.logs.length + '）';
        try{ ttStop(2); }catch(e){}
        done();
      }
    }, 500);
  }, 2600);
})();
</script>
"""


def main():
    if not os.path.exists(EXE):
        print("  [SKIP] 找不到 %s，跳过端到端（请先跑 build_gui.bat）" % EXE)
        return 0

    src = open(UI, encoding="utf-8").read()
    tmp = os.path.join(tempfile.gettempdir(), "_tt_uitest.html")
    open(tmp, "w", encoding="utf-8", newline="").write(src.replace("</body>", PROBE + "</body>"))

    try:
        p = subprocess.run([EXE, "--uitest", tmp, "26000"],
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
        print("   stdout 前 700 字：")
        print(out[:700])
        if err.strip():
            print("   stderr：")
            print(err[:400])
        return 2

    try:
        data, _ = json.JSONDecoder().raw_decode(out[i:])
    except Exception as e:
        print("!! JSON 解析失败：%s" % e)
        print(out[i:i+500])
        return 2

    R = []

    def ok(name, cond, extra=""):
        R.append(("PASS" if cond else "FAIL") + " | " + name + ("" if cond else (" -> " + str(extra))))

    ok("页面切到语音助手分组", data.get("stage") not in ("init", "ui-ready"),
       data.get("stage"))
    ok("C# 引擎返回了日志", data.get("ok") is True,
       data.get("err") or data.get("stage"))

    logs = data.get("logs") or []
    ok("收到 autolog 行", len(logs) > 0, len(logs))

    joined = "\n".join(logs)
    ok("日志含启动提示", ("任务已启动" in joined), joined[:150])
    ok("日志含轮次标记", ("第 1 轮" in joined), joined[:200])
    ok("日志含扫描结果（anr=/crash=）",
       re.search(r"anr=\d+", joined) is not None, joined[:250])

    states = data.get("states") or []
    ok("收到状态推送", len(states) > 0, states)

    ok("暂停后按钮变「继续」", data.get("pausedBtn") == "继续", data.get("pausedBtn"))
    ok("暂停后状态为已暂停", data.get("pausedState") == "已暂停", data.get("pausedState"))
    ok("恢复后状态为运行中", data.get("resumedState") == "运行中", data.get("resumedState"))
    ok("停止后开始按钮恢复可用", data.get("stoppedBtnDisabled") is True,
       data.get("stoppedBtnDisabled"))

    print("")
    print("=== C# 引擎真实输出（mode 2 监听异常）===")
    for line in logs[:18]:
        print("  " + line)
    if len(logs) > 18:
        print("  …（共 %d 行）" % len(logs))
    print("")
    print("  状态推送序列：%s" % ", ".join(states[:8]))
    print("")

    for line in R:
        print("  " + line)
    fail = sum(1 for x in R if x.startswith("FAIL"))
    print("")
    print("  定时任务端到端：通过 %d / %d" % (len(R) - fail, len(R)))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
