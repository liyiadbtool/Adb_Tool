#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""2026-11-25（C6）：把门禁报告里的"未登记新增"整理成可直接粘贴的基线段。

背景：每加一个 id / onclick / onmessage kind，都要手工去 _gate_invariants.py
补 2~3 处基线；漏一处门禁就红一轮，今天因此浪费了 5 轮编译+门禁。

用法：
    python _gate_update.py            # 只打印建议片段
    python _gate_update.py --write    # 直接写入 _gate_new.txt（人工复核后粘贴）

数据来源：docs/INVARIANT-DIFF.md（_gate_invariants.py 每次都会重写它）
"""
import io, os, re, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
MD = os.path.join(ROOT, "docs", "INVARIANT-DIFF.md")

def main():
    if not os.path.exists(MD):
        print("没有找到 docs/INVARIANT-DIFF.md，先跑一次 python _gate_invariants.py")
        return 2
    txt = io.open(MD, encoding="utf-8", errors="replace").read()
    blocks = re.findall(r"未登记新增s?\s*\[([^\]]*)\]", txt)
    names = []
    for b in blocks:
        for m in re.findall(r"'([^']+)'", b):
            if m not in names:
                names.append(m)
    if not names:
        print("门禁报告里没有未登记项，基线是齐的。")
        return 0
    print("需要补进基线的名字（共 %d 个）：" % len(names))
    print()
    for i in range(0, len(names), 6):
        print('        ' + ", ".join('"%s"' % n for n in names[i:i+6]) + ",")
    print()
    print("提示：id / onclick / kind 分属三个集合，粘贴前确认分类。")
    if "--write" in sys.argv:
        out = os.path.join(ROOT, "_gate_new.txt")
        io.open(out, "w", encoding="utf-8", newline="\n").write(", ".join(names))
        print("已写入 " + out)
    return 0

if __name__ == "__main__":
    sys.exit(main())
