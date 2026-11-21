# AGENTS.md — Adb_Tool 项目规则（给 AI / 给人看同一份）

> 这份文件是**硬约束**，不是建议。每次开工先读它，改完代码必须跑最后那一条命令。
> 状态与交接记录在 `STATE.md`，不要往这份文件里写"今天做了什么"。

---

## 0. 开工 / 收工：两条不可违反的操作纪律

> **最高优先级。任何设备、任何人、任何 AI 拉取本仓库后都必须遵守。**
> 一句话版本：**开工 = 拉代码 + 跑测试（有缺陷就修）；收工 = 清理无用数据 + 上传。**
> 详细步骤与汇报格式见 `WORKFLOW.md`（本文件只留原则与红线）。

### 开工（三条铁律）

1. **拉代码前先 `git status -s`** —— 本地有未提交改动就停下来问，禁止 `reset --hard` 硬覆盖。
2. **拉完立即 `python verify_all.py --fast`**（~5 秒）—— 确认这份代码在本机健康。
3. **按结果分流**：全绿 → **保持原样、什么都不动**，只汇报版本 + 结果；有红 → 修到绿再汇报。

修缺陷的边界：

- 只修**测试暴露的真实缺陷**，不夹带需求、不重构、不"顺便优化"。
- 环境性失败（换机器必现）**不改代码绕过**，如实汇报。
- **判定基线以 `verify_all.py` 实际项数为准** —— 不在门禁清单里的历史脚本不算缺陷。
- 开工阶段**禁止** `git commit` / `git push`，也禁止改功能（那是"干活"阶段）。

### 收工（两条铁律）

1. **先清理，再 `git add`** —— 见下方清理表。不许跳过清理直接 `git add -A`。
2. **编译 + 门禁绿才能提交**，然后 `git push origin main`。

**收工前必须清理的六类无用数据**：

| 类别 | 具体文件 | 处理 |
|---|---|---|
| **运行态污染** | `adb_log_gui/adb_log_export.ini`（程序改写 theme / accent / prefs） | `git checkout -- <该文件>` 丢弃 |
| 构建产物 | `adb_log_gui/dist/`、`release/` | 已被 `.gitignore` 忽略，出现在 status 说明误 add，`git reset` 撤掉 |
| 编译中间件 | `*.exe`、`*.pdb`、`*.obj` | 同上，不入库 |
| 临时调试文件 | `_tmp*.py`、`*.log`、`*.png`、`_shot_*/` | 删除或确认已忽略 |
| 测试生成物 | `377/test_*.html`、`377/_*_probe.html`、`_dbg*.html` | 已被 `.gitignore` 覆盖，确认即可 |
| 飞书交付副本 | `_feishu/` | 已被 `.gitignore` 覆盖，确认即可 |

收工禁止事项：不许再改代码、不许 `--amend`、不许 `--force`（除用户明确要求）。

### 收工前必查（缺一不可）

| 检查 | 命令 | 期望 |
|---|---|---|
| 编译通过 | `adb_log_gui/build_gui.bat`（自动化加 `NO_PAUSE=1`） | `Compile success` |
| 门禁绿 | `python verify_all.py --fast` | `失败 0 项` |
| 无用数据已清理 | `git status -s` | 无 `dist/`、无运行态 ini、无临时文件 |
| 推送成功 | `git push origin main` | `main -> main` |

> 用户明确缩小范围时（如"只拉代码不跑测试"），**以用户当场说的为准**，字面执行。

### 门禁三档（2026-11-21 整改，实测耗时）

| 档位 | 命令 | 耗时 | 跑什么 | 什么时候跑 |
|---|---|---|---|---|
| 日常 | `--fast` | **~5 秒** | 静态四项 + CLI 自检，全毫秒级 | 改一行代码就验，随时 |
| 常规 | 无参数 | ~90 秒 | + 真实浏览器/exe 行为套件（12 套）+ 配置导入导出 | **功能改完、准备提交** |
| 全量 | `--full` | ~5 分钟 | + `_test_ux`(185s) + v12/v13/a14 + A15/A16/A17 落点 | **发包前** |

> 分档理由：`_test_ux` 单套 185 秒、`_test_profile` 62 秒（起 20+ 次 exe），
> 原来把它们算进"日常档"导致每轮 69 秒 —— 名不副实。现在各跑各的档，不要每轮全跑。

---

## 0.1 UI 基线约定（不可动摇）

> **所有 UI 需求一律在现有 `adb_log_gui/webview2/ui.html` 上实现。**
> 这条优先级等同于 §0，任何"顺手美化""整体换肤"都必须先拿到用户单独授权。

### 唯一的 UI 基线

| 项 | 值 |
|---|---|
| 唯一页面 | `adb_log_gui/webview2/ui.html` |
| 分层注入源 | `_v12..v17.js/.css`（改注入块必须改源文件，不许直接改 ui.html 的标记段，见 §3） |
| 配色令牌 | `--accent` 16 色（`_cs/Prefix.cs` 的 `ACCENTS` 是唯一白名单） |
| 主题 | dark / light / eye 三套，令牌在 ui.html 的 `:root` 段 |

