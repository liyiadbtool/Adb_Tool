/* === V16 JS START === */
/* ==========================================================================
   A16（2026-11-15 第 5 批）
     §1 偏好统一回填（字号 / 日志等级 / 显示选项 / tab 顺序）
     §2 tab 拖拽换位并记忆
     §3 快捷指令搜索：一次性索引 + 分词 + 加权 + 防抖 + 结果上限
   这一层不重写原有逻辑，只包一层：既有函数都是顶层 function 声明，
   挂在 window 上，替换 window 上的引用即可生效，调用方（含内联 onclick）
   拿到的就是新实现。
   ========================================================================== */
(function () {
  'use strict';

  /* ==================== §1 偏好统一回填 ====================
     用户第 8 条："要记忆用户设置的前调色、主题、字体、文字大小等等"。
     现状不是"没存"而是"存了不读"：
       · prefsApply 只认 font / custom 两个字段；
       · 字号在 v14 层自己再解析一遍（补丁式写法，注释都写着"得自己再解析"）；
       · 日志等级 logshow 只写不读；
       · 显示选项（跟随系统 / OLED / 护眼）压根没进 prefs。
     这里改成"一份 schema 一次吃完"，后面不用再加补丁。 */
  function parsePrefs(b64) {
    try { return JSON.parse(b64dec(b64) || '{}') || {}; } catch (e) { return {}; }
  }

  function applyAllPrefs(o) {
    if (!o || typeof o !== 'object') return;
    /* A17：强调色也进 prefs。原来只存在 ini 的 accent= 一处，
       而那条路要经过 C# 的合法性白名单 —— 白名单一旦落后于色板（16 色时
       就出过一次），用户选的色会被静默改成 blue，重启即"强调色没记忆"。
       现在 prefs（base64 串）里也存一份，两条路任一存活就能恢复。 */
    if (typeof o.accent === 'string' && o.accent && typeof window.applyAccent === 'function') {
      try { window.applyAccent(o.accent); } catch (e) {}
    }
    if (typeof o.size === 'string' && o.size && typeof window.applySize === 'function') {
      try { window.applySize(o.size, true); } catch (e) {}
    }
    if (typeof window.v15Restore === 'function') {
      try {
        window.v15Restore({ logShow: o.logshow, oled: o.oled, eye: o.eye, auto: o.auto });
      } catch (e) {}
    }
    if (Array.isArray(o.tabOrder) && o.tabOrder.length) {
      try { applyTabOrder(o.tabOrder); } catch (e) {}
    }
  }

  var _prefsApplyOrig = window.prefsApply;
  window.prefsApply = function (b64) {
    var r = _prefsApplyOrig ? _prefsApplyOrig.apply(this, arguments) : undefined;
    applyAllPrefs(parsePrefs(b64));
    return r;
  };

  /* 切换强调色时同时写 prefs —— 见上面 applyAllPrefs 里注释：
     ini 的 accent= 是一条路，prefs 是第二条，双保险。 */
  var _setAccentOrig = window.setAccent;
  if (typeof _setAccentOrig === 'function') {
    window.setAccent = function (name) {
      var r = _setAccentOrig.apply(this, arguments);
      try {
        if (typeof _prefs === 'object' && _prefs) {
          _prefs.accent = name;
          if (typeof window.prefsSave === 'function') window.prefsSave();
        }
      } catch (e) {}
      return r;
    };
  }

  /* ==================== §2 tab 拖拽排序 + 记忆 ====================
     原来 tab 是写死的静态 HTML，顺序由 DOM 决定；翻页方向又用另一份写死的
     TAB_ORDER —— 两处不同步，所以拖不动。
     现在单一来源：DOM 顺序就是唯一真源，拖完把 data-tab 列表存进 prefs，
     启动时按它重排，并让 v15 的 TAB_ORDER 从 DOM 重算（翻页方向自动跟着走）。
     用 pointer 事件而不是 HTML5 draggable：后者在 WebView2 里长按延迟很难受。 */
  function tabEls() {
    return Array.prototype.slice.call(document.querySelectorAll('.tabs .tab'));
  }

  function applyTabOrder(order) {
    var bar = document.querySelector('.tabs');
    if (!bar || !order || !order.length) return;
    var els = tabEls();
    if (!els.length) return;
    var map = {};
    for (var i = 0; i < els.length; i++) map[els[i].getAttribute('data-tab')] = els[i];
    var frag = document.createDocumentFragment();
    var used = {};
    for (var k = 0; k < order.length; k++) {
      var e = map[order[k]];
      if (e && !used[order[k]]) { frag.appendChild(e); used[order[k]] = 1; }
    }
    for (var j = 0; j < els.length; j++) {
      var t = els[j].getAttribute('data-tab');
      if (!used[t]) frag.appendChild(els[j]);      // 新增的 tab 保持在末尾，不丢
    }
    bar.appendChild(frag);
    if (typeof window.v15SyncTabOrder === 'function') window.v15SyncTabOrder();
  }

  function saveTabOrder() {
    try {
      var arr = tabEls().map(function (e) { return e.getAttribute('data-tab'); });
      if (!window._prefs) return;
      _prefs.tabOrder = arr;
      prefsSave();
    } catch (e) {}
  }

  var drag = null;
  var suppressClickUntil = 0;

  function initTabDrag() {
    var bar = document.querySelector('.tabs');
    if (!bar || bar.getAttribute('data-v16drag')) return;
    bar.setAttribute('data-v16drag', '1');

    bar.addEventListener('pointerdown', function (ev) {
      if (ev.button !== 0) return;
      var el = ev.target && ev.target.closest ? ev.target.closest('.tab') : null;
      if (!el) return;
      drag = { el: el, x0: ev.clientX, y0: ev.clientY, moved: false };
    });

    bar.addEventListener('pointermove', function (ev) {
      if (!drag) return;
      var dx = ev.clientX - drag.x0, dy = ev.clientY - drag.y0;
      if (!drag.moved) {
        // 6px 死区：小于它就是普通点击，不能把"切 tab"误判成拖拽
        if (Math.abs(dx) < 6 && Math.abs(dy) < 6) return;
        drag.moved = true;
        drag.el.classList.add('v16-dragging');
        document.body.classList.add('v16-tabdrag');
        try { drag.el.setPointerCapture(ev.pointerId); } catch (e) {}
      }
      ev.preventDefault();
      var over = document.elementFromPoint(ev.clientX, ev.clientY);
      over = over && over.closest ? over.closest('.tab') : null;
      if (!over || over === drag.el) return;
      var r = over.getBoundingClientRect();
      var after = ev.clientX > r.left + r.width / 2;
      over.parentNode.insertBefore(drag.el, after ? over.nextSibling : over);
    });

    function end() {
      if (!drag) return;
      var moved = drag.moved;
      try { drag.el.classList.remove('v16-dragging'); } catch (e) {}
      document.body.classList.remove('v16-tabdrag');
      drag = null;
      if (moved) {
        // 松手后浏览器还会补一个 click，必须吃掉，否则会顺带切到被拖的那个 tab
        suppressClickUntil = Date.now() + 160;
        saveTabOrder();
        if (typeof window.v15SyncTabOrder === 'function') window.v15SyncTabOrder();
      }
    }
    bar.addEventListener('pointerup', end);
    bar.addEventListener('pointercancel', end);
    bar.addEventListener('click', function (ev) {
      if (Date.now() < suppressClickUntil) {
        ev.stopPropagation();
        ev.preventDefault();
      }
    }, true);
  }

  /* ==================== §3 快捷指令搜索 ====================
     用户第 5 条：指令会越堆越多，靠分类找不现实，要能"搜命令本身"。
     旧实现每次按键都全量遍历、只看 name/desc/cmd 三个字段、无防抖。
     现在：
       · 一次性把每条卡的 name/desc/cmd/cat/alias/kw/所属分组 拼成小写 hay；
       · 空格分词，全部命中才算中（"adb log 抓" 三个词都要在）；
       · 命中位置越靠前分越高，同分保持原顺序（稳定，不会跳来跳去）；
       · 输入 80ms 防抖 + 结果上限 80 条，输入法组合期间不触发。 */
  var HAY = null;

  function buildIndex() {
    HAY = [];
    for (var g = 0; g < quickGroups.length; g++) {
      var items = quickGroups[g].items || [];
      var gn = quickGroups[g].name || '';
      var row = [];
      for (var j = 0; j < items.length; j++) {
        var it = items[j];
        row.push(((it.name || '') + ' ' + (it.desc || '') + ' ' + (it.cmd || '') + ' '
                + (it.cat || '') + ' ' + (it.alias || '') + ' ' + (it.kw || '') + ' '
                + gn).toLowerCase());
      }
      HAY.push(row);
    }
  }

  function ensureIndex() {
    if (!HAY || HAY.length !== quickGroups.length) { buildIndex(); return; }
    for (var i = 0; i < quickGroups.length; i++) {
      // 自定义命令是异步推过来的，条数一变就得重建
      if (((quickGroups[i].items || []).length) !== (HAY[i] || []).length) { buildIndex(); return; }
    }
  }

  function scoreAt(hay, toks) {
    var s = 0;
    for (var i = 0; i < toks.length; i++) {
      var p = hay.indexOf(toks[i]);
      if (p < 0) return -1;
      s += p < 24 ? 3 : (p < 80 ? 2 : 1);      // 名字/命令里命中 > 说明里命中
    }
    return s;
  }

  var MAX_HITS = 80;

  window.renderSearchResults = function () {
    var nameEl = document.getElementById('quick-group-name');
    var cntEl = document.getElementById('quick-group-count');
    var panel = document.getElementById('vr-panel'); if (panel) panel.style.display = 'none';
    // 从 panel 型分组进搜索时，grid 还停在 display:none，必须显式恢复
    var ap = document.getElementById('apk-panel'); if (ap) ap.style.display = 'none';
    var np = document.getElementById('netsim-panel'); if (np) np.style.display = 'none';
    var cp = document.getElementById('custom-panel'); if (cp) cp.style.display = 'none';
    var g0 = document.getElementById('quick-grid'); if (g0) g0.style.display = '';
    var navItems = document.querySelectorAll('#quick-nav .qnav-item');
    for (var q = 0; q < navItems.length; q++) navItems[q].classList.remove('active');

    ensureIndex();
    var toks = String(_quickFilter || '').split(/\s+/).filter(function (x) { return !!x; });
    var hits = [];
    for (var g = 0; g < quickGroups.length; g++) {
      var items = quickGroups[g].items || [];
      for (var j = 0; j < items.length; j++) {
        var sc = toks.length ? scoreAt(HAY[g][j] || '', toks) : 0;
        if (sc < 0) continue;
        hits.push({ g: g, j: j, it: items[j], sc: sc });
      }
    }
    hits.sort(function (a, b) { return b.sc - a.sc || a.g - b.g || a.j - b.j; });

    var shown = hits.length > MAX_HITS ? MAX_HITS : hits.length;
    if (nameEl) nameEl.textContent = '搜索结果';
    if (cntEl) {
      cntEl.textContent = hits.length > shown
        ? (hits.length + ' 条，显示前 ' + shown)
        : (hits.length + ' 条');
    }

    var grid = document.getElementById('quick-grid');
    if (!grid) return;
    if (!hits.length) {
      grid.innerHTML = '<div class="qempty">没有匹配「' + escHtml(_quickFilter) + '」的指令</div>';
      return;
    }

    var html = '';
    for (var k = 0; k < shown; k++) {
      var h = hits[k], it2 = h.it;
      var sub2 = it2.desc || it2.cmd;
      var cls2 = 'qcard' + (it2.arg ? ' arg' : '') + (it2.toggle ? ' toggle' : '')
               + (it2.progress ? ' progress' : '');
      html += '<div class="' + cls2 + '" data-g="' + h.g + '" data-j="' + h.j + '"'
            + ' onclick="runQuickAt(' + h.g + ',' + h.j + ',this)">'
            + '<div class="qhead"><span class="qico">' + ICON_PLAY + '</span>'
            + '<span class="qname" title="' + escAttr(it2.name) + '">' + escHtml(it2.name) + '</span>'
            + (it2.arg ? '<span class="qarg" title="需要补充参数">＋</span>' : '')
            + '</div>'
            + '<div class="qcmd" title="' + escAttr(sub2) + '">' + escHtml(sub2) + '</div>'
            + '<div class="qbar"><i></i></div>'
            + '</div>';
    }
    grid.innerHTML = html;
  };

  /* 输入防抖放在"事件入口"这一层，而不是替换 onQuickSearch：
     替换会让任何同步调用者（测试、代码里直接调）都要等 80ms 才看到结果，
     表现为"点了没反应"。所以 input 事件改走 v16QuickInput，
     onQuickSearch 仍然是同步的那一个。80ms 足够挡住连续击键。 */
  var debTimer = null;
  window.v16QuickInput = function () {
    if (debTimer) clearTimeout(debTimer);
    debTimer = setTimeout(function () {
      debTimer = null;
      if (typeof window.onQuickSearch === 'function') window.onQuickSearch();
    }, 80);
  };

  /* 清空 / 回车这类即时动作不要等防抖 */
  var clearOrig = window.clearQuickSearch;
  if (clearOrig) {
    window.clearQuickSearch = function () {
      if (debTimer) { clearTimeout(debTimer); debTimer = null; }
      return clearOrig.apply(this, arguments);
    };
  }

  /* 供其它层在数据变化（自定义命令增删）后让索引失效 */
  window.v16InvalidateQuick = function () { HAY = null; };

  function boot() {
    try { initTabDrag(); } catch (e) {}
  }
  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', boot);
  else
    setTimeout(boot, 0);
})();
/* === V16 JS END === */
