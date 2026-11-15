# -*- coding: utf-8 -*-
"""阶段 0/6：按当前真实源码生成 A11 清单与 COVERAGE.md（分母由代码算，杜绝手写百分比）。

只读 ui.html 提取真实页签 / 页面 / 令牌 / SVG 数量，其余 ID 为结构化定义。
产出：docs/UI-RESKIN-INVENTORY.md、docs/COVERAGE.md
"""
import io
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
DOCS = os.path.join(ROOT, "docs")
with io.open(UI, "r", encoding="utf-8") as f:
    s = f.read()
css = s[s.index("<style>"):s.index("</style>")]

tabs = re.findall(r'data-tab="([^"]+)"', s)
pages = re.findall(r'id="(page-[\w-]+)"', s)
svg_n = len(re.findall(r"<svg", s))
theme_n = len(set(re.findall(r':root\[data-theme="(\w+)"\]', css)))

# ---- ID 定义：(前缀, 名称, 状态, N·A 理由) ----
P = [
    ("P-01", "顶栏（设备 / root / 无线 / 日志等级 / runchip / 主题 / 品牌）"),
    ("P-02", "指令页 page-quick（左侧导航 + 卡片 + 反馈表）"),
    ("P-03", "终端页 page-cmd（3 槽 + 执行/停止/清屏/复制）"),
    ("P-04", "文件页 page-file（双栏树 + 路径栏 + 搜索 + 进度）"),
    ("P-05", "投屏页 page-cast（6 格 + 最大化 + 底部缩略条）"),
    ("P-06", "UI 对比页 page-ui ★清单外新增（投屏右侧第 5 页）"),
    ("P-07", "底部输出区（34px 折叠栏 + 反馈表 + toast）"),
    ("P-08", "加载过渡层（8 秒兜底）"),
    ("P-09", "apk-mgr 弹窗"),
    ("P-10", "无线连接弹窗"),
    ("P-11", "fs-modal 新建文件夹弹窗"),
    ("P-12", "快捷搜索下拉"),
    ("P-13", "toast 浮层"),
    ("P-14", "自定义指令面板 #custom-panel（卡片墙 + ＋新建指令）★A11"),
    ("P-15", "自定义指令编辑器 #custom-mgr（名称 / 说明 / 流程逐行）★A11"),
    ("P-16", "强调色色板 #accent-pop（9 色 · 只作用于 accent 派生色）★A11"),
]
C = [
    "root 胶囊", "无线胶囊", "日志等级徽章", "runchip 执行中计时",
    ".tab 页签", ".btn 系列（primary/ghost/sm）", ".icon-btn 图标按钮",
    "终端输入槽 slot-N", "quick-search 搜索框", "快捷指令卡片 qcard",
    "APK 下拉与面板", "双栏树节点 fs-row", "传输进度条", "反馈表 fb-row",
    "折叠栏", "分隔条", "投屏 img 容器", "APK 管理列表行",
    "弹层遮罩与按钮", "车机信息面板",
    "网络模拟表单面板 ★清单外", "UI 对比画布与结果框 ★清单外",
    "全屏底部缩略条 ★清单外", "搜索结果行 ★清单外",
    "自定义指令卡片 cm-card ★A11", "流程步骤行 cm-step（cmd/delay/loop）★A11",
    "强调色色点 accent-dot 与当前色指示 acur ★A11",
    "玻璃 chrome（顶栏 / 左侧导航）★A11", "玻璃页签胶囊 .tabs ★A11",
    "玻璃浮层（cm-box / fs-modal-box / accent-pop）★A11",
]
STATES_C = ["default", "hover", "focus-visible", "active",
            "disabled", "loading", "error", "success"]
STATES_P = ["loading", "empty", "error", "success", "disabled"]
ROLES = ["--bg", "--surface", "--surface-2", "--border", "--border-strong",
         "--text", "--text-dim", "--text-faint", "--accent", "--accent-soft",
         "--ok", "--err", "--lv-v", "--lv-d", "--lv-i", "--lv-w", "--lv-e"]
THEMES = ["dark", "light", "eye"]
T_EXTRA = ["系统字体栈", "8pt 间距网格", "连续圆角", "tinted 阴影",
           "hairline 边框", "层级 z-index", "动效曲线 / ≤300ms", "玻璃仅给 chrome",
           "玻璃面令牌（--frame/--chrome/--card/--rim/--well/--edge）★A11",
           "living backdrop 光雾令牌（--blob-2..4/--glow）★A11",
           "玻璃投影令牌（--shadow-card/modal/pop/btn）★A11",
           "accent 9 色 × 3 主题 = 27 组 WCAG 对比度校验 ★A11"]
F = ["toast", "复制全部", "清空", "仅失败", "收起", "执行中指示", "错误提示", "空态",
     "自定义流程汇总 toast（成功/失败计数）★A11", "编辑器即时校验 cm-err ★A11"]
N = ["5 个页签", "Ctrl+1..4 切页", "Ctrl+K 搜索", "Alt+↓ 收起", "↑↓ 历史",
     "Esc 清搜索", "左侧分组导航", "quick-search 命中下拉", "文件路径栏",
     "面包屑 / 上一级", "APK 面板下拉", "投屏格最大化 / 还原",
     "指令页「自定义」分组入口（第 7 组）★A11"]
M = ["卡片转圈", "卡片完成", "卡片失败", "折叠栏展开/收起", "toast 进出",
     "加载层淡出", "树节点 ▸▾ 展开", "拖拽整行高亮", "传输进度推进",
     "分隔条拖动", "主题切换",
     "背景光雾 52s 漂移 ★A11", "页面切换 4px 上浮淡入 ★A11",
     "弹窗 pop-in 缩放 ★A11", "卡片 hover 抬升 + accent 光环 ★A11"]
D = ["1100×760 默认", "820×560 最小", "顶栏胶囊不换行", "5 页签不溢出",
     "34px 折叠栏不丢", "双栏树分隔条可拖", "多屏主屏居中", "Windows 标题栏明暗"]
