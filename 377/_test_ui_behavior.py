"""ui.html 交互行为测试（headless Edge + DOM 断言）。

为什么需要这一层：
  _check_ui.js 只能看源码文本，"点击后按钮不消失"这种事源上看不出来 ——
  它取决于 class 在事件前后的变化。这里真的把页面跑起来，用 JS 触发点击、
  读取 class/样式，把结论写进 DOM，再用 --dump-dom 抓回来。

运行：python _test_ui_behavior.py
"""
import os
import tempfile
import re
import subprocess
import sys

try:
    import _wv2                      # 真实 WebView2 测量通道（同目录）
except Exception:
    _wv2 = None


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 本脚本在 377/，项目根是上一级
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
TEST = os.path.join(ROOT, "377", "test_behavior.html")
def _find_browser():
    """2026-11-26（B）：浏览器可配置 + Chrome/Chromium 回退。
       本机实测 Edge 新版 --dump-dom 输出恒为空（rc=0 但无 DOM），
       所以顺序改成：环境变量 UI_BROWSER > Chrome > Chromium > Edge。
       Edge 仍保留在候选末尾，换台机器能跑就不影响原有行为。"""
    # 2026-11-26：项目内置 chrome-headless-shell（免安装，Edge 在本机跑不动）
    bundled = os.path.join(ROOT, "tools", "chrome-headless-shell", "chrome-headless-shell.exe")
    if os.path.exists(bundled):
        return bundled
    env = os.environ.get("UI_BROWSER")
    if env and os.path.exists(env):
        return env
    cands = []
    for envname in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.environ.get(envname)
        if not base:
            continue
        cands.append(os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"))
        cands.append(os.path.join(base, "Chromium", "Application", "chrome.exe"))
        cands.append(os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"))
    cands += [
        r"C://Program Files//Google//Chrome//Application//chrome.exe",
        r"C://Program Files (x86)//Google//Chrome//Application//chrome.exe",
        r"C://Program Files (x86)//Microsoft//Edge//Application//msedge.exe",
        r"C://Program Files//Microsoft//Edge//Application//msedge.exe",
    ]
    for c in cands:
        try:
            if c and os.path.exists(c):
                return c
        except Exception:
            pass
    return "msedge.exe"


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


EDGE = _find_browser()
# 2026-11-22：支持通过环境变量指定独立的浏览器 profile 目录。
# 目的：让 verify_all.py 能**并行**跑多个套件（它们共用同一个 profile 时会争抢锁，
# 串行必须 sleep 等待，实测 3 套串行 13.7s、并行只有 4.8s）。
# 不设该变量时行为与原来完全一致（仍落 edgeprof_beh），单独跑测试不受影响。
PROF = os.environ.get("UI_PROF") or os.path.join(tempfile.gettempdir(), "edgeprof_beh")
# ---- 注入的行为测试脚本 ----
# 每个 case 用 window.__ok() 记录，最后统一写进 #RESULT，便于 --dump-dom 抓取
BEHAVIOR = r"""
<script>
(function(){
  var R = [];
  function ok(name, cond, extra){
    R.push((cond ? 'PASS' : 'FAIL') + ' | ' + name + (cond ? '' : ' | ' + (extra===undefined?'':extra)));
  }
  function css(el, prop){ return getComputedStyle(el)[prop]; }

  /* 按名字取分组下标。
     之前测试里到处写死 switchQuickGroup(1) 表示「语音助手」，2026-11-12
     插入「方控按键」独立分组后，1 变成了方控、语音助手顺延到 2，
     结果 SCROLL 那几条断言拿到的是 display:none 的面板（rect 全 0），
     报出「面板顶部不被裁 0.0 vs 146.0」这种看不懂的失败。
     改成按名字查，以后再插分组也不会错位。 */
  function grpIdx(name){
    for(var i=0;i<quickGroups.length;i++){
      if(quickGroups[i].name === name) return i;
    }
    return -1;
  }

  function run(){
    try{
      // ---------- 问题3：root 按钮 ----------
      var pill = document.getElementById('root-pill');
      ok('P3 root 按钮存在', !!pill);

      setStatus({dev:'311b4567',online:true,soc:'8295',res:'1920x1080',dir:'',rooted:false,msg:'ok'});
      ok('P3 未 root 时带 no 类（红）', pill.classList.contains('no'), pill.className);
      ok('P3 未 root 时无 yes 类', !pill.classList.contains('yes'), pill.className);
      ok('P3 在线时不禁用', !pill.classList.contains('disabled'), pill.className);
      // A13：root 胶囊收成了纯圆点，「未 root」的语义由"红字"改为"圆点置灰"
      // （用户明确要求：已 root 跟随强调色、未 root 置灰）。红留给真正的异常。
      var dotEl = pill.querySelector('.rdot');
      // 圆点有 120ms 的背景过渡，headless 虚拟时间下过渡可能停在起始帧，
      // 读计算值前先临时关掉过渡并强制一次回流，否则读到的是旧颜色。
      function dotBg(el){
        if (!el) return '';
        var prev = el.style.transition;
        el.style.transition = 'none';
        void el.offsetWidth;
        var v = getComputedStyle(el).backgroundColor;
        el.style.transition = prev;
        return v;
      }
      var cDotNo = dotBg(dotEl);
      var accProbe = document.createElement('span');
      accProbe.style.color = 'var(--accent)';
      document.body.appendChild(accProbe);
      var cAccent = getComputedStyle(accProbe).color;
      document.body.removeChild(accProbe);
      ok('P3 未 root 圆点置灰（不等于强调色）',
         !!cDotNo && cDotNo !== cAccent, cDotNo + ' / accent=' + cAccent);

      setStatus({dev:'311b4567',online:true,soc:'8295',res:'1920x1080',dir:'',rooted:true,msg:'ok'});
      ok('P3 已 root 时带 yes 类（强调色）', pill.classList.contains('yes'), pill.className);
      ok('P3 已 root 时无 no 类', !pill.classList.contains('no'), pill.className);
      var cDotYes = dotBg(dotEl);
      ok('P3 已 root 圆点跟随强调色', !!cDotYes && cDotYes === cAccent,
         cDotYes + ' / accent=' + cAccent + ' / cls=' + pill.className);

      setStatus({dev:'',online:false,soc:'',res:'',dir:'',rooted:false,msg:'x'});
      ok('P3 离线时置灰禁用', pill.classList.contains('disabled'), pill.className);

      // 提权流程：点一下 → busy；rootdone 回来 → 解除
      setStatus({dev:'311b4567',online:true,soc:'8295',res:'1920x1080',dir:'',rooted:false,msg:'ok'});
      onRootClick();
      ok('P3 点击后进入 busy（转圈）', pill.classList.contains('busy'), pill.className);
      ok('P3 busy 期间不再响应点击', (function(){
        var before = pill.className;
        onRootClick();
        return pill.className === before;
      })());
      onRootDone({elevate:true, rooted:false});
      ok('P3 失败回执后解除 busy', !pill.classList.contains('busy'), pill.className);
      ok('P3 失败后回到红色', pill.classList.contains('no'), pill.className);
      onRootDone({elevate:true, rooted:true});
      ok('P3 成功回执后变绿', pill.classList.contains('yes'), pill.className);
      ok('P3 成功后解除 busy', !pill.classList.contains('busy'), pill.className);

      // ---------- 问题7：分辨率 ----------
      setStatus({dev:'311b4567',online:true,soc:'8295',res:'1920x1080',dir:'',rooted:false,msg:'ok'});
      var resEl = document.getElementById('dev-res');
      ok('P7 分辨率显示出来', resEl.textContent === '1920x1080', resEl.textContent);
      setStatus({dev:'311b4567',online:true,soc:'8295',res:'',dir:'',rooted:false,msg:'ok'});
      ok('P7 无分辨率时不显示', resEl.textContent === '', resEl.textContent);

      // ---------- 问题5/6：布局 ----------
      switchTab('quick');
      var cols = css(document.getElementById('quick-grid'), 'gridTemplateColumns');
      ok('P5 快捷指令一行三个', cols.split(' ').length === 3, cols);
      var names = [];
      var navs = document.querySelectorAll('.qnav-item');
      /* 2026-11-21（第 7 批需求1）：导航项内部结构变成
         「图标 qico2 + 名称 qname2 + 计数 qcnt + 名称气泡 qnav-tip」，
         直接取 textContent 会拼成「指令执行53指令执行」。只读 .qname2。 */
      for(var i=0;i<navs.length;i++){
        var nmEl = navs[i].querySelector('.qname2');
        names.push((nmEl ? nmEl.textContent : navs[i].textContent).trim());
      }
      // 2026-11-12：方控按键独立成组插在「指令执行」之后；
      // 同日又插入「手车互联」，语音助手再顺延到第四位。
      // 2026-11-15（A14）：用户在「指令执行」下面又加了「网联服务」，后面整体顺延一位。
      // 顺序：指令执行 / 网联服务 / 方控按键 / 手车互联 / 语音助手 / ...
      // 2026-11-15（A16）：用户要求「删掉独立的投屏（scrcpy）组，6 张卡并进指令执行」，
      // 所以从第三位起整体前移一位。
      // 2026-11-20（第 5 批需求 16）：用户明确给出 11 项顺序，整页重排：
      //   指令执行 / 网联服务 / 手车互联 / 语音助手 / 智驾出行 /
      //   方控按键 / Tbox / Scrcpy投屏 / Apk管理 / 网络模拟 / 自定义指令
      ok('P6 网联服务在第二位', names[1] === '网联服务', names.join('/'));
      ok('P6 手车互联在第三位', names[2] === '手车互联', names.join('/'));
      ok('P6 语音助手在第四位', names[3] === '语音助手', names.join('/'));
      ok('P6 智驾出行在第五位', names[4] === '智驾出行', names.join('/'));
      ok('P6 方控按键在第六位', names[5] === '方控按键', names.join('/'));
      ok('P6 没有独立的投屏组（已并入指令执行）',
         names.indexOf('投屏（scrcpy）') < 0 && names.indexOf('投屏') < 0, names.join('/'));

      // ---------- 问题8：卡片点击后不消失 ----------
      switchQuickGroup(grpIdx('指令执行'));
      var cards = document.querySelectorAll('.qcard');
      ok('快捷卡片已渲染', cards.length > 0, cards.length);
      var card = cards[0];
      var icoBefore = card.querySelector('.qico').innerHTML;
      runQuick(0);                  // 触发第一张卡（HCI导出）
      ok('P8 点击后卡片仍在 DOM 中', !!card.parentNode);
      ok('P8 点击后卡片仍可见', css(card,'display') !== 'none' && css(card,'visibility') !== 'hidden', css(card,'display'));
      ok('P8 点击后卡片不透明', parseFloat(css(card,'opacity')) > 0.9, css(card,'opacity'));
      ok('P8 点击后带 running 类', card.classList.contains('running'), card.className);
      ok('P8 执行中图标换成转圈/停止（仍有图标）',
         card.querySelector('.qico').innerHTML !== '' && card.querySelector('.qico').innerHTML !== icoBefore);
      // 执行中非 toggle 卡片不可再点
      ok('P8 执行中非 toggle 不可重复点击', css(card,'pointerEvents') === 'none', css(card,'pointerEvents'));

      // 结束 → 恢复可点
      endRun({ok:true, ms:1200, feed:{time:'10:00:00', cmd:'hci', ok:true, ms:1200}});
      ok('P8 结束后移除 running', !card.classList.contains('running'), card.className);
      ok('P8 结束后恢复可点击', css(card,'pointerEvents') !== 'none', css(card,'pointerEvents'));
      ok('P8 结束后卡片仍存在', !!card.parentNode);

      // ---------- 问题4：记录与输出 ----------
      // 2026-11-13 需求：输出框默认收起，有输出才按内容高度拉起。
      // 下面这些断言要量布局，所以先展开（默认态在 FOLD 段落单独验）。
      if(window.fbSetCollapsed) window.fbSetCollapsed(false);
      var tb = document.getElementById('fb-table');
      var rows = tb.querySelectorAll('.fb-row');
      ok('P4 至少有一条记录', rows.length >= 1, rows.length);
      var head = tb.querySelector('.fb-head');
      ok('P4 表头存在且在第一位', head && tb.firstElementChild === head);
      ok('P4 表头 sticky 置顶', head && css(head,'position') === 'sticky', head && css(head,'position'));

      var r0 = rows[rows.length-1];
      ok('P4 记录含左栏/竖线/右栏三块',
         !!r0.querySelector('.fb-left') && !!r0.querySelector('.fb-split') && !!r0.querySelector('.fb-right'));
      ok('P4 左栏含时间', !!r0.querySelector('.fb-meta .t') && r0.querySelector('.fb-meta .t').textContent.length > 0);
      ok('P4 左栏含耗时', /ms|—/.test(r0.querySelector('.fb-meta .d').textContent));
      ok('P4 左栏含结果徽章', !!r0.querySelector('.fb-meta .badge'));

      // 连续两条记录不能互相覆盖：各自的右栏是不同节点
      var rA = tb.querySelectorAll('.fb-row');
      addFeed({time:'10:00:01', cmd:'cmdA', ok:true, ms:1, out:[{level:0,text:'OUTPUT-A'}]});
      addFeed({time:'10:00:02', cmd:'cmdB', ok:true, ms:2, out:[{level:0,text:'OUTPUT-B'}]});
      var all = tb.querySelectorAll('.fb-row');
      var lastA = all[all.length-2], lastB = all[all.length-1];
      ok('P4 两条记录是不同节点', lastA !== lastB);
      ok('P4 前一条输出没被后一条覆盖',
         lastA.querySelector('.fb-right').textContent.indexOf('OUTPUT-A') >= 0,
         lastA.querySelector('.fb-right').textContent);
      ok('P4 后一条输出在自己栏内',
         lastB.querySelector('.fb-right').textContent.indexOf('OUTPUT-B') >= 0,
         lastB.querySelector('.fb-right').textContent);

      // 分栏占比：改 --fb-left 后左右栏实际宽度应跟着变
      var fb = document.getElementById('feedback');
      var w0 = r0.querySelector('.fb-left').offsetWidth;
      fb.style.setProperty('--fb-left','70%');
      var w1 = r0.querySelector('.fb-left').offsetWidth;
      ok('P4 调整 --fb-left 后左栏变宽', w1 > w0, w0 + ' -> ' + w1);
      fb.style.setProperty('--fb-left','46%');

      // 竖线可拖：mousedown 后带 dragging 类
      var sp = r0.querySelector('.fb-split');
      var ev = document.createEvent('MouseEvents');
      ev.initMouseEvent('mousedown', true, true, window, 0, 0, 0, 10, 10, false,false,false,false,0,null);
      sp.dispatchEvent(ev);
      ok('P4 竖线按下进入 dragging', sp.classList.contains('dragging'), sp.className);
      var up = document.createEvent('MouseEvents');
      up.initMouseEvent('mouseup', true, true, window, 0, 0, 0, 10, 10, false,false,false,false,0,null);
      document.dispatchEvent(up);

      // 换行：长指令的 scrollWidth 不超过 clientWidth（说明被换行而不是横向溢出）
      addFeed({time:'10:00:03', cmd:'x'.repeat(400), ok:true, ms:3, out:[{level:0,text:'y'.repeat(400)}]});
      var allc = tb.querySelectorAll('.fb-row');
      var rl = allc[allc.length-1];
      var cEl = rl.querySelector('.c');
      ok('P4 长指令换行不横向溢出', cEl.scrollWidth <= cEl.clientWidth + 1, cEl.scrollWidth + '/' + cEl.clientWidth);
      var oEl = rl.querySelector('.fb-right');
      ok('P4 长输出换行不横向溢出', oEl.scrollWidth <= oEl.clientWidth + 1, oEl.scrollWidth + '/' + oEl.clientWidth);
      ok('P4 长输出内部可滚动', css(oEl,'overflowY') === 'auto', css(oEl,'overflowY'));
      ok('P4 记录区可滚动', css(tb,'overflowY') === 'auto', css(tb,'overflowY'));

      // ---------- 需求1：表头与记录列严丝合缝 + 字符限制 ----------
      // 只看源码证明不了对齐，必须量真实像素：表头每个标签的左边界
      // 要等于记录里对应字段的左边界（误差 <= 1px）。
      var hT = head.querySelector('.h-meta .h-t');
      var hB = head.querySelector('.h-meta .h-b');
      var hD = head.querySelector('.h-meta .h-d');
      var hC = head.querySelector('.h-c');
      var hS = head.querySelector('.h-s');
      ok('需求1 表头含 时间/状态/耗时/指令/输出 五个标签',
         !!hT && !!hB && !!hD && !!hC && !!hS,
         [!!hT,!!hB,!!hD,!!hC,!!hS].join(','));

      // 拿一条正常长度的记录来比对（长指令那条会换行，但左边界一样）
      var rm = allc[allc.length-1];
      var rT = rm.querySelector('.fb-meta .t');
      var rB = rm.querySelector('.fb-meta .badge');
      var rD = rm.querySelector('.fb-meta .d');
      var rC = rm.querySelector('.c');
      var rR = rm.querySelector('.fb-right');
      function L(el){ return el.getBoundingClientRect().left; }
      function near(a,b){ return Math.abs(a-b) <= 1; }
      ok('需求1 时间列左右边界对齐', near(L(hT), L(rT)), L(hT).toFixed(1)+' vs '+L(rT).toFixed(1));
      ok('需求1 状态列左右边界对齐', near(L(hB), L(rB)), L(hB).toFixed(1)+' vs '+L(rB).toFixed(1));
      ok('需求1 耗时列左右边界对齐', near(L(hD), L(rD)), L(hD).toFixed(1)+' vs '+L(rD).toFixed(1));
      // 右对齐列：右边界也要齐，否则数字位数不同就歪
      ok('需求1 耗时列右边界对齐',
         near(hD.getBoundingClientRect().right, rD.getBoundingClientRect().right),
         hD.getBoundingClientRect().right.toFixed(1)+' vs '+rD.getBoundingClientRect().right.toFixed(1));
      ok('需求1 指令列左边界对齐', near(L(hC), L(rC)), L(hC).toFixed(1)+' vs '+L(rC).toFixed(1));
      ok('需求1 输出列左边界对齐', near(L(hS), L(rR)), L(hS).toFixed(1)+' vs '+L(rR).toFixed(1));
      ok('需求1 状态列居中于 38px 盒内',
         css(rB,'textAlign') === 'center' && css(rB,'width') === '38px',
         css(rB,'textAlign')+'/'+css(rB,'width'));

      // 字符限制：400 字符指令必须被截到 2 行（不是撑高整条记录）
      var lh = parseFloat(css(rC,'lineHeight')) || 18;
      ok('需求1 长指令被限制在 2 行内',
         rC.clientHeight <= lh*2 + 2, rC.clientHeight+'px / line '+lh);
      ok('需求1 长指令溢出被隐藏（overflow:hidden）', css(rC,'overflow') === 'hidden', css(rC,'overflow'));
      ok('需求1 长指令有 title 悬停全文',
         !!rC.title && rC.title.length === 400, rC.title && rC.title.length);
      ok('需求1 输出区限高 200px（足够放下车机信息 10 行）', Math.abs(parseFloat(css(rR,'maxHeight')) - 200) < 1, css(rR,'maxHeight'));

      // 未超长的指令不该有 title（避免无意义的悬停提示）
      var shortRow = lastA;
      var shortC = shortRow.querySelector('.c');
      ok('需求1 短指令不设 title', !shortC.title, shortC.title);

      // ---------- 问题2：加载层 ----------
      var sp2 = document.getElementById('splash');
      ok('P2 splash 已退场', sp2.classList.contains('hide') || sp2.classList.contains('gone'), sp2.className);
      ok('P2 frame 已显示', document.getElementById('frame').classList.contains('show'));
      var fr = document.getElementById('frame');
      ok('P2 frame 不留半透明', parseFloat(css(fr,'opacity')) > 0.99, css(fr,'opacity'));

      // ---------- 需求·补充：删除输入框 ----------
      switchTab('cmd');
      buildSlots();   // 复位到 1 个槽
      ok('DEL 初始只有 1 个槽', document.querySelectorAll('#slots .slot').length === 1,
         document.querySelectorAll('#slots .slot').length);
      ok('DEL 单槽时隐藏删除按钮',
         css(document.querySelector('#slot-0 .delbtn'),'display') === 'none',
         css(document.querySelector('#slot-0 .delbtn'),'display'));

      addSlot(); addSlot();
      var slots = document.querySelectorAll('#slots .slot');
      ok('DEL 加满 3 个槽', slots.length === 3, slots.length);
      ok('DEL 多槽时显示删除按钮',
         css(document.querySelector('#slot-0 .delbtn'),'display') !== 'none',
         css(document.querySelector('#slot-0 .delbtn'),'display'));
      ok('DEL 每个槽都有独立删除按钮',
         !!document.getElementById('btn-del-0') && !!document.getElementById('btn-del-1') && !!document.getElementById('btn-del-2'));
      ok('DEL 达到上限后 ＋ 禁用', document.getElementById('btn-add').disabled === true);

      // 删除按钮不能压住日志文字：日志区的右内边距要能容下按钮
      var lb0 = document.getElementById('logbox-0');
      var db0 = document.getElementById('btn-del-0');
      var padR = parseFloat(css(lb0,'paddingRight'));
      var dbW = db0.getBoundingClientRect().width;
      var lbR = lb0.getBoundingClientRect().right;
      var dbL = db0.getBoundingClientRect().left;
      // 文字可用的右边界 = 日志区右边界 - 右内边距；必须在按钮左边之前
      ok('DEL 日志文字右边界在删除按钮左侧（不被遮挡）',
         (lbR - padR) <= dbL + 1,
         'textRight=' + (lbR-padR).toFixed(1) + ' btnLeft=' + dbL.toFixed(1)
         + ' padR=' + padR + ' btnW=' + dbW.toFixed(1));

      // 写入可区分的日志，验证删除后内容不串位
      document.getElementById('logbox-0').innerHTML = '<div class="ln">LOG-ZERO</div>';
      document.getElementById('logbox-1').innerHTML = '<div class="ln">LOG-ONE</div>';
      document.getElementById('logbox-2').innerHTML = '<div class="ln">LOG-TWO</div>';
      document.getElementById('cmd-input-0').value = 'draft-0';
      document.getElementById('cmd-input-1').value = 'draft-1';
      document.getElementById('cmd-input-2').value = 'draft-2';

      // 删中间那个（slot 1）
      delSlot(1);
      var after = document.querySelectorAll('#slots .slot');
      ok('DEL 删除后剩 2 个槽', after.length === 2, after.length);
      ok('DEL 编号重排为 0/1',
         !!document.getElementById('slot-0') && !!document.getElementById('slot-1') && !document.getElementById('slot-2'));
      ok('DEL 前一个槽内容保留',
         document.getElementById('logbox-0').textContent.indexOf('LOG-ZERO') >= 0,
         document.getElementById('logbox-0').textContent);
      ok('DEL 后一个槽内容前移不丢',
         document.getElementById('logbox-1').textContent.indexOf('LOG-TWO') >= 0,
         document.getElementById('logbox-1').textContent);
      ok('DEL 被删的那份日志已消失',
         document.getElementById('slots').textContent.indexOf('LOG-ONE') < 0,
         document.getElementById('slots').textContent);
      ok('DEL 输入框草稿跟着前移',
         document.getElementById('cmd-input-1').value === 'draft-2',
         document.getElementById('cmd-input-1').value);
      ok('DEL ＋ 按钮仍存在（整体重建没丢）', !!document.getElementById('btn-add'));
      ok('DEL 删除后 ＋ 恢复可用', document.getElementById('btn-add').disabled === false);

      // 删首槽：验证 ＋ 不会跟着消失
      delSlot(0);
      ok('DEL 删首槽后剩 1 个', document.querySelectorAll('#slots .slot').length === 1);
      ok('DEL 删首槽后 ＋ 仍在 DOM', !!document.getElementById('btn-add'));
      ok('DEL 只剩 1 个时删除按钮重新隐藏',
         css(document.querySelector('#slot-0 .delbtn'),'display') === 'none',
         css(document.querySelector('#slot-0 .delbtn'),'display'));
      ok('DEL 剩 1 个时再删无效',
         (function(){ delSlot(0); return document.querySelectorAll('#slots .slot').length === 1; })());

      // busy 期间禁删
      addSlot();
      _busy[0] = true;
      beginRun({slot:0});
      ok('DEL 执行中删除按钮被禁用',
         document.querySelector('#slot-0 .delbtn').disabled === true);
      var cntBefore = document.querySelectorAll('#slots .slot').length;
      delSlot(1);
      ok('DEL 执行中调用 delSlot 不生效',
         document.querySelectorAll('#slots .slot').length === cntBefore, cntBefore);
      endRun({ok:true, ms:1, slot:0});
      ok('DEL 执行结束后删除按钮恢复',
         document.querySelector('#slot-0 .delbtn').disabled === false);
      ok('DEL _busy 长度始终保持 3', _busy.length === 3, _busy.length);

      // ---------- 需求·补充：语音助手页整体滑动 ----------
      switchTab('quick');
      switchQuickGroup(grpIdx('语音助手'));
      var sc = document.getElementById('quick-scroll');
      ok('SCROLL 存在 quick-scroll 容器', !!sc);
      ok('SCROLL 容器可纵向滚动', css(sc,'overflowY') === 'auto', css(sc,'overflowY'));
      ok('SCROLL vr-panel 在 quick-scroll 内',
         document.getElementById('vr-panel').parentNode === sc,
         document.getElementById('vr-panel').parentNode && document.getElementById('vr-panel').parentNode.className);
      ok('SCROLL quick-grid 在 quick-scroll 内',
         document.getElementById('quick-grid').parentNode === sc,
         document.getElementById('quick-grid').parentNode && document.getElementById('quick-grid').parentNode.className);
      // 【方案 A】输入区不再吸顶 —— 这条断言必须反转。
      // 旧版这里断言 position === 'sticky'，正是因为那条吸顶才导致用户看到
      // "面板钉在顶部不动、卡片只在底部露一点"，被反馈成"输入框不能滑动"。
      ok('SCROLL vr-panel 不吸顶（position 非 sticky）',
         css(document.getElementById('vr-panel'),'position') !== 'sticky',
         css(document.getElementById('vr-panel'),'position'));
      // 关键：滚动容器时面板必须真的跟着上移（这才是用户说的"能滑动"）
      (function(){
        sc.scrollTop = 0;
        var top0 = document.getElementById('vr-panel').getBoundingClientRect().top;
        sc.scrollTop = 120;
        var top1 = document.getElementById('vr-panel').getBoundingClientRect().top;
        var moved = (top0 - top1) > 60;   // 滚了 120px，面板至少要上移一半以上
        ok('SCROLL 滚动时输入区跟着上移（不是钉住的）', moved,
           'top ' + top0.toFixed(1) + ' -> ' + top1.toFixed(1) + ' scrollTop=' + sc.scrollTop);
      })();
      sc.scrollTop = 0;
      ok('SCROLL quick-grid 不再自己滚',
         css(document.getElementById('quick-grid'),'overflowY') !== 'auto',
         css(document.getElementById('quick-grid'),'overflowY'));
      // 面板底部必须落在容器可视范围内（旧实现会被裁掉）
      var pr = document.getElementById('vr-panel').getBoundingClientRect();
      var sr = sc.getBoundingClientRect();
      ok('SCROLL 面板顶部不被裁', pr.top >= sr.top - 1, pr.top.toFixed(1)+' vs '+sr.top.toFixed(1));
      ok('SCROLL 面板宽度不超过容器', pr.width <= sr.width + 1, pr.width+'/'+sr.width);
      // 有内容时容器应可滚动（语音助手组 9 张卡 + 面板 > 视高）
      ok('SCROLL 内容超出时 scrollHeight > clientHeight',
         sc.scrollHeight >= sc.clientHeight, sc.scrollHeight+'/'+sc.clientHeight);

      // 切分组后滚动复位
      sc.scrollTop = 200;
      switchQuickGroup(grpIdx('指令执行'));
      ok('SCROLL 切分组后滚动复位到 0', sc.scrollTop === 0, sc.scrollTop);

      // ---------- 关键：窗口矮的时候面板不能被裁 ----------
      // 用户报的就是这个场景：窗口压矮后 vr-panel 吃掉全部高度、
      // .quick-body 的 overflow:hidden 把发送按钮直接切掉且无处可滚。
      //
      // 【断言收紧】旧版是 `fits || canScroll` —— 只要"能滚"就算通过。
      // 面板 244px / 容器 254px 也 PASS，可卡片区已经被压成 0、什么都看不见，
      // 缺陷正是这样漏过去的。现在改成验"真实可滚到"：
      // 从顶部滚到底，面板必须整体离开可视区（说明它真的跟着滚，而不是钉住）。
      switchQuickGroup(grpIdx('语音助手'));   // 面板显示
      sc.scrollTop = 0;
      var vp = document.getElementById('vr-panel');
      var vr = vp.getBoundingClientRect();
      var cbox = sc.getBoundingClientRect();
      var scrollable = sc.scrollHeight > sc.clientHeight + 1;
      ok('矮窗 容器可滚动（内容高于视区时）',
         scrollable || vr.height <= cbox.height + 1,
         'panel=' + vr.height.toFixed(1) + ' box=' + cbox.height.toFixed(1)
         + ' scrollH=' + sc.scrollHeight + ' clientH=' + sc.clientHeight);

      // 滚到底：面板顶边必须已经滚出容器顶边之上（或面板本来就装得下）
      var vpTopAt0 = vp.getBoundingClientRect().top;
      sc.scrollTop = sc.scrollHeight;
      var vpTopAtEnd = vp.getBoundingClientRect().top;
      ok('矮窗 滚到底后输入区可完全让出可视区（真的能滑走）',
         vpTopAtEnd < cbox.top - 1 || vr.height <= cbox.height + 1,
         'free=' + (vpTopAt0 - vpTopAtEnd).toFixed(1) + ' topEnd=' + vpTopAtEnd.toFixed(1));
      sc.scrollTop = 0;

      // 发送按钮必须是可达的（能滚到它）
      // 注意别用"滚到底"来判断：滚到底时面板已经整个滚出容器，按钮自然也出去了
      // —— 矮窗下 initBottom 超容器 20px，滚到底 endTop 又跑到容器上方 83px，
      // 两个极端都不在容器内，但按钮实际上是随时能看到的。正确做法是
      // scrollIntoView 让浏览器自己滚到"刚好可见"的位置，再量边界。
      var sendBtn = document.getElementById('btn-vr-send');
      sc.scrollTop = 0;
      var br0 = sendBtn.getBoundingClientRect();
      var visibleAtStart = (br0.top >= cbox.top - 1 && br0.bottom <= cbox.bottom + 1);
      var visibleAfterScroll = false;
      if(!visibleAtStart){
        try{ sendBtn.scrollIntoView({block:'nearest'}); }catch(err){ sendBtn.scrollIntoView(false); }
        var brS = sendBtn.getBoundingClientRect();
        visibleAfterScroll = (brS.top >= cbox.top - 1 && brS.bottom <= cbox.bottom + 1);
      }
      ok('矮窗 发送按钮能滚到可见（不会被永久裁掉）',
         visibleAtStart || visibleAfterScroll,
         'initBottom=' + br0.bottom.toFixed(1) + ' box=' + cbox.top.toFixed(1)
         + '..' + cbox.bottom.toFixed(1) + ' afterScroll=' + visibleAfterScroll);
      ok('矮窗 发送按钮在视口内',
         br0.bottom <= window.innerHeight + 1 && br0.top >= 0,
         'btn.bottom=' + br0.bottom.toFixed(1) + ' vh=' + window.innerHeight);
      sc.scrollTop = 0;

      // ---------- 需求·补充：输出框可拖到收起 ----------
      // 用户原话："底部的输出框要可以通过鼠标最小调整到收起"。
      // 旧版做不到：CSS min-height:120px + JS Math.max(120,…) 双重下限。
      // 这里真的派发 mousedown/mousemove/mouseup，走完整的拖拽路径。
      var fbEl = document.getElementById('feedback');
      var rzEl = document.getElementById('fb-resizer');
      var barEl = document.getElementById('fb-collapsed-bar');
      ok('FOLD 折叠栏存在', !!barEl);
      ok('FOLD 拖拽条存在', !!rzEl);
      ok('FOLD 展开后不再是 collapsed 态', !fbEl.classList.contains('collapsed'), fbEl.className);
      ok('FOLD 展开态折叠栏不显示', css(barEl,'display') === 'none', css(barEl,'display'));

      function mouse(type, target, y){
        var e2 = document.createEvent('MouseEvents');
        e2.initMouseEvent(type, true, true, window, 0, 0, 0, 10, y, false,false,false,false,0,null);
        target.dispatchEvent(e2);
      }

      // 先把输出区拖高一点，便于测量
      var h0 = fbEl.offsetHeight;
      mouse('mousedown', rzEl, 400);
      mouse('mousemove', document, 250);   // 向上拖 = 增高
      mouse('mouseup', document, 250);
      var hBig = fbEl.offsetHeight;
      ok('FOLD 向上拖能增高', hBig > h0, h0 + ' -> ' + hBig);

      // 关键用例：一路往下拖到底，必须能收到只剩折叠栏
      mouse('mousedown', rzEl, 300);
      mouse('mousemove', document, 900);   // 大幅向下 = 压到最小
      mouse('mouseup', document, 900);
      var hMin = fbEl.offsetHeight;
      ok('FOLD 拖到底后高度只剩折叠栏（<=40px）', hMin <= 40, hMin);
      ok('FOLD 拖到底后进入收起态', fbEl.classList.contains('collapsed'), fbEl.className);
      ok('FOLD 收起后内容区被隐藏', css(document.getElementById('fb-table'),'display') === 'none',
         css(document.getElementById('fb-table'),'display'));
      ok('FOLD 收起后拖拽条被隐藏', css(rzEl,'display') === 'none', css(rzEl,'display'));
      ok('FOLD 收起后折叠栏可见', css(barEl,'display') === 'flex', css(barEl,'display'));
      ok('FOLD 收起后仍能显示记录条数', barEl.textContent.replace(/\s/g,'').length > 2,
         barEl.textContent);

      // 点折叠栏 → 展开，且还原到收起前的高度（不是回到 40px）
      mouse('mousedown', barEl, 500);
      mouse('mouseup', document, 500);      // 按下未移动 = 点击
      var hOpen = fbEl.offsetHeight;
      ok('FOLD 点折叠栏可展开', !fbEl.classList.contains('collapsed'), fbEl.className);
      ok('FOLD 展开后高度还原（>40px）', hOpen > 40, hOpen);
      ok('FOLD 展开后内容区重新可见', css(document.getElementById('fb-table'),'display') !== 'none',
         css(document.getElementById('fb-table'),'display'));

      // 从收起态直接往上拖 → 一步展开（不用先点一下）
      mouse('mousedown', rzEl, 400);
      mouse('mousemove', document, 900);
      mouse('mouseup', document, 900);
      var hCollapsed2 = fbEl.offsetHeight;
      ok('FOLD 再次收起成功', fbEl.classList.contains('collapsed'), hCollapsed2);
      mouse('mousedown', barEl, 500);
      mouse('mousemove', document, 300);    // 收起态直接上拖
      mouse('mouseup', document, 300);
      ok('FOLD 从收起态直接上拖可一步展开', !fbEl.classList.contains('collapsed'), fbEl.className);
      ok('FOLD 一步展开后高度明显大于折叠栏', fbEl.offsetHeight > 60, fbEl.offsetHeight);

      // 折叠状态不影响新记录落盘（收起时命令仍要有输出）
      fbEl.classList.remove('collapsed');
      fbEl.style.height = '160px';
      var rowsBefore = document.querySelectorAll('#fb-table .fb-row').length;
      addFeed({time:'11:00:00', cmd:'foldtest', ok:true, ms:1, out:[{level:0,text:'FOLD-OK'}]});
      ok('FOLD 收起/展开不影响新记录追加',
         document.querySelectorAll('#fb-table .fb-row').length === rowsBefore + 1,
         rowsBefore);

      // ---------- 需求·补充：新增指令卡片与方控分组 ----------
      switchTab('quick');
      switchQuickGroup(grpIdx('指令执行'));
      var allTxt = document.getElementById('quick-grid').textContent;
      ok('CARD 指令执行组含「导出ANR日志」', allTxt.indexOf('导出ANR日志') >= 0);
      ok('CARD 指令执行组含「导出crash日志」', allTxt.indexOf('导出crash日志') >= 0);
      ok('CARD 指令执行组含「重启车机」', allTxt.indexOf('重启车机') >= 0);
      ok('CARD 指令执行组含「查询星河云环境」', allTxt.indexOf('查询星河云环境') >= 0);
      ok('CARD 指令执行组含「切预发布环境」', allTxt.indexOf('切预发布环境') >= 0);
      ok('CARD 指令执行组含「切现网环境」', allTxt.indexOf('切现网环境') >= 0);
      ok('CARD 指令执行组含「切测试环境」', allTxt.indexOf('切测试环境') >= 0);
      // 2026-11-13：这四张前台相关卡片挪进了「APK管理」分组，卡片下架、命令保留
      ok('CARD 「清理前台应用」已从指令执行组下架',
         allTxt.indexOf('清理前台应用') < 0, allTxt.slice(0, 60));
      ok('CARD 「导出APK」已从采集导出组下架',
         allTxt.indexOf('导出APK') < 0, allTxt.slice(0, 60));

      // 方控独立分组：13 张卡（2026-11-12 新增「强制重启」+ 语音/通话长按 + 星号分左右），分四类小标题
      switchQuickGroup(grpIdx('方控按键'));
      var fkGrid = document.getElementById('quick-grid');
      var fkCards = fkGrid.querySelectorAll('.qcard');
      ok('FK 方控组共 13 张卡', fkCards.length === 13, fkCards.length);
      var fkTxt = fkGrid.textContent;
      ok('FK 有音量控制分类', fkTxt.indexOf('音量控制') >= 0);
      ok('FK 有播放控制分类', fkTxt.indexOf('播放控制') >= 0);
      ok('FK 有功能按键分类', fkTxt.indexOf('功能按键') >= 0);
      ok('FK 有组合键分类', fkTxt.indexOf('组合键') >= 0);
      ok('FK 含音量+', fkTxt.indexOf('音量 +') >= 0);
      ok('FK 含静音', fkTxt.indexOf('静音') >= 0);
      ok('FK 含上一首', fkTxt.indexOf('上一首') >= 0);
      ok('FK 含下一首', fkTxt.indexOf('下一首') >= 0);
      // 星号键分左/右（2026-11-12 逆向 SynTestUtil：leftkey=521 右=rightkey=520）
      ok('FK 含左星号键（521）', fkTxt.indexOf('左星号键') >= 0);
      ok('FK 含右星号键（520）', fkTxt.indexOf('右星号键') >= 0);
      ok('FK 含短按语音', fkTxt.indexOf('短按语音') >= 0);
      ok('FK 含长按语音', fkTxt.indexOf('长按语音') >= 0);
      ok('FK 含短按通话', fkTxt.indexOf('短按通话') >= 0);
      ok('FK 含长按通话', fkTxt.indexOf('长按通话') >= 0);
      ok('FK 不再出现旧名「音源切换」', fkTxt.indexOf('音源切换') < 0);
      ok('FK 含强制重启组合键', fkTxt.indexOf('强制重启') >= 0);
      ok('FK 强制重启说明提到按住', /按住/.test(fkTxt));
      ok('FK 含语音', fkTxt.indexOf('语音') >= 0);
      ok('FK 含通话', fkTxt.indexOf('通话') >= 0);
      ok('FK 卡片自身说明显示键值',
         /inject-key 5\d\d/.test(fkGrid.textContent), fkGrid.textContent.slice(0,120));
      // 方控组不显示语音面板
      ok('FK 方控组不显示语音输入面板',
         css(document.getElementById('vr-panel'),'display') === 'none',
         css(document.getElementById('vr-panel'),'display'));

      // 点第一张方控卡：应走 quick 通道、进反馈区
      var fkFirst = fkCards[0];
      runQuick(0);
      ok('FK 点方控卡后卡片进入 running', fkFirst.classList.contains('running'), fkFirst.className);
      endRun({ok:true, ms:800, feed:{time:'12:00:00', cmd:':fkvolup', ok:true, ms:800}});
      ok('FK 方控卡执行结束后复位', !fkFirst.classList.contains('running'), fkFirst.className);

      // 语音助手组仍然有面板
      switchQuickGroup(grpIdx('语音助手'));
      ok('FK 语音助手组仍显示输入面板',
         css(document.getElementById('vr-panel'),'display') !== 'none',
         css(document.getElementById('vr-panel'),'display'));
      sc.scrollTop = 0;

      // ---------- 手车互联分组（2026-11-12 需求1~4）----------
      var cpIdx = grpIdx('手车互联');
      ok('CP 存在「手车互联」分组', cpIdx >= 0, cpIdx);
      if(cpIdx >= 0){
        switchQuickGroup(cpIdx);
        var cpGrid = document.getElementById('quick-grid');
        var cpCards = cpGrid.querySelectorAll('.qcard');
        var cpTxt = cpGrid.textContent;
        // 2026-11-22（第 12 批需求 4）：补一张「查询se_linux」，16 → 17 张。
        ok('CP 手车互联共 17 张卡', cpCards.length === 17, cpCards.length);
        ok('CP 新增「查询se_linux」卡', cpTxt.indexOf('查询se_linux') >= 0);
        // ---- 2026-11-20 第 5 批需求 1~8：讯飞音频 / SELinux / 拾音 / dump ----
        ok('CP 新增「讯飞音频」分类', cpTxt.indexOf('讯飞音频') >= 0);
        ok('CP 新增「SELinux」分类', cpTxt.indexOf('SELinux') >= 0);
        ok('CP 新增「拾音日志」分类', cpTxt.indexOf('拾音日志') >= 0);
        ok('CP 新增「音频 dump」分类', cpTxt.indexOf('音频 dump') >= 0);
        ok('CP 含导出audio_dsp_hal.config卡', cpTxt.indexOf('导出讯飞audio_dsp_hal.config') >= 0);
        ok('CP 含导出audio.service.rc卡', cpTxt.indexOf('导出讯飞audio.service.rc') >= 0);
        ok('CP 含关闭se_linux卡', cpTxt.indexOf('关闭se_linux') >= 0);
        ok('CP 含打开se_linux卡', cpTxt.indexOf('打开se_linux') >= 0);
        ok('CP 含查找siri拾音日志卡', cpTxt.indexOf('查找siri拾音日志') >= 0);
        ok('CP 含导出拾音日志卡', cpTxt.indexOf('导出拾音日志') >= 0);
        ok('CP 含创建dump卡', cpTxt.indexOf('创建dump') >= 0);
        ok('CP 含导出dump卡', cpTxt.indexOf('导出dump') >= 0);
        // 命令本身不渲染进 DOM（卡片只显示 name + desc），
        // 所以这几条必须查数据源 quickGroups，不能查 innerHTML。
        var cpItems = quickGroups[cpIdx].items;
        var cpCmds = [];
        for(var ci=0; ci<cpItems.length; ci++){ cpCmds.push(cpItems[ci].cmd); }
        var cpCmdStr = cpCmds.join(' | ');
        ok('CP 命令含 :audiohal config', cpCmdStr.indexOf(':audiohal config') >= 0, cpCmdStr);
        ok('CP 命令含 :audiohal rc', cpCmdStr.indexOf(':audiohal rc') >= 0, cpCmdStr);
        ok('CP 命令含 :selinux off', cpCmdStr.indexOf(':selinux off') >= 0, cpCmdStr);
        ok('CP 命令含 :selinux on', cpCmdStr.indexOf(':selinux on') >= 0, cpCmdStr);
        ok('CP 命令含 :md5so', cpCmdStr.indexOf(':md5so') >= 0, cpCmdStr);
        ok('CP 命令含 :md5pull', cpCmdStr.indexOf(':md5pull') >= 0, cpCmdStr);
        ok('CP 命令含 :audiodump', cpCmdStr.indexOf(':audiodump') >= 0, cpCmdStr);
        ok('CP 命令含 :audiodumppull', cpCmdStr.indexOf(':audiodumppull') >= 0, cpCmdStr);
        ok('CP 有 CarPlay 认证分类', cpTxt.indexOf('CarPlay 认证') >= 0);
        ok('CP 有 CarPlay 调试分类', cpTxt.indexOf('CarPlay 调试') >= 0);
        ok('CP 有 HiCar 分类', cpTxt.indexOf('HiCar') >= 0);
        ok('CP 有 hdc 通道分类', cpTxt.indexOf('hdc 通道') >= 0);
        ok('CP 含认证查询卡', cpTxt.indexOf('CarPlay认证-查询') >= 0);
        ok('CP 含认证开启卡', cpTxt.indexOf('CarPlay认证-开启') >= 0);
        ok('CP 含认证关闭卡', cpTxt.indexOf('CarPlay认证-关闭') >= 0);
        ok('CP 含清除HiCar历史设备卡', cpTxt.indexOf('清除HiCar历史设备') >= 0);
        ok('CP 含 hdc 设备列表卡', cpTxt.indexOf('hdc设备列表') >= 0);
        ok('CP carplay 音频导出已迁入', cpTxt.indexOf('导出carplay音频文件') >= 0);
        ok('CP 打开HiCarSDK日志已迁入', cpTxt.indexOf('打开HiCarSDK日志') >= 0);
        ok('CP 说明里出现 CERT 属性名',
           /persist\.connectivityphone\.carplay\.CERT/.test(cpGrid.innerHTML));
        // 命令本身不渲染进 DOM（卡片只显示 name + desc），
        // 所以这几条必须查数据源 quickGroups，不能查 innerHTML。
        var cpItems = quickGroups[cpIdx].items;
        var cpCmds = [];
        for(var ci=0; ci<cpItems.length; ci++){ cpCmds.push(cpItems[ci].cmd); }
        var cpCmdStr = cpCmds.join(' | ');
        ok('CP 开启卡命令带 on 参数', cpCmdStr.indexOf(':carplaycert on') >= 0, cpCmdStr);
        ok('CP 关闭卡命令带 off 参数', cpCmdStr.indexOf(':carplaycert off') >= 0, cpCmdStr);
        ok('CP 查询卡命令是裸 :carplaycert',
           cpCmds.indexOf(':carplaycert') >= 0, cpCmdStr);
        ok('CP 清除卡命令是 hicarclear', cpCmdStr.indexOf(':hicarclear') >= 0, cpCmdStr);
        ok('CP 有 hdc 设备列表命令', cpCmdStr.indexOf(':hdclist') >= 0, cpCmdStr);
        ok('CP 有导出 carplay 命令', cpCmdStr.indexOf(':carplay') >= 0, cpCmdStr);
        ok('CP 有打开 carplay 音频命令', cpCmdStr.indexOf(':carplayon') >= 0, cpCmdStr);
        ok('CP 有打开 HiCarSDK 日志命令', cpCmdStr.indexOf(':hicar') >= 0, cpCmdStr);
        ok('CP 手车互联组不显示语音输入面板',
           css(document.getElementById('vr-panel'),'display') === 'none',
           css(document.getElementById('vr-panel'),'display'));
      }

      // ---------- SynTestUtil 复用（2026-11-15 重构）----------
      // 需求：删除「测试工具箱」独立分组，11 张卡并入「指令执行」并按三类小标题分类；
      //       「网络模拟」按参考图改成参数表单面板（不再渲染 5 张卡）。
      var stIdx = grpIdx('测试工具箱');
      ok('ST 「测试工具箱」独立分组已删除', stIdx < 0, stIdx);
      var ieIdx = grpIdx('指令执行');
      ok('ST 存在「指令执行」分组', ieIdx >= 0, ieIdx);
      if(ieIdx >= 0){
        switchQuickGroup(ieIdx);
        var ieGrid = document.getElementById('quick-grid');
        var ieCmds = [], ieCats = {};
        for(var si=0; si<quickGroups[ieIdx].items.length; si++){
          ieCmds.push(quickGroups[ieIdx].items[si].cmd);
          if(quickGroups[ieIdx].items[si].cat) ieCats[quickGroups[ieIdx].items[si].cat] = 1;
        }
        var stCmdStr = ieCmds.join(' | ');
        ok('ST 11 条 st* 命令已并入指令执行',
           ['stlogall','stsyslog','sttcpdump','stxyon','stxyoff','stvin',
            'stping','stip','stlogset','staccount','stengmode'].every(function(c){
              return stCmdStr.indexOf(c) >= 0;
            }), stCmdStr.slice(-120));
        ok('ST 开启/关闭坐标成对',
           stCmdStr.indexOf('stxyon') >= 0 && stCmdStr.indexOf('stxyoff') >= 0);
        ok('ST 三类小标题齐全（日志与取证/显示与信息/配置入口）',
           !!ieCats['日志与取证'] && !!ieCats['显示与信息'] && !!ieCats['配置入口'],
           Object.keys(ieCats).join('/'));
        // 分类小标题用 .qcat（不含 .qcard），不能打乱 runQuick 的卡片下标
        ok('ST 分类标题不与卡片混用类名',
           ieGrid.querySelectorAll('.qcat').length >= 3 &&
           ieGrid.querySelectorAll('.qcat.qcard').length === 0,
           ieGrid.querySelectorAll('.qcat').length);
        ok('ST 抓全日志卡片渲染在指令执行组内',
           ieGrid.textContent.indexOf('抓全日志') >= 0);
      }
      // 星河座舱云两条入口（2026-11-19）：必须走 :url（PC 浏览器）而不是设备侧命令
      var wsG = null;
      for (var wi = 0; wi < quickGroups.length; wi++) if (quickGroups[wi].name === '网联服务') wsG = quickGroups[wi];
      var preCard = null, testCard = null;
      if (wsG) for (var ci = 0; ci < wsG.items.length; ci++){
        if (wsG.items[ci].name === '准上线星河座舱云') preCard = wsG.items[ci];
        if (wsG.items[ci].name === '测试星河座舱云') testCard = wsG.items[ci];
      }
      ok('星河座舱云：准上线入口存在且走 :url',
         !!preCard && preCard.cmd.indexOf(':url ') === 0
         && preCard.cmd.indexOf('web-pre.syncore.space') > 0,
         preCard ? preCard.cmd : '没有');
      ok('星河座舱云：测试入口存在且走 :url',
         !!testCard && testCard.cmd.indexOf(':url ') === 0
         && testCard.cmd.indexOf('web-test.syncore.space') > 0,
         testCard ? testCard.cmd : '没有');

      /* ---- 2026-11-20 第 5 批需求 9~14：网联服务新增 PKI / 广汽云 ---- */
      var wsCards = {};
      if (wsG) for (var pk = 0; pk < wsG.items.length; pk++) wsCards[wsG.items[pk].name] = wsG.items[pk];
      ok('WS 含「删除PKI证书」卡且走 :pki del',
         !!wsCards['删除PKI证书'] && wsCards['删除PKI证书'].cmd === ':pki del',
         wsCards['删除PKI证书'] ? wsCards['删除PKI证书'].cmd : '没有');
      ok('WS 含「PKI证书切换预发布」卡且走 :pki pre',
         !!wsCards['PKI证书切换预发布'] && wsCards['PKI证书切换预发布'].cmd === ':pki pre',
         wsCards['PKI证书切换预发布'] ? wsCards['PKI证书切换预发布'].cmd : '没有');
      ok('WS 含「PKI证书切换正式」卡且走 :pki prod',
         !!wsCards['PKI证书切换正式'] && wsCards['PKI证书切换正式'].cmd === ':pki prod',
         wsCards['PKI证书切换正式'] ? wsCards['PKI证书切换正式'].cmd : '没有');
      ok('WS 含切广汽云预发布卡且是 ini 名 gacpre',
         !!wsCards['切广汽云预发布环境'] && wsCards['切广汽云预发布环境'].cmd === 'gacpre',
         wsCards['切广汽云预发布环境'] ? wsCards['切广汽云预发布环境'].cmd : '没有');
      ok('WS 含切广汽云测试卡且是 ini 名 gactest',
         !!wsCards['切广汽云测试环境'] && wsCards['切广汽云测试环境'].cmd === 'gactest',
         wsCards['切广汽云测试环境'] ? wsCards['切广汽云测试环境'].cmd : '没有');
      ok('WS 含查询广汽云环境卡且是 ini 名 gacquery',
         !!wsCards['查询广汽云环境'] && wsCards['查询广汽云环境'].cmd === 'gacquery',
         wsCards['查询广汽云环境'] ? wsCards['查询广汽云环境'].cmd : '没有');

      /* ---- 2026-11-20 第 5 批需求 15：智驾出行分组 ---- */
      var zdIdx = grpIdx('智驾出行');
      ok('ZD 存在「智驾出行」分组', zdIdx >= 0, zdIdx);
      if (zdIdx >= 0){
        switchQuickGroup(zdIdx);
        var zdTxt = document.getElementById('quick-grid').textContent;
        ok('ZD 含「导出高德日志」卡', zdTxt.indexOf('导出高德日志') >= 0);
        var zdItems = quickGroups[zdIdx].items;
        // 2026-11-22（第 14 批）：智驾出行扩到 18 张卡并重排了分组，
        // 不再是"第一张就是导出高德日志"，改成按名字查找。
        var gmItem = null;
        for(var zi=0; zi<zdItems.length; zi++){
          if(zdItems[zi].name === '导出高德日志'){ gmItem = zdItems[zi]; break; }
        }
        ok('ZD 导出高德日志走 :gmqtlog',
           gmItem !== null && gmItem.cmd === ':gmqtlog',
           gmItem ? gmItem.cmd : '没找到该卡');
        ok('ZD 共 18 张卡', zdItems.length === 18, zdItems.length);
      }
      /* ---- 需求 16：改名校验 ---- */
      ok('P16 TBOX 已改名为 Tbox', grpIdx('TBOX') < 0 && grpIdx('Tbox') >= 0);
      ok('P16 APK管理 已改名为 Apk管理', grpIdx('APK管理') < 0 && grpIdx('Apk管理') >= 0);
      ok('P16 自定义 已改名为 自定义指令',
         grpIdx('自定义') < 0 && grpIdx('自定义指令') >= 0);
      ok('P16 分组总数为 11', quickGroups.length === 11, quickGroups.length);

      /* ---- 历史记录（2026-11-19）：持久化 + Win11 边界语义 + 每槽独立 ---- */
      try{
        var i0 = document.getElementById('cmd-input-0');
        var i1 = document.getElementById('cmd-input-1');
        hist.length = 0; histPos = {}; drafts = {};
        histPush('echo A'); histPush('echo B'); histPush('echo B'); histPush('echo C');
        ok('历史去连续重复（A,B,B,C → 3 条）', hist.length === 3, hist.length);
        i0.value = 'echo draft';
        nav(-1, 0);
        ok('上键取到最新一条', i0.value === 'echo C', i0.value);
        nav(-1, 0); nav(-1, 0);
        ok('上键到最旧仍是第一条', i0.value === 'echo A', i0.value);
        nav(-1, 0);
        ok('到最旧停住不越界', i0.value === 'echo A', i0.value);
        nav(1, 0); nav(1, 0);
        ok('下键回到最新', i0.value === 'echo C', i0.value);
        nav(1, 0);
        ok('越过最新还原草稿', i0.value === 'echo draft', i0.value);

        // 每槽独立：槽 1 从最新开始，不影响槽 0
        if(i1){
          i1.value = 'slot1 own';
          nav(-1, 1);
          ok('槽 1 独立翻历史', i1.value === 'echo C', i1.value);
          ok('槽 0 未被槽 1 影响', i0.value === 'echo draft', i0.value);
        }

        // 持久化：写进 localStorage
        histSave();
        var raw2 = localStorage.getItem('adb_hist_v1');
        ok('历史已落 localStorage', !!raw2 && raw2.indexOf('echo A') > 0, raw2 ? raw2.slice(0, 40) : 'null');
        localStorage.removeItem('adb_hist_v1');
        hist.length = 0; histPos = {}; drafts = {};
      }catch(e){ ok('历史记录套件未抛异常', false, String(e)); }

      /* ---- R1（2026-11-19）：无设备时指令入口置灰
         2026-11-20 调整：卡片**不再置灰**（点一下全灰的根因已去掉），
         只保留语音发送按钮的门禁 —— 它没有回执区，点了没反应最难受。 ---- */
      setStatus({dev:'', online:false, rooted:false});
      var sendBtn = document.getElementById('btn-vr-send');
      ok('R1 离线时语音发送置灰', !!sendBtn && sendBtn.disabled === true && sendBtn.classList.contains('is-disabled'));
      ok('R1 置灰带原因', (sendBtn.title || '').indexOf('设备未连接') >= 0, sendBtn.title);
      setStatus({dev:'x', online:true, rooted:true});
      ok('R1 上线后恢复可点', sendBtn.disabled === false && !sendBtn.classList.contains('is-disabled'));

      /* ---- R1b（2026-11-20）：离线时卡片全部可点 ---- */
      (function(){
        setStatus({dev:'', online:false, rooted:false});
        var cards2 = document.querySelectorAll('#quick-grid .qcard');
        var grey = 0;
        for (var ci = 0; ci < cards2.length; ci++) if (cards2[ci].classList.contains('is-disabled')) grey++;
        ok('R1b 离线时卡片不置灰', cards2.length > 0 && grey === 0, grey + '/' + cards2.length);
        // 云平台 H5 卡当然也要可点
        var urlOk = true;
        for (var cj = 0; cj < cards2.length; cj++){
          var nm = cards2[cj].querySelector('.qname');
          if (nm && nm.textContent.indexOf('星河埋点云') >= 0 && cards2[cj].classList.contains('is-disabled')) urlOk = false;
        }
        ok('R1b 离线时 H5 卡可点', urlOk);
        setStatus({dev:'x', online:true, rooted:true});
      })();

      /* ---- R6（2026-11-20）：搜索按 name 去重 ---- */
      (function(){
        var gW = null;
        for (var wi = 0; wi < quickGroups.length; wi++) if (quickGroups[wi].name === '网联服务') gW = quickGroups[wi];
        if (!gW){ ok('R6 网联服务分组存在', false); return; }
        var dup = {name:'打开星河埋点云', desc:'故意重复', cmd:':url https://example.com/dup'};
        gW.items.push(dup);
        _quickFilter = '星河埋点云';
        // 搜索走 window.renderSearchResults（不是 renderQuick）；
        // 条数变了它内部会自动 buildIndex，不用手工重建
        try { window.renderSearchResults(); } catch(e){ ok('R6 渲染未抛异常', false, String(e)); }
        var cards3 = document.querySelectorAll('#quick-grid .qcard');
        var cnt = 0;
        for (var ck = 0; ck < cards3.length; ck++){
          var n3 = cards3[ck].querySelector('.qname');
          if (n3 && n3.textContent.replace(/\s+/g,'') === '打开星河埋点云') cnt++;
        }
        ok('R6 搜索同名指令只出 1 条', cnt === 1, cnt);
        // 浏览态（无过滤）不去重：切到该分组，同名两条都该在
        try { switchQuickGroup(quickGroups.indexOf(gW)); } catch(e){}
        var all = document.querySelectorAll('#quick-grid .qcard'), cnt2 = 0;
        for (var cl = 0; cl < all.length; cl++){
          var n4 = all[cl].querySelector('.qname');
          if (n4 && n4.textContent.replace(/\s+/g,'') === '打开星河埋点云') cnt2++;
        }
        ok('R6 浏览态不去重（同名 2 条都在）', cnt2 === 2, cnt2);
        gW.items.pop();
        try { renderQuickItems(); } catch(e){}
      })();

      /* ---- R2/R5（2026-11-19）：网联服务新增两条卡片 ---- */
      var wsG2 = null;
      for (var wi2 = 0; wi2 < quickGroups.length; wi2++) if (quickGroups[wi2].name === '网联服务') wsG2 = quickGroups[wi2];
      var privCard = null, delCard = null;
      if (wsG2) for (var ci2 = 0; ci2 < wsG2.items.length; ci2++){
        if (wsG2.items[ci2].name === '打开隐私授权') privCard = wsG2.items[ci2];
        if (wsG2.items[ci2].name === '删除代理') delCard = wsG2.items[ci2];
      }
      ok('R5 打开隐私授权卡片存在', !!privCard && privCard.cmd === ':sxlog set',
         privCard ? privCard.cmd : '没有');
      ok('R2 删除代理卡片存在且走 :proxydel', !!delCard && delCard.cmd === ':proxydel',
         delCard ? delCard.cmd : '没有');

      var nsIdx = grpIdx('网络模拟');
      ok('NS 存在「网络模拟」分组', nsIdx >= 0, nsIdx);
      if(nsIdx >= 0){
        ok('NS 是 panel:netsim 表单面板', quickGroups[nsIdx].panel === 'netsim',
           String(quickGroups[nsIdx].panel));
        switchQuickGroup(nsIdx);
        var nsPanel = document.getElementById('netsim-panel');
        var nsGrid = document.getElementById('quick-grid');
        ok('NS 面板可见', !!nsPanel && css(nsPanel,'display') !== 'none',
           nsPanel ? css(nsPanel,'display') : 'missing');
        ok('NS 卡片网格隐藏（不再渲染 5 张卡）',
           css(nsGrid,'display') === 'none' && nsGrid.querySelectorAll('.qcard').length === 0,
           css(nsGrid,'display'));
        ok('NS 表单有预置/速率/延迟/丢包输入',
           !!document.getElementById('ns-preset') &&
           !!document.getElementById('ns-rate-up') &&
           !!document.getElementById('ns-delay-up') &&
           !!document.getElementById('ns-loss-up'));
        ok('NS 表单有配置代理/开启/关闭三按钮',
           nsPanel.querySelectorAll('.ns-acts .btn').length >= 3,
           nsPanel.querySelectorAll('.ns-acts .btn').length);
        ok('NS 有操作记录大输出框', !!document.getElementById('ns-out'));
        /* ---------- T3（2026-11-19）：校验 + 回读复核 + 一键还原 ---------- */
        // 捕获下发的命令（真实 WebView2 里 post 走 chrome.webview）
        // 代理改造后走 postObj（对象消息），两种入口都捕获
        var _nsSent = [];
        var _postBak = window.post;
        var _postObjBak = window.postObj;
        try { window.post = function(kind, data){ _nsSent.push(String(data)); }; } catch (e) {}
        try { window.postObj = function(o){ _nsSent.push(JSON.stringify(o)); }; } catch (e) {}

        ok('T3 有「回读现状」和「一键还原」按钮',
           nsPanel.textContent.indexOf('回读现状') >= 0 && nsPanel.textContent.indexOf('一键还原') >= 0);

        // 越界丢包率：不下发
        _nsSent.length = 0;
        document.getElementById('ns-loss-up').value = '120';
        document.getElementById('ns-delay-up').value = '200';
        document.getElementById('ns-rate-up').value = '512';
        nsRun('wekon');
        ok('T3 丢包率 >100 拒绝下发', _nsSent.length === 0, _nsSent.join('|'));

        // 速率 0：不下发
        _nsSent.length = 0;
        document.getElementById('ns-loss-up').value = '5';
        document.getElementById('ns-rate-up').value = '0';
        nsRun('wekon');
        ok('T3 速率 0 拒绝下发', _nsSent.length === 0, _nsSent.join('|'));

        // 合法参数：启动内置代理（2026-11-19 改向：不再下发 tc）
        _nsSent.length = 0;
        document.getElementById('ns-rate-up').value = '512';
        document.getElementById('ns-rate-down').value = '2048';
        nsRun('wekon');
        ok('T3 合法参数启动内置代理',
           _nsSent.length === 1 && _nsSent[0].indexOf('"kind":"netsimstart"') >= 0,
           _nsSent.join('|'));

        // 代理格式校验：只写端口 → 拒绝
        _nsSent.length = 0;
        document.getElementById('ns-proxy').value = '8888';
        nsRun('proxyon');
        ok('T3 代理只写端口被拒绝', _nsSent.length === 0, _nsSent.join('|'));

        _nsSent.length = 0;
        document.getElementById('ns-proxy').value = '10.41.152.100:8888';
        nsRun('proxyon');
        ok('T3 合法代理下发 stproxyon',
           _nsSent.length === 1 && _nsSent[0] === 'stproxyon 10.41.152.100:8888', _nsSent.join('|'));

        _nsSent.length = 0;
        nsRun('weakreset');
        ok('T3 一键还原停止代理',
           _nsSent.length === 1 && _nsSent[0].indexOf('"kind":"netsimstop"') >= 0,
           _nsSent.join('|'));

        /* T3 续（2026-11-19）：上下行分别生效（对齐逆向里 UPLOAD 与 DOWNLOAD 两套参数） */
        _nsSent.length = 0;
        document.getElementById('ns-rate-up').value = '512';
        document.getElementById('ns-delay-up').value = '200';
        document.getElementById('ns-loss-up').value = '5';
        document.getElementById('ns-rate-down').value = '2048';
        document.getElementById('ns-delay-down').value = '300';
        document.getElementById('ns-loss-down').value = '2';
        nsRun('wekon');
        var startMsg = _nsSent.length ? _nsSent[0] : '';
        ok('T3 上下行参数分别带进代理',
           startMsg.indexOf('"kind":"netsimstart"') >= 0
           && startMsg.indexOf('"upRate":512') > 0
           && startMsg.indexOf('"downRate":2048') > 0
           && startMsg.indexOf('"upDelay":200') > 0
           && startMsg.indexOf('"downDelay":300') > 0,
           startMsg.slice(0, 160));

        // 预设：上下行值不同（2G 上行 32 / 下行 64）
        var sel = document.getElementById('ns-preset');
        sel.value = '2g';
        nsApplyPreset();
        ok('T3 预设 2G 上下行取值不同',
           document.getElementById('ns-rate-up').value === '32'
           && document.getElementById('ns-rate-down').value === '64',
           document.getElementById('ns-rate-up').value + '/' + document.getElementById('ns-rate-down').value);
        ok('T3 预设回显区分上下行',
           document.getElementById('ns-out').textContent.indexOf('上行') >= 0
           && document.getElementById('ns-out').textContent.indexOf('下行') >= 0);

        // 下行命令拼装口径与上行一致
        var downCmd = nsWeakCmdDown({delay:'300', loss:'2', rate:'2048'});
        ok('T3 下行命令走 stweakdown 且参数齐全',
           downCmd.indexOf('stweakdown ') === 0
           && downCmd.indexOf('300ms') > 0
           && downCmd.indexOf('2%') > 0
           && downCmd.indexOf('2048kbit') > 0, downCmd);

        try { window.post = _postBak; } catch (e) {}
        try { window.postObj = _postObjBak; } catch (e) {}
        // 还原输入，避免影响后续断言
        document.getElementById('ns-loss-up').value = '';
        document.getElementById('ns-delay-up').value = '';
        document.getElementById('ns-rate-up').value = '';
        document.getElementById('ns-proxy').value = '';
        ok('NS 5 条命令仍保留供搜索命中',
           quickGroups[nsIdx].items.length === 5, quickGroups[nsIdx].items.length);
        var nsCmdStr = quickGroups[nsIdx].items.map(function(it){ return it.cmd; }).join(' | ');
        ok('NS 代理三件套 + 弱网开关齐全',
           nsCmdStr.indexOf('stproxyget') >= 0 &&
           nsCmdStr.indexOf('stproxyon') >= 0 &&
           nsCmdStr.indexOf('stproxyoff') >= 0 &&
           nsCmdStr.indexOf('stweak') >= 0 &&
           nsCmdStr.indexOf('stweakoff') >= 0, nsCmdStr);
        // 纯函数打靶：表单参数 → stweak 命令（上行优先）
        ok('NS nsWeakCmd 折命令正确',
           typeof nsWeakCmd === 'function' &&
           nsWeakCmd({delay:'200', loss:'5', rate:'512'}) === 'stweak 200ms 5% 512kbit',
           typeof nsWeakCmd === 'function' ? nsWeakCmd({delay:'200', loss:'5', rate:'512'}) : 'no-fn');
        ok('NS 空参数给合法默认',
           typeof nsWeakCmd === 'function' && nsWeakCmd({}) === 'stweak 0ms 0% 100000kbit');
      }

      // 原「指令执行」组不应再残留 carplay/hicar 卡片（避免两处重复）
      switchQuickGroup(grpIdx('指令执行'));
      var ieTxt = document.getElementById('quick-grid').textContent;
      ok('CP 指令执行组已无 carplay 音频导出',
         ieTxt.indexOf('导出carplay音频文件') < 0);
      ok('CP 指令执行组已无 HiCarSDK 日志',
         ieTxt.indexOf('打开HiCarSDK日志') < 0);
      ok('CP 指令执行组已无打开carplay音频',
         ieTxt.indexOf('打开carplay音频') < 0);
      sc.scrollTop = 0;

      /* ---------- T10（2026-11-19）：输入条 5 行自适应 ---------- */
      switchTab('cmd');
      var ta = document.getElementById('cmd-input-0');
      if(!ta){
        ok('T10 指令输入框存在', false, '找不到 #cmd-input-0');
      } else {
        var lh = parseFloat(css(ta, 'lineHeight')) || 20;
        var maxH = parseFloat(css(ta, 'maxHeight')) || (lh * 5);
        var h0 = ta.offsetHeight;

        ta.value = 'line1';
        txAutoGrow(0);
        var h1 = ta.offsetHeight;
        ok('T10 单行时高度约一行', h1 < lh * 2, 'h=' + h1 + ' lh=' + lh);

        ta.value = '1\n2\n3\n4\n5';
        txAutoGrow(0);
        var h5 = ta.offsetHeight;
        ok('T10 五行时输入框变高', h5 > h1 + lh * 2, 'h1=' + h1 + ' h5=' + h5);
        ok('T10 五行时不超过 5 行上限', h5 <= maxH + 2, 'h5=' + h5 + ' max=' + maxH);

        ta.value = '1\n2\n3\n4\n5\n6\n7\n8\n9\n10';
        txAutoGrow(0);
        var h10 = ta.offsetHeight;
        ok('T10 十行时封顶在 5 行并内部滚动',
           h10 <= maxH + 2 && css(ta, 'overflowY') === 'auto',
           'h10=' + h10 + ' max=' + maxH + ' overflow=' + css(ta, 'overflowY'));

        // 容器不能被裁：.field 原来是死高 32px
        var field = ta.closest('.field');
        ok('T10 容器跟着长高（不再是死高）',
           field && field.offsetHeight >= h5 - 2, field ? 'field=' + field.offsetHeight : '无 .field');

        // IME 组字期间不抖：组字中的 input 不应立刻改高度
        ta.value = '';
        txAutoGrow(0);
        var hb = ta.offsetHeight;
        ta.dispatchEvent(new Event('compositionstart'));
        ta.value = 'nihao';
        txAutoGrow(0);
        ok('T10 组字期间不改高度（防抖）', ta.offsetHeight === hb, 'before=' + hb + ' during=' + ta.offsetHeight);
        ta.dispatchEvent(new Event('compositionend'));
        ok('T10 组字结束后补算高度', ta.offsetHeight >= hb, 'after=' + ta.offsetHeight);

        // 清空后收回单行
        ta.value = '1\n2\n3';
        txAutoGrow(0);
        ta.value = '';
        txAutoGrow(0);
        ok('T10 清空后高度收回单行', ta.offsetHeight < lh * 2, 'h=' + ta.offsetHeight);
      }

      /* ---------- T12（2026-11-19）：提示符口径 ---------- */
      var inPmt = document.querySelector('#page-cmd .inputbar .field .pmt');
      ok('T12 输入框提示符只显示 >', inPmt && inPmt.textContent.trim() === '>',
         inPmt ? inPmt.textContent : '无');
      // 这一段只验"提示符怎么分派"，不验状态链路：把会去连设备拉列表的
      // fsOnDeviceOnline 临时屏蔽掉，避免测试依赖车机、也避免把取值窗口顶穿。
      var __fsBak = window.fsOnDeviceOnline;
      try { window.fsOnDeviceOnline = function () {}; } catch (e) {}
      setStatus({dev:'b09acfa2', online:true, dir:'/sdcard/Download', soc:'8295',
                 res:'1920x1080', rooted:true, msg:'ok'});
      try { window.fsOnDeviceOnline = __fsBak; } catch (e) {}
      var inPmt2 = document.querySelector('#page-cmd .inputbar .field .pmt');
      ok('T12 有目录/设备号时输入框仍只显示 >',
         inPmt2 && inPmt2.textContent.trim() === '>', inPmt2 ? inPmt2.textContent : '无');
      ok('T12 回显提示符保留设备号与目录',
         curPmt().indexOf('b09acfa2') >= 0 && curPmt().indexOf('/sdcard/Download') >= 0,
         curPmt());

      /* ---------- T13（2026-11-19）：文件名单行省略 ----------
         不去 switchTab('file')：那会真的向设备拉文件列表，测试变成"要插着车机"，
         而且慢到能把 --uitest 的取值窗口顶穿。这里用 DOM 副本量计算样式即可 ——
         CSS 规则命中与是否可见无关。 */
      var probe = document.createElement('div');
      probe.className = 'fs-row';
      probe.innerHTML = '<div class="n"><span class="t">a-very-long-file-name.apk</span></div>';
      probe.style.cssText = 'position:absolute;left:-9999px;top:0;width:120px;';
      document.body.appendChild(probe);
      var fn = probe.querySelector('.n .t');
      ok('T13 文件名单行省略（nowrap + ellipsis）',
         css(fn, 'whiteSpace') === 'nowrap' && css(fn, 'textOverflow') === 'ellipsis',
         css(fn, 'whiteSpace') + '/' + css(fn, 'textOverflow'));

      var qprobe = document.createElement('div');
      qprobe.className = 'qcard';
      qprobe.innerHTML = '<div class="qname">一条很长很长的快捷指令名称，应当允许换行不截断</div>';
      qprobe.style.cssText = 'position:absolute;left:-9999px;top:0;width:120px;';
      document.body.appendChild(qprobe);
      var qn = qprobe.querySelector('.qname');
      // 2026-11-25：需求变更 —— 卡片名改为单行省略（超长显示 ...），不再允许换行
      ok('T13 卡片名单行省略（不换行）', css(qn, 'whiteSpace') === 'nowrap', css(qn, 'whiteSpace'));
      probe.parentNode.removeChild(probe);
      qprobe.parentNode.removeChild(qprobe);

    }catch(e){

      R.push('FAIL | 测试脚本异常 | ' + e.message + ' @ ' + (e.stack||'').split('\n')[1]);
    }

    var pre = document.createElement('pre');
    pre.id = 'RESULT';
    pre.textContent = R.join('\n');
    document.body.appendChild(pre);
  }

  /* 2026-11-18：等页面进入稳态再量。
     页面启动后约 1.6s，.frame 的 opacity/visibility 过渡才走完（此前
     getAnimations() 里 3 个 fill:backwards 的 CSSTransition 卡在 currentTime=0，
     把 .frame 钉在 opacity:0/visibility:hidden）。原实现在 250ms 就开测，量到的是
     过渡中的隐藏态 —— 而断言本意都是稳态。改成等稳态，**断言一行未改**。 */
  (function(){
    var t0 = Date.now();
    (function waitSteady(){
      var fr = document.getElementById('frame');
      var ok = fr && fr.classList.contains('show') &&
               getComputedStyle(fr).opacity === '1';
      if (ok || Date.now() - t0 > 6000) { run(); return; }
      setTimeout(waitSteady, 50);
    })();
  })();
})();
</script>
"""


def main():
    # 窗口尺寸可用参数覆盖：矮窗（如 1100x600）是用户报缺陷的场景，
    # 默认 760 高看不出面板被裁，必须专门再跑一遍矮窗。
    win = os.environ.get("UI_WIN", "1100,760")
    src = open(UI, encoding="utf-8").read()
    os.makedirs(os.path.dirname(TEST), exist_ok=True)
    # 必须在 </body> 前注入，保证依赖的 ui.html 原生函数已定义
    out = src.replace("</body>", BEHAVIOR + "</body>")
    # 隐藏加载层之外的干扰：不需要，测试脚本自己会 setStatus
    open(TEST, "w", encoding="utf-8").write(out)

    url = "file:///" + TEST.replace("\\", "/")
    # 测量通道（2026-11-22 实测后调整默认值）：
    #   默认 headless Edge —— 实测与真实 WebView2 **断言结果逐条一致**（277/277），
    #   但耗时稳定在 4.5s，而真实 WebView2 在 10~50s 之间剧烈抖动（同一代码两次跑
    #   差 5 倍），且抖动不带来任何额外检出能力。这是常规档最大的耗时来源。
    #   需要"完全等同线上渲染器"时，用 UI_CHANNEL=wv2 切回真实 WebView2。
    dom = None
    _chan = os.environ.get("UI_CHANNEL", "headless")
    if _chan == "wv2" and _wv2 is not None and _wv2.find_exe():
        dom = _wv2.dump_dom(TEST, wait_ms=2200)
        if not re.search(r'<pre id="RESULT">', dom):
            dom = None
    if dom is None:
        cmd = [
            EDGE, "--headless=new", "--disable-gpu",
            "--window-size=" + win, "--no-first-run", "--no-default-browser-check",
            "--disable-background-networking", "--disable-sync", "--disable-extensions",
            "--disable-component-update",
            "--virtual-time-budget=5000",
            "--dump-dom",
            "--user-data-dir=" + PROF,
            url,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=90)
        dom = r.stdout or ""
    # 假绿防线：页面根本没产出 RESULT（脚本异常/加载失败）时必须判失败，
    # 否则下面按行统计会把空结果算成"全部通过"。
    if "__NO_RESULT__" in dom:
        print("  页面没有产出 RESULT（脚本异常或加载失败）")
        return 1
    m = re.search(r'<pre id="RESULT">(.*?)</pre>', dom, re.S)
    if not m:
        print("没拿到 RESULT，DOM 长度", len(dom))
        print("  浏览器:", EDGE)
        print("  提示：Edge 新版 --dump-dom 可能返回空。可设 UI_BROWSER=<chrome.exe 路径> 切换；")
        print("        或用 --headless=old；确认 msedge --version 是否有输出。")
        print(dom[:800])
        return 1

    lines = [l for l in m.group(1).split("\n") if l.strip()]
    fails = [l for l in lines if l.startswith("FAIL")]
    for l in lines:
        print("  " + l)
    print("")
    print("  窗口 %s：通过 %d / %d" % (win, len(lines) - len(fails), len(lines)))
    if fails:
        print("  有 %d 项失败" % len(fails))
        return 1
    print("  ui.html 交互行为全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
