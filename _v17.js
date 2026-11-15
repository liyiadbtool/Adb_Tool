/* === V17 JS START ===
   A17（2026-11-15 第 6 批）— 行为层
     §1 开合动效的触发（打开 / 收起 / 恢复）
     §2 内嵌 scrcpy：区域上报、开关、降级
   这一层不重写既有逻辑，只在 window 上补函数 + 包一层，注入顺序最后。
   ========================================================================== */
(function () {
  'use strict';

  function $(id) { return document.getElementById(id); }
  function post(kind, data) {
    try { window.chrome.webview.postMessage({ kind: kind, data: data }); } catch (e) {}
  }

  /* ==================== §1 开合动效 ====================
     打开：hideSplash() 给 .frame 加 show 的同一帧再加 v17-in，
           和 splash 的 280ms 淡出叠在一起 —— 看到的是"从中心展开"。
     收起：C# 在最小化 / 关闭前 ExecuteScriptAsync("v17Out()")，
           130ms 后它再真正动窗口。
     恢复：从最小化回来时 C# 调 v17InRestore() 把 scale/opacity 复位，
           否则窗口会停在上一次淡出的"缩小的透明"状态。 */

  var _hideSplash0 = window.hideSplash;
  if (typeof _hideSplash0 === 'function') {
    window.hideSplash = function () {
      var fr = $('frame');
      if (fr) {
        fr.classList.remove('v17-out');
        fr.classList.remove('v16-in');     // A16 那套轮询触发会晚 300ms 再跑一次，去掉
        fr.classList.add('v17-in');
      }
      return _hideSplash0.apply(this, arguments);
    };
  }

  window.v17Out = function () {
    var fr = $('frame');
    if (!fr) return;
    fr.classList.remove('v17-in');
    fr.classList.add('v17-out');
  };

  window.v17InRestore = function () {
    var fr = $('frame');
    if (!fr) return;
    fr.classList.remove('v17-out');
    fr.classList.remove('v17-in');
  };

  /* ==================== §2 内嵌 scrcpy（每格一块） ====================
     A18 改造：从"单屏全窗口"改成"投屏页 3×2 六格，每格一块 scrcpy"。
     为什么用 Panel 而不是 <video>：scrcpy 是 SDL 原生窗口，推的是 h264 流，
     客户端解码后直接画在自己的 HWND 上。我们能做的是把这个 HWND
     用 SetParent 塞进应用（C# 侧 _cs/GuiWeb.cs 的 ScrcpyEmbed*），
     这样鼠标事件天然由 scrcpy 处理 —— 点击 / 滑动 / 键盘全都是原生跟手，
     帧率就是 scrcpy 自己的帧率（h264，30~60fps），不经过截图轮询。

     页面这边只负责：
       ① 每格告诉 C# 它那块区域在窗口里的比例（用比例而非像素，避免 Zoom/DPI 错位）；
       ② 开 / 停某格、切页时统一隐显。

     降级：某格 scrcpy 起不来（没装 / 设备不支持该屏）→ 该格回退到内置抓帧，
     并 toast 说明原因，其余格子不受影响。 */

  var EMBED = { on: [false, false, false, false, false, false] };

  /* 记住"用内嵌还是内置"——用户切到内置通道后不要又强行拉起 scrcpy。
     存进 _prefs（跟字号/显示选项同一条持久化通道），重启也保持。 */
  function rememberMode(m) {
    try {
      if (typeof _prefs === 'object' && _prefs) {
        _prefs.castMode = m;
        if (typeof window.prefsSave === 'function') window.prefsSave();
      }
    } catch (e) {}
  }

  /* 某格画面区的窗口比例（cell 的 .cast-view 矩形） */
  function embedRect(slot) {
    var v = document.querySelector('#cast-cell-' + slot + ' .cast-view');
    if (!v) return null;
    var r = v.getBoundingClientRect();
    var W = Math.max(1, window.innerWidth), H = Math.max(1, window.innerHeight);
    return { l: r.left / W, t: r.top / H, r: r.right / W, b: r.bottom / H };
  }

  /* 把某格区域比例发给 C#；隐藏时发 hide */
  function syncSlot(slot) {
    if (EMBED.on[slot] !== true) return;
    var r = embedRect(slot);
    if (!r) return;
    post('castembedrect', JSON.stringify({
      slot: slot,
      l: Math.round(r.l * 10000) / 10000,
      t: Math.round(r.t * 10000) / 10000,
      r: Math.round(r.r * 10000) / 10000,
      b: Math.round(r.b * 10000) / 10000
    }));
  }

  function cellIdle(slot, txt) {
    var el = document.getElementById('cast-idle-' + slot);
    if (el) el.textContent = txt;
  }

  function cellScrcpy(slot, on) {
    var c = document.getElementById('cast-cell-' + slot);
    if (c) c.classList.toggle('scrcpy', !!on);
  }

  /* 打开某格的内嵌 scrcpy。id = displayId（0 主屏 / 4 副驾 / 1 后排 / 3 HUD / 9 / 10） */
  window.v17CastEmbed = function (slot, id) {
    if (typeof slot !== 'number' || slot < 0 || slot > 5) slot = 0;
    if (typeof id !== 'number' || id < 0) id = 0;
    if (typeof _online !== 'undefined' && !_online) { toast('设备未连接'); return; }

    EMBED.on[slot] = true;
    cellScrcpy(slot, true);
    cellIdle(slot, '正在启动 scrcpy（h264 直连）…');
    rememberMode('embed');
    post('scrcpyembed', JSON.stringify({ slot: slot, id: id }));
    /* 区域要先给一次，Panel 才知道摆在哪；之后靠 resize / 切页同步 */
    setTimeout(function () { syncSlot(slot); }, 30);
  };

  window.v17CastEmbedStop = function (slot) {
    if (typeof slot !== 'number' || slot < 0 || slot > 5) slot = 0;
    EMBED.on[slot] = false;
    cellScrcpy(slot, false);
    post('scrcpyembedstop', JSON.stringify({ slot: slot }));
  };

  /* C# 回报：某格启动失败 → 该格回退内置通道并说明原因 */
  window.v17CastEmbedFail = function (slot, why) {
    if (typeof slot !== 'number' || slot < 0 || slot > 5) slot = 0;
    EMBED.on[slot] = false;
    cellScrcpy(slot, false);
    cellIdle(slot, 'scrcpy 没起来');
    try { toast('「' + (CAST_NAMES[slot] || ('屏' + slot)) + '」scrcpy 没起来：' + (why || '未知原因') + '，已回退内置抓帧'); } catch (e) {}
    /* 回退：让该格走内置抓帧通道 */
    try {
      if (typeof window.castBuiltinFallback === 'function') window.castBuiltinFallback(slot);
    } catch (e) {}
  };

  window.v17CastEmbedReady = function (slot) {
    if (typeof slot !== 'number' || slot < 0 || slot > 5) slot = 0;
    cellIdle(slot, 'scrcpy · 可点击操作');
  };

  /* 全屏某格时，把其它格的 scrcpy 藏起来（否则会浮在全屏那格上） */
  window.v17CastEmbedHide = function () {
    post('castembedhide', '');
  };

  /* 切页 / 改窗口大小时同步区域；离开投屏页就把所有 Panel 藏起来 */
  var _switch0 = window.switchTab;
  if (typeof _switch0 === 'function') {
    window.switchTab = function (name) {
      var r = _switch0.apply(this, arguments);
      try {
        if (name === 'cast') {
          setTimeout(function () {
            for (var i = 0; i < 6; i++) if (EMBED.on[i]) syncSlot(i);
          }, 30);
        } else {
          post('castembedhide', '');
        }
      } catch (e) {}
      return r;
    };
  }

  window.addEventListener('resize', function () {
    for (var i = 0; i < 6; i++) if (EMBED.on[i]) syncSlot(i);
  });
  /* 字号（ZoomFactor）变化时布局会重排，区域必须重报 */
  window.addEventListener('v17layout', function () {
    for (var i = 0; i < 6; i++) if (EMBED.on[i]) syncSlot(i);
  });

  /* ==================== §3 Edge 调研建议落地 ====================
     建议 1：色点 hover 显示 WCAG 对比度（把"白也能看清"从断言变成可见信任凭证）。
     建议 2：主题选择加迷你预览卡（真实令牌渲染明暗差异，不再纯文字按钮）。
     建议 3：强调色按设备序列号记忆（插 A8R 蓝、T09M 橙，一眼知道在测哪台）。
     建议 4：设置项按 Edge 顺序（明暗 → 强调色 → 字体）重排。
     建议 5（自定义 hex）明确不做，理由见 docs/参考-Edge主题设置与同类实现.md。 */

  /* —— 建议 1：动态算对比度（跟随当前主题的 --accent / --surface）—— */
  function hex2rgb(h) {
    h = (h || '').trim();
    if (h[0] === '#') h = h.slice(1);
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    if (h.length < 6) return null;
    var n = parseInt(h.slice(0, 6), 16);
    if (isNaN(n)) return null;
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function relLum(c) {
    if (!c) return 0;
    var f = function (v) { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
  }
  function contrast(a, b) {
    var la = relLum(a), lb = relLum(b);
    var hi = Math.max(la, lb), lo = Math.min(la, lb);
    return (hi + 0.05) / (lo + 0.05);
  }
  function accentContrastText(accentName) {
    /* 先临时把 --accent 换成目标色，再读它和 --on-accent 的对比度。
       用 CSS 变量读值，主题切换后自动跟着变，不用硬编码 48 条表。 */
    var r = document.documentElement;
    var prev = r.getAttribute('data-accent');
    r.setAttribute('data-accent', accentName);
    var cs = getComputedStyle(r);
    var acc = hex2rgb(cs.getPropertyValue('--accent').trim());
    var on = hex2rgb(cs.getPropertyValue('--on-accent').trim());
    r.setAttribute('data-accent', prev || 'blue');
    if (!acc || !on) return '';
    var c = contrast(acc, on);
    return c.toFixed(2) + ':1（AA' + (c >= 4.5 ? ' ✓' : ' ✗') + '）';
  }
  function armAccentContrast() {
    var dots = document.querySelectorAll('.accent-dot');
    for (var i = 0; i < dots.length; i++) {
      (function (d) {
        var name = d.getAttribute('data-accent') || 'blue';
        var baseTitle = d.getAttribute('title') || d.textContent;
        var armed = false;
        d.addEventListener('mouseenter', function () {
          try {
            if (!armed) { d.setAttribute('data-orig-title', baseTitle); armed = true; }
            d.setAttribute('title', baseTitle + ' · 文字对比度 ' + accentContrastText(name));
          } catch (e) {}
        });
      })(dots[i]);
    }
  }
  function tryArmContrast() {
    if (document.querySelector('.accent-dot')) armAccentContrast();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', tryArmContrast);
  else tryArmContrast();

  /* —— 建议 2：主题按钮加迷你预览卡 ——
     在 buildThemeSeg 之后补一层：每个主题按钮里塞一张小窗口缩略图，
     用该主题的真实令牌（--surface/--text/--accent）渲染，选中态仍走 .on。 */
  var _buildThemeSeg = window.buildThemeSeg;
  if (typeof _buildThemeSeg === 'function') {
    window.buildThemeSeg = function () {
      var r = _buildThemeSeg.apply(this, arguments);
      try {
        var box = document.getElementById('set-theme');
        if (box) {
          var btns = box.querySelectorAll('button');
          for (var i = 0; i < btns.length; i++) {
            var t = btns[i].getAttribute('data-theme');
            if (t) btns[i].classList.add('theme-card', 'tc-' + t);
          }
        }
      } catch (e) {}
      return r;
    };
  }

  /* —— 建议 3：按设备序列号记强调色 ——
     _prefs.accentByDevice = { '<serial>': '<accent>' }。
     prefsApply 时若有当前序列号，就用它覆盖全局 accent；没有就退回全局。
     C# 侧收到 device 变化会推 status，这里按 App.SERIAL 对应字段取名。 */
  function deviceAccentKey() {
    /* 序列号来源：setStatus 里存的全局 _dev（设备号）；取不到就空，退回全局色 */
    try {
      if (typeof _dev === 'string' && _dev) return _dev;
    } catch (e) {}
    return '';
  }
  function applyDeviceAccent() {
    try {
      var k = deviceAccentKey();
      if (!k || typeof _prefs !== 'object' || !_prefs) return;
      var map = _prefs.accentByDevice;
      if (!map || typeof map !== 'object') return;
      var a = map[k];
      if (typeof a === 'string' && a && typeof window.applyAccent === 'function') {
        window.applyAccent(a);
      }
    } catch (e) {}
  }
  /* 记住"这台设备用这个强调色"：用户切强调色时，若已连设备就写进设备映射 */
  var _setAccent0 = window.setAccent;
  if (typeof _setAccent0 === 'function') {
    window.setAccent = function (name) {
      var r = _setAccent0.apply(this, arguments);
      try {
        var k = deviceAccentKey();
        if (k && typeof _prefs === 'object' && _prefs) {
          if (!_prefs.accentByDevice || typeof _prefs.accentByDevice !== 'object') _prefs.accentByDevice = {};
          _prefs.accentByDevice[k] = name;
          if (typeof window.prefsSave === 'function') window.prefsSave();
        }
      } catch (e) {}
      return r;
    };
  }
  /* prefs 回填后按设备覆盖一次；设备上线时（setStatus）也补一次 */
  var _prefsApply0 = window.prefsApply;
  if (typeof _prefsApply0 === 'function') {
    window.prefsApply = function (b64) {
      var r = _prefsApply0.apply(this, arguments);
      try { applyDeviceAccent(); } catch (e) {}
      return r;
    };
  }
  var _setStatus0 = window.setStatus;
  if (typeof _setStatus0 === 'function') {
    window.setStatus = function (s) {
      var r = _setStatus0.apply(this, arguments);
      try { applyDeviceAccent(); } catch (e) {}
      return r;
    };
  }
})();
/* === V17 JS END === */
