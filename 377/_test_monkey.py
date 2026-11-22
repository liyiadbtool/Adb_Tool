"""Monkey 稳定性测试页回归测试（2026-11-22 第 10 批需求）。

用户需求：「tab 栏新增 Monkey 集成 Fastbot 功能」。

实现策略（方案 C）：
  第一版用 Android 系统自带的 `adb shell monkey` 跑通链路，
  先把「配置 → 下发 → 实时回显 → 结果收集」验证扎实。
  Fastbot 官方仓库不提供预编译 jar（需自建 NDK+gradle 才能编出 monkeyq.jar），
  在被前置条件卡住之前先把架构定下来 —— jar 到位后只需替换 mkBuildCmd()
  里的命令字符串，界面与输出链路完全不动。

本套件钉住的关键点：
  1. 页签出现在正确位置（末尾追加，不打乱既有三个）
  2. 页面容器存在且可切换
  3. 配置控件齐全（包名/时长/间隔/策略/verbose/忽略开关）
  4. 命令拼接正确（含 -p 包名、--throttle、--ignore-*、-v 层数）
  5. 输出路由走 src=4，不污染终端页 logbox
  6. 崩溃/ANR 计数能从输出里识别

运行：python 377/_test_monkey.py
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
    for c in (r"C://Program Files (x86)//Microsoft//Edge//Application//msedge.exe",
              r"C://Program Files//Microsoft//Edge//Application//msedge.exe",
              r"C://Program Files//Google//Chrome//Application//chrome.exe"):
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

  /* ---- 1. 页签 ---- */
  var tabs=document.querySelectorAll('.tabs .tab');
  var order=[];
  for(var i=0;i<tabs.length;i++) order.push(tabs[i].getAttribute('data-tab'));
  ok('Monkey 页签已加入', order.indexOf('monkey')>=0, order.join(','));
  ok('Monkey 是最后一个页签', order[order.length-1]==='monkey', order.join(','));
  ok('既有三页顺序未变', order.slice(0,3).join(',')==='quick,cmd,file', order.join(','));

  var mkTab=null;
  for(var j=0;j<tabs.length;j++) if(tabs[j].getAttribute('data-tab')==='monkey') mkTab=tabs[j];
  ok('页签文字为 Monkey', mkTab && mkTab.textContent.trim()==='Monkey',
     mkTab?mkTab.textContent.trim():'无');

  /* ---- 2. 页面容器与切换 ---- */
  var page=document.getElementById('page-monkey');
  ok('page-monkey 容器存在', !!page);
  if(mkTab){ mkTab.click(); }
  setTimeout(function(){
    ok('点击后页面激活', page && page.classList.contains('active'),
       page?page.className:'无');
    ok('其它页面已失活',
       !document.getElementById('page-quick').classList.contains('active'));

    /* ---- 3. 配置控件 ---- */
    var need=['mk-pkg','mk-minutes','mk-throttle','mk-count','mk-seed',
              'mk-type','mk-verbose','mk-ignore-crash','mk-start','mk-stop',
              'mk-out','mk-st-crash','mk-st-anr','mk-st-events','mk-st-elapsed'];
    var miss=[];
    for(var k=0;k<need.length;k++) if(!document.getElementById(need[k])) miss.push(need[k]);
    ok('配置控件齐全', miss.length===0, miss.join(','));

    ok('时长默认 30 分钟',
       (document.getElementById('mk-minutes')||{}).value==='30',
       (document.getElementById('mk-minutes')||{}).value);
    ok('停止按钮初始禁用',
       (document.getElementById('mk-stop')||{}).disabled===true);

    /* ---- 4. 命令拼接 ---- */
    document.getElementById('mk-pkg').value='com.test.demo';
    document.getElementById('mk-minutes').value='5';
    document.getElementById('mk-throttle').value='200';
    document.getElementById('mk-count').value='0';
    var cmd=mkBuildCmd();
    ok('命令含包名', /-p com\.test\.demo/.test(cmd||''), cmd);
    ok('命令含 throttle', /--throttle 200/.test(cmd||''), cmd);
    ok('命令含 --ignore-crashes', /--ignore-crashes/.test(cmd||''), cmd);
    ok('命令含 --ignore-timeouts', /--ignore-timeouts/.test(cmd||''), cmd);
    ok('命令含 -v -v（详细日志）', /-v -v/.test(cmd||''), cmd);

    mkSetVerbose('1');
    ok('verbose=1 时只有一个 -v', /-v$/.test(mkBuildCmd()||''), mkBuildCmd());
    mkSetVerbose('2');

    mkSetType('5');
    ok('触摸策略含 --pct-touch', /--pct-touch/.test(mkBuildCmd()||''), mkBuildCmd());
    mkSetType('15');
    ok('全部策略不含 pct 限制', !/--pct-touch 0/.test(mkBuildCmd()||''));

    /* ---- 5. 输出路由 src=4 ---- */
    var box=document.getElementById('mk-out');
    ok('输出区初始为空态', !!box.querySelector('.mk-empty'));

    mkOnOut({text:'Monkey: seed=1 count=100'});
    ok('普通输出已追加', box.textContent.indexOf('seed=1')>=0);

    mkOnOut({text:'Events injected: 42'});
    ok('事件数已统计',
       document.getElementById('mk-st-events').textContent==='42',
       document.getElementById('mk-st-events').textContent);

    mkOnOut({text:'CRASH: com.test.demo'});
    ok('崩溃已计数',
       document.getElementById('mk-st-crash').textContent==='1',
       document.getElementById('mk-st-crash').textContent);

    mkOnOut({text:'NOT RESPONDING: com.test.demo'});
    ok('ANR 已计数',
       document.getElementById('mk-st-anr').textContent==='1',
       document.getElementById('mk-st-anr').textContent);

    ok('终端页未被污染',
       (document.getElementById('logbox-0')||{textContent:''}).textContent.indexOf('CRASH:')<0);

    /* ---- 6. 清空 ---- */
    mkClear();
    ok('清空后回到空态', !!box.querySelector('.mk-empty'));
    ok('清空后统计归零',
       document.getElementById('mk-st-crash').textContent==='0' &&
       document.getElementById('mk-st-anr').textContent==='0');

    ok('无运行时错误', window.__E.length===0, window.__E.join('; '));
    try {
      var pre=document.createElement('pre');
      pre.id='MONKEY_RESULT';
      pre.textContent=JSON.stringify(R);
      document.body.appendChild(pre);
    } catch(je){ window.__E.push('序列化异常: '+je); }
  }, 500);
}, 1500);
</script>
"""


