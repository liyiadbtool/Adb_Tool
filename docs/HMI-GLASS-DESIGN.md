# 液态玻璃风 HMI 设计方案（第四主题「玻璃」）

> 仅设计，不改代码。目标：在现有 黑夜 / 白天 / 护眼 三套之外，新增一套**同层级、独立**的「玻璃」主题（Apple visionOS 风格），通过 `data-theme="glass"` 启用。

---

## 1. 设计原则（4 条）

1. **玻璃是材质，不是颜色**：玻璃态不是第四种“配色”，而是一层叠加在**动态背景**上的材质系统。它同时兼容亮/暗两种环境，通过背景亮度决定前景字色。
2. **光来自材料本身**：所有玻璃面的高光、折射、描边都模拟物理光学（上缘内高光 + 边缘 1px 半透明描边 + 底部微弱投影），不靠贴图。
3. **可读性优先于炫技**：毛玻璃模糊必须可控（≤ `blur(30px) saturate(160%)`），文字永远落在可读对比度之上；关闭模糊时要自动退化为半透明纯色，功能不受影响。
4. **继承既有体系**：圆角刻度、间距、时长、字体、13 色强调色、日志等级色全部沿用，玻璃态**只新增材质令牌 + 背景层**，不新增第四套配色矩阵。

---

## 2. 令牌设计（新增，与现有 `:root[data-theme=…]` 平级）

```css
:root[data-theme="glass"] {
  /* 背景层：柔和极光 + 微噪点（玻璃要透出东西，这是"被模糊的底"） */
  --glass-bg-a: #7aa7ff;          /* 冷蓝 */
  --glass-bg-b: #c2a0ff;          /* 淡紫 */
  --glass-bg-c: #ffd6e0;          /* 暖粉 */
  --glass-noise: 0.018;           /* 噪点强度 */

  /* 材质层（亮玻璃，默认） */
  --glass-surface:   rgba(255,255,255,.54);
  --glass-surface-2: rgba(255,255,255,.38);
  --glass-elevated:  rgba(255,255,255,.68);   /* 弹窗/悬浮 */
  --glass-edge:      rgba(255,255,255,.55);   /* 外描边（上高光） */
  --glass-edge-dim:  rgba(255,255,255,.22);   /* 内分界 */
  --glass-specular:  inset 0 1px 0 rgba(255,255,255,.65);  /* 上缘高光 */
  --glass-blur:      blur(28px) saturate(170%);
  --glass-blur-soft: blur(16px) saturate(150%);

  /* 文字（亮玻璃上用深字，保证对比） */
  --text:#1d1d1f; --text-dim:rgba(28,28,32,.70); --text-faint:rgba(28,28,32,.52);

  /* 阴影：玻璃投影更轻更柔，模拟"浮在光上" */
  --shadow-sm:0 1px 2px rgba(20,30,60,.14), inset 0 1px 0 rgba(255,255,255,.5);
  --shadow-md:0 8px 24px rgba(20,30,60,.18), inset 0 1px 0 rgba(255,255,255,.55);
  --shadow-lg:0 24px 64px rgba(20,30,60,.28), inset 0 1px 0 rgba(255,255,255,.6);
  --scrim:rgba(30,40,80,.28);      /* 遮罩也用淡色，透出背景 */

  --accent:#0066cc; --accent-soft:rgba(0,102,204,.12);
  --ok:#1a7f37; --ok-soft:rgba(26,127,55,.12);
  --err:#c0362c; --err-soft:rgba(192,54,44,.10); --err-soft-hover:rgba(192,54,44,.20);
  --on-accent:#ffffff;

  color-scheme: light;
}

/* 暗玻璃变体（由背景亮度自动/手动触发，同一套玻璃逻辑） */
:root[data-theme="glass"][data-glass-tone="dark"] {
  --glass-surface:   rgba(22,24,34,.52);
  --glass-surface-2: rgba(22,24,34,.36);
  --glass-elevated:  rgba(22,24,34,.66);
  --glass-edge:      rgba(255,255,255,.22);
  --glass-edge-dim:  rgba(255,255,255,.10);
  --glass-specular:  inset 0 1px 0 rgba(255,255,255,.18);
  --text:#f5f5f7; --text-dim:rgba(235,235,245,.72); --text-faint:rgba(235,235,245,.54);
  --accent:#0a84ff; --accent-soft:rgba(10,132,255,.16);
  --ok:#30d158; --ok-soft:rgba(48,209,88,.16);
  --err:#ff453a; --err-soft:rgba(255,69,58,.14); --err-soft-hover:rgba(255,69,58,.24);
  --shadow-sm:0 1px 2px rgba(0,0,0,.40), inset 0 1px 0 rgba(255,255,255,.12);
  --shadow-md:0 8px 24px rgba(0,0,0,.44), inset 0 1px 0 rgba(255,255,255,.14);
  --shadow-lg:0 24px 64px rgba(0,0,0,.60), inset 0 1px 0 rgba(255,255,255,.16);
  color-scheme: dark;
}
```

> 说明：玻璃态下 **accent / ok / err / 日志等级色仍随强调色切换**，与既有 13 色体系完全兼容，不新增色相。

