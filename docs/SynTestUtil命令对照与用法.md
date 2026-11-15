# SynTestUtil 功能命令对照与用法

> 生成日期：2026-11-14；2026-11-15 按参考图重构后同步修订
> 承接需求：① 前后排投屏 ② 十个功能的命令与用法 ③ 指令页复用 ④ 网络模拟复用 ⑤ 投屏右侧新增 UI 对比页签
> 原则：**以文件为准，不猜**。每条命令都标明证据来源；没有直接证据的标【推断】并写出验证方法。

---

## 0. 证据源与局限

| 标记 | 来源 | 说明 |
|---|---|---|
| 【实·日志】 | `SynTestUtil/log/polaris-info.log` | 2,221,042 B，2024-06-22 与 2026-11-13~14 两次运行；`tools.commons.adb:adb_cmd:8 - cmd:` 共 **13 条唯一命令** |
| 【实·脚本】 | `_internal/adbutils/binaries/` 三个投屏脚本 | 见 §2 |
| 【实·DB】 | `_internal/syntest.db` → `path` 表 19 行 | 产物目录命名 |
| 【文·逆向】 | 项目内 `SynTestUtil功能逆向与需求源_20261103.md`、`SynTestUtil源码级解析_20261104.md` | 已有逆向结论 |
| 【我方】 | `cmds.ini` / `ui.html` / `_cs/*.cs` | 本工具等价实现 |
| 【推断】 | 无直接证据 | 按命名/上下文推得，**上机确认前不算定论** |

**必须先说清的三个局限：**

1. 日志里只有 13 条 `adb_cmd` 命令。采集类长任务（logcat / tcpdump / scrcpy）**不走统一 adb 封装**，而是起子进程（【文·逆向】§2.3），所以日志里查不到它们的命令行。
2. 十个功能名是 UI 按钮文案，日志只落**英文函数名**（`car_net`、`vin`、`coordinate_off`、`scrcpyfront`、`zhzs`…），功能名与命令的对应关系部分靠时间窗口与语义推断。
3. `scrcpyback` 在本次日志里 **0 次命中**，`scrcpyfront` 1 次，两者参数差异仍未由日志确认；能由脚本确认的只有 `--display-id=1`。

---

## 1. 实现协议（先定协议再写实现，项目规则 B2）

### 1.1 分层与改动范围

| 层 | 改动 | 文件 |
|---|---|---|
| 数据 / 纯函数 | 主屏 = displayId 0、后排屏 = displayId 1；纯函数 `castDefaultId(i)` / `castHasDisplay(disp,id)` | `ui.html` |
| 后端动作 | 命令链路零改动：复用 `case "quick"` → `App.Dispatch`、`case "caststart"` → `Cast.CastStart(slot, displayId)`；本轮仅为「点击流畅」在 `Cast.cs` / `GuiWeb.cs` 加 `Kick` 与丢弃式 tap 队列 | `_cs/Cast.cs`、`_cs/GuiWeb.cs` |
| 消息协议 | **不新增 kind**：卡片 / 表单 `post('quick', cmd)`；投屏 `postObj({kind:'caststart', slot, id})`；UI 对比纯前端，不走消息桥 | 无 |
| 前端渲染 | `quickGroups` 分组（2026-11-15 重构，见 §2.2 / §4.2 / §5）；投屏固定格子内建屏位、删三个按钮；新增 `#page-ui` | `ui.html` |
| 样式 | 复用 `.btn`；新增 `.ns-*` / `.ui-*` / `.logpill[data-lv="none"]` / 投屏禁拖拽；**第三轮起 `.fs-enter` 已删除**（搜索结果改为点整行进树），全量换为 Apple 语义令牌 | `ui.html` |
| 配置 | 新增 `st*` 系列命令，全部配置化 | `cmds.ini` |
| 验证 | 功能清单 + 机检清单 + 结构/行为/投屏断言 + 手册 | §1.4 |

### 1.2 消息协议与并发归属（以代码为准）

- **卡片**：`ui.html → post('quick', <命令>)` → `_cs/GuiWeb.cs` 的 `case "quick"` → `SubmitCmd(txt, 1, 0)`。
  输出源 `src=1`（反馈表），固定槽位 `slot=0`，**输出不跳页**（现有交互，不改）。
