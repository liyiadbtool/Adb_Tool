// ============================================================================
//  ApkCmds.cs — APK 管理页用到的三个「按包」动作
//
//  和原来那三个命令的区别只有一点：**对象从"当前前台应用"变成"用户指定的包"**。
//  判定口径一分不改 —— 尤其是 pm clear：
//      · am force-stop 只杀进程，数据完整保留
//      · pm clear 清空全部数据，应用回到刚安装
//      两者语义差得远，APK 管理页的按钮文案必须写「清空数据」，不能写「清缓存」。
//
//  pm clear 的坑（沿用 DoFstop 的结论）：
//      包名不存在 / 系统级包不允许清数据时，输出是 "Failed"，但**退出码仍然是 0**。
//      只判 rc != 0 会把失败当成功，用户以为清干净了、其实数据还在。
//      所以必须同时要求正向证据 "Success"、并排除 Failed/denied/unknown package。
//
//  导出 APK：只导 base + 各 split 文件本身，**不打包**（用户明确要求）。
//      多 split 的应用光有 base.apk 是装不上的，所以这里把 pm path 返回的
//      每一行都拉到同一个目录，并在结果里写清楚导了几个文件。
// ============================================================================
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

namespace AdbLogExport
{
    internal static partial class App
    {
        // ==================== 清空数据（pm clear）====================
        // 成功返回 true。所有提示都直接打印，GUI 的输出区照收即可。
        internal static bool ClearPkg(string pkg)
        {
            string err = "";
            if (!ApkPkgValid(pkg, out err))
            {
                Fail("包名不合法：" + err);
                return false;
            }
            if (!RequireDevice("")) return false;

            Echo("pm clear", pkg + "   （清空应用数据，应用回到刚安装状态）");

            string o = "";
            string e = "";
            int rc = ShellCall(CUR, "pm clear " + pkg, out o, out e);

            string combined = (o + "\n" + e).Trim();
            string low = combined.ToLowerInvariant();
            string detail = FirstLine(combined);

            if (!PmClearSucceeded(combined) || rc != 0)
            {
                CMD_OK = false;
                Fail("清理失败" + (detail.Length > 0 ? "：" + detail : "（没有返回 Success）"));

                if (low.IndexOf("unknown package") >= 0 || low.IndexOf("no such") >= 0)
                {
                    Hint("设备上找不到这个包：" + pkg);
                    Hint("核对包名，或在 APK 管理里点「查询全部版本」确认是否已安装");
                }
                else if (low.IndexOf("denied") >= 0)
                {
                    Hint("权限不足：pm clear 系统级包需要 root，先点顶部 ROOT 按钮提权");
                }
                else
                {
                    Hint("系统级应用通常不允许清数据；可先用「关闭进程」验证包名是否正确");
                }
                return false;
            }

            CMD_OK = true;
            Ok("已清空应用数据  " + pkg);
            Hint("应用已回到刚安装状态，进程同时被终止；下次启动会重新走初始化流程");
            return true;
        }

        // pm clear 的结果判定（纯函数，自检直接打靶）
        //   正向证据：输出里出现 Success
        //   反向证据：Failed / Exception / denied / unknown package / no such
        // 两个条件必须同时满足才算成功。
        internal static bool PmClearSucceeded(string combined)
        {
            string low = (combined == null) ? "" : combined.ToLowerInvariant();
            bool saidSuccess = (low.IndexOf("success") >= 0);
            if (!saidSuccess) return false;

            if (low.IndexOf("failed") >= 0) return false;
            if (low.IndexOf("exception") >= 0) return false;
            if (low.IndexOf("denied") >= 0) return false;
            if (low.IndexOf("unknown package") >= 0) return false;
            if (low.IndexOf("no such") >= 0) return false;
            return true;
        }

