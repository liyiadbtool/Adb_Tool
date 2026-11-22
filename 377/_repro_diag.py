"""诊断页显示不全 / 复制错乱 —— 复现量测（第 21 批）

目的：不复现就不改。
用 Edge（与 WebView2 同 Chromium 内核）加载 ui.html，
注入**完整数据量**（本机 13 行 + 车机 12 行），然后量真实尺寸：

  1. 每张卡 clientHeight vs scrollHeight —— 判断内容是否被裁
  2. .diag-rows--cols 的实际高度与 grid 计算值
  3. 每行 .diag-row 的位置 + 复制按钮是否溢出卡片右边
  4. .diag-scroll 的 clientWidth / scrollWidth / 列数
  5. 数据加载前后宽度差（缩放问题的量化证据）

运行：python 377/_repro_diag.py
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
window.chrome = window.chrome || {};
window.chrome.webview = { postMessage: function(){} };

function r2(n){ return Math.round(n*100)/100; }
function box(el){ var b = el.getBoundingClientRect(); return {x:r2(b.x),y:r2(b.y),w:r2(b.width),h:r2(b.height)}; }

var OUT = {};

setTimeout(function(){
  try { run(); } catch(e){
    OUT.error = String(e);
  }
  var pre = document.createElement('pre');
  pre.id = 'REPRO';
  pre.textContent = JSON.stringify(OUT, null, 1);
  document.body.appendChild(pre);
}, 1500);

function run(){
  /* ---------- 准备：切到诊断页 + 注入完整数据 ---------- */
  switchTab('diag');

  // 本机：13 项（真实条数）
  // ★ 用截图里的**真实值**（超长 CPU 串 / 真实键名）复现，
  //   假数据太短，掩盖了布局问题。
  var pcRows = [
    {k:'CPU', v:'Intel(R) Xeon(R) CPU E5-2666 v3 @ 2.98GHz 10 核 / 20 线程 @2.98GHz'},
    {k:'内存', v:'16 GB DDR3-1867MHz'},
    {k:'存储', v:'C: 512 GB / 可用 120 GB'},
    {k:'系统', v:'Windows 11 专业版 23H2'},
    {k:'设备名', v:'LIYI-PC'},
    {k:'分辨率', v:'2560 x 1440（缩放 125%）'},
    {k:'系统类型', v:'64 位'},
    {k:'GPU', v:'Intel Iris Xe'},
    {k:'主板', v:'Lenovo 21HM'},
    {k:'BIOS', v:'N3WET28W'},
    {k:'网卡', v:'Intel Wi-Fi 6E AX211'},
    {k:'可用内存', v:'18.2 GB'},
    {k:'进程数', v:'312'}
  ];
  diagOnLocal({ok:true, rows:pcRows, adb:'1.0.41', adbsrc:'内置'});

  // 车机：12 项（真实条数）
  var carRows = [
    {k:'车型', v:'GAC-A18-T75'},
    {k:'SOC 版本', v:'V1.2.3.20261101'},
    {k:'MCU 版本', v:'MCU-8838-1.0.7'},
    {k:'Android 版本', v:'14'},
    {k:'VIN 码', v:'LGWEF6A55NH123456'},
    {k:'UUID', v:'a1b2c3d4-e5f6-7890-abcd-ef1234567890-very-long-uuid-value'},
    {k:'DID', v:'DID-20261101-0001'},
    {k:'OPENID', v:'openid-9f8e7d6c5b4a3210'},
    {k:'芯片', v:'qcm8838'},
    {k:'内存', v:'8.0 GB'},
    {k:'存储', v:'64.0 GB / 可用 22.9 GB'},
    {k:'屏幕分辨率', v:'1920x720'}
  ];
  diagOnCar({online:true, got:true, root:true, rootprobed:true, serial:'ABC123',
             rows:carRows, res:'1920x720'});

  // 资源占用：完整数据
  top5OnData({
    host:{ok:true, cores:12, freeCpu:72.4, freeMem:18.2,
          cpu:[{n:'msedgewebview2',v:6.8},{n:'Ld9BoxHeadless',v:5.1},
               {n:'WorkBuddy',v:4.2},{n:'Code',v:3.3},{n:'Memory Compression',v:1.6}],
          mem:[{n:'msedgewebview2',v:1024.0},{n:'Memory Compression',v:1008.4},
               {n:'Code',v:527.5},{n:'WorkBuddy',v:396.3},{n:'explorer',v:210.2}]},
    car:{ok:true, memTotal:8.0, memFree:2.5, freeCpu:98.0,
         cpu:[{n:'com.android.systemui',v:9.4},{n:'com.gxatek.map',v:3.1}],
         mem:[{n:'com.android.systemui',v:'180M'},{n:'com.gxatek.map',v:'96M'}]}
  });

  /* ---------- 量测 ---------- */
  var sc = document.getElementById('diag-scroll');
  var cs = getComputedStyle(sc);
  OUT.scroll = {
    clientWidth: sc.clientWidth,
    scrollWidth: sc.scrollWidth,
    clientHeight: sc.clientHeight,
    scrollHeight: sc.scrollHeight,
    overflowY: cs.overflowY,
    gridCols: cs.gridTemplateColumns,
    gap: cs.gap
  };

  OUT.cards = {};
  ['adb','pc','car','res'].forEach(function(id){
    var c = document.getElementById('diag-card-' + id);
    if (!c) return;
    OUT.cards[id] = {
      clientH: c.clientHeight,
      scrollH: c.scrollHeight,
      clipped: c.scrollHeight > c.clientHeight + 2,
      rect: box(c)
    };
  });

  // 每张卡的 rows 容器
  OUT.rowsBoxes = {};
  ['adb','pc','car','res'].forEach(function(id){
    var b = document.getElementById('diag-rows-' + id);
    if (!b) return;
    var bs = getComputedStyle(b);
    OUT.rowsBoxes[id] = {
      clientH: b.clientHeight,
      scrollH: b.scrollHeight,
      clipped: b.scrollHeight > b.clientHeight + 2,
      display: bs.display,
      gridCols: bs.gridTemplateColumns,
      rowCount: b.querySelectorAll('.diag-row').length
    };
  });

  // 复制按钮溢出检测：卡片右边界 vs 复制按钮右边界
  var pcCard = document.getElementById('diag-card-pc');
  var copys = pcCard ? pcCard.querySelectorAll('.diag-copy, .diag-row button') : [];
  var cardRight = pcCard ? pcCard.getBoundingClientRect().right : 0;
  var overflow = 0, maxOver = 0;
  var copyInfo = [];
  for (var i = 0; i < copys.length; i++){
    var r = copys[i].getBoundingClientRect();
    var over = r.right - cardRight;
    if (over > 1){ overflow++; if (over > maxOver) maxOver = over; }
    if (i < 3) copyInfo.push({t:(copys[i].textContent||'').trim(), x:r2(r.x), y:r2(r.y), w:r2(r.width)});
  }
  OUT.copyBtns = {
    total: copys.length,
    overflowCount: overflow,
    maxOverflowPx: r2(maxOver),
    cardRight: r2(cardRight),
    sample: copyInfo
  };

  // 资源占用里的进程名是否换行（行高 vs 单行行高）
  var resBox = document.getElementById('diag-rows-res');
  if (resBox){
    var ks = resBox.querySelectorAll('.diag-k');
    var wrapped = [];
    for (var j = 0; j < ks.length && j < 20; j++){
      var k = ks[j];
      var lh = parseFloat(getComputedStyle(k).lineHeight) || 0;
      if (lh > 0 && k.getBoundingClientRect().height > lh * 1.6){
        wrapped.push({txt:(k.textContent||'').trim().slice(0,26),
                      h:r2(k.getBoundingClientRect().height), lh:r2(lh)});
      }
    }
    OUT.resNameWrap = { wrappedCount: wrapped.length, samples: wrapped.slice(0,4) };
  }

  // 列数
  OUT.columnCount = (cs.gridTemplateColumns || '').trim().split(/\s+/).length;

  /* ---------- 复制按钮实测（竖排 / 溢出 的量化证据）---------- */
  (function(){
    var card = document.getElementById('diag-card-pc');
    if (!card) return;
    var cps = card.querySelectorAll('.diag-cp');
    var cardRect = card.getBoundingClientRect();
    var sample = [];
    var narrow = 0, overRight = 0, tall = 0;
    var lh = 16;
    var probe = cps[0];
    if (probe) lh = parseFloat(getComputedStyle(probe).lineHeight) || 16;
    for (var i = 0; i < cps.length; i++){
      var r = cps[i].getBoundingClientRect();
      var st = getComputedStyle(cps[i]);
      if (r.width < 24) narrow++;                 // 两个汉字都放不下 → 竖排
      if (r.right > cardRect.right + 1) overRight++;  // 溢出卡片右边
      if (r.height > 34) tall++;                  // 固定 20px 高，>34 才算竖排
      if (i < 3) sample.push({w:r2(r.width), h:r2(r.height), x:r2(r.x),
                              ws:st.whiteSpace, flex:st.flex, minW:st.minWidth});
    }
    OUT.copyProbe = {
      count: cps.length,
      tooNarrow: narrow,
      overflowRight: overRight,
      tooTall: tall,
      cardW: r2(cardRect.width),
      sample: sample
    };
  })();

  /* ---------- 关键：模拟不同 ZoomFactor（WebView2 的缩放等价于 CSS zoom）----------
     用户的字号设置不是「中」时，整页按 0.9 / 1.15 / 1.25 缩放。
     缩放后 CSS 的固定 px 会被等比放大，可能撑破固定宽度 —— 这是"显示不全"的
     高度可疑点，必须在这里量出来。 */
  OUT.zoomMatrix = {};
  [1.0, 1.15, 1.25, 1.35].forEach(function(z){
    document.documentElement.style.zoom = String(z);
    // 强制 reflow
    void document.documentElement.offsetHeight;
    void sc.offsetWidth;

    var c = document.getElementById('diag-card-pc');
    var car = document.getElementById('diag-card-car');
    var rp = document.getElementById('diag-rows-pc');
    var pcCopy = c ? c.querySelectorAll('.diag-row button') : [];
    var cardRight = c ? c.getBoundingClientRect().right : 0;
    var over = 0;
    for (var i = 0; i < pcCopy.length; i++){
      if (pcCopy[i].getBoundingClientRect().right - cardRight > 1) over++;
    }
    OUT.zoomMatrix['x' + z] = {
      scrollW: sc.scrollWidth,
      clientW: sc.clientWidth,
      hScroll: sc.scrollWidth > sc.clientWidth + 1,
      pcClipped: rp ? (rp.scrollHeight > rp.clientHeight + 2) : null,
      pcClientH: rp ? rp.clientHeight : null,
      pcScrollH: rp ? rp.scrollHeight : null,
      pcCardH: c ? c.clientHeight : null,
      pcCardScrollH: c ? c.scrollHeight : null,
      copyOverflow: over,
      cols: (getComputedStyle(sc).gridTemplateColumns || '').trim().split(/\s+/).length
    };
  });
  document.documentElement.style.zoom = '';

  // 窄窗模拟（用户窗口可能只有 1100~1200 宽）：改 scroll 容器宽度再量
  var origW = sc.style.width;
  ['1100px','1000px','920px'].forEach(function(w){
    sc.style.width = w;
    void sc.offsetWidth;
    var c = document.getElementById('diag-card-pc');
    var rp = document.getElementById('diag-rows-pc');
    var cardRight = c ? c.getBoundingClientRect().right : 0;
    var pcCopy = c ? c.querySelectorAll('.diag-row button') : [];
    var over = 0;
    for (var i = 0; i < pcCopy.length; i++){
      if (pcCopy[i].getBoundingClientRect().right - cardRight > 1) over++;
    }
    OUT.zoomMatrix['w' + w] = {
      scrollW: sc.scrollWidth,
      clientW: sc.clientWidth,
      hScroll: sc.scrollWidth > sc.clientWidth + 1,
      pcClipped: rp ? (rp.scrollHeight > rp.clientHeight + 2) : null,
      pcClientH: rp ? rp.clientHeight : null,
      pcScrollH: rp ? rp.scrollHeight : null,
      copyOverflow: over,
      cols: (getComputedStyle(sc).gridTemplateColumns || '').trim().split(/\s+/).length
    };
  });
  sc.style.width = origW;
}
</script>
"""


