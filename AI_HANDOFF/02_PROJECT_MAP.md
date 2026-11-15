# 02 · 项目地图（AI 上手用，改代码前必读）

> 目的：让你在 10 分钟内知道「一个点击从界面到 adb 走了哪条路」「要改的东西在哪一层」。
> 不确定时以代码为准，本文只给路标，不给结论。

---

## 1. 一句话架构

```
ui.html（界面 + 全部前端逻辑，单文件 5479 行）
   │  window.chrome.webview.postMessage({kind, ...})      ← 前端 → 后端
   ▼
GuiWeb.cs（WebView2 窗口 + 消息桥 + 后台线程调度）
   │  PostWebMessageAsJson({kind, ...})                   ← 后端 → 前端
   ▼
能力层（纯 C#，与界面无关）：Adb / FileBrowser / Cast / Ffmpeg / Scrcpy / TaskCmds / PkgVer
   ▼
adb.exe / 车机 shell / 本地文件系统
```

**同一个 `_cs` 目录编出两个程序**：

| 产物 | 入口 | 编译脚本 | 用途 |
|---|---|---|---|
| `adb_log_gui\adb_Tool.exe` | `GuiEntry.Main` | `adb_log_gui\build_gui.bat` | GUI（当前重点，1.41 MB，含内嵌资源） |
| `adb_log_export.exe` | `App.Main` | `_cs\build.bat` | 命令行版（能力最全，`-selftest` 489 条断言） |

> 两个 exe **共用同一批 .cs**。改 `TaskCmds.cs` 会同时影响 GUI 的 `:` 命令和 CLI。
> 新增 `.cs` 必须同时加进两个 bat，否则 `_check_build_list.js` 会报错（有人漏加过，结果编译"成功"但那文件没参与编译）。

---

## 2. 文件职责（只列你改代码会碰到的）

### 前端

| 文件 | 说明 |
|---|---|
| `adb_log_gui\webview2\ui.html` | **全部界面**：HTML + CSS + JS 内联。页签：终端 / 快捷指令 / APK / 投屏 / 文件 / 无线。改界面只改这一个文件 |
| `adb_log_gui\webview2\*.dll` | WebView2 SDK（编译要引用，运行要加载） |

### 后端（`_cs\`，33 个 .cs，按重要性）

| 文件 | 行数 | 负责 |
|---|---|---|
| `GuiWeb.cs` | 2580 | GUI 窗口、消息分发、后台线程、状态推送（**改协议先看这里**） |
| `GuiEntry.cs` | 195 | 入口：DPI、异常兜底、AssemblyResolve、定位 ui.html |
| `Embed.cs` | 300 | 单 exe：内嵌资源 → 本地文件（外置优先） |
| `Prefix.cs` | 1012 | `:` 命令分派（`:car` `:rec` `:ffmpeg` `:sysnight` …） |
| `TaskCmds.cs` | 1254 | 采集导出：截图 / 截帧录屏 / 拉日志 / 前台包 |
| `FileBrowser.cs` | 992 | 文件管理：树、复制（流式）、搜索、增删改 |
| `Cast.cs` | 724 | 投屏：screencap 逐帧 + 本地 HTTP multipart（**不用 ffmpeg**） |
| `Ffmpeg.cs` | 451 | 录屏编码器：四级查找 + `-version` 校验 + 写回 ini |
| `Scrcpy.cs` | 364 | 外挂 scrcpy：探针 + 独立窗口 + 降级 |
| `Render.cs` | 1753 | 输出渲染 + **CLI 自检 489 条断言**（纯函数优先放这里） |
| `CmdRegistry.cs` | — | `cmds.ini` 自定义命令（`$1..$9` 模板） |
| `Common.cs` / `Env.cs` | — | 字符串/路径工具、环境探测 |
| `GuiSelfCheck.cs` | — | GUI 自检（42 条，不开窗口布局断言） |

### 测试与交付

| 路径 | 说明 |
|---|---|
| `verify_all.py` | **总入口**：16 项检查，任一失败退出码非 0 |
| `377\_test_*.py` | 11 个 DOM 套件（无头 Edge，把 ui.html 读进来注入断言脚本，dump DOM 判 PASS/FAIL） |
| `377\_check_ui.js` | ui.html 静态自检（元素 id、函数存在性等） |
| `_check_build_list.js` | 每个 .cs 是否都在两个 bat 里 |
| `_check_features.js` + `_check_features.json` | 21 项功能的「代码落点」机检（防功能被删） |
| `release.py` | 编译 → 跑 verify_all → 出 3 个包 + 3 个 zip |
| `make_handoff.py` | 重新生成 AI 交接包（本目录） |

---

## 3. 消息协议速查（前后端唯一契约）

前端发 → `GuiWeb.OnWebMessage` 的 `switch`；后端回 → `PostWebMessageAsJson`。

