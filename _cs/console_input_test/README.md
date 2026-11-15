# 控制台输入回归测试（不需要真机）

验证一件事：**adb 卡死的时候，键盘输入还能不能上屏。**

## 为什么要这个测试

用户反馈：电脑息屏再亮屏后，工具里敲字没反应，只能关掉重开。
为了不靠"真的去睡一觉"复现，这里造一个**永远不返回的假 adb**，把工具逼到
"adb 卡死"的状态，再用 Windows 控制台 API 直接往它的输入缓冲区写按键，
然后读屏幕缓冲区看字符有没有被回显、命令有没有被执行。

## 跑法

```bat
build_fake.bat                       :: 编出 fake_adb.exe（3 秒）
mkdir t && copy ..\adb_log_export.exe t\
>> t\adb_log_export.ini echo adb=<这里的绝对路径>\fake_adb.exe
>> t\adb_log_export.ini echo timeout_ms=2500
>> t\adb_log_export.ini echo probe_ms=2500
>> t\adb_log_export.ini echo serial=
python drive_console.py t\adb_log_export.exe
```

期望输出：

```
[结果] 卡死被检测到并自动急救: YES
[结果] 敲字回显: YES (0.05s)
[结果] 命令被执行: YES (0.02s)
总体: PASS
```

## 原理

1. `CREATE_NEW_CONSOLE` 启动被测程序，它有自己的控制台窗口
2. 本进程 `FreeConsole` → `AttachConsole(pid)`
3. `WriteConsoleInputW` 写 KEY_EVENT_RECORD（按下 + 抬起）
4. `ReadConsoleOutputCharacterW` 读屏幕文本，判断有没有回显

不抢焦点、不碰真键盘，可以在自动化里跑。

## 注意

- 64 位 Python 必须给 `AttachConsole` / `CreateFileW` 声明 `argtypes`，
  否则句柄会被截断，`AttachConsole` 直接返回 0（错误 6）。
- 被测程序第一次跑可能要等 `adb` 超时（这里给了 `timeout_ms=2500`），
  `drive_console.py` 会先等提示符出现。

## 三个脚本各管什么

| 脚本 | 验什么 |
|---|---|
| `drive_console.py` | 假 adb 卡死 → 能否被检测/急救、敲字能否上屏、命令能否执行 |
| `test_input_features.py` | 键盘回显 / 退格 / `Ctrl+V` 粘贴 / 多行只取首行 / 回车执行 |
| `check_mouse_mode.py` | 控制台输入模式里 QuickEdit 到底开没开（= 滚轮上滑 / 拖选复制 / 右键粘贴） |

```bat
python drive_console.py ..\..\adb_log_export.exe
python test_input_features.py ..\..\adb_log_export.exe
python check_mouse_mode.py ..\..\adb_log_export.exe
```

`check_mouse_mode.py` 期望看到：

```
控制台输入模式 = 0x01F6
  QuickEdit  (滚轮上滑 / 拖选复制 / 右键粘贴) : ON
  扩展标志位 (QuickEdit 生效的前提)          : ON
总体: PASS
```

把 ini 里的 `quick_edit` 改成 `0` 再跑，QuickEdit 会变成 OFF —— 这是反证用例，
用来确认这个开关真的生效，不是"看起来像开了"。
