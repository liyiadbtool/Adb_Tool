"""无线 adb 顶栏控件（2026-11-13）的 DOM 行为测试。

覆盖：
  1) 按钮位置在 root 胶囊右边
  2) 浮层开合、Esc 关闭
  3) 连接发消息（act=connect + host）
  4) 连接成功：按钮变绿、显示 IP、浮层关闭
  5) 连接失败：显示后端给的原因，不假装成功
  6) 断开：发 act=disconnect
  7) 切换过程中按钮 busy、不可重复点

运行：python _test_wadb_ui.py
"""
import os
import tempfile
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
TEST = os.path.join(ROOT, "377", "test_wadb_ui.html")
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
PROF = os.path.join(tempfile.gettempdir(), "edgeprof_wadb")
JS = r"""
<script>
(function(){
  var R = [];
  function ok(name, cond, extra){
    R.push((cond ? 'PASS' : 'FAIL') + ' | ' + name + (cond ? '' : ' | ' + (extra===undefined?'':extra)));
  }
  function textOf(id){ var e=document.getElementById(id); return e ? (e.textContent||'') : ''; }

  var SENT = [];
  try{
    window.chrome = window.chrome || {};
    window.chrome.webview = {
      postMessage: function(o){ SENT.push(o); },
      addEventListener: function(){}
    };
  }catch(e){}
  function lastSent(kind){
    for(var i=SENT.length-1;i>=0;i--) if(SENT[i] && SENT[i].kind === kind) return SENT[i];
    return null;
  }

  function run(){
    try{
      setStatus({dev:'b09acfa2', online:true, rooted:true});

      // ---------- 1. 位置 ----------
      var top = document.getElementById('tb-status') || document.querySelector('.titlebar');
      var kids = top.children;
      var rootIdx = -1, wadbIdx = -1;
      for(var i=0;i<kids.length;i++){
        if(kids[i].id === 'root-pill') rootIdx = i;
        if(kids[i].id === 'wadb') wadbIdx = i;
      }
      ok('顶栏有无线控件', wadbIdx >= 0, wadbIdx);
      ok('无线控件紧挨 ROOT 右边', wadbIdx === rootIdx + 1, rootIdx + '->' + wadbIdx);
      ok('默认文案是「无线」', textOf('wadb-txt') === '无线', textOf('wadb-txt'));
      ok('默认不是绿色（未连接）', !document.getElementById('wadb-btn').classList.contains('on'));

      // ---------- 2. 浮层 ----------
      toggleWadb({stopPropagation:function(){}});
      ok('点开浮层', document.getElementById('wadb-pop').style.display === 'flex',
         document.getElementById('wadb-pop').style.display);
      onWadbKey({key:'Escape', preventDefault:function(){}});
      ok('Esc 关闭浮层', document.getElementById('wadb-pop').style.display === 'none');

      // ---------- 3. 连接 ----------
      toggleWadb({stopPropagation:function(){}});
      document.getElementById('wadb-host').value = '192.168.1.7';
      wadbConnect();
      var m = lastSent('wadb');
      ok('发出 connect 消息', !!m && m.act === 'connect' && m.host === '192.168.1.7', JSON.stringify(m));
      ok('连接中按钮 busy', document.getElementById('wadb-btn').classList.contains('busy'));
      ok('连接中按钮文案', textOf('wadb-txt') === '连接中…', textOf('wadb-txt'));
      ok('连接中禁止重复点', document.getElementById('wadb-connect').disabled);

      // 重复点不重复发
      var n = SENT.length;
      wadbConnect();
      ok('忙时重复点不再发消息', SENT.length === n, SENT.length - n);

      // ---------- 4. 成功 ----------
      onWadb({kind:'wadb', ok:true, ip:'192.168.1.7:5555', msg:''});
      ok('成功后按钮变绿', document.getElementById('wadb-btn').classList.contains('on'));
      ok('成功后显示 IP', textOf('wadb-txt') === '192.168.1.7:5555', textOf('wadb-txt'));
      ok('成功后浮层关闭', document.getElementById('wadb-pop').style.display === 'none');
      ok('成功后按钮不再 busy', !document.getElementById('wadb-btn').classList.contains('busy'));

      // ---------- 5. 失败 ----------
      onWadb({kind:'wadb', ok:false, ip:'', msg:'取不到设备 IP，请手动填'});
      ok('失败原因显示在浮层提示里',
         textOf('wadb-tip').indexOf('取不到设备 IP') >= 0, textOf('wadb-tip'));
      ok('失败提示是错误色',
         document.getElementById('wadb-tip').classList.contains('err'));
      ok('失败不清掉已有连接状态',
         document.getElementById('wadb-btn').classList.contains('on') && textOf('wadb-txt') === '192.168.1.7:5555',
         textOf('wadb-txt'));

      // ---------- 6. 断开 ----------
      toggleWadb({stopPropagation:function(){}});
      wadbDisconnect();
      var d = lastSent('wadb');
      ok('发出 disconnect 消息', !!d && d.act === 'disconnect' && d.host === '192.168.1.7:5555', JSON.stringify(d));
      onWadb({kind:'wadb', ok:true, ip:'', msg:''});
      ok('断开后按钮不再绿色', !document.getElementById('wadb-btn').classList.contains('on'));
      ok('断开后回到「无线」', textOf('wadb-txt') === '无线', textOf('wadb-txt'));

    }catch(e){
      ok('运行异常', false, e.message);
    }

    var pre = document.createElement('pre');
    pre.id = 'RESULT';
    pre.textContent = R.join('\n');
    document.body.appendChild(pre);
  }
  setTimeout(run, 300);
})();
</script>
"""


def main():
    win = os.environ.get("UI_WIN", "1100,760")
    src = open(UI, encoding="utf-8").read()
    open(TEST, "w", encoding="utf-8").write(src.replace("</body>", JS + "</body>"))

    url = "file:///" + TEST.replace("\\", "/")
    cmd = [
        EDGE, "--headless=new", "--disable-gpu",
        "--window-size=", "--no-first-run", "--no-default-browser-check", "--disable-background-networking", "--disable-sync", "--disable-extensions", "--disable-component-update" + win,
        "--virtual-time-budget=5000",
        "--dump-dom",
        "--user-data-dir=" + PROF,
        url,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=120)
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
    print("  无线 adb：通过 %d / %d" % (len(lines) - len(fails), len(lines)))
    if fails:
        print("  有 %d 项失败" % len(fails))
        return 1
    print("  无线 adb 行为全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
