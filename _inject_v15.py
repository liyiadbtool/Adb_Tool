# -*- coding: utf-8 -*-
"""只灌 A15 的 CSS / JS 两个块（结构由 _patch_a15.py 管）。可反复跑。"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")

s = io.open(UI, encoding="utf-8").read()

# 先拆掉旧的两块，保证幂等
s = re.sub(r"/\* === V15 LAYER START === \*/.*?/\* === V15 LAYER END === \*/\n", "", s, flags=re.S)
s = re.sub(r"/\* === V15 JS START === \*/.*?/\* === V15 JS END === \*/\n", "", s, flags=re.S)

if s.count("</style>") != 1:
    sys.exit("[FAIL] </style> 不唯一：%d" % s.count("</style>"))
if s.count("\n</script>") != 1:
    sys.exit("[FAIL] </script> 不唯一：%d" % s.count("\n</script>"))
if "V14 LAYER END" not in s:
    sys.exit("[FAIL] 找不到 V14 层，V15 必须排在它后面")

css = io.open(os.path.join(ROOT, "_v15.css"), encoding="utf-8").read()
js = io.open(os.path.join(ROOT, "_v15.js"), encoding="utf-8").read()

s = s.replace("</style>", css + "</style>", 1)
s = s.replace("\n</script>", "\n" + js + "\n</script>", 1)

io.open(UI, "w", encoding="utf-8", newline="").write(s)
sys.stdout.write("V15 注入完成，%.1f KB（css %.1fKB / js %.1fKB）\n"
                 % (len(s) / 1024.0, len(css) / 1024.0, len(js) / 1024.0))
