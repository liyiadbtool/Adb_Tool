/* === V12 JS START ===
   2026-11-15 第二轮需求的行为层。
   约定：所有函数挂在全局，便于 377 下的 DOM 自测直接调用。
   分块：
     §1 自绘标题栏与窗口控制
     §2 设置抽屉（主题 / 强调色 / 字体 / 关闭）
     §3 使用说明（按已实现功能扫描生成）
     §4 文本编辑器
     §5 文件页：左右切换 / 列宽拖拽
     §6 结果图空态
     §7 消息接入
   ========================================================================== */

function $v12(id){ return document.getElementById(id); }

/* ============================ §1 标题栏 ============================ */
function tbDrag(ev){
  if (ev && ev.button !== 0) return;
  // 交给系统做原生拖动：贴边分屏、双击最大化、多屏切换全都免费拿到
  post('windrag', '');
}
function tbMin(){ post('winmin', ''); }
function tbMax(){ post('winmax', ''); }
function tbClose(){ post('winclose', ''); }
function appClose(){
  // 设置里的「关闭应用」：有未保存的文本先问一句
  if (typeof txAnyDirty === 'function' && txAnyDirty()){
    if (!confirm('文本页还有未保存的文件，确定要关闭应用吗？')) return;
  }
  post('winclose', '');
}
function setWinMax(on){
  document.documentElement.setAttribute('data-winmax', on ? '1' : '0');
  var b = $v12('tb-max');
  if (b) b.title = on ? '向下还原' : '最大化';
}
/* 无边框窗口的 8 个缩放热区。
   为什么不用系统 NC 拖拽：FormBorderStyle.None 的窗口没有 WS_THICKFRAME，
   发 WM_NCLBUTTONDOWN + HTLEFT 这类命中码系统不会真的去缩放（实测 delta=0）。
   所以改成页面自己算位移、把目标几何交给 C# 去做 SetWindowPos —— 行为确定、
   可自测，还能顺手把最小尺寸卡住。 */
var _rz = null;
function rzDown(ev, dir){
  if (ev.button !== 0) return;
  ev.preventDefault();
  ev.stopPropagation();
  // 用 movementX/Y 累加而不是 screenX 差值：WebView2 里 screenX 偶尔为 0 或不跟随，
  // 累加 movement 在任何 DPI / 坐标体系下都成立；再乘 devicePixelRatio 换成物理像素
  // （C# 的 Bounds 是物理像素）。
  _rz = { dir: dir, ax: 0, ay: 0, dpr: window.devicePixelRatio || 1 };
  post('winresize2', '', null, null, { dir: dir, dx: 0, dy: 0, reset: 1 });
  document.addEventListener('mousemove', rzMove);
  document.addEventListener('mouseup', rzUp);
  document.body.classList.add('win-resizing');
}
function rzMove(ev){
  if (!_rz) return;
  _rz.ax += (ev.movementX || 0);
  _rz.ay += (ev.movementY || 0);
  post('winresize2', '', null, null, {
    dir: _rz.dir,
    dx: Math.round(_rz.ax * _rz.dpr),
    dy: Math.round(_rz.ay * _rz.dpr),
    reset: 0
  });
}
function rzUp(){
  if (!_rz) return;
  _rz = null;
  document.removeEventListener('mousemove', rzMove);
  document.removeEventListener('mouseup', rzUp);
  document.body.classList.remove('win-resizing');
  post('winresizeend', '');
}
(function installResizeZones(){
  var dirs = ['n', 's', 'w', 'e', 'nw', 'ne', 'sw', 'se'];
  function build(){
    for (var i = 0; i < dirs.length; i++){
      var d = dirs[i];
      var el = document.createElement('div');
      el.className = 'rz rz-' + d;
      el.addEventListener('mousedown', (function (dir) {
        return function (ev) { rzDown(ev, dir); };
      })(d));
      document.body.appendChild(el);
    }
  }
  if (document.body) build();
  else document.addEventListener('DOMContentLoaded', build);
})();

/* ============================ §2 设置 ============================ */
/* 免费字体清单：
   内置两款（OFL 协议，base64 内嵌，离线可用）：
     Inter           —— 拉丁 UI 字体，Apple 系统字的开源替代
     JetBrains Mono  —— 等宽，代码/日志/路径
   系统自带（Windows 10/11 中文版均有）：
     Noto Sans SC / 微软雅黑 / 等线 / 楷体 / 宋体 / 黑体
   想用别的已安装字体：选「自定义」直接填字体名。 */
var FONT_LIST = [
  { id: 'system', name: '系统默认（苹方 / 微软雅黑）',
    ui: '-apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Microsoft YaHei UI",system-ui,sans-serif' },
  { id: 'inter', name: 'Inter（内置 · OFL 开源）',
    ui: '"Inter","Microsoft YaHei UI",system-ui,sans-serif' },
  { id: 'noto', name: 'Noto Sans SC（思源黑体 · 免费）',
    ui: '"Noto Sans SC","Microsoft YaHei UI",system-ui,sans-serif' },
  { id: 'deng', name: '等线 DengXian（Win 自带）',
    ui: '"DengXian","Microsoft YaHei UI",sans-serif' },
  { id: 'kai', name: '楷体 KaiTi（Win 自带）',
    ui: '"KaiTi","Microsoft YaHei UI",serif' },
  { id: 'song', name: '宋体 SimSun（Win 自带）',
    ui: '"SimSun","Microsoft YaHei UI",serif' },
  { id: 'hei', name: '黑体 SimHei（Win 自带）',
    ui: '"SimHei","Microsoft YaHei UI",sans-serif' },
  { id: 'mono-all', name: 'JetBrains Mono（内置 · 全等宽）',
    ui: '"JetBrains Mono","Microsoft YaHei UI",monospace',
    mono: '"JetBrains Mono",Consolas,monospace' },
  { id: 'custom', name: '自定义（填已安装的字体名）', ui: '' }
];
var _prefs = { font: 'system', custom: '' };
var _prefsLoaded = false;

