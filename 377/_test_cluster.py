"""仪表投屏 + 参数输入归拢 回归测试（2026-11-22 第 16 批）。

覆盖：
  A. 智驾出行「参数输入」不再重复（上一版渲染出两个同名标题）
  B. 仪表页存在、页签可切换
  C. 芯片切换：8295 显示凭据区，8838 隐藏
  D. 硬门禁：未登录时「开启仪表实时显示」按钮禁用
  E. 登录成功后按钮解禁、状态变「已登录」
  F. 换芯片自动退出登录（不同芯片通道不同，不能混用）
  G. 投屏请求带正确参数（display / view）

运行：python 377/_test_cluster.py
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
window.__E = [];
window.addEventListener('error', function(e){ window.__E.push(String(e.message)); });

var R = [];
function ok(n, c, e){ R.push((c?'PASS':'FAIL') + ' | ' + n + (c?'':' -> ' + (e===undefined?'':e))); }
function finish(){
  var pre = document.createElement('pre');
  pre.id = 'CLU_RESULT';
  pre.textContent = JSON.stringify(R);
  document.body.appendChild(pre);
}

var sent = [];
window.chrome = window.chrome || {};
window.chrome.webview = { postMessage: function(o){ if(o && o.kind) sent.push(o); } };

setTimeout(function(){
  try { runAll(); } catch(err){ ok('探针异常', false, String(err)); finish(); }
}, 1800);

function runAll(){

  /* ---------- A. 参数输入不重复 ---------- */
  var driveIdx = -1;
  for(var i=0;i<quickGroups.length;i++) if(quickGroups[i].name==='智驾出行') driveIdx = i;
  ok('存在智驾出行分组', driveIdx >= 0);

  var items = quickGroups[driveIdx].items;
  // 模拟渲染器的"遇新 cat 插标题"逻辑，统计实际会出现的标题序列
  var titles = [];
  for(var j=0;j<items.length;j++){
    var c = items[j].cat || '';
    if(titles.length === 0 || titles[titles.length-1] !== c) titles.push(c);
  }
  var dup = false, seen = {};
  for(var k=0;k<titles.length;k++){
    if(seen[titles[k]]) { dup = true; break; }
    seen[titles[k]] = 1;
  }
  ok('★ 分类标题不重复（第15批出现两个「参数输入」）', !dup, titles.join(' → '));

  // 参数输入必须 3 张
  var param = items.filter(function(x){ return x.cat === '参数输入'; });
  ok('参数输入 3 张卡', param.length === 3, param.length);
  var pnames = param.map(function(x){return x.name;});
  ok('含地图激活', pnames.indexOf('地图激活') >= 0, pnames.join(','));
  ok('含修改系统时间', pnames.indexOf('修改系统时间') >= 0);
  ok('含设置时间', pnames.indexOf('设置时间') >= 0);

  // 三张必须连续（否则标题会被插两次）
  var idxs = [];
  for(var m=0;m<items.length;m++) if(items[m].cat === '参数输入') idxs.push(m);
  var cont = (idxs.length === 3) && (idxs[1] === idxs[0]+1) && (idxs[2] === idxs[0]+2);
  ok('★ 三张参数输入卡连续排列', cont, idxs.join(','));

  /* ---------- B. 仪表页存在 ---------- */
  ok('页签存在', !!document.querySelector('[data-tab="cluster"]'));
  ok('页面容器存在', !!document.getElementById('page-cluster'));

  switchTab('cluster');
  ok('切换到仪表页后可见',
     document.getElementById('page-cluster').classList.contains('active'));

  /* ---------- C. 芯片切换显示/隐藏凭据 ---------- */
  var sel = document.getElementById('clu-chip');
  var cred = document.getElementById('clu-cred');
  ok('芯片下拉存在', !!sel);
  ok('有两个芯片', sel && sel.options.length === 2, sel ? sel.options.length : 0);
  var opts = [];
  if(sel) for(var o=0;o<sel.options.length;o++) opts.push(sel.options[o].value);
  ok('芯片选项为 8838/8295', opts.indexOf('8838')>=0 && opts.indexOf('8295')>=0, opts.join(','));

  // 8838 → 凭据隐藏
  sel.value = '8838'; cluChipChanged();
  ok('8838 时凭据区隐藏', cred.style.display === 'none', cred.style.display);

  // 8295 → 凭据显示
  sel.value = '8295'; cluChipChanged();
  ok('8295 时凭据区显示', cred.style.display !== 'none', cred.style.display);
  ok('8295 有 telnet 地址输入框', !!document.getElementById('clu-host'));
  ok('8295 有账号输入框', !!document.getElementById('clu-user'));
  ok('8295 有密码输入框', !!document.getElementById('clu-pass'));
  ok('8295 有 su 密码输入框', !!document.getElementById('clu-su'));

  /* ---------- D. 门禁：未登录不能投 ---------- */
  var castBtn = document.getElementById('clu-cast-btn');
  ok('未登录时投屏按钮禁用', castBtn.disabled === true, castBtn.disabled);
  ok('未登录时状态显示未登录',
     document.getElementById('clu-state').textContent.indexOf('未登录') >= 0,
     document.getElementById('clu-state').textContent);

  // 直接调 cluCast 应被拦（不发请求）
  sent.length = 0;
  cluCast();
  ok('未登录时点投屏不发请求', sent.length === 0, JSON.stringify(sent));

  /* ---------- E. 登录成功 → 解禁 ---------- */
  // 先验证：8295 缺凭据会被前端拦下（不发请求）
  sent.length = 0;
  cluLogin();
  ok('★ 8295 缺凭据时不发登录请求（前端拦截）', sent.length === 0,
     JSON.stringify(sent).slice(0, 120));

  // 填齐凭据后再登录
  document.getElementById('clu-host').value = '192.168.8.1';
  document.getElementById('clu-user').value = 'root';
  document.getElementById('clu-pass').value = 'testpass';
  sent.length = 0;
  cluLogin();
  var loginMsg = null;
  for(var s=0;s<sent.length;s++) if(sent[s].kind === 'clulogin') loginMsg = sent[s];
  ok('发出了登录请求', !!loginMsg, JSON.stringify(sent).slice(0,120));
  if(loginMsg){
    ok('登录请求带芯片', loginMsg.chip === '8295', loginMsg.chip);
    ok('登录请求带账号', loginMsg.user !== undefined);
    ok('登录请求带密码字段', loginMsg.pass !== undefined);
  }

  // 模拟 C# 回包：登录成功
  cluOnState({kind:'clustate', logged:true, chip:'8295', err:''});
  ok('★ 登录成功后投屏按钮解禁', castBtn.disabled === false, castBtn.disabled);
  ok('登录后状态显示已登录',
     document.getElementById('clu-state').textContent.indexOf('已登录') >= 0,
     document.getElementById('clu-state').textContent);
  ok('登录后「退出登录」可用',
     document.getElementById('clu-logout').disabled === false);

  /* ---------- G. 投屏参数 ---------- */
  document.getElementById('clu-display').value = '7';
  document.getElementById('clu-viewonly').checked = true;
  sent.length = 0;
  cluCast();
  var castMsg = null;
  for(var t=0;t<sent.length;t++) if(sent[t].kind === 'clucast') castMsg = sent[t];
  ok('发出了投屏请求', !!castMsg, JSON.stringify(sent).slice(0,120));
  if(castMsg){
    ok('投屏带屏号 7', castMsg.display === 7, castMsg.display);
    ok('投屏带只读标记', castMsg.view === 1, castMsg.view);
  }

  /* ---------- F. 换芯片自动退出 ---------- */
  sel.value = '8838'; cluChipChanged();
  ok('★ 换芯片后自动退出登录',
     document.getElementById('clu-login').disabled === false &&
     document.getElementById('clu-state').textContent.indexOf('未登录') >= 0,
     document.getElementById('clu-state').textContent);
  ok('换芯片后投屏按钮重新禁用', castBtn.disabled === true, castBtn.disabled);

  /* ---------- 登录失败态 ---------- */
  cluOnState({kind:'clustate', logged:false, chip:'8838', err:'容器不存在或 lxc-attach 不可用'});
  ok('失败时状态显示原因',
     document.getElementById('clu-state').textContent.indexOf('容器不存在') >= 0,
     document.getElementById('clu-state').textContent);
  ok('失败时投屏仍禁用', castBtn.disabled === true);

  /* ---------- 退出登录 ---------- */
  cluOnState({kind:'clustate', logged:true, chip:'8838', err:''});
  cluLogout();
  ok('退出登录后状态回未登录',
     document.getElementById('clu-state').textContent.indexOf('未登录') >= 0);
  ok('退出后投屏禁用', castBtn.disabled === true);

  ok('无运行时错误', window.__E.length === 0, window.__E.join('; '));
  finish();
}
</script>
"""


