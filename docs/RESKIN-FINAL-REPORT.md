# RESKIN-FINAL-REPORT · Apple UI 全面替换验收报告

> 日期：2026-11-15 02:47
> 范围：按 `adb_Tool-Apple-UI替换-提示词与Skill组合.md` 的 A0–A11 执行，B1–B5 技能口径。
> 基线：用户指定的 `Adb_Tool_成品_20261115_0138`；源码 `C:\Users\李亦\Desktop\Adb_Tool`。
> 结论：**四道门禁全过，覆盖率 100%（⬜=0），功能回归一致。可以交付。**
> 但必须同时读 §7「超出纯换肤范围的声明」与 §8「遗留项」。

---

## 1. 四道门禁结论

| 门禁 | 结论 | 证据 |
|---|---|---|
| **1 功能回归** | ✅ 通过 | `INVARIANT-DIFF.md`：34 项对照 0 失败。项目非 git 仓库，改用「阶段 0 快照 vs 当前源码逐项解析」等价核验。kind 28 / onclick 59 / DOM id 135 / 5 页签 / 5 页面 / THEME_ORDER / 消息桥全部一致 |
| **2 零遗漏** | ✅ 通过 | `COVERAGE.md`：总项 456 / ✅450 / ⬜0 / N·A6 / 有效分母 450 / **100%**。`UI-RESKIN-INVENTORY.md` 逐 ID 列出 |
| **3 Apple HIG + 无障碍 + 图标终审** | ✅ 通过（有边界） | HIG 常载项（accessibility / layout / typography / color）按桌面工具型核对；三态语义色、`:focus-visible`、`prefers-reduced-motion` / `reduced-transparency` / `contrast` 齐备；日志等级保留字母徽章不靠颜色单独表意；图标 `currentColor`、硬编码色 0、7 尺寸 ico 同源。**对比度按令牌 hex 计算，未做截图采样** |
| **4 交付与同步** | ✅ 通过 | `verify_all.py` **16 项 0 失败**；`release.py` RC=0；`_check_apple_release.py` U1–U6 / 三包 / ico / cmds.ini **0 失败** |

### 门禁数字明细（`verify_all.py`）

| 项 | 结果 |
|---|---|
| 编译列表（两个 bat 覆盖所有 `.cs`） | PASS |
| 功能清单落点 | PASS · **35 项**（本轮新增 `cfg.ico_sync`） |
| ui.html 静态自检 | PASS · 含新增 §13 Apple 断言 5 条 |
| 页面结构 / 窗口与记录 / 交互与输出区 | 48/48 · 196/196 · 75/75 |
| 输出路由 / 并发互斥 / 批量输出 | 27/27 · 15/15 · 14/14 |
| APK 管理 / 无线 adb / 文件管理 | 58/58 · 21/21 · 42/42 |
| 文件搜索与监听 / 投屏 | 42/42 · 115/115 |
| CLI 自检 / GUI 自检 | 491 条 0 失败 · 42 条 0 失败 |
| **合计** | **16 项，失败 0 项** |

---

## 2. 覆盖率

`COVERAGE.md`：总项 **456**，✅ **450**，⬜ **0**，N·A **6**，有效分母 450，**覆盖率 100%**。
状态矩阵按组件八态（24×8=192 格）与视图五态（13×5=65 格）逐单元格展开，共 257 格，全部 ✅。

N·A 六条（逐条理由写在 `COVERAGE.md`）：
`ICO-05`（ShowIcon=false 属功能冻结）、`ICO-07`（系统 MessageBox 图标）、
`ICO-08` / `ICO-09`（md 未定义编号）、`ICO-35`（投屏设备原图禁止主题化）、
`ICO-36`（WebView2 宿主无 favicon 需求）。

