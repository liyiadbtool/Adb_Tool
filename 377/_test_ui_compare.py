"""UI 比对（UI 对比）实测 —— 真实导入图片、真实跑算法。

背景（2026-11-21 第 7 批需求）：用户要求「结合网上的 UI 比对工具看下交互和功能
有没有缺少的」，补齐后要求「导入图片进入 UI 比对的功能测试」。

对标 pixelmatch / resemble.js 后补的三项关键能力：
  ① 忽略抗锯齿（ignoreAA）—— 单像素级的边缘过渡差异不算缺陷，否则误报率极高
  ② 只显示差异（onlyDiff）—— 隐藏底图，只留差异高亮，看缺陷位置最快
  ③ 只比结构（structOnly）—— 忽略颜色，只比布局/形状（换主题后验布局是否走样）
另补：尺寸不一致时明确告知（原来静默取 min 裁剪，「假通过」风险）。

测试用**程序生成的 PNG**（差异完全已知），走真实比对链路：
  T1 两张完全相同的图       → 差异必须 0%
  T2 内容位移               → 差异 > 1%
  T3 关闭「忽略抗锯齿」     → 差异仍 > 1%，且 >= 开启时的值（忽略只减不增）
  T4 只比结构 + 纯换色      → 差异必须 0%
  T5 不勾结构 + 纯换色      → 差异 > 0.5%
  T6 只显示差异模式         → 能出结果图
  T7 三个新控件 + 尺寸提示都在，且尺寸一致时提示「一致」

运行：python 377/_test_ui_compare.py
"""
import base64
import json
import os
import re
import struct
import subprocess
import tempfile
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, 'adb_log_gui', 'webview2', 'ui.html')
IMG = os.path.join(tempfile.gettempdir(), 'adb_uitest_imgs')


def _find_edge():
    cands = [
        r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
        r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    ]
    for c in cands:
        if os.path.exists(c):
            return c
    return 'msedge.exe'


EDGE = _find_edge()


def _make_png(path, w, h, pixel_fn):
    raw = b''
    for y in range(h):
        raw += b'\x00'
        for x in range(w):
            raw += bytes(pixel_fn(x, y))

    def chunk(t, d):
        c = t + d
        return struct.pack('>I', len(d)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)

    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(raw, 9))
    png += chunk(b'IEND', b'')
    open(path, 'wb').write(png)


def build_images():
    """生成 4 张差异已知的测试图（400x300）。"""
    os.makedirs(IMG, exist_ok=True)
    W, H = 400, 300

    def design(x, y):
        if 50 <= x < 150 and 50 <= y < 150:
            return (40, 110, 220)          # 蓝矩形
        if (x - 300) ** 2 + (y - 200) ** 2 <= 50 ** 2:
            return (40, 180, 90)           # 绿圆
        return (245, 246, 250)             # 白底

    def shifted(x, y):
        # 蓝矩形右移 12px、绿圆下移 8px
        if 62 <= x < 162 and 50 <= y < 150:
            return (40, 110, 220)
        if (x - 300) ** 2 + (y - 208) ** 2 <= 50 ** 2:
            return (40, 180, 90)
        return (245, 246, 250)

    def recolored(x, y):
        # 结构完全一样，只把蓝色换成紫色
        if 50 <= x < 150 and 50 <= y < 150:
            return (150, 40, 220)
        if (x - 300) ** 2 + (y - 200) ** 2 <= 50 ** 2:
            return (40, 180, 90)
        return (245, 246, 250)

    _make_png(os.path.join(IMG, 'design.png'), W, H, design)
    _make_png(os.path.join(IMG, 'real_same.png'), W, H, design)
    _make_png(os.path.join(IMG, 'real_shift.png'), W, H, shifted)
    _make_png(os.path.join(IMG, 'real_color.png'), W, H, recolored)


def dataurl(p):
    return 'data:image/png;base64,' + base64.b64encode(open(p, 'rb').read()).decode()


