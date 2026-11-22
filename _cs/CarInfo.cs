// ============================================================================
//  CarInfo.cs - 车机信息统一查询（车型 / SOC / MCU / Android / VIN / UUID /
//              DID / OPENID / 分辨率）
//
//  为什么要单独一个文件：
//    这 9 项信息有三个使用场景，必须**同一份口径**，否则三处显示不一致：
//      1) 工具启动连上设备时，顶栏要显示（原来只取车型/SOC/分辨率）
//      2) 用户输入 r / :r 刷新时，要把 9 项全部重新取一遍并输出到界面
//      3) 快捷指令页「车机信息」按钮点一下，逐项输出
//    以前第 1 项在 Adb.LoadDeviceInfo 里硬编码 4 条 shell 拼接，
//    第 2、3 项还不存在。现在全部收敛到这里，Adb 和 Prefix 都调它。
//
//  性能设计：
//    9 个 getprop + 1 个 wm size，如果一条一条发就是 10 次 adb 往返
//    （每次约 80~150ms，累计 1 秒以上，界面明显卡顿）。
//    这里合并成**一次** adb shell，用 echo '##KEY' 做分隔标记，
//    再由 ParseMarkedText 切回来 —— 一次往返约 150ms。
//
//  getprop 取不到值的行为：
//    返回空行（不是 "not-found"）。所以解析后统一用 "-" 占位，
//    宁可显示 "-" 也不要显示一串空白让人以为工具坏了。
// ============================================================================
using System;
using System.Text;

namespace AdbLogExport
{
    internal static partial class App
    {
        // ---------------- 9 项车机信息 ----------------
        //
        // 字段顺序即输出顺序。key 是 getprop 属性名，也用作 shell 里的分段标记。
        internal static readonly string[] CAR_KEYS = new string[]
        {
            "sys.product.gacvehicleplatform",     // 车型值
            "ro.product.version.short_name",      // SOC 版本
            "sys.vehicle.mcu.version",            // MCU 版本
            "ro.build.version.release",           // Android 版本
            "persist.sys.vehicle.vin",            // VIN 码
            "persist.sys.navi.uuid",              // UUID
            "persist.sys.navi.did",               // DID
            "persist.sys.navi.openid"             // OPENID
        };

        internal static readonly string[] CAR_LABELS = new string[]
        {
            "车型",
            "SOC 版本",
            "MCU 版本",
            "Android 版本",
            "VIN 码",
            "UUID",
            "DID",
            "OPENID",
            // ---- 2026-11-22（第 18 批 D2）：新增四项 ----
            // ★ 必须追加在末尾：Adb.cs 里有 DEV_PLAT = CAR_VALS[0] /
            //   DEV_SOC = CAR_VALS[1] 这种按索引取的代码，插中间会错位。
            "芯片",
            "内存",
            "DDR 类型",
            "存储"
        };

        // 扩展项的取值命令（与 CAR_LABELS 末尾四项一一对应）。
        //
        // 为什么不用 getprop 逐一取：这四项都不是单一属性 ——
        //   芯片要 fallback（ro.soc.model 常常为空）、
        //   内存要算 /proc/meminfo、DDR 要 grep、存储要 df。
        // 所以单独给一段 shell 片段，结果同样用 ##N 标记分隔。
        internal static readonly string[] CAR_EXTRA_CMDS = new string[]
        {
            // 芯片：三个属性依次兜底
            "a=$(getprop ro.soc.model); b=$(getprop ro.board.platform); " +
            "c=$(getprop ro.hardware); " +
            "if [ -n \"$a\" ]; then echo \"$a\"; " +
            "elif [ -n \"$b\" ]; then echo \"$b\"; else echo \"$c\"; fi",

            // 内存：MemTotal（kB）→ GB，保留 1 位
            "awk '/^MemTotal:/{printf \"%.1f GB\", $2/1048576}' /proc/meminfo",

            // DDR 类型：各平台写法不统一，尽力 grep 一把。
            // 取不到就返回空串 —— 页面会**整行隐藏**（用户明确要求）。
            // 用 cut + tr 取值，不用 sed 的 \[ \] —— 那两个方括号在 C# 字符串里
            // 是非法转义（CS1009），要写成 \\[ 才行，可读性太差。
            "getprop 2>/dev/null | grep -iE 'ddr|dram|lpddr' | head -1 " +
            "| cut -d: -f2 | tr -d ' []'",

            // 存储：/data 的总量与可用量。
            // df 默认输出 1K-blocks，除以 1048576 换成 GB，直接可读。
            "df /data 2>/dev/null | tail -1 " +
            "| awk '{printf \"%.1f GB / 可用 %.1f GB\", $2/1048576, $4/1048576}'"
        };

