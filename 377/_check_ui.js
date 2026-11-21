// ui.html 静态自检：语法 + DOM 引用 + CSS 类 + 问题项覆盖
// 用途：改完 ui.html 先跑一遍，避免"打开是白屏 / 点按钮没反应"。
// 运行：node _check_ui.js
var fs = require('fs');
var path = require('path');

// 本脚本放在 377/（验证产物目录），ui.html 在上上一级
var ROOT = path.resolve(__dirname, '..');
var f = path.join(ROOT, 'adb_log_gui', 'webview2', 'ui.html');
var src = fs.readFileSync(f, 'utf8');

var FAIL = 0;
// 【关键】判断"某条 CSS 规则里有没有某属性"时，必须先把注释剥掉。
// 本轮就踩了一次：为了让后来人看懂为什么要回退吸顶，在 .vr-panel 规则里
// 写了"上一版用 position:sticky…"的说明，结果断言把注释当代码判成失败。
// 所以凡是针对 `选择器{...}` 内部内容的断言，一律用 srcNoCmt。
var srcNoCmt = src.replace(/\/\*[\s\S]*?\*\//g, '');
function ck(name, cond, extra) {
    if (cond) {
        console.log('  [OK] ' + name);
    } else {
        FAIL++;
        console.log('  [XX] ' + name + (extra ? '  -> ' + extra : ''));
    }
}

// ---- 1. 抽 script 做语法检查 ----
var m = src.match(/<script>([\s\S]*?)<\/script>/);
ck('找到 <script> 块', !!m);
var js = m ? m[1] : '';
console.log('\n== 1. JS 语法 ==');
try {
    new Function(js);
    ck('script 语法可解析', true);
} catch (e) {
    ck('script 语法可解析', false, e.message);
}

// ---- 2. getElementById 引用的 id 必须存在于 HTML ----
console.log('\n== 2. DOM 引用完整性 ==');
// 运行时才创建的节点不在静态 HTML 里，属于正常情况，单独白名单。
// 新增动态节点时记得往这里加，否则会被误判成"引用不存在的 id"。
var DYNAMIC_IDS = ['toast', 'fs-modal',
  // 2026-11-21（第 7 批需求3）：page-ui / page-text 两个一级页容器已并入文件页
  // （内容搬进 #fileview-ui / #fileview-text）。switchTab 里仍保留
  // `var pu = getElementById('page-ui'); if(pu) ...` 的兼容分支，
  // 元素不存在时静默跳过 —— 这是刻意保留的旧路径兼容，不是漏写 id。
  'page-ui', 'page-text'];
var ids = [];
var reId = /getElementById\(\s*'([^']+)'\s*\)/g, mm;
while ((mm = reId.exec(js)) !== null) {
    if (ids.indexOf(mm[1]) < 0) ids.push(mm[1]);
}
// 需求1：多输入框槽位的 id 由 buildSlots()/slotHTML() 动态生成（带 -0/-1/-2 后缀），
// 静态 HTML 里没有，按模式跳过。删除按钮 btn-del-N 同属动态节点。
// 2026-11-15：投屏 6 格的 <img id="cast-img-N"> 由 castRenderCells() 动态生成；
// UI 对比页「后屏截图」(uiShot) 里硬引用了 cast-img-2，静态 HTML 同样没有，按动态跳过。
var dynId = /^(slot|logbox|log-empty|cmd-input|btn-run|btn-stop|btn-del)-\d+$|^btn-add$|^cast-img-\d+$/;
var missing = [];
for (var i = 0; i < ids.length; i++) {
    if (DYNAMIC_IDS.indexOf(ids[i]) >= 0) continue;
    if (dynId.test(ids[i])) continue;
    if (src.indexOf('id="' + ids[i] + '"') < 0) missing.push(ids[i]);
}
ck('getElementById 目标都存在（' + ids.length + ' 个，动态 ' + DYNAMIC_IDS.length + ' 个除外）',
   missing.length === 0, missing.join(','));

// ---- 3. querySelector 用到的类必须至少有样式或会被 js 赋上 ----
console.log('\n== 3. 关键类名 ==');
var need = ['fb-row', 'fb-left', 'fb-split', 'fb-right', 'fb-meta', 'badge', 'rootpill', 'qcard'];
for (var k = 0; k < need.length; k++) {
    // CSS 里出现 .cls  或 js 里出现 'cls'
    var inCss = src.indexOf('.' + need[k]) >= 0 || src.indexOf('#' + need[k]) >= 0;
    ck('类 ' + need[k] + ' 有定义/使用', inCss);
}
// toast 用的是 id 选择器 + 动态创建，单独校验
ck('toast 有 #toast 样式', src.indexOf('#toast{') >= 0);
ck('toast 有 .show 态', src.indexOf('#toast.show') >= 0);

// ---- 4. 问题项：逐条 ACL 断言 ----
console.log('\n== 4. 九个问题逐条覆盖 ==');

