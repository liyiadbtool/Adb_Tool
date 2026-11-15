# -*- coding: utf-8 -*-
"""阶段 1-2-4：Apple 三态语义令牌 / 字体 / 硬编码色清理 / 组件与动效覆盖层。
只动 <style> 与 body 的 font-family；不碰任何 JS、id、onclick、kind。"""
import io, os, re, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")

with io.open(UI, "r", encoding="utf-8") as f:
    s = f.read()

fails = []
def rep(old, new, cnt=1, tag=""):
    global s
    n = s.count(old)
    if n != cnt:
        fails.append(u"%s: 期望 %d 处，实际 %d 处" % (tag or old[:38], cnt, n))
        return
    s = s.replace(old, new, cnt)

# ---------------------------------------------------------------- 1. 三套令牌
TOKENS = u""":root[data-theme="dark"] {
  /* Apple 深色 = dimming 而非反转：#000 → #1C1C1E → #2C2C2E 三级抬升 */
  --bg:#000000; --surface:#1c1c1e; --surface-2:#2c2c2e;
  --border:rgba(84,84,88,.60); --border-strong:rgba(235,235,245,.30);
  --text:#f5f5f7; --text-dim:rgba(235,235,245,.68); --text-faint:rgba(235,235,245,.46);
  --accent:#0a84ff; --accent-soft:rgba(10,132,255,.16);
  --ok:#30d158; --ok-soft:rgba(48,209,88,.16);
  --err:#ff453a; --err-soft:rgba(255,69,58,.14); --err-soft-hover:rgba(255,69,58,.24);
  --on-accent:#ffffff; --cast-stage:#000000;
  --lv-v:#bf5af2; --lv-d:#0a84ff; --lv-i:#30d158; --lv-w:#ff9f0a; --lv-e:#ff453a;
  --shadow-sm:0 1px 2px rgba(0,0,0,.40); --shadow-md:0 4px 12px rgba(0,0,0,.48);
  --shadow-lg:0 16px 40px rgba(0,0,0,.62); --scrim:rgba(0,0,0,.62);
  --glass:rgba(28,28,30,.72); color-scheme:dark;
}
:root[data-theme="eye"] {
  /* 护眼 = Apple 浅色 + 暖白低蓝光变体（保留第三套，绝不合并） */
  --bg:#fdfaf3; --surface:#fffdf7; --surface-2:#f6efe0;
  --border:rgba(120,105,75,.28); --border-strong:rgba(120,105,75,.46);
  --text:#3b352c; --text-dim:rgba(59,53,44,.76); --text-faint:rgba(59,53,44,.56);
  --accent:#8a5a12; --accent-soft:rgba(138,90,18,.12);
  --ok:#4f7d3a; --ok-soft:rgba(79,125,58,.12);
  --err:#a63f3f; --err-soft:rgba(166,63,63,.10); --err-soft-hover:rgba(166,63,63,.20);
  --on-accent:#fffdf7; --cast-stage:#000000;
  --lv-v:#6b46c1; --lv-d:#2f6f9c; --lv-i:#4f7d3a; --lv-w:#a8761f; --lv-e:#a63f3f;
  --shadow-sm:0 1px 2px rgba(80,66,40,.10); --shadow-md:0 4px 12px rgba(80,66,40,.14);
  --shadow-lg:0 16px 40px rgba(80,66,40,.20); --scrim:rgba(48,40,26,.38);
  --glass:rgba(255,253,247,.80); color-scheme:light;
}
:root[data-theme="light"] {
  /* Apple 浅色：冷白系统底 + 纯白卡片；accent 加深以保白字 ≥4.5:1 */
  --bg:#f2f2f7; --surface:#ffffff; --surface-2:#f2f2f7;
  --border:rgba(60,60,67,.29); --border-strong:rgba(60,60,67,.46);
  --text:#1d1d1f; --text-dim:rgba(60,60,67,.72); --text-faint:rgba(60,60,67,.54);
  --accent:#0066cc; --accent-soft:rgba(0,102,204,.10);
  --ok:#1a7f37; --ok-soft:rgba(26,127,55,.11);
  --err:#c0362c; --err-soft:rgba(192,54,44,.10); --err-soft-hover:rgba(192,54,44,.20);
  --on-accent:#ffffff; --cast-stage:#000000;
  --lv-v:#8944ab; --lv-d:#0066cc; --lv-i:#1a7f37; --lv-w:#a35a00; --lv-e:#c0362c;
  --shadow-sm:0 1px 2px rgba(0,0,0,.08); --shadow-md:0 4px 12px rgba(0,0,0,.12);
  --shadow-lg:0 16px 40px rgba(0,0,0,.20); --scrim:rgba(0,0,0,.34);
  --glass:rgba(255,255,255,.76); color-scheme:light;
}
:root{
  /* 8pt 网格 / 连续圆角 / 语义化阴影 / 统一时长与曲线（工具型：≤300ms） */
  --space-1:4px; --space-2:8px; --space-3:12px; --space-4:16px;
  --space-6:24px; --space-8:32px;
  --r-sm:6px; --r-md:10px; --r-lg:14px; --r-pill:999px;
  --dur-fast:150ms; --dur:220ms;
  --ease:cubic-bezier(.2,.8,.2,1);
  --font-ui:-apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Microsoft YaHei UI",system-ui,sans-serif;
  --font-mono:"SF Mono","JetBrains Mono",Consolas,"Microsoft YaHei UI",monospace;
}"""

