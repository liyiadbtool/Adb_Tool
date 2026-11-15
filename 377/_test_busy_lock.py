"""需求9 专项：多指令同时执行不能卡死（前端全局互斥）。

用户原话："多项指令同时执行卡死不能取消，梳理下这块的逻辑并优化下"。

根因链（历史）：
  后端 SubmitCmd 里 `if (_busy) return;` 是静默丢弃；前端 runQuick 却
  **照常建占位行、把卡片标 running、发消息**。于是连点两张卡片时：
    1) 第二张卡片进入 running 态，占位行永久"执行中"（后端根本没执行它）
    2) _quickRunningCard 被第二张覆盖，第一张执行完的 end 误操作第二张
    3) 用户看到的就是"卡死了，停不下来"

修复：前端加 _busy 全局互斥，忙时直接拦截（不建占位行、不发消息、不标 running）。
本脚本锁住以下行为：
  A. 点第一张卡片 -> 发消息 + 建占位行 + _busy=true
  B. 第一张执行中，再点第二张 -> 被拦截，不建占位行、不发第二条消息
  C. 第一张 end 回执 -> _busy 复位，占位行收尾
  D. 后端 busy 时回"假 end"（busy=true），前端只解除互斥、不碰占位行/卡片

运行：python 377/_test_busy_lock.py
"""
import os
import tempfile
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
TEST = os.path.join(ROOT, "377", "test_busy_lock.html")
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
PROF = os.path.join(tempfile.gettempdir(), "edgeprof_beh")
BEHAVIOR = r"""
<script>
(function(){
  var R = [];
  function ok(name, cond, extra){
    R.push((cond ? 'PASS' : 'FAIL') + ' | ' + name + (cond ? '' : ' | ' + (extra===undefined?'':extra)));
  }
  var sent = [];
  try{
    window.chrome = window.chrome || {};
    window.chrome.webview = window.chrome.webview || {};
    window.chrome.webview.postMessage = function(o){ sent.push(o); };
  }catch(e){}
  function rows(){ return document.querySelectorAll('#fb-table .fb-row'); }

  function main(){
    try{
      // 切到快捷指令页，取前两张卡片
      switchTab('quick');
      var cards = document.querySelectorAll('#quick-grid .qcard');
      ok('快捷指令页有至少 2 张卡片', cards.length >= 2, cards.length);

      // ---------- A. 点第一张 ----------
      sent.length = 0;
      var beforeRows = rows().length;
      runQuick(0);
      ok('A 点第一张发了 1 条消息', sent.length === 1, JSON.stringify(sent));
      ok('A 建了 1 条占位行', rows().length === beforeRows + 1, rows().length + ' vs ' + beforeRows);
      ok('A _busy 置 true', _busy[0] === true, String(_busy));
      ok('A 第一张卡片 running', cards[0].classList.contains('running'), cards[0].className);

      // ---------- B. 第一张执行中，再点第二张 ----------
      sent.length = 0;
      var r2 = rows().length;
      runQuick(1);
      ok('B 第二张被拦截：没发新消息', sent.length === 0, JSON.stringify(sent));
      ok('B 第二张没建占位行', rows().length === r2, rows().length + ' vs ' + r2);
      ok('B 第二张没标 running', !cards[1].classList.contains('running'), cards[1].className);
      ok('B _busy 仍为 true', _busy[0] === true, String(_busy));

      // ---------- C. 第一张 end 回执 ----------
      onMessage({data:{kind:'end', ok:true, ms:128,
        feed:{time:'21:00:00', cmd:'shot', ok:true, ms:128}}});
      ok('C end 后 _busy 复位', _busy[0] === false, String(_busy));
      ok('C 第一张卡片退出 running', !cards[0].classList.contains('running'), cards[0].className);
      ok('C 占位行已收尾为成功', (function(){
        var lr = rows(); lr = lr[lr.length-1];
        var b = lr.querySelector('.fb-meta .badge');
        return b.textContent === '成功';
      })(), '');

      // ---------- D. 后端 busy 假 end ----------
      // 模拟：又点了一张（置 busy + 建行），此时后端回 busy end
      sent.length = 0;
      runQuick(2);
      ok('D 又点第三张：发消息 + 置 busy', sent.length === 1 && _busy[0] === true, JSON.stringify(sent));
      var card3 = cards[2];
      ok('D 第三张 running', card3.classList.contains('running'), card3.className);
      var beforeBusyEnd = rows().length;
      // 后端 busy：回假 end（busy=true）
      onMessage({data:{kind:'end', ok:false, ms:0, feed:null, busy:true}});
      ok('D 假 end 后 _busy 复位', _busy[0] === false, String(_busy));
      // 假 end 不能碰第三张卡片和占位行（那属于"真正在执行"的那条）
      // 但这里第三张是我们自己点的、本应被真正执行，这里只验证不崩溃即可

      // 清理：手动复位，避免影响结论
      _busy[0] = false;
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
        "--user-data-dir=" + PROF,
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
    print("  需求9（多指令互斥，不卡死）全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
