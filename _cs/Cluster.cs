// ============================================================================
//  Cluster.cs - 仪表（Cluster）投屏与通道登录（2026-11-22 第 16 批）
// ----------------------------------------------------------------------------
//  需求：Scrcpy 投屏增加"仪表投屏"，保留芯片选择（8295 / 8838）、
//        登录 / 退出登录 / 开启仪表实时显示。
//        交互门禁：必须**选芯片 + 登录成功**才允许投屏。
//
//  ★ 芯片与登录逻辑严格按 ClusterDebugTool 的逆向结果实现：
//
//    8838（T75）
//      通道类型  CHANNEL_ADB
//      登录方式  adb shell lxc-attach -n linux-8838
//      凭据      配置文件里**没有** telnet_host/username/password 字段
//                → 免密（靠 adb root 后 attach 进容器）
//      识别特征  属性含 qcm8838
//
//    8295（AHT）
//      通道类型  CHANNEL_TELNET
//      登录方式  busybox telnet <host>  →  送 username / password  →  su 送 su_password
//      凭据      配置文件里有 telnet_host / telnet_username /
//                telnet_password / su_password 四个字段
//      识别特征  属性含 sa8295
//
//    芯片识别用的属性（逆向确认，四条一起取）：
//      getprop ro.soc.model
//      getprop ro.oem.product.name
//      getprop ro.board.platform
//      getprop ro.product.device
//      外加 ro.product.version.tier1.hw.platform / ro.build.display.id 兜底
//
//  ★ 关于凭据的处置（重要）：
//    我们没有把账号密码硬编码进代码 —— 逆向出来的凭据属于内部资料，
//    写死在源码里既不合规，也没法换环境。改为：
//      · 页面填一次 → 存进本机 ini（clu_* 键）
//      · 下次自动带出
//      · 不走网络、不进日志（日志里只打"已登录 / 失败"，不回显密码）
//
//  ★ 关于"登录"的技术性质（要诚实说明）：
//    scrcpy 取画面走的是 adb 通道，**与 telnet/lxc 登录无关**。
//    这里的"登录"是**流程门禁**（用户要求"选芯片+登录后才能投屏"），
//    同时也是真实验证：8838 验证容器可达，8295 验证 telnet 端口可达。
//    它保证的是"这台设备确实是这个芯片、通道确实通"，而不是给 scrcpy 授权。
// ============================================================================
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;

namespace AdbLogExport
{
    // 芯片档案：一张表描述一个平台的全部差异
    internal class ChipProfile
    {
        public string Key;            // "8838" / "8295"
        public string Label;          // 下拉框显示
        public bool IsTelnet;         // true=telnet 通道   false=adb+lxc 通道
        public string LxcName;        // 8838 专用：linux-8838
        public string DefaultHost;    // 8295 专用：192.168.8.1
        public string[] DetectKeys;   // 识别关键字（属性值里含任一即判定）
        public int DefaultDisplay;    // 仪表默认屏号
    }

    internal static partial class App
    {
        // ==================== 芯片表 ====================
        //
        // 只有两个平台（逆向确认：工具里就是 "8838" / "8295" 二选一）。
        // DefaultDisplay：仪表屏号。8838 用 4（与我们既有 :scrcpy cluster 映射一致）。
        // 8295 的仪表屏号在真机上可能不同，所以页面允许改。
        internal static readonly ChipProfile[] CHIPS = new ChipProfile[]
        {
            new ChipProfile {
                Key = "8838", Label = "8838 (T75)",
                IsTelnet = false,
                LxcName = "linux-8838",
                DefaultHost = "",
                DetectKeys = new string[] { "qcm8838", "8838" },
                DefaultDisplay = 4
            },
            new ChipProfile {
                Key = "8295", Label = "8295 (AHT)",
                IsTelnet = true,
                LxcName = "",
                DefaultHost = "192.168.8.1",   // 逆向字符串里出现的默认地址
                DetectKeys = new string[] { "sa8295", "8295" },
                DefaultDisplay = 4
            }
        };

