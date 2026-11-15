// ============================================================================
//  Send.cs — 中文文本 → ADB 意图发送（融合进主工具）
//  与 Program.cs 通过 partial class App 合并编译
//
//  输入入口（在 Program.cs 的 Dispatch 里调用）：
//     send <文本>       显式发送
//     send 1 ~ send 9   发送常用语（纯数字=编号，send "1" 强制当文本）
//     send -f <路径>    批量发送 txt（也支持 b 交互式进入）
//     <纯中文裸输入>     走启发式直接发送
//
//  与 bat 版的关键差别：
//    1) URL 编码用 Uri.EscapeDataString，不再起 PowerShell（快一个量级）
//    2) 批量发送合并进单个 shell 会话 —— 100 条从 ~100 次进程调用降到 ~5 次
//       采用"乐观批量 + 悲观回退"：整批成功就过；整批有错才逐条重发定位
//    3) 失败清单落盘 send_failed.txt，100 条里失败 3 条能立刻知道是哪 3 条
//    4) am 子命令与组件可配置，直接根治 Android 8+ 后台限制 / scheme 未匹配
// ============================================================================
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

namespace AdbLogExport
{
    internal static partial class App
    {
        // ==================== 一、发送入口 ====================
        private static void DoSend(string argRaw)
        {
            string t = (argRaw == null) ? "" : argRaw.Trim();
            if (t.Length == 0) { SendUsage(); return; }

            // send -f <路径>：批量
            if (t.Length >= 2 && t.Substring(0, 2) == "-f")
            {
                string rest = t.Substring(2).Trim();
                BatchMode(rest);
                return;
            }

            // send 1 ~ 9：常用语（要求"纯数字且没被引号包裹"，这样 send "1" 能强制发文本 1）
            string unq = Unquote(t);
            if (unq.Length == 1 && unq[0] >= '1' && unq[0] <= '9' && string.Equals(unq, t, StringComparison.Ordinal))
            {
                int idx = unq[0] - '0';
                string q = QUICK[idx];
                if (string.IsNullOrEmpty(q))
                {
                    Console.WriteLine("  [!] 该编号的常用语未配置（在 ini 里填 quick_" + idx + "）");
                    return;
                }
                SendText(q);
                return;
            }

            SendText(unq);
        }

        private static void SendUsage()
        {
            Console.WriteLine("  用法：:send <文本>         发送一条");
            Console.WriteLine("        :send 1 ~ 9         发送常用语（ini 的 quick_1~9）");
            Console.WriteLine("        :send -f <txt路径>  批量发送");
            Console.WriteLine("        :send \"1\"           发送文本 1（引号强制当文本）");
            Console.WriteLine("        也可以直接输入中文，例如：你好");
        }

        // ==================== 二、单条发送（带重试 + 着色结果）====================
        private static void SendText(string text)
        {
            if (string.IsNullOrEmpty(text)) return;
            string enc = Util.EscapeData(text);
            string errMsg;
            string tip;
            bool ok = SendOnce(enc, out errMsg, out tip);
            if (ok)
            {
                // 发送成功说明设备必然在线，省掉下一轮 devices 探测
                CMD_OK = true;
                Ok("发送成功：" + Clip(text, 40));
            }
            else
            {
                CMD_OK = false;
                Fail("发送失败：" + errMsg);
                if (!string.IsNullOrEmpty(tip)) Hint("建议：" + tip);
            }
        }

        // ==================== 三、构造 am 命令 ====================
        // 生成一条设备端命令，URL 用单引号包住，避免 shell 对 ? & 等做解析
        private static string BuildAmCmd(string enc)
        {
            StringBuilder sb = new StringBuilder();
            sb.Append("am ");
            sb.Append(AM_CMD);
            if (!string.IsNullOrEmpty(COMPONENT))
            {
                sb.Append(" -n ");
                sb.Append(COMPONENT);
            }
            sb.Append(" -a ");
            sb.Append(ACTION);
            sb.Append(" -d '");
            sb.Append(URI_PREFIX);
            sb.Append(enc);
            sb.Append('\'');
            return sb.ToString();
        }

