# adb_Tool 交接说明

> ⚠️ **换机器 / 换 AI 请看 `AI_HANDOFF/README.md`**（含环境自检脚本、冷启动提示词、项目地图、排障表）。
> 本文是早期的手写交接笔记，保留作历史参考，部分内容（卡片数量、功能进度）已过时。

> 用途：新开会话时快速续上。开头说一句「继续 adb_Tool 项目」即可，我会先读 `.workbuddy/memory/` 恢复上下文。

## 一、项目是什么

车机 adb 命令行/日志导出工具的 GUI 版（孙小伟，QA 测试工程师，测汽车语音/功能）。
- 命令行版：`adb_log_export.exe`（项目根目录，能力最全，280 项自检）
- **GUI 版：`adb_log_gui/adb_Tool.exe`（当前重点，WebView2 内嵌 HTML）**

## 二、关键文件

| 文件 | 作用 |
|---|---|
| `adb_log_gui/adb_Tool.exe` | 交付产物 |
| `adb_log_gui/webview2/ui.html` | 前端界面（深色主题、快捷指令页都在这里） |
| `adb_log_gui/build_gui.bat` | GUI 编译脚本（csc，C# 5.0，x64） |
| `_cs/*.cs` | C# 源码（GuiWeb.cs 是窗口外壳，PkgVer.cs 是包/前台查询，Prefix.cs 是 `:` 内置命令） |
| `cmds.ini` | 自定义命令（`$(desktop)` 占位符、hci/shot/rec 等） |
| `.workbuddy/memory/` | 项目记忆（每天的坑和决策，续会话先读这里） |

## 三、当前进度

界面（WebView2 深色主题 + 黑猫图标/加载动画）、快捷指令页（侧边导航，6 分组）都已完成。

**「指令执行」分组现有 7 个卡片**（cmd → 命令）：
- HCI导出 → `hci`（导出 btsnoop 到 `桌面\logcat\日期\HCI`）
- 一键截图 → `shot`（once 交互，存到 `桌面\logcat\日期\screencap`）
- 一键录屏 → `rec`（toggle 交互，点击停止后自动 pull 到 `桌面\logcat\日期\screenrecord`）
- 分辨率查询 → `:res`
- 清理前台应用 → `:fstop`
- 查询前台包名 → `:front`（包名+Activity+路径）
- 升级前置指令 → `:preup`（root→enable-verity→reboot，报错跳过）

**后端内置命令**（Prefix.cs / PkgVer.cs）：`:res` `:fstop` `:front` `:preup` `:pkg now/ver` 等，都已编译验证通过，实机测试正常。

**导出路径（2026-11-10 更晚定稿）**：统一走 `$(out:xxx)` 占位符，落到
`桌面\logcat\<yyyy-MM-dd>\{screencap|screenrecord|HCI}` 两级结构，不再平铺。
详见「四之三」。


## 四、最新进展（2026-11-10）

**按钮交互已落地：方案3 图标态（主）+ 方案4 进度条（长任务叠加）。**

- 图标态：卡片左侧图标随状态切换 —— 待机▶ / once执行中转圈 / toggle执行中■停止 / 完成✓ / 失败✗（颜色：灰/青绿/绿/红）
- 进度条：长任务卡片（HCI导出、一键录屏）底部 2px 青绿条，执行扫动、完成满格
- 完成态停留 1.5s、失败态停留 2s 后自动复位
- 两个生命周期：**周期1 一次性**（截图/查询/导出，转圈不可中断，自动复位）、**周期2 开关**（录屏，■停止块可再点结束）
- 只改 `ui.html`（外部文件，exe 带 `?v=时间戳` 防缓存，改完直接生效、无需重编译）

**反馈窗口重构（4 项需求）：**

1. 去掉「执行反馈」标题行和表头，反馈窗口高度 25%→40%
2. 反馈窗口顶部加 `fb-resizer` 拖拽条，鼠标上下拖调整高度（120px~85%）
3. 反馈窗口新增**输出区** `fb-out`（查询类命令 stdout 显示在此），与结果列表上下各半
4. 快捷指令页命令（source=1）的 line/echo **不再进指令输入页 logbox**，路由到反馈窗口输出区：
   - 后端 `GuiWeb.cs` 的 `PushLine`/`PushEcho` 消息加 `src` 字段（`_cmdSource`）
   - 前端 `appendLine`/`appendEcho` 按 `src` 路由（src=1 → `fb-out`，src=0 → logbox）
   - `runQuick` 执行前清空输出区

**关键 bug 修复**：转圈图标 `@keyframes spin` 缺 `transform-origin`，svg 绕左上角旋转飞出
导致「按钮消失」。已加 `transform-origin:center; transform-box:fill-box;`。

## 四之二、九项界面/功能问题修复（2026-11-10 晚）

用户给两张截图列了 9 条问题，逐条落地。**先说最重要的一条**：

### 【最严重】`.running` 类名冲突 —— 这是"按钮点击后消失"的真凶

顶栏进度条原来写成裸选择器：

```css
.running{display:none;}      /* 本意：给顶部 2px 流动线用的 */
.running.on{display:block;}
```

而快捷指令卡片执行中加的是 `class="qcard running"`。两条规则撞名后，
**卡片一点击就 `display:none` 整体消失**，要等 `endRun` 移除类才回来 ——
这就是用户说的"一点击就消失"。

不光是 pointer-events 的问题（上一轮以为是那个，改完还是消失）。
真正的验证方式：在 headless 浏览器里点一下读 `getComputedStyle(card).display`，
返回 `none` 才暴露出来。**光看源码看不出来，必须跑起来量。**

修法：进度条改专属类名 `.runbar` / `#runbar`，与 `.qcard.running` 彻底分开。
`_check_ui.js` 里加了断言禁止裸 `.running` 规则复发。

### 逐条对照