function fontById(id){
  for (var i = 0; i < FONT_LIST.length; i++) if (FONT_LIST[i].id === id) return FONT_LIST[i];
  return FONT_LIST[0];
}
function b64enc(s){
  try { return btoa(unescape(encodeURIComponent(String(s)))); } catch (e) { return ''; }
}
function b64dec(s){
  try { return decodeURIComponent(escape(atob(String(s)))); } catch (e) { return ''; }
}

function applyFont(id, silent){
  var f = fontById(id);
  if (id === 'custom') {
    var fam = (_prefs.custom || '').trim();
    if (fam) f = { id: 'custom', name: fam, ui: '"' + fam.replace(/"/g, '') + '","Microsoft YaHei UI",sans-serif' };
    else { id = 'system'; f = fontById('system'); }
  }
  var r = document.documentElement;
  r.style.setProperty('--font-ui', f.ui);
  if (f.mono) r.style.setProperty('--font-mono', f.mono);
  else r.style.removeProperty('--font-mono');
  r.setAttribute('data-font', id);

  var sel = $v12('set-font');
  if (sel) sel.value = id;
  var pv = $v12('set-font-preview');
  if (pv) pv.textContent = '车载语音测试 · Adb_Tool 12345 ABCdef';
  _prefs.font = id;
  if (!silent) { prefsSave(); toast('字体已切换：' + (id === 'custom' ? _prefs.custom : f.name), 'ok'); }
}

function setFont(id){
  if (id === 'custom') {
    var cur = _prefs.custom || '';
    var v = prompt('输入已安装的字体名（如 HarmonyOS Sans SC / 思源宋体）', cur);
    if (v === null) { var s = $v12('set-font'); if (s) s.value = _prefs.font; return; }
    _prefs.custom = v.trim();
    if (!_prefs.custom) { applyFont('system'); return; }
  }
  applyFont(id);
}

function prefsSave(){
  try { post('prefsave', b64enc(JSON.stringify(_prefs))); } catch (e) {}
}
function prefsApply(b64){
  try {
    var o = JSON.parse(b64dec(b64) || '{}');
    if (o && typeof o === 'object') {
      if (typeof o.font === 'string' && o.font) _prefs.font = o.font;
      if (typeof o.custom === 'string') _prefs.custom = o.custom;
    }
  } catch (e) {}
  _prefsLoaded = true;
  applyFont(_prefs.font, true);
}

function syncThemeSeg(){
  var cur = document.documentElement.dataset.theme || 'dark';
  var box = $v12('set-theme');
  if (!box) return;
  var btns = box.querySelectorAll('button');
  for (var i = 0; i < btns.length; i++)
    btns[i].classList.toggle('on', btns[i].getAttribute('data-theme') === cur);
}
function setThemeByName(name){
  applyTheme(name);
  post('theme', name);
  syncThemeSeg();
}

function buildFontSelect(){
  var sel = $v12('set-font');
  if (!sel || sel.options.length) return;
  var html = '';
  for (var i = 0; i < FONT_LIST.length; i++)
    html += '<option value="' + FONT_LIST[i].id + '">' + escHtml(FONT_LIST[i].name) + '</option>';
  sel.innerHTML = html;
  sel.value = _prefs.font;
}

function openSettings(){
  buildFontSelect();
  buildThemeSeg();
  syncThemeSeg();
  if (typeof applyAccent === 'function')
    applyAccent(document.documentElement.getAttribute('data-accent') || 'blue');
  var m = $v12('set-mask');
  if (m) m.style.display = 'flex';
  var b = $v12('settings-btn');
  if (b) b.classList.add('on');
}
function closeSettings(){
  var m = $v12('set-mask');
  if (m) m.style.display = 'none';
  var b = $v12('settings-btn');
  if (b) b.classList.remove('on');
}
function toggleSettings(){
  var m = $v12('set-mask');
  if (m && m.style.display === 'flex') closeSettings();
  else openSettings();
}

/* ============================ §3 使用说明 ============================ */
function helpCmdCatalog(){
  var out = '';
  try {
    for (var i = 0; i < quickGroups.length; i++){
      var g = quickGroups[i];
      if (!g.items || !g.items.length) continue;
      out += '<h4>' + escHtml(g.name) + ' <span class="cmd-d">（' + g.items.length + ' 条）</span></h4>';
      out += '<table><tr><th style="width:34%">指令</th><th>说明</th></tr>';
      for (var j = 0; j < g.items.length; j++){
        var it = g.items[j];
        out += '<tr><td class="cmd-t">' + escHtml(it.name || '') + '</td><td class="cmd-d">'
             + escHtml(it.desc || '') + '</td></tr>';
      }
      out += '</table>';
    }
  } catch (e) { out += '<p>指令目录读取失败：' + escHtml(e.message) + '</p>'; }
  return out;
}

var HELP_SECS = [
  { id: 'start', title: '1. 快速上手', html:
    '<h3>快速上手</h3>' +
    '<p>这是一个把常用 adb 操作做成按钮的车载测试工具。三步就能跑起来：</p>' +
    '<ol><li>用 USB 线连车机（或点顶栏「无线」填 IP 连接），顶栏出现绿色圆点 + 设备号即就绪。</li>' +
    '<li>到 <span class="hi">指令</span> 页，点任意卡片即可执行；右侧底部是输出区。</li>' +
    '<li>要看原始输出、敲任意命令，切到 <span class="hi">终端</span> 页。</li></ol>' +
    '<p>顶栏左侧四个胶囊是状态：<code>root</code> / <code>无线</code> / <code>日志</code> / 设备号。' +
    '点 root 可一键提权，点无线可切 TCP 连接，点日志显示当前日志等级。</p>' },

  { id: 'top', title: '2. 顶栏与状态灯', html:
    '<h3>顶栏与状态灯</h3>' +
    '<table><tr><th>元素</th><th>含义</th><th>可点吗</th></tr>' +
    '<tr><td><code>root</code></td><td>绿=已 root，红=未 root，灰=离线</td><td>点一下执行 <code>adb root</code> 提权</td></tr>' +
    '<tr><td><code>无线</code></td><td>是否走 TCP 连接</td><td>点开填 IP，留空自动取设备 IP</td></tr>' +
    '<tr><td><code>日志</code></td><td>当前 log 等级 V/D/I/W/E</td><td>只读</td></tr>' +
    '<tr><td>设备号</td><td>序列号 + SoC + 分辨率</td><td>只读</td></tr>' +
    '<tr><td>执行中</td><td>有命令在跑，带计时</td><td>点一下停止</td></tr>' +
    '<tr><td>⚙ 设置</td><td>主题 / 强调色 / 字体 / 关闭</td><td>点开设置抽屉</td></tr></table>' +
    '<p>标题栏右上角是最小化 / 最大化 / 关闭。标题栏空白处可拖动窗口，' +
    '双击最大化，拖到屏幕边缘可分屏 —— 和普通窗口一致。</p>' },

  { id: 'cmd', title: '3. 指令页（全部指令）', html:
    '<h3>指令页</h3>' +
    '<p>左侧分组，右侧卡片。卡片上写的就是它实际执行的 adb 动作，点一下立刻下发。' +
    '左上角搜索框（<kbd>Ctrl</kbd>+<kbd>K</kbd>）可以按名称过滤；带进度条的卡片会实时显示进度。' +
    '执行中的卡片有高亮描边，再点一次可停止（仅部分长任务支持）。</p>' +
    '<p>底部是输出区：只显示失败可勾「仅失败」，可复制全部、清空。</p>' +
    '<h4>内置指令目录（按分组自动生成）</h4>' + helpCmdCatalog() },

  { id: 'term', title: '4. 终端页', html:
    '<h3>终端页</h3>' +
    '<p>输入框敲任意 adb 命令或内置短命令，回车执行。<code>↑</code>/<code>↓</code> 翻历史，' +
    '<kbd>Ctrl</kbd>+<kbd>L</kbd> 清屏。点输入框右侧「＋」可以再开一个输入槽，' +
    '多个槽位互不阻塞（一个在跑长任务时，另一个还能继续敲）。</p>' +
    '<p>支持直接贴 Windows 路径（会走 push），也支持中文指令（如「截图」「导出日志」）。</p>' +
    '<p>输出区按等级着色：V 紫 / D 蓝 / I 绿 / W 橙 / E 红，一眼能扫到错误。</p>' },

  { id: 'file', title: '5. 文件页', html:
    '<h3>文件页</h3>' +
    '<p>左边电脑、右边设备，<span class="hi">把文件从一侧拖到另一侧即可复制</span>（拖到文件夹行上=复制进该目录）。</p>' +
    '<ul><li><b>⇄ 按钮</b>：一键左右换边（设备在左、电脑在右），习惯哪边就是哪边。</li>' +
    '<li><b>列宽</b>：拖动表头「名称 / 大小 / 时间」之间的分隔线调整列宽，双击分隔线恢复默认。</li>' +
    '<li><b>搜索框</b>：每栏独立搜索，Esc 退出搜索。</li>' +
    '<li><b>底部按钮</b>：新建文件夹 / 重命名 / 删除，作用于当前选中项。</li></ul>' +
    '<p>复制过程有进度条，可随时「取消复制」。</p>' },

  { id: 'cast', title: '6. 投屏页', html:
    '<h3>投屏页</h3>' +
    '<p>支持主屏 / 副屏 / 后排放屏 / HUD / PHUD 多路同时投。每块屏可单独「开启」，' +
    '也可「录制」（走 ffmpeg 合成 mp4）、「外部」（用 scrcpy 开独立窗口，最流畅）。</p>' +
    '<ul><li>画面可直接点击（等效触摸设备）。</li>' +
    '<li>第一次用录屏/外部窗口要先指定 ffmpeg / scrcpy 路径，点「选择…」，之后会记住。</li>' +
    '<li>顶部「多屏投屏」标签可最大化某一块屏，再点还原。</li></ul>' +
    '<p>单帧截图有 8 秒超时保护：设备卡住会自动放弃并标记原因，不会把整个工具拖死。</p>' },

  { id: 'ui', title: '7. UI 对比页', html:
    '<h3>UI 对比页</h3>' +
    '<p>把设计稿和实机截图叠在一起比对，全部本地运算，不上传任何图片。</p>' +
    '<ol><li>选「设计图」和「实景图」（PNG/JPG），也可以「直接截图」从设备抓一帧。</li>' +
    '<li>调「透明度」让两层对齐；勾「标记差异」会用红块标出超过阈值的像素。</li>' +
    '<li>「差异阈值」越大越宽松（默认 30 / 255）。</li>' +
    '<li>点「开始对比」生成结果图；「打开结果图」导出 PNG。</li></ol>' +
    '<p>没有结果图时结果区显示空态，不会出现破图。</p>' },

  { id: 'text', title: '8. 文本页', html:
    '<h3>文本页</h3>' +
    '<p>内置一个轻量文本编辑器，用来现场改 ini / 脚本 / json，不用来回切记事本。</p>' +
    '<ul><li><b>多文档</b>：可以同时开多个文件，页签上有圆点=未保存。</li>' +
    '<li><b>打开 / 保存 / 另存为</b>：保留原文件的编码（UTF-8 / UTF-8 BOM / GBK / UTF-16 LE）' +
    '和换行符（CRLF / LF），改 ini 不会把文件改坏。</li>' +
    '<li><b>查找替换</b>：<kbd>Ctrl</kbd>+<kbd>F</kbd> 查找，<kbd>Ctrl</kbd>+<kbd>H</kbd> 替换，可区分大小写、全部替换。</li>' +
    '<li><b>跳行</b>：<kbd>Ctrl</kbd>+<kbd>G</kbd>，输入行号直接定位。</li>' +
    '<li><b>自动换行 / 字号</b>：长行可换行显示，字号可 ±，只影响编辑器。</li>' +
    '<li><b>状态栏</b>：行、列、选中字符数、总长度、编码、换行符。</li></ul>' +
    '<p>单文件上限 2 MB；超出会提示并只载入前 2 MB。</p>' },

  { id: 'custom', title: '9. 自定义指令', html:
    '<h3>自定义指令</h3>' +
    '<p>指令页左侧第 7 组「自定义」，把一串 adb 命令存成一张卡片，一键按顺序执行。</p>' +
    '<h4>新建</h4><p>填名称（必填）、说明（选填，不填就不显示）、命令（支持多行，一行一条）。</p>' +
    '<h4>两个官方节点</h4>' +
    '<ul><li><b>延时</b>：等 N 毫秒（适合「点完等界面刷新」）。</li>' +
    '<li><b>循环</b>：把<b>上一条 adb 命令</b>重复 N 次。</li></ul>' +
    '<h4>三条规则（不满足会当场红字拒绝保存）</h4>' +
    '<ol><li>第一行必须是 adb 命令，不能是节点。</li>' +
    '<li>节点之间必须隔一条 adb 命令（不能连续两个节点）。</li>' +
    '<li>加节点时，它上面那条命令不能是空的。</li></ol>' +
    '<p>执行时某条失败<b>不会中止</b>：跳过它继续跑，失败的原生报错照常进输出区。' +
    '全部跑完弹一条汇总：成功 N / 失败 M。</p>' },

  { id: 'settings', title: '10. 设置', html:
    '<h3>设置</h3>' +
    '<p>右上角齿轮打开。这里集成全部外观项：</p>' +
    '<ul><li><b>主题</b>：黑夜 / 白天 / 护眼。标题栏、顶栏、卡片、弹窗全部跟随（自绘标题栏，不再有黑色边条）。</li>' +
    '<li><b>强调色</b>：红黄蓝白紫黑绿橙粉 9 色，只改按钮 / 进度条 / 滑块 / 选中态，不动背景明暗。</li>' +
    '<li><b>字体</b>：内置 Inter、JetBrains Mono（OFL 开源，离线可用），以及系统自带的黑体、楷体、宋体、等线、' +
    'Noto Sans SC；也可以选「自定义」填任意已安装字体名。<b>全局生效</b>（含标题栏与帮助）。</li>' +
    '<li><b>关闭应用</b>：有未保存文本会先问一句。</li></ul>' +
    '<p>所有偏好写在 exe 同目录的 <code>adb_log_export.ini</code>（<code>theme=</code> <code>accent=</code> <code>prefs=</code>），' +
    '换机器把 ini 一起拷走即可。</p>' },

  { id: 'keys', title: '11. 快捷键', html:
    '<h3>快捷键</h3>' +
    '<table><tr><th>快捷键</th><th>作用</th></tr>' +
    '<tr><td><kbd>Ctrl</kbd>+<kbd>K</kbd></td><td>指令页搜索</td></tr>' +
    '<tr><td><kbd>Ctrl</kbd>+<kbd>L</kbd></td><td>终端清屏</td></tr>' +
    '<tr><td><kbd>↑</kbd>/<kbd>↓</kbd></td><td>终端历史命令</td></tr>' +
    '<tr><td><kbd>Ctrl</kbd>+<kbd>N</kbd></td><td>文本页新建</td></tr>' +
    '<tr><td><kbd>Ctrl</kbd>+<kbd>O</kbd></td><td>文本页打开</td></tr>' +
    '<tr><td><kbd>Ctrl</kbd>+<kbd>S</kbd></td><td>文本页保存</td></tr>' +
    '<tr><td><kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>S</kbd></td><td>文本页另存为</td></tr>' +
    '<tr><td><kbd>Ctrl</kbd>+<kbd>F</kbd> / <kbd>Ctrl</kbd>+<kbd>H</kbd></td><td>查找 / 替换</td></tr>' +
    '<tr><td><kbd>Ctrl</kbd>+<kbd>G</kbd></td><td>跳行</td></tr>' +
    '<tr><td><kbd>Tab</kbd></td><td>文本页插入 4 个空格</td></tr>' +
    '<tr><td><kbd>Esc</kbd></td><td>关闭弹层 / 搜索 / 帮助</td></tr></table>' },

  { id: 'faq', title: '12. 常见问题', html:
    '<h3>常见问题</h3>' +
    '<h4>顶栏一直是灰色「未连接」</h4>' +
    '<p>先看设备管理器有没有 ADB 接口；换线换口；终端页敲 <code>adb devices</code> 看是否 unauthorized（车机上点允许）。' +
    '无线连接需与车机同一网段。</p>' +
    '<h4>投屏黑屏 / 转圈</h4>' +
    '<p>多半是另一个 adb 进程占着设备，或画面编码器被别的投屏工具占用。先关掉 scrcpy / Android Studio 的投屏再试。</p>' +
    '<h4>「未找到 ffmpeg / scrcpy」</h4>' +
    '<p>它们只用于录屏/外部窗口，点「选择…」指到 exe 即可；也可以点「重新查找」自动扫常见目录。' +
    '不装也不影响截图、指令、文件这些主功能。</p>' +
    '<h4>改了 ini 里的字体/主题没生效</h4>' +
    '<p>主题与强调色即时生效；字体在设置里选。若手改 ini，重启工具即可。</p>' +
    '<h4>窗口最大化后盖住任务栏？</h4>' +
    '<p>已按工作区限制，不会盖任务栏。若出现，双击标题栏还原再最大化一次。</p>' }
];

function helpRender(){
  var toc = $v12('help-toc'), doc = $v12('help-doc');
  if (!toc || !doc) return;
  var th = '', dh = '';
  for (var i = 0; i < HELP_SECS.length; i++){
    var s = HELP_SECS[i];
    th += '<button data-sec="' + s.id + '" onclick="helpGo(\'' + s.id + '\')">'
        + escHtml(s.title) + '</button>';
    dh += '<div class="sec' + (i === 0 ? ' on' : '') + '" id="help-sec-' + s.id + '">' + s.html + '</div>';
  }
  toc.innerHTML = th;
  doc.innerHTML = dh;
  helpGo(HELP_SECS[0].id);
}
function helpGo(id){
  var doc = $v12('help-doc');
  if (!doc) return;
  var secs = doc.querySelectorAll('.sec');
  for (var i = 0; i < secs.length; i++) secs[i].classList.toggle('on', secs[i].id === 'help-sec-' + id);
  var btns = $v12('help-toc').querySelectorAll('button');
  for (var j = 0; j < btns.length; j++) btns[j].classList.toggle('on', btns[j].getAttribute('data-sec') === id);
  doc.scrollTop = 0;
}
function openHelp(){
  closeSettings();
  helpRender();
  var m = $v12('help-mask');
  if (m) m.style.display = 'flex';
}
function closeHelp(){
  var m = $v12('help-mask');
  if (m) m.style.display = 'none';
  var s = $v12('help-search');
  if (s) s.value = '';
  helpSearch('');
}
/* 搜索：命中标题或正文就保留该节，并把第一节滚到视野里 */
function helpSearch(q){
  q = String(q || '').trim().toLowerCase();
  var toc = $v12('help-toc'), doc = $v12('help-doc');
  if (!toc || !doc) return;
  var secs = doc.querySelectorAll('.sec');
  var btns = toc.querySelectorAll('button');
  var first = null;
  for (var i = 0; i < secs.length; i++){
    var hit = !q || secs[i].textContent.toLowerCase().indexOf(q) >= 0;
    if (btns[i]) btns[i].style.display = hit ? '' : 'none';
    if (!hit) secs[i].classList.remove('on');
    if (hit && !first) first = secs[i].id.replace('help-sec-', '');
  }
  if (q && first) helpGo(first);
  else if (!q) helpGo(HELP_SECS[0].id);
}

/* ============================ §4 文本编辑器 ============================ */
var TX_DOCS = [];
var _txSeq = 1;
var _txCur = -1;
var _txFontSize = 13;
var _txWrap = false;
var _txTimer = null;
var _txLastFind = '';

function txDoc(){ return (_txCur >= 0 && _txCur < TX_DOCS.length) ? TX_DOCS[_txCur] : null; }
function txEl(){ return $v12('tx-edit'); }

function txActivate(){
  if (!TX_DOCS.length) txNew();
  else txSelect(_txCur < 0 ? 0 : _txCur);
  var ta = txEl();
  if (ta) { try { ta.focus({ preventScroll: true }); } catch (e) {} }
}

function txNew(name){
  var d = {
    id: ++_txSeq, name: name || ('未命名-' + TX_DOCS.length + '.txt'),
    path: '', enc: 'UTF-8', eol: 'CRLF', dirty: false, text: '',
    sel: [0, 0], scroll: 0
  };
  TX_DOCS.push(d);
  _txCur = TX_DOCS.length - 1;
  txRenderTabs();
  txLoad();
  return d;
}

function txLoad(){
  var d = txDoc(), ta = txEl();
  if (!d || !ta) return;
  ta.value = d.text;
  ta.scrollTop = d.scroll || 0;
  txGutter();
  txStatus();
  txSyncScroll();
  var enc = $v12('tx-enc'); if (enc) enc.value = d.enc;
  var eol = $v12('tx-eol'); if (eol) eol.value = d.eol;
  try { ta.setSelectionRange(d.sel[0], d.sel[1]); } catch (e) {}
}

function txRenderTabs(){
  var box = $v12('tx-tabs');
  if (!box) return;
  var html = '';
  for (var i = 0; i < TX_DOCS.length; i++){
    var d = TX_DOCS[i];
    html += '<button class="tx-tab' + (i === _txCur ? ' on' : '') + '" onclick="txSelect(' + i + ')"'
          + ' title="' + escHtml(d.path || d.name) + '">'
          + '<span class="nm">' + escHtml(d.name) + '</span>'
          + (d.dirty ? '<span class="dt"></span>' : '')
          + '<span class="x" onclick="txClose(event,' + i + ')" title="关闭">✕</span>'
          + '</button>';
  }
  box.innerHTML = html;
}

function txSelect(i){
  var cur = txDoc();
  if (cur) { cur.text = txEl().value; cur.scroll = txEl().scrollTop; }
  if (i < 0 || i >= TX_DOCS.length) return;
  _txCur = i;
  txRenderTabs();
  txLoad();
}

function txClose(ev, i){
  if (ev) ev.stopPropagation();
  var d = TX_DOCS[i];
  if (!d) return;
  if (d.dirty && !confirm('「' + d.name + '」还有未保存的修改，仍然关闭吗？')) return;
  TX_DOCS.splice(i, 1);
  if (_txCur >= TX_DOCS.length) _txCur = TX_DOCS.length - 1;
  if (!TX_DOCS.length) { txNew(); return; }
  txRenderTabs();
  txLoad();
}

function txAnyDirty(){
  for (var i = 0; i < TX_DOCS.length; i++){
    var d = TX_DOCS[i];
    var t = (i === _txCur && txEl()) ? txEl().value : d.text;
    if (d.dirty && t.length) return true;
  }
  return false;
}

function txOnInput(){
  var d = txDoc(), ta = txEl();
  if (!d || !ta) return;
  if (!d.dirty) { d.dirty = true; txRenderTabs(); }
  d.text = ta.value;
  txGutter();
  txStatus();
  txSyncScroll();
}
function txSyncScroll(){
  var ta = txEl(), g = $v12('tx-gutter');
  if (ta && g) g.scrollTop = ta.scrollTop;
}
function txGutter(){
  var ta = txEl(), g = $v12('tx-gutter');
  if (!ta || !g) return;
  if (_txWrap) { g.textContent = ''; return; }
  var n = ta.value.split('\n').length;
  if (n < 1) n = 1;
  var arr = new Array(n);
  for (var i = 1; i <= n; i++) arr[i - 1] = i;
  g.textContent = arr.join('\n');
}
function txStatus(){
  var d = txDoc(), ta = txEl();
  if (!d || !ta) return;
  var v = ta.value, s = ta.selectionStart, e = ta.selectionEnd;
  var before = v.slice(0, s);
  var ln = before.split('\n').length;
  var col = s - before.lastIndexOf('\n');
  var set = function (id, txt){ var el = $v12(id); if (el) el.textContent = txt; };
  set('tx-st-pos', '行 ' + ln + ', 列 ' + col);
  set('tx-st-sel', (e > s) ? ('选中 ' + (e - s)) : '未选中');
  set('tx-st-len', '长度 ' + v.length);
  set('tx-st-enc', d.enc);
  set('tx-st-eol', d.eol);
  set('tx-st-font', _txFontSize + 'px');
}
function txSyncCaret(){ txStatus(); }

function txKey(ev){
  if (ev.key === 'Tab' && !ev.ctrlKey && !ev.altKey){
    ev.preventDefault();
    var ta = txEl();
    var s = ta.selectionStart, e = ta.selectionEnd;
    var ins = '    ';
    ta.value = ta.value.slice(0, s) + ins + ta.value.slice(e);
    ta.setSelectionRange(s + ins.length, s + ins.length);
    txOnInput();
    return;
  }
  if (ev.ctrlKey && !ev.shiftKey && ev.key.toLowerCase() === 's'){ ev.preventDefault(); txSave(false); return; }
  if (ev.ctrlKey && ev.shiftKey && ev.key.toLowerCase() === 's'){ ev.preventDefault(); txSave(true); return; }
  if (ev.ctrlKey && ev.key.toLowerCase() === 'o'){ ev.preventDefault(); txOpen(); return; }
  if (ev.ctrlKey && ev.key.toLowerCase() === 'n'){ ev.preventDefault(); txNew(); return; }
  if (ev.ctrlKey && ev.key.toLowerCase() === 'f'){ ev.preventDefault(); txFindOpen(false); return; }
  if (ev.ctrlKey && ev.key.toLowerCase() === 'h'){ ev.preventDefault(); txFindOpen(true); return; }
  if (ev.ctrlKey && ev.key.toLowerCase() === 'g'){ ev.preventDefault(); txGoto(); return; }
  if (ev.key === 'Escape' && $v12('tx-find') && $v12('tx-find').style.display !== 'none'){ txFindClose(); }
  if (ev.key === 'Enter' && $v12('tx-find') && $v12('tx-find').style.display !== 'none'){
    ev.preventDefault(); txFindNext(ev.shiftKey ? -1 : 1);
  }
}

function txOpen(){
  post('textopen', '');
}
function txSave(asNew){
  var d = txDoc();
  if (!d) return;
  post('textsave', '', undefined, undefined, {
    path: asNew ? '' : d.path,
    name: d.name,
    enc: d.enc,
    eol: d.eol,
    data: b64enc(txEl().value)
  });
}
function txSaveAs(){ txSave(true); }

function txApplyFile(msg){
  var text = b64dec(msg.data || '');
  // 打开的第一个文件直接占用那个「未命名」空壳，不再多留一个空白页签
  var d = null;
  if (TX_DOCS.length === 1 && !TX_DOCS[0].path && !TX_DOCS[0].dirty && !TX_DOCS[0].text){
    d = TX_DOCS[0]; _txCur = 0;
  } else {
    d = txNew(msg.name || '未命名.txt');
  }
  d.name = msg.name || '未命名.txt';
  d.path = msg.path || '';
  d.enc = msg.enc || 'UTF-8';
  d.eol = msg.eol || 'CRLF';
  d.text = text;
  d.dirty = false;
  d.sel = [0, 0];
  txRenderTabs();
  txLoad();
  if (msg.trunc === '1' || msg.trunc === 1)
    toast('文件超过 2 MB，只载入了前 2 MB', 'err');
  else
    toast('已打开 ' + d.name + '（' + d.enc + ' / ' + d.eol + '）', 'ok');
}
function txSaved(msg){
  var d = txDoc();
  if (!d) return;
  d.path = msg.path || d.path;
  d.name = msg.name || d.name;
  if (msg.enc) d.enc = msg.enc;
  if (msg.eol) d.eol = msg.eol;
  d.dirty = false;
  txRenderTabs();
  txStatus();
  toast('已保存 ' + d.name, 'ok');
}

function txZoom(dir){
  _txFontSize = Math.max(10, Math.min(22, _txFontSize + dir));
  var ta = txEl(), g = $v12('tx-gutter');
  if (ta) ta.style.fontSize = _txFontSize + 'px';
  if (g) g.style.fontSize = _txFontSize + 'px';
  var v = $v12('tx-zoom-val');
  if (v) v.textContent = String(_txFontSize);
  txStatus();
}
/* 撤销/重做：textarea 的原生撤销栈最可靠（不用自己拍快照，也不会和输入法打架） */
function txUndoRedo(dir){
  var ta = txEl();
  if (!ta) return;
  ta.focus();
  try { document.execCommand(dir === 'undo' ? 'undo' : 'redo'); } catch (e) {}
  txOnInput();
}
/* 查找框里的按键：回车下一个，Shift+回车上一个，Esc 关闭 */
function txFindKey(ev){
  if (ev.key === 'Enter'){ ev.preventDefault(); txFindNext(ev.shiftKey ? -1 : 1); return; }
  if (ev.key === 'Escape'){ ev.preventDefault(); txFindClose(); }
}
/* 主题分段控件（用 THEME_ICON 的同一份图标，避免两处维护） */
function buildThemeSeg(){
  var box = $v12('set-theme');
  if (!box || box.children.length) return;
  var names = { dark: '黑夜', light: '白天', eye: '护眼' };
  var html = '';
  for (var i = 0; i < THEME_ORDER.length; i++){
    var k = THEME_ORDER[i];
    html += '<button type="button" data-theme="' + k + '" onclick="setThemeByName(\'' + k + '\')">'
          + THEME_ICON[k] + '<span>' + names[k] + '</span></button>';
  }
  box.innerHTML = html;
}
function txSetEnc(v){
  var d = txDoc(); if (!d) return;
  d.enc = v; txStatus();
  toast('保存时将按 ' + v + ' 写入', 'ok');
}
function txSetEol(v){
  var d = txDoc(); if (!d) return;
  d.eol = v; txStatus();
}
function txToggleWrap(){
  _txWrap = !_txWrap;
  var b = $v12('tx-body'), btn = $v12('tx-wrap-btn');
  if (b) { b.classList.toggle('wrap', _txWrap); b.classList.toggle('nowrap', !_txWrap); }
  if (btn) btn.classList.toggle('on', _txWrap);
  var ta = txEl();
  if (ta) ta.setAttribute('wrap', _txWrap ? 'soft' : 'off');
  txGutter();
  txStatus();
}

/* --- 查找 / 替换 --- */
function txFindOpen(showReplace){
  var box = $v12('tx-find');
  if (!box) return;
  box.style.display = 'flex';
  $v12('tx-repl-i').style.display = showReplace ? '' : 'none';
  $v12('tx-repl-one').style.display = showReplace ? '' : 'none';
  $v12('tx-repl-all').style.display = showReplace ? '' : 'none';
  var ta = txEl();
  var sel = ta.value.slice(ta.selectionStart, ta.selectionEnd);
  if (sel && sel.indexOf('\n') < 0) $v12('tx-find-i').value = sel;
  $v12('tx-find-i').focus();
  $v12('tx-find-i').select();
  txFindHighlight();
}
function txFindClose(){
  var box = $v12('tx-find');
  if (box) box.style.display = 'none';
  var ta = txEl(); if (ta) ta.focus();
}
function txFindMatches(){
  var ta = txEl(), q = $v12('tx-find-i').value;
  if (!q) return [];
  var hay = ta.value, cs = $v12('tx-case').checked;
  if (!cs) { hay = hay.toLowerCase(); q = q.toLowerCase(); }
  var out = [], i = 0;
  while (true){
    var k = hay.indexOf(q, i);
    if (k < 0) break;
    out.push(k); i = k + Math.max(1, q.length);
    if (out.length > 5000) break;
  }
  return out;
}
function txFindHighlight(){
  var n = $v12('tx-find-n');
  var q = $v12('tx-find-i').value;
  if (!n) return;
  if (!q) { n.textContent = ''; return; }
  var m = txFindMatches();
  n.textContent = m.length ? (m.length + ' 处') : '无匹配';
}
function txFindNext(dir){
  var ta = txEl(), q = $v12('tx-find-i').value;
  if (!q) { txFindHighlight(); return; }
  var m = txFindMatches();
  if (!m.length) { toast('没有匹配内容', 'err'); return; }
  var cur = ta.selectionStart, target = null;
  if (dir > 0){
    for (var i = 0; i < m.length; i++) if (m[i] > cur) { target = m[i]; break; }
    if (target === null) target = m[0];
  } else {
    for (var j = m.length - 1; j >= 0; j--) if (m[j] < cur) { target = m[j]; break; }
    if (target === null) target = m[m.length - 1];
  }
  ta.focus();
  ta.setSelectionRange(target, target + q.length);
  txScrollToCaret();
  txStatus();
  txFindHighlight();
}
function txScrollToCaret(){
  var ta = txEl();
  var before = ta.value.slice(0, ta.selectionStart);
  var line = before.split('\n').length;
  var lh = _txFontSize * 1.55;
  var y = (line - 1) * lh;
  if (y < ta.scrollTop || y > ta.scrollTop + ta.clientHeight - lh * 2)
    ta.scrollTop = Math.max(0, y - ta.clientHeight / 2);
  txSyncScroll();
}
function txReplaceOne(){
  var ta = txEl(), q = $v12('tx-find-i').value, rep = $v12('tx-repl-i').value;
  if (!q) return;
  var sel = ta.value.slice(ta.selectionStart, ta.selectionEnd);
  var cs = $v12('tx-case').checked;
  var hit = cs ? (sel === q) : (sel.toLowerCase() === q.toLowerCase());
  if (hit){
    var s = ta.selectionStart;
    ta.value = ta.value.slice(0, s) + rep + ta.value.slice(ta.selectionEnd);
    ta.setSelectionRange(s + rep.length, s + rep.length);
    txOnInput();
  }
  txFindNext(1);
}
function txReplaceAll(){
  var ta = txEl(), q = $v12('tx-find-i').value, rep = $v12('tx-repl-i').value;
  if (!q) return;
  var n = 0;
  if ($v12('tx-case').checked){
    n = ta.value.split(q).length - 1;
    ta.value = ta.value.split(q).join(rep);
  } else {
    var re = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
    n = (ta.value.match(re) || []).length;
    ta.value = ta.value.replace(re, rep);
  }
  txOnInput();
  txFindHighlight();
  toast(n ? ('已替换 ' + n + ' 处') : '没有匹配内容', n ? 'ok' : 'err');
}
function txGoto(){
  var v = prompt('跳到第几行？', '1');
  if (!v) return;
  var n = parseInt(v, 10);
  if (!n || n < 1) return;
  var ta = txEl();
  var lines = ta.value.split('\n');
  if (n > lines.length) n = lines.length;
  var off = 0;
  for (var i = 0; i < n - 1; i++) off += lines[i].length + 1;
  ta.focus();
  ta.setSelectionRange(off, off);
  txScrollToCaret();
  txStatus();
}

/* ============================ §5 文件页增强 ============================ */
function fsSwapSides(){
  var p = $v12('fs-panes');
  if (!p) return;
  p.classList.toggle('flip');
  var flip = p.classList.contains('flip');
  try { localStorage.setItem('_fsFlip', flip ? '1' : '0'); } catch (e) {}
  toast(flip ? '已换边：设备在左 / 电脑在右' : '已换边：电脑在左 / 设备在右', 'ok');
}
function fsRestoreFlip(){
  var p = $v12('fs-panes');
  if (!p) return;
  var v = '0';
  try { v = localStorage.getItem('_fsFlip') || '0'; } catch (e) {}
  p.classList.toggle('flip', v === '1');
}

/* 列宽：拖表头分隔线。写入 --w-name / --w-size（行与表头共用同一组变量，
   所以拖完表头行会一起变，不会错位）。双击分隔线恢复默认。 */
var _fsCols = { name: 0, size: 74 };
function fsApplyCols(){
  var p = $v12('fs-panes');
  if (!p) return;
  p.style.setProperty('--w-name', _fsCols.name ? (_fsCols.name + 'px') : '1fr');
  p.style.setProperty('--w-size', _fsCols.size + 'px');
}
function fsSaveCols(){
  try { localStorage.setItem('_fsCols', JSON.stringify(_fsCols)); } catch (e) {}
}
function fsLoadCols(){
  try {
    var o = JSON.parse(localStorage.getItem('_fsCols') || '{}');
    if (o && typeof o === 'object'){
      if (o.name) _fsCols.name = o.name;
      if (o.size) _fsCols.size = o.size;
    }
  } catch (e) {}
  fsApplyCols();
}
function fsColDown(ev, which){
  ev.preventDefault();
  ev.stopPropagation();
  var pane = ev.target.closest ? ev.target.closest('.fs-pane') : null;
  if (!pane) return;
  var heads = pane.querySelectorAll('.fs-cols .ct');
  var nameW = heads[0] ? heads[0].getBoundingClientRect().width : 200;
  var sizeW = heads[1] ? heads[1].getBoundingClientRect().width : 74;
  var startX = ev.clientX;
  var g = ev.target;
  g.classList.add('on');
  document.body.classList.add('col-resizing');
  function move(e){
    var dx = e.clientX - startX;
    if (which === 'name') _fsCols.name = Math.max(110, Math.round(nameW + dx));
    else _fsCols.size = Math.max(48, Math.round(sizeW + dx));
    fsApplyCols();
  }
  function up(){
    document.removeEventListener('mousemove', move);
    document.removeEventListener('mouseup', up);
    g.classList.remove('on');
    document.body.classList.remove('col-resizing');
    fsSaveCols();
  }
  document.addEventListener('mousemove', move);
  document.addEventListener('mouseup', up);
}
function fsColReset(ev){
  if (ev) ev.stopPropagation();
  _fsCols.name = 0; _fsCols.size = 74;
  fsApplyCols(); fsSaveCols();
  toast('列宽已恢复默认', 'ok');
}

/* ============================ §6 结果图空态 ============================ */
function uiResultImgErr(){
  var img = $v12('ui-result-img');
  if (img) { img.classList.remove('has'); img.removeAttribute('src'); }
  var em = $v12('ui-result-empty');
  if (em) { em.style.display = ''; em.textContent = '没有结果图（点「开始对比」生成）'; }
  var box = $v12('ui-resultbox');
  if (box) box.classList.add('err');
}

/* ============================ §7 接入 ============================ */
function v12OnMessage(msg){
  switch (msg.kind){
    case 'winstate':
      setWinMax(msg.max === 1 || msg.max === '1');
      return true;
    case 'prefs':
      prefsApply(msg.data || '');
      return true;
    case 'textfile':
      if ($v12('page-text')) { switchTab('text'); }
      txApplyFile(msg);
      return true;
    case 'textsaved':
      txSaved(msg);
      return true;
    case 'texterr':
      toast(msg.text || '文本操作失败', 'err');
      return true;
  }
  return false;
}

/* 主题 / 强调色被别处改动时同步设置面板的选中态 */
(function hookAppliers(){
  if (typeof applyTheme === 'function'){
    var t0 = applyTheme;
    applyTheme = function (n){ t0(n); try { syncThemeSeg(); } catch (e) {} };
  }
  if (typeof switchTab === 'function'){
    var s0 = switchTab;
    switchTab = function (n){
      s0(n);
      var pt = $v12('page-text');
      if (pt) pt.classList.toggle('active', n === 'text');
      if (n === 'text') txActivate();
    };
  }
})();

document.addEventListener('keydown', function (ev){
  if (ev.key !== 'Escape') return;
  var hm = $v12('help-mask');
  if (hm && hm.style.display === 'flex') { closeHelp(); ev.stopPropagation(); return; }
  var sm = $v12('set-mask');
  if (sm && sm.style.display === 'flex') { closeSettings(); ev.stopPropagation(); return; }
});

document.addEventListener('DOMContentLoaded', function (){
  setWinMax(false);
  fsRestoreFlip();
  fsLoadCols();
  buildFontSelect();
  buildThemeSeg();
  applyFont(_prefs.font, true);
  syncThemeSeg();
});
/* === V12 JS END === */