        // ==================== 四、单条执行（含重试）====================
        // 返回是否成功；失败时填 errMsg（错误行）与 tip（处置建议）
        private static bool SendOnce(string enc, out string errMsg, out string tip)
        {
            errMsg = "";
            tip = "";
            int attempt = 0;
            string stdout = "";
            string stderr = "";
            int rc = 0;

            while (true)
            {
                attempt++;
                rc = AdbCall(new List<string> { "shell", BuildAmCmd(enc) }, out stdout, out stderr);

                string combined = stdout + "\n" + stderr;
                if (rc == 0 && !LooksLikeError(combined)) return true;

                // 失败：未超过重试次数就等一会儿再试
                if (attempt <= RETRY)
                {
                    System.Threading.Thread.Sleep(1200);
                    continue;
                }

                errMsg = BuildErrMsg(combined);
                tip = BuildTip(combined);
                return false;
            }
        }

        // ==================== 五、批量模式 ====================
        private static void BatchMode(string givenPath)
        {
            string path = givenPath;

            if (string.IsNullOrEmpty(path))
            {
                Console.WriteLine();
                Console.WriteLine("  [批量] 把 txt 文件直接拖进窗口，或输入完整路径（输入 q 取消）");
                Console.Write("  路径 → ");
                string l = Console.ReadLine();
                if (l == null) return;
                path = l.Trim();
                if (path.Length == 0) return;
            }

            path = Unquote(path);
            if (string.Equals(path, "q", StringComparison.OrdinalIgnoreCase)) { Info("已取消批量"); return; }

            if (!File.Exists(path))
            {
                Console.WriteLine("  [!] 文件不存在，请检查路径");
                return;
            }

            byte[] bytes;
            try { bytes = File.ReadAllBytes(path); }
            catch (Exception ex)
            {
                Console.WriteLine("  [!] 读取文件失败：" + ex.Message);
                return;
            }

            // 自动识别编码：BOM / UTF-8 / GBK 都能直接读
            string content = Util.DecodeText(bytes);

            // 按行拆分，跳过空行
            List<string> items = new List<string>();
            string[] rawLines = content.Replace("\r\n", "\n").Replace('\r', '\n').Split('\n');
            for (int i = 0; i < rawLines.Length; i++)
            {
                string l = rawLines[i].Trim();
                if (l.Length > 0) items.Add(l);
            }

            if (items.Count == 0)
            {
                Console.WriteLine("  [!] 文件里没有可发送的内容（空行会被自动跳过）");
                return;
            }

            Console.WriteLine("  共 " + items.Count + " 条待发送");
            Console.WriteLine("  目标：" + URI_PREFIX + "   动作：" + AM_CMD);
            Console.WriteLine("  直接回车开始，输入 n 取消");
            Console.Write("  ");
            string confirm = Console.ReadLine();
            if (confirm != null && string.Equals(confirm.Trim(), "n", StringComparison.OrdinalIgnoreCase))
            {
                Info("已取消批量");
                return;
            }

            RunBatch(items);
        }

        // 分批合并 + 乐观批量 + 悲观回退
        // Windows 命令行上限 8191 字符，这里按 6000 留余量，一批约 15~40 条
        private const int CMD_BUDGET = 6000;

