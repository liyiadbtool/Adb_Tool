# -*- coding: utf-8 -*-
"""只灌 A14 的 CSS / JS 两个块（结构由 _patch_a14_ui.py 管）。可反复跑。"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")

s = io.open(UI, encoding="utf-8").read()

# 先拆掉旧的两块，保证幂等
s = re.sub(r"/\* === V14 LAYER START === \*/.*?/\* === V14 LAYER END === \*/\n", "", s, flags=re.S)
s = re.sub(r"/\* === V14 JS START === \*/.*?/\* === V14 JS END === \*/\n", "", s, flags=re.S)

if s.count("</style>") != 1:
    sys.exit("[FAIL] </style> 不唯一：%d" % s.count("</style>"))
if s.count("\n</script>") != 1:
    sys.exit("[FAIL] </script> 不唯一：%d" % s.count("\n</script>"))
if "V13 LAYER END" not in s:
    sys.exit("[FAIL] 找不到 V13 层，V14 必须排在它后面")

css = io.open(os.path.join(ROOT, "_v14.css"), encoding="utf-8").read()
js = io.open(os.path.join(ROOT, "_v14.js"), encoding="utf-8").read()

s = s.replace("</style>", css + "</style>", 1)
s = s.replace("\n</script>", "\n" + js + "\n</script>", 1)

io.open(UI, "w", encoding="utf-8", newline="").write(s)
sys.stdout.write("V14 注入完成，%.1f KB（css %.1fKB / js %.1fKB）\n"
                 % (len(s) / 1024.0, len(css) / 1024.0, len(js) / 1024.0))