| # | 问题 | 做法 |
|---|---|---|
| 1 | 设备未在线却显示执行成功 | `Dispatch` 入口统一 `CMD_OK=false`，成功路径才置 true；纯本地命令（`:h` `:cmds` `pwd` 等）显式调 `OkLocal()` |
| 2 | 加载过渡动画闪烁 | `.frame` 去掉自己的 opacity 过渡（框架在 splash 底下瞬间就位）；splash 单层淡出 `.45s→.28s`，`transitionend` 后加 `.gone` 彻底 `display:none` |
| 3 | 顶栏加 root 指示按钮 | 新增 `Root.cs`（`RootProbe`/`RootElevate`/`WaitBack`）；顶栏红/绿胶囊，**点击直接 `adb root` 不弹确认**；`rootdone` 回执解除转圈，10s 兜底解锁 |
| 4 | 恢复「时间/指令/结果/耗时」+ 左右分栏 | `fb-row` 重构为 `左(时间+指令+耗时) │ 竖线 │ 右(输出)`；`--fb-left` 变量 + 竖线拖动调占比（18%~82%）；两侧 `white-space:pre-wrap` 双换行；每条命令独立 `.fb-row` 天然不覆盖；输出区 `max-height:132px` 内部滚动 |
| 5 | 指令执行按钮太大 | `.quick-grid` 两列 → **一行三个**（`repeat(3,minmax(0,1fr))`），窗口 <900px 自动退回两列 |
| 6 | 语音助手位置 | `quickGroups` 里从最后一位移到**第 2 位**（紧接"指令执行"） |
| 7 | 连接后显示分辨率 | `LoadDeviceInfo` 合并同一次 shell 往返取 `wm size`（`tr '\n' ';'` 压平才不丢 Override 行）；`ParseWmSize` 纯函数 + 12 项自检；`PushStatus` 加 `res` 字段，顶栏设备号后显示 |
| 8 | 按钮点击后不消失 | 修 `.running` 冲突（见上）+ 结果态停留 1.5s/2s → **2.6s/3.2s** |
| 9 | （空） | — |

### 输出归属：为什么改成"每条命令一个记录块"

原来所有输出都 `appendChild` 到同一个 `#fb-out`，连续执行两条命令时后一条的
输出会盖住前一条的观感。现在 `runQuick` 先建一条带"执行中"占位的 `.fb-row`，
把它的右栏节点记在 `_curOutEl`；`appendOut` 逐行追加进去；`endRun` 用
`finalizeRow` 只改左栏徽章/耗时，**右栏一个字都不动**。

## 四之三、列对齐与字符限制 + 导出路径重构（2026-11-10 更晚）

### 需求1：时间/状态/耗时/指令要与输出排列对齐，并限制字符

**用户原话**：
> 时间、耗时、指令要和输出的内容排列对齐，并对字符做出一个合理的限制

**对齐错位的真根因**（不是调间距能解决的）：

表头原来把「时间 指令 耗时」三个标签**横排一行**，而一条记录左栏是**上下两行**
（时间+徽章+耗时 一行、指令 一行）。标签横排、内容竖排 —— **结构都不对应**，
无论怎么调 padding/margin 都对不上。

修法：表头复制记录的同一套结构。

```
表头左栏                      记录左栏
┌──────────────────────┐     ┌──────────────────────┐
│ 时间   状态   耗时    │     │ 19:54:06 成功  3241 ms│
│ 指令                 │     │ pull /log/...        │
└──────────────────────┘     └──────────────────────┘
```

**三个字段全部定宽**（这才是"严格成列"的关键，光靠 flex 自动分配会随内容宽度抖动）：

| 字段 | 表头选择器 | 记录选择器 | 宽度 | 对齐 |
|---|---|---|---|---|
| 时间 | `.h-meta .h-t` | `.fb-meta .t` | 58px | 左 |
| 状态 | `.h-meta .h-b` | `.fb-meta .badge` | 38px | 居中 |
| 耗时 | `.h-meta .h-d` | `.fb-meta .d` | 62px | **右** |

耗时必须右对齐：`12 ms` 和 `3241 ms` 位数不同，左对齐或居中会让数字右边缘参差。

**字符限制**（不再糊满屏幕）：

| 区域 | 限制 | 兜底手段 |
|---|---|---|
| 指令 | `-webkit-line-clamp:2`，最多 2 行 | `title` 悬停看全文 + 双击复制完整内容 |
| 输出 | `max-height:132px`（约 6 行）内部滚动 | 右栏独立滚动条 |

**两个隐形坑**：

1. **`.fb-split` 根本没有 CSS 规则** —— JS 里 `sp.className='fb-split'` 创建了元素，
   但样式表里没有对应规则，宽度是 0，鼠标压根抓不到，"可拖动调占比"实际失效。
   补上 `flex:0 0 13px;margin:0 3px;cursor:col-resize`，宽度必须与表头 `.h-sp` 一致。

2. **border-left 让百分比基数不同，差 0.9~1.1px** —— `.fb-row` 有
   `border-left:2px`（成功/失败色条），记录内容盒比表头窄 2px；两边 `flex-basis:46%`
   算出来的基准不同，右栏起点就差 1px 左右。修法：把那 2px 透明边框移到 `.fb-head` 上，
   两边内容盒完全一致。

**验证方式**（这类问题必须量像素，看源码看不出来）：

```bash
python 377/_measure_text_align.py   # 字形级，4 种窗口宽度 × 11 项断言
```

用 `Range.selectNodeContents + getBoundingClientRect()` 取**文字字形盒**
（不是元素盒），在 900/1180/1440/1920 四种宽度下断言每个字段的对齐边偏差 ≤ 1.5px。
实测四个宽度**偏差全部 0.00px**，`8 ms` 与 `3241 ms` 字形右边界也完全重合。

### 需求2：导出路径改成「桌面\logcat\<日期>\<分类>」

**用户原话**：
> 导出的文件存储路径需要修改下导出在桌面创建 logcat 文件再生成一个日期文件比如当前是 2026-11-10 再创建各个分类的文件比如截图 screencap、录屏 screenrecord、HCI 导出文件 HCI

目标结构：

```
桌面\logcat\
  ├─ 2026-11-10\
  │    ├─ screencap\     截图（:shot）
  │    ├─ screenrecord\  录屏（:rec 停止后自动 pull）
  │    └─ HCI\           HCI 蓝牙日志（:hci）
  └─ 2026-11-11\  ...
```

**实现**：统一入口 `$(out:xxx)` 占位符，三处调用点共用同一套规则（不要各写一份）。

| 占位符 | 展开结果 |
|---|---|
| `$(out)` | `桌面\logcat\2026-11-10` |
| `$(out:shot)` | `桌面\logcat\2026-11-10\screencap` |
| `$(out:rec)` | `桌面\logcat\2026-11-10\screenrecord` |
| `$(out:hci)` | `桌面\logcat\2026-11-10\HCI` |

关键点：