        // ==================== 卸载（adb uninstall）====================
        // T8（2026-11-19）：用户明确"无需二次确认"。不可逆风险由
        // 「正反双判 + 明确结果提示」承担 —— 和 pm clear 同一套口径：
        //   正向：输出里出现 Success
        //   反向：Failed / Exception / DELETE_FAILED_* / denied / unknown package
        // 注意：`adb uninstall` 在 Failure [DELETE_FAILED_INTERNAL_ERROR] 时
        // 退出码也可能是 0，只看 rc 会把失败当成功。
        internal static bool UninstallPkg(string pkg)
        {
            string err = "";
            if (!ApkPkgValid(pkg, out err))
            {
                Fail("包名不合法：" + err);
                return false;
            }
            if (!RequireDevice("")) return false;

            Echo("adb uninstall", pkg);

            string o = "";
            string e = "";
            int rc = ShellCall(CUR, "adb uninstall " + pkg, out o, out e);
            if (rc != 0 && (o + e).Trim().Length == 0)
            {
                // 某些机型 adb 在设备 shell 里不接受嵌套 adb，退一步用 pm uninstall
                rc = ShellCall(CUR, "pm uninstall " + pkg, out o, out e);
            }

            string combined = (o + "\n" + e).Trim();
            string low = combined.ToLowerInvariant();
            string detail = FirstLine(combined);

            if (!UninstallSucceeded(combined))
            {
                CMD_OK = false;
                Fail("卸载失败" + (detail.Length > 0 ? "：" + detail : "（没有返回 Success）"));
                if (low.IndexOf("intern") >= 0 || low.IndexOf("system") >= 0)
                    Hint("系统应用通常不允许卸载；确认包名是否正确，或换用「清理数据」");
                else if (low.IndexOf("unknown package") >= 0 || low.IndexOf("not installed") >= 0)
                    Hint("设备上没装这个包：" + pkg);
                else if (low.IndexOf("denied") >= 0)
                    Hint("权限不足：先点顶部 ROOT 按钮提权");
                return false;
            }

            CMD_OK = true;
            Ok("已卸载  " + pkg);
            Hint("卸载不可撤销；需要时可重新安装 APK");
            return true;
        }

        // adb uninstall 的结果判定（纯函数，自检直接打靶）
        //   正向：输出里出现 Success
        //   反向：Failure / Failed / Exception / denied / unknown package / not installed
        // 为什么要双判：`adb uninstall` 在 Failure [DELETE_FAILED_INTERNAL_ERROR] 时
        // 退出码也可能是 0 —— 只看 rc 会把失败当"卸载成功"。
        internal static bool UninstallSucceeded(string combined)
        {
            string low = (combined == null) ? "" : combined.ToLowerInvariant();
            if (low.IndexOf("success") < 0) return false;
            if (low.IndexOf("failure") >= 0) return false;
            if (low.IndexOf("failed") >= 0) return false;
            if (low.IndexOf("exception") >= 0) return false;
            if (low.IndexOf("denied") >= 0) return false;
            if (low.IndexOf("unknown package") >= 0) return false;
            if (low.IndexOf("not installed") >= 0) return false;
            return true;
        }

        // ==================== 关闭进程（am force-stop）====================
        internal static bool KillPkg(string pkg)
        {
            string err = "";
            if (!ApkPkgValid(pkg, out err))
            {
                Fail("包名不合法：" + err);
                return false;
            }
            if (!RequireDevice("")) return false;

            Echo("am force-stop", pkg);

            string o = "";
            string e = "";
            int rc = ShellCall(CUR, "am force-stop " + pkg, out o, out e);

            // am force-stop 成功时不输出任何东西，所以只能看退出码；
            // 有错误输出时把首行贴出来，别让用户对着"失败"两个字猜。
            if (rc != 0)
            {
                CMD_OK = false;
                string detail = FirstLine((o + "\n" + e).Trim());
                Fail("关闭失败" + (detail.Length > 0 ? "：" + detail : "（退出码 " + rc + "）"));
                return false;
            }

            CMD_OK = true;
            Ok("已关闭进程  " + pkg);
            Hint("只杀了进程，应用数据和登录态都还在；要彻底重置用「清空数据」");
            return true;
        }