---

## 3. 背景层（玻璃的灵魂）

玻璃态需要一个“被模糊的底”，放在最底层：

```
层级（自底向上）：
  ① 极光底  body 背景 = 多层径向渐变（--glass-bg-a/b/c）缓慢流动
  ② 噪点层  伪元素 + SVG feTurbulence 或 CSS 噪点图，透明度 --glass-noise
  ③ 内容层  所有 surface 用 backdrop-filter 模糊 ①+②，产生“玻璃”质感
```

- 极光用 3 个径向渐变（冷蓝/淡紫/暖粉）各占一角，`background-blend-mode: screen`。
- 动效：极光 60s 极慢平移（`transform` 位移），**可关闭**；关闭后静止底仍保留玻璃效果。
- 性能：噪点用静态图（不做实时 per-pixel），模糊只作用于 surface 面积，不在整页 blur。

---

## 4. 组件规格

| 组件 | 玻璃态规格 |
|---|---|
| **卡片** | `surface` 半透明 + `blur(28px) saturate(170%)` + 上缘 1px 内高光 + `edge` 描边；圆角沿用 `--r-4/10px`；hover 时 `elevated` + `shadow-md` + 上浮 `translateY(-1px)` |
| **面板/抽屉** | `elevated` 更高不透明 + `shadow-lg`；边缘内高光更亮，突出“浮起” |
| **标题栏** | 顶部 1px `edge-dim` 分界 + 底部 `blur(20px)`，悬浮不遮挡内容 |
| **输入框** | `surface-2` 浅玻璃 + 内凹投影 `inset 0 1px 2px rgba(...)`，聚焦时 `edge` 变 `--accent` 且高光增强 |
| **按钮（主）** | `--accent` 实色底 + `--on-accent` 白字（不透明，保证点击区对比）；按下 `scale(.97)` |
| **按钮（次）** | `surface-2` 玻璃 + 描边；hover 提亮 `surface`；按下 `scale(.97)` |
| **选中态** | `--accent-soft` 半透明叠加 + `--accent` 描边（与现有一致，只是底变玻璃） |
| **滚动条** | 细玻璃条 `rgba(120,130,160,.35)` + `border-radius:pill`，hover 提亮 |
| **遮罩** | 淡色 `--scrim` 半透明，`blur(4px)` 轻微雾化，透出背景 |
| **弹窗** | `elevated` + `blur(32px)` + 双层描边（外 `edge`、内 1px 白高光），出现 `scale(.96→1)` + `opacity` |
| **危险/成功** | 沿用 `--err / --ok`，仅底材变玻璃，色相不变 |

---

## 5. 动效（统一 ≤300ms，与既有时长一致）

| 交互 | 玻璃态动效 |
|---|---|
| 卡片 hover | `translateY(-1px)` + 阴影加深 + 透明度提升，`--dur-fast` |
| 按钮 press | `scale(.97)`，`--dur-fast` |
| 弹窗进入 | `scale(.96→1)` + `opacity 0→1`，`--dur` `--ease` |
| 页签切换 | 保持现有瞬时切换（无位移动画） |
| 极光背景 | 60s 慢移，`prefers-reduced-motion` 下静止 |

---

## 6. 无障碍与降级

1. **对比度**：亮玻璃字色固定深色（≥4.5:1），暗玻璃固定浅色；玻璃底只做背景，不承载文字。
2. **无模糊降级**：检测不到 `backdrop-filter` 时，`--glass-surface` 退化为不透明近似色（`.52→.9`），界面仍完整可用。
3. **减少透明**：`prefers-reduced-transparency` 下关闭模糊与极光动效，玻璃面退化为纯色。
4. **减少动效**：`prefers-reduced-motion` 下极光静止、卡片不上浮。

---

## 7. 与现有三套主题的关系

```
显示选项（4 档，同一层级）：
  跟随系统  |  OLED 深黑  |  护眼  |  玻璃
             （= 现 dark）        （= 现 eye）   ← 新增

启用方式：document.documentElement.setAttribute('data-theme','glass')
玻璃色调：默认亮玻璃；用户可切「玻璃·暗」→ data-glass-tone="dark"
强调色：玻璃态下仍可切 13 色（沿用现有 data-accent 机制）
```

**不改代码的落地路径（供后续实现参考）**：

```
① :root[data-theme="glass"] 令牌块（本节 §2）
② body 加一层极光底 + 噪点伪元素
③ surface 类补 backdrop-filter（用 --glass-blur 令牌）
④ 显示选项面板加第四档「玻璃」（含 亮/暗 子开关）
⑤ 持久化到现有 PREFS（与主题/强调色同一通道）
```

---

## 8. 验收标准（实现后核对）

```
① 四档平级切换，玻璃态不影响其它三档
② 玻璃态下强调色仍可切 13 色、日志等级五色仍区分
③ 关闭模糊/减少透明后，功能与可读性不降级
④ 弹窗、遮罩、滚动条、输入框均有玻璃质感而非纯白块
⑤ 极光背景 60s 慢移，减少动效时静止
```