        // 第 9 项单独处理（不是 getprop，是 wm size）
        internal const string CAR_RES_LABEL = "屏幕分辨率";

        // 最近一次取到的值。前 CAR_KEYS.Length 项与 CAR_KEYS 对齐，
        // 后面追加 CAR_EXTRA_CMDS.Length 项（芯片/内存/DDR/存储）。
        internal static string[] CAR_VALS = NewEmptyVals();

        // 分辨率缓存（与 DEV_RES 同步，保留 DEV_RES 是为了不破坏既有引用）
        internal static string CAR_RES = "";

        // 总项数：getprop 项 + 扩展项
        internal static int CAR_TOTAL
        {
            get { return CAR_KEYS.Length + CAR_EXTRA_CMDS.Length; }
        }

        private static string[] NewEmptyVals()
        {
            string[] a = new string[CAR_TOTAL];
            for (int i = 0; i < a.Length; i++) a[i] = "";
            return a;
        }

        // ---------------- 采集 ----------------

        // 一次 shell 往返取回全部 9 项。成功返回 true 并填好 CAR_VALS / CAR_RES。
        //
        // 为什么用 `getprop <key>` 而不是 `getprop | grep`：
        //   · 逐个 key 取值，输出顺序稳定，不依赖 grep 的匹配顺序；
        //   · 属性不存在时输出空行，不会像 grep 那样整行消失导致分段错位；
        //   · 不需要再拼正则，避免属性名里 '.' 被当通配符。
        internal static bool LoadCarInfo()
        {
            CAR_VALS = NewEmptyVals();
            CAR_RES = "";

            if (OFFLINE || DEVN == 0) return false;

            // 拼一条 shell：每个 key 前先 echo 一个标记行，后面紧跟取值。
            // 用 '##i'（数字下标）而不是 '##属性名' 做标记，避免属性名里的
            // 点号、长短不一带来的解析歧义，切分时只认下标。
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < CAR_KEYS.Length; i++)
            {
                sb.Append("echo '##").Append(i).Append("'; ");
                sb.Append("getprop ").Append(CAR_KEYS[i]).Append("; ");
            }
            // 分辨率：wm size 可能有多行（Physical + Override），
            // 用 tr 压成 ';' 分隔，否则只取到第一行，Override 生效值会被丢。
            // ---- 2026-11-22（第 18 批 D2）：扩展项（芯片/内存/DDR/存储）----
            //
            // ★ 每条命令后面必须补一个 `echo` 强制换行。
            //   原因：这几条命令有的**不带末尾换行**
            //   （awk 的 printf、df | awk、tr 这些输出完就停），
            //   下一条 `echo '##N'` 的标记会直接粘在值末尾，比如
            //     "5.8 GB##10"
            //   然后 ParseMarkedTextN 按标记切分就整体错位 ——
            //   表现为"内存显示成 5.8 GB##10、DDR 显示成 df 的输出"。
            for (int k = 0; k < CAR_EXTRA_CMDS.Length; k++)
            {
                sb.Append("echo '##").Append(CAR_KEYS.Length + k).Append("'; ");
                sb.Append(CAR_EXTRA_CMDS[k]).Append("; echo; ");
            }

            // 分辨率放在最后（原索引 = CAR_KEYS.Length，现在要顺延）
            sb.Append("echo '##").Append(CAR_TOTAL).Append("'; ");
            sb.Append("wm size 2>/dev/null | tr '\\n' ';'; ");

            string o = "";
            string e = "";
            int rc = ShellCall(CUR, sb.ToString(), out o, out e);
            string all = o + e;

            // 全部为空说明命令压根没跑通（断链/无权限），如实返回失败
            if (rc != 0 && all.Trim().Length == 0) return false;

            string[] parts = ParseMarkedTextN(all, CAR_TOTAL + 1);
            for (int i = 0; i < CAR_TOTAL; i++) CAR_VALS[i] = parts[i];
            CAR_RES = ParseWmSize(parts[CAR_TOTAL]);

            // 至少取到一个值才算成功（避免断链时"假成功"）
            bool any = CAR_RES.Length > 0;
            for (int i = 0; i < CAR_VALS.Length; i++)
                if (CAR_VALS[i].Length > 0) { any = true; break; }
            return any;
        }

