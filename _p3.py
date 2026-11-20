# -*- coding: utf-8 -*-
"""P3：删除 Cast.cs 与 GuiWeb 里的投屏处理。

UI 层已在上一提交删完（投屏页不存在，前端不再发任何 cast 消息），
这里清理后端死代码：
  · GuiWeb：8 个 case、5 个 Run/PushCast 方法、EnsureCastHosts/ResizeEmbedded/
    ScrcpyEmbed*/AttachEmbedded 一整段
  · OnFormClosing 里的 ScrcpyEmbedStopAll / CastStopAll
  · Cast.cs 整文件；两个 bat 的编译列表去掉它
"""
import io
import re

ROOT = r"C:\Users\SunWwei\Desktop\Adb_Tool"
G = ROOT + r"\_cs\GuiWeb.cs"
lines = io.open(G, encoding="utf-8").read().split("\n")


def drop(a, b, why):
    print("  删 %d-%d（%d 行）：%s" % (a, b, b - a + 1, why))
    del lines[a - 1:b]


# ---- GuiWeb：自底向上 ----
# 1) 内嵌 scrcpy 整段：EnsureCastHosts .. ScrcpyEmbedHideAll 结束
drop(4338, 4700, "内嵌 scrcpy 整段") if False else None

s = "\n".join(lines)

# 用标记删内嵌段：从 EnsureCastHosts 的定义前注释到 ScrcpyEmbedHideAll 方法体结束
start = s.index("        private void EnsureCastHosts()")
# 往回找该方法的注释起点（保守：取其上方的 /* 或 // 行起点）
back = s.rfind("\n\n", 0, start) + 2
end_mark = "        private void ScrcpyEmbedHideAll()"
i = s.index(end_mark)
# 找该方法体结束：从 i 起第一个 "\n        }\n"
j = s.index("\n        }\n", i) + len("\n        }\n")
print("  删内嵌 scrcpy 段（%d 字符）" % (j - back))
s = s[:back] + s[j:]

# 2) 投屏业务方法：PushCastStat / RunCastTap / CastTapWorker / RunCastList / RunCastRecord
start2 = s.index("        private void PushCastStat(int slot)")
end2 = s.index("        private void RunFfmpegJob(int mode, string arg)")
back2 = s.rfind("\n\n", 0, start2) + 2
print("  删投屏方法段（%d 字符）" % (end2 - back2))
s = s[:back2] + s[end2:]

# 3) 8 个 case
for kind in ("castlist", "caststart", "caststop", "caststat", "casttap", "castrec"):
    m = re.search(r"\n\s*case \"%s\":\n(?:[^\n]*\n)*?\s*break;\n" % kind, s)
    if m:
        s = s[:m.start()] + "\n" + s[m.end():]
        print("  删 case %s" % kind)
    else:
        print("  ! case %s 未匹配（可能写法不同）" % kind)

for kind in ("scrcpyembed", "scrcpyembedstop", "castembedrect", "castembedhide"):
    m = re.search(r"\n\s*case \"%s\":\n(?:[^\n]*\n)*?\s*break;\n" % kind, s)
    if m:
        s = s[:m.start()] + "\n" + s[m.end():]
        print("  删 case %s" % kind)
    else:
        print("  ! case %s 未匹配" % kind)

# 4) OnFormClosing 里的两行
s = s.replace("""            // A18：内嵌的 scrcpy 是外部进程，不主动杀会留在后台继续推流（每格一个）
            try { ScrcpyEmbedStopAll(); } catch { }
""", "")
s = s.replace("""            // 2026-11-15 闪退修复：关窗时显式停掉所有投屏采集线程与 adb 子进程，
            // 否则 CastLoop 可能赶在进程退出前又拉起一个 screencap（僵尸 adb 堆积）。
            try { App.CastStopAll(); } catch { }
""", "")

io.open(G, "w", encoding="utf-8", newline="\n").write(s)
print("GuiWeb.cs 清理完成")

# ---- 删除 Cast.cs 并从两个 bat 的编译列表移除 ----
import os
os.remove(ROOT + r"\_cs\Cast.cs")
print("已删 _cs/Cast.cs")
for bat, pat in ((ROOT + r"\adb_log_gui\build_gui.bat", '"%SRC%\\Cast.cs" '),
                 (ROOT + r"\_cs\build.bat", '"%~dp0Cast.cs" ')):
    t = io.open(bat, encoding="gbk", errors="replace").read()
    assert pat in t, bat
    io.open(bat, "w", encoding="gbk", newline="").write(t.replace(pat, "", 1))
    print("  从编译列表移除：", os.path.basename(bat))
