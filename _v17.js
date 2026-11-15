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

  /* ==================== §2 内嵌 scrcpy ====================
     为什么用 Panel 而不是 <video>：scrcpy 是 SDL 原生窗口，推的是 h264 流，
     客户端解码后直接画在自己的 HWND 上。我们能做的是把这个 HWND
     用 SetParent 塞进应用（C# 侧 _cs/GuiWeb.cs 的 ScrcpyEmbed*），
     这样鼠标事件天然由 scrcpy 处理 —— 点击 / 滑动 / 键盘全都是原生跟手，
     帧率就是 scrcpy 自己的帧率（h264，30~60fps），不经过截图轮询。

     页面这边只负责两件事：
       ① 告诉 C# 那块区域在窗口里的比例（用比例而不是像素：页面受 ZoomFactor
          和 DPI 缩放影响，比例换算不会有误差）；
       ② 切换 / 切页时同步显隐。 */

  var EMBED = { on: false, id: 0, mode: 'embed' };

  /* 记住"用内嵌还是内置"——用户切到内置通道后再进投屏页，不要又强行拉起 scrcpy。
     存进 _prefs（跟字号/显示选项同一条持久化通道），重启也保持。 */
  function rememberMode(m) {
    EMBED.mode = m;
    try {
      if (typeof _prefs === 'object' && _prefs) {
        _prefs.castMode = m;
        if (typeof window.prefsSave === 'function') window.prefsSave();
      }
    } catch (e) {}
  }

  function embedRect() {
    var st = $('ce-stage');
    if (!st) return null;
    var r = st.getBoundingClientRect();
    var W = Math.max(1, window.innerWidth), H = Math.max(1, window.innerHeight);
    return { l: r.left / W, t: r.top / H, r: r.right / W, b: r.bottom / H };
  }

  /* 把当前区域比例发给 C#；隐藏时发 hide，让 C# 把 Panel 藏起来 */
  window.v17CastEmbedSync = function () {
    var host = $('cast-embed');
    if (!host || host.style.display === 'none') { post('castembedhide', ''); return; }
    var r = embedRect();
    if (!r) return;
    post('castembedrect', JSON.stringify({
      l: Math.round(r.l * 10000) / 10000,
      t: Math.round(r.t * 10000) / 10000,
      r: Math.round(r.r * 10000) / 10000,
      b: Math.round(r.b * 10000) / 10000
    }));
  };

  function setEmbedHint(txt) {
    var h = $('ce-hint');
    if (h) h.textContent = txt || '';
  }

  /* 当前选中的屏位号（投屏页网格的选中项；没选过就按主屏 0） */
  window.v17CurrentCastId = function () {
    var i = (typeof _castMaxed !== 'undefined' && _castMaxed >= 0) ? _castMaxed : 0;
    var id = 0;
    try { id = (typeof castSelectedId === 'function') ? castSelectedId(i) : 0; } catch (e) { id = 0; }
    return (typeof id === 'number' && id >= 0) ? id : 0;
  };

  /* 打开内嵌：id = displayId（0 主屏 / 4 副驾 / 1 后排 / 3 HUD / 9 / 10） */
  window.v17CastEmbed = function (id) {
    var host = $('cast-embed');
    if (!host) return;
    if (typeof _online !== 'undefined' && !_online) { toast('设备未连接'); return; }
    host.style.display = '';
    EMBED.on = true;
    EMBED.id = (typeof id === 'number') ? id : 0;
    setEmbedHint('正在启动内嵌 scrcpy（h264 直连，可点击操作）…');
    rememberMode('embed');
    post('scrcpyembed', String(EMBED.id));
    /* 区域要先给一次，Panel 才知道摆在哪；之后靠 resize / 切页同步 */
    setTimeout(function () { window.v17CastEmbedSync(); }, 30);
    var grid = $('cast-grid');
    if (grid) grid.style.display = 'none';
    var strip = $('cast-strip');
    if (strip) strip.style.display = 'none';
    syncCastModeBtn();
  };

  window.v17CastEmbedStop = function () {
    EMBED.on = false;
    post('scrcpyembedstop', '');
    var host = $('cast-embed');
    if (host) host.style.display = 'none';
    setEmbedHint('');
    var grid = $('cast-grid');
    if (grid) grid.style.display = '';
    var strip = $('cast-strip');
    if (strip) strip.style.display = '';
    syncCastModeBtn();
  };

  /* 内置抓帧通道（老路）：回到 MJPEG 网格 */
  window.v17CastBuiltin = function () {
    rememberMode('builtin');
    window.v17CastEmbedStop();
    if (typeof castRefreshStripFrames === 'function') { try { castRefreshStripFrames(); } catch (e) {} }
  };

  function syncCastModeBtn() {
    var b = $('cm-embed'), g = $('cm-builtin');
    if (b) b.classList.toggle('on', !!EMBED.on);
    if (g) g.classList.toggle('on', !EMBED.on);
    var hint = $('cast-hint');
    if (hint) {
      hint.textContent = EMBED.on
        ? '内嵌 scrcpy：h264 直连，30~60fps，可直接点击操作'
        : '内置通道 1~5fps（看链路，无线 adb 更慢）；要流畅请切到「内嵌 scrcpy」';
    }
    var fps = $('cast-fps');
    if (fps && EMBED.on) fps.textContent = '';
  }

  /* C# 回报：启动失败（没装 scrcpy / 找不到窗口）→ 自动降级并说明原因 */
  window.v17CastEmbedFail = function (why) {
    EMBED.on = false;
    var host = $('cast-embed');
    if (host) host.style.display = 'none';
    var grid = $('cast-grid');
    if (grid) grid.style.display = '';
    var strip = $('cast-strip');
    if (strip) strip.style.display = '';
    syncCastModeBtn();
    try { toast('内嵌投屏没起来：' + (why || '未知原因') + '，已回退内置通道'); } catch (e) {}
  };

  window.v17CastEmbedReady = function () {
    setEmbedHint('画面已接管 · 鼠标点击 / 拖动直接作用在车机上');
    syncCastModeBtn();
  };

  /* 切页 / 改窗口大小时同步区域；离开投屏页就把 Panel 藏起来（否则会浮在别的页上） */
  var _switch0 = window.switchTab;
  if (typeof _switch0 === 'function') {
    window.switchTab = function (name) {
      var r = _switch0.apply(this, arguments);
      try {
        if (name === 'cast') {
          /* 进投屏页：默认把内嵌 scrcpy 拉起来（用户要求"scrcpy 替代兜底"）。
             已经在内嵌就只重报区域；上次主动选了内置就尊重用户选择。 */
          setTimeout(function () {
            if (EMBED.on) { window.v17CastEmbedSync(); return; }
            if (EMBED.mode === 'embed') window.v17CastAutoEmbed();
            else window.v17CastEmbedSync();
          }, 30);
        } else if (EMBED.on) {
          post('castembedhide', '');
        }
      } catch (e) {}
      return r;
    };
  }

  window.addEventListener('resize', function () {
    if (EMBED.on) window.v17CastEmbedSync();
  });
  /* 字号（ZoomFactor）变化时布局会重排，区域必须重报 */
  window.addEventListener('v17layout', function () {
    if (EMBED.on) window.v17CastEmbedSync();
  });

  /* 初次进入投屏页时，如果还没选过模式，默认走内嵌（用户要求：scrcpy 替代兜底） */
  window.v17CastAutoEmbed = function () {
    var host = $('cast-embed');
    if (!host) return;
    if (EMBED.on) return;
    window.v17CastEmbed(window.v17CurrentCastId());
  };

  /* 回填上次选的模式（跟着 prefs 一起进来） */
  var _pa0 = window.prefsApply;
  window.prefsApply = function (b64) {
    var r = _pa0 ? _pa0.apply(this, arguments) : undefined;
    try {
      var o = JSON.parse(b64dec(b64) || '{}');
      if (o && (o.castMode === 'builtin' || o.castMode === 'embed')) EMBED.mode = o.castMode;
    } catch (e) {}
    return r;
  };
})();
/* === V17 JS END === */
