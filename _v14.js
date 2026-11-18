/* === V14 JS START === */
/* ==========================================================================
   A14 · 下拉浮层 / 字体大小 / 启动图标颜色 / 浅色主题补充
   只接线，不改既有函数语义（和 V13 一样的做法：能包就不复制）。
   ========================================================================== */
(function(){
  'use strict';

  /* ---------------- §1 自绘下拉浮层（需求 5 / 7） ----------------
     为什么不用 CSS 改原生 select 的弹层：
       黑色模式下 <select> 展开是 Chromium 的原生弹层，属浏览器进程绘制，
       `option{background}` / `color-scheme` 在 WebView2 里不保证生效
       （实测就是用户截图里的白底白字）。
     做法：在捕获阶段拦下 select 的 mousedown，自己画一层 div 列表。
       · 列表用主题令牌 → 三套主题都对
       · 选中后写回原生 select 再派发 change → 既有的 onchange 全部照常工作
       · 只拦 mousedown，不动 DOM 结构，动态生成的 select（投屏 6 格）也覆盖
  */
  var pop = null;
  var popAnchor = null;

  function closePop(){
    if (pop && pop.parentNode) pop.parentNode.removeChild(pop);
    pop = null;
    popAnchor = null;
  }

  /* 浮层跟着锚点走：外面滚动时重新定位，而不是直接关掉。
     （A15 修）原来是"一滚就关"，设置面板往下滑一下字体下拉就没了，
     用户以为控件坏掉。真正该关的只有"锚点被滚出可视区"。 */
  function repositionPop(){
    if (!pop || !popAnchor || !popAnchor.getBoundingClientRect) return;
    var r = popAnchor.getBoundingClientRect();
    if (r.bottom < 0 || r.top > window.innerHeight){
      closePop();
      return;
    }
    var w = pop.offsetWidth, h = pop.offsetHeight;
    var top = r.bottom + 4;
    if (top + h > window.innerHeight - 8 && r.top - h - 4 > 8) top = r.top - h - 4;
    var left = Math.min(Math.max(r.left, 8), Math.max(8, window.innerWidth - w - 8));
    pop.style.top = Math.max(8, top) + 'px';
    pop.style.left = left + 'px';
  }

  function openPop(sel){
    closePop();
    var opts = sel.options;
    if (!opts || !opts.length) return;

    pop = document.createElement('div');
    pop.className = 'a14-selpop';
    popAnchor = sel;

    var lastGrp = null;
    for (var i = 0; i < opts.length; i++){
      var o = opts[i];
      // A15：分组标题（字体列表按「内置 / 系统自带 / 需安装 / 等宽」分堆）
      var g = o.getAttribute ? o.getAttribute('data-grp') : null;
      if (g && g !== lastGrp){
        lastGrp = g;
        var gh = document.createElement('div');
        gh.className = 'grp';
        gh.textContent = g;
        pop.appendChild(gh);
      }
      var off = o.getAttribute && o.getAttribute('data-off') === '1';
      var it = document.createElement('div');
      it.className = 'it' + (o.selected ? ' on' : '') + (off ? ' off' : '');
      it.textContent = o.text;
      it.setAttribute('data-v', o.value);
      if (off){
        it.setAttribute('data-off', '1');
        it.title = '未安装（选中后由系统回退字体渲染）';
      }
      pop.appendChild(it);
    }

    document.body.appendChild(pop);

    var r = sel.getBoundingClientRect();
    var w = Math.max(r.width, 180);
    if (w + 16 > window.innerWidth) w = window.innerWidth - 16;
    pop.style.minWidth = w + 'px';

    var h = pop.offsetHeight;
    var top = r.bottom + 4;
    // 下方放不下就翻到上面（文本页那排工具条贴着顶，弹层往下压最自然，
    // 但输出区上面的搜索框就得翻上来）
    if (top + h > window.innerHeight - 8 && r.top - h - 4 > 8) top = r.top - h - 4;
    var left = Math.min(Math.max(r.left, 8), Math.max(8, window.innerWidth - w - 8));
    pop.style.top = top + 'px';
    pop.style.left = left + 'px';

    pop.addEventListener('click', function(ev){
      var t = ev.target;
      while (t && t !== pop && !t.getAttribute) t = t.parentNode;
      if (!t || t === pop) return;
      var v = t.getAttribute('data-v');
      if (v === null) return;
      ev.preventDefault();
      ev.stopPropagation();
      closePop();
      sel.value = v;      // 派发 change：既有的 onchange（setFont / txSetEnc / txSetEol / 投屏屏号）照常跑
      try { sel.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
      try { sel.focus(); } catch (e) {}
    });

    // 键盘：上下选、回车确认、Esc 关（原生下拉的键盘习惯别丢）
    pop.tabIndex = -1;
    try { pop.focus(); } catch (e) {}
    pop.addEventListener('keydown', function(ev){
      var items = pop.querySelectorAll('.it');
      if (!items.length) return;
      var idx = -1;
      for (var k = 0; k < items.length; k++) if (items[k].classList.contains('on')) idx = k;
      if (ev.key === 'ArrowDown'){ idx = Math.min(idx + 1, items.length - 1); }
      else if (ev.key === 'ArrowUp'){ idx = Math.max(idx - 1, 0); }
      else if (ev.key === 'Enter'){
        if (idx >= 0){
          sel.value = items[idx].getAttribute('data-v');
          closePop();
          try { sel.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
        }
        ev.preventDefault();
        return;
      }
      else if (ev.key === 'Escape'){ closePop(); ev.preventDefault(); return; }
      else return;
      ev.preventDefault();
      for (var m = 0; m < items.length; m++) items[m].classList.toggle('on', m === idx);
    });
  }

  document.addEventListener('mousedown', function(ev){
    var t = ev.target;
    while (t && t !== document.body && t.tagName !== 'SELECT') t = t.parentNode;
    if (t && t.tagName === 'SELECT'){
      if (t.disabled) return;
      ev.preventDefault();     // 阻止原生弹层
      ev.stopPropagation();
      openPop(t);
      return;
    }
    /* T2（2026-11-18）：原来这里无条件 closePop()，点浮层**条目**也会命中 ——
       浮层挂在 body 下，向上找不到 SELECT，于是 mousedown 当场把节点移除，
       等 click 派发时节点已脱离文档，pop 上的 click 监听收不到 →
       选中无效、change 不派发（字体切换/预置环境值/屏号/编码全都"点了没反应"）。
       现在：点到浮层内部就不关（让 click 正常走 choose 逻辑），
       只有点到浮层外面才关。 */
    if (pop && pop.contains(ev.target)) return;
    closePop();
  }, true);

  document.addEventListener('keydown', function(ev){
    if (ev.key === 'Escape') closePop();
  }, true);
  window.addEventListener('resize', repositionPop);
  /* A15：原实现是 scroll → closePop()，于是设置面板往下滑一点、
     或浮层自身因为项多而要滚，都会把下拉直接关掉（用户以为控件坏了）。
     现在：浮层内部的滚动忽略，外部滚动改为跟随重定位；
     只有锚点被滚出可视区时才关。 */
  document.addEventListener('scroll', function(ev){
    if (!pop) return;
    if (pop.contains(ev.target)) return;
    repositionPop();
  }, true);

  /* ---------------- §2 字体大小（需求 8） ----------------
     三种：小 90% / 中 100% / 大 115%。
     实现方式是 WebView2 的 ZoomFactor（整页等比缩放并重新排版）——
     不用逐条改 CSS 字号：那样要么漏组件，要么被迫把所有 px 换成 em。
     好处：窗口热区、tooltip 定位这类靠 getBoundingClientRect 的计算
     仍然自洽（devicePixelRatio 在 Chromium 里已含页面缩放）。 */
  var SIZES = {
    s: { z: 0.90, name: '小' },
    m: { z: 1.00, name: '中' },
    l: { z: 1.15, name: '大' }
  };

  function curSize(){
    var id = (typeof _prefs === 'object' && _prefs && _prefs.size) ? _prefs.size : 'm';
    return SIZES[id] ? id : 'm';
  }

  function syncSizeSeg(){
    var box = document.getElementById('set-fsize');
    if (!box) return;
    var cur = curSize();
    var bs = box.querySelectorAll('button');
    for (var i = 0; i < bs.length; i++)
      bs[i].classList.toggle('on', bs[i].getAttribute('data-fsize') === cur);
  }

  function buildSizeSeg(){
    var box = document.getElementById('set-fsize');
    if (!box || box.children.length) return;
    var order = ['s', 'm', 'l'];
    var html = '';
    for (var i = 0; i < order.length; i++){
      var k = order[i];
      html += '<button type="button" data-fsize="' + k + '" onclick="setSize(\'' + k + '\')">'
            + SIZES[k].name + '</button>';
    }
    box.innerHTML = html;
    syncSizeSeg();
  }

  window.applySize = function(id, silent){
    if (!SIZES[id]) id = 'm';
    if (typeof _prefs === 'object' && _prefs) _prefs.size = id;
    document.documentElement.setAttribute('data-fsize', id);
    try { post('uizoom', String(SIZES[id].z)); } catch (e) {}
    syncSizeSeg();
    if (!silent){
      try { prefsSave(); } catch (e) {}
      try { toast('字体大小：' + SIZES[id].name, 'ok'); } catch (e) {}
    }
  };

  window.setSize = function(id){ window.applySize(id, false); };

  // 设置面板打开时补建分段控件（面板是懒渲染，第一次打开才需要内容）
  if (typeof window.openSettings === 'function'){
    var origOpen = window.openSettings;
    window.openSettings = function(){
      var r = origOpen.apply(this, arguments);
      buildSizeSeg();
      syncSizeSeg();
      return r;
    };
  }

  /* ---------------- §3 偏好：把 size 一起存进 prefs ----------------
     prefs 是前端自己序列化的不透明 blob（C# 只存取不解析），
     所以这里只需要在 _prefs 上多挂一个 size 字段，prefsSave 自动带上；
     读的时候 prefsApply 只认 font/custom，size 得自己再解析一遍。 */
  if (typeof window.prefsApply === 'function'){
    var origApply = window.prefsApply;
    window.prefsApply = function(b64){
      var saved = null;
      try { saved = JSON.parse(b64dec(b64 || '') || '{}'); } catch (e) { saved = null; }
      var r = origApply.apply(this, arguments);
      if (saved && SIZES[saved.size]) _prefs.size = saved.size;
      window.applySize(curSize(), true);
      return r;
    };
  }

  /* ---------------- §4 字体预览文案：去掉中文（需求 6） ----------------
     applyFont 里会把预览文案重写成带中文的样例，这里包一层统一改成纯 ASCII。 */
  var A14_PREVIEW = 'Adb_Tool 12345 ABCdef';
  if (typeof window.applyFont === 'function'){
    var origFont = window.applyFont;
    window.applyFont = function(id, silent){
      var r = origFont.apply(this, arguments);
      var pv = document.getElementById('set-font-preview');
      if (pv) pv.textContent = A14_PREVIEW;
      return r;
    };
  }

  /* ---------------- §5 主题 → color-scheme（需求 5/7 的兜底） ----------------
     CSS 里 :root[data-theme] 已经声明了 color-scheme，这里再用内联样式钉一次：
     个别 WebView2 运行时对 :root 上的 color-scheme 传递不彻底，表单控件会退回浅色。 */
  function syncScheme(){
    try {
      var t = document.documentElement.getAttribute('data-theme') || 'dark';
      document.documentElement.style.colorScheme = (t === 'dark') ? 'dark' : 'light';
    } catch (e) {}
  }
  if (typeof window.applyTheme === 'function'){
    var origTheme = window.applyTheme;
    window.applyTheme = function(name){
      var r = origTheme.apply(this, arguments);
      syncScheme();
      return r;
    };
  }

  /* ---------------- 启动：把上面这些接到当前状态上 ---------------- */
  function boot(){
    syncSizeSeg();
    syncScheme();
    var pv = document.getElementById('set-font-preview');
    if (pv) pv.textContent = A14_PREVIEW;
    // 首帧就把缩放打上去：prefs 还没到时按「中」，到了 prefsApply 会再校一次
    try { post('uizoom', String(SIZES[curSize()].z)); } catch (e) {}
  }
  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', boot);
  else
    boot();

  // 页面 ready 后 C# 会推 prefs，prefsApply 里已经带了 applySize
})();
/* === V14 JS END === */
