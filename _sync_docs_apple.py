# -*- coding: utf-8 -*-
"""把三份既有文档同步到 2026-11-15 Apple UI 替换 + 3 项交互修复（A8 门禁 4）。

精确字符串替换 + 追加章节；任一锚点找不到就报错退出，避免静默漏改。
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(ROOT, "docs")


def load(name):
    with io.open(os.path.join(DOCS, name), "r", encoding="utf-8") as f:
        return f.read()


def save(name, text):
    with io.open(os.path.join(DOCS, name), "w", encoding="utf-8", newline="") as f:
        f.write(text)


def rep(text, old, new, name):
    if old not in text:
        sys.stderr.write("[ERROR] %s 找不到锚点：%s\n" % (name, old[:60]))
        sys.exit(1)
    return text.replace(old, new, 1)


def append(name, block):
    p = os.path.join(DOCS, name)
    with io.open(p, "a", encoding="utf-8", newline="") as f:
        f.write(block)


# ==================== 用户使用手册 ====================
m = load("用户使用手册.md")
m = rep(m, u"> 版本：2026-11-15",
        u"> 版本：2026-11-15（Apple UI 全面替换 + 3 项交互修复）", "手册·版本")
m = rep(m, u"> 表里的体积是 **zip 实测值**（2026-11-14 出包）",
        u"> 表里的体积是 **zip 实测值**（2026-11-15 出包）", "手册·体积日期")
m = rep(m,
        u"| 双击结果 | 退出搜索，把树逐级展开并选中这一项（能看清它到底在哪） |\n"
        u"| 文件夹点「进入 ⤵」 | **打开这个文件夹看里面一层**：退出搜索态、把从根到该目录的整条祖先链展开、选中并渲染目标目录。比双击定位更直接，不用再到树里找 |",
        u"| 单击结果行 | **进入树状结构**：退出搜索态、清空搜索框、把从根到该目标的整条祖先链逐级展开、选中并渲染它。目录行左侧有 ▸ 箭头，和平时在树里点开文件夹的方式一致，没有额外按钮 |\n"
        u"| 双击结果行 | 同上（保留兼容，老习惯双击也能进树）；不会重复发起搜索 |",
        "手册·搜索交互")
m = rep(m,
        u"- 设备侧不显示大小/时间（每条都去 stat 会把 adb 排队排满），双击跳回树里就能看到；",
        u"- 设备侧不显示大小/时间（每条都去 stat 会把 adb 排队排满），点结果行进树里就能看到；",
        "手册·设备侧说明")
save("用户使用手册.md", m)

append("用户使用手册.md", u"""

---

## 16. Apple UI 全面替换（2026-11-15 第三轮）

### 16.1 换了什么

整个界面换成 Apple 设计语言的**桌面工具型**表达：语义色、系统字体栈、8pt 网格、连续圆角、hairline 边框、tinted 阴影、单一 accent。
玻璃效果只用于顶栏和浮层，日志区 / 反馈表 / 树这些阅读面保持不透明。

| 项 | 说明 |
|---|---|
| 三套主题 | **黑夜 / 白天 / 护眼全部保留**，切换按钮位置、顺序、`theme=` 持久化都不变。护眼是 Apple 浅色 + 暖白低蓝光变体，不是简单反色 |
| 品牌图标 | 原黑猫改为 Apple 单线「终端提示符 >_」。顶栏、加载过渡层、窗口图标、任务栏四处同源；`.ico` 含 16/24/32/48/64/128/256 七种尺寸 |
| 图标线宽 | 内联 SVG 统一 24×24 viewBox（加载层 48×48）、1.75 描边、圆角端点、随文字色变化；不再有写死的颜色 |
| 无障碍 | 键盘焦点有清晰焦点环；支持系统的「减少动态效果 / 降低透明度 / 增强对比度」；日志等级 V/D/I/W/E 保留字母徽章，不靠颜色单独表意 |

本应用是**工具台**，不是官网。动效刻意压到 ≤300ms 且近乎不可见，没有滚动叙事、没有大范围弹性动画。

### 16.2 本轮修掉的 3 个交互问题

| 问题 | 现在的行为 |
|---|---|
| 投屏超过两路后，底部缩略条画面不显示 | 底部缩略图改走 `/snap/<槽位>` 单帧短连接，不再与主画面抢同源长连接；1 秒轮询只换图片地址，不重建 DOM。6 路全开 + 全屏也不黑 |
| 全屏后底部缩略条缺少关闭投屏按钮 | 每一路已开启的缩略图右上角有常驻「×」，不用退出全屏就能停掉别路 |
| 搜索结果的进入方式不符合现有交互 | 删掉「进入 ⤵」按钮，点结果整行即展开进入树状结构，与未搜索时一致；目录行带 ▸ 箭头，双击仍兼容 |

> 这 3 项需要改前端函数体和后端 HTTP 端点，**超出了「只改表现层」的范围**，是本次明确追加的需求。
> 命令、消息协议、ini 配置、页签结构一概没动。

### 16.3 升级注意

