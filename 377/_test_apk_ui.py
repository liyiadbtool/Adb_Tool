"""APK 管理面板（2026-11-13）的 DOM 行为测试。

覆盖：
  1) 「APK管理」分组：导航计数、面板/网格互斥
  2) 下拉：只显示名称、包名参与过滤但不显示、键盘选择、点选
  3) 按钮禁用态：未选应用 / 设备离线
  4) 管理列表：两列都显示、增删走消息、ack 失败原样提示
  5) 动作：点击后清空旧结果并写头行、src=3 输出进面板而不是日志区
  6) 版本结果：名称/包名/版本/路径四样齐全、未安装标记、汇总、复制为 TSV

运行：python _test_apk_ui.py
"""
import os
import tempfile
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
TEST = os.path.join(ROOT, "377", "test_apk_ui.html")
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
PROF = os.path.join(tempfile.gettempdir(), "edgeprof_apkui")
JS = r"""
<script>
(function(){
  var R = [];
  function ok(name, cond, extra){
    R.push((cond ? 'PASS' : 'FAIL') + ' | ' + name + (cond ? '' : ' | ' + (extra===undefined?'':extra)));
  }
  function textOf(id){
    var e = document.getElementById(id);
    return e ? (e.textContent || '') : '';
  }

  // 截获发给 C# 的消息（真实 WebView2 里才有 chrome.webview）
  var SENT = [];
  try{
    window.chrome = window.chrome || {};
    window.chrome.webview = {
      postMessage: function(o){ SENT.push(o); },
      addEventListener: function(){}
    };
  }catch(e){}

  function findSent(kind){
    for(var i=SENT.length-1;i>=0;i--) if(SENT[i] && SENT[i].kind === kind) return SENT[i];
    return null;
  }

  var APPS = [
    {name:'个人中心', pkg:'com.gac.user.center'},
    {name:'Settings', pkg:'com.android.settings'},
    {name:'消息中心 HMI', pkg:'com.gac.msg.hmi'}
  ];

  function run(){
    try{
      buildSlots();

      // ---------- 1. 分组与面板 ----------
      var apkIdx = -1;
      for(var i=0;i<quickGroups.length;i++) if(quickGroups[i].panel === 'apk') apkIdx = i;
      ok('存在 panel=apk 的分组', apkIdx >= 0, apkIdx);
      ok('该分组没有卡片', apkIdx >= 0 && quickGroups[apkIdx].items.length === 0);

      switchTab('quick');
      switchQuickGroup(apkIdx);
      ok('切到 APK 分组：面板显示',
         document.getElementById('apk-panel').style.display !== 'none',
         document.getElementById('apk-panel').style.display);
      ok('切到 APK 分组：卡片网格隐藏',
         document.getElementById('quick-grid').style.display === 'none',
         document.getElementById('quick-grid').style.display);
      var navTxt = document.getElementById('quick-nav').textContent;
      ok('导航里显示「管理」而不是 0', navTxt.indexOf('管理') >= 0, navTxt.slice(0, 120));

      // ---------- 2. 下拉 ----------
      setApkApps(APPS);
      ok('三条应用进入列表', _apkApps.length === 3, _apkApps.length);
      ok('未选中时按钮禁用', document.getElementById('apk-btn-clear').disabled);

      toggleApkDrop();
      ok('下拉展开', document.getElementById('apk-drop').style.display !== 'none');
      var dropTxt = textOf('apk-list');
      ok('下拉显示名称', dropTxt.indexOf('个人中心') >= 0, dropTxt.slice(0, 80));
      ok('下拉不显示包名', dropTxt.indexOf('com.gac.user.center') < 0, dropTxt.slice(0, 80));
      ok('非中文名称也能显示', dropTxt.indexOf('Settings') >= 0, dropTxt.slice(0, 120));

      // 过滤：用包名也能找到（但下拉里不显示包名）
      var f = document.getElementById('apk-filter');
      f.value = 'settings';
      renderApkDrop();
      var filtered = document.getElementById('apk-list').querySelectorAll('.apk-item');
      ok('按包名过滤命中 1 条', filtered.length === 1, filtered.length);

      // 键盘：ArrowDown + Enter
      onApkFilterKey({key:'ArrowDown', preventDefault:function(){}});
      onApkFilterKey({key:'Enter', preventDefault:function(){}});
      ok('键盘回车选中', _apkSel === 'com.android.settings', _apkSel);
      ok('选中后下拉收起', document.getElementById('apk-drop').style.display === 'none');
      ok('选择框显示名称', textOf('apk-seltext') === 'Settings', textOf('apk-seltext'));

      // ---------- 3. 禁用态 ----------
      _online = true; updateApkButtons();
      ok('在线且已选中：动作可用', !document.getElementById('apk-btn-clear').disabled);
      ok('导出按钮的 title 说明语义',
         document.getElementById('apk-btn-export').title.indexOf('APK') >= 0,
         document.getElementById('apk-btn-export').title);

      _online = false; updateApkButtons();
      ok('离线时动作禁用', document.getElementById('apk-btn-clear').disabled);
      ok('离线时版本查询禁用', document.getElementById('apk-btn-ver').disabled);
      _online = true; updateApkButtons();

      // ---------- 4. 管理列表 ----------
      openApkMgr();
      ok('管理浮层打开', document.getElementById('apk-mgr').style.display === 'flex');
      var mgrTxt = textOf('apk-mgr-list');
      ok('管理列表显示名称', mgrTxt.indexOf('个人中心') >= 0, mgrTxt.slice(0, 80));
      ok('管理列表显示包名', mgrTxt.indexOf('com.gac.user.center') >= 0, mgrTxt.slice(0, 120));

      // 新增：空名称不提交
      var before = SENT.length;
      document.getElementById('apk-new-name').value = '';
      document.getElementById('apk-new-pkg').value = 'com.x.y';
      apkAddApp();
      ok('空名称不提交', SENT.length === before, SENT.length - before);

      document.getElementById('apk-new-name').value = '车控';
      document.getElementById('apk-new-pkg').value = 'com.gac.vehicle';
      apkAddApp();
      var addMsg = findSent('apkadd');
      ok('提交新增消息', !!addMsg && addMsg.name === '车控' && addMsg.pkg === 'com.gac.vehicle', JSON.stringify(addMsg));

      // 后端拒绝：原因原样提示，不能变成"保存失败"
      onApkAck({ok:false, op:'add', msg:'名称「车控」已经存在（对应 com.x.y）'});
      ok('失败原因原样显示',
         textOf('toast').indexOf('名称「车控」已经存在') >= 0, textOf('toast'));

      onApkAck({ok:true, op:'add'});
      ok('新增成功后清空输入', document.getElementById('apk-new-name').value === '');

      // 删除
      delApk('com.gac.vehicle');
      var delMsg = findSent('apkdel');
      ok('提交删除消息', !!delMsg && delMsg.pkg === 'com.gac.vehicle', JSON.stringify(delMsg));

      // 后端回推整份列表后，选中项被删要自动清空
      setApkApps([{name:'个人中心', pkg:'com.gac.user.center'}]);
      ok('选中项被删后清空选择', _apkSel === null, _apkSel);

      closeApkMgr();
      ok('管理浮层关闭', document.getElementById('apk-mgr').style.display === 'none');

      // ---------- 5. 动作 ----------
      setApkApps(APPS);
      pickApk('com.gac.user.center');
      var logBefore = document.getElementById('logbox-0').childElementCount;
      apkAct('clear');
      ok('动作写入头行', textOf('apk-out').indexOf('清空数据') >= 0, textOf('apk-out'));
      ok('头行带包名', textOf('apk-out').indexOf('com.gac.user.center') >= 0);
      ok('执行中按钮禁用', document.getElementById('apk-btn-kill').disabled);
      var actMsg = findSent('apkact');
      ok('动作消息带 pkg+act',
         !!actMsg && actMsg.pkg === 'com.gac.user.center' && actMsg.act === 'clear',
         JSON.stringify(actMsg));
      ok('动作不写日志区',
         document.getElementById('logbox-0').childElementCount === logBefore,
         document.getElementById('logbox-0').childElementCount);

      // src=3 的输出必须进面板，不能进指令输入页
      appendLine({level:1, src:3, slot:0, text:'已清空应用数据  com.gac.user.center'});
      ok('src=3 输出进面板', textOf('apk-out').indexOf('已清空应用数据') >= 0);
      ok('src=3 输出不进日志区',
         textOf('logbox-0').indexOf('已清空应用数据') < 0, textOf('logbox-0').slice(-60));

      // end 消息收尾后按钮恢复
      endRun({ok:true, ms:120, slot:0});
      ok('收尾后按钮恢复', !document.getElementById('apk-btn-clear').disabled);

      // ---------- 6. 版本结果 ----------
      renderApkVers({ms:1800, rows:[
        {name:'个人中心', pkg:'com.gac.user.center', ver:'3.2.1.261026', code:'30201',
         path:'/data/app/~~ab==/com.gac.user.center-yy==/base.apk', ok:true},
        {name:'Settings', pkg:'com.android.settings', ver:'', code:'', path:'', ok:false}
      ]});
      var out = textOf('apk-out');
      ok('版本结果含名称', out.indexOf('个人中心') >= 0);
      ok('版本结果含包名', out.indexOf('com.gac.user.center') >= 0);
      ok('版本结果含版本号', out.indexOf('3.2.1.261026') >= 0);
      ok('版本结果含完整路径', out.indexOf('/data/app/~~ab==/') >= 0, out.slice(0, 120));
      ok('未安装有标记', out.indexOf('未安装') >= 0);
      ok('未安装行有 miss 类',
         document.querySelectorAll('#apk-out .av-item.miss').length === 1,
         document.querySelectorAll('#apk-out .av-item.miss').length);
      var sum = textOf('apk-sum');
      ok('汇总含总数与未安装数', sum.indexOf('共 2 个') >= 0 && sum.indexOf('未安装 1') >= 0, sum);
      ok('汇总含耗时', sum.indexOf('1.8s') >= 0, sum);

      // 路径必须允许换行（否则长路径会把面板撑破）
      var pathEl = document.querySelector('#apk-out .av-path');
      var cs = pathEl ? getComputedStyle(pathEl) : null;
      ok('路径可换行', !!cs && (cs.wordBreak === 'break-all' || cs.wordWrap === 'break-word'),
         cs ? cs.wordBreak : 'null');

      // 复制全部 → TSV
      copyApkOut();
      var copyMsg = findSent('copy');
      ok('复制为 TSV', !!copyMsg && copyMsg.data.indexOf('个人中心\tcom.gac.user.center\t3.2.1.261026') >= 0,
         copyMsg ? copyMsg.data.slice(0, 80) : 'null');
      ok('TSV 里未安装写文字', !!copyMsg && copyMsg.data.indexOf('\t未安装\t') >= 0);

      // 空列表
      setApkApps([]);
      apkQueryVersions();
      ok('空列表不发起查询', !findSent('apkver'));
      ok('空列表版本按钮禁用', document.getElementById('apk-btn-ver').disabled);

      // ---------- 7. 删除按钮 + 结果不被覆盖 ----------
      setApkApps(APPS);
      _online = true; _apkBusy = false;
      apkQueryVersions();
      renderApkVers({ms:900, rows:[
        {name:'个人中心', pkg:'com.gac.user.center', ver:'3.2.1.261026', code:'30201',
         path:'/data/app/~~ab==/x/base.apk', ok:true}
      ]});

      var btns = document.querySelectorAll('#apk-panel .apk-foot .btn');
      var delBtn = null;
      for(var bi=0; bi<btns.length; bi++){
        if((btns[bi].textContent || '').indexOf('删除') >= 0) delBtn = btns[bi];
      }
      ok('底部有删除按钮', !!delBtn);
      ok('删除按钮在复制全部右边',
         !!delBtn && btns[btns.length-1] === delBtn,
         btns.length ? btns[btns.length-1].textContent : 'none');

      // 新指令不能把上一次的版本结果冲掉
      _apkBusy = false;
      apkRunCmd(':pkg now');
      var outAfter = textOf('apk-out');
      ok('执行新指令后旧版本结果仍在', outAfter.indexOf('3.2.1.261026') >= 0, outAfter.slice(0, 80));
      ok('新指令有自己的段落标题', outAfter.indexOf(':pkg now') >= 0, outAfter.slice(-80));
      ok('两段结果共存',
         document.querySelectorAll('#apk-out .apk-sec').length >= 2,
         document.querySelectorAll('#apk-out .apk-sec').length);
      var cmdMsg = findSent('apkcmd');
      ok('指令消息带 cmd', !!cmdMsg && cmdMsg.cmd === ':pkg now', JSON.stringify(cmdMsg));

      // 删除：清空全部输出
      apkOutClear();
      ok('删除后旧内容消失', textOf('apk-out').indexOf('3.2.1.261026') < 0, textOf('apk-out').slice(0, 60));
      ok('删除后回到空态', textOf('apk-out').indexOf('还没有输出') >= 0, textOf('apk-out').slice(0, 60));

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
        "--window-size=" + win,
        "--virtual-time-budget=6000",
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
    print("  APK 管理：通过 %d / %d" % (len(lines) - len(fails), len(lines)))
    if fails:
        print("  有 %d 项失败" % len(fails))
        return 1
    print("  APK 管理行为全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
