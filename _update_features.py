# -*- coding: utf-8 -*-
"""同步机检清单：搜索交互变更 + 本轮 4 项 Apple/投屏新功能登记。"""
import io, json, os, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(ROOT, "_check_features.json")

with io.open(P, "r", encoding="utf-8") as f:
    cfg = json.load(f)

feats = cfg["features"]

# ---- 1. 旧的「进入」按钮交互 → 点击行进入树状结构 ----
hit = [x for x in feats if x.get("id") == "fs.search-enter"]
if len(hit) != 1:
    raise SystemExit("[ERROR] fs.search-enter 条目数异常 %d" % len(hit))
hit[0]["id"] = "fs.search-click"
hit[0]["desc"] = "文件搜索结果不再挂「进入 ⤵」按钮；点击结果行即退出搜索、展开祖先链进入树状结构，与未搜索时树交互一致"
hit[0]["anchors"] = [{
    "file": "adb_log_gui/webview2/ui.html",
    "has": [
        "data-search=\"1\"",
        "点击结果进入树状结构",
        "function fsOpenSearchDir",
        ".fs-row[data-search=\"1\"]",
        "getAttribute('data-search')"
    ]
}]
hit[0]["tests"] = ["377/_test_fs_search.py"]

NEW = [
    {
        "id": "cast.strip-snap",
        "desc": "投屏超过 2 路后底部缩略条不再黑屏：底部改走 /snap 单帧短连接，不占 /live 长连接池；1 秒轮询只换 img.src 不重建 DOM",
        "anchors": [
            {"file": "adb_log_gui/webview2/ui.html",
             "has": ["function castRefreshStripFrames", "/snap/' + i", "castRefreshStripFrames();   // 2026-11-15"]},
            {"file": "_cs/Cast.cs",
             "has": ["path.StartsWith(\"/snap/\"", "Content-Type: image/jpeg", "Connection: close"]}
        ],
        "tests": ["377/_test_cast_ui.py"]
    },
    {
        "id": "cast.strip-stop",
        "desc": "全屏投屏时底部缩略条每路补「停止」按钮，不用退出全屏即可关闭别路（事件委托 [data-stop]）",
        "anchors": [
            {"file": "adb_log_gui/webview2/ui.html",
             "has": ["cast-thumb-stop", "data-stop=\"' + i + '\"", "closest('[data-stop]')"]}
        ],
        "tests": ["377/_test_cast_ui.py"]
    },
    {
        "id": "apple.tokens",
        "desc": "Apple 三态语义令牌：dark/light/eye 各 17 角色 + 系统字体栈 + 8pt 网格 + 连续圆角 + 三套无障碍降级；THEME_ORDER 不变",
        "anchors": [
            {"file": "adb_log_gui/webview2/ui.html",
             "has": ["--bg:#000000; --surface:#1c1c1e; --surface-2:#2c2c2e",
                     "--bg:#fdfaf3; --surface:#fffdf7",
                     "--accent:#0066cc;",
                     "--font-ui:-apple-system",
                     "prefers-reduced-transparency",
                     "prefers-contrast:more",
                     "var THEME_ORDER = ['dark', 'light', 'eye']"]}
        ],
        "tests": ["377/_test_ux.py"]
    },
    {
        "id": "apple.icons",
        "desc": "图标专项：24 处内联 SVG 统一 24×24（加载层 48×48）/ 1.75 stroke / currentColor，硬编码色清零；品牌改 Apple 单线终端，7 尺寸 ico 与顶栏/加载层/任务栏同源",
        "anchors": [
            {"file": "adb_log_gui/webview2/ui.html",
             "has": ["Apple 单线终端", "viewBox=\"0 0 48 48\"", "stroke-linejoin=\"round\"",
                     "<g transform=\"scale(1.5)\">"]},
            {"file": "adb_log_gui/icons/svg/Apple终端标识.svg",
             "has": ["viewBox=\"0 0 24 24\"", "#0A84FF", "终端提示符"]}
        ],
        "tests": ["377/_test_structure.py"]
    }
]

have = set(x.get("id") for x in feats)
for n in NEW:
    if n["id"] not in have:
        feats.append(n)

with io.open(P, "w", encoding="utf-8", newline="") as f:
    f.write(json.dumps(cfg, ensure_ascii=False, indent=2) + u"\n")

sys.stdout.write(u"OK features=%d（新增 %d，改 1）\n" % (len(feats), len(NEW)))
