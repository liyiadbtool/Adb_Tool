# AGENTS.md — Adb_Tool 项目规则（给 AI / 给人看同一份）

> 这份文件是**硬约束**，不是建议。每次开工先读它，改完代码必须跑最后那一条命令。
> 状态与交接记录在 `STATE.md`，不要往这份文件里写"今天做了什么"。

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
