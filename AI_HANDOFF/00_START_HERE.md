# 00 · 开始这里（换机器 / 换 AI 的第一份文档）

> 这份文档解决一件事：**把你现在这台机器上的项目，原样搬到另一台机器，并让它那里的 AI 在半小时内能独立改代码、能跑测试、能出包。**
>
> 读的顺序：`00`（本文）→ `03`（验收排障）→ `01`（把提示词贴给 AI）→ `02`（项目地图，AI 自己会读）。

---

## 1. 这个包是什么

`AI交接包_*.zip` = **完整源码 + 测试 + 文档 + 给 AI 的提示词**，不含任何编译产物和第三方大文件。

| 里面有 | 说明 |
|---|---|
| `_cs/*.cs`（33 个） | C# 全部源码（CLI 与 GUI 共用） |
| `adb_log_gui/` | GUI 编译脚本、`webview2/ui.html`（界面，5479 行）、WebView2 SDK dll、两个 ini |
| `377/` | 14 个 Python/JS 测试套件（无头 Edge 跑 DOM 断言） |
| `docs/` | 用户手册、项目规则、功能清单、AI 协作指南 |
| `.workbuddy/memory/` | 项目记忆：每天踩的坑与决策（**AI 最该先读这个**） |
| `AI_HANDOFF/` | 本文档 + 提示词 + 自检脚本 + 清单 |

**刻意没打进去**（换机器重建即可，占 200MB+）：

- `ffmpeg.exe`（105MB，录屏编码器，可后补 / 指向用户自己的）
- `adb_log_gui/dist*`、`release/`、`*.exe`（编译产物）
- `syntest_rebuild/`、`SynTestLite*.exe`（另一个子项目 SynTestLite，与本工具无关）
- `377/377/`（19MB 车机日志样本）

---

## 2. 前置环境（缺一项就跑不通）

| 工具 | 要求 | 用途 | 检查命令 |
|---|---|---|---|
| Windows | 10 / 11，x64 | 只能在 Windows 跑 | — |
| .NET Framework | 4.x（系统自带） | 编译器 `csc.exe` | `dir C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe` |
| WebView2 Runtime | Evergreen（Win11 自带，Win10 可能没装） | 界面内核 | 装 `MicrosoftEdgeWebview2Setup.exe` |
| Microsoft Edge | 任意新版 | 无头跑 DOM 测试 | 打开 Edge 能启动即可 |
| Python | 3.9+ | 测试 / 打包脚本 | `python --version` |
| Node.js | 18+ | 只用于静态检查（编译列表 / 功能清单 / ui.html 自检） | `node --version` |
| adb | 任意版本，在 PATH 或 ini 里配 | 连车机 | `adb devices` |

可选（不影响编译和测试，只影响功能）：`ffmpeg.exe`（截帧录屏）、`scrcpy.exe`（流畅投屏通道）。

> 一键体检：`python AI_HANDOFF\verify_handoff.py`
> 它会逐项检查上面这些 + 校验文件完整性，缺什么直接告诉你。

---

## 3. 三步跑起来

```bat
:: ① 解压到一个「可写」目录（不要放 C:\Program Files，程序要在旁边写 ini 和日志）
D:\work\adb_Tool\

:: ② 环境自检（第一次一定要跑）
python AI_HANDOFF\verify_handoff.py

:: ③ 先编 CLI（verify_all 的「CLI 自检」需要 adb_log_export.exe）
cd _cs && build.bat
::    自动化调用时用：cmd /c "build.bat < nul"

:: ④ 编 GUI + 出包（release.py 内部会先编 GUI、再跑全量检查，全绿才出 zip）
cd .. && python release.py
```