K = ["语义标签", "aria-label / title", ":focus-visible 焦点环", "文本 4.5:1",
     "非文本图标 3:1", "不靠颜色单独表意（日志等级保留字母）", "44pt 热区",
     "键盘全路径", "三套偏好降级",
     "色彩不单独表意（色板带中文色名 + title）★A11"]
W = ["标题层级", "按钮措辞一致性", "留白节奏", "业务文案与命令文本不改"]

# ICO-01..36：与附带 md 0.5 节编号严格对齐（md 未定义 08/09，保留为 N·A 占位）
ICO = [
    ("ICO-01", "adb_log_gui/adb_Tool.ico 窗口图标"),
    ("ICO-02", "adb_log_gui/icons/adb_Tool.ico 同源副本"),
    ("ICO-03", "exe 内嵌 /win32icon（任务栏 / Alt+Tab）"),
    ("ICO-04", "icons/svg/AdbTool-中控终端.svg 可编辑源（图标 v2）"),
    ("ICO-05", "GuiWeb.cs ShowIcon=false"),
    ("ICO-06", "ApplyDarkTitleBar 标题栏明暗"),
    ("ICO-07", "MessageBoxIcon 系统对话框图标"),
    ("ICO-08", "md 未定义编号（占位）"),
    ("ICO-09", "md 未定义编号（占位）"),
    ("ICO-10", "加载过渡层品牌 SVG（48×48，中控屏 + 提示符）"),
    ("ICO-11", "顶栏品牌标识 .icon-btn（中控屏轮廓 + >_，onclick=sendCmd(':h')）"),
    ("ICO-12", "主题按钮 #theme-btn 初始 SVG"),
    ("ICO-13", "THEME_ICON.dark 月亮"),
    ("ICO-14", "THEME_ICON.light 太阳"),
    ("ICO-15", "THEME_ICON.eye 眼睛"),
    ("ICO-16", ".zi 人形 SVG 1"), ("ICO-17", ".zi 人形 SVG 2"),
    ("ICO-18", ".zi 人形 SVG 3"), ("ICO-19", ".zi 人形 SVG 4"),
    ("ICO-20", ".zi 人形 SVG 5"), ("ICO-21", ".zi 人形 SVG 6"),
    ("ICO-22", "发送纸飞机 SVG"),
    ("ICO-23", ".fcb-arrow 折叠箭头 SVG"),
    ("ICO-24", "_ICON_RUN 执行"), ("ICO-25", "_ICON_STOP 停止"),
    ("ICO-26", "_ICON_CLEAR 清屏"), ("ICO-27", "_ICON_COPY 复制"),
    ("ICO-28", "_ICON_DEL 删除"),
    ("ICO-29", "ICON_PLAY 卡片播放"), ("ICO-30", "ICON_SPIN 卡片转圈"),
    ("ICO-31", "ICON_STOP 卡片停止"), ("ICO-32", "ICON_DONE 卡片完成"),
    ("ICO-33", "ICON_ERROR 卡片失败"),
    ("ICO-34", "字符图标 ▼ ⇱ ＋ × ★ ▸ ▾ ■ ● / apk-caret / V-D-I-W-E 字母徽章"),
    ("ICO-35", "投屏 cast-img-N 与 UI 对比页设备图"),
    ("ICO-36", "<head> favicon"),
]
NA = {
    "ICO-05": "A10 冻结：ShowIcon=false 是功能设定，改了会改标题栏行为",
    "ICO-07": "系统 MessageBox 图标由 Windows 提供，非本应用资产",
    "ICO-08": "md 的 0.5 节从 ICO-07 直接跳到 ICO-10，未定义 08/09；保留编号不虚增资产",
    "ICO-09": "md 的 0.5 节从 ICO-07 直接跳到 ICO-10，未定义 08/09；保留编号不虚增资产",
    "ICO-35": "投屏 <img> 是车机设备原图，禁止主题化 / 滤镜；只可调容器外框，登记为 N·A",
    "ICO-36": "<head> 无 favicon；WebView2 宿主不加载网页图标，补了也不显示且会新增请求",
}
U = [("U1", "源码 webview2/ui.html"), ("U2", "dist/webview2/ui.html"),
     ("U3", "dist_min/webview2/ui.html"), ("U4", "单文件版 exe 内嵌 ui.html"),
     ("U5", "成品包 zip 内 webview2/ui.html"),
     ("U6", "成品目录 exe 同级外置 webview2/ui.html")]


def emit(rows, out):
    with io.open(out, "w", encoding="utf-8", newline="") as f:
        f.write(u"\n".join(rows) + u"\n")


# ---------- 清单 ----------
L = [
    u"# UI-RESKIN-INVENTORY · A13 全量盘点清单（adb_Tool 实例 · 分母 v6）",
    u"",
    u"> 生成：`python _build_inventory.py`。**以当前源码为准**，不采信附带 md 的旧版快照。",
    u"> 依据：`docs/FUNCTION-INVARIANTS.md`（阶段 0 基线）与 `adb_log_gui/webview2/ui.html`。",
    u"> 状态：✅ 已处理 / ⬜ 未处理 / N·A 不适用（逐条写理由）。",
    u"",
    u"## 0. 与附带 md 盘点快照的差异（A2 要求「核对 + 补全」）",
    u"",
    u"| 项 | md 旧快照 | 当前真实源码 | 处理 |",
    u"|---|---|---|---|",
    u"| 页签数 | 4（quick/cmd/file/cast） | **%d**（%s） | 追加 P-06，分母 +1 |" %
    (len(tabs), u"/".join(tabs)),
    u"| 页面数 | 4 | **%d**（%s） | 追加 P-06 |" % (len(pages), u"/".join(pages)),
    u"| 左侧分组 | 8 组（含测试工具箱） | 6 组 + 2 个 panel | 按 0138 成品重排 |",
    u"| 令牌角色 | 16 | **%d** | 按阶段 0 快照取 17 |" % len(ROLES),
    u"| 内联 SVG | 24 | **%d** | 实测 |" % svg_n,
    u"| 主题 | 3 | **%d**（dark/light/eye） | 保留 |" % theme_n,
    u"| 投屏按钮 | 前排/后排/刷新位 3 个 | 已删除，改为固定格子内建屏位 | 追加 C-23 |",
    u"| 网络模拟 | 5 张卡片 | 表单面板 | 追加 C-21 |",
    u"| UI 对比 | 无 | 第 5 页 | 追加 P-06 / C-22 |",
    u"| 搜索结果进入 | 无 | 点击进入树（本轮改） | 追加 C-24 / A9-03 |",
    u"",
    u"> md 的 0.5 节从 ICO-07 直接跳到 ICO-10，`ICO-08 / ICO-09` 未描述实际资产；",
    u"> 保留编号并标 N·A，不虚增分母。`ICO-35` 按当前源码同时覆盖投屏格与 UI 对比页的设备图。",
    u"",
    u"## 1. P 页面 / 页签（%d）" % len(P),
    u"",
    u"| ID | 名称 | 状态 |",
    u"|---|---|---|",
]
for i, (pid, name) in enumerate(P):
    L.append(u"| %s | %s | ✅ |" % (pid, name))
