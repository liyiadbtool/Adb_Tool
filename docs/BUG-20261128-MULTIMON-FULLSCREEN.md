# D19 切到扩展屏后全屏溢出（仅记录，未改代码）

> 2026-11-28 15:53 · 用户截图 · 与 D18 不是同一个问题

## 现象

把窗口拖到**扩展屏（副屏）**再最大化：

```
· 窗口铺满副屏，但底部输入条贴到屏幕最边缘、被压住一截
· 右侧内容也被裁掉一点
· 主屏最大化正常（D18 修的是"从任务栏恢复"路径，这里是"换屏"路径）
```

## 与已修问题的区别

| 编号 | 触发 | 已做处理 |
|---|---|---|
| D2 | 最大化遮住底部输出条 | `EnsureInsideWorkingArea` |
| D13 | 任务栏收起/展开后越界 | `WM_SETTINGCHANGE` + 250ms 防抖 |
| D18 | 最小化→任务栏恢复 | `WM_ACTIVATE`/`WM_SHOWWINDOW` + BeginInvoke |
| **D19** | **拖到副屏后最大化** | **无** |

D19 走的是另一条路径：**显示器 / DPI 变化**，前三次修复都覆盖不到。

## 最可能的原因（按可能性）

### ① `MaximizedBounds` 还是主屏的工作区

`MaximizedBounds` 在 `UpdateMaximizedBounds()` 里按"当前所在屏"算。
如果拖动窗口到副屏时该函数没被调用（或调用时窗口还在主屏边界上），
`MaximizedBounds` 就是主屏矩形（比如 1920×1080 副屏 vs 2560×1440 主屏 →
尺寸偏小/偏移），最大化后窗口与屏幕对不齐，底部/右侧就溢出或留白。

### ② 两屏 DPI 不同，窗口尺寸按逻辑像素算

副屏 150%、主屏 100% 是常见组合。无边框窗口跨屏后：

```
· WinForms 的 Bounds 是物理像素
· WebView2 内部的 CSS 布局按 缩放比 换算
· DPI 变化没有处理 WM_DPICHANGED 时，尺寸不会重算
```

结果就是"窗口铺满了，但页面内容按另一个比例排版"，底部一行被挤出可视区。

### ③ 自绘标题栏 + 无边框，系统不再帮忙

`FormBorderStyle=None` 时，跨屏最大化不会自动吸附工作区，
全靠 `MaximizedBounds` / `WM_GETMINMAXINFO` 自己算——任一处用旧值就溢出。

## 复现步骤

```
1. 主屏打开工具，最大化 → 正常
2. 还原，把窗口拖到扩展屏
3. 在扩展屏上最大化
4. 观察：底部输入条 / 右侧边缘是否被裁
5. 再看任务栏：副屏任务栏在下方还是侧边？（侧边时更容易复现）
```

## 建议修法（后续实施）

```csharp
// ① 接住 DPI / 显示变化，重算边界后再最大化
protected override void WndProc(ref Message m)
{
    if (m.Msg == 0x02E0)   // WM_DPICHANGED
    {
        UpdateMaximizedBounds();
        if (WindowState == Maximized)
            BeginInvoke((Action)(() => EnsureInsideWorkingArea(false)));
    }
    if (m.Msg == 0x007E)   // WM_DISPLAYCHANGE
    {
        UpdateMaximizedBounds();
        BeginInvoke((Action)(() => EnsureInsideWorkingArea(false)));
    }
    base.WndProc(ref m);
}

// ② 最大化前用"窗口中心所在屏"取工作区，而不是 Screen.PrimaryScreen
var scr = Screen.FromControl(this);       // 已有用法，确认没被写成 PrimaryScreen
MaximizedBounds = scr.WorkingArea;

// ③ 副屏任务栏在侧边时，工作区宽度会变窄 —— 用 WorkingArea 而不是 Bounds
```

**关键点**：`UpdateMaximizedBounds()` 必须在**窗口已经移动到副屏之后**执行；
拖动过程中窗口跨屏瞬间会触发多次，建议用 200ms 防抖（与 D13 的 `_trayTimer` 复用）。

## 验收标准

```
□ 拖到副屏 → 最大化：底部输入条完整可见，右侧无裁切
□ 副屏任务栏移到侧边 → 再次最大化：仍完整
□ 主副屏 DPI 不同（如 100% / 150%）→ 最大化后布局不糊、不溢出
□ 从副屏最大化状态拖回主屏 → 不越界（跨屏往返）
□ D18 的"最小化→恢复"仍正常（回归）
```

## 备注

这次只记录。要修的话改动集中在 `WndProc` 与 `UpdateMaximizedBounds`，
与 D18 的改动同区域，建议**一起验证**（跨屏 + 恢复 两个场景交替测）。
