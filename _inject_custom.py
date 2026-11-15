# -*- coding: utf-8 -*-
"""注入「自定义 ADB 指令」前端层（CSS / HTML / JS），可重复执行。

协议（先定协议再写实现）：
  数据模型 def = {id, name(必填), desc(选填), steps:[
      {t:'cmd',   v:'一行或多行 adb 命令（换行=多条）'},
      {t:'delay', ms:1000},     // 官方节点：执行间隔
      {t:'loop',  n:3}          // 官方节点：重复「上一条 adb 指令」n 次
  ]}
  校验：第一行必须是 cmd；节点不能连续；至少一条命令。
  持久化：整表 JSON -> base64 -> post('customsave', b64)；C# 不解析只存取。
  执行：展开成线性队列，逐条 post('quick', line)（复用既有 SubmitCmd 链路，
        原生输出/失败提示照常回输出框）；用 end 消息驱动下一条，失败也继续 = 跳过。
"""
import io
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")

CSS = r"""
/* === CUSTOM LAYER START === */
/* 2026-11-15 自定义 ADB 指令：全部只用语义令牌，随 9 色 accent 与三态明暗自适应 */
.cm-panel{display:flex;flex-direction:column;gap:14px;padding:16px;overflow:auto;min-height:0;}
.cm-head{display:flex;align-items:center;gap:12px;}
.cm-title{font-size:15px;font-weight:600;color:var(--text);letter-spacing:.2px;}
.cm-sub{font-size:12px;color:var(--text-faint);margin-top:4px;line-height:1.7;}
.cm-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));
  gap:12px;align-content:start;}
.cm-card{cursor:pointer;}
.cm-card .qname{font-size:13px;font-weight:600;}
.cm-meta{font-size:11px;color:var(--text-faint);margin-top:9px;letter-spacing:.2px;}
.cm-empty{grid-column:1/-1;padding:28px 16px;border:1px dashed var(--border-strong);
  border-radius:var(--r-md);color:var(--text-faint);font-size:13px;line-height:1.9;text-align:center;}
.cm-mgr{position:fixed;inset:0;z-index:96;background:var(--scrim);
  display:flex;align-items:center;justify-content:center;}
.cm-box{width:880px;max-width:92vw;max-height:88vh;display:flex;flex-direction:column;
  background:var(--surface);border:1px solid var(--border-strong);
  border-radius:var(--r-lg);box-shadow:var(--shadow-lg);overflow:hidden;}
.cm-mgr-head{display:flex;align-items:center;gap:12px;padding:14px 18px;
  border-bottom:1px solid var(--border);font-size:14px;font-weight:600;color:var(--text);}
.cm-mgr-head .cm-hint{font-weight:400;color:var(--text-faint);font-size:12px;}
.cm-mgr-head .x{margin-left:auto;width:28px;height:28px;border:none;
  border-radius:var(--r-sm);background:none;color:var(--text-faint);
  font-size:18px;line-height:1;cursor:pointer;}
@media (hover:hover){ .cm-mgr-head .x:hover{background:var(--surface-2);color:var(--text);} }
.cm-body{flex:1;min-height:0;overflow:auto;padding:16px 18px;
  display:flex;flex-direction:column;gap:16px;}
.cm-list{max-height:150px;overflow:auto;border:1px solid var(--border);
  border-radius:var(--r-md);background:var(--surface-2);}
.cm-list-empty{padding:14px;color:var(--text-faint);font-size:12px;}
.cm-list-row{display:flex;align-items:center;gap:10px;padding:8px 12px;
  border-bottom:1px solid var(--border);font-size:13px;}
.cm-list-row:last-child{border-bottom:none;}
.cm-list-name{font-weight:600;color:var(--text);min-width:110px;}
.cm-list-desc{flex:1;min-width:0;color:var(--text-faint);overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap;}
.cm-field{display:flex;align-items:center;gap:12px;margin-bottom:10px;}
.cm-field label{width:56px;flex:0 0 auto;font-size:12px;color:var(--text-dim);}
.cm-field label b{color:var(--err);font-weight:600;}
.cm-field input{flex:1;height:38px;padding:0 12px;border:1px solid var(--border);
  border-radius:var(--r-sm);background:var(--bg);color:var(--text);font-size:13px;}
.cm-field input:focus{outline:none;border-color:var(--accent);
  box-shadow:0 0 0 3px var(--accent-soft);}
.cm-steps-head{font-size:12px;font-weight:600;color:var(--text-dim);
  margin:6px 0 8px;letter-spacing:.3px;}
.cm-steps{display:flex;flex-direction:column;gap:8px;}
.cm-step{display:flex;align-items:flex-start;gap:10px;padding:10px;
  border:1px solid var(--border);border-radius:var(--r-sm);background:var(--surface-2);}
.cm-no{flex:0 0 auto;width:24px;height:24px;border-radius:50%;
  background:var(--accent-soft);color:var(--accent);font-size:11px;font-weight:600;
  display:flex;align-items:center;justify-content:center;margin-top:8px;}
.cm-kind{flex:0 0 auto;width:76px;margin-top:8px;font-size:11px;font-weight:600;
  color:var(--text-dim);}
.cm-kind.node{color:var(--accent);}
.cm-val{flex:1;min-width:0;min-height:60px;padding:9px 11px;resize:vertical;
  border:1px solid var(--border);border-radius:var(--r-sm);
  background:var(--bg);color:var(--text);font-family:var(--font-mono);
  font-size:12px;line-height:1.6;}
.cm-val:focus{outline:none;border-color:var(--accent);
  box-shadow:0 0 0 3px var(--accent-soft);}
.cm-num{width:110px;height:38px;padding:0 10px;border:1px solid var(--border);
  border-radius:var(--r-sm);background:var(--bg);color:var(--text);font-size:13px;}
.cm-unit{align-self:center;font-size:12px;color:var(--text-faint);}
.cm-tip{align-self:center;font-size:11px;color:var(--text-faint);line-height:1.5;}
.cm-del{flex:0 0 auto;width:28px;height:28px;margin-top:6px;border:none;
  border-radius:var(--r-sm);background:none;color:var(--text-faint);
  font-size:16px;cursor:pointer;}
@media (hover:hover){ .cm-del:hover{background:var(--err-soft);color:var(--err);} }
.cm-addrow{display:flex;gap:8px;margin-top:10px;flex-wrap:wrap;}
.cm-err{min-height:18px;margin-top:8px;color:var(--err);font-size:12px;}
.cm-foot{display:flex;align-items:center;gap:8px;padding:12px 18px;
  border-top:1px solid var(--border);}
.cm-foot .spacer{flex:1;}
@media (prefers-reduced-motion:reduce){
  .cm-box,.cm-mgr{animation:none !important;transition:none !important;}
}
/* === CUSTOM LAYER END === */
"""

