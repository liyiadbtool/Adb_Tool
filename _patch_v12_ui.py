# -*- coding: utf-8 -*-
"""
v12 结构补丁：把自绘标题栏 / 设置 / 帮助 / 文本页 / 文件页增强注入 ui.html。
可重复执行（每块都带标记，第二次跑会先剥掉旧块再插）。
"""
import io, os, re, sys

UI = r'C:\Users\李亦\Desktop\Adb_Tool\adb_log_gui\webview2\ui.html'
ROOT = r'C:\Users\李亦\Desktop\Adb_Tool'

s = io.open(UI, encoding='utf-8').read()
orig = s
log = []

def sub1(old, new, tag):
    global s
    assert old in s, '找不到锚点：' + tag
    assert s.count(old) == 1, '锚点不唯一：' + tag
    s = s.replace(old, new, 1)
    log.append(tag)

# ---------------------------------------------------------------- 0. 清理旧注入
for mark in ('/* === V12 LAYER START === */', '/* === V12 FONTS START ==='):
    pass
s = re.sub(r'/\* === V12 LAYER START === \*/.*?/\* === V12 LAYER END === \*/\n', '', s, flags=re.S)
s = re.sub(r'/\* === V12 FONTS START ===.*?/\* === V12 FONTS END === \*/\n', '', s, flags=re.S)
s = re.sub(r'/\* === V12 JS START ===.*?/\* === V12 JS END === \*/\n', '', s, flags=re.S)
# 结构块（标题栏 / 设置 / 帮助 / 文本页）先删掉重插
s = re.sub(r'\n *<!-- V12:TITLEBAR START -->.*?<!-- V12:TITLEBAR END -->', '', s, flags=re.S)
s = re.sub(r'\n *<!-- V12:SETTINGS START -->.*?<!-- V12:SETTINGS END -->', '', s, flags=re.S)

# ---------------------------------------------------------------- 1. 自绘标题栏
TITLEBAR = """
  <!-- V12:TITLEBAR START -->
  <!-- 自绘标题栏（2026-11-15）：系统标题栏在深/浅色下都是纯黑、字体也改不了。
       改成页面内绘制：颜色走主题令牌，字体跟着设置里的全局字体。 -->
  <div class="titlebar" id="titlebar">
    <div class="tb-drag" onmousedown="tbDrag(event)" ondblclick="tbMax()">
      <span class="tb-logo" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><rect x="2.9" y="7.1" width="18.2" height="11.2" rx="3.1"/><path d="M7.5 10.6l3.1 2.2-3.1 2.2"/><path d="M13.4 15h3.2"/></svg>
      </span>
      <span class="tb-name">网联服务_Adb_Tool</span>
      <span class="tb-sub" id="tb-sub"></span>
    </div>
    <div class="tb-btns">
      <button class="tb-btn" id="tb-min" onclick="tbMin()" title="最小化">
        <svg viewBox="0 0 10 10"><path d="M2 5h6"/></svg>
      </button>
      <button class="tb-btn" id="tb-max" onclick="tbMax()" title="最大化">
        <svg class="tb-max-ico" viewBox="0 0 10 10"><rect x="2" y="2" width="6" height="6" rx="1"/></svg>
        <svg class="tb-rest-ico" viewBox="0 0 10 10"><rect x="2" y="3.2" width="4.8" height="4.8" rx="1"/><path d="M3.6 3.2V2h4.4v4.4H6.8"/></svg>
      </button>
      <button class="tb-btn tb-close" id="tb-close" onclick="tbClose()" title="关闭">
        <svg viewBox="0 0 10 10"><path d="M2.4 2.4l5.2 5.2M7.6 2.4L2.4 7.6"/></svg>
      </button>
    </div>
  </div>
  <!-- V12:TITLEBAR END -->"""
sub1('<div class="frame" id="frame">\n', '<div class="frame" id="frame">\n' + TITLEBAR + '\n', '标题栏')

