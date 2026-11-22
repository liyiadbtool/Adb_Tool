"""诊断页回归测试（2026-11-22）。

用户需求：
  · 诊断是否安装 adb，装了显示版本，没装提示并支持一键安装**内置** adb
  · 本机 CPU / 内存(DDR4/DDR5) / Windows / 分辨率+缩放 / 存储 / 设备名 / 系统类型
  · 连上设备后显示 ROOT / 车型 / SOC / MCU / Android / VIN / UUID / DID / OPENID / 分辨率 / 设备ID
  · 诊断数据要能「一键单独复制某一项」
  · 内存信息里显示本工具在 CPU 的占比
  · 用户明确去掉：磁盘健康、温度、GPU

运行：python 377/_test_diag.py
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
setTimeout(function(){
  var R=[];
  function ok(n,c,e){R.push((c?'PASS':'FAIL')+' | '+n+(c?'':' -> '+(e===undefined?'':e)));}

  /* ---- 1. 页签存在并能切换 ---- */
  var tabs=document.querySelectorAll('.tab');
  var diagTab=null;
  for(var i=0;i<tabs.length;i++) if(tabs[i].dataset.tab==='diag') diagTab=tabs[i];
  ok('一级页签含「诊断」', !!diagTab, diagTab?diagTab.textContent.trim():'无');
  ok('诊断页容器存在', !!document.getElementById('page-diag'));

  switchTab('diag');
  ok('切到诊断页后可见',
     document.getElementById('page-diag').classList.contains('active'));
  ok('诊断页签高亮', diagTab.classList.contains('active'));

  /* ---- 2. 五块区域齐全 ---- */
  ['adb','pc','car','link','res','hist'].forEach(function(s){
    ok('卡片存在：'+s, !!document.getElementById('diag-card-'+s));
  });

  /* ---- 3. 顶部按钮 ---- */
  ok('重新检测按钮存在',
     document.querySelector('[onclick="diagRefresh()"]')!==null);
  ok('复制全部按钮存在',
     document.querySelector('[onclick="diagCopyAll()"]')!==null);
  ok('保存快照按钮存在',
     document.querySelector('[onclick="diagSaveSnapshot()"]')!==null);

  /* ---- 4. 本机信息渲染（模拟 C# 回包）---- */
  diagOnLocal({
    ok:true,
    adb:'C:\\Tools\\platform-tools\\adb.exe',
    adbsrc:'系统 PATH',
    rows:[
      {k:'CPU', v:'Intel i7-12700H  12 核 / 20 线程', lv:''},
      {k:'内存', v:'32 GB  DDR5-4800MHz', lv:''},
      {k:'Windows', v:'Windows 11 专业版  (Build 22631)', lv:''},
      {k:'系统版本号', v:'10.0.22631', lv:''},
      {k:'系统类型', v:'64 位', lv:''},
      {k:'设备名称', v:'TEST-PC', lv:''},
      {k:'屏幕分辨率', v:'2560 × 1600  @150% 缩放', lv:''},
      {k:'存储 C:', v:'512 GB（剩余 120 GB）', lv:''}
    ]
  });

  var pcRows=document.querySelectorAll('#diag-rows-pc .diag-row');
  ok('本机信息已渲染', pcRows.length===8, pcRows.length);

  var pcText=document.getElementById('diag-rows-pc').textContent;
  ok('显示 CPU', pcText.indexOf('i7-12700H')>=0);
  ok('显示内存且带 DDR 代数', /DDR5/.test(pcText), pcText.slice(0,80));
  ok('显示 Windows 版本', /Windows 11/.test(pcText));
  ok('显示系统类型', /64 位/.test(pcText));
  ok('显示分辨率+缩放', /2560/.test(pcText) && /150%/.test(pcText));

  /* ---- 5. adb 状态 ---- */
  var adbText=document.getElementById('diag-rows-adb').textContent;
  ok('adb 显示已找到', /已找到/.test(adbText), adbText.slice(0,60));
  ok('adb 显示来源', /系统 PATH/.test(adbText), adbText.slice(0,80));
  ok('adb 状态点为正常色',
     document.getElementById('diag-adb-dot').className.indexOf('ok')>=0);

  /* ---- 6. adb 未安装时应给一键启用按钮 ---- */
  diagOnLocal({ok:true, adb:'adb', adbsrc:'未找到', rows:[]});
  var adbText2=document.getElementById('diag-rows-adb').textContent;
  ok('未安装时提示未找到', /未安装/.test(adbText2), adbText2.slice(0,60));
  ok('未安装时给出一键启用按钮',
     document.querySelector('[onclick="diagInstallBuiltinAdb()"]')!==null);
  ok('未安装时状态点为异常色',
     document.getElementById('diag-adb-dot').className.indexOf('bad')>=0);

  /* ---- 7. 车机信息 ---- */
  diagOnCar({
    online:true, got:true, root:true, rootprobed:true, serial:'ABC123', devn:1,
    rows:[
      {k:'车型', v:'GAC-A18'},
      {k:'SOC 版本', v:'8295-A-1.2.3'},
      {k:'MCU 版本', v:'MCU-9.1'},
      {k:'Android 版本', v:'14'},
      {k:'VIN 码', v:'LVTEST1234567890'},
      {k:'UUID', v:'uuid-111'},
      {k:'DID', v:'did-222'},
      {k:'OPENID', v:'open-333'}
    ],
    res:'Physical size: 1920x720'
  });

  var carText=document.getElementById('diag-rows-car').textContent;
  ok('车机显示 ROOT 已 root', /已 root/.test(carText), carText.slice(0,40));
  ok('车机显示车型', /GAC-A18/.test(carText));
  ok('车机显示 SOC', /8295-A-1\.2\.3/.test(carText));
  ok('车机显示 MCU', /MCU-9\.1/.test(carText));
  ok('车机显示 Android', /14/.test(carText));
  ok('车机显示 VIN', /LVTEST1234567890/.test(carText));
  ok('车机显示 UUID', /uuid-111/.test(carText));
  ok('车机显示 DID', /did-222/.test(carText));
  ok('车机显示 OPENID', /open-333/.test(carText));
  ok('车机显示分辨率', /1920x720/.test(carText));
  ok('车机显示设备 ID', /ABC123/.test(carText));

  /* ---- 8. 未连接设备时的提示 ---- */
  diagOnCar({online:false});
  ok('未连接时提示',
     /没有连接设备/.test(document.getElementById('diag-rows-car').textContent));
  // 恢复
  diagOnCar({online:true, got:true, root:false, rootprobed:true, serial:'S1',
    rows:[{k:'车型',v:'X'},{k:'SOC 版本',v:'Y'}], res:'1920x720'});

  /* ---- 9. 单行复制（用户核心诉求）---- */
  var cpBtn=document.querySelector('#diag-rows-car .diag-cp');
  ok('每行都有复制按钮', cpBtn!==null);

  var copied=null, _wc=navigator.clipboard;
  try{
    Object.defineProperty(navigator,'clipboard',{
      value:{writeText:function(t){ copied=t; return Promise.resolve(); }},
      configurable:true
    });
  }catch(e){}
  if(cpBtn) diagCopyOne(cpBtn);
  ok('单行复制有内容', !!copied, copied===null?'null':copied);
  ok('单行复制带字段名', /:/.test(copied||''), copied);
  ok('单行复制内容是当前行', (copied||'').indexOf('是否 ROOT')>=0, copied);

  // 指定复制 SOC 那一行
  var socBtn=null;
  var allCp=document.querySelectorAll('#diag-rows-car .diag-cp');
  for(var ci=0;ci<allCp.length;ci++){
    if(allCp[ci].getAttribute('data-k')==='SOC 版本') socBtn=allCp[ci];
  }
  ok('SOC 行有独立复制按钮', socBtn!==null);
  copied=null;
  if(socBtn) diagCopyOne(socBtn);
  ok('单独复制 SOC 版本成功',
     (copied||'').indexOf('SOC 版本')>=0 && /Y/.test(copied||''), copied);

  try{ Object.defineProperty(navigator,'clipboard',{value:_wc,configurable:true}); }catch(e){}

  /* ---- 10. 整块复制 / 全部复制 ---- */
  ok('整块复制函数存在', typeof diagCopySection==='function');
  ok('全部复制函数存在', typeof diagCopyAll==='function');

  /* ---- 11. 资源采样（只在采样时测，无 GPU）---- */
  ok('采样按钮存在', !!document.getElementById('diag-sample-btn'));
  ok('初始未采样', _diag.sampling===false);

  diagStartSample();
  ok('开始采样后状态为真', _diag.sampling===true);
  ok('采样按钮文案变为停止',
     document.getElementById('diag-sample-btn').textContent==='停止采样');

  diagOnSample({cpu:12.5, mem:180});
  var resText=document.getElementById('diag-rows-res').textContent;
  ok('采样显示 CPU 占比', /12\.5/.test(resText), resText.slice(0,60));
  ok('采样显示内存', /180/.test(resText));

  var resAll=resText;
  ok('不显示 GPU（用户已去掉）', resAll.indexOf('GPU')<0, resAll.slice(0,80));

  diagStopSample();
  ok('停止后状态为假', _diag.sampling===false);
  ok('停止后按钮恢复',
     document.getElementById('diag-sample-btn').textContent==='开始采样');

  /* ---- 12. 不显示已去除的项 ---- */
  ok('无磁盘健康项（已去掉）',
     document.getElementById('diag-rows-pc').textContent.indexOf('磁盘健康')<0);
  ok('无温度项（已去掉）',
     document.getElementById('diag-rows-pc').textContent.indexOf('温度')<0);

  /* ---- 13. 快照历史 ---- */
  ok('历史渲染函数存在', typeof diagRenderHist==='function');
  try{ localStorage.removeItem('diag_history_v1'); }catch(e){}
  _diag.hist=[];
  _diag.local=[{k:'CPU',v:'测试CPU',lv:''},{k:'本工具 CPU',v:'5%',lv:''}];
  diagSaveSnapshot();
  ok('保存后历史有 1 条', _diag.hist.length===1, _diag.hist.length);
  if(_diag.hist.length){
    var snap=_diag.hist[0];
    ok('快照含本机字段', !!snap.pc && snap.pc['CPU']==='测试CPU', JSON.stringify(snap.pc));
    ok('快照不含实时采样字段',
       !snap.pc['本工具 CPU'], JSON.stringify(snap.pc));
  }
  ok('历史条目已渲染',
     document.querySelectorAll('.diag-hist-item').length===1);

  diagClearHistory();
  ok('清空后历史为 0', _diag.hist.length===0);

  ok('无运行时错误', window.__E.length===0, window.__E.join('; '));

  var pre=document.createElement('pre');
  pre.id='DIAG_RESULT';
  pre.textContent=JSON.stringify(R);
  document.body.appendChild(pre);
}, 1800);
</script>
"""


def main():
    src = open(UI, encoding="utf-8").read()
    tmp = os.path.join(ROOT, "377", "_diag.html")
    open(tmp, "w", encoding="utf-8", newline="").write(src.replace("</body>", PROBE + "</body>"))
    try:
        p = subprocess.run(
            [EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--no-first-run", "--no-default-browser-check",
             "--disable-background-networking", "--disable-sync",
             "--disable-extensions", "--disable-component-update",
             "--user-data-dir=" + os.path.join(tempfile.gettempdir(), "edgeprof_diag"),
             "--window-size=1280,900", "--virtual-time-budget=14000", "--dump-dom",
             "file:///" + tmp.replace("\\", "/")],
            capture_output=True, timeout=180)
        dom = p.stdout.decode("utf-8", "replace")
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass

    m = re.search(r'<pre id="DIAG_RESULT">(.*?)</pre>', dom, re.S)
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
    print("  诊断页：通过 %d / %d" % (len(results) - fail, len(results)))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
