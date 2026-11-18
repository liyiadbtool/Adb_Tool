# -*- coding: utf-8 -*-
"""377/_ui_drive.py —— 交互测试的"人手模拟"工具（T17）。

为什么要有它：
  规格书 T2 铁律：涉及下拉/按钮选择的回归**禁止直接 dispatchEvent(click)**，
  必须走真实鼠标序列 mousedown → 断言浮层仍在 → mouseup → click。
  历史事故就是这么来的：直接派发 click 绕过了 mousedown 阶段，浮层被关闭的 bug
  一直"通过"。规矩靠人记不住，所以把它变成**唯一入口**：断言里只能调用这里的函数。

用法（在注入到页面里的 JS 中，先调 _ui_drive 注入的那段 JS）：
    const r = await drive.click('#set-font');        // 完整鼠标序列
    await drive.mouseDown(el); await drive.mouseUp(el); await drive.clickAt(el);
    await drive.key(el, 'ArrowDown'); await drive.press('Enter');
    await drive.typeInto(el, 'abc');                // 逐字符 input 事件
    await drive.waitSteady();                       // 等 .frame 进入稳态

设计约束：
  · 全部基于真实事件类型（mousedown/mouseup/click/keydown/input），坐标取元素中心；
  · 每个动作后让出一帧（await raf），保证页面有机会处理，避免"同一 tick 里改变量";
  · 不碰任何业务状态，只驱动 DOM。
"""

# 注入到测试页 <script> 里的运行时（ES5 语法，兼容 WebView2 老内核）
JS = r"""
(function(){
  function raf(cb){ try{ requestAnimationFrame(function(){ cb(); }); }catch(e){ setTimeout(cb, 16); } }
  function center(el){
    var r = el.getBoundingClientRect();
    return { x: Math.round(r.left + r.width/2), y: Math.round(r.top + r.height/2) };
  }
  function mouse(el, type){
    var c = center(el);
    el.dispatchEvent(new MouseEvent(type, {
      bubbles: true, cancelable: true, view: window,
      clientX: c.x, clientY: c.y, button: 0
    }));
  }
  function keyEv(el, type, key, modifiers){
    var m = modifiers || {};
    el.dispatchEvent(new KeyboardEvent(type, {
      key: key, bubbles: true, cancelable: true,
      ctrlKey: !!m.ctrl, shiftKey: !!m.shift, altKey: !!m.alt, metaKey: !!m.meta
    }));
  }

  var drive = window.drive = {};

  drive.q = function(sel){ return (typeof sel === 'string') ? document.querySelector(sel) : sel; };

  drive.mouseDown = function(sel){ var el = drive.q(sel); if(!el) throw new Error('找不到元素 ' + sel); mouse(el, 'mousedown'); return el; };
  drive.mouseUp   = function(sel){ var el = drive.q(sel); if(!el) throw new Error('找不到元素 ' + sel); mouse(el, 'mouseup');   return el; };
  drive.clickAt   = function(sel){ var el = drive.q(sel); if(!el) throw new Error('找不到元素 ' + sel); mouse(el, 'click');     return el; };

  /* 完整鼠标序列：down → up → click。要点：down 与 click 之间页面不得把节点摘掉，
     否则 click 派发不到（T2 的 bug 就死在这一步）。 */
  drive.click = function(sel){
    var el = drive.mouseDown(sel);
    drive.mouseUp(el);
    drive.clickAt(el);
    return el;
  };

  /* 按住不放（用于验证"按下不松手时浮层还在"） */
  drive.pressAndHold = function(sel){ return drive.mouseDown(sel); };
  drive.release = function(sel){ var el = drive.mouseUp(sel); drive.clickAt(el); return el; };

  drive.key = function(sel, key, modifiers){ var el = drive.q(sel) || document.activeElement || document.body; keyEv(el, 'keydown', key, modifiers); keyEv(el, 'keyup', key, modifiers); return el; };
  drive.press = function(key, modifiers){ return drive.key(document.activeElement || document.body, key, modifiers); };

  /* 逐字符输入：每个字符都派发 input 事件，等价用户敲键盘（受控组件才会响应） */
  drive.typeInto = function(sel, text){
    var el = drive.q(sel); if(!el) throw new Error('找不到元素 ' + sel);
    el.focus();
    el.value = '';
    for (var i = 0; i < text.length; i++){
      el.value += text.charAt(i);
      el.dispatchEvent(new Event('input', { bubbles: true }));
    }
    return el;
  };

  /* 等页面进入稳态：.frame 有 show 且 opacity=1（启动过渡走完）。
     上限 6s —— 超时就让调用方自己判，不要静默变成"永远等下去"。 */
  drive.waitSteady = function(){
    return new Promise(function(resolve){
      var t0 = Date.now();
      (function poll(){
        var fr = document.getElementById('frame');
        var ok = fr && fr.classList.contains('show') && getComputedStyle(fr).opacity === '1';
        if (ok || Date.now() - t0 > 6000) { raf(function(){ resolve(ok); }); return; }
        setTimeout(poll, 50);
      })();
    });
  };
})();
"""


def inject_js() -> str:
    """返回要插进测试页的 <script> 片段（放在断言脚本之前）。"""
    return "<script>%s</script>" % JS
