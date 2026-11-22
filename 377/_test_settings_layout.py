"""设置面板布局与导航回归测试（第 9 批需求，2026-11-22）。

用户 6 条需求：
  1  恢复顶部页签玻璃胶囊动效（上一轮误删，见 _test_a32_motion 的 A32-1）
  2  主题按钮自适应一行、不留白
  3  强调色只留滑动条，16 个方形色块去掉
  4  「显示」的三个开关并排一行
  5  字体大小 + 导航栏显示名称并排一行
  6  去掉导航宽度的拖拽分隔条，宽度自适应内容（但保留分组拖拽排序）

关键约束：
  · 需求3 的色块**只能隐藏不能删** —— applyAccent() 靠遍历 .accent-dot 同步选中态，
    删掉节点会让强调色的选中状态失效。
  · 需求6 只去掉"拖宽度"（.qsplit），分组拖拽排序（applyNavOrder）必须保留，
    两者是完全不同的东西，不要一起删。

运行：python 377/_test_settings_layout.py
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
  try{ toggleSettings(); }catch(e){}
  setTimeout(function(){
    /* ---- 需求2：主题按钮撑满可用宽度 ---- */
    var th=document.getElementById('set-theme');
    var seg=th?th.getBoundingClientRect():{width:0};
    var panel=document.querySelector('.set-body');
    var pw=(panel?panel.clientWidth:0) - 36;   // .set-body 左右各 18px padding
    ok('需求2 主题按钮组撑满可用宽度', seg.width > pw*0.95,
       Math.round(seg.width)+' / '+Math.round(pw));

    /* ---- 需求3：色块隐藏、滑动条可见 ---- */
    var pop=document.getElementById('accent-pop');
    ok('需求3 色块容器已隐藏',
       !pop || getComputedStyle(pop).display==='none',
       pop?getComputedStyle(pop).display:'none');
    ok('需求3 色块 DOM 仍保留（选中态依赖它）',
       document.querySelectorAll('.accent-dot').length === 16,
       document.querySelectorAll('.accent-dot').length);
    var track=document.getElementById('as-track');
    ok('需求3 滑动条仍可见', !!track && track.getBoundingClientRect().height>0);

    /* ---- 需求4：显示三按钮同排 ---- */
    var ids=['set-auto','set-oled','set-eyelevel'];
    var tops=ids.map(function(id){var e=document.getElementById(id);return e?Math.round(e.getBoundingClientRect().top):-999;});
    ok('需求4 显示三按钮同一行',
       tops.every(function(t){return Math.abs(t-tops[0])<6;}), tops.join(','));

    /* ---- 需求5：字号与导航名称同排 ---- */
    var fs=document.getElementById('set-fsize');
    var nl=document.getElementById('set-navlabels');
    var t1=fs?Math.round(fs.getBoundingClientRect().top):-999;
    var t2=nl?Math.round(nl.getBoundingClientRect().top):-999;
    ok('需求5 字号与导航名称同一行', Math.abs(t1-t2)<10, t1+' vs '+t2);

    /* ---- 需求6：去拖拽条、宽度自适应、保留分组排序 ---- */
    ok('需求6 导航拖拽条已删除', !document.getElementById('qsplit'));
    ok('需求6 导航拖拽条 CSS 已删除',
       document.querySelectorAll('.qsplit').length === 0);
    var nav=document.getElementById('quick-nav');
    if(nav){
      var w=nav.getBoundingClientRect().width;
      ok('需求6 导航宽度自适应（不是 168 固定）', w>0 && w<300, Math.round(w));
    }
    ok('需求6 分组拖拽排序保留（applyNavOrder 存在）',
       typeof applyNavOrder === 'function');

    ok('无运行时错误', window.__E.length===0, window.__E.join('; '));
    document.title='@@R@@'+JSON.stringify(R)+'@@E@@';
  }, 900);
}, 1500);
</script>
"""


def main():
    src = open(UI, encoding="utf-8").read()
    tmp = os.path.join(ROOT, "377", "_lay.html")
    open(tmp, "w", encoding="utf-8", newline="").write(src.replace("</body>", PROBE + "</body>"))
    try:
        p = subprocess.run(
            [EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--no-first-run", "--no-default-browser-check",
             "--disable-background-networking", "--disable-sync",
             "--disable-extensions", "--disable-component-update",
             "--user-data-dir=" + os.path.join(tempfile.gettempdir(), "edgeprof_layout"),
             "--window-size=1280,900", "--virtual-time-budget=10000", "--dump-dom",
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
        print("!! 探针未返回")
        for mm in re.finditer(r"(Uncaught[^<\n]{0,160})", dom):
            print("   ", mm.group(1))
        return 2

    results = json.loads(m.group(1))
    for line in results:
        print("  " + line)
    fail = sum(1 for r in results if r.startswith("FAIL"))
    print("")
    print("  设置面板布局：通过 %d / %d" % (len(results) - fail, len(results)))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