        // 取某一项（按 key）。没取到返回 ""。
        internal static string CarVal(string key)
        {
            for (int i = 0; i < CAR_KEYS.Length; i++)
                if (CAR_KEYS[i] == key) return CAR_VALS[i];
            return "";
        }

        // ---------------- 输出 ----------------

        // 把 9 项按"标签 + 值"对齐输出。getProps 为 true 时带上取值的命令，
        // 方便用户复制到别处复现（:car cmd 用）。
        //
        // 对齐做法：标签按最长的那一项（"Android 版本" 12 字节宽，中文按 2 计）
        // 手动补空格。中文在等宽字体下占 2 格，所以要用显示宽度算，不能 len。
        internal static void RenderCarInfo(bool withCmd, bool onlyMissing)
        {
            int maxW = 0;
            for (int i = 0; i < CAR_LABELS.Length; i++)
            {
                int w = DispWidth(CAR_LABELS[i]);
                if (w > maxW) maxW = w;
            }
            int w2 = DispWidth(CAR_RES_LABEL);
            if (w2 > maxW) maxW = w2;

            bool printed = false;

            // ★ 2026-11-22（第 18 批 D2）：循环上界从 CAR_KEYS.Length 改成 CAR_TOTAL。
            //   原来只渲染 getprop 那 8 项，新增的 芯片/内存/DDR/存储 永远显示不出来。
            //   withCmd 时扩展项不是 getprop，标注成对应的小片段而不是拼个假属性名。
            for (int i = 0; i < CAR_TOTAL; i++)
            {
                string v = CAR_VALS[i];
                bool empty = (v == null || v.Length == 0);
                if (onlyMissing && !empty) continue;

                // DDR 类型取不到时**整行不出**（用户明确要求，不是显示 "-"）
                if (i >= CAR_KEYS.Length
                    && CAR_LABELS[i] == "DDR 类型" && empty) continue;

                PrintCarLine(CAR_LABELS[i], empty ? "-" : v, maxW, empty);
                if (withCmd)
                {
                    UseDim();
                    int extraIdx = i - CAR_KEYS.Length;
                    if (extraIdx >= 0)
                        Console.Write("      $ adb shell <" + CAR_LABELS[i] + " 探测片段>");
                    else
                        Console.Write("      $ adb shell getprop " + CAR_KEYS[i]);
                    Console.WriteLine();
                    UseDefault();
                }
                printed = true;
            }

            {
                bool empty = CAR_RES.Length == 0;
                if (!onlyMissing || empty)
                {
                    PrintCarLine(CAR_RES_LABEL, empty ? "-" : CAR_RES, maxW, empty);
                    if (withCmd)
                    {
                        UseDim();
                        Console.Write("      $ adb shell wm size");
                        Console.WriteLine();
                        UseDefault();
                    }
                    printed = true;
                }
            }

            if (!printed)
            {
                UseDim();
                Console.WriteLine("      （全部已取到）");
                Console.WriteLine();
                UseDefault();
            }
        }

        // 一行：  标签(补齐到 maxW)  值
        // 空值用灰黄色，能取到的值用正常色 —— 一眼看出哪项没配。
        //
        // 关于颜色：GUI 的 GuiSink 是**按行**记颜色的（切行时取"当前色"），
        // 一行里改两次色只有最后一次生效。所以这里不能指望"标签灰、值亮"
        // 这种行内双色 —— 那样整行会跟着最后一个 Use 走，九项全变灰。
        // 现在统一用行级着色：
        //   取到值 -> UseInput（最亮一档，sink 映射成 level 0 正常色）
        //   空值   -> UseWarn（黄色，sink 映射成 level 3，一眼看出哪项没配）
        // 行内区分标签和值靠的是对齐后的空白，不靠颜色。
        private static void PrintCarLine(string label, string val, int maxW, bool empty)
        {
            int pad = maxW - DispWidth(label);
            if (pad < 0) pad = 0;

            if (empty) UseWarn(); else UseInput();
            Console.Write("  ");
            Console.Write(label);
            Console.Write(new string(' ', pad));
            Console.Write("  ");
            Console.Write(val);
            Console.WriteLine();
            UseDefault();
        }

        // 显示宽度用 Program.cs 里已有的 DispWidth（CJK 算 2 格），
        // 这里不再重复实现 —— 同一份口径只能有一个实现，
        // 否则两处宽度算法不一致，输出列就会歪。

    }
}
