
var hist = [];
var histIdx = -1;
var draft = '';

function post(kind, data){
  try{ window.chrome.webview.postMessage({ kind:kind, data:data||'' }); }catch(e){}
}

// 帮助按钮等快捷入口：直接以"命令"形式发给 C# 执行（等价于在输入框敲 :h 回车）
function sendCmd(cmd){
  post('cmd', cmd);
}

function onMessage(ev){
  var msg = ev.data;
  if(!msg || !msg.kind) return;
  switch(msg.kind){
    case 'line': appendLine(msg); break;
    case 'echo': appendEcho(msg.data); break;
    case 'status': setStatus(msg.data); break;
    case 'begin': beginRun(); break;
    case 'end': endRun(msg.data); break;
    case 'clear': clearLog(); break;
    case 'filePath': onFilePath(msg.data); break;
  }
}
window.chrome.webview.addEventListener('message', onMessage);

// 页面就绪后主动向 C# 请求一次状态，避免设备号因初始化竞态丢失
function ready(){ try{ window.chrome.webview.postMessage({kind:'ready'}); }catch(e){} }

var levelClass = { 1:'c-ok', 2:'c-err', 3:'c-dim', 4:'c-faint', 5:'c-path' };

function appendEcho(cmd){
  var box = document.getElementById('logbox');
  hideEmpty(box);
  var d = document.createElement('div');
  d.className = 'echo';
  d.innerHTML = '<span class="pmt"></span><span class="cmd"></span>';
  d.querySelector('.pmt').textContent = curPmt();
  d.querySelector('.cmd').textContent = cmd;
  box.appendChild(d);
  scrollBottom(box);
}

function appendLine(msg){
  var box = document.getElementById('logbox');
  hideEmpty(box);
  var d = document.createElement('div');
  d.className = 'ln ' + (levelClass[msg.level] || '');
  d.textContent = msg.text;
  box.appendChild(d);
  scrollBottom(box);
}

function hideEmpty(box){
  var e = document.getElementById('log-empty');
  if(e && e.parentNode) e.style.display = 'none';
}
function scrollBottom(el){ el.scrollTop = el.scrollHeight; }

// 统一提示符：设备号 + 当前目录 + " >"，供输入框和回显共用
var _dev = '', _dir = '';
function curPmt(){
  var s = _dev;
  if(_dir) s += ' ' + _dir;
  return s + ' >';
}

function toggleTheme(){
  var r = document.documentElement;
  r.dataset.theme = (r.dataset.theme === 'dark') ? 'light' : 'dark';
  post('theme', r.dataset.theme);
}

function switchTab(name){
  document.querySelectorAll('.tab').forEach(function(t){
    t.classList.toggle('active', t.dataset.tab === name);
  });
  document.getElementById('page-cmd').classList.toggle('active', name === 'cmd');
  document.getElementById('page-quick').classList.toggle('active', name === 'quick');
}

function run(){
  var inp = document.getElementById('cmd-input');
  var cmd = inp.value.trim();
  if(!cmd) return;
  inp.value = '';
  hist.push(cmd); histIdx = -1; draft = '';
  post('cmd', cmd);
}

function stop(){ post('stop'); }

function clearLog(){
  var box = document.getElementById('logbox');
  box.innerHTML = '';
  var e = document.createElement('div');
  e.className = 'empty'; e.id = 'log-empty';
  e.innerHTML = '<div class="t">等待输入指令</div><div class="d">直接敲命令即可，不认识的会原样交给设备 shell</div>';
  box.appendChild(e);
}

function copyCmd(){
  var inp = document.getElementById('cmd-input');
  if(inp.value) post('copy', inp.value);
}

function onInputKey(e){
  if(e.key === 'Enter'){ e.preventDefault(); run(); return; }
  if(e.key === 'ArrowUp'){ e.preventDefault(); nav(-1); return; }
  if(e.key === 'ArrowDown'){ e.preventDefault(); nav(1); return; }
}

function nav(dir){
  if(hist.length === 0) return;
  var inp = document.getElementById('cmd-input');
  if(histIdx < 0){ draft = inp.value; histIdx = hist.length; }
  histIdx += dir;
  if(histIdx < 0) histIdx = 0;
  if(histIdx > hist.length) histIdx = hist.length;
  inp.value = (histIdx === hist.length) ? draft : hist[histIdx];
}

