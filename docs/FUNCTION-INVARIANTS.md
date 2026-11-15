# FUNCTION-INVARIANTS · 功能不变量快照（阶段 0 基线）

> 生成：2026-11-15；源：`adb_log_gui/webview2/ui.html`（6071 行 / 276644 B）
> 用途：Apple UI 换肤期间作为 diff 基线。**本文件列出的任何一项都不允许改动。**
> 说明：附带 md（`adb_Tool-Apple-UI替换-提示词与Skill组合.md`）的盘点是旧版快照，
> 以本文件与当前源码为准。差异见 `UI-RESKIN-INVENTORY.md`。

## 1. 消息协议（onMessage 的 case）

共 28 个：`apkack` `apkapps` `apkdetail` `apkfront` `apkver` `begin` `castdisplays` `castrec` `caststat` `clear` `commands` `echo` `end` `ffmpegstat` `filePath` `fsack` `fsdone` `fslist` `fsprog` `fssearchdone` `line` `lines` `rootdone` `scrcpyres` `scrcpystat` `status` `theme` `wadb`

## 2. onclick 绑定的函数（59 个）

`addSlot` `apkAct` `apkAddApp` `apkAddCurrentFront` `apkOutClear` `apkQueryFront` `apkQuerySel` `apkQueryVersions` `apkRunCmd` `castMaxToggle` `castRecord` `castStartFromStrip` `castToggle` `clearFeed` `clearLog` `closeApkMgr` `collapseFeed` `copyApkOut` `copyCmd` `copyFeedAll` `delApk` `delSlot` `ffmpegAuto` `ffmpegPick` `fsCancel` `fsCollapseAll` `fsDelete` `fsNewFolder` `fsReload` `fsRename` `jumpLatest` `nsOutClear` `nsRun` `onApkMgrBackdrop` `onRootClick` `onRunChipClick` `openApkMgr` `pickZone` `run` `runQuick` `runQuickAt` `scrcpyAuto` `scrcpyOpen` `scrcpyPick` `sendCmd` `sendVr` `setVrMode` `stop` `switchTab` `toggleApkDrop` `toggleFeedErr` `toggleTheme` `toggleWadb` `uiBrowse` `uiCompareRun` `uiOpenResult` `uiShot` `wadbConnect` `wadbDisconnect`

## 3. 静态 DOM id（135 个）

`apk-btn-clear` `apk-btn-export` `apk-btn-kill` `apk-btn-query` `apk-btn-ver` `apk-drop` `apk-filter` `apk-front` `apk-list` `apk-mgr` `apk-mgr-list` `apk-new-name` `apk-new-pkg` `apk-out` `apk-panel` `apk-selbtn` `apk-select` `apk-seltext` `apk-sum` `btn-add` `btn-vr-send` `cast-fps` `cast-grid` `cast-hint` `cast-strip` `crumb-dev` `crumb-local` `dev-badge` `dev-dot` `dev-id` `dev-res` `dev-sep` `dev-sep2` `dev-soc` `fb-collapse-btn` `fb-collapsed-bar` `fb-collapsed-cnt` `fb-only-err` `fb-resizer` `fb-table` `feedback` `ff-dot` `ff-enc` `ff-txt` `frame` `fs-cancel` `fs-hint` `fs-panes` `fs-prog` `fs-prog-i` `fs-prog-txt` `fs-q-dev` `fs-q-local` `fs-resizer` `list-dev` `list-local` `log-lv` `log-pill` `netsim-panel` `ns-custom` `ns-delay-down` `ns-delay-up` `ns-loss-down` `ns-loss-up` `ns-out` `ns-preset` `ns-proxy` `ns-rate-down` `ns-rate-up` `page-cast` `page-cmd` `page-file` `page-quick` `page-ui` `pane-dev` `pane-local` `quick-grid` `quick-group-count` `quick-group-name` `quick-nav` `quick-scroll` `quick-search` `root-pill` `root-txt` `runbar` `runchip` `runchip-time` `sc-dot` `sc-enc` `sc-txt` `slots` `splash` `splash-tip` `theme-btn` `ui-design-box` `ui-design-empty` `ui-design-file` `ui-design-img` `ui-design-op` `ui-design-opv` `ui-design-path` `ui-hint` `ui-open-result` `ui-overlay-img` `ui-real-box` `ui-real-empty` `ui-real-file` `ui-real-img` `ui-real-op` `ui-real-opv` `ui-real-path` `ui-result-empty` `ui-result-img` `ui-result-path` `ui-resultbox` `ui-shot-front` `ui-shot-rear` `ui-thr` `vr-input` `vr-local` `vr-modes` `vr-panel` `vr-zones` `vrmode-in` `vrmode-out` `vrmode-text` `wadb` `wadb-btn` `wadb-connect` `wadb-disconnect` `wadb-dot` `wadb-host` `wadb-pop` `wadb-tip` `wadb-txt`

## 4. 页签与页面

- data-tab: `quick`, `cmd`, `file`, `cast`, `ui`
- #page-*: `page-cmd`, `page-quick`, `page-cast`, `page-ui`, `page-file`
- THEME_ORDER: `'dark', 'light', 'eye'`
- THEME_TITLE / THEME_ICON 的 key: `dark`, `eye`, `light`

## 5. 冻结的其它项

- `post(kind,data,src,slot)` / `postObj(o)` / `ready()` 的 `{kind:'ready'}`
- `window.chrome.webview.postMessage` / `postMessageWithAdditionalObjects('fileDrop',[files[0]])`
- `sendCmd` / `switchTab` / `applyTheme` / `toggleTheme` / `castToggle` / `castTap` 等函数体
- `:h` / `:shot` / `:front` / `:car` / `:sid` 等命令串、`cmds.ini` 全部 `[cmd.*]` 段
- 快捷键 Ctrl+K / Ctrl+1..4 / Alt+↓ / ↑↓ 历史 / Enter / Esc
- 行为常量：最多 3 槽、输出 12 段、34px 折叠栏、树 500 项分页、400ms 完成态、
  8 秒加载兜底、CAST_SLOTS=6、`/live/<i>` 流端口与 multipart 协议
- `adb_log_export.ini` 的 `theme=` 持久化、`GuiWeb.cs` 的 ShowIcon / ApplyDarkTitleBar / TrySetCatIcon

## 6. 表现层基线（允许改，改完需复核）

- `<style>` 段：第 6–1064 行
- CSS 硬编码色值：61 处 / 45 个不同值
- 高频硬编码色：#fff×5, #3fb99b×3, #161b22×2, #e06c6c×2, #ffffff×2, #4f7d3a×2, #a63f3f×2, #6b46c1×2, #177a66×2, #c93c3c×2, #000×2, #10151b×2
- 内联 `<svg>`：24 处；其中带硬编码 stroke/fill 的色值：#3fb99b, #a8761f, #e8a33d

## 7. 本轮新增（不属于冻结项，属用户明确要求）

- 底部缩略条：改单帧短连接（新增 `/snap/<slot>` 端点），并补每路「停止」按钮
- 文件搜索结果：去掉「进入 ⤵」按钮，点击行即展开进入树状结构；双击保留兼容
- Apple UI 表现层：三套主题语义令牌、系统字体栈、组件八态 / 视图五态、三套无障碍降级、
  内联 SVG 统一 `currentColor`、品牌改 Apple 单线终端、7 尺寸 ico（**允许层**）
- 门禁补充：`_gate_invariants.py` 对照本快照，`_build_inventory.py` 生成清单与覆盖率；
  两者只读，不进入 `verify_all.py` 的 16 项计数