        // ==================== 导出 APK（不打包）====================
        internal static bool ExportPkg(string pkg)
        {
            string err = "";
            if (!ApkPkgValid(pkg, out err))
            {
                Fail("包名不合法：" + err);
                return false;
            }
            if (!RequireDevice("")) return false;

            List<string> paths = QueryPkgPaths(pkg);
            if (paths.Count == 0)
            {
                Fail("取不到 " + pkg + " 的 apk 路径（pm path 无结果）");
                Hint("系统预置但未安装的应用、或包名写错时会出现这种情况");
                return false;
            }

            // 落点：桌面\logcat\<今天>\APK（与原来的 :apk 一致）
            string target = OutDir("APK");
            Echo("export-apk", pkg + "  " + paths.Count + " 个文件  →  " + target);

            int okCount = 0;
            List<string> failed = new List<string>();
            for (int i = 0; i < paths.Count; i++)
            {
                string msg = "";
                if (PullOneApk(paths[i], target, out msg)) okCount++;
                else failed.Add(LastSeg(paths[i]) + "（" + msg + "）");
            }

            if (okCount == 0)
            {
                CMD_OK = false;
                Fail("导出失败：一个文件都没拉下来");
                for (int i = 0; i < failed.Count && i < 5; i++) Hint("  " + failed[i]);
                return false;
            }

            CMD_OK = true;
            if (failed.Count == 0)
            {
                Ok("APK 已导出 " + okCount + " 个文件到 " + target);
            }
            else
            {
                // 部分成功要如实说，不能报"失败"也不能报"成功"
                Warn("部分成功：" + okCount + "/" + paths.Count + " 个文件");
                for (int i = 0; i < failed.Count && i < 5; i++) Hint("  失败：" + failed[i]);
            }

            if (paths.Count > 1)
            {
                Hint("该应用是多 split 安装包，只装 base.apk 会失败；" + target + " 里的文件要一起用");
            }
            return true;
        }

        // 一次 pull 一个文件到本地目录（文件名沿用设备侧末段）
        private static bool PullOneApk(string devPath, string localDir, out string msg)
        {
            msg = "";
            string name = LastSeg(devPath);
            if (string.IsNullOrEmpty(name) || name == "/") { msg = "设备路径异常"; return false; }

            try { Directory.CreateDirectory(localDir); } catch { }

            string dst = Path.Combine(localDir, name);
            if (File.Exists(dst))
            {
                // 不覆盖旧文件：同一天导两次时加时间戳，避免"看起来成功了其实是上次的"
                string stamp = DateTime.Now.ToString("HHmmss");
                dst = Path.Combine(localDir, Path.GetFileNameWithoutExtension(name)
                                    + "_" + stamp + Path.GetExtension(name));
            }

            List<string> argv = new List<string>();
            argv.Add("pull");
            argv.Add(devPath);
            argv.Add(dst);

            string combined = "";
            int rc = AdbCallStream(argv, out combined);
            if (rc != 0)
            {
                msg = FirstLine(combined);
                if (msg.Length == 0) msg = "退出码 " + rc;
                return false;
            }

            long size = 0;
            try { size = new FileInfo(dst).Length; } catch { }
            if (size <= 0)
            {
                msg = "文件为空";
                return false;
            }

            Console.WriteLine("    " + name + "   " + FormatSize(size));
            return true;
        }

        // ==================== pm path 解析 ====================
        // 多 split 的包会返回多行：
        //     package:/data/app/~~xx==/com.a-yy==/base.apk
        //     package:/data/app/~~xx==/com.a-yy==/split_config.arm64_v8a.apk
        // 原来 QueryPkgPath 只取第一行，导出的包装不上 —— 这里保留全部。
        internal static List<string> QueryPkgPaths(string pkg)
        {
            List<string> list = new List<string>();
            string o = "";
            string e = "";
            ShellCall(CUR, "pm path " + pkg + " 2>/dev/null", out o, out e);
            return ParsePmPathLines(o + "\n" + e);
        }

        internal static List<string> ParsePmPathLines(string text)
        {
            List<string> list = new List<string>();
            if (string.IsNullOrEmpty(text)) return list;

            string[] lines = text.Split('\n');
            for (int i = 0; i < lines.Length; i++)
            {
                string s = lines[i].TrimEnd('\r').Trim();
                if (s.Length == 0) continue;
                if (!s.StartsWith("package:", StringComparison.Ordinal)) continue;

                string p = s.Substring("package:".Length).Trim();
                if (p.Length == 0) continue;
                if (list.IndexOf(p) >= 0) continue;   // 去重（个别 ROM 会重复输出）
                list.Add(p);
            }
            return list;
        }
    }
}