两个**旧成品目录**（`Adb_Tool_成品\`、`Adb_Tool_成品_20261114_2341\`）标 N·A：
它们的 exe 没有本轮新增的 `/snap` 端点，若把新版外置 `ui.html` 放进去，底部缩略条会请求 404 反而黑屏，属于功能倒退。本轮只维护最新版。

---

## 3. 改动文件总表（层级判定）

| 文件 | 层级 | 改动 |
|---|---|---|
| `adb_log_gui/webview2/ui.html` | **允许层**（`<style>` / class / 内联 SVG）+ **A9 追加轮**（渲染与事件函数） | 三态 Apple 令牌、字体栈、8pt 网格、组件八态 / 视图五态、玻璃仅给 chrome、三套无障碍降级；24 处 SVG 单线化 + `currentColor`；品牌改 Apple 单线终端；`quickGroups` 死数据 `color` 改 `var(--accent)`；`/snap` 缩略条 + 停止按钮 + 搜索点击进树 |
| `adb_log_gui/adb_Tool.ico`、`icons/adb_Tool.ico` | 允许层（图标资源） | 重绘为 7 尺寸 Apple 单线终端，两份字节一致（5,627 B） |
| `adb_log_gui/icons/svg/Apple终端标识.svg` | 允许层（新增） | 可编辑 SVG 源 |
| `_cs/Cast.cs` | **A9 追加轮（超出纯换肤）** | 新增 `/snap/<slot>` 单帧短连接端点，返回最近一帧 PNG，`Connection: close`；没有帧时 204 |
| `adb_log_gui/build_gui.bat`、`make_min.bat`、`release.py` | 构建入口（图标专项所需） | 三个入口都把 `adb_Tool.ico` 拷进 `dist` / `dist_min` / `dist_single`（出包核验发现原先漏拷，已加 `cfg.ico_sync` 机检防复发） |
| `_check_features.json` | 机检配置 | 34 → 35 项，新增 `cfg.ico_sync`；此前已登记 `fs.search-click` / `cast.strip-snap` / `cast.strip-stop` / `apple.tokens` / `apple.icons` |
| `377/_check_ui.js` | 测试 | 2 条旧颜色断言改为语义令牌断言；新增 §13 五条 Apple 断言 |
| `377/_test_ui_behavior.py` / `_test_ux.py` / `_test_fs_search.py` / `_test_cast_ui.py` | 测试 | 旧断言写死 `rgb(224,108,108)` / `#3fb99b` / `#e8a33d` / `#a8761f` / `/live/1`，改为检查 `--err` 语义值、形状语义 + `currentColor`、`/snap/` 端点；补「三态图标零硬编码色」 |
| `docs/*.md`（8 份） | 文档 | 手册加 §16、功能清单加 §9、命令对照加 §6；新增 `FUNCTION-INVARIANTS.md` / `INVARIANT-DIFF.md` / `UI-RESKIN-INVENTORY.md` / `COVERAGE.md` / `DESIGN.md` / 本报告 |
| `_gate_invariants.py` / `_build_inventory.py` / `_make_preview.py` / `_check_apple_release.py` | 新增只读门禁 | 不变量对照 / 清单与覆盖率生成 / 组件状态墙 / 出包同步核验 |
| `cmds.ini`、`adb_log_export.ini`、所有命令串、消息 kind、`post()` / `sendCmd()` / `switchTab()` 等函数签名、DOM id、快捷键、行为常量 | **禁止层** | **0 改动**（`INVARIANT-DIFF.md` 34 项逐条确认） |

---

## 4. U1–U6 副本同步状态

| ID | 位置 | 状态 | 证据 |
|---|---|---|---|
| U1 | `adb_log_gui/webview2/ui.html` | ✅ 源 | 287,322 B / sha `f8686c7996da68a1` |
| U2 | `adb_log_gui/dist/webview2/ui.html` | ✅ | 与 U1 逐字节一致 |
| U3 | `adb_log_gui/dist_min/webview2/ui.html` | ✅ | 与 U1 逐字节一致 |
| U4 | 单文件版 exe 内嵌 ui.html | ✅ 重编译 | exe 1,492,480 B，含 `castRefreshStripFrames` / `/snap/' + i` / `cast-thumb-stop` / `data-search="1"` / Apple 令牌 / `/snap` C# 端点 |
| U5 | 三个 zip 内 `webview2/ui.html` | ✅ | 完整版 / 最小版 zip 内文件与 U1 逐字节一致；单文件版走内嵌 |
| U6 | 本轮成品目录 exe 同级 `webview2/ui.html` + `adb_Tool.ico` | ✅ | 组装时放入，与 U1 / ICO-01 逐字节一致 |

ICO 同步：`ICO-01` = `ICO-02` = `dist` = `dist_min` = `dist_single` = 三个 zip（有外置位的）= 成品目录外置，全部 5,627 B 同一份；`ICO-03` exe 内嵌 `/win32icon` 已随 `build_gui.bat` 重编译。

---

## 5. 《功能回归对照表》（A8 门禁 1 摘要）

| 操作路径 | 改造前 | 改造后 | 一致 |
|---|---|---|---|
| 切换 5 个页签 / Ctrl+K / Ctrl+1..4 / Alt+↓ | 正常 | 正常（`_test_structure.py` 48/48、`_test_ux.py` 75/75） | ✅ |
| 点卡片执行 / 停止 / 带参补参数 | 正常 | 正常（196/196） | ✅ |
| 多槽并行输入 / 增删槽 / 输出不覆盖 | 正常 | 正常（196/196） | ✅ |
| APK 管理增删改 / 批量查版本 / 前台四指令 | 正常 | 正常（58/58） | ✅ |
| 双栏树拖拽 / 同名加时间戳 / 传输进度 | 正常 | 正常（42/42） | ✅ |
| 主题三态循环 + `theme=` 持久化 | 正常 | 正常，THEME_ORDER 未动（75/75） | ✅ |
| 日志等级 V/D/I/W/E + 「未设置」占位 | 正常 | 正常，字母徽章保留、颜色换语义令牌 | ✅ |
| 投屏 6 格 / 最大化 / 录制 / 点击换算 / scrcpy | 正常 | 正常（115/115） | ✅ |
| 断线 / 无 root / 空态 / 超时 | 正常 | 正常，见清单 §15 最坏数据表 | ✅ |
| **底部缩略条（>2 路）** | 黑屏 | 显示最近一帧并每秒刷新 | **修复** |
| **全屏时关闭别路投屏** | 无入口 | 每路常驻「×」 | **修复** |
| **搜索结果进入下一级** | 「进入 ⤵」按钮 | 点整行进入树，与未搜索一致 | **修复** |