- **求值时即建目录**。重定向 `> path` 到不存在的目录会直接失败，所以 `OutDir()`
  里先 `Directory.CreateDirectory`（对已存在目录幂等）。
- 分类名做了归一化：`shot/screencap/screenshot/截图` 都映射到 `screencap`；
  `rec/screenrecord/video/录屏` → `screenrecord`；`hci/btsnoop/bluetooth/蓝牙` → `HCI`。
- `fn.StartsWith("out")` 改成精确匹配 `fn == "out"` 或 `fn.StartsWith("out:")`，
  否则以后加个 `$(output)` 之类的函数会被这里先截走。
- GUI 启动时 `EnsureLogcatDir()` 预建四层目录，用户点导出必然有落点。

**实测验证**（真机 b09acfa2）：

```
:shot  → adb exec-out screencap -p > "C:\Users\zuo20\Desktop\logcat\2026-11-10\screencap\shot_200544.png"
         文件 920KB 已落盘
:hci   → pull /log/android_log/btsnoop "C:\Users\zuo20\Desktop\logcat\2026-11-10\HCI"
         √ 4 files pulled，落在 2026-11-10\HCI\btsnoop\
```

## 四之四、截图静默 + 录屏误报 + 车机信息九项（2026-11-10 深夜）

用户一次提了 4 条，前 3 条是修 bug，第 4 条是新增能力。

### 需求1 — 截图时不要弹黑框

**根因**：`AdbCmd.cs` 的 `RunLocalShell` 里 `CreateNoWindow = false`。
GUI 是 WinExe（本身没控制台），`UseShellExecute=false` + `CreateNoWindow=false`
时 Windows 会给**每个子进程新建一个可见控制台窗口**。
截图命令 `adb exec-out screencap -p > "path"` 带本地重定向 `>`，必须走 cmd.exe，
于是每次截图都闪一个黑框。纯 adb 调用走 `BuildPsi`（本来就 `true`），所以只有截图/录屏会出现。

**修复**：`CreateNoWindow = true`。

**验证特别值得一提**（详见坑 27）：前两版测试都是"假绿"，第三版才有效。

### 需求2 — 结束录屏报失败

**根因**：点停止 → `StopWorker()` → `RUNNING.Kill()` → adb 子进程退出码 **1**
→ `Dispatch` 只看退出码 → `CMD_OK=false` → 界面"失败"。
但录像其实已经完整写进设备文件（真机实测 811KB/841KB），用户点"停止"就杀进程是**预期行为**。

**修复**：
- 加 `volatile bool _stopRequested`：`SubmitCmd` 开头清 `false`，`StopWorker` 置 `true`；
- worker 里 `if (isRec && _stopRequested) ok = true;`（**只**对用户主动停止翻转，
  screenrecord 自己崩了仍然如实报错）；
- pull 之后补 `if (!App.CMD_OK) ok = false;`，录像没落盘不能算成功。

### 需求3 — r 刷新要输出九项 + 执行命令

刷新链路上 `RenderCarInfoOnRefresh()` 会先打两条取值命令（`$ adb shell getprop ...`
和 `$ adb shell wm size`），再打九项。挂载点：`RetrySoft()` / `RetryHard()` 各自
`Ok(...)` 之后。

**但有个隐蔽分支**：用户不是点卡片，而是**在「快捷指令」页用键盘敲 r**。
这条路径原来走 `source=0`，输出全进另一个页签的 logbox —— 用户看到的
就是"敲了 r 一点反应都没有"。修它的过程踩了三个坑（27~29），最终：
- 前端 `run()` 带上当前页签 `post('cmd', cmd, _tab==='quick' ? 1 : 0)`；
- 后端 `case "cmd"` 读 `src` 字段再传给 `SubmitCmd`；
- **反馈区必须先有占位记录**，否则 `appendOut` 找不到 `_curOutEl` 会静默丢弃整段输出。

### 需求4 — 车机信息九项（新文件 CarInfo.cs）

用户给了 8 条 `getprop` + 要求含分辨率，共 9 项。三个使用场景必须同一份口径，
所以收敛到 `_cs/CarInfo.cs`：

| 场景 | 入口 |
|---|---|
| 打开工具自动查 | `Adb.InitEnv` 末尾（`_carPrinted` 保证只打一次） |
| `r` 刷新重查 | `Adb.RenderCarInfoOnRefresh` |
| 「车机信息」按钮 | `:car` / `:car cmd` / `:car miss` |

**性能**：9 项如果一条一发就是 10 次 adb 往返（每次 80~150ms，累计 1s+）。
合并成**一次** shell：`echo '##0'; getprop ...; echo '##1'; ...`，
再用 `ParseMarkedTextN` 切回来，一次往返约 150ms。

**实测**（真机 b09acfa2，`:car`）：

```
车型          181
SOC 版本      GAC_T68_IDC_S1B3_261105_0745F_D
MCU 版本      T68_IC2015_01_21.773_261105_R
Android 版本  12
VIN 码        LMGNA1S86R1S00331
UUID          8545003ANB010000VD311000124091400N10001
DID           3885895
OPENID        6a29b54b
屏幕分辨率    2560x1440
```

「车机信息」卡片已加入「指令执行」组（该组现 8 条），
`cmds.ini` 另附 `[cmd.carinfo]` 供不重编译改口径。

### 这一轮又踩的坑（27~31）

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 27 | 测 `CreateNoWindow` 用管道跑 → 假绿 | 改回 false 也 PASS | 子进程自证 `GetConsoleWindow()`+`IsWindowVisible()` |
| 28 | `var _tab` 声明晚于 `switchTab` | 初始化赋值被 `='cmd'` 覆盖 | 声明移到函数之前（var 有提升、赋值没有） |
| 29 | 反馈区无占位行时 `appendOut` 直接 return | 快捷指令页敲 r，输出全丢 | 先 `addPendingRow()` 再发命令 |
| 30 | `UseDefault()` 里 `if(!COLOR) return` 在 HOOK 之前 | 车机信息九项整行变灰 | HOOK 提到 COLOR 判断之前 |
| 31 | 输出区 132px 装不下 10 行 | OPENID/分辨率被截掉，看起来"只出 7 项" | 限高改 200px + `scrollbar-width:thin` |

**坑 27 补充**：GUI 的 `--exec` 模式下 stdout 被重定向到管道，Windows 不会给
"输出已重定向"的子进程建控制台，所以那个路径根本无法测出黑框问题。

