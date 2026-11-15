# UI-RESKIN-INVENTORY · A13 全量盘点清单（adb_Tool 实例 · 分母 v6）

> 生成：`python _build_inventory.py`。**以当前源码为准**，不采信附带 md 的旧版快照。
> 依据：`docs/FUNCTION-INVARIANTS.md`（阶段 0 基线）与 `adb_log_gui/webview2/ui.html`。
> 状态：✅ 已处理 / ⬜ 未处理 / N·A 不适用（逐条写理由）。

## 0. 与附带 md 盘点快照的差异（A2 要求「核对 + 补全」）

| 项 | md 旧快照 | 当前真实源码 | 处理 |
|---|---|---|---|
| 页签数 | 4（quick/cmd/file/cast） | **6**（quick/cmd/file/cast/ui/text） | 追加 P-06，分母 +1 |
| 页面数 | 4 | **6**（page-cmd/page-quick/page-cast/page-ui/page-file/page-text） | 追加 P-06 |
| 左侧分组 | 8 组（含测试工具箱） | 6 组 + 2 个 panel | 按 0138 成品重排 |
| 令牌角色 | 16 | **17** | 按阶段 0 快照取 17 |
| 内联 SVG | 24 | **37** | 实测 |
| 主题 | 3 | **3**（dark/light/eye） | 保留 |
| 投屏按钮 | 前排/后排/刷新位 3 个 | 已删除，改为固定格子内建屏位 | 追加 C-23 |
| 网络模拟 | 5 张卡片 | 表单面板 | 追加 C-21 |
| UI 对比 | 无 | 第 5 页 | 追加 P-06 / C-22 |
| 搜索结果进入 | 无 | 点击进入树（本轮改） | 追加 C-24 / A9-03 |

> md 的 0.5 节从 ICO-07 直接跳到 ICO-10，`ICO-08 / ICO-09` 未描述实际资产；
> 保留编号并标 N·A，不虚增分母。`ICO-35` 按当前源码同时覆盖投屏格与 UI 对比页的设备图。

## 1. P 页面 / 页签（16）

| ID | 名称 | 状态 |
|---|---|---|
| P-01 | 顶栏（设备 / root / 无线 / 日志等级 / runchip / 主题 / 品牌） | ✅ |
| P-02 | 指令页 page-quick（左侧导航 + 卡片 + 反馈表） | ✅ |
| P-03 | 终端页 page-cmd（3 槽 + 执行/停止/清屏/复制） | ✅ |
| P-04 | 文件页 page-file（双栏树 + 路径栏 + 搜索 + 进度） | ✅ |
| P-05 | 投屏页 page-cast（6 格 + 最大化 + 底部缩略条） | ✅ |
| P-06 | UI 对比页 page-ui ★清单外新增（投屏右侧第 5 页） | ✅ |
| P-07 | 底部输出区（34px 折叠栏 + 反馈表 + toast） | ✅ |
| P-08 | 加载过渡层（8 秒兜底） | ✅ |
| P-09 | apk-mgr 弹窗 | ✅ |
| P-10 | 无线连接弹窗 | ✅ |
| P-11 | fs-modal 新建文件夹弹窗 | ✅ |
| P-12 | 快捷搜索下拉 | ✅ |
| P-13 | toast 浮层 | ✅ |
| P-14 | 自定义指令面板 #custom-panel（卡片墙 + ＋新建指令）★A11 | ✅ |
| P-15 | 自定义指令编辑器 #custom-mgr（名称 / 说明 / 流程逐行）★A11 | ✅ |
| P-16 | 强调色色板 #accent-pop（9 色 · 只作用于 accent 派生色）★A11 | ✅ |

## 2. C 组件（30）

| ID | 名称 | 状态 |
|---|---|---|
| C-01 | root 胶囊 | ✅ |
| C-02 | 无线胶囊 | ✅ |
| C-03 | 日志等级徽章 | ✅ |
| C-04 | runchip 执行中计时 | ✅ |
| C-05 | .tab 页签 | ✅ |
| C-06 | .btn 系列（primary/ghost/sm） | ✅ |
| C-07 | .icon-btn 图标按钮 | ✅ |
| C-08 | 终端输入槽 slot-N | ✅ |
| C-09 | quick-search 搜索框 | ✅ |
| C-10 | 快捷指令卡片 qcard | ✅ |
| C-11 | APK 下拉与面板 | ✅ |
| C-12 | 双栏树节点 fs-row | ✅ |
| C-13 | 传输进度条 | ✅ |
| C-14 | 反馈表 fb-row | ✅ |
| C-15 | 折叠栏 | ✅ |
| C-16 | 分隔条 | ✅ |
| C-17 | 投屏 img 容器 | ✅ |
| C-18 | APK 管理列表行 | ✅ |
| C-19 | 弹层遮罩与按钮 | ✅ |
| C-20 | 车机信息面板 | ✅ |
| C-21 | 网络模拟表单面板 ★清单外 | ✅ |
| C-22 | UI 对比画布与结果框 ★清单外 | ✅ |
| C-23 | 全屏底部缩略条 ★清单外 | ✅ |
| C-24 | 搜索结果行 ★清单外 | ✅ |
| C-25 | 自定义指令卡片 cm-card ★A11 | ✅ |
| C-26 | 流程步骤行 cm-step（cmd/delay/loop）★A11 | ✅ |
| C-27 | 强调色色点 accent-dot 与当前色指示 acur ★A11 | ✅ |
| C-28 | 玻璃 chrome（顶栏 / 左侧导航）★A11 | ✅ |
| C-29 | 玻璃页签胶囊 .tabs ★A11 | ✅ |
| C-30 | 玻璃浮层（cm-box / fs-modal-box / accent-pop）★A11 | ✅ |

## 3. S 状态矩阵

八态与五态由**同一套 CSS 覆盖层**实现（`:hover` 门控 / `:focus-visible` /
`[disabled],.disabled,[aria-disabled]` / `.loading` / `.err` / `.ok` 等），
不做 320 份重复实现。下表逐单元格列出，证据见 `COMPONENT-STATES.preview.html`。

### 3.1 组件八态（30 行 × 8 列 = 240 格）

| 组件 | default | hover | focus-visible | active | disabled | loading | error | success |
|---|---|---|---|---|---|---|---|---|
| C-01 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-02 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-03 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-04 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-05 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-06 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-07 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-08 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-09 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-10 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-11 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-12 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-13 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-14 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-15 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-16 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-17 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-18 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-19 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-20 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-21 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-22 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-23 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-24 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-25 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-26 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-27 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-28 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-29 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-30 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

### 3.2 视图五态（16 行 × 5 列 = 80 格）

