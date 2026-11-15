"""需求1 专项：语音助手迁移到「快捷指令-语音助手」分组。

用户原话（2026-11-11）："语音助手取消，功能迁移到快捷指令-语音助手"。

即：取消独立的「语音助手」页签，把文本输入 + 六音区 + 发送 + 上下键历史
这套交互迁到「快捷指令」tab 下的「语音助手」分组里，发送结果走反馈窗口（src=1）。

本脚本锁住：
  A. 不再有独立的 vr 页签 / page-vr
  B. vr 输入区（vr-panel）在快捷指令页内，切到「语音助手」分组才显示
  C. 六个音区按钮 + 默认选中主驾
  D. 发送走 src=1（反馈窗口），命令 :vr sr <文本> -a <音区>
  E. 断网模式 :vr local
  F. 上下键历史回放 + 草稿暂存/恢复
  G. 切到其它分组时输入区隐藏

运行：python 377/_test_vr_ui.py
"""
import os
import tempfile
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
TEST = os.path.join(ROOT, "377", "test_vr_ui.html")
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

  function main(){
    try{
      // ---------- A. 独立语音助手页签已取消 ----------
      var tabVr = document.querySelector('.tab[data-tab="vr"]');
      ok('A 不再有独立 vr 页签', !tabVr);
      ok('A 不再有 page-vr', !document.getElementById('page-vr'));

      // ---------- B. 输入区在快捷指令页内 ----------
      var panel = document.getElementById('vr-panel');
      ok('B 存在 vr-panel 输入区', !!panel);
      var inp = document.getElementById('vr-input');
      ok('B 有文本输入框', !!inp && inp.tagName.toLowerCase() === 'textarea', inp && inp.tagName);

      // 默认在「指令执行」分组，输入区应隐藏
      ok('B 默认分组（非语音助手）输入区隐藏', panel.style.display === 'none', panel.style.display);

      // 切到「语音助手」分组。
      // 【别写死下标】以前这里是 switchQuickGroup(1)，2026-11-12 插入
      // 「方控按键」独立分组后 1 变成方控、语音助手顺延到 2，这条断言开始
      // 报「切到语音助手分组 | 方控按键」。改成按名字查，以后再插分组不会错位。
      var vrIdx = -1;
      for(var gi=0;gi<quickGroups.length;gi++){
        if(quickGroups[gi].name === '语音助手'){ vrIdx = gi; break; }
      }
      ok('B 能找到语音助手分组', vrIdx >= 0, vrIdx);
      switchQuickGroup(vrIdx);
      ok('B 切到语音助手分组', quickGroups[_quickIdx].name === '语音助手', quickGroups[_quickIdx].name);
      ok('B 语音助手分组时输入区显示', panel.style.display !== 'none', panel.style.display);

      // ---------- C. 六个音区 ----------
      var zones = document.querySelectorAll('#vr-zones .zone');
      ok('C 有六个音区按钮', zones.length === 6, zones.length);
      var names = ['主驾','副驾','二排左','二排右','三排左','三排右'];
      var namesOk = true;
      for(var i=0;i<6;i++){
        var t = zones[i].querySelector('.zt');
        if(!t || t.textContent !== names[i]){ namesOk = false; break; }
      }
      ok('C 音区名称正确（主驾→三排右）', namesOk, '');
      ok('C 默认选中主驾（area 0）', zones[0].classList.contains('sel'), zones[0].className);

      // ---------- D. 选音区 + 发送（走 src=1） ----------
      sent.length = 0;
      pickZone(2);   // 二排左
      ok('D 选中二排左', zones[2].classList.contains('sel') && !zones[0].classList.contains('sel'), '');
      inp.value = '打开车窗';
      sendVr();
      ok('D 发了 1 条消息', sent.length === 1, JSON.stringify(sent));
      var m = sent[0] || {};
      ok('D kind=cmd', m.kind === 'cmd', m.kind);
      ok('D src=1（快捷指令反馈窗口）', m.src === 1, JSON.stringify(m));
      ok('D 命令含 :vr sr', m.data.indexOf(':vr sr') === 0, m.data);
      ok('D 命令含文本', m.data.indexOf('打开车窗') >= 0, m.data);
      ok('D 命令含音区 -a 2', m.data.indexOf('-a 2') >= 0, m.data);
      ok('D 发送后输入框清空', inp.value === '', inp.value);
      ok('D _busy 置 true', _busy[0] === true, String(_busy));
      // 反馈窗口建了占位行
      ok('D 反馈窗口建占位行', (function(){
        return document.querySelectorAll('#fb-table .fb-row').length >= 1;
      })(), '');

      // ---------- E. 断网模式 ----------
      sent.length = 0;
      _busy[0] = false;
      pickZone(5);
      document.getElementById('vr-local').checked = true;
      inp.value = '导航回家';
      sendVr();
      var m2 = sent[0] || {};
      ok('E 断网命令 :vr local', m2.data.indexOf(':vr local') === 0, m2.data);
      ok('E 断网命令含 -a 5', m2.data.indexOf('-a 5') >= 0, m2.data);
      document.getElementById('vr-local').checked = false;

      // ---------- F. 上下键历史回放 ----------
      _busy[0] = false;
      ok('F 历史栈有 2 条', _vrHist.length === 2, JSON.stringify(_vrHist));
      inp.value = '';
      onVrKey({key:'ArrowUp', preventDefault:function(){}});
      ok('F ↑ 回放最近一条', inp.value === '导航回家', inp.value);
      onVrKey({key:'ArrowUp', preventDefault:function(){}});
      ok('F ↑↑ 回放最早一条', inp.value === '打开车窗', inp.value);
      onVrKey({key:'ArrowDown', preventDefault:function(){}});
      ok('F ↓ 前进到最近一条', inp.value === '导航回家', inp.value);

      // 草稿暂存/恢复
      inp.value = '临时草稿';
      if(typeof onVrInput === 'function') onVrInput();
      onVrKey({key:'ArrowUp', preventDefault:function(){}});
      ok('F 草稿被暂存（↑ 进入历史）', inp.value === '导航回家', inp.value);
      onVrKey({key:'ArrowDown', preventDefault:function(){}});
      ok('F ↓ 到底恢复草稿', inp.value === '临时草稿', inp.value);

      // ---------- G. 切到其它分组，输入区隐藏 ----------
      switchQuickGroup(0);
      ok('G 切到指令执行分组', quickGroups[_quickIdx].name === '指令执行');
      ok('G 输入区隐藏', panel.style.display === 'none', panel.style.display);

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
    print("  需求1（语音助手迁移到快捷指令）全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