---

## 6. 技能口径（B1–B5）

按 B1 判定为 **Windows 桌面 · 工具型 / utility**：动效近乎不可见、spring ≤300ms、cinematic OFF、Bento 不套用。
本轮实际使用：`apple-design-family`（HUB：Clarity / Deference / Depth）、`apple-design-foundations`（语义色 / 系统字体栈 / 8pt）、
`apple-design-materials`（玻璃只给 chrome）、`apple-design-tactics`（WCAG 2.2 AA、44pt、三偏好降级、不靠颜色单独表意）、
`apple-design-hig`（accessibility / layout / typography / color 常载）、
`finesse-ui`（product register 的 audit / component-scope / redesign 只读流程）、
`break-ui`（最坏数据补隐藏状态）。
按 B3 明确**未用**：`apple-design-web`、`apple-design-os`、`mobile-native`、`apple-design-backend`、`frame-smith`、`write-swift`、`animate-expo`、`ask-sonner`、`finesse-brief`。
`learn-taste` 的沉淀落在 `docs/DESIGN.md`（12 条「别这么做」）；`prototype` 只用于图标方向，未用于整页。

---

## 7. ★ 超出纯换肤范围的声明（必读）

A10 契约规定「只改 `ui.html` 表现层，exe / ini / C# 一律不动」。
但用户本轮**显式追加了 3 个交互缺陷修复**，它们无法只靠 CSS 完成：

- `A9-01` 底部缩略条黑屏 → 需要 `_cs/Cast.cs` 新增 `/snap/<slot>` 端点 + `ui.html` 改 `castRenderStrip()` / `castRefreshStripFrames()`；
- `A9-02` 全屏缩略条缺停止按钮 → 需要改 `ui.html` 渲染与事件委托；
- `A9-03` 搜索结果进入方式 → 需要改 `ui.html` 的 `renderFsSearch()` / `bindFsRows()` / `dblclick` 处理。

按 A9「追加轮」处理：追加 ID、重算分母、沿用已锁定的三态令牌与图标规范、不重新发明设计语言。
**同时必须重编译 exe**（否则 `/snap` 404、任务栏还是旧图标），并同步三处构建入口的外置 ico。
以上改动**未新增 `msg.kind`、未改 `post()` 签名、未改命令串 / ini key / DOM id / 快捷键**，冻结层仍为 0 改动。

---

## 8. 遗留项 / 需人工确认项

| # | 项 | 状态 | 说明 |
|---|---|---|---|
| 1 | 真机（车机设备）手测 | **未做** | 本轮只跑无头 DOM 门禁、静态自检、不变量对照。6 路投屏并发、`/snap` 在真实 adb 截帧压力下的表现需 QA 现场验证 |
| 2 | dark / light / eye 三套逐页截图索引 | **N·A** | 当前环境没有连接车机、也没有 WebView2 宿主截图工具。替代证据：`docs/COMPONENT-STATES.preview.html`（内嵌产品真实 `<style>`，可切三态）与 16 项 DOM 门禁 |
| 3 | Windows 图标缓存 | 提示 | exe 内嵌图标与外置 ico 都是新的；若任务栏 / Alt+Tab 仍显示旧图，重启资源管理器或注销一次 |
| 4 | 组件状态墙逐组件 `.preview.html` | 合并交付 | A4 原要求每个组件一份；本项目是单文件 UI，改为 1 份合并状态墙（24 组件 × 8 态 + 13 页 × 5 态矩阵在清单里逐格列出），避免往生产目录塞 20+ 个非生产文件 |
| 5 | 两个旧成品目录 | N·A | 见 §2，放新版外置 UI 会功能倒退 |

---

## 9. A1 固定格式输出（本轮）