| 页面 | loading | empty | error | success | disabled |
|---|---|---|---|---|---|
| P-01 | ✅ | ✅ | ✅ | ✅ | ✅ |
| P-02 | ✅ | ✅ | ✅ | ✅ | ✅ |
| P-03 | ✅ | ✅ | ✅ | ✅ | ✅ |
| P-04 | ✅ | ✅ | ✅ | ✅ | ✅ |
| P-05 | ✅ | ✅ | ✅ | ✅ | ✅ |
| P-06 | ✅ | ✅ | ✅ | ✅ | ✅ |
| P-07 | ✅ | ✅ | ✅ | ✅ | ✅ |
| P-08 | ✅ | ✅ | ✅ | ✅ | ✅ |
| P-09 | ✅ | ✅ | ✅ | ✅ | ✅ |
| P-10 | ✅ | ✅ | ✅ | ✅ | ✅ |
| P-11 | ✅ | ✅ | ✅ | ✅ | ✅ |
| P-12 | ✅ | ✅ | ✅ | ✅ | ✅ |
| P-13 | ✅ | ✅ | ✅ | ✅ | ✅ |
| P-14 | ✅ | ✅ | ✅ | ✅ | ✅ |
| P-15 | ✅ | ✅ | ✅ | ✅ | ✅ |
| P-16 | ✅ | ✅ | ✅ | ✅ | ✅ |

状态单元格合计：**320** 个，全部 ✅。

## 4. T 令牌（63）

| ID | 角色 · 主题 | 状态 |
|---|---|---|
| T-001 | `--bg` · dark | ✅ |
| T-002 | `--surface` · dark | ✅ |
| T-003 | `--surface-2` · dark | ✅ |
| T-004 | `--border` · dark | ✅ |
| T-005 | `--border-strong` · dark | ✅ |
| T-006 | `--text` · dark | ✅ |
| T-007 | `--text-dim` · dark | ✅ |
| T-008 | `--text-faint` · dark | ✅ |
| T-009 | `--accent` · dark | ✅ |
| T-010 | `--accent-soft` · dark | ✅ |
| T-011 | `--ok` · dark | ✅ |
| T-012 | `--err` · dark | ✅ |
| T-013 | `--lv-v` · dark | ✅ |
| T-014 | `--lv-d` · dark | ✅ |
| T-015 | `--lv-i` · dark | ✅ |
| T-016 | `--lv-w` · dark | ✅ |
| T-017 | `--lv-e` · dark | ✅ |
| T-018 | `--bg` · light | ✅ |
| T-019 | `--surface` · light | ✅ |
| T-020 | `--surface-2` · light | ✅ |
| T-021 | `--border` · light | ✅ |
| T-022 | `--border-strong` · light | ✅ |
| T-023 | `--text` · light | ✅ |
| T-024 | `--text-dim` · light | ✅ |
| T-025 | `--text-faint` · light | ✅ |
| T-026 | `--accent` · light | ✅ |
| T-027 | `--accent-soft` · light | ✅ |
| T-028 | `--ok` · light | ✅ |
| T-029 | `--err` · light | ✅ |
| T-030 | `--lv-v` · light | ✅ |
| T-031 | `--lv-d` · light | ✅ |
| T-032 | `--lv-i` · light | ✅ |
| T-033 | `--lv-w` · light | ✅ |
| T-034 | `--lv-e` · light | ✅ |
| T-035 | `--bg` · eye | ✅ |
| T-036 | `--surface` · eye | ✅ |
| T-037 | `--surface-2` · eye | ✅ |
| T-038 | `--border` · eye | ✅ |
| T-039 | `--border-strong` · eye | ✅ |
| T-040 | `--text` · eye | ✅ |
| T-041 | `--text-dim` · eye | ✅ |
| T-042 | `--text-faint` · eye | ✅ |
| T-043 | `--accent` · eye | ✅ |
| T-044 | `--accent-soft` · eye | ✅ |
| T-045 | `--ok` · eye | ✅ |
| T-046 | `--err` · eye | ✅ |
| T-047 | `--lv-v` · eye | ✅ |
| T-048 | `--lv-d` · eye | ✅ |
| T-049 | `--lv-i` · eye | ✅ |
| T-050 | `--lv-w` · eye | ✅ |
| T-051 | `--lv-e` · eye | ✅ |
| T-A01 | 系统字体栈 | ✅ |
| T-A02 | 8pt 间距网格 | ✅ |
| T-A03 | 连续圆角 | ✅ |
| T-A04 | tinted 阴影 | ✅ |
| T-A05 | hairline 边框 | ✅ |
| T-A06 | 层级 z-index | ✅ |
| T-A07 | 动效曲线 / ≤300ms | ✅ |
| T-A08 | 玻璃仅给 chrome | ✅ |
| T-A09 | 玻璃面令牌（--frame/--chrome/--card/--rim/--well/--edge）★A11 | ✅ |
| T-A10 | living backdrop 光雾令牌（--blob-2..4/--glow）★A11 | ✅ |
| T-A11 | 玻璃投影令牌（--shadow-card/modal/pop/btn）★A11 | ✅ |
| T-A12 | accent 9 色 × 3 主题 = 27 组 WCAG 对比度校验 ★A11 | ✅ |

## 5. F 反馈（10）

| ID | 名称 | 状态 |
|---|---|---|
| F-01 | toast | ✅ |
| F-02 | 复制全部 | ✅ |
| F-03 | 清空 | ✅ |
| F-04 | 仅失败 | ✅ |
| F-05 | 收起 | ✅ |
| F-06 | 执行中指示 | ✅ |
| F-07 | 错误提示 | ✅ |
| F-08 | 空态 | ✅ |
| F-09 | 自定义流程汇总 toast（成功/失败计数）★A11 | ✅ |
| F-10 | 编辑器即时校验 cm-err ★A11 | ✅ |

## 6. N 导航（13）

| ID | 名称 | 状态 |
|---|---|---|
| N-01 | 5 个页签 | ✅ |
| N-02 | Ctrl+1..4 切页 | ✅ |
| N-03 | Ctrl+K 搜索 | ✅ |
| N-04 | Alt+↓ 收起 | ✅ |
| N-05 | ↑↓ 历史 | ✅ |
| N-06 | Esc 清搜索 | ✅ |
| N-07 | 左侧分组导航 | ✅ |
| N-08 | quick-search 命中下拉 | ✅ |
| N-09 | 文件路径栏 | ✅ |
| N-10 | 面包屑 / 上一级 | ✅ |
| N-11 | APK 面板下拉 | ✅ |
| N-12 | 投屏格最大化 / 还原 | ✅ |
| N-13 | 指令页「自定义」分组入口（第 7 组）★A11 | ✅ |

## 7. M 动效（15）

| ID | 名称 | 状态 |
|---|---|---|
| M-01 | 卡片转圈 | ✅ |
| M-02 | 卡片完成 | ✅ |
| M-03 | 卡片失败 | ✅ |
| M-04 | 折叠栏展开/收起 | ✅ |
| M-05 | toast 进出 | ✅ |
| M-06 | 加载层淡出 | ✅ |
| M-07 | 树节点 ▸▾ 展开 | ✅ |
| M-08 | 拖拽整行高亮 | ✅ |
| M-09 | 传输进度推进 | ✅ |
| M-10 | 分隔条拖动 | ✅ |
| M-11 | 主题切换 | ✅ |
| M-12 | 背景光雾 52s 漂移 ★A11 | ✅ |
| M-13 | 页面切换 4px 上浮淡入 ★A11 | ✅ |
| M-14 | 弹窗 pop-in 缩放 ★A11 | ✅ |
| M-15 | 卡片 hover 抬升 + accent 光环 ★A11 | ✅ |