- **主屏 / 后排屏**（2026-11-15 起）：固定格子「主屏」（槽 0）/「后排屏」（槽 2）由 `castDefaultId(i)` 内建 displayId 0 / 1，`castToggle()` 在下拉未选时也用它兜底，仍走 `postObj({kind:'caststart', slot, id})` → `Cast.CastStart(slot, displayId)`。
  **探测列表里找不到该屏就退化为按顺序分配**（`castHasDisplay()` 返回 false），其它车型仍可用。内置截帧通道 `CastGrabPng` 用 `adb exec-out screencap -d <displayId> -p`，画面经 multipart 流回传到页内 `<img>`，**不启动任何外部窗口**。
- 不新增设备判定分支，沿用现有 `_online` 检查（规则 A6：判定要有正向证据）。
- 不新增 `.cs`，因此不涉及两个 bat 的编译列表（规则 A1）；`#page-*` 层级不动（规则 A3）；投屏 `<img>` 不 `display:none`（规则 A4）。

### 1.3 前后排映射

| 概念 | displayId | 证据 |
|---|---|---|
| 主屏（前排，槽 0） | 0 | scrcpy 默认屏；`scrcpy-noconsole.vbs` 不带参数即主屏 |
| 后排屏（第二块屏，槽 2） | 1 | `scrcpy-console.bat` 全文 `scrcpy.exe    --display-id=1`；`open_a_terminal_here.bat` 全文 `scrcpy --display-id=1` |

2026-11-15 起这两个 id 由 `castDefaultId(i)` 直接给出（槽 0 → 0、槽 2 → 1），不再依赖按钮或 `castRowId(disp,row)`；旧函数已删除。`castFillSelects()` 用它设下拉默认值，探测不到时退化为按顺序分配。

### 1.4 验证登记

| 改动 | 保护落点 |
|---|---|
| 11 卡并入「指令执行」+ 三类小标题 | `docs/功能清单.md`、`quick.syntest`、`377/_test_ui_behavior.py` |
| 网络模拟表单面板 | `docs/功能清单.md`、`quick.netsim`、`377/_test_ui_behavior.py` |
| 主屏 / 后排屏内建（原两按钮已删） | `docs/功能清单.md`、`cast.builtin-rows`、`377/_test_structure.py`、`377/_test_cast_ui.py` |
| UI 对比页 | `docs/功能清单.md`、`page.ui`、`377/_test_structure.py` |
| 命令配置 | `_check_features.json` 检查 `cmds.ini` 里的 `[cmd.st*]` 锚点 |
| 使用说明 | `docs/用户使用手册.md` |

---

## 2. 前后排投屏方案（需求 1）

### 2.1 逆向实证

`_internal/adbutils/binaries/` 下三个文件（原文照录）：

```bat
:: open_a_terminal_here.bat
@cmd
scrcpy --display-id=1
```

```bat
:: scrcpy-console.bat
@echo off

scrcpy.exe    --display-id=1
```

```vbscript
' scrcpy-noconsole.vbs
strCommand = "cmd /c scrcpy.exe"

For Each Arg In WScript.Arguments
    strCommand = strCommand & " """ & replace(Arg, """", """""""""") & """"
Next

CreateObject("Wscript.Shell").Run strCommand, 0, false
```

**读出来的结论：**

- `--display-id=1` 是切换第二块屏（后排）的关键参数，两个 bat 都写死它。【实·脚本】
- `Wscript.Shell.Run ..., 0, false`：`0` = `SW_HIDE`，隐藏的是 **cmd 控制台窗口**；`false` = 不等待子进程。它解决的是「不弹黑窗」，**并没有解决 scrcpy 自己的 SDL 窗口抢焦点**。【实·脚本 + 分析】
- 日志里 `scrcpyfront` 出现 1 次（2024-06-22 21:07:04），`scrcpyback` 0 次，两段都只有 `start/stop function` 装饰器行，没有命令行 —— 印证【文·逆向】§2.3「采集类功能不走 adb_cmd」。【实·日志】

### 2.2 我方实现（保持投屏不切出应用）

**不照抄「弹 scrcpy 独立窗口」，改用本工具已有的内置截帧通道：**

| 项 | SynTestUtil | 我方 |
|---|---|---|
| 选屏 | `scrcpy --display-id=N` | `screencap -d N -p`（`_cs/Cast.cs` 的 `CastGrabPng`） |
| 画面落点 | scrcpy 的 SDL 独立窗口（**切出应用**） | 页内 `<img>` + multipart 流（**留在应用内**） |
| 控制台 | VBS 隐藏 cmd 窗口 | `UseShellExecute=false` / 无子进程，根本没有黑窗 |
| 焦点 | SDL 窗口会抢焦点 | 不创建新窗口，主窗口焦点不变 |