PANEL_HTML = r"""          <!-- 2026-11-15 自定义 ADB 指令面板：与 apk / netsim 同一套 panel 机制 -->
          <div class="cm-panel" id="custom-panel" style="display:none;">
            <div class="cm-head">
              <div>
                <div class="cm-title">自定义 ADB 指令</div>
                <div class="cm-sub">自定义命令一键下发；支持多行按顺序执行、失败跳过，
                  以及「延时 / 循环」两个官方节点。失败命令的原始回显照常显示在下方「输出」区。</div>
              </div>
              <div class="spacer"></div>
              <button class="btn primary" onclick="openCustomMgr()">＋ 新建指令</button>
            </div>
            <div class="cm-grid" id="cm-grid"></div>
          </div>

"""

MGR_HTML = r"""<!-- 2026-11-15 自定义 ADB 指令编辑弹窗（参考 APK 管理应用列表） -->
<div class="cm-mgr" id="custom-mgr" style="display:none;" onclick="cmBackdrop(event)">
  <div class="cm-box" onclick="event.stopPropagation()">
    <div class="cm-mgr-head">
      <span>自定义 ADB 指令</span>
      <span class="cm-hint">名称必填 · 第一行必须是命令 · 节点需间隔命令</span>
      <button class="x" onclick="closeCustomMgr()" title="关闭">×</button>
    </div>
    <div class="cm-body">
      <div class="cm-list" id="cm-list"></div>
      <div class="cm-form">
        <div class="cm-field"><label>名称 <b>*</b></label>
          <input id="cm-name" placeholder="例如：重启并清缓存" maxlength="40" autocomplete="off"></div>
        <div class="cm-field"><label>说明</label>
          <input id="cm-desc" placeholder="选填；不填则卡片上不显示说明" maxlength="120" autocomplete="off"></div>
        <div class="cm-steps-head">执行流程（每行一条；ADB 命令可在一个框内换行输入多条）</div>
        <div class="cm-steps" id="cm-steps"></div>
        <div class="cm-addrow">
          <button class="btn ghost sm" onclick="cmAddStep('cmd')">＋ 添加命令</button>
          <button class="btn ghost sm" onclick="cmAddStep('delay')">＋ 延时节点</button>
          <button class="btn ghost sm" onclick="cmAddStep('loop')">＋ 循环节点</button>
        </div>
        <div class="cm-err" id="cm-err"></div>
      </div>
    </div>
    <div class="cm-foot">
      <button class="btn ghost sm" onclick="cmNew()">清空表单</button>
      <div class="spacer"></div>
      <button class="btn" onclick="closeCustomMgr()">关闭</button>
      <button class="btn primary" onclick="cmSave()">保存</button>
    </div>
  </div>
</div>

"""

