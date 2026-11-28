# D18 全屏后窗口仍溢出屏幕（被任务栏遮住）· 记录

> 2026-11-28 15:25 · 用户截图确认 · **仅记录，未改代码**

## 现象

最大化后窗口底部延伸到任务栏下方，最底部那行「输出 / 刷新」被任务栏压住一半，右侧时间戳也被截。

- 窗口宽度：正常占满
- 窗口高度：**超出工作区**（不是屏幕，是工作区）
- 表现：底部内容条被遮，滚动条末端不可见

## 与已修问题的关系

今天修过 **D2 / D13**，思路是"最大化时把窗口约束到 `Screen.WorkingArea`"：

```
D2  全屏遮住底部输出条      → EnsureInsideWorkingArea()
D13 任务栏收起/展开后越界    → WM_SETTINGCHANGE(TraySettings) + 250ms 防抖
```

D13 只在**任务栏状态变化**时纠正。截图这次是**一开始最大化就已经溢出**，
说明纠正没在"首次最大化"这一刻生效。

## 三个可能的原因（按可能性排序）

### ① `MaximizedBounds` 设置时机太晚

现有逻辑在 `EnsureInsideWorkingArea()` 里才 `MaximizedBounds = wa`。
但 `MaximizedBounds` 必须在**该次最大化之前**设好，否则本次最大化仍按
屏幕全尺寸（`Screen.Bounds`）计算，任务栏高度被吃掉 → 底部越界。

首次最大化时，如果 `MaximizedBounds` 还是默认值，就会复现这次的现象。

### ② 自绘窗口 + 无边框，系统不帮我们扣任务栏

有边框窗口最大化时，Windows 会自动用工作区。
我们 `FormBorderStyle = None` 且自绘标题栏，系统不再接管尺寸，
**必须自己扣掉 `WorkingArea`**——一旦某条路径漏了，就是现在这样。

### ③ `_fixingMax` 重入锁把纠正挡掉了

`EnsureInsideWorkingArea` 里有：

```csharp
if (_fixingMax) return;
```

如果最大化在 `_fixingMax = true` 的窗口期内发生（例如从 `Normal → Maximized`
的切换过程中又触发一次 `Resize`），那次纠正会被直接跳过，
且没有"稍后再试"的兜底。

## 复现步骤

```
1. 打开工具，确认窗口未最大化
2. 点标题栏最大化（或双击标题栏）
3. 观察窗口底部：最底一行是否被任务栏压住
4. 再取消最大化、重新最大化一次，看是否第二次正常
   （如果第二次正常 → 强烈指向原因 ①：第一次没设好 MaximizedBounds）
```

## 建议修法（后续实施，本轮不动）

```csharp
// ① 在任何进入最大化的入口之前先设边界
protected override void OnResize(EventArgs e)
{
    if (WindowState == FormWindowState.Maximized)
    {
        var wa = Screen.FromControl(this).WorkingArea;
        if (MaximizedBounds != wa)
        {
            MaximizedBounds = wa;
            // 设完需要重新应用一次，否则本次最大化仍是旧边界
            WindowState = FormWindowState.Normal;
            WindowState = FormWindowState.Maximized;
        }
    }
    base.OnResize(e);
}

// ② _fixingMax 命中时不要"丢掉这次纠正"，改为排队重试一次
if (_fixingMax) { BeginInvoke((Action)(() => EnsureInsideWorkingArea(false))); return; }

// ③ 首次启动若记忆的是最大化状态，先设 MaximizedBounds 再进最大化
```

## 验收标准

```
□ 首次最大化：底部「输出/刷新」整行可见，不被任务栏压住
□ 任务栏收起 → 展开：仍不越界（D13 已覆盖，回归验证）
□ 双屏切换（主/副）：最大化后落在各自工作区内
□ 三档窗口宽度（1280/1100/900）都不出现横向滚动
```

## 备注

D13 的 `WM_SETTINGCHANGE` 只能解决"任务栏变化后的纠正"，
解决不了"一开始最大化就超界"。两者要一起看，不能因为 D13 修过就认为这条已闭环。