def main():
    src = open(UI, encoding="utf-8").read()
    tmp = os.path.join(ROOT, "377", "_clu.html")
    open(tmp, "w", encoding="utf-8", newline="").write(src.replace("</body>", PROBE + "</body>"))
    try:
        p = subprocess.run(
            [EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--no-first-run", "--no-default-browser-check",
             "--disable-background-networking", "--disable-sync",
             "--disable-extensions", "--disable-component-update",
             "--user-data-dir=" + os.path.join(tempfile.gettempdir(), "edgeprof_clu"),
             "--window-size=1400,900", "--virtual-time-budget=14000", "--dump-dom",
             "file:///" + tmp.replace("\\", "/")],
            capture_output=True, timeout=180)
        dom = p.stdout.decode("utf-8", "replace")
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass

    m = re.search(r'<pre id="CLU_RESULT">(.*?)</pre>', dom, re.S)
    if not m:
        print("!! 探针未返回")
        for mm in re.finditer(r"(Uncaught[^<\n]{0,220})", dom):
            print("   ", mm.group(1))
        return 2

    results = json.loads(m.group(1))
    for line in results:
        print("  " + line)
    fail = sum(1 for r in results if r.startswith("FAIL"))
    print("")
    print("  仪表投屏：通过 %d / %d" % (len(results) - fail, len(results)))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