> **解压工具很重要**：用资源管理器 / 7-Zip / WinRAR。
> **别用 Git Bash 的 `unzip`** —— 它不认 zip 的 UTF-8 标记，会把 `docs\` 下的中文文件名解成
> `ÓÃ»§Ê¹ÓÃÊÖ²á.md` 这种乱码，之后所有按路径找文件的检查都会报"文件缺失"（看起来像包坏了）。
> 已经解错了：删掉重解，或 `python -c "import zipfile;zipfile.ZipFile(r'包.zip').extractall('.')"`。
> `verify_handoff.py` 会主动识别这种乱码并告诉你原因。

`release.py` 正常结束时会打印四个交付物：

```
dist\                  本地完整包（含 ffmpeg，可录屏）
dist_min\              最小包（不含 ffmpeg）
dist_single\           单文件版（只有一个 exe，资源全内嵌）
release\*.zip          三个可分享的压缩包
```

只想快速验证「代码还能编过」时：

```bat
cd adb_log_gui
cmd /c "set NO_PAUSE=1 && build_gui.bat"
```

`build_gui.bat` 末尾有 `pause`，自动化调用必须带 `NO_PAUSE=1`，否则会一直挂在那里等按键（这个坑真发生过：一次失败构建挂了 55 分钟）。

---

## 4. 五分钟验收（照这个顺序点）

| # | 动作 | 通过标准 |
|---|---|---|
| 1 | `python verify_all.py` | 末尾 `合计 16 项，失败 0 项` |
| 2 | 双击 `adb_log_gui\dist\adb_Tool.exe` | 出现深色界面，左上角有黑猫加载动画，随后消失 |
| 3 | 插车机 USB，车机选「一律允许」 | 顶栏出现设备号 + SOC + 分辨率，`root` 胶囊变绿（或红=可点提权） |
| 4 | 终端页输入 `:car` | 输出九项车机信息 |
| 5 | 投屏页点「刷新屏位」→ 选屏 → 开启 | 格子出画面（约 3fps 属正常）；顶部 ffmpeg/scrcpy 芯片显示状态 |
| 6 | 文件页：左栏搜个本地文件名；右栏搜 `log` | 左侧出本地结果、右侧出设备结果；双击结果能跳回树 |
| 7 | 单文件版：把 `dist_single\adb_Tool.exe` 单独拷到空目录双击 | 能启动，并在旁边自动生成两个 ini |

第 7 步是验收「内嵌资源」是否正常的关键：空目录里没有任何 dll / ui.html / ini，程序仍要能跑起来。

---

## 5. 把这个项目交给那台机器上的 AI

打开 `AI_HANDOFF\01_AI_PROMPT.md`，把 **第 1 节「短版提示词」** 整段复制，替换掉里面的路径，作为新会话的第一条消息发过去。之后：

- 要改功能 → 用第 3 节的「新功能模板」；
- 要改交互/文案 → 用第 4 节；
- 要修 bug → 用第 5 节（要求找根因，不许改表象）；
- 每次收尾 → 用第 6 节（要求跑全量检查 + 出包 + 给数字）。

**为什么要给提示词而不是让它自己摸**：这个项目有一批「违反就返工」的硬约束（C# 5.0、bat 只能 ASCII、页面必须挂在 `.main` 下、不能用 `display:none` 隐藏投屏 `<img>`……）。不写进提示词，新 AI 一定会踩，而且踩了之后表现是「白屏 / 编译过但功能没生效」这种极难查的形态。

---

## 6. 两台机器之间怎么同步后续改动

推荐顺序（从省事到稳妥）：

1. **只同步源码**：改完在旧机器 `python AI_HANDOFF\make_manifest.py` 重新出 zip，拷过去覆盖；
2. **用 git**（推荐长期）：`git init` → 把本目录提交 → 两台机器 `push/pull`。`.gitignore` 已按「只留源码」写好；
3. **别手工拷 exe**：可执行文件是编译产物，跨机器拷容易遇到「版本不一致但看不出来」，一律重新编译。

> 如果两台机器都要编译，注意 `adb_log_gui\adb_Tool.exe` 会被正在运行的进程锁住。
> 构建脚本会自动改走 `adb_Tool_new.exe` 并把新 exe 送进 `dist\`（见 `03` 排障第 1 条）。

---

## 7. 目录里哪些文件是「活的」

改代码时只需要关心这些，其它都是产物或样本：

```
_cs/                        ← 后端 + CLI（33 个 .cs，改这里）
adb_log_gui/webview2/ui.html← 前端全部（HTML+CSS+JS 单文件，改这里）
adb_log_gui/build_gui.bat   ← GUI 编译（新增 .cs 必须加进这里的列表）
_cs/build.bat               ← CLI 编译（同上，两个都要加）
377/_test_*.py              ← 测试（改交互必须同步改断言）
verify_all.py               ← 全量检查总入口（release.py 会调用它）
docs/用户使用手册.md          ← 用户文档（改交互必须同步）
.workbuddy/memory/*.md      ← 项目记忆（收尾时追加一段）
```

---

## 8. 一句话总结

**解压 → `verify_handoff.py` 体检 → `release.py` 出包 → 把那 16 项检查跑绿 → 把 `01` 里的提示词喂给 AI。**
这四步走完，那台机器上的 AI 就和你现在这台站在同一条起跑线上了。
