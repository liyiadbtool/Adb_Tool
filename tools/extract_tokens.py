# -*- coding: utf-8 -*-
"""从 ui.html 抽出设计系统，生成 tokens.css / components.css 供 Agent 工作台复用。

背景
----
Agent 工作台是独立页面（agent.html），但它必须和主界面"长得一模一样"——
主题、强调色、字号、圆角、间距、字体全都得跟着走。

手工抄一份 CSS 是不可行的：主界面几乎每次改动都会动令牌，
抄过去的东西一周就漂移了，最后变成"两个应用两副面孔"。

所以这里走**单向流水线**：

    ui.html（唯一真源）
        ↓  python tools/extract_tokens.py
    tokens.css / components.css（生成物，不手改）
        ↓  被 agent.html 引用

纪律
----
1. ui.html 是唯一真源；agent 侧需要新令牌，先加到 ui.html，再重跑本脚本。
2. 生成物带源文件 md5，用来判断"是否已同步"（verify_all.py 会校验）。
3. 抽取必须**自校验**：令牌数、主题数、强调色规则数对不上就报错退出，
   绝不生成一份"少了半截"的 CSS 让下游默默出错。
4. **数据隔离**：生成物只写 agent_workbench\\gen\\，绝不写进
   adb_log_gui\\webview2\\（主应用源码目录）。那边多一个文件就会被
   build_gui.bat 打进 dist 发布包，属于污染。

抽取范围（锚点已在 ui.html 中确认）
--------------------------------
    A  三套主题令牌      :root[data-theme="dark|eye|light"]
    B  通用令牌          :root{ ... }（间距/圆角/时长/字体）
    C  基础重置          * / html,body / body / .frame / .frame.show
    D  无障碍媒体查询    prefers-reduced-transparency / prefers-contrast
    E  强调色矩阵        48 条 :root[data-theme][data-accent]

用法
----
    python tools/extract_tokens.py            # 生成
    python tools/extract_tokens.py --check    # 只校验是否同步（不写文件）
"""
import hashlib
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
# ★ 数据隔离（用户明确要求）：生成物**绝不**写进 adb_log_gui\webview2\
#   那里是主应用的源码目录，任何多余文件都会被 build_gui.bat 打进 dist，
#   等于用开发中间产物污染发布包。全部收进独立的 agent_workbench\gen\。
OUT_DIR = os.path.join(ROOT, "agent_workbench", "gen")
OUT_TOKENS = os.path.join(OUT_DIR, "tokens.css")
OUT_COMPONENTS = os.path.join(OUT_DIR, "components.css")

# ---- 预期值：ui.html 一旦变化，这里要同步更新（校验失败时会提示新值） ----
EXPECT_THEMES = 3            # dark / eye / light
EXPECT_ACCENT_RULES = 48     # 16 色 × 3 主题
# 注意：这里数的是"变量定义**次数**"，同一变量在三套主题各定义一次会算 3 次
# （--accent 就出现 3 次）。所以是 258 而不是 190（190 是"含 -- 的源码行数"）。
EXPECT_TOKEN_DEFS = 258

# 组件白名单：只收这些前缀的规则（其余都是页面专属，不该进公共样式）
# 组件白名单：只列 ui.html 里**真实存在且通用**的。
# 核查结论（2026-11-26）：
#   · .btn / .set-seg / .h5-seg  → 全站公共，直接复用
#   · .inp / .card / .mini-btn   → **主界面没有**。输入框是各页面自己写的
#     （qinp / mk-inp / clu-inp），卡片只有 diag-card（页面专属）。
#   所以 agent 侧的卡片与输入框要用**令牌新建**（--surface/--r-4/--border/--space-*），
#   不放在这里假装"复用"。
COMPONENT_PREFIXES = (".btn", ".set-seg", ".h5-seg")
# 选择器里出现这些就跳过（页面专属 / 已废弃）
COMPONENT_SKIP = ("#page-", "#diag-", "#agent-", ".qcard", ".diag-", ".fb-", ".fs-")


def read_ui():
    if not os.path.exists(UI):
        raise SystemExit("[ERROR] 找不到 ui.html: " + UI)
    return io.open(UI, encoding="utf-8").read()


def extract_style(html):
    """取出 <style>...</style> 的内容。只认第一对（本项目只有一个）。"""
    m = re.search(r"<style>(.*?)</style>", html, re.S)
    if not m:
        raise SystemExit("[ERROR] ui.html 里找不到 <style> 段")
    return m.group(1)