2026-11-15 起**删除「前排投屏」「后排投屏」「刷新屏位」三个按钮**，把能力内建进固定格子：主屏（槽 0）→ displayId 0，后排屏（槽 2）→ displayId 1，由纯函数 `castDefaultId(i)` 给出；`castFillSelects()` 用它设下拉默认值，`castToggle()` 在下拉没选时用它兜底。旧函数 `castRow()` / `castRowId()` 已移除。

**用法：**
1. 连上设备 → 切到「投屏」页，**进页面自动探测屏位**（`dumpsys display`），不用手动刷新。
2. 「主屏」「后排屏」两格直接点「开启」即可，不用先选下拉；其余格子在下拉里选屏（默认按顺序分配）。
3. 再点「停止」结束该路。**不弹任何外部窗口**，可继续在应用内点画面、录屏、切页。
4. 探测列表里找不到内建 displayId 时退化为按顺序分配，不会静默失败。

> 若确实需要 scrcpy 的高帧率，每格右下原有的「外部」按钮仍可用（`Scrcpy.Launch` 已支持 `--display-id=N`）。这是**用户显式选择**才切出应用，与一键前后排互不冲突。

---

## 3. 十个功能的命令与用法（需求 2）

### 3.1 总表

| # | 功能 | SynTestUtil 实际命令 | 证据 | 我方命令 | 我方落点 |
|---:|---|---|---|---|---|
| 1 | 抓全日志 | `logcat -c` → `logcat -v time > <logpath>\MM-DD-HHMMSS.txt`（长任务，日志无记录） | 【文·逆向】§5.1 | `stlogall` → `logcat -v time -d -t 2000` | `cmds.ini` |
| 2 | 抓系统日志 | `shell am start -n com.gxa.car.systemlog/com.gxatek.logger.MainActivity` | 【实·日志】 | `stsyslog` | `cmds.ini` |
| 3 | 抓TCPdump数据 | `adb root` → `shell "tcpdump -i any -w /data/<time>.pcap"` → `pull` → `rm` | 【文·逆向】§5.3 | `sttcpdump` → `shell "tcpdump -i any -c 200"` | `cmds.ini` |
| 4 | 开启坐标 | `shell settings put system pointer_location 1` | 【实·日志】 | `stxyon` | `cmds.ini` |
| 5 | 关闭坐标 | `shell settings put system pointer_location 0` | 【文·逆向】§5.6 | `stxyoff` | `cmds.ini` |
| 6 | 查看VIN | `getprop persist.sys.vehicle.vin`（`information` 的 9 属性之一） | 【文·逆向】§5.12 + 日志 `vin` 函数名 | `stvin` | `cmds.ini` |
| 7 | 网络状态 | `shell ping -c 5 www.baidu.com` + `shell ifconfig wlan0` | 【实·日志】×2 | `stping` / `stip` | `cmds.ini` |
| 8 | 日志配置 | `am start -n com.android.engmode/com.android.engmode.MainActivity`（工程模式主页） | 【文·逆向】F 组 `gcms`；【推断】 | `stlogcfg` | `cmds.ini` |
| 9 | 账号助手 | `shell am start -n com.android.engmode/com.android.engmode.ui.AssistantActivity` | 【实·日志】+ 日志 `zhzs` 函数名 | `staccount` | `cmds.ini` |
| 10 | 下线配置 | `am start -n com.android.engmode/.ui.OfflineConfigActivity` | 【文·逆向】F 组 `xxpz`；【推断】 | `stoffline` | `cmds.ini` |

### 3.2 逐条说明

**1. 抓全日志 `stlogall`**
- 逆向做法：清缓冲后起 `logcat -v time` 子进程**持续落盘**，再点一次停止并 pull（【文·逆向】§5.1、§2.3 单实例模型）。日志里查不到命令，因为它不走 `adb_cmd`。
- 我方做法：`logcat -v time -d -t 2000` 一次性导出当前缓冲最近 2000 行到输出区，避免把几十 MB 日志灌进 GUI；需要长时采集仍用我方 `:sid`（流式）或 `:dlog`（导出 `/log/android_log`）。
- 用法：指令页 →「指令执行」→「日志与取证」→「抓全日志」。输出在反馈表，可「复制全部」。