# ---------------------------------------------------------------- 2. 顶栏右侧收敛
i0 = s.index('    <!-- 品牌标识：中控屏 + 终端提示符，与应用图标 / 加载层 / 任务栏同源 -->')
i1 = s.index('  </div>\n\n  <!-- 页签', i0)
old_block = s[i0:i1]
assert 'accent-pop' in old_block, '旧块里应有色板'
# 挖出色板（9 色点要搬进设置）
p0 = old_block.index('      <div class="accent-pop"')
p1 = old_block.index('      </div>\n    </div>', p0) + len('      </div>')
ACCENT_POP = old_block[p0:p1]
assert ACCENT_POP.count('accent-dot') >= 9, '色板不足 9 色'

NEW_RIGHT = """    <span class="tb-sep"></span>
    <!-- 设置入口（2026-11-15）：主题 / 强调色 / 字体 / 使用说明 / 关闭 全部收进来 -->
    <button class="icon-btn set-btn" id="settings-btn" onclick="toggleSettings()"
            title="设置（主题 / 强调色 / 字体 / 关闭）" aria-label="设置" aria-expanded="false">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3.2"/><path d="M19.4 15a1.7 1.7 0 00.3 1.9l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.9-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.9.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.9 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.9l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.9.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.9-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.9V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z"/></svg>
    </button>
"""
s = s[:i0] + NEW_RIGHT + s[i1:]
log.append('顶栏收敛')

# ---------------------------------------------------------------- 3. 页签（图标 + 文本）
old_tabs = """  <div class="tabs">
    <button class="tab active" data-tab="quick" onclick="switchTab('quick')">指令</button>
    <button class="tab" data-tab="cmd" onclick="switchTab('cmd')">终端</button>
    <button class="tab" data-tab="file" onclick="switchTab('file')">文件</button>
    <button class="tab" data-tab="cast" onclick="switchTab('cast')">投屏</button>
    <button class="tab" data-tab="ui" onclick="switchTab('ui')">UI</button>
  </div>"""
new_tabs = """  <div class="tabs">
    <button class="tab active" data-tab="quick" onclick="switchTab('quick')">
      <svg viewBox="0 0 24 24"><path d="M4 6h6.5M4 12h6.5M4 18h6.5"/><path d="M14.5 7.2L18 10.6l-3.5 3.4"/><path d="M14.5 18h5"/></svg><span>指令</span></button>
    <button class="tab" data-tab="cmd" onclick="switchTab('cmd')">
      <svg viewBox="0 0 24 24"><rect x="2.8" y="4.4" width="18.4" height="15.2" rx="3"/><path d="M7 10l2.3 2.1L7 14.2"/><path d="M12.6 14.6h4"/></svg><span>终端</span></button>
    <button class="tab" data-tab="file" onclick="switchTab('file')">
      <svg viewBox="0 0 24 24"><path d="M3.4 7.6a2 2 0 012-2h3.6l2 2.2h7.6a2 2 0 012 2v8.2a2 2 0 01-2 2H5.4a2 2 0 01-2-2z"/></svg><span>文件</span></button>
    <button class="tab" data-tab="cast" onclick="switchTab('cast')">
      <svg viewBox="0 0 24 24"><rect x="2.6" y="4.2" width="18.8" height="12" rx="2.6"/><path d="M9 19.8h6M12 16.2v3.6"/></svg><span>投屏</span></button>
    <button class="tab" data-tab="ui" onclick="switchTab('ui')">
      <svg viewBox="0 0 24 24"><rect x="3.2" y="3.6" width="7.6" height="16.8" rx="2"/><rect x="13.2" y="3.6" width="7.6" height="16.8" rx="2"/></svg><span>UI</span></button>
    <button class="tab" data-tab="text" onclick="switchTab('text')">
      <svg viewBox="0 0 24 24"><path d="M6 3.6h7.4L19 8.8v11.6H6z"/><path d="M13.4 3.6v5.2H19"/><path d="M9 13.2h6.6M9 16.4h4.6"/></svg><span>文本</span></button>
  </div>"""
