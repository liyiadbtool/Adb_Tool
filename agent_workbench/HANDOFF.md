# Agent 工作台 · 交接文档

> **接手请从第 1 节读起，第 4 节是红线，第 8 节是你要做的第一件事。**

---

## 1. 这是什么

给 `Adb_Tool`（WinForms + WebView2 的 adb 调试工具）新做一个 **Agent 工作台**：
任务编排 + 多步骤 + 工具调用可视化。后端逻辑将来由 C# 内置。

**当前只做 UI 与规范集成，功能从零开始。**

- 主应用仓库：`C:\Users\李亦\Desktop\Adb_Tool`
- 本工作台：`agent_workbench\`
- 最近提交：`82509f3`（在其之上的远端已推进到 71+ 个提交，rebase 前先 `git fetch` 看清）

---

## 2. 现在到哪了

**阶段一（UI 骨架）已完成并验证。**

| 项 | 状态 |
|---|---|
| 设计系统抽取器 | ✅ `tools/extract_tokens.py`，4 项自校验 |
| 三栏布局 | ✅ 任务列表 / 执行时间线 / 步骤详情 |
| 四种状态 | ✅ 空 / 单步 / 多步（进行中）/ 失败 |
| 交互 | ✅ 步骤展开收起、点选详情、输入框自动增高 |
| 主题同步接收 | ✅ 模拟父页 postMessage，`--accent` 实测变化 |
| 通信协议 | ⬜ 只有接收端占位，**阶段二才做** |

**阶段二未开始**：请求/响应配对、超时、乱序、并发、接真实 op。

---

## 3. 文件地图

```
agent_workbench/
├── HANDOFF.md          ← 本文件
├── README.md           ← 面向使用者的说明（隔离规则/协议）
├── agent.html          ← 页面结构（三栏）
├── agent.css           ← 本页独有样式（**只用令牌**）
├── agent.js            ← 假数据 + 渲染 + 主题接收
└── gen/
    ├── tokens.css      ← 自动生成，勿手改
    └── components.css  ← 自动生成，勿手改

