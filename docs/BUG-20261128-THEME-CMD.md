# 主题模式两条指令"无效"的排查记录

> 2026-11-28 15:31 · 设备 b09acfa2 实测 · **仅记录，未改代码**

## 结论先说

两条不是同一个原因：

```
自动主题模式    命令执行了，但只改了 uimode，没打开系统的"自动"开关 → 看不出变化
查询系统主题模式 读错了键，拿"自动开关"当"当前主题" → 显示的值与屏幕实际不符
```

---

## 一、设备实测数据（b09acfa2）

```
$ adb shell settings get global day_night_auto_mode
0                                   ← 自动开关：关

$ adb shell settings get secure ui_night_mode
1                                   ← 真正的主题状态存在 secure 键

$ adb shell cmd uimode night
Night mode: no                      ← 系统自称"非夜间"

$ adb shell su 0 id
uid=0(root) ...                     ← root 可用，su 0 不是障碍
```

注意 `secure ui_night_mode = 1` 与 `cmd uimode night → no` **互相矛盾**：
这台 ROM 的夜间状态存在 `secure` 里，`uimode` 命令读不到它。

---

## 二、自动主题模式（cmd: `autotheme`）

### 它实际做什么

`cmds.ini`：

```ini
[cmd.autotheme]
run = shell "su 0 cmd uimode night auto"
```

就一条：把 uimode 设成 auto。

### 为什么"无效"

```
① 只设了 uimode=auto，没有把 day_night_auto_mode 置 1
   → 系统层面仍认为"未开启自动"，没有日夜调度，行为与手动无异
② 本机 day_night_auto_mode = 0（实测），说明从来没人打开过这个开关
③ auto 只是"允许跟随"，真正切换依赖系统 UI 的定时/光照策略；
   车机通常没有这套调度 → 设了也不会变
```

**对比**：`yes` / `no` 是强制值，执行立刻生效，所以那两张卡"看起来有效"，
而 `auto` 是"交回系统决定"，系统没开调度 → 看不出任何变化。

### 建议（后续）

```ini
[cmd.autotheme]
run = shell "settings put global day_night_auto_mode 1; su 0 cmd uimode night auto"
```

并补一条"关闭自动"的反向命令，否则用户开了没法关。

---

## 三、查询系统主题模式（cmd: `:sysnight`）

### 它实际做什么

`_cs/PkgVer.cs:1008 DoSysNight()`：

```csharp
ShellCall(CUR, "settings get global day_night_auto_mode 2>&1", out o, out e);
...
if (v == "0") Console.WriteLine("日间（0）");
else if (v == "1") Console.WriteLine("夜间（1）");
else if (v == "2") Console.WriteLine("自动（2）");
```

### 为什么"无效"

**读的键不是"当前主题"**：

| 键 | 含义 | 本机值 |
|---|---|---|
| `global day_night_auto_mode` | 自动开关（0/1） | 0 |
| `secure ui_night_mode` | 当前主题（1=夜间） | 1 |

代码把 `day_night_auto_mode` 的值硬映射成 `0=日间 / 1=夜间 / 2=自动`——
但这个键**只有 0 和 1，且语义是"开关"，不是"主题"**。
于是：

```
本机 day_night_auto_mode=0  →  工具显示"日间（0）"
但 secure ui_night_mode=1   →  屏幕实际是夜间
→ 用户看到"查询结果和屏幕不一致" = "无效"
```

而且屏幕若是夜间，用户点"查询"却显示"日间"，会直接判定这个功能坏了。

### 建议（后续）

```
① 主判据改成 cmd uimode night（解析 "Night mode: yes/no/auto"）
② 辅助读 secure ui_night_mode 作为交叉验证
③ 显示时把"当前主题"与"自动开关"分开两行，别混成一个值
```

---

## 四、两条共同的一个隐患

卡片里 `cmd:'autotheme'`（不带冒号），ini 的 `usage = :autotheme`（带冒号）。
目前 `yes` / `no` 也不带冒号且能正常执行，说明调度器对裸命令名也能命中 `[cmd.*]`，
**所以不是前缀问题**——这一点已排除，避免以后误判。

---

## 五、验收标准（修完后）

```
□ 自动主题模式：点完 day_night_auto_mode 变 1，且能再关回 0
□ 查询系统主题模式：与 cmd uimode night 的输出一致
□ 手动 yes/no 仍立即生效（回归）
□ 三张卡在同一设备上连续点，结果互不串
```