def strip_comments(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def grab_block(css, marker):
    """从 marker 起抓一个配平的 {...} 块。

    为什么不用正则：CSS 里有嵌套（@media 内部还有规则），
    正则数不清嵌套层级，会出现"抓到一半"的问题。
    """
    i = css.find(marker)
    if i < 0:
        return None
    j = css.find("{", i)
    if j < 0:
        return None
    depth = 0
    k = j
    while k < len(css):
        c = css[k]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return css[i:k + 1]
        k += 1
    return None


ACCENT_RE = re.compile(
    r':root\[data-theme="[a-z]+"\]\[data-accent="[a-z]+"\]\s*\{[^}]*\}'
)


def collect_tokens(css):
    """返回 (段列表, 统计信息)"""
    parts = []
    stat = {}

    # ---- A 三套主题 ----
    themes = []
    for th in ("dark", "eye", "light"):
        blk = grab_block(css, ':root[data-theme="%s"]' % th)
        if not blk:
            raise SystemExit('[ERROR] 找不到主题令牌 :root[data-theme="%s"]' % th)
        themes.append(blk)
    parts.extend(themes)
    stat["themes"] = len(themes)

    # ---- B 通用令牌 :root{ ----
    idx = css.find(":root{")
    if idx < 0:
        idx = css.find(":root {")
    if idx < 0:
        raise SystemExit("[ERROR] 找不到通用令牌 :root{...}")
    blk = grab_block(css, ":root" )
    # grab_block 会命中第一个 :root（即 dark 主题），这里显式从 idx 起抓
    j = css.find("{", idx)
    depth = 0
    k = j
    while k < len(css):
        if css[k] == "{":
            depth += 1
        elif css[k] == "}":
            depth -= 1
            if depth == 0:
                blk = css[idx:k + 1]
                break
        k += 1
    parts.append(blk)
    stat["has_root_generic"] = True

    # ---- C 基础重置 ----
    # ★ 必须按**选择器完全相等**匹配，不能用子串 find：
    #   曾经用 css.find("body{") —— 它命中的是 "html,body{" 里的那段，
    #   于是真正的 body{...}（12 行字体/背景/防选中规则）被丢掉，
    #   换成一条空的 body{height:100%;margin:0;}。下游样式全崩且很难看出来。
    BASE_SELECTORS = {"*", "html,body", "body", ".frame", ".frame.show"}
    base = []
    for m in SIMPLE_RULE.finditer(css):
        sel = " ".join(m.group(1).split())
        if sel in BASE_SELECTORS:
            base.append("%s{%s}" % (sel, m.group(2).strip()))
    parts.append("\n".join(base))
    stat["base_rules"] = len(base)

    # 自校验：body 规则必须包含字体与背景（原版就有，丢了说明抓错）
    body_blk = next((b for b in base if b.startswith("body{")), "")
    if "font-family" not in body_blk or "background" not in body_blk:
        raise SystemExit("[ERROR] body{...} 抓取不完整（缺 font-family/background），"
                         "疑似被 html,body{ 干扰")

    # ---- D 无障碍媒体查询 ----
    a11y = []
    for mk in ('@media (prefers-reduced-transparency', '@media (prefers-contrast',
               '@media (prefers-reduced-motion'):
        b = grab_block(css, mk)
        if b:
            a11y.append(b)
    parts.append("\n".join(a11y))
    stat["a11y_blocks"] = len(a11y)

    # ---- E 强调色矩阵 ----
    accents = ACCENT_RE.findall(css)
    parts.append("\n".join(accents))
    stat["accent_rules"] = len(accents)

    return "\n\n".join(p for p in parts if p.strip()), stat


def _prefix_hit(sel, prefix):
    """sel 是否以 prefix 开头且边界合法（后面是结尾或 . : [ , 空格 > 等）。"""
    if not sel.startswith(prefix):
        return False
    if len(sel) == len(prefix):
        return True
    return sel[len(prefix)] in ".:[ ,>~+"


SIMPLE_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.S)