**2. 抓系统日志 `stsyslog`**
- 实证命令（日志原文）：`cmd: shell am start -n com.gxa.car.systemlog/com.gxatek.logger.MainActivity`。这是车机上的「系统日志」App 主页，测试岗从里面开抓取/看配置。
- 用法：点卡片即打开该 App，之后在车机上操作。

**3. 抓TCPdump数据 `sttcpdump`**
- 逆向做法：`adb root` → `tcpdump -i any -w /data/<time>.pcap` → 停止后 `pull` + `rm`（【文·逆向】§5.3）。`/data/` 需要 root。
- 我方做法：`shell "tcpdump -i any -c 200"`，抓 200 个包直接回显到输出区，**不在设备侧落文件**，因此不需要 root 写 `/data`、也不留残留。需要完整 pcap 文件时，用终端页手动跑逆向那套四步。
- 用法：点卡片；若设备无 tcpdump 或权限不足，输出区会显示设备原话。

**4/5. 开启坐标 `stxyon` / 关闭坐标 `stxyoff`**
- 实证：`cmd: shell settings put system pointer_location 1`（日志 2024-06-22 23:57:05，对应函数名 `coordinate_off` 的配对操作）。逆向文档 §5.6 给出 `0` 为关闭、"先读再切"做开关。
- 用法：各一张卡片，点完看车机屏幕是否出现坐标十字；读当前值可在终端页敲 `shell settings get system pointer_location`。

**6. 查看VIN `stvin`**
- 命令：`shell getprop persist.sys.vehicle.vin`。日志里 `start function 'vin'` 出现 1 次（2026-11-14 22:47:13），属性键来自【文·逆向】§5.12 的 9 属性表。
- 用法：点卡片，VIN 直接显示在反馈表。完整车况看我方已有的「车机信息」卡片 `:car`。

**7. 网络状态 `stping` / `stip`**
- 实证两条（日志原文）：`cmd: shell ping -c 5 www.baidu.com`、`cmd: shell ifconfig wlan0`（各 3 次，函数名 `car_net`）。
- 拆成两张卡片：一张测公网连通、一张读 wlan0 地址。用法：连上设备后点，看是否有 `64 bytes from` 与 `inet addr`。

**8. 日志配置 `stlogcfg`**
- 【推断】工程模式主页是日志设置的入口（我方 `:pcm` 的说明就是「工程模式→日志设置→audio→使能开关」）。逆向文档 F 组 `gcms` 命令实测 18 次。
- 命令：`shell am start -n com.android.engmode/com.android.engmode.MainActivity`。
- **待上机确认**：车机「日志配置」是否有独立 Activity；若有，把 `cmds.ini` 里 `stlogcfg` 的 `run` 换成实际组件名即可，不用改代码。

**9. 账号助手 `staccount`**
- 实证（日志原文）：`cmd: shell am start -n com.android.engmode/com.android.engmode.ui.AssistantActivity`，且日志有 `start function 'zhzs'`（1 次）。【文·逆向】F 组把 `zhzs` 记为工程模式-助手页，两者一致。
- 用法：点卡片直接跳转到助手页。

**10. 下线配置 `stoffline`**
- 【文·逆向】F 组 `xxpz`（2 次）：`am start -n com.android.engmode/.ui.OfflineConfigActivity`；源码级文档 §5.15 另描述了一个「读 `下线配置.json` 输出 HTML 表格」的 `xxpz`，**两份材料不一致，属于版本差异**。
- 我方取「打开离线配置页」这条（有 adb 命令、可直接复用），用逆向文档原文的相对组件名。
- **待上机确认**：该 Activity 的全路径。若跳转失败，看输出区的 `Error type 3` 再改 `cmds.ini`。

### 3.3 为什么有三条标【推断】

日志只落函数名、不落按钮中文名，`日志配置` / `下线配置` / `抓全日志` 这三个名字与命令的对应关系没有直接证据。按项目规则「不许猜」，这里把它们标成推断并给出验证方法，**没有假装成实测**。

---

## 4. 网络模拟（需求 4）

### 4.1 逆向做了什么

