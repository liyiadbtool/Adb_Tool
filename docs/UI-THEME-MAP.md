# 界面主题三维度拆解（Edge 模型）

> 2026-11-22 整理。**纯文档，不含代码改动。**
> 目的：把现有界面的每一处着色归到 Edge 浏览器的三个主题维度上，
> 作为将来做「主题编辑器 / 自定义配色」的**完整清单底稿**。

---

## 0. 为什么用 Edge 这套划分

Edge 把主题拆成三层，是因为**这三层的着色逻辑互不干扰**：

| 维度 | 语义 | 换主题时的影响面 |
|---|---|---|
| New tab page | 用户真正在看的**内容** | 只换背景，不影响 chrome |
| Browser frame | 包在内容外面的**框架** | 边框、标题栏、侧边栏一起换 |
| Browser tabs | 区分**当前/非当前**标签 | 靠强调色区分层级 |

这个划分能直接套到我们身上，因为我们的结构恰好同构：

```
自绘标题栏 (#titlebar)        ← Browser frame
左侧导航 (#quick-nav)         ← Browser frame（侧边栏）
一级页签 (.tab ×5)            ← Browser tabs
─────────────────────────────────────────
页面内容 (page-* ×5)          ← New tab page
```

---

## 1. 现有主题体系

### 1.1 三套主题（`data-theme`）

| 值 | 名称 | 定位 |
|---|---|---|
| `dark` | 深色 | 默认。Apple 深色 = dimming 而非反转（#000 → #1C1C1E → #2C2C2E 三级抬升） |
| `eye` | 护眼 | Apple 浅色 + 暖白低蓝光变体 |
| `light` | 浅色 | Apple 浅色：冷白系统底 + 纯白卡片 |

### 1.2 强调色（`data-accent`）

`blue` / 默认等多档，通过 `--accent` / `--accent-soft` 体现。

### 1.3 变量总量

每套主题约 **40 个变量**，分三族：

```
颜色族（约 20）  --bg --surface --surface-2 --border --border-strong
                --text --text-dim --text-faint
                --accent --accent-soft --on-accent
                --ok --ok-soft --err --err-soft --err-soft-hover
                --cast-stage --lv-v --lv-d --lv-i --lv-w --lv-e
框架族（约 12）  --frame --chrome --chrome-solid --card --card-hover
                --rim --rim-strong --well --edge --glow
                --blob-2 --blob-3 --blob-4 --gloss-btn
阴影族（约 8）   --shadow-sm --shadow-md --shadow-lg
                --shadow-card --shadow-card-hover --shadow-cell
                --shadow-btn --shadow-btn-hover --shadow-modal --shadow-pop
其它             --scrim --glass --space-* --r-* --ease-*
```

---

## 2. 维度一：New Tab Page（新标签页 → 内容区）

> Edge 对应：新标签页的背景图 / 背景内容。
> 我们对应：**页面内容区**里所有「用户正在看的数据」。

### 2.1 元素清单（12 类）

| # | 元素 | DOM / 类名 | 变量 | 说明 |
|---|---|---|---|---|
| 1 | 主背景 | `body` / `.main` | `--bg` | 整页底色 |
| 2 | 指令卡片（默认） | `.qcard` | `--card` + `--shadow-card` | 内容主体 |
| 3 | 指令卡片（悬停） | `.qcard:hover` | `--card-hover` + `--shadow-card-hover` | |
| 4 | 指令卡片（拖拽中） | `.qcard.dragging` | `--edge` + 大阴影 | |
| 5 | 分组小标题 | `.qcat` | `--text-faint` | 「地图操作」「日志导出」等 |
| 6 | 空状态 | `.qempty` / `.diag-empty` / `.heap-empty` | `--text-faint` | 「没有匹配的指令」 |
| 7 | 内凹区块 | `--well` | `--well` | 定时任务框、汇总条底 |
| 8 | 日志输出区 | `#logbox-0` ~ `#logbox-N` | `--bg` | 终端页，多槽位 |
| 9 | 日志等级色 | `.ln.v/.d/.i/.w/.e` | `--lv-v` `--lv-d` `--lv-i` `--lv-w` `--lv-e` | 5 档（Verbose/Debug/Info/Warn/Error） |
| 10 | 诊断进度条 | `.diag-meter-fill` | `--ok` / `--accent` / `--err` | 三档阈值：<75% 正常 / 75~90% 黄 / >90% 红 |
| 11 | 诊断汇总条 | `.diag-sum` | `--well` + 状态色 | 第 15 批新增 |
| 12 | 背景光斑装饰 | `--blob-2/3/4` | 同左 | living backdrop，深色下才明显 |

