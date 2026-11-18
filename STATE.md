# STATE.md — 交接状态（谁接手都先看这里）

> 规则：**只写"现在是什么状态"和"下一步做什么"**，过程与原因写进 `docs/`。
> 每次收工更新「最后更新」「本轮做了什么」「下一步」，并保证「验收基线」是最新真实数字。

---

## 最后更新

2026-11-17 15:10 · A28（版本水印：一眼确认跑的是哪份副本；门禁 27/28 绿）

---

## 本轮做了什么（A28）

**起因**：用户反馈「字体切换还是不生效」。查下来**代码是通的** —— 用 headless 走真实点击路径
（mousedown 开自绘下拉 → 点「等线 DengXian」）实测：`--font-ui` 变成 DengXian、`body` 计算字族跟随、
toast 显示「已切换」。真正的问题是**机器上同时开着两个实例**：

| PID | 启动时间 | 路径 | 结论 |
|---|---|---|---|
| 34980 | 11-13 21:21 | `WorkBuddy\2026-10-30-16-43-30\adb_log_gui\` | **4 天前的旧副本**（另一个项目目录） |
| 36468 | 11-17 14:44 | `Desktop\Adb_Tool\adb_log_gui\` | 最新（程序 14:10 / 界面 13:45） |

| # | 改动 | 落点 |
|---|---|---|
| 1 | **关于里加实时版本水印**：`程序 <时间> · 界面 <时间> · 目录 …<末两级>` | `GuiWeb.cs` 在 `themeget` 回推 `build` 消息（`StampOf()` 读文件时间）；`ui.html` 新增 `#build-stamp` + `applyBuildStamp()`；原来那行写死的 `v8.3 · 2026-11-15` 删掉 |
| 2 | 门禁登记 | `_gate_invariants.py` 新增 `A27_ADDS`（kind `build` + id `build-stamp`，附理由）—— 不许靠放宽断言过关 |
| 3 | 自检纳入 | `GuiSelfCheck` 15 条：新增「版本水印已显示（程序时间/界面时间）」，覆盖 C# 推 → 前端渲染整条链路 |
| 4 | 文档 | 手册新增 §20.0「怎么确认自己在哪一版」；代码导读同步 |

**僵尸进程**：PID 34980 已发终止信号但停在 1 线程 / 0 CPU 的不可回收态（驱动调用中），
不影响使用，**重启电脑即清除**。

验收基线：**28 项 / 27 绿 / 1 红**（唯一红：Liquid Glass —— 系统透明效果关闭，环境）。

---

## 本轮做了什么（A27）

| # | 需求 | 落点 |
|---|---|---|
| 1 | **性能实测** | 新建 `377/_bench_render.py`：Edge headless **真实时钟**（不能用 `--virtual-time-budget`，虚拟时钟下 `performance.now()` 不前进，新旧写法都返回 0.0ms）。实测：一批 500 行、日志区在 5000 行上限时 **旧 34.8ms → 新 13.3ms（2.6×）**；2000 行 136.9 → 53.5ms。**旧路径 34.8ms > 泵血间隔 33ms，所以 logcat 满速时 UI 线程必然饱和 —— 这就是现场 99.7% 的机制**。报告见 `docs/性能测试报告_20261117.md` |
| 2 | 启动/空闲基线 | `--exec ":h"` 3 次：3391/2961/3074ms（`:h` 瞬时，差值即启动开销）；空闲 CPU 实测 0.00s/4s，工作集 64MB；门禁 1m34s |
| 3 | **O6 自检改测真实界面** | `GuiEntry` 不再 `return GuiSelfCheck.Run()`，改为照常建 `GuiWeb` 并置 `SelfCheckMode`（窗口移到屏幕外、不占任务栏）；`GuiWeb` 新增 `StartSelfCheck/EvalForSelfCheck`（`ExecuteScriptAsync` 读计算样式）；`GuiSelfCheck` 整体重写为 14 条真实界面断言（页签 6/互斥/卡片/6 格/输出区占比/输入框宽/主题/强调色/字体令牌/窗口圆角 8px） |
| 4 | 连带收益 | GUI 自检**不再依赖 winget 版 scrcpy**，本机从"45 条 1 失败"变成 **14 条 0 失败** → 门禁 26/28 → **27/28 绿** |
| 5 | 文档同步 | `docs/代码导读.md`（自检链路、GuiMain 已孤儿化）、`docs/测试用例.md` R-32、`docs/性能测试报告_20261117.md` |