1. **必须整包替换**，不要只把新的 `ui.html` 拷到旧 exe 旁边：本轮新增了 `/snap` 端点并换了应用图标，
   旧 exe 没有这个端点，缩略条会请求 404 反而更糟。
2. 任务栏 / Alt+Tab 若还显示旧图标，是 **Windows 图标缓存**，重启资源管理器或注销一次即可；窗口内图标已是新的。
3. 外置文件优先的机制没变：`exe` 同级有 `webview2\\ui.html` 和 `adb_Tool.ico` 就用外部的，没有才用内嵌的。
4. 三套主题逐页截图索引、真机（车机设备）手测本轮**未做**，见 `docs/RESKIN-FINAL-REPORT.md` 的遗留项。
   界面回归以 `verify_all.py` 的 16 项门禁和 `docs/COMPONENT-STATES.preview.html` 状态墙为准。

### 16.4 相关文档

`docs/UI-RESKIN-INVENTORY.md`（全量清单）、`docs/COVERAGE.md`（覆盖率）、
`docs/FUNCTION-INVARIANTS.md`（功能基线）、`docs/INVARIANT-DIFF.md`（改动对照）、
`docs/DESIGN.md`（本轮沉淀的规则）、`docs/RESKIN-FINAL-REPORT.md`（验收结论）。
""")

# ==================== 功能清单 ====================
f = load("功能清单.md")
f = rep(f,
        u"> 2026-11-15 按参考图重构后，本章 §1 / §4 / §5 / §6 / §7 已同步，新增 §8 汇总本轮变更。",
        u"> 2026-11-15 按参考图重构后，本章 §1 / §4 / §5 / §6 / §7 已同步，新增 §8 汇总本轮变更。\n"
        u"> 2026-11-15 第三轮（Apple UI 全面替换 + 3 项交互修复）同步 §4 / §5，新增 §9 汇总。",
        "功能清单·头部")
f = rep(f,
        u"| 搜索 | 左右各自独立、平铺结果、双击定位回树 | `renderFsSearch()`、`fsReveal()`、`case \"fssearch\"` | `_test_fs_search.py`、`fs.search` |\n"
        u"| **搜索结果进入下一级** | 目录行有「进入 ⤵」，点一下退出搜索态、展开整条祖先链、选中并渲染目标目录 | `.fs-enter[data-enter]`、`bindFsRows()`、`fsOpenSearchDir()` | `_test_fs_search.py`、`fs.search-enter` |",
        u"| 搜索 | 左右各自独立、平铺结果；单击或双击结果都定位回树 | `renderFsSearch()`、`fsReveal()`、`case \"fssearch\"` | `_test_fs_search.py`、`fs.search` |\n"
        u"| **点击结果进入树状结构** | 无额外按钮。结果行带 `data-search=\"1\"`、目录行带 ▸ 箭头，点整行即退出搜索态、清空搜索框、展开整条祖先链、选中并渲染；与未搜索时树交互一致。双击保留兼容，并有 `justRevealed` 保护补发的 dblclick | `bindFsRows()`、`fsOpenSearchDir()`、`fsReveal()` | `_test_fs_search.py`、`fs.search-click` |",
        "功能清单·搜索")
f = rep(f,
        u"| 6 | 搜索结果目录可进入 | 「进入 ⤵」直接展开下一级 | `fs.search-enter` |",
        u"| 6 | 搜索结果可进入下一级 | 第三轮改为点击整行进入树（原「进入 ⤵」按钮已删），见 §9 | `fs.search-click` |",
        "功能清单·§8 第 6 行")
save("功能清单.md", f)

append("功能清单.md", u"""

## 9. 2026-11-15 第三轮变更汇总（Apple UI + 3 项交互修复）

| # | 变更 | 用户可见效果 | 机检 / 验证入口 |
|---:|---|---|---|
| 1 | Apple 三态语义令牌 | dark / light / eye 各 17 个角色 + 系统字体栈 / 8pt 网格 / 连续圆角 / tinted 阴影；三套无障碍降级；`THEME_ORDER` 不变 | `apple.tokens`、`_test_ux.py` |
| 2 | 图标专项 | 24 处内联 SVG 统一 24×24 / 1.75 描边 / `currentColor`；品牌改 Apple 单线终端；7 尺寸 ico 与顶栏 / 加载层 / 任务栏同源 | `apple.icons`、`_gate_invariants.py` |
| 3 | 组件八态 + 视图五态 | 统一的 hover / focus-visible / active / disabled / loading / error / success 与视图五态覆盖层 | `COMPONENT-STATES.preview.html` |
| 4 | **修复：底部缩略条黑屏** | 6 路投屏 + 全屏时缩略图不再黑；改 `/snap/<slot>` 单帧短连接 + 1 秒轮询换 `img.src` | `cast.strip-snap`、`_test_cast_ui.py` |
| 5 | **修复：全屏缩略条缺停止按钮** | 每路缩略图常驻「×」，不用退出全屏即可关闭别路 | `cast.strip-stop`、`_test_cast_ui.py` |
| 6 | **修复：搜索结果进入方式** | 删「进入 ⤵」，点整行进入树状结构，与未搜索时一致 | `fs.search-click`、`_test_fs_search.py` |
| 7 | 功能不变量门禁 | 项目非 git 仓库，改用「阶段 0 快照 vs 当前源码」逐项解析，34 项对照 | `_gate_invariants.py` → `docs/INVARIANT-DIFF.md` |
| 8 | 静态自检补 Apple 断言 | 分组颜色零硬编码 / 三处旧品牌色清零 / 三态令牌 / 三套降级 / SVG 全 currentColor | `377/_check_ui.js` §13 |

