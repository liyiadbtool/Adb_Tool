# D18 全屏后窗口仍溢出屏幕（被任务栏遮住）· 记录

> 2026-11-28 15:25 · 用户截图确认 · **仅记录，未改代码**

## 触发条件（2026-11-28 15:29 用户补充，修正前一版判断）

```
① 直接最大化        → 正常，不溢出
② 最大化后「收起」（最小化）→ 从任务栏（dock）点回来 → 底部溢出、被任务栏遮住
```

所以这不是"首次最大化算错边界"，而是**最小化 → 恢复这条路径**把窗口放大了。
前一版文档里"首次最大化"的假设作废，保留在下文仅作记录。

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

## 恢复路径专属的原因（本次新增，优先级最高）

### ④ 恢复时按"屏幕全尺寸"重算，而不是工作区

无边框窗口最小化后恢复，Windows 会重新走一次 `WM_GETMINMAXINFO` /
`WM_WINDOWPOSCHANGING`。如果此时 `MaximizedBounds` 已被重置或从未持久生效，
恢复出来的矩形是 `Screen.Bounds`（含任务栏区域）→ 底部压到任务栏下面。

**特征**：窗口内部布局没有错乱，只是整体往下多出一截（截图正是这样）。

### ⑤ 恢复时用了 `RestoreBounds`（最小化前的矩形）

`RestoreBounds` 记录的是最后一次 Normal 状态的位置。如果最小化发生在
"最大化"状态，部分路径会把 `RestoreBounds` 当成目标矩形恢复 →
得到一个既是最大化尺寸、又没扣任务栏的混合值。

### ⑥ `WM_SETTINGCHANGE` 的 250ms 防抖窗口正好盖住恢复时机

D13 的实现是"收到任务栏变化 → 250ms 后纠正"。从任务栏点回来的瞬间，
如果 `_fixingMax` 为 true 或防抖计时器刚重置，这次纠正会被吃掉，
且之后没有第二次机会 —— 于是停在越界状态。

## 通用可能原因（原判断，保留）

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

## 复现步骤（按用户实际路径）

```
1. 点标题栏最大化 → 观察：正常（这一步已确认 OK）
2. 点最小化（收起）
3. 从任务栏图标点回来（恢复）
4. 观察窗口底部：「输出/刷新」整行是否被任务栏压住
5. 再最大化/还原一次，看是否自愈（能自愈 → 说明恢复时用的是错误矩形）
```

## 建议修法（后续实施，本轮不动）

**针对恢复路径（④⑤⑥）的最小改动**

```csharp
// 恢复时强制重算一次工作区，而不是信任系统给的矩形
protected override void OnShown(EventArgs e) { ... }

protected override void WndProc(ref Message m)
{
    // WM_ACTIVATE + WA_ACTIVE / WM_SHOWWINDOW：从最小化恢复的必经消息
    if (m.Msg == WM_ACTIVATE || m.Msg == WM_SHOWWINDOW)
    {
        if (WindowState == FormWindowState.Maximized)
        {
            // 下一帧再纠正：此刻窗口矩形还没最终确定
            BeginInvoke((Action)(delegate {
                var wa = Screen.FromControl(this).WorkingArea;
                if (Bounds.Bottom > wa.Bottom || Bounds.Right > wa.Right)
                {
                    MaximizedBounds = wa;
                    WindowState = FormWindowState.Normal;
                    WindowState = FormWindowState.Maximized;
                }
            }));
        }
    }
    base.WndProc(ref m);
}
```

要点：**必须用 `BeginInvoke` 延后一帧**。在消息处理当场改尺寸，
系统随后还会覆盖一次（这就是"改了没用"的常见原因）。

**原判断的修法（① ② ③）**

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