| 功能 | 命令 / 参数 | 证据 |
|---|---|---|
| 取本机 IP | `get_local_ip`（20 次），样例 `10.41.152.100` | 【文·逆向】F-E1 |
| 设代理 | `settings put global http_proxy <PC_IP>:8888` | 【文·逆向】F-E2 |
| 查代理 | `settings get global http_proxy`（**56 次，所有 settings 操作里最多**） | 【文·逆向】F-E2 |
| 清代理 | `settings delete global http_proxy` + `delete global global_http_proxy_host` + `delete global global_http_proxy_port`（**三键一起删**） | 【文·逆向】F-E2 |
| 代理服务 | mitmproxy 监听 8888，加载 `temp_mitmproxy_script.py` | 【文·逆向】F-E3 |
| 弱网参数 | `UPLOAD_RATE=15` / `DOWNLOAD_RATE=15` / `UPLOAD_DELAY=0.5` / `DOWNLOAD_DELAY=0.4` / `UPLOAD_LOSS=0.0` / `DOWNLOAD_LOSS=0.0`（KB/s、秒、比率） | 【文·逆向】F-E4 |

**逆向方案的三条硬局限**（【文·逆向】F-E4 实测推断）：只对 HTTP(S) 生效，UDP / 原生 socket 不受影响；丢包是「整个请求丢弃并返回 502」的假丢包；限速粒度 1 秒，短请求几乎不减速。项目内 `SynTestUtil功能逆向与需求源_20261103.md` §7 已把「应用层弱网代理（mitmproxy 版）」列为**明确不做**，理由正是「只影响 HTTP，丢包是假丢包，价值低于 `tc netem`」。

### 4.2 我方实现

**代理部分原样复用逆向命令**（这是纯 adb settings 操作，与 PC 侧有没有 mitmproxy 无关）；**弱网部分按逆向文档自己的建议改用设备端 `tc netem`**，参数沿用逆向的 delay / loss / rate 三元组。

2026-11-15 起由「网络模拟」**表单面板**下发（不再是 5 张卡片；5 条命令仍保留在 `items` 里供搜索命中）。面板「开启」把当前**上行**参数折成 `stweak <延迟>ms <丢包>% <速率>kbit`；下行列用于记录设计参数，`tc netem` 只作用于 `wlan0` 出口。

| 卡片（旧）/ 面板按钮 | 我方命令 | 用法 |
|---|---|---|
| 代理查询 | `stproxyget` → `shell settings get global http_proxy` | 点一下看当前值，期望 `null` 表示没走代理 |
| 开启代理 | `stproxyon` → `shell settings put global http_proxy $1` | 需要补参数：`stproxyon 10.41.152.100:8888`。卡片会把命令填进终端页输入框并提示格式 |
| 关闭代理 | `stproxyoff` → 三条 `settings delete` 用 `;` 串在一条设备侧 shell 里 | **必须三键一起删**；只删 `http_proxy` 会留 host/port 残值，看起来清了实际还走代理 |
| 弱网模拟 | `stweak` → `shell "su 0 tc qdisc replace dev wlan0 root netem delay $1 loss $2 rate $3"` | 需要补参数：`stweak 200ms 5% 1mbit`。**需 root**，`su 0` 是逆向夜間模式那条实证过的提权写法 |
| 关闭弱网 | `stweakoff` → `shell "su 0 tc qdisc del dev wlan0 root"` | 一键还原，删除 qdisc 规则 |

**与逆向实现的差别（不藏着）：**

1. 没有把 mitmproxy / Python 打进本工具 —— 本工具是 C# 单文件 + WebView2，加 Python 运行时会推翻交付形态。代理**命令**照用，代理**服务**需 PC 侧自行启动（逆向包里自带 `mitmdump.exe`）。
2. 丢包与限速由 `tc netem` 在内核网络栈生效，覆盖 UDP 与原生 socket，比逆向的 HTTP 502 假丢包更接近真实弱网。
3. `tc netem` 需要 root 且车机内核支持 `sch_netem`；不支持时输出区会给出 `su`/`tc` 的设备原话，不会静默失败。

### 4.3 典型链路

```
指令页 →「网络模拟」（表单面板）
  1) 点「配置代理」(`stproxyget`) 确认当前是 null
  2) PC 上起 mitmdump（监听 8888）
  3) 代理地址填 10.41.152.100:8888 → 点「开启代理」(`stproxyon`)
  4) 复现问题；需要弱网则选预置环境值或填上下行参数 → 点「开启」(下发 `stweak`)
  5) 收尾：点「关闭」(`stweakoff`) →「关闭代理」(`stproxyoff`) →「配置代理」复核为 null
```