## 8. D 尺寸（8）

| ID | 名称 | 状态 |
|---|---|---|
| D-01 | 1100×760 默认 | ✅ |
| D-02 | 820×560 最小 | ✅ |
| D-03 | 顶栏胶囊不换行 | ✅ |
| D-04 | 5 页签不溢出 | ✅ |
| D-05 | 34px 折叠栏不丢 | ✅ |
| D-06 | 双栏树分隔条可拖 | ✅ |
| D-07 | 多屏主屏居中 | ✅ |
| D-08 | Windows 标题栏明暗 | ✅ |

## 9. K 无障碍（10）

| ID | 名称 | 状态 |
|---|---|---|
| K-01 | 语义标签 | ✅ |
| K-02 | aria-label / title | ✅ |
| K-03 | :focus-visible 焦点环 | ✅ |
| K-04 | 文本 4.5:1 | ✅ |
| K-05 | 非文本图标 3:1 | ✅ |
| K-06 | 不靠颜色单独表意（日志等级保留字母） | ✅ |
| K-07 | 44pt 热区 | ✅ |
| K-08 | 键盘全路径 | ✅ |
| K-09 | 三套偏好降级 | ✅ |
| K-10 | 色彩不单独表意（色板带中文色名 + title）★A11 | ✅ |

## 10. W 视觉文案（4）

| ID | 名称 | 状态 |
|---|---|---|
| W-01 | 标题层级 | ✅ |
| W-02 | 按钮措辞一致性 | ✅ |
| W-03 | 留白节奏 | ✅ |
| W-04 | 业务文案与命令文本不改 | ✅ |

## 11. H 主题（6）

| ID | 名称 | 状态 |
|---|---|---|
| H-01 | data-theme=dark | ✅ |
| H-02 | data-theme=light | ✅ |
| H-03 | data-theme=eye | ✅ |
| H-04 | 降级 prefers-reduced-motion | ✅ |
| H-05 | 降级 prefers-reduced-transparency | ✅ |
| H-06 | 降级 prefers-contrast | ✅ |

## 12. A 资产（ICO-01..36 + U1..U6 = 42）

| ID | 名称 | 状态 | N·A 理由 |
|---|---|---|---|
| ICO-01 | adb_log_gui/adb_Tool.ico 窗口图标 | ✅ | |
| ICO-02 | adb_log_gui/icons/adb_Tool.ico 同源副本 | ✅ | |
| ICO-03 | exe 内嵌 /win32icon（任务栏 / Alt+Tab） | ✅ | |
| ICO-04 | icons/svg/AdbTool-中控终端.svg 可编辑源（图标 v2） | ✅ | |
| ICO-05 | GuiWeb.cs ShowIcon=false | N·A | A10 冻结：ShowIcon=false 是功能设定，改了会改标题栏行为 |
| ICO-06 | ApplyDarkTitleBar 标题栏明暗 | ✅ | |
| ICO-07 | MessageBoxIcon 系统对话框图标 | N·A | 系统 MessageBox 图标由 Windows 提供，非本应用资产 |
| ICO-08 | md 未定义编号（占位） | N·A | md 的 0.5 节从 ICO-07 直接跳到 ICO-10，未定义 08/09；保留编号不虚增资产 |
| ICO-09 | md 未定义编号（占位） | N·A | md 的 0.5 节从 ICO-07 直接跳到 ICO-10，未定义 08/09；保留编号不虚增资产 |
| ICO-10 | 加载过渡层品牌 SVG（48×48，中控屏 + 提示符） | ✅ | |
| ICO-11 | 顶栏品牌标识 .icon-btn（中控屏轮廓 + >_，onclick=sendCmd(':h')） | ✅ | |
| ICO-12 | 主题按钮 #theme-btn 初始 SVG | ✅ | |
| ICO-13 | THEME_ICON.dark 月亮 | ✅ | |
| ICO-14 | THEME_ICON.light 太阳 | ✅ | |
| ICO-15 | THEME_ICON.eye 眼睛 | ✅ | |
| ICO-16 | .zi 人形 SVG 1 | ✅ | |
| ICO-17 | .zi 人形 SVG 2 | ✅ | |
| ICO-18 | .zi 人形 SVG 3 | ✅ | |
| ICO-19 | .zi 人形 SVG 4 | ✅ | |
| ICO-20 | .zi 人形 SVG 5 | ✅ | |
| ICO-21 | .zi 人形 SVG 6 | ✅ | |
| ICO-22 | 发送纸飞机 SVG | ✅ | |
| ICO-23 | .fcb-arrow 折叠箭头 SVG | ✅ | |
| ICO-24 | _ICON_RUN 执行 | ✅ | |
| ICO-25 | _ICON_STOP 停止 | ✅ | |
| ICO-26 | _ICON_CLEAR 清屏 | ✅ | |
| ICO-27 | _ICON_COPY 复制 | ✅ | |
| ICO-28 | _ICON_DEL 删除 | ✅ | |
| ICO-29 | ICON_PLAY 卡片播放 | ✅ | |
| ICO-30 | ICON_SPIN 卡片转圈 | ✅ | |
| ICO-31 | ICON_STOP 卡片停止 | ✅ | |
| ICO-32 | ICON_DONE 卡片完成 | ✅ | |
| ICO-33 | ICON_ERROR 卡片失败 | ✅ | |
| ICO-34 | 字符图标 ▼ ⇱ ＋ × ★ ▸ ▾ ■ ● / apk-caret / V-D-I-W-E 字母徽章 | ✅ | |
| ICO-35 | 投屏 cast-img-N 与 UI 对比页设备图 | N·A | 投屏 <img> 是车机设备原图，禁止主题化 / 滤镜；只可调容器外框，登记为 N·A |
| ICO-36 | <head> favicon | N·A | <head> 无 favicon；WebView2 宿主不加载网页图标，补了也不显示且会新增请求 |
| U1 | 源码 webview2/ui.html | ✅ | |
| U2 | dist/webview2/ui.html | ✅ | |
| U3 | dist_min/webview2/ui.html | ✅ | |
| U4 | 单文件版 exe 内嵌 ui.html | ✅ | |
| U5 | 成品包 zip 内 webview2/ui.html | ✅ | |
| U6 | 成品目录 exe 同级外置 webview2/ui.html | ✅ | |

## 13. A9 追加轮（用户本轮显式要求，超出纯换肤范围）

| ID | 名称 | 状态 | 落点 |
|---|---|---|---|
| A9-01 | 投屏超过 2 路后底部缩略条黑屏 | ✅ | `_cs/Cast.cs` 新增 `/snap/<slot>` + `ui.html` 缩略条改单帧轮询 |
| A9-02 | 全屏时底部缩略条缺「停止」按钮 | ✅ | `.cast-thumb-stop[data-stop]` + 事件委托 |
| A9-03 | 搜索结果改为点击整行进入树状结构 | ✅ | `data-search="1"` / `fsOpenSearchDir()` / dblclick 兼容 |

