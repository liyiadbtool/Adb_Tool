# 断线重连复现与验证（v7.13）

现场问题：拔线/息屏后再插上，工具"搜不到设备"，重开 exe 才好。
这套脚本用来**复现**最坏情况，并**验证**工具不会假死、且能说清原因。

## 快速验证（不需要复现故障）

```bat
:: 1) 内置自检（纯逻辑，不需要真机）
..\..\adb_log_export.exe -selftest

:: 2) 真机：正常重连
..\..\adb_log_export.exe
::   进去后敲 :rr      预期 10 秒左右，打印"已重连：<序列号>"
::   再敲 :diag        预期看到 adb 路径 / 本机几份 adb / 5037 状态 / 结论
```

SynTestLite 侧：

```bat
SynTestLite_cli.exe dev
SynTestLite_cli.exe dev rr
```

GUI 刷新链路（无头，不需要点界面）：

```bat
cd syntest_rebuild
set QT_QPA_PLATFORM=offscreen
python smoke_gui_refresh.py
```

## 复现"adb server 僵死"

```bat
:: 窗口 A —— 先停掉真服务，再占住 5037（收连接但不回话）
adb kill-server
python hang_server.py 120

:: 窗口 B —— 这时 adb devices 会一直挂着
adb_log_export.exe
::   敲 :r
```

预期（改造前的表现 / 改造后的表现）：

| | 改造前 | 改造后 |
|---|---|---|
| 界面 | 卡 30 秒以上，无提示 | 有进度提示，不假死 |
| 耗时 | 最多 150 秒（5 次 × 30 秒超时） | 25 秒内出结论 |
| 结论 | "刷新失败：5 次内设备都未上线" | **"5037 端口被 python.exe（PID xxxx）占着，不是 adb"** |
| 下一步 | 没有 | "关掉这个进程后按 :rr" |

跑完记得关掉 `hang_server.py`，否则真 adb 起不来：

```bat
adb start-server
adb devices
```

## 这套脚本钉住的几个点

1. **一次 `adb devices` 不是结论**：USB 重新枚举要 1.5~6 秒，必须给窗口。
2. **offline 要 `adb reconnect offline`**，不是直接 kill-server。
3. **空列表 ≠ 没插设备**：server 坏了也回空列表，只有重启能区分。
4. **重启后要等**：刚起来的 server 枚举 USB 时 `devices` 会阻塞，
   这时候再判"无响应"就会形成 杀→起→杀 的死循环。
5. **校验不能用 `adb version`**：它不连 server，端口上蹲着假服务也返回成功。

## 相关文件

- `_cs/Reconnect.cs` —— 状态机（`Rec.ScanOnce` / `Rec.WaitDevice` / `Rec.ResetServer` / `Rec.Diagnose`）
- `_cs/Render.cs` —— 自检里的 16 项断线重连用例
- `syntest_rebuild/adb_core.py` —— Python 侧同一套（`scan_once` / `ensure_device` / `reset_server`）
- `息屏唤醒输入失效_分析与修复_20261104.md` 第八章 —— 完整分析
