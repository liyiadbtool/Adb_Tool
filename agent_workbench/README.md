# Agent 工作台

> **接手开发请先读 [HANDOFF.md](HANDOFF.md)** —— 那里有红线、已验证事实、踩过的坑和下一步任务。

给 Adb_Tool 新做的任务编排界面。**独立目录，不进主应用源码树。**

---

## 隔离规则（重要）

```
Adb_Tool/
├── adb_log_gui/webview2/     ← 主应用源码，本工作台**不往里写任何文件**
├── tools/extract_tokens.py   ← 只读 ui.html，输出到下面
└── agent_workbench/          ← 全部产物都在这里
    ├── agent.html
    ├── agent.css
    ├── agent.js
    ├── gen/
    │   ├── tokens.css        ← 自动生成，勿手改
    │   └── components.css    ← 自动生成，勿手改
    └── README.md             ← 本文件
```

**为什么这么严**：`adb_log_gui/webview2/` 里的文件会被 `build_gui.bat`
打进 `dist` 发布包。那里多一个文件，用户的安装包里就多一份永远用不到的
实验代码 —— 属于污染。

**嵌入阶段（阶段三）**才会把 4 个文件复制到 `dist/internal/`，
但**源码仍留在本目录**，不进主应用源码树。

---

## 样式从哪来

不手抄。全部由脚本从主界面抽取：

```bash
python tools/extract_tokens.py          # 生成
python tools/extract_tokens.py --check  # 只校验是否同步
```

| 文件 | 内容 |
|---|---|
| `gen/tokens.css` | 258 个令牌定义 / 3 套主题 / 48 条强调色矩阵 / 基础重置 / 无障碍媒体查询 |
| `gen/components.css` | 公共组件：`.btn`（25 条）、`.set-seg`、`.h5-seg` |

**主界面改动后必须重跑**，否则样式会漂移。`--check` 用一个 md5 判断是否同步。

### 一个已知限制

主界面**没有**通用的 `.inp` / `.card` / `.mini-btn` —— 输入框是各页面自己写的
（`qinp` / `mk-inp` / `clu-inp`），卡片只有 `diag-card`（页面专属）。

所以 `agent.css` 里的卡片和输入框是**新建**的，但每一处颜色/圆角/间距都取自令牌，
视觉与主界面一致。

---

## 当前状态：阶段一（假数据）

已完成：
- 三栏布局（任务列表 / 执行时间线 / 步骤详情）
- 四种状态：空任务、单步、多步（进行中）、失败
- 步骤可展开收起、点选看详情
- 主题同步接收（父页 postMessage 推 HEX 强调色 / 主题 / 字号）

**独立打开即可看**（不需要主应用）：

```
双击 agent.html  →  或 Edge 打开
```

验证结果（Edge 实测）：

```
三栏 grid       220px / 856px / 300px
tokens.css 加载  --bg=#000000  --space-3=12px
components 加载  .btn 规则存在
任务 / 步骤     4 个任务，多步任务 4 步
详情面板        4 条键值
主题推送        accent=#B28F98  theme=light  fsize=l  ✓
```

---

## 阶段二待做

1. `agent-bridge.js`：请求/响应配对（id 映射、超时、乱序、并发）
2. 接真实 `op`：先只开三个 —— `adb.shell`、`fs.read`、`logcat.tail`
3. 用桩数据测：永不回包（超时）、先回 r2 再回 r1（乱序）、同时 5 个（并发）

---

## 阶段三待做（嵌入主应用）

改 4 处，**都在 ui.html 里，且都是增量**：

1. `.tabs` 末尾加 `<button class="tab" data-tab="agent">Agent</button>`
2. `</main>` 前加 `<div class="page" id="page-agent"><iframe src="agent.html">…</iframe></div>`
3. `applyAccent` / `setThemeByName` / `applySize` 末尾各加一次 `pushThemeToAgent()`
4. `build_gui.bat` 加 5 行 `copy`（4 个文件 + README 不需要）

---

## 通信协议

```
agent  → 父页   { __agent:1, type:'req', id:'r-0017', op:'adb.shell', args:{cmd} }
父页   → C#     { kind:'agentreq', id:'r-0017', op, args }
C#     → 父页   { kind:'agentres', id:'r-0017', ok, data, err }
父页   → agent  { __agent:1, type:'res', id:'r-0017', ok, data, err }
```

主题同步：

```
父页 → agent  { __agent:1, type:'theme', theme, accent(HEX), accentSoft, onAccent, fsize }
```

**为什么必须走父页转发**：WebView2 只往顶层文档注入 `chrome.webview`，
iframe 里拿不到。这一点无法绕过。

**为什么 accent 要传 HEX 而不是名字**：iframe 里没有 `[data-accent="blue"]`
这类规则，传 `'blue'` 是无效 CSS 值。父页算好 HEX 再推，agent 侧直接 `setProperty`。