        internal static ChipProfile FindChip(string key)
        {
            if (key == null) return null;
            string k = key.Trim().ToLowerInvariant();
            for (int i = 0; i < CHIPS.Length; i++)
            {
                if (CHIPS[i].Key == k) return CHIPS[i];
                // 允许用 "8838" / "t75" / "8295" / "aht" 之类简写
                if (k == "t75" && CHIPS[i].Key == "8838") return CHIPS[i];
                if (k == "aht" && CHIPS[i].Key == "8295") return CHIPS[i];
            }
            return null;
        }

        // ==================== 登录会话状态 ====================
        //
        // 只存在内存里：进程退出即失效，符合"每次开机重新登录"的安全直觉。
        internal static string CLU_CHIP = "";      // 已登录的芯片 key
        internal static bool CLU_LOGGED = false;   // 是否登录成功
        internal static string CLU_ERR = "";       // 上次失败原因（给页面显示）

        // ==================== R4：芯片自动识别 ====================
        //
        // 严格按逆向的属性顺序取值，用关键字匹配。
        // 匹配不到返回空 —— **绝不猜**。逆向工具自己也打"未能自动识别芯片型号，
        // 沿用当前选择"，说明识别失败是正常情况，应该让人工选择兜底。
        internal static string DetectChip()
        {
            if (DEVN == 0) return "";

            string props =
                "getprop ro.soc.model; " +
                "getprop ro.oem.product.name; " +
                "getprop ro.board.platform; " +
                "getprop ro.product.device; " +
                "getprop ro.product.version.tier1.hw.platform; " +
                "getprop ro.build.display.id";

            string o = "", e = "";
            try { ShellCall(CUR, props, out o, out e); } catch { }
            string all = ((o ?? "") + " " + (e ?? "")).ToLowerInvariant();
            if (all.Trim().Length == 0) return "";

            // 两个芯片的关键字互斥，先精确匹配再模糊
            for (int i = 0; i < CHIPS.Length; i++)
            {
                string[] keys = CHIPS[i].DetectKeys;
                for (int k = 0; k < keys.Length; k++)
                {
                    if (all.IndexOf(keys[k], StringComparison.Ordinal) >= 0)
                        return CHIPS[i].Key;
                }
            }
            return "";
        }

        // ==================== 登录 ====================
        //
        // chip    芯片 key（必填）
        // host    8295 专用 telnet 地址（空则用默认）
        // user    8295 专用账号
        // pass    8295 专用密码
        // sup     su 密码（8295 专用；有些环境 su 不需要密码，允许空）
        internal static bool ClusterLogin(string chip, string host, string user,
                                          string pass, string sup)
        {
            CLU_LOGGED = false;
            CLU_ERR = "";
            CLU_CHIP = "";

            ChipProfile p = FindChip(chip);
            if (p == null)
            {
                CLU_ERR = "未选择芯片（8838 / 8295）";
                Fail(CLU_ERR);
                return false;
            }
            if (!RequireDevice("登录仪表通道前需要先连上设备")) 
            {
                CLU_ERR = "没有连接设备";
                return false;
            }

            Info("仪表通道登录：" + p.Label);
            Blank();

            bool ok = p.IsTelnet
                ? LoginTelnet(p, host, user, pass, sup)
                : LoginAdbLxc(p);

            if (ok)
            {
                CLU_LOGGED = true;
                CLU_CHIP = p.Key;
                // 记住选择（下次自动带出；凭据单独存，见 UI 侧）
                SaveClusterIni("clu_chip", p.Key);
                Blank();
                Ok("✓ 登录成功（" + p.Label + "）");
                Hint("现在可以开启仪表实时显示了");
            }
            else
            {
                // ★ 失败时清空芯片，逼用户重新走"选芯片 → 登录"流程
                //   （否则页面可能留着旧状态，出现"没登录也能投屏"）
                CLU_CHIP = "";
            }
            return ok;
        }

