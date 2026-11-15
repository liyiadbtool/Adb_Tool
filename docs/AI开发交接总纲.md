# AI 开发交接总纲 —— 给任何一台设备上的 AI 读

> **这份文档是喂给 AI 的「大脑记忆」。** 换机器、换 AI、换会话后，先让它完整读这份文件，
> 它就知道「这是个什么项目、规则是什么、红线在哪、之前踩过什么坑、怎么改怎么测怎么交付」。
> 比人记笔记可靠，比翻聊天记录快。

---

## 0. 30 秒看懂这个项目

一个 Windows 单 exe 的**车机（Android IVI）测试工具**，CLI + 自绘 WebView2 GUI 双形态，同一个仓库出两个可执行文件。

| 形态 | 入口 | 编译 | 产物 |
|---|---|---|---|
| CLI | `_cs/Program.cs` | `_cs/build.bat` | `adb_log_export.exe` |
| GUI | `_cs/GuiEntry.cs` → `GuiMain` / `GuiWeb` | `adb_log_gui/build_gui.bat` | `adb_log_gui/dist/adb_Tool.exe` |

- **被测对象**：`Max-8838-T75` / `A8R_8295` / `T09M_8295` / `AHT` / `V20` 等车型的中控、副驾、后排、HUD 屏。
- **核心场景**：`场景大师` 语音与功能测试。
- **本质**：一个把 `adb` 能力（日志抓取、投屏、文件管理、APK 管理、语音、网联服务、UI 对比）包进漂亮 GUI 的壳。
- **开发方式**：全程用 WorkBuddy（AI）迭代，用户是 QA 测试工程师孙小伟，按日期/缺陷驱动，产出要能通过飞书交付。

---

## 1. 技术栈已冻结（不许升级、不许引包）

### 1.1 C# 语言版本 5（`csc.exe` from .NET Framework 4.0.30319，`/langversion:5`）

以下写法**编译不过**，看到编译报错先怀疑自己写新语法了：

| 禁止 | 替代 |
|---|---|
| 字符串插值 `$"{x}"` | `"a" + x` |
| `?.` / `?.Invoke()` | `if (x != null)` |
| `nameof()` | 写字符串字面量 |
| 表达式体成员 `=> x;` | 普通方法体 |
| `out var` | 先声明变量再 `out` |
| 元组 `(a, b)` | 用 `out` 参数或小类 |
| `using static` | 全限定名 |

### 1.2 其它冻结项

- **UI 是手写 HTML/CSS/JS，没有前端构建**。`ui.html` 是唯一页面，跑在 WebView2 里。
- **不引第三方 NuGet / npm 包**。WebView2 两个 DLL 随包分发（固定版本）。
- **依赖 GDI+/WinForms**（`System.Drawing` / `System.Windows.Forms`），**不要**换 WPF。
- **CLI 那个 exe 编译时不引用 System.Drawing**。任何 CLI/GUI 共用的文件（如 `Prefix.cs`）里一旦出现 `Color` 类型，CLI 立刻 `CS0234`。→ **共用代码只返回 `int`（0xRRGGBB），GUI 自己转 `Color`**。

---

## 2. 架构与文件地图

```
项目根 C:\Users\李亦\Desktop\Adb_Tool\
├── _cs\*.cs                全部 C# 源码（32 个文件，两个 bat 的编译列表必须覆盖所有 .cs）
├── _cs\build.bat           CLI 编译脚本（显式文件列表，新 .cs 必须加进去）
├── adb_log_gui\
│   ├── build_gui.bat       GUI 编译脚本（同上，末尾有 pause，要 NO_PAUSE=1）
│   ├── webview2\ui.html    唯一页面（≈715 KB，含 4 层注入）
│   ├── adb_Tool.ico        应用图标（由 _icon_v2.py 生成，7 档）
│   └── dist\ / dist_min\   编译产物（不进 Git）
├── _v14..v17.js/.css       前端分层源文件（见 §3）
├── _gen_accent.py          16 色 × 3 主题 = 48 条配色规则生成器（带 WCAG 校验）
├── _icon_v2.py             应用图标生成器（ico 7 档 + 内联 SVG + 预览图，单一来源）
├── cmds.ini                命令注册表（快捷指令的 cmd: 指向这里）
├── _check_features.json    功能清单（52 条），锚点文本 + 测试文件
├── verify_all.py           26 项门禁总入口
├── 377\                    行为测试（headless 浏览器跑 ui.html）
├── release.py              出三个包（完整 / 精简 / 单文件）
├── docs\                   用户手册、UI 清单、功能清单、不变量差异、截图
├── AGENTS.md               硬约束（AI/人共读）
├── STATE.md                当前状态与交接记录
└── .gitignore / .gitattributes
```