function setStatus(s){
  _dev = s.dev || '';
  _dir = s.dir || '';
  // 数据到了，关掉黑猫加载层
  var sp = document.getElementById('splash');
  if(sp && !sp.classList.contains('hide')){ sp.classList.add('hide'); }
  // 设备徽章（无设备时不显示任何占位文字，去掉"检测中/未连接"这类噪音）
  var dot = document.getElementById('dev-dot');
  var id = document.getElementById('dev-id');
  var sep = document.getElementById('dev-sep');
  var soc = document.getElementById('dev-soc');
  if(s.dev){
    dot.style.display = '';
    dot.className = 'dot' + (s.online ? '' : '.off');
    id.textContent = s.dev;
    sep.textContent = s.soc ? '·' : '';
    soc.textContent = s.soc || '';
  } else {
    dot.style.display = 'none';
    id.textContent = '';
    sep.textContent = '';
    soc.textContent = '';
  }
  // 提示符（输入框 > 前显示设备号）
  document.getElementById('pmt').textContent = curPmt();
}

function beginRun(){
  document.getElementById('running').classList.add('on');
  document.getElementById('btn-run').disabled = true;
  document.getElementById('btn-stop').disabled = false;
}

function endRun(r){
  document.getElementById('running').classList.remove('on');
  document.getElementById('btn-run').disabled = false;
  document.getElementById('btn-stop').disabled = true;
  if(r.feed) addFeed(r.feed);
}

function addFeed(f){
  var tb = document.getElementById('fb-table');
  var row = document.createElement('div');
  row.className = 'fb-row';
  row.innerHTML = '<span class="t"></span><span class="c"></span><span class="'+(f.ok?'ok':'err')+'"></span><span class="d"></span>';
  row.querySelector('.t').textContent = f.time;
  row.querySelector('.c').textContent = f.cmd;
  row.querySelector('span:nth-child(3)').textContent = f.ok ? '成功' : '失败';
  row.querySelector('.d').textContent = f.ms + ' ms';
  tb.appendChild(row);
  var rows = tb.querySelectorAll('.fb-row:not(.head)').length;
  document.getElementById('fb-count').textContent = rows + ' 条';
}

// 首次加载时请求状态
ready();

// ==================== 拖拽文件到输入框 ====================
// 问题3：允许把电脑文件拖到输入框。WebView2 里 File.path 为 null，
// 需用 postMessageWithAdditionalObjects 把 File 对象交给 C#，由
// C# 端 CoreWebView2File.Path 拿完整路径后回填。
(function(){
  var field = document.querySelector('.field');
  var inp = document.getElementById('cmd-input');
  if(!field || !inp) return;

  field.addEventListener('dragover', function(e){
    e.preventDefault();
    e.stopPropagation();
    field.style.borderColor = 'var(--accent)';
  });
  field.addEventListener('dragleave', function(e){
    field.style.borderColor = '';
  });
  field.addEventListener('drop', function(e){
    e.preventDefault();
    e.stopPropagation();
    field.style.borderColor = '';

    var files = e.dataTransfer && e.dataTransfer.files;
    if(files && files.length > 0){
      try{
        // 把 File 对象连同消息交给 C#，C# 解析完整路径后回填
        window.chrome.webview.postMessageWithAdditionalObjects({kind:'fileDrop'}, [files[0]]);
      }catch(err){
        // API 不可用时退化为文件名
        inp.value = files[0].name || '';
        inp.focus();
      }
    }
  });
})();

// 收到 C# 解析出的完整文件路径，填入输入框
function onFilePath(path){
  if(!path) return;
  var inp = document.getElementById('cmd-input');
  if(/\s/.test(path) && path.charAt(0) !== '"') path = '"' + path + '"';
  inp.value = path;
  inp.focus();
}

// 兜底：8 秒后无论是否收到状态都关掉加载层，避免一直卡在"连接中"
setTimeout(function(){
  var sp = document.getElementById('splash');
  if(sp){ sp.classList.add('hide'); }
}, 8000);

