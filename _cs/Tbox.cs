// ============================================================================
//  Tbox.cs — TBOX 环境切换（正式 / 预发布）
//
//  参考脚本：Downloads\正式环境.bat / 预发布环境.bat
//  原理：往 /dev/mcu_spi 依次写 15 帧二进制，末帧触发 MCU 重启。
//
//  帧结构（从脚本反读）：
//      05 75 23 <len> 00 <cmd> <sub> <dataLen> <data...>
//        帧头              命令   子命令 字段长度
//     · 端口帧末尾是大端端口号：86 76→0x21E4=8676、6588→0x19BC
//     · 域名帧 dataLen=0x32=50：域名 ASCII + 右补 0 到 50 字节
//
//  安全：
//    · 不带 yes 只做 dry-run（打印两套环境的域名/端口 + 帧数），不写设备
//    · 写之前校验 root（该节点普通用户写不进去）
//    · 末帧会重启车机，提示"设备将断开 10~60 秒"
// ============================================================================
using System;
using System.Collections.Generic;
using System.Text;

namespace AdbLogExport
{
    internal static partial class App
    {
        // ---------------- 帧表 ----------------

        // ---- 正式环境 15 帧（顺序与 `Downloads\正式环境.bat` 完全一致）----
        // 由 _gen_tbox_frames.py 从 bat 直接提取，未手抄。
        private static readonly string[] FRAMES_PROD = new string[]
        {
            "0575233600EF0D326D7174742D7075626C69632D6163636573732E6761636963762E636F6D000000000000000000000000000000000000000000",   // Public Tsp Domain mqtt-public-access.gacicv.com
            "0575230C00EF0E0800000000000019BC",   // Public Tsp Port 8676
            "0575233600EF00326D7174742D707269766174652D6163636573732E6761636963762E636F6D0000000000000000000000000000000000000000",   // Private Tsp Domain mqtt-private-access.gacicv.com
            "0575230C00EF0B0800000000000021E4",   // Private Tsp Port 6588
            "0575230C00F80E083132343433000000",   // PKI端口号 12443
            "0575233600F80D32636D732D736D2D6163636573732E6761636963762E636F6D0000000000000000000000000000000000000000000000000000",   // PKI域名 cms-sm-access.gacicv.com
            "0575231200EF030E3130303030000000000000000000",   // ECall电话 10000
            "0575231200EF040E3130303030000000000000000000",   // BCall电话 10000
            "0575232400EF052061696F6E356730312E67642E696F740000000000000000000000000000000000",   // APN1接入点 aion5g01.gd.iot
            "0575232400EF0720676163322E6374696F7400000000000000000000000000000000000000000000",   // APN2接入点 gac2.ctiot
            "0575232400EF0920676163332E6374696F7400000000000000000000000000000000000000000000",   // APN3接入点 gac3.ctiot
            "0575230500EF060100",   // APN1类型 0
            "0575230500EF080101",   // APN2类型 1
            "0575230500EF0A0102",   // APN3类型 2
            "05550203000101",   // Reboot
        };

        // ---- 预发布只替换这 3 帧，其余逐字节相同 ----
        // 差异：Public TSP / Private TSP / PKI 三处域名多了 pre- 前缀
        private static readonly int[] PRE_DIFF_IDX = new int[] { 0, 2, 5 };
        private static readonly string[] PRE_DIFF_VAL = new string[]
        {
            "0575233600EF0D327072652D6D7174742D7075626C69632D6163636573732E6761636963762E636F6D0000000000000000000000000000000000",   // Public Tsp Domain mqtt-public-access.gacicv.com
            "0575233600EF00327072652D6D7174742D707269766174652D6163636573732E6761636963762E636F6D00000000000000000000000000000000",   // Private Tsp Domain mqtt-private-access.gacicv.com
            "0575233600F80D327072652D736D2D636D732E6761636963762E636F6D0000000000000000000000000000000000000000000000000000000000",   // PKI域名 cms-sm-access.gacicv.com
        };

        /// <summary>取某一套环境的 15 帧（pre=true 时套用 3 处域名差异）。</summary>
        internal static string[] TboxFrames(bool pre)
        {
            string[] f = (string[])FRAMES_PROD.Clone();
            if (!pre) return f;
            for (int i = 0; i < PRE_DIFF_IDX.Length; i++)
                f[PRE_DIFF_IDX[i]] = PRE_DIFF_VAL[i];
            return f;
        }

        /// <summary>把 hex 串转成 shell 的 \xNN 转义写法（与 bat 一致，设备端 echo 能还原）。</summary>
        internal static string HexToEscaped(string hex)
        {
            StringBuilder sb = new StringBuilder(hex.Length * 2);
            for (int i = 0; i + 1 < hex.Length; i += 2)
                sb.Append("\\x").Append(hex.Substring(i, 2));
            return sb.ToString();
        }