def main():
    src = open(UI, encoding="utf-8").read()
    tmp = os.path.join(ROOT, "377", "_mk.html")
    open(tmp, "w", encoding="utf-8", newline="").write(src.replace("</body>", PROBE + "</body>"))
    try:
        p = subprocess.run(
            [EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--no-first-run", "--no-default-browser-check",
             "--disable-background-networking", "--disable-sync",
             "--disable-extensions", "--disable-component-update",
             "--user-data-dir=" + os.path.join(tempfile.gettempdir(), "edgeprof_monkey"),
             "--window-size=1280,900", "--virtual-time-budget=10000", "--dump-dom",
             "file:///" + tmp.replace("\\", "/")],
            capture_output=True, timeout=150)
        dom = p.stdout.decode("utf-8", "replace")
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass

    m = re.search(r'<pre id="MONKEY_RESULT">(.*?)</pre>', dom, re.S)
    if not m:
        print("!! 探针未返回")
        for mm in re.finditer(r"(Uncaught[^<\n]{0,160})", dom):
            print("   ", mm.group(1))
        return 2

    raw = m.group(1)
    try:
        results = json.loads(raw)
    except Exception as e:
        print('!! JSON 解析失败:', e)
        print('   原始长度:', len(raw))
        print('   前 400 字:', raw[:400])
        return 2
    for line in results:
        print("  " + line)
    fail = sum(1 for r in results if r.startswith("FAIL"))
    print("")
    print("  Monkey 页：通过 %d / %d" % (len(results) - fail, len(results)))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