def collect_components(css):
    """按白名单抓简单规则（不含嵌套的）。"""
    out = []
    seen = set()
    for m in SIMPLE_RULE.finditer(css):
        sel = m.group(1).strip()
        body = m.group(2)
        if not sel or "\n\n" in sel:
            continue
        # 选择器里带换行说明是多个规则粘连，跳过
        one_line_sel = " ".join(sel.split())
        if any(bad in one_line_sel for bad in COMPONENT_SKIP):
            continue
        # 只认**第一段选择器**的前缀。原来的宽松匹配（find(p+" ") 等）
        # 会把 ".inputbar" 这种页面专属类当成组件收进来 —— 公共样式里
        # 混入主界面内部结构，下游一旦复制过去就带着耦合。
        first = one_line_sel.split(",")[0].strip()
        first = first.split(" ")[0] if first else ""
        # 前缀匹配必须**边界安全**：".inp" 是 ".inputbar" 的前缀，
        # 不检查后续字符就会把页面专属的 .inputbar / .inputwrap 收进来。
        if not any(_prefix_hit(first, p) for p in COMPONENT_PREFIXES):
            continue
        key = one_line_sel + "|" + body.strip()
        if key in seen:
            continue
        seen.add(key)
        out.append("%s{%s}" % (one_line_sel, body.strip()))
    return "\n".join(out)


def count_token_lines(css):
    return len(re.findall(r"--[a-zA-Z0-9-]+\s*:", css))


def md5(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()


HEADER = """/* ============================================================================
   ⚠ 自动生成，请勿手改
   来源   : adb_log_gui/webview2/ui.html
   生成   : python tools/extract_tokens.py
   源 md5 : {src_md5}
   {extra}
   改设计令牌请改 ui.html，然后重跑脚本。
   ============================================================================ */
"""


def main():
    check_only = "--check" in sys.argv

    html = read_ui()
    src_md5 = md5(html)
    raw = extract_style(html)
    css = strip_comments(raw)

    tokens_body, stat = collect_tokens(css)
    comps_body = collect_components(css)

    token_lines = count_token_lines(tokens_body)

    # ---------------- 自校验 ----------------
    problems = []
    if stat["themes"] != EXPECT_THEMES:
        problems.append("主题数 %d（期望 %d）" % (stat["themes"], EXPECT_THEMES))
    if stat["accent_rules"] != EXPECT_ACCENT_RULES:
        problems.append("强调色规则 %d（期望 %d）" % (stat["accent_rules"], EXPECT_ACCENT_RULES))
    if token_lines != EXPECT_TOKEN_DEFS:
        problems.append("令牌定义 %d 次（期望 %d）" % (token_lines, EXPECT_TOKEN_DEFS))
    if not comps_body.strip():
        problems.append("组件段为空（白名单一个都没抓到）")

    # 组件里不允许出现裸色值（除 rgba(0,0,0,...) 这类全透明遮罩）
    raw_hex = re.findall(r"#[0-9a-fA-F]{3,8}\b", comps_body)
    if raw_hex:
        problems.append("组件段含裸色值 %d 处：%s" % (len(raw_hex), ", ".join(sorted(set(raw_hex))[:6])))

    if problems:
        print("[FAIL] 抽取结果不符合预期：")
        for p in problems:
            print("   ·", p)
        print()
        print("如果 ui.html 确实是**有意**改了，请更新脚本顶部的 EXPECT_* 常量。")
        return 2

    tokens = (
        HEADER.format(src_md5=src_md5,
                      extra="内容   : 令牌定义 %d 次 / 主题 %d 套 / 强调色规则 %d 条"
                            % (token_lines, stat["themes"], stat["accent_rules"]))
        + "\n" + tokens_body + "\n"
    )
    comps = (
        HEADER.format(src_md5=src_md5,
                      extra="内容   : 公共组件（按钮/输入/卡片/分段/小按钮/滚动条）")
        + "\n" + comps_body + "\n"
    )

    if check_only:
        ok = True
        for path, content in ((OUT_TOKENS, tokens), (OUT_COMPONENTS, comps)):
            if not os.path.exists(path):
                print("[FAIL] 缺少生成物:", os.path.basename(path))
                ok = False
                continue
            cur = io.open(path, encoding="utf-8").read()
            if cur != content:
                print("[FAIL] 已过期，需要重跑 extract_tokens.py:", os.path.basename(path))
                ok = False
        if ok:
            print("[OK] tokens.css / components.css 与 ui.html 同步（src md5 %s）" % src_md5[:12])
            return 0
        return 1

    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)
    io.open(OUT_TOKENS, "w", encoding="utf-8", newline="").write(tokens)
    io.open(OUT_COMPONENTS, "w", encoding="utf-8", newline="").write(comps)

    print("[OK] 已生成：")
    print("     tokens.css      %5d 字节  令牌 %d 次 / 主题 %d / 强调色 %d"
          % (len(tokens), token_lines, stat["themes"], stat["accent_rules"]))
    print("     components.css  %5d 字节  组件规则 %d 条"
          % (len(comps), len(comps_body.split("\n"))))
    print("     源 md5 %s" % src_md5[:12])
    return 0


if __name__ == "__main__":
    sys.exit(main())
