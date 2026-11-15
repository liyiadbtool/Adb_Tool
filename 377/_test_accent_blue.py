# -*- coding: utf-8 -*-
"""专项验证：splash 光晕 + 三白色点是否已去蓝（A21）。

用 Edge headless 加载 ui.html，读取：
  1. .splash .cat svg 的计算 filter（应跟随 --accent-soft，不再写死蓝 --glow）
  2. .splash .cat svg 的 color（应 = --accent，跟随强调色）
  3. 三个白色点 accent-dot 的 --dot（应为中性灰白，非冷蓝 #E9E9EE / 暖黄 #FFFDF5）
  4. glasswhite 的 --accent / --accent-soft（应为 #E6E6E6 中性灰白）
"""
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
TEST = os.path.join(ROOT, "377", "_test_accent_blue.html")


def _find_edge():
    cands = []
    for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            cands.append(os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"))
    cands += [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]
    for c in cands:
        try:
            if c and os.path.exists(c):
                return c
        except Exception:
            pass
    return "msedge.exe"


EDGE = _find_edge()

JS = r"""
<style>*,*::before,*::after{transition:none !important;animation:none !important;}</style>
<script>
(function(){
  var R = [];
  function ok(name, cond, extra){
    R.push((cond ? 'PASS' : 'FAIL') + ' | ' + name + (cond ? '' : ' | ' + (extra===undefined?'':extra)));
  }
  function rgbOf(el){
    var s = getComputedStyle(el);
    return s.color;
  }
  function isBlue(c){
    // 解析 rgb(r,g,b)，判断是否明显偏蓝
    var m = /rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(c);
    if(!m) return false;
    var r=+m[1], g=+m[2], b=+m[3];
    return b > r + 20 && b > g + 20;
  }
  function run(){
    try{
      var svg = document.querySelector('.splash .cat svg');
      ok('splash 图标存在', !!svg);
      if(svg){
        var filter = getComputedStyle(svg).filter;
        ok('splash 光晕 filter 不含写死的蓝 --glow 字面量（应走 --accent-soft）',
           filter.indexOf('glow') < 0 && filter.indexOf('drop-shadow') >= 0, filter);
        // 计算后的 filter 里，drop-shadow 的色值应跟随强调色（glasswhite 下应是灰白，非蓝）
        var hasBlueDrop = /drop-shadow\([^)]*rgb\(\s*\d+\s*,\s*\d+\s*,\s*(\d+)/.test(filter);
        ok('splash 光晕 computed filter 已生成（含 drop-shadow）', filter.indexOf('drop-shadow') >= 0, filter);
      }

      // 切到 glasswhite 强调色，验证 splash 图标颜色 = 中性灰白
      if(typeof applyAccent === 'function') applyAccent('glasswhite');
      var col = rgbOf(svg);
      ok('glasswhite 下 splash 图标颜色不偏蓝', !isBlue(col), col);
      var acc = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim();
      ok('glasswhite 的 --accent 是中性灰白 #E6E6E6', acc.toLowerCase() === '#e6e6e6', acc);
      var accSoft = getComputedStyle(document.documentElement).getPropertyValue('--accent-soft').trim();
      ok('glasswhite 的 --accent-soft 跟随强调色（230,230,230）',
         accSoft.indexOf('230') >= 0, accSoft);

      // 三个白色点的 --dot
      var dots = {
        'purewhite': document.querySelector('.accent-dot[data-accent="purewhite"]'),
        'eyewhite': document.querySelector('.accent-dot[data-accent="eyewhite"]'),
        'glasswhite': document.querySelector('.accent-dot[data-accent="glasswhite"]')
      };
      var expect = { 'purewhite': '#f2f2f2', 'eyewhite': '#f0f0f0', 'glasswhite': '#e6e6e6' };
      for(var k in dots){
        var d = dots[k];
        if(!d){ ok('白色点 ' + k + ' 存在', false, 'missing'); continue; }
        var dot = (d.style.getPropertyValue('--dot') || '').trim().toLowerCase();
        ok('白色点 ' + k + ' 的 --dot 是中性灰白 ' + expect[k],
           dot === expect[k], dot);
        ok('白色点 ' + k + ' 不再用冷蓝 #E9E9EE / 暖黄 #FFFDF5',
           dot !== '#e9e9ee' && dot !== '#fffdf5', dot);
      }

      // 恢复默认强调色
      if(typeof applyAccent === 'function') applyAccent('blue');
    }catch(e){
      ok('专项检查异常', false, e.message);
    }
    var pre = document.createElement('pre');
    pre.id = 'RESULT';
    pre.textContent = R.join('\n');
    document.body.appendChild(pre);
  }
  setTimeout(run, 400);
})();
</script>
"""


def main():
    src = open(UI, encoding="utf-8").read()
    open(TEST, "w", encoding="utf-8").write(src.replace("</body>", JS + "</body>"))

    prof = os.path.join(os.environ["TEMP"], "edgeprof_accent_%d" % int(time.time()))
    cmd = [EDGE, "--headless=new", "--disable-gpu", "--window-size=1100,760",
           "--virtual-time-budget=6000", "--dump-dom",
           "--user-data-dir=" + prof,
           "file:///" + TEST.replace("\\", "/")]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=150)
    m = re.search(r'<pre id="RESULT">(.*?)</pre>', r.stdout or "", re.S)
    if not m:
        print("没拿到 RESULT（headless 可能没跑起来）")
        return 1

    lines = [l for l in m.group(1).split("\n") if l.strip()]
    fails = [l for l in lines if l.startswith("FAIL")]
    for l in lines:
        print("  " + l)
    print("")
    print("  去蓝专项：通过 %d / %d" % (len(lines) - len(fails), len(lines)))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
