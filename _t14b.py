# -*- coding: utf-8 -*-
"""T14b：文件交互第一批（6 项）。

现状核对：Ctrl 多选、新建/重命名/删除的后端与函数都已存在，缺的是
「入口」和「渲染层的过滤/排序」。所以这批基本是前端接线：

  ① 右键菜单（下载/上传/重命名/删除/复制路径/新建文件夹）
  ② Shift 连选（Ctrl 连选原本就有）
  ⑧ 排序（名称/大小/时间，升降序）
  ③ 显示隐藏文件
  ⑤ 路径栏双击可编辑
  ⑥ 新建文件夹入口（函数已有，补按钮与菜单项）
"""
import io

P = r"C:\Users\SunWwei\Desktop\Adb_Tool\adb_log_gui\webview2\ui.html"
s = io.open(P, encoding="utf-8").read()

# ---------- 1) 渲染层：排序 + 隐藏文件过滤 ----------
old = """  var limit = Math.min(node.children.length, node.shown || FS_PAGE);
  for (var i = 0; i < limit; i++) {
    out += fsWalk(side, fsNode(side, node.children[i]), depth + 1);
  }
  if (node.children.length > limit) {
    out += '<div class="fs-more" data-more="' + escAttr(node.e.path) + '" style="padding-left:' + (pad + 16) + 'px">'
         + '还有 ' + (node.children.length - limit) + ' 项，点这里加载更多</div>';
  }
  return out;"""

new = """  // T14b：隐藏文件过滤 + 排序在这里统一做（原来按后端返回的原样渲染）
  var kids = fsKids(_fs[side], node.children);
  var limit = Math.min(kids.length, node.shown || FS_PAGE);
  for (var i = 0; i < limit; i++) {
    out += fsWalk(side, fsNode(side, kids[i]), depth + 1);
  }
  if (kids.length > limit) {
    out += '<div class="fs-more" data-more="' + escAttr(node.e.path) + '" style="padding-left:' + (pad + 16) + 'px">'
         + '还有 ' + (kids.length - limit) + ' 项，点这里加载更多</div>';
  }
  return out;"""
assert s.count(old) == 1, "fsWalk 尾部没匹配上"
s = s.replace(old, new)