tools/
└── extract_tokens.py   ← 从 ui.html 抽取设计系统
```

---

## 4. 红线（违反会返工）

| # | 禁止 | 原因 |
|---|---|---|
| 1 | **不要往 `adb_log_gui/webview2/` 写任何文件** | 那里会被 `build_gui.bat` 打进 dist 发布包，等于往用户安装包里塞实验代码 |
| 2 | **不要改 `ui.html`**（阶段三前） | 主应用在活跃开发（远端已有 71+ 提交），改它必冲突 |
| 3 | **不要手改 `gen/*.css`** | 下次跑脚本就覆盖；要改令牌去改 `ui.html` |
| 4 | **不要在 agent 里硬编码颜色/圆角/间距** | 一切取自 tokens，否则切主题时不跟着变 |
| 5 | **不要用 `s += "...CSS..."` 方式改 HTML** | 上一轮这样写，CSS 落到了 `</html>` 之后，界面直接崩 |
| 6 | **不要改测试断言去迁就代码** | 曾多次这样做，等于自己判卷，缺陷全放过 |

---

## 5. 已确认的技术决策（含为什么）

| 决策 | 为什么 |
|---|---|
| **独立文件 + iframe 嵌入**（不走同页） | ui.html 已 1.2MB，再塞会更大；独立文件可单独回滚 |
| **抽取器生成 CSS**（不手抄） | 主界面令牌会变，手抄必然漂移 |
| **单向依赖：ui.html → tokens.css → agent** | 反向会形成两套真源 |
| **通信必须经父页转发** | WebView2 只往**顶层文档**注入 `chrome.webview`，iframe 里没有 |
| **主题用 postMessage 推，不读 parent.document** | `file://` 下 iframe 同源访问不可靠 |
| **推 accent 要推 HEX，不推名字** | iframe 里没有 `[data-accent="blue"]` 规则，推 `'blue'` 是无效 CSS 值 |
| **字号不用单独同步** | ZoomFactor 作用于整个 WebView2 控件，iframe 自动跟着缩放 |

---

## 6. 已验证的事实（不是推测，可直接依赖）

**设计系统**（`--check` 实测）：

```
主题 3 套 · 强调色矩阵 48 条 · 令牌定义 258 次 · 组件规则 75 条
ui.html 当前 md5: 3b132e4de7f6
```

**主界面组件真实情况**：

- ✅ 有：`.btn`（25 条）、`.set-seg`、`.h5-seg`
- ❌ **没有**：通用 `.inp` / `.card` / `.mini-btn`
- 输入框是各页面自己写的：`qinp`（智驾）、`mk-inp`（Monkey）、`clu-inp`（投屏）
- 卡片只有 `diag-card`（页面专属）

→ **agent 的卡片和输入框必须新建**，但每处取值用令牌。别去找"现成组件"。

**布局实测**（Edge 1400×900）：

```
三栏 grid      220px / 856px / 300px
tokens 加载    --bg=#000000  --space-3=12px
任务 / 步骤    4 个任务，多步任务 4 段
主题推送       accent=#B28F98  theme=light  fsize=l  ✓
```

**关键：`tokens.css` 里 `body` 是 `display:flex`**，所以根容器必须 `flex:1 1 auto; width:100%`，否则 grid 的 `1fr` 只分到内容宽度（实测中间栏被压到 268px）。

---

## 7. 踩过的坑（别再踩）

| 坑 | 现象 | 正确做法 |
|---|---|---|
| `css.find("body{")` 命中 `html,body{` | 真正的 `body` 规则（字体/背景/防选中）被丢掉，换成一条空的，**生成物看起来正常** | 按**选择器完全相等**匹配；并断言 `body` 必须含 `font-family` |
| `.inp` 是 `.inputbar` 的前缀 | 页面专属类混进公共组件 | 前缀匹配要检查边界字符（`.` `:` `[` 空格 `,` `>`） |
| 探针放在 temp 目录测相对路径 | CSS 全 404，页面裸奔 | 探针必须与目标 HTML **同目录** |
| 用 `s +=` 往 HTML 末尾加 CSS | CSS 变成页面正文，界面崩 | 定位到 `</style>` 之前插入 |
| 改测试断言让测试通过 | 缺陷全放过 | 断言改的是**行为**，不是**字面代码** |

---

## 8. 你接手后要做的第一件事

**阶段二：通信桥**

写 `agent-bridge.js`，实现请求/响应的配对与容错：

```
agent  → 父页   { __agent:1, type:'req', id:'r-0017', op:'adb.shell', args:{cmd} }
父页   → C#     { kind:'agentreq', id:'r-0017', op, args }
C#     → 父页   { kind:'agentres', id:'r-0017', ok, data, err }
父页   → agent  { __agent:1, type:'res', id:'r-0017', ok, data, err }
```

**必须覆盖的四种情况**（缺一个就不算完成）：

1. **超时**：桩永不回包 → 30s 后显示错误，不卡死
2. **乱序**：先回 r2 再回 r1 → 结果不错位
3. **并发**：同时发 5 个 → 全部正确归位
4. **异常**：C# 返回 `ok:false` → 步骤标红 + 显示 `err`

**先只开三个 op**，跑通再加：

| op | args | 说明 |
|---|---|---|
| `adb.shell` | `{cmd}` | 执行 shell，返回纯文本 |
| `fs.read` | `{path}` | 读本地文件（限白名单） |
| `logcat.tail` | `{n}` | 取最近 N 行 |

**改完必做**：

```bash
python tools/extract_tokens.py --check   # 确认样式没漂
```

（如果这期间别人改了 `ui.html`，先 `python tools/extract_tokens.py` 重新生成，再提交）

---

## 9. 阶段三：嵌入主应用（阶段二完成后再做）

只改 4 处，**全是增量**：

1. `.tabs` 末尾加 `<button class="tab" data-tab="agent">Agent</button>`
2. `</main>` 前加 `<div class="page" id="page-agent"><iframe src="agent.html">…</iframe></div>`
3. `applyAccent` / `setThemeByName` / `applySize` 三个函数末尾各加一次 `pushThemeToAgent()`
4. `build_gui.bat` 加 4 行 `copy`（agent.html / agent.css / agent.js / gen 两个 css）

**验收**：切主题、换强调色、调字号 → agent 页面全部跟着变；adb 请求能往返。

---

## 10. 设计取向（接手别推翻）

现在这套是**克制**的：

- 三栏不分心，中间是主战场
- 步骤卡默认收起，只露"序号 + 名称 + 工具名"
- 状态只用三种色：灰（等待/空闲）、强调色（进行中/完成）、红（失败）
- 不做渐变、不做玻璃拟态、不加装饰性图标

**如果要改视觉，先确认这三条是否还成立**，否则很容易滑向"通用 AI 产品风"。

---

## 11. 怎么用这份文档启动新对话

在 WorkBuddy 新对话里发这一句就够：

```
@agent_workbench/HANDOFF.md 请先完整读这份交接文档，
然后按第 8 节开始做阶段二（通信桥）。
```

**不要**只靠"我之前和你说过……"——对话记忆是摘要，会丢细节；
**也不要**指望 `conversation_search` 能捞全——它靠关键词，容易漏。

**文件才是确定的。**