### 明确禁止

- **不许**引入或合并任何"另一套 UI"（包括独立目录里的视觉探索稿）。
- **不许**以"新 UI 更好看"为由建议整体替换。
- **不许**把 `HMI_LiquidGlass/`（已封存的液态玻璃演示，位于工作区
  `C:\Users\李亦\WorkBuddy\2026-11-14-22-02-28\` 下，不在本仓库内）
  的样式、结构或组件搬进本仓库。
- **不许**因为一次需求而顺带改全局配色/圆角/字体令牌（那会波及所有页面）。

### 例外

只有当用户**明确说**"把某套 UI / 某个视觉稿实现进来"时，才可跨基线改动；
届时也需要单独开一轮、单独验收，不与功能需求混在一个提交里。

---

## 1. 这是什么

一个 Windows 单 exe 的**车机（Android IVI）测试工具**：CLI + 自绘 WebView2 GUI 双形态，同一个仓库出两个可执行文件。

| 形态 | 入口 | 编译 | 产物 |
|---|---|---|---|
| CLI | `_cs/Program.cs` | `_cs/build.bat` | `adb_log_export.exe` |
| GUI | `_cs/GuiEntry.cs` → `GuiMain` / `GuiWeb` | `adb_log_gui/build_gui.bat` | `adb_log_gui/dist/adb_Tool.exe` |

被测对象：`Max-8838-T75` / `A8R_8295` / `T09M_8295` / `AHT` / `V20` 等车型的中控、副驾、后排、HUD 屏；核心场景是「场景大师」语音与功能测试。

---

## 2. 技术栈已冻结（不许升级、不许引包）

- **C# 语言版本 5**（`csc.exe` from .NET Framework 4.0.30319，`/langversion:5`）。
  这意味着下列写法**编译不过**，看到报错先怀疑自己写新语法了：
  - 字符串插值 `$"{x}"` → 用 `"a" + x`
  - `?.` / `?.Invoke()` → 用 `if (x != null)`
  - `nameof()`、表达式体成员 `=> x;`、`out var`、元组、`using static`
- **UI 是手写 HTML/CSS/JS，没有前端构建**。`ui.html` 是唯一页面，直接跑在 WebView2 里。
- **不引第三方 NuGet / npm 包**。WebView2 的两个 DLL 是随包分发的固定版本。
- 依赖 GDI+/WinForms（`System.Drawing` / `System.Windows.Forms`），**不要**换成 WPF。

> CLI 那个 exe 编译时**不引用 System.Drawing**。任何被 CLI 和 GUI 共用的文件（如 `Prefix.cs`）里
> 一旦出现 `Color` 类型，CLI 立刻 CS0234 —— 共用代码只返回 `int`（0xRRGGBB），GUI 自己转 `Color`。

---

## 3. 前端是"分层注入"的，别直接改 ui.html 的注入块

`adb_log_gui/webview2/ui.html` 里有 4 段被标记包裹的代码，它们**由源文件生成**：

```
/* === V14 LAYER START === */ ... /* === V14 LAYER END === */    ← _v14.js / _v14.css
/* === V15 LAYER START === */ ...                                ← _v15.js / _v15.css
/* === V16 LAYER START === */ ...                                ← _v16.js / _v16.css
/* === V17 LAYER START === */ ...                                ← _v17.js / _v17.css
（JS 同理，标记是 "V1x JS START/END"）
```

**规则：**

1. 要改这几段里的东西 → 改 `_vNN.js` / `_vNN.css`，再按顺序重注：
   ```bash
   python _inject_v14.py && python _inject_v15.py && python _inject_v16.py && python _inject_v17.py
   ```
2. 顺序不能乱，每一层都靠替换 `window.xxx` 引用生效，前面没到位后面就白搭。
3. 注入脚本必须**幂等**（重复跑不叠层）。A17 踩过一次：正则要求 `START === */` 而实际是
   `START ===` 换行，结果每跑一次多一份，页面里同一段 CSS 出现两次。
4. `ui.html` 里标记**外面**的部分（页面骨架、A13 标题栏、A15 之前的样式）可以直接改。
5. 强调色色板（16 个 `.accent-dot`）是 `_gen_accent.py` 之外手写的，改色必须同时动三处：
   生成器 `ORDER`、`var ACCENT_ORDER`、`_cs/Prefix.cs` 的 `ACCENTS`。
   **`ACCENT_ORDER` 是隐藏门槛：不在表里的色名会被静默回退成 blue。**

---

## 4. 构建与验收（每次改完必须跑第 3 条）

```bash
# 1) 编译（两条都要，别只编 GUI）
cmd //c "_cs\\build.bat" < /dev/null                      # CLI
NO_PAUSE=1 cmd //c "adb_log_gui\\build_gui.bat"           # GUI（必须带 NO_PAUSE，脚本末尾有 pause）

