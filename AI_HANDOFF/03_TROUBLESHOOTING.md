# 03 · 接手验收与排障

> 换机器后 90% 的问题都在这张表里。先看现象，再按"根因"那一列理解，别只看"处理"。

---

## 1. 接手验收（按顺序做，每步都有明确判据）

```bat
:: 0) 环境体检（缺什么直接说）
python AI_HANDOFF\verify_handoff.py

:: 1) 编译
cd adb_log_gui && cmd /c "set NO_PAUSE=1 && build_gui.bat"

:: 2) 全量检查
cd .. && python verify_all.py
::    判据：合计 16 项，失败 0 项
```

| # | 人工验收项 | 通过标准 | 不通过的常见原因 |
|---|---|---|---|
| 3 | 双击 `dist\adb_Tool.exe` | 深色界面出现，标题栏有黑猫 | WebView2 Runtime 没装 |
| 4 | 插车机 + 车机点「一律允许」 | 顶栏显示设备号/SOC/分辨率 | adb 不在 PATH、USB 调试未开、车机弹窗没确认 |
| 5 | 终端页 `:car` | 输出九项信息 | 设备离线 / root 未提权（部分项要 root） |
| 6 | 投屏页「刷新屏位」→ 开启 | 出画面（3fps 正常） | 屏受 FLAG_SECURE 保护 → 全黑属预期 |
| 7 | 文件页左搜本地 / 右搜 `log` | 两边各自出结果，互不串 | 右侧空 → 见排障 6 |
| 8 | 单文件版拷到空目录双击 | 能启动，旁边自动生成两个 ini | 内嵌资源没编进去 → 见排障 2 |

---

## 2. 排障表

### 1) 编译报「另一个程序正在使用此文件」/ exe 换不掉

**现象**：`build_gui.bat` 打印 WARN，说 `adb_Tool.exe` 被占用，新构建留在 `adb_Tool_new.exe`。
**根因**：有个 `adb_Tool.exe` 还在跑（常见是上次没关的窗口，或崩溃后残留的幽灵进程，`taskkill`/`Stop-Process` 都杀不掉）。
**处理**：
- 构建脚本已经处理：会把新 exe 送进 `dist\`（变量 `%BIN%`），`dist\` 里的永远是新的；
- 幽灵进程只能重启机器清掉；
- **不要**为了绕过它去手工拷 exe，那正是"dist 里装旧程序"的成因（历史事故）。

### 2) 双击没反应 / 白屏 / 提示"找不到界面文件"

| 检查 | 命令 | 结论 |
|---|---|---|
| 日志里有没有 `ui.html = ...` | `type %LOCALAPPDATA%\adb_Tool\logs\gui_trace.log` | 有 → 界面文件找到了；没有 → 卡在更早的初始化 |
| 崩溃详情 | `type %LOCALAPPDATA%\adb_Tool\logs\gui_error.log` | 出现 `FileLoadException` 说明托管 dll 没加载上 |
| 内嵌资源是否在 exe 里 | exe 体积 > 1MB | 300KB 左右 = 没编进资源（检查 build_gui.bat 的 `/resource:` 段） |

**根因**：单文件版靠 `Embed.HookAssemblyResolve()`（挂在 `GuiEntry` 静态构造函数里）+ `PrepareNativeLoader()`。
任何一个提前失败，表现都是白屏或 `WebView2Loader.dll not found`。

### 3) 页面整块空白，但 exe 正常

**根因**：新增的 `#page-*` 没挂在 `.main` 直接子节点上（插到 `#feedback` 里了）。`#feedback` 是 `#page-quick` 的子节点。
**查法**：`python 377\_test_structure.py`——它有专门的父子关系断言。

### 4) 本地目录永远显示"加载中…"

**根因**：前端 `JSON.stringify` 发 `C:\\Users\\...`，后端 `GetField` 若不做反转义就会拿到双反斜杠 → `Directory.Exists` 为 false。
**现状**：已修（`App.JsonUnescape`），回包路径也必须能对上节点 key（`fsNorm` 归一化尾部斜杠）。
**查法**：`adb_log_export.exe -selftest` 里有「反转义双反斜杠」断言。

### 5) 设备侧搜索永远"没有匹配项"

**根因（真机实测）**：Android 12 / toybox 0.8.4 的 `find /sdcard ...` **一条都不返回**——`/sdcard` 是软链，toybox 默认不跟随命令行软链。
**现状**：代码里写成 `find -H`。
**自查命令**：

```bat
adb shell "find -H /sdcard -maxdepth 6 -type d -iname '*log*' | head -n 5"
:: 有输出 = 正常；无输出但 ls /sdcard 正常 = 就是这个问题
```

### 6) 设备没连上时进过文件页，右栏一直红字不恢复