### 2.2 特例

| 元素 | 处理方式 |
|---|---|
| 投屏画面底 | `--cast-stage`（固定 #000000，不随主题变 —— 视频画面必须黑底） |
| 卡片内输入框 | `.qinp` 用 `--surface` + focus 时 `--accent` |

---

## 3. 维度二：Browser Frame（浏览器框架）

> Edge 对应：最外边框、标题栏、书签栏、侧边栏、垂直标签的颜色。
> 我们对应：**所有包在内容外面的壳**。

### 3.1 最外边框

| 元素 | 变量 | 说明 |
|---|---|---|
| 窗口外边框/投影 | `--edge`、`--shadow-modal` | |
| 常规边框 | `--border` | 分隔线、卡片描边 |
| 强调边框 | `--border-strong` | 选中态、焦点态 |
| 1px 内高光 | `--rim` / `--rim-strong` | 拟物高光，深色下让面「浮起来」 |
| 按钮高光渐变 | `--gloss-btn` | 主按钮顶部反光 |

### 3.2 标题栏（自绘）

| 元素 | DOM | 变量 |
|---|---|---|
| 标题栏底 | `#titlebar` | `--frame` |
| 玻璃面（半透明） | `--chrome` | 滚动时透出内容 |
| 实心面（不透明） | `--chrome-solid` | 浮层面板底 |
| 状态四圆点 | `#tb-status` | `--ok`（root）/ `--accent`（无线）/ `--err`（断连） |
| 窗口按钮 | `.tb-btn`（最小/最大/关闭） | `--gloss-btn` + `--accent` / `--err` |
| 拖动热区 | `-webkit-app-region:drag` | 无颜色 |

### 3.3 侧边栏（= 我们的左侧导航）

| 元素 | DOM | 变量 |
|---|---|---|
| 导航容器 | `#quick-nav` | `--chrome` |
| 导航项（默认） | `.qnav-item` | `--text-dim` |
| 导航项（悬停） | `.qnav-item:hover` | `--surface-hover` |
| 导航项（选中） | `.qnav-item.active` | `--accent-soft` + `--accent` 文字 |
| 搜索框 | `#quick-search` | `--surface` + `--border` |
| 分组数量徽标 | `.qnav-count` | `--text-faint` |

### 3.4 工具条 / 书签栏

> **注**：我们没有真正的书签栏。最接近的是运行时工具条。

| 元素 | DOM | 变量 |
|---|---|---|
| 设备面包屑 | `runbar` 的 CRUMB | `--text-dim` |
| 运行胶囊 | `.runchip` | `--accent` + `--accent-soft` |
| 根权限胶囊 | `.rootpill` | `--ok` / `--text-faint` |
| 诊断工具条 | `diag-bar` | `--border` 下边线 |
| 输入槽位容器 | `#slots` | `--surface` |
| 复制格式选择器 | `#diag-fmt` | `--surface` + `--border` |

### 3.5 浮层框架（12 个）

所有浮层共用同一套着色：

```
遮罩层   --scrim
面板底   --chrome-solid
投影     --shadow-modal
边框     --border
```

| # | 浮层 | id | 用途 |
|---|---|---|---|
| 1 | 设置 | `set-mask` | 主题/字号/缩放 |
| 2 | 帮助 | `help-mask` | 指令说明 |
| 3 | 关于 | `about-mask` | 版本信息 |
| 4 | 配置说明 | `cfg-help-mask` | cmds.ini 写法 |
| 5 | 自定义指令管理 | `custom-mgr` | 增删改自定义命令 |
| 6 | APK 管理 | `apk-mgr` | 应用列表与版本 |
| 7 | APK 面板 | `apk-panel` | 指令分组内的 APK 操作区 |
| 8 | 网络模拟 | `netsim-panel` | 延迟/丢包参数 |
| 9 | HeapDump | `heap-mask` | 进程选择器（第 14 批） |
| 10 | Monkey 崩溃 | `mk-crash-mask` | 崩溃详情 |
| 11 | 语音输入 | `vr-panel` | 语音助手分组内 |
| 12 | 自定义面板 | `custom-panel` | 自定义分组容器 |

---

## 4. 维度三：Browser Tabs（标签页）

> Edge 对应：当前标签 / 未打开标签的颜色。
> 我们对应：**所有用「选中/未选中」表达层级的控件**。

### 4.1 一级页签（5 个）