# 2) 改了 cmds.ini 的话：打包源必须同步，否则 release 校验会红
cp cmds.ini adb_log_gui/cmds.ini

# 3) 全量门禁：26 项，必须 0 失败
python verify_all.py
```

门禁里几条最容易踩的：

| 项 | 它会抓什么 |
|---|---|
| 功能不变量对照（44 项） | 新增的 DOM id / 按钮 / 页签 / 消息 kind 必须先在 `_gate_invariants.py` 的 `A1x_ADDS` 里登记，否则算"未登记新增" |
| ui.html 静态自检 | 不许出现内联 `onclick` 之外的隐式全局、不许重复 id |
| A15/A16/A17 落点机检 | 历次需求的落点，任何一次误删立刻红灯 |
| 功能清单落点（52 项） | `_check_features.json` 里每条都要指向真实存在的锚点文本 + 测试文件 |
| 窗口原生行为（13 项） | 真的起一次 exe，量 GWL_STYLE、ClientSize、最大化是否盖任务栏 |

**验收没通过不许提交。** 不许为了让测试变绿去改断言 —— 要么改代码，要么在 `_gate_invariants.py`
里显式登记并写清理由。

### 4.1 文档同步契约（2026-11-16 起，和门禁同等要求）

代码会漂，文档不更新就等于没有。以下四份文档**跟着改动走**，缺一份不算完成：

| 改了什么 | 必须同步更新 |
|---|---|
| 任何模块的实现/职责变化 | `docs/代码导读.md` 对应 §5 模块行 + §8 影响面速查 |
| 新增/删除一条命令、一个消息 kind、一个页面 | `docs/测试用例.md` 增删用例 ID；`docs/功能清单.md` 同步 |
| 可见交互行为变化 | `docs/用户使用手册.md` + `377/` 对应断言 |
| 每轮收工 | `STATE.md` 的「本轮做了什么」+「验收基线数字」+ `docs/测试报告_<日期>.md` |

**门禁数字必须以代码为准**（`python verify_all.py` 的实际项数），不许照抄旧文档里的"26 项"。

---

## 5. 三次踩过的坑（别再踩）

1. **不要用改窗口尺寸做动画**。`SetWindowPos` 缩真窗口再放大，必然留下"巴掌大窗口"：
   目标读运行时 `Bounds`（重入即自我叠加）+ WebView2 初始化堵消息泵 1~3s（帧整段丢失）
   + 任何中断都停在中间尺寸且不最小化。动效只做在渲染层（`transform:scale`）。
2. **弹窗不要挂在会被裁剪的祖先里**。`.titlebar` / `.tabs` 各有 `backdrop-filter`
   → 各自形成层叠上下文，后 DOM 压前 DOM。要用 body 级 `position:fixed` portal。
3. **不要用"改 `onQuickSearch`"的方式加防抖**。同步调用者（测试、代码直调）会"点了没反应"。
   防抖只放事件入口。

---

## 6. 文件地图

| 路径 | 作用 |
|---|---|
| `AGENTS.md` | **本文件**：硬约束总纲。开工前必读 |
| `WORKFLOW.md` | **开工/收工操作细则**：只拉 / 只推的执行步骤与常见错误 |
| `_cs/*.cs` | 全部 C# 源码（32 个文件，两个 bat 的编译列表必须覆盖所有 .cs） |
| `adb_log_gui/webview2/ui.html` | 唯一页面（≈715 KB，含 4 层注入） |
| `_v14..v17.js/.css` | 前端分层源文件，见 §3 |
| `_gen_accent.py` | 16 色 × 3 主题 = 48 条配色规则生成器（带 WCAG 校验） |
| `_icon_v2.py` | 应用图标生成器（ico 7 档 + 内联 SVG + 预览图，**单一来源**） |
| `cmds.ini` | 命令注册表（快捷指令的 `cmd:` 全部指向这里的段） |
| `_check_features.json` | 功能清单（52 条），锚点文本 + 测试文件 |
| `verify_all.py` | 26 项门禁总入口 |
| `377/` | 行为测试（headless 浏览器跑 ui.html） |
| `release.py` | 出三个包（完整 / 精简 / 单文件） |
| `docs/` | 用户手册、UI 清单、功能清单、不变量差异、截图 |
| `STATE.md` | 当前状态与交接记录 |

---

## 7. 红线

- 不许把 `dist*/` / `release/` / `*.exe` / `ffmpeg.exe` 提交进 Git（见 `.gitignore`）。
- 不许改 `_check_features.json` 的锚点去"绕过"失败 —— 锚点是需求的可追溯证据。
- 不许删 `cmds.ini` 里的段来"简化"；快捷指令卡片与它一一对应。
- 不许把设备相关的密钥、密码、token 写进任何文件。
- 不许在 `.bat` 里写中文（编码会坏，`/codepage:65001` 会把注释也当源码）。
