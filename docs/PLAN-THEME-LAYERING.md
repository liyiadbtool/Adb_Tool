# 白天 / 黑夜主题按 Edge 分层的修改方案（可执行版）

> 2026-11-28 · 目标文件：`adb_log_gui/webview2/ui.html`
> 范围：`dark` / `light` / `eye` 三套主题；**玻璃主题不动**
> 原则：先加令牌别名（零视觉变化）→ 逐层替换（每步可截图）→ 删别名

---

## 0. 一句话方案

把"组件语义"（`--bg` / `--surface` / `--surface-2`）换成"层级语义"
（`--l0-bg` … `--l5-scrim`），现有 200+ 处引用通过别名平滑过渡，
每层替换后单独截图验收，最后删别名收口。

---

## 1. 现状事实（已核对代码）

| 层 | 选择器 | 现在的背景 |
|---|---|---|
| 标题栏 | `.tb`（自绘标题栏容器） | 继承 `--bg` / 局部 `--surface` |
| 左侧导航 | `.qnav-item` 等 | 透明 + hover 用 `color-mix` |
| 内容区（快捷页） | `#page-quick .quick-body`（3198 行） | `background: var(--surface)` |
| 浮层 | `.v15-pop`（2979 行）、`.cf-panel`（5819 行） | `var(--surface)` |
| 模态遮罩 | `.cf-mask`、`#op-backdrop` | `var(--scrim)` |

问题：**标题栏、导航、内容区、浮层全指向同一个 `--surface`**，
想给其中一层单独上色，就会连带改掉其它三层。

---

## 2. 令牌定义（直接可粘贴）

### 2.1 三套主题都加这一段

```css
/* ===== 层级令牌：L0 窗口 / L1 标题栏 / L2 导航 / L3 内容 / L4 浮层 / L5 遮罩 ===== */
:root[data-theme="dark"]{
  --l0-bg:#000000;
  --l1-bg:#1c1c1e;
  --l2-bg:#161618;          /* 比 L1 略暗：侧栏"退后一层" */
  --l3-bg:#1c1c1e;
  --l4-bg:#2c2c2e;
  --l5-scrim:rgba(0,0,0,.62);
  --l3-sunken:#101012;      /* 内容区里的内凹块（代码块 / 输入框） */

  --rim-weak:rgba(84,84,88,.60);
  --rim-strong:rgba(235,235,245,.16);
  --rim-inner:rgba(255,255,255,.08);

  --l1-text:#f5f5f7;  --l1-text-dim:rgba(235,235,245,.72);
  --l3-text:#f5f5f7;  --l3-text-dim:rgba(235,235,245,.72);
  --l4-text:#f5f5f7;  --l4-text-dim:rgba(235,235,245,.72);

  --l1-tint:transparent;    /* 品牌色叠加位（默认关） */
  --l2-tint:transparent;
}

:root[data-theme="light"]{
  --l0-bg:#f2f2f7;
  --l1-bg:#f7f7fa;
  --l2-bg:#f2f2f7;          /* 侧栏是灰、内容是白（Edge 观感） */
  --l3-bg:#ffffff;
  --l4-bg:#ffffff;
  --l5-scrim:rgba(0,0,0,.34);
  --l3-sunken:#f7f7fa;

  --rim-weak:rgba(60,60,67,.29);
  --rim-strong:rgba(60,60,67,.18);
  --rim-inner:rgba(255,255,255,.90);

  --l1-text:#1d1d1f;  --l1-text-dim:rgba(60,60,67,.72);
  --l3-text:#1d1d1f;  --l3-text-dim:rgba(60,60,67,.72);
  --l4-text:#1d1d1f;  --l4-text-dim:rgba(60,60,67,.72);

  --l1-tint:transparent;
  --l2-tint:transparent;
}

:root[data-theme="eye"]{   /* 护眼：暖调，不借 light 的冷白 */
  --l0-bg:#fdfaf3;
  --l1-bg:#fffdf7;
  --l2-bg:#f8f4ea;
  --l3-bg:#fffdf7;
  --l4-bg:#f6efe0;
  --l5-scrim:rgba(48,40,26,.38);
  --l3-sunken:#f6efe0;

  --rim-weak:rgba(120,105,75,.28);
  --rim-strong:rgba(120,105,75,.20);
  --rim-inner:rgba(255,255,255,.85);

  --l1-text:#3b352c;  --l1-text-dim:rgba(59,53,44,.76);
  --l3-text:#3b352c;  --l3-text-dim:rgba(59,53,44,.76);
  --l4-text:#3b352c;  --l4-text-dim:rgba(59,53,44,.76);

  --l1-tint:transparent;
  --l2-tint:transparent;
}
```

### 2.2 别名（关键：让 200+ 处旧引用不用改）

```css
/* 旧名指到新令牌 —— 这一步"零视觉变化"，用来验证令牌本身没写错 */
:root{
  --bg:var(--l0-bg);
  --surface:var(--l3-bg);
  --surface-2:var(--l4-bg);
  --border:var(--rim-weak);
  --scrim:var(--l5-scrim);
}
```