| kind | 方向 | 主要字段 | 作用 |
|---|---|---|---|
| `cmd` | → | `text` | 执行一条命令（走 `App.Dispatch`，与 CLI 同一套） |
| `stop` | → | `slot` | 停掉某槽正在跑的命令 |
| `ready` / `status` | ← | `dev,online,soc,res,rooted,dir,msg` | 设备状态（**文件页靠 online 跃变刷新设备树**） |
| `echo` / `begin` / `end` | ← | `slot,ok,ms,feed` | 命令执行生命周期 |
| `apklist/apkver/apkquery/apkact/apkadd/apkdel/apkfront/apkcmd` | ↔ | `pkg,path…` | APK 管理 |
| `castlist/caststart/caststop/casttap/castrec` | ↔ | `slot,id,x,y` | 投屏 |
| `castdisplays/caststat` | ← | `port,items[],on,frames,id,err` | 屏位与状态 |
| `fslist` | ↔ | `side,path,parent,items[],err` | 目录列表（树节点懒加载） |
| `fssearch` / `fssearchdone` | ↔ | `side,root,q,seq,items[],truncated,ms` | 搜索（`seq` 用来丢过期回包） |
| `fssearchcancel` | → | — | 取消搜索（独立标志，别复用文件传输的 `FS_CANCEL`） |
| `fscopy/fscancel/fsop/fsdone/fsprog` | ↔ | `dir,dst,src,op,name,bytes,bytesTotal` | 文件传输（单文件走字节级流式） |
| `ffmpegstat/ffmpegauto/ffmpegpick/ffmpegset` | ↔ | `ok,path,version,source,err,req` | 录屏编码器找/选/验 |
| `scrcpystat/scrcpyauto/scrcpypick/scrcpyset/scrcpyopen` | ↔ | `ok,path,version,id,slot,msg` | 外挂 scrcpy |
| `root`/`rootprobe`/`rootdone` | ↔ | `elevate,rooted` | root 状态 |
| `wadb` | ↔ | `act,host` | 无线 adb |
| `theme`/`themeget` | ↔ | `name` | 主题 |

**加新协议的固定套路**：
1. `ui.html` 里 `postObj({kind:'xxx', ...})`；
2. `GuiWeb.cs` 的 switch 加 `case "xxx":`（要 IO 就开后台线程，回到 UI 线程再 push）；
3. 回包 `PostWebMessageAsJson("{...}")`，字段名与前端读取一致；
4. `ui.html` 的 `onMessage` 加 `case 'xxx':`；
5. 在 `377/_test_*.py` 里用 `SENT`/`last('xxx')` 断言"发了什么"、"回包渲染成什么"。

---

## 4. 前端代码组织（ui.html 内部）

```
<style>   主题变量(--accent/--ok/--err/--text-dim…) + 各页样式
<body>    #topbar / .main > #page-cmd #page-quick #page-apk #page-cast #page-file #page-wireless
          #feedback（输出区，属于 #page-quick）
<script>  状态变量 → 渲染函数 → 交互函数 → onMessage 分发
```

关键的几条约定：

- `#page-*` 必须是 `.main` 的**直接子节点**（插错父容器会整页空白，出过一次事故）；
- 输出区用 `collapsed` 类控制，**任何命令都不自动展开**；
- 投屏的 `<img src="/live/N">` 是 multipart 长连接，**不能用 `display:none` 隐藏**（流会挂起），要浮层盖住；
- 文件页状态是 `_fs[side] = {root, nodes{}, sel{}, search{}}`，节点 key 一律过 `fsNorm()`（尾部斜杠差异曾导致"永远加载中"）；
- 渲染统一走 `renderFs(side)`：搜索态渲染平铺结果，否则渲染树。

---

## 5. 命令速查（改完必跑）

```bat
:: 只编 GUI（最快，几十秒）
cd adb_log_gui && cmd /c "set NO_PAUSE=1 && build_gui.bat"

:: 只编 CLI（自检需要）
cd _cs && cmd /c "build.bat < nul"

:: 全量检查（16 项）
python verify_all.py
python verify_all.py --fast      :: 跳过 GUI 自检，快一点

:: 单个套件
python 377\_test_file_ui.py
python 377\_test_fs_search.py

:: CLI / GUI 自检
adb_log_export.exe -selftest
adb_log_gui\dist\adb_Tool.exe --selfcheck

:: 出包（含全量检查，不绿就拒绝打包）
python release.py
python release.py --no-build     :: 只重打包（改完 UI 想快速出 zip）
```

---

## 6. 单文件版是怎么做的（改资源必看）

`adb_Tool.exe` 里有 6 个内嵌资源（`build_gui.bat` 的 `/resource:` 段）：

| 资源名 | 内容 | 运行时怎么用 |
|---|---|---|
| `adb.ui.html` | 界面 | 外置优先；没有就释放到 `%LOCALAPPDATA%\adb_Tool\ui\ui.html` |
| `adb.WebView2.Core.dll` / `adb.WebView2.WinForms.dll` | 托管 SDK | `AssemblyResolve` 内存加载 |
| `adb.WebView2Loader.dll` | 原生加载器 | 释放到 `%LOCALAPPDATA%\adb_Tool\native\` + `SetDllDirectory` |
| `adb.default.ini` / `adb.default.cmds.ini` | 默认配置 | **缺失时**才写出来，已有绝不覆盖 |

**外置优先**：exe 同级有同名文件就用外部的。所以改界面可以先改 `dist\webview2\ui.html` 立即看效果，不用重编译。
新增外部资源时，`build_gui.bat` 加 `/resource:` + `Embed.cs` 加常量，两处都不能漏。

---

## 7. 纯函数与断言放哪

真机不一定在手边，所以**判定逻辑必须抽成纯函数**，然后进 `Render.cs` 的自检：

| 纯函数 | 断言覆盖 |
|---|---|
| `Ffmpeg.ParseVersion` / `Candidates` | 四级查找顺序、版本解析、坏文件拒绝 |
| `Scrcpy.ParseVersion` | 版本解析 |
| `FsParseLsLine` / `FsParseLsOutput` | `ls -la` 解析 |
| `JsonUnescape` | Windows 路径反转义（事故复现） |
| `castMapPoint` | 投屏点击坐标换算 |
| `NormPath` | 设备路径归一化 |

新增一个"容易看走眼"的判定时，先写纯函数 + 断言，再接到实际路径上。