start = s.index(u':root[data-theme="dark"] {')
end = s.index(u"*{box-sizing:border-box;}", start)
rep(s[start:end], TOKENS + u"\n", 1, u"三套 :root 令牌段")

# ---------------------------------------------------------------- 2. 字体栈
rep(u'font-family:"Microsoft YaHei UI","PingFang SC","Segoe UI",system-ui,sans-serif;',
    u'font-family:var(--font-ui);', 1, u"body 字体栈")

# ---------------------------------------------------------------- 3. 硬编码色 → 语义令牌
HEXMAP = [
    (u"rgba(224,108,108,.20)", u"var(--err-soft-hover)"),
    (u"rgba(224,108,108,.14)", u"var(--err-soft)"),
    (u"rgba(224,108,108,.12)", u"var(--err-soft)"),
    (u"rgba(224,108,108,.10)", u"var(--err-soft)"),
    (u"rgba(87,192,125,.22)",  u"var(--ok-soft)"),
    (u"rgba(87,192,125,.12)",  u"var(--ok-soft)"),
    (u"rgba(63,185,155,.15)",  u"var(--accent-soft)"),
    (u"rgba(63,185,155,.14)",  u"var(--accent-soft)"),
    (u"0 14px 36px rgba(0,0,0,.36)", u"var(--shadow-lg)"),
    (u"0 6px 24px rgba(0,0,0,.35)",  u"var(--shadow-lg)"),
    (u"0 12px 30px rgba(0,0,0,.32)", u"var(--shadow-lg)"),
    (u"0 18px 48px rgba(0,0,0,.42)", u"var(--shadow-lg)"),
    (u"0 24px 60px rgba(0,0,0,.55)", u"var(--shadow-lg)"),
    (u"0 1px 4px rgba(0,0,0,.35)",   u"var(--shadow-md)"),
    (u"0 2px 8px rgba(0,0,0,.18)",   u"var(--shadow-sm)"),
    (u"rgba(0,0,0,.46)", u"var(--scrim)"),
    (u"rgba(0,0,0,.55)", u"var(--scrim)"),
    (u"color:#fff;", u"color:var(--on-accent);"),
    (u"color:#fff}", u"color:var(--on-accent)}"),
    (u"color:#fff;filter:none", u"color:var(--on-accent);filter:none"),
    (u"svg{color:#fff;", u"svg{color:var(--on-accent);"),
    (u"color:#e6edf3;", u"color:var(--text);"),
    (u"color:#4a5260;", u"color:var(--text-faint);"),
    (u"background:#000;", u"background:var(--cast-stage);"),
    (u"background:#10151b;", u"background:var(--cast-stage);"),
]
for a, b in HEXMAP:
    n = s.count(a)
    if n:
        s = s.replace(a, b)