        /// <summary>
        /// 从帧里取出可读文本（域名帧），用于 dry-run 展示。
        /// 数据区固定从第 9 个字节开始：帧头(05 75 23)+长度 后是 00 + 命令 + 子命令 + 字段长度，
        /// 即 4+1+1+1+1 = 8 字节，所以下标 8 是第一个数据字节。
        /// 端口帧这里会是二进制，取不满 4 个可读字符就返回空串（不展示）。
        /// </summary>
        internal static string FrameAscii(string hex)
        {
            if (hex == null || hex.Length < 20) return "";
            StringBuilder sb = new StringBuilder();
            for (int i = 16; i + 1 < hex.Length; i += 2)   // 16 = 第 9 个字节的字符下标
            {
                int v = Convert.ToInt32(hex.Substring(i, 2), 16);
                if (v >= 32 && v < 127) sb.Append((char)v);
                else break;
            }
            return sb.Length >= 4 ? sb.ToString() : "";
        }

        // ---------------- 入口 ----------------

        // :tbosprod yes / :tbospre yes / :tboschek
        internal static void DoTbox(bool pre, string argRaw)
        {
            bool go = string.Equals((argRaw ?? "").Trim(), "yes", StringComparison.OrdinalIgnoreCase);
            string env = pre ? "预发布" : "正式";
            string[] frames = TboxFrames(pre);

            if (!go)
            {
                Echo("plan", "TBOX " + env + "环境（dry-run）");
                Console.WriteLine("  帧数：" + frames.Length + "（末帧 = 重启 MCU）");
                string[] names = TboxFrameNames();
                for (int i = 0; i < frames.Length; i++)
                {
                    string ascii = FrameAscii(frames[i]);
                    Console.WriteLine("    " + (i + 1).ToString().PadLeft(2) + ". "
                        + names[i] + (ascii.Length > 0 ? " = " + ascii : ""));
                }
                Warn("以上内容会写入 /dev/mcu_spi，写入后车机将重启");
                Hint("确认执行：:tbos" + (pre ? "pre" : "prod") + " yes");
                CMD_OK = false;
                return;
            }

            if (!RequireDevice("")) return;

            // 1) 必须 root：这条节点普通 shell 写不进去
            if (!TboxEnsureRoot()) return;

            // 2) 逐帧写入
            CMD_OK = true;
            for (int i = 0; i < frames.Length; i++)
            {
                string inner = "echo -n '" + HexToEscaped(frames[i]) + "' > /dev/mcu_spi";
                bool ok = ShellStep(inner, "写帧 " + (i + 1) + "/" + frames.Length);
                if (!ok) { CMD_OK = false; break; }
                if (i < frames.Length - 1) System.Threading.Thread.Sleep(60);
            }
            if (!CMD_OK)
            {
                Fail("写帧中断，TBOX 可能处于半切换状态");
                Hint("重新执行一次 :tbos" + (pre ? "pre" : "prod") + " yes 可覆盖为完整配置");
                return;
            }
            Ok("TBOX 已切到「" + env + "」环境");
            Warn("末帧已触发 MCU 重启，设备将断开 10~60 秒，工具会自动重连");
        }

        /// <summary>写 /dev/mcu_spi 前保证 root；失败返回 false。</summary>
        private static bool TboxEnsureRoot()
        {
            string id = ShellValue("id");
            if (id != null && id.IndexOf("uid=0", StringComparison.Ordinal) >= 0) return true;

            Echo("root", "提升权限（写 mcu_spi 需要 root）");
            string o = "", e = "";
            AdbCall(new List<string> { "root" }, out o, out e);
            if ((o + e).ToLowerInvariant().Contains("restarting adbd as root"))
                System.Threading.Thread.Sleep(1500);

            // 等设备重新上线（adbd 重启会短暂 offline）
            for (int t = 0; t < 10; t++)
            {
                string st = "", se = "";
                AdbCall(new List<string> { "get-state" }, out st, out se);
                if (st.Trim().ToLowerInvariant() == "device") break;
                System.Threading.Thread.Sleep(800);
            }
            id = ShellValue("id");
            if (id != null && id.IndexOf("uid=0", StringComparison.Ordinal) >= 0)
            {
                Ok("已获取 root");
                return true;
            }
            Fail("拿不到 root，写 /dev/mcu_spi 会失败");
            Hint("确认设备是 userdebug/eng 版本；或先手动 :root 再试");
            return false;
        }

        /// <summary>前 n 帧是否都以 prefix 开头（自检用）。</summary>
        internal static bool AllStartWith(string[] frames, string prefix, int n)
        {
            for (int i = 0; i < n && i < frames.Length; i++)
                if (frames[i] == null || !frames[i].StartsWith(prefix, StringComparison.Ordinal))
                    return false;
            return true;
        }

        /// <summary>帧的中文说明（dry-run 展示，顺序与 bat 注释一致）。</summary>
        internal static string[] TboxFrameNames()
        {
            return new string[]
            {
                "Public TSP 域名", "Public TSP 端口", "Private TSP 域名", "Private TSP 端口",
                "PKI 端口 12443", "PKI 域名", "ECall 电话", "BCall 电话",
                "APN1 接入点", "APN2 接入点", "APN3 接入点",
                "APN1 类型", "APN2 类型", "APN3 类型", "重启 MCU"
            };
        }
    }
}