## 四之五、七条快捷指令 + 语音助手页 + 多指令互斥（2026-11-10 深夜 20:54）

用户一次提了 10 条，落到代码里是四类：

### ① 导出类快捷指令（需求1/3/4/7）

新增 `_cs/TaskCmds.cs`，四个命令共用 `OutDir()` + `Export()` 两份既有逻辑：

| 命令 | 动作 | 落点 |
|---|---|---|
| `:apk` | 查前台包名 → `pm path` → pull apk | `桌面\logcat\<今天>\APK` |
| `:pcm` | 探测 PCM 采集目录后整体拉取 | `桌面\logcat\<今天>\PCM` |
| `:dlog` | pull `/log/android_log` | `桌面\logcat\<今天>\`（不套分类） |
| `:carplay` | pull `/data/carplay/records` | `桌面\logcat\<今天>\carplay` |

目录由 `OutDir()` 即时创建，不存在就建。PCM 的底部文案
「工程模式→日志设置→audio→使能开关」是**前置操作提示**（不是命令），
在缺目录时作为 Hint 打出。

### ② 顺序执行类（需求5/6）

复用 `DoPreUpgrade` 的思路抽成通用 `RunSteps(title, steps)`：逐条 `AdbCall`，
失败**跳过继续**，最后汇总"失败 N 条"并逐条列出失败命令。

- `:hicar`（打开 HiCarSDK 日志，6 条）：root → remount → setprop vendor → setprop sys → sync → reboot
- `:carplayon`（打开 carplay 音频，2 条）：setprop record.audio.input/output

### ③ 静默截图（需求2，真正根因）

**根因（比上一轮的坑 27 更进一步）**：上一轮把 `RunLocalShell` 的
`CreateNoWindow` 改成 `true`，只消除了 **cmd.exe 这一层**的窗口；
但 `:shot` 的命令是 `adb exec-out screencap -p > file`，cmd 内部还要再拉起
**adb.exe（控制台程序）**——Windows 会为这个 console 子进程补一个可见控制台，
所以黑框还在。

**正解**：`:shot` 改成内置 `DoShotSilent()`，完全不经过 cmd.exe：
直接 `Process` 拉起 adb.exe，`RedirectStandardOutput` 拿 screencap 的 PNG 二进制，
C# 自己写文件。stdout 被重定向后子进程不需要控制台，自然不会弹窗。
落点仍是 `桌面\logcat\<今天>\screencap\shot_HHmmss.png`，并校验 PNG 签名。
`:shot -r` 保留老的重定向路径作逃生舱（走 cmds.ini 的 `[cmd.shot]`）。

### ④ 语音助手页（需求8）

新增第三个页签「语音助手」（`page-vr`）：
- 文本 textarea（Shift+Enter 换行）
- 六个音区按钮：主驾/副驾/二排左/二排右/三排左/三排右（对应 voiceArea 0~5，与 `Voice.cs` 的 `VR_AREAS` 一致）
- 「断网识别」勾选（`-l`）
- 发送 → `:vr sr <文本> -a <音区>`（断网则 `:vr local ...`），`src=2` 输出回显到页内结果区

### ⑤ 多指令互斥（需求9）

**根因**：后端 `SubmitCmd` 的 `if(_busy) return;` 是静默丢弃，前端 `runQuick`
却照常建占位行、标 running、发消息。连点两张卡片时，后点的卡片永远"执行中"、
`_quickRunningCard` 被覆盖、前一条结束的 end 误操作后一张 → 看起来"卡死"。

**修复**：前端加 `_busy` 全局互斥（`runQuick`/`run`/`sendVr` 三处都拦），
忙时 toast 提示直接返回；`endRun` 复位。后端 `_busy` 时回一个 `end{busy:true}`
兜底，前端只解除互斥、不碰正在执行的卡片。

### 这一轮踩的坑（32~34）

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 32 | `CreateNoWindow` 只挡 cmd 这一层 | 截图仍弹黑框（adb.exe 是 console 程序） | 绕开 cmd，直接 Process 捕二进制写文件 |
| 33 | 后端 `_busy` 静默丢弃 + 前端照常建行 | 连点卡片"卡死"停不下来 | 前端 `_busy` 互斥 + 后端 `end{busy}` 兜底 |
| 34 | 语音助手 CSS 硬编码 rgba 选中色 | 浅色主题下选中态色偏 | 抽 `--accent-soft` 主题变量 |

**环境备注**：本轮尾声系统进程创建整体变慢（连 `adb version` 都要 ~1.9s），
CLI 自检里的「adb 不存在 -> 1 秒内返回」这一项会因环境抖动失败，与代码无关。
headless Edge 测试也因 fork 资源耗尽偶发超时；功能专项测试（busy 15 项、vr 24 项、
src 26 项）已单独通过。
（2026-11-11 补：清理 msedge/msedgewebview2 僵尸进程后，进程创建恢复到 ~150ms，
CLI 自检 326/326 全绿。）

## 四之六、五项收尾修正（2026-11-11 上午）

用户复测后提了 5 条，都是上轮遗留的细节问题：

### ① 语音助手取消独立页签，迁入快捷指令分组

取消第三个「语音助手」页签，把文本输入 + 六音区 + 发送 + 上下键历史
整套交互迁到「快捷指令」tab 下的「语音助手」分组顶部（`vr-panel`）。
发送结果复用快捷指令页的反馈窗口（src=1），不再有独立 vr-log。

### ② 多屏下窗口强制居中主屏

`GuiWeb` 原来 `FormStartPosition.CenterScreen`，多显示器下会居中到"当前工作屏"
（可能是副屏）。取消拓展屏后窗口可能跑到屏幕外。
改成 `Manual` + `Load` 时按 `Screen.PrimaryScreen.WorkingArea` 居中，
永远落在主屏、避开任务栏。

### ③ APK 导出失败（路由撞名）

根因：`Prefix.cs` 里 `if (n == "pkg" || n == "apk")` 把 `apk` 当成了 `:pkg` 的别名，
后加的 `:apk` 导出分支永远执行不到（实测 `:apk` 回的是 `:pkg` 用法提示）。
修复：把 `apk` 从 `:pkg` 别名移除。实测导出成功（SYLauncher.apk 36MB 落盘）。

### ④ carplay 音频导出失败（目录不存在）

根因：`/data/carplay/records` 是 carplay 连接并开始音频录制后才创建的目录，
没连 iPhone / 没触发录制时目录不存在，`adb pull` 直接报 "No such file"。
修复：导出前先 `test -d` 探测，不存在则给出明确指导
（① 开 carplay 音频开关 → ② 连 carplay → ③ 触发通话/播放），不再甩晦涩报错。

### ⑤ APK 导出说明文案

「导出APK」卡片的 desc 改为「前台APK导出到桌面logcat文件」。

### 坑 35

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 35 | `:apk` 被 `:pkg` 别名拦截 | 导出 APK 回"pkg 用法"提示 | 别名与命令撞名，从别名里移除 apk |

## 四之七、目录与指令分组重构（2026-11-11 中午）

8 条需求，核心是"起始目录回退到 adb 原始位置"+"指令执行分组收敛"。

### ① 起始目录改为 adb 原始位置（需求1）

`ROOT` 默认值从 `/log/android_log/androidlog` 改成 `/`（ini 里 `root=` 同步改）。
`r`/`rr` 刷新不再跳日志目录，`logs` 命令仍跳 `/log/android_log/androidlog`
（走 `JUMP_LOG`，与 `ROOT` 解耦）。实测：pwd→`/`、r→`/`、logs→`/log/android_log/androidlog`。

### ② 一行三列（需求2）

三列 CSS 一直还在（`repeat(3,minmax(0,1fr))`），但降级阈值是 900px ——
默认窗口 1100px 减掉左导航 176px 后内容区只剩 ~920px，稍微拖窄就掉两列，
用户以为"三列丢了"。把阈值收紧到 660px，三列在更窄窗口下也稳定。

### ③ 导出说明文案（需求3/4）

- Android日志导出 desc →「pull /log/android_log 到桌面logcat文件」
- 导出carplay音频文件 desc →「pull /data/carplay/records 到logcat文件」

### ④ 按钮迁移（需求5/6/7）

迁入「指令执行」分组：
- 查前台应用（`:pkg now`）
- 打开TSP后台（`tsp`，即原「启动Cloud App」，用户确认为 com.gac.cloud.app）
- UUID 查询（`uuid`）、DID 查询（`did`）

### ⑤ 指令执行内部分类（需求8）

给 items 加 `cat` 字段，渲染时按 cat 分块插入横跨整行的小标题（`.qcat`）。
四个分类：采集导出 / 开关调试 / 应用控制 / 信息查询，共 18 个卡片。
`.qcat` 不含 `qcard` 类，`querySelectorAll('.qcard')` 索引不受影响，
`data-j` 仍按 items 下标一一对应（DOM 探针验证 datajIndexOk=true）。

## 四之八、全面测试 + 使用文档 + 缺陷修复（2026-11-11 午后）

### 发现并修复的缺陷（dlog Android 日志导出）

`/log/android_log` 是活动日志目录，文件在设备侧实时轮转，逐文件 `adb pull`
中途遇到文件被删（`remote open failed: No such file or directory`）导致整体失败。

修复（`_cs/Adb.cs` + `TaskCmds.cs`）：
- `Export` 加 `forceZip` 可选参数，`DoExportDlog` 传 true 强制打包
- `ExportZipped` 里 tar 失败**重试一次**（轮转竞态偶发，重试通常就过）
- toybox tar 静默失败（无 stderr）时提示「日志文件轮转中，改为逐文件导出」，
  不再甩空错误
- 修复后实测：打包失败回退逐文件，最终成功导出 2389 个文件

### 全面测试结果（真机 b09acfa2）

全部通过：
- CLI 自检 326/326、静态 61、交互 60、vr 30、busy 15、src 26
- 真机：shot(420KB)、apk(86MB)、dlog、hci(4 文件)、car、front、fstop、res、
  pkg now/ver、sysinfo、battery、screen、uuid、did、vr sr/wake/ver/area、
  carplayon、send 中文、ls/getprop 透传
- carplay/pcm 导出走友好提示分支
- GUI：2 tab、7 分组（18/9/3/3/4/3/3 卡片）、语音助手输入区齐全

### 交付：`使用手册.md`

面向新用户的完整使用文档，含：工具介绍、准备工作（含 adb 环境）、界面介绍、
常用操作速查（查信息/截图录屏/导出/语音助手）、命令参考、常见问题 FAQ、
分享清单（4 个文件打包即可分享）。

## 四之九、讨论模式 7 条需求落地（2026-11-11 午后）

讨论模式确认的需求全部实现，最关键的是**并行多命令**。

### ① 并行多命令（真并行）

`>` 左侧加 `+` 号，最多 3 个输入框，每个独立输出区 + 独立停止按钮。

**后端（真并行核心）**：
- `CMD_OK` 改 `[ThreadStatic]` —— 一行改动实现"每 worker 线程独立副本"，不用改 77 处引用
- `GuiSink` 行装配状态（`_cur`/`_curColor`/`_curLevel`/`_dropAnim`/`_pendingCr`）改 `[ThreadStatic]`，`GuiLine` 加 `Slot` 字段
- `GuiWeb` 单 worker → 3 槽位数组（`_worker`/`_busy`/`_cmdSource`/`_stopRequested`/`_lastCmd`），输出消息带 `slot`
- `App.CUR_SLOT` `[ThreadStatic]` 标记 worker 线程槽位，`GuiSink` 据此给输出行打槽位标记

**前端**：`buildSlots`/`slotHTML`/`addSlot` 动态生成输入框；`run`/`stop`/`clearLog`/`copyCmd`/`onInputKey`/`nav` 加 slot 参数；`appendLog`/`appendEcho` 按 slot 路由；`_busy` 布尔 → 数组。

**已知限制**：`CUR`（当前目录）等设备状态保持共享（"多终端共享设备状态"语义），抓日志+查信息这类典型场景不冲突；真并行的 `cd`/相对路径命令可能互相影响目录，属可接受边界。

### ② 复制纯文本
拦截 `slots`/`feedback` 的 copy 事件，只写 `text/plain`，解决深色主题复制到白底看不清。

### ③ 卡片等高
标题 + 说明都单行省略号，悬停 `title` 补全。

### ④ 输出精简
`Echo` 全局去 kind 标签；`uuid`/`did` 内置化（`:uuid`/`:did` 绿色输出 `key: value`）。

### ⑤ 进入工程模式 + 6 条新指令
cmds.ini 加 `autotheme`/`airec`/`engmode`/`bypassgm`；黑夜/白天复用 `yes`/`no`；指令执行分组新增「主题模式」类，共 24 卡片 5 分类。

### ⑥ 日志等级
`persist.log.tag`（V/D/I/W/E）显示在 ROOT 胶囊后（`log-pill` 徽章）。

### 验证
CLI 326、静态、交互 60、vr 30、busy 15、src 26、多输入框探针 20 全绿；真机 uuid/did 绿色、新增命令、日志等级 V、GUI 启动正常。


## 五、语音助手融合（2026-11-10 下午）

**来源**：`C:\Users\zuo20\Downloads\语音助手工具.exe`（Python 3.13 + Tkinter / PyInstaller 打包，作者肖旺银 V1.0.4）。
已完整逆向：PyInstaller 归档 → zlib 解压 → marshal 反序列化 → 拿到 5 个业务模块
（`SpeechUtil.py` / `src/util/AndroidAdbUtil.py` / `Constans.py` / `view/Memu.py` / `AdbLoggerUtil.py`），
全部 adb 调用逻辑已提取，无遗漏。

**实现方式**：新建 `_cs/Voice.cs`（约 600 行），走 `:vr` 命名空间，`Prefix.cs` 加 1 个路由分支。
底层全部复用现有能力（`AdbCall` / `Util.EscapeData` / `Ok·Fail·Hint` / `Clip`），不重复造轮子。

**命令清单**（`:vr help` 可看）：

| 命令 | 作用 | 关键点 |
|---|---|---|
| `:vr wake` | 主驾唤醒 | `vr://...start?type=` + ini 的 `vr_wake_type`（默认 1） |
| `:vr wake 99` | 唤醒（原工具参数） | `type=99&canSleep=false` |
| `:vr sr 文本` | 主驾识别 | `sr://...?text=<URL编码>` |
| `:vr sr 文本 -a 1` | 指定音区 | `-a` 认数字/中文/英文别名，前置后置都行 |
| `:vr local 文本` | AH8 断网识别 | `&mode=local` |
| `:vr ts 文本` | 旧版 TextSemanticService | `--es text/msgType/package` |
| `:vr ver` | 语助版本号 | 设备侧 `grep`（原工具用 findstr 是 bug） |
| `:vr restart` | 重启语助进程 | `am force-stop` |
| `:vr reboot` | 重启车机 | `adb reboot` |
| `:vr un` | 卸载语助 | `adb uninstall` |
| `:vr set` / `:vr dbg` | 后台设置页 / 语义调试页 | `am start -n` |
| `:vr area` | 音区对照表 | 纯本地，离线可用 |
| `:vr log` | 语音日志入口引导 | 引导到已有 `:sid` / `:hci` |

