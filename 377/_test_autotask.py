"""定时任务回归测试（2026-11-22 第 12 批需求 2.1 / 2.2）。

两个 bat 变成界面功能：
  mode 1  定时导出日志（pull_log-iflytek-system.bat）
  mode 2  定时监听异常（check_crash.bat，有新增才导出）

用户明确要求的交互：
  · 间隔可输入（不是写死 30 分钟）
  · 开始之后有「暂停」按钮
  · 导出到桌面 logcat

本测试只验证**页面侧**（按钮状态机、日志渲染、状态同步）。
C# 引擎的行为（暂停冻结倒计时、分段 sleep 可中断）靠代码审查 + 真机验证。

运行：python 377/_test_autotask.py
"""
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")


def _find_edge():
    for c in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
        if os.path.exists(c):
            return c
    return "msedge.exe"


EDGE = _find_edge()

PROBE = r"""
<script>
window.__E=[];window.addEventListener('error',e=>window.__E.push(String(e.message)));
setTimeout(function(){
  var R=[];
  function ok(n,c,e){R.push((c?'PASS':'FAIL')+' | '+n+(c?'':' -> '+(e===undefined?'':e)));}

  /* ---- 1. 两个任务框存在 ---- */
  ok('定时导出日志框存在', !!document.getElementById('tt-log-box'));
  ok('定时监听异常框存在', !!document.getElementById('tt-crash-box'));

  // 2026-11-22（第 15 批）：hint 元素已删除（为压缩高度，信息挪到 title）
  ['log','crash'].forEach(function(k){
    ['min','start','pause','stop','state','out'].forEach(function(f){
      ok('控件存在 '+k+'-'+f, !!document.getElementById('tt-'+k+'-'+f));
    });
  });
  ok('hint 已移除（压高度）', !document.getElementById('tt-log-hint'));

  /* ---- 2. 默认间隔 30 分钟 ---- */
  ok('导出日志默认 30 分钟',
     document.getElementById('tt-log-min').value === '30');
  ok('监听异常默认 30 分钟',
     document.getElementById('tt-crash-min').value === '30');

  /* ---- 3. 初始按钮状态 ---- */
  ok('导出-开始可用', document.getElementById('tt-log-start').disabled === false);
  ok('导出-暂停禁用', document.getElementById('tt-log-pause').disabled === true);
  ok('导出-停止禁用', document.getElementById('tt-log-stop').disabled === true);
  ok('导出-初始状态文字',
     document.getElementById('tt-log-state').textContent === '未启动');

  /* ---- 4. 只在语音助手分组显示 ---- */
  // 找「语音助手」分组并渲染（真实函数名是 renderQuickItems，靠 _quickIdx 定位分组）
  var vrIdx = -1;
  for(var i=0;i<quickGroups.length;i++) if(quickGroups[i].name==='语音助手') vrIdx=i;
  ok('存在语音助手分组', vrIdx >= 0);
  if(vrIdx >= 0){
    _quickIdx = vrIdx;
    _quickFilter = '';
    renderQuickItems();
    // 2026-11-22 第 2 版：显隐挂在 .tt-row2 容器上（两个框外面那层网格），
    // 不再单独控制 tt-log-box / tt-crash-box。
    ok('语音助手分组显示任务框',
       document.getElementById('tt-row2').style.display !== 'none',
       document.getElementById('tt-row2').style.display);
  }
  // 切到别的分组应隐藏
  for(var j=0;j<quickGroups.length;j++){
    if(quickGroups[j].name==='指令执行'){
      _quickIdx = j; renderQuickItems(); break;
    }
  }
  ok('其它分组隐藏任务框',
     document.getElementById('tt-row2').style.display === 'none',
     document.getElementById('tt-row2').style.display);

  /* ---- 5. 启动：按钮状态机 ---- */
  // headless Edge 没有 WebView2 的 chrome.webview 对象，postObj 会静默失败。
  // 这里先把它造出来，才能观察到页面发出的消息。
  var sent = [];
  window.chrome = window.chrome || {};
  window.chrome.webview = { postMessage: function(o){ sent.push(o); } };
  var _op = window.chrome.webview.postMessage;

  document.getElementById('tt-log-min').value = '15';
  ttStart(1);

  ok('启动后开始按钮禁用',
     document.getElementById('tt-log-start').disabled === true);
  ok('启动后暂停按钮可用',
     document.getElementById('tt-log-pause').disabled === false);
  ok('启动后停止按钮可用',
     document.getElementById('tt-log-stop').disabled === false);
  ok('启动后状态为运行中',
     document.getElementById('tt-log-state').textContent === '运行中',
     document.getElementById('tt-log-state').textContent);

  var startMsg = null;
  for(var s=0;s<sent.length;s++) if(sent[s].kind==='autostart') startMsg = sent[s];
  ok('发出了 autostart 消息', !!startMsg, JSON.stringify(sent));
  if(startMsg){
    ok('autostart 带 mode=1', startMsg.mode === 1, startMsg.mode);
    ok('autostart 带 minutes=15（用了输入值）', startMsg.minutes === 15, startMsg.minutes);
  }

  /* ---- 6. 暂停 / 继续 ---- */
  sent.length = 0;
  ttTogglePause(1);
  ok('暂停后按钮文字变「继续」',
     document.getElementById('tt-log-pause').textContent === '继续',
     document.getElementById('tt-log-pause').textContent);
  ok('暂停后状态为已暂停',
     document.getElementById('tt-log-state').textContent === '已暂停');
  ok('发出了 autopause', sent.some(function(m){ return m.kind==='autopause'; }),
     JSON.stringify(sent));

  sent.length = 0;
  ttTogglePause(1);
  ok('继续后按钮文字回「暂停」',
     document.getElementById('tt-log-pause').textContent === '暂停');
  ok('继续后状态为运行中',
     document.getElementById('tt-log-state').textContent === '运行中');
  ok('发出了 autoresume', sent.some(function(m){ return m.kind==='autoresume'; }),
     JSON.stringify(sent));

  /* ---- 7. 日志渲染 ---- */
  ttLog(1, '第 1 行测试日志', '');
  ttLog(1, '[OK] 没有异常文件', 'ok');
  ttLog(1, '跳过某目录', 'warn');
  var outBox = document.getElementById('tt-log-out');
  ok('日志行已渲染', outBox.children.length === 3, outBox.children.length);
  ok('日志内容正确',
     outBox.textContent.indexOf('第 1 行测试日志') >= 0, outBox.textContent.slice(0,60));

  // 颜色：ok/warn 应各不同
  var colorOk = outBox.children[1].style.color;
  var colorWarn = outBox.children[2].style.color;
  ok('ok 行有颜色', colorOk.length > 0, colorOk);
  ok('warn 行有颜色', colorWarn.length > 0, colorWarn);
  /* 2026-11-23（第 21 批）：用户要求"成功也改强调色"，
     ok 与 warn 现在都是 var(--accent)。
     这里不再要求两者不同色，但要求**都不是绿色**（绿色已全量替换）。
     ⚠ 副作用已记录：ok 和 warn 同色后只能靠文字/图标区分，
       如果用户需要区分，warn 应另给一个语义色（如橙）。 */
  ok('ok/warn 已统一为强调色（非绿）',
     colorOk.indexOf('--accent') >= 0 && colorWarn.indexOf('--accent') >= 0,
     colorOk + ' vs ' + colorWarn);

  // 行数上限（跑几小时不能撑爆内存）
  for(var n=0;n<350;n++) ttLog(1, '填充行 ' + n, '');
  ok('日志行数封顶 300', outBox.children.length <= 300, outBox.children.length);

  /* ---- 8. 状态同步（C# → 页面）---- */
  ttOnState({kind:'autostate', state:'running', mode:1, minutes:15, round:3,
             remain:125, dir:'C:\\Users\\x\\Desktop\\logcat\\2026-11-22\\x_Log'});
  // 2026-11-22（第 15 批）：hint 元素删除后，信息挂在 title 上
  var minTitle = document.getElementById('tt-log-min').title || '';
  ok('状态同步：轮次挂到 title', minTitle.indexOf('第 3 轮') >= 0, minTitle);
  ok('状态同步：倒计时挂到 title',
     /2 分 5 秒|125 秒/.test(minTitle), minTitle);

  ttOnState({kind:'autostate', state:'paused', mode:1, round:3, remain:0});
  ok('同步暂停态',
     document.getElementById('tt-log-state').textContent === '已暂停');
  ok('同步暂停态按钮文字',
     document.getElementById('tt-log-pause').textContent === '继续');

  ttOnState({kind:'autostate', state:'idle', mode:1, round:3, remain:0});
  ok('同步停止态后开始按钮恢复',
     document.getElementById('tt-log-start').disabled === false);
  ok('同步停止态后暂停禁用',
     document.getElementById('tt-log-pause').disabled === true);
  ok('同步停止态文字',
     document.getElementById('tt-log-state').textContent === '已停止');

  /* ---- 9. 模式 2 独立工作 ---- */
  ttStart(2);
  ok('模式2 启动后暂停可用',
     document.getElementById('tt-crash-pause').disabled === false);
  ok('模式1 不受模式2 影响',
     document.getElementById('tt-log-start').disabled === false,
     '模式1 start disabled=' + document.getElementById('tt-log-start').disabled);
  ttStop(2);
  ok('模式2 停止后开始恢复',
     document.getElementById('tt-crash-start').disabled === false);

  /* ---- 10. 间隔校验 ---- */
  document.getElementById('tt-log-min').value = '0';
  var before = document.getElementById('tt-log-start').disabled;
  ttStart(1);
  ok('间隔 0 被拒绝（仍可再次点击）',
     document.getElementById('tt-log-start').disabled === before);

  document.getElementById('tt-log-min').value = '999';
  ttStart(1);
  ok('间隔 999 被拒绝',
     document.getElementById('tt-log-start').disabled === false);

  // 恢复 postMessage 并清理定时器
  try{
    if(window.chrome && window.chrome.webview && _op)
      window.chrome.webview.postMessage = _op;
  }catch(e){}
  ttStopLocal(1); ttStopLocal(2);

  ok('无运行时错误', window.__E.length===0, window.__E.join('; '));

  var pre=document.createElement('pre');
  pre.id='TT_RESULT';
  pre.textContent=JSON.stringify(R);
  document.body.appendChild(pre);
}, 1800);
</script>
"""