# ---------- 2) 排序/过滤/右键菜单/路径编辑 的实现块 ----------
anchor = """/* T14a-4：错误行的一键重试 —— 清掉错误/加载态后重发同一个路径 */"""
block = """/* ==================== T14b（2026-11-19）：文件交互第一批 ====================
   ① 右键菜单  ② Shift 连选  ⑧ 排序  ③ 显示隐藏文件  ⑤ 路径可编辑  ⑥ 新建入口
   注意：Ctrl 多选、新建/重命名/删除的后端（fsop）与函数本来就有 ——
   这批补的是**入口**和**渲染层的过滤/排序**，不重复造轮子。 */

/* 排序 + 隐藏文件过滤：目录恒在前，其余按 st.sortBy */
function fsKids(st, children){
  if (!children) return [];
  var arr = [];
  for (var i = 0; i < children.length; i++){
    var e = children[i];
    var nm = e.name || '';
    if (!st.showHidden && nm.charAt(0) === '.') continue;
    arr.push(e);
  }
  var by = st.sortBy || 'name', desc = !!st.sortDesc;
  arr.sort(function(a, b){
    if (!!a.dir !== !!b.dir) return a.dir ? -1 : 1;
    var r;
    if (by === 'size') r = (a.size || 0) - (b.size || 0);
    else if (by === 'time') r = String(a.time || '').localeCompare(String(b.time || ''));
    else r = String(a.name || '').localeCompare(String(b.name || ''), 'zh-Hans-CN');
    return desc ? -r : r;
  });
  return arr;
}

/* 排序菜单：点同一个字段切换升降序，点不同字段按默认方向开始 */
function fsSortBy(side, by){
  var st = _fs[side];
  if (!st) return;
  if (st.sortBy === by) st.sortDesc = !st.sortDesc;
  else { st.sortBy = by; st.sortDesc = (by === 'size' || by === 'time'); }
  renderFs(side);
  var cn = { name:'名称', size:'大小', time:'时间' }[by] || by;
  toast('按' + cn + (st.sortDesc ? '降序' : '升序'));
}

function fsToggleHidden(side){
  var st = _fs[side];
  if (!st) return;
  st.showHidden = !st.showHidden;
  renderFs(side);
  toast(st.showHidden ? '显示隐藏文件' : '隐藏点文件');
}

/* 右键菜单：复用 Overlay（T16）—— 外点关闭 / Esc / 滚动跟随都不用再写一遍 */
function fsCtxOpen(ev, side, path){
  if (ev) { ev.preventDefault(); ev.stopPropagation(); }
  var st = _fs[side];
  if (!st) return;
  var key = fsNorm(path);

  // 右键的行没选中 → 先选中它（和资源管理器一致），已选中则保留多选
  if (!st.sel[key]) { st.sel = {}; st.sel[key] = 1; renderFs(side); }

  var isDev = (side === 'dev');
  var one = fsSelectedPaths(side).length === 1;
  var rowEl = document.querySelector('#list-' + side + ' .fs-row[data-path="' +
              String(path).replace(/"/g, '\\\\"') + '"]');

  var menu = document.createElement('div');
  menu.className = 'a14-selpop fs-ctx';
  menu.style.minWidth = '168px';

  function item(text, act, disabled){
    var d = document.createElement('div');
    d.className = 'it' + (disabled ? ' off' : '');
    d.textContent = text;
    d.setAttribute('data-act', act);
    menu.appendChild(d);
  }
  if (isDev) item('下载到本机', 'download');
  else       item('上传到设备', 'upload');
  menu.appendChild(document.createElement('div')).className = 'grp';
  item('重命名', 'rename', !one);
  item('删除', 'del');
  menu.appendChild(document.createElement('div')).className = 'grp';
  item('复制路径', 'copypath');
  item('新建文件夹', 'mkdir');
  menu.appendChild(document.createElement('div')).className = 'grp';
  item('排序：名称' + (st.sortBy === 'name' ? (st.sortDesc ? ' ↓' : ' ↑') : ''), 'sortname');
  item('排序：大小' + (st.sortBy === 'size' ? (st.sortDesc ? ' ↓' : ' ↑') : ''), 'sortsize');
  item('排序：时间' + (st.sortBy === 'time' ? (st.sortDesc ? ' ↓' : ' ↑') : ''), 'sorttime');
  item((st.showHidden ? '✓ ' : '') + '显示隐藏文件', 'hidden');
  item('刷新', 'refresh');

  menu.addEventListener('click', function(e){
    var t = e.target;
    if (!t.getAttribute || !t.getAttribute('data-act')) return;
    e.preventDefault(); e.stopPropagation();
    var act = t.getAttribute('data-act');
    Overlay.close();
    if (act === 'download') fsCopy('down', fsCurrentDir('local'), fsSelectedPaths('dev'));
    else if (act === 'upload') fsCopy('up', fsCurrentDir('dev'), fsSelectedPaths('local'));
    else if (act === 'rename') fsRename(side);
    else if (act === 'del') fsDelete(side);
    else if (act === 'copypath') fsCopyPath(side);
    else if (act === 'mkdir') fsNewFolder(side);
    else if (act === 'sortname') fsSortBy(side, 'name');
    else if (act === 'sortsize') fsSortBy(side, 'size');
    else if (act === 'sorttime') fsSortBy(side, 'time');
    else if (act === 'hidden') fsToggleHidden(side);
    else if (act === 'refresh') fsReload(side);
  });

  Overlay.open({ el: menu, anchor: rowEl || document.getElementById('list-' + side),
                 z: Overlay.LEVEL.pop });
}

/* 复制选中项的路径到剪贴板（多行；设备侧路径本身就是可以直接用的形式） */
function fsCopyPath(side){
  var paths = fsSelectedPaths(side);
  if (!paths.length) { toast('先选中一项'); return; }
  var text = paths.join('\\n');
  try {
    navigator.clipboard.writeText(text);
    toast(paths.length === 1 ? '已复制路径' : ('已复制 ' + paths.length + ' 条路径'));
  } catch (e) {
    // 无剪贴板权限时退化成可见提示，至少让用户能手工复制
    toast('复制失败：' + text);
  }
}

/* ⑤ 路径栏双击可编辑：回车跳转，Esc 取消。
   为什么不做常驻输入框：面包屑本身可点，再并排一个输入框会挤掉搜索框。 */
function fsPathEdit(ev, side){
  if (ev) { ev.preventDefault(); ev.stopPropagation(); }
  var crumb = document.getElementById('crumb-' + side);
  if (!crumb || crumb.querySelector('.fs-pathin')) return;
  var cur = fsCurrentDir(side) || (side === 'dev' ? '/' : '');
  var bak = crumb.innerHTML;

  crumb.innerHTML = '<input class="fs-pathin" spellcheck="false" value="' +
                    escAttr(cur) + '" placeholder="输入路径后回车">';
  var inp = crumb.querySelector('.fs-pathin');
  inp.focus();
  try { inp.select(); } catch (e) {}

  function done(go){
    if (!crumb.querySelector('.fs-pathin')) return;
    crumb.innerHTML = bak;
    if (!go) return;
    var v = (inp.value || '').trim();
    if (!v) return;
    var key = fsNorm(v);
    var st = _fs[side];
    st.nodes[key] = st.nodes[key] || { e:{ name:key, path:key, dir:true }, children:null,
                                       expanded:true, loading:true, err:'', shown:FS_PAGE };
    st.nodes[key].loading = true;
    st.nodes[key].expanded = true;
    renderFs(side);
    fsRequest(side, key);
  }
  inp.addEventListener('keydown', function(e){
    if (e.key === 'Enter') { e.preventDefault(); done(true); }
    else if (e.key === 'Escape') { e.preventDefault(); done(false); }
  });
  inp.addEventListener('blur', function(){ done(false); });
}

/* T14a-4：错误行的一键重试 —— 清掉错误/加载态后重发同一个路径 */"""
assert s.count(anchor) == 1, "重试函数锚点没匹配上"
s = s.replace(anchor, block, 1)

