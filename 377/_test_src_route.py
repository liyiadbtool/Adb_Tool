"""需求3 专项：在快捷指令页用键盘敲命令，输出必须落在**看得见的反馈区**。

为什么单独测这一条：
  用户的原话是「r指令刷新的时候要把打开应用要获取的数据和执行的执行都操作下输出显示」。
  这里有个特别容易漏的分支 —— 他不是点卡片，而是在「快捷指令」页用键盘敲 r。
  历史上这条路径会走 source=0，输出被送进另一个页签的 logbox，用户看到的
  就是"敲了 r 一点反应都没有"。修的时候连续踩了三个坑，都用本脚本锁住：

  坑A 前端没把当前页签带上去          -> 后端无从判断该往哪推
  坑B var _tab 声明晚于 switchTab     -> 初始化赋值被 ='cmd' 覆盖，永远当成指令输入页
  坑C 反馈区没有 _curOutEl 占位行     -> appendOut 直接 return，整段输出静默丢弃

运行：python 377/_test_src_route.py
"""
import os
import tempfile
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
TEST = os.path.join(ROOT, "377", "test_src_route.html")
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
# 2026-11-22：支持通过环境变量指定独立的浏览器 profile 目录。
# 目的：让 verify_all.py 能**并行**跑多个套件（它们共用同一个 profile 时会争抢锁，
# 串行必须 sleep 等待，实测 3 套串行 13.7s、并行只有 4.8s）。
# 不设该变量时行为与原来完全一致（仍落 edgeprof_beh），单独跑测试不受影响。
PROF = os.environ.get("UI_PROF") or os.path.join(tempfile.gettempdir(), "edgeprof_beh")
BEHAVIOR = r"""
<script>
(function(){
  var R = [];
  function ok(name, cond, extra){
    R.push((cond ? 'PASS' : 'FAIL') + ' | ' + name + (cond ? '' : ' | ' + (extra===undefined?'':extra)));
  }

  // 拦截发往 C# 的消息，检查 src 字段有没有真的带出去。
  // 注意：headless Edge 里没有 WebView2，window.chrome / chrome.webview 都不存在，
  // 直接给 window.chrome.webview.postMessage 赋值会 TypeError（被 post 内部的
  // try/catch 吞掉，于是 sent 永远为空 —— 看起来像"前端没发消息"，其实是打桩失败）。
  // 所以必须逐层把对象建出来再挂方法。
  var sent = [];
  window.__sent = sent;
  try{
    window.chrome = window.chrome || {};
    window.chrome.webview = window.chrome.webview || {};
    window.chrome.webview.postMessage = function(o){ sent.push(o); };
  }catch(e){}

  function rows(){ return document.querySelectorAll('#fb-table .fb-row'); }
  function lastRow(){ var r = rows(); return r.length ? r[r.length-1] : null; }

  function main(){
    try{
      // ---------- 坑B：_tab 的初始值不能被覆盖 ----------
      // switchTab('cmd') 在初始化时被调用过，如果 var _tab='cmd' 声明在后面，
      // 这里读到的会是 'cmd' 而"当前真的是 cmd" —— 分辨不出来。
      // 所以直接切到 quick 再读，确认赋值链是通的。
      switchTab('quick');
      ok('快捷指令页 _tab 跟随切换', _tab === 'quick', _tab);
      switchTab('cmd');
      ok('切回指令输入页 _tab 跟随切换', _tab === 'cmd', _tab);
      switchTab('quick');

      // ---------- 坑A：键盘输入必须把当前页签带给后端 ----------
      sent.length = 0;
      var inp = document.getElementById('cmd-input-0');
      inp.value = 'r';
      run(0);
      ok('快捷指令页敲命令会发出 cmd 消息', sent.length === 1, JSON.stringify(sent));
      var m = sent[0] || {};
      ok('  kind 是 cmd', m.kind === 'cmd', m.kind);
      ok('  data 是 r', m.data === 'r', m.data);
      ok('  src=1（输出进反馈区）', m.src === 1, JSON.stringify(m));

      // ---------- 坑C：反馈区必须先建占位行，否则输出无处可落 ----------
      ok('  占位记录已创建', rows().length === 1, rows().length);
      ok('  _curOutEl 已指向该记录右栏', !!_curOutEl, String(_curOutEl));
      if(_curOutEl){
        ok('  右栏挂了这条记录', _curOutEl.parentNode === lastRow(), '');
        ok('  占位态显示"执行中"', (_curOutEl.textContent||'').indexOf('执行中') >= 0,
           _curOutEl.textContent);
      }
      var lr = lastRow();
      if(lr){
        ok('  左栏指令写的是 r', lr.querySelector('.c').textContent === 'r',
           lr.querySelector('.c').textContent);
        ok('  时间已填（非空）', (lr.querySelector('.fb-meta .t').textContent||'').length === 8,
           lr.querySelector('.fb-meta .t').textContent);
        ok('  耗时显示占位 —', lr.querySelector('.fb-meta .d').textContent === '—',
           lr.querySelector('.fb-meta .d').textContent);
      }

      // ---------- 输出真的落到这条记录里（模拟 C# 推回来的 src=1 行） ----------
      var payload = [
        {kind:'line', level:0, src:1, text:'车型          181'},
        {kind:'line', level:0, src:1, text:'SOC 版本      GAC_T68_IDC_S1B3'},
        {kind:'line', level:1, src:1, text:'√ 车机信息已刷新'}
      ];
      for(var i=0;i<payload.length;i++){
        onMessage({data:payload[i]});
      }
      var outTxt = _curOutEl ? _curOutEl.textContent : '';
      ok('需求3 九项输出进入了反馈区右栏',
         outTxt.indexOf('车型') >= 0 && outTxt.indexOf('SOC 版本') >= 0, outTxt.slice(0,120));
      ok('需求3 成功行用绿色语义类', (function(){
        var okEls = _curOutEl ? _curOutEl.querySelectorAll('.o-ok') : [];
        return okEls.length === 1;
      })(), '');
      ok('需求3 "执行中"占位被真实的输出替换',
         outTxt.indexOf('执行中') < 0, outTxt.slice(0,120));

      // ---------- 指令输入页：输出留在本页 logbox，不跳页 ----------
      // 2026-11-13 曾改成"回车后自动跳快捷指令页"，用下来是反效果（连续敲命令会被弹走），
      // 已回退：在哪个页面敲，输出就留在哪个页面。
      switchTab('cmd');
      sent.length = 0;
      _busy[0] = false;          // 模拟上一条 end 已回执（需求9 互斥会拦截忙时输入）
      inp.value = 'ls';
      run(0);
      var m2 = sent[0] || {};
      ok('主输入框命令走 src=0', m2.src === 0, JSON.stringify(m2));
      ok('主输入框不建反馈区占位', rows().length === 1, rows().length);
      ok('执行后仍停在指令输入页', _tab === 'cmd', _tab);

      var beforeLog = document.querySelectorAll('#logbox-0 .ln').length;
      onMessage({data:{kind:'line', level:0, src:0, text:'init  system  vendor'}});
      var afterLog = document.querySelectorAll('#logbox-0 .ln').length;
      ok('src=0 的输出进 logbox', afterLog === beforeLog + 1, beforeLog + '->' + afterLog);

      // ---------- 收尾：end 回执要把占位行改成真实结果 ----------
      switchTab('quick');
      _busy[0] = false;
      inp.value = 'r';
      run(0);
      var r2 = lastRow();
      onMessage({data:{kind:'end', ok:true, ms:128,
        feed:{time:'20:30:00', cmd:'r', ok:true, ms:128}}});
      ok('end 回执后徽章变"成功"',
         r2.querySelector('.fb-meta .badge').textContent === '成功',
         r2.querySelector('.fb-meta .badge').textContent);
      ok('end 回执后显示真实耗时',
         r2.querySelector('.fb-meta .d').textContent === '128 ms',
         r2.querySelector('.fb-meta .d').textContent);
      ok('end 回执后记录带成功色', r2.classList.contains('ok'), r2.className);
      // 这条命令没有产生任何输出行，end 之后右栏应当如实显示"（无输出）"，
      // 而不是留一个"执行中"或者空壳 —— 这是 finalizeRow 的职责。
      ok('end 之后无输出的记录标注（无输出）',
         r2.querySelector('.fb-right').textContent.indexOf('（无输出）') >= 0,
         r2.querySelector('.fb-right').textContent);
      ok('end 之后不留"执行中"占位',
         r2.querySelector('.fb-right').textContent.indexOf('执行中') < 0, '');

      // 有输出的情况：end 不能把已经写进去的输出抹掉（问题4 的核心诉求）
      switchTab('quick');
      _busy[0] = false;
      inp.value = 'ls';
      run(0);
      var r3 = lastRow();
      onMessage({data:{kind:'line', level:0, src:1, text:'init'}});
      onMessage({data:{kind:'line', level:0, src:1, text:'vendor'}});
      onMessage({data:{kind:'end', ok:true, ms:42,
        feed:{time:'20:31:00', cmd:'ls', ok:true, ms:42}}});
      var t3 = r3.querySelector('.fb-right').textContent;
      ok('end 之后已有输出原样保留',
         t3.indexOf('init') >= 0 && t3.indexOf('vendor') >= 0, t3);
      ok('end 之后没有误加（无输出）', t3.indexOf('（无输出）') < 0, t3);

    }catch(e){
      R.push('FAIL | 测试脚本异常 | ' + e.message + ' @ ' + (e.stack||'').split('\n')[1]);
    }

    var pre = document.createElement('pre');
    pre.id = 'RESULT';
    pre.textContent = R.join('\n');
    document.body.appendChild(pre);
  }

  setTimeout(main, 300);
})();
</script>
"""


def main():
    src = open(UI, encoding="utf-8").read()
    out = src.replace("</body>", BEHAVIOR + "</body>")
    open(TEST, "w", encoding="utf-8").write(out)

    url = "file:///" + TEST.replace("\\", "/")
    cmd = [
        EDGE, "--headless=new", "--disable-gpu",
        "--window-size=1180,820",
        "--virtual-time-budget=5000",
        "--dump-dom",
        "--user-data-dir=", "--no-first-run", "--no-default-browser-check", "--disable-background-networking", "--disable-sync", "--disable-extensions", "--disable-component-update" + PROF,
        url,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=90)
    dom = r.stdout or ""
    m = re.search(r'<pre id="RESULT">(.*?)</pre>', dom, re.S)
    if not m:
        print("没拿到 RESULT，DOM 长度", len(dom))
        print(dom[:800])
        return 1

    lines = [l for l in m.group(1).split("\n") if l.strip()]
    fails = [l for l in lines if l.startswith("FAIL")]
    for l in lines:
        print("  " + l)
    print("")
    print("  通过 %d / %d" % (len(lines) - len(fails), len(lines)))
    if fails:
        print("  有 %d 项失败" % len(fails))
        return 1
    print("  需求3（输出跟着页签走）全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
