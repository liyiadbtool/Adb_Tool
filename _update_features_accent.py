# -*- coding: utf-8 -*-
"""把 A9 第三批（9 色强调色 + 可见视觉增强）追加进 _check_features.json。"""
import io
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(ROOT, "_check_features.json")
with io.open(P, "r", encoding="utf-8") as f:
    cfg = json.load(f)

key = "features" if "features" in cfg else None
if key is None:
    for k, v in cfg.items():
        if isinstance(v, list) and v and isinstance(v[0], dict) and "id" in v[0]:
            key = k
            break
arr = cfg[key]
have = set(x["id"] for x in arr)

NEW = [
    {
        "id": "accent.picker",
        "desc": "顶栏 9 色强调色切换器（红黄蓝白紫黑绿橙粉）：只切按钮/进度条/滑块/radio/选中态等 --accent 派生色，明暗三态背景不变；27 条 主题×色 令牌按 Apple system* 明暗配对生成并自动校验 WCAG 对比度",
        "anchors": [
            {"file": "adb_log_gui/webview2/ui.html", "has": [
                "var ACCENT_ORDER = ['red','yellow','blue','white','purple','black','green','orange','pink'];",
                "function applyAccent(name)",
                "document.documentElement.setAttribute('data-accent', name)",
                "/* === ACCENT LAYER START === */"
            ]},
            {"file": "docs/ACCENT-CONTRAST.md", "has": [
                "WCAG 2.2 AA", "自适应为 systemGray"
            ]},
            {"file": "_gen_accent.py", "has": [
                "ORDER = [\"red\", \"yellow\", \"blue\", \"white\", \"purple\", \"black\", \"green\", \"orange\", \"pink\"]",
                "ratio(c, surface) >= 3.0"
            ]},
        ],
        "tests": ["377/_check_ui.js", "_check_accent_dom.py", "_gate_invariants.py"],
    },
    {
        "id": "accent.persistence",
        "desc": "强调色持久化：新增 accent 消息 kind 与 ini 的 accent= 键，重启后按钮/进度条/选中态保持用户选色；旧 ini 无该键时自动追加，不破坏其它键",
        "anchors": [
            {"file": "_cs/GuiWeb.cs", "has": [
                "case \"accent\":", "SaveAccentPreference", "Json(App.ACCENT)"
            ]},
            {"file": "_cs/Prefix.cs", "has": ["internal static string ACCENT = \"blue\";"]},
            {"file": "_cs/Program.cs", "has": ["case \"accent\":"]},
            {"file": "adb_log_gui/adb_log_export.ini", "has": ["accent=blue"]},
            {"file": "adb_log_export.ini", "has": ["accent=blue"]},
        ],
        "tests": ["_check_features.js", "_check_apple_release.py"],
    },
    {
        "id": "visual.enhance",
        "desc": "通读 md 后的可见 Apple 化增强：页签改分段控件观感、主按钮改实心 accent 填充、卡片加层级阴影与 hover 抬升、顶栏 56px 与 8pt 留白、:focus-visible 统一 accent；全部只改 <style>，不动 DOM/JS 冻结层",
        "anchors": [
            {"file": "adb_log_gui/webview2/ui.html", "has": [
                ".btn.primary{", "background:var(--accent);border-color:var(--accent);color:var(--on-accent)",
                ".tabs .tab.active{", "box-shadow:var(--shadow-sm)",
                ".topbar{height:56px;gap:12px;padding:0 20px;}"
            ]},
        ],
        "tests": ["377/_check_ui.js", "377/_test_structure.py"],
    },
]

added = [x for x in NEW if x["id"] not in have]
arr.extend(added)
with io.open(P, "w", encoding="utf-8", newline="") as f:
    f.write(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
print("OK features=%d（新增 %d）" % (len(arr), len(added)))