**简写**：`:vr 打开车窗` 等价 `:vr sr 打开车窗`（兜底走 sr）。

**音区映射**（AH8 0626apk 起）：`0主驾 1副驾 2二排左 3二排右 4三排左 5三排右`，
`-a` 也认 `driver/passenger/rear2l/rear2r/rear3l/rear3r`。

**GUI**：快捷指令页新增「语音助手」分组（第 8 组，粉色 `#e879a8`），9 张卡片。
带参卡片（语音识别/断网识别）走"填入输入框"流程，其余一键执行。

**新增 ini 配置**（`adb_log_export.ini` 末尾「语音助手调试」段）：
`vr_pkg` / `vr_vr_uri` / `vr_wake_type` / `vr_wake_type_alt` / `vr_sr_uri` / `vr_text_max` / `vr_ts_service` / `vr_ts_package`。

**关键设计决策**：
1. **不做成 `:send` 子参数** —— `:send` 的 URI 在 ini 硬编码、`BuildAmCmd` 只认单一前缀，
   而语音需要 3 种 URI + 2 个可选参数；且 `:send` 的批量发送必须原样保留。
2. **`&` 只能有一层引号**（改动时最容易踩，**已实测纠正**）：
   - URI 外层用**双引号**包住：`-d "sr://...?text=X&voiceArea=1"`
   - 因为已经在双引号内，`&` 天然是字面量，**URI 里必须写裸 `&`，不能写 `'&'`**
   - ⚠️ 早先写成 `'&'` 是错误的（当时以为"设备侧要单引号"）：那个结论只在
     URI 外层**不加引号**时成立。叠加双引号后 `'` 退化成普通字符，设备实际收到
     `text=X'&'voiceArea=1` → text 结尾多一个 `'`、参数名变成 `'voiceArea`，音区失效。
   - 已用伪造 `am` 脚本回显 argv 端到端实测（`verify_vr_e2e.py`，30 项）
   - Windows 侧：整条命令因含空格被 `QuoteArg` 包双引号，且 `RunRaw` 走
     `UseShellExecute=false` 直接 CreateProcess **不经过 cmd.exe**，`&` 不会被吞