        private static void RunBatch(List<string> items)
        {
            int ok = 0;
            int ng = 0;
            List<int> failIdx = new List<int>();
            List<string> failTxt = new List<string>();
            bool aborted = false;

            Console.WriteLine();
            Progress("发送中", 0, items.Count);

            int i = 0;
            while (i < items.Count && !aborted)
            {
                // ---- 组批：把尽量多的 am 命令用 ; 连成一条 shell 命令 ----
                List<int> batch = new List<int>();
                StringBuilder cmd = new StringBuilder();
                while (i < items.Count)
                {
                    string encOne = Util.EscapeData(items[i]);
                    string one = BuildAmCmd(encOne);
                    if (cmd.Length > 0 && cmd.Length + one.Length + 2 > CMD_BUDGET) break;
                    if (cmd.Length > 0) cmd.Append("; ");
                    cmd.Append(one);
                    batch.Add(i);
                    i++;
                }

                if (batch.Count == 0) break;

                // ---- 快路径：整批一次执行 ----
                string so = "";
                string se = "";
                int rc = AdbCall(new List<string> { "shell", cmd.ToString() }, out so, out se);
                string combined = so + "\n" + se;

                if (rc == 0 && !LooksLikeError(combined))
                {
                    ok += batch.Count;
                    Progress("发送中", ok + ng, items.Count);
                    continue;
                }

                // ---- 慢路径：这一批有问题，逐条重发以精确定位 ----
                for (int k = 0; k < batch.Count; k++)
                {
                    if (aborted) break;
                    int idx = batch[k];

                    string encOne = Util.EscapeData(items[idx]);
                    string errMsg;
                    string tip;
                    bool r = SendOnce(encOne, out errMsg, out tip);

                    if (r)
                    {
                        ok++;
                    }
                    else
                    {
                        ng++;
                        failIdx.Add(idx + 1);
                        failTxt.Add(items[idx]);
                        if (BATCH_STOP_ON_ERROR)
                        {
                            aborted = true;
                            Progress("发送中", ok + ng, items.Count);
                            ProgressEnd();
                            Info("已按配置在首个失败处停止（batch_stop_on_error=1）");
                            break;
                        }
                    }
                    Progress("发送中", ok + ng, items.Count);
                }
            }

            ProgressEnd();
            Console.WriteLine();

            // ---- 结果汇总 ----
            if (ng == 0)
            {
                CMD_OK = true;
                Ok("全部成功（" + ok + " 条）");
                return;
            }

            CMD_OK = false;
            Fail("完成：成功 " + ok + " 条，失败 " + ng + " 条");
            if (failIdx.Count > 0) Hint("首个失败：第 " + failIdx[0] + " 条 - " + Clip(failTxt[0], 40));

            // ---- 失败清单落盘，方便改完再发一次 ----
            string fp = Path.Combine(ExeDir(), "send_failed.txt");
            try
            {
                StringBuilder sb = new StringBuilder();
                sb.Append("# 发送失败清单  共 ").Append(ng).Append(" 条\r\n");
                sb.Append("# 生成时间：").Append(DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss")).Append("\r\n");
                sb.Append("# 修好下面内容后，可用 send -f 直接重发（这 3 行 # 注释不会发送）\r\n");
                for (int k = 0; k < failTxt.Count; k++)
                {
                    sb.Append(failTxt[k]).Append("\r\n");
                }
                File.WriteAllText(fp, sb.ToString(), new UTF8Encoding(false));
                Hint("失败清单已写入：" + fp);
            }
            catch (Exception ex)
            {
                Hint("失败清单写入失败：" + ex.Message);
            }
        }

        // ==================== 六、错误诊断 ====================
        // 判断输出是否包含错误特征
        private static bool LooksLikeError(string output)
        {
            if (string.IsNullOrEmpty(output)) return false;
            string low = output.ToLowerInvariant();
            string[] marks = new string[]
            {
                "error", "exception", "not allowed", "does not exist",
                "permission denial", "unable to resolve"
            };
            for (int i = 0; i < marks.Length; i++)
            {
                if (low.IndexOf(marks[i], StringComparison.OrdinalIgnoreCase) >= 0) return true;
            }
            return false;
        }

        // 从输出中提取首条错误行（去掉引号，截断到 80 字符）
        private static string BuildErrMsg(string output)
        {
            if (string.IsNullOrEmpty(output)) return "设备无返回信息";
            string[] lines = output.Split('\n');
            string[] marks = new string[] { "Error", "Exception", "not allowed", "offline", "unauthorized", "unable to resolve" };

            for (int i = 0; i < lines.Length; i++)
            {
                string l = lines[i].TrimEnd('\r').Trim();
                if (l.Length == 0) continue;
                for (int j = 0; j < marks.Length; j++)
                {
                    if (l.IndexOf(marks[j], StringComparison.OrdinalIgnoreCase) >= 0)
                        return Clip(l.Replace("\"", ""), 80);
                }
            }
            // 兜底：取第一条非空行
            for (int i = 0; i < lines.Length; i++)
            {
                string l = lines[i].TrimEnd('\r').Trim();
                if (l.Length > 0) return Clip(l.Replace("\"", ""), 80);
            }
            return "设备无返回信息";
        }

        // 根据错误特征给出中文处置建议
        // 原 bat 版只"提示"这些情况，这里配合 am_cmd / component 配置可直接根治
        private static string BuildTip(string output)
        {
            if (string.IsNullOrEmpty(output)) return "";
            string low = output.ToLowerInvariant();

            if (low.IndexOf("not allowed to start service", StringComparison.OrdinalIgnoreCase) >= 0 ||
                low.IndexOf("background start not allowed", StringComparison.OrdinalIgnoreCase) >= 0)
                return "Android 8+ 后台服务限制：把 ini 的 am_cmd 改成 start-foreground-service，或让 App 保持前台";
            if (low.IndexOf("activity not started", StringComparison.OrdinalIgnoreCase) >= 0 ||
                low.IndexOf("unable to resolve intent", StringComparison.OrdinalIgnoreCase) >= 0)
                return "未匹配到 intent-filter：在 ini 的 component 填 包名/.服务名（如 com.x/.SendSvc），或确认 App 已安装";
            if (low.IndexOf("device offline", StringComparison.OrdinalIgnoreCase) >= 0)
                return "设备离线，请检查数据线与 USB 连接，或输入 r 刷新";
            if (low.IndexOf("unauthorized", StringComparison.OrdinalIgnoreCase) >= 0)
                return "设备未授权，请在手机弹窗中点允许 USB 调试";
            if (low.IndexOf("no devices", StringComparison.OrdinalIgnoreCase) >= 0 ||
                low.IndexOf("more than one device", StringComparison.OrdinalIgnoreCase) >= 0)
                return "设备数量异常，请执行 adb devices 检查；多设备时在 ini 填 serial";
            if (low.IndexOf("device not found", StringComparison.OrdinalIgnoreCase) >= 0 ||
                low.IndexOf("error: closed", StringComparison.OrdinalIgnoreCase) >= 0)
                return "设备连接中断：输入 r 刷新，或 rl 重试上次操作";
            // 高频错误：把 Windows 命令当设备命令用（findstr / find / dir / type）
            if (low.IndexOf("inaccessible or not found", StringComparison.OrdinalIgnoreCase) >= 0 ||
                low.IndexOf("command not found", StringComparison.OrdinalIgnoreCase) >= 0 ||
                low.IndexOf(": not found", StringComparison.OrdinalIgnoreCase) >= 0)
                return "设备上没有这个命令：检查拼写；findstr / find / dir / type 是 Windows 命令，设备上对应 grep / find / ls / cat";
            if (low.IndexOf("permission denial", StringComparison.OrdinalIgnoreCase) >= 0)
                return "权限不足：该服务可能需要 root 或系统签名，请确认 App 的权限声明";
            return "";
        }

        // 截断显示（避免切在代理对中间导致乱码）
        private static string Clip(string s, int max)
        {
            if (s == null) return "";
            if (s.Length <= max) return s;
            int n = max;
            if (n > 0 && char.IsHighSurrogate(s[n - 1])) n--;
            return s.Substring(0, n) + "…";
        }
    }
}
