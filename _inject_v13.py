# -*- coding: utf-8 -*-
"""只灌 A13 的 CSS / JS 两个块（结构已在 ui.html 里）。可反复跑。"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")

s = io.open(UI, encoding="utf-8").read()

# 先拆掉旧的两块，保证幂等
s = re.sub(r"/\* === V13 LAYER START === \*/.*?/\* === V13 LAYER END === \*/\n", "", s, flags=re.S)
s = re.sub(r"/\* === V13 JS START === \*/.*?/\* === V13 JS END === \*/\n", "", s, flags=re.S)

if s.count("</style>") != 1:
    sys.exit("[FAIL] </style> 不唯一：%d" % s.count("</style>"))
if s.count("\n</script>") != 1:
    sys.exit("[FAIL] </script> 不唯一：%d" % s.count("\n</script>"))

css = io.open(os.path.join(ROOT, "_v13.css"), encoding="utf-8").read()
js = io.open(os.path.join(ROOT, "_v13.js"), encoding="utf-8").read()

s = s.replace("</style>", css + "</style>", 1)
s = s.replace("\n</script>", "\n" + js + "\n</script>", 1)

io.open(UI, "w", encoding="utf-8", newline="").write(s)
sys.stdout.write("V13 注入完成，%.1f KB（css %.1fKB / js %.1fKB）\n"
                 % (len(s) / 1024.0, len(css) / 1024.0, len(js) / 1024.0))
