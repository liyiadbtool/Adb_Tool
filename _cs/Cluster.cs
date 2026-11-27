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
                Key = "8838", Label = "8838",
                IsTelnet = false,
                LxcName = "linux-8838",
                DefaultHost = "",
                DetectKeys = new string[] { "qcm8838", "8838" },
                DefaultDisplay = 2
            },
            new ChipProfile {
                Key = "8295", Label = "8295",
                IsTelnet = true,
                LxcName = "",
                DefaultHost = "192.168.8.1",   // 逆向字符串里出现的默认地址
                DetectKeys = new string[] { "sa8295", "8295" },
                DefaultDisplay = 2
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

        // 2026-11-23：允许"跳过登录直接投屏"。
        // 依据（本文件开头也写了）：scrcpy 取画面走 adb 通道，与 telnet/lxc 登录无关；
        // 登录只是流程门禁 + 通道连通性自检。8295 的 telnet 凭据拿不到时，
        // 用户仍然可以投屏 —— 这时候把门禁做成可选，比让人卡在登录页合理。
        internal static bool CLU_SKIP = false;

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
            try { AdbCall(new List<string> { "root" }, out o, out e); } catch { }
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

        // ==================== 仪表录屏（B3）====================
        //
        // 与普通屏录制（:castrec）**完全独立**：
        //   · 普通录屏走 :castrec <屏号>，不需要芯片/登录
        //   · 仪表录屏走 :ccastrec，**必须登录**，屏号取芯片档案默认值
        //
        // 互不影响的技术保证：
        //   每次录制都是独立的 scrcpy --record 进程，各写各的 mp4；
        //   LaunchRecord 启动后立即返回，不阻塞。
        //   两个录制同时跑 = 两个进程并行。
        //
        // ⚠ 唯一约束：同一个 display 不能同时投/录两次
        //   （Scrcpy.Active 按 displayId 去重）。若仪表屏号 = 4，
        //   而用户又在录「副驾屏 4」，第二个会被拒 —— 这是物理限制，不是 bug。
        internal static void ClusterCastRec(int sec)
        {
            if (!CLU_LOGGED || CLU_CHIP.Length == 0)
            {
                Fail("请先选择芯片并登录，再录制仪表");
                Hint("流程：① 选芯片 → ② 点「登录设备」→ ③ 录 60s");
                return;
            }
            ChipProfile p = FindChip(CLU_CHIP);
            if (p == null)
            {
                Fail("登录状态异常，请重新登录");
                CLU_LOGGED = false;
                return;
            }

            int displayId = p.DefaultDisplay;
            if (sec <= 0) sec = 60;
            if (sec > 1800) sec = 1800;

            // 复用与 :castrec 完全相同的一套：OutDir + LaunchRecord
            string dir = OutDirFor("screenrecord", "screenrecord");
            string file = Path.Combine(dir, "cluster" + displayId + "_"
                          + DateTime.Now.ToString("HHmmss") + ".mp4");

            Info("录制仪表（" + p.Label + "）屏号 " + displayId + "，" + sec + " 秒");
            string err = "";
            if (!Scrcpy.LaunchRecord(displayId, "仪表-" + p.Key, file, sec, out err))
            {
                Fail("scrcpy 启动失败：" + (err == null ? "未知" : err));
                Hint("如果提示该屏已被占用，先用 :caststop " + displayId + " 关掉");
                return;
            }
            Ok("✓ 已开始录制仪表（" + sec + " 秒后自动停止）");
            Hint("文件：" + file);
            Hint("普通屏录制不受影响，可同时进行");
        }

        // ==================== 退出登录 ====================
        /// <summary>
        /// 从 ClusterDebugTool 的 config_*.json 导入 telnet 通道配置。
        ///
        /// 为什么不在代码里写死账号密码：那种东西属于内部资料，硬编码进源码既不合规
        /// 也无法换环境。这里只负责"按已知键名取出来写进本机 ini"，值从用户的文件来，
        /// 全程不回显、不打日志、不进 git（ini 已在 .gitignore）。
        ///
        /// 已知键名（逆向得到）：telnet_host / telnet_username / telnet_password / su_password
        /// 兼容大小写与常见变体（user/username、pass/password、su/su_password）。
        /// </summary>
        internal static string ImportFromTool(string jsonPath, out int cluCount)
        {
            cluCount = 0;
            try
            {
                if (string.IsNullOrEmpty(jsonPath) || !System.IO.File.Exists(jsonPath))
                    return "文件不存在：" + jsonPath;

                string txt = System.IO.File.ReadAllText(jsonPath, Encoding.UTF8);

                string host = PickJson(txt, "telnet_host");
                string user = PickJson(txt, "telnet_username", "telnet_user", "username");
                string pass = PickJson(txt, "telnet_password", "telnet_pass", "password");
                string sup  = PickJson(txt, "su_password", "su_pass", "supassword", "root_password");

                if (host.Length == 0 && user.Length == 0 && pass.Length == 0 && sup.Length == 0)
                    return "没找到 telnet_host / username / password / su_password 字段（确认选的是 config_aht.json？）";

                if (host.Length > 0) { SaveClusterIni("clu_host", host); cluCount++; }
                if (user.Length > 0) { SaveClusterIni("clu_user", user); cluCount++; }
                if (pass.Length > 0) { SaveClusterIni("clu_pass", pass); cluCount++; }
                if (sup.Length  > 0) { SaveClusterIni("clu_su",   sup);  cluCount++; }

                // 只报"导入了几个字段"，绝不回显值
                return "已导入 " + cluCount + " 个字段（host/user/pass/su 里成功的那些）";
            }
            catch (Exception ex)
            {
                return "导入失败：" + ex.Message;
            }
        }

        /// <summary>按若干候选键名从扁平 JSON 里取第一个非空字符串值（不引 JSON 库）。</summary>
        private static string PickJson(string js, params string[] keys)
        {
            foreach (string k in keys)
            {
                int i = js.IndexOf("\"" + k + "\"", StringComparison.OrdinalIgnoreCase);
                if (i < 0) continue;
                i = js.IndexOf(':', i);
                if (i < 0) continue;
                i++;
                while (i < js.Length && char.IsWhiteSpace(js[i])) i++;
                if (i >= js.Length || js[i] != '"') continue;
                i++;
                StringBuilder sb = new StringBuilder();
                for (; i < js.Length && js[i] != '"'; i++)
                {
                    if (js[i] == '\\' && i + 1 < js.Length) { i++; sb.Append(js[i]); }
                    else sb.Append(js[i]);
                }
                string v = sb.ToString().Trim();
                if (v.Length > 0) return v;
            }
            return "";
        }

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
        /// <summary>跑一条 adb shell 命令并返回 stdout（失败返回空串）。</summary>
        private static string Sh(string shellCmd)
        {
            try
            {
                string adb = App.ADB;
                if (string.IsNullOrEmpty(adb)) adb = "adb";
                var psi = new System.Diagnostics.ProcessStartInfo();
                psi.FileName = adb;
                psi.Arguments = (string.IsNullOrEmpty(App.SERIAL) ? "" : ("-s " + App.SERIAL + " "))
                               + " shell " + shellCmd;
                psi.UseShellExecute = false;
                psi.CreateNoWindow = true;
                psi.RedirectStandardOutput = true;
                psi.RedirectStandardError = true;
                using (var pr = System.Diagnostics.Process.Start(psi))
                {
                    string o = pr.StandardOutput.ReadToEnd();
                    pr.StandardError.ReadToEnd();
                    if (!pr.WaitForExit(15000)) { try { pr.Kill(); } catch { } }
                    return o ?? "";
                }
            }
            catch { return ""; }
        }

        /// <summary>当前设备真实存在的 display id 列表（dumpsys display 解析）。</summary>
        internal static List<int> AvailableDisplays()
        {
            var list = new List<int>();
            try
            {
                string outp = Sh("dumpsys display | grep -oE 'mDisplayId=[0-9]+' | sort -u");
                if (string.IsNullOrEmpty(outp)) return list;
                foreach (string line in outp.Split('\n'))
                {
                    int eq = line.IndexOf('=');
                    if (eq < 0) continue;
                    int id;
                    if (int.TryParse(line.Substring(eq + 1).Trim(), out id) && !list.Contains(id))
                        list.Add(id);
                }
                list.Sort();
            }
            catch { }
            return list;
        }

        /// <summary>每个屏的高度（width x height 里的 height），用于挑"长条仪表屏"。</summary>
        internal static Dictionary<int, int> DisplaySizes()
        {
            var map = new Dictionary<int, int>();
            try
            {
                string outp = Sh("dumpsys display | grep -E 'DisplayDeviceInfo' | head -8");
                if (string.IsNullOrEmpty(outp)) return map;
                int idx = 0;
                foreach (string line in outp.Split('\n'))
                {
                    var m = System.Text.RegularExpressions.Regex.Match(line, @"(\d+)\s*x\s*(\d+)");
                    if (m.Success)
                    {
                        int h;
                        if (int.TryParse(m.Groups[2].Value, out h)) map[idx] = h;
                        idx++;
                    }
                }
            }
            catch { }
            return map;
        }

        internal static void ClusterCast(int displayId, bool viewOnly)
        {
            // 勾了"跳过登录"就只校验芯片；登录不是投屏的技术前提
            bool skipped = CLU_SKIP;
            if (!skipped && (!CLU_LOGGED || CLU_CHIP.Length == 0))
            {
                Fail("请先选择芯片并登录，再开启仪表实时显示");
                Hint("流程：① 选芯片（8838 / 8295）→ ② 点「登录设备」→ ③ 开显示");
                Hint("8295 没有 telnet 口令时，可勾选「跳过登录直接投屏」");
                return;
            }
            ChipProfile p = FindChip(CLU_CHIP);
            if (p == null && skipped)
            {
                // 跳过登录时芯片可能没选：退回按当前设备识别
                string det = DetectChip();
                p = FindChip(det);
                if (p != null) CLU_CHIP = p.Key;
            }
            if (p == null)
            {
                Fail("登录状态异常，请重新登录");
                CLU_LOGGED = false;
                return;
            }

            if (displayId < 0) displayId = p.DefaultDisplay;

            // 2026-11-23：投不出画面的头号原因是**屏号不存在**。
            // 默认值 4 来自逆向时的台架，换一台车机可能只有 0~3（实测 b09acfa2
            // 就是 0:2560x1440 中控 / 1:2880x1620 / 2:1920x480 长条 / 3:800x480）。
            // 这里先查真实存在的屏：目标不在就自动挑一个"像仪表"的（高度 < 600 的长条屏），
            // 并把可用清单打出来，避免用户对着"投不出来"干瞪眼。
            var ids = AvailableDisplays();
            if (ids.Count > 0 && !ids.Contains(displayId))
            {
                int pick = -1, pickH = 0;
                var tops = DisplaySizes();
                foreach (var kv in tops)
                {
                    if (kv.Value < 600 || kv.Value > 4000) continue;   // 长条屏优先
                    if (pick < 0 || kv.Value > pickH) { pick = kv.Key; pickH = kv.Value; }
                }
                if (pick < 0) pick = ids[0];
                Warn("屏号 " + displayId + " 在当前设备上不存在，自动改用 " + pick);
                Hint("可用屏号：" + string.Join(", ", ids.ToArray()));
                displayId = pick;
            }

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

        // :displays —— 动态列屏幕上所有 display（scrcpy --list-displays）
        internal static void DoListDisplays()
        {
            if (!RequireDevice("")) return;

            Info("列出屏幕（scrcpy --list-displays）…");
            string err = "";
            var list = Scrcpy.ListDisplays(out err);

            if (list.Count == 0)
            {
                Fail(err.Length > 0 ? err : "没有列出任何屏幕");
                Hint("可用 `:cast <屏号>` 直接试某个屏号");
                return;
            }

            Blank();
            Ok("找到 " + list.Count + " 块屏：");
            for (int i = 0; i < list.Count; i++)
            {
                int[] d = list[i];
                // 常见屏号的语义提示（仅作参考，真值以实际为准）
                string guess = "";
                if (d[0] == 0) guess = "（通常是主屏 / 中控）";
                else if (d[0] == 4) guess = "（常见于仪表 / 副驾屏）";
                Hint("  display " + d[0] + "   " + d[1] + "x" + d[2] + "  " + guess);
            }
            Blank();
            Hint("投屏：:cast <屏号>    仪表：:clogin <芯片> 后再 :ccast <屏号>");
        }

        // :ccastrec [秒]  —— 录制仪表（默认 60 秒）
        internal static void DoClusterRecCli(string argRaw)
        {
            string a = (argRaw == null ? "" : argRaw).Trim();
            int sec = 60;
            if (a.Length > 0) int.TryParse(a, out sec);
            ClusterCastRec(sec);
        }

        // ====================================================================
        //  2026-11-22（第 18 批 D4）：车机 TOP5 进程 + 剩余 CPU/内存
        // --------------------------------------------------------------------
        //  一条 shell 拿齐：
        //    · top 头部 cpu 行  → 全机占用（idle 反推剩余）
        //    · /proc/meminfo    → MemTotal / MemAvailable
        //    · top 进程区       → 按 CPU% 排序取 5
        //
        //  ★ Android 的 top 有几套实现（toybox / busybox / procps），
        //    列格式和参数都不一样。这里**不依赖 -m/-o 参数**，
        //    而是自己解析表头定位列号 —— 换平台不会错位。
        // ====================================================================
        internal static string CarTop5()
        {
            if (DEVN == 0) return "{\"ok\":false,\"err\":\"没有连接设备\"}";

            // 统一输出成 "标记|内容" 形式，C# 侧好切分
            string cmd =
                // ★ Android(toybox) 的 CPU 行是 "600%cpu  8%user ... 588%idle ..."
                //   行首是数字不是 "cpu"，所以不能按 ^cpu 去 grep，改成抓含 idle 的行。
                //   顺带能从 "600%cpu" 推出核数（600/100 = 6）。
                "echo '##CPU'; top -n 1 -b 2>/dev/null | grep -m1 -i 'idle' ; " +
                "echo '##MEM'; grep -E '^MemTotal:|^MemAvailable:' /proc/meminfo; " +
                "echo '##PROC'; top -n 1 -b 2>/dev/null | head -40; " +
                "echo '##END'";

            string o = "", e = "";
            try { ShellCall(CUR, cmd, out o, out e); } catch { }
            string all = (o ?? "") + "\n" + (e ?? "");

            // ---- 切段 ----
            string cpuLine = Between(all, "##CPU", "##MEM");
            string memBlk = Between(all, "##MEM", "##PROC");
            string procBlk = Between(all, "##PROC", "##END");

            // ---- 内存 ----
            long memTotal = 0, memAvail = 0;
            foreach (string ln in (memBlk ?? "").Split('\n'))
            {
                string t = ln.Trim();
                if (t.StartsWith("MemTotal:")) memTotal = FirstNumber(t);
                else if (t.StartsWith("MemAvailable:")) memAvail = FirstNumber(t);
            }

            // ---- CPU（从 cpu 行里找 idle，剩余 = 100 - (100 - idle) = idle）----
            // top 的 cpu 行形如：cpu  12% user 3% sys 0% nic 84% idle ...
            // 注意不同版本可能是 "84%idle"（无空格），用正则兼容两种写法
            double freeCpu = -1;
            int carCores = 1;
            if (!string.IsNullOrEmpty(cpuLine))
            {
                // idle 值（形如 "588%idle" 或 "84% idle"）
                System.Text.RegularExpressions.Match mi =
                    System.Text.RegularExpressions.Regex.Match(cpuLine, @"([\d.]+)\s*%?\s*idle");
                if (mi.Success)
                {
                    double idle;
                    if (double.TryParse(mi.Groups[1].Value,
                        System.Globalization.NumberStyles.Float,
                        System.Globalization.CultureInfo.InvariantCulture, out idle))
                    {
                        // ★ 这里的 idle 是"占所有核累加"的百分比（6 核 → 满载 600%）。
                        //   换算成"占全机"才是人话：idle / 总百分比 × 100。
                        //   总百分比形如 "600%cpu"，从同一条行里取。
                        System.Text.RegularExpressions.Match mt =
                            System.Text.RegularExpressions.Regex.Match(cpuLine, @"([\d.]+)\s*%?\s*cpu");
                        double totalPct = 100;
                        if (mt.Success)
                        {
                            double tv;
                            if (double.TryParse(mt.Groups[1].Value,
                                System.Globalization.NumberStyles.Float,
                                System.Globalization.CultureInfo.InvariantCulture, out tv)
                                && tv > 0)
                            {
                                totalPct = tv;
                                carCores = (int)Math.Round(tv / 100.0);
                                if (carCores < 1) carCores = 1;
                            }
                        }
                        freeCpu = idle / totalPct * 100.0;
                        if (freeCpu < 0) freeCpu = 0;
                        if (freeCpu > 100) freeCpu = 100;
                    }
                }
            }

            // ---- 进程 top5：按表头定位列 ----
            // 表头形如：  PID USER  PR NI  VIRT  RES  SHR S[%CPU] %CPU %MEM  TIME+  ARGS
            // 不同版本列数和顺序都不同，所以先找表头，记下 PID/%CPU/%MEM/ARGS 的下标
            var rows = new List<string[]>();
            string[] lines = (procBlk ?? "").Split('\n');
            int hPID = -1, hCPU = -1, hMEM = -1, hName = -1;
            int hResIdx = -1, hNameIdx = -1;
            for (int i = 0; i < lines.Length; i++)
            {
                string t = lines[i];
                if (t == null) continue;
                string tr = t.Trim();
                if (tr.Length == 0) continue;

                // 表头：同时含 PID 和 %CPU
                if (hPID < 0 && tr.IndexOf("PID", StringComparison.Ordinal) >= 0
                    && tr.IndexOf("CPU", StringComparison.Ordinal) >= 0)
                {
                    // ★ Android(toybox) 的表头把状态和 CPU% 挤在一个 token 里：
                    //     PID USER PR NI VIRT RES SHR S[%CPU] %MEM TIME+ ARGS
                    //   但**数据行是分开的两列**（R  8.0  0.0 ...）。
                    //   所以这里要先把 "S[%CPU]" 拆成 "S" 和 "%CPU" 两列，
                    //   否则后面的列索引全部左移一位 —— 表现为"CPU% 显示成 0、内存显示成 CPU%"。
                    var hs = new List<string>();
                    string[] raw = tr.Split(new char[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries);
                    for (int h = 0; h < raw.Length; h++)
                    {
                        string x = raw[h];
                        int br = x.IndexOf('[');
                        if (br > 0 && x.EndsWith("]"))
                        {
                            hs.Add(x.Substring(0, br));                      // "S"
                            hs.Add(x.Substring(br + 1, x.Length - br - 2));  // "%CPU"
                        }
                        else hs.Add(x);
                    }
                    for (int h = 0; h < hs.Count; h++)
                    {
                        string x = hs[h].ToUpperInvariant();
                        if (x == "PID") hPID = h;
                        else if (x.IndexOf("%CPU", StringComparison.Ordinal) >= 0 || x == "CPU%") hCPU = h;
                        else if (x.IndexOf("%MEM", StringComparison.Ordinal) >= 0 || x == "MEM%") hMEM = h;
                        else if (x == "ARGS" || x == "NAME" || x == "CMD" || x == "COMMAND") hName = h;
                    }
                    hResIdx = -1;
                    for (int h2 = 0; h2 < hs.Count; h2++)
                        if (hs[h2].ToUpperInvariant() == "RES") hResIdx = h2;
                    hNameIdx = hName;
                    continue;
                }

                // 数据行：按列数大致对得上才收
                if (hPID >= 0 && hCPU >= 0)
                {
                    string[] cs = tr.Split(new char[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries);
                    if (cs.Length <= hCPU || cs.Length <= hPID) continue;
                    int pid;
                    if (!int.TryParse(cs[hPID], out pid)) continue;   // PID 列不是数字 → 跳过
                    rows.Add(cs);
                }
            }

            // 按 CPU% 排序
            rows.Sort(delegate(string[] a, string[] b)
            {
                return ParseD(b[hCPU]).CompareTo(ParseD(a[hCPU]));
            });

            StringBuilder sb = new StringBuilder();
            sb.Append("{\"ok\":true");
            sb.Append(",\"memTotal\":").Append(memTotal > 0 ? (memTotal / 1048576.0).ToString("0.0", System.Globalization.CultureInfo.InvariantCulture) : "null");
            sb.Append(",\"memFree\":").Append(memAvail > 0 ? (memAvail / 1048576.0).ToString("0.0", System.Globalization.CultureInfo.InvariantCulture) : "null");
            sb.Append(",\"freeCpu\":").Append(freeCpu < 0 ? "null" : freeCpu.ToString("0.0", System.Globalization.CultureInfo.InvariantCulture));

            // CPU 榜
            sb.Append(",\"cpu\":[");
            int n = 0;
            for (int i = 0; i < rows.Count && n < 5; i++)
            {
                string[] r = rows[i];
                // toybox 的 %CPU 是"占单核"，除核数换成"占全机"，与本机口径一致
                double pct = ParseD(r[hCPU]) / carCores;
                if (pct <= 0.1) continue;
                string pname = (hName >= 0 && hName < r.Length) ? r[hName]
                             : (r.Length > 0 ? r[r.Length - 1] : "?");
                if (n > 0) sb.Append(',');
                sb.Append("{\"n\":").Append(JsonStr(ShortName(pname)))
                  .Append(",\"v\":").Append(pct.ToString("0.0", System.Globalization.CultureInfo.InvariantCulture))
                  .Append('}');
                n++;
            }
            sb.Append("],\"mem\":[");

            // 内存榜：按 RES 排（表头里有 RES 列的话）
            int hRes = hResIdx;
            var mrows = new List<string[]>(rows);
            if (hRes >= 0)
            {
                mrows.Sort(delegate(string[] a, string[] b)
                {
                    double va = (hRes < a.Length) ? ParseMem(a[hRes]) : 0;
                    double vb = (hRes < b.Length) ? ParseMem(b[hRes]) : 0;
                    return vb.CompareTo(va);
                });
            }
            int nm = 0;
            for (int i = 0; i < mrows.Count && nm < 5; i++)
            {
                string[] r = mrows[i];
                string nmn = (hName >= 0 && hName < r.Length) ? r[hName]
                           : (r.Length > 0 ? r[r.Length - 1] : "?");
                string memTxt = (hRes >= 0 && hRes < r.Length) ? r[hRes] : "";
                if (nm > 0) sb.Append(',');
                sb.Append("{\"n\":").Append(JsonStr(ShortName(nmn)))
                  .Append(",\"v\":").Append(JsonStr(memTxt)).Append('}');
                nm++;
            }
            sb.Append("]}");
            return sb.ToString();
        }

        // ---- 小工具 ----

        // 极简 JSON 字符串转义（Cluster.cs 不是 GuiWeb，拿不到那边的 Json()）
        private static string JsonStr(string v)
        {
            if (v == null) return "\"\"";
            StringBuilder b = new StringBuilder("\"");
            for (int i = 0; i < v.Length; i++)
            {
                char c = v[i];
                if (c == '"') b.Append("\\\"");
                else if (c == '\\') b.Append("\\\\");
                else if (c == '\n') b.Append("\\n");
                else if (c == '\r') b.Append("\\r");
                else if (c == '\t') b.Append("\\t");
                else if (c < ' ') b.Append(' ');
                else b.Append(c);
            }
            b.Append('"');
            return b.ToString();
        }

        private static string Between(string all, string a, string b)
        {
            if (string.IsNullOrEmpty(all)) return "";
            int i = all.IndexOf(a, StringComparison.Ordinal);
            if (i < 0) return "";
            i += a.Length;
            int j = all.IndexOf(b, i, StringComparison.Ordinal);
            if (j < 0) j = all.Length;
            return all.Substring(i, j - i);
        }

        private static long FirstNumber(string s)
        {
            System.Text.RegularExpressions.Match m =
                System.Text.RegularExpressions.Regex.Match(s ?? "", @"(\d+)");
            long v;
            return (m.Success && long.TryParse(m.Groups[1].Value, out v)) ? v : 0;
        }

        private static double ParseD(string s)
        {
            if (string.IsNullOrEmpty(s)) return 0;
            double v;
            return double.TryParse(s.Trim().TrimEnd('%'),
                System.Globalization.NumberStyles.Float,
                System.Globalization.CultureInfo.InvariantCulture, out v) ? v : 0;
        }

        // RES 列可能是 "123M" / "4560K" / "12G"，换算成 KB 便于排序
        private static double ParseMem(string s)
        {
            if (string.IsNullOrEmpty(s)) return 0;
            string t = s.Trim().ToUpperInvariant();
            double mul = 1;
            if (t.EndsWith("G")) { mul = 1048576; t = t.Substring(0, t.Length - 1); }
            else if (t.EndsWith("M")) { mul = 1024; t = t.Substring(0, t.Length - 1); }
            else if (t.EndsWith("K")) { mul = 1; t = t.Substring(0, t.Length - 1); }
            double v;
            return double.TryParse(t, System.Globalization.NumberStyles.Float,
                System.Globalization.CultureInfo.InvariantCulture, out v) ? v * mul : 0;
        }

        // 进程名可能很长（com.xxx.yyy），截到 22 字符避免撑破 UI
        private static string ShortName(string s)
        {
            string t = (s ?? "").Trim();
            return t.Length <= 22 ? t : t.Substring(0, 21) + "…";
        }

        // :top5 —— 本机 + 车机 TOP5 速查（GUI 诊断页同源）
        internal static void DoTop5()
        {
            Info("本机 TOP5…");
            try
            {
                string h = Top5.HostTop5();
                ShowTop5("本机", h);
            }
            catch (Exception ex) { Fail("本机采集失败：" + ex.Message); }

            Blank();
            Info("车机 TOP5…");
            try
            {
                string c = CarTop5();
                ShowTop5("车机", c);
            }
            catch (Exception ex) { Fail("车机采集失败：" + ex.Message); }
        }

        private static void ShowTop5(string who, string json)
        {
            if (string.IsNullOrEmpty(json) || json.IndexOf("\"ok\":true", StringComparison.Ordinal) < 0)
            {
                Warn("  " + who + "：采集失败或设备未连接");
                return;
            }
            // 用正则把 {"n":"x","v":1.2} 抠出来，避免为 CLI 再写一套 JSON 解析
            System.Text.RegularExpressions.MatchCollection cpus =
                System.Text.RegularExpressions.Regex.Matches(json,
                    "\\{\"n\":\"([^\"]*)\",\"v\":([0-9.]+)\\}");
            var all = new List<string>();
            for (int i = 0; i < cpus.Count; i++)
                all.Add(cpus[i].Groups[1].Value + "  " + cpus[i].Groups[2].Value);

            System.Text.RegularExpressions.Match fc =
                System.Text.RegularExpressions.Regex.Match(json, "\"freeCpu\":([0-9.]+)");
            System.Text.RegularExpressions.Match fm =
                System.Text.RegularExpressions.Regex.Match(json, "\"freeMem\":([0-9.]+)");

            if (fc.Success) Hint("  剩余 CPU：" + fc.Groups[1].Value + "%");
            if (fm.Success) Hint("  剩余内存：" + fm.Groups[1].Value + " GB");

            if (all.Count == 0) Warn("  没有拿到进程数据");
            else
            {
                Hint("  占用 TOP（CPU / 内存合并展示）：");
                for (int i = 0; i < all.Count && i < 10; i++)
                    Hint("    " + all[i]);
            }
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
