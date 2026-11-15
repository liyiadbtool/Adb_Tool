// ============================================================================
//  Env.cs — 环境切换与查询
//
//  场景：座舱项目有多套服务端环境（test / pre / dev），切换靠改系统的
//  persist.sys.autofly.web.* 属性。手敲三条 setprop 容易漏、也看不出是否生效。
//
//  设计：
//    · 三个属性名与各环境的取值全部放 ini，换项目只改配置不动代码
//    · 切换后**立即 getprop 回读校验**，逐条比对设置值与实际值，
//      而不是"假设 setprop 成功了"
//    · 一次 shell 调用完成 3 条 setprop + 3 条校验，只走 1 次 adb 往返
//
//  命令：
//    test / pre / dev   切到对应环境
//    syncore            查询当前值，并自动识别属于哪套环境
//    !test              设备 shell 自带的 test 命令（工具里的 test 被环境切换占用）
// ============================================================================
using System;
using System.Collections.Generic;
using System.Text;

namespace AdbLogExport
{
    internal static partial class App
    {
        // 三个属性名（ini 可覆盖）
        internal static string ENV_P_DEPLOY = "persist.sys.autofly.web.deploy";
        internal static string ENV_P_HTTPS = "persist.sys.autofly.web.https";
        internal static string ENV_P_DOMAIN = "persist.sys.autofly.web.domain";

        internal class EnvProfile
        {
            internal string Name = "";
            internal string Deploy = "";
            internal string Https = "";
            internal string Domain = "";
        }

        private static readonly List<EnvProfile> ENVS = new List<EnvProfile>();
        private static bool ENV_DEFAULTED = false;

        // ==================== 配置 ====================
        // 内置默认值，保证不改 ini 也能用；ini 里的同名配置会覆盖
        internal static void InitDefaultEnvs()
        {
            if (ENV_DEFAULTED) return;
            ENV_DEFAULTED = true;

            AddEnv("test", "test", "api-test.syncore.space:20443", "api-test.syncore.space:20443");
            AddEnv("pre", "pre", "api-pre.syncore.space:20443", "api-pre.syncore.space:20443");
            AddEnv("dev", "dev", "api.syncore.space", "api.syncore.space");
        }

        private static void AddEnv(string name, string deploy, string https, string domain)
        {
            EnvProfile p = new EnvProfile();
            p.Name = name;
            p.Deploy = deploy;
            p.Https = https;
            p.Domain = domain;

            for (int i = 0; i < ENVS.Count; i++)
            {
                if (string.Equals(ENVS[i].Name, name, StringComparison.OrdinalIgnoreCase))
                {
                    ENVS[i] = p;
                    return;
                }
            }
            ENVS.Add(p);
        }

        // ini: env_test=deploy值;https值;domain值
        internal static void LoadEnvProfile(string name, string v)
        {
            InitDefaultEnvs();
            if (string.IsNullOrEmpty(v)) return;

            string[] parts = v.Split(';');
            string deploy = (parts.Length > 0) ? parts[0].Trim() : "";
            string https = (parts.Length > 1) ? parts[1].Trim() : "";
            string domain = (parts.Length > 2) ? parts[2].Trim() : "";

            AddEnv(name, deploy, https, domain);
        }

        private static EnvProfile FindEnv(string name)
        {
            InitDefaultEnvs();
            for (int i = 0; i < ENVS.Count; i++)
            {
                if (string.Equals(ENVS[i].Name, name, StringComparison.OrdinalIgnoreCase)) return ENVS[i];
            }
            return null;
        }

        private static string[] EnvProps()
        {
            return new string[] { ENV_P_DEPLOY, ENV_P_HTTPS, ENV_P_DOMAIN };
        }

        // ==================== 切换 ====================
        internal static void DoEnvSwitch(string name)
        {
            if (OFFLINE)
            {
                Warn("设备未连接，无法切换环境");
                Hint("输入 r 重连");
                return;
            }

            EnvProfile p = FindEnv(name);
            if (p == null)
            {
                Fail("没有配置环境：" + name);
                Hint("在 ini 里写 env_" + name + "=deploy值;https值;domain值");
                return;
            }

            Echo("env", "切换到 " + name + " 环境");

            string[] props = EnvProps();
            string[] vals = new string[] { p.Deploy, p.Https, p.Domain };

            // 一次调用：3 条 setprop + 3 条分段 getprop 校验
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < props.Length; i++)
            {
                sb.Append("setprop '").Append(props[i]).Append("' '").Append(vals[i]).Append("'; ");
            }
            for (int i = 0; i < props.Length; i++)
            {
                sb.Append("echo '##").Append(i + 1).Append("'; getprop '").Append(props[i]).Append("'; ");
            }

            string o = "";
            string e = "";
            ShellCall(CUR, sb.ToString(), out o, out e);

            string[] actual = ParseMarked(o + "\n" + e, props.Length);

            RenderEnvResult(true, name, props, vals, actual);
            CMD_OK = true;
        }

        // ==================== 查询 ====================
        internal static void DoEnvQuery()
        {
            if (OFFLINE)
            {
                Warn("设备未连接，无法查询环境");
                Hint("输入 r 重连");
                return;
            }

            InitDefaultEnvs();

            Echo("env", "查询环境属性");

            string[] props = EnvProps();

            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < props.Length; i++)
            {
                sb.Append("echo '##").Append(i + 1).Append("'; getprop '").Append(props[i]).Append("'; ");
            }

