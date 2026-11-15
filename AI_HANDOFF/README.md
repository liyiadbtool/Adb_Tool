# AI_HANDOFF · 交接包索引

> 给「换到另一台机器 / 换一个 AI」用。文件名用英文是为了跨机器、跨 shell 不乱码；
> 内容全是中文。

| 文件 | 中文标题 | 什么时候看 |
|---|---|---|
| `00_START_HERE.md` | **开始这里**：解压 → 自检 → 编译 → 验收（主教程） | 第一次打开就从这个读 |
| `01_AI_PROMPT.md` | **给 AI 的提示词**：短版/长版 + 新功能/改交互/修 bug/交付 模板 | 把第一段贴给那台机器的 AI |
| `02_PROJECT_MAP.md` | **项目地图**：架构、文件职责、消息协议、命令速查 | AI 改代码前必读 |
| `03_TROUBLESHOOTING.md` | **接手验收与排障**：13 个真实故障的根因与处理 | 跑不起来 / 行为怪异时查 |
| `04_STATUS.md` | **当前状态**：基线数字、R1–R12 进度、已知限制 | 判断"还剩什么没做" |
| `verify_handoff.py` | 环境与文件自检（缺什么直接告诉你） | 解压后第一条命令 |
| `make_manifest.py` | 重新生成 `MANIFEST.json`（改了源码后跑） | 想让两台机器对齐时 |
| `MANIFEST.json` | 文件清单 + sha256（自动生成） | 由脚本读，不用手看 |

快速开始（四条命令，缺一条都会让 `verify_all` 少一项）：

```bat
python AI_HANDOFF\verify_handoff.py          :: 环境体检
cd _cs && build.bat                          :: 编 CLI（adb_log_export.exe，自检要用）
cd ..\adb_log_gui && cmd /c "set NO_PAUSE=1 && build_gui.bat"
cd .. && python verify_all.py                :: 必须 16 项 0 失败
```

> 之后出包只要一条：`python release.py`（它内部会重编 GUI 并再跑一遍全量检查）。

> **解压注意**：请用 Windows 资源管理器 / 7-Zip / WinRAR 解压。
> **不要用 Git Bash 的 `unzip`** —— 它不认 zip 里的 UTF-8 标记，会把 `docs\` 下的中文文件名
> 解成乱码（`用户使用手册.md` → `ÓÃ»§Ê¹ÓÃÊÖ²á.md`），代码找不到文件。
> 已经解错了：删掉重解；或者用 `python -c "import zipfile;zipfile.ZipFile(r'包.zip').extractall('.')"`。
