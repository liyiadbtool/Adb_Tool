# -*- coding: utf-8 -*-
"""T14b-⑤ 路径栏编辑：改用内联 onkeydown + 全局函数。

原因：addEventListener 的闭包版本在无头环境里不稳定（测试里 dispatch 后没进处理函数），
而且内联写法能被静态扫描到、也能被门禁登记，可测性更好。
"""
import io

P = r"C:\Users\SunWwei\Desktop\Adb_Tool\adb_log_gui\webview2\ui.html"
s = io.open(P, encoding="utf-8").read()

old = """/* ⑤ 路径栏双击可编辑：回车跳转，Esc 取消。
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
}"""

new = """/* ⑤ 路径栏双击可编辑：回车跳转，Esc 取消。
   为什么不做常驻输入框：面包屑本身可点，再并排一个输入框会挤掉搜索框。
   为什么用内联 onkeydown 而不是 addEventListener：闭包版在无头环境下不稳定
   （dispatch 之后没进处理函数，实测），内联写法则一定能被触发，也便于门禁登记。 */
function fsPathEdit(ev, side){
  if (ev) { ev.preventDefault(); ev.stopPropagation(); }
  var crumb = document.getElementById('crumb-' + side);
  if (!crumb || crumb.querySelector('.fs-pathin')) return;
  var cur = fsCurrentDir(side) || (side === 'dev' ? '/' : '');
  crumb.setAttribute('data-bak', crumb.innerHTML);   // 原面包屑暂存，Esc 时还原

  crumb.innerHTML = '<input class="fs-pathin" spellcheck="false" value="' + escAttr(cur) +
                    '" placeholder="输入路径后回车，Esc 取消" ' +
                    'onkeydown="fsPathDone(event,\\'' + escAttr(side) + '\\')" ' +
                    'onblur="fsPathDone(event,\\'' + escAttr(side) + '\\')">';
  var inp = crumb.querySelector('.fs-pathin');
  try { inp.focus(); inp.select(); } catch (e) {}
}

/* 路径输入的收尾：Enter 跳转、Esc 还原、失焦也还原 */
function fsPathDone(ev, side){
  var crumb = document.getElementById('crumb-' + side);
  if (!crumb) return;
  var inp = crumb.querySelector('.fs-pathin');
  if (!inp) return;                                  // 已经收尾过了
  var key = (ev && ev.key) || '';
  if (key && key !== 'Enter' && key !== 'Escape') return;

  var v = (inp.value || '').trim();
  var bak = crumb.getAttribute('data-bak') || '';
  crumb.innerHTML = bak;
  crumb.removeAttribute('data-bak');
  if (key !== 'Enter' || !v) return;

  var st = _fs[side];
  if (!st) return;
  var p = fsNorm(v);
  st.nodes[p] = st.nodes[p] || { e:{ name:p, path:p, dir:true }, children:null,
                                 expanded:false, loading:false, err:'', shown:FS_PAGE };
  st.nodes[p].loading = true;
  st.nodes[p].expanded = true;
  renderFs(side);
  fsRequest(side, p);
}"""

assert s.count(old) == 1, "fsPathEdit 没匹配上"
s = s.replace(old, new)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("路径编辑改为内联 onkeydown + 全局 fsPathDone")