// 问题2 不闪烁：frame 不再有 opacity 过渡；splash 有 gone 收尾
ck('P2 frame 去掉 opacity 过渡', !/\.frame\{[^}]*transition:opacity/.test(src));
ck('P2 splash 有 .gone 彻底退场', src.indexOf('.splash.gone') >= 0);
ck('P2 有 hideSplash 单次退场', js.indexOf('function hideSplash') >= 0);

// 问题3 root 按钮
ck('P3 顶栏有 root 按钮', src.indexOf('id="root-pill"') >= 0);
ck('P3 未 root 红色样式', src.indexOf('.rootpill.no') >= 0);
ck('P3 已 root 绿色样式', src.indexOf('.rootpill.yes') >= 0);
// 只约束提权函数本身不要弹确认框；自定义指令「删除」用 confirm 是合理的二次确认，
// 不能用全文 indexOf('confirm(') 一刀切（2026-11-15 追加功能时踩过）。
ck('P3 点击即提权（无确认框）',
   js.indexOf("post('root')") >= 0 &&
   !/function onRootClick\([^)]*\)\{[\s\S]{0,800}?confirm\(/.test(js));
ck('P3 有 rootdone 回执处理', js.indexOf('onRootDone') >= 0);
ck('P3 提权有超时解锁', js.indexOf('10000') >= 0);

// 问题4 左右分栏
ck('P4 分栏变量 --fb-left', src.indexOf('--fb-left') >= 0);
ck('P4 竖线可拖（col-resize）', src.indexOf('col-resize') >= 0);
ck('P4 指令自动换行 pre-wrap', /\.fb-row \.c\{[\s\S]{0,200}pre-wrap/.test(src));
ck('P4 输出自动换行 pre-wrap', /\.fb-right\{[\s\S]{0,400}pre-wrap/.test(src));
ck('P4 输出不覆盖（每条独立行）', js.indexOf('_curOutEl') >= 0 && js.indexOf('addFeed') >= 0);
ck('P4 可滚动浏览', /\.fb-table\{[\s\S]{0,120}overflow-y:auto/.test(src));
ck('P4 输出高亮时覆盖率', /max-height:200px/.test(src));
// 需求4：输出区必须装得下车机信息「8 项属性 + 分辨率 = 9 行」。
// 12.5px 字号 × 1.5 行高 = 18.75px/行，9 行 = 169px，200px 才有余量。
// 原来 132px 只能放 7 行，OPENID 和屏幕分辨率会被截掉 —— 用户在界面上
// 根本看不到这两项，等于"车机信息"按钮少输出了两项。
ck('需求4 输出区装得下车机信息 9 行（>=180px）',
   (function(){
     var m = src.match(/\.fb-row \.fb-right\{[^}]*max-height:(\d+)px/);
     return m && parseInt(m[1], 10) >= 180;
   })());
ck('P4 时间/指令/结果/耗时 四项齐全', js.indexOf('f.time') >= 0 && js.indexOf('f.cmd') >= 0 && js.indexOf('f.ok') >= 0 && js.indexOf('f.ms') >= 0);
// 追加顺序：表头是第一个子元素，新记录必须 appendChild（旧→新）
// 一旦改成 insertBefore(head.nextSibling)，列表就变成倒序，这里会挂。
// 注意要先剥掉注释再判 —— 说明性注释里会提到 insertBefore 这个词，
// 不剥的话断言会被自己的注释判失败（第一次就踩了）。
var jsNoCmt = js.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
ck('P4 记录按旧→新追加（appendChild）', /tb\.appendChild\(row\)/.test(jsNoCmt));
ck('P4 未用 insertBefore 打乱顺序', jsNoCmt.indexOf('insertBefore(row') < 0);

// 问题5 一行三个
ck('P5 快捷指令 3 列', /\.quick-grid\{[\s\S]{0,200}repeat\(3,/.test(src));
// 2026-11-15：UI 对比页 .ui-stage 合法使用 grid-template-columns:1fr 1fr 做设计图/实景图双栏，
// 全文禁止 1fr 1fr 会误伤。这里只针对「快捷指令网格」断言没退回旧双列。
ck('P5 快捷指令网格未退回旧双列',
   !/\.quick-grid\{[^}]*grid-template-columns:\s*1fr 1fr/.test(srcNoCmt));

// 问题6 语音助手下移
var idxZhiling = js.indexOf("name:'指令执行'");
var idxYuyin = js.indexOf("name:'语音助手'");
ck('P6 语音助手在指令执行之后', idxZhiling >= 0 && idxYuyin > idxZhiling);
// 2026-11-12：应用操作/设备信息/性能监控/系统控制/文件管理 五个分组已整体删除

// 问题7 分辨率
ck('P7 顶栏有分辨率节点', src.indexOf('id="dev-res"') >= 0);
ck('P7 setStatus 消费 s.res', js.indexOf('s.res') >= 0);

// 问题8 按钮不消失
ck('P8 执行中不隐藏卡片（无 display:none）', !/\.qcard\.running\{[^}]*display:none/.test(src));
// 【类名冲突防护】曾出过一次真 bug：顶部进度条用了裸 .running{display:none}，
// 与卡片的 .qcard.running 撞名，导致卡片一点击就整个消失。
// 这里强制：不允许存在"裸 .running"规则（必须以 .qcard 或 .runbar 开头）。
ck('P8 不存在裸 .running 规则（与卡片类名冲突）',
   !/(^|\})\s*\.running\s*[{.,: ]/.test(src));
ck('P8 进度条改用独立类名 .runbar', src.indexOf('.runbar{') >= 0);
ck('P8 进度条 HTML 元素已改名', src.indexOf('id="runbar"') >= 0);
ck('P8 进度条 keyframes 仍在', src.indexOf('@keyframes run{') >= 0);
ck('P8 结果态停留可感知（>=2s）', /ok \? 2600 : 3200/.test(js));
ck('P8 toggle 类执行中仍可点', /\.qcard\.toggle\.running\{pointer-events:auto/.test(src));

// ---- 5. 旧的废弃引用不能残留 ----
console.log('\n== 5. 废弃引用清理 ==');
ck('旧 fb-out 已移除', src.indexOf("id=\"fb-out\"") < 0);
ck('旧 .out-ln 已移除', src.indexOf('out-ln') < 0);
ck('旧 .fb-row .s 列已移除', !/row\.querySelector\('\.s'\)/.test(js));

// ---- 6. 需求1：表头与记录列对齐 + 字符限制 ----
console.log('\n== 6. 需求1 列对齐与字符限制 ==');
// 表头必须是"两行"结构（h-meta 一行 + h-c 一行），与记录左栏结构一致；
// 只放一个整体标签 .h-lbl 是对不上记录的（已废弃）。
ck('需求1 表头第1行 h-meta 存在', src.indexOf('class="h-meta"') >= 0);
ck('需求1 表头第2行 h-c 存在', /<div class="h-c">/.test(src));
ck('需求1 表头已废弃单标签 h-lbl', src.indexOf('h-lbl') < 0);
// 三个字段的定宽必须与记录端一字不差，否则竖直方向不成列
function wOf(sel){
  var m = src.match(new RegExp(sel.replace(/[.\-]/g, function(c){return '\\'+c;}) + '\\{([^}]*)\\}'));
  return m ? m[1] : '';
}
ck('需求1 时间列定宽 58px（表头=记录）',
   /\.fb-head \.hl \.h-meta \.h-t\{flex:0 0 auto;width:58px;\}/.test(src) &&
   /\.fb-row \.fb-meta \.t\{flex:0 0 auto;width:58px;/.test(src));
ck('需求1 状态列定宽 38px（表头=记录）',
   /\.fb-head \.hl \.h-meta \.h-b\{flex:0 0 auto;width:38px;/.test(src) &&
   /\.fb-row \.fb-meta \.badge\{[^}]*width:38px/.test(src));
ck('需求1 耗时列定宽 62px 右对齐（表头=记录）',
   /\.fb-head \.hl \.h-meta \.h-d\{flex:0 0 auto;width:62px;text-align:right;\}/.test(src) &&
   /\.fb-row \.fb-meta \.d\{[^}]*width:62px;text-align:right;/.test(src));
// 指令限 2 行 + 输出限高，防止长内容糊满屏幕
ck('需求1 指令限 2 行（line-clamp:2）', /\.fb-row \.c\{[^}]*-webkit-line-clamp:2/.test(src));
ck('需求1 输出区限高 200px', /\.fb-row \.fb-right\{[^}]*max-height:200px/.test(src));
ck('需求1 指令超长补 title 悬停全文', /c\.title = f\.cmd/.test(js));
// 分隔线宽度必须与表头 .h-sp 一致，否则右栏整体错位
ck('需求1 分隔线 .fb-split 有宽度 13px', /\.fb-row \.fb-split\{[^}]*flex:0 0 13px/.test(src));
ck('需求1 表头 .h-sp 宽度与分隔线一致', /\.fb-head \.h-sp\{flex:0 0 13px;margin:0 3px;\}/.test(src));

// ---- 7. 需求4：车机信息按钮 ----
console.log('\n== 7. 需求4 车机信息按钮 ==');
ck('指令执行组有「车机信息」卡片', /name:'车机信息'/.test(js));
ck('车机信息卡片命令为 :car', /name:'车机信息'[^}]*cmd:':car'/.test(js));
ck('车机信息在指令执行分组内',
   (function(){
     var i = js.indexOf("name:'车机信息'");
     if (i < 0) return false;
     var g = js.indexOf("name:'指令执行'");
     var nxt = js.indexOf("{ name:'", g + 10);
     return g >= 0 && i > g && (nxt < 0 || i < nxt);
   })());
ck('车机信息卡片带描述（九项口径）',
   /name:'车机信息', desc:'[^']*(SOC|VIN|UUID)/.test(js));

// ---- 8. 需求·补充：删除输入框 ----
console.log('\n== 8. 删除输入框交互 ==');
ck('需求有 .delbtn 样式', src.indexOf('.delbtn{') >= 0);
ck('需求删除按钮常显半透明（能被发现）', /\.delbtn\{[\s\S]{0,400}opacity:\.35/.test(src));
ck('需求整槽 hover 时按钮变清晰', /\.slot:hover \.delbtn\{opacity:1;\}/.test(src));
ck('需求只有 1 个槽时隐藏删除按钮', /\.slots\.one \.delbtn\{display:none;\}/.test(src));
ck('需求多槽时日志区给按钮预留右侧空间（不遮字）',
   /\.slots:not\(\.one\) \.logbox\{padding-right:44px;\}/.test(src));
ck('需求执行中禁用删除（delbtn:disabled）', /\.delbtn:disabled\{[^}]*pointer-events:none/.test(src));
ck('需求 slotHTML 生成 btn-del-N', js.indexOf("id=\"btn-del-") >= 0 || js.indexOf('id="btn-del-') >= 0);
ck('需求有 delSlot 函数', js.indexOf('function delSlot(') >= 0);
ck('需求 delSlot 整体重建而非 removeChild',
   js.indexOf('function delSlot(') >= 0 &&
   !/function delSlot\([\s\S]{0,3000}?removeChild/.test(js));
ck('需求 delSlot 快照并回填 logbox 内容', /function delSlot\([\s\S]{0,1500}?innerHTML = keep\[k\]\.html/.test(js));
ck('需求 _busy 随删除重排', /function delSlot\([\s\S]{0,2500}?_busy\.splice\(n, 1\)/.test(js));
ck('需求 单槽时拒绝删除', /function delSlot\([\s\S]{0,200}?_slotCount <= 1/.test(js));
ck('需求 busy 时拒绝删除并提示', /function delSlot\([\s\S]{0,400}?_anyBusy\(\)[\s\S]{0,200}?toast\(/.test(js));
ck('需求 beginRun 期间禁用删除', /function beginRun\([\s\S]{0,600}?setDelEnabled\(false\)/.test(js));
ck('需求 endRun 后恢复删除', /_busy\[slot\] = false;[\s\S]{0,200}?setDelEnabled\(!_anyBusy\(\)\)/.test(js));

// ---- 9. 需求·补充：语音助手页整体滑动 ----
console.log('\n== 9. 语音助手页整体滑动 ==');
ck('需求有 .quick-scroll 滚动容器', src.indexOf('.quick-scroll{') >= 0);
ck('需求 .quick-scroll 可纵向滚动', /\.quick-scroll\{[\s\S]{0,160}?overflow-y:auto/.test(src));
ck('需求 .quick-scroll 滚动条样式已迁移', /\.quick-scroll::-webkit-scrollbar\{width:12px;\}/.test(src));
ck('需求 HTML 里 vr-panel 被 quick-scroll 包住', /<div class="quick-scroll" id="quick-scroll">[\s\S]{0,400}?id="vr-panel"/.test(src));
ck('需求 quick-grid 不再自己滚（flex:none）', /\.quick-grid\{flex:none;/.test(src));
ck('需求 quick-grid 已去掉 overflow-y:auto', !/\.quick-grid\{[^}]*overflow-y:auto/.test(src));
// 【方案 A 回退】上一版给 .vr-panel 加了 position:sticky 吸顶，本意是"边滚边输入"，
// 实际观感相反：面板钉在顶部、卡片只在底部露出一点，用户看到的是"输入框不能滑动"。
// 现在回归流式布局 —— 这里必须断言"没有 sticky"，否则同类缺陷会再被误加回来。
ck('需求 vr-panel 不再吸顶（无 position:sticky）',
   !/\.vr-panel\{[\s\S]{0,800}?position:sticky/.test(srcNoCmt));
ck('需求 vr-panel 去掉了吸顶用的投影',
   !/\.vr-panel\{[\s\S]{0,800}?box-shadow:0 8px 16px/.test(srcNoCmt));
ck('需求 vr-panel 随容器一起滚（flex:0 0 auto 自然高度）',
   /\.vr-panel\{[\s\S]{0,800}?flex:0 0 auto;margin:0 20px 12px;padding:12px 14px;/.test(srcNoCmt));
ck('需求 切分组时滚动复位', /function switchQuickGroup\([\s\S]{0,600}?sc\.scrollTop = 0/.test(js));
// 2026-11-15：新增「UI」页签后 switchTab 里的分支变多，固定 {0,700} 窗口会被撑破，
// 报出假失败。改成先切出 switchTab 函数体、再在体内部判断，新增页签不影响。
ck('需求 切页签时滚动复位', (function(){
  var s = js.indexOf('function switchTab(');
  if (s < 0) return false;
  var e = js.indexOf('\nfunction ', s + 10);
  var body = js.slice(s, e < 0 ? s + 2000 : e);
  return /quick-scroll[\s\S]{0,200}?scrollTop = 0/.test(body);
})());

// ---- 10. 需求·补充：输出框可拖到收起 ----
console.log('\n== 10. 输出框拖拽收起 ==');
// 旧版收不起来的原因：CSS min-height:120px 与 JS Math.max(120,…) 双重下限。
// 现在下限单点由 FB_MIN=34（折叠栏高度）控制，这两处硬编码都必须消失。
ck('需求 .feedback 去掉 120px 硬地板', !/\.feedback\{[^}]*min-height:120px/.test(srcNoCmt));
ck('需求 .feedback 最小高度归零', /\.feedback\{[^}]*min-height:0;/.test(srcNoCmt));
ck('需求 JS 不再写死 Math.max(120', jsNoCmt.indexOf('Math.max(120') < 0);
ck('需求 JS 用 FB_MIN 作为可拖下限', /var FB_MIN = 34;/.test(jsNoCmt));
ck('需求 收起吸附阈值 SNAP 存在', /var SNAP\s*= 90;/.test(jsNoCmt));
ck('需求 有折叠栏 .fb-collapsed-bar', src.indexOf('.fb-collapsed-bar{') >= 0);
ck('需求 HTML 有折叠栏节点', src.indexOf('id="fb-collapsed-bar"') >= 0);
ck('需求 收起态隐藏内容区',
   /\.feedback\.collapsed \.fb-table\{display:none;\}/.test(src));
ck('需求 收起态隐藏拖拽条',
   /\.feedback\.collapsed \.fb-resizer,[\s\S]{0,80}?\.fb-table\{display:none;\}/.test(src));
ck('需求 收起态高度锁到折叠栏高度', /\.feedback\.collapsed\{height:34px !important;\}/.test(src));
ck('需求 收起态显示折叠栏', /\.feedback\.collapsed \.fb-collapsed-bar\{display:flex;\}/.test(src));
ck('需求 有 setCollapsed 统一收放', jsNoCmt.indexOf('function setCollapsed(') >= 0);
ck('需求 展开时还原收起前高度（prevH）', jsNoCmt.indexOf('var prevH') >= 0 && /prevH > FB_MIN \* 2/.test(jsNoCmt));
ck('需求 松手低于 SNAP 自动吸附收起', /if\(h < SNAP\)/.test(jsNoCmt));
ck('需求 折叠栏可点击切换收放', jsNoCmt.indexOf('setCollapsed(!wasCollapsed)') >= 0);
ck('需求 折叠栏显示记录条数（收起后看不到列表）',
   src.indexOf('id="fb-collapsed-cnt"') >= 0 && jsNoCmt.indexOf('function refreshCount(') >= 0);

// ---- 11. 需求·补充：新增指令与方控独立分组 ----
console.log('\n== 11. 新增指令与方控分组 ==');
ck('需求 有「导出ANR日志」卡片', /name:'导出ANR日志'/.test(js));
ck('需求 ANR 卡片走 :anrlog', /name:'导出ANR日志'[^}]*cmd:':anrlog'/.test(js));
ck('需求 有「导出crash日志」卡片', /name:'导出crash日志'/.test(js));
ck('需求 crash 卡片走 :dropboxlog', /name:'导出crash日志'[^}]*cmd:':dropboxlog'/.test(js));
ck('需求 有「重启车机」卡片', /name:'重启车机'/.test(js));
ck('需求 重启卡片走 :reboot', /name:'重启车机'[^}]*cmd:':reboot'/.test(js));
// 2026-11-13：前台相关的四张卡（导出APK / 查前台应用 / 查询前台包名 / 清理前台应用）
// 挪到「APK管理」分组，这里改成断言"卡片下架 + 命令仍在 C# 侧可用"。
ck('需求 清理前台应用卡片已下架', !/name:'清理前台应用'/.test(js));
ck('需求 导出APK 卡片已下架', !/name:'导出APK'/.test(js));
ck('需求 有 Apk管理 面板分组', /name:'Apk管理'[^}]*panel:'apk'/.test(js));
// 星河云环境：查询 + 三套环境，四条都要在
ck('需求 有「查询星河云环境」卡片', /name:'查询星河云环境'/.test(js));
ck('需求 有「切预发布环境」卡片', /name:'切预发布环境'[^}]*cmd:':env pre'/.test(js));
ck('需求 有「切现网环境」卡片', /name:'切现网环境'[^}]*cmd:':env dev'/.test(js));
ck('需求 有「切测试环境」卡片', /name:'切测试环境'[^}]*cmd:':env test'/.test(js));
ck('需求 星河云环境自成一类', js.indexOf("cat:'星河云环境'") >= 0);
// 方控：必须**独立分组**（用户原话"方控独立的页面"），不能混进指令执行
ck('需求 方控独立成组（name 方控按键）',
   /name:'方控按键'/.test(js));
// 2026-11-15 Apple UI：分组 color 是遗留死数据（无任何地方读取），
// 改为统一引用语义令牌；保留「独立成组」的真实需求（上方断言）。
ck('需求 方控组独立且颜色走语义令牌', /name:'方控按键', color:'var\(--accent\)'/.test(js));
ck('需求 方控组内分音量控制', js.indexOf("cat:'音量控制'") >= 0);
ck('需求 方控组内分播放控制', js.indexOf("cat:'播放控制'") >= 0);
ck('需求 方控组内分功能按键', js.indexOf("cat:'功能按键'") >= 0);
(function(){
  // 方控组的 { ... } 区间内必须恰好 13 张卡，且键值一一对应
  // （2026-11-12：星号分左右 + 语音/通话分长短按，由 10 条变 13 条）
  var gi = js.indexOf("name:'方控按键'");
  if (gi < 0) { ck('需求 方控 13 条命令齐全', false, '没找到分组'); return; }
  var seg = js.slice(gi, gi + 4000);
  var want = {
    ':fkvolup': 1, ':fkvoldown': 1, ':fkmute': 1,
    ':fkprev': 1, ':fknext': 1, ':fkplay': 1,
    ':fkvoice': 1, ':fkvoicelong': 1, ':fkcall': 1, ':fkcalllong': 1,
    ':fkstarleft': 1, ':fkstarright': 1,
    ':fkforce': 1
  };
  var miss = [];
  for (var k2 in want) { if (seg.indexOf("cmd:'" + k2 + "'") < 0) miss.push(k2); }
  ck('需求 方控 13 条命令齐全', miss.length === 0, miss.join(','));
})();
ck('需求 方控组有组合键分类', js.indexOf("cat:'组合键'") >= 0);
ck('需求 方控强制重启卡走 :fkforce',
   /name:'强制重启'[^}]*cmd:':fkforce'/.test(js));
ck('需求 方控强制重启说明提到按住 20 秒',
   /name:'强制重启'[^}]*按住 20 秒/.test(js));
// 星号键分左/右（逆向 SynTestUtil：leftkey=521，rightkey=520）
ck('需求 右星号键 520', /name:'右星号键'[^}]*inject-key 520/.test(js));
ck('需求 左星号键 521', /name:'左星号键'[^}]*inject-key 521/.test(js));
ck('需求 有长按语音卡', /name:'长按语音'[^}]*:fkvoicelong/.test(js));
ck('需求 有长按通话卡', /name:'长按通话'[^}]*:fkcalllong/.test(js));
// 【踩坑】不能用 js.indexOf('音源切换') < 0 判 —— 本轮在方控组里
// 写了说明性注释"旧版误标音源切换"，那几个字会被这条断言当代码匹配上，
// 报出假失败。只查真正的卡片定义。
ck('需求 不再有「音源切换」卡片', !/name:'音源切换'/.test(js));
ck('需求 520 卡片名不是音源切换',
   !/name:'音源切换'[^}]*520/.test(js));

// ---- 手车互联分组（2026-11-12 需求1~4）----
ck('需求 有「手车互联」独立分组', /name:'手车互联'/.test(js));
ck('需求 手车互联组独立且颜色走语义令牌', /name:'手车互联', color:'var\(--accent\)'/.test(js));
(function(){
  var ci = js.indexOf("name:'手车互联'");
  if (ci < 0) { ck('需求 手车互联 8 条命令齐全', false, '没找到分组'); return; }
  var cseg = js.slice(ci, ci + 3000);
  var cwant = {
    ':carplaycert': 1,           // 查询（裸命令）
    ':carplaycert on': 1,        // 开启
    ':carplaycert off': 1,       // 关闭
    ':hicarclear': 1,            // 清除 HiCar 历史设备
    ':hdclist': 1,               // hdc 设备列表
    ':carplay': 1,               // carplay 音频导出（迁入）
    ':carplayon': 1,             // 打开 carplay 音频（迁入）
    ':hicar': 1                  // 打开 HiCarSDK 日志（迁入）
  };
  var cmiss = [];
  for (var ck2 in cwant) {
    if (cseg.indexOf("cmd:'" + ck2 + "'") < 0) cmiss.push(ck2);
  }
  ck('需求 手车互联 8 条命令齐全', cmiss.length === 0, cmiss.join(','));
})();
ck('需求 手车互联组内分 CarPlay 认证', js.indexOf("cat:'CarPlay 认证'") >= 0);
ck('需求 手车互联组内分 CarPlay 调试', js.indexOf("cat:'CarPlay 调试'") >= 0);
ck('需求 手车互联组内分 HiCar', js.indexOf("cat:'HiCar'") >= 0);
ck('需求 手车互联组内分 hdc 通道', js.indexOf("cat:'hdc 通道'") >= 0);
ck('需求 说明里出现 CERT 属性名',
   js.indexOf('persist.connectivityphone.carplay.CERT') >= 0);
ck('需求 手车互联含清除HiCar卡',
   /name:'清除HiCar历史设备'/.test(js));
ck('需求 手车互联含 hdc 设备列表卡',
   /name:'hdc设备列表'/.test(js));

(function(){
  // carplay/hicar 三条必须从「指令执行」里搬走，否则会两处重复出现
  var z2 = js.indexOf("name:'指令执行'");
  var c2 = js.indexOf("name:'手车互联'");
  if (z2 < 0 || c2 < 0) { ck('需求 carplay/hicar 已从指令执行移出', false, '分组没找到'); return; }
  var ieSeg = js.slice(z2, c2);
  ck('需求 carplay/hicar 已从指令执行移出',
     ieSeg.indexOf('导出carplay音频文件') < 0
     && ieSeg.indexOf('打开HiCarSDK日志') < 0
     && ieSeg.indexOf('打开carplay音频') < 0);
  // 2026-11-20（第 5 批需求 16）：分组顺序整页重排，改为按用户给定的 11 项顺序断言。
  //   指令执行 / 网联服务 / 手车互联 / 语音助手 / 智驾出行 /
  //   方控按键 / Tbox / Scrcpy投屏 / Apk管理 / 网络模拟 / 自定义指令
  var ORDER = ['指令执行','网联服务','手车互联','语音助手','智驾出行',
               '方控按键','Tbox','Scrcpy投屏','Apk管理','网络模拟','自定义指令'];
  var pos = [];
  var orderOk = true;
  for (var oi = 0; oi < ORDER.length; oi++){
    var at = js.indexOf("name:'" + ORDER[oi] + "'");
    pos.push(at);
    if (at < 0) orderOk = false;
  }
  for (var pi = 1; pi < pos.length; pi++){
    if (pos[pi] < pos[pi-1]) orderOk = false;
  }
  ck('需求 11 个分组按指定顺序排列（需求16）', orderOk, pos.join(','));

  // 手车互联现在紧跟网联服务，在语音助手之前（不再是"在方控之后"）
  var ws2 = js.indexOf("name:'网联服务'");
  var vc2 = js.indexOf("name:'语音助手'");
  ck('需求 手车互联组在网联服务之后、语音助手之前',
     z2 >= 0 && c2 > ws2 && vc2 > c2);
})();

ck('需求 旧的「环境切换」卡片已移除（与环境组重复）',
   !/name:'环境切换'/.test(js));
(function(){
  // 方控卡片不能出现在「指令执行」分组区间里（否则又混回去了）
  var z = js.indexOf("name:'指令执行'");
  var fk = js.indexOf("name:'方控按键'");
  var yy = js.indexOf("name:'语音助手'");
  // 2026-11-20（第 5 批需求 16）：方控现在排在语音助手之后，只要仍在指令执行之后即可
  ck('需求 方控组在指令执行之后（且不早于语音助手）',
     z >= 0 && fk > z && fk > yy);
  ck('需求 方控命令未混入指令执行',
     z >= 0 && js.slice(z, fk).indexOf(':fk') < 0);
})();
ck('需求 旧的「环境切换」卡片已移除（与环境组重复）',
   !/name:'环境切换'/.test(js));

// ---- 12. 2026-11-12 需求：删分组 / 语音输出 / 日志等级分色 / 方控长短按与左右星号 ----
console.log('\n== 12. 2026-11-12 需求 ==');
// R1：五个分组整体删除
ck('R1 应用操作分组已删除', js.indexOf("name:'应用操作'") < 0);
ck('R1 设备信息分组已删除', js.indexOf("name:'设备信息'") < 0);
ck('R1 性能监控分组已删除', js.indexOf("name:'性能监控'") < 0);
ck('R1 系统控制分组已删除', js.indexOf("name:'系统控制'") < 0);
ck('R1 文件管理分组已删除', js.indexOf("name:'文件管理'") < 0);
ck('R1 保留主题模式 黑夜/白天命令', js.indexOf("name:'黑夜模式'") >= 0 && js.indexOf("name:'白天模式'") >= 0);
// R2：语音输入/语音输出互斥按钮
ck('R2 有语音输入按钮', src.indexOf('id="vrmode-in"') >= 0);
ck('R2 有语音输出按钮', src.indexOf('id="vrmode-out"') >= 0);
ck('R2 有 setVrMode 函数', js.indexOf('function setVrMode(') >= 0);
ck('R2 输出模式拼 :vr tts', js.indexOf("':vr tts '") >= 0);
ck('R2 默认语音输入', js.indexOf("setVrMode('in')") >= 0);
// R4：日志等级按 V/D/I/W/E 分色
ck('R4 日志等级分色 CSS（E 红）', src.indexOf('.logpill[data-lv="E"]') >= 0);
ck('R4 setLogLevel 写 data-lv', js.indexOf("setAttribute('data-lv'") >= 0);
ck('R4 空等级时移除 data-lv', js.indexOf("removeAttribute('data-lv'") >= 0);
// R3：一键截图卡片走内置校验路径 :shot
ck('R3 一键截图卡走 :shot', /name:'一键截图'[^}]*cmd:':shot'/.test(js));

// ---- 13. 2026-11-15 Apple UI：零硬编码色 / 三态降级 ----
console.log('\n== 13. Apple UI 换肤 ==');
ck('Apple 分组颜色零硬编码', !/color:'#[0-9a-fA-F]{3,8}'/.test(js));
ck('Apple 三处旧品牌色全清零',
   !/#3fb99b|#e8a33d|#a8761f/i.test(src));
// 基础定义 3 处 + prefers-contrast 覆盖 3 处 = 6 处，按主题名去重判断
ck('Apple 三态主题令牌齐备',
   ['dark','light','eye'].every(function(t){
     return src.indexOf(':root[data-theme="' + t + '"]') >= 0;
   }));
ck('Apple 三套无障碍降级齐备',
   ['prefers-reduced-motion','prefers-reduced-transparency','prefers-contrast']
     .every(function(q){ return src.indexOf(q) >= 0; }));
ck('Apple 图标全部 currentColor',
   !/(?:stroke|fill)="#[0-9a-fA-F]{3,8}"/i.test(src));

// ---- 14. 2026-11-15 A9 追加轮：9 色强调色（与明暗主题正交）----
console.log('\n== 14. 16 色强调色切换器 ==');
var accRules = (srcNoCmt.match(/:root\[data-theme="\w+"\]\[data-accent="\w+"\]/g) || []).length;
ck('Accent 16 色顺序冻结（色相环 + 三白）',
   src.indexOf("var ACCENT_ORDER = ['blue','cyan','teal','mint','green','yellow','orange','red','pink','purple','indigo','brown','graphite','purewhite','eyewhite','glasswhite'];") >= 0);
ck('Accent 48 条 主题×色 令牌规则齐备（16 色 × 3 套）', accRules === 48, '实际 ' + accRules);
ck('顶栏色板 16 个可点色点',
   (src.match(/class="accent-dot[^"]*" data-accent=/g) || []).length === 16);
ck('切色只改 data-accent，不改 data-theme',
   src.indexOf("document.documentElement.setAttribute('data-accent', name)") >= 0);
ck('accent 消息双向链路（post + onMessage）',
   src.indexOf("post('accent', name)") >= 0 && src.indexOf("case 'accent': applyAccent") >= 0);
ck('主按钮 / 选中页签填充引用 --accent',
   /\.btn\.primary\{[^}]*background:var\(--accent\)/.test(srcNoCmt) &&
   /\.tabs \.tab\.active\{[^}]*background:var\(--accent\)/.test(srcNoCmt));
ck('滑块 / radio 跟随 accent',
   /input\[type=range\]\{accent-color:var\(--accent\);\}/.test(srcNoCmt));
ck('ACCENT LAYER 由生成器维护（可复跑）',
   src.indexOf('/* === ACCENT LAYER START === */') >= 0 &&
   src.indexOf('/* === ACCENT LAYER END === */') >= 0);

// ---- T4（2026-11-19）：无设备时进界面的兜底不能超过 5 秒 ----
ck('启动层兜底 <= 5000ms（T4）',
   /setTimeout\(hideSplash,\s*(\d+)\)/.test(src) &&
   parseInt(/setTimeout\(hideSplash,\s*(\d+)\)/.exec(src)[1], 10) <= 5000,
   /setTimeout\(hideSplash,\s*(\d+)\)/.exec(src) ? '实际 ' + /setTimeout\(hideSplash,\s*(\d+)\)/.exec(src)[1] + 'ms' : '没找到');

// ---- T6（2026-11-19）：APK 查询按钮必须进按钮映射，否则 HTML 上的 disabled 永远没人清 ----
ck('apk-btn-query 已进 APK_BTNS 映射（T6）',
   /APK_BTNS\s*=\s*\{[^}]*apk-btn-query/.test(src));
ck('三处「清空数据」已改为「清理数据」（T6）',
   src.indexOf('清空数据') === -1, '仍有 ' + (src.match(/清空数据/g) || []).length + ' 处');

// ---- T11（2026-11-19）：圆角只用数值刻度令牌，不再散落字面量 ----
// 例外只有 1px（刻意保留的近直角，用于极窄元素）。
var _radLit = (srcNoCmt.match(/border-radius:\s*(\d+)px/g) || []);
var _radBad = _radLit.filter(function (x) { return !/\b1px\b/.test(x); });
ck('圆角字面量已全部折算成令牌（T11）', _radBad.length === 0, _radBad.slice(0, 6).join(' '));
ck('圆角刻度令牌齐备（--r-1..--r-6）',
   ['--r-1:4px', '--r-2:6px', '--r-3:8px', '--r-4:10px', '--r-5:12px', '--r-6:16px']
     .every(function (t) { return src.indexOf(t) >= 0; }));

// ---- T9（2026-11-19）：非自定义分组内指令 name 不许重复（DOM 级断言在 _check_a14.py） ----
ck('airec 卡片只保留一张（T9）', (src.match(/cmd:'airec'/g) || []).length === 1);

console.log('');
console.log(FAIL === 0 ? '  ui.html 静态自检全部通过' : '  失败 ' + FAIL + ' 项');process.exit(FAIL === 0 ? 0 : 1);