关键文件职责一句话：

| 文件 | 一句话 |
|---|---|
| `Prefix.cs` | 共用常量与配置（强调色白名单 `ACCENTS`、`AccentArgb()` 返回 int） |
| `GuiWeb.cs` | GUI 主逻辑：消息路由、scrcpy 内嵌、splash、标题栏、窗口管理 |
| `ui.html` | 唯一页面，含 4 层注入 + 页面骨架 + 全部 JS/CSS |
| `cmds.ini` | 快捷指令的命令定义（`[cmd.xxx]` 段） |

---

## 3. 前端是「分层注入」的（最重要的一条机制）

`ui.html` 里有 4 段被标记包裹的代码，**由源文件生成**：

```
/* === V14 LAYER START === */ ... /* === V14 LAYER END === */    ← _v14.js / _v14.css
/* === V15 LAYER START === */ ...                                ← _v15.js / _v15.css
/* === V16 LAYER START === */ ...                                ← _v16.js / _v16.css
/* === V17 LAYER START === */ ...                                ← _v17.js / _v17.css
（JS 同理，标记是 "V1x JS START/END"）
```

**规则（违反必返工）：**

1. 要改这几段里的东西 → 改 `_vNN.js` / `_vNN.css`，再按顺序重注：
   ```bash
   python _inject_v14.py && python _inject_v15.py && python _inject_v16.py && python _inject_v17.py
   ```
2. **顺序不能乱**，每一层靠替换 `window.xxx` 引用生效，前面没到位后面就白搭。
3. 注入脚本必须**幂等**（重复跑不叠层）。A17 踩过：正则要求 `START === */` 而实际是 `START ===` 换行，每跑一次多一份，同段 CSS 出现两次。
4. `ui.html` 里标记**外面**的部分（页面骨架、A13 标题栏、A15 之前样式）可直接改。
5. 强调色色板（16 个 `.accent-dot`）是手写的，改色必须**三处同步**：生成器 `ORDER`、`var ACCENT_ORDER`、`_cs/Prefix.cs` 的 `ACCENTS`。**`ACCENT_ORDER` 是隐藏门槛：不在表里的色名会被静默回退成 blue**。

---

## 4. 门禁体系（26 项，一条命令 `python verify_all.py`）

### 4.1 26 项清单

| # | 门禁 | 抓什么 |
|---|---|---|
| 1 | 编译列表（两个 bat 覆盖所有 .cs） | 新 .cs 没加进 bat 就红灯 |
| 2 | 功能清单落点（52 项） | `_check_features.json` 每条锚点文本 + 测试文件必须真实存在 |
| 3 | ui.html 静态自检 | 隐式全局、重复 id、硬编码色违规 |
| 4-5 | 页面结构 + 功能套件 | DOM 层级、窗口行为、交互、输出路由、并发互斥等 |
| 5.5 | 根目录 DOM 实测 | v12/v13/a14/16色/Liquid Glass/窗口原生 |
| 5.6 | 冻结层与 A15/A16/A17 落点 | 历次需求落点，误删立刻红灯 |
| 6 | CLI 自检 | 489 条断言 |
| 7 | GUI 自检 | 46 条断言 |

### 4.2 门禁红线

- **验收没通过不许提交。**
- **不许为了让测试变绿去改断言** —— 要么改代码，要么在 `_gate_invariants.py` 里显式登记（新增 `A1x_ADDS`，删除 `A1x_REMOVED`）并写清理由。
- 功能不变量对照（44 项）：新增的 DOM id / 按钮 / 页签 / 消息 kind 必须先在 `_gate_invariants.py` 登记，否则算"未登记新增"。