**根因**：早期实现只在"首次进页"请求一次设备根目录，之后不再重试。
**现状**：`setStatus` 检测 `online` 的 false→true 跃变 → `fsOnDeviceOnline()`（400ms 防抖 + 清缓存 + 重拉）。
**验证**：拔插一次 USB，右栏应自动刷新；`377\_test_fs_search.py` 有对应断言。

### 7) 录屏失败 / 提示找不到 ffmpeg

**根因**：车机屏带 `FLAG_SECURE`，`screenrecord` 录到 0 帧；只能用"截帧 + ffmpeg 合成"，而 ffmpeg 不打进包（105MB）。
**处理**：投屏页右上「选择…」挑 `ffmpeg.exe`（会校验并写回 ini），或命令行 `:ffmpeg D:\ff\ffmpeg.exe`。
**查找顺序**：ini → 程序同级 → PATH → 常见位置（每级都跑 `-version` 验真）。

### 8) 投屏全黑

**根因**：该屏受 `FLAG_SECURE` 保护，`screencap` 拿到黑帧。这不是 bug。
**替代**：用 `:rec` 截帧录屏，或改用外挂 scrcpy（同屏仍可能受保护）。

### 9) 某个 DOM 套件/verify_all 超时

**根因**：无头 Edge 的 `--user-data-dir` 被上一个进程锁住（`%TEMP%\edgeprof_*`）。
**处理**：

```bat
rmdir /s /q %TEMP%\edgeprof_fssearch      :: 换成对应套件的名字
python 377\_test_fs_search.py
```

`verify_all.py` 对浏览器套件已经会自动重试一次；两次都超时才判失败。

### 10) 测试报 `msedge.exe` 找不到

**根因**：测试脚本要一个 Edge 可执行文件。脚本里已改成**自动查找**（`PROGRAMFILES(X86)` / `PROGRAMFILES` / `LOCALAPPDATA` + 两个默认路径 + `PATH`）。
**处理**：装 Edge，或把 `EDGE` 环境变量指向 `msedge.exe`。`verify_handoff.py` 会提前告诉你。

### 11) bat 跑起来报一堆奇怪的"不是内部或外部命令"

**根因**：`.bat` 里写了中文注释。cmd 用 OEM 代码页（GBK）解析，UTF-8 中文被拆成命令碎片。
**规则**：**bat 只写 ASCII**。中文一律放 .md 或直接输出到界面。

### 12) 改完文件，功能没变化 / 行尾变了

**根因**：用 Python 读写 `.cs`/`.bat` 时把 CRLF 转成了 LF，或改的是 `dist\` 里的副本而源码没动。
**规则**：改完 `git diff --stat` 或 `fc` 比一下；批量改文件时用 `newline=''` 保留原行尾。

### 13) 单文件版改了界面却看不到效果

**根因**：单文件版用的是 exe 内嵌的 `ui.html`，**必须重新编译**；或者 `%LOCALAPPDATA%\adb_Tool\ui\ui.html` 还是旧的。
**处理**：重编译；或把手改的 `ui.html` 放到 exe 同级 `webview2\ui.html`（外置优先，立即生效）。

---

## 3. 出问题先看这三个地方

| 位置 | 内容 |
|---|---|
| `%LOCALAPPDATA%\adb_Tool\logs\gui_trace.log` | 启动到哪一步（`进入 Main` → `GuiBoot 完成` → `ui.html = ...` → `进入消息循环`） |
| `%LOCALAPPDATA%\adb_Tool\logs\gui_error.log` | 未处理异常的完整堆栈 |
| 界面输出区 | 所有 `:` 命令的真实输出（GUI 没有控制台） |

命令行版排查更直接：`adb_log_export.exe -selftest`（489 条断言，最快的自检）。

---

## 4. 交接时最容易漏的两件事

1. **WebView2 Runtime**：Win10 不一定有。缺了表现是"窗口一闪"或纯白。装 Evergreen Runtime 即可，不需要 SDK。
2. **可写目录**：程序要在自己旁边写 `adb_log_export.ini` / `cmds.ini`。放 `C:\Program Files` 会写不进去（单文件版会静默跳过写 ini，然后用内置默认值跑，看起来"配置改了不生效"）。

---

## 5. 给 AI 的排障提示

让 AI 排障时，把这三条一起给它：

```text
1. 先要根因，不接受"可能是缓存/时序/环境问题"这种猜测。
2. 根因必须能用一个新断言复现（先红后绿），否则就是没找到根因。
3. 说明为什么之前没测出来，并补上防复发的断言。
```

这个项目三次"看着像玄学"的故障，最后都是确定的代码原因：JSON 反转义缺失、toybox `find` 软链、构建脚本判成功用错了变量。
