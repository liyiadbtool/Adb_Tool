# STATE.md — 交接状态（谁接手都先看这里）

> 规则：**只写"现在是什么状态"和"下一步做什么"**，过程与原因写进 `docs/`。
> 每次收工更新「最后更新」「本轮做了什么」「下一步」，并保证「验收基线」是最新真实数字。

---

## 最后更新

2026-11-16 01:58 · A19（四条：投屏全屏交互 / 图标跟色 / 主题图标恢复 / 交接总纲）已落地并过门禁

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

## 本轮做了什么（A19）

| # | 需求 | 落点 |
|---|---|---|
| 1 | 投屏全屏交互修复 | scrcpy 内嵌默认小屏；点「⤢」扩全屏、底部缩略条切换。`_v17.js` hook `castEnterFull`/`castExitFull` 重报 Panel 区域；`_cs/GuiWeb.cs` `ScrcpyEmbedPlace` 识别退化区域（r<=l 或 b<=t）隐藏 Panel |
| 2 | 图标跟色 + 消除交接跳变 | `_v17.css` `.appmark{ color:var(--accent) }` 统一跟色，删旧 `.splash .appmark` 覆盖；标题栏与启动层图标颜色一致，不再"蓝跳白" |
| 3 | 主题图标恢复 + 文字居中 | `_v17.css` `.theme-card` 恢复图标+文字横排居中，迷你预览卡改绝对定位装饰（不占图标位）；`ui.html` `buildThemeSeg` 图标包 `.tc-ic` |
| 4 | 交接总纲文档 | 产出 `docs/AI开发交接总纲.md`（喂给其它设备 AI 的全量规则/红线/历史经验/技术/测试/UI 约定） |

门禁状态：26 项 0 失败（A17 落点 64/64、功能清单 52/52）。

---

## 下一步（按优先级）

1. **GitHub 已就位**（用户已建仓库）：`git push -u origin main` 首次推送即可。
2. **真机验收**（必须人工）：投屏全屏/切换交互；启动图标是否跟色且无跳变；主题卡图标与居中是否恢复。
3. 出包：`python release.py` → 组装 `Desktop\Adb_Tool_成品_V19_<时间戳>`。

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
