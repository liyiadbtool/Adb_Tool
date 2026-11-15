# STATE.md — 交接状态（谁接手都先看这里）

> 规则：**只写"现在是什么状态"和"下一步做什么"**，过程与原因写进 `docs/`。
> 每次收工更新「最后更新」「本轮做了什么」「下一步」，并保证「验收基线」是最新真实数字。

---

## 最后更新

2026-11-16 00:20 · A17（第 6 批：八条需求 + 两条追加）已落地并过门禁

---

## 现在能跑吗

**能。** 两个形态都编译通过，26 项门禁 0 失败。

| 检查 | 命令 | 当前结果 |
|---|---|---|
| 全量门禁 | `python verify_all.py` | **26 项 / 0 失败** |
| A17 落点 | `python _v17_checks.py` | 63 / 63 |
| A16 落点 | `python _v16_checks.py` | 78 / 78 |
| A15 落点 | `python _v15_checks.py` | 54 / 54 |
| 功能清单 | `node _check_features.js` | 52 项通过 |
| 窗口原生 | `python _smoke_win.py` | 13 / 13 |
| GUI 自检 | `adb_Tool.exe -guiSelfCheck`（由 verify_all 调用） | 46 条断言 0 失败 |
| CLI 自检 | `adb_log_export.exe -selftest` | 489 条断言 0 失败 |

---

## 本轮做了什么（A17）

| # | 需求 | 落点 |
|---|---|---|
| 1 | 强调色未记忆 | 白名单收口成 `_cs/Prefix.cs` 的 `ACCENTS`（单一来源）；`SaveAccentPreference` 不再"没 ini 就 return"；页面侧另存一份 `_prefs.accent` |
| 2 | 恢复 dock 开合动效 | `_v17.css` `.v17-in/.v17-out`（只动 transform）；C# `PlayOutThen()` 播 130ms 再最小化/关闭 |
| 3 | icon 改黑白灰 + 黑底 | `_icon_v2.py`（底 `#2E2E2E→#050505`，严格 R=G=B）；页面内联图形与 ico 同源（`#appmark-glyph`），启动层与标题栏共用 |
| 4 | 浅色窗口边界 | `_v17.css` §2：实边 0.72 + 内高光 + 6px 内阴影 |
| 5 | 直角改圆角 | `_v17.css` §1：侧栏/终端页/输入行各自成卡片（8px 内缩 + 12px 圆角） |
| 6 | Edge 主题设置调研 | `docs/参考-Edge主题设置与同类实现.md`；落地「中性色」分组标签 |
| 7 | 关闭要两次 | 先 `Hide()` 立即消失 → `BeginInvoke(Close)` 跑清理 → 看门狗 2.5s 硬退 |
| 8 | 启动层高斯模糊渐变 + 图标跟随强调色 | `_v17.css` §4（`--splash-g0/1/2` + blur 光晕）；C# `SplashPaint` 同步 |
| 追加1 | scrcpy 内嵌到应用内 | `SetParent` 把 scrcpy 窗口塞进 `_castHost` Panel；页面按比例报区域；进投屏页默认拉起、模式记忆 |
| 追加2 | 换任务栏图标 + 去标题前缀 | `Text = "Adb_Tool"`；`TrySetCatIcon()` 读同目录 `adb_Tool.ico` |

---

## 下一步（按优先级）

1. **真机验收**（必须人工）：内嵌 scrcpy 在有设备时是否真的"可点击、跟手"；关闭是否一次就退；浅色下边界是否够清楚。
   命令：`adb_log_gui\dist\adb_Tool.exe`，投屏页看是否自动接管。
2. **Edge 调研里的建议 1**（低风险）：色点 `title` 补对比度数字，数值从 `_gen_accent.py` 输出。
3. **Edge 调研里的建议 2/3**（中风险，单独一轮）：主题缩略预览卡；强调色按设备序列号记忆。
4. 出包：`python release.py` → 组装 `Desktop\Adb_Tool_成品_V17_<时间戳>`（含交付说明 + `docs/shots/a17-*.png`）。

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