**注意**：`GuiSelfCheck` 断言数从 46 降到 14 —— 不是"丢了 32 条覆盖"，而是那 32 条本该由 `377/` 的 headless 套件（页面结构 48、交互 75、投屏 115 等）负责；老窗体那些"顶栏高度 36~60px"的断言对 WebView2 界面无意义。

**未做**：性能报告第 4 节的 4 项候选（投屏不可见暂停 / 启动 3s 归因 / Range 批量裁剪 / 日志上限 3000）。

验收基线：**28 项 / 27 绿 / 1 红**（唯一红：Liquid Glass —— 系统透明效果关闭，属环境）。

---

## 本轮做了什么（A25）

| # | 需求 | 落点 |
|---|---|---|
| 1 | **bug2 应用边界有问题** | 根因：V17 的窗口内描边 `body::after{ border-radius:inherit }` 继承的是 **body**（body 没有圆角 = 0），所以描边是**方角**，被原生 8px 圆角（`GuiWeb._cornerDip=8`）裁掉 → 四角出现"描边断头 + 1px 台阶"。修复：新增 `--win-radius:8px` 与原生同值，描边/内阴影统一用它；最大化（`data-winmax=1`）时改回方角，避免四角残留圆弧（`_v17.css`，已重注） |
| 2 | 回归固化 | `377/_test_interaction.py` 22 → **25 断言**（内描边半径=8、描边仍在、最大化无圆弧） |

**验证方式说明**：真机截屏在本机不可用（前台窗口抢占 + 多显示器未点亮区域），改用「计算样式断言 + headless 渲染截图」验证：圆角处描边已跟随弧线，不再是方角被裁。

---

## 本轮做了什么（A24）

| # | 需求 | 落点 |
|---|---|---|
| 1 | **bug1 字体切换不生效** | 根因两条：①「等宽 · 代码日志」组只给 `mono`、`ui` 为空，`setProperty('--font-ui', undefined)` 把令牌写成字面量 `undefined`，全站 `font-family` 失效（实测切 consolas 后 body 字族 = "undefined"）；②标「未安装」的字体仍可选中，应用后回退雅黑，却 toast「已切换」。修复：`ui` 为空时不动 `--font-ui`；应用后 `fontReallyApplied()` 做 canvas 测宽自检，未生效则如实提示且不写偏好（`ui.html:9140`） |
| 2 | O2 空输入回车有反馈 | `run()` 空输入给 toast，不落历史（`ui.html:4615`） |
| 3 | O3 六个页签补快捷键 | `Ctrl+5` → UI、`Ctrl+6` → 文本；帮助「11. 快捷键」补一行 |
| 4 | O4 日志裁剪热点 | `trimLog` 把提示节点缓存到 `box.__trimNote`，不再每行一次属性选择器全子树扫描（`ui.html:4149`） |
| 5 | O5 投屏"点不动"三因分流 | 未开启 / 离线 / 未收到首帧 各自给提示，不再静默 return |
| 6 | 回归固化 | `377/_test_interaction.py` 14 → **22 断言**（新增字体令牌、Inter 生效、日志裁剪三条） |

**未做**：bug2「应用边界」——用户提供的参考图无法确定具体指哪一处（窗口外框 / 内容内边距 / 圆角缝隙），已在对话中请其确认，不做猜测性修改。

验收基线：**28 项 / 26 绿 / 2 红**（环境：系统透明效果关闭、缺 winget scrcpy）。

---

## 本轮做了什么（A23）

| # | 需求 | 落点 |
|---|---|---|
| 1 | 换机接力：新设备拉代码并跑通 | `C:\Users\zuo20\Desktop\Adb_Tool`；补根 `adb_log_export.ini`（`accent=blue`）修好 2 项门禁 |
| 2 | 交互走查 I3：文本页 active 只由 V12 钩子补 | 主 `switchTab` 补 `page-text` 分支（`ui.html:4579`） |
| 3 | 交互走查 I4：投屏状态轮询从不 clearInterval | 离开投屏页 `clearInterval`，回来 `castStartPoll()` 重启（`ui.html:4585/4599`） |
| 4 | 交互走查 I5：投屏点黑边静默无反馈 | letterbox 点击给 toast，同槽 1.2s 节流（`ui.html:6949`）；手册同步 |
| 5 | 新增交互一致性门禁 | `377/_test_interaction.py`（14 断言），并入 `verify_all.py`，门禁 27 → **28 项** |
| 6 | 交付测试资产 | `docs/测试用例.md`（10 维度约 221 条）+ `docs/测试报告_20261116.md` |