`.tab` → 5 个页面：指令 / 终端 / 文件 / Monkey / 诊断

| 状态 | 样式 | 变量 |
|---|---|---|
| **当前** | `.tab.active` | 底 `--accent`、字 `--on-accent`、粗体 600 |
| **未激活** | `.tab` | 底 `--surface`、字 `--text-dim`、边 `--border` |
| 悬停 | `.tab:hover` | 字 → `--text` |
| 按下 | `.tab:active` | `transform:scale(.97)` |

### 4.2 二级页签（3 处）

| 位置 | 类名 | 着色规则 |
|---|---|---|
| Monkey 子页 | `.mk-subtab` | 同 `.tab` |
| Fastbot 子页 | `.fb-subtab` | 同 `.tab` |
| 文件页左右切换 | `fileNavSwitch` | 同 `.tab` |

### 4.3 卡片「执行态」（等价于"打开的标签"）

卡片本身也是一个可着色单元，用**状态**而不是颜色块来区分：

| 状态 | 类名 | 变量 | 语义 |
|---|---|---|---|
| 执行中 | `.qcard.running` | `--accent` + 转圈图标 | 相当于"活动标签" |
| 已完成 | `.qcard.done` | `--ok` | |
| 失败 | `.qcard.error` | `--err` | |
| 空闲 | `.qcard` | `--card` | 相当于"未打开标签" |

### 4.4 其它层级表达

| 元素 | 变量 | 说明 |
|---|---|---|
| 诊断卡折叠态 | `.diag-card.folded` | 只留标题栏 |
| 定时任务状态 | `.tt-state.run/.pause` | `--ok` / `--accent` |
| 折叠箭头 | `.diag-caret` | 旋转 180° 表展开 |

---

## 5. 覆盖核对表（防遗漏）

| 类别 | 数量 | 归属维度 | 核对 |
|---|---|---|---|
| 一级页面 | 5（cmd / quick / file / monkey / diag） | New tab page | ✅ |
| 浮层 / 面板 | 12 | Browser frame | ✅ |
| 一级页签 | 5 | Browser tabs | ✅ |
| 二级页签 | 3 处 | Browser tabs | ✅ |
| 日志等级色 | 5 | New tab page | ✅ |
| 卡片状态 | 4（默认/执行/完成/错误） | Browser tabs | ✅ |
| 主题变量 | 约 40 × 3 套 | 三族已归类 | ✅ |
| 阴影令牌 | 10 | Browser frame | ✅ |
| 装饰光斑 | 3 | New tab page | ✅ |

---

## 6. 现状问题与重构建议（仅建议，本期不实施）

### 6.1 问题：框架层变量过碎，且命名不带语义

当前框架族混了三类东西：

```
语义类    --frame  --chrome  --chrome-solid        （框架面）
装饰类    --rim  --rim-strong  --gloss-btn  --glow （高光，纯视觉）
尺寸类    --card  --card-hover  --well  --edge     （介于面与线之间）
```

后果：想做一个「换主题只改 6 个值」的编辑器，改不动 —— 因为改 `--chrome` 不会自动影响 `--frame`。

### 6.2 建议：合并成 3 个语义组

```
frame.border      最外边框 + 高光    ← --edge --rim --rim-strong
frame.chrome      标题栏 + 侧边栏 + 工具条 ← --frame --chrome --chrome-solid
frame.overlay     浮层遮罩 + 面板    ← --scrim --card --card-hover --well
```

### 6.3 建议：给每个维度定 5 个可编辑槽位

如果将来做主题编辑器，按 Edge 的做法，每个维度只暴露 5 个可调项：

| 维度 | 可编辑项 |
|---|---|
| New tab page | 背景色 / 内容面 / 文字主色 / 文字次色 / 强调色 |
| Browser frame | 边框 / 标题栏 / 侧边栏 / 工具条 / 浮层底 |
| Browser tabs | 当前标签底 / 当前标签字 / 非当前底 / 非当前字 / 悬停 |

15 个槽位 → 映射到现有 40 个变量，其余（阴影、光斑、渐变）全部由这 15 个推导。

---

## 7. 维护约定

1. **新增界面元素时**，先判断它属于哪个维度，再用该维度的现有变量 —— 不要新建变量。
2. **不要写 hex**，一律 `rgba()` / `var()`（不变量门禁会拦）。
3. 三套主题必须**同增同减** —— 加一个变量就要在 dark / eye / light 三处都加。
4. `--cast-stage` 固定黑色，**不参与主题**（视频画面必须黑底）。