sub1(old_tabs, new_tabs, '页签图标 + 文本页签')

# ---------------------------------------------------------------- 4. 文本页
PAGE_TEXT = """
    <!-- V12:TEXT START -->
    <div class="page" id="page-text">
      <div class="tx-wrap">
        <div class="tx-bar">
          <div class="tx-grp">
            <button class="tx-btn" onclick="txNew()" title="新建文档（Ctrl+N）">新建</button>
            <button class="tx-btn" onclick="txOpen()" title="打开本地文件（Ctrl+O）">打开</button>
            <button class="tx-btn" onclick="txSave(false)" title="保存（Ctrl+S）">保存</button>
            <button class="tx-btn" onclick="txSave(true)" title="另存为（Ctrl+Shift+S）">另存为</button>
          </div>
          <span class="tx-div"></span>
          <div class="tx-grp">
            <button class="tx-ico" onclick="txUndoRedo('undo')" title="撤销（Ctrl+Z）">↶</button>
            <button class="tx-ico" onclick="txUndoRedo('redo')" title="重做（Ctrl+Y）">↷</button>
          </div>
          <span class="tx-div"></span>
          <div class="tx-grp">
            <button class="tx-btn" onclick="txFindOpen(false)" title="查找（Ctrl+F）">查找</button>
            <button class="tx-btn" onclick="txFindOpen(true)" title="替换（Ctrl+H）">替换</button>
            <button class="tx-btn" onclick="txGoto()" title="跳到指定行（Ctrl+G）">跳行</button>
          </div>
          <span class="tx-div"></span>
          <label class="tx-lbl">编码
            <select id="tx-enc" onchange="txSetEnc(this.value)">
              <option>UTF-8</option><option>UTF-8 BOM</option><option>GBK</option><option>UTF-16 LE</option>
            </select>
          </label>
          <label class="tx-lbl">换行
            <select id="tx-eol" onchange="txSetEol(this.value)">
              <option>CRLF</option><option>LF</option>
            </select>
          </label>
          <button class="tx-btn" id="tx-wrap-btn" onclick="txToggleWrap()" title="长行自动换行">自动换行</button>
          <div class="spacer"></div>
          <div class="tx-zoom">
            <button class="tx-ico" onclick="txZoom(-1)" title="减小字号">A-</button>
            <b id="tx-zoom-val">13</b>
            <button class="tx-ico" onclick="txZoom(1)" title="增大字号">A+</button>
          </div>
        </div>
        <div class="tx-tabs" id="tx-tabs"></div>
        <div class="tx-find" id="tx-find" style="display:none;">
          <input class="tx-find-i" id="tx-find-i" placeholder="查找内容" autocomplete="off"
                 oninput="txFindHighlight()" onkeydown="txFindKey(event)">
          <input class="tx-repl-i" id="tx-repl-i" placeholder="替换为" autocomplete="off"
                 style="display:none;" onkeydown="txFindKey(event)">
          <button class="tx-btn" onclick="txFindNext(1)">下一个</button>
          <button class="tx-btn" onclick="txFindNext(-1)">上一个</button>
          <button class="tx-btn" id="tx-repl-one" onclick="txReplaceOne()" style="display:none;">替换</button>
          <button class="tx-btn" id="tx-repl-all" onclick="txReplaceAll()" style="display:none;">全部替换</button>
          <label class="tx-chk"><input type="checkbox" id="tx-case" onchange="txFindHighlight()"> 区分大小写</label>
          <span class="tx-find-n" id="tx-find-n"></span>
          <button class="tx-ico" onclick="txFindClose()" title="关闭（Esc）">✕</button>
        </div>
        <div class="tx-body nowrap" id="tx-body">
          <div class="tx-gutter" id="tx-gutter">1</div>
          <textarea class="tx-edit" id="tx-edit" spellcheck="false" wrap="off"
                    oninput="txOnInput()" onscroll="txSyncScroll()" onkeydown="txKey(event)"
                    onclick="txSyncCaret()" onkeyup="txSyncCaret()"></textarea>
        </div>
        <div class="tx-status">
          <span id="tx-st-pos">行 1, 列 1</span>
          <span id="tx-st-sel">未选中</span>
          <span id="tx-st-len">长度 0</span>
          <div class="spacer"></div>
          <span id="tx-st-enc">UTF-8</span>
          <span id="tx-st-eol">CRLF</span>
          <span id="tx-st-font">13px</span>
        </div>
      </div>
    </div>
    <!-- V12:TEXT END -->
"""
sub1('\n  </div>\n</div>\n\n<script>', PAGE_TEXT + '\n  </div>\n</div>\n\n<script>', '文本页')

