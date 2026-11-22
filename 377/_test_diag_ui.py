"""诊断页布局专项测试（2026-11-22 第 2 版）。

为什么单独一个文件：
  用户反馈「诊断内容显示不全」——这是**布局 bug**，不是逻辑 bug。
  _test_diag.py 验证的是渲染逻辑（喂数据看 HTML 对不对），
  量不出"卡片被 flex 压扁、内容被 overflow:hidden 裁掉"这种问题。
  所以这里专门量布局尺寸。

被验证的 5 个点（都是用户明确提的）：
  1. 卡片不被 flex 压扁（flex-shrink:0）—— 上一版 bug 的根因
  2. 本机 13 行全部真实渲染（没有行被裁成 0 高）
  3. 宽屏两列 / 窄屏单列
  4. 复制按钮常驻可见（不再 hover 才出）
  5. 进度条 + 折叠

运行：python 377/_test_diag_ui.py
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

# 13 行本机数据（和真实采集的字段一致）
FAKE_ROWS = [
    {"k": "CPU", "v": "Intel(R) Xeon(R) CPU E5-2666 v3 @ 2.90GHz  10 核 / 20 线程", "lv": ""},
    {"k": "内存", "v": "16 GB  DDR3-1867MHz", "lv": ""},
    {"k": "Windows", "v": "Windows 10 专业版  (Build 19045)", "lv": ""},
    {"k": "系统版本号", "v": "10.0.19045", "lv": ""},
    {"k": "系统类型", "v": "64 位", "lv": ""},
    {"k": "设备名称", "v": "DESKTOP-62SVF04", "lv": ""},
    {"k": "屏幕分辨率", "v": "1920 × 1080  @100% 缩放", "lv": ""},
    {"k": "存储 C:", "v": "446.9 GB（剩余 211.5 GB）", "lv": ""},
    {"k": "存储 D:", "v": "29.3 GB（剩余 26.5 GB）", "lv": ""},
    {"k": ".NET 版本", "v": "4.0.30319.42000", "lv": ""},
    {"k": "进程数", "v": "335 个", "lv": ""},
    {"k": "日志目录", "v": "1.2 KB（2 个文件）", "lv": ""},
    {"k": "工具版本", "v": "2026-11-22 16:48", "lv": ""},
]

FAKE_CAR = [
    {"k": "车型", "v": "GAC-A18"},
    {"k": "SOC 版本", "v": "8295-A-1.2.3"},
    {"k": "MCU 版本", "v": "MCU-9.1"},
    {"k": "Android 版本", "v": "14"},
    {"k": "VIN 码", "v": "LVTEST1234567890"},
    {"k": "UUID", "v": "uuid-111"},
    {"k": "DID", "v": "did-222"},
    {"k": "OPENID", "v": "open-333"},
]

PROBE = """
<script>
window.__E=[];window.addEventListener('error',e=>window.__E.push(String(e.message)));
var FAKE_ROWS = __ROWS__;
var FAKE_CAR  = __CAR__;
setTimeout(function(){
  var R=[];
  function ok(n,c,e){R.push((c?'PASS':'FAIL')+' | '+n+(c?'':' -> '+(e===undefined?'':e)));}

  try{ switchTab('diag'); }catch(e){ R.push('FAIL | 切页失败 -> '+e); }

  /* 先喂数据（模拟 C# 回包），保证有 13 行真实布局可量 */
  try{
    diagOnLocal({ok:true, adb:'C:\\\\x\\\\adb.exe', adbsrc:'系统 PATH', rows:FAKE_ROWS});
    diagOnCar({online:true, got:true, root:true, rootprobed:true,
               serial:'ABC123', rows:FAKE_CAR, res:'1920x720'});
  }catch(e){ R.push('FAIL | 喂数据失败 -> '+e); }

  /* ---- 1. 卡片不被压扁（上一版 bug 的根因）----
     2026-11-22（第 19 批）：布局从 flex 改成 CSS Grid，
     "flex-shrink:0" 这个判据失效了。改成更本质的验证：
     卡片可见高度要能容纳内容（scrollHeight <= clientHeight + 容差），
     这才是"不被压扁"的真正含义。 */
  var card = document.getElementById('diag-card-pc');
  ok('卡片不被压扁（内容高度不超出可视高度）',
     card.scrollHeight <= card.clientHeight + 2,
     'scrollH=' + card.scrollHeight + ' clientH=' + card.clientHeight);

  /* ---- 2. 本机 13 行全部真实渲染 ---- */
  var rows = card.querySelectorAll('.diag-row');
  ok('本机行数为 13', rows.length === 13, rows.length);

  var zeroH = 0;
  for(var i=0;i<rows.length;i++) if(rows[i].offsetHeight < 12) zeroH++;
  ok('没有行被裁成 0 高', zeroH === 0, zeroH + ' 行为 0 高');

  // 内容没被裁剪：卡片内容高度 <= 卡片高度（允许 2px 误差）
  ok('本机卡片内容未被裁剪', card.scrollHeight <= card.clientHeight + 2,
     'scrollH=' + card.scrollHeight + ' clientH=' + card.clientHeight);

  var carCard = document.getElementById('diag-card-car');
  ok('车机卡片内容未被裁剪', carCard.scrollHeight <= carCard.clientHeight + 2,
     'scrollH=' + carCard.scrollHeight + ' clientH=' + carCard.clientHeight);

  /* ---- 3. 两列布局（宽屏）---- */
  ok('本机信息卡占整行（--wide）',
     card.classList.contains('diag-card--wide'));
  var rowBox = document.getElementById('diag-rows-pc');
  ok('本机行容器是两列网格',
     getComputedStyle(rowBox).display === 'grid', getComputedStyle(rowBox).display);

  var gridCols = getComputedStyle(rowBox).gridTemplateColumns;
  ok('宽屏下网格为 2 列', (gridCols.match(/px/g)||[]).length === 2, gridCols);

  // 2026-11-22（第 15 批）：adb + 连通性合并成一张「连接状态」卡，占整行。
  var adbCard = document.getElementById('diag-card-adb');
  ok('连接状态卡占整行（合并后）',
     adbCard.classList.contains('diag-card--wide'));
  var adbW = adbCard.getBoundingClientRect().width;
  var pcW = card.getBoundingClientRect().width;
  ok('连接状态卡与其它整行卡同宽',
     adbW > 0 && Math.abs(adbW - pcW) < 2,
     'adbW=' + Math.round(adbW) + ' pcW=' + Math.round(pcW));

  /* ---- 4. 复制按钮常驻可见 ---- */
  var cp = card.querySelector('.diag-cp');
  ok('复制按钮存在', !!cp);
  if(cp){
    var op = parseFloat(getComputedStyle(cp).opacity);
    ok('复制按钮常驻可见（opacity>0）', op > 0, 'opacity=' + op);
  }
  var allCp = card.querySelectorAll('.diag-cp');
  ok('每一行都有复制按钮', allCp.length === 13, allCp.length);

  /* ---- 5. 进度条 ---- */
  var meters = card.querySelectorAll('.diag-meter');
  ok('存储行渲染成进度条', meters.length === 2, meters.length);
  if(meters.length){
    var fill = meters[0].querySelector('.diag-meter-fill');
    var w = fill ? fill.style.width : '';
    ok('进度条有宽度值', /%$/.test(w), w);
    ok('进度条带余量文字',
       /剩余|剩/.test(meters[0].textContent), meters[0].textContent);
  }

  /* ---- 6. 折叠 ---- */
  var foldBefore = card.classList.contains('folded');
  ok('初始未折叠', foldBefore === false);
  diagToggleCard('pc');
  ok('折叠后加上 folded 类', card.classList.contains('folded'));
  ok('折叠后行容器隐藏',
     getComputedStyle(rowBox).display === 'none', getComputedStyle(rowBox).display);
  diagToggleCard('pc');
  ok('再次点击恢复展开', !card.classList.contains('folded'));

  /* ---- 7. 采样进度条 ---- */
  _diag.totalMemGB = 16;
  diagStartSample();
  /* 2026-11-22（第 19 批 B2）：资源占用改成"本机 + 车机 剩余量 + TOP5"，
     不再用进度条展示本工具自身的 CPU/内存。断言改成新口径。 */
  top5OnData({
    host:{ok:true, cores:8, freeCpu:64.8, freeMem:5.2,
          cpu:[{n:'chrome', v:12.5}], mem:[{n:'chrome', v:1024.0}]},
    car:{ok:false, err:'没有连接设备'}
  });
  var resBox = document.getElementById('diag-rows-res');
  ok('采样显示本机剩余 CPU', /剩余 CPU/.test(resBox.textContent),
     resBox.textContent.slice(0,80));
  ok('采样显示本机剩余内存', /剩余内存/.test(resBox.textContent));
  ok('车机未检测时显示 --（不隐藏）',
     resBox.textContent.indexOf('--') >= 0, resBox.textContent.slice(-80));
  diagStopSample();

  /* ---- 8. 页面整体可滚动（内容多于视口时不能没有滚动条）---- */
  var sc = document.getElementById('diag-scroll');
  ok('诊断滚动容器存在', !!sc);
  ok('滚动容器 overflow-y 为 auto',
     getComputedStyle(sc).overflowY === 'auto', getComputedStyle(sc).overflowY);
  ok('滚动容器无横向溢出',
     sc.scrollWidth <= sc.clientWidth + 2,
     'scrollW=' + sc.scrollWidth + ' clientW=' + sc.clientWidth);

  /* ---- 9. 窄屏回到单列 ---- */
  /* 直接改视口宽度不好模拟，改为检查 media query 规则存在 */
  var hasMedia = false, cssAll='';
  for(var si=0;si<document.styleSheets.length;si++){
    try{
      var rr=document.styleSheets[si].cssRules||[];
      for(var ri=0;ri<rr.length;ri++){
        if(rr[ri].conditionText && /max-width:\\s*1180px/.test(rr[ri].conditionText)) hasMedia=true;
      }
    }catch(e){}
  }
  ok('存在窄屏单列的媒体查询', hasMedia);

  ok('无运行时错误', window.__E.length===0, window.__E.join('; '));

  var pre=document.createElement('pre');
  pre.id='UI_RESULT';
  pre.textContent=JSON.stringify(R);
  document.body.appendChild(pre);
}, 1800);
</script>
"""


def main():
    src = open(UI, encoding="utf-8").read()
    probe = (PROBE
             .replace("__ROWS__", json.dumps(FAKE_ROWS, ensure_ascii=False))
             .replace("__CAR__", json.dumps(FAKE_CAR, ensure_ascii=False)))
    tmp = os.path.join(ROOT, "377", "_diag_ui.html")
    open(tmp, "w", encoding="utf-8", newline="").write(src.replace("</body>", probe + "</body>"))
    try:
        p = subprocess.run(
            [EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--no-first-run", "--no-default-browser-check",
             "--disable-background-networking", "--disable-sync",
             "--disable-extensions", "--disable-component-update",
             "--user-data-dir=" + os.path.join(tempfile.gettempdir(), "edgeprof_diagui"),
             "--window-size=1400,900", "--virtual-time-budget=14000", "--dump-dom",
             "file:///" + tmp.replace("\\", "/")],
            capture_output=True, timeout=180)
        dom = p.stdout.decode("utf-8", "replace")
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass

    m = re.search(r'<pre id="UI_RESULT">(.*?)</pre>', dom, re.S)
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
    print("  诊断页布局：通过 %d / %d" % (len(results) - fail, len(results)))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
