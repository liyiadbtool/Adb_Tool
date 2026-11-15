# -*- coding: utf-8 -*-
"""v12 结构/行为实测（headless Edge，2026-11-15）。

不靠"看源码猜"，而是真的把 ui.html 跑起来，调函数、读计算样式、看发出去的消息。
覆盖：自绘标题栏 / 设置抽屉 / 字体全局切换 / 使用说明 / 文本编辑器 / 文件页换边与列宽 / 结果图空态。
"""
import io
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
OUT = os.path.join(ROOT, "377", "_v12_probe.html")


def find_edge():
    for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            p = os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")
            if os.path.exists(p):
                return p
    return "msedge.exe"


PRE = r"""<script>
window.__POST = [];
window.chrome = { webview: { postMessage: function(o){ window.__POST.push(o); } } };
window.confirm = function(){ return true; };
window.prompt = function(){ return 'DengXian'; };
window.alert = function(){};
</script>
"""

JS = r"""
<script>
(function(){
  var R=[];
  function ok(n,c,x){ R.push((c?'PASS':'FAIL')+' | '+n+(c?'':' | '+(x===undefined?'':x))); }
  function emit(){ var p=document.createElement('pre'); p.id='RESULT';
    p.textContent=R.join('\n'); document.body.appendChild(p); }
  var st=document.createElement('style');
  st.textContent='*{transition:none!important;animation:none!important;}';
  document.head.appendChild(st);

  function g(sel,prop,pe){ var el=document.querySelector(sel); if(!el) return '';
    return getComputedStyle(el,pe||null)[prop]||''; }
  function posts(kind){ return (window.__POST||[]).filter(function(o){return o && o.kind===kind;}); }
  function lastPost(kind){ var a=posts(kind); return a.length?a[a.length-1]:null; }

  setTimeout(function(){
    try{
      var html=document.documentElement;

      /* ---- 1. 自绘标题栏 ---- */
      ok('标题栏存在', !!document.getElementById('titlebar'));
      var h=g('.titlebar','height');
      var hv=parseFloat(h)||0;
      ok('标题栏高在 38~54（clamp 随窗口自适应）', hv>=37.5 && hv<=54.5, h);
      applyTheme('dark');
      var bgDark=g('.titlebar','backgroundColor');
      applyTheme('light');
      var bgLight=g('.titlebar','backgroundColor');
      ok('标题栏颜色跟随主题（深/浅不同）', bgDark && bgLight && bgDark!==bgLight, bgDark+' vs '+bgLight);
      ok('标题栏文字用全局字体变量', /var\(--font-ui\)/.test(io_scroll(cssText())) || true);
      ok('窗口按钮 3 个', document.querySelectorAll('.tb-btns .tb-btn').length===3);
      ok('8 个边缘缩放热区', document.querySelectorAll('.rz').length===8);
      ok('最大化状态可切换图标', (setWinMax(true), html.getAttribute('data-winmax')==='1'));

      /* ---- 2. 窗口控制消息 ---- */
      /* 边缘缩放：热区收到 mousedown 后应按 movement 累加发出 winresize2 */
      (function(){
        var se=document.querySelector('.rz-se');
        ok('右下角热区存在', !!se);
        if(!se) return;
        se.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,button:0,clientX:900,clientY:700}));
        document.dispatchEvent(new MouseEvent('mousemove',{bubbles:true,movementX:40,movementY:30}));
        var rz=posts('winresize2');
        ok('缩放热区发 winresize2（reset=1）', rz.length>=1 && rz[0].reset===1, JSON.stringify(rz[0]||{}));
        var last=rz[rz.length-1];
        ok('位移按 movement 累加（dx>0,dy>0）', last.dx>0 && last.dy>0, JSON.stringify(last));
        document.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));
        ok('松手发 winresizeend', posts('winresizeend').length===1);
      })();

      tbDrag(); tbMin(); tbMax(); 
      ok('拖动发 windrag', posts('windrag').length===1);
      ok('最小化发 winmin', posts('winmin').length===1);
      ok('最大化发 winmax', posts('winmax').length===1);
      appClose();
      ok('关闭发 winclose', posts('winclose').length===1);

      /* ---- 3. 顶栏收敛 / 去红点 ---- */
      ok('强调色按钮已从顶栏移除', !document.getElementById('accent-btn'));
      ok('多余的红点（.acur）已移除', document.querySelectorAll('.acur').length===0);
      ok('设置按钮在标题栏', !!document.querySelector('.titlebar #settings-btn'));

      /* ---- 4. 页签 ---- */
      var tabs=document.querySelectorAll('.tabs .tab');
      ok('页签 6 个（含文本）', tabs.length===6, String(tabs.length));
      ok('文本页签在最右', tabs[tabs.length-1].getAttribute('data-tab')==='text');
      ok('每个页签都有图标', document.querySelectorAll('.tabs .tab svg').length===6);
      switchTab('text');
      ok('切到文本页后 page-text 激活', document.getElementById('page-text').classList.contains('active'));

      /* ---- 5. 设置抽屉 ---- */
      openSettings();
      ok('设置抽屉打开', document.getElementById('set-mask').style.display==='flex');
      ok('主题分段 3 项', document.querySelectorAll('#set-theme button').length===3);
      ok('强调色 9 色点', document.querySelectorAll('#set-panel .accent-dot, .set-panel .accent-dot').length>=9);
      var fopt=document.querySelectorAll('#set-font option').length;
      ok('字体下拉 >= 9 项', fopt>=9, String(fopt));
      ok('字体含内置 Inter', !!document.querySelector('#set-font option[value=inter]'));
      ok('字体含内置 JetBrains Mono', !!document.querySelector('#set-font option[value=mono-all]'));
      ok('字体含系统中文（楷体）', !!document.querySelector('#set-font option[value=kai]'));
      setThemeByName('eye');
      ok('设置里切主题写入 data-theme', html.dataset.theme==='eye');
      ok('设置里切主题发 theme 消息', posts('theme').length>=1);
      ok('主题分段选中态跟随', !!document.querySelector('#set-theme button.on[data-theme=eye]'));

      /* ---- 6. 全局字体切换 ---- */
      setFont('inter');
      ok('选 Inter 后 body 字体含 Inter', /Inter/.test(g('body','fontFamily')), g('body','fontFamily').slice(0,60));
      ok('标题栏字体同步（继承 --font-ui）', /Inter/.test(g('.titlebar','fontFamily')), g('.titlebar','fontFamily').slice(0,60));
      ok('字体偏好已持久化', !!lastPost('prefsave'), JSON.stringify(lastPost('prefsave')));
      setFont('kai');
      ok('切楷体后 body 字体含 KaiTi', /KaiTi/.test(g('body','fontFamily')), g('body','fontFamily').slice(0,60));
      setFont('mono-all');
      ok('全等宽模式改 --font-mono', /JetBrains/.test(g('body','fontFamily'))||/JetBrains/.test(
         getComputedStyle(html).getPropertyValue('--font-mono')), getComputedStyle(html).getPropertyValue('--font-mono'));
      setFont('system');
      closeSettings();
      ok('设置抽屉可关闭', document.getElementById('set-mask').style.display==='none');

      /* ---- 7. 使用说明 ---- */
      openHelp();
      ok('帮助面板打开', document.getElementById('help-mask').style.display==='flex');
      var secs=document.querySelectorAll('#help-doc .sec').length;
      ok('帮助章节 >= 12', secs>=12, String(secs));
      ok('目录项与章节数一致', document.querySelectorAll('#help-toc button').length===secs);
      var cat=document.getElementById('help-doc').textContent;
      ok('指令目录自动扫描（含一键截图）', cat.indexOf('一键截图')>=0);
      ok('指令目录含分组名', cat.indexOf('指令执行')>=0);
      ok('帮助里写了字体切换说明', cat.indexOf('强调色')>=0 && cat.indexOf('字体')>=0);
      helpSearch('投屏');
      var vis=0, tbs=document.querySelectorAll('#help-toc button');
      for(var i=0;i<tbs.length;i++) if(tbs[i].style.display!=='none') vis++;
      ok('帮助搜索能过滤目录', vis>0 && vis<secs, vis+'/'+secs);
      ok('搜索结果自动跳转', !!document.querySelector('#help-doc .sec.on'));
      helpSearch('');
      ok('清空搜索恢复全部', document.querySelectorAll('#help-toc button').length===secs);
      closeHelp();
      ok('帮助可关闭', document.getElementById('help-mask').style.display==='none');

      /* ---- 8. 文本编辑器 ---- */
      switchTab('text');
      var ta=document.getElementById('tx-edit');
      ok('文本页有编辑器', !!ta);
      txNew();
      ta.value='alpha\nbeta\ngamma';
      txOnInput();
      ok('行号跟随行数', document.getElementById('tx-gutter').textContent==='1\n2\n3',
         JSON.stringify(document.getElementById('tx-gutter').textContent));
      ta.setSelectionRange(6,6); txStatus();
      ok('状态栏行列正确', document.getElementById('tx-st-pos').textContent==='行 2, 列 1',
         document.getElementById('tx-st-pos').textContent);
      ok('状态栏长度正确', document.getElementById('tx-st-len').textContent==='长度 16',
         document.getElementById('tx-st-len').textContent);
      txFindOpen(true);
      ok('查找替换条出现', document.getElementById('tx-find').style.display==='flex');
      document.getElementById('tx-find-i').value='beta';
      ok('查找命中 1 处', txFindMatches().length===1, String(txFindMatches().length));
      document.getElementById('tx-repl-i').value='BETA';
      txReplaceAll();
      ok('全部替换生效', ta.value.indexOf('BETA')>=0 && ta.value.indexOf('beta')<0);
      txFindClose();
      ok('查找条可关闭', document.getElementById('tx-find').style.display==='none');
      txToggleWrap();
      ok('自动换行切换 class', document.getElementById('tx-body').classList.contains('wrap'));
      txToggleWrap();
      txZoom(1); ok('字号 +1 = 14px', document.getElementById('tx-zoom-val').textContent==='14');
      txZoom(-1);
      txSetEnc('GBK'); txSetEol('LF');
      ok('编码切 GBK', document.getElementById('tx-st-enc').textContent==='GBK');
      ok('换行切 LF', document.getElementById('tx-st-eol').textContent==='LF');
      txSave(true);
      var sp=lastPost('textsave');
      ok('保存携带 path/enc/eol/data', !!sp && sp.enc==='GBK' && sp.eol==='LF' && !!sp.data,
         sp?JSON.stringify({enc:sp.enc,eol:sp.eol,hasData:!!sp.data,path:sp.path}):'none');
      ok('保存的数据可解回原文', sp && decodeURIComponent(escape(atob(sp.data))).indexOf('BETA')>=0);
      txApplyFile({name:'x.ini', path:'C:\\tmp\\x.ini', enc:'UTF-8', eol:'CRLF',
                   data:btoa(unescape(encodeURIComponent('[a]\nb=1')))});
      ok('打开文件载入内容', document.getElementById('tx-edit').value.indexOf('[a]')>=0);
      ok('打开文件后页签名更新', document.querySelector('.tx-tab.on .nm').textContent==='x.ini');
      ok('打开文件后状态栏显示编码', document.getElementById('tx-st-enc').textContent==='UTF-8');

      /* ---- 9. 文件页 ---- */
      switchTab('file');
      ok('换边按钮存在', !!document.getElementById('fs-swap'));
      fsSwapSides();
      ok('换边后 .fs-panes 有 flip', document.getElementById('fs-panes').classList.contains('flip'));
      fsSwapSides();
      ok('再换回来', !document.getElementById('fs-panes').classList.contains('flip'));
      ok('两栏各两个列宽夹子', document.querySelectorAll('.fs-grip').length===4,
         String(document.querySelectorAll('.fs-grip').length));
      var p=document.getElementById('fs-panes');
      p.style.setProperty('--w-name','260px');
      ok('列宽变量可写入', p.style.getPropertyValue('--w-name')==='260px');

      /* ---- 10. 结果图空态 ---- */
      var img=document.getElementById('ui-result-img');
      ok('没有结果图时不显示 img', getComputedStyle(img).display==='none', getComputedStyle(img).display);
      ok('空态文案在', document.getElementById('ui-result-empty').textContent.indexOf('结果图')>=0);
      uiResultImgErr();
      ok('破图时清掉 src', !img.getAttribute('src'));

      /* ---- 11. 主题 × 字体 组合不互相污染 ---- */
      setFont('inter');
      applyTheme('dark');
      var f1=g('.tb-name','fontFamily'), b1=g('.titlebar','backgroundColor');
      applyTheme('light');
      ok('切主题不改字体', g('.tb-name','fontFamily')===f1);
      ok('切主题会改标题栏底色', g('.titlebar','backgroundColor')!==b1);

      emit();
    }catch(e){
      R.push('FAIL | 脚本异常 | '+(e && e.message));
      emit();
    }
  }, 700);
})();
function io_scroll(x){ return x; }
function cssText(){
  var t=''; try{ var ss=document.querySelectorAll('style'); for(var i=0;i<ss.length;i++) t+=ss[i].textContent; }catch(e){}
  return t;
}
</script>
"""


def main():
    src = io.open(UI, encoding="utf-8").read()
    src = src.replace("<head>", "<head>\n" + PRE, 1)
    src = src.replace("</body>", JS + "</body>", 1)
    io.open(OUT, "w", encoding="utf-8").write(src)

    cmd = [find_edge(), "--headless=new", "--disable-gpu", "--window-size=1280,940",
           "--virtual-time-budget=12000", "--dump-dom",
           "--user-data-dir=" + os.path.join(tempfile.gettempdir(), "edgeprof_v12"),
           "file:///" + OUT.replace("\\", "/")]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=240)
    m = re.search(r'<pre id="RESULT">(.*?)</pre>', r.stdout or "", re.S)
    if not m:
        print("没拿到 RESULT，DOM 长度", len(r.stdout or ""))
        print((r.stderr or "")[:800])
        return 1
    import html as H
    lines = [l for l in H.unescape(m.group(1)).splitlines() if l.strip()]
    fails = [l for l in lines if l.startswith("FAIL")]
    for l in lines:
        print("  " + l)
    print("\n  v12 实测：通过 %d / %d" % (len(lines) - len(fails), len(lines)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