# ---------------------------------------------------------------- 5. 文件页增强
old_cols = '            <div class="fs-cols"><span>名称</span><span>大小</span><span>时间</span></div>'
new_cols = """            <div class="fs-cols">
              <span></span>
              <span class="ct c1">名称</span>
              <span class="ct c2">大小<i class="fs-grip" onmousedown="fsColDown(event,'name')" ondblclick="fsColReset(event)" title="拖动调整列宽 · 双击恢复"></i></span>
              <span class="ct c3">时间<i class="fs-grip" onmousedown="fsColDown(event,'size')" ondblclick="fsColReset(event)" title="拖动调整列宽 · 双击恢复"></i></span>
            </div>"""
assert s.count(old_cols) == 2, 'fs-cols 出现次数不是 2'
s = s.replace(old_cols, new_cols, 2)
log.append('文件页列宽夹子')

sub1('          <div class="fs-mid"><span>⇄</span></div>',
     '          <div class="fs-mid"><button class="fs-swap" id="fs-swap" onclick="fsSwapSides()"'
     ' title="左右换边（设备在左 / 电脑在右）">⇄</button></div>',
     '文件页换边按钮')

# ---------------------------------------------------------------- 6. 结果图空态
sub1('          <img id="ui-result-img" alt="结果图">',
     '          <img id="ui-result-img" alt="" onerror="uiResultImgErr()">',
     '结果图 alt/onerror')
sub1('  if(rim) rim.src = _uiResult;',
     '  if(rim){ rim.src = _uiResult; rim.classList.add("has"); }',
     '结果图显示态')

# ---------------------------------------------------------------- 7. post 支持附加字段
sub1("""function post(kind, data, src, slot){
  var o = { kind:kind, data:data||'' };
  if(src !== undefined && src !== null) o.src = src;
  if(slot !== undefined && slot !== null) o.slot = slot;
  try{ window.chrome.webview.postMessage(o); }catch(e){}
}""",
"""function post(kind, data, src, slot, extra){
  var o = { kind:kind, data:data||'' };
  if(src !== undefined && src !== null) o.src = src;
  if(slot !== undefined && slot !== null) o.slot = slot;
  // 2026-11-15：附加字段（文本编辑器要一次带 path/enc/eol/data 多个值）。
  // 仍然走同一个 postMessage 通道，C# 侧用 GetField 取。
  if(extra) for(var k in extra) if(extra.hasOwnProperty(k)) o[k] = extra[k];
  try{ window.chrome.webview.postMessage(o); }catch(e){}
}""", 'post 附加字段')

# ---------------------------------------------------------------- 8. onMessage 接入
sub1("""function onMessage(ev){
  var msg = ev.data;
  if(!msg || !msg.kind) return;""",
"""function onMessage(ev){
  var msg = ev.data;
  if(!msg || !msg.kind) return;
  // v12：标题栏状态 / 偏好 / 文本编辑器消息先处理（返回 true = 已消费）
  if(typeof v12OnMessage === 'function' && v12OnMessage(msg)) return;""", 'onMessage 接入')

