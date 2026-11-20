# -*- coding: utf-8 -*-
"""修「投屏不能点击」：`:cast` 默认带控制，另留 view 只看模式。

原来 Launch 写死 --no-control（防误触），代价是窗口里点不动。
scrcpy 的鼠标点击要通过 --control 注入触摸事件，没这个参数就是纯画面。
"""
import io

ROOT = r"C:\Users\SunWwei\Desktop\Adb_Tool"

# ---------- 1) Scrcpy.cs：Launch 加 control 参数 ----------
p = ROOT + r"\_cs\Scrcpy.cs"
s = io.open(p, encoding="utf-8").read()

old = '''        internal static bool Launch(int displayId, string name, out string err)
        {
            return LaunchCore(displayId, name, null, 0, out err);
        }'''
new = '''        internal static bool Launch(int displayId, string name, out string err)
        {
            // 2026-11-20：默认带控制。之前写死 --no-control，用户反馈"投屏不能点击"——
            // 那是防误触的代价，但对测试来说点不动等于没用。要只看请走 LaunchView。
            return LaunchCore(displayId, name, null, 0, true, out err);
        }

        /// <summary>只看模式（--no-control）：画面能看，鼠标点不动，不会误触车机。</summary>
        internal static bool LaunchView(int displayId, string name, out string err)
        {
            return LaunchCore(displayId, name, null, 0, false, out err);
        }'''
assert s.count(old) == 1
s = s.replace(old, new, 1)

old2 = '''            return LaunchCore(displayId, name, outFile, seconds, out err);'''
new2 = '''            // 录制不需要接管输入，保持只看（--no-control），避免录制时误操作车机
            return LaunchCore(displayId, name, outFile, seconds, false, out err);'''
assert s.count(old2) == 1
s = s.replace(old2, new2, 1)

old3 = '''        private static bool LaunchCore(int displayId, string name, string recFile,
                                       int recSeconds, out string err)'''
new3 = '''        private static bool LaunchCore(int displayId, string name, string recFile,
                                       int recSeconds, bool control, out string err)'''
assert s.count(old3) == 1
s = s.replace(old3, new3, 1)

old4 = '''            // --no-control：只投屏不接管输入。测试场景下误触会改车机状态，风险太大。
            a.Append("--no-control");'''
new4 = '''            // 控制开关：control=true 才能用鼠标点车机（scrcpy 通过 adb 注入触摸）。
            // 不加这个参数 = 纯画面，点了没反应 —— 用户反馈的"投屏不能点击"就是这个。
            if (!control) a.Append("--no-control");'''
assert s.count(old4) == 1
s = s.replace(old4, new4, 1)

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("Scrcpy.cs：Launch 默认带控制 + 新增 LaunchView")

# ---------- 2) TaskCmds：:cast 解析 view ----------
q = ROOT + r"\_cs\TaskCmds.cs"
t = io.open(q, encoding="utf-8").read()

old5 = '''            Echo("scrcpy", "--display-id=" + id + "  (" + name + ")");
            CMD_OK = false;
            string err = "";
            bool ok = false;
            try { ok = Scrcpy.Launch(id, name, out err); }
            catch (Exception ex) { err = "启动异常：" + ex.Message; }

            if (ok)
            {
                CMD_OK = true;
                Ok("已打开 scrcpy 窗口：「" + name + "」display-id=" + id);
                Hint("只投屏不接管输入（--no-control），不会误触车机");
            }'''
new5 = '''            Echo("scrcpy", "--display-id=" + id + "  (" + name + ")");
            CMD_OK = false;
            string err = "";
            bool ok = false;
            try
            {
                ok = ViewOnly
                    ? Scrcpy.LaunchView(id, name, out err)
                    : Scrcpy.Launch(id, name, out err);
            }
            catch (Exception ex) { err = "启动异常：" + ex.Message; }

            if (ok)
            {
                CMD_OK = true;
                Ok("已打开 scrcpy 窗口：「" + name + "」display-id=" + id
                   + (ViewOnly ? "（只看，不可点）" : "（可鼠标操作）"));
                if (ViewOnly) Hint("只看模式：鼠标点不动车机，适合演示/录屏");
                else Hint("点击会真的操作车机；不想误触请加 view，例如 :cast 0 view");
            }'''
assert t.count(old5) == 1
t = t.replace(old5, new5, 1)
io.open(q, "w", encoding="utf-8", newline="\n").write(t)
print("TaskCmds：:cast 分支接 ViewOnly")