**① 本轮处理的清单 ID**（完整枚举见 `UI-RESKIN-INVENTORY.md`）
`P-01` `P-02` `P-03` `P-04` `P-05` `P-06` `P-07` `P-08` `P-09` `P-10` `P-11` `P-12` `P-13`；
`C-01`…`C-24`；`S` 组件八态矩阵 192 格 + 视图五态矩阵 65 格；
`T-001`…`T-051`、`T-A01`…`T-A08`；`F-01`…`F-08`；`N-01`…`N-12`；`M-01`…`M-11`；
`H-01`…`H-06`；`D-01`…`D-08`；`K-01`…`K-09`；`W-01`…`W-04`；
`ICO-01`…`ICO-36`、`U1` `U2` `U3` `U4` `U5` `U6`；`A9-01` `A9-02` `A9-03`。

**② 覆盖率表**：总项 456 / ✅450 / ⬜0 / N·A6 / 有效分母 450 / **100%**。N·A 逐条理由见 `COVERAGE.md`。

**③ 改动文件清单与层级**：见 §3，每项都标了「允许层 / A9 追加轮 / 禁止层」。

**④ 功能不变量核验结论**：冻结层 **0 改动**；A9 三项按追加轮处理并已在 §7 声明越界；34 项对照 0 失败。

**⑤ U1–U6 同步状态表**：见 §4，六处全 ✅。

**⑥ 下一批要处理的 ID**：无。⬜=0，本轮清单已闭合；后续若新增页面 / 图标 / 交互，按 A9 追加新 ID 并重算分母。

---

# 附：A11 轮（2026-11-15 03:05–03:40 需求）验收报告

## 1. 需求 → 交付对照

| 时间 | 需求原文要点 | 交付 | 证据 |
|---|---|---|---|
| 03:05 | A11 清单规格：总项数 / 分母版本 / 覆盖率基线 / 分类前缀 / 三条规则 | `UI-RESKIN-INVENTORY.md` 分母 v3，548 项；`COVERAGE.md` 按 `✅/(总−N·A)` 计算 | `python _build_inventory.py` |
| 03:06 | 整体没变化，通读文档优化；白天模式顶栏未跟随 | 三态顶栏跟随已核实（此前是 headless 读到过渡起始帧的误判） | `_diag_theme.py` |
| 03:11 | 9 色强调色，只切按钮/进度条/选中色 | `#accent-picker` + 27 条覆盖层 + 持久化 | `_check_accent_dom.py` 13/13、`ACCENT-CONTRAST.md` 27 组 |
| 03:23 | 自定义 ADB 指令全流程 | `#custom-panel` / `#custom-mgr` / `CustomStore.cs` | `377/_test_custom_cmd.py` 52/52 |
| 03:24 | 保留明暗，新增颜色 | 两条正交轴（`data-theme` / `data-accent`） | 切色不改 `.frame` 背景（实测） |
| 03:27 | 性能与健壮性、闪退排查 | `perf.crash-guard`：8 处修复 | 编译通过 + 见 §3 |
| 03:30 | UI 大变样（毛玻璃 / 渐变） | `GLASS LAYER`：光雾背景 + 玻璃 chrome + 卡片光学 | `_check_glass.py` 20/20 |
| 03:35 | 图标重设计（简约 / 大气 / 车载+测试+联网） | `_icon_v2.py`：中控屏 + `>_` + wifi 弧，7 档 ico | `_gate_invariants.py` ICO-01..04 全绿 |

## 2. 门禁结果（全绿）

| 门禁 | 结果 |
|---|---|
| `_gate_invariants.py` | 44 项，失败 0 |
| `node 377/_check_ui.js` | 全部通过 |
| `node _check_features.js` | 40 项通过 |
| `_check_accent_dom.py` | 13/13 |
| `_check_glass.py` | 20/20 |
| `377/_test_custom_cmd.py` | 52/52 |
| `verify_all.py` | 16 项，失败 0 |

## 3. 闪退排查：从"现象"到"根因"

用户描述：**"工具一直在打开，突然就在 dock 栏没看到工具了"** —— 没有任何提示、没有日志。

取证路径：`%LOCALAPPDATA%\adb_Tool\logs\gui_error.log` / `gui_trace.log` / `gui_perf.log`。
判断规则：`gui_error.log` 里有 `[非UI线程]` 才是线程异常；**两个文件都干净 = 指向硬退出**。

按可能性排序，本轮修掉的（全部改在 `_cs/`）：

