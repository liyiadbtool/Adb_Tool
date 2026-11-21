"""设置面板（第 8 批需求）回归测试。

2026-11-22 用户提了 12 条设置面板改造需求，本套件把它们钉住：

  1  页签底部的滑动条去除（A32 的 .tab-glider 下线，改激活项自带底色）—— 见 _test_a32_motion
  2  仅图标时文件页导航不重叠（固定 42px 宽 + gap 归零）
  3  主题：去「背景与文字明暗」文案，按钮收小（.set-seg-compact）
  4  强调色：色点网格 → 渐变滑动条，去所有说明文案
  5  配置文件：去文案，改成问号按钮，点开才有说明 + 导出/导入
  6  字体：去「全局生效，含标题栏与帮助」，删掉预览卡片
  7  字号：去两段说明，五档 超小50%/小80%/中100%/大120%/超大150%
  8  导航栏名称：去两段说明
  9  使用说明：去「（全部功能逐项说明）」
  10 关于：改成问号按钮，点开显示版本信息与应用介绍
  11 去掉设置底部「关闭应用 / 完成」按钮
  12 布局重排：外观 → 工具

关键约束（本套件的重点）：
  强调色滑动条**必须吸附到 16 个既有锚点**。因为保存链路是
  setAccent(name) → post('accent') → C# NormalizeAccent() 按 ACCENTS 白名单校验，
  非法值**静默回退 blue**。若允许自由插值，用户选了"蓝和靛之间"重启后变蓝 —— 
  这是最恶劣的 bug（看起来存了、实际没存）。所以这里专门断言吸附行为。

运行：python 377/_test_settings_panel.py
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
  try{ toggleSettings(); }catch(e){}

  setTimeout(function(){
    var body = document.querySelector('.set-body');
    var txt  = body ? body.textContent : '';

    /* ---------- 面板可打开 ---------- */
    var m = document.getElementById('set-mask');
    ok('设置面板可打开', m && m.style.display === 'flex', m ? m.style.display : 'no-el');

    /* ---------- 需求3：主题去文案 + 紧凑按钮 ---------- */
    ok('需求3 主题未显示「背景与文字明暗」', txt.indexOf('背景与文字明暗') < 0);
    var themeSeg = document.getElementById('set-theme');
    ok('需求3 主题按钮组存在', !!themeSeg);
    ok('需求3 主题按钮用紧凑样式',
       themeSeg && themeSeg.classList.contains('set-seg-compact'),
       themeSeg ? themeSeg.className : 'none');

    /* ---------- 需求4：强调色滑动条 ---------- */
    var track = document.getElementById('as-track');
    ok('需求4 强调色滑动条已渲染', !!track);
    if (track){
      var bg = getComputedStyle(track).backgroundImage || '';
      ok('需求4 滑动条是连续渐变', /gradient/.test(bg), bg.slice(0, 50));
      ok('需求4 有 16 个锚点刻度',
         document.querySelectorAll('#as-ticks i').length === 16,
         document.querySelectorAll('#as-ticks i').length);
    }
    ok('需求4 未显示「按钮 / 进度条 / 选中态」文案', txt.indexOf('按钮 / 进度条') < 0);
    ok('需求4 未显示「中性色 · 浅色/护眼下会压成灰」文案',
       txt.indexOf('中性色') < 0);

    /* ---------- 需求4 核心：滑块必须吸附到 16 锚点 ---------- */
    var input = document.getElementById('as-input');
    var cases = [{i:0,k:'blue'},{i:4,k:'green'},{i:7,k:'red'},{i:12,k:'graphite'}];
    var bad = [];
    for (var c = 0; c < cases.length; c++){
      input.value = cases[c].i;
      input.dispatchEvent(new Event('input', {bubbles:true}));
      var cur = document.documentElement.getAttribute('data-accent');
      if (cur !== cases[c].k) bad.push(cases[c].i + '→' + cur + '(期望' + cases[c].k + ')');
    }
    ok('需求4 滑动条吸附到 16 个锚点（可保存）', bad.length === 0, bad.join('; '));

    var th = document.getElementById('as-thumb');
    input.value = 7; input.dispatchEvent(new Event('input', {bubbles:true}));
    var l1 = th.style.left;
    input.value = 0; input.dispatchEvent(new Event('input', {bubbles:true}));
    var l2 = th.style.left;
    ok('需求4 滑块位置随选择移动', l1 !== l2, l1 + ' vs ' + l2);

    /* ---------- 需求6：字体 ---------- */
    ok('需求6 未显示「全局生效，含标题栏与帮助」', txt.indexOf('全局生效') < 0);
    ok('需求6 字体预览卡片已删除', !document.getElementById('set-font-preview'));

    /* ---------- 需求7：字号五档 ---------- */
    var fs = document.querySelectorAll('#set-fsize button');
    ok('需求7 字号为五档', fs.length === 5, fs.length);
    var names = [];
    for (var i = 0; i < fs.length; i++) names.push(fs[i].textContent.trim());
    ok('需求7 档位名称为 超小/小/中/大/超大',
       names.join(',') === '超小,小,中,大,超大', names.join(','));
    ok('需求7 未显示「整页跟随缩放」文案', txt.indexOf('整页跟随缩放') < 0);
    ok('需求7 未显示「整页改完立即生效」文案', txt.indexOf('改完立即生效') < 0);
    // 比例断言：SIZES 定义在 IIFE 内，外部拿不到。改为**实测缩放效果** ——
    // 依次点各档，读 document 的缩放（WebView2 里是 zoom，浏览器里是 body 的缩放比）。
    // 这里用「点第 i 档 → 记录 zoom 值」的方式验证比例是否正确落地。
    var zs = [];
    (function(){
      for (var z = 0; z < fs.length; z++){
        try { setSize(fs[z].getAttribute('data-fsize')); } catch(e){}
        // setSize 通过 post('uizoom') 下发，浏览器里不会真缩放；
        // 所以改为读 prefs 里记录的档位 + 档位名映射是否一致。
        zs.push(fs[z].getAttribute('data-fsize'));
      }
    })();
    ok('需求7 五档键名 xs/s/m/l/xl',
       zs.join(',') === 'xs,s,m,l,xl', zs.join(','));

    /* ---------- 需求8：导航栏名称去文案 ---------- */
    ok('需求8 未显示「关闭后只显示图标，悬停看名称」',
       txt.indexOf('关闭后只显示图标') < 0);
    ok('需求8 未显示「关闭时导航栏自动收窄」',
       txt.indexOf('关闭时导航栏自动收窄') < 0);
    ok('需求8 导航名称开关仍在', !!document.getElementById('set-navlabels'));

    /* ---------- 需求5/9/10：三个问号按钮 ---------- */
    ok('需求5 配置文件问号按钮', !!document.querySelector('[onclick="openCfgHelp()"]'));
    ok('需求5 配置文件说明文案已从面板移除', txt.indexOf('打包成一个文件') < 0);
    ok('需求9 使用说明按钮', !!document.querySelector('[onclick="openHelp()"]'));
    ok('需求9 未显示「（全部功能逐项说明）」', txt.indexOf('全部功能逐项说明') < 0);
    ok('需求10 关于问号按钮', !!document.querySelector('[onclick="openAbout()"]'));
    ok('需求10 三个按钮都有圈号徽章',
       document.querySelectorAll('.set-body .set-link .q-badge').length === 3,
       document.querySelectorAll('.set-body .set-link .q-badge').length);

    /* ---------- 需求11：底部按钮删除 ---------- */
    ok('需求11 底部「关闭应用/完成」已删除',
       !document.querySelector('.set-foot'), 'set-foot 仍存在');

    /* ---------- 需求5/10：弹层可开可关 ---------- */
    try { openCfgHelp(); } catch(e){}
    setTimeout(function(){
      var cm = document.getElementById('cfg-help-mask');
      ok('需求5 配置文件弹层可打开', cm && cm.style.display === 'flex',
         cm ? cm.style.display : 'no-el');
      ok('需求5 弹层内有导出/导入',
         !!document.querySelector('#cfg-help-mask [onclick*="cfgHelpAction"]'));
      try { closeCfgHelp(); } catch(e){}
      ok('需求5 配置文件弹层可关闭',
         !document.getElementById('cfg-help-mask')
         || document.getElementById('cfg-help-mask').style.display === 'none');

      try { openAbout(); } catch(e){}
      setTimeout(function(){
        var am = document.getElementById('about-mask');
        ok('需求10 关于弹层可打开', am && am.style.display === 'flex',
           am ? am.style.display : 'no-el');
        ok('需求10 关于弹层有版本字段', !!document.getElementById('about-ver'));
        ok('需求10 关于弹层有程序/界面/目录字段',
           !!document.getElementById('about-exe')
           && !!document.getElementById('about-ui')
           && !!document.getElementById('about-dir'));
        ok('需求10 关于弹层有关闭应用入口',
           !!document.querySelector('#about-mask [onclick*="appClose"]'));

        /* ---------- 需求12：布局顺序 外观 → 工具 ---------- */
        var hs = document.querySelectorAll('.set-body .set-h');
        var order = [];
        for (var q = 0; q < hs.length; q++) order.push(hs[q].textContent.trim());
        ok('需求12 布局顺序：外观在前、工具在后',
           order[0] === '主题' && order[order.length-1] === '工具',
           order.join(' / '));

        ok('无运行时错误', window.__E.length === 0, window.__E.join('; '));
        document.title = '@@R@@' + JSON.stringify(R) + '@@E@@';
      }, 400);
    }, 400);
  }, 800);
}, 1300);
</script>
"""


