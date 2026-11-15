# STATE.md — 交接状态（谁接手都先看这里）

> 规则：**只写"现在是什么状态"和"下一步做什么"**，过程与原因写进 `docs/`。
> 每次收工更新「最后更新」「本轮做了什么」「下一步」，并保证「验收基线」是最新真实数字。

---

## 最后更新

2026-11-16 02:50 · A21（启动层图标去蓝 + 三白色点去蓝 + 专项运行时测试）已落地并过门禁

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

**能。** 两个形态都编译通过，26 项门禁 0 失败。

| 检查 | 命令 | 当前结果 |
|---|---|---|
| 全量门禁 | `python verify_all.py` | **26 项 / 0 失败** |
| A17 落点 | `python _v17_checks.py` | 64 / 64 |
| A16 落点 | `python _v16_checks.py` | 78 / 78 |
| A15 落点 | `python _v15_checks.py` | 54 / 54 |
| 功能清单 | `node _check_features.js` | 52 项通过 |
| 功能不变量 | `python _gate_invariants.py` | 44 项 / 0 失败 |
| 窗口原生 | `python _smoke_win.py` | 13 / 13 |
| GUI 自检 | `adb_Tool.exe -guiSelfCheck`（由 verify_all 调用） | 46 条断言 0 失败 |
| CLI 自检 | `adb_log_export.exe -selftest` | 489 条断言 0 失败 |

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

1. **清 Windows 图标缓存**（dock 栏还显示旧蓝色云朵时，人工操作一次）：
   - 删除任务栏 pin → 资源管理器重启（`taskkill /f /im explorer.exe && start explorer.exe`）→ 重新 pin
   - 或删除 `%LOCALAPPDATA%\Microsoft\Windows\Explorer\iconcache_*.db` 后重启资源管理器
2. **真机验收**（必须人工）：启动动画图标是否不再显蓝；设置面板三白点是否中性灰白；投屏默认小屏、点「⤢」扩全屏、底部缩略条切换。
3. 出包：`python release.py`（会自动重跑 27 项门禁），组装 `Desktop\Adb_Tool_成品_V21_<时间戳>`。

---

## 环境（别人接手要照这个来）

```bash
python --version     # 3.x 即可，只用到标准库
node --version       # 只给 _check_features.js / 377 用
git --version        # >= 2.28
# C# 编译器：C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe（系统自带，无需安装 SDK）
```

- 本机用户名是中文（`C:\Users\李亦`），**不要在 .bat 里拼含中文的路径**；脚本里一律用 `%~dp0`。
- Git Bash 里跑 .bat 要 `cmd //c "..."`；`build.bat` 末尾有 `pause`，必须 `< /dev/null`。
- 编译输出是 GBK，管道里要看中文得 `| iconv -f GBK -t UTF-8`。

---

## 已知限制（不要当 bug 报）

- **内置投屏通道 1~5fps**，无线 adb 约 1.5fps。天花板在"每帧从设备搬一张整图"，不在编码。
  要流畅走内嵌 scrcpy（h264 原生解码）。按用户要求**不做** h264→MSE 的页内 30fps。
- **三白在浅色/护眼下必然是灰**（`#939393` / `#9C9284` / `#8E949E`）。白压到可读对比度必然是灰，这是数学问题。
- **`adb root` 不提供**（用户明确要求）。它会重启 adbd，断掉正在跑的日志与投屏。
- 副屏/HUD 不一定支持 `screencap -d`，内置通道首帧失败会直接提示改用 scrcpy。
