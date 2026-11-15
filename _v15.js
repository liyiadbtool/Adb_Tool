/* === V15 JS START === */
/* ==========================================================================
   A15 · 交互层
     1) 页签翻页（按方向）
     2) 字体列表扩充 + 安装检测 + 分组
     3) 日志等级：hover 看 / 点击设（设备端 persist.log.tag + 本工具显示级别）
     4) 设备管理：hover 看 / 点击断开·切换
     5) 显示选项：跟随系统 / OLED 深黑 / 护眼三档
     6) 强调色白·黑 → 石墨 迁移

   原则和 V13/V14 一样：能包就不复制。既有函数语义一行不改，
   只在外面套一层，出问题把这一层摘掉就能回到上一版行为。
   ========================================================================== */
(function(){
  'use strict';

  function $(id){ return document.getElementById(id); }
  function el(tag, cls, html){
    var d = document.createElement(tag);
    if (cls) d.className = cls;
    if (html != null) d.innerHTML = html;
    return d;
  }
  function post2(kind, data, extra){
    try { post(kind, data, null, null, extra); } catch (e) {}
  }

  /* ======================================================================
     §1 页签翻页
     方向由 tab 序号决定：往右翻 = 从左下角起，往左翻 = 从右下角起。
     动画结束必须摘 class —— 带 transform 的元素会成为 fixed 后代的包含块，
     设置面板 / 帮助 / 文件弹窗都是 fixed，挂着不放会把它们定位错。
     ==================================================================== */
  var TAB_ORDER = ['quick', 'cmd', 'file', 'cast', 'ui', 'text'];

  function tabIndex(name){
    for (var i = 0; i < TAB_ORDER.length; i++) if (TAB_ORDER[i] === name) return i;
    return -1;
  }

  function flipTo(name){
    var page = $('page-' + name);
    if (!page) return;
    var cur = (document.querySelector('.tabs .tab.active') || {}).dataset;
    var from = cur ? tabIndex(cur.tab) : -1;
    var to = tabIndex(name);
    // 目标与当前相同：不翻，也不重启动画（重复点同一个页签不该抖）
    if (from === to || to < 0) return;

    var cls = (to > from) ? 'v15-flip-next' : 'v15-flip-prev';
    var other = (cls === 'v15-flip-next') ? 'v15-flip-prev' : 'v15-flip-next';
    page.classList.remove(other);
    page.classList.remove(cls);
    void page.offsetWidth;          // 强制回流，否则连点同一方向不会重播
    page.classList.add(cls);

    var done = function(){
      page.classList.remove(cls);
      page.removeEventListener('animationend', done);
    };
    page.addEventListener('animationend', done);
    // 兜底：prefers-reduced-motion 或动画被打断时 animationend 不触发
    setTimeout(done, 520);
  }

  if (typeof window.switchTab === 'function'){
    var origSwitch = window.switchTab;
    window.switchTab = function(name){
      flipTo(name);
      return origSwitch.apply(this, arguments);
    };
  }

  /* ======================================================================
     §2 字体：内置 / 系统自带 / 需安装 / 等宽
     检测方式用 canvas 测宽（document.fonts.check 对系统字体不可靠）：
     同一串字用「候选字体 + monospace」和「monospace」各量一次，宽度不同才算装了。
     ==================================================================== */
  var measure = (function(){
    try { return document.createElement('canvas').getContext('2d'); } catch (e) { return null; }
  })();
  var PROBE = 'mmmmmmmmmmlliWWW中文测试0123';

  function installed(name){
    if (!measure) return true;                       // 测不了就别拦着用户
    try {
      measure.font = '72px monospace';
      var w0 = measure.measureText(PROBE).width;
      measure.font = '72px "' + name + '", monospace';
      var w1 = measure.measureText(PROBE).width;
      return Math.abs(w1 - w0) > 0.5;
    } catch (e) { return true; }
  }

  /* group：下拉里的分组标题；only：候选字体名（用于检测与 CSS 回退链） */
  var FONTS = [
    { id:'system', name:'系统默认', group:'内置', core:'-apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Microsoft YaHei UI",system-ui,sans-serif', mono:'', always:true },
    { id:'inter',  name:'Inter', group:'内置', core:'"Inter","Microsoft YaHei UI",system-ui,sans-serif', mono:'', always:true },
    { id:'mono-all', name:'JetBrains Mono', group:'内置', core:'"JetBrains Mono","Microsoft YaHei UI",monospace', mono:'"JetBrains Mono",Consolas,monospace', always:true },

    { id:'yahei',  name:'微软雅黑', group:'中文 · 系统自带', core:'"Microsoft YaHei UI","Microsoft YaHei",sans-serif', probe:'Microsoft YaHei UI' },
    { id:'yaheel', name:'微软雅黑 Light', group:'中文 · 系统自带', core:'"Microsoft YaHei UI Light","Microsoft YaHei Light","Microsoft YaHei",sans-serif', probe:'Microsoft YaHei UI Light' },
    { id:'deng',   name:'等线 DengXian', group:'中文 · 系统自带', core:'"DengXian","Microsoft YaHei UI",sans-serif', probe:'DengXian' },
    { id:'jh',     name:'微软正黑体（繁）', group:'中文 · 系统自带', core:'"Microsoft JhengHei","Microsoft YaHei UI",sans-serif', probe:'Microsoft JhengHei' },
    { id:'hei',    name:'黑体 SimHei', group:'中文 · 系统自带', core:'"SimHei","Microsoft YaHei UI",sans-serif', probe:'SimHei' },
    { id:'song',   name:'宋体 SimSun', group:'中文 · 系统自带', core:'"SimSun","Microsoft YaHei UI",serif', probe:'SimSun' },
    { id:'nsong',  name:'新宋体 NSimSun', group:'中文 · 系统自带', core:'"NSimSun","SimSun",serif', probe:'NSimSun' },
    { id:'kai',    name:'楷体 KaiTi', group:'中文 · 系统自带', core:'"KaiTi","Microsoft YaHei UI",serif', probe:'KaiTi' },
    { id:'fang',   name:'仿宋 FangSong', group:'中文 · 系统自带', core:'"FangSong","Microsoft YaHei UI",serif', probe:'FangSong' },
    { id:'you',    name:'幼圆 YouYuan', group:'中文 · 系统自带', core:'"YouYuan","Microsoft YaHei UI",sans-serif', probe:'YouYuan' },
    { id:'li',     name:'隶书 LiSu', group:'中文 · 系统自带', core:'"LiSu","Microsoft YaHei UI",serif', probe:'LiSu' },
    { id:'xingkai', name:'华文行楷', group:'中文 · 系统自带', core:'"STXingkai","KaiTi",cursive', probe:'STXingkai' },

    { id:'noto',   name:'Noto Sans SC（思源黑体）', group:'中文 · 需安装', core:'"Noto Sans SC","Source Han Sans SC","Microsoft YaHei UI",sans-serif', probe:'Noto Sans SC' },
    { id:'notoser', name:'Noto Serif SC（思源宋体）', group:'中文 · 需安装', core:'"Noto Serif SC","Source Han Serif SC","SimSun",serif', probe:'Noto Serif SC' },
    { id:'wenkai', name:'霞鹜文楷 LXGW WenKai', group:'中文 · 需安装', core:'"LXGW WenKai","KaiTi",serif', probe:'LXGW WenKai' },
    { id:'smiley', name:'得意黑 Smiley Sans', group:'中文 · 需安装', core:'"Smiley Sans","Microsoft YaHei UI",sans-serif', probe:'Smiley Sans' },
    { id:'sarasa', name:'更纱黑体 Sarasa Gothic', group:'中文 · 需安装', core:'"Sarasa Gothic SC","Microsoft YaHei UI",sans-serif', probe:'Sarasa Gothic SC' },
    { id:'harmony', name:'HarmonyOS Sans', group:'中文 · 需安装', core:'"HarmonyOS Sans SC","Microsoft YaHei UI",sans-serif', probe:'HarmonyOS Sans SC' },
    { id:'misans', name:'MiSans（小米）', group:'中文 · 需安装', core:'"MiSans","Microsoft YaHei UI",sans-serif', probe:'MiSans' },
    { id:'puhuiti', name:'阿里巴巴普惠体', group:'中文 · 需安装', core:'"Alibaba PuHuiTi","Microsoft YaHei UI",sans-serif', probe:'Alibaba PuHuiTi' },

    { id:'segoe',  name:'Segoe UI', group:'西文 · 系统自带', core:'"Segoe UI","Microsoft YaHei UI",system-ui,sans-serif', probe:'Segoe UI' },
    { id:'segoevar', name:'Segoe UI Variable', group:'西文 · 系统自带', core:'"Segoe UI Variable Text","Segoe UI",system-ui,sans-serif', probe:'Segoe UI Variable Text' },
    { id:'calibri', name:'Calibri', group:'西文 · 系统自带', core:'"Calibri","Microsoft YaHei UI",sans-serif', probe:'Calibri' },
    { id:'cambria', name:'Cambria', group:'西文 · 系统自带', core:'"Cambria","Microsoft YaHei UI",serif', probe:'Cambria' },
    { id:'georgia', name:'Georgia', group:'西文 · 系统自带', core:'"Georgia","Microsoft YaHei UI",serif', probe:'Georgia' },
    { id:'verdana', name:'Verdana', group:'西文 · 系统自带', core:'"Verdana","Microsoft YaHei UI",sans-serif', probe:'Verdana' },
    { id:'tahoma',  name:'Tahoma', group:'西文 · 系统自带', core:'"Tahoma","Microsoft YaHei UI",sans-serif', probe:'Tahoma' },
    { id:'trebuc',  name:'Trebuchet MS', group:'西文 · 系统自带', core:'"Trebuchet MS","Microsoft YaHei UI",sans-serif', probe:'Trebuchet MS' },
    { id:'roboto',  name:'Roboto', group:'西文 · 需安装', core:'"Roboto","Microsoft YaHei UI",sans-serif', probe:'Roboto' },
    { id:'opensans', name:'Open Sans', group:'西文 · 需安装', core:'"Open Sans","Microsoft YaHei UI",sans-serif', probe:'Open Sans' },
    { id:'lato',    name:'Lato', group:'西文 · 需安装', core:'"Lato","Microsoft YaHei UI",sans-serif', probe:'Lato' },
    { id:'montserrat', name:'Montserrat', group:'西文 · 需安装', core:'"Montserrat","Microsoft YaHei UI",sans-serif', probe:'Montserrat' },
    { id:'plexsans', name:'IBM Plex Sans', group:'西文 · 需安装', core:'"IBM Plex Sans","Microsoft YaHei UI",sans-serif', probe:'IBM Plex Sans' },

    { id:'consolas', name:'Consolas', group:'等宽 · 代码日志', core:'', mono:'"Consolas","Microsoft YaHei UI",monospace', probe:'Consolas' },
    { id:'cascadia', name:'Cascadia Code', group:'等宽 · 代码日志', core:'', mono:'"Cascadia Code","Cascadia Mono",Consolas,monospace', probe:'Cascadia Code' },
    { id:'firacode', name:'Fira Code', group:'等宽 · 代码日志', core:'', mono:'"Fira Code",Consolas,monospace', probe:'Fira Code' },
    { id:'smono',   name:'Source Code Pro', group:'等宽 · 代码日志', core:'', mono:'"Source Code Pro",Consolas,monospace', probe:'Source Code Pro' },
    { id:'plexmono', name:'IBM Plex Mono', group:'等宽 · 代码日志', core:'', mono:'"IBM Plex Mono",Consolas,monospace', probe:'IBM Plex Mono' },
    { id:'robotomono', name:'Roboto Mono', group:'等宽 · 代码日志', core:'', mono:'"Roboto Mono",Consolas,monospace', probe:'Roboto Mono' },
    { id:'sarasamono', name:'Sarasa Mono SC', group:'等宽 · 代码日志', core:'', mono:'"Sarasa Mono SC",Consolas,monospace', probe:'Sarasa Mono SC' },

    { id:'custom', name:'自定义（填已安装的字体名）', group:'其它', core:'', mono:'' }
  ];

  // 是否已安装（内存缓存，一次启动只测一遍）
  var avail = {};
  function isAvail(f){
    if (f.always) return true;
    if (avail[f.id] === undefined)
      avail[f.id] = installed(f.probe || f.id);
    return avail[f.id];
  }

  /* 用新的字体表替换掉原 FONT_LIST，并复用既有的 buildFontSelect / applyFont。
     原表是 var FONT_LIST，顶层 var 挂在 window 上，可直接改内容。 */
  function rebuildFontTable(){
    if (typeof FONT_LIST === 'undefined' || !FONT_LIST.length) return false;
    FONT_LIST.length = 0;
    for (var i = 0; i < FONTS.length; i++){
      var f = FONTS[i];
      var ok = isAvail(f);
      FONT_LIST.push({
        id: f.id,
        name: ok ? f.name : (f.name + '（未安装）'),
        ui: f.core || undefined,
        mono: f.mono || undefined,
        // 下面两个是本层新增的元数据，_v14 的自绘浮层认它们
        grp: f.group,
        off: !ok
      });
    }
    return true;
  }

  function decorateFontSelect(){
    var sel = $('set-font');
    if (!sel) return;
    // 把 grp / off 写到 option 上：原生 select 不用它们，
    // 但 _v14 的自绘浮层会读，从而画出分组标题与「未安装」灰显。
    for (var i = 0; i < sel.options.length && i < FONT_LIST.length; i++){
      var o = sel.options[i], f = FONT_LIST[i];
      if (!o || !f) continue;
      if (f.grp) o.setAttribute('data-grp', f.grp);
      if (f.off) o.setAttribute('data-off', '1');
    }
  }

  if (typeof window.buildFontSelect === 'function'){
    var origBuildFont = window.buildFontSelect;
    window.buildFontSelect = function(){
      rebuildFontTable();
      var r = origBuildFont.apply(this, arguments);
      decorateFontSelect();
      return r;
    };
  }

  /* ======================================================================
     §3 即时提示（hover 看）
     原生 title 要等 1 秒且不能多行，圆点/徽章场景等不了。
     ==================================================================== */
  var tip = null;

  /* ==== 弹窗单例 + body 级 portal（A16）====
     两个徽章弹窗原来都 position:absolute 挂在徽章**里面**，三个后果：
       ① .titlebar 和 .tabs 都用了 backdrop-filter，各自形成层叠上下文，
          .tabs 在 DOM 里靠后，同级就压住了标题栏里的弹窗 —— 用户截图里
          弹窗右半边被 tab 栏吃掉，就是这条；
       ② 徽章自身（以及祖先链上的容器）有 overflow 裁剪，超出即被切掉；
       ③ 两个弹窗各管各的，谁也不知道对方开着，互斥无从谈起。
     现在统一挂到 body 上做 position:fixed，位置按锚点实时算：
       下方空间不够翻到上方，左右溢出贴边。层叠上下文 / overflow 全部绕开。 */
  var popCur = null;        // 'log' | 'dev' | null —— 同一时刻只允许一个
  var popAnchors = {};      // which -> 锚点元素

  function anyPopOpen(){ return !!popCur; }

  function popNode(which){
    return $(which === 'log' ? 'v15-logpop' : 'v15-devpop');
  }

  function placePop(p, anchor){
    if (!p || !anchor) return;
    var r = anchor.getBoundingClientRect();
    var w = p.offsetWidth, h = p.offsetHeight;
    var gap = 8, pad = 10;
    var vw = window.innerWidth, vh = window.innerHeight;
    var left = r.right - w;                       // 默认右对齐锚点
    if (left < pad) left = pad;
    if (left + w > vw - pad) left = Math.max(pad, vw - w - pad);
    var top = r.bottom + gap;                     // 优先往下
    if (top + h > vh - pad){
      var up = r.top - h - gap;                   // 下面放不下 → 翻上面
      top = (up >= pad) ? up : Math.max(pad, vh - h - pad);
    }
    p.style.left = Math.round(left) + 'px';
    p.style.top = Math.round(top) + 'px';
    p.style.maxHeight = Math.max(200, vh - pad * 2) + 'px';
  }

  function attachPop(p, which, anchor){
    if (!p) return;
    p.style.position = 'fixed';
    p.style.zIndex = '9800';
    document.body.appendChild(p);                 // 关键：脱离徽章，不受祖先裁剪
    popCur = which;
    popAnchors[which] = anchor;
    p.style.display = '';
    p.classList.add('on');
    placePop(p, anchor);
  }

  function detachPop(p, which){
    if (!p) return;
    p.style.display = 'none';
    p.classList.remove('on');
    delete popAnchors[which];
    if (popCur === which) popCur = null;
  }

  function closeAllPops(){
    var lp = $('v15-logpop'), dp = $('v15-devpop');
    if (lp) detachPop(lp, 'log');
    if (dp) detachPop(dp, 'dev');
    popCur = null;
  }

  function repositionPops(){
    if (!popCur) return;
    var p = popNode(popCur), a = popAnchors[popCur];
    if (p && a) placePop(p, a);
  }

  function showTip(anchor, html){
    // A16：弹窗开着就不要再冒提示 —— 鼠标从徽章移到弹窗上时仍算在徽章范围内，
    // 会再触发一次 mouseenter，结果提示和弹窗两套内容叠在一起（用户截图的那条）。
    if (anyPopOpen()) return;
    hideTip();
    tip = el('div', 'v15-tip', html);
    document.body.appendChild(tip);
    var r = anchor.getBoundingClientRect();
    var w = tip.offsetWidth, h = tip.offsetHeight;
    var left = Math.min(Math.max(r.right - w, 8), window.innerWidth - w - 8);
    var top = r.bottom + 8;
    if (top + h > window.innerHeight - 8) top = r.top - h - 8;
    tip.style.left = left + 'px';
    tip.style.top = Math.max(8, top) + 'px';
  }
  function hideTip(){
    if (tip && tip.parentNode) tip.parentNode.removeChild(tip);
    tip = null;
  }

  function bindHover(id, build){
    var node = $(id);
    if (!node) return;
    var timer = null;
    node.addEventListener('mouseenter', function(){
      if (timer) clearTimeout(timer);
      timer = setTimeout(function(){
        try { showTip(node, build()); } catch (e) {}
      }, 60);                     // 和标题栏圆点一致：60ms 就出
    });
    node.addEventListener('mouseleave', function(){
      if (timer) { clearTimeout(timer); timer = null; }
      hideTip();
    });
  }

  /* 全局收口：点空白处 / 按 Esc 关弹窗；窗口尺寸变化或滚动时跟随重定位。 */
  function initPopLayer(){
    document.addEventListener('click', function(ev){
      var t = ev.target;
      var inLog = t && t.closest && t.closest('#log-pill');
      var inDev = t && t.closest && t.closest('#dev-badge');
      var p = popCur ? popNode(popCur) : null;
      var inPop = p && t && p.contains(t);
      if (inPop) return;
      closeAllPops();
      if (!inLog && !inDev) hideTip();
    });
    document.addEventListener('keydown', function(ev){
      if (ev.key === 'Escape' && popCur) { closeAllPops(); hideTip(); }
    });
    window.addEventListener('resize', function(){ repositionPops(); hideTip(); });
    // 捕获阶段：页面内任何可滚动区域滚动，弹窗都跟着锚点走
    document.addEventListener('scroll', function(){ repositionPops(); }, true);
  }

  /* ======================================================================
     §4 日志等级：hover 看当前值，点击设
     Android 上有两件事，别混：
       A. 本工具显示级别 —— 只是本机过滤，立刻生效，不影响设备
       B. 设备端 persist.log.tag —— 全局默认等级，对新启动的进程生效，
          改完要重启才彻底（这一点必须写进面板，否则用户会以为没生效）
     ==================================================================== */
  var LV = ['V', 'D', 'I', 'W', 'E'];
  var LVNAME = { V:'Verbose', D:'Debug', I:'Info', W:'Warning', E:'Error' };
  var logDev = '';        // 设备端当前等级（getprop 回读）
  var logShow = 'V';      // 本工具显示级别

  function logTipHtml(){
    var d = logDev || (($('log-lv') || {}).textContent || '').trim() || '—';
    return '<b>日志等级</b><br>'
         + '<span class="k">设备端</span> <span class="mono">persist.log.tag</span> = <b>' + d + '</b>'
         + ' <span class="k">' + (LVNAME[d] || '') + '</span><br>'
         + '<span class="k">本工具显示</span> ≥ <b>' + logShow + '</b>'
         + '<br><span class="k">点击设置</span>';
  }

  function buildLogPop(){
    var p = el('div', 'v15-pop', '');
    p.id = 'v15-logpop';
    p.onclick = function(ev){ ev.stopPropagation(); };
    p.innerHTML =
      '<div class="v15-h">设备端日志等级 · persist.log.tag</div>' +
      '<div class="v15-lvseg" id="v15-lvdev">' +
        LV.map(function(k){ return '<button type="button" data-lv="' + k + '">' + k + '</button>'; }).join('') +
      '</div>' +
      '<div class="v15-note">写的是系统级默认等级，<b>对新启动的进程生效</b>；要彻底生效需重启设备。</div>' +
      '<div class="v15-sep"></div>' +
      '<div class="v15-h">本工具显示（只看不改设备）</div>' +
      '<div class="v15-lvseg" id="v15-lvshow">' +
        LV.map(function(k){ return '<button type="button" data-lv="' + k + '">' + k + '</button>'; }).join('') +
      '</div>' +
      '<div class="v15-note" id="v15-lvstate"></div>';
    return p;
  }

  function syncLogPop(){
    var p = $('v15-logpop');
    if (!p) return;
    var dbox = p.querySelector('#v15-lvdev'), sbox = p.querySelector('#v15-lvshow');
    if (dbox) [].forEach.call(dbox.children, function(b){
      b.classList.toggle('on', b.getAttribute('data-lv') === logDev);
    });
    if (sbox) [].forEach.call(sbox.children, function(b){
      b.classList.toggle('on', b.getAttribute('data-lv') === logShow);
    });
  }

  function openLogPop(){
    var pill = $('log-pill');
    if (!pill) return;
    if (popCur === 'dev'){ var dp = $('v15-devpop'); if (dp) detachPop(dp, 'dev'); }
    var p = $('v15-logpop');
    if (!p) p = buildLogPop();
    hideTip();
    attachPop(p, 'log', pill);
    syncLogPop();
    post2('logget', '');         // 打开时读一次设备真实值，别只信缓存
  }
  function closeLogPop(){
    var p = $('v15-logpop');
    if (p) detachPop(p, 'log');
  }

  function initLogPill(){
    var pill = $('log-pill');
    if (!pill) return;
    pill.addEventListener('click', function(ev){
      ev.stopPropagation();
      hideTip();
      if (popCur === 'log') { closeLogPop(); return; }
      openLogPop();
    });
    bindHover('log-pill', logTipHtml);

    // 事件委托挂在弹窗自己身上（弹窗已经挂到 body，不再是 pill 的后代）
    var pop = $('v15-logpop');
    if (!pop) { pop = buildLogPop(); }
    pop.addEventListener('click', function(ev){
      ev.stopPropagation();
      var t = ev.target;
      if (!t || t.tagName !== 'BUTTON') return;
      var lv = t.getAttribute('data-lv');
      if (!lv) return;
      if (t.parentNode && t.parentNode.id === 'v15-lvdev'){
        post2('logset', lv);
        logDev = lv;
        setTimeout(function(){ post2('logget', ''); }, 600);
      } else {
        logShow = lv;
        try { applyLogShow(lv); } catch (e) {}
      }
      syncLogPop();
    });
  }

  /* 本工具显示级别：前端过滤输出区。
     既有的输出区是按行渲染的，这里只在「已有的等级着色」基础上加一层隐藏，
     不动 C# 的抓取逻辑 —— 用户要的是"看得清"，不是"少抓"。 */
  function applyLogShow(lv){
    var rank = { V:0, D:1, I:2, W:3, E:4 };
    var min = rank[lv] || 0;
    var boxes = document.querySelectorAll('.logbox');
    for (var i = 0; i < boxes.length; i++){
      var rows = boxes[i].children;
      for (var j = 0; j < rows.length; j++){
        var row = rows[j];
        if (!row.dataset || !row.dataset.lv) continue;
        var r = rank[row.dataset.lv];
        if (r === undefined) continue;
        row.style.display = (r >= min) ? '' : 'none';
      }
    }
    try { _prefs.logshow = lv; prefsSave(); } catch (e) {}
  }

  /* ======================================================================
     §5 设备管理：hover 看当前设备，点击断开 / 切换
     切换要清探测缓存（车机信息 / 屏位 / APK 都是按设备缓存的），
     这一步交给 C# 做 —— 前端只发指令。
     ==================================================================== */
  var devCur = '';
  var devList = [];

  function devTipHtml(){
    var id = (($('dev-id') || {}).textContent || '').trim();
    var soc = (($('dev-soc') || {}).textContent || '').trim();
    var res = (($('dev-res') || {}).textContent || '').trim();
    var on = $('dev-dot') && $('dev-dot').classList.contains('ok');
    return '<b>设备</b> ' + (on ? '<span class="k">在线</span>' : '<span class="k">离线</span>') + '<br>'
         + '<span class="k">序列号</span> <span class="mono">' + (devCur || id || '—') + '</span><br>'
         + (soc ? '<span class="k">平台</span> ' + soc + '<br>' : '')
         + (res ? '<span class="k">分辨率</span> ' + res + '<br>' : '')
         + '<span class="k">点击管理设备</span>';
  }

  function buildDevPop(){
    var p = el('div', 'v15-pop', '');
    p.id = 'v15-devpop';
    p.style.width = '310px';
    p.onclick = function(ev){ ev.stopPropagation(); };
    p.innerHTML =
      '<div class="v15-h" id="v15-devh">已连接设备</div>' +
      '<div id="v15-devrows"></div>' +
      '<div class="v15-sep"></div>' +
      '<div class="v15-acts">' +
        '<button class="btn" id="v15-devrefresh" type="button">刷新</button>' +
        '<button class="btn" id="v15-devoff" type="button">断开当前</button>' +
      '</div>' +
      '<div class="v15-note">USB 连接无法软件断开，需拔线；无线连接会执行 adb disconnect。</div>';
    return p;
  }

  function renderDevRows(){
    var box = $('v15-devrows');
    if (!box) return;
    box.innerHTML = '';
    if (!devList.length){
      box.appendChild(el('div', 'v15-h', '没检测到设备（检查 USB / 无线连接）'));
      return;
    }
    for (var i = 0; i < devList.length; i++){
      var d = devList[i];
      var row = el('div', 'v15-row' + (d.cur ? ' on' : ''), '');
      row.setAttribute('data-serial', d.s);
      var dot = el('span', 'v15-dot ' + (d.st === 'device' ? 'ok' : (d.st === 'offline' ? 'err' : '')));
      row.appendChild(dot);
      var nm = el('span', '', d.model ? (d.model + ' · ') : '');
      nm.appendChild(el('span', 'mono', d.s));
      row.appendChild(nm);
      row.appendChild(el('span', 'v15-sub', d.cur ? '当前' : (d.st === 'device' ? '切换' : d.st)));
      box.appendChild(row);
    }
  }

  function openDevPop(){
    var badge = $('dev-badge');
    if (!badge) return;
    if (popCur === 'log'){ var lp = $('v15-logpop'); if (lp) detachPop(lp, 'log'); }
    var p = $('v15-devpop');
    if (!p) p = buildDevPop();
    hideTip();
    attachPop(p, 'dev', badge);
    renderDevRows();
    placePop(p, badge);          // 行数变了，尺寸跟着变，重新定位一次
    post2('devlist', '');
  }
  function closeDevPop(){
    var p = $('v15-devpop');
    if (p) detachPop(p, 'dev');
  }

  function initDevBadge(){
    var badge = $('dev-badge');
    if (!badge) return;
    badge.addEventListener('click', function(ev){
      ev.stopPropagation();
      hideTip();
      if (popCur === 'dev') { closeDevPop(); return; }
      openDevPop();
    });
    bindHover('dev-badge', devTipHtml);

    // 事件委托挂在弹窗身上（已挂到 body）
    var pop = $('v15-devpop');
    if (!pop) pop = buildDevPop();
    pop.addEventListener('click', function(ev){
      ev.stopPropagation();
      var t = ev.target;
      if (!t) return;
      if (t.id === 'v15-devrefresh'){ post2('devlist', ''); return; }
      if (t.id === 'v15-devoff'){ post2('devdisconnect', devCur || ''); return; }
      var row = t;
      while (row && row !== pop && !row.getAttribute('data-serial')) row = row.parentNode;
      if (row && row !== pop && row.getAttribute('data-serial')){
        var s = row.getAttribute('data-serial');
        if (s && s !== devCur) post2('devswitch', s);
      }
    });
  }

  /* ======================================================================
     §6 显示选项：跟随系统 / OLED / 护眼三档
     「跟随系统」= prefers-color-scheme + 21:00~07:00 自动护眼。
     它是迭在主题之上的一层策略，不新增第四套主题（避免主题矩阵 4×13 膨胀）。
     ==================================================================== */
  var DISP = { auto:false, oled:false, eye:'mid' };

  function sysDark(){
    try { return window.matchMedia('(prefers-color-scheme: dark)').matches; } catch (e) { return true; }
  }
  function isNight(){
    var h = new Date().getHours();
    return (h >= 21 || h < 7);
  }

  function applyDisplay(silent){
    var r = document.documentElement;
    r.dataset.oled = DISP.oled ? '1' : '';
    r.dataset.eyelevel = DISP.eye || 'mid';
    if (DISP.auto){
      var want = isNight() ? 'eye' : (sysDark() ? 'dark' : 'light');
      if (r.dataset.theme !== want){
        applyTheme(want);
        try { post('theme', want); } catch (e) {}
      }
    }
    syncDispSeg();
    if (!silent){
      // A16：显示选项也要进 prefs —— 原来只改 DOM，下次启动又回到默认。
      // 三个字段一起写，v15Restore 才能完整还原。
      try {
        _prefs.oled = !!DISP.oled;
        _prefs.eye = DISP.eye;
        _prefs.auto = !!DISP.auto;
        prefsSave();
      } catch (e) {}
    }
  }

  function seg(box, items, cur, onPick){
    if (!box) return;
    box.innerHTML = '';
    for (var i = 0; i < items.length; i++){
      (function(it){
        var b = document.createElement('button');
        b.type = 'button';
        b.textContent = it.name;
        b.className = it.v === cur ? 'on' : '';
        b.onclick = function(){ onPick(it.v); };
        box.appendChild(b);
      })(items[i]);
    }
  }

  function syncDispSeg(){
    seg($('set-auto'), [{v:0,name:'关闭'},{v:1,name:'跟随系统'}], DISP.auto ? 1 : 0, function(v){
      DISP.auto = !!v; applyDisplay(false);
      try { toast('跟随系统：' + (DISP.auto ? '开' : '关'), 'ok'); } catch (e) {}
    });
    seg($('set-oled'), [{v:0,name:'标准'},{v:1,name:'纯黑 OLED'}], DISP.oled ? 1 : 0, function(v){
      DISP.oled = !!v; applyDisplay(false);
    });
    seg($('set-eyelevel'), [{v:'light',name:'轻'},{v:'mid',name:'中'},{v:'deep',name:'深'}], DISP.eye, function(v){
      DISP.eye = v; applyDisplay(false);
    });
    var hint = $('set-display-hint');
    if (hint){
      var t = document.documentElement.dataset.theme;
      hint.textContent = DISP.auto
        ? ('跟随系统：当前按 ' + (isNight() ? '时段(夜间)' : '系统外观') + ' 判定为「' + ({dark:'黑夜',light:'白天',eye:'护眼'}[t] || t) + '」')
        : ('OLED 深黑只在黑夜主题下生效；护眼强度只在护眼主题下生效。');
    }
  }

  /* 主题切换加 180ms 交叉淡入，硬切会闪一下。
     实现用"旧底色遮罩淡出"，不是给 * 加 transition —— 后者会让
     getComputedStyle 在过渡期间返回**旧值**（颜色过渡的中间态），
     门禁里的对比度断言全部会读到上一套主题的颜色，实测直接挂 3 条。
     遮罩法：先把旧底色铺一层盖住，再瞬间换主题，然后让遮罩淡出。 */
  function crossfadeTheme(fn){
    var oldBg = '';
    try { oldBg = getComputedStyle(document.body).backgroundColor; } catch (e) {}
    fn();
    if (!oldBg) return;
    try {
      var ov = document.createElement('div');
      ov.style.cssText = 'position:fixed;inset:0;z-index:9999;pointer-events:none;'
                       + 'background:' + oldBg + ';transition:opacity 180ms cubic-bezier(.2,.8,.2,1);';
      document.body.appendChild(ov);
      void ov.offsetWidth;
      ov.style.opacity = '0';
      setTimeout(function(){ if (ov.parentNode) ov.parentNode.removeChild(ov); }, 220);
    } catch (e) {}
  }

  if (typeof window.applyTheme === 'function'){
    var origTheme2 = window.applyTheme;
    window.applyTheme = function(name){
      var self = this, args = arguments;
      crossfadeTheme(function(){ origTheme2.apply(self, args); });
      syncDispSeg();
    };
  }

  /* ======================================================================
     §7 强调色：white / black → graphite 迁移
     老偏好里存过 white / black。现在这两个名字没了（合并成石墨），
     不迁移的话 data-accent="white" 匹配不到任何规则 → 静默退回默认蓝。
     ==================================================================== */
  var ACCENT_ALIAS = { white:'graphite', black:'graphite' };
  function migrateAccent(){
    var r = document.documentElement;
    var a = r.dataset.accent || 'blue';
    if (ACCENT_ALIAS[a]){
      r.dataset.accent = ACCENT_ALIAS[a];
      try { post('accent', ACCENT_ALIAS[a]); } catch (e) {}
      // 同步色板上的选中态
      var dots = document.querySelectorAll('.accent-dot');
      for (var i = 0; i < dots.length; i++)
        dots[i].classList.toggle('sel', dots[i].getAttribute('data-accent') === ACCENT_ALIAS[a]);
    }
  }

  /* ======================================================================
     §8 设置面板：懒渲染，打开时补一次显示选项
     ==================================================================== */
  if (typeof window.openSettings === 'function'){
    var origOpen2 = window.openSettings;
    window.openSettings = function(){
      var r = origOpen2.apply(this, arguments);
      try { syncDispSeg(); } catch (e) {}
      return r;
    };
  }

  /* ======================================================================
     §9 与 C# 的消息入口
     C# 侧会推：logtag / logset 的回读、devlist 的设备表。
     ==================================================================== */
  window.v15Msg = function(msg){
    if (!msg || !msg.kind) return false;
    if (msg.kind === 'logtag'){
      var v = (msg.data || '').toString().trim().toUpperCase();
      logDev = (LV.indexOf(v) >= 0) ? v : '';
      var lvEl = $('log-lv');
      if (lvEl && logDev) lvEl.textContent = logDev;
      var st = $('v15-lvstate');
      if (st) st.textContent = logDev ? ('设备端已确认为 ' + logDev + '（' + (LVNAME[logDev] || '') + '）') : '读取失败：这个属性可能被系统锁定';
      syncLogPop();
      return true;
    }
    if (msg.kind === 'devlist'){
      devList = [];
      var lines = (msg.data || '').toString().split('\n');
      for (var i = 0; i < lines.length; i++){
        var ln = lines[i];
        if (!ln || ln.indexOf('|') < 0) continue;
        var p = ln.split('|');
        devList.push({ s:p[0] || '', model:p[1] || '', st:p[2] || 'device', cur:(p[3] === '1') });
        if (p[3] === '1') devCur = p[0] || '';
      }
      renderDevRows();
      return true;
    }
    return false;
  };

  /* ======================================================================
     §9.5 对上层（V16）暴露的偏好读写口
     以前 logshow / 显示选项是"只存不读"：写进 prefs 之后没有一处把它读回来。
     这里给一对明确的 API，由 _v16.js 的 prefsApply 包装统一调用 ——
     回填逻辑集中在 V16 一处，其它层不用各自再解析一遍。
     ==================================================================== */
  window.v15Snapshot = function(){
    return { logShow: logShow, oled: !!DISP.oled, eye: DISP.eye, auto: !!DISP.auto };
  };

  window.v15Restore = function(o){
    if (!o) return;
    try {
      if (typeof o.logShow === 'string' && LV.indexOf(o.logShow) >= 0){
        logShow = o.logShow;
        applyLogShow(logShow);
      }
      if (typeof o.oled === 'boolean') DISP.oled = o.oled;
      if (typeof o.eye === 'string' && o.eye) DISP.eye = o.eye;
      if (typeof o.auto === 'boolean') DISP.auto = o.auto;
      applyDisplay(true);          // silent：回填过程不要再写一次 prefs
      syncLogPop();
    } catch (e) {}
  };

  /* tab 顺序变了（用户拖动）→ 翻页方向必须跟着新顺序走。
     翻页方向只依赖 TAB_ORDER，重算一次即可，不需要改翻页实现。 */
  window.v15SyncTabOrder = function(){
    var els = document.querySelectorAll('.tabs .tab');
    var arr = [];
    for (var i = 0; i < els.length; i++){
      var t = els[i].getAttribute('data-tab');
      if (t) arr.push(t);
    }
    if (arr.length) TAB_ORDER = arr;
    return arr;
  };

  /* ======================================================================
     §10 启动
     ==================================================================== */
  /* 开场动效：等网页自己的 splash 退场之后再放，否则和启动动画叠一起。
     用轮询而不是监听 transitionend —— splash 可能在"减少动画"下不走过渡。 */
  function hookOpenAnim(){
    var fr = $('frame');
    if (!fr || fr.classList.contains('v16-in')) return;
    var t0 = Date.now();
    (function tick(){
      var sp = $('splash');
      var gone = !sp || sp.classList.contains('gone') || sp.style.display === 'none';
      if (gone || Date.now() - t0 > 8000){ fr.classList.add('v16-in'); return; }
      setTimeout(tick, 60);
    })();
  }

  function boot(){
    try { migrateAccent(); } catch (e) {}
    try { rebuildFontTable(); } catch (e) {}
    try { initLogPill(); } catch (e) {}
    try { initDevBadge(); } catch (e) {}
    try { syncDispSeg(); } catch (e) {}

    // A16：弹窗层收口（互斥 / 外部点击关闭 / 锚点跟随 / Esc）。
    // 原来的 mousedown 关闭逻辑在这里，弹窗挂到 body 之后它会把
    // "点弹窗自己"也算成"点空白"，必须搬进 initPopLayer 统一判断。
    try { initPopLayer(); } catch (e) {}
    try { hookOpenAnim(); } catch (e) {}

    // 系统外观变化时，跟随系统要跟着动
    try {
      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function(){
        if (DISP.auto) applyDisplay(true);
      });
    } catch (e) {}

    // 每分钟校一次时段（夜间自动护眼）
    setInterval(function(){ if (DISP.auto) applyDisplay(true); }, 60000);

    // 输出行补 data-lv：applyLogShow 靠它过滤
    try { markLogLevels(); } catch (e) {}
    if (logShow !== 'V') try { applyLogShow(logShow); } catch (e) {}
  }

  /* 给输出区每一行打上等级标记。C# 已经按等级上色（class 里带 lv?），
     这里做兜底：从行首的 "I/", "W/" 这类标记里取。取不到的当 V 放行。 */
  function markLogLevels(){
    var boxes = document.querySelectorAll('.logbox');
    for (var i = 0; i < boxes.length; i++){
      var rows = boxes[i].children;
      for (var j = 0; j < rows.length; j++){
        var row = rows[j];
        if (!row.dataset || row.dataset.lv) continue;
        var txt = (row.textContent || '').trim().slice(0, 2);
        var m = txt.match(/^([VDIWE])[\/\s]/);
        if (m) row.dataset.lv = m[1];
      }
    }
  }

  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', boot);
  else
    boot();

  // 设置面板每次打开都可能重建 select，补一次装饰
  document.addEventListener('click', function(ev){
    var t = ev.target;
    if (t && t.id === 'set-font') decorateFontSelect();
  }, true);
})();
/* === V15 JS END === */