---

## 5. 硬规则与红线（全部，含踩坑来源）

### 5.1 硬规则 A（违反即返工）

| # | 规则 | 事故来源 |
|---|---|---|
| A1 | 新增 `.cs` 必须**同时**加进 `_cs/build.bat` 与 `adb_log_gui/build_gui.bat` | `Cast.cs` 第一次只加了 GUI，CLI 报 "Compile success" 实际没编进去 |
| A2 | `.bat` 里只写 ASCII 注释与路径 | 中文注释被 cmd 按 GBK 读，命令行拆碎 |
| A3 | 新增页面 `#page-*` 必须是 `.main` 的直接子节点 | `#page-file` 插错父容器，整页空白 |
| A4 | 任何"隐藏"（display:none）都要先想副作用 | 投屏最大化 display:none 导致 img 的 multipart 流挂起，看起来"别的投屏断了" |
| A5 | 诊断脚本必须走前端真实路径 | 加 `?t=` 防缓存后服务端解析崩了，`-castprobe` 没带参数全"通过" |
| A6 | 判定要有正向证据，不能只看退出码 | `pm clear` 失败退出码仍是 0；`screenrecord` 失败输出 0 字节不报错 |
| A7 | 回退必须逐字节核对 | Python 读写 ui.html 把 CRLF 转 LF，diff 不干净 |
| A8 | 不可覆盖用户文件（同名加时间戳） | 覆盖等于毁数据 |

### 5.2 流程规则 B

| # | 规则 |
|---|---|
| B1 | 改前先读代码确认现状（Grep 找实现，不猜） |
| B2 | 先定协议（消息字段/输出源 src/并发归属），再写实现 |
| B3 | 每改一层立刻编译，不攒到最后 |
| B4 | 断言优先做纯函数（Decide / castMapPoint / FsParseLsLine） |
| B5 | 交互改动必须同步改**测试断言**和**手册** |
| B6 | 交付前跑 `python verify_all.py` |
| B7 | 交付永远两个产物：本地包 + 可分享 zip |

### 5.3 输出规则 C

| # | 规则 |
|---|---|
| C1 | 结论带数字（测试通过数、体积、帧率实测值），不写"已优化" |
| C2 | 做不到直说原因，不用"受限于环境"糊弄 |
| C3 | 发现的坑写进注释（`// 事故：...`），避免后人"顺手优化"回去 |

### 5.4 三条最大的坑（AGENTS.md §5）

1. **不要用改窗口尺寸做动画**（会留"巴掌大窗口"）→ 动效只做渲染层 `transform:scale`。
2. **弹窗不要挂在会被裁剪的祖先里**（`.titlebar`/`.tabs` 有 backdrop-filter 形成层叠上下文）→ 用 body 级 `position:fixed` portal。
3. **不要用改 `onQuickSearch` 的方式加防抖**（同步调用者会"点了没反应"）→ 防抖只放事件入口。

### 5.5 红线（绝对不许）

- 不许把 `dist*/` / `release/` / `*.exe` / `ffmpeg.exe` 提交进 Git。
- 不许改 `_check_features.json` 锚点去"绕过"失败（锚点是需求可追溯证据）。
- 不许删 `cmds.ini` 的段来"简化"（快捷指令卡片与它一一对应）。
- 不许把设备密钥、密码、token 写进任何文件。
- 不许在 `.bat` 里写中文。

---

## 6. UI 交互与视觉约定（会反复被问到）

### 6.1 主题与强调色（三套明暗 + 16 色）

- **三套主题**：`dark`（黑夜）/ `light`（白天）/ `eye`（护眼暖纸色），`THEME_ORDER = ['dark','light','eye']`。
- **16 色强调色**：`blue cyan teal mint green yellow orange red pink purple indigo brown graphite purewhite eyewhite glasswhite`。
- **强调色与明暗主题正交**：只切 `--accent / --accent-soft / --on-accent` 三个令牌，背景不动。
- **48 条配色规则**（16 色 × 3 主题）由 `_gen_accent.py` 生成，全部过 WCAG。
- **三白（purewhite/eyewhite/glasswhite）在浅色/护眼下必然是灰**（`#939393`/`#9C9284`/`#8E949E`）—— 白压到可读对比度必然是灰，数学问题，**不是 bug**。
- **图标（logo）跟强调色**：`.appmark { color:var(--accent) }`，启动层和标题栏**统一跟色**，消除"启动层蓝图标 → 主界面白图标"的交接跳变（A19 修复）。

