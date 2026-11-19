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
  /* ===== T16（2026-11-18）：浮层管理器 Overlay =====
     动机：全仓 9 个浮层容器（accent-pop / apk-mgr / apk-panel / custom-mgr /
     custom-panel / netsim-panel / vr-panel / wadb-pop + 动态 a14-selpop）、
     z-index 8 档（220~9999），"外点关闭 / Esc / 滚动跟随"各写一套。
     T14b 还要加右键菜单 —— 再写一套就是第 10 个。
     这里只抽**生命周期 + 定位 + 关闭**三件事，浮层内容仍由各自负责。
     层级收敛成三档，别再随手写 9998/9999。
     pop 沿用 1400（.a14-selpop 的现有值）—— 不改它，避免和弹窗/提示的层序打架。 */
  var LEVEL = { pop: 1400, modal: 9000, toast: 9990 };

  var _cur = null;         // { el, anchor, onClose }

  /* 定位：优先贴锚点下方，放不下翻到上方；左右夹在窗口内；
     锚点被滚出可视区就关掉（不是"一滚就关"，见 A15 的教训）。 */
  function placeOverlay(el, anchor){
    if (!el || !anchor || !anchor.getBoundingClientRect) return;
    var r = anchor.getBoundingClientRect();
    if (r.bottom < 0 || r.top > window.innerHeight){ Overlay.close(); return; }
    var w = el.offsetWidth, h = el.offsetHeight;
    var top = r.bottom + 4;
    if (top + h > window.innerHeight - 8 && r.top - h - 4 > 8) top = r.top - h - 4;
    var left = Math.min(Math.max(r.left, 8), Math.max(8, window.innerWidth - w - 8));
    el.style.top = Math.max(8, top) + 'px';
    el.style.left = left + 'px';
  }

  var Overlay = window.Overlay = {
    LEVEL: LEVEL,
    current: function(){ return _cur ? _cur.el : null; },
    contains: function(node){ return !!(_cur && _cur.el && _cur.el.contains(node)); },
    /* 一次只留一个浮层：开新的先关旧的 */
    open: function(o){
      Overlay.close();
      _cur = { el: o.el, anchor: o.anchor || null, onClose: o.onClose || null };
      if (o.el.parentNode !== document.body) document.body.appendChild(o.el);
      o.el.style.zIndex = String(o.z || LEVEL.pop);
      if (_cur.anchor) placeOverlay(o.el, _cur.anchor);
    },
    close: function(){
      var c = _cur;
      if (!c) return;
      _cur = null;
      try { if (c.el && c.el.parentNode) c.el.parentNode.removeChild(c.el); } catch (e) {}
      try { if (c.onClose) c.onClose(); } catch (e) {}
    },
    reposition: function(){ if (_cur && _cur.anchor) placeOverlay(_cur.el, _cur.anchor); }
  };

  var pop = null;
  var popAnchor = null;

  function closePop(){
    Overlay.close();          // 真正摘节点/清状态在 Overlay.close 的 onClose 里
    pop = null;
    popAnchor = null;
  }

  function repositionPop(){
    if (pop && popAnchor) placeOverlay(pop, popAnchor);
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

    // T16：挂载 / 层级 / 定位统一交给 Overlay。
    // minWidth 仍在这里算 —— 它跟"这一层里最长的那条选项"有关，属于内容侧。
    var r = sel.getBoundingClientRect();
    var w = Math.max(r.width, 180);
    if (w + 16 > window.innerWidth) w = window.innerWidth - 16;
    pop.style.minWidth = w + 'px';

    Overlay.open({
      el: pop, anchor: sel, z: LEVEL.pop,
      onClose: function(){ pop = null; popAnchor = null; }
    });

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
       只有点到浮层外面才关。
       T16：判断改为 Overlay.contains —— 以后右键菜单等浮层也自动被保护。 */
    if (Overlay.contains(ev.target)) return;
    Overlay.close();
  }, true);

  document.addEventListener('keydown', function(ev){
    if (ev.key === 'Escape') closePop();
  }, true);
  window.addEventListener('resize', function(){ Overlay.reposition(); });
  /* A15：原实现是 scroll → closePop()，于是设置面板往下滑一点、
     或浮层自身因为项多而要滚，都会把下拉直接关掉（用户以为控件坏了）。
     现在：浮层内部的滚动忽略，外部滚动改为跟随重定位；
     只有锚点被滚出可视区时才关（判断在 placeOverlay 里）。 */
  document.addEventListener('scroll', function(ev){
    var el = Overlay.current();
    if (!el) return;
    if (el.contains(ev.target)) return;
    Overlay.reposition();
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