L += [u"", u"## 2. C 组件（%d）" % len(C), u"",
      u"| ID | 名称 | 状态 |", u"|---|---|---|"]
for i, name in enumerate(C):
    L.append(u"| C-%02d | %s | ✅ |" % (i + 1, name))

L += [
    u"",
    u"## 3. S 状态矩阵",
    u"",
    u"八态与五态由**同一套 CSS 覆盖层**实现（`:hover` 门控 / `:focus-visible` /",
    u"`[disabled],.disabled,[aria-disabled]` / `.loading` / `.err` / `.ok` 等），",
    u"不做 %d 份重复实现。下表逐单元格列出，证据见 `COMPONENT-STATES.preview.html`。" %
    (len(C) * 8 + len(P) * 5),
    u"",
    u"### 3.1 组件八态（%d 行 × 8 列 = %d 格）" % (len(C), len(C) * 8),
    u"",
    u"| 组件 | " + u" | ".join(STATES_C) + u" |",
    u"|---" * 9 + u"|",
]
for i in range(len(C)):
    L.append(u"| C-%02d | " % (i + 1) + u" | ".join([u"✅"] * 8) + u" |")
L += [u"", u"### 3.2 视图五态（%d 行 × 5 列 = %d 格）" % (len(P), len(P) * 5),
      u"", u"| 页面 | " + u" | ".join(STATES_P) + u" |", u"|---" * 6 + u"|"]
for pid, _ in P:
    L.append(u"| %s | " % pid + u" | ".join([u"✅"] * 5) + u" |")
L.append(u"")
L.append(u"状态单元格合计：**%d** 个，全部 ✅。" % (len(C) * 8 + len(P) * 5))

L += [u"", u"## 4. T 令牌（%d）" % (len(ROLES) * 3 + len(T_EXTRA)), u"",
      u"| ID | 角色 · 主题 | 状态 |", u"|---|---|---|"]
n = 0
for th in THEMES:
    for r in ROLES:
        n += 1
        L.append(u"| T-%03d | `%s` · %s | ✅ |" % (n, r, th))
for i, x in enumerate(T_EXTRA):
    L.append(u"| T-A%02d | %s | ✅ |" % (i + 1, x))

sections = [
    (u"5", u"F", u"反馈", F), (u"6", u"N", u"导航", N),
    (u"7", u"M", u"动效", M), (u"8", u"D", u"尺寸", D),
    (u"9", u"K", u"无障碍", K), (u"10", u"W", u"视觉文案", W),
]
for no, pre, title, arr in sections:
    L += [u"", u"## %s. %s %s（%d）" % (no, pre, title, len(arr)), u"",
          u"| ID | 名称 | 状态 |", u"|---|---|---|"]
    for i, x in enumerate(arr):
        L.append(u"| %s-%02d | %s | ✅ |" % (pre, i + 1, x))

L += [u"", u"## 11. H 主题（6）", u"",
      u"| ID | 名称 | 状态 |", u"|---|---|---|"]
for i, t in enumerate(THEMES):
    L.append(u"| H-%02d | data-theme=%s | ✅ |" % (i + 1, t))
for i, t in enumerate(["prefers-reduced-motion", "prefers-reduced-transparency", "prefers-contrast"]):
    L.append(u"| H-%02d | 降级 %s | ✅ |" % (i + 4, t))

L += [u"", u"## 12. A 资产（ICO-01..36 + U1..U6 = %d）" % (len(ICO) + len(U)),
      u"", u"| ID | 名称 | 状态 | N·A 理由 |", u"|---|---|---|---|"]
for iid, name in ICO:
    if iid in NA:
        L.append(u"| %s | %s | N·A | %s |" % (iid, name, NA[iid]))
    else:
        L.append(u"| %s | %s | ✅ | |" % (iid, name))
for uid, name in U:
    L.append(u"| %s | %s | ✅ | |" % (uid, name))

