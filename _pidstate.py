# -*- coding: utf-8 -*-
"""去重机制换实现：WMI CommandLine → pid 文件。

为什么换：Win32_Process 的 CommandLine 字段在**非管理员**下读出来是 null，
实测"手工起一个 --display-id=0 的 scrcpy，再 :cast 0 仍然放行"——去重失效。
pid 文件只依赖 Path/Process.GetProcessById，不需要任何权限。
"""
import io

ROOT = r"C:\Users\SunWwei\Desktop\Adb_Tool"
p = ROOT + r"\_cs\Scrcpy.cs"
s = io.open(p, encoding="utf-8").read()

start = s.index("        /// <summary>该屏是否正在投（内存表 + 进程存活 + 跨会话 WMI 兜底）。</summary>")
end_mark = "        /// <summary>取消某块屏的投屏；返回被杀掉的进程数。</summary>"
k = s.index(end_mark, start)

new = '''        /// <summary>pid 文件目录：%LOCALAPPDATA%\\adb_Tool\\casts</summary>
        private static string CastStateDir()
        {
            string dir = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "adb_Tool", "casts");
            try { Directory.CreateDirectory(dir); } catch { }
            return dir;
        }

        private static string CastPidFile(int displayId)
        {
            return Path.Combine(CastStateDir(), "cast_" + displayId + ".pid");
        }

        private static void WritePid(int displayId, int pid)
        {
            try { File.WriteAllText(CastPidFile(displayId), pid.ToString()); } catch { }
        }

        private static void ErasePid(int displayId)
        {
            try { if (File.Exists(CastPidFile(displayId))) File.Delete(CastPidFile(displayId)); } catch { }
        }

        /// <summary>
        /// 读 pid 文件判断这块屏是否在投。
        /// 为什么不用 WMI 扫命令行：Win32_Process.CommandLine 在非管理员下是 null，
        /// 实测会漏判（手工开的 scrcpy 认不出来），去重就形同虚设。
        /// pid 文件 + GetProcessById 只依赖文件系统，不需要提权。
        /// </summary>
        private static Process FindCasting(int displayId)
        {
            string f = CastPidFile(displayId);
            try
            {
                if (!File.Exists(f)) return null;
                int pid;
                if (!int.TryParse(File.ReadAllText(f).Trim(), out pid)) { ErasePid(displayId); return null; }
                Process p = Process.GetProcessById(pid);
                if (p == null || p.HasExited) { ErasePid(displayId); return null; }
                return p;
            }
            catch
            {
                // 进程已退出（GetProcessById 抛 ArgumentException）→ 清掉过期 pid
                ErasePid(displayId);
                return null;
            }
        }

        /// <summary>该屏是否正在投（内存表 + pid 文件，两条互相兜底）。</summary>
        internal static bool IsCasting(int displayId)
        {
            lock (ActiveLock)
            {
                Process p;
                if (Active.TryGetValue(displayId, out p))
                {
                    try { if (p != null && !p.HasExited) return true; } catch { }
                    Active.Remove(displayId);
                }
            }
            return FindCasting(displayId) != null;
        }

'''
s = s[:start] + new + s[k:]

# StopCast：改成读 pid 文件
old_stop = s[s.index("        /// <summary>取消某块屏的投屏；返回被杀掉的进程数。</summary>"):]
old_stop = old_stop[:old_stop.index("        /// <summary>取消全部投屏（含工具启动前就开着的那些）。</summary>")]
new_stop = '''        /// <summary>取消某块屏的投屏；返回被杀掉的进程数。</summary>
        internal static int StopCast(int displayId)
        {
            int n = 0;
            lock (ActiveLock)
            {
                Process p;
                if (Active.TryGetValue(displayId, out p))
                {
                    try { if (p != null && !p.HasExited) { p.Kill(); n++; } } catch { }
                    try { if (p != null) p.Dispose(); } catch { }
                    Active.Remove(displayId);
                }
            }
            Process q = FindCasting(displayId);
            if (q != null)
            {
                try { if (!q.HasExited) { q.Kill(); n++; } } catch { }
                try { q.Dispose(); } catch { }
            }
            ErasePid(displayId);
            return n;
        }

'''
s = s.replace(old_stop, new_stop, 1)

# 启动成功后写 pid 文件
old_rem = '''                Remember(displayId, p);'''
new_rem = '''                Remember(displayId, p);
                WritePid(displayId, p.Id);'''
assert s.count(old_rem) == 1
s = s.replace(old_rem, new_rem, 1)

# StopAllCasts：清掉所有 pid 文件
s = s.replace('''            foreach (int id in ids) n += StopCast(id);''',
'''            foreach (int id in ids) n += StopCast(id);
            // 扫一遍 pid 文件目录：工具重启前开的那些，内存表里没有
            try
            {
                foreach (string f in Directory.GetFiles(CastStateDir(), "cast_*.pid"))
                {
                    string num = Path.GetFileNameWithoutExtension(f).Substring(5);
                    int did;
                    if (int.TryParse(num, out did)) n += StopCast(did);
                }
            }
            catch { }''', 1)

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("Scrcpy.cs：去重改用 pid 文件")