> A9 三项按 A9 规则追加 ID、重算分母、**沿用已锁定的三态令牌与图标规范**，
> 未新造设计语言。它们需要改 JS 函数体与 C# 端点，已在最终报告里标注「超出纯换肤」。

## 14. 风险最高的 5 个 ID

1. **U4** — 单文件版 exe 内嵌 ui.html 与 ico，只有重编译才会更新（漏了界面还是旧的）。
2. **ICO-03** — exe 内嵌图标影响任务栏 / Alt+Tab；Windows 图标缓存可能让新图标不立刻显示。
3. **H-01..03** — 三套主题是功能，合并成明暗两套即为功能变更。
4. **A9-01** — 新增 `/snap` 端点必须随 exe 一起重编译，否则外置 ui.html 指向 404。
5. **C-24 / A9-03** — 搜索态单击进树会替换 DOM，浏览器补发的 dblclick 可能落在容器上，
   需 `justRevealed` 保护，否则刚展开的祖先链会被 `fsCollapseAll` 收起。

## 15. break-ui 最坏数据补充的隐藏状态（A2 第 4 点）

| 最坏数据 | 暴露的状态 | 本轮处理 |
|---|---|---|
| 0 个设备 / 断线 | 顶栏置灰、日志等级隐藏、设备树红字 | ✅ P-01/P-04 五态 |
| 无 root | root 胶囊红、提示文案 | ✅ C-01 / F-07 |
| 搜索 0 命中 / 500 条截断 | 空态 / 截断提示 | ✅ P-04 五态 |
| 6 路投屏同时开 + 全屏 | 底部缩略条每路都要有画面和停止按钮 | ✅ A9-01 / A9-02 |
| 超长包名 / 超长日志 / emoji | 换行不横向溢出、line-clamp、title 全文 | ✅ C-14 / C-18 / K-07 |
| 请求超时 / 加载中 | 按钮 busy 不可重复点、8 秒兜底 | ✅ C-06 / P-08 |
| 200% 缩放 / 820×560 最小窗 | 顶栏不换行、5 页签不溢出、34px 折叠栏 | ✅ D-02..05 |

## 16. A11 追加轮（2026-11-15 用户新需求，分母 v2 → v3）

| ID | 名称 | 状态 | 落点 |
|---|---|---|---|
| A11-01 | 顶栏 9 色强调色切换（红/黄/蓝/白/紫/黑/绿/橙/粉） | ✅ | `#accent-pick` / `_gen_accent.py` 生成 27 条 `:root[data-theme][data-accent]` |
| A11-02 | 强调色与明暗主题正交（切色不动背景） | ✅ | `data-accent` 只覆盖 `--accent/--accent-soft/--on-accent`；`_check_accent_dom.py` 13 项实测 |
| A11-03 | 自定义 ADB 指令：3 输入框 + 卡片墙 + 一键下发 | ✅ | `#custom-panel` / `#cm-grid` / `post('customsave')` + `CustomStore.cs` |
| A11-04 | 多指令换行顺序执行 + 失败跳过 + 原生回显 | ✅ | `customExpand()` 线性队列 + `end` 钩子驱动；`377/_test_custom_cmd.py` 52 项 |
| A11-05 | 官方节点：延时（自定义间隔）/ 循环（重复上一条） | ✅ | `{t:'delay'}` / `{t:'loop'}`，第一行禁节点、节点必须间隔命令 |
| A11-06 | Liquid Glass 玻璃层：living backdrop + 玻璃 chrome + 卡片光学 | ✅ | `GLASS LAYER` 段落 + `_check_glass.py` 20 项实测 |
| A11-07 | 应用图标 v2（车载中控 + 测试工程师 + 联网） | ✅ | `_icon_v2.py` 7 尺寸 ico + SVG 源 + 顶栏/加载层同源 |
| A11-08 | 性能 / 闪退隐患修复（含 GUI 下 q/exit 硬退出根因） | ✅ | `App.GUI_MODE` 守卫 + 线程委托兜底 + screencap 超时 |

> A11 各项**只新增**：不删旧 ID、不改既有断言语义，分母由 456 增至 477，覆盖率仍按
> `✅ /(总项−N·A)` 计算。8 项里 2 项（A11-06/07）是纯表现层，6 项需要改 JS/C#，
> 已在 `RESKIN-FINAL-REPORT.md` 标注「超出纯换肤」。

## 17. A12 追加轮（2026-11-15 用户 13 条需求，分母 v3 → v4）

| ID | 名称 | 用户需求 | 状态 | 落点 |
|---|---|---|---|---|
| A12-01 | 自绘标题栏（颜色 + 字体跟随用户设置） | ①②⑧ | ✅ | `FormBorderStyle.None` + `#titlebar`；`--chrome`/`--font-ui` 令牌；headless 实测 dark `(22,21,24)` / light `(254,254,255)` / eye `(255,251,240)` |
| A12-02 | 设置抽屉：主题 / 9 色 / 字体 / 关闭应用 四合一 | ⑤⑥⑧ | ✅ | `#set-mask` + `#set-theme`+`#set-accent`+`#set-font`；`post('prefsave')` → ini `prefs=`（base64） |
| A12-03 | 全局字体切换（内置 Inter / JetBrains Mono + 系统字体） | ⑥ | ✅ | `_v12_fonts.css` 两枚 base64 woff2；34 处硬编码 `font-family` 全部改 `var(--font-ui)`/`var(--font-mono)` |
| A12-04 | 使用说明面板（12 章 + 指令目录运行时扫描 + 搜索） | ⑦ | ✅ | `#help-mask`/`#help-nav`；`helpCmdCatalog()` 扫 `quickGroups`；颜色字体均走令牌 |
| A12-05 | 「文本」页签 + 记事本能力（C# 真实读写，保编码/换行） | ④ | ✅ | `#page-text` + `#page-text` 编辑器；`textopen`/`textsave` 路由；UTF-8/BOM/GBK/UTF-16 LE + CRLF/LF 原样保留 |
| A12-06 | 文件页：⇄ 左右换边 + 列宽鼠标拖拽（参考资源管理器） | ⑩⑪ | ✅ | `fsSwapSides()`；`fsColDown()` 4 个表头夹子写 `--w-name`/`--w-size`，localStorage 持久化 |
| A12-07 | 结果图空态 + 去掉顶栏多余强调色小圆点 | ③⑨ | ✅ | `uiResultImgErr()` + `alt=""`；删除 `.acur` 与 `theme-btn`/`accent-btn`/`accent-pick` |
| A12-08 | 无边框窗口窗口能力回填（拖动/缩放/最小化/最大化/关闭） | ①② | ✅ | `windrag`(ReleaseCapture+WM_NCLBUTTONDOWN) / `winresize2`(movementX×dpr 累加) / `winmin` / `winmax`(MaximizedBounds=WorkingArea) / `winclose`；`_smoke_win.py` 12 项 |

> A12 共 8 项，全部为**新增能力**，未删除任何旧 ID。删除项仅 3 个顶栏元素
> （`theme-btn` / `accent-btn` / `accent-pick`，功能迁入设置抽屉）与 3 个 onclick
> （`toggleTheme` / `sendCmd` / `toggleAccentPop`），逐条登记在 `_gate_invariants.py` 的
> `A12_REMOVED` 并写明理由；页签与页面的追加机制由「必须完全相同」升级为
> 「前缀一致 + 末尾追加须登记」，故 `text` / `page-text` 合法追加。分母由 477 增至 485。