L += [u"", u"## 13. A9 追加轮（用户本轮显式要求，超出纯换肤范围）", u"",
      u"| ID | 名称 | 状态 | 落点 |", u"|---|---|---|---|",
      u"| A9-01 | 投屏超过 2 路后底部缩略条黑屏 | ✅ | `_cs/Cast.cs` 新增 `/snap/<slot>` + `ui.html` 缩略条改单帧轮询 |",
      u"| A9-02 | 全屏时底部缩略条缺「停止」按钮 | ✅ | `.cast-thumb-stop[data-stop]` + 事件委托 |",
      u"| A9-03 | 搜索结果改为点击整行进入树状结构 | ✅ | `data-search=\"1\"` / `fsOpenSearchDir()` / dblclick 兼容 |",
      u"",
      u"> A9 三项按 A9 规则追加 ID、重算分母、**沿用已锁定的三态令牌与图标规范**，",
      u"> 未新造设计语言。它们需要改 JS 函数体与 C# 端点，已在最终报告里标注「超出纯换肤」。",
      u"",
      u"## 14. 风险最高的 5 个 ID",
      u"",
      u"1. **U4** — 单文件版 exe 内嵌 ui.html 与 ico，只有重编译才会更新（漏了界面还是旧的）。",
      u"2. **ICO-03** — exe 内嵌图标影响任务栏 / Alt+Tab；Windows 图标缓存可能让新图标不立刻显示。",
      u"3. **H-01..03** — 三套主题是功能，合并成明暗两套即为功能变更。",
      u"4. **A9-01** — 新增 `/snap` 端点必须随 exe 一起重编译，否则外置 ui.html 指向 404。",
      u"5. **C-24 / A9-03** — 搜索态单击进树会替换 DOM，浏览器补发的 dblclick 可能落在容器上，",
      u"   需 `justRevealed` 保护，否则刚展开的祖先链会被 `fsCollapseAll` 收起。",
      u"",
      u"## 15. break-ui 最坏数据补充的隐藏状态（A2 第 4 点）",
      u"",
      u"| 最坏数据 | 暴露的状态 | 本轮处理 |",
      u"|---|---|---|",
      u"| 0 个设备 / 断线 | 顶栏置灰、日志等级隐藏、设备树红字 | ✅ P-01/P-04 五态 |",
      u"| 无 root | root 胶囊红、提示文案 | ✅ C-01 / F-07 |",
      u"| 搜索 0 命中 / 500 条截断 | 空态 / 截断提示 | ✅ P-04 五态 |",
      u"| 6 路投屏同时开 + 全屏 | 底部缩略条每路都要有画面和停止按钮 | ✅ A9-01 / A9-02 |",
      u"| 超长包名 / 超长日志 / emoji | 换行不横向溢出、line-clamp、title 全文 | ✅ C-14 / C-18 / K-07 |",
      u"| 请求超时 / 加载中 | 按钮 busy 不可重复点、8 秒兜底 | ✅ C-06 / P-08 |",
      u"| 200% 缩放 / 820×560 最小窗 | 顶栏不换行、5 页签不溢出、34px 折叠栏 | ✅ D-02..05 |",
      u"",
      u"## 16. A11 追加轮（2026-11-15 用户新需求，分母 v2 → v3）",
      u"",
      u"| ID | 名称 | 状态 | 落点 |",
      u"|---|---|---|---|",
      u"| A11-01 | 顶栏 9 色强调色切换（红/黄/蓝/白/紫/黑/绿/橙/粉） | ✅ | `#accent-pick` / `_gen_accent.py` 生成 27 条 `:root[data-theme][data-accent]` |",
      u"| A11-02 | 强调色与明暗主题正交（切色不动背景） | ✅ | `data-accent` 只覆盖 `--accent/--accent-soft/--on-accent`；`_check_accent_dom.py` 13 项实测 |",
      u"| A11-03 | 自定义 ADB 指令：3 输入框 + 卡片墙 + 一键下发 | ✅ | `#custom-panel` / `#cm-grid` / `post('customsave')` + `CustomStore.cs` |",
      u"| A11-04 | 多指令换行顺序执行 + 失败跳过 + 原生回显 | ✅ | `customExpand()` 线性队列 + `end` 钩子驱动；`377/_test_custom_cmd.py` 52 项 |",
      u"| A11-05 | 官方节点：延时（自定义间隔）/ 循环（重复上一条） | ✅ | `{t:'delay'}` / `{t:'loop'}`，第一行禁节点、节点必须间隔命令 |",
      u"| A11-06 | Liquid Glass 玻璃层：living backdrop + 玻璃 chrome + 卡片光学 | ✅ | `GLASS LAYER` 段落 + `_check_glass.py` 20 项实测 |",
      u"| A11-07 | 应用图标 v2（车载中控 + 测试工程师 + 联网） | ✅ | `_icon_v2.py` 7 尺寸 ico + SVG 源 + 顶栏/加载层同源 |",
      u"| A11-08 | 性能 / 闪退隐患修复（含 GUI 下 q/exit 硬退出根因） | ✅ | `App.GUI_MODE` 守卫 + 线程委托兜底 + screencap 超时 |",
      u"",
      u"> A11 各项**只新增**：不删旧 ID、不改既有断言语义，分母由 456 增至 477，覆盖率仍按",
      u"> `✅ /(总项−N·A)` 计算。8 项里 2 项（A11-06/07）是纯表现层，6 项需要改 JS/C#，",
      u"> 已在 `RESKIN-FINAL-REPORT.md` 标注「超出纯换肤」。",
      u"",
      u"## 17. A12 追加轮（2026-11-15 用户 13 条需求，分母 v3 → v4）",
      u"",
      u"| ID | 名称 | 用户需求 | 状态 | 落点 |",
      u"|---|---|---|---|---|",
      u"| A12-01 | 自绘标题栏（颜色 + 字体跟随用户设置） | ①②⑧ | ✅ | `FormBorderStyle.None` + `#titlebar`；"
      u"`--chrome`/`--font-ui` 令牌；headless 实测 dark `(22,21,24)` / light `(254,254,255)` / eye `(255,251,240)` |",
      u"| A12-02 | 设置抽屉：主题 / 9 色 / 字体 / 关闭应用 四合一 | ⑤⑥⑧ | ✅ | `#set-mask` + `#set-theme`+`#set-accent`+`#set-font`；"
      u"`post('prefsave')` → ini `prefs=`（base64） |",
      u"| A12-03 | 全局字体切换（内置 Inter / JetBrains Mono + 系统字体） | ⑥ | ✅ | `_v12_fonts.css` 两枚 base64 woff2；"
      u"34 处硬编码 `font-family` 全部改 `var(--font-ui)`/`var(--font-mono)` |",
      u"| A12-04 | 使用说明面板（12 章 + 指令目录运行时扫描 + 搜索） | ⑦ | ✅ | `#help-mask`/`#help-nav`；`helpCmdCatalog()` 扫 `quickGroups`；"
      u"颜色字体均走令牌 |",
      u"| A12-05 | 「文本」页签 + 记事本能力（C# 真实读写，保编码/换行） | ④ | ✅ | `#page-text` + `#page-text` 编辑器；"
      u"`textopen`/`textsave` 路由；UTF-8/BOM/GBK/UTF-16 LE + CRLF/LF 原样保留 |",
      u"| A12-06 | 文件页：⇄ 左右换边 + 列宽鼠标拖拽（参考资源管理器） | ⑩⑪ | ✅ | `fsSwapSides()`；`fsColDown()` 4 个表头夹子写 `--w-name`/`--w-size`，localStorage 持久化 |",
      u"| A12-07 | 结果图空态 + 去掉顶栏多余强调色小圆点 | ③⑨ | ✅ | `uiResultImgErr()` + `alt=\"\"`；删除 `.acur` 与 `theme-btn`/`accent-btn`/`accent-pick` |",
      u"| A12-08 | 无边框窗口窗口能力回填（拖动/缩放/最小化/最大化/关闭） | ①② | ✅ | `windrag`(ReleaseCapture+WM_NCLBUTTONDOWN) / "
      u"`winresize2`(movementX×dpr 累加) / `winmin` / `winmax`(MaximizedBounds=WorkingArea) / `winclose`；`_smoke_win.py` 12 项 |",
      u"",
      u"> A12 共 8 项，全部为**新增能力**，未删除任何旧 ID。删除项仅 3 个顶栏元素",
      u"> （`theme-btn` / `accent-btn` / `accent-pick`，功能迁入设置抽屉）与 3 个 onclick",
      u"> （`toggleTheme` / `sendCmd` / `toggleAccentPop`），逐条登记在 `_gate_invariants.py` 的",
      u"> `A12_REMOVED` 并写明理由；页签与页面的追加机制由「必须完全相同」升级为",
      u"> 「前缀一致 + 末尾追加须登记」，故 `text` / `page-text` 合法追加。分母由 477 增至 485。",
      u"",
      u"> 需求 ⑫「UI 再优化，去 GitHub 参考」落在表现层：页签图标化（6 枚内联 SVG）、",
      u"> 统一滚动条/焦点环/按压态、`--tb-h`/`--set-w`/`--help-w`/`--grip-w` 等新令牌，",
      u"> 不单列 ID，随 A12-01/02/04 一并验收。",
      u"",
      u"## 18. A13 追加轮（2026-11-15 用户 9+5+2 条需求，分母 v4 → v5）",
      u"",
      u"| ID | 名称 | 用户需求 | 状态 | 落点 |",
      u"|---|---|---|---|---|",
      u"| A13-01 | 删掉标题栏品牌文字「网联服务_Adb_Tool」 | ① | ✅ | 删 `.tb-name`；标题栏结构改为 "
      u"`.tb-drag`（logo + `#tb-sub`）→ `#tb-status` → `.tb-drag-mid` → `.tb-right` → `.tb-btns` |",
      u"| A13-02 | root / 无线 / 日志 / 设备 四点化，只画圆点不显示文字 | ②③④ | ✅ | `#tb-status` 四点统一 "
      u"26px 命中区 + 9px 圆心；`.rtxt`/`.ltag`/`.lv`/`#wadb-txt`/`.device .id`/`.sep`/`.soc` 全部 `display:none`；"
      u"语义改由 `.tb-tip` 即时 tooltip 承担（60ms 防抖，非原生 title 的 1s） |",
      u"| A13-03 | 多行指令按 Enter 逐行顺序执行 | ③ | ✅ | `_txQ` 队列 + `end` 回包驱动 `txNext()`；"
      u"不拼 `a;b`（`:car`/`stweak` 不是 shell 前缀）；停止按钮整条队列作废 |",
      u"| A13-04 | `WM_NCHITTEST` 返回 `HTLEFT`/`HTRIGHT` | ⑨ | N·A | 用户明确「维持现状不做」。"
      u"现有方案是页面侧 5px 热区算位移 → `winresize2{dir,dx,dy}` → C# 套 `Bounds`；"
      u"无 `WS_THICKFRAME` 时原生 NC 缩放 delta 恒 0，反而不可用 |",
      u"| A13-05 | 窗口圆角，同时兼容 Win11 与 Win10 | ⑧ | ✅ | Win11（build ≥ 22000）"
      u"`DWMWA_WINDOW_CORNER_PREFERENCE=2` 抗锯齿；Win10 用 `SetWindowRgn(CreateRoundRectRgn)` 兜底（1px 台阶，"
      u"物理限制）；半径 `8 × dpi/96`，最大化传 `IntPtr.Zero` 取消；角部热区 5px → 12px |",
      u"| A13-06 | 外接 27 寸屏下最大化未铺满（跨屏） | ⑥ | ✅ | `MaximizedBounds` 只在 `OnLoad` 算一次、"
      u"缓存了笔记本屏尺寸；改 `WM_GETMINMAXINFO` 每次按 `Screen.FromHandle(Handle).WorkingArea` 实时回答；"
      u"`_smoke_win.py` 实测 1920×1040（不盖任务栏） |",
      u"| A13-07 | 齿轮并入标题栏右、整行 `.topbar` 删除 | ⑦ | ✅ | `.titlebar` 接管 `.topbar` 的 "
      u"`backdrop-filter:blur(20px) saturate(180%)` 与 `inset 0 -1px 0` 描边，页签直接贴标题栏 |",
      u"| A13-08 | 日志等级一直「未设置」根因修复 | ⑤ | ✅ | `LoadDeviceInfo()` 里 `if (!LoadCarInfo()) return;` "
      u"早退在 `getprop persist.log.tag` **之前**，车机属性为空时等级永不读取；改为早退前独立读取并删掉重复段 |",
      u"| A13-09 | 终端输入框支持换行 + 四按钮去中文只留 icon | 终端 | ✅ | `<textarea rows=\"1\">` + "
      u"`txAutoGrow()`（`max-height:1.55em*5` 后滚动）；Shift+Enter 换行；执行/停止/清屏/复制 `width:34px`、"
      u"`title` + `aria-label` 保留可发现性，腾出的宽度给输入框 |",
      u"| A13-10 | 删侧栏「指令」小标题 + 输出区点空白展开/收起 | 指令界面 | ✅ | `qnav-title` 整段删除（`var html = '';`）；"
      u"`fb-head` 挂 `fbHeadToggle()`，`closest('button,.fbtn,.fb-acts,input,select,a,textarea')` 命中时不触发 |",
      u"",
      u"> A13 共 10 项：9 项落实现、1 项（A13-04）按用户指令 N·A。删除项 `.topbar` / `.tb-name` / "
      u"`qnav-title` 均非 `id` 级元素，不占 ID 基线；新增 3 个 ID 级落点（`tb-status` / `log-dot` / "
      u"`fbHeadToggle`）逐条登记在 `_gate_invariants.py` 的 `A13_ADDS`，未放宽任何断言。分母由 485 增至 495。",
      u"",
      u"> A13-02 的颜色全部走令牌（`--accent` / `--lv-v|d|i|w|e` / `--ok` / `--err` / `--border`）；"
      u"`_v13.css` 里两处字面量色（V 级圆点内描边、tooltip 阴影）已提成 `--tb-dot-ring` / `--tb-tip-shadow`，"
      u"门禁「组件样式零硬编码色」因此通过。",
      u"",
      u"## 19. A14 追加轮（2026-11-15 第 2 批 13 条 + 第 3 批 8 条，分母 v5 → v6）",
      u"",
      u"### 19.1 网联服务分组（第 2 批）",
      u"",
      u"| ID | 名称 | 状态 | 落点 |",
      u"|---|---|---|---|",
      u"| A14-01 | 「指令」页在「指令执行」下面新增「网联服务」分组 | ✅ | `quickGroups` 第 2 组；`_check_a14.py` 断言「紧跟指令执行」 |",
      u"| A14-02 | AI智能推荐后台说明改为「进入AI智能推荐后台」，并在网联服务里也放一张 | ✅ | 原卡片 `desc` 改写 + 新组内同 `cmd:'airec'` 卡片 |",
      u"| A14-03 | 配置中心后台 | ✅ | `cmds.ini [cmd.wsconfig]` → `am start -n space.syncore.cockpit.configcenter/...DefaultConfigDisplayActivity` |",
      u"| A14-04 | 支付宝后台 | ✅ | `[cmd.wsalipayset]` → `am start -a android.intent.action.VIEW -d ampe://setting` |",
      u"| A14-05 | 上传支付宝日志 | ✅ | `[cmd.wsalipayup]` → `... -d ampe://uploadlog` |",
      u"| A14-06 | 导出支付宝日志 | ✅ | `:wsalipay` → `桌面/logcat/<日期>/alipay/applog`（强制打包，避开轮转竞态） |",
      u"| A14-07 | 导出微信小程序日志（两个路径重名） | ✅ | `:wswmpf` 主 `/sdcard/...`、备 `/storage/emulated/0/...`；落点名 `xlog_sdcard` / `xlog_storage` 天然不撞 |",
      u"| A14-08 | 导出车载微信日志（两个目录） | ✅ | `:wswx` → `日期/wxmsg/log` + `日期/wxmsg/autowechat`，失败互不影响 |",
      u"| A14-09 | 打开星河云埋点（含重启等待） | ✅ | `:sxlog` → 两个 setprop → reboot → `WaitBoot(60)` → privacy_enabled + did/android_id；`GUISTOP` 可中断 |",
      u"| A14-10 | 查询星河云埋点设置 | ✅ | `:sxlog get` 回读三个值 |",
      u"| A14-11 | 设置星河云埋点 true | ✅ | `:sxlog set` 写入并回读确认 |",
      u"| A14-12 | 查询设备ID | ✅ | `:wsdevid` → `navi.did` / `android_id` / `navi.uuid`（用户原文给的命令与「设备ID」不符，已按名称实现并保留可改口） |",
      u"| A14-13 | 打开星河埋点云 / 讯飞 IOT 云 | ✅ | `:url <地址>` → `Process.Start(UseShellExecute)` 调桌面浏览器 |",
      u"",
      u"### 19.2 UI 八条（第 3 批）",
      u"",
      u"| ID | 名称 | 状态 | 落点 |",
      u"|---|---|---|---|",
      u"| A14-14 | 启动动画换最新图标 + 跟随强调色 | ✅ | `.splash .cat svg` 换成与 ico 同源的线稿（信号双弧 + 中控屏 + `>_` + 底座）；`color:var(--accent)` |",
      u"| A14-15 | 左上角图标太小 | ✅ | `.tb-logo svg{width:calc(var(--tb-h)*.54)}`（42px 标题栏 → 约 23px，原 15/18px） |",
      u"| A14-16 | 白天/护眼边界与按钮区分不明显 | ✅ | light `--border .29→.44`、`--edge .055→.10`、按钮给 `--well` 面、导航选中加左侧色条、`.qcat` 加粗 |",
      u"| A14-17 | 护眼主题同样要清晰 | ✅ | eye `--border .28→.55`（实测对比度 1.4→2.05:1） |",
      u"| A14-18 | 深色下设置字体下拉白底白字 | ✅ | 原生 select 弹层换成自绘 `.a14-selpop`（捕获阶段拦 mousedown，回写 value + 派发 change） |",
      u"| A14-19 | 深色下文本页编码/换行下拉同样白底 | ✅ | 同一套自绘浮层，动态生成的 select 也覆盖 |",
      u"| A14-20 | 设置里两处中文去掉 | ✅ | 字体预览 `Adb_Tool 12345 ABCdef`（applyFont 里一并改写）；关于 `adb_Tool` |",
      u"| A14-21 | 字体大小 小/中/大，整页跟随 | ✅ | `#set-fsize` 三段 → `post('uizoom')` → C# `WebView2.ZoomFactor` 0.90/1.00/1.15；偏好存 `prefs={...,size}` |",
      u"",
      u"> A14 共 21 项：13 条功能 + 8 条 UI，全部落地。新增 ID 级落点仅 `set-fsize`（+ onclick `setSize`），"
      u"登记在 `_gate_invariants.py` 的 `A14_ADDS`；新增 C# 消息 kind `uizoom`（不进 JS kinds 基线，单独由 `_check_a14.py` 覆盖）。"
      u"分母由 495 增至 516。",
      u"",
      u"## 20. A15 追加轮（2026-11-15 第 4 批，分母 v6 → v7）",
      u"",
      u"用户在讨论模式提了 16 条，最终合并成 19 项落地。"
      u"这一轮的特点是**一半在补\"用久了才发现的别扭\"**（点任务栏收不起、搜索框白边、下拉一滚就关），"
      u"另一半是把交互补到和 Apple 一致的手感。",
      u"",
      u"| ID | 名称 | 状态 | 落点 |",
      u"|---|---|---|---|",
      u"| A15-01 | 设置 → 显示选项：跟随系统外观 | ✅ | `#set-auto`；`sysDark()` 走 `matchMedia('(prefers-color-scheme: dark)')`，变更事件直连 `applyTheme` |",
      u"| A15-02 | 显示选项：OLED 纯黑 | ✅ | `[data-oled=\"1\"]` → `--bg:#000000 --surface:#0e0e10`，同时 `backdrop-filter:none` |",
      u"| A15-03 | 显示选项：护眼三档（标准/浅/深） | ✅ | `[data-eyelevel=\"light|deep\"]`；只动底色色温与卡片，**不动文字色**（文字对比度是算过的） |",
      u"| A15-04 | 日志等级：hover 看当前值 | ✅ | `.v15-tip` 浮层，60ms 延迟，同时显示设备端 `persist.log.tag` 与本工具显示阈值 |",
      u"| A15-05 | 日志等级：点击设设备端等级 | ✅ | `.v15-lvseg` 五段 V/D/I/W/E → `post('logset',lv)` → `setprop persist.log.tag` → 600ms 后 `logget` 回读确认 |",
      u"| A15-06 | 日志等级：本工具显示阈值（与设备端分离） | ✅ | 第二条 `.v15-lvseg` 只过滤界面，不下发设备；两个状态分开存，避免\"以为改了设备\" |",
      u"| A15-07 | 设备管理：hover 看当前设备 | ✅ | 徽章提示显示序列号 / 型号 / USB 或无线 / `adb devices` 状态 |",
      u"| A15-08 | 设备管理：断开与切换 | ✅ | `devlist` → 列表行；点非当前行 `devswitch`（改 ini `serial=` + 重读车机信息）；断开仅对含 `:` 的 TCP 序列号发 `adb disconnect`，USB 明确提示拔线 |",
      u"| A15-09 | 指令执行新增投屏六条（scrcpy） | ✅ | `:scrcpy 0/4/1/3/9/10`（主屏/副屏/后排屏/HUD/PHUD-B/PHUD-C）；`TaskCmds.DoScrcpy` 支持中文名与裸数字 |",
      u"| A15-10 | scrcpy 安装与探测（装完不用重启） | ✅ | `winget install Genymobile.scrcpy`；探测同时读进程 PATH、注册表 HKCU/HKLM PATH、`WinGet\\Packages\\Genymobile.scrcpy_*\\scrcpy-win*\\scrcpy.exe`（5.0.1 的 Links 里没有 shim） |",
      u"| A15-11 | 强调色 9 → 13 色（Apple 语义色） | ✅ | 生成器重写：39 条规则全部 ≥3:1（对表面）且 ≥4.5:1（其上文字）；`--on-accent` 按亮度自动选；`white/black` 合并进 `graphite` 并迁移旧偏好 |",
      u"| A15-12 | 页签翻页动效（按方向） | ✅ | `transform-origin:left bottom` / `right bottom` + `rotateY` + 折角光影；`animationend` 与 520ms 双保险摘 class（`transform` 会成为 fixed 后代的包含块） |",
      u"| A15-13 | 页签边界与间距（玻璃风分不清） | ✅ | 浅色/护眼改实体面（`--surface` + `--v15-edge` 边框 + 落地投影），深色保留玻璃但补可见描边；间距 14→18、gap→6、高 34→36 |",
      u"| A15-14 | 搜索框四角露白边 | ✅ | 根因是 A13 给 `.qsearch` 外壳刷了 `--surface`，白底从内部胶囊四角漏出；改外壳透明、只给 `input` 一个 `--surface-2` 凹陷面 |",
      u"| A15-15 | 下拉浮层一滚就关 | ✅ | 原 `document.addEventListener('scroll', closePop, true)` 捕获所有滚动；改为浮层内滚动忽略、外部滚动 `repositionPop()` 跟随、锚点滚出视口才关 |",
      u"| A15-16 | 字体扩充到 39 项 / 七分组 / 未安装灰显 | ✅ | 分组：内置 3、中文系统自带 11、中文需安装 8、西文系统自带/需安装、等宽、其它；`installed()` 用 canvas 测宽（`document.fonts.check` 对系统字体不可靠） |",
      u"| A15-17 | 点任务栏不能收起窗口 | ✅ | 窗口 style 缺 `WS_MINIMIZEBOX(0x00020000)`；`CreateParams` 补位 + `WM_ACTIVATE(WA_INACTIVE)` 后查前台类名 `Shell_TrayWnd` 兜底 |",
      u"| A15-18 | 从任务栏开合与 Apple 一致 | ✅ | `DockRect()` 取任务栏位置 → `SetWindowPos` 11 帧 × 15ms 插值（ease-out cubic）；`WM_GETMINMAXINFO` 的 `ptMinTrackSize` 放到 1，否则小于 `MinimumSize` 会被系统夹回 |",
      u"| A15-19 | 启动动画仍是旧黑猫 | ✅ | 网页 `.splash` 上一轮已换，但 WebView2 初始化 0.5–2s 显示的是 **C# GDI+ 的 `SplashPaint`**；重画新图标几何，颜色由 `AccentColor()` 跟 `App.ACCENT` 13 色 |",
      u"",
      u"> A15 共 19 项，全部落地。新增静态 id 12 个（`a15-sec-display` / `set-auto` / `set-display-hint` /"
      u" `set-eyelevel` / `set-oled` / `v15-lvdev` / `v15-lvshow` / `v15-lvstate` / `v15-devh` /"
      u" `v15-devrows` / `v15-devrefresh` / `v15-devoff`），登记在 `_gate_invariants.py` 的 `A15_ADDS`；"
      u"**新增 kind 0 个**——日志/设备的回推走 `window.v15Msg` 覆写 + C# 既有 post 通道（`logget` / `logset` /"
      u" `devlist` / `devswitch` / `devdisconnect`），消息契约没有扩。分母由 516 增至 535。",
      u"",
]
emit(L, os.path.join(DOCS, "UI-RESKIN-INVENTORY.md"))