---

## 5. UI 对比页（需求 3 的 UI tab，2026-11-15 新增）

### 5.1 参考图与取舍

参考图为 SynTestUtil「UI 对比」页：设计图路径 / 透明度、本地图路径 / 透明度 / 直接截图 / 后屏截图、设计图与实景图双栏、结果图路径 / 是否标记差异 / 2016车机是否需要打开 / 开始对比 / 打开结果图。

本工具在「投屏」右侧新增 **UI** 页签复刻布局，功能在浏览器内重做，**不照搬原实现**：

| 项 | SynTestUtil | 我方 |
|---|---|---|
| 图片来源 | 填设备 / 本地路径 | File API 选本地文件（`uiPick()`），图片以 data URL 留在页面内，**不出本机** |
| 叠加 / 差异 | Python + PIL（逆向包内脚本，见【文·逆向】） | Canvas `getImageData()` + 纯 JS 逐像素（`uiDiffPixels()`），不引入 Python / PIL |
| 结果图 | 写到结果图路径、用「打开结果图」查看 | 本页生成 dataURL，「打开结果图」导出 `ui_compare_<时间戳>.png`（浏览器下载） |
| 消息桥 | 需要后端转发 | **不新增 C# kind**，也不改两个 bat；仅「直接截图」复用 `post('quick', ':shot')` |

选这套取舍的原因：本工具交付形态是 C# 单文件 + WebView2，塞 Python 运行时会推翻它；而 Canvas 足够做透明度叠加与像素差异。

### 5.2 命令与协议

- 「直接截图」→ `post('quick', ':shot')`（走指令页既有 `quick` 通道，输出在反馈表）；截图落 `桌面\logcat\<日期>\screencap\`，**不会自动填进对比框**，需手动「选择…」。
- 「后屏截图」→ 取投屏页后排屏格子（槽 2）`<img id="cast-img-2">` 的当前 `src` 作预览（`uiShot('rear')`）。该帧来自 `http://127.0.0.1:<port>/live/2`，**Canvas 读像素会被浏览器按跨域拒绝**，所以只用于对齐预览；正式对比要把截图存成本地文件再选。`uiCompareRun()` 已 try/catch 并给出明确提示，不会静默出错图。
- 「2016车机是否需要打开」是参考图带过来的记录项，**不参与对比运算**，本工具不驱动车机。

### 5.3 差异口径

- 取两张图**较小**的宽高为对比区域；
- 逐像素 RGB 三通道绝对差之和 > `阈值 × 3` 记一个差异像素（阈值默认 30 / 255，可填）；
- 结果图以实景图为底，命中像素偏红；选「否（只看叠加）」时不标红；
- 差异率 = 命中像素 / 对比区域像素，**不是**还原度评分，也不做结构 / 文字识别。

### 5.4 验证登记

| 改动 | 保护落点 |
|---|---|
| UI 页是 `.main` 直接子节点、页签顺序、切页可见性 | `377/_test_structure.py` |
| `uiDiffPixels()` / `uiCompareRun()` / `uiOpenResult()` 存在 | `_check_features.json` 的 `page.ui` |
| 手册 | `docs/用户使用手册.md` §9 |

---

## 6. 未确认项（上机验证，未确认前不写进规格）

| # | 项 | 验证方法 |
|---:|---|---|
| 1 | `scrcpyback` 与 `scrcpyfront` 的参数差异（日志 0 / 1 次，无命令行） | 运行时抓 `scrcpy.exe` 进程命令行 |
| 2 | 「日志配置」是否有独立 Activity | 车机上打开日志设置页，用 `dumpsys activity activities` 看组件名 |
| 3 | 「下线配置」Activity 全路径（两份逆向文档不一致） | 点卡片看是否 `Error type 3` |
| 4 | 「抓全日志」「抓系统日志」在新型号上是否对应同一入口 | 上机点两个按钮，对比日志里的 `am start` 组件 |
| 5 | 车机内核是否支持 `tc netem`（`/system/lib/modules/` 有无 `sch_netem.ko`） | `shell "su 0 tc qdisc add dev wlan0 root netem delay 10ms"` 看回显 |
| 6 | `tcpdump` 在无 root 机型上能否直接读 `any` | 点「抓TCPdump数据」看设备原话 |

---