> 需求 ⑫「UI 再优化，去 GitHub 参考」落在表现层：页签图标化（6 枚内联 SVG）、
> 统一滚动条/焦点环/按压态、`--tb-h`/`--set-w`/`--help-w`/`--grip-w` 等新令牌，
> 不单列 ID，随 A12-01/02/04 一并验收。

## 18. A13 追加轮（2026-11-15 用户 9+5+2 条需求，分母 v4 → v5）

| ID | 名称 | 用户需求 | 状态 | 落点 |
|---|---|---|---|---|
| A13-01 | 删掉标题栏品牌文字「网联服务_Adb_Tool」 | ① | ✅ | 删 `.tb-name`；标题栏结构改为 `.tb-drag`（logo + `#tb-sub`）→ `#tb-status` → `.tb-drag-mid` → `.tb-right` → `.tb-btns` |
| A13-02 | root / 无线 / 日志 / 设备 四点化，只画圆点不显示文字 | ②③④ | ✅ | `#tb-status` 四点统一 26px 命中区 + 9px 圆心；`.rtxt`/`.ltag`/`.lv`/`#wadb-txt`/`.device .id`/`.sep`/`.soc` 全部 `display:none`；语义改由 `.tb-tip` 即时 tooltip 承担（60ms 防抖，非原生 title 的 1s） |
| A13-03 | 多行指令按 Enter 逐行顺序执行 | ③ | ✅ | `_txQ` 队列 + `end` 回包驱动 `txNext()`；不拼 `a;b`（`:car`/`stweak` 不是 shell 前缀）；停止按钮整条队列作废 |
| A13-04 | `WM_NCHITTEST` 返回 `HTLEFT`/`HTRIGHT` | ⑨ | N·A | 用户明确「维持现状不做」。现有方案是页面侧 5px 热区算位移 → `winresize2{dir,dx,dy}` → C# 套 `Bounds`；无 `WS_THICKFRAME` 时原生 NC 缩放 delta 恒 0，反而不可用 |
| A13-05 | 窗口圆角，同时兼容 Win11 与 Win10 | ⑧ | ✅ | Win11（build ≥ 22000）`DWMWA_WINDOW_CORNER_PREFERENCE=2` 抗锯齿；Win10 用 `SetWindowRgn(CreateRoundRectRgn)` 兜底（1px 台阶，物理限制）；半径 `8 × dpi/96`，最大化传 `IntPtr.Zero` 取消；角部热区 5px → 12px |
| A13-06 | 外接 27 寸屏下最大化未铺满（跨屏） | ⑥ | ✅ | `MaximizedBounds` 只在 `OnLoad` 算一次、缓存了笔记本屏尺寸；改 `WM_GETMINMAXINFO` 每次按 `Screen.FromHandle(Handle).WorkingArea` 实时回答；`_smoke_win.py` 实测 1920×1040（不盖任务栏） |
| A13-07 | 齿轮并入标题栏右、整行 `.topbar` 删除 | ⑦ | ✅ | `.titlebar` 接管 `.topbar` 的 `backdrop-filter:blur(20px) saturate(180%)` 与 `inset 0 -1px 0` 描边，页签直接贴标题栏 |
| A13-08 | 日志等级一直「未设置」根因修复 | ⑤ | ✅ | `LoadDeviceInfo()` 里 `if (!LoadCarInfo()) return;` 早退在 `getprop persist.log.tag` **之前**，车机属性为空时等级永不读取；改为早退前独立读取并删掉重复段 |
| A13-09 | 终端输入框支持换行 + 四按钮去中文只留 icon | 终端 | ✅ | `<textarea rows="1">` + `txAutoGrow()`（`max-height:1.55em*5` 后滚动）；Shift+Enter 换行；执行/停止/清屏/复制 `width:34px`、`title` + `aria-label` 保留可发现性，腾出的宽度给输入框 |
| A13-10 | 删侧栏「指令」小标题 + 输出区点空白展开/收起 | 指令界面 | ✅ | `qnav-title` 整段删除（`var html = '';`）；`fb-head` 挂 `fbHeadToggle()`，`closest('button,.fbtn,.fb-acts,input,select,a,textarea')` 命中时不触发 |

> A13 共 10 项：9 项落实现、1 项（A13-04）按用户指令 N·A。删除项 `.topbar` / `.tb-name` / `qnav-title` 均非 `id` 级元素，不占 ID 基线；新增 3 个 ID 级落点（`tb-status` / `log-dot` / `fbHeadToggle`）逐条登记在 `_gate_invariants.py` 的 `A13_ADDS`，未放宽任何断言。分母由 485 增至 495。

> A13-02 的颜色全部走令牌（`--accent` / `--lv-v|d|i|w|e` / `--ok` / `--err` / `--border`）；`_v13.css` 里两处字面量色（V 级圆点内描边、tooltip 阴影）已提成 `--tb-dot-ring` / `--tb-tip-shadow`，门禁「组件样式零硬编码色」因此通过。

## 19. A14 追加轮（2026-11-15 第 2 批 13 条 + 第 3 批 8 条，分母 v5 → v6）

### 19.1 网联服务分组（第 2 批）

| ID | 名称 | 状态 | 落点 |
|---|---|---|---|
| A14-01 | 「指令」页在「指令执行」下面新增「网联服务」分组 | ✅ | `quickGroups` 第 2 组；`_check_a14.py` 断言「紧跟指令执行」 |
| A14-02 | AI智能推荐后台说明改为「进入AI智能推荐后台」，并在网联服务里也放一张 | ✅ | 原卡片 `desc` 改写 + 新组内同 `cmd:'airec'` 卡片 |
| A14-03 | 配置中心后台 | ✅ | `cmds.ini [cmd.wsconfig]` → `am start -n space.syncore.cockpit.configcenter/...DefaultConfigDisplayActivity` |
| A14-04 | 支付宝后台 | ✅ | `[cmd.wsalipayset]` → `am start -a android.intent.action.VIEW -d ampe://setting` |
| A14-05 | 上传支付宝日志 | ✅ | `[cmd.wsalipayup]` → `... -d ampe://uploadlog` |
| A14-06 | 导出支付宝日志 | ✅ | `:wsalipay` → `桌面/logcat/<日期>/alipay/applog`（强制打包，避开轮转竞态） |
| A14-07 | 导出微信小程序日志（两个路径重名） | ✅ | `:wswmpf` 主 `/sdcard/...`、备 `/storage/emulated/0/...`；落点名 `xlog_sdcard` / `xlog_storage` 天然不撞 |
| A14-08 | 导出车载微信日志（两个目录） | ✅ | `:wswx` → `日期/wxmsg/log` + `日期/wxmsg/autowechat`，失败互不影响 |
| A14-09 | 打开星河云埋点（含重启等待） | ✅ | `:sxlog` → 两个 setprop → reboot → `WaitBoot(60)` → privacy_enabled + did/android_id；`GUISTOP` 可中断 |
| A14-10 | 查询星河云埋点设置 | ✅ | `:sxlog get` 回读三个值 |
| A14-11 | 设置星河云埋点 true | ✅ | `:sxlog set` 写入并回读确认 |
| A14-12 | 查询设备ID | ✅ | `:wsdevid` → `navi.did` / `android_id` / `navi.uuid`（用户原文给的命令与「设备ID」不符，已按名称实现并保留可改口） |
| A14-13 | 打开星河埋点云 / 讯飞 IOT 云 | ✅ | `:url <地址>` → `Process.Start(UseShellExecute)` 调桌面浏览器 |

