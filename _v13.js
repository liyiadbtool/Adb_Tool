/* === V13 JS START === */
/* ==========================================================================
   A13 · 标题栏四圆点 / 终端多行顺序执行 / 输出区点空白切换
   --------------------------------------------------------------------------
   这一层只做「接线」，不改任何既有函数的语义：
     · 状态圆点：颜色由 CSS 按类名/属性决定，这里只负责即时 tooltip；
     · 终端多行：包装 run / endRun，逐行顺序下发，失败也继续（靠 end 驱动）；
     · 输出区：展开态补一个"点表头空白收起"的热区。
   所以所有原有的 id、onclick、状态类名都保持不动 —— 门禁和 377 套件不用重写。
   ========================================================================== */
(function () {
  'use strict';

  function $(id) { return document.getElementById(id); }

  /* ===================== §1 四个状态圆点 ===================== */

  // 即时 tooltip：原生 title 有 1 秒延迟、样式也不跟主题，
  // 而四点没有文字，语义全靠 hover —— 延迟 1 秒等于没有。
  var _tip = null;
  var _tipTimer = null;

  function ensureTip() {
    if (_tip) return _tip;
    _tip = document.createElement('div');
    _tip.className = 'tb-tip';
    _tip.setAttribute('role', 'tooltip');
    document.body.appendChild(_tip);
    return _tip;
  }

  function dotText(el) {
    if (!el) return '';
    var id = el.id || '';

    if (id === 'root-pill') {
      // title 由 setRootState() 按真实状态写：已 root / 未 root，点击执行 adb root …
      return el.title || 'root';
    }
    if (el.classList && el.classList.contains('wadb') || id === 'wadb-btn') {
      var ip = (typeof _wadbIp !== 'undefined' && _wadbIp) ? _wadbIp : '';
      var btn = $('wadb-btn');
      var on = btn && btn.classList.contains('on');
      return on || ip
        ? ('无线调试：已连接' + (ip ? ' ' + ip : '') + '（点击管理）')
        : '无线调试：未连接（点击连接）';
    }
    if (id === 'log-pill') {
      var lv = el.getAttribute('data-lv') || '';
      if (lv === 'none' || !lv) return '日志等级：未设置（点击查看取值方法）';
      return el.title || ('日志等级：' + lv);
    }
    if (id === 'dev-badge') {
      var parts = [];
      var i1 = $('dev-id'), i2 = $('dev-soc'), i3 = $('dev-res');
      if (i1 && i1.textContent.trim()) parts.push(i1.textContent.trim());
      if (i2 && i2.textContent.trim()) parts.push(i2.textContent.trim());
      if (i3 && i3.textContent.trim()) parts.push(i3.textContent.trim());
      return parts.length ? ('设备：' + parts.join(' · ')) : '设备未连接';
    }
    return el.title || '';
  }

  function tipShow(el) {
    var txt = dotText(el);
    if (!txt) return;
    var t = ensureTip();
    t.textContent = txt;
    t.style.left = '0px';
    t.style.top = '0px';
    t.classList.add('show');

    var r = el.getBoundingClientRect();
    var w = t.offsetWidth;
    var left = r.left + r.width / 2 - w / 2;
    var maxL = window.innerWidth - w - 8;
    if (left < 8) left = 8;
    if (left > maxL) left = maxL;
    t.style.left = Math.round(left) + 'px';
    t.style.top = Math.round(r.bottom + 8) + 'px';
  }

  function tipHide() {
    if (_tipTimer) { clearTimeout(_tipTimer); _tipTimer = null; }
    if (_tip) _tip.classList.remove('show');
  }

  function bindDot(el) {
    if (!el) return;
    el.addEventListener('mouseenter', function () {
      if (_tipTimer) clearTimeout(_tipTimer);
      _tipTimer = setTimeout(function () { tipShow(el); }, 60);
    });
    el.addEventListener('mouseleave', tipHide);
    el.addEventListener('blur', tipHide);
    el.addEventListener('click', tipHide);
  }

  function initDots() {
    // 点在自己身上的 mousedown 不能冒泡到 .tb-drag —— 否则点 root 点会变成拖窗口，
    // 点击永远不触发（这是四点放进标题栏最容易踩的一个坑）。
    var box = $('tb-status');
    if (box) {
      box.addEventListener('mousedown', function (e) { e.stopPropagation(); });
    }
    bindDot($('root-pill'));
    bindDot($('wadb-btn'));
    bindDot($('log-pill'));
    bindDot($('dev-badge'));
  }

  /* ===================== §2 无线弹窗定位 ===================== */

  // 弹窗进了标题栏，absolute 会被标题栏的堆叠上下文压到页签下面，
  // 所以改成 fixed + 按圆点位置算坐标。
  function positionWadbPop() {
    var pop = $('wadb-pop');
    var btn = $('wadb-btn');
    if (!pop || !btn) return;
    if (pop.style.display === 'none') return;
    var r = btn.getBoundingClientRect();
    pop.style.top = Math.round(r.bottom + 6) + 'px';
    var w = pop.offsetWidth || 300;
    var left = r.left - 6;
    var maxL = window.innerWidth - w - 10;
    if (left > maxL) left = maxL;
    if (left < 10) left = 10;
    pop.style.left = Math.round(left) + 'px';
  }

  function wrapWadb() {
    if (typeof window.toggleWadb === 'function' && !window.__v13WadbWrapped) {
      var orig = window.toggleWadb;
      window.toggleWadb = function (ev) {
        var r = orig.apply(this, arguments);
        positionWadbPop();
        return r;
      };
      window.__v13WadbWrapped = true;
    }
  }

  /* ===================== §3 终端：多行输入 ===================== */

  function taAutoGrow(n) {
    var el = $('cmd-input-' + n);
    if (!el || el.tagName !== 'TEXTAREA') return;
    el.style.height = 'auto';
    var h = el.scrollHeight;
    var max = 0;
    try {
      max = parseFloat(getComputedStyle(el).maxHeight) || 0;
    } catch (e) { max = 0; }
    el.style.height = (max > 0 ? Math.min(h, max) : h) + 'px';
    el.style.overflowY = (max > 0 && h > max) ? 'auto' : 'hidden';
  }
  // T10（2026-11-19）：中文输入法组字态守卫。
  // 用**事件委托**而不是给每个 textarea 绑：buildSlots() 在基础脚本里、
  // 比本层脚本先执行，直接调用 bindImeGrow 会 "is not defined"（实测整页中断）。
  // 委托挂在 document 上，只注册一次，动态新增的槽位也自动覆盖。
  function imeInputIndex(el) {
    if (!el || el.tagName !== 'TEXTAREA' || !el.id) return -1;
    var m = /^cmd-input-(\d+)$/.exec(el.id);
    return m ? parseInt(m[1], 10) : -1;
  }
  document.addEventListener('compositionstart', function (ev) {
    if (imeInputIndex(ev.target) >= 0) ev.target.__imeComposing = true;
  }, true);
  document.addEventListener('compositionend', function (ev) {
    var n = imeInputIndex(ev.target);
    if (n < 0) return;
    ev.target.__imeComposing = false;
    if (ev.target.__imePending) { ev.target.__imePending = false; taAutoGrow(n); }
  }, true);

  window.txAutoGrow = taAutoGrow;

  function insertNewline(el) {
    var s = el.selectionStart, e = el.selectionEnd, v = el.value;
    el.value = v.slice(0, s) + '\n' + v.slice(e);
    el.selectionStart = el.selectionEnd = s + 1;
    el.dispatchEvent(new Event('input', { bubbles: true }));
  }

  // 队列：一条跑完（end 消息回来）再发下一条。
  // 不用一次性拼成一条 shell 命令的原因：a;b 只在 shell 内成立，
  // 而这里允许 `adb xxx`、`:car`、`stweakxxx` 各种前缀混写。
  var _txQ = {};

  function txNext(slot) {
    var q = _txQ[slot];
    if (!q) return;
    if (q.i >= q.lines.length) { _txQ[slot] = null; return; }
    var inp = $('cmd-input-' + slot);
    if (!inp) { _txQ[slot] = null; return; }
    inp.value = q.lines[q.i++];
    taAutoGrow(slot);
    try { window.__v13RunRaw(slot); } catch (e) { _txQ[slot] = null; }
  }

  function wrapRun() {
    if (typeof window.run !== 'function' || window.__v13RunWrapped) return;
    var origRun = window.run;
    var origEnd = window.endRun;
    window.__v13RunRaw = function (slot) { return origRun(slot); };

    window.run = function (slot) {
      slot = slot || 0;
      var inp = $('cmd-input-' + slot);
      if (!inp) return origRun(slot);
      var raw = inp.value || '';
      if (raw.indexOf('\n') < 0) return origRun(slot);

      var lines = raw.split(/\r?\n/).map(function (s) { return s.trim(); })
                      .filter(function (s) { return s.length > 0; });
      if (lines.length <= 1) return origRun(slot);
      if (window._busy && window._busy[slot]) {
        if (typeof toast === 'function') toast('这个输入框的上一条指令还在执行，请稍候');
        return;
      }
      _txQ[slot] = { lines: lines, i: 0 };
      txNext(slot);
    };

    if (typeof origEnd === 'function') {
      window.endRun = function (r) {
        var out = origEnd.apply(this, arguments);
        var slot = (r && r.slot) || 0;
        if (_txQ[slot]) setTimeout(function () { txNext(slot); }, 0);
        return out;
      };
    }
  }

  function wrapStop() {
    if (typeof window.stop !== 'function' || window.__v13StopWrapped) return;
    var orig = window.stop;
    window.stop = function (slot) {
      slot = slot || 0;
      _txQ[slot] = null;   // 停止 = 整条队列作废，不是只停当前这一行
      return orig.apply(this, arguments);
    };
    window.__v13StopWrapped = true;
  }

  function wrapInputKey() {
    if (typeof window.onInputKey !== 'function' || window.__v13KeyWrapped) return;
    var orig = window.onInputKey;
    window.onInputKey = function (ev, n) {
      var el = ev.target;
      var isTA = el && el.tagName === 'TEXTAREA';

      if (isTA && ev.key === 'Enter' && ev.shiftKey) {
        ev.preventDefault();
        insertNewline(el);
        return;
      }
      if (isTA && (ev.key === 'ArrowUp' || ev.key === 'ArrowDown')) {
        // 多行编辑时方向键先走光标，走到首行/末行才交给历史 ——
        // 否则在第二行按 ↑ 会直接把内容换成上一条命令，整段丢光。
        var v = el.value || '';
        var pos = el.selectionStart;
        var first = v.indexOf('\n');
        var last = v.lastIndexOf('\n');
        if (ev.key === 'ArrowUp' && first >= 0 && pos > first) return;
        if (ev.key === 'ArrowDown' && last >= 0 && pos <= last) return;
      }
      return orig(ev, n);
    };
    window.__v13KeyWrapped = true;
  }

  function initTerminal() {
    wrapRun();
    wrapStop();
    wrapInputKey();
    // 已有的 textarea（slot 0..n）先量一次高度，避免首屏是空盒子
    var tas = document.querySelectorAll('#slots textarea[id^="cmd-input-"]');
    for (var i = 0; i < tas.length; i++) {
      var id = tas[i].id || '';
      var n = parseInt(id.replace('cmd-input-', ''), 10);
      if (!isNaN(n)) taAutoGrow(n);
    }
  }

  /* ===================== §4 输出区：点空白切换 ===================== */

  // 展开态点表头空白 = 收起；按钮/列标题上的点击不拦。
  window.fbHeadToggle = function (ev) {
    if (ev) {
      var t = ev.target;
      if (t && t.closest &&
          t.closest('button,.fbtn,.fb-acts,input,select,a,textarea')) return;
      ev.preventDefault();
    }
    if (typeof window.collapseFeed === 'function') window.collapseFeed();
  };

  /* ===================== §5 启动 ===================== */

  function boot() {
    initDots();
    wrapWadb();
    initTerminal();

    // 窗口尺寸变了，无线弹窗如果开着要跟着挪
    window.addEventListener('resize', function () {
      positionWadbPop();
      tipHide();
    });
    // 页面滚动 / 切页签时 tooltip 必须收起，否则会浮在错误的位置
    document.addEventListener('scroll', tipHide, true);
    window.addEventListener('blur', tipHide);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  // 切页签会重建 slot（buildSlots 重写 innerHTML），textarea 是新节点，
  // 这里在切换后补一次自动增高 + 重新接线。
  var _origSwitch = window.switchTab;
  if (typeof _origSwitch === 'function' && !window.__v13TabWrapped) {
    window.switchTab = function (name) {
      var r = _origSwitch.apply(this, arguments);
      try { initTerminal(); } catch (e) {}
      return r;
    };
    window.__v13TabWrapped = true;
  }
})();
/* === V13 JS END === */