def main():
    src = open(UI, encoding="utf-8").read()
    tmp = os.path.join(ROOT, "377", "_repro.html")
    open(tmp, "w", encoding="utf-8", newline="").write(src.replace("</body>", PROBE + "</body>"))
    try:
        p = subprocess.run(
            [EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--no-first-run", "--no-default-browser-check",
             "--disable-background-networking", "--disable-sync",
             "--disable-extensions", "--disable-component-update",
             "--user-data-dir=" + os.path.join(tempfile.gettempdir(), "edgeprof_repro"),
             "--window-size=1400,900", "--virtual-time-budget=14000", "--dump-dom",
             "file:///" + tmp.replace("\\", "/")],
            capture_output=True, timeout=200)
        dom = p.stdout.decode("utf-8", "replace")
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass

    m = re.search(r'<pre id="REPRO">(.*?)</pre>', dom, re.S)
    if not m:
        print("!! 复现脚本没返回结果")
        for mm in re.finditer(r"(Uncaught[^<\n]{0,200})", dom):
            print("   ", mm.group(1))
        return 2

    data = json.loads(m.group(1))
    print(json.dumps(data, ensure_ascii=False, indent=1))

    # 结论摘要
    print("\n===== 结论 =====")
    if data.get("error"):
        print("  脚本异常:", data["error"])
        return 2

    sc = data.get("scroll", {})
    print(f"  diag-scroll: clientW={sc.get('clientWidth')} scrollW={sc.get('scrollWidth')} "
          f"列数={data.get('columnCount')} overflowY={sc.get('overflowY')}")
    if sc.get("scrollWidth", 0) > sc.get("clientWidth", 0) + 1:
        print("  ⚠ 横向溢出：内容比容器宽（复制按钮可能超出）")

    for k, v in (data.get("cards") or {}).items():
        flag = " ⚠ 被裁" if v.get("clipped") else ""
        print(f"  卡片 {k:4s}: clientH={v['clientH']:4d} scrollH={v['scrollH']:4d}{flag}")

    for k, v in (data.get("rowsBoxes") or {}).items():
        flag = " ⚠ 被裁" if v.get("clipped") else ""
        print(f"  rows {k:4s}: clientH={v['clientH']:4d} scrollH={v['scrollH']:4d} "
              f"行数={v['rowCount']:2d} display={v['display']}{flag}")

    cb = data.get("copyBtns", {})
    print(f"  复制按钮: 共 {cb.get('total')} 个，溢出 {cb.get('overflowCount')} 个"
          f"（最大超出 {cb.get('maxOverflowPx')}px）")

    print("\n  ===== 缩放 / 窄窗矩阵 =====")
    for k, v in (data.get("zoomMatrix") or {}).items():
        flags = []
        if v.get("hScroll"): flags.append("横向溢出")
        if v.get("pcClipped"): flags.append("本机行被裁")
        if v.get("copyOverflow"): flags.append(f"复制溢出{v['copyOverflow']}个")
        st = " ⚠ " + ",".join(flags) if flags else " ok"
        print(f"    {k:8s} 列={v.get('cols')} clientW={v.get('clientW')} "
              f"scrollW={v.get('scrollW')} pc: {v.get('pcClientH')}/{v.get('pcScrollH')}{st}")

    cp = data.get("copyProbe", {})
    if cp:
        print(f"  复制按钮实测: 共 {cp.get('count')} 个, 过窄(竖排) {cp.get('tooNarrow')} 个, "
              f"溢出右边 {cp.get('overflowRight')} 个, 异常高 {cp.get('tooTall')} 个, 卡宽 {cp.get('cardW')}")
        for smp in (cp.get("sample") or []):
            print(f"      w={smp['w']} h={smp['h']} ws={smp['ws']} flex={smp['flex']} minW={smp['minW']}")

    rw = data.get("resNameWrap", {})
    print(f"  资源占用进程名换行: {rw.get('wrappedCount')} 处")
    for s in (rw.get("samples") or []):
        print(f"      {s['txt']}  h={s['h']} lh={s['lh']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
