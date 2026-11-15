// ============================================================================
//  Root.cs — root 状态检测与一键提权
//
//  需求来源（2026-11-10 界面反馈）：
//    指令输入页需要一个「root 指示按钮」：未 root 显示红色，已 root 显示绿色，
//    并且**点击就能完成 root**。
//
//  为什么要单独一个模块：
//    AutoRoot() 是"启动时按 ini 的 auto_root 自动提权"，只在连接设备时跑一次，
//    而且不带任何状态回传给界面。界面需要的是：
//      1) 随时可查询"现在到底是不是 root"
//      2) 主动触发一次提权，并知道成功还是失败
//    这两件事与启动流程无关，独立出来更清楚。
//
//  root 判定方式（按可靠性排序，任一命中即为已 root）：
//    a) `id -u` 返回 0            —— 最直接，uid 为 0 就是 root
//    b) `id` 输出里含 uid=0       —— 老版本 toybox 的 id 输出格式不同
//    c) `adb shell whoami` 为 root
//    注意不能用"能否读某个目录"来判：权限受 SELinux 影响，不可靠。
//
//  C# 5.0 兼容：不用 out var / 局部函数 / => 表达式体 / $"..."。
// ============================================================================
using System;
using System.Collections.Generic;
using System.Text;

namespace AdbLogExport
{
    internal static partial class App
    {
        // 最近一次探测到的 root 状态。
        //   false = 未 root（含"未知/离线"，界面上按未 root 显示红色更安全，
        //           避免明明没权限却显示绿色让用户以为能读全部目录）
        internal static bool ROOTED = false;

        // 是否已经为本次连接探测过（用于界面首次刷新时决定要不要主动查一次）
        internal static bool ROOT_PROBED = false;

        // ---------------- 查询 ----------------

        // 直接问设备：当前 shell 是不是 root。会真实调用 adb。
        // 返回是否 root，并同步更新 ROOTED / ROOT_PROBED。
        internal static bool RootProbe()
        {
            ROOT_PROBED = true;

            if (OFFLINE || DEVN == 0)
            {
                ROOTED = false;
                return false;
            }

            // a) id -u 最可靠：root 一定是 0
            string o = "";
            string e = "";
            int rc = ShellCall(CUR, "id -u 2>&1", out o, out e);
            string out1 = (o + e).Trim();

            if (rc == 0 && out1 == "0")
            {
                ROOTED = true;
                return true;
            }

            // b) 有些老 toybox 不支持 id -u，退回看整串 id
            o = "";
            e = "";
            ShellCall(CUR, "id 2>&1", out o, out e);
            string out2 = (o + e).Trim();
            if (out2.IndexOf("uid=0", StringComparison.Ordinal) >= 0)
            {
                ROOTED = true;
                return true;
            }

            // c) whoami 兜底
            o = "";
            e = "";
            ShellCall(CUR, "whoami 2>&1", out o, out e);
            string out3 = (o + e).Trim().ToLowerInvariant();
            if (out3 == "root")
            {
                ROOTED = true;
                return true;
            }

            ROOTED = false;
            return false;
        }

        // ---------------- 提权 ----------------

        // 一键 root：下发 adb root，等 adbd 重启回来，再复核一次。
        // 返回是否最终拿到了 root。全程把关键信息打到输出区，便于排查。
        internal static bool RootElevate()
        {
            if (OFFLINE || DEVN == 0)
            {
                ROOTED = false;
                Warn("设备未连接，无法提权");
                Hint("输入 :r 重连后再试");
                return false;
            }

            // 已经是 root 就不用折腾 adbd（重启 adbd 会短暂断连）
            if (RootProbe())
            {
                Ok("当前已是 root，无需提权");
                return true;
            }

            Info("正在提权：adb root …");
            string o = "";
            string e = "";
            AdbCall(new List<string> { "root" }, out o, out e);
            string low = (o + "\n" + e).ToLowerInvariant();

            // adbd 会重启，给它时间回来；不能立刻查询，否则必然 device not found
            if (low.IndexOf("restarting adbd as root", StringComparison.Ordinal) >= 0)
            {
                Info("adbd 正在以 root 身份重启，等待设备回来 …");
                WaitBack(6000);
            }

            // 复核：以实际 id -u 为准，不看 adb 的口头回执
            if (RootProbe())
            {
                Ok("提权成功：当前 shell 为 root");
                return true;
            }

            // 失败：把最可能的原因讲清楚（这几条覆盖了现场绝大多数情况）
            ROOTED = false;
            Fail("提权未成功，当前仍不是 root");
            if (low.IndexOf("cannot run as root", StringComparison.Ordinal) >= 0)
            {
                Hint("adbd cannot run as root in production builds —— 该版本是 user 版");
                Hint("需要刷 userdebug / eng 版本，或用 :preup 走升级前置流程");
            }
            else if (low.IndexOf("more than one device", StringComparison.Ordinal) >= 0)
            {
                Hint("连接了多台设备：在 ini 里填 serial（用 devices 查看），然后 :ri");
            }
            else if (low.IndexOf("not found", StringComparison.Ordinal) >= 0)
            {
                Hint("设备在执行过程中掉线了，等它回来后按 F5 或输入 :r 再看状态");
            }
            else
            {
                Hint("若该版本确实支持 root，可试 :preup（root → enable-verity → reboot）");
            }
            return false;
        }

        // 等设备回来（adbd 重启后会短暂无设备）。
        // 只轮询 get-state，不发业务命令，避免把还在启动的 adbd 打死。
        private static void WaitBack(int maxMs)
        {
            int waited = 0;
            while (waited < maxMs)
            {
                string st = "";
                string se = "";
                AdbCall(new List<string> { "get-state" }, out st, out se);
                if (st.Trim().ToLowerInvariant() == "device")
                {
                    // 刚回来时 shell 可能还没就绪，再给一点点缓冲
                    System.Threading.Thread.Sleep(400);
                    return;
                }
                System.Threading.Thread.Sleep(500);
                waited += 500;
            }
        }
    }
}