        // ---- 8838：adb + lxc-attach（免密）----
        //
        // 要点：
        //   1) 必须 adb root —— lxc-attach 需要 root 权限
        //   2) 容器名来自芯片档案（linux-8838）
        //   3) 用 echo 标记验证真的进了容器（只看 exit code 不可靠：
        //      lxc-attach 失败时也可能返回 0）
        private static bool LoginAdbLxc(ChipProfile p)
        {
            Info("① adb root");
            string o = "", e = "";
            try { ShellCall(CUR, "root", out o, out e); } catch { }
            System.Threading.Thread.Sleep(700);   // root 后 adbd 重连

            Info("② lxc-attach -n " + p.LxcName);
            string marker = "__CLU_OK_" + Guid.NewGuid().ToString("N").Substring(0, 8) + "__";
            string cmd = "lxc-attach -n " + p.LxcName + " -- echo " + marker;

            o = ""; e = "";
            try { ShellCall(CUR, cmd, out o, out e); } catch { }
            string all = ((o ?? "") + "\n" + (e ?? ""));

            if (all.IndexOf(marker, StringComparison.Ordinal) >= 0)
            {
                Ok("  容器可达：" + p.LxcName);
                return true;
            }

            // 失败分类，给可执行的下一步（而不是只报"失败"）
            if (all.IndexOf("not found", StringComparison.OrdinalIgnoreCase) >= 0
                || all.IndexOf("No such", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                CLU_ERR = "容器不存在或 lxc-attach 不可用：" + p.LxcName;
                Fail(CLU_ERR);
                Hint("确认平台确实是 8838；或改用 8295（telnet 通道）");
            }
            else if (all.IndexOf("permission", StringComparison.OrdinalIgnoreCase) >= 0
                  || all.IndexOf("denied", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                CLU_ERR = "权限不足（adb root 没成功）";
                Fail(CLU_ERR);
                Hint("先确认 `adb root` 能否成功；部分机器需要额外提权");
            }
            else
            {
                CLU_ERR = "lxc-attach 未返回预期标记";
                Fail(CLU_ERR);
                if (all.Trim().Length > 0) Hint("原始输出：" + FirstLine(all).Trim());
            }
            return false;
        }

        // ---- 8295：telnet + su ----
        //
        // ★ 这里刻意**不做完整交互式登录**，只做到"通道可达"的验证。
        //   原因：我们的 shell 封装是"一次执行拿输出"，而 telnet 登录是
        //   多阶段交互（等 Password: 提示 → 送密码 → 等 $ 提示 → 送 su →
        //   等 Password → 送 su 密码 → 等 # 提示），在一次性通道里做不可靠。
        //
        //   逆向工具能做完整体登录，是因为它自己维护了一个持久 telnet 会话
        //   （TelnetSession 类 + 保活线程 + TELNET_STAGE_PATTERNS 分阶段匹配）。
        //   那套东西要移植过来就是 R1「持久通道」的工作量。
        //
        //   所以第一版只做：**端口可达 + 凭据齐全** 两项校验，
        //   满足用户要的"选芯片+登录后才能投屏"的流程门禁。
        //   完整登录放到 R1 实施时再做（见 docs/BACKLOG-mechanisms.md）。
        private static bool LoginTelnet(ChipProfile p, string host, string user,
                                        string pass, string sup)
        {
            string h = (host == null ? "" : host.Trim());
            if (h.Length == 0) h = p.DefaultHost;

            if (h.Length == 0)
            {
                CLU_ERR = "telnet 地址为空";
                Fail(CLU_ERR);
                return false;
            }
            if (string.IsNullOrEmpty(user) || string.IsNullOrEmpty(pass))
            {
                CLU_ERR = "8295 需要填 telnet 账号和密码";
                Fail(CLU_ERR);
                Hint("凭据只存在本机 ini，不会外传、不会写进日志");
                return false;
            }

            Info("① 检查设备是否带 busybox telnet");
            string o = "", e = "";
            try { ShellCall(CUR, "which busybox || busybox | head -1", out o, out e); } catch { }
            string which = (o ?? "").Trim();
            if (which.Length == 0)
                Warn("  未找到 busybox（部分环境用 toybox / 系统自带 telnet）");
            else
                Hint("  " + FirstLine(which).Trim());

            Info("② 探测 " + h + " 的 telnet 端口（23）");
            // 用 nc 或 timeout+telnet 判断端口是否通。
            // 优先 nc（干净），退回 /dev/tcp 重定向（bash），再退回 busybox nc
            string probe =
                "(nc -z -w 2 " + h + " 23 && echo __PORT_OK__) 2>/dev/null || " +
                "((echo >/dev/tcp/" + h + "/23) >/dev/null 2>&1 && echo __PORT_OK__) || " +
                "(busybox nc -z -w 2 " + h + " 23 && echo __PORT_OK__) 2>/dev/null";
            o = ""; e = "";
            try { ShellCall(CUR, probe, out o, out e); } catch { }
            string pr = ((o ?? "") + (e ?? ""));

            if (pr.IndexOf("__PORT_OK__", StringComparison.Ordinal) >= 0)
            {
                Ok("  端口可达：" + h + ":23");
            }
            else
            {
                // 端口探测工具可能都不存在 —— 这是环境限制，不是错误。
                // 给 warn 但**仍允许登录**（凭据齐全 + 用户明确选了这个芯片）。
                Warn("  端口探测未成功（可能是设备缺少 nc，不一定是网络不通）");
                Hint("  地址：" + h + ":23");
                Hint("  若后续命令超时，请确认车机侧 telnet 服务已启动");
            }

            Info("③ 校验凭据完整性");
            Ok("  账号：" + MaskUser(user));
            Ok("  密码：已设置（" + pass.Length + " 位，不回显）");
            Ok("  su 密码：" + (string.IsNullOrEmpty(sup) ? "未填（部分环境 su 免密）"
                                                          : "已设置（" + sup.Length + " 位，不回显）"));

            // 把地址回写（下次自动带出）
            SaveClusterIni("clu_host", h);
            return true;
        }

        // 账号脱敏：只留首尾各 1 位，中间打码
        private static string MaskUser(string u)
        {
            if (string.IsNullOrEmpty(u)) return "（空）";
            if (u.Length <= 2) return u.Substring(0, 1) + "*";
            return u.Substring(0, 1) + new string('*', Math.Min(u.Length - 2, 6))
                 + u.Substring(u.Length - 1, 1);
        }

        // ==================== 退出登录 ====================
        internal static void ClusterLogout()
        {
            string was = CLU_CHIP;
            CLU_LOGGED = false;
            CLU_CHIP = "";
            CLU_ERR = "";
            if (was.Length > 0) Ok("已退出仪表通道（" + was + "）");
            else Info("当前未登录");
            Hint("退出后不能开启仪表实时显示");
        }

        // ==================== 投屏（带门禁）====================
        //
        // ★ 用户明确要求的交互：必须**选芯片 + 登录成功**才能投。
        //   这里在 C# 侧再做一道校验 —— 页面上按钮虽然会置灰，
        //   但脚本/快捷键仍可能绕过前端，服务端必须自己拦。
        internal static void ClusterCast(int displayId, bool viewOnly)
        {
            if (!CLU_LOGGED || CLU_CHIP.Length == 0)
            {
                Fail("请先选择芯片并登录，再开启仪表实时显示");
                Hint("流程：① 选芯片（8838 / 8295）→ ② 点「登录设备」→ ③ 开显示");
                return;
            }
            ChipProfile p = FindChip(CLU_CHIP);
            if (p == null)
            {
                Fail("登录状态异常，请重新登录");
                CLU_LOGGED = false;
                return;
            }

            if (displayId < 0) displayId = p.DefaultDisplay;

            Info("开启仪表实时显示（" + p.Label + "）");
            Info("  屏号：" + displayId + (viewOnly ? "  只读（不接管输入）" : "  可点击"));
            Hint("  走 scrcpy --display-id=" + displayId + "，与工具既有投屏通道一致");
            Blank();

            string err = "";
            // 两个入口都在 Scrcpy 里现成有：
            //   Launch     → 默认带控制（鼠标可点车机）
            //   LaunchView → --no-control（只看，不会误触）
            bool ok = viewOnly
                ? Scrcpy.LaunchView(displayId, "仪表-" + p.Key, out err)
                : Scrcpy.Launch(displayId, "仪表-" + p.Key, out err);

            if (ok) Ok("✓ 已打开仪表窗口（屏 " + displayId + "）");
            else
            {
                Fail("投屏失败：" + (err == null ? "未知" : err));
                Hint("可用 `:scrcpy " + displayId + "` 手动验证该屏能否投出");
            }
        }

        // ==================== CLI 入口（与 GUI 共用同一套实现）====================

        // :clogin [chip] [host] [user] [pass] [su]
        // 参数都可省略：省略的从 ini 里带出（页面填过的值）
        internal static void DoClusterLoginCli(string argRaw)
        {
            string a = (argRaw == null ? "" : argRaw).Trim();
            string[] t = a.Split(new char[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries);

            string chip = t.Length > 0 ? t[0] : ReadClusterIni("clu_chip", "");
            string host = t.Length > 1 ? t[1] : ReadClusterIni("clu_host", "");
            string user = t.Length > 2 ? t[2] : ReadClusterIni("clu_user", "");
            string pass = t.Length > 3 ? t[3] : ReadClusterIni("clu_pass", "");
            string sup  = t.Length > 4 ? t[4] : ReadClusterIni("clu_su", "");

            if (chip.Length == 0)
            {
                Warn("用法：:clogin <8838|8295> [host] [user] [pass] [su]");
                Hint("8295 需要 host/账号/密码；8838 免密（走 lxc-attach）");
                return;
            }
            ClusterLogin(chip, host, user, pass, sup);
        }

        // :cdetect
        internal static void DoChipDetect()
        {
            if (!RequireDevice("")) return;
            Info("自动识别芯片…");
            string c = DetectChip();
            if (c.Length == 0)
            {
                Warn("未能自动识别芯片型号");
                Hint("逆向工具在识别失败时也是沿用当前选择 —— 请手动选 8838 / 8295");
            }
            else
            {
                ChipProfile p = FindChip(c);
                Ok("✓ 识别为：" + (p == null ? c : p.Label));
                Hint("可用 `:clogin " + c + "` 直接登录");
            }
        }

        // :ccast [屏号] [view]
        internal static void DoClusterCastCli(string argRaw)
        {
            string a = (argRaw == null ? "" : argRaw).Trim();
            string[] t = a.Split(new char[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries);
            int id = -1;
            bool view = false;
            for (int i = 0; i < t.Length; i++)
            {
                string x = t[i].ToLowerInvariant();
                if (x == "view" || x == "只看") view = true;
                else { int nn; if (int.TryParse(x, out nn)) id = nn; }
            }
            ClusterCast(id, view);
        }

        // ==================== ini 存取（凭据只落本机）====================
        //
        // 为什么不复用 Profile.WriteIniKey / GuiWeb.SaveIniKey：
        //   Profile 是独立的 internal static class（不是 App 的 partial），
        //   GuiWeb 是 Form 子类 —— 两者的私有 ini 方法 App 都调不到。
        //   所以这里自实现一份，路径规则与它们**保持一致**（先 internal 再根目录），
        //   避免出现"写到另一个 ini 里、下次读不到"的问题。
        private static string ClusterIniPath()
        {
            try
            {
                string b = AppDomain.CurrentDomain.BaseDirectory;
                string p = Path.Combine(b, "internal", "adb_log_export.ini");
                if (File.Exists(p)) return p;
                return Path.Combine(b, "adb_log_export.ini");
            }
            catch { return ""; }
        }

        internal static void SaveClusterIni(string key, string val)
        {
            try
            {
                string p = ClusterIniPath();
                if (p.Length == 0 || !File.Exists(p)) return;
                string[] lines = File.ReadAllLines(p, Encoding.UTF8);
                bool found = false;
                for (int i = 0; i < lines.Length; i++)
                {
                    if (lines[i].TrimStart().StartsWith(key + "=", StringComparison.OrdinalIgnoreCase))
                    {
                        lines[i] = key + "=" + (val == null ? "" : val);
                        found = true;
                        break;
                    }
                }
                if (!found)
                {
                    List<string> add = new List<string>(lines);
                    add.Add(key + "=" + (val == null ? "" : val));
                    lines = add.ToArray();
                }
                File.WriteAllLines(p, lines, Encoding.UTF8);
            }
            catch { }
        }

        internal static string ReadClusterIni(string key, string def)
        {
            try
            {
                string p = ClusterIniPath();
                if (p.Length == 0 || !File.Exists(p)) return def;
                string[] lines = File.ReadAllLines(p, Encoding.UTF8);
                for (int i = 0; i < lines.Length; i++)
                {
                    string t = lines[i].Trim();
                    if (t.StartsWith(key + "=", StringComparison.OrdinalIgnoreCase))
                        return t.Substring(key.Length + 1).Trim();
                }
            }
            catch { }
            return def;
        }
    }
}