| # | 隐患 | 后果 | 修复 |
|---|---|---|---|
| 1 | `Program.cs` 的 `q/quit/exit` → `Environment.Exit(0)` | 命令框敲这四个字母 = 进程无提示消失，正是用户描述的现象 | 新增 `App.GUI_MODE`，GUI 下拒绝退出并提示 |
| 2 | `CastLoop` / `CastTapWorker` / `FireReconnect` 线程委托无兜底 | 工作线程异常直接终止 CLR | 三处补最外层 try/catch；`_reconnecting`/`_castTapBusy` 用 finally 复位 |
| 3 | `CastGrabPng` 的 `CopyTo` 无超时 | adb 卡住 → 采集线程永久阻塞、screencap 越积越多 | 后台线程拷贝 + `WaitForExit(8000)` 超时 Kill + stderr 排水 |
| 4 | `PumpOutput`（UI 线程 Timer）无兜底 | 单帧异常即崩窗口 | 整体 try/catch + Dump |
| 5 | `OnFormClosing` 不停投屏 | 关窗瞬间重建 adb 子进程（僵尸） | 补 `App.CastStopAll()` |
| 6 | `SetTitleBarDark(dark=true)` 不回退属性号 19 | Win10 1809 前标题栏明暗不同步 | 与 false 分支一致，失败回退 19 |
| 7 | `CustomStore.Dir()` 用 `Path.Combine` 结果判空 | 恒为假，可能把配置落到进程目录 | 先判基目录再拼接 |

## 4. 性能护栏（写进 CSS 注释，防止后人破坏）

- `backdrop-filter` 只出现在结构层；卡片、日志区、终端区、投屏画面零 blur。
- 背景光雾只动 `transform`，无 `filter`、无 `background-position` 动画。
- 动效统一 ≤ 300ms，`prefers-reduced-motion` 下全部关闭。

## 5. 已知取舍

- 16px 图标去掉了信号弧：1px 以下的双弧只会糊成噪点，这是**有意的多尺寸简化**，不是遗漏。
- 强调色的白/黑在浅底会自适应为中性灰：否则按钮字对比度不足，属无障碍优先。
- 自定义指令的 `loop` 只重复「上一条命令」，不支持嵌套子流程 —— 与"节点必须间隔命令"的约束一致。

# 附：A12 轮（2026-11-15 13 条需求）验收报告

## 1. 需求 → 交付对照（逐条）

| # | 需求原文 | 交付 | 证据 |
|---|---|---|---|
| ① | 顶部状态栏的颜色也要跟随变化 | `FormBorderStyle.None` + 自绘 `#titlebar`，底色走 `--chrome` | `_shot_ui.py` 三主题像素：dark `(22,21,24)` / light `(254,254,255)` / eye `(255,251,240)` |
| ② | 切换模式顶部状态栏没变化 | 同上，标题栏与顶栏共用同一令牌，无二次同步 | 切三主题标题栏色差实测 > 200 |
| ③ | 这个点不要多余了（`.acur` 红点） | 删除 `.acur` 及 `accent-btn` / `accent-pick` 浮层 | `_check_v12.py`「无多余红点」断言 |
| ④ | 逆向 npp，文本功能加到 UI 右侧 + 文本 tab | 第 6 页签 `#page-text`：多标签、行号、状态栏、查找替换、跳行、换行、字号、撤销重做；C# 真实读写 | `377/_test_structure.py` 48/48；`_check_v12.py` 文本全链路 |
| ⑤ | 右上角设置按钮，主题/颜色/icon 全集成 | `#set-mask` 抽屉：主题 3 段 + 9 色 + 字体 + 关闭 | `_check_accent_dom.py` 13/13（色板在抽屉内可点选生效） |
| ⑥ | 设置里加字体，选择时全局切换 | 内置 Inter / JetBrains Mono（OFL，base64 woff2）+ 系统 5 款 + 自定义；`:root` 令牌 | 34 处硬编码 `font-family` 清零；`_check_v12.py` 字体全局断言（含标题栏继承） |
| ⑦ | 使用说明，扫描已实现功能，颜色字体跟随 | `#help-mask` 12 章 + 运行时扫描指令目录 + 搜索过滤 + 目录高亮 | `_check_v12.py` 帮助 12 章 / 搜索 / 目录扫描 |
| ⑧ | 设置里加关闭应用；这一块字体要和全局一致 | 抽屉内「关闭应用」；面板字体走 `--font-ui` 不写第二套 | 同 ⑥ 字体断言覆盖设置面板 |
| ⑨ | 没有图片这里就显示空 | `uiResultImgErr()` + `alt=""` + 空态占位 | `_check_v12.py` 结果图空态 |
| ⑩ | 文件里这个按钮要支持切换（左右换边） | `fsSwapSides()` 交换两栏 + 箭头方向跟随 | `_check_v12.py` 换边断言 |
| ⑪ | 增加鼠标拖宽（参考资源管理器列宽） | 4 个表头夹子写 `--w-name` / `--w-size`，localStorage 持久化 | `_check_v12.py` 4 个夹子命中 + 拖动改写宽度 |
| ⑫ | UI 再优化，去 GitHub 参考 | 6 枚内联页签图标、统一滚动条/焦点环/按压态、新增 6 个尺寸令牌 | 静态自检 + 截图 |
| ⑬ | 全面测试验收后飞书发 | 20 项门禁全绿 + 出包 U1–U6 同源核验 | 本文 §2 |

## 2. 门禁结果（20 项 0 失败）

