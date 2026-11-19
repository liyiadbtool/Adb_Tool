# 门禁 1 · 功能不变量对照表（阶段 6）

> 生成：`python _gate_invariants.py`（只读，重复运行结果一致）。
> 项目**不是 git 仓库**，无法用 `git diff`；本表用「阶段 0 快照 vs 当前源码逐项解析」等价核验。
> 基线：`docs/FUNCTION-INVARIANTS.md`；被检源码：`adb_log_gui/webview2/ui.html`、`_cs/Cast.cs`、`*.ico`。

| 核验项 | 结论 | 说明 |
|---|---|---|
| onMessage 的 kind（基线 28） | PASS | 基线 28 / 当前 39；新增 ['accent', 'build', 'customcmds', 'netsimlog', 'netsimstat', 'netsimstate', 'prefs', 'texterr', 'textfile', 'textsaved', 'winstate']；经批准删除 无；违约删除 无；未登记新增 无 |
| onclick 绑定函数（基线 59） | PASS | 基线 59 / 当前 96；新增 ['accentPopClick', 'apkFillFront', 'appClose', 'closeCustomMgr', 'closeHelp', 'closeSettings', 'cmAddStep', 'cmBackdrop', 'cmDel', 'cmDelStep', 'cmEdit', 'cmNew', 'cmSave', 'fbHeadToggle', 'fsRetry', 'fsSwapSides', 'helpGo', 'openCustomMgr', 'openHelp', 'setSize', 'setThemeByName', 'tbClose', 'tbMax', 'tbMin', 'toggleSettings', 'txClose', 'txFindClose', 'txFindNext', 'txFindOpen', 'txGoto', 'txNew', 'txOpen', 'txReplaceAll', 'txReplaceOne', 'txSave', 'txSelect', 'txSyncCaret', 'txToggleWrap', 'txUndoRedo', 'txZoom']；经批准删除 ['scrcpyOpen', 'sendCmd', 'toggleTheme']；违约删除 无；未登记新增 无 |
| 静态 DOM id（基线 135） | PASS | 基线 135 / 当前 204；新增 ['a15-sec-display', 'accent-pop', 'apk-btn-fillfront', 'apk-btn-uninstall', 'apk-pkg-hint', 'apk-pkg-input', 'appmark-bg', 'appmark-glyph', 'build-stamp', 'cm-desc', 'cm-err', 'cm-grid', 'cm-list', 'cm-name', 'cm-steps', 'custom-mgr', 'custom-panel', 'fs-swap', 'help-doc', 'help-mask', 'help-search', 'help-toc', 'log-dot', 'ns-stat', 'ns-state', 'page-text', 'set-auto', 'set-display-hint', 'set-eyelevel', 'set-font', 'set-font-preview', 'set-fsize', 'set-mask', 'set-oled', 'set-theme', 'settings-btn', 'tb-close', 'tb-max', 'tb-min', 'tb-status', 'tb-sub', 'titlebar', 'tx-body', 'tx-case', 'tx-edit', 'tx-enc', 'tx-eol', 'tx-find', 'tx-find-i', 'tx-find-n', 'tx-gutter', 'tx-repl-all', 'tx-repl-i', 'tx-repl-one', 'tx-st-enc', 'tx-st-eol', 'tx-st-font', 'tx-st-len', 'tx-st-pos', 'tx-st-sel', 'tx-tabs', 'tx-wrap-btn', 'tx-zoom-val', 'v15-devh', 'v15-devoff', 'v15-devrefresh', 'v15-devrows', 'v15-lvdev', 'v15-lvshow', 'v15-lvstate']；经批准删除 ['theme-btn']；违约删除 无；未登记新增 无 |
| data-tab 页签顺序 | PASS | 基线 ['quick', 'cmd', 'file', 'cast', 'ui'] / 当前 ['quick', 'cmd', 'file', 'cast', 'ui', 'text'] |
| #page-* 页面集合 | PASS | 基线 ['page-cmd', 'page-quick', 'page-cast', 'page-ui', 'page-file'] / 当前 ['page-cmd', 'page-quick', 'page-cast', 'page-ui', 'page-file', 'page-text'] |
| post() 签名（v12 起多一个 extra 字段包） | PASS | function post(kind, data, src, slot, extra){ |
| postObj() 签名 | PASS | function postObj(o){ |
| sendCmd() 签名 | PASS | function sendCmd(cmd){ |
| switchTab() 签名 | PASS | function switchTab(name){ |
| applyTheme() 签名 | PASS | function applyTheme(name){ |
| toggleTheme() 签名 | PASS | function toggleTheme(){ |
| WebView2 消息桥 | PASS | window.chrome.webview.postMessage(o) |
| ready() 回包 | PASS | {kind:'ready'} |
| 文件拖放桥 | PASS | postMessageWithAdditionalObjects('fileDrop', [fi |
| THEME_ORDER 冻结 | PASS | var THEME_ORDER = ['dark', 'light', 'eye']; |
| 三处旧品牌硬编码色全文件清零 | PASS | [] |
| 内联 SVG 硬编码 stroke/fill = 0 | PASS | [] |
| 组件样式零硬编码色（令牌定义段除外） | PASS | [] |
| 主题 dark 的 17 个语义令牌齐备 | PASS | 17/17 |
| 主题 light 的 17 个语义令牌齐备 | PASS | 17/17 |
| 主题 eye 的 17 个语义令牌齐备 | PASS | 17/17 |
| 无障碍降级 prefers-reduced-motion | PASS |  |
| 无障碍降级 prefers-reduced-transparency | PASS |  |
| 无障碍降级 prefers-contrast | PASS |  |
| 键盘焦点 :focus-visible | PASS |  |
| ICO-01 / ICO-02 字节一致 | PASS | 32187 / 32187 B |
| ICO 多尺寸齐备（16/24/32/48/64/128/256） | PASS | [16, 24, 32, 48, 64, 128, 256] |
| 可编辑 SVG 源存在（图标 v2：车载中控终端） | PASS |  |
| A9 追加轮 · 缩略条 /snap 单帧端点 | PASS |  |
| A9 追加轮 · 前端缩略条走 /snap + 1 秒轮询 | PASS |  |
| A9 追加轮 · 缩略条每路停止按钮 | PASS |  |
| A9 追加轮 · 搜索结果点击整行进树 | PASS |  |
| A9 追加轮 · 旧的「进入 ⤵」按钮已删 | PASS |  |
| A9 追加轮 · 搜索态 dblclick 兼容 | PASS |  |
| A9 追加轮 · 13 色强调色 · 16 色顺序冻结（色相环 + 三白） | PASS |  |
| A9 追加轮 · 13 色强调色 · 48 条 主题×色 令牌规则齐备 | PASS |  |
| A9 追加轮 · 13 色强调色 · 色板 16 个可点色点 | PASS |  |
| A9 追加轮 · 13 色强调色 · 切色只改 data-accent，不改 data-theme | PASS |  |
| A9 追加轮 · 13 色强调色 · 前端回传 accent 消息 | PASS |  |
| A9 追加轮 · 13 色强调色 · 后端接收并持久化 accent | PASS |  |
| A9 追加轮 · 13 色强调色 · 启动时回传 accent | PASS |  |
| A9 追加轮 · 13 色强调色 · ini 两个源都有 accent= 键 | PASS |  |
| A9 追加轮 · 13 色强调色 · ACCENT 状态字段与 ini 解析 | PASS |  |
| A9 追加轮 · 13 色强调色 · 对比度表已生成 | PASS |  |

**合计 44 项，失败 0 项。**

## 判定

- 冻结层（kind / onclick / DOM id / 页签 / 页面 / 消息桥 / THEME_ORDER）：**0 删除 / 0 改名**；新增项均已登记
- 允许层（`<style>` 语义令牌、内联 SVG 图形与颜色、图标文件）：已改，见 `COVERAGE.md`。
- 追加轮（3 个交互缺陷 + 强调色切换器）：**超出 A10「纯换肤」范围**，属用户本轮显式要求，按 A9 处理并在 `UI-RESKIN-INVENTORY.md` 追加 ID、重算分母。
- A15 轮（显示选项 / 日志等级 / 设备管理）：新增 12 个静态 id，全部逐条登记在 `A15_ADDS`；**0 个 new kind**——回推走 `window.v15Msg` 覆写 + C# 既有 post 通道，未扩消息契约。
- 本轮新增：`accent` kind、3 个 DOM id、2 个 onclick、13×3 条语义令牌规则；改动落在 `ui.html` 的渲染/事件函数、`_cs/Cast.cs` 的 `/snap` 端点、`_cs/GuiWeb.cs` / `Prefix.cs` / `Program.cs` 的 accent 持久化、以及 ini **新增** `accent=` 键。
- 仍未触碰：`post()` 签名、既有 28 个 kind、既有 onclick、命令串、既有 ini key、`THEME_ORDER`、三套明暗主题取值、快捷键与 DOM 层级。