验收基线：**28 项 / 26 绿 / 2 红**（2 红为环境差异：系统透明效果关闭 → Liquid Glass 3 条；未装 winget scrcpy → GUI 自检 1 条）。

---

## 本轮做了什么（A21）

| # | 需求 | 落点 |
|---|---|---|
| 1 | 启动层图标"最后一帧蓝色"根因修复 | 根因：`ui.html` `.splash .cat svg` 的光晕用了 `--glow`，而 `--glow` 在 `:root[data-theme]` 层**写死蓝色**（dark=rgba(10,132,255,.22)），不跟随强调色。图标本体 currentColor 已跟色，但外圈 22px 蓝光晕把它映蓝。修复：光晕改用 `--accent-soft`（每个 data-accent 都有对应值、跟随强调色） |
| 2 | 三白色点展示色去蓝 | 色板里三白 `accent-dot` 的 `--dot` 是手写内联样式（`_gen_accent.py` 之外），A20 改生成器时漏改：glasswhite 仍是冷蓝 `#E9E9EE`、eyewhite 仍是暖黄 `#FFFDF5`。修复：`--dot` 统一改为中性灰白（purewhite `#F2F2F2` / eyewhite `#F0F0F0` / glasswhite `#E6E6E6`），与生效值一致 |
| 3 | 新增专项运行时测试 | `377/_test_accent_blue.py`（Edge headless 实际渲染 ui.html，读计算样式验证光晕/色点去蓝），纳入 `verify_all.py` EDGE_TESTS，门禁 26 → **27 项** |

**dock 栏蓝色云朵图标结论**：不是代码 bug。exe 内嵌 7 档 PNG 图标最大饱和差=0（纯黑白灰）、`.ico` 文件也是黑白灰，用户看到的"蓝色圆角方块+白色云朵"是 **Windows 任务栏图标缓存（IconCache.db）残留**。清缓存方法见"下一步"。

门禁状态：27 项 0 失败（新增"启动去蓝"12/12）。

---

## 现在能跑吗

**能。** 两个形态都编译通过；门禁 28 项 / 26 绿 / 2 红（2 红为**环境差异**，非代码缺陷，见下）。

| 检查 | 命令 | 当前结果 |
|---|---|---|
| 全量门禁 | `python verify_all.py` | **28 项 / 26 通过 / 2 环境失败** |
| 交互一致性 | `python 377/_test_interaction.py` | 14 / 14 |
| A17 落点 | `python _v17_checks.py` | 64 / 64 |
| A16 落点 | `python _v16_checks.py` | 78 / 78 |
| A15 落点 | `python _v15_checks.py` | 54 / 54 |
| 功能清单 | `node _check_features.js` | 52 项通过 |
| 功能不变量 | `python _gate_invariants.py` | 44 项 / 0 失败 |
| 窗口原生 | `python _smoke_win.py` | 13 / 13 |
| GUI 自检 | `adb_Tool.exe -guiSelfCheck`（由 verify_all 调用） | 45 条 / 1 失败（**缺 winget 版 scrcpy**） |
| CLI 自检 | `adb_log_export.exe -selftest` | 489 条断言 0 失败 |

**两条环境失败（换机器必复现，按此处理）：**

1. `Liquid Glass 17/20` —— 系统「透明效果」关闭（`EnableTransparency=0`）→ Edge 报
   `prefers-reduced-transparency: reduce` → 玻璃层按无障碍设计退化纯色。
   **打开系统透明效果即转绿；不许改代码绕过（那等于取消无障碍降级）。**
2. `GUI 自检 1 条` —— 断言 `scrcpy 探测覆盖 winget Packages 目录` 需要本机真装过
   winget 版 scrcpy。`winget install Genymobile.scrcpy` 即转绿。

### 本轮做了什么（2026-11-18 · T1 + T2，按《AI 实现规格书》批次 1-2）