| 门禁 | 结果 |
|---|---|
| `_gate_invariants.py` | 44 项，失败 0（新增 `A12_ADDS` 28 onclick / 34 id / 5 kind，`A12_REMOVED` 3 onclick + 3 id 逐条写理由） |
| `node 377/_check_ui.js` | 全部通过 |
| `node _check_features.js` | 46 项通过（新增 6 条：`ui.titlebar` / `ui.settings` / `ui.font` / `help.panel` / `text.editor` / `fs.pane-tools`） |
| `377/_test_structure.py` | 48/48 |
| `377/_test_ux.py` | 75/75 |
| `_check_v12.py` | 75/75 |
| `_check_accent_dom.py` | 13/13 |
| `_check_glass.py` | 20/20 |
| `_smoke_win.py` | 12/12（真机起窗） |
| `verify_all.py` | 20 项，失败 0 |

盘点分母：**v3 → v4**，总项 477 → **556**，✅ 550 / N·A 6，覆盖率 **100%**。

## 3. 三个"看似能做、实际做不到"的判断（避免下次返工）

1. **想给原生标题栏设主题色 → 不可行**。DWM 标题栏在深浅两套系统主题下都是纯黑 + 白字，
   不读应用配色。只能自绘。这一条直接决定了本轮 `FormBorderStyle.None` 的取舍。
2. **无边框后想靠 `WM_NCLBUTTONDOWN + HTSE` 缩放 → 不可行**（实测 delta=0）。
   没有 `WS_THICKFRAME`，系统不进入 NC 缩放循环。必须页面算位移、C# 套 `Bounds`。
3. **WebView2 里用 `screenX` 算拖拽位移 → 不可行**。`screenX` 不跟随窗口移动，
   必须用 `movementX/Y` 累加并乘 `devicePixelRatio`。

## 4. 已知取舍

- 自绘标题栏后失去系统 Aero Snap 边缘吸附（拖到屏幕边自动半屏）。当前用
  `MaximizedBounds = WorkingArea` 保证最大化不盖任务栏；如果需要 Snap，得补
  `WM_NCHITTEST` 返回 `HTLEFT/HTRIGHT` 等，属下一轮可选项。
- 文本页限 2MB：超过会卡界面，提示走外部编辑器。
- 系统字体（雅黑/等线/楷体等）依赖本机安装；未安装的自定义字体回退系统默认 + toast。

---

# 附录 A13：2026-11-15 第六轮（四圆点 / 圆角 / 跨屏最大化 / 终端多行 / 输出区热区）

用户 9 条 + 指令界面 5 条 + 2 条补充，共 16 条。**9 项落地、1 项按用户指令 N·A**。

## 1. 需求 → 交付对照

| # | 用户需求 | 交付 | 证据 |
|---|---|---|---|
| 1 | 删掉标题栏品牌字「网联服务_Adb_Tool」 | 删 `.tb-name`，只留 logo（悬停显全名） | `_check_v13.py` 断言 `.tb-name` 不存在 |
| 2 | 四状态改成只显示圆点 | `#tb-status` 四点，26px 命中区 / 9px 圆心，文字全 `display:none` | 37 项断言含「文字全部隐藏」 |
| 3 | 多行 Enter 逐行顺序执行 | `_txQ` 队列 + `end` 回包驱动 | `one→two→three→不再多发` 实测 |
| 4 | `WM_NCHITTEST` 返回 HTLEFT/HTRIGHT | **N·A**（用户明确「维持现状」） | 清单 A13-04 记录理由 |
| 5 | 圆角兼容 Win11 + Win10、效果要好 | Win11 DWM / Win10 Region 双轨 + 读回校验 + DPI 重算 | `_cs/GuiWeb.cs` 三处 P/Invoke |
| 6 | 外接 27 寸屏最大化铺满 | `WM_GETMINMAXINFO` 实时按当前屏工作区 | `_smoke_win.py` 1920×1040 不盖任务栏 |
| 7 | 齿轮并入标题栏、删 `.topbar` 整行 | `.titlebar` 接管玻璃层与 1px 描边 | `_check_glass.py` 6 处改 `.titlebar` |
| 8 | 日志等级一直「未设置」 | 根因：早退在 `getprop` 之前；已提到早退前独立读 | `_cs/Adb.cs` |
| 9 | 终端换行 + 四按钮纯图标 | `<textarea>` + `txAutoGrow`（≤5 行）+ `Shift+Enter`；按钮 `34px` 纯 icon | `_check_v13.py` |
| 10 | 删侧栏「指令」标题 | `qnav-title` 整段删除 | `_check_v13.py` |
| 11 | 输出区收起态点空白展开、展开态点空白收起 | `fbHeadToggle()` + 可交互元素白名单 | 点表头空白收起 / 点按钮不收起 |

## 2. 门禁结果（全绿）