### 19.2 UI 八条（第 3 批）

| ID | 名称 | 状态 | 落点 |
|---|---|---|---|
| A14-14 | 启动动画换最新图标 + 跟随强调色 | ✅ | `.splash .cat svg` 换成与 ico 同源的线稿（信号双弧 + 中控屏 + `>_` + 底座）；`color:var(--accent)` |
| A14-15 | 左上角图标太小 | ✅ | `.tb-logo svg{width:calc(var(--tb-h)*.54)}`（42px 标题栏 → 约 23px，原 15/18px） |
| A14-16 | 白天/护眼边界与按钮区分不明显 | ✅ | light `--border .29→.44`、`--edge .055→.10`、按钮给 `--well` 面、导航选中加左侧色条、`.qcat` 加粗 |
| A14-17 | 护眼主题同样要清晰 | ✅ | eye `--border .28→.55`（实测对比度 1.4→2.05:1） |
| A14-18 | 深色下设置字体下拉白底白字 | ✅ | 原生 select 弹层换成自绘 `.a14-selpop`（捕获阶段拦 mousedown，回写 value + 派发 change） |
| A14-19 | 深色下文本页编码/换行下拉同样白底 | ✅ | 同一套自绘浮层，动态生成的 select 也覆盖 |
| A14-20 | 设置里两处中文去掉 | ✅ | 字体预览 `Adb_Tool 12345 ABCdef`（applyFont 里一并改写）；关于 `adb_Tool` |
| A14-21 | 字体大小 小/中/大，整页跟随 | ✅ | `#set-fsize` 三段 → `post('uizoom')` → C# `WebView2.ZoomFactor` 0.90/1.00/1.15；偏好存 `prefs={...,size}` |

> A14 共 21 项：13 条功能 + 8 条 UI，全部落地。新增 ID 级落点仅 `set-fsize`（+ onclick `setSize`），登记在 `_gate_invariants.py` 的 `A14_ADDS`；新增 C# 消息 kind `uizoom`（不进 JS kinds 基线，单独由 `_check_a14.py` 覆盖）。分母由 495 增至 516。

## 20. A15 追加轮（2026-11-15 第 4 批，分母 v6 → v7）

用户在讨论模式提了 16 条，最终合并成 19 项落地。这一轮的特点是**一半在补"用久了才发现的别扭"**（点任务栏收不起、搜索框白边、下拉一滚就关），另一半是把交互补到和 Apple 一致的手感。

| ID | 名称 | 状态 | 落点 |
|---|---|---|---|
| A15-01 | 设置 → 显示选项：跟随系统外观 | ✅ | `#set-auto`；`sysDark()` 走 `matchMedia('(prefers-color-scheme: dark)')`，变更事件直连 `applyTheme` |
| A15-02 | 显示选项：OLED 纯黑 | ✅ | `[data-oled="1"]` → `--bg:#000000 --surface:#0e0e10`，同时 `backdrop-filter:none` |
| A15-03 | 显示选项：护眼三档（标准/浅/深） | ✅ | `[data-eyelevel="light|deep"]`；只动底色色温与卡片，**不动文字色**（文字对比度是算过的） |
| A15-04 | 日志等级：hover 看当前值 | ✅ | `.v15-tip` 浮层，60ms 延迟，同时显示设备端 `persist.log.tag` 与本工具显示阈值 |
| A15-05 | 日志等级：点击设设备端等级 | ✅ | `.v15-lvseg` 五段 V/D/I/W/E → `post('logset',lv)` → `setprop persist.log.tag` → 600ms 后 `logget` 回读确认 |
| A15-06 | 日志等级：本工具显示阈值（与设备端分离） | ✅ | 第二条 `.v15-lvseg` 只过滤界面，不下发设备；两个状态分开存，避免"以为改了设备" |
| A15-07 | 设备管理：hover 看当前设备 | ✅ | 徽章提示显示序列号 / 型号 / USB 或无线 / `adb devices` 状态 |
| A15-08 | 设备管理：断开与切换 | ✅ | `devlist` → 列表行；点非当前行 `devswitch`（改 ini `serial=` + 重读车机信息）；断开仅对含 `:` 的 TCP 序列号发 `adb disconnect`，USB 明确提示拔线 |
| A15-09 | 指令执行新增投屏六条（scrcpy） | ✅ | `:scrcpy 0/4/1/3/9/10`（主屏/副屏/后排屏/HUD/PHUD-B/PHUD-C）；`TaskCmds.DoScrcpy` 支持中文名与裸数字 |
| A15-10 | scrcpy 安装与探测（装完不用重启） | ✅ | `winget install Genymobile.scrcpy`；探测同时读进程 PATH、注册表 HKCU/HKLM PATH、`WinGet\Packages\Genymobile.scrcpy_*\scrcpy-win*\scrcpy.exe`（5.0.1 的 Links 里没有 shim） |
| A15-11 | 强调色 9 → 13 色（Apple 语义色） | ✅→扩至 16 | A16-04 再加纯白/护眼白/玻璃白，本行结论仍成立 | 生成器重写：39 条规则全部 ≥3:1（对表面）且 ≥4.5:1（其上文字）；`--on-accent` 按亮度自动选；`white/black` 合并进 `graphite` 并迁移旧偏好 |
| A15-12 | 页签翻页动效（按方向） | ✅ | `transform-origin:left bottom` / `right bottom` + `rotateY` + 折角光影；`animationend` 与 520ms 双保险摘 class（`transform` 会成为 fixed 后代的包含块） |
| A15-13 | 页签边界与间距（玻璃风分不清） | ✅ | 浅色/护眼改实体面（`--surface` + `--v15-edge` 边框 + 落地投影），深色保留玻璃但补可见描边；间距 14→18、gap→6、高 34→36 |
| A15-14 | 搜索框四角露白边 | ✅ | 根因是 A13 给 `.qsearch` 外壳刷了 `--surface`，白底从内部胶囊四角漏出；改外壳透明、只给 `input` 一个 `--surface-2` 凹陷面 |
| A15-15 | 下拉浮层一滚就关 | ✅ | 原 `document.addEventListener('scroll', closePop, true)` 捕获所有滚动；改为浮层内滚动忽略、外部滚动 `repositionPop()` 跟随、锚点滚出视口才关 |
| A15-16 | 字体扩充到 39 项 / 七分组 / 未安装灰显 | ✅ | 分组：内置 3、中文系统自带 11、中文需安装 8、西文系统自带/需安装、等宽、其它；`installed()` 用 canvas 测宽（`document.fonts.check` 对系统字体不可靠） |
| A15-17 | 点任务栏不能收起窗口 | ✅ | 窗口 style 缺 `WS_MINIMIZEBOX(0x00020000)`；`CreateParams` 补位 + `WM_ACTIVATE(WA_INACTIVE)` 后查前台类名 `Shell_TrayWnd` 兜底 |
| A15-18 | 从任务栏开合与 Apple 一致 | ❌ 已撤销 | **A16-01 判定此做法会留下小窗口，整段删除**；`DockRect()` 取任务栏位置 → `SetWindowPos` 11 帧 × 15ms 插值（ease-out cubic）；`WM_GETMINMAXINFO` 的 `ptMinTrackSize` 放到 1，否则小于 `MinimumSize` 会被系统夹回 |
| A15-19 | 启动动画仍是旧黑猫 | ✅ | 网页 `.splash` 上一轮已换，但 WebView2 初始化 0.5–2s 显示的是 **C# GDI+ 的 `SplashPaint`**；重画新图标几何，颜色由 `AccentColor()` 跟 `App.ACCENT` 13 色 |