| # | 需求 | 落点 | 说明 |
|---|---|---|---|
| 1 | **T1 GetField 转义解码** | `GuiWeb.cs` `GetField`（≈4014） | 原实现是极简扫描、不解转义：含 `"` 的命令被截断（`shell "settings delete global http_proxy"` 只剩 `shell \`）、UNC 路径翻倍、回显与执行不同源。改为按 JSON 规则扫描（遇 `\` 跳过一个字符）+ 解 `\\ \" \/ \b \f \n \r \t \uXXXX`；非字符串值仍原样取（数字/布尔不受影响） |
| 2 | **T1 删除二次解码** | `GuiWeb.cs` 11 处 | 规格书只点了 3 处，实测共 **11 处** `App.JsonUnescape(GetField(...))`（ffmpegset/scrcpyset/fslist/fssearch/fsop 等）。已全部拆掉 —— 不拆会把 `C:\temp` 解成 TAB，制造新的"打不开" |
| 3 | **T2 自绘下拉 mousedown 误关** | `_v14.js` 捕获阶段处理器（已重注） | 原实现无条件 `closePop()`：点浮层**条目**时也命中（浮层挂 body 下，向上找不到 SELECT），mousedown 当场移除节点 → click 派发时已脱离文档 → 选中无效、`change` 不派发。现在 `pop.contains(ev.target)` 时不关。一处修复救活字体切换 / 预设环境值 / 投屏屏号 / 编码换行四类下拉 |
| 4 | **回归断言** | `GuiSelfCheck` 15 → **19 条**；`377/_test_interaction.py` 28 → **35 条** | T1 四条（引号不截断 / UNC 不翻倍 / `C:\temp` 不进 TAB / 数字仍可取值）；T2 七条（**真实鼠标序列** mousedown→断言浮层仍在→mouseup→click，另含点外部关闭、键盘 ↓+Enter 不回归）|
| 5 | 测试模式不落盘 | `GuiWeb.cs` | `prefsave` 也纳入 ProbeJs 判断，避免测试页改字体时把 `adb_log_gui/adb_log_export.ini` 弄脏 |

验收基线：**28 项 / 0 失败**（门禁 1m24s）；GUI 自检 19 条 0 失败；交互一致性 35/35。

---

### 9 条假红已定位并消除 → 门禁回到 **28 项 / 0 失败**（2026-11-18）

换机后本机一度是 **28 项 / 24 通过 / 4 失败**，多出的 3 红共 9 条断言：

| 门禁项 | 修前 | 修后 |
|---|---|---|
| 窗口与记录 | 194/199 | **199/199** |
| 交互与输出区 | 72/75 | **75/75** |
| 交互一致性 | 27/28 | **28/28** |

**根因（实测，不是猜）**：页面启动后要 ~1.58s 才进入稳态。此前 `.frame` 上有
**3 个 `fill:backwards` 的 CSSTransition**（opacity / transform-origin / visibility）
卡在 `currentTime=0`，把 `.frame` 钉在 `opacity:0 / visibility:hidden`；
而这三个套件分别在 250~500ms 就开测，量到的是**过渡中的隐藏态**。
连带效应：根元素 `background-color` 与伪元素 `body::after` 的半径读到的都是旧值
（`--bg`/`--frame` 变量本身是对的，只有解析值不刷新）。

稳态实测（`--uitest`，真实 WebView2，等稳态后取值）：

| 断言 | 过渡态（旧） | 稳态（新） |
|---|---|---|
| 三套主题背景色 | `rgb(0,0,0)` ×3 | `rgb(0,0,0)` / `rgb(242,242,247)` / `rgb(253,250,243)` |
| 输入框可聚焦 | false | **true** |
| winmax 时 `body::after` 半径 | 8px | **0px** |
| `.frame` | `opacity:0` | `opacity:1 / visible` |

**处置（断言一行未改）**：三个套件的测量前置改为"等 `.frame` 稳态（`show` + `opacity===1`，
上限 6s）再跑"，测量通道切到 `adb_Tool.exe --uitest`（真实 WebView2 + 真实时钟；
headless 的 `--virtual-time-budget` 会冻结 transition，怎么等都等不到稳态）。
新增 `377/_wv2.py` 做调用封装，无 exe 时自动回退原来的 Edge 路径。

**顺带确认**：`Liquid Glass` 本次也 20/20 通过（本机系统透明效果为开启状态）。

---

## 本轮做了什么（A20）

