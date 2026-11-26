/* ============================================================================
   Agent 工作台 · 骨架逻辑（阶段一：全假数据）

   【本阶段只验证三件事】
     1. 界面结构与主界面视觉一致
     2. 四种状态都画得出来（空 / 单步 / 多步 / 失败）
     3. 父页推主题过来时，颜色能立刻跟着变

   【不做什么】
     · 不发真实请求（阶段二才接）
     · 不依赖 adb（iframe 里没有 chrome.webview，必须父页转发）

   通信协议（阶段二启用，这里只留接收端）
     agent ← 父页  { __agent:1, type:'theme', theme, accent, accentSoft, onAccent, fsize }
     agent  → 父页  { __agent:1, type:'req', id, op, args }
     agent ← 父页  { __agent:1, type:'res', id, ok, data, err }
   ============================================================================ */

(function () {
  'use strict';

  var root = document.documentElement;

  /* ------------------------------------------------------------------
     假数据：四种状态各一个任务
     ------------------------------------------------------------------ */
  var TASKS = [
    {
      id: 't1', name: '空任务（刚创建）', state: 'idle', time: '—',
      steps: []
    },
    {
      id: 't2', name: '单步：查设备型号', state: 'done', time: '12s',
      steps: [
        { name: '读取设备型号', tool: 'adb.shell', st: 'done',
          args: 'getprop ro.product.model',
          out: 'GAC-A18-T75' }
      ]
    },
    {
      id: 't3', name: '多步：导出崩溃日志并分析', state: 'run', time: '进行中',
      steps: [
        { name: '确认设备在线', tool: 'adb.shell', st: 'done',
          args: 'adb devices',
          out: 'emulator-5554\tdevice' },
        { name: '拉取 crash 日志', tool: 'adb.logcat', st: 'done',
          args: 'logcat -b crash -d -t 200',
          out: '--------- beginning of crash\n' +
               'E/AndroidRuntime( 4821): FATAL EXCEPTION: main\n' +
               'E/AndroidRuntime( 4821): Process: space.syncore.cockpit.map\n' +
               'E/AndroidRuntime( 4821): java.lang.NullPointerException: ' +
               'Attempt to invoke virtual method on a null object reference' },
        { name: '定位异常类', tool: 'local.model', st: 'run',
          args: '分析 3 条堆栈', out: '正在分析…' },
        { name: '生成结论', tool: 'local.model', st: 'wait',
          args: '—', out: '' }
      ]
    },
    {
      id: 't4', name: '失败：安装 APK 被拒', state: 'fail', time: '8s',
      steps: [
        { name: '推送 APK', tool: 'adb.push', st: 'done',
          args: 'push app-debug.apk /data/local/tmp/',
          out: 'app-debug.apk: 1 file pushed, 12.4 MB/s (8.2 MB in 0.66s)' },
        { name: '安装', tool: 'adb.shell', st: 'fail',
          args: 'pm install -r /data/local/tmp/app-debug.apk',
          out: 'Failure [INSTALL_FAILED_VERSION_DOWNGRADE: ' +
               'Downgrade detected: Update version code 120 is older than current 130]' }
      ]
    }
  ];

  /* 一张超长输出，专门用来压测布局（200 行命令结果） */
  var LONG_OUT = (function () {
    var a = [];
    for (var i = 0; i < 200; i++) {
      a.push('/system/priv-app/Component' + i + '.apk');
    }
    return a.join('\n');
  })();

  var cur = null;     // 当前任务
  var curStep = -1;   // 当前步骤

  /* ------------------------------------------------------------------
     渲染
     ------------------------------------------------------------------ */
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function renderTasks() {
    var box = document.getElementById('aw-tasks');
    box.innerHTML = TASKS.map(function (t) {
      var cls = 'aw-task' + (cur && cur.id === t.id ? ' sel' : '');
      return '<button class="' + cls + '" data-id="' + t.id + '">' +
               '<span class="aw-task-name">' + esc(t.name) + '</span>' +
               '<span class="aw-task-meta">' + esc(t.state) + ' · ' + esc(t.time) + '</span>' +
             '</button>';
    }).join('');
  }

  var STATE_TXT = { idle: '空闲', run: '进行中', done: '已完成', fail: '失败' };

  function renderMain() {
    var title = document.getElementById('aw-title');
    var state = document.getElementById('aw-state');
    var tl = document.getElementById('aw-timeline');

    if (!cur) {
      title.textContent = '选择一个任务';
      state.textContent = '空闲';
      state.setAttribute('data-state', 'idle');
      tl.innerHTML = '<div class="aw-detail-empty">左侧还没有任务</div>';
      return;
    }

    title.textContent = cur.name;
    state.textContent = STATE_TXT[cur.state] || cur.state;
    state.setAttribute('data-state', cur.state);

    if (!cur.steps.length) {
      tl.innerHTML = '<div class="aw-detail-empty">这个任务还没有执行步骤</div>';
      return;
    }

    var html = '';
    for (var i = 0; i < cur.steps.length; i++) {
      var s = cur.steps[i];
      var open = (i === curStep);
      html += '<div class="aw-step' + (open ? ' open sel' : '') +
                '" data-i="' + i + '" data-st="' + s.st + '">' +
                '<div class="aw-step-head">' +
                  '<span class="aw-dot"></span>' +
                  '<span class="aw-step-name">' + (i + 1) + '. ' + esc(s.name) + '</span>' +
                  '<span class="aw-step-tool">' + esc(s.tool) + '</span>' +
                '</div>' +
                '<div class="aw-step-body">' +
                  '<pre class="aw-out' + (s.st === 'fail' ? ' fail' : '') + '">' +
                    esc(s.st === 'fail' ? s.out : (s.out || '（无输出）')) +
                  '</pre>' +
                '</div>' +
              '</div>';
    }
    tl.innerHTML = html;
  }

  function renderDetail() {
    var box = document.getElementById('aw-detail');
    if (!cur || curStep < 0 || !cur.steps[curStep]) {
      box.innerHTML = '<div class="aw-detail-empty">点左侧任一步骤查看详情</div>';
      return;
    }
    var s = cur.steps[curStep];
    box.innerHTML =
      '<div class="aw-detail-h">步骤详情</div>' +
      kv('名称', s.name) +
      kv('工具', s.tool) +
      kv('状态', s.st) +
      kv('参数', s.args) +
      '<div class="aw-detail-h" style="margin-top:var(--space-3)">输出</div>' +
      '<pre class="aw-out' + (s.st === 'fail' ? ' fail' : '') + '">' +
        esc(s.out || '（无）') + '</pre>';
  }

  function kv(k, v) {
    return '<div class="aw-kv"><span class="k">' + esc(k) + '</span>' +
           '<span class="v" title="' + esc(v) + '">' + esc(v) + '</span></div>';
  }

  function renderAll() {
    renderTasks();
    renderMain();
    renderDetail();
  }

  /* ------------------------------------------------------------------
     交互
     ------------------------------------------------------------------ */
  function bind() {
    document.getElementById('aw-tasks').addEventListener('click', function (e) {
      var b = e.target.closest('.aw-task');
      if (!b) return;
      var id = b.getAttribute('data-id');
      cur = TASKS.filter(function (t) { return t.id === id; })[0] || null;
      curStep = -1;
      renderAll();
    });

    document.getElementById('aw-timeline').addEventListener('click', function (e) {
      var step = e.target.closest('.aw-step');
      if (!step) return;
      var i = parseInt(step.getAttribute('data-i'), 10);
      curStep = (curStep === i) ? -1 : i;   // 再点一次收起
      renderAll();
    });

    // 输入框自动增高（最多 120px）
    var input = document.getElementById('aw-input');
    input.addEventListener('input', function () {
      input.style.height = 'auto';
      input.style.height = Math.min(input.scrollHeight, 120) + 'px';
    });

    // Enter 发送 / Shift+Enter 换行（阶段一只是占位）
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        send();
      }
    });
    document.getElementById('aw-send').addEventListener('click', send);

    document.getElementById('aw-new').addEventListener('click', function () {
      var n = TASKS.filter(function (t) { return t.id.indexOf('new') === 0; }).length + 1;
      TASKS.unshift({
        id: 'new' + n, name: '新任务 ' + n, state: 'idle', time: '—', steps: []
      });
      renderAll();
    });
  }

  function send() {
    var input = document.getElementById('aw-input');
    var txt = input.value.trim();
    if (!txt) return;
    /* 阶段一：把发出去的文字变成一条"占位步骤"，让交互闭环可看。
       阶段二这里换成 post({type:'req', op:'agent.run', args:{text:txt}})。 */
    if (!cur) {
      cur = { id: 'new-ad', name: txt.slice(0, 20), state: 'idle', time: '—', steps: [] };
      TASKS.unshift(cur);
    }
    cur.steps.push({
      name: '用户输入', tool: 'user', st: 'done',
      args: txt, out: '（阶段一：这里是假回显；阶段二会接真实执行）'
    });
    curStep = cur.steps.length - 1;
    input.value = '';
    input.style.height = 'auto';
    renderAll();
  }

  /* ------------------------------------------------------------------
     主题同步（父页推送）
     为什么需要：iframe 里的 CSS 变量**不继承**父页，
     必须由父页把算好的值推过来。父页调 applyAccent / 切主题 / 调字号时都会推。
     ------------------------------------------------------------------ */
  function applyTheme(m) {
    if (m.theme) root.setAttribute('data-theme', m.theme);
    if (m.fsize) root.setAttribute('data-fsize', m.fsize);
    if (m.accent) root.style.setProperty('--accent', m.accent);
    if (m.accentSoft) root.style.setProperty('--accent-soft', m.accentSoft);
    if (m.onAccent) root.style.setProperty('--on-accent', m.onAccent);
  }

  window.addEventListener('message', function (e) {
    var m = e.data;
    if (!m || m.__agent !== 1) return;      // 只认带命名空间标记的消息
    if (m.type === 'theme') applyTheme(m);
    // 阶段二：if (m.type === 'res') onAgentRes(m);
  });

  /* 告诉父页"我准备好了"，父页收到后立刻推一次主题 */
  function announceReady() {
    try {
      if (window.parent && window.parent !== window) {
        window.parent.postMessage({ __agent: 1, type: 'ready' }, '*');
      }
    } catch (err) { /* 独立打开时没有父页，忽略 */ }
  }

  /* ------------------------------------------------------------------
     启动
     ------------------------------------------------------------------ */
  bind();
  cur = TASKS[0];
  renderAll();
  announceReady();

  // 独立调试用：把超长输出挂到 window，方便手动塞进步骤里压测
  window.__awLongOut = LONG_OUT;

})();