> 注意：`--bg/--surface/--surface-2` 现在已有定义，**替换成别名**而不是再新增，
> 否则两套值并存会出现"改一处不生效"。

---

## 3. 分层替换清单（按顺序做，每步截图）

### 第 1 步：标题栏

```css
.tb{
  background:linear-gradient(var(--l1-tint), var(--l1-tint)), var(--l1-bg);
  color:var(--l1-text);
  border-bottom:1px solid var(--rim-strong);   /* Edge 的那条分隔线 */
}
.tb .tb-name{color:var(--l1-text-dim);}
```
**验收**：标题栏与内容区之间的分隔线可见；切换三套主题后标题栏颜色各自不同（不再跟卡片同色）。

### 第 2 步：左侧导航

```css
.qnav{
  background:linear-gradient(var(--l2-tint), var(--l2-tint)), var(--l2-bg);
  border-right:1px solid var(--rim-strong);
  box-shadow:none;          /* 去投影，层级靠线 */
}
.qnav-item{ color:var(--l1-text-dim); }
.qnav-item.on{ color:var(--l1-text); }
```
**验收**：深色下侧栏比标题栏暗一档；浅色下侧栏是灰、内容区是白——四层能一眼分开。

### 第 3 步：内容区

```css
#page-quick .quick-body{
  background:var(--l3-bg);
  border:1px solid var(--rim-weak);
}
.qcard{
  background:var(--l3-bg);          /* 卡片不再是另一种面 */
  border:1px solid var(--rim-weak);
  box-shadow:inset 0 1px 0 var(--rim-inner), var(--shadow-sm);
}
code, pre, .tx-area{ background:var(--l3-sunken); }
```
**验收**：卡片与内容区同色，只靠 1px 边 + 顶部内高光区分（这是 Edge 的核心观感）。

### 第 4 步：浮层

```css
.v15-pop, .cf-panel, .qsearch-pop{
  background:var(--l4-bg);
  border:1px solid var(--rim-strong);
  box-shadow:var(--shadow-lg);      /* 全屏只保留这一处大投影 */
}
```
**验收**：浮层比内容区"高一层"；关掉浮层后整屏没有第二处大投影。

### 第 5 步：模态遮罩

```css
.cf-mask, .op-mask{ background:var(--l5-scrim); }
```

### 第 6 步：删别名

把 `--bg/--surface/--surface-2/--border` 全部替换为对应的 `--l*`，
然后删除 2.2 那段别名。**必须 grep 确认没有残留**：

```bash
grep -n "var(--surface)\|var(--surface-2)\|var(--bg)\|var(--border)" adb_log_gui/webview2/ui.html
```

---

## 4. 验证清单（每步都跑）

```
编译          build_gui.bat → Compile success
门禁          python _gate_invariants.py → 44/44（新增令牌名要登记）
行为测试      377/_test_ui_behavior.py → 279/279
发送守卫      377/_test_cmd_send.py → PASS
截图          三套主题 × 1280/1100/900 三档宽度
```

**截图判据（不看边框只看看色块）**

```
□ dark：标题栏 #1c1c1e > 侧栏 #161618（侧栏更深）
□ light：内容区纯白、侧栏灰、窗口底最灰
□ eye：整体暖调，没有一处冷白
□ 四层边界清晰：标题栏 / 侧栏 / 内容 / 浮层
□ 全屏只有浮层一处大投影
```

---

## 5. 风险与回退

| 风险 | 表现 | 处置 |
|---|---|---|
| 深色侧栏变暗后"凹进去" | 与工具现有重阴影风格冲突 | 把 `--l2-bg` 调回 `#1c1c1e`，改用 `--rim-strong` 分隔 |
| 浅色内容区纯白 + 卡片同色 | 卡片边界消失 | 提高 `--rim-weak` 到 `.34`，或给卡片加 `--shadow-sm` |
| 别名删除不彻底 | 部分区域仍是旧色 | 第 6 步前先 grep 清单，逐个替换 |
| 护眼被冷白污染 | 护眼失去"暖" | eye 的 `--l3-bg` 必须 `#fffdf7`，禁用 light 的值 |

**回退**：每步一个独立提交，出问题 `git revert` 单个提交即可，
不必回退整批（这也是分 7 步做的原因）。

---

## 6. 后续填主题色的用法（这版方案的直接收益）

```css
/* 想给标题栏上品牌色：只改一行，内容区不受影响 */
:root[data-theme="light"]{ --l1-tint:rgba(0,102,204,.10); }

/* 想给侧栏做渐变：也只改一行 */
:root[data-theme="dark"]{ --l2-tint:linear-gradient(180deg, rgba(10,132,255,.10), transparent); }
```

对比现在：改标题栏要动 `--surface`，连带卡片、弹窗、内容区全变。

---

## 7. 工作量

```
第 1-5 步      每步 10~20 分钟（改 1~3 个选择器 + 截图）
第 6 步        30 分钟（grep + 批量替换 + 回归）
总             约 2 小时，7 个提交
```