JS = r"""
/* ==================================================================
   2026-11-15 · 自定义 ADB 指令
   协议见 _inject_custom.py 顶部说明。所有函数全局可见，便于 DOM 自测。
   ================================================================== */
var _customDefs = [];
var _customDraft = null;
var _customEditId = null;
var _customQueue = [];
var _customIdx = -1;
var _customRunning = false;
var _customOk = 0;
var _customFail = 0;

function _customB64Encode(obj){
  return btoa(unescape(encodeURIComponent(JSON.stringify(obj))));
}
function _customB64Decode(b64){
  if(!b64) return [];
  try{
    var a = JSON.parse(decodeURIComponent(escape(atob(b64))));
    return Object.prototype.toString.call(a) === '[object Array]' ? a : [];
  }catch(e){ return []; }
}
function customSaveDefs(){
  try{ post('customsave', _customB64Encode(_customDefs)); }catch(e){}
}
function customLoadDefs(b64){
  _customDefs = _customB64Decode(b64);
  renderCustomCards();
  renderCustomList();
}
function customFind(id){
  for(var i=0;i<_customDefs.length;i++) if(_customDefs[i].id === id) return _customDefs[i];
  return null;
}

/* 校验：名称必填 / 第一行必须是 adb 命令 / 官方节点必须间隔一条命令 */
function customValidate(name, steps){
  if(!String(name||'').trim()) return '名称必填';
  if(!steps || !steps.length) return '至少添加一条 adb 命令';
  if(steps[0].t !== 'cmd' || !String(steps[0].v||'').replace(/\s/g,''))
    return '第一行必须是 adb 命令，不能是官方节点';
  var prevNode = false, hasCmd = false;
  for(var i=0;i<steps.length;i++){
    var st = steps[i];
    if(st.t === 'cmd'){
      if(!String(st.v||'').replace(/\s/g,'')) return '第 ' + (i+1) + ' 行命令不能为空';
      hasCmd = true; prevNode = false;
    }else{
      if(prevNode) return '官方节点不能连续，中间必须间隔一条 adb 命令';
      prevNode = true;
      if(st.t === 'delay' && !(parseInt(st.ms,10) > 0)) return '第 ' + (i+1) + ' 行延时毫秒数要大于 0';
      if(st.t === 'loop' && !(parseInt(st.n,10) >= 2)) return '第 ' + (i+1) + ' 行循环次数至少 2 次';
    }
  }
  if(!hasCmd) return '至少添加一条 adb 命令';
  return '';
}

/* 把流程展开成线性队列：命令按换行拆条；延时原样；循环重复「上一条命令」n 次 */
function customExpand(def){
  var q = [], last = '';
  var steps = (def && def.steps) || [];
  for(var i=0;i<steps.length;i++){
    var st = steps[i];
    if(st.t === 'cmd'){
      var lines = String(st.v||'').split(/\r?\n/);
      for(var k=0;k<lines.length;k++){
        var ln = lines[k].trim();
        if(!ln) continue;
        q.push({t:'cmd', v:ln});
        last = ln;
      }
    }else if(st.t === 'delay'){
      q.push({t:'delay', ms: Math.max(0, parseInt(st.ms,10)||0)});
    }else if(st.t === 'loop'){
      var n = Math.max(2, Math.min(99, parseInt(st.n,10)||2));
      if(last) for(var z=0;z<n;z++) q.push({t:'cmd', v:last});
    }
  }
  return q;
}

/* 执行：逐条复用 quick 链路；end 消息驱动下一条，失败也继续（= 跳过） */
function customRun(id){
  var def = customFind(id);
  if(!def) return;
  if(_customRunning){ toast('已有自定义流程在执行，请稍候'); return; }
  var q = customExpand(def);
  if(!q.length){ toast('这个流程没有可执行的命令'); return; }
  _customQueue = q; _customIdx = -1; _customRunning = true;
  _customOk = 0; _customFail = 0;
  customNext();
}
function customNext(){
  if(!_customRunning) return;
  _customIdx++;
  if(_customIdx >= _customQueue.length){ customFinish(); return; }
  var st = _customQueue[_customIdx];
  if(st.t === 'delay'){ setTimeout(customNext, st.ms); return; }
  try{ post('quick', st.v); }catch(e){ setTimeout(customNext, 30); }
}
function customOnEnd(msg){
  if(!_customRunning) return;
  if(msg && msg.busy){ _customIdx--; setTimeout(customNext, 150); return; }
  if(msg && msg.ok) _customOk++; else _customFail++;
  setTimeout(customNext, 30);
}
function customFinish(){
  _customRunning = false;
  toast('自定义流程结束：成功 ' + _customOk + ' / 失败 ' + _customFail +
        '（失败命令的原始回显见输出区）');
}

/* ---- 卡片（与快捷指令 .qcard 同规范；无说明则不渲染说明行）---- */
function renderCustomCards(){
  var grid = document.getElementById('cm-grid');
  if(!grid) return;
  if(!_customDefs.length){
    grid.innerHTML = '<div class="cm-empty">还没有自定义指令。<br>'
      + '点「＋ 新建指令」，填名称、说明和 adb 命令，保存后这里会出现可一键下发的卡片。</div>';
    return;
  }
  var h = '';
  for(var i=0;i<_customDefs.length;i++){
    var d = _customDefs[i];
    h += '<div class="qcard cm-card" data-id="' + escAttr(d.id) + '" title="点击执行">'
      +  '<div class="qhead"><span class="qico">' + ICON_PLAY + '</span>'
      +  '<span class="qname">' + escHtml(d.name) + '</span></div>'
      +  (d.desc ? '<div class="qcmd">' + escHtml(d.desc) + '</div>' : '')
      +  '<div class="cm-meta">' + customExpand(d).length + ' 步 · 点击执行</div>'
      +  '</div>';
  }
  grid.innerHTML = h;
}
function renderCustomList(){
  var box = document.getElementById('cm-list');
  if(!box) return;
  if(!_customDefs.length){ box.innerHTML = '<div class="cm-list-empty">还没有保存的指令</div>'; return; }
  var h = '';
  for(var i=0;i<_customDefs.length;i++){
    var d = _customDefs[i];
    h += '<div class="cm-list-row"><span class="cm-list-name">' + escHtml(d.name) + '</span>'
      +  '<span class="cm-list-desc">' + escHtml(d.desc || '') + '</span>'
      +  '<button class="btn ghost sm" onclick="cmEdit(\'' + escAttr(d.id) + '\')">编辑</button>'
      +  '<button class="btn ghost sm" onclick="cmDel(\'' + escAttr(d.id) + '\')">删除</button></div>';
  }
  box.innerHTML = h;
}

/* ---- 编辑器 ---- */
function cmErr(t){ var e = document.getElementById('cm-err'); if(e) e.textContent = t || ''; }
function openCustomMgr(){
  var m = document.getElementById('custom-mgr');
  if(m) m.style.display = 'flex';
  cmNew();
}
function closeCustomMgr(){ var m = document.getElementById('custom-mgr'); if(m) m.style.display = 'none'; }
function cmBackdrop(ev){ if(ev && ev.target && ev.target.id === 'custom-mgr') closeCustomMgr(); }
function cmNew(){
  _customEditId = null;
  _customDraft = { name:'', desc:'', steps:[{t:'cmd', v:''}] };
  var n = document.getElementById('cm-name'); if(n) n.value = '';
  var d = document.getElementById('cm-desc'); if(d) d.value = '';
  cmErr(''); renderCustomSteps();
}
function cmEdit(id){
  var d = customFind(id);
  if(!d) return;
  _customEditId = id;
  _customDraft = { name:d.name, desc:d.desc || '', steps:[] };
  for(var i=0;i<d.steps.length;i++){
    var s = d.steps[i];
    _customDraft.steps.push(s.t === 'cmd' ? {t:'cmd', v:s.v}
      : s.t === 'delay' ? {t:'delay', ms:s.ms} : {t:'loop', n:s.n});
  }
  var n = document.getElementById('cm-name'); if(n) n.value = d.name;
  var de = document.getElementById('cm-desc'); if(de) de.value = d.desc || '';
  cmErr(''); renderCustomSteps();
}
function cmDel(id){
  var d = customFind(id);
  if(!d) return;
  if(!confirm('确定删除「' + d.name + '」？')) return;
  var next = [];
  for(var i=0;i<_customDefs.length;i++) if(_customDefs[i].id !== id) next.push(_customDefs[i]);
  _customDefs = next;
  customSaveDefs(); renderCustomCards(); renderCustomList();
  if(_customEditId === id) cmNew();
  toast('已删除');
}
function cmAddStep(t){
  if(!_customDraft) return;
  var st = _customDraft.steps;
  if(!st.length && t !== 'cmd'){ cmErr('第一行必须是 adb 命令'); return; }
  if(t !== 'cmd' && st.length && st[st.length-1].t !== 'cmd'){
    cmErr('官方节点不能连续，中间要隔一条 adb 命令'); return;
  }
  if(t === 'cmd') st.push({t:'cmd', v:''});
  else if(t === 'delay') st.push({t:'delay', ms:1000});
  else st.push({t:'loop', n:3});
  cmErr(''); renderCustomSteps();
}
function cmDelStep(i){
  if(!_customDraft) return;
  _customDraft.steps.splice(i, 1);
  renderCustomSteps();
}
/* 输入只更新数据，绝不重建 DOM（否则输入框会失焦） */
function cmOnInput(el){
  if(!_customDraft || !el) return;
  var i = parseInt(el.getAttribute('data-i'), 10);
  var st = _customDraft.steps[i];
  if(!st) return;
  var t = el.getAttribute('data-t');
  if(t === 'cmd') st.v = el.value;
  else if(t === 'delay') st.ms = el.value;
  else if(t === 'loop') st.n = el.value;
  cmErr('');
}
function renderCustomSteps(){
  var box = document.getElementById('cm-steps');
  if(!box || !_customDraft) return;
  var h = '';
  for(var i=0;i<_customDraft.steps.length;i++){
    var st = _customDraft.steps[i];
    var kind = st.t === 'cmd' ? 'ADB 命令' : (st.t === 'delay' ? '延时' : '循环');
    var cls = st.t === 'cmd' ? '' : ' node';
    h += '<div class="cm-step" data-i="' + i + '">'
      +  '<span class="cm-no">' + (i+1) + '</span>'
      +  '<span class="cm-kind' + cls + '">' + kind + '</span>';
    if(st.t === 'cmd'){
      h += '<textarea class="cm-val" data-i="' + i + '" data-t="cmd" '
        +  'placeholder="每行一条 adb 命令，可换行输入多条" oninput="cmOnInput(this)">'
        +  escHtml(st.v || '') + '</textarea>';
    }else if(st.t === 'delay'){
      h += '<input type="number" class="cm-num" data-i="' + i + '" data-t="delay" min="1" '
        +  'value="' + escAttr(st.ms) + '" oninput="cmOnInput(this)">'
        +  '<span class="cm-unit">ms</span>'
        +  '<span class="cm-tip">执行到这一步等待指定毫秒</span>';
    }else{
      h += '<input type="number" class="cm-num" data-i="' + i + '" data-t="loop" min="2" max="99" '
        +  'value="' + escAttr(st.n) + '" oninput="cmOnInput(this)">'
        +  '<span class="cm-unit">次</span>'
        +  '<span class="cm-tip">重复执行「上一条 adb 指令」指定次数</span>';
    }
    h += '<button class="cm-del" onclick="cmDelStep(' + i + ')" title="删除这一行">×</button></div>';
  }
  box.innerHTML = h;
}
function cmSave(){
  if(!_customDraft) return;
  var nEl = document.getElementById('cm-name'), dEl = document.getElementById('cm-desc');
  var name = String(nEl ? nEl.value : '').trim();
  var desc = String(dEl ? dEl.value : '').trim();
  _customDraft.name = name; _customDraft.desc = desc;
  var err = customValidate(name, _customDraft.steps);
  if(err){ cmErr(err); return; }
  var def = {
    id: _customEditId || ('c' + Date.now().toString(36) + Math.random().toString(36).slice(2,6)),
    name: name, desc: desc, steps: _customDraft.steps.slice()
  };
  if(_customEditId){
    for(var i=0;i<_customDefs.length;i++) if(_customDefs[i].id === _customEditId) _customDefs[i] = def;
  }else{
    _customDefs.push(def);
  }
  customSaveDefs();
  renderCustomCards(); renderCustomList(); cmNew();
  toast('已保存：' + name);
}

/* 卡片点击（事件委托）；弹层 Esc 关闭；启动拉一次持久化数据 */
(function(){
  var grid = document.getElementById('cm-grid');
  if(grid) grid.addEventListener('click', function(ev){
    var c = ev.target.closest ? ev.target.closest('.cm-card') : null;
    if(c) customRun(c.getAttribute('data-id'));
  });
  document.addEventListener('keydown', function(ev){
    if(ev.key === 'Escape'){
      var m = document.getElementById('custom-mgr');
      if(m && m.style.display !== 'none' && m.style.display !== '') closeCustomMgr();
    }
  });
  setTimeout(function(){ try{ post('customlist', ''); }catch(e){} }, 260);
})();
"""


