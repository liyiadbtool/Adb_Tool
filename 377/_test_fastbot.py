"""Fastbot 子页回归测试（2026-11-22）。

用户需求：「Monkey tab 下增加两个页，一个是我们这个 Monkey，一个 Fastbot，
就是我们的工具既可以用安卓的原生 monkey 也能用 Fastbot」。

实现要点（均由真机实测驱动，见 fastbot_verified 记录）：
  · 二级页签：原生 Monkey / Fastbot，两套配置完全独立
  · Fastbot 需要 3 个 jar + 1 个 native so，so **必须带 ABI 子目录**
    （平铺到 /data/local/tmp/ 会 dlopen failed）
  · 工具内置 fastbot/ 目录，用户点「一键部署」即可，零准备
  · Fastbot 原生支持 --running-minutes，不需要我们算事件数
  · 结束时打印 Activity 覆盖率，这是原生 monkey 没有的
  · 已知无害报错 findMethod() error 不能当失败

运行：python 377/_test_fastbot.py
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
// 测试辅助：复用页面的添加逻辑（输入框 + 按钮）
function fbAddPkg_with(v){
  var el=document.getElementById('fb-add-pkg');
  if(!el) return;
  el.value=v;
  fbAddPkg();
}
setTimeout(function(){
  var R=[];
  function ok(n,c,e){R.push((c?'PASS':'FAIL')+' | '+n+(c?'':' -> '+(e===undefined?'':e)));}

  /* ---- 1. 二级页签 ---- */
  var subs=document.querySelectorAll('#mk-subtabs button');
  ok('二级页签有两个', subs.length===2, subs.length);
  ok('第一个是原生 Monkey',
     subs[0] && subs[0].textContent.trim().indexOf('原生')>=0,
     subs[0]?subs[0].textContent.trim():'无');
  ok('第二个是 Fastbot',
     subs[1] && subs[1].textContent.trim()==='Fastbot',
     subs[1]?subs[1].textContent.trim():'无');

  // 切换
  mkSubTab('fastbot');
  ok('切到 Fastbot 后该子页可见',
     document.getElementById('mk-sub-fastbot').style.display==='flex',
     document.getElementById('mk-sub-fastbot').style.display);
  ok('原生页已隐藏',
     document.getElementById('mk-sub-native').style.display==='none',
     document.getElementById('mk-sub-native').style.display);

  mkSubTab('native');
  ok('切回原生正常',
     document.getElementById('mk-sub-native').style.display==='flex');

  /* ---- 2. Fastbot 配置控件齐全 ---- */
  // 2026-11-22：单包输入框 fb-pkg 已删除，改为必检清单区元素
  var need=['fb-minutes','fb-throttle','fb-agent','fb-bugreport',
            'fb-keep-model','fb-outdir','fb-start','fb-stop','fastbot-out','fb-status',
            'fb-st-crash','fb-st-anr','fb-st-cov','fb-st-act','fb-st-elapsed',
            'fb-deploy-btn','fb-hint','fb-list','fb-listcnt','fb-add-pkg',
            'fb-hint-text'];
  var miss=[];
  for(var k=0;k<need.length;k++) if(!document.getElementById(need[k])) miss.push(need[k]);
  ok('Fastbot 控件齐全', miss.length===0, miss.join(','));

  ok('时长默认 30', (document.getElementById('fb-minutes')||{}).value==='30');
  ok('Agent 默认 reuseq', _fb.agent==='reuseq', _fb.agent);
  ok('停止按钮初始禁用', (document.getElementById('fb-stop')||{}).disabled===true);

  /* ---- 3. 命令构建 ---- */
  // 单包模式已删除：必须先在清单里放一个包
  _fbApps=[{pkg:'com.test.fb', name:'', sel:true}];
  _fb.agent='reuseq';
  var cmd=fbBuildCmd();
  ok('命令含 CLASSPATH', /CLASSPATH=\/sdcard\/monkeyq\.jar/.test(cmd||''), cmd);
  ok('命令含三个 jar',
     cmd.indexOf('framework.jar')>=0 && cmd.indexOf('fastbot-thirdpart.jar')>=0);
  ok('命令用 app_process',
     /exec\s+app_process\s+\/system\/bin/.test(cmd||''), cmd);
  ok('命令含 Fastbot 主类',
     cmd.indexOf('com.android.commands.monkey.Monkey')>=0, cmd);
  ok('命令含包名', /-p com\.test\.fb/.test(cmd||''), cmd);
  ok('命令含 --running-minutes（Fastbot 原生支持）',
     /--running-minutes 30/.test(cmd||''), cmd);
  ok('命令含 --agent reuseq', /--agent reuseq/.test(cmd||''), cmd);
  ok('命令含 --bugreport', /--bugreport/.test(cmd||''), cmd);
  ok('命令含 -v -v', /-v -v/.test(cmd||''), cmd);

  // agent 切换
  fbSetAgent('robot');
  ok('切到 robot 后命令同步',
     /--agent robot/.test(fbBuildCmd()||''), fbBuildCmd());
  fbSetAgent('reuseq');

  // 输出目录
  document.getElementById('fb-outdir').value='/sdcard/fbout';
  ok('指定输出目录时带上 --output-directory',
     /--output-directory \/sdcard\/fbout/.test(fbBuildCmd()||''), fbBuildCmd());
  document.getElementById('fb-outdir').value='';

  // 无包名返回 null
  _fbApps=[];
  ok('清单为空时命令为 null', fbBuildCmd()===null);
  _fbApps=[{pkg:'com.test.fb', name:'', sel:true}];

  /* ---- 4. 部署状态解析 ---- */
  _fb._okFiles=[]; _fb._missFiles=[];
  fbOnCheckLine('OK:/sdcard/monkeyq.jar');
  fbOnCheckLine('OK:/sdcard/framework.jar');
  fbOnCheckLine('OK:/sdcard/fastbot-thirdpart.jar');
  fbOnCheckLine('OK:/data/local/tmp/x86_64/libfastbot_native.so');
  fbOnCheckLine('ABI=x86_64');
  fbOnCheckDone();
  ok('四个文件都在时标记已部署', _fb.deployed===true);
  ok('已部署徽标为 ok',
     document.getElementById('fb-status').className.indexOf('ok')>=0,
     document.getElementById('fb-status').className);
  ok('ABI 已解析', _fb.abi==='x86_64', _fb.abi);

  // 缺文件
  _fb._okFiles=[]; _fb._missFiles=[]; _fb.checked=false;
  fbOnCheckLine('OK:/sdcard/monkeyq.jar');
  fbOnCheckLine('NO:/sdcard/framework.jar');
  fbOnCheckLine('NO:/data/local/tmp/arm64-v8a/libfastbot_native.so');
  fbOnCheckLine('ABI=arm64-v8a');
  fbOnCheckDone();
  ok('缺文件时标记未部署', _fb.deployed===false);
  ok('未部署徽标为 bad',
     document.getElementById('fb-status').className.indexOf('bad')>=0,
     document.getElementById('fb-status').className);
  ok('提示里列出缺失文件',
     document.getElementById('fb-hint').textContent.indexOf('framework.jar')>=0,
     document.getElementById('fb-hint').textContent);

  // 部署结果回调
  _fb.deployed=false;
  fbOnDeployResult({ok:true, text:'部署完成（4 个文件）'});
  ok('部署成功回调后标记已部署', _fb.deployed===true);
  ok('部署成功后按钮恢复可用',
     document.getElementById('fb-deploy-btn').disabled===false);

  fbOnDeployResult({ok:false, text:'推送失败'});
  ok('部署失败回调后标记未部署', _fb.deployed===false);

  /* ---- 5. 输出解析：覆盖率 ---- */
  _fb.acts=0; _fb.coverage='';
  fbOnOut('[Fastbot] Activity of Coverage: 12.345%');
  ok('覆盖率解析正确',
     document.getElementById('fb-st-cov').textContent==='12.345%',
     document.getElementById('fb-st-cov').textContent);

  /* ---- 6. 输出解析：已探页面数 ---- */
  _fb.acts=0; _fb._inActs=false;
  // 真实格式带时间戳前缀（实测抓的），必须按这个测
  fbOnOut('[Fastbot][2026-11-22 15:19:37.807] Explored app activities:');
  fbOnOut('[Fastbot][2026-11-22 15:19:37.807]    1 com.android.settings.Settings$NetworkDashboardActivity');
  fbOnOut('[Fastbot][2026-11-22 15:19:37.807]    2 com.android.settings.SubSettings');
  fbOnOut('[Fastbot][2026-11-22 15:19:37.807]    3 com.android.settings.spa.SpaActivity');
  ok('已探页面数解析正确',
     document.getElementById('fb-st-act').textContent==='3',
     document.getElementById('fb-st-act').textContent);

  /* ---- 7. 输出解析：崩溃 ---- */
  _fb.crash=0; _fb.crashes=[]; _fb.seenSig={};
  fbOnOut('[Fastbot] // CRASH: com.test.fb (pid 1234)');
  fbOnOut('[Fastbot] // Short Msg: android.app.RemoteServiceException$CrashedByAdbException');
  fbOnOut('[Fastbot] // Long Msg: android.app.RemoteServiceException$CrashedByAdbException: shell-induced crash');
  ok('崩溃计数正确',
     document.getElementById('fb-st-crash').textContent==='1',
     document.getElementById('fb-st-crash').textContent);
  ok('崩溃包名与 pid 已记录',
     _fb.crashes.length===1 && _fb.crashes[0].pkg==='com.test.fb'
     && _fb.crashes[0].pid==='1234');
  ok('崩溃消息已解出',
     (_fb.crashes[0].msg||'').indexOf('shell-induced crash')>=0,
     _fb.crashes[0].msg);

  // 去重：同一个 pid 再来一次不重复计数
  fbOnOut('[Fastbot] // CRASH: com.test.fb (pid 1234)');
  ok('同一匹崩溃不重复计数', _fb.crash===1, _fb.crash);

  /* ---- 8. 已知无害报错不刷红 ---- */
  var before=document.getElementById('fastbot-out').textContent.length;
  fbOnOut("[Fastbot]*** ERROR *** findMethod() error, NoSuchMethodException happened, there is no such method: setActivityController");
  var after=document.getElementById('fastbot-out').textContent.length;
  ok('findMethod 无害报错被过滤', after===before,
     before+' -> '+after);

  /* ---- 9. 结果统计字段 ---- */
  ok('ANR 统计字段存在', !!document.getElementById('fb-st-anr'));
  fbSetStat('fb-st-anr', 2);
  ok('ANR 可写入', document.getElementById('fb-st-anr').textContent==='2');

  /* ---- 10. 报告导出 ---- */
  var sent=null, _op=window.post;
  try { window.post=function(k,d,s,sl,ex){
    if(k==='mkreport') sent={csv:d, full:ex&&ex.full, pkg:ex&&ex.pkg};
    return _op?_op(k,d,s,sl,ex):null;
  }; } catch(e){}
  _fb.t0=Date.now()-60000; _fb.mode='fastbot';
  fbExport();
  try { window.post=_op; } catch(e){}
  ok('导出调用了 mkreport', !!sent);
  if(sent){
    ok('报告带 BOM（Excel 不乱码）', (sent.csv||'').charCodeAt(0)===0xFEFF);
    ok('报告含覆盖率', (sent.csv||'').indexOf('Activity覆盖率')>=0);
    ok('报告含包名', (sent.csv||'').indexOf('com.test.fb')>=0);
    ok('报告含崩溃明细', (sent.csv||'').indexOf('shell-induced')>=0);
  }

  /* ---- 11. 未部署时不允许开始 ---- */
  _fb.deployed=false; _fb.running=false;
  fbStart();
  ok('未部署时未进入运行态', _fb.running===false);

  /* ---- 11b. 白名单（2026-11-22 单包/Activity黑名单已删除）----
     实测确认：白名单 = 重复给 -p（Fastbot 没有 --pkg-whitelist-file） */
  ok('范围切换函数仍在（兼容旧调用）', typeof fbSetScope === 'function');
  ok('从APK管理导入函数存在', typeof fbImportFromApk === 'function');

  // 一个包 → 一个 -p
  _fbApps=[{pkg:'com.test.one', name:'', sel:true}];
  var c1 = fbBuildCmd();
  ok('单包清单给一个 -p', (c1.match(/-p /g)||[]).length===1, c1);

  // 两个包 → 两个 -p
  _fbApps=[
    {pkg:'com.test.a', name:'', sel:true},
    {pkg:'com.test.b', name:'', sel:true}
  ];
  var c2 = fbBuildCmd();
  ok('白名单用重复 -p', (c2.match(/-p /g)||[]).length===2, c2);
  ok('白名单含两个包名',
     c2.indexOf('com.test.a')>=0 && c2.indexOf('com.test.b')>=0, c2);
  ok('白名单不含 --pkg-whitelist-file（Fastbot 没这个参数）',
     c2.indexOf('pkg-whitelist')<0, c2);
  ok('不再有 Activity 黑名单参数',
     c2.indexOf('act-blacklist')<0, c2);

  // 未勾选的不算
  _fbApps=[
    {pkg:'com.test.a', name:'', sel:true},
    {pkg:'com.test.b', name:'', sel:false}
  ];
  var c3 = fbBuildCmd();
  ok('未勾选的包不进入命令', (c3.match(/-p /g)||[]).length===1, c3);

  // 恢复
  _fbApps=[{pkg:'com.test.fb', name:'', sel:true}];

  /* ---- 12. 清空 ---- */
  fbClear();
  ok('清空后覆盖率归位',
     document.getElementById('fb-st-cov').textContent==='—');
  ok('清空后崩溃归零',
     document.getElementById('fb-st-crash').textContent==='0');

  ok('无运行时错误', window.__E.length===0, window.__E.join('; '));

  var pre=document.createElement('pre');
  pre.id='FB_RESULT';
  pre.textContent=JSON.stringify(R);
  document.body.appendChild(pre);
}, 1800);
</script>
"""


def main():
    src = open(UI, encoding="utf-8").read()
    tmp = os.path.join(ROOT, "377", "_fb.html")
    open(tmp, "w", encoding="utf-8", newline="").write(src.replace("</body>", PROBE + "</body>"))
    try:
        p = subprocess.run(
            [EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--no-first-run", "--no-default-browser-check",
             "--disable-background-networking", "--disable-sync",
             "--disable-extensions", "--disable-component-update",
             "--user-data-dir=" + os.path.join(tempfile.gettempdir(), "edgeprof_fb"),
             "--window-size=1280,900", "--virtual-time-budget=12000", "--dump-dom",
             "file:///" + tmp.replace("\\", "/")],
            capture_output=True, timeout=180)
        dom = p.stdout.decode("utf-8", "replace")
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass

    m = re.search(r'<pre id="FB_RESULT">(.*?)</pre>', dom, re.S)
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
    print("  Fastbot 子页：通过 %d / %d" % (len(results) - fail, len(results)))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