- `verify_all.py`：**21 项 0 失败**（新增 `_check_v13.py` 37/37；`_check_v12.py` 75/75、
  `_check_glass.py` 20/20、`377` 九套件、CLI 489 条、GUI 42 条同步通过）
- `_gate_invariants.py`：**44 项 0 失败**（新增 `A13_ADDS` 登记 3 个落点，
  零硬编码色规则靠 `--tb-dot-ring` / `--tb-tip-shadow` 两个令牌通过）
- `_check_apple_release.py`：U1–U6 **0 失败**（补 7 个 A13 字符串标记 + 3 条 C# 源核验）

## 3. 「看似能做、实际做不到 / 做了更糟」的判断

1. **`SetWindowRgn` 抗锯齿**：做不到。WebView2 不支持透明分层窗口，
   `WS_EX_LAYERED` 那条路是死的，Win10 上 1px 台阶是物理上限。能做的只是把半径算准 + 底色跟主题。
2. **`MaximizedBounds` 修跨屏**：修不了。它只在 `OnLoad` 生效，必须换 `WM_GETMINMAXINFO`。
3. **多行命令拼 `a;b`**：不行。`cmds.ini` 的命令是应用内前缀不是 shell 语法。

## 4. 已知取舍

- Win10 圆角边缘 1px 台阶（系统限制，已在上表说明）。
- 圆点无文字 → 依赖 60ms 即时 tooltip；键盘用户仍可通过 `title`/`aria-label` 获知语义。
- 自绘标题栏仍无 Aero Snap（与本轮 N·A 的第 4 条同一原因）。

---

# 附录 A14：2026-11-15 第七轮（网联服务 13 条 + 界面 8 条）

用户两批需求：网联服务 13 条（第 2 批）、界面 8 条（第 3 批），**21 项全部落地**。
第 2 批第 3 条要求「暂停飞书，先本地生成」——本轮未发飞书。

## 1. 界面 8 条 → 交付对照

| # | 用户需求 | 根因 | 交付 | 证据 |
|---|---|---|---|---|
| 1 | 启动动画换成最新 icon，颜色跟随强调色 | 启动动画是旧版手绘 SVG，与 ico 不同源 | 启动动画与标题栏 logo 换成与 ico 同源的图标（双弧 + 中控屏 + `>_` + 底座）；`.splash .cat{color:var(--accent)}` | `_check_a14`：启动图标含 `M9.1 20.9h5.8`（双弧）与底座路径；图标色 `rgb(10,132,255)` = `--accent` |
| 2 | 白天模式白底上边界不清 | 不是描边细，是**底色与卡片同白**（#f2f2f7 vs 白 = 1.05:1） | 灰底 + 白卡分组式：新增 `--a14-page`（light `rgba(232,232,239,.88)` / eye `rgba(240,231,211,.90)`） | 卡片边框对比度 light 2.24:1 / eye 2.04:1 |
| 3 | 左上角 icon 太小 | 固定 px，不跟布局 | `.tb-logo svg{width:calc(var(--tb-h)*.54)}` | 实测 ≥ 20px |
| 4 | 白天/护眼界面与按钮区分不明显 | 只靠一个 `--border`，卡片走玻璃层 `--edge(.055)` = **1.25:1** | 五层叠加：页面底 / 卡片边令牌 `--a14-card-edge` / 按钮独立面 `--well` / 导航选中色条 / 分组标题加粗 | 见上表数值 |
| 5 | 黑夜下设置字体下拉显示白底 | Chromium 原生 `<select>` 弹层，CSS 改不动 | 捕获阶段拦 `mousedown` → 自绘 `.a14-selpop` → 回写 `select.value` + 派发 `change` | `_check_a14`：浮层非白底、列出全部字体、当前项有标记、Esc 可关 |
| 6 | 红框中文去除 | 预览文案与关于区应用名是中文 | 预览 → `Adb_Tool 12345 ABCdef`；关于 → `adb_Tool`（版本行保留中文） | `_check_a14`：预览/主名无中文（跳过 `.dim`） |
| 7 | 黑夜下文本页格式设置（编码/换行）显示白底 | 同 5 | 同一套自绘浮层，自动覆盖动态 select | `_check_a14`：换行下拉同样是浮层、非白底 |
| 8 | 设置增加字体大/中/小，整页跟随 | 逐条改 px 必漏 | `WebView2.ZoomFactor`（s .90 / m 1.00 / l 1.15），持久化 + 夹紧 .75~1.6 | `_check_a14`：三段文案、`uizoom` 值、偏好 `size=l/s`、选中态 |

## 2. 网联服务 13 条

分组位置：**「指令执行」之后第二位**（原「方控按键」起整体顺延一位，`377/_test_ui_behavior.py` 的 P6 五条断言已同步）。
4 个分类 13 张卡：后台入口 4 / 日志导出 3 / 星河云埋点 4 / 云平台 2。