def must(s, old, new, tag):
    if old not in s:
        raise SystemExit("注入失败：找不到锚点 " + tag)
    return s.replace(old, new, 1)


def main():
    s = io.open(UI, "r", encoding="utf-8").read()

    # 1) CSS 覆盖层（可重复执行：先删旧块再插）
    s = re.sub(r"\n/\* === CUSTOM LAYER START === \*/.*?/\* === CUSTOM LAYER END === \*/\n",
               "\n", s, flags=re.S)
    s = must(s, "</style>", CSS + "</style>", "CSS")

    # 2) 面板 HTML（可重复执行）
    s = re.sub(r"\s*<!-- 2026-11-15 自定义 ADB 指令面板.*?</div>\s*\n\s*<div class=\"cm-grid\" id=\"cm-grid\"></div>\s*\n\s*</div>\n",
               "\n", s, flags=re.S)
    s = must(s, '<div class="quick-grid" id="quick-grid"></div>',
             PANEL_HTML + '<div class="quick-grid" id="quick-grid"></div>', "PANEL")

    # 3) 弹窗 HTML（可重复执行）
    s = re.sub(r"<!-- 2026-11-15 自定义 ADB 指令编辑弹窗.*?</div>\s*\n\s*</div>\s*\n\s*</div>\s*\n",
               "", s, flags=re.S)
    s = must(s, "</body>", MGR_HTML + "</body>", "MGR")

    # 4) JS（可重复执行）
    s = re.sub(r"\n/\* =+\n   2026-11-15 · 自定义 ADB 指令.*?\n\}\)\(\);\n(?=</script>)",
               "\n", s, flags=re.S)
    s = must(s, "</script>", JS + "</script>", "JS")

    # 5) quickGroups 基础定义里加「自定义」panel 分组
    anchor = "var quickGroups = ["
    i = s.index(anchor)
    j = s.index("\n];", i)
    if "panel:'custom'" not in s[i:j]:
        # 数组最后一个元素形如 "  ]}"（网络模拟分组），追加新元素前必须补逗号，
        # 否则整段 script 会变成 Unexpected token '{'。
        head = s[i:j]
        k = head.rfind("]}")
        if k >= 0:
            ak = i + k + 2
            if s[ak:ak + 1] != ",":
                s = s[:ak] + "," + s[ak:]
                j += 1
        s = s[:j] + "\n  // 2026-11-15：用户自定义 ADB 指令，复用 panel 机制（与 apk / netsim 同源）\n" \
                    "  { name:'自定义', color:'var(--accent)', panel:'custom', items:[] }" + s[j:]

    # 6) applyServerCommands 不再往自定义分组塞 cmds.ini 卡片
    old6 = """  var base = BASE_GROUPS.slice();
  if(_serverCmds.length){
    var known = {};
    for(var g=0; g<base.length; g++){
      for(var j=0; j<base[g].items.length; j++) known[normCmd(base[g].items[j].cmd)] = 1;
    }
    // 2026-11-14：分组改名「自定义」并清空原有 cmds.ini 卡片，
    // 保留这个空分组作为后续新功能的入口（用户要求）。
    // 2026-11-14：分组改名「自定义」并**清空**原有 cmds.ini 卡片（用户要求），
    // 保留这个空分组作为后续新功能的入口；cmds.ini 的命令仍在终端页可用。
    var custom = { name:'自定义', color:'var(--accent)', items:[] };
    base.push(custom);
  }
"""
    new6 = """  var base = BASE_GROUPS.slice();
  // 2026-11-15：自定义分组已在 quickGroups 基础定义里（panel:'custom'），
  // 由用户自建的 ADB 流程填充；cmds.ini 的命令仍只在终端页可用，不再塞卡片。
"""
    s = must(s, old6, new6, "applyServerCommands")

    # 7) renderQuickItems 显示自定义面板
    old7 = """  // 网络模拟（2026-11-15）：参数表单面板，与 APK 面板同一套 panel 机制
  var nsPanel = document.getElementById('netsim-panel');
  if(nsPanel) nsPanel.style.display = (g.panel === 'netsim') ? '' : 'none';
"""
    new7 = old7 + """
  // 自定义 ADB 指令（2026-11-15）：同一套 panel 机制，显示时刷新卡片
  var cmPanel = document.getElementById('custom-panel');
  if(cmPanel){
    cmPanel.style.display = (g.panel === 'custom') ? '' : 'none';
    if(g.panel === 'custom') renderCustomCards();
  }
"""
    if "cmPanel" not in s:
        s = must(s, old7, new7, "renderQuickItems")

    # 8) onMessage：end 挂钩 + customcmds 回包
    s = must(s, "    case 'end': endRun(msg); break;            // end 字段在顶层，传整个 msg",
             "    case 'end': endRun(msg); if(_customRunning) customOnEnd(msg); break;", "case end")
    if "case 'customcmds'" not in s:
        s = must(s, "    case 'theme': applyTheme(msg.name || 'dark'); break;",
                 "    case 'theme': applyTheme(msg.name || 'dark'); break;\n"
                 "    case 'customcmds': customLoadDefs(msg.data || ''); break;", "case customcmds")

    io.open(UI, "w", encoding="utf-8", newline="").write(s)
    print("OK 自定义 ADB 指令前端已注入")


if __name__ == "__main__":
    main()