# ---------------------------------------------------------------- 4. Apple 覆盖层
LAYER = u"""
/* ==========================================================================
   Apple 设计系统覆盖层（2026-11-15）
   来源：apple-design-family(HUB) / foundations / materials / tactics / motion /
         finesse-ui(component-scope, redesign)
   适用：Windows 桌面工具型界面 —— 动效近乎不可见、spring ≤300ms、
         cinematic OFF、玻璃只给 chrome（顶栏 / 浮层 / 弹层），阅读面不透明。
   约束：只加样式，不改任何 id / class 语义 / DOM 层级 / JS。
   ========================================================================== */

/* ---- 表现层基线：字号节奏、hairline、焦点环 ---- */
html{ -webkit-font-smoothing:antialiased; }
body{ letter-spacing:.01em; }
button,input,select,textarea{ font-family:inherit; }
:focus-visible{ outline:2px solid var(--accent); outline-offset:2px; }
::selection{ background:var(--accent-soft); color:var(--text); }
*::-webkit-scrollbar{ width:10px;height:10px; }
*::-webkit-scrollbar-thumb{ background:var(--border-strong);border-radius:var(--r-pill);
  border:2px solid transparent;background-clip:padding-box; }
*::-webkit-scrollbar-thumb:hover{ background:var(--text-faint);background-clip:padding-box; }

/* ---- 命中区：桌面窗口 52px 顶栏 / 34px 折叠栏放不下 44pt，
   鼠标下保持 32px 最小高度（不撑破既有布局），触屏/粗指针下升到 44pt。
   这是工具型桌面界面的显式取舍，见 RESKIN-FINAL-REPORT.md。 ---- */
.tab,.btn,.icon-btn,.fbtn,.addbtn,.delbtn,.fs-ico,.cast-max{ min-height:32px; }
@media (pointer:coarse){
  .tab,.btn,.icon-btn,.fbtn,.addbtn,.delbtn,.fs-ico,.cast-max{ min-height:44px;min-width:44px; }
}

/* ---- 组件八态：default / hover / focus-visible / active / disabled / loading / error / success ---- */
.tab,.btn,.icon-btn,.fbtn,.addbtn,.delbtn,.fs-ico,.cast-max,.qcard,.apk-act,
.fs-act,.ns-btn,.ui-line .btn{
  transition:background-color var(--dur-fast) var(--ease),
             border-color var(--dur-fast) var(--ease),
             color var(--dur-fast) var(--ease),
             box-shadow var(--dur-fast) var(--ease),
             transform var(--dur-fast) var(--ease),
             opacity var(--dur-fast) var(--ease);
}
@media (hover:hover){
  .btn:hover:not(:disabled),.fbtn:hover:not(:disabled),.fs-act:hover:not(:disabled),
  .cast-max:hover:not(:disabled){ border-color:var(--accent); }
  .qcard:hover{ border-color:var(--accent); box-shadow:var(--shadow-md); }
  .tab:hover:not(.active){ color:var(--text); }
}
.btn:active:not(:disabled),.tab:active:not(:disabled),.icon-btn:active:not(:disabled),
.fbtn:active:not(:disabled),.cast-max:active:not(:disabled){ transform:scale(.97); }
.btn:disabled,.fbtn:disabled,.tab:disabled,.icon-btn:disabled,
input:disabled,select:disabled,textarea:disabled{
  opacity:.42;cursor:not-allowed;pointer-events:none;filter:grayscale(.35);
}
[aria-disabled="true"]{ opacity:.42;cursor:not-allowed; }
.btn.primary,.tab.active{ box-shadow:var(--shadow-sm); }
.btn.primary:focus-visible,.tab.active:focus-visible{ outline-offset:3px; }

/* 视图五态：loading / empty / error / success（不改变内容，只统一外观） */
.fs-empty,.fs-info,.ui-empty,.log-empty{ color:var(--text-faint); }
.fs-empty.err,.fb-row.err .fb-meta,.toast.err{ color:var(--err); }
.toast.ok,.fb-row .fb-meta .badge.ok{ color:var(--ok); }
.spin{ animation:spin 900ms linear infinite; }
@keyframes spin{ to{ transform:rotate(360deg); } }
.qcard.running,.cast-cell.on{ border-color:var(--accent); }

/* ---- 玻璃只给 chrome；阅读面保持不透明 ---- */
.topbar,.apk-mgr-box,.fs-modal-box,.wadb-pop,.qsearch-pop,.ui-wrap .ui-form{
  background:var(--glass);
  -webkit-backdrop-filter:blur(20px) saturate(180%);
  backdrop-filter:blur(20px) saturate(180%);
}
.topbar{ box-shadow:inset 0 -1px 0 var(--border); }
.fs-list,.fb-list,.logbox,.fs-pane,.ui-resultbox,.ui-canvas{ background:var(--surface); }
.apk-mgr,.fs-modal{ background:var(--scrim); }

/* ---- 圆角成体系：内嵌面半径 < 容器；hairline 边框不改 border-width ---- */
.qcard,.fs-pane,.apk-mgr-box,.fs-modal-box,.cast-cell,.ui-canvas,.ui-resultbox{
  border-radius:var(--r-md);
}
.tab.active,.rootpill,.wadb-pill,.logpill,.runchip{ border-radius:var(--r-pill); }
.btn,.fbtn,.fs-act,.icon-btn,.addbtn,.delbtn{ border-radius:var(--r-sm); }
.cast-thumb{ border-radius:var(--r-sm); }

/* ---- 动效：≤300ms、可中断、只动 transform/opacity/颜色；来源相关展开 ---- */
.toast,.apk-mgr-box,.fs-modal-box,.qsearch-pop{
  animation:apple-in var(--dur) var(--ease) both;
}
@keyframes apple-in{ from{ opacity:0;transform:translateY(6px) scale(.985); }
                     to{ opacity:1;transform:none; } }
.splash{ transition:opacity var(--dur) var(--ease); }
.feedback,.quick-scroll,.fs-list{ transition:opacity var(--dur-fast) var(--ease); }

/* ---- 无障碍：三个独立偏好分别降级，不混淆 ---- */
@media (prefers-reduced-motion:reduce){
  *,*::before,*::after{ animation-duration:.01ms !important;animation-iteration-count:1 !important;
    transition-duration:.01ms !important;scroll-behavior:auto !important; }
  .spin{ animation:none; }
}
@media (prefers-reduced-transparency:reduce){
  .topbar,.apk-mgr-box,.fs-modal-box,.wadb-pop,.qsearch-pop,.ui-wrap .ui-form{
    -webkit-backdrop-filter:none;backdrop-filter:none;background:var(--surface);
  }
}
@media (prefers-contrast:more){
  :root[data-theme="dark"]{ --border:rgba(235,235,245,.62);--border-strong:rgba(235,235,245,.80);
    --text-dim:rgba(235,235,245,.86);--text-faint:rgba(235,235,245,.70); }
  :root[data-theme="light"]{ --border:rgba(60,60,67,.58);--border-strong:rgba(60,60,67,.78);
    --text-dim:rgba(60,60,67,.88);--text-faint:rgba(60,60,67,.72); }
  :root[data-theme="eye"]{ --border:rgba(120,105,75,.56);--border-strong:rgba(120,105,75,.76);
    --text-dim:rgba(59,53,44,.90);--text-faint:rgba(59,53,44,.74); }
  .btn,.tab,.qcard,.fs-pane{ border-color:var(--border-strong); }
}
/* 文字缩放 200%：允许换行，不截断主体内容 */
.qcard .qname,.fs-row .n .t,.fb-row .fb-cmd{ white-space:normal;overflow-wrap:anywhere; }
"""

anchor = u"</style>"
rep(anchor, LAYER + u"\n" + anchor, 1, u"Apple 覆盖层插入")

if fails:
    for f in fails:
        sys.stdout.write(u"FAIL " + f + u"\n")
    raise SystemExit(u"[ERROR] %d 处锚点异常，未写回" % len(fails))

with io.open(UI, "w", encoding="utf-8", newline="") as f:
    f.write(s)

# 复核：CSS 段剩余硬编码色
css = s[:s.index(u"</style>")]
hard = sorted(set(re.findall(r"#[0-9a-fA-F]{3,8}\b", css)))
rgba = re.findall(r"rgba?\([^)]*\)", css)
sys.stdout.write(u"OK 令牌/字体/覆盖层已写入\n")
sys.stdout.write(u"CSS 残留 hex(%d): %s\n" % (len(hard), ", ".join(hard)))
sys.stdout.write(u"CSS 残留 rgba(%d，多为令牌定义与 44pt 扩展): %s\n" %
                 (len(rgba), ", ".join(sorted(set(rgba))[:14])))
