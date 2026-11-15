"""投屏页（2026-11-13）的 DOM 行为测试。

覆盖：
  1) 第五个页签与 5 个固定槽位
  2) 屏位探测结果填充下拉、默认映射、提示文案
  3) 开启/停止：消息参数、img 流地址、按钮与边框状态
  4) 状态回传：帧率计算（按帧数差值）
  5) 录制：消息参数、按钮态、失败回滚
  6) 离线拦截、快捷键 Ctrl+4

运行：python _test_cast_ui.py
"""
import os
import tempfile
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
TEST = os.path.join(ROOT, "377", "test_cast_ui.html")
def _find_edge():
    """跨机器找 Edge：优先环境变量，再试两个默认安装位置。
    原先写死 C:/Program Files (x86)/...，换台机器/换用户名就跑不了。"""
    cands = []
    for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            cands.append(os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"))
    cands.append(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
    cands.append(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")
    for c in cands:
        try:
            if c and os.path.exists(c):
                return c
        except Exception:
            pass
    return "msedge.exe"   # 交给 PATH


EDGE = _find_edge()
PROF = os.path.join(tempfile.gettempdir(), "edgeprof_castui")
JS = r"""
<script>
(function(){
  var R = [];
  function ok(name, cond, extra){
    R.push((cond ? 'PASS' : 'FAIL') + ' | ' + name + (cond ? '' : ' | ' + (extra===undefined?'':extra)));
  }
  var SENT = [];
  try{
    window.chrome = window.chrome || {};
    window.chrome.webview = {
      postMessage: function(o){ SENT.push(o); },
      addEventListener: function(){}
    };
  }catch(e){}
  function last(kind){
    for(var i=SENT.length-1;i>=0;i--) if(SENT[i] && SENT[i].kind === kind) return SENT[i];
    return null;
  }
  function meta(i){
    return document.getElementById('cast-meta-' + i).textContent;
  }

  var DISP = { port: 45678, items: [
    {id:0, w:2560, h:1440, type:'INTERNAL', active:true},
    {id:2, w:1920, h:720,  type:'EXTERNAL', active:true},
    {id:3, w:800,  h:480,  type:'EXTERNAL', active:true}
  ]};

  function run(){
    try{
      setStatus({dev:'6dd4523c', online:true, rooted:true});

      // ---------- 1. 页签与槽位 ----------
      var tabs = document.querySelectorAll('.tab'), t = null;
      for(var i=0;i<tabs.length;i++) if(tabs[i].getAttribute('data-tab') === 'cast') t = tabs[i];
      ok('有「投屏」页签', !!t);
      switchTab('cast');
      ok('切到投屏页激活', document.getElementById('page-cast').classList.contains('active'));
      ok('生成 6 个槽位（含 HUD）', document.querySelectorAll('#cast-grid .cast-cell').length === 6,
         document.querySelectorAll('#cast-grid .cast-cell').length);
      ok('第 4 槽是 HUD',
         document.querySelector('#cast-cell-3 .cast-name').textContent === 'HUD',
         document.querySelector('#cast-cell-3 .cast-name').textContent);
      ok('进入页面就请求屏位', !!last('castlist'));

      // ---------- 2. 屏位填充 ----------
      onCastDisplays(DISP);
      ok('提示里显示屏数与分辨率',
         document.getElementById('cast-hint').textContent.indexOf('3 块屏') >= 0,
         document.getElementById('cast-hint').textContent);
      var sel0 = document.getElementById('cast-sel-0');
      ok('下拉填入 3 个选项', sel0.options.length === 3, sel0.options.length);
      ok('第 1 槽默认对应第 1 块屏', sel0.value === '0', sel0.value);
      ok('第 2 槽默认对应第 2 块屏',
         document.getElementById('cast-sel-1').value === '2',
         document.getElementById('cast-sel-1').value);
      ok('HUD 槽默认绑定 display 3（不落到主屏）',
         document.getElementById('cast-sel-3').value === '3',
         document.getElementById('cast-sel-3').value);

      // ---------- 3. 开启 ----------
      SENT.length = 0;
      castToggle(0);
      var st = last('caststart');
      ok('发出 caststart', !!st && st.slot === 0 && st.id === 0, JSON.stringify(st));
      var img = document.getElementById('cast-img-0');
      ok('img 指向本地流',
         (img.getAttribute('src') || '').indexOf('http://127.0.0.1:45678/live/0') === 0,
         img.getAttribute('src'));
      ok('img 显示', img.classList.contains('on'));
      ok('按钮变「停止」', document.getElementById('cast-btn-0').textContent === '停止');
      ok('格子带 on 类', document.getElementById('cast-cell-0').classList.contains('on'));
      ok('空闲提示隐藏', document.getElementById('cast-idle-0').style.display === 'none');

      // ---------- 4. 状态回传与帧率 ----------
      onCastStat({slot:0, on:true, frames:10, lastMs:400, id:0, err:''});
      ok('首帧算 10 fps', meta(0).indexOf('10 fps') >= 0, meta(0));
      ok('显示单帧耗时', meta(0).indexOf('400 ms') >= 0, meta(0));
      onCastStat({slot:0, on:true, frames:15, lastMs:320, id:0, err:''});
      ok('按差值算 5 fps', meta(0).indexOf('5 fps') >= 0, meta(0));

      // 后端报错 → 页面同步停止
      onCastStat({slot:0, on:false, frames:15, lastMs:0, id:0, err:'采集失败'});
      ok('后端停止后前端也停',
         document.getElementById('cast-btn-0').textContent === '开启',
         document.getElementById('cast-btn-0').textContent);
      ok('停止后隐藏画面', !document.getElementById('cast-img-0').classList.contains('on'));
      ok('停止后显示原因', meta(0).indexOf('未开启') >= 0 || document.getElementById('cast-idle-0').textContent.length > 0,
         document.getElementById('cast-idle-0').textContent);

      // ---------- 5. 停止（正常路径） ----------
      SENT.length = 0;
      castToggle(1);
      ok('第 2 槽开启时带的是屏 2',
         (last('caststart') || {}).id === 2, JSON.stringify(last('caststart')));
      SENT.length = 0;
      castToggle(1);
      var sp = last('caststop');
      ok('再点一次发 caststop', !!sp && sp.slot === 1, JSON.stringify(sp));
      ok('停止后按钮回「开启」',
         document.getElementById('cast-btn-1').textContent === '开启');

      // ---------- 6. 录制 ----------
      SENT.length = 0;
      castRecord(2);
      var rc = last('castrec');
      ok('录制发出 castrec on=1', !!rc && rc.slot === 2 && rc.on === '1', JSON.stringify(rc));
      ok('录制按钮变「停止录制」',
         document.getElementById('cast-rec-2').textContent === '停止录制');
      ok('录制时格子带 rec 类',
         document.getElementById('cast-cell-2').classList.contains('rec'));

      onCastRec({ok:false, slot:2, msg:'该屏不支持录制'});
      ok('录制失败后按钮回滚',
         document.getElementById('cast-rec-2').textContent === '录制',
         document.getElementById('cast-rec-2').textContent);
      ok('录制失败清掉 rec 类',
         !document.getElementById('cast-cell-2').classList.contains('rec'));
      ok('录制失败有提示',
         document.getElementById('toast').textContent.indexOf('不支持') >= 0,
         document.getElementById('toast').textContent);

      // ---------- 7. 离线拦截 / 快捷键 ----------
      _online = false;
      SENT.length = 0;
      castToggle(3);
      ok('离线不发起投屏', !last('caststart'));
      ok('离线给出提示',
         document.getElementById('toast').textContent.indexOf('设备未连接') >= 0,
         document.getElementById('toast').textContent);
      _online = true;

      switchTab('cmd');
      var ev = new Event('keydown', {bubbles:true, cancelable:true});
      Object.defineProperty(ev, 'key', {value:'4'});
      Object.defineProperty(ev, 'ctrlKey', {value:true});
      Object.defineProperty(ev, 'metaKey', {value:false});
      document.dispatchEvent(ev);
      ok('Ctrl+4 切到投屏页', document.getElementById('page-cast').classList.contains('active'));

      // ---------- 8. 最大化 / 还原 ----------
      ok('每格有最大化按钮',
         !!document.getElementById('cast-max-0') && !!document.getElementById('cast-max-4'));
      ok('默认有 2 条竖向 + 1 条横向分隔条',
         document.querySelectorAll('#cast-grid .cast-split.v').length === 2
         && document.querySelectorAll('#cast-grid .cast-split.h').length === 1,
         document.querySelectorAll('#cast-grid .cast-split').length);

      castMaxToggle(2);
      ok('最大化后该格带 maxed 类',
         document.getElementById('cast-cell-2').classList.contains('maxed'));
      ok('最大化后网格带 has-max 类',
         document.getElementById('cast-grid').classList.contains('has-max'));
      ok('最大化后按钮变还原符号',
         document.getElementById('cast-max-2').textContent === '⤡',
         document.getElementById('cast-max-2').textContent);
      ok('最大化后分隔条被移除',
         document.querySelectorAll('#cast-grid .cast-split').length === 0,
         document.querySelectorAll('#cast-grid .cast-split').length);
      ok('最大化不影响其它格：仍然显示（浮层覆盖，不是隐藏）',
         getComputedStyle(document.getElementById('cast-cell-0')).display !== 'none',
         getComputedStyle(document.getElementById('cast-cell-0')).display);
      // 让第 2 格也处于投屏中，再验证最大化不会把它停掉
      _castBusyResetForTest();
      castToggle(1);
      castMaxToggle(2);
      function _castBusyResetForTest(){ /* no-op：占位，保持结构清晰 */ }
      ok('最大化后其它格仍在投（img 还在、状态还是 on）',
         document.getElementById('cast-img-1').classList.contains('on')
         && !!document.getElementById('cast-img-1').getAttribute('src'),
         document.getElementById('cast-btn-1').textContent);
      castMaxToggle(2);

      castMaxToggle(2);
      ok('再点一次还原',
         !document.getElementById('cast-cell-2').classList.contains('maxed')
         && !document.getElementById('cast-grid').classList.contains('has-max'));
      ok('还原后分隔条回来',
         document.querySelectorAll('#cast-grid .cast-split').length === 3,
         document.querySelectorAll('#cast-grid .cast-split').length);

      // 换一格最大化：上一格要自动还原
      castMaxToggle(0);
      castMaxToggle(3);
      ok('切换到另一格时旧格自动还原',
         !document.getElementById('cast-cell-0').classList.contains('maxed')
         && document.getElementById('cast-cell-3').classList.contains('maxed'));
      castMaxToggle(3);

      // ---------- 8b. 全屏 + 底部缩略条 + 互换（R7） ----------
      _cast.on[0] = true; _cast.on[1] = true; _cast.on[4] = true;
      _cast.port = 45678;
      castEnterFull(0);
      ok('进入全屏：该格带 maxed',
         document.getElementById('cast-cell-0').classList.contains('maxed'));
      ok('全屏时显示缩略条',
         document.getElementById('cast-strip').classList.contains('on'));
      var thumbs = document.querySelectorAll('#cast-strip .cast-thumb');
      ok('缩略条覆盖其余 5 个槽', thumbs.length === 5, thumbs.length);
      ok('当前全屏的那一路不在缩略条里',
         !document.querySelector('#cast-strip .cast-thumb[data-slot="0"]'));
      ok('已开启的缩略图有 img',
         !!document.querySelector('#cast-strip .cast-thumb[data-slot="1"] img'));
      ok('未开启的缩略图有「开启」按钮',
         !!document.querySelector('#cast-strip .cast-thumb[data-slot="2"] button'));

      // 已开启的缩略图要真的显示画面（img 指向该槽的流）
      var tImg = document.querySelector('#cast-strip .cast-thumb[data-slot="1"] img');
      // 2026-11-15：底部缩略条改走 /snap 单帧短连接，避免多路 /live 长连接耗尽同源连接数。
      // 1 秒轮询只换 img.src 拿最新帧，所以这里不再要求 /live。
      ok('已开启的缩略图带当前画面（/snap 单帧）',
         !!tImg && (tImg.getAttribute('src') || '').indexOf('/snap/1') > 0,
         tImg ? tImg.getAttribute('src') : 'no-img');

      // 点「开启」把未开启的那一路开起来
      SENT.length = 0;
      castStartFromStrip(2);
      ok('从缩略条能直接开启',
         !!last('caststart') && last('caststart').slot === 2, JSON.stringify(last('caststart')));
      _cast.on[2] = false;

      castSwapFull(1);
      ok('点缩略图后全屏切换到目标格',
         document.getElementById('cast-cell-1').classList.contains('maxed'));
      ok('原全屏格已退出 maxed',
         !document.getElementById('cast-cell-0').classList.contains('maxed'));
      ok('切换后缩略条里出现原全屏格',
         !!document.querySelector('#cast-strip .cast-thumb[data-slot="0"]'));

      castExitFull();
      ok('退出全屏后缩略条隐藏',
         !document.getElementById('cast-strip').classList.contains('on'));

      // 关掉正在全屏的那一路 → 自动退出全屏
      castEnterFull(0);
      castToggle(0);
      ok('关掉全屏那一路会自动退出全屏',
         !document.querySelector('#cast-grid .cast-cell.maxed'),
         document.getElementById('cast-grid').className);

      _cast.on[0] = false; _cast.on[1] = false; _cast.on[4] = false;
      _castMaxed = -1;
      document.getElementById('cast-grid').classList.remove('has-max');
      document.getElementById('cast-strip').classList.remove('on');
      document.getElementById('cast-strip').innerHTML = '';

      // ---------- 8c. 录屏编码器 ffmpeg 状态芯片（R9） ----------
      SENT.length = 0;
      ffmpegQuery();
      ok('查询 ffmpeg 会发消息',
         !!last('ffmpegstat'), JSON.stringify(last('ffmpegstat')));

      SENT.length = 0;
      ffmpegAuto();
      ok('重新查找发 ffmpegauto',
         !!last('ffmpegauto'), JSON.stringify(last('ffmpegauto')));
      ok('重新查找时芯片显示查找中',
         document.getElementById('ff-txt').textContent.indexOf('查找中') >= 0,
         document.getElementById('ff-txt').textContent);

      SENT.length = 0;
      ffmpegPick();
      ok('选择按钮发 ffmpegpick',
         !!last('ffmpegpick'), JSON.stringify(last('ffmpegpick')));

      // 后端回包：可用 -> 绿点 + 版本 + 来源
      onFfmpegStat({ok:true, path:'C://tools//ffmpeg.exe', source:'程序同级',
                    version:'6.1.1', err:'', req:'auto'});
      ok('可用时芯片绿点', document.getElementById('ff-enc').className.indexOf('ok') >= 0,
         document.getElementById('ff-enc').className);
      var ffTxt = document.getElementById('ff-txt').textContent;
      ok('可用时显示版本与来源',
         ffTxt.indexOf('6.1.1') >= 0 && ffTxt.indexOf('程序同级') >= 0, ffTxt);
      ok('可用时 title 带完整路径',
         document.getElementById('ff-enc').title.indexOf('C://tools//ffmpeg.exe') >= 0,
         document.getElementById('ff-enc').title);

      // 不可用 -> 红点 + 引导点「选择…」
      onFfmpegStat({ok:false, path:'', source:'', version:'',
                    err:'没有可用的 ffmpeg.exe（检查了 12 个位置）', req:'stat'});
      ok('不可用时芯片红点', document.getElementById('ff-enc').className.indexOf('bad') >= 0,
         document.getElementById('ff-enc').className);
      ok('不可用时有引导文案',
         document.getElementById('ff-txt').textContent.indexOf('选择') >= 0,
         document.getElementById('ff-txt').textContent);
      ok('不可用时 title 是失败原因',
         document.getElementById('ff-enc').title.indexOf('检查了') >= 0,
         document.getElementById('ff-enc').title);

      // ---------- 8d. 外挂 scrcpy（R10）：探针 / 接入 / 降级 ----------
      SENT.length = 0;
      scrcpyQuery();
      ok('查询 scrcpy 会发消息', !!last('scrcpystat'), JSON.stringify(last('scrcpystat')));

      SENT.length = 0;
      scrcpyAuto();
      ok('重新查找发 scrcpyauto', !!last('scrcpyauto'));

      SENT.length = 0;
      scrcpyPick();
      ok('选择按钮发 scrcpypick', !!last('scrcpypick'));

      // 未安装：芯片红点；点「外部」不发请求（降级，别让用户以为坏了）
      onScrcpyStat({ok:false, path:'', version:'', err:'没有可用的 scrcpy.exe', req:'stat'});
      ok('scrcpy 未找到时芯片红点',
         document.getElementById('sc-enc').className.indexOf('bad') >= 0,
         document.getElementById('sc-enc').className);
      ok('scrcpy 未找到时文案标明可选',
         document.getElementById('sc-txt').textContent.indexOf('可选') >= 0,
         document.getElementById('sc-txt').textContent);

      // 先让 0 号槽有可选的屏（castSelectedId 读的是下拉框的值）
      onCastDisplays({port:45678, items:[{id:0, w:1920, h:720, type:'hdmi', active:true}]});
      var sel0 = document.getElementById('cast-sel-0');
      if (sel0) sel0.value = '0';
      _cast.on[0] = true;
      SENT.length = 0;
      scrcpyOpen(0);
      ok('未装 scrcpy 时不发 scrcpyopen', !last('scrcpyopen'), JSON.stringify(last('scrcpyopen')));

      // 装了：芯片绿点；点「外部」发 scrcpyopen{slot,id}
      onScrcpyStat({ok:true, path:'C://scrcpy//scrcpy.exe', version:'2.4', err:'', req:'auto'});
      ok('scrcpy 可用时芯片绿点',
         document.getElementById('sc-enc').className.indexOf('ok') >= 0,
         document.getElementById('sc-enc').className);
      ok('scrcpy 可用时显示版本',
         document.getElementById('sc-txt').textContent.indexOf('2.4') >= 0,
         document.getElementById('sc-txt').textContent);

      SENT.length = 0;
      scrcpyOpen(0);
      var so = last('scrcpyopen');
      ok('点「外部」发 scrcpyopen', !!so, JSON.stringify(so));
      ok('scrcpyopen 带槽位与屏 id', !!so && so.slot === 0 && so.id === 0, JSON.stringify(so));

      // A18：格子不再有「外部」按钮（scrcpy 已内嵌到每格）；开启即走 scrcpy 内嵌
      ok('格子不再有「外部」按钮（scrcpy 已内嵌）', !document.getElementById('cast-sc-0'));

      // 回包提示不抛异常
      onScrcpyRes({ok:true, slot:0, id:0, msg:'已用 scrcpy 打开屏 0'});
      onScrcpyRes({ok:false, slot:0, id:0, msg:'scrcpy 启动后立即退出'});
      ok('scrcpy 结果回包不抛异常', true);

      _cast.on[0] = false;

      // ---------- 9. 点击投屏（坐标换算 + 发 tap） ----------
      // 纯函数打靶：16:9 画面放进 4:3 的框里，左右会各有黑边
      var rect = {left: 0, top: 0, width: 400, height: 300};
      var c = castMapPoint(200, 150, rect, 1600, 900, 1600, 900);
      ok('点正中 → 设备中心', !!c && c.x === 800 && c.y === 450, JSON.stringify(c));

      // 400x300 的框放 16:9：上下有黑边（内容实际 400x225，垂直居中）
      var topGap = castMapPoint(200, 10, rect, 1600, 900, 1600, 900);
      ok('点在上方黑边上 → 不发送', topGap === null, JSON.stringify(topGap));

      var leftEdge = castMapPoint(0, 150, rect, 1600, 900, 1600, 900);
      ok('点最左边（内容内）能换算',
         !!leftEdge && leftEdge.x === 0 && leftEdge.y === 450, JSON.stringify(leftEdge));

      var quarter = castMapPoint(50, 150, rect, 1600, 900, 1600, 900);
      ok('横向按比例换算',
         !!quarter && quarter.x === 200 && quarter.y === 450, JSON.stringify(quarter));

      var far = castMapPoint(50, 150, rect, 1600, 900, 800, 480);
      ok('换分辨率按比例缩放', !!far && far.y === 240, JSON.stringify(far));

      ok('尺寸缺失返回 null', castMapPoint(10, 10, rect, 0, 0, 100, 100) === null);

      // 真实点击：桩住 img 的尺寸与 rect，点正中应发 casttap
      var img0 = document.getElementById('cast-img-0');
      _cast.on[0] = true;
      _cast.dim[0] = {w: 2560, h: 1440};
      Object.defineProperty(img0, 'naturalWidth', {value: 2560, configurable: true});
      Object.defineProperty(img0, 'naturalHeight', {value: 1440, configurable: true});
      img0.getBoundingClientRect = function(){
        return {left: 0, top: 0, width: 640, height: 360, right: 640, bottom: 360};
      };

      SENT.length = 0;
      var tapEv = new MouseEvent('click', {bubbles: true, clientX: 320, clientY: 180});
      img0.dispatchEvent(tapEv);
      var tMsg = last('casttap');
      ok('点画面发出 casttap', !!tMsg && tMsg.slot === 0, JSON.stringify(tMsg));
      ok('坐标换算到设备分辨率',
         !!tMsg && tMsg.x === 1280 && tMsg.y === 720, JSON.stringify(tMsg));
      ok('点击有涟漪反馈',
         !!document.querySelector('#cast-cell-0 .cast-ripple'));

      // 点在黑边（x>640）不发
      SENT.length = 0;
      var outEv = new MouseEvent('click', {bubbles: true, clientX: 700, clientY: 180});
      img0.dispatchEvent(outEv);
      ok('黑边点击不发送', !last('casttap'));

      // 未开启的格子点击不发
      SENT.length = 0;
      _cast.on[1] = false;
      var img1 = document.getElementById('cast-img-1');
      Object.defineProperty(img1, 'naturalWidth', {value: 1920, configurable: true});
      Object.defineProperty(img1, 'naturalHeight', {value: 720, configurable: true});
      img1.getBoundingClientRect = function(){
        return {left: 0, top: 0, width: 480, height: 180, right: 480, bottom: 180};
      };
      img1.dispatchEvent(new MouseEvent('click', {bubbles: true, clientX: 240, clientY: 90}));
      ok('未开启的格子点击不发送', !last('casttap'));

      // ---------- 主屏/后排屏内建映射（2026-11-15）----------
      // 需求：删除「前排投屏 / 后排投屏 / 刷新屏位」三个按钮，把能力内建进固定格子。
      ok('前排投屏按钮已删除', !document.getElementById('cast-front-btn'));
      ok('后排投屏按钮已删除', !document.getElementById('cast-rear-btn'));
      ok('刷新屏位按钮已删除', !document.getElementById('cast-refresh-btn'));
      ok('旧的一键前后排函数已移除（castRow/castRowId）',
         typeof castRow === 'undefined' && typeof castRowId === 'undefined');
      ok('内建映射纯函数存在',
         typeof castDefaultId === 'function' && typeof castHasDisplay === 'function');
      ok('castDefaultId 六格固定屏位映射（主屏0/副屏4/后排1/HUD3/PHUD-B9/PHUD-C10）',
         castDefaultId(0) === 0 && castDefaultId(1) === 4 &&
         castDefaultId(2) === 1 && castDefaultId(3) === 3 &&
         castDefaultId(4) === 9 && castDefaultId(5) === 10);
      ok('castHasDisplay 命中与缺失',
         castHasDisplay([{id:0},{id:1},{id:3}], 1) === true &&
         castHasDisplay([{id:0}], 1) === false &&
         castHasDisplay(null, 0) === false);
      ok('castToggle 在下拉没选时用 castDefaultId 兜底',
         castToggle.toString().indexOf('castDefaultId') >= 0);
      ok('主屏名字是「主屏」、后排屏名字是「后排屏」',
         CAST_NAMES[0] === '主屏' && CAST_NAMES[2] === '后排屏',
         CAST_NAMES.join('/'));

      // ---------- 禁拖拽 ghost（2026-11-15）----------
      ok('投屏 <img> 带 draggable=false',
         document.getElementById('cast-img-0').getAttribute('draggable') === 'false',
         String(document.getElementById('cast-img-0').getAttribute('draggable')));
      ok('castRenderCells 对 cast-view 绑了 dragstart 兜底',
         castRenderCells.toString().indexOf('dragstart') >= 0);

      // ---------- 点击流畅化（2026-11-15）----------
      ok('有同槽点击节流状态数组（6 槽各一份）',
         typeof _castTapLast !== 'undefined' && _castTapLast.length === 6,
         typeof _castTapLast !== 'undefined' ? _castTapLast.length : 'missing');
      ok('castTap 用 25ms 节流合并连点',
         castTap.toString().indexOf('_castTapLast') >= 0 &&
         castTap.toString().indexOf('25') >= 0);
      ok('castTap 用 naturalWidth/Height 兜底设备分辨率',
         castTap.toString().indexOf('naturalWidth') >= 0);
      ok('涟漪用 animationend 自清理（不堆 setTimeout）',
         castTap.toString().indexOf('animationend') >= 0 &&
         castTap.toString().indexOf('setTimeout') < 0);

      // ---------- 底部缩略条：/snap 单帧短连接 + 每路停止按钮（2026-11-15）----------
      ok('缩略条刷新函数存在（1 秒轮询换帧）',
         typeof castRenderStrip === 'function' && typeof castRefreshStripFrames === 'function');
      ok('缩略条改走 /snap，不再开 /live 长连接',
         castRenderStrip.toString().indexOf("'/snap/'") >= 0 &&
         castRenderStrip.toString().indexOf("'/live/'") < 0,
         castRenderStrip.toString().slice(0,180));
      ok('缩略图 img 带 data-slot 供轮询定位',
         castRenderStrip.toString().indexOf("data-slot=\"' + i + '\"") >= 0);
      ok('state 轮询里调 castRefreshStripFrames',
         castStartPoll.toString().indexOf('castRefreshStripFrames') >= 0);
      ok('刷新只换 img.src，不重建 DOM（停止按钮不会失效）',
         castRefreshStripFrames.toString().indexOf('innerHTML') < 0 &&
         castRefreshStripFrames.toString().indexOf('.src =') >= 0);
      ok('已开启的缩略图带常显停止按钮',
         castRenderStrip.toString().indexOf('cast-thumb-stop') >= 0 &&
         castRenderStrip.toString().indexOf("data-stop=\"' + i + '\"") >= 0);
      // 真的渲染一次：全屏槽0，开启槽1/2，看生成了什么
      var _oldPort = _cast.port, _oldMax = _castMaxed;
      _cast.port = 12345; _cast.on[1] = true; _cast.on[2] = true; _castMaxed = 0;
      castRenderStrip();
      var stripEl = document.getElementById('cast-strip');
      ok('全屏时缩略条为每路已开启画面生成停止按钮',
         !!stripEl && stripEl.querySelectorAll('.cast-thumb-stop[data-stop]').length === 2,
         stripEl ? stripEl.innerHTML.slice(0,150) : 'missing');
      ok('缩略图 src 指向 /snap 单帧端点',
         !!stripEl && stripEl.querySelectorAll('img[src*="/snap/"]').length === 2,
         stripEl ? stripEl.innerHTML.slice(0,150) : 'missing');
      ok('事件委托里识别 [data-stop]',
         document.body.innerHTML.indexOf("closest('[data-stop]')") >= 0);
      _cast.port = _oldPort; _cast.on[1] = false; _cast.on[2] = false; _castMaxed = _oldMax;
      castRenderStrip();

      // 清理定时器，避免影响页面卸载
      if(_cast.timer) { clearInterval(_cast.timer); _cast.timer = null; }

    }catch(e){
      ok('运行异常', false, e.message);
    }

    var pre = document.createElement('pre');
    pre.id = 'RESULT';
    pre.textContent = R.join('\n');
    document.body.appendChild(pre);
  }
  setTimeout(run, 300);
})();
</script>
"""


def main():
    win = os.environ.get("UI_WIN", "1100,760")
    src = open(UI, encoding="utf-8").read()
    open(TEST, "w", encoding="utf-8").write(src.replace("</body>", JS + "</body>"))

    url = "file:///" + TEST.replace("\\", "/")
    cmd = [
        EDGE, "--headless=new", "--disable-gpu",
        "--window-size=" + win,
        "--virtual-time-budget=6000",
        "--dump-dom",
        "--user-data-dir=" + PROF,
        url,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=150)
    dom = r.stdout or ""
    m = re.search(r'<pre id="RESULT">(.*?)</pre>', dom, re.S)
    if not m:
        print("没拿到 RESULT，DOM 长度", len(dom))
        print(dom[:800])
        return 1

    lines = [l for l in m.group(1).split("\n") if l.strip()]
    fails = [l for l in lines if l.startswith("FAIL")]
    for l in lines:
        print("  " + l)
    print("")
    print("  投屏：通过 %d / %d" % (len(lines) - len(fails), len(lines)))
    if fails:
        print("  有 %d 项失败" % len(fails))
        return 1
    print("  投屏行为全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