3. **唤醒两套参数都留** —— `type=1`（新文档）与 `type=99&canSleep=false`（原工具实测）行为不同，
   现场可对比，用 `:vr wake 99` 切。
4. **`am -n` 组件名用 `pkg/.Cls`** —— 原工具拼 `pkg/com.pkg.Cls` 双包名（`ActivityNotFound`），
   `VrComponent()` 统一拼标准形式，自检 7 条锚点锁死。

**验证结果**（2026-11-10 全量测试后，**含真机实测**）：
- CLI 自检 **280 项全部通过**，0 失败
- `verify_vr_e2e.py` 端到端 **30 项全部通过**（覆盖 Windows 传参 → adb → 设备 sh 三段链路）
- CLI `adb_log_export.exe` 与 GUI `adb_Tool.exe` 均编译通过
- GUI 无头 `--exec-file` 跑 12 条 `:vr` 命令全部 `rc=0`，输出与 CLI 一致
- 原有功能回归通过：`:which` 路由、32 条 DIY 命令、`:h`/`:h all`、离线白名单均正常
- **真机环境**：`311b4567`（135 / AH8 8295，语助 `vpa.asst.share.3.6.8...gac_ah8_8295standard`）
  - `sr://` 主驾识别 + `voiceArea=1` 副驾识别：Intent 解析正确，`&` 未丢失
  - 旧写法 `'&'` 在真机复现污染：`dat=...text=打开车窗'&'voiceArea=1`（单引号残留）
  - `:vr set` / `:vr dbg`：两个调试页都能成功拉起（类名修对之后）
  - `:vr ver`：正确读出 `versionName` + `versionCode`
  - 旧版 `TextSemanticService` 在本机**确实存在**（`exported=true`），`:vr ts` 可用