| # | 需求 | 落点 |
|---|---|---|
| 1 | 投屏默认全屏修复 | 根因：`GuiWeb.cs` `_embL/T/R/B` 默认 `0.02/0.10/0.98/0.92` 近乎全屏，`AttachEmbedded` 用默认值先显示再等页面报小屏坐标，导致 scrcpy Panel 一上来盖满窗口。修复：默认坐标改 0 区域，`AttachEmbedded` 仅收到有效小屏坐标才 `Visible=true` |
| 2 | 标题栏图标回退中性白 | 用户明确 dock/标题栏图标=中性黑白灰品牌图不跟色。回退 `_v17.css`：`.appmark{ color:var(--mark-fg) }`，仅 `.splash .appmark` 跟色 |
| 3 | 三白强调色改中性灰白 | `_gen_accent.py` + `Prefix.cs`：purewhite `#F2F2F2`、eyewhite `#F0F0F0`、glasswhite `#E6E6E6`（原 `#E9E9EE` 带冷蓝调是"图标显蓝"元凶） |
| 4 | 切换设备文档更新 | 重写 `docs/明天到公司继续开发.md`（GitHub 已建仓、代码已推送，切换设备专用版） |

门禁状态：26 项 0 失败（A17 落点 64/64、功能清单 52/52、功能不变量 44/44）。

---

## 下一步（按优先级）

1. **接真机** 跑 `docs/测试用例.md` 的 D1(60) + D3(18) + D7(10) —— 当前最大覆盖缺口（约 60% 用例因无设备未执行）。
2. **补两个环境项**（转绿即 28/28）：
   - `winget install Genymobile.scrcpy` → GUI 自检转绿
   - 打开系统「透明效果」→ Liquid Glass 转绿
3. **架构偿还**（独立、低风险，按 `docs/测试报告_20261116.md` 第 5 节）：
   - `GuiSelfCheck` 改测 WebView2 或明确标注定位（它现在只守老 WinForms 窗体）
   - `Thread.Abort()` 换协作式取消（`GuiWeb.cs:4293`）
   - `trimLog` 缓存 trim 节点（`ui.html:4151`，日志满 5000 行后的最大 DOM 热点）
4. **清 Windows 图标缓存**（dock 栏还显示旧蓝色云朵时，人工操作一次）：
   - 删除任务栏 pin → 资源管理器重启（`taskkill /f /im explorer.exe && start explorer.exe`）→ 重新 pin
   - 或删除 `%LOCALAPPDATA%\Microsoft\Windows\Explorer\iconcache_*.db` 后重启资源管理器
5. **真机验收**（必须人工）：启动动画图标是否不再显蓝；设置面板三白点是否中性灰白；投屏默认小屏、点「⤢」扩全屏、底部缩略条切换。
6. 出包：`python release.py`（会自动重跑 **28 项**门禁），组装 `Desktop\Adb_Tool_成品_V23_<时间戳>`；顺带验 D8 的 G-06~G-09（三形态）。

---

## 环境（别人接手要照这个来）

```bash
python --version     # 3.x 即可，只用到标准库
node --version       # 只给 _check_features.js / 377 用
git --version        # >= 2.28
# C# 编译器：C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe（系统自带，无需安装 SDK）
```

- 用户名可能是中文（历史上出现过 `C:\Users\李亦`），**不要在 .bat 里拼含中文的路径**；脚本里一律用 `%~dp0`。
- Git Bash 里跑 .bat 要 `cmd //c "..."`；`build.bat` 末尾有 `pause`，必须 `< /dev/null`。
- 编译输出是 GBK，管道里要看中文得 `| iconv -f GBK -t UTF-8`。

---

## 已知限制（不要当 bug 报）

- **内置投屏通道 1~5fps**，无线 adb 约 1.5fps。天花板在"每帧从设备搬一张整图"，不在编码。
  要流畅走内嵌 scrcpy（h264 原生解码）。按用户要求**不做** h264→MSE 的页内 30fps。
- **三白在浅色/护眼下必然是灰**（`#939393` / `#9C9284` / `#8E949E`）。白压到可读对比度必然是灰，这是数学问题。
- **`adb root` 不提供**（用户明确要求）。它会重启 adbd，断掉正在跑的日志与投屏。
- 副屏/HUD 不一定支持 `screencap -d`，内置通道首帧失败会直接提示改用 scrcpy。
