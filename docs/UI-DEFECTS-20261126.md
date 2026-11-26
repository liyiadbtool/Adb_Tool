# UI 缺陷记录（2026-11-26）

> 仅记录，未修代码。每条含：现象 / 根因 / 影响面 / 建议修法 / 验证方式。

---

## D1 切换页面时界面“抖一下”（诊断页最明显）

**现象**：点「诊断」页签瞬间，页面先矮后高，视觉上抖一下。

**根因（两层）**

1. **纵向高度跳变**：`diagOnEnter() → diagRefresh()` 先把状态清空、渲染“正在采集/正在读取”占位，
   随后本机数据（~300ms）、车机数据（1~3s）、超时兜底（8s）依次填充，
   两列 Grid 互相牵扯 → 高度变化 3~4 次。
2. **缺滚动条占位**：全站 40 个 `overflow` 容器未设 `scrollbar-gutter`，
   内容跨过“刚好出现滚动条”的阈值时，可用宽度突变 15px。

**影响面（同类问题，不止诊断页）**

| 类型 | 涉及位置 |
|---|---|
| 缺 gutter（横向抖） | `.mk-wrap`(L4091) `.set-body`(L2021) `.help-toc`(L2128) `.help-doc`(L2139) `.cm-body`(L1446) `.apk-mgr-list`(L984) `.ui-wrap`(L1097) `.heap-list`(L1960) `.ns-out`(L1088) 等 40 处 |
| 异步填充（纵向抖） | 诊断页、文件页首次 `fsEnsureInit()`、Monkey 应用清单、APK 查询、H5 渲染、投屏设备扫描、TOP5 |
| 结构性差异 | 各页头部高度不同（`quick-head` / `diag-head`）；诊断卡片折叠状态记忆在 localStorage |

**建议修法**

```
① 全局给 overflow 容器加 scrollbar-gutter:stable（通配或逐个补）
② 会异步填充的卡片给 min-height（约等于预期行数高度）
③ 切换页签时把重活推迟一帧（requestAnimationFrame / setTimeout 0），避免掉帧
```

**验证方式**

```js
// 切页前后对比
[el.clientWidth, el.scrollHeight]
```
clientWidth 差 15~18px → gutter 问题；scrollHeight 明显变化 → 异步填充问题。

**优先级**：高（每次进入都会触发）

---

## D2 全屏/最大化时底部 dock（输出条）被遮挡

**现象**：窗口最大化后，底部「输出」条被窗口/屏幕下缘切掉半截，看不到完整一行。

**根因**

无边框窗口（`FormBorderStyle.None`）最大化时，Windows 会铺满**整屏**、盖住任务栏，
项目用 `MaximizedBounds = Screen.FromControl(this).WorkingArea` 来纠正。

但该计算**只在 `OnLoad` 执行一次**（L890），之后：

- 窗口被拖到副屏后最大化 → `MaximizedBounds` 仍是主屏工作区 → 尺寸/位置错
- 任务栏位置或显示缩放（DPI）变化 → 计算值过期
- 一旦 `MaximizedBounds` 失效，窗口高度 = 屏幕全高（含任务栏），
  WebView2 以 `Dock=Fill` 跟随窗口 → 页面底部 34~40px 落在屏幕外

页面侧无补偿：`html,body{height:100%}`，`body{overflow:hidden}`，
底部 `.feedback.collapsed{height:34px}` 是布局的最后一行，被屏幕裁掉后没有任何滚动条可看到。

**影响面**

- 所有页面都受影响（底部是全局输出区，不属于某一页）
- 只出现在「最大化 / 全屏」状态；普通尺寸下正常

**建议修法（三选一或叠加）**

```
① 在 Resize / 显示设置变化时重算 MaximizedBounds（而不是只在 OnLoad）
② 最大化前后用 SetWindowPos 把窗口钳到 WorkingArea
③ 页面侧兜底：body 加 padding-bottom: env(safe-area-inset-bottom, 0) 并允许 .main 收缩
```

**验证方式**

```
· 最大化后对比：窗口下缘 y 坐标 vs WorkingArea.Bottom
· 若窗口 Bottom > WorkingArea.Bottom → 印证 MaximizedBounds 失效
· 移到副屏再最大化，观察是否更严重
```

**优先级**：高（最大化是常用状态，且影响全局输出区可见性）

---

## 待办汇总

| 编号 | 项 | 优先级 | 状态 |
|---|---|---|---|
| D1 | 切页/开面板抖动（40 处 gutter + 异步填充） | 高 | 记录，未修 |
| D2 | 最大化时底部输出条被遮挡（已确认：窗口越界，底部在屏幕外） | 高 | 记录，未修 |
| D3 | 导出路径齿轮偏小 / 点击看似无响应（弹窗在 overflow 容器内） | 高 | 记录，未修 |

---

## D3 导出路径齿轮：视觉偏小 + 点击“看起来没反应”

**现象**：卡片右上角齿轮仍是小图标；点它没有弹出设置框。

**实测（无头浏览器，ui.html 现版本）**

```
齿轮数量            8（= 当前 exp 卡片数，正确）
计算样式            width 26px / font-size 17px（CSS 已生效）
点击 .click()       op-backdrop display=flex，op-id="shot"（逻辑正确）
遮罩几何            位置 y=116，高 784（**没有覆盖顶部 116px 标签栏**）
面板几何            560 × 74
祖先裁剪链          quick-scroll → quick-body(overflow:hidden)
                    → quick-wrap(overflow:hidden) → main(perspective:1700px)
```

**结论：逻辑没坏，是“住错了地方”**

`#op-backdrop` 被写在 `#page-quick` 内部，而中间有三层 `overflow:hidden` 和一个
`perspective` 容器。`position:fixed` 在有 transform/perspective 的祖先下**不再是视口定位**，
而是相对该祖先，并被 `overflow:hidden` 裁剪：

- 遮罩从 y=116 开始，顶部标签栏没被盖住（说明 `inset:0` 失效）
- 页面滚动时弹窗跟着内容跑，可能滚出可视区 → 用户看到的就是“点了没反应”
- 面板高度仅 74px（一行控件 + 空列表），本身也偏小，容易被当成“没打开”

**次要问题：齿轮视觉尺寸**
`.qgear` 盒子 26px，但字形只有 17px，实际观感约 13px；且默认 `opacity:.45` 偏淡。

**建议修法**

```
① 把 #op-backdrop 移到 <body> 末尾（脱离 overflow/perspective 容器）
   —— 一行 DOM 位置调整，治"点击无效"
② .qgear 字号 17 → 20，盒子 26 → 28；或改用 SVG 齿轮图标
③ 面板加最小高度（约 160px），列表区留空时也给提示
```

**优先级**：高（功能入口，用户直接感知）