分工原则（与既有约定一致）：

- **纯单行 shell → `cmds.ini`**：`[cmd.wsconfig]` 配置中心后台、`[cmd.wsalipayset]` 支付宝后台、
  `[cmd.wsalipayup]` 上传日志。改包名/Activity 不用重编译。
- **需要控制落点、等重启、开浏览器 → 内置前缀**：`:wsalipay` / `:wswmpf` / `:wswx` /
  `:sxlog [on|get|set]` / `:wsdevid` / `:url`。

几个实现要点：

1. **同名路径规避**：`/sdcard` 是 `/storage/emulated/0` 的软链，两条都拉 = 传两遍。
   改主备回退（先 `/sdcard`，成功即止），落点名分开 `xlog_sdcard` / `xlog_storage`。
2. **重启后继续**：`cmds.ini` 一条 `run` 只能一行，表达不了「等 + 条件继续」，所以必须写进代码。
   `WaitBoot(60)` 双判定：`adb get-state` 回 `device` **且** `sys.boot_completed=1`
   （只满足前者时设备还在开机动画，此时 `settings put` 会被吞）。
3. **可中断**：GUI 的「停止」是 kill adb 进程，对纯 `sleep` 轮询无效。
   另立 `App.GUISTOP` volatile 标志，`StopWorker` 置位 / `SubmitCmd` 清零，循环每 2s 读一次。
4. **`:url` 是桌面浏览器**（`Process.Start(UseShellExecute)`），不是车机 `am start`；schema 可省。
5. **写后回读**：`:sxlog set` 写完立刻 `settings get` 回读，不是发完就算成功。

## 3. 本轮修掉的两个既有问题（不影响用户操作，但影响结论可信度）

1. **玻璃层被写死** —— V14 一开始用不透明纯色给 `.frame` 上底，把 A11 玻璃层背后漂移的光雾糊死了。
   `_check_glass.py` 的护栏当场报红（light/eye 各一条）。改带 alpha 的 rgba 后 20/20 恢复。
   **教训：给 `.frame` 加底色必须留透明度，护栏就是为了这个存在的。**
2. **窗口冒烟测试抓错窗口** —— 原来按标题 `网联服务_Adb_Tool` 匹配取 `found[0]`。
   而机器上正开着上一版交付的 `网联服务_Adb_Tool_完整版_20261115`，标题前缀完全一致，
   于是量的是那个旧窗口（`style=0x14cf0000` 正是 `WS_OVERLAPPEDWINDOW`，尺寸停在 940x640），
   五条几何断言集体红。**改成 `GetWindowThreadProcessId` 按 PID 认领**，别人的窗口再同名也不会误认。
   清理逻辑同时收窄为「只清本目录这一个 exe」（按 `$_.Path` 过滤）—— 原先的
   `taskkill /IM adb_Tool.exe` 会把用户开着的交付版一起关掉。

顺带补了两处可诊断性：
`verify_all.run()` 失败时把子进程完整输出落 `_fail_<套件>.log`；`release.py` 失败时落
`_release_verify.log` —— 之前只打最后三行，具体哪条红要靠运气复现。

## 4. 门禁结果（全绿）

- `verify_all.py`：**22 项 0 失败**（新增 `_check_a14.py` 50/50）
- `377/_test_ui_behavior.py`：**198/198**（P6 分组顺序顺延一位）
- `_gate_invariants.py`：**44 项 0 失败**（新增 `A14_ADDS` 登记 `setSize` / `set-fsize`）
- `_check_features.js`：**49 项**（新增 `ui.wsvc` / `ui.a14`；`apple.icons` 锚点随图标换版更新）
- `_check_apple_release.py`：U1–U6 **0 失败**（补 8 个 A14 标记）
- CLI 489 条 / GUI 42 条断言，0 失败

## 5. 「看似能做、实际做不到」的判断

1. **原生 `<select>` 弹层用 CSS 改配色**：不行。它是浏览器进程画的，不在页面 DOM 里。
   只能自绘（已做），或换成 `div` 自己实现（会丢掉原生键盘/无障碍行为，代价更大）。
2. **字体大小逐条改 px**：必漏。字号散在卡片、页签、输出区、弹窗十几处，
   改完还有行高错位。整页缩放是唯一不漏的做法。
3. **`cmds.ini` 里表达「重启后等待并继续」**：不行，一条 `run` 只能一行命令。

## 6. 已知取舍

- 字号缩放到 1.15 时，极窄窗口下卡片文字会有更多折行（整页缩放的必然结果，不是 bug）。
- 自绘下拉放弃了原生弹层的「输入首字母跳转」，换来一致的配色；键盘 ↑↓/Enter/Esc 保留。
- 支付宝日志仍要求 root（`/data/data` 权限），失败时给的是明确提示而非静默。