# ---------------------------------------------------------------- 9. 设置 + 帮助 + 缩放热区
SETTINGS = """
<!-- V12:SETTINGS START -->
<!-- 设置抽屉：主题 / 强调色 / 字体 / 帮助 / 关闭（2026-11-15） -->
<div class="set-mask" id="set-mask" style="display:none;" onclick="closeSettings()">
  <div class="set-panel" onclick="event.stopPropagation()">
    <div class="set-head">
      <span class="set-title">设置</span>
      <div class="spacer"></div>
      <button class="icon-btn" onclick="closeSettings()" title="关闭（Esc）">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>
      </button>
    </div>
    <div class="set-body">
      <section class="set-sec">
        <div class="set-h">主题 <span class="set-sub">背景与文字明暗</span></div>
        <div class="set-seg" id="set-theme"></div>
      </section>

      <section class="set-sec">
        <div class="set-h">强调色 <span class="set-sub">按钮 / 进度条 / 选中态</span></div>
        __ACCENT_POP__
      </section>

      <section class="set-sec">
        <div class="set-h">字体 <span class="set-sub">全局生效，含标题栏与帮助</span></div>
        <select class="set-sel" id="set-font" onchange="setFont(this.value)"></select>
        <div class="set-preview" id="set-font-preview">车载语音测试 · Adb_Tool 12345 ABCdef</div>
      </section>

      <section class="set-sec">
        <div class="set-h">帮助</div>
        <button class="set-link" onclick="openHelp()">
          <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M9.6 9.2a2.5 2.5 0 114 2.1c-.9.6-1.6 1.1-1.6 2.2"/><path d="M12 17.2v.1"/></svg>
          <span>使用说明（全部功能逐项说明）</span>
          <span class="arr">›</span>
        </button>
      </section>

      <section class="set-sec">
        <div class="set-h">关于</div>
        <div class="set-about">adb_Tool · 车载语音与功能测试工具</div>
        <div class="set-about dim">v8.3 · 2026-11-15 · 单机本地运行，不上传任何数据</div>
      </section>
    </div>
    <div class="set-foot">
      <button class="btn danger" onclick="appClose()">关闭应用</button>
      <button class="btn" onclick="closeSettings()">完成</button>
    </div>
  </div>
</div>

<!-- 使用说明：左侧目录 + 右侧内容，支持搜索（2026-11-15） -->
<div class="help-mask" id="help-mask" style="display:none;" onclick="closeHelp()">
  <div class="help-box" onclick="event.stopPropagation()">
    <div class="help-head">
      <span class="help-title">使用说明</span>
      <input class="help-search" id="help-search" placeholder="搜索功能 / 命令…" autocomplete="off"
             oninput="helpSearch(this.value)">
      <button class="icon-btn" onclick="closeHelp()" title="关闭（Esc）">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>
      </button>
    </div>
    <div class="help-body">
      <nav class="help-toc" id="help-toc"></nav>
      <div class="help-doc" id="help-doc"></div>
    </div>
  </div>
</div>
<!-- V12:SETTINGS END -->
"""
SUB_DIR = SETTINGS.replace('__ACCENT_POP__', ACCENT_POP)
sub1('\n<script>', '\n' + SUB_DIR + '\n<script>', '设置 + 帮助')

# ---------------------------------------------------------------- 10. 注入 CSS / 字体 / JS
css_lib = io.open(os.path.join(ROOT, '_v12.css'), encoding='utf-8').read()
css_fonts = io.open(os.path.join(ROOT, '_v12_fonts.css'), encoding='utf-8').read()
js = io.open(os.path.join(ROOT, '_v12.js'), encoding='utf-8').read()
sub1('</style>', css_fonts + css_lib + '</style>', 'CSS 注入')
sub1('\n</script>', '\n' + js + '\n</script>', 'JS 注入')

io.open(UI, 'w', encoding='utf-8', newline='').write(s)
print('patched:', ' / '.join(log))
print('size: %.1f KB -> %.1f KB' % (len(orig) / 1024.0, len(s) / 1024.0))