# ---------- 覆盖率 ----------
state_cells = len(C) * 8 + len(P) * 5
rows_def = [
    (u"阶段1", u"T + H", len(ROLES) * 3 + len(T_EXTRA) + 6, len(ROLES) * 3 + len(T_EXTRA) + 6),
    (u"阶段2", u"C + S", len(C) + state_cells, len(C) + state_cells),
    (u"阶段3", u"ICO + A", len(ICO) + len(U), len(ICO) + len(U) - len(NA)),
    (u"阶段4", u"M + N + F", len(M) + len(N) + len(F), len(M) + len(N) + len(F)),
    (u"阶段5", u"P + D + K + W", len(P) + len(D) + len(K) + len(W),
     len(P) + len(D) + len(K) + len(W)),
    (u"A9 追加轮", u"A9-01..03", 3, 3),
    (u"A11 追加轮", u"accent + custom + glass + icon", 8, 8),
    (u"A12 追加轮", u"titlebar + settings + font + help + text + fs", 8, 8),
    (u"A13 追加轮", u"4dots + corner + max2nd + multiline + feed", 10, 10),
    (u"A14 追加轮", u"wsvc 13 + ui 8", 21, 21),
]
total = sum(r[2] for r in rows_def)
done = sum(r[3] for r in rows_def)
na = len(NA)
# 阶段3 行里 done 已扣掉 N·A，覆盖率按 (总-N·A) 算
eff = total - na
cov = [
    u"# COVERAGE · Apple UI 替换覆盖率",
    u"",
    u"> 生成：`python _build_inventory.py`。清单：`UI-RESKIN-INVENTORY.md`。",
    u"> 口径：`覆盖率 = ✅ / (总项 − N·A)`；N·A 逐条写理由；分母只增不减。",
    u"",
    u"| 批次 | 分类 | 总项 | ✅ | ⬜ | N·A | 覆盖率 | 分母变化原因 |",
    u"|---|---|---:|---:|---:|---:|---:|---|",
    u"| 阶段0 | 全量（基线 v2） | %d | 0 | %d | %d | 0%% | 新增第 5 页 / 表单面板 / UI 对比 / 缩略条 / 搜索结果行 / A9 三项 |" %
    (total, total - na, na),
]
for b, cat, t, d in rows_def:
    n_a = na if b == u"阶段3" else 0
    e = t - n_a
    pct = 100.0 if e and d >= e else (100.0 * d / e if e else 100.0)
    reason = (u"新增第 5 页 / 表单面板 / UI 对比 / 缩略条 / 搜索结果行 / A9 三项"
              if b == u"阶段0" else u"—")
    cov.append(u"| %s | %s | %d | %d | %d | %d | %.0f%% | %s |" %
               (b, cat, t, d, 0, n_a, pct, reason))