### 6.2 投屏（六格 scrcpy 内嵌）

- **六格**：主屏(displayId 0) / 副屏(4) / 后排屏(1) / HUD(3) / PHUD-B(9) / PHUD-C(10)，`castDefaultId` 映射 `[0,4,1,3,9,10]`。
- **默认小屏显示**，每格独立启停；有 scrcpy 走内嵌（h264 原生帧率 30~60fps，可点击），没有回退内置抓帧（screencap 轮询 1~5fps）。
- **全屏交互**（A19 修复）：点「⤢」按钮扩到全屏 → 底部显示其他位置投屏缩略条 → 点缩略图与全屏互换。全屏/退出全屏通过 hook `castEnterFull`/`castExitFull` 重报 scrcpy Panel 区域比例（`castembedrect`），C# 侧 `ScrcpyEmbedPlace` 识别退化区域（r<=l 或 b<=t）就隐藏 Panel。
- **内置通道 1~5fps**（无线 adb 约 1.5fps）是协议上限，不是参数没调，**不要当 bug 报**。要流畅只能走 scrcpy。
- **`adb root` 不提供**（用户明确要求）—— 会重启 adbd 断掉日志与投屏。

### 6.3 启动加载动画（splash）

- 原生遮罩（`SplashPaint`/`DrawLogo`）+ 网页 `.splash` 两层，**图形同源**（100 视窗：中控屏 + `>_` + 信号双弧 + 底座）。
- 渐变提亮 `#3C3E45→#26282E→#121316`，光晕 blur 78px + 白雾层（用户要"更白更模糊"）。
- 启动闪蓝的根因是 `data-accent="blue"` 写死，已用 `AddScriptToExecuteOnDocumentCreatedAsync` 在首帧前同步 theme/accent。

### 6.4 设置抽屉顺序（Edge 对齐）

主题 → 强调色 → 显示 → 字体。主题卡要保留月亮/太阳/眼睛图标 + 文字横排居中，迷你预览窗口卡做绝对定位装饰背景（不占图标位，A19 修复）。

---

## 7. 三层测试体系（新功能往对应层加，别新造）

| 层 | 入口 | 适合验什么 |
|---|---|---|
| 纯逻辑 | `adb_log_export.exe -selftest`（489 条） | 解析、校验、判定、状态机 |
| GUI 内部 | `adb_Tool.exe --selfcheck`（46 条） | 窗体/WebView 初始化、消息通道 |
| DOM 行为 | `377\_test_*.py`（headless Edge） | 交互、样式、路由、禁用态 |

**核心经验：纯函数优先。** 写不动的逻辑（"重连该不该触发"）先抽成 `Decide(prev, now, curDev)` 纯函数再测，否则只能靠真机碰运气。

---

## 8. 交付与收工流程

### 8.1 收工（改完代码、门禁全绿后）

```bash
cd /c/Users/李亦/Desktop/Adb_Tool

# 1) 编译两条
cmd //c "_cs\\build.bat" < /dev/null
NO_PAUSE=1 cmd //c "adb_log_gui\\build_gui.bat"

# 2) 改了 cmds.ini 的话同步打包源
cp cmds.ini adb_log_gui/cmds.ini

# 3) 全量门禁，必须 0 失败
python verify_all.py

# 4) 提交 + 推送
git add -A
git commit -m "feat/fix: 一句话说清改了什么"
git push
```

### 8.2 出交付物

```bash
python release.py              # 编译 + 完整包 + 最小包 + 单文件 + 三个 zip
python release.py --no-build   # 只重打包（改完 UI 快速出包）
```

三个 zip：完整版（含 ffmpeg，录屏用 ~38MB）、最小版（~1.4MB）、单文件版（一个 exe ~0.86MB）。