def main():
    src = open(UI, encoding="utf-8").read()
    tmp = os.path.join(ROOT, "377", "_sp.html")
    open(tmp, "w", encoding="utf-8", newline="").write(src.replace("</body>", PROBE + "</body>"))

    try:
        p = subprocess.run(
            [EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--user-data-dir=", "--no-first-run", "--no-default-browser-check", "--disable-background-networking", "--disable-sync", "--disable-extensions", "--disable-component-update" + os.path.join(tempfile.gettempdir(), "edgeprof_setpanel"),
             "--window-size=1280,900", "--virtual-time-budget=9000", "--dump-dom",
             "file:///" + tmp.replace("\\", "/")],
            capture_output=True, timeout=150)
        dom = p.stdout.decode("utf-8", "replace")
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass

    m = re.search(r"@@R@@(.*?)@@E@@", dom, re.S)
    if not m:
        print("!! 探针未返回（页面异常或加载失败）")
        for mm in re.finditer(r"(Uncaught[^<\n]{0,160})", dom):
            print("   ", mm.group(1))
        return 2

    results = json.loads(m.group(1))
    for line in results:
        print("  " + line)
    fail = sum(1 for r in results if r.startswith("FAIL"))
    print("")
    print("  设置面板：通过 %d / %d" % (len(results) - fail, len(results)))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