> A15 共 19 项，全部落地。新增静态 id 12 个（`a15-sec-display` / `set-auto` / `set-display-hint` / `set-eyelevel` / `set-oled` / `v15-lvdev` / `v15-lvshow` / `v15-lvstate` / `v15-devh` / `v15-devrows` / `v15-devrefresh` / `v15-devoff`），登记在 `_gate_invariants.py` 的 `A15_ADDS`；**新增 kind 0 个**——日志/设备的回推走 `window.v15Msg` 覆写 + C# 既有 post 通道（`logget` / `logset` / `devlist` / `devswitch` / `devdisconnect`），消息契约没有扩。分母由 516 增至 535。


---

## 21. A16 追加轮（2026-11-15 第 5 批九条，分母 v7 → v8）

这一批的来源是 9 张截图 + 讨论模式逐条过。九条里有四条同一根因（弹窗生命周期），
两条同一根因（用改窗口尺寸做动画），剩下的是性能与持久化。

| ID | 名称 | 状态 | 落点 |
|---|---|---|---|
| A16-01 | dock 打开窗口很小、点不动 | ✅ | 根因是 `PlayOpenAnim()` 用 `SetWindowPos` 把真窗口缩到 168×100 再分 11 帧放大：①目标读运行时 `Bounds`，重入一次就自我叠加；②WebView2 初始化堵 UI 消息泵 1~3s，帧整段丢失；③任何中断都停在中间尺寸且不最小化。**整段删除**（`DockRect` / `AnimateBounds` / `PlayOpenAnim` / `PlayMinimizeAnim` 已零残留） |
| A16-02 | 窗口最小尺寸兜底 | ✅ | `WM_GETMINMAXINFO` 的 `ptMinTrackSize` 从 `1` 恢复成 `MinimumSize`（A15-18 为做缩到 160×96 放开了系统下限，等于允许残留 `SetWindowPos` 钉住小窗口）；`RefreshSane()` 记 `_sane`，`EnsureSaneBounds()` 在 `OnShown` / `WM_ACTIVATE` / 异常时拉回，`_sane` 也不合法才按工作区居中开 1100×760 |
| A16-03 | 开合动效改内容层 | ✅ | 窗口一步到位，`#frame` 加 `.v16-in`：`opacity .001→1` + `transform:scale(.94)→1`，200ms；`hookOpenAnim()` 等 splash `gone` 再挂（不等就看不见）；`prefers-reduced-motion` 降级 |
| A16-04 | 强调色 13 → 16（纯白/护眼白/玻璃白） | ✅ | 生成器 `NEUTRAL` 表 + 16 色 `ORDER`；色板 `repeat(4,40px)` 4×4；`ACCENT_ORDER` 与 `Program.cs` ini 白名单同步扩到 16 |
| A16-05 | 三白在浅色/护眼下压成中性灰 | ✅ | 直接把白压到 3:1 会得到 `#AA8E8E`（那 1% 暖调被放大成玫瑰灰）。改按 `(色相, 饱和度)` 在 HLS `L=0.62` 起算再压暗：纯白 `#939393` / 护眼白 `#9C9284` / 玻璃白 `#8E949E` |
| A16-06 | 投屏六卡并入「指令执行」，分类统一「投屏」 | ✅ | 独立组「投屏（scrcpy）」删除；6 张卡 `cat:'投屏'`；有搜索框后分类不再承担导航职责 |
| A16-07 | 投屏页「用 scrcpy 打开」按钮 | ✅ | `castOpenScrcpy()` 按选中屏发 `:scrcpy <displayId>`；内置通道帧率不够时一键换原生窗口 |
| A16-08 | 弹窗互斥（后开抢占先开） | ✅ | 根因：弹窗挂在徽章里，`.titlebar` / `.tabs` 各有 `backdrop-filter` 形成层叠上下文，DOM 靠后的压住靠前的，祖先还有 `overflow` 裁剪。改 body 级 `position:fixed` portal + `placePop()` 算坐标 + 单例 `popCur`；`openLogPop` / `openDevPop` 互先 `detachPop`；`closeAllPops()` 统一收口 |
| A16-09 | 弹窗开着不再冒 hover 提示 | ✅ | `bindHover` 只听徽章 `mouseenter`，弹窗开着时鼠标在弹窗上仍算徽章范围。`showTip()` 开头 `if (anyPopOpen()) return;` |
| A16-10 | 设备弹窗显示不全 | ✅ | 同 A16-08 根因；另给 `.v15-pop` 加 `max-height:calc(100vh - 20px)` + `overflow:auto` |
| A16-11 | 投屏低帧率（raw 抓帧 + 本地 JPEG + 自适应选路） | ✅ | `CastGrabRaw`（`exec-out screencap -d N` 不带 `-p`）+ `CastEncodeJpeg`（R/B 交换 → 缩 1280 宽双线性 → JPEG q72）；**首帧两条路各测一次选快的再固定**（raw 允许 15% 容差）——原以为 raw 必赢，实测无线 adb 8MB/s 下 raw 734ms 输给 png 656ms，USB3 才反过来 |
| A16-12 | scrcpy 画质参数 + stderr 抽干 | ✅ | `--max-size=1600 --max-fps=60 --video-bit-rate=16M --no-audio --print-fps`；`--stay-awake` 与 `--no-control` 互斥（5.0.1 直接报错退出）故去掉；`--print-fps` 每秒写 stderr 而无人读，Windows 管道 4KB 写满后 scrcpy 阻塞 → 起后台线程 `ReadLine` 抽干 |
| A16-13 | 偏好统一持久化 | ✅ | 不是"没存"而是"存了不读"：`prefsApply` 只认 `font/custom`、字号在 v14 层二次解析、`logshow` 只写不读、显示三项没进 prefs。改一份 schema：`applyAllPrefs()` 吃 `size/logshow/oled/eye/auto/tabOrder` |
| A16-14 | tab 拖拽换位并记忆 | ✅ | pointer 事件（HTML5 `draggable` 在 WebView2 长按有系统延迟）+ 6px 死区 + `elementFromPoint`/`insertBefore` 实时换位 + `suppressClickUntil` 吃掉松手后的 click；顺序存 `_prefs.tabOrder`，`v15SyncTabOrder()` 重算翻页方向 |
| A16-15 | 9 条 adb 查询指令 | ✅ | `cmds.ini` 新增 `adbver/windisp/aid/osver/devs/adbst/adbsp` 七段 + 修 `mem`（30→40 行）/`screen`（补 density）；**`adb root` 按用户要求不做**，用 `kill-server` 顶"停止 adb 服务" |
| A16-16 | 快捷指令搜索架构（为指令堆积做准备） | ✅ | 一次性索引（`name/desc/cmd/cat/alias/kw/组名`）+ 空格分词全命中 + 命中位置加权 + 结果上限 80；**防抖只放事件入口 `v16QuickInput`，`onQuickSearch` 保持同步**（替换它会让同步调用者"点了没反应"） |