**全量测试发现并修复的 7 个 bug**（详见第六节）：

| # | 问题 | 影响 |
|---|---|---|
| 1 | URI 里写 `'&'` 且外层加双引号 | 设备收到 `text=X'&'voiceArea=1`，文本被污染 + 音区失效 |
| 2 | `am -n` 拼成 `pkg/com.pkg.Cls` 双包名 | 调试页 `ActivityNotFound` |
| 3 | `local` 裸词被当开关吞掉 | 发送 `打开 local 模式` 实际发 `打开 模式` |
| 4 | `VrLooksBad` 漏 `failure`/`failed` | `adb uninstall` 失败（rc=0 + `Failure[...]`）误报成功 |
| 5 | 硬编码 `startservice`/`VIEW` | 改 ini 的 `am_cmd` 对 `:vr` 无效，与 `:send` 不一致 |
| 6 | `-a 9` 非法音区静默当文本发出 | 用户以为指定了音区，实际把 `-a 9` 念了出去 |
| 7 | 调试页类名猜错（`.SettingDebugActivity`） | 真机 `Error type 3 ... does not exist`，页面打不开 |
| 8 | `reboot`/`un` 无二次确认 | **冒烟测试真的重启了车机**，差点卸载生产语助 |

> 第 7 条最值得记：单测全绿 + 端到端全绿，`VrComponent` 的拼接逻辑也是对的，
> 但**类名本身是猜的**。这类"常量错误"只有连真机跑才能发现。
> 以后凡是 `am -n` / `am startservice` 里的包名类名，一律从设备 `dumpsys` 取，不要凭记忆写。


- GUI 卡片视觉截图核对：9 张卡片、图标/文字齐全、带参卡片边框青绿

**改源码时注意**：`Voice.cs` 要同时加进 `_cs/build.bat` 和 `adb_log_gui/build_gui.bat`
的源文件列表（两个编译脚本各维护一份列表）。

## 六、必踩过的坑（避免重蹈）

1. **测试环境窗口会落离屏坐标（-32000）、SetCursorPos 偏移不稳定** → 无法用鼠标模拟可靠验证点击。UI 交互验证交给用户本机双击 exe 看。
2. **视觉模型不可用**（本会话无法看图）→ 截图只能靠像素分析，低效且易误判。颜色/图标类问题优先让用户本机确认。
3. **`CmdRegistry.cs` 不是独立类，是 `App` 的 partial** → 访问它用 `App.xxx` 不是 `CmdRegistry.xxx`。
4. **`:` 前缀内置命令**，快捷指令卡片 cmd 要写 `':res'` 这种；cmds.ini 命令不用 `:`。
5. **`GuiWeb.cs` 需要 `using System.IO;`**（Path/Directory）。
6. **改 `cmds.ini` 后要同步到 `adb_log_gui/cmds.ini`**（build 脚本只在无文件时才从上级复制）。
7. **透传输出颜色 = 执行时 Console.ForegroundColor**（AdbCallStream 里 Console.WriteLine）；查询命令要统一色用 UseOk()。
8. **`'&'` 是陷阱**（本次最大的坑）：URI 外层已用双引号时，URI 里必须写**裸 `&`**。
   写成 `'&'` 会让单引号残留在值里（`text=X'&'voiceArea=1`），参数解析失败。
   `'&'` 只在 URI **完全不加引号** 时才正确。
9. **`am -n` 必须写 `pkg/.Cls`**，不能把完整类名再拼一次包名（`pkg/com.pkg.Cls`）→ `ActivityNotFound`。
10. **`adb uninstall` 失败时 rc 仍是 0**，错误在标准输出的 `Failure [...]` 里，
    只看退出码会误报成功。`am` 的 `Error: Activity not started` 同理。
11. **字符串级断言测不出引号链路问题**：`Render.cs` 自检只能验"URI 长什么样"，
    验不了"设备侧 sh 真正收到什么"。这类问题必须用 `verify_vr_e2e.py`（伪 `am` 回显 argv）。
12. **假 adb 不能用 `.bat`/`.cmd`**：会被 Windows 强制走 cmd.exe，`&` 变分隔符造成假阳性。
    用 `.ps1` 或直接以 Python 回显 argv。
13. **`am -n` 的包名/类名一律从设备 `dumpsys` 取，不要凭记忆写**。
    本轮在这上面连错两次：先双包名，再猜错子包路径（`.SettingDebugActivity`）。
    取法：`adb shell dumpsys package <pkg> | grep -oE '<pkg>/[A-Za-z0-9_.]*'`
14. **`am startservice` 打印 `Starting service:` 不代表成功**。
    包没装时它也会先打这句再报 `Error: Not found; no service started.`；
    而且 rc 可能是 0、stderr 可能为空 —— 判断成败必须看合并输出的关键字。
15. **破坏性命令必须加显式确认开关**（`-y`）。本轮冒烟测试"无脑喂所有子命令"，
    把 `:vr reboot` 发给了一台**真实在线车机**，车机真的重启了。
    **教训：跑冒烟测试前必须先断言"设备已断开"，或先确认命令清单里没有破坏性项。**
16. **单测全绿 ≠ 功能可用**：`VrComponent` 的拼接逻辑有 10 条锚点全过，
    但传进去的类名常量是错的，只有真机能发现。常量要实测。
17. **CSS 类名撞车是隐形杀手**：裸 `.running{display:none}` 与 `.qcard.running`
    撞名，卡片一点击就整个消失。**通用词（running/active/on/hide/show）
    做类名时必须带前缀**，或写成组合选择器限定作用域。看源码发现不了，
    要在浏览器里 `getComputedStyle(el).display` 量出来。
18. **断言要剥注释再判**：`_check_ui.js` 里断言"不存在 insertBefore(row"，
    结果被自己写的说明性注释判失败。文本断言前先 `replace(/\/\*[\s\S]*?\*\//g,'')`。
19. **`PrintWindow` 抓 WebView2 窗口**：`CopyFromScreen` 会抓到压在上面的别的窗口
    （`SetWindowPos(HWND_TOPMOST)` 在这台机器上也不生效）；改用
    `PrintWindow(hwnd, hdc, PW_RENDERFULLCONTENT=0x2)`，跟遮挡无关。
    **不带 0x2 会得到黑块**（DirectComposition 内容）。