## 7. 附：本次日志实证的 13 条唯一 adb 命令

```
4×  shell getprop | findstr ro.oem.product.name
3×  shell ifconfig wlan0
3×  shell pm list packages
3×  shell dumpsys package com.iflytek.autofly.mediax | findstr version
3×  shell dumpsys package com.iflytek.autofly.mediaxkid | findstr version
3×  shell dumpsys package space.syncore.cockpit.soundeffect | findstr version
3×  shell dumpsys package com.gxatek.cockpit.ispace | findstr version
3×  shell dumpsys package com.gxatek.cockpit.shortcut | findstr version
3×  shell dumpsys package com.gxatek.cockpit.gallery | findstr version
1×  shell ping -c 5 www.baidu.com
1×  shell settings put system pointer_location 1
1×  shell am start -n com.gxa.car.systemlog/com.gxatek.logger.MainActivity
1×  shell am start -n com.android.engmode/com.android.engmode.ui.AssistantActivity
```

`_internal/syntest.db` 的 `path` 表另外给出 19 个产物目录键：`car_log`、`android_log`、`car_screen`、`car_video`、`car_tcpdump`、`car_crash`、`car_anr`、`longvideo`、`mediax_crash`，以及 10 个语音临时目录 —— 这是「测试岗的产物清单」，可与本工具 `$(out:xxx)` 的分类落盘对照。


---

## 6. 2026-11-15 第三轮：Apple UI 替换与 3 项交互修复

### 6.1 命令与协议：一行未改

本轮是界面换肤，加 3 个用户点名的交互缺陷修复。下表所列 10 个功能的**命令字符串、`cmds.ini` 的 `[cmd.*]` 段、
消息 kind、`post()` 签名、快捷键、ini key 全部保持原样**，第三轮没有新增或删改任何一条命令。

- 快捷指令仍然走 `post('quick', cmd)`，网络模拟表单面板的「开启」仍然折成 `stweak <延迟>ms <丢包>% <速率>kbit`；
- 投屏仍然走 `postObj({kind:'caststart', slot, id})` / `caststop` / `casttap`；
- 主屏 / 后排屏的 displayId 内建映射 `castDefaultId()` 不变；
- UI 对比页仍为纯前端 Canvas，不新增 C# kind。

### 6.2 本轮实际改动

| 层 | 改动 | 是否超出纯换肤 |
|---|---|---|
| `ui.html` `<style>` | 三套 Apple 语义令牌、字体栈、8pt 网格、组件八态 / 视图五态、三套无障碍降级 | 否 |
| `ui.html` 内联 SVG | 24 处统一 24×24 / 1.75 / `currentColor`，品牌改 Apple 单线终端 | 否 |
| `adb_Tool.ico` ×2 + SVG 源 + exe `/win32icon` | 7 尺寸新图标，四处同源 | 否（但需重编译） |
| `ui.html` 投屏渲染 / 事件 | 底部缩略条改 `/snap` 单帧、每路补停止按钮 | **是**（A9-01 / A9-02） |
| `ui.html` 文件搜索渲染 / 事件 | 点整行进入树状结构，dblclick 兼容 | **是**（A9-03） |
| `_cs/Cast.cs` | 新增 `/snap/<slot>` 单帧快照端点（短连接，`Connection: close`） | **是**（A9-01 依赖） |

> A10 的「禁止层」原则针对纯换肤；用户本轮显式要求修这 3 个 bug，按 A9 追加轮处理，
> 追加 ID、重算分母、沿用已锁定令牌，并在 `docs/RESKIN-FINAL-REPORT.md` 显式声明超出范围。

### 6.3 实现协议与未确认项（保留原口径）

- **实现协议**：所有复用的功能都先在本文件登记命令、证据等级与落点，再落到 `cmds.ini` / `ui.html`；
  不把逆向推测写成已实现。第三轮没有引入新的逆向功能。
- **未确认项**：真机（车机设备）上的 6 路投屏并发、`/snap` 端点在真实 adb 截帧压力下的表现、
  三套主题逐页截图 —— 本轮只做了无头 DOM 门禁与静态/不变量对照，**未做真机手测**，留待 QA 现场验证。

### 6.4 相关文档

`docs/UI-RESKIN-INVENTORY.md`、`docs/COVERAGE.md`、`docs/INVARIANT-DIFF.md`、
`docs/用户使用手册.md` §16、`docs/功能清单.md` §9。