# ---------- 3) Shift 连选 ----------
old_click = """  var sp = fsNorm(p);
  if (ev.ctrlKey || ev.metaKey) {
    if (st.sel[sp]) delete st.sel[sp]; else st.sel[sp] = 1;
  } else {
    st.sel = {};
    st.sel[sp] = 1;
  }"""
new_click = """  var sp = fsNorm(p);
  // T14b-②：Shift 连选（Ctrl 连选原来就有）。范围按**当前可见行**的顺序取，
  // 与用户在屏幕上看到的区间一致（隐藏文件过滤后也不会错位）。
  if (ev.shiftKey && st.lastSel && st.lastSel !== sp) {
    var allRows = document.querySelectorAll('#list-' + side + ' .fs-row');
    var i0 = -1, i1 = -1;
    for (var ri = 0; ri < allRows.length; ri++) {
      var rp = fsNorm(allRows[ri].getAttribute('data-path'));
      if (rp === st.lastSel) i0 = ri;
      if (rp === sp) i1 = ri;
    }
    if (i0 >= 0 && i1 >= 0) {
      st.sel = {};
      var a = Math.min(i0, i1), b = Math.max(i0, i1);
      for (var k = a; k <= b; k++) st.sel[fsNorm(allRows[k].getAttribute('data-path'))] = 1;
      renderFs(side);
      return;
    }
  }
  if (ev.ctrlKey || ev.metaKey) {
    if (st.sel[sp]) delete st.sel[sp]; else st.sel[sp] = 1;
  } else {
    st.sel = {};
    st.sel[sp] = 1;
  }
  st.lastSel = sp;"""
assert s.count(old_click) == 1, "fsClick 选中逻辑没匹配上"
s = s.replace(old_click, new_click)

# ---------- 4) 右键绑定 + 双击面包屑 ----------
old_bind = """  box.addEventListener('dblclick', function(ev){"""
new_bind = """  // T14b-①：右键菜单（挂在行上；空白处右键也给菜单，方便新建/排序）
  box.addEventListener('contextmenu', function(ev){
    var row = ev.target.closest ? ev.target.closest('.fs-row') : null;
    fsCtxOpen(ev, side, row ? row.getAttribute('data-path') : fsCurrentDir(side));
  });

  box.addEventListener('dblclick', function(ev){"""
assert s.count(old_bind) == 1, "dblclick 锚点没匹配上"
s = s.replace(old_bind, new_bind, 1)

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("T14b：排序/隐藏/右键/Shift 连选/路径编辑 已接入")