PROBE = r"""
<script>
(function(){
  var R=[];
  function ok(n,c,e){R.push((c?'PASS':'FAIL')+' | '+n+(c?'':' -> '+(e===undefined?'':e)));}
  var D = __IMGDATA__;
  function load(url){
    return new Promise(function(res,rej){
      var im=new Image(); im.onload=function(){res(im);}; im.onerror=rej; im.src=url;
    });
  }
  function setImgs(aUrl,bUrl,opts){
    return Promise.all([load(aUrl),load(bUrl)]).then(function(){
      var di=document.getElementById('ui-design-img'), ri=document.getElementById('ui-real-img');
      di.src=aUrl; ri.src=bUrl;
      _uiImg.design=aUrl; _uiImg.real=bUrl;
      document.getElementById('ui-ignore-aa').checked = !!opts.aa;
      document.getElementById('ui-only-diff').checked = !!opts.only;
      document.getElementById('ui-struct').checked = !!opts.struct;
      document.getElementById('ui-thr').value = opts.thr || 30;
      return new Promise(function(r){ setTimeout(r,120); });
    });
  }
  function resultText(){ return document.getElementById('ui-result-path').value; }
  function resultPng(){ return document.getElementById('ui-result-img').src; }
  function rateOf(t){ var m=t.match(/差异\s*([0-9.]+)%/); return m?parseFloat(m[1]):-1; }

  function step(list, i){
    if (i >= list.length) { document.title='@@R@@'+JSON.stringify(R)+'@@E@@'; return; }
    var c = list[i];
    setImgs(c.a, c.b, c.o).then(function(){
      uiCompareRun();
      setTimeout(function(){
        c.f(rateOf(resultText()), resultText());
        step(list, i+1);
      }, 420);
    });
  }

  var R2 = -1, R3 = -1, RUN = [
    {a:D.same,   b:D.same,   o:{aa:true},  f:function(r,t){
        ok('T1 完全相同的图 → 差异 0%', r===0, t);
        ok('T1 生成了结果图', /^data:image\/png/.test(resultPng()));
    }},
    {a:D.design, b:D.shift,  o:{aa:true},  f:function(r,t){
        R2 = r;
        ok('T2 位移图 → 差异 > 1%', r>1, t);
    }},
    {a:D.design, b:D.shift,  o:{aa:false}, f:function(r,t){
        R3 = r;
        ok('T3 关闭忽略AA后差异仍 > 1%', r>1, t);
        ok('T3 忽略AA 的差异率 <= 不忽略（只减不增）', R2<=R3+0.01, R2+' vs '+R3);
    }},
    {a:D.design, b:D.color,  o:{aa:true, struct:true},  f:function(r,t){
        ok('T4 只比结构：纯换色 → 差异 0%', r===0, t);
    }},
    {a:D.design, b:D.color,  o:{aa:true, struct:false}, f:function(r,t){
        ok('T5 不勾结构：纯换色 → 差异 > 0.5%', r>0.5, t);
    }},
    {a:D.design, b:D.shift,  o:{aa:true, only:true},    f:function(r,t){
        ok('T6 只显示差异：生成结果图', /^data:image\/png/.test(resultPng()));
        ok('T7 忽略抗锯齿复选框存在', !!document.getElementById('ui-ignore-aa'));
        ok('T7 只显示差异复选框存在', !!document.getElementById('ui-only-diff'));
        ok('T7 只比结构复选框存在', !!document.getElementById('ui-struct'));
        var hint = document.getElementById('ui-dim-hint');
        ok('T7 尺寸提示存在', !!hint);
        ok('T7 尺寸一致时提示「一致」', hint && /一致/.test(hint.textContent),
           hint ? hint.textContent : 'none');
    }}
  ];

  setTimeout(function(){ step(RUN, 0); }, 1600);
})();
</script>
"""


def main():
    build_images()
    src = open(UI, encoding='utf-8').read()

    probe = PROBE.replace('__IMGDATA__', json.dumps({
        'same':   dataurl(os.path.join(IMG, 'real_same.png')),
        'design': dataurl(os.path.join(IMG, 'design.png')),
        'shift':  dataurl(os.path.join(IMG, 'real_shift.png')),
        'color':  dataurl(os.path.join(IMG, 'real_color.png')),
    }))

    tmp = os.path.join(ROOT, '377', '_uitest.html')
    open(tmp, 'w', encoding='utf-8', newline='').write(src.replace('</body>', probe + '</body>'))

    # 2026-11-22：补上启动优化参数（其它套件已统一），减少 Edge 冷启动抖动
    args = [EDGE, '--headless=new', '--disable-gpu', '--no-sandbox',
            '--no-first-run', '--no-default-browser-check',
            '--disable-background-networking', '--disable-sync',
            '--disable-extensions', '--disable-component-update',
            '--user-data-dir=' + os.path.join(tempfile.gettempdir(), 'edgeprof_uitest'),
            '--virtual-time-budget=20000', '--dump-dom',
            'file:///' + tmp.replace('\\', '/')]
    try:
        p = subprocess.run(args, capture_output=True, timeout=180)
        dom = p.stdout.decode('utf-8', 'replace')
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass

    m = re.search(r'@@R@@(.*?)@@E@@', dom, re.S)
    if not m:
        print('!! 探针未返回')
        for mm in re.finditer(r'(Uncaught[^<\n]{0,160})', dom):
            print('   ', mm.group(1))
        return 2

    results = json.loads(m.group(1))
    for line in results:
        print('  ' + line)
    fail = sum(1 for r in results if r.startswith('FAIL'))
    print('')
    print('  UI 比对实测：通过 %d / %d' % (len(results) - fail, len(results)))
    return 0 if fail == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