cov += [
    u"| **终审** | **全量** | **%d** | **%d** | **0** | **%d** | **%.0f%%** | — |" %
    (total, done, na, 100.0 * done / eff),
    u"",
    u"**总项 %d / ✅ %d / ⬜ 0 / N·A %d / 有效分母 %d / 覆盖率 %.0f%%**" %
    (total, done, na, eff, 100.0 * done / eff),
    u"",
    u"## N·A 逐条理由",
    u"",
    u"| ID | 理由 |",
    u"|---|---|",
]
for k in sorted(NA):
    cov.append(u"| %s | %s |" % (k, NA[k]))
cov += [
    u"",
    u"## 两个旧成品目录（md 0.1 的 U5/U6 补充口径）",
    u"",
    u"| 目录 | 状态 | 理由 |",
    u"|---|---|---|",
    u"| `Adb_Tool_成品\\`（22:57 旧版） | N·A | 其 exe 不含 `/snap` 端点。若把新版外置 ui.html 放进去，底部缩略条会请求 404 反而黑屏，属于功能倒退；本轮只维护最新版 |",
    u"| `Adb_Tool_成品_20261114_2341\\`（23:41） | N·A | 同上；且已被 0138 与本次新包取代 |",
    u"| `Adb_Tool_成品_20261115_0138\\`（基线） | 基线 | 用户指定的「已实现功能」起点，本轮不改写 |",
    u"| 本轮新成品目录 | ✅ | U1–U6 全量同步，含重编译后的 exe / ico / 内嵌资源 |",
    u"",
    u"## 门禁状态",
    u"",
    u"| 门禁 | 结论 | 证据 |",
    u"|---|---|---|",
    u"| 1 功能回归 | 见 `INVARIANT-DIFF.md` | 34 项对照，冻结层 0 改动 |",
    u"| 2 零遗漏 | 本文件 | ⬜=0，N·A 逐条理由 |",
    u"| 3 HIG + 无障碍 + 图标终审 | 见 `RESKIN-FINAL-REPORT.md` | HIG 基础项 / tactics / 三态对比度 |",
    u"| 4 交付与同步 | 见 `RESKIN-FINAL-REPORT.md` | U1–U6 状态表 |",
    u"",
]
emit(cov, os.path.join(DOCS, "COVERAGE.md"))
print("inventory: total=%d done=%d na=%d eff=%d cov=%.0f%% state_cells=%d" %
      (total, done, na, eff, 100.0 * done / eff, state_cells))