> 第 4–6 项属于用户本轮显式追加的需求，需要改 JS 函数体与 `_cs/Cast.cs` 的 HTTP 端点，
> **超出「只改表现层」的换肤范围**，已在 `docs/RESKIN-FINAL-REPORT.md` 声明。
> 第 1–3、7–8 项没有新增 `msg.kind`、没有改 `post()` 签名、没有改命令串或 ini key。

对应文档：`docs/用户使用手册.md` §7.2.2 / §16、`docs/SynTestUtil命令对照与用法.md` §6、
`docs/UI-RESKIN-INVENTORY.md`、`docs/COVERAGE.md`、`docs/DESIGN.md`。
""")

# ==================== SynTestUtil 命令对照 ====================
c = load("SynTestUtil命令对照与用法.md")
c = rep(c,
        u"| 样式 | 复用 `.btn`；新增 `.ns-*` / `.ui-*` / `.logpill[data-lv=\"none\"]` / `.fs-enter` / 投屏禁拖拽 | `ui.html` |",
        u"| 样式 | 复用 `.btn`；新增 `.ns-*` / `.ui-*` / `.logpill[data-lv=\"none\"]` / 投屏禁拖拽；**第三轮起 `.fs-enter` 已删除**（搜索结果改为点整行进树），全量换为 Apple 语义令牌 | `ui.html` |",
        "命令对照·样式行")
save("SynTestUtil命令对照与用法.md", c)

append("SynTestUtil命令对照与用法.md", u"""

---

## 6. 2026-11-15 第三轮：Apple UI 替换与 3 项交互修复

### 6.1 命令与协议：一行未改

本轮是界面换肤，加 3 个用户点名的交互缺陷修复。下表所列 10 个功能的**命令字符串、`cmds.ini` 的 `[cmd.*]` 段、
消息 kind、`post()` 签名、快捷键、ini key 全部保持原样**，第三轮没有新增或删改任何一条命令。

- 快捷指令仍然走 `post('quick', cmd)`，网络模拟表单面板的「开启」仍然折成 `stweak <延迟>ms <丢包>% <速率>kbit`；
- 投屏仍然走 `postObj({kind:'caststart', slot, id})` / `caststop` / `casttap`；
- 主屏 / 后排屏的 displayId 内建映射 `castDefaultId()` 不变；
- UI 对比页仍为纯前端 Canvas，不新增 C# kind。

### 6.2 本轮实际改动

| 层 | 改动 | 是否超出纯换肤 |
|---|---|---|
| `ui.html` `<style>` | 三套 Apple 语义令牌、字体栈、8pt 网格、组件八态 / 视图五态、三套无障碍降级 | 否 |
| `ui.html` 内联 SVG | 24 处统一 24×24 / 1.75 / `currentColor`，品牌改 Apple 单线终端 | 否 |
| `adb_Tool.ico` ×2 + SVG 源 + exe `/win32icon` | 7 尺寸新图标，四处同源 | 否（但需重编译） |
| `ui.html` 投屏渲染 / 事件 | 底部缩略条改 `/snap` 单帧、每路补停止按钮 | **是**（A9-01 / A9-02） |
| `ui.html` 文件搜索渲染 / 事件 | 点整行进入树状结构，dblclick 兼容 | **是**（A9-03） |
| `_cs/Cast.cs` | 新增 `/snap/<slot>` 单帧快照端点（短连接，`Connection: close`） | **是**（A9-01 依赖） |

> A10 的「禁止层」原则针对纯换肤；用户本轮显式要求修这 3 个 bug，按 A9 追加轮处理，
> 追加 ID、重算分母、沿用已锁定令牌，并在 `docs/RESKIN-FINAL-REPORT.md` 显式声明超出范围。

### 6.3 实现协议与未确认项（保留原口径）

- **实现协议**：所有复用的功能都先在本文件登记命令、证据等级与落点，再落到 `cmds.ini` / `ui.html`；
  不把逆向推测写成已实现。第三轮没有引入新的逆向功能。
- **未确认项**：真机（车机设备）上的 6 路投屏并发、`/snap` 端点在真实 adb 截帧压力下的表现、
  三套主题逐页截图 —— 本轮只做了无头 DOM 门禁与静态/不变量对照，**未做真机手测**，留待 QA 现场验证。

### 6.4 相关文档

`docs/UI-RESKIN-INVENTORY.md`、`docs/COVERAGE.md`、`docs/INVARIANT-DIFF.md`、
`docs/用户使用手册.md` §16、`docs/功能清单.md` §9。
""")

print("OK 三份文档已同步到 Apple UI + 3 项交互修复")