            string o = "";
            string e = "";
            ShellCall(CUR, sb.ToString(), out o, out e);

            string[] actual = ParseMarked(o + "\n" + e, props.Length);

            // 自动识别属于哪套环境
            string matched = MatchEnv(actual);

            RenderEnvResult(false, matched, props, null, actual);
            CMD_OK = true;
        }

        // 三个值全部吻合才算匹配
        private static string MatchEnv(string[] actual)
        {
            for (int i = 0; i < ENVS.Count; i++)
            {
                EnvProfile p = ENVS[i];
                if (string.Equals(actual[0], p.Deploy, StringComparison.Ordinal) &&
                    string.Equals(actual[1], p.Https, StringComparison.Ordinal) &&
                    string.Equals(actual[2], p.Domain, StringComparison.Ordinal))
                {
                    return p.Name;
                }
            }
            return "";
        }

        // 按 ##1 ##2 ##3 分段取第一条非空内容（getprop 无值时是空行）
        private static string[] ParseMarked(string text, int n)
        {
            string[] r = new string[n];
            for (int i = 0; i < n; i++) r[i] = "";

            if (string.IsNullOrEmpty(text)) return r;

            string[] lines = text.Split('\n');
            int cur = -1;

            for (int i = 0; i < lines.Length; i++)
            {
                string t = lines[i].TrimEnd('\r').Trim();
                if (t.Length == 0) continue;

                if (t.Length >= 2 && t[0] == '#' && t[1] == '#')
                {
                    int idx = 0;
                    if (int.TryParse(t.Substring(2), out idx)) cur = idx - 1;
                    continue;
                }

                if (cur >= 0 && cur < n && r[cur].Length == 0) r[cur] = t;
            }
            return r;
        }

        // ==================== 渲染 ====================
        // isSwitch=true  : 显示"设置值"并逐条比对
        // isSwitch=false : 只显示当前值，并报出识别到的环境
        private static void RenderEnvResult(bool isSwitch, string envName, string[] props, string[] expected, string[] actual)
        {
            const int GAP = 2;

            Console.WriteLine();

            if (isSwitch)
            {
                W("  切换到 ", ConsoleColor.Yellow);
                W(envName, ConsoleColor.Yellow);
                W(" 环境", ConsoleColor.Yellow);
                UseDefault();
                Console.WriteLine();
            }
            else
            {
                W("  当前环境", ConsoleColor.Yellow);
                UseDefault();
                if (envName.Length > 0)
                {
                    Console.Write("：");
                    W(envName, ConsoleColor.Green);
                }
                else
                {
                    UseDim();
                    Console.Write("：未知（不匹配任何已配置环境）");
                    UseDefault();
                }
                Console.WriteLine();
            }
            Console.WriteLine();

            // 列宽
            int wProp = DispWidth("属性");
            int wVal = DispWidth("当前值");
            for (int i = 0; i < props.Length; i++)
            {
                int a = DispWidth(props[i]);
                int b = DispWidth(actual[i]);
                if (a > wProp) wProp = a;
                if (b > wVal) wVal = b;
            }
            if (wProp > 38) wProp = 38;
            if (wVal > 34) wVal = 34;

            // 表头
            StringBuilder head = new StringBuilder("  ");
            head.Append(PadRight("属性", wProp)).Append(new string(' ', GAP));
            head.Append(PadRight(isSwitch ? "当前值" : "值", wVal));
            if (isSwitch) head.Append(new string(' ', GAP)).Append("结果");

            UseDim();
            Console.WriteLine(head.ToString());
            Console.WriteLine("  " + new string('-', DispWidth(head.ToString())));
            UseDefault();

            int ok = 0;
            int bad = 0;

            for (int i = 0; i < props.Length; i++)
            {
                StringBuilder line = new StringBuilder("  ");
                line.Append(PadRight(FitWidth(props[i], wProp), wProp)).Append(new string(' ', GAP));

                bool good = true;
                if (isSwitch && expected != null)
                    good = string.Equals(actual[i], expected[i], StringComparison.Ordinal);

                if (good)
                {
                    ok++;
                    Console.Write(line.ToString());
                    UseOk();
                    Console.Write(PadRight(FitWidth(actual[i], wVal), wVal));
                    UseDefault();
                    if (isSwitch)
                    {
                        Console.Write(new string(' ', GAP));
                        UseOk();
                        Console.Write("\u221A");   // √
                        UseDefault();
                    }
                }
                else
                {
                    bad++;
                    Console.Write(line.ToString());
                    UseErr();
                    Console.Write(PadRight(FitWidth(actual[i].Length == 0 ? "(空)" : actual[i], wVal), wVal));
                    if (isSwitch)
                    {
                        Console.Write(new string(' ', GAP));
                        Console.Write("\u00D7 期望 " + FitWidth(expected[i], 28));
                    }
                    UseDefault();
                }
                Console.WriteLine();
            }

            Console.WriteLine();

            if (isSwitch)
            {
                if (bad == 0)
                    Ok("3 个属性全部生效（部分服务需重启后才读取新值）");
                else
                    Warn(ok + "/" + props.Length + " 生效，" + bad + " 个不符 —— 可能被设备策略锁定，或属性名写错");
            }
            else
            {
                if (envName.Length > 0)
                    Ok("环境识别：" + envName);
                else
                    Hint("对比 ini 里的 env_test / env_pre / env_dev 可确认是否被改动");
            }
        }
    }
}
