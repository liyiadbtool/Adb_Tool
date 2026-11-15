
(function(){
  var R=[];
  function ok(n,c,x){ R.push((c?'PASS':'FAIL')+' | '+n+(c?'':' | '+(x===undefined?'':x))); }
  function emit(){
    var p=document.createElement('pre'); p.id='RESULT';
    p.textContent=R.join('\n'); document.body.appendChild(p);
  }
  var st=document.createElement('style');
  st.textContent='*{transition:none!important;animation:none!important;}';
  document.head.appendChild(st);

  function g(sel,prop){ var el=document.querySelector(sel); if(!el) return '';
    return getComputedStyle(el)[prop]||''; }
  function posts(kind){ return (window.__POST||[]).filter(function(o){return o && o.kind===kind;}); }
  function idxOf(name){
    for(var i=0;i<quickGroups.length;i++) if(quickGroups[i].name === name) return i;
    return -1;
  }
  function hasChinese(t){ return /[\u4e00-\u9fa5]/.test(String(t||'')); }
  function parse(c){
    var m = String(c).match(/rgba?\(([^)]+)\)/);
    if(!m) return null;
    var p = m[1].split(',').map(function(x){ return parseFloat(x); });
    return { r:p[0], g:p[1], b:p[2], a:(p.length>3?p[3]:1) };
  }
  function overWhite(c){
    var o = parse(c); if(!o) return null;
    return { r:o.r*o.a+255*(1-o.a), g:o.g*o.a+255*(1-o.a), b:o.b*o.a+255*(1-o.a) };
  }
  function lum(o){
    function f(v){ v=v/255; return v<=0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); }
    return 0.2126*f(o.r) + 0.7152*f(o.g) + 0.0722*f(o.b);
  }
  function ratio(c){
    var o = overWhite(c); if(!o) return 0;
    return 1.05/(lum(o)+0.05);
  }
  function tok(name){
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }
  function isWhite(rgb){
    var o = parse(rgb);
    return !!o && o.r > 230 && o.g > 230 && o.b > 230;
  }
  function esc(k){ document.dispatchEvent(new KeyboardEvent('keydown', { key:'Escape', bubbles:true })); }

  function run(){
    /* ================= 一、网联服务分组 ================= */
    var qe = idxOf('指令执行'), ws = idxOf('网联服务');
    ok('存在「网联服务」分组', ws >= 0, ws);
    ok('紧跟在「指令执行」下面', ws === qe + 1, qe + ' -> ' + ws);
    if (ws < 0) return;

    var items = quickGroups[ws].items;
    ok('网联服务 13 条卡片', items.length === 13, items.length);

    var want = ['AI智能推荐后台','配置中心后台','支付宝后台','上传支付宝日志',
                '导出支付宝日志','导出微信小程序日志','导出车载微信日志',
                '打开星河云埋点','查询星河云埋点设置','设置星河云埋点true','查询设备ID',
                '打开星河埋点云','打开讯飞IOT云'];
    var names = items.map(function(it){ return it.name; });
    var miss = want.filter(function(w){ return names.indexOf(w) < 0; });
    ok('13 个卡片名齐全', miss.length === 0, miss.join(','));

    var cats = {};
    items.forEach(function(it){ if(it.cat) cats[it.cat]=1; });
    ok('按 4 个分类分组', Object.keys(cats).length === 4, Object.keys(cats).join('/'));

    function find(n){ for(var i=0;i<items.length;i++) if(items[i].name===n) return items[i]; return null; }
    ok('AI智能推荐 在网联服务里也有一张',
       !!find('AI智能推荐后台') && find('AI智能推荐后台').cmd === 'airec',
       find('AI智能推荐后台') && find('AI智能推荐后台').cmd);
    ok('三条导出走内置命令',
       (find('导出支付宝日志')||{}).cmd === ':wsalipay'
       && (find('导出微信小程序日志')||{}).cmd === ':wswmpf'
       && (find('导出车载微信日志')||{}).cmd === ':wswx',
       [find('导出支付宝日志'),find('导出微信小程序日志'),find('导出车载微信日志')]
         .map(function(x){ return x && x.cmd; }).join(','));
    ok('打开埋点走 :sxlog', (find('打开星河云埋点')||{}).cmd === ':sxlog',
       (find('打开星河云埋点')||{}).cmd);
    ok('查询设备ID 走 :wsdevid', (find('查询设备ID')||{}).cmd === ':wsdevid',
       (find('查询设备ID')||{}).cmd);
    var urls = items.filter(function(it){ return /^:url https://///.test(it.cmd||''); });
    ok('两条云平台走 :url', urls.length === 2, urls.length);
    ok('讯飞 IOT 链接正确', urls.some(function(u){ return u.cmd.indexOf('link.xfyun.cn/logs') > 0; }));
    ok('埋点校验页链接正确', urls.some(function(u){ return u.cmd.indexOf('acquisition-center-front') > 0; }));

    switchTab('quick');
    var nav = document.querySelectorAll('#quick-nav .qnav-item');
    var hit = -1;
    for(var i=0;i<nav.length;i++) if(nav[i].textContent.indexOf('网联服务') >= 0) hit = i;
  }
  setTimeout(function(){ run(); emit(); }, 200);
})();