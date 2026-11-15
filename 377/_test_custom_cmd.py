# -*- coding: utf-8 -*-
"""自定义 ADB 指令 · DOM 行为自测（2026-11-15）。

覆盖：校验规则 / 流程展开（换行、延时、循环）/ 编辑器交互 / 持久化 /
      卡片渲染 / 执行顺序与「失败跳过」。
运行：python 377/_test_custom_cmd.py
"""
import html
import io
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
TEST = os.path.join(ROOT, "377", "test_custom_cmd.html")


def find_edge():
    for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            p = os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")
            if os.path.exists(p):
                return p
    for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if os.path.exists(p):
            return p
    return "msedge.exe"


JS = r"""
<script>
(function(){
  var R=[];
  function ok(n,c,x){ R.push((c?'PASS':'FAIL')+' | '+n+(c?'':' | '+(x===undefined?'':x))); }
  function eq(n,a,b){ ok(n, a===b, String(a)+' != '+String(b)); }
  function emit(){ var p=document.getElementById('RESULT');
    if(!p){ p=document.createElement('pre'); p.id='RESULT'; document.body.appendChild(p); }
    p.textContent=R.join('\n'); }

  // 拦下所有后端消息用于断言（普通浏览器没有 chrome.webview）
  var POSTED=[];
  post = function(kind,data,src,slot){ POSTED.push([kind,data]); };
  window.confirm = function(){ return true; };
  var _toasts=[];
  toast = function(t){ _toasts.push(t); };

  function run(){
    try{
      // ---------- A. 校验规则 ----------
      ok('名称必填', customValidate('', [{t:'cmd',v:'adb shell ls'}]) === '名称必填');
      ok('第一行不能是延时节点',
         customValidate('x',[{t:'delay',ms:100},{t:'cmd',v:'adb shell ls'}]).indexOf('第一行') >= 0);
      ok('第一行不能是循环节点',
         customValidate('x',[{t:'loop',n:3},{t:'cmd',v:'adb shell ls'}]).indexOf('第一行') >= 0);
      ok('官方节点不能连续',
         customValidate('x',[{t:'cmd',v:'a'},{t:'delay',ms:1},{t:'loop',n:3}]).indexOf('不能连续') >= 0);
      ok('延时必须大于 0',
         customValidate('x',[{t:'cmd',v:'a'},{t:'delay',ms:0}]).indexOf('大于 0') >= 0);
      ok('循环至少 2 次',
         customValidate('x',[{t:'cmd',v:'a'},{t:'loop',n:1}]).indexOf('至少 2') >= 0);
      eq('合法单命令通过', customValidate('测试',[{t:'cmd',v:'adb shell ls'}]), '');
      eq('合法多步骤通过', customValidate('测试',[
         {t:'cmd',v:'a'},{t:'delay',ms:500},{t:'cmd',v:'b'},{t:'loop',n:3},{t:'cmd',v:'c'}]), '');
      ok('空命令被拒', customValidate('x',[{t:'cmd',v:'  '}]).indexOf('不能为空') >= 0);

      // ---------- B. 流程展开 ----------
      eq('单命令展开为 1 条', customExpand({steps:[{t:'cmd',v:'adb shell ls'}]}).length, 1);
      var q2=customExpand({steps:[{t:'cmd',v:'adb shell ls\nadb shell pwd\n\nadb shell id'}]});
      eq('换行拆成 3 条（空行忽略）', q2.length, 3);
      ok('多条顺序正确', q2[0].v==='adb shell ls' && q2[1].v==='adb shell pwd' && q2[2].v==='adb shell id',
         JSON.stringify(q2));
      var q3=customExpand({steps:[{t:'cmd',v:'a'},{t:'delay',ms:800},{t:'cmd',v:'b'}]});
      eq('延时节点入队', q3.length, 3);
      ok('延时值保留', q3[1].t==='delay' && q3[1].ms===800, JSON.stringify(q3[1]));
      var q4=customExpand({steps:[{t:'cmd',v:'a'},{t:'loop',n:3},{t:'cmd',v:'b'}]});
      eq('循环重复上一条命令 3 次', q4.length, 5);
      ok('循环展开顺序正确',
         q4[0].v==='a' && q4[1].v==='a' && q4[2].v==='a' && q4[3].v==='a' && q4[4].v==='b',
         JSON.stringify(q4));
      var q5=customExpand({steps:[{t:'cmd',v:'a\nb'},{t:'loop',n:2}]});
      ok('循环重复「最后一条」命令',
         q5.length===4 && q5[2].v==='b' && q5[3].v==='b', JSON.stringify(q5));
      eq('空流程展开为 0 条', customExpand({steps:[]}).length, 0);

      // ---------- C. 持久化 ----------
      var b64=_customB64Encode([{name:'中文名称',desc:'说明',steps:[{t:'cmd',v:'a'}]}]);
      var back=_customB64Decode(b64);
      ok('base64 中文往返', back.length===1 && back[0].name==='中文名称' && back[0].steps[0].v==='a',
         JSON.stringify(back));
      eq('非法 base64 回退空数组', _customB64Decode('!!!not-base64!!!').length, 0);
      eq('空 base64 回退空数组', _customB64Decode('').length, 0);

      // ---------- D. 编辑器 ----------
      _customDefs=[];
      openCustomMgr();
      ok('弹窗可打开', document.getElementById('custom-mgr').style.display==='flex');
      eq('新建初始 1 行命令', document.querySelectorAll('#cm-steps .cm-step').length, 1);
      ok('初始行是 ADB 命令', document.querySelector('#cm-steps .cm-kind').textContent.indexOf('ADB')>=0);
      cmAddStep('delay');
      eq('第一行不能加官方节点（仍 1 行）', document.querySelectorAll('#cm-steps .cm-step').length, 1);
      ok('拒绝时给出提示', (document.getElementById('cm-err').textContent||'').indexOf('第一行')>=0);
      // 填一条命令，再加节点
      var ta=document.querySelector('#cm-steps .cm-val');
      ta.value='adb shell ls\nadb shell pwd';
      cmOnInput(ta);
      eq('输入已同步到 draft', _customDraft.steps[0].v, 'adb shell ls\nadb shell pwd');
      ok('输入不重建 DOM（引用未失效）', document.querySelector('#cm-steps .cm-val')===ta);
      cmAddStep('delay');
      eq('命令后可加延时节点', document.querySelectorAll('#cm-steps .cm-step').length, 2);
      cmAddStep('loop');
      eq('节点不能连续（仍 2 行）', document.querySelectorAll('#cm-steps .cm-step').length, 2);
      ok('连续节点有提示', (document.getElementById('cm-err').textContent||'').indexOf('不能连续')>=0);
      // 名称必填拦截
      document.getElementById('cm-name').value='';
      cmSave();
      eq('名称必填不新增', _customDefs.length, 0);
      ok('名称必填有错误提示', (document.getElementById('cm-err').textContent||'').indexOf('名称必填')>=0);
      // 正常保存
      document.getElementById('cm-name').value='重启流程';
      document.getElementById('cm-desc').value='先清缓存再重启';
      cmSave();
      eq('保存后 1 条自定义指令', _customDefs.length, 1);
      ok('卡片显示名称', document.querySelector('#cm-grid .qname').textContent==='重启流程');
      ok('卡片显示说明', document.querySelector('#cm-grid .qcmd').textContent==='先清缓存再重启');
      ok('保存发出 customsave 消息',
         POSTED.some(function(p){return p[0]==='customsave';}));
      ok('保存的 blob 可解回同一份数据',
         _customB64Decode(POSTED.filter(function(p){return p[0]==='customsave';}).pop()[1])[0].name==='重启流程');
      // 无说明时不渲染说明行
      document.getElementById('cm-name').value='无说明';
      document.getElementById('cm-desc').value='';
      cmNew();
      document.getElementById('cm-name').value='无说明';
      document.querySelector('#cm-steps .cm-val').value='adb shell date';
      cmOnInput(document.querySelector('#cm-steps .cm-val'));
      cmSave();
      eq('第二条保存成功', _customDefs.length, 2);
      var noDescCard=document.querySelectorAll('#cm-grid .cm-card')[1];
      ok('无说明时卡片不显示说明', !noDescCard.querySelector('.qcmd'), noDescCard.innerHTML.slice(0,120));
      // 编辑 / 删除
      var id0=_customDefs[0].id;
      cmEdit(id0);
      eq('编辑回填名称', document.getElementById('cm-name').value, '重启流程');
      cmDel(id0);
      eq('删除后剩 1 条', _customDefs.length, 1);
      closeCustomMgr();
      ok('弹窗可关闭', document.getElementById('custom-mgr').style.display==='none');

      // ---------- E. 执行：顺序 / 失败跳过 ----------
      POSTED.length=0;
      _customDefs=[{id:'cx',name:'执行测试',desc:'',steps:[
        {t:'cmd',v:'cmd-a'},
        {t:'cmd',v:'cmd-b\ncmd-c'},
        {t:'loop',n:2},
        {t:'cmd',v:'cmd-d'}
      ]}];
      renderCustomCards();
      // 直接跑队列，避免依赖卡片点击
      customRun('cx');
      ok('启动后处于运行态', _customRunning===true);
      eq('第一条命令已下发', POSTED.length, 1);
      ok('第一条是 cmd-a', POSTED[0][0]==='quick' && POSTED[0][1]==='cmd-a', JSON.stringify(POSTED[0]));
      customOnEnd({ok:false});          // 失败也要继续
      setTimeout(function(){
        eq('失败后仍推进到第 2 条', POSTED.length, 2);
        ok('第 2 条是 cmd-b', POSTED[1] && POSTED[1][1]==='cmd-b', JSON.stringify(POSTED[1]));
        var expected=['cmd-a','cmd-b','cmd-c','cmd-c','cmd-c','cmd-d'];
        // 逐步推进（跳过 delay，本流程无 delay）
        function step(i){
          if(i>=expected.length){
            /* 最后一条命令的 end 也要发，才会触发 customFinish 解除运行态 */
            customOnEnd({ok:true});
            setTimeout(function(){
              eq('全部命令按顺序下发', POSTED.length, expected.length);
              ok('顺序完全一致', POSTED.every(function(p,k){return p[1]===expected[k];}),
                 JSON.stringify(POSTED.map(function(p){return p[1];})));
              ok('完成后解除运行态', _customRunning===false);
              ok('失败计数被记录', _customFail>=1, String(_customFail));
              emit();
            }, 60);
            return;
          }
          customOnEnd({ok:(i%2===0)});   // 交替成功/失败，验证都不中断
          setTimeout(function(){ step(i+1); }, 45);
        }
        step(2);
      }, 60);
    }catch(e){
      R.push('FAIL | 测试脚本异常 | '+(e && e.stack ? e.stack : e));
      emit();
    }
  }
  setTimeout(run, 300);
})();
</script>
"""


def main():
    src = io.open(UI, "r", encoding="utf-8").read()
    io.open(TEST, "w", encoding="utf-8").write(src.replace("</body>", JS + "</body>"))
    cmd = [find_edge(), "--headless=new", "--disable-gpu", "--window-size=1100,760",
           "--virtual-time-budget=12000", "--dump-dom",
           "--user-data-dir=" + os.path.join(tempfile.gettempdir(), "edgeprof_custom"),
           "file:///" + TEST.replace("\\", "/")]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=180)
    m = re.search(r'<pre id="RESULT">(.*?)</pre>', r.stdout or "", re.S)
    if not m:
        print("没拿到 RESULT，DOM 长度", len(r.stdout or ""))
        return 1
    out = html.unescape(m.group(1))
    lines = [l for l in out.splitlines() if l.strip()]
    fails = [l for l in lines if l.startswith("FAIL")]
    for l in lines:
        print("  " + l)
    print("")
    print("  自定义 ADB 指令：通过 %d / %d" % (len(lines) - len(fails), len(lines)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
