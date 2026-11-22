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

    /* ---- 4. 命令拼接 ----
       2026-11-22：单包模式已删除，只剩白名单/黑名单。
       要验证 -p 必须切到黑名单模式（它仍需要一个目标包）。 */
    mkSetScope('black');
    document.getElementById('mk-pkg').value='com.test.demo';
    document.getElementById('mk-minutes').value='5';
    document.getElementById('mk-throttle').value='200';
    document.getElementById('mk-count').value='0';
    var cmd=mkBuildCmd('com.test.demo');
    ok('黑名单命令含包名', /-p com\.test\.demo/.test(cmd||''), cmd);
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

    /* ---- 5b. 设备能力降级（2026-11-22 实测后补）----
       实测 emulator Android 14 镜像是**没有 monkey 的**（部分 AOSP 会裁掉）。
       所以必须有降级路径，否则用户点了"开始遍历"只会看到一条失败命令。 */
    ok('环境检测函数存在', typeof mkCheckEnv === 'function');
    ok('uiautomator 降级命令可生成',
       /uiautomator dump/.test(mkBuildUiautomatorCmd(5, 300) || ''),
       (mkBuildUiautomatorCmd(5,300)||'').slice(0,60));
    ok('input 兜底命令可生成',
       /input keyevent/.test(mkBuildInputCmd(5, 300) || ''),
       (mkBuildInputCmd(5,300)||'').slice(0,60));
    ok('降级命令轮数正确',
       (mkBuildInputCmd(7, 200) || '').indexOf('i -lt 7') >= 0);

    // 能力解析：喂一行模拟输出验证解析逻辑
    _mkEnv.monkey=false; _mkEnv.uiautomator=false; _mkEnv.input=false;
    mkOnEnvLine('MK=0');
    mkOnEnvLine('UA=1');
    mkOnEnvLine('IN=1');
    ok('能力解析 MK=0 正确', _mkEnv.monkey === false);
    ok('能力解析 UA=1 正确', _mkEnv.uiautomator === true);
    ok('能力解析 IN=1 正确', _mkEnv.input === true);

    /* ---- 5c. 崩溃堆栈抓取（需求 B-1）----
       实测格式（Android 14 emulator）：
         E AndroidRuntime: FATAL EXCEPTION: main
         E AndroidRuntime: Process: com.android.settings, PID: 2586
         E AndroidRuntime: java.lang.NullPointerException: msg
         E AndroidRuntime: \tat android.app.ActivityThread.xxx(ActivityThread.java:2124) */
    _mk.crashes=[]; _mk.crash=0; _mk.seenCrashSig={};
    _mk.pkg='com.test.demo'; _mk.mode='monkey';
    mkOnCrashLogChunk([
      '11-22 14:25:20.361  2586  2586 E AndroidRuntime: FATAL EXCEPTION: main',
      '11-22 14:25:20.361  2586  2586 E AndroidRuntime: Process: com.test.demo, PID: 2586',
      '11-22 14:25:20.361  2586  2586 E AndroidRuntime: java.lang.NullPointerException: boom',
      '11-22 14:25:20.361  2586  2586 E AndroidRuntime: \tat android.app.ActivityThread.main(AT.java:1)',
      '11-22 14:25:20.361  2586  2586 E AndroidRuntime: \tat com.demo.Main.run(Main.java:9)'
    ]);
    ok('崩溃被记录到 crashes', _mk.crashes.length===1, _mk.crashes.length);
    if(_mk.crashes.length){
      var c0=_mk.crashes[0];
      ok('异常类型提取正确', c0.type==='java.lang.NullPointerException', c0.type);
      ok('异常消息提取正确', c0.msg==='boom', c0.msg);
      ok('进程名提取正确', /com\.test\.demo/.test(c0.proc||''), c0.proc);
      ok('堆栈帧已采集', c0.stack.length===2, c0.stack.length);
      ok('崩溃计数已更新',
         document.getElementById('mk-st-crash').textContent==='1',
         document.getElementById('mk-st-crash').textContent);
    }

    // 去重：同样的内容再来一遍不应重复计数
    var before=_mk.crashes.length;
    mkOnCrashLogChunk([
      '11-22 14:25:20.361  2586  2586 E AndroidRuntime: FATAL EXCEPTION: main',
      '11-22 14:25:20.361  2586  2586 E AndroidRuntime: Process: com.test.demo, PID: 2586',
      '11-22 14:25:20.361  2586  2586 E AndroidRuntime: java.lang.NullPointerException: boom'
    ]);
    ok('重复崩溃不重复计数', _mk.crashes.length===before, before+' -> '+_mk.crashes.length);

    // 非被测包的崩溃不应计入
    mkOnCrashLogChunk([
      '11-22 14:26:00.000  9999  9999 E AndroidRuntime: FATAL EXCEPTION: main',
      '11-22 14:26:00.000  9999  9999 E AndroidRuntime: Process: com.other.app, PID: 9999',
      '11-22 14:26:00.000  9999  9999 E AndroidRuntime: java.lang.IllegalStateException: x'
    ]);
    ok('非被测包崩溃被过滤', _mk.crashes.length===before, before+' -> '+_mk.crashes.length);

    /* ---- 5d. 崩溃详情弹层 ---- */
    ok('崩溃弹层存在', !!document.getElementById('mk-crash-mask'));
    mkOpenCrash(0);
    ok('点开崩溃后弹层可见',
       document.getElementById('mk-crash-mask').style.display==='flex');
    ok('弹层显示异常类型',
       document.getElementById('mk-crash-title').textContent.indexOf('NullPointer')>=0,
       document.getElementById('mk-crash-title').textContent);
    ok('弹层显示堆栈内容',
       document.getElementById('mk-crash-body').textContent.indexOf('ActivityThread')>=0);
    mkCloseCrash();
    ok('关闭后弹层隐藏',
       document.getElementById('mk-crash-mask').style.display==='none');

    /* ---- 5e. 自动重启开关 ---- */
    var rst=document.getElementById('mk-restart-on-crash');
    ok('自动重启开关存在且默认勾选', !!rst && rst.checked===true);

    /* ---- 5f. 报告导出 ---- */
    ok('导出按钮存在', !!document.getElementById('mk-export'));
    // 拦截 post 验证导出内容
    var sent=null; var _origPost2=window.post;
    try { window.post=function(k,d,s,sl,ex){ if(k==='mkreport') sent={csv:d,full:ex&&ex.full,pkg:ex&&ex.pkg}; return _origPost2?_origPost2(k,d,s,sl,ex):null; }; } catch(e){}
    _mk.t0=Date.now()-5000; _mk.events=120; _mk.mode='monkey';
    mkExportReport();
    try { window.post=_origPost2; } catch(e){}
    ok('导出调用了 mkreport', !!sent);
    if(sent){
      ok('CSV 含 BOM（Excel 不乱码）', (sent.csv||'').charCodeAt(0)===0xFEFF);
      ok('CSV 含包名', (sent.csv||'').indexOf('com.test.demo')>=0);
      ok('CSV 含崩溃明细', (sent.csv||'').indexOf('NullPointerException')>=0);
      ok('完整堆栈已附带', (sent.full||'').indexOf('ActivityThread')>=0);
      ok('CSV 含自动重启次数', (sent.csv||'').indexOf('自动重启次数')>=0);
    }

    /* ---- 5g. 多包 / 白名单 / 黑名单（2026-11-22）---- */
    ok('测试范围切换存在', typeof mkSetScope === 'function');
    ok('执行方式切换存在', typeof mkSetExec === 'function');
    ok('应用清单渲染存在', typeof mkRenderList === 'function');
    ok('从设备扫描存在', typeof mkScanApps === 'function');
    ok('从APK管理导入存在', typeof mkImportFromApk === 'function');
    ok('持久化函数存在', typeof mkPersist === 'function');
    ok('恢复函数存在', typeof mkRestore === 'function');

    // 范围切换 UI 联动
    mkSetScope('white');
    ok('白名单模式显示清单区',
       document.getElementById('mk-row-list').style.display !== 'none');
    ok('白名单模式隐藏单包输入',
       document.getElementById('mk-row-single').style.display === 'none');

    // 添加包名（支持逗号分隔）
    _mk.apps = [];
    document.getElementById('mk-add-pkg').value = 'com.a, com.b;com.c';
    mkAddPkgFromInput();
    ok('逗号分隔可一次加多个', _mk.apps.length===3, _mk.apps.length);

    // 去重合并
    mkMergeApps([{pkg:'com.a', name:'A'}, {pkg:'com.d', name:'D'}]);
    ok('重复包不重复添加', _mk.apps.length===4, _mk.apps.length);
    ok('已有包补上名称',
       (_mk.apps.filter(function(x){return x.pkg==='com.a';})[0]||{}).name==='A');

    // 白名单命令：只给 --pkg-whitelist-file，**不能有 -p**（否则取交集）
    _mk.apps.forEach(function(a){ a.sel = true; });
    mkSetExec('seq');
    var wcmd = mkBuildCmd();
    ok('白名单命令含 --pkg-whitelist-file',
       /--pkg-whitelist-file/.test(wcmd||''), wcmd);
    ok('白名单命令不含 -p（避免取交集）',
       !/\s-p\s/.test(wcmd||''), wcmd);

    // 黑名单命令：-p + --pkg-blacklist-file
    mkSetScope('black');
    document.getElementById('mk-pkg').value = 'com.target';
    mkBuildCmd('com.target');
    var bcmd = mkBuildCmd('com.target');
    ok('黑名单命令含 -p', /-p com\.target/.test(bcmd||''), bcmd);
    ok('黑名单命令含 --pkg-blacklist-file',
       /--pkg-blacklist-file/.test(bcmd||''), bcmd);

    // 单包命令：只有 -p
    mkSetScope('single');
    var scmd = mkBuildCmd('com.target');
    ok('单包命令只有 -p', /-p com\.target/.test(scmd||'') && !/-file/.test(scmd||''), scmd);

    // 名单文件内容
    var lf = mkBuildListFile();
    ok('名单文件每行一个包', lf.split('\n').length===4, lf);

    // 持久化与恢复往返
    var sentCfg=null; var _op3=window.post;
    try { window.post=function(k,d,s,sl,ex){ if(k==='monkeysave') sentCfg=d; return _op3?_op3(k,d,s,sl,ex):null; }; } catch(e){}
    mkPersist();
    try { window.post=_op3; } catch(e){}
    ok('保存调用了 monkeysave', !!sentCfg);
    if(sentCfg){
      var parsed=JSON.parse(sentCfg);
      ok('保存内容含应用清单', (parsed.apps||'').indexOf('com.a')>=0, parsed.apps);
      ok('保存内容含范围', parsed.scope==='single', parsed.scope);
    }
    // 恢复
    _mk.apps=[];
    mkRestore({apps:'com.x|X应用|1;com.y|Y应用|0', scope:'white', exec:'rotate'});
    ok('恢复应用清单', _mk.apps.length===2, _mk.apps.length);
    ok('恢复勾选状态',
       _mk.apps[0].sel===true && _mk.apps[1].sel===false);
    ok('恢复应用名称', _mk.apps[0].name==='X应用', _mk.apps[0].name);

    // 扫描结果解析
    _mk.apps=[];
    mkOnPkgScan('package:com.scan.one\npackage:com.scan.two');
    ok('扫描结果进入清单', _mk.apps.length===2, _mk.apps.length);

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
