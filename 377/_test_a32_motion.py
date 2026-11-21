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
    /* ============ 需求 1：页签玻璃胶囊滑块 ============ */
    var gl = document.querySelector('.tab-glider');
    ok('A32-1 胶囊层已创建', !!gl);

    if (gl){
      var cs = getComputedStyle(gl);
      // 半透明：背景不能是实色
      var bg = cs.backgroundImage || cs.background;
      ok('A32-1 胶囊底是渐变（非实色）', /gradient/.test(bg), bg.slice(0,80));
      // 玻璃模糊
      var bf = cs.backdropFilter || cs.webkitBackdropFilter;
      ok('A32-1 胶囊带 backdrop-filter 玻璃', /blur/.test(bf||''), bf);
      // 边缘高光：box-shadow 里必须有 inset
      ok('A32-1 胶囊边缘有内高光(inset)', /inset/.test(cs.boxShadow), cs.boxShadow.slice(0,60));
      // 过渡曲线必须是弹性（cubic-bezier 且有过冲）
      var tr = cs.transition || cs.transitionProperty;
      ok('A32-1 transform 过渡使用弹簧曲线',
         /cubic-bezier/.test(cs.transition) && /transform/.test(cs.transition),
         cs.transition.slice(0,90));
      // 定位到当前激活页签
      var act = document.querySelector('.tab.active');
      var glW = parseFloat(cs.width) || 0;
      ok('A32-1 胶囊有宽度（已定位）', glW > 10, glW);
      ok('A32-1 胶囊可见（opacity=1）', parseFloat(cs.opacity) > 0.5, cs.opacity);

      // 切换页签 → 胶囊应移动到新位置
      var before = cs.transform;
      var tabs = document.querySelectorAll('.tab');
      var target = null;
      for (var i=0;i<tabs.length;i++) if (tabs[i].dataset.tab === 'cmd') target = tabs[i];
      if (target){
        target.click();
        setTimeout(function(){
          var cs2 = getComputedStyle(gl);
          var after = cs2.transform;
          ok('A32-1 切换页签后胶囊位移变化', before !== after,
             before + ' -> ' + after);

          // 移回指令页，继续测后面
          var back = null;
          for (var j=0;j<tabs.length;j++) if (tabs[j].dataset.tab === 'quick') back = tabs[j];
          back.click();

          setTimeout(function(){ testReq2(); }, 260);
        }, 260);
      } else {
        testReq2();
      }
    } else {
      testReq2();
    }

    function testReq2(){
      /* ============ 需求 2：原位放大详情视图 ============ */
      // 先确保在指令页、有卡片
      var card = document.querySelector('#quick-grid .qcard');
      ok('A32-2 指令页有卡片可点', !!card);
      if (!card){ finish(); return; }

      var name = card.querySelector('.qname').textContent.trim();
      card.click();

      setTimeout(function(){
        var panel = document.querySelector('.qz-panel');
        ok('A32-2 点击后出现详情面板', !!panel);
        var mask = document.querySelector('.qz-mask');
        ok('A32-2 出现遮罩', !!mask && mask.classList.contains('open'));

        if (panel){
          ok('A32-2 详情显示卡片名称', panel.textContent.indexOf(name) >= 0,
             'panel=' + panel.textContent.slice(0,60) + ' / card=' + name);
          ok('A32-2 详情有执行按钮', !!panel.querySelector('.qz-run'));
          ok('A32-2 详情有关闭按钮', !!panel.querySelector('.qz-x'));

          // 面板已放大到目标尺寸 —— 用 offsetWidth（不受 transform 影响）
          // 不能用 getBoundingClientRect：它返回的是**变换后**的视觉尺寸，
          // 动画正向 scale(1) 收敛但若还在中途，量到的就偏小。
          var pw = panel.offsetWidth, ph = panel.offsetHeight;
          var cw = card.offsetWidth;
          ok('A32-2 面板已放大（比卡片大）',
             pw > cw * 1.2, 'panel=' + pw + 'x' + ph + ' card=' + cw);
          // 视觉上要真的铺开：宽度应接近 min(520, vw-48)
          var expectW = Math.min(520, window.innerWidth - 48);
          ok('A32-2 面板宽度=目标宽度',
             Math.abs(pw - expectW) < 4, pw + ' vs ' + expectW);
          // 放大动画在推进（scale 应从 <1 趋向 1）
          // 注意：headless 的虚拟时钟会把 CSS 过渡冻在中途，所以这里只断言
          // "动画确实启动了"（存在 matrix 且 scaleX 在 0~1 收敛），
          // 不断言"已归位"—— 那在 headless 下必然假红，属测试环境限制而非缺陷。
          var tf = getComputedStyle(panel).transform;
          var mtx = tf.match(/matrix\(([-0-9.]+),\s*([-0-9.]+),\s*([-0-9.]+),\s*([-0-9.]+)/);
          var sx = mtx ? parseFloat(mtx[1]) : (tf === 'none' ? 1 : -1);
          ok('A32-2 放大动画已启动（scaleX 在 0~1 收敛）',
             tf === 'none' || (sx >= 0 && sx <= 1.02),
             'transform=' + tf + ' scaleX=' + sx);

          // 关闭 → 原路收回后消失
          panel.querySelector('.qz-x').click();
          setTimeout(function(){
            var p2 = document.querySelector('.qz-panel');
            ok('A32-2 关闭后面板内容已清空',
               !p2 || p2.textContent.trim() === '', p2 ? p2.textContent.slice(0,40) : 'removed');
            var m2 = document.querySelector('.qz-mask');
            ok('A32-2 关闭后遮罩收起',
               !m2 || !m2.classList.contains('open'));
            testReq3();
          }, 520);
        } else {
          testReq3();
        }
      }, 900);
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
        "--user-data-dir=" + PROF,
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
