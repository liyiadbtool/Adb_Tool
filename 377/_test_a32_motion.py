"""A32 动效三件套 · DOM 行为测试（2026-11-21）

覆盖用户第 6 批需求的三个动画：
  1) 页签当前项用半透明玻璃胶囊做底；切换时胶囊滑到新位置，
     移动中沿方向拉长、到位弹性回弹；胶囊边缘带一圈细高光
  2) 点击卡片 → 原位放大为详情视图，关闭时原路收回
  3) 指令导航做成底部居中的浮动玻璃停靠栏，只放图标；
     悬停时当前图标放大、相邻图标跟随放大；上方显示名称

运行：python 377/_test_a32_motion.py
"""
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")


def _find_edge():
    cands = []
    for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            cands.append(os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"))
    cands += [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    ]
    for c in cands:
        if c and os.path.exists(c):
            return c
    return "msedge.exe"


EDGE = _find_edge()
PROF = os.path.join(tempfile.gettempdir(), "edgeprof_a32")

JS = r"""
<script>
(function(){
  var R = [];
  function ok(n, c, e){ R.push((c?'PASS':'FAIL')+' | '+n+(c?'':' -> '+(e===undefined?'':e))); }

  function txt(sel){ var e=document.querySelector(sel); return e?e.textContent:''; }
  function has(sel){ return !!document.querySelector(sel); }

  setTimeout(function(){
    /* ============ 需求 1：顶部页签玻璃胶囊（已恢复）============
       2026-11-22 修正：上一轮把这里误删了。
       用户原话「顶部指令、终端、文件的点击特效给我恢复，不要瞎改，
       我要改的是指令下面导航标签，顶部的没说过要改」。
       第 8 批说的「页签底部滑动条」指的是左侧导航的宽度拖拽条（.qsplit），
       不是这个顶部胶囊。所以断言恢复成"胶囊存在且有玻璃质感"。 */
    var gl = document.querySelector('.tab-glider');
    ok('A32-1 顶部页签胶囊层已恢复', !!gl);
    if (gl){
      var cs = getComputedStyle(gl);
      var bg = cs.backgroundImage || cs.background;
      ok('A32-1 胶囊底是渐变（非实色）', /gradient/.test(bg), bg.slice(0, 60));
      var bf = cs.backdropFilter || cs.webkitBackdropFilter;
      ok('A32-1 胶囊带 backdrop-filter 玻璃', /blur/.test(bf || ''), bf);
      ok('A32-1 胶囊边缘有内高光(inset)', /inset/.test(cs.boxShadow),
         cs.boxShadow.slice(0, 50));
      ok('A32-1 transform 过渡使用弹簧曲线',
         /cubic-bezier/.test(cs.transition) && /transform/.test(cs.transition),
         cs.transition.slice(0, 80));
      var actTab = document.querySelector('.tabs .tab.active');
      ok('A32-1 有激活页签', !!actTab);
      ok('A32-1 胶囊有宽度（已定位）', (parseFloat(cs.width) || 0) > 10, cs.width);
      ok('A32-1 胶囊可见（opacity>0.5）', parseFloat(cs.opacity) > 0.5, cs.opacity);
    }
    testReq2();

    function testReq2(){
      /* ============ 需求 2：原位放大详情视图 ============ */
      // 先确保在指令页、有卡片
      var card = document.querySelector('#quick-grid .qcard');
      ok('A32-2 指令页有卡片可点', !!card);
      if (!card){ finish(); return; }

      /* 2026-11-22（需求）：详情弹窗已彻底删除。
         用户原话「彻底删除这段弹窗（而不是修补动画），恢复"点卡片直接执行"」。
         所以这里断言：点卡片后**没有**任何遮罩/详情面板出现，
         命令直接进入执行态（卡片加 .running）。

         为什么之前的"卡死"要整段删而不是修：
           原实现把 runQuickAt 写进 qzClose 的 320ms 回调，
           链路一断 → 弹窗关不掉 + 命令不发 + 全屏 mask 挡住界面。 */

      // 拦截 post 以便观察是否真的下发了命令
      var posted = [];
      var _origPost = window.post;
      try {
        window.post = function(k, v){ posted.push({k:k, v:v}); return _origPost ? _origPost(k,v) : null; };
      } catch(e) {}

      card.click();

      setTimeout(function(){
        // 1) 不出现任何弹窗/遮罩
        ok('A32-2 点击卡片不弹详情面板', !document.querySelector('.qz-panel'));
        ok('A32-2 点击卡片不出现遮罩', !document.querySelector('.qz-mask'));
        ok('A32-2 界面上无残留 .qz-* 元素',
           document.querySelectorAll('[class*="qz-"]').length === 0,
           document.querySelectorAll('[class*="qz-"]').length);

        // 2) 卡片直接进入执行态（说明 onclick=runQuick 真的被触发了）
        ok('A32-2 卡片直接进入执行态（running）',
           card.classList.contains('running') || posted.length > 0,
           'running=' + card.classList.contains('running') + ' posts=' + posted.length);

        // 3) 恢复了原生 onclick（这是"直接执行"的结构保证）
        ok('A32-2 卡片保留原生 onclick=runQuick*',
           /runQuick/.test(card.getAttribute('onclick') || ''),
           card.getAttribute('onclick'));

        try { window.post = _origPost; } catch(e) {}
        testReq3();
      }, 700);
    }

    function testReq3(){
      /* ============ 需求 3（已改向）：底部 Dock 删除，特征迁到导航 ============
         2026-11-21 用户明确要求「底部的 dock 栏要删除」。
         所以这里反过来断言：Dock 必须不存在；而它的两个交互特征
         （图标化 + 悬停名称气泡）必须已经落在左侧导航项上。 */
      ok('A32-3 底部 Dock 已删除', !document.querySelector('.qdock'));
      ok('A32-3 无残留 .qdock-item', !document.querySelector('.qdock-item'));
      ok('A32-3 无残留 .qdock-tip', !document.querySelector('.qdock-tip'));

      // 特征迁移：导航项必须带图标 + 名称气泡
      var navItems = document.querySelectorAll('.qnav-item');
      ok('A32-3 导航项存在', navItems.length > 0, navItems.length);
      var allIco = true, allTip = true, allName = true;
      for (var i = 0; i < navItems.length; i++){
        if (!navItems[i].querySelector('.qico2 svg')) allIco = false;
        if (!navItems[i].querySelector('.qnav-tip')) allTip = false;
        if (!navItems[i].querySelector('.qname2')) allName = false;
      }
      ok('A32-3 每个导航项都有图标', allIco);
      ok('A32-3 每个导航项都有名称气泡', allTip);
      ok('A32-3 每个导航项都有名称节点', allName);

      // 名称气泡内容 = 分组名
      var tip0 = navItems[0] ? navItems[0].querySelector('.qnav-tip') : null;
      ok('A32-3 气泡文字是分组名',
         tip0 && tip0.textContent.trim() === quickGroups[0].name,
         tip0 ? tip0.textContent : 'none');

      // 收集 CSS 规则，验证图标态的悬停放大与气泡显示
      var cssTxt = '';
      for (var si = 0; si < document.styleSheets.length; si++){
        try{
          var rules = document.styleSheets[si].cssRules || [];
          for (var ri = 0; ri < rules.length; ri++){
            if (rules[ri].selectorText) cssTxt += rules[ri].selectorText + '\n';
          }
        }catch(e){}
      }
      ok('A32-3 有图标态悬停放大规则',
         /data-navlabels="0"\] \.qnav-item:hover/.test(cssTxt), '见 CSS');
      ok('A32-3 有图标态气泡显示规则',
         /data-navlabels="0"\] \.qnav-item:hover \.qnav-tip/.test(cssTxt), '见 CSS');

      finish();
    }

    function finish(){
      document.title = '@@R@@' + JSON.stringify(R) + '@@E@@';
    }
  }, 1500);
})();
</script>
"""


def main():
    src = open(UI, encoding="utf-8").read()
    out_html = os.path.join(ROOT, "377", "test_a32_motion.html")
    open(out_html, "w", encoding="utf-8", newline="").write(
        src.replace("</body>", JS + "</body>"))

    args = [
        EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
        "--user-data-dir=", "--no-first-run", "--no-default-browser-check", "--disable-background-networking", "--disable-sync", "--disable-extensions", "--disable-component-update" + PROF,
        "--virtual-time-budget=12000",
        "--dump-dom",
        "file:///" + out_html.replace("\\", "/"),
    ]
    try:
        p = subprocess.run(args, capture_output=True, timeout=120)
        dom = p.stdout.decode("utf-8", "replace")
    except Exception as e:
        print("!! 浏览器执行失败:", e)
        return 2
    finally:
        try:
            os.remove(out_html)
        except Exception:
            pass

    m = re.search(r"@@R@@(.*?)@@E@@", dom, re.S)
    if not m:
        print("!! 探针未返回，页面可能报错")
        # 打印可能的错误
        for mm in re.finditer(r"(Uncaught[^<\n]{0,200})", dom):
            print("   ", mm.group(1))
        return 2

    import json
    results = json.loads(m.group(1))
    for line in results:
        print("  " + line)

    fail = sum(1 for r in results if r.startswith("FAIL"))
    print("")
    print("  A32 动效三件套：通过 %d / %d" % (len(results) - fail, len(results)))
    if fail:
        print("  有 %d 项失败" % fail)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