20. **表头与内容"结构不对应"就永远调不齐**：给三个标签调 padding/margin 是白费力气 ——
    标签横排、内容竖排，几何上不可能对齐。**先把两边 DOM 结构做成同构**，再谈间距。
21. **百分比分栏 + 单边 border = 1px 隐性错位**：`.fb-row` 有 `border-left:2px`、
    表头没有，两边 `flex-basis:46%` 的基数差 2px，右栏起点就差 ~1px。
    **要么两边都加同宽透明 border，要么把 border 挂在共同父级上**。
22. **`class` 写进 JS 但 CSS 里没有对应规则 = 元素宽度 0**：`.fb-split` 就是这种，
    看起来"有这个分隔线"，实际鼠标抓不到。**新增 class 后必须回 CSS 里搜一遍**，
    或用 `getComputedStyle(el).width` 断言非 0。
23. **对齐要量字形，不是量盒子**：元素盒对齐不代表文字看起来对齐（内边距、
    `text-align` 都会造成视觉偏移）。用 `Range.selectNodeContents(el)` +
    `getBoundingClientRect()` 取真实字形范围，才是用户看到的位置。
24. **headless 截图前要先让页面"真的显示"**：`.frame` 是 `opacity:0;visibility:hidden`
    靠 `.show` 类才出现，只改 `style.opacity` 截图仍是全黑；而且反馈区在
    `#page-quick` 页，得先 `switchTab('quick')`。踩了两轮才截出正常画面。
25. **`StartsWith("out")` 这类宽匹配会吃掉未来函数**：`$(out:xxx)` 判断最初写成
    `fn.StartsWith("out")`，以后加 `$(output)` 就被误判。**前缀匹配要带上分隔符**
    （`StartsWith("out:")`）或精确匹配。
26. **重定向到不存在的目录会直接失败**：`cmd > path` 里若 path 的父目录不存在，
    命令整体失败。所以 `$(out:xxx)` 必须在**求值时**就 `Directory.CreateDirectory`，
    不能指望写文件时自动创建。
20. **WebView2 里 `--headless` 截图不行，但 Edge headless 可以用**：
    用 `msedge.exe --headless=new --dump-dom` 抓注入的测试结果，
    可以在不改生产代码的前提下做 DOM 级交互断言（点击前后 class 变化等）。
21. **`wm size` 有 Override 行时以 Override 为准**（那才是实际生效值）；
    多行输出要用 `tr '\n' ';'` 压平，否则只取第一行会漏掉 Override。
22. **PowerShell 工具被安全策略限制**：`Add-Type` 被禁（等价于运行时编译），
    `csc.exe` 直调也被禁。截屏改用 Python + PIL + ctypes（`user32`/`gdi32`）。


## 七、编译与验证

```bash
# 编译 CLI（build.bat 末尾有 pause，非交互执行要喂空行）
printf '\n' | cmd //c "cd /d <项目>\_cs && build.bat"

# 编译 GUI（先杀旧进程，否则 move 替换 exe 会"拒绝访问"）
taskkill //F //IM adb_Tool.exe
printf '\n' | cmd //c "cd /d <项目>\adb_log_gui && build_gui.bat"

# 改 cmds.ini 后同步
cp cmds.ini adb_log_gui/cmds.ini

# 自检（CLI，309 项，含导出目录分类 17 项）
./adb_log_export.exe -selftest

# 端到端链路验收（:vr 专用，30 项）
python verify_vr_e2e.py

# 前端静态自检（语法 + DOM 引用 + 九问题 + 需求1 逐条覆盖）
node 377/_check_ui.js

# 前端交互行为测试（headless Edge + DOM 断言，60 项）
python 377/_test_ui_behavior.py

# 列对齐像素级断言（字形级，4 种窗口宽度 × 11 项）
python 377/_measure_text_align.py

# 抓对齐效果截图（headless 渲染 + 注入样例记录）
python 377/_shot_align.py

# 抓真实窗口截图（PrintWindow，不受遮挡影响）
python 377/_shot_pw.py

# 无头命令验证（GUI 不启动界面；批量用 --exec-file，注意 --exec 会按空格拆参数）
printf ':vr area\n:vr help\n:h all\n' > /tmp/cmds.txt
./adb_log_gui/adb_Tool.exe --exec-file /tmp/cmds.txt
```

**验证矩阵（本轮最终状态）**：

| 层 | 脚本 | 项数 | 覆盖 |
|---|---|---|---|
| 逻辑 | `-selftest` | 326 | 解析函数、分辨率、导出目录分类、车机信息九项 |
| 静态 | `377/_check_ui.js` | 61 | 源码文本、DOM 引用、九问题 + 需求1/4 |
| 交互 | `377/_test_ui_behavior.py` | 60 | 真实浏览器 DOM 断言 |
| 像素 | `377/_measure_text_align.py` | 44 | 字形级列对齐 × 4 宽度 |
| 链路 | `377/_test_src_route.py` | 26 | 输出跟着页签走（需求3，含 3 个坑的反向锁） |
| 互斥 | `377/_test_busy_lock.py` | 15 | 多指令互斥不卡死（需求9） |
| 语音页 | `377/_test_vr_ui.py` | 24 | 语音助手页：音区/发送/回显（需求8） |
| 探针 | `377/_probe_cnw.py` | 2 | 无黑窗（子进程自证，正反双向） |
| 端到端 | `verify_vr_e2e.py` | 30 | 语音助手端到端 |
| 真机 | `377/_test_rec_stop.py` | 4 | 录屏强杀后仍完整落盘（需求2 前提） |
| 视觉 | `377/_shot_align.py` / `377/_shot_real_gui.py` / `377/_shot_vr.py` | — | 网页渲染 + 真实窗口截图 |

**注意**：
- CLI 版**没有** `--exec-file`，只有 `-selftest` / `-adb` / `-serial`；
  批量喂命令用 stdin 管道（`printf ':h\n\n' | ./adb_log_export.exe`）。
- GUI 的 `--selfcheck` 输出在 WinExe 里没有控制台，看不到结果；
  要验逻辑请走 CLI 的 `-selftest`（两边共享同一份源码）。
- 前端验证脚本放在 `377/`（验证产物目录），不污染项目根。


## 八、协作建议（提升效率）

- 新开会话续做，别在超长会话里继续堆需求
- 需求"定点"：截图 + 一句话指出问题
- UI 视觉/交互靠用户本机跑 exe 确认，我负责逻辑和编译