> A16 共 16 项，全部落地。新增静态 id **0 个**、kind **0 个**、onclick **1 个**（`castOpenScrcpy`），登记在 `_gate_invariants.py` 的 `A16_ADDS`；消息契约零扩展（投屏帧走既有 `/snap/` HTTP 端点，仅 MIME 由 PNG 改 JPEG）。**分母由 535 增至 536。**
>
> 两条被撤销的旧结论，别照着回改：
> - **A15-18「从任务栏位置起做开合动画」整段删除** —— 它必然留下小窗口（A16-01）。
> - **A15-11 的 13 色不是终点** —— A16-04 扩到 16 色，三白在浅色下另有起算规则（A16-05）。

新增校验入口：`_v16_checks.py`（78 条落点断言），已挂进 `verify_all.py` 的第 5.6 段；`_check_apple_release.py` 增加 15 个 A16 内嵌字节标记与手册 §27 检查。

---

## 22. A17 追加轮（2026-11-15 第 6 批，分母 v8 → v9）

这一批是交付后反馈：八条 + 两条追加。三条是上一轮留下的尾巴（强调色记忆、关闭两次、开合动效），
两条是新能力（icon 重做、scrcpy 内嵌）。

| ID | 名称 | 状态 | 落点 |
|---|---|---|---|
| A17-01 | 强调色未记忆 | ✅ | 白名单原来在 `Program.cs` 与 `GuiWeb.cs` 各一份，扩 16 色时只改前者 → 收口成 `Prefix.ACCENTS` + `NormalizeAccent()`；`SaveAccentPreference` 不再"没 ini 就 return"；页面另存 `_prefs.accent`（`setAccent` 包一层 + `applyAllPrefs` 回填） |
| A17-02 | 恢复开合动效（不碰窗口尺寸） | ✅ | `.frame.v17-in`（`scale(.93)→1`，260ms，**只动 transform**）+ `.v17-out`（130ms）；C# `PlayOutThen()` 播完才最小化/关闭；`v17InRestore()` 复位。A16 的"等 splash 消失再补 class"关掉（会晚 300ms 再放一次） |
| A17-03 | 应用 icon 黑白灰 + 黑底 | ✅ | `_icon_v2.py`：`C_TOP #2E2E2E` / `C_BOT #050505`，右下压暗从 `[0,0.05,0.30]` 改纯黑（原偏蓝留下 15/255 饱和差）；全图最大饱和差 = 0 |
| A17-04 | 页面图标与 ico 同源 | ✅ | `ui.html` 顶部 `<defs>` 只画一份 `#appmark-glyph`，启动层与标题栏各一个 `<use>`；启动层 `color:var(--accent)`，标题栏 `var(--mark-fg)` |
| A17-05 | 浅色窗口边界不明显 | ✅ | `_v17.css` §2 三条：实边 `rgba(48,48,54,.72)`（原 .55）+ 顶高光 + 6px/24px 内阴影；深色不动 |
| A17-06 | 直角改圆角 | ✅ | 侧栏 / 终端页 / 输入行各自成卡（8px 内缩 + 12px 圆角）；投屏页、文件页同步内缩，避免切页跳动 |
| A17-07 | 关闭要点两次 | ✅ | 根因是 `OnFormClosing` 的清理（停 watcher / `CastStopAll` / `Thread.Abort`）卡在 adb 同步读上且跑在 UI 线程。改：播 130ms → `Hide()` → `BeginInvoke(Close)` → 看门狗 2.5s 硬退；`_closing` 拦住任务栏收起 |
| A17-08 | 启动层高斯模糊渐变 + 图标跟随强调色 | ✅ | 网页层：三段竖向渐变（`--splash-g0/1/2`）+ 强调色光晕 `filter:blur(56px)`；C# `SplashPaint` 改 `PathGradientBrush`；图标取 `AccentColor()` |
| A17-09 | scrcpy 内嵌到应用内 | ✅ | `SetParent` 把 scrcpy HWND 塞进 `_castHost` Panel（精确盖 `#ce-stage`）；页面按**比例**报区域；`--window-title` 唯一名 + `MainWindowHandle` 兜底；`CreateNoWindow=true`；stdout/stderr 抽干；切页 `castembedhide`；关窗 `ScrcpyEmbedStop` |
| A17-10 | 内嵌/内置模式记忆 | ✅ | `_prefs.castMode`，进投屏页默认 `embed`；用户主动切内置后不再强行拉起 |
| A17-11 | 任务栏图标 + 标题去前缀 | ✅ | `Text = "Adb_Tool"`；`TrySetCatIcon()` 读同目录 ico，缺失时 `ExtractAssociatedIcon` 兜底；`build_gui.bat` 保证 ico 进 dist |
| A17-12 | 色板分组标签（参考 Edge） | ✅ | 13 彩色后插分隔线 + 「中性色 · 浅色/护眼下会压成灰」；见 `docs/参考-Edge主题设置与同类实现.md` §五 |
| A17-13 | Edge 主题设置调研 | ✅ | `docs/参考-Edge主题设置与同类实现.md`：对齐项 / 差距 / 5 条建议（1 条已落地，4 条标注成本与风险） |

> A17 共 13 项，全部落地。新增静态 id **8 个**（`appmark-bg` / `appmark-glyph` / `cast-embed` /
> `cast-mode` / `ce-hint` / `ce-stage` / `cm-builtin` / `cm-embed`）、onclick **2 个**
> （`v17CastEmbed` / `v17CastBuiltin`）、后端 kind **4 个**（`scrcpyembed` / `scrcpyembedstop` /
> `castembedrect` / `castembedhide`），全部登记在 `_gate_invariants.py` 的 `A17_ADDS`。
> **分母由 536 增至 537。**

新增校验入口：`_v17_checks.py`（63 条落点断言），已挂进 `verify_all.py` 第 5.6 段（25 → 26 项）。

> 两条被本批修正的旧结论：
> - **A16-01 删掉开合动效是对的，但"没有动效"不是终态** —— A17-02 用渲染层 transform 把动效加回来了。
> - **A16-12 给 scrcpy 加的 `--print-fps` 只服务"外部窗口"这种形态** —— 内嵌时反而要关掉（帧率数字给谁看？），
>   见 `Scrcpy.LaunchEmbedded` 里的注释。
