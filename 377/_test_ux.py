"""交互优化（2026-11-13）的 DOM 行为测试。

覆盖：
  1) 快捷指令搜索（含 Ctrl+K、无结果、清空）
  2) 贴底才跟随 + "↓ 最新"浮标
  3) 顶栏运行 chip（begin/end）
  4) 复制按钮语义（无输入时复制最近输出）
  5) 反馈区 仅失败 / 复制全部 / 清空
  6) 失败自动展开反馈区

运行：python _test_ux.py
"""
import os
import tempfile
import re
import subprocess
import sys

try:
    import _wv2                      # 真实 WebView2 测量通道（同目录）
except Exception:                    # 极端情况（缺文件）下仍能回退 Edge
    _wv2 = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
TEST = os.path.join(ROOT, "377", "test_ux.html")
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
PROF = os.path.join(tempfile.gettempdir(), "edgeprof_ux")
UX = r"""
<script>
(function(){
  var R = [];
  function ok(name, cond, extra){
    R.push((cond ? 'PASS' : 'FAIL') + ' | ' + name + (cond ? '' : ' | ' + (extra===undefined?'':extra)));
  }
  function lines(n, prefix){
    var a = [];
    for(var i=0;i<n;i++) a.push({level:0, src:0, slot:0, text:prefix+i});
    return a;
  }
  function toastText(){
    var t = document.getElementById('toast');
    return t ? t.textContent : '';
  }
  function run(){
    try{
      // 默认页签已改为「指令」（quick），终端页要先切过去才有尺寸，
      // 否则 logbox 是 display:none，滚动/跳转按钮都测不出来。
      switchTab('cmd');
      buildSlots();
      var box = document.getElementById('logbox-0');

      // ---------- 1. 贴底才跟随 ----------
      appendLines(lines(200, 'A'));
      ok('200 行后仍在底部', nearBottom(box, 4), box.scrollTop);
      box.scrollTop = 0;                       // 模拟用户上翻读历史
      appendLines(lines(10, 'B'));
      ok('上翻时新输出不把视口拽回底部', box.scrollTop === 0, box.scrollTop);
      var jb = document.getElementById('jump-0');
      ok('上翻后"↓ 最新"出现', jb && jb.classList.contains('on'));
      jumpLatest(0);
      ok('点"↓ 最新"回到底部', nearBottom(box, 4), box.scrollTop);
      ok('回到底部后浮标消失', !jb.classList.contains('on'));
      appendLines(lines(5, 'C'));
      ok('贴底状态下继续跟随', nearBottom(box, 4), box.scrollTop);

      // ---------- 2. 复制按钮语义 ----------
      var copyBtn = document.getElementById('btn-copy-0');
      updateCopyBtn(0);
      ok('有输出时复制按钮可用', copyBtn && !copyBtn.disabled);
      copyCmd(0);
      ok('复制走"最近一条输出"', toastText().indexOf('最近一条输出') >= 0, toastText());
      var inp = document.getElementById('cmd-input-0');
      inp.value = 'shell test';
      updateCopyBtn(0);
      ok('输入非空时按钮可用', !copyBtn.disabled);
      inp.value = '';

      // ---------- 3. 运行 chip ----------
      beginRun({slot:0});
      var chip = document.getElementById('runchip');
      ok('begin 后 chip 出现', chip.classList.contains('on'));
      endRun({slot:0, ok:true});
      ok('end 后 chip 消失', !chip.classList.contains('on'));

      // ---------- 4. 反馈区操作 ----------
      addFeed({time:'12:00:01', cmd:':ok1', ok:true, ms:5, out:[{level:1,text:'fine'}]});
      addFeed({time:'12:00:02', cmd:':bad', ok:false, ms:7, out:[{level:2,text:'boom'}]});
      addFeed({time:'12:00:03', cmd:':ok2', ok:true, ms:9, out:[]});
      var fb = document.getElementById('feedback');
      toggleFeedErr();
      var okRows = document.querySelectorAll('.fb-row.ok');
      var hidden = 0;
      for(var i=0;i<okRows.length;i++){ if(getComputedStyle(okRows[i]).display === 'none') hidden++; }
      ok('仅失败：成功记录被隐藏', fb.classList.contains('feed-only-err') && hidden === okRows.length,
         hidden + '/' + okRows.length);
      toggleFeedErr();
      ok('再点一次恢复全部', !fb.classList.contains('feed-only-err'));

      copyFeedAll();
      ok('复制全部有反馈', toastText().indexOf('已复制') >= 0, toastText());
      var before = document.querySelectorAll('.fb-row').length;
      clearFeed();
      ok('清空后无记录', before > 0 && document.querySelectorAll('.fb-row').length === 0);

      // ---------- 5. 失败也不自动展开（2026-11-13 用户确认） ----------
      fbSetCollapsed(true);
      ok('反馈区可收起', fb.classList.contains('collapsed'));
      addPendingRow(':fail');
      endRun({slot:0, ok:false, ms:12,
              feed:{time:'12:00:04', cmd:':fail', ok:false, ms:12, out:[{level:2,text:'boom'}]}});
      ok('失败时保持收起', fb.classList.contains('collapsed'), fb.className);
      ok('失败时弹出错误 toast', toastText().indexOf('执行失败') >= 0, toastText());

      // ---------- 6. 搜索 ----------
      switchTab('quick');
      var s = document.getElementById('quick-search');
      s.value = 'carplay';
      onQuickSearch();
      var nameEl = document.getElementById('quick-group-name');
      ok('搜索标题为"搜索结果"', nameEl.textContent === '搜索结果', nameEl.textContent);
      var cards = document.querySelectorAll('#quick-grid .qcard');
      ok('搜索有命中', cards.length > 0, cards.length);
      var allMatch = true;
      for(var c=0;c<cards.length;c++){
        if(cards[c].textContent.toLowerCase().indexOf('carplay') < 0) allMatch = false;
      }
      ok('命中项都与关键词相关', allMatch);

      s.value = 'zzzz不存在';
      onQuickSearch();
      ok('无结果时显示空态', !!document.querySelector('#quick-grid .qempty'));
      s.value = 'carplay';
      onQuickSearch();
      clearQuickSearch();
      ok('清空搜索后回到分组', nameEl.textContent === quickGroups[_quickIdx].name, nameEl.textContent);

      // ---------- 7. Ctrl+K ----------
      switchTab('cmd');
      // headless 里页面本身没有系统焦点，直接断言 document.activeElement 不可靠
      //（focus() 会被浏览器忽略）。这里拦截 focus 调用，验证"快捷键确实去聚焦了"。
      var sEl = document.getElementById('quick-search');
      var focusCalled = false;
      var rawFocus = sEl.focus;
      sEl.focus = function(){ focusCalled = true; try{ rawFocus.call(this); }catch(e){} };
      document.dispatchEvent(new KeyboardEvent('keydown', {key:'k', ctrlKey:true, bubbles:true}));
      ok('Ctrl+K 切到快捷指令页', _tab === 'quick', _tab);
      ok('Ctrl+K 聚焦搜索框', focusCalled);
      sEl.focus = rawFocus;

      // ---------- 8. 「自定义指令」分组：2026-11-14 起固定为空壳 ----------
      // 用户要求把原「自定义命令」改名为「自定义」并清空，作为后续新功能的入口；
      // 2026-11-20（第 5 批需求 16）：再次改名为「自定义指令」。
      // cmds.ini 里的命令仍在终端页可用，不再生成卡片。
      applyServerCommands([
        {cmd:':mycmd', name:'我的命令', desc:'测试用', group:'别名', arg:false},
        {cmd:':argcmd', name:'带参命令', desc:'需要参数', group:'别名', arg:true, usage:'argcmd <值>'},
        {cmd:':shot', name:'重复的截图', desc:'', group:'x', arg:false}
      ]);
      var cg = null;
      for (var gi = 0; gi < quickGroups.length; gi++) {
        if (quickGroups[gi].name === '自定义指令') cg = quickGroups[gi];
      }
      ok('存在「自定义指令」分组', !!cg);
      ok('分组名是「自定义指令」', !!cg && cg.name === '自定义指令', cg ? cg.name : 'none');
      ok('自定义指令分组已清空（cmds.ini 不再生成卡片）', !!cg && cg.items.length === 0,
         cg ? cg.items.length : -1);

      applyServerCommands([
        {cmd:':mycmd', name:'我的命令', desc:'测试用', group:'别名', arg:false},
        {cmd:':argcmd', name:'带参命令', desc:'需要参数', group:'别名', arg:true, usage:'argcmd <值>'}
      ]);
      var cg2 = null;
      for (var gj = 0; gj < quickGroups.length; gj++) {
        if (quickGroups[gj].name === '自定义指令') cg2 = quickGroups[gj];
      }
      ok('重复推送后自定义指令组仍为空', !!cg2 && cg2.items.length === 0,
         cg2 ? cg2.items.length : -1);

      // 文本输入模式（2026-11-14）：命令走 adb shell input text
      var captured = [];
      var rawPost = post;
      post = function(kind, data){ captured.push({kind:kind, data:data}); };
      setVrMode('text');
      var vi = document.getElementById('vr-input');
      vi.value = '打开车窗';
      sendVr();
      post = rawPost;
      var typed = null;
      for (var ci2 = 0; ci2 < captured.length; ci2++) {
        if (captured[ci2].kind === 'cmd') { typed = captured[ci2]; break; }
      }
      ok('文本输入发出 input text 命令',
         !!typed && typed.data.indexOf("shell input text '") === 0, typed && typed.data);
      setVrMode('in');

      // ---------- 9. root 胶囊：已连接 + 已 root 必须显示"已连接" ----------
      var pill = document.getElementById('root-pill');
      setStatus({dev:'b09acfa2', online:true, rooted:null});
      ok('早期状态（rooted 未知）保持可点击',
         !pill.classList.contains('disabled'), pill.className);
      setStatus({dev:'b09acfa2', online:true, rooted:true});
      ok('自动 root 完成后按钮变绿',
         pill.classList.contains('yes') && !pill.classList.contains('no'), pill.className);
      setStatus({dev:'b09acfa2', online:false, rooted:true});
      ok('adbd 重启窗口内不退回未连接',
         pill.classList.contains('yes') && !pill.classList.contains('disabled'), pill.className);
      setStatus({dev:'b09acfa2', online:true, rooted:null});
      ok('后续 rooted=null 不把绿打回红',
         pill.classList.contains('yes'), pill.className);
      setStatus({dev:'', online:false, rooted:false});
      ok('真的没设备才置灰', pill.classList.contains('disabled'), pill.className);
      ok('断开后 root 置灰（不是红色）',
         !pill.classList.contains('yes') && pill.classList.contains('off')
         && !pill.classList.contains('no'), pill.className);
      ok('断开后设备号被清空',
         document.getElementById('dev-id').textContent === '',
         document.getElementById('dev-id').textContent);
      ok('断开后设备灯隐藏',
         document.getElementById('dev-dot').style.display === 'none',
         document.getElementById('dev-dot').style.display);

      // ---------- 7. 输出框默认收起 / 有输出才拉起 ----------
      var fbEl2 = document.getElementById('feedback');
      if(window.fbSetCollapsed) window.fbSetCollapsed(true);
      ok('收起态带 collapsed 类', fbEl2.classList.contains('collapsed'), fbEl2.className);
      ok('收起时只剩一条窄栏', fbEl2.offsetHeight <= 36, fbEl2.offsetHeight);

      _curRowEl = null; _curOutEl = null;
      addPendingRow(':fittest');
      onMessage({data:{kind:'line', level:0, src:1, text:'OUT-FIT-1'}});
      ok('有输出也不自动展开', fbEl2.classList.contains('collapsed'), fbEl2.className);
      ok('展开高度不超过半屏',
         fbEl2.offsetHeight <= Math.round(window.innerHeight * 0.5) + 2,
         fbEl2.offsetHeight + '/' + Math.round(window.innerHeight * 0.5));
      onMessage({data:{kind:'end', ok:true, ms:10,
        feed:{time:'00:00:01', cmd:':fittest', ok:true, ms:10}}});
      ok('结束后仍保持收起', fbEl2.classList.contains('collapsed'), fbEl2.className);

      // 没有输出就不拉起（否则敲一条 ls 也会弹一大块空白）
      if(window.fbSetCollapsed) window.fbSetCollapsed(true);
      _curRowEl = null; _curOutEl = null;
      addPendingRow(':nooutput');
      onMessage({data:{kind:'end', ok:true, ms:5,
        feed:{time:'00:00:02', cmd:':nooutput', ok:true, ms:5}}});
      ok('没有输出时保持收起', fbEl2.classList.contains('collapsed'), fbEl2.className);

      // ---------- 8. 重连后 root 复核（2026-11-13） ----------
      // 现场：自动重连成功了，但 root 胶囊还是红的。
      // 后端修法是在重连后补一次 RootProbe 并推 rootdone；这里验前端收到后会不会变绿。
      var pill2 = document.getElementById('root-pill');
      setStatus({dev:'', online:false, rooted:false});           // 模拟断链：置灰
      ok('断链后 root 是灰的', pill2.classList.contains('off'), pill2.className);
      setStatus({dev:'b09acfa2', online:true, rooted:null});     // 重连，但还没探测
      ok('重连但未探测时不强行判红',
         !pill2.classList.contains('no'), pill2.className);
      onMessage({data:{kind:'rootdone', elevate:false, rooted:true}});
      ok('rootdone(true) 后变绿', pill2.classList.contains('yes'), pill2.className);
      onMessage({data:{kind:'rootdone', elevate:false, rooted:false}});
      ok('rootdone(false) 后变红', pill2.classList.contains('no'), pill2.className);

      // ---------- 9. 切到指令输入页自动聚焦（2026-11-13） ----------
      switchTab('quick');
      ok('切到快捷页时焦点不在命令输入框',
         document.activeElement !== document.getElementById('cmd-input-0'),
         document.activeElement ? document.activeElement.id : 'null');
      switchTab('cmd');
      ok('切回指令输入页输入框自动获得焦点',
         document.activeElement === document.getElementById('cmd-input-0'),
         document.activeElement ? document.activeElement.id : 'null');
      ok('输入框外层有焦点高亮（focus-within 生效）',
         !!document.querySelector('.field:focus-within'),
         'no focus-within');

      // ---------- 10. 日志等级归一化与配色（2026-11-13） ----------
      ok('V 归一化', normLogLevel('V') === 'V', normLogLevel('V'));
      ok('verbose 归一化', normLogLevel('verbose') === 'V', normLogLevel('verbose'));
      ok('数字 4 归一化 I', normLogLevel('4') === 'I', normLogLevel('4'));
      ok('warning 归一化 W', normLogLevel('warning') === 'W', normLogLevel('warning'));
      ok('空值返回空', normLogLevel('') === '');
      ok('无法识别返回空', normLogLevel('xyz') === '', normLogLevel('xyz'));

      var lvColors = [];
      ['V', 'D', 'I', 'W', 'E'].forEach(function(lv){
        setLogLevel(lv);
        var el = document.getElementById('log-lv');
        lvColors.push(getComputedStyle(el).color);
      });
      var uniq = {};
      for(var li = 0; li < lvColors.length; li++) uniq[lvColors[li]] = 1;
      ok('五个等级五种颜色', Object.keys(uniq).length === 5, lvColors.join(' | '));
      setLogLevel('V');
      ok('V 不再是灰色（有明确色相）',
         getComputedStyle(document.getElementById('log-lv')).color !== 'rgb(124, 134, 146)',
         getComputedStyle(document.getElementById('log-lv')).color);

      // 2026-11-15：在线但设备没设 persist.log.tag 时，不再整块隐藏，
      // 而是显示灰色「未设置」占位；只有离线才隐藏。
      (function(){
        var savedOnline = _online;
        var pill = document.getElementById('log-pill');
        var el = document.getElementById('log-lv');
        _online = true;
        setLogLevel('');
        ok('在线但无日志等级时显示（不隐藏）', pill.style.display !== 'none',
           pill.style.display);
        ok('在线但无日志等级时标记 data-lv=none',
           pill.getAttribute('data-lv') === 'none', String(pill.getAttribute('data-lv')));
        ok('在线但无日志等级时文案是「未设置」',
           el.textContent === '未设置', el.textContent);
        _online = false;
        setLogLevel('');
        ok('离线时日志等级徽章才隐藏', pill.style.display === 'none', pill.style.display);
        ok('离线时移除 data-lv', !pill.getAttribute('data-lv'),
           String(pill.getAttribute('data-lv')));
        _online = savedOnline;
        setLogLevel('V');   // 复位，别影响后面的主题断言
      })();

      // ---------- 11. 三套主题（2026-11-14） ----------
      var rootEl = document.documentElement;
      // 2026-11-15 第二轮：顶栏主题按钮收进设置抽屉，控件变成三段式（需求 5）。
      buildThemeSeg();
      var segEl = document.getElementById('set-theme');
      ok('设置里有主题分段控件（3 项）',
         !!segEl && segEl.querySelectorAll('button').length === 3);
      var segIcon = function(name){
        var b = segEl ? segEl.querySelector('button[data-theme="' + name + '"]') : null;
        return b ? b.innerHTML : '';
      };

      applyTheme('dark');
      var cDark = getComputedStyle(document.body).backgroundColor;
      ok('黑夜主题生效', rootEl.dataset.theme === 'dark', rootEl.dataset.theme);
      // 2026-11-15 Apple UI：THEME_ICON 三态改 currentColor 单线，硬编码色全部消灭。
      // 断言从「写死旧色值」改为「形状语义 + 语义色令牌」。
      ok('黑夜图标是月亮（单线 currentColor）',
         segIcon('dark').indexOf('stroke="currentColor"') >= 0 &&
         segIcon('dark').indexOf('<circle') < 0 &&
         segIcon('dark').indexOf('<path') >= 0 &&
         segIcon('dark').indexOf('#3fb99b') < 0,
         segIcon('dark').slice(0, 90));

      toggleTheme();
      var cLight = getComputedStyle(document.body).backgroundColor;
      ok('切到白天', rootEl.dataset.theme === 'light', rootEl.dataset.theme);
      ok('白天图标是太阳（单线 currentColor）',
         segIcon('light').indexOf('<circle') >= 0 &&
         segIcon('light').indexOf('stroke="currentColor"') >= 0 &&
         segIcon('light').indexOf('#e8a33d') < 0,
         segIcon('light').slice(0, 90));

      toggleTheme();
      var cEye = getComputedStyle(document.body).backgroundColor;
      ok('再切到护眼', rootEl.dataset.theme === 'eye', rootEl.dataset.theme);
      ok('护眼图标是眼睛（单线 currentColor）',
         segIcon('eye').indexOf('M2.2 12') >= 0 &&
         segIcon('eye').indexOf('stroke="currentColor"') >= 0 &&
         segIcon('eye').indexOf('#a8761f') < 0,
         segIcon('eye').slice(0, 90));

      toggleTheme();
      ok('第三次切回黑夜', rootEl.dataset.theme === 'dark', rootEl.dataset.theme);
      var allIcons = THEME_ICON.dark + THEME_ICON.light + THEME_ICON.eye;
      ok('三态主题图标零硬编码色、全部 currentColor',
         allIcons.indexOf('#') < 0 && allIcons.split('currentColor').length - 1 === 3,
         allIcons.slice(0, 90));
      ok('三套主题背景色互不相同',
         cDark !== cLight && cLight !== cEye && cDark !== cEye,
         cDark + ' / ' + cLight + ' / ' + cEye);

      onMessage({data: {kind: 'theme', name: 'eye'}});
      ok('收到 theme 消息能切换', rootEl.dataset.theme === 'eye', rootEl.dataset.theme);
      applyTheme('dark');

    }catch(e){
      ok('运行异常', false, e.message);
    }

    var pre = document.createElement('pre');
    pre.id = 'RESULT';
    pre.textContent = R.join('\n');
    document.body.appendChild(pre);
  }
  /* 2026-11-18：页面启动后约 1.6s 才进入稳态（.frame 的 opacity/visibility 过渡
     才走完；之前 getAnimations() 里有 3 个 fill:backwards 的 CSSTransition 卡在
     currentTime=0，把 .frame 钉在 opacity:0/visibility:hidden）。
     本文件原有断言在 300ms 就量，量到的是"过渡中的隐藏态"，与断言本意（稳态）不符：
     实测稳态下三套主题背景色 / 焦点 / winmax 半径全部正常。
     改成等稳态再跑，**断言本身一行未改**。 */
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
    win = os.environ.get("UI_WIN", "1100,760")
    src = open(UI, encoding="utf-8").read()
    open(TEST, "w", encoding="utf-8").write(src.replace("</body>", UX + "</body>"))

    url = "file:///" + TEST.replace("\\", "/")
    # 测量通道：优先**真实 WebView2**（adb_Tool.exe --uitest，同一渲染器 + 真实时钟）。
    # 为什么必须换：headless 的 --virtual-time-budget 会冻结 CSS transition，
    # .frame 的过渡永远停在起始帧，怎么等都等不到稳态（详见 377/_wv2.py 头注释）。
    # 没编译出 exe 时回退到原来的 Edge 路径，保证脚本仍能跑。
    dom = None
    if _wv2 is not None and _wv2.find_exe():
        dom = _wv2.dump_dom(TEST, wait_ms=3500)
        if not re.search(r'<pre id="RESULT">', dom):
            dom = None
    if dom is None:
        cmd = [
            EDGE, "--headless=new", "--disable-gpu",
            "--window-size=" + win,
            "--virtual-time-budget=6000",
            "--dump-dom",
            "--user-data-dir=" + PROF,
            url,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
        dom = r.stdout or ""
    # 假绿防线：页面根本没产出 RESULT（脚本异常/加载失败）时必须判失败，
    # 否则下面按行统计会把空结果算成"全部通过"。
    if "__NO_RESULT__" in dom:
        print("  页面没有产出 RESULT（脚本异常或加载失败）")
        return 1
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
    print("  交互优化：通过 %d / %d" % (len(lines) - len(fails), len(lines)))
    if fails:
        print("  有 %d 项失败" % len(fails))
        return 1
    print("  交互优化行为全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