### 8.3 「完成定义」（一次改动算完成，5 条同时满足）

1. `verify_all.py` 26 项 0 失败；
2. 新增 id/按钮/消息 kind 已在 `_gate_invariants.py` 的 `A1x_ADDS` 登记；
3. 改了需求落点 → `_check_features.json` 有对应条目；
4. 改了可见行为 → `docs/功能清单.md` / `docs/用户使用手册.md` 同步；
5. `STATE.md` 的验收基线数字是新的。

---

## 9. 环境与已知限制（接手必读）

### 9.1 环境

```bash
python --version     # 3.x，只用标准库
node --version       # 只给 _check_features.js / 377 用
git --version        # >= 2.28
# C#：C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe（系统自带）
```

- 本机用户名是中文（`C:\Users\李亦`），**不要在 .bat 里拼含中文路径**，用 `%~dp0`。
- Git Bash 跑 .bat 要 `cmd //c "..."`；`build.bat` 末尾有 `pause` 必须 `< /dev/null`。
- 编译输出 GBK，管道看中文要 `| iconv -f GBK -t UTF-8`。
- `ffmpeg.exe` 不进 Git（105MB），换机后手动放一份（没它只是"录屏"用不了）。

### 9.2 已知限制（不要当 bug 报）

| 项 | 说明 |
|---|---|
| 内置投屏 1~5fps | 天花板在"每帧搬整图"，要流畅走 scrcpy 内嵌 |
| 三白在浅色下是灰 | 白压到可读对比度必然是灰 |
| `adb root` 不提供 | 用户明确要求去除 |
| 副屏/HUD 不一定支持 screencap -d | 内置通道首帧失败提示改用 scrcpy |

---

## 10. 给 AI 的提示语模板（用户提需求时照着写）

### 新功能：目标一句话 + 交互细节 + 例外边界 + 验收标准

### 改交互：现状 + 期望 + 明确反例（"不要 xxx"）

### 修 bug：现象 + 复现 + 已知条件 + 禁止绕（"不要用轮询绕过"）

### 口径类：文案 + 原因（"pm clear 叫清空数据不能叫清缓存，因为它清全部数据"）

### 回退：明确"这是回退" + 点名同步测试/文档

**三句话开场（缺哪句补哪句）**：
1. 改哪个文件/页面，现状是什么。
2. 期望行为和明确反例（不要什么）。
3. 验收标准（断言数量 / 真机验证 / 交付物）。

---

## 11. 本轮（A19，2026-11-16）改动快照

> 接手时先知道"最近刚动了什么"，避免重复劳动或踩到半成品。

| # | 需求 | 落点 |
|---|---|---|
| 1 | 投屏全屏交互修复 | scrcpy 内嵌默认小屏；点「⤢」全屏，底部缩略条切换。hook `castEnterFull`/`castExitFull` 重报 Panel 区域（`_v17.js`）；`ScrcpyEmbedPlace` 识别退化区域隐藏 Panel（`_cs/GuiWeb.cs`） |
| 2 | 图标跟色 + 消除交接跳变 | `.appmark { color:var(--accent) }` 统一跟色（`_v17.css`），删掉旧的 `.splash .appmark` 覆盖 |
| 3 | 主题图标恢复 + 文字居中 | `.theme-card` 恢复图标+文字横排居中，迷你预览卡改绝对定位装饰（`_v17.css` + `ui.html` buildThemeSeg 包 `.tc-ic`） |
| 4 | 文档 | 生成本文档 `docs/AI开发交接总纲.md` |

门禁状态：26 项 0 失败（A17 落点 64/64、功能清单 52/52）。

---

## 附：最常用的 5 个命令（贴在脑门上）

```bash
python verify_all.py                                              # 门禁，改完必跑
python _inject_v17.py                                             # 只重注 V17（改 _v17.js/.css 后）
python _inject_v14.py && python _inject_v15.py && python _inject_v16.py && python _inject_v17.py  # 全量重注
NO_PAUSE=1 cmd //c "adb_log_gui\\build_gui.bat"                   # 编译 GUI
python release.py                                                 # 出包
```
