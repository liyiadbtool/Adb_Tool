# STATE.md — 交接状态（谁接手都先看这里）

> 规则：**只写"现在是什么状态"和"下一步做什么"**，过程与原因写进 `docs/`。
> 每次收工更新「最后更新」「本轮做了什么」「下一步」，并保证「验收基线」是最新真实数字。

---

## 最后更新

2026-11-16 01:15 · A18（第 7 批：七条反馈 + 两件收尾）已落地并过门禁

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

## 本轮做了什么（A18）

| # | 需求 | 落点 |
|---|---|---|
| 1 | 验证 SSH + 接手指南 | SSH 公钥已生效；GitHub 仓库 `liyiadbtool/Adb_Tool` **还没建**（见下一步）。产出 `docs/明天到公司继续开发.md` |
| 2 | 各分屏用 scrcpy 内嵌 | 六格（主屏0/副屏4/后排1/HUD3/PHUD-B9/PHUD-C10）各自内嵌 scrcpy；删掉单屏全窗口宿主、全屏弹窗、「外部」按钮；`castToggle` 有 scrcpy 走 `v17CastEmbed(i,id)`、没有回退 `castBuiltinFallback(i)`；C# `_castHost[6]` 数组化 |
| 3 | 应用图标 | 源码/二进制已全换黑白灰（7 档 ico 全嵌入、饱和差=0）；用户看到的旧图标是 **Windows 图标缓存**，非代码问题 |
| 4 | 启动闪一帧蓝 | 根因：`data-accent="blue"` 写死，prefs 回填前先渲染默认蓝。`OnCoreReady` 里 `AddScriptToExecuteOnDocumentCreatedAsync` 首帧前就同步 theme/accent；`DrawLogo` 换成 100 视窗同源图形 |
| 5 | 精简完整版 | 成品 zip 只含运行必需 + 一份使用手册，不夹带交付说明/调研/截图（见 `docs/明天到公司继续开发.md` §七） |
| 6 | 启动更白更模糊 | 渐变提亮（`#3C3E45→#26282E→#121316`）+ 光晕 blur 56→78px + 加白雾层；C# `PaintSplashBackdrop` 同步 |
| 7 | Edge 建议落地 | 建议1 色点 hover 显对比度、建议2 主题预览卡、建议3 按设备序列号记强调色（`_prefs.accentByDevice`）、建议4 设置重排（主题→强调色→显示→字体）；建议5（自定义hex）不做 |

---

## 下一步（按优先级）

1. **在 GitHub 建仓库**（30 秒）：https://github.com/new → 名字 `Adb_Tool` → Private → 不勾初始化 → Create。然后 `git push -u origin main`。SSH key 已生效，只差仓库。
2. **真机验收**（必须人工）：六格 scrcpy 内嵌是否"可点击、跟手"；启动是否还闪蓝；强调色重启是否保持；图标（刷新缓存后）是否黑白灰。
3. **刷新图标缓存**（若还看到旧图标）：取消固定 → 重新固定，或重启资源管理器。
4. 出包：`python release.py` → 组装 `Desktop\Adb_Tool_成品_V18_<时间戳>`（精简：运行文件 + 一份交付说明，不带截图/调研文档）。

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