def main():
    src = open(UI, encoding="utf-8").read()
    tmp = os.path.join(ROOT, "377", "_tt.html")
    open(tmp, "w", encoding="utf-8", newline="").write(src.replace("</body>", PROBE + "</body>"))
    try:
        p = subprocess.run(
            [EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--no-first-run", "--no-default-browser-check",
             "--disable-background-networking", "--disable-sync",
             "--disable-extensions", "--disable-component-update",
             "--user-data-dir=" + os.path.join(tempfile.gettempdir(), "edgeprof_tt"),
             "--window-size=1400,900", "--virtual-time-budget=14000", "--dump-dom",
             "file:///" + tmp.replace("\\", "/")],
            capture_output=True, timeout=180)
        dom = p.stdout.decode("utf-8", "replace")
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass

    m = re.search(r'<pre id="TT_RESULT">(.*?)</pre>', dom, re.S)
    if not m:
        print("!! 探针未返回")
        for mm in re.finditer(r"(Uncaught[^<\n]{0,200})", dom):
            print("   ", mm.group(1))
        return 2

    results = json.loads(m.group(1))
    for line in results:
        print("  " + line)
    fail = sum(1 for r in results if r.startswith("FAIL"))
    print("")
    print("  定时任务：通过 %d / %d" % (len(results) - fail, len(results)))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
