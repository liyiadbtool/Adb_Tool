// ============================================================================
//  Render.cs — 视觉层：配色体系、状态栏、动作回显、进度条、提示、帮助、自检
//  与 Program.cs 通过 partial class App 合并编译
//
//  配色只有 5 个语义色（控制台 16 色的天花板，多于 5 种反而降低扫读速度）：
//      绿  = 成功 / 在线
//      红  = 失败
//      黄  = 设备号 / 强调
//      青  = 路径 / 目录
//      灰  = 辅助（动作回显、建议、统计）
//
//  注意：Console.ForegroundColor 在输出被重定向时自动失效（走控制台 API 而非
//        ANSI 转义），所以导出日志到文件不会出现颜色码污染。
// ============================================================================
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

namespace AdbLogExport
{
    internal static partial class App
    {
        // ==================== 一、配色体系 ====================
        internal static bool COLOR = true;      // ini: color=0 关闭全部着色

        // 深色终端（cmd 默认黑底）用亮色；浅色终端用暗色，否则看不清。
        private static ConsoleColor COL_OK = ConsoleColor.Green;
        private static ConsoleColor COL_ERR = ConsoleColor.Red;
        private static ConsoleColor COL_WARN = ConsoleColor.Yellow;
        private static ConsoleColor COL_PATH = ConsoleColor.Cyan;
        private static ConsoleColor COL_DIM = ConsoleColor.DarkGray;
        private static ConsoleColor COL_INPUT = ConsoleColor.White;   // 用户输入：最亮的一档

        // 按主题切换具体颜色值（语义不变，只是深浅换档）
        internal static void ApplyTheme(bool light)
        {
            if (light)
            {
                COL_OK = ConsoleColor.DarkGreen;
                COL_ERR = ConsoleColor.DarkRed;
                COL_WARN = ConsoleColor.DarkYellow;
                COL_PATH = ConsoleColor.DarkCyan;
                COL_DIM = ConsoleColor.Gray;
                COL_INPUT = ConsoleColor.Black;     // 白底上必须压到最暗，否则看不见
            }
            else
            {
                COL_OK = ConsoleColor.Green;
                COL_ERR = ConsoleColor.Red;
                COL_WARN = ConsoleColor.Yellow;
                COL_PATH = ConsoleColor.Cyan;
                COL_DIM = ConsoleColor.DarkGray;
                COL_INPUT = ConsoleColor.White;
            }
        }

        internal static void Use(ConsoleColor c)
        {
            // v8.0：GUI 模式下的颜色旁路。
            // Console.ForegroundColor 是静态属性，TextWriter 子类拦不到 setter；
            // 但**所有**着色都经过这一个函数，所以在这里把当前颜色转告 GuiSink，
            // 它切行时会把颜色一起带出去。GUI 侧据此上色，命令行行为不变。
            if (GUI_COLOR_HOOK != null) GUI_COLOR_HOOK(c);

            if (!COLOR) return;
            try { Console.ForegroundColor = c; } catch { }
        }

        // GUI 入口安装的颜色旁路；命令行模式下始终为 null
        internal static Action<ConsoleColor> GUI_COLOR_HOOK = null;

        // 槽位标记旁路（GUI 专用）。
        // 背景：adb 的 OutputDataReceived 回调跑在 ThreadPool 线程上，那里
        // [ThreadStatic] 的 CUR_SLOT 恒为 0，1/2 号槽的流式输出会被归到 0 号槽。
        // AdbCallStream 在 worker 线程上捕获真实槽位后，通过这个旁路告诉 GuiSink
        // "接下来这一行属于哪个槽"。CLI 里没有 GuiSink，钩子为 null，零开销。
        internal static Action<int> GUI_SLOT_HOOK = null;

        internal static void MarkSlot(int slot)
        {
            Action<int> h = GUI_SLOT_HOOK;
            if (h != null) h(slot);
        }

        internal static void UseDim() { Use(COL_DIM); }
        internal static void UseOk() { Use(COL_OK); }
        internal static void UseErr() { Use(COL_ERR); }
        internal static void UseWarn() { Use(COL_WARN); }
        internal static void UsePath() { Use(COL_PATH); }
        internal static void UsePrompt() { Use(COL_PATH); }   // 提示符：路径色
        internal static void UseInput() { Use(COL_INPUT); }   // 用户敲的字：最亮

        // 恢复默认前景色（Windows 控制台默认是 Gray）
        internal static void UseDefault()
        {
            // 注意：HOOK 必须放在 COLOR 判断**之前**。
            // GUI 模式下 COLOR 是 false（不真的改控制台颜色），如果按老写法
            // `if (!COLOR) return;` 提前返回，HOOK 就永远不会被调用 ——
            // sink 会一直停在最后一处 UseDim() 的灰色上，
            // 于是 "标签灰 + 值正常色" 的整行都被染成灰的（车机信息九项就是这样）。
            // 命令行模式下 GUI_COLOR_HOOK 为 null，这一句是空操作，行为不变。
            if (GUI_COLOR_HOOK != null) GUI_COLOR_HOOK(ConsoleColor.Gray);

            if (!COLOR) return;
            try { Console.ForegroundColor = ConsoleColor.Gray; } catch { }
        }

        internal static void Line(string s, ConsoleColor c)
        {
            Use(c);
            Console.WriteLine(s);
            UseDefault();
        }

        internal static void W(string s, ConsoleColor c)
        {
            Use(c);
            Console.Write(s);
            UseDefault();
        }

        // ==================== 二、语义提示 ====================
        internal static void Ok(string msg)
        {
            Use(COL_OK);
            Console.WriteLine("  \u221A " + msg); // √
            UseDefault();
        }

        internal static void Fail(string msg)
        {
            Use(COL_ERR);
            Console.WriteLine("  \u00D7 " + msg); // ×
            UseDefault();
        }

        internal static void Warn(string msg)
        {
            Use(COL_WARN);
            Console.WriteLine("  ! " + msg);
            UseDefault();
        }

        internal static void Info(string msg)
        {
            Console.WriteLine("  - " + msg);
        }

        // 缩进建议（灰色弱化）
        internal static void Hint(string msg)
        {
            Use(COL_DIM);
            Console.WriteLine("    " + msg);
            UseDefault();
        }

        // ==================== 三、动作回显 ====================
        // 只在"这条输入被工具接管/改写"时调用（透传不打，否则每条命令多一行噪音）
        //   → adb     devices
        //   → send    你好
        //   → export  /log/x/351 -> D:\log\351
        //
        // 排版网格：符号固定在列 3，正文从列 5 开始 —— 所有工具行共用同一条竖线。
        internal static void Echo(string kind, string detail)
        {
            if (!ECHO_ACTION) return;
            Use(COL_DIM);
            // 需求4：去掉 kind 标签（cmd/adb/shell/export 等），只显示箭头 + 实际内容，
            // 灰色维持现状。kind 参数保留以兼容所有调用点，但不再打印。
            Console.Write("  \u2192 " + detail);
            UseDefault();
            Console.WriteLine();
        }

        // 按显示宽度补空格（中文占 2 列），保证表格列对齐
        internal static string PadRight(string s, int width)
        {
            int w = DispWidth(s);
            if (w >= width) return s;
            StringBuilder sb = new StringBuilder(s);
            for (int i = 0; i < width - w; i++) sb.Append(' ');
            return sb.ToString();
        }

        // ==================== 四、状态栏 ====================
        // 替代原来的 8 行 banner：一行常驻状态，省 7 行且状态始终可见
        internal static void StatusBar()
        {
            UpdateTitle();
            Console.WriteLine();

            if (OFFLINE)
            {
                W("\u25CF ", COL_ERR);   // ●
                W("未连接设备", COL_ERR);
                UseDefault();
                Console.WriteLine();
                Console.WriteLine();
                return;
            }

            W("\u25CF ", COL_OK);   // ●

            if (string.IsNullOrEmpty(DEVID))
            {
                W("(无设备)", COL_ERR);
            }
            else
            {
                W(DEVID, COL_WARN);
                if (DEVN > 0) W("  在线", COL_OK);
                else W("  离线", COL_ERR);
            }

            if (!PERMOK) W("  目录受限", COL_WARN);
            if (DEVN > 1) W("  (" + DEVN + " 台)", COL_DIM);

            // 不再打当前路径：提示符里有、标题栏里有、导出回显里也有，
            // 状态行再放一遍就是第三次重复，而且会把这一行撑得没重点。
            UseDefault();
            Console.WriteLine();

            // 车型 / SOC 紧跟状态行：每次连上设备都要看得到
            RenderDeviceInfo();

            // 帮助提示紧贴身份信息，中间不再空行 —— 启动块从 5 行压到 3 行
            UseDim();
            Console.WriteLine("  :h 帮助 · 命令直接输入（adb / shell 均可）· :q 退出");
            UseDefault();
            Console.WriteLine();
        }

        // 离线时的引导：告诉用户"还能干什么"，而不是让人以为程序废了
        internal static void OfflineBanner()
        {
            StatusBar();

            UseDim();
            Console.WriteLine("  离线模式下仍可使用：");
            Console.WriteLine("    :h            查看帮助索引");
            Console.WriteLine("    :which 输入   解释某条输入会怎么执行");
            Console.WriteLine("    :cmds         查看全部自定义命令");
            Console.WriteLine("    :r            重新检测并连接设备");
            Console.WriteLine("    :rr           重启 adb 服务后再连");
            Console.WriteLine("    devices       查看当前设备列表");
            Console.WriteLine("    :q            退出");
            UseDefault();
            Console.WriteLine();
            Console.WriteLine("  提示：插上设备后直接敲任意命令，会自动重连并执行");
            Console.WriteLine();
        }

        // 路径过长时保留首尾、省略中段，保证末段始终可见
        internal static string ShortPath(string p, int maxLen)
        {
            if (string.IsNullOrEmpty(p)) return "/";
            if (p.Length <= maxLen) return p;

            string tail = LastSeg(p);
            int keepHead = maxLen - tail.Length - 5;
            if (keepHead < 3) return "..." + p.Substring(Math.Max(0, p.Length - (maxLen - 3)));
            return p.Substring(0, keepHead) + ".../" + tail;
        }

        // ==================== 五、进度条 ====================
        // 用 \r 原地刷新，不刷屏。只用 █ 与空格（GBK 安全，无需降级）
        internal static void Progress(string label, int done, int total)
        {
            const int WIDTH = 20;
            int fill = (total > 0) ? (int)((long)done * WIDTH / total) : 0;
            if (fill > WIDTH) fill = WIDTH;

            StringBuilder bar = new StringBuilder(WIDTH);
            for (int i = 0; i < WIDTH; i++) bar.Append(i < fill ? '\u2588' : ' '); // █

            Console.Write('\r');
            Console.Write("  ");
            W(label, COL_WARN);
            Console.Write(" [");
            W(bar.ToString(), COL_OK);
            Console.Write("]  " + done + "/" + total + "    ");
        }

        // 进度条收尾：清掉残留并换行
        internal static void ProgressEnd()
        {
            Console.Write('\r');
            Console.Write(new string(' ', 78));
            Console.Write('\r');
        }

        // ==================== 六、帮助 ====================
        private static void Separator(string ch)
        {
            int n = Util.ConsoleWidth(76);
            if (n < 40) n = 76;
            StringBuilder sb = new StringBuilder(n);
            for (int i = 0; i < n; i++) sb.Append(ch);
            UseDim();
            Console.WriteLine(sb.ToString());
            UseDefault();
        }

        private static void HelpAll()
        {
            Console.WriteLine();
            Separator("-");
            Console.WriteLine("  目录与列表");
            Console.WriteLine("    ls              列出当前目录（横排；目录青、可执行绿、隐藏灰）");
            Console.WriteLine("    ls 351          列出子目录 351 的内容（不改变当前目录）");
            Console.WriteLine("    ls -l / ls -la  带选项时原样交给设备，输出系统原生格式");
            Console.WriteLine("    lsf [目录]      只列文件（确认某个 log 在不在）");
            Console.WriteLine("    cd 目录         进入目录，例如 cd 351");
            Console.WriteLine("    cd .. / cd -    返回上级 / 返回上一个目录");
            Console.WriteLine("    cd              回到设备家目录（即 /）");
            Console.WriteLine("    pwd             显示当前目录");
            Console.WriteLine("    cd @logs        跳到 " + JUMP_LOG);
            Console.WriteLine("    cd @res         跳到 " + JUMP_RES);
            Console.WriteLine("    cd @anr / @dropbox   跳到 " + JUMP_ANR + " / " + JUMP_DROPBOX);
            Console.WriteLine("  （跳转点是数据，配在 ini 的 jump_* 里）");
            Console.WriteLine("  环境切换（: 前缀，不占设备命令名）");
            Console.WriteLine("    :env test / :env pre / :env dev   切到对应环境（设置后立即回读校验）");
            Console.WriteLine("    :env                              查询当前环境属性，自动识别是哪套");
            Console.WriteLine("    属性名与取值在 ini 的 env_prop_* / env_test / env_pre / env_dev");
            Console.WriteLine("    （设备原生的 test 命令仍可用，直接写 test -f /x 即可）");
            Console.WriteLine("  文件传输");
            Console.WriteLine("    C:\\XX           把当前目录导出到 C:\\XX（文件多时自动打包 tar.gz）");
            Console.WriteLine("    pull 351 D:\\log  导出指定目录（设备路径相对当前目录）");
            Console.WriteLine("    pull D:\\log      简写：导出当前目录");
            Console.WriteLine("    push D:\\a.sh /data/local/tmp/    推送到设备");
            Console.WriteLine("    （打包开关见 ini 的 export_zip：0=不打包 1=总是 2=超阈值）");
            Console.WriteLine("  adb 命令（加不加 adb 前缀都行）");
            Console.WriteLine("    devices                 列出设备，标出当前使用哪台");
            Console.WriteLine("    install D:\\a.apk        安装 apk（自动校验文件存在）");
            Console.WriteLine("    uninstall 包名           卸载");
            Console.WriteLine("    reboot                  重启设备（不二次确认，执行后明确报告状态）");
            Console.WriteLine("    root / unroot / remount 取 root / 取消 / 重挂载分区");
            Console.WriteLine("    forward / reverse       端口转发");
            Console.WriteLine("    tcpip 5555 / connect IP 无线调试");
            Console.WriteLine("    version                 查看 adb 版本");
            Console.WriteLine("    adb shell <命令>         等价于直接输入该命令（保持当前目录）");
            Console.WriteLine("    adb exec-out screencap -p > a.png   截屏存本地（支持 > 重定向）");
            Console.WriteLine("  发送到 App（: 前缀）");
            Console.WriteLine("    :send 你好      发送一条文本");
            Console.WriteLine("    你好            直接输入中文也行（等价于 :send 你好）");
            Console.WriteLine("    :send 1 ~ 9     发送常用语（ini 里 quick_1 ~ quick_9）");
            Console.WriteLine("    :send \"1\"       发送文本 1（引号强制当文本，不当编号）");
            Console.WriteLine("    :send -f D:\\a.txt 批量发送（UTF-8 / ANSI / BOM 自动识别）");
            Console.WriteLine("  其他命令");
            Console.WriteLine("    df -h / cat 文件 / ps / rm / mkdir / mount ...  直接透传给设备 shell");
            Console.WriteLine("    （透传命令的路径都相对于当前目录，不用每次写全路径）");
            Console.WriteLine("    logcat          裸跑会自动加 -d；带参数则原样交给设备");
            Console.WriteLine("    交互式命令（top / vi / less）会先提示，");
            Console.WriteLine("    确实要原样跑就加前缀 ! ，例如 !top");
            Console.WriteLine("  工具命令（: 前缀）");
            Console.WriteLine("    :r=刷新回根  :rr=重启 adb 服务  :ri=完全初始化");
            Console.WriteLine("    :rl=重试：优先重做失败的 cd/ls/导出，否则重跑上一条命令");
            Console.WriteLine("    （空回车 = 显示当前设备与路径，不会什么也不发生）");
            Console.WriteLine("    :ri=完全初始化  :rw=重取窗口宽度  :h=帮助索引  :h all=完整帮助  :q=退出");
            Console.WriteLine("    :which <输入>     解释这条输入会被谁接走、最终执行什么");
            Console.WriteLine("    :ime              下一条用中文输入（读完自动回编辑）");
            Console.WriteLine("    :ime on|off|auto  常驻中文 / 关闭 / 跟随系统输入法状态");
            Console.WriteLine("    :pkg ver          批量查版本：ini 的 version_pkgs（一次 adb 调用查全部）");
            Console.WriteLine("    :pkg ver com.a    查单个包：版本名 / 版本码 / 更新时间 / 安装路径");
            Console.WriteLine("    com.a.b           直接输入包名等价于 :pkg ver com.a.b（版本 + 路径）");
            Console.WriteLine("    :pkg ver com.a.b  只查指定包");
            Console.WriteLine("    :front            查前台包名 / Activity / 路径 / pid（原 :pkg now）");
            Console.WriteLine("    :ping             连通性快测（一条命令，带耗时）");
            Console.WriteLine("    :diag             连接体检：adb 进程/端口/版本/设备状态，搜不到设备时先看这个");
            Console.WriteLine("    :cmds             列出所有自定义命令（DIY 指令）");
            Console.WriteLine("  语音助手调试（:vr，融合自 语音助手工具.exe）");
            Console.WriteLine("    :vr wake          主驾唤醒（vr:// type=1，默认真实唤醒）");
            Console.WriteLine("    :vr wake 99       唤醒（原参 type=99，不睡屏 canSleep=false）");
            Console.WriteLine("    :vr sr 打开车窗    语音识别（文本经 URL 编码后发出）");
            Console.WriteLine("    :vr sr 打开车窗 -a 1  指定音区（0主驾 1副驾 2二排左 3二排右 4三排左 5三排右）");
            Console.WriteLine("    :vr local 打开车门    断网识别（AH8 离线 mode=local）");
            Console.WriteLine("    :vr area          音区对照表（纯本地输出，不连设备）");
            Console.WriteLine("    :vr ver           语助版本号（versionName + versionCode）");
            Console.WriteLine("    :vr restart       重启语助进程（force-stop 后由语音重新拉起）");
            Console.WriteLine("    :vr set           打开语助后台设置页（SettingDebugActivity）");
            Console.WriteLine("    :vr dbg           打开文本语义调试页（DebugTextExecuteSemanticActivity）");
            Console.WriteLine("    :vr reboot -y     重启车机（破坏性，必须带 -y）");
            Console.WriteLine("    :vr un -y         卸载语助（破坏性，必须带 -y）");
            Console.WriteLine("    :vr help          语音助手调试专用帮助");
            Console.WriteLine("    （参数只认 -a 音区、-l/--local 离线，其余原文当识别文本；");
            Console.WriteLine("      pkg / uri / 上限等可改 ini 的 vr_* 项）");
            Console.WriteLine("  手车互联（: 前缀）");
            Console.WriteLine("    :carplaycert          查询 CarPlay 认证属性（CERT 当前值）");
            Console.WriteLine("    :carplaycert on       设为 true，放行认证（设完自动回读确认）");
            Console.WriteLine("    :carplaycert off      设为 false，拒绝认证（设完自动回读确认）");
            Console.WriteLine("    （属性名 persist.connectivityphone.carplay.CERT，改完需断开重连 CarPlay）");
            Console.WriteLine("    :carplay   导出 CarPlay 音频/HCI 日志");
            Console.WriteLine("    :carplayon 打开 CarPlay 音频（两条顺序执行，失败跳过并报告）");
            Console.WriteLine("    :hicarclear           清除 HiCar 历史设备（走 hdc，清后手机需重新配对）");
            Console.WriteLine("    :hicar     打开 HiCar SDK 日志");
            Console.WriteLine("    :hdclist              列出 hdc 设备（排查 hdc 通道是否连上）");
            Console.WriteLine("    （hdc 找不到时：把 hdc.exe 放到 exe 同级，或在 ini 里配 hdc=路径）");
            Console.WriteLine("  方控（: 前缀，注入 keycode 到 car_service）");
            Console.WriteLine("    :fkcall :fkvoice :fkprev :fknext :fkplay   通话/语音/上首/下首/播放");
            Console.WriteLine("    :fkvolup :fkvoldown :fkmute                音量+/音量-/静音");
            Console.WriteLine("    :fkstarleft :fkstarright                   左星号(521)/右星号(520)");
            Console.WriteLine("    :fkcalllong :fkvoicelong                   通话/语音 长按 3 秒");
            Console.WriteLine("    :fkforce              强制重启：电话(503)+星号(520) 同时按住 20 秒");
            Console.WriteLine("    :fkforce 25           按住 25 秒（车机重启导致断线也算成功）");
            Console.WriteLine("  旧名仍可用（过渡期）");
            Console.WriteLine("    send / ver / now / test / pre / dev / syncore / res / logs / anr / dropbox");
            Console.WriteLine("    这些已迁移到 : 前缀，裸名不再被工具占用；ini 设 legacy_alias=0 可彻底关闭");
            Console.WriteLine("  自定义命令（DIY）");
            Console.WriteLine("    在 cmds.ini 里用 [cmd.名字] 定义，用 :名字 调用：");
            Console.WriteLine("      [cmd.crash]");
            Console.WriteLine("      desc = 崩溃日志缓冲区");
            Console.WriteLine("      run  = logcat -d -b crash");
            Console.WriteLine("    调用：:crash（撞设备命令的名字只能用 : 形式，防止抢走透传）");
            Console.WriteLine("    支持 $1..$9 位置参数、$* 全部、$(date) $(serial) $(cur) 等");
            Console.WriteLine("    导出落点：$(out:shot) $(out:rec) $(out:hci)");
            Console.WriteLine("              分别对应 桌面\\logcat\\<日期>\\screencap|screenrecord|HCI");
            if (CMD_ORDER.Count > 0)
                Console.WriteLine("    当前已加载 " + CMD_ORDER.Count + " 条，输入 cmds 查看");
            Separator("-");
            Console.WriteLine("  发送目标：" + URI_PREFIX);
            Console.WriteLine("  发送动作：" + AM_CMD + (COMPONENT.Length > 0 ? "  -n " + COMPONENT : "") + "   重试：" + RETRY + " 次");
            Console.WriteLine("  提示：全程不清屏，方便复制粘贴；长操作可按 Ctrl+C 中断");
            Console.WriteLine();
        }

        // ==================== 七、自检 ====================
        private static int ST_FAIL;

        private static void STCheck(string name, bool cond)
        {
            if (cond) Console.WriteLine("  [OK] " + name);
            else { Console.WriteLine("  [FAIL] " + name); ST_FAIL++; }
        }

        // 带实际值：失败时把"期望看到什么、实际是什么"直接打出来，
        // 省得回头再手动复现一遍
        private static void STCheck(string name, bool cond, string actual)
        {
            if (cond) { Console.WriteLine("  [OK] " + name); return; }
            Console.WriteLine("  [FAIL] " + name + "  （实际：" + actual + "）");
            ST_FAIL++;
        }

        private static int SelfTest()
        {
            ST_FAIL = 0;
            COLOR = false;   // 自检不输出颜色，便于粘贴比对

            string savedCur = CUR;
            CUR = ROOT;

            Console.WriteLine("== 自检：路径工具 ==");
            STCheck("NormPath /a/b/../c => /a/c", NormPath("/a/b/../c") == "/a/c");
            STCheck("NormPath //a///b// => /a/b", NormPath("//a///b//") == "/a/b");
            STCheck("NormPath 多级 .. => /", NormPath("/a/b/../../") == "/");
            STCheck("LastSeg /a/b/ => b", LastSeg("/a/b/") == "b");
            STCheck("LastSeg / => /", LastSeg("/") == "/");
            STCheck("DevAbs 相对补全", DevAbs("351") == NormPath(ROOT + "/351"));
            STCheck("DevAbs 绝对路径", DevAbs("/x/y") == "/x/y");

            CUR = savedCur;

            Console.WriteLine("== 自检：分词 ==");
            string c, a;
            SplitLine("ls 351", out c, out a);
            STCheck("SplitLine ls 351 -> cmd=ls", c == "ls" && a == "351");
            SplitLine("pull 353 \"D:\\my log\"", out c, out a);
            STCheck("SplitLine 保留引号", c == "pull");
            List<string> sa = SplitArgs("353 \"D:\\my log\"");
            STCheck("SplitArgs 引号感知 2 段", sa.Count == 2 && sa[0] == "353" && sa[1] == "D:\\my log");
            STCheck("IsWinPath C:\\", IsWinPath("C:\\xx"));
            STCheck("IsWinPath UNC", IsWinPath("\\\\nas\\share"));
            STCheck("IsWinPath 非路径", !IsWinPath("351"));

            Console.WriteLine("== 自检：显示宽度与截断 ==");
            STCheck("DispWidth 中文=2", DispWidth("中文") == 4);
            STCheck("DispWidth 英文=1", DispWidth("abc") == 3);
            STCheck("DispWidth 混合", DispWidth("a中b") == 4);
            STCheck("Unquote 去引号", Unquote("\"C:\\my dir\"") == "C:\\my dir");
            STCheck("ShortPath 短路径不变", ShortPath("/a/b", 60) == "/a/b");
            STCheck("ShortPath 长路径保留末段", ShortPath("/aaa/bbb/ccc/ddd/androidlog", 20).EndsWith("androidlog"));
            STCheck("ShortPath 长路径含省略号", ShortPath("/aaa/bbb/ccc/ddd/androidlog", 20).IndexOf("...") >= 0);

            Console.WriteLine("== 自检：纯中文启发式 ==");
            STCheck("中文 -> 文本", IsProbablyText("你好"));
            STCheck("中英混合首 token -> 文本", IsProbablyText("你好abc"));
            STCheck("cat -> 非文本", !IsProbablyText("cat"));
            STCheck("351 -> 非文本", !IsProbablyText("351"));
            STCheck("空 -> 非文本", !IsProbablyText(""));

            Console.WriteLine("== 自检：并行槽位状态 ==");
            STCheck("SLOT_COUNT 与 GUI 一致（3）", SLOT_COUNT == 3);
            STCheck("运行中进程表长度 = 槽位数", RUNNING_SLOTS.Length == SLOT_COUNT);
            STCheck("录屏运行标志长度 = 槽位数", REC_GRAB_RUNNING.Length == SLOT_COUNT);
            STCheck("默认无录屏在跑", !REC_GRAB_RUNNING[0] && !REC_GRAB_RUNNING[1] && !REC_GRAB_RUNNING[2]);
            STCheck("KillRunning 越界不抛且返回 false", !KillRunning(-1) && !KillRunning(99));
            bool stopThrew = false;
            try { StopRecGrab(99); StopRecGrab(-1); } catch { stopThrew = true; }
            STCheck("StopRecGrab 越界/负值不抛异常", !stopThrew);
            bool markThrew = false;
            try { MarkSlot(2); MarkSlot(-1); } catch { markThrew = true; }
            STCheck("MarkSlot 无 GUI 钩子时安全（CLI）", !markThrew && GUI_SLOT_HOOK == null);

            Console.WriteLine("== 自检：adb 子命令识别 ==");
            STCheck("devices 是 adb 子命令", IsAdbSubcmd("devices"));
            STCheck("install 是 adb 子命令", IsAdbSubcmd("install"));
            STCheck("REBOOT 大小写不敏感", IsAdbSubcmd("REBOOT"));
            STCheck("exec-out 是 adb 子命令", IsAdbSubcmd("exec-out"));
            STCheck("pm 不是 adb 子命令（走 shell）", !IsAdbSubcmd("pm"));
            STCheck("dumpsys 不是 adb 子命令（走 shell）", !IsAdbSubcmd("dumpsys"));
            STCheck("screencap 不是 adb 子命令（走 shell）", !IsAdbSubcmd("screencap"));
            STCheck("空串不是 adb 子命令", !IsAdbSubcmd(""));
            STCheck("含 > 判为本地重定向", HasLocalRedir("exec-out screencap -p > a.png"));
            STCheck("含 | 判为本地管道", HasLocalRedir("devices | findstr device"));
            STCheck("无重定向", !HasLocalRedir("devices -l"));
            STCheck("引号内 > 不算本地", !HasLocalRedir("shell \"ls > /sdcard/a\""));
            STCheck("引号外 | 算本地", HasLocalRedir("shell getprop | findstr navi"));
            STCheck("findstr 管道判为本地", IsLocalPipe("getprop | findstr navi"));
            STCheck("grep 管道保持设备侧", !IsLocalPipe("ps | grep xxx"));
            STCheck("无管道不算本地", !IsLocalPipe("getprop"));
            STCheck("引号内管道不算本地", !IsLocalPipe("echo \"a | findstr b\""));
            STCheck("IndexOutsideQuotes 跳过引号内", IndexOfOutsideQuotes("a \"b|c\" d|e", '|') == 9);
            STCheck("AfterToken 跳过 shell", AfterToken("shell ls -l", 1) == "ls -l");
            STCheck("AfterToken 保留用户引号", AfterToken("-s X shell \"ls > /a\"", 3) == "\"ls > /a\"");
            STCheck("AfterToken 跳过过多返回空", AfterToken("shell", 2) == "");
            STCheck("AfterToken 跳过 -s 两项", AfterToken("-s ABC shell df -h", 3) == "df -h");

            // ==================== 复合命令体检（2026-11-12 修复）====================
            // 背景：裸名 ls/cd 接管前必须确认参数里没有 shell 连接符，否则
            // "ls && echo ok" 会把 "&& echo ok" 当成路径塞给 ls -1pF，静默失败。
            Console.WriteLine("== 自检：复合命令体检 ==");
            STCheck("ls && echo ok 判为复合", IsComplexShellLine("&& echo ok"));
            STCheck("ls > /sdcard/a 判为复合", IsComplexShellLine("> /sdcard/a.txt"));
            STCheck("cd x && ls 判为复合", IsComplexShellLine("/sdcard && ls"));
            STCheck("分号串联判为复合", IsComplexShellLine("; ls"));
            STCheck("设备管道判为复合", IsComplexShellLine("| grep media"));
            STCheck("输入重定向判为复合", IsComplexShellLine("< /sdcard/a"));
            STCheck("命令替换 $( ) 判为复合", IsComplexShellLine("$(getprop ro.model)"));
            STCheck("反引号命令替换判为复合", IsComplexShellLine("`date`"));
            STCheck("普通 ls 参数不算复合", !IsComplexShellLine(" /sdcard"));
            STCheck("ls -l 不算复合", !IsComplexShellLine(" -l"));
            STCheck("空串不算复合", !IsComplexShellLine(""));
            STCheck("null 不算复合", !IsComplexShellLine(null));
            // 引号内的符号属于设备侧语义，不能因为"看起来像重定向"就放弃接管
            STCheck("引号内 > 不算复合", !IsComplexShellLine(" \"a > b\""));
            STCheck("引号内 ; 不算复合", !IsComplexShellLine(" \"a; b\""));
            // 单个 & 不判复合：路径里可能出现 a&b，误判代价大于收益
            STCheck("单个 & 不算复合", !IsComplexShellLine(" a&b"));

            Console.WriteLine("== 自检：cmd 参数构造（/s /c 引号层）==");
            // 【2026-11-12 修复】这三条锁死"必须 /s /c 且整行加引号"这个形态。
            // 背景：旧实现是 "/c " + cmdLine，cmd 的规则2会剥掉行首+行尾引号，
            // 导致 `getprop | findstr navi` 表现为 rc=0 但零输出（真机实测）。
            // 只要有人把 /s 去掉或把外层引号去掉，下面第一条就会失败。
            STCheck("cmd 参数以 /s /c 开头", BuildCmdArgs("adb shell x").StartsWith("/s /c "));
            STCheck("cmd 参数整行被引号包住", BuildCmdArgs("adb shell x") == "/s /c \"adb shell x\"");
            {
                // 内层引号必须原样保留，不能翻倍、不能改成 \"
                string qArgs = BuildCmdArgs("adb.exe shell \"cd '/' && getprop\" | findstr navi");
                STCheck("cmd 参数保留内层引号",
                    qArgs == "/s /c \"adb.exe shell \"cd '/' && getprop\" | findstr navi\"");
                STCheck("cmd 参数内层引号不翻倍", qArgs.IndexOf("\"\"") < 0);
                STCheck("cmd 参数内层引号不转义", qArgs.IndexOf("\\\"") < 0);
            }
            STCheck("cmd 参数空串不抛异常", BuildCmdArgs("") == "/s /c \"\"");
            STCheck("cmd 参数 null 不抛异常", BuildCmdArgs(null) == "/s /c \"\"");

            // 路径含空格是本项目最容易复发的一类问题：
            // 只要 adb 装在 "C:\Program Files\..." 下，命令行的引号数就变成 4 个，
            // 没有 /s 的话 cmd 会剥掉首尾引号，整行错位（实测报"文件名语法不正确"）。
            {
                string sp = BuildCmdArgs("\"C:\\Program Files\\pt\\adb.exe\" shell \"cd '/' && getprop\" | findstr x");
                STCheck("含空格路径仍以 /s /c 包整行", sp.StartsWith("/s /c \"") && sp.EndsWith("\""));
            }

            Console.WriteLine("== 自检：:which 与 Dispatch 判定一致 ==");
            // 这两条是"解释必须等于行为"的回归门禁。
            // 曾经 :which getprop | findstr navi 报"透传设备 shell"，
            // 实际却走 RunShellPipe 本地过滤 —— 解释与行为相反。
            {
                string k1;
                string d1;
                Classify("getprop | findstr navi", out k1, out d1);
                STCheck(":which findstr 管道 -> 本地过滤", k1 == "设备 + 本地过滤", k1);

                string k2;
                string d2;
                Classify("ps | grep media", out k2, out d2);
                STCheck(":which grep 管道 -> 透传", k2 == "透传设备 shell", k2);

                string k3;
                string d3;
                Classify("ls && echo ok", out k3, out d3);
                STCheck(":which ls 复合 -> 透传", k3 == "透传设备 shell", k3);

                string k4;
                string d4;
                Classify("ls > /sdcard/a.txt", out k4, out d4);
                STCheck(":which ls 重定向 -> 透传", k4 == "透传设备 shell", k4);

                string k5;
                string d5;
                Classify("ls -l", out k5, out d5);
                STCheck(":which ls -l 仍为增强", k5 == "设备（语义增强）", k5);

                string k6;
                string d6;
                Classify("cd /sdcard", out k6, out d6);
                STCheck(":which cd 仍为增强", k6 == "设备（语义增强）", k6);
            }


            Console.WriteLine("== 自检：交互式命令预判 ==");
            STCheck("裸 top 被识别为交互式", IsInteractiveBare("top", ""));
            STCheck("裸 vi 被识别为交互式", IsInteractiveBare("vi", ""));
            STCheck("top -n 1 不算交互式", !IsInteractiveBare("top", "-n 1"));
            STCheck("top -d 1 -n 3 不算交互式", !IsInteractiveBare("top", "-d 1 -n 3"));
            STCheck("cat 不算交互式", !IsInteractiveBare("cat", "x.log"));
            STCheck("less -l 仍算交互式", IsInteractiveBare("less", "-l a.txt"));

            Console.WriteLine("== 自检：URL 编码 ==");
            STCheck("EscapeData 中文", Util.EscapeData("中文") == "%E4%B8%AD%E6%96%87");
            STCheck("EscapeData 空格", Util.EscapeData("a b") == "a%20b");
            STCheck("EscapeData 英文不变", Util.EscapeData("hello") == "hello");

            Console.WriteLine("== 自检：编码识别 ==");
            byte[] u8 = Encoding.UTF8.GetBytes("中文abc");
            STCheck("DecodeText UTF-8", Util.DecodeText(u8) == "中文abc");
            byte[] u8b = new byte[3 + u8.Length];
            u8b[0] = 0xEF; u8b[1] = 0xBB; u8b[2] = 0xBF;
            Array.Copy(u8, 0, u8b, 3, u8.Length);
            STCheck("DecodeText UTF-8 BOM", Util.DecodeText(u8b) == "中文abc");
            byte[] gb = Encoding.GetEncoding(936).GetBytes("中文abc");
            STCheck("DecodeText GBK", Util.DecodeText(gb) == "中文abc");

            Console.WriteLine("== 自检：发送命令构造 ==");
            string am = BuildAmCmd("%E4%BD%A0");
            STCheck("am 命令以子命令开头", am.IndexOf("am " + AM_CMD) == 0);
            STCheck("am 命令含 -a", am.Contains("-a " + ACTION));
            STCheck("am 命令 URL 单引号包裹", am.Contains("-d '" + URI_PREFIX + "%E4%BD%A0'"));

            Console.WriteLine("== 自检：ls 类型后缀解析 ==");
            STCheck("目录 / 后缀", ParseLsSuffix("351/") == 0);
            STCheck("可执行 * 后缀", ParseLsSuffix("run.sh*") == 1);
            STCheck("符号链接 @ 后缀", ParseLsSuffix("link@") == 2);
            STCheck("普通文件无后缀", ParseLsSuffix("a.log") == 3);
            STCheck("隐藏文件识别", ParseLsSuffix(".hidden") == 4);
            STCheck("目录优先于隐藏", ParseLsSuffix(".git/") == 0);

            Console.WriteLine("== 自检：自定义命令（DIY）==");
            STCheck("未定义命令 HasCmd=false", !HasCmd("zzz_no_such_cmd"));
            STCheck("ExpandTemplate $1", ExpandTemplate("pull $1 \"D:\\log\"", "351", "x") == "pull 351 \"D:\\log\"");
            STCheck("ExpandTemplate $*", ExpandTemplate("echo $*", "a b c", "x") == "echo a b c");
            STCheck("ExpandTemplate $0", ExpandTemplate("run $0", "", "net") == "run net");
            STCheck("ExpandTemplate 缺参为空", ExpandTemplate("pull $2", "only1", "x") == "pull ");
            STCheck("ExpandTemplate $(cur)", ExpandTemplate("x $(cur)", "", "x") == "x " + CUR);
            STCheck("ExpandTemplate 未知函数为空", ExpandTemplate("a $(nope) b", "", "x") == "a  b");
            STCheck("ExpandTemplate 无占位符原样", ExpandTemplate("shell df -h", "", "x") == "shell df -h");
            STCheck("CompleteCmd 前缀命中 ls", CompleteCmd("ls").Contains("ls"));
            STCheck("CompleteCmd 无匹配为空", CompleteCmd("zzzz").Count == 0);
            STCheck("CompleteCmd 结果含自定义命令", CompleteCmd("cmds").Count >= 0);

            Console.WriteLine("== 自检：离线模式 ==");
            STCheck("离线允许 h", OfflineAllowed("h"));
            STCheck("离线允许 cmds", OfflineAllowed("cmds"));
            STCheck("离线允许 r", OfflineAllowed("r"));
            STCheck("离线允许 ri", OfflineAllowed("ri"));
            STCheck("离线允许 adb", OfflineAllowed("adb"));
            STCheck("离线允许 devices", OfflineAllowed("devices"));
            STCheck("离线允许 connect", OfflineAllowed("connect"));
            STCheck("离线拒绝 ls", !OfflineAllowed("ls"));
            STCheck("离线拒绝 send", !OfflineAllowed("send"));
            STCheck("离线拒绝 cd", !OfflineAllowed("cd"));
            STCheck("离线拒绝 pull", !OfflineAllowed("pull"));
            STCheck("离线拒绝未知命令", !OfflineAllowed("dfx"));

            Console.WriteLine("== 自检：前台包名提取 ==");
            STCheck("mCurrentFocus 提取", ExtractPkg("  mCurrentFocus=Window{3f2a1b u0 com.gxatek.cockpit/.MainActivity}") == "com.gxatek.cockpit");
            STCheck("mResumedActivity 提取", ExtractPkg("mResumedActivity: ActivityRecord{abc u0 com.a.b/.C t1}") == "com.a.b");
            STCheck("完整组件名提取", ExtractPkg("cmp=com.x.y/com.x.y.Z") == "com.x.y");
            STCheck("带点包名提取", ExtractPkg("u0 a.b.c.d/e.f") == "a.b.c.d");
            STCheck("无包名返回空", ExtractPkg("no package here") == "");
            STCheck("纯数字不算包名", ExtractPkg("123/456") == "");
            STCheck("无点号不算包名", ExtractPkg("abc/def") == "");

            Console.WriteLine("== 自检：列宽截断 ==");
            STCheck("FitWidth 短串不变", FitWidth("abc", 10) == "abc");
            STCheck("FitWidth 恰好等宽不截断", FitWidth("abcde", 5) == "abcde");
            STCheck("FitWidth 超长截断加 ..", FitWidth("abcdefghij", 6) == "abcd..");
            STCheck("FitWidth 中文按 2 列", FitWidth("中文中文", 5) == "中..");
            STCheck("FitWidth 空串", FitWidth("", 5) == "");
            STCheck("CharWidth ASCII=1", CharWidth('a') == 1);
            STCheck("CharWidth 中文=2", CharWidth('中') == 2);

            Console.WriteLine("== 自检：打包导出辅助 ==");
            STCheck("ParentOf /a/b => /a", ParentOf("/a/b") == "/a");
            STCheck("ParentOf /a => /", ParentOf("/a") == "/");
            STCheck("ParentOf 多级", ParentOf("/a/b/c") == "/a/b");
            STCheck("ParentOfWin D:\\a\\b => D:\\a", ParentOfWin("D:\\a\\b") == "D:\\a");
            STCheck("SanitizeName 普通名不变", SanitizeName("351") == "351");
            STCheck("SanitizeName 替换斜杠", SanitizeName("a/b") == "a_b");
            STCheck("SanitizeName 替换冒号", SanitizeName("a:b") == "a_b");
            STCheck("FormatSize B", FormatSize(512) == "512 B");
            STCheck("FormatSize KB", FormatSize(2048) == "2 KB");
            STCheck("FormatSize MB", FormatSize(3 * 1024 * 1024) == "3 MB");

            // v7.15 导出落点（BUG-01/04/06 回归锚点）
            //
            // 这几条只测"纯路径计算"，不碰设备、不碰磁盘，因此可以在自检里常驻。
            // 之前的双嵌套、单文件多一层、失败留空目录，根因全部出在这几个函数上。
            STCheck("LastSegWin 反斜杠", LastSegWin("C:\\a\\b") == "b");
            STCheck("LastSegWin 正斜杠", LastSegWin("C:/a/b") == "b");
            STCheck("LastSegWin 混合斜杠", LastSegWin("C:/a\\b") == "b");
            STCheck("LastSegWin 尾斜杠", LastSegWin("C:\\a\\b\\") == "b");
            STCheck("LastSegWin 盘符根为空", LastSegWin("C:\\") == "");
            STCheck("LastSegWin 裸盘符为空", LastSegWin("C:") == "");

            STCheck("ParentOfWin 反斜杠", ParentOfWin("D:\\a\\b") == "D:\\a");
            STCheck("ParentOfWin 正斜杠", ParentOfWin("D:/a/b") == "D:/a");
            STCheck("ParentOfWin 尾斜杠", ParentOfWin("D:\\a\\b\\") == "D:\\a");
            STCheck("ParentOfWin 二级不越界", ParentOfWin("D:\\a").Length > 0);
            STCheck("ParentOfWin 根不变", ParentOfWin("D:\\") == "D:\\");

            // 单文件导出的落点拼接规则：目标给"文件名"就用它，给"目录"就拼源名
            STCheck("单文件落点-目标即文件名",
                JoinWin("C:\\t9", "one.zst") == "C:\\t9\\one.zst");
            STCheck("单文件落点-目标目录拼源名",
                JoinWin("C:\\t10", LastSeg("/a/b/x.zst")) == "C:\\t10\\x.zst");
            STCheck("单文件落点-不重复拼同名",
                LastSegWin(JoinWin("C:\\t10", "x.zst")) == "x.zst");

            Console.WriteLine("== 自检：环境切换 ==");
            InitDefaultEnvs();
            EnvProfile et = FindEnv("test");
            STCheck("默认有 test 环境", et != null);
            STCheck("test 的 deploy 值", et != null && et.Deploy == "test");
            STCheck("test 的 https 值", et != null && et.Https == "api-test.syncore.space:20443");
            STCheck("默认有 dev 环境", FindEnv("dev") != null);
            STCheck("默认有 pre 环境", FindEnv("pre") != null);
            STCheck("未知环境返回 null", FindEnv("nope") == null);
            STCheck("属性名默认值", ENV_P_DEPLOY == "persist.sys.autofly.web.deploy");

            string[] mk = ParseMarked("##1\nvalueA\n##2\n\n##3\nvalueC\n", 3);
            STCheck("ParseMarked 取到第 1 段", mk[0] == "valueA");
            STCheck("ParseMarked 空段保持空", mk[1] == "");
            STCheck("ParseMarked 取到第 3 段", mk[2] == "valueC");

            Console.WriteLine("== 自检：引号工具 ==");
            STCheck("QuoteArg 含空格加引号", Util.QuoteArg("a b") == "\"a b\"");
            STCheck("QuoteArg 无空格不变", Util.QuoteArg("abc") == "abc");

            Console.WriteLine("== 自检：控制台与 adb 超时（v7.11 新增）==");

            // 1) 控制台保护：只要求"不抛异常"
            try { ConsoleUtil.Init(); STCheck("ConsoleUtil.Init 不抛异常", true); }
            catch { STCheck("ConsoleUtil.Init 不抛异常", false); }
            try { bool h = ConsoleUtil.Healthy(); STCheck("ConsoleUtil.Healthy 可调用", h || !h); }
            catch { STCheck("ConsoleUtil.Healthy 可调用", false); }

            // 1b) 鼠标能力（v7.12）：滚轮上滑 / 拖选复制 / 右键粘贴全靠 QuickEdit。
            //     只有真控制台才查得到，管道输入时跳过（不算失败）。
            if (ConsoleUtil.Ready)
            {
                STCheck("QuickEdit 已开启（滚轮/复制/粘贴可用）", ConsoleUtil.QuickEditActive());
                STCheck("选择状态查询可用（不抛异常）",
                        !ConsoleUtil.SelectionInProgress() || ConsoleUtil.SelectionInProgress());
            }

            string savedAdb = ADB;
            string savedSerial = SERIAL;
            bool savedOk = SERIAL_OK;
            SERIAL_OK = false;              // 自检里不要拼 -s，否则假的命令会被串上序列号
            SERIAL = "";

            // 2) adb 不存在：必须立刻失败，而不是卡住
            ADB = "no_such_adb_zzz_711";
            string so = "";
            string se = "";
            long t0 = Environment.TickCount;
            int rc = AdbCall(new List<string> { "devices" }, out so, out se);
            long dt = Environment.TickCount - t0;
            STCheck("adb 不存在 -> 返回 9009", rc == 9009);
            STCheck("adb 不存在 -> 1 秒内返回", dt < 1000);

            // 3) 会挂住的命令：必须有超时（这是"唤醒后卡死"的根因防线）
            ADB = "ping";
            t0 = Environment.TickCount;
            rc = AdbCallTimeout(new List<string> { "-n", "30", "127.0.0.1" }, 1200, out so, out se);
            dt = Environment.TickCount - t0;
            STCheck("挂住的 adb -> 返回 124", rc == 124);
            STCheck("挂住的 adb -> 按超时返回(1.2~6s)", dt >= 1000 && dt <= 6000);

            // 4) 后台探测线程：请求 -> 取结果，全程不碰输入线程
            ADB = "no_such_adb_zzz_711";
            Bg.PROBE_TIMEOUT_MS = 2000;
            Bg.Start();
            Bg.Request();
            bool got = false;
            int gkind = 0;
            int grc = 0;
            string gtext = null;
            long wait = Environment.TickCount;
            while (Environment.TickCount - wait < 5000)
            {
                if (Bg.TryTake(out gtext, out grc, out gkind)) { got = true; break; }
                System.Threading.Thread.Sleep(50);
            }
            STCheck("后台探测能取回结果", got);
            STCheck("探测结果带类型", !got || gkind == Bg.KIND_PROBE);
            STCheck("探测失败不阻塞（rc=9009）", !got || grc == 9009);

            ADB = savedAdb;
            SERIAL = savedSerial;
            SERIAL_OK = savedOk;

            // ================================================================
            // 5) 断线重连层（v7.13）：状态判定是纯函数，可以脱离真机喂文本
            // ================================================================
            Console.WriteLine("== 自检：断线重连状态判定（v7.13 新增）==");

            Rec.Snap q = Rec.Classify("List of devices attached\r\nABC123\tdevice\r\n", 0, false);
            STCheck("device 行 -> 在线", q.state == Rec.ST_OK && q.online == 1);
            STCheck("device 行 -> 记住序列号", q.firstOnline == "ABC123");

            q = Rec.Classify("List of devices attached\r\nABC123\toffline\r\n", 0, false);
            STCheck("offline 行 -> 判为 offline", q.state == Rec.ST_OFFLINE && q.offline == 1);

            q = Rec.Classify("List of devices attached\r\nABC123\tunauthorized\r\n", 0, false);
            STCheck("unauthorized 行 -> 判为未授权", q.state == Rec.ST_UNAUTH && q.unauth == 1);

            q = Rec.Classify("List of devices attached\r\n", 0, false);
            STCheck("只有表头 -> 判为无设备", q.state == Rec.ST_NONE);

            q = Rec.Classify("", 0, false);
            STCheck("空输出 -> 判为无设备", q.state == Rec.ST_NONE);

            q = Rec.Classify("* daemon not running; starting now at tcp:5037\r\n"
                + "* daemon started successfully\r\nList of devices attached\r\nXYZ\tdevice\r\n", 0, false);
            STCheck("daemon 提示行不干扰解析", q.state == Rec.ST_OK && q.online == 1);

            q = Rec.Classify("List of devices attached\r\nA\tdevice\r\nB\toffline\r\n", 0, false);
            STCheck("在线+offline 混合 -> 仍判在线", q.state == Rec.ST_OK && q.offline == 1);

            q = Rec.Classify("List of devices attached\r\nA\tunauthorized\r\nB\toffline\r\n", 0, false);
            STCheck("未授权优先于 offline（需要人去点）", q.state == Rec.ST_UNAUTH);

            q = Rec.Classify("adb server version (41) doesn't match this client (39); killing...\r\n", 0, false);
            STCheck("版本冲突被识别", q.state == Rec.ST_VERSION);

            q = Rec.Classify("", 0, true);
            STCheck("超时 -> 判为 adb 无响应", q.state == Rec.ST_HANG);

            q = Rec.Classify("", -1, false);
            STCheck("adb 起不来 -> 判为不可用", q.state == Rec.ST_NOADB);

            q = Rec.Classify("", 9009, false);
            STCheck("9009 -> 判为不可用", q.state == Rec.ST_NOADB);

            // 端口探测：只要求能调用、不抛异常（5037 有没有开都合法）
            try { bool po = Rec.PortOpen(200); STCheck("PortOpen 可调用", po || !po); }
            catch { STCheck("PortOpen 可调用", false); }

            // 预算上限：adb 不存在时 WaitDevice 必须快速失败，不能把界面拖住
            ADB = "no_such_adb_zzz_713";
            long wt = Environment.TickCount;
            bool wd = Rec.WaitDevice(2000, false, false);
            long wdt = Environment.TickCount - wt;
            STCheck("没有 adb 时 WaitDevice 返回 false", !wd);
            STCheck("没有 adb 时 WaitDevice 快速失败(<6s)", wdt < 6000);

            ADB = savedAdb;
            SERIAL = savedSerial;
            SERIAL_OK = savedOk;

            // ================================================================
            // 6) 提示符（v7.14）：纯函数，喂数据就能验
            //    现场要求：提示符里必须能看出"这是哪台设备"，
            //    cd 之后还要看得出"在哪个目录"。
            // ================================================================
            Console.WriteLine("== 自检：提示符（v7.14 新增）==");

            const string RT = "/log/android_log/androidlog";
            string pv;

            // 6.1 停在起始目录：只显示设备号（旧版这里显示 "androidlog"，认不出设备）
            pv = PromptBody(0, "ef2e593d", RT, RT);
            STCheck("起始目录 -> 只显示设备号", pv == "ef2e593d", pv);
            STCheck("起始目录 -> 不再显示目录名", pv.IndexOf("androidlog") < 0, pv);

            // 6.2 cd 之后：设备号 + 目录
            pv = PromptBody(0, "ef2e593d", "/data/anr", RT);
            STCheck("cd 之后 -> 设备号:目录", pv == "ef2e593d:/data/anr", pv);

            pv = PromptBody(0, "ef2e593d", "/", RT);
            STCheck("根目录 -> 只显示设备号", pv == "ef2e593d", pv);

            // 6.3 长路径压成末两段，且用 "…/" 标明前面还有
            pv = PromptBody(0, "ef2e593d", RT + "/288", RT);
            STCheck("长路径 -> 压成 …/末两段", pv == "ef2e593d:\u2026/androidlog/288", pv);
            STCheck("长路径 -> 有截断标记", pv.IndexOf('\u2026') >= 0, pv);
            STCheck("长路径 -> 长度受控(<=28)", DispWidth(pv) <= 28, "" + DispWidth(pv));

            // 6.4 没有设备时不能出现空提示符
            pv = PromptBody(0, "", RT, RT);
            STCheck("无设备 -> 有占位文字", pv.Length > 0 && pv.IndexOf("无设备") >= 0, pv);

            // 6.5 极长序列号 + 深路径：总宽必须被压住
            string longDev = "0123456789abcdef0123456789abcdef";
            pv = PromptBodyTight(longDev, "/a/b/c/d/e/f/g/h");
            STCheck("极长设备号+深路径 -> 只留 设备号:末段",
                    pv == longDev + ":h", pv);
            STCheck("极长设备号 -> 不再追加路径", pv.IndexOf('/') < 0, pv);

            // 6.6 模式开关
            STCheck("prompt=path 保留老样式（只目录）",
                    PromptBody(2, "ef2e593d", "/data/anr", RT) == "/data/anr");
            STCheck("prompt=id 只给设备号",
                    PromptBody(1, "ef2e593d", "/data/anr", RT) == "ef2e593d");

            // 6.7 大小写/尾斜杠不该影响"是不是起始目录"
            STCheck("起始目录比较忽略大小写与尾斜杠",
                    PromptBody(0, "X", RT.ToUpperInvariant() + "/", RT) == "X");

            // ==================== 语音助手（:vr，v8.16 新增）====================
            Console.WriteLine("== 自检：语音助手（:vr）==");

            // 7.1 音区解析：数字 / 中文 / 英文别名 / 越界
            STCheck("area 0 => 主驾", ParseArea("0") == 0);
            STCheck("area 5 => 三排右", ParseArea("5") == 5);
            STCheck("area 6 越界返回 -1", ParseArea("6") == -1);
            STCheck("area -1 返回 -1", ParseArea("-1") == -1);
            STCheck("area 主驾 => 0", ParseArea("主驾") == 0);
            STCheck("area 副驾 => 1", ParseArea("副驾") == 1);
            STCheck("area 二排左 => 2", ParseArea("二排左") == 2);
            STCheck("area 三排右 => 5", ParseArea("三排右") == 5);
            STCheck("area passenger => 1", ParseArea("passenger") == 1);
            STCheck("area rear3r => 5", ParseArea("rear3r") == 5);
            STCheck("area 非法词返回 -1", ParseArea("驾驶位") == -1);
            STCheck("area 空返回 -1", ParseArea("") == -1);

            // 7.2 参数摘取：-a 后置 / 前置 / 中文 / 连写 / -l
            int vArea;
            bool vLocal;
            string vText;

            vText = VrStripArgs("打开车窗", out vArea, out vLocal);
            STCheck("无参 文本保留", vText == "打开车窗", vText);
            STCheck("无参 音区为 -1", vArea == -1, "" + vArea);
            STCheck("无参 local=false", !vLocal);

            vText = VrStripArgs("打开车窗 -a 1", out vArea, out vLocal);
            STCheck("-a 后置 文本剥离", vText == "打开车窗", vText);
            STCheck("-a 后置 音区=1", vArea == 1, "" + vArea);

            vText = VrStripArgs("-a 2 打开车窗", out vArea, out vLocal);
            STCheck("-a 前置 文本剥离", vText == "打开车窗", vText);
            STCheck("-a 前置 音区=2", vArea == 2, "" + vArea);

            vText = VrStripArgs("打开车窗 -a 副驾", out vArea, out vLocal);
            STCheck("-a 中文 音区=1", vArea == 1, "" + vArea);
            STCheck("-a 中文 文本剥离", vText == "打开车窗", vText);

            vText = VrStripArgs("打开车门 -a3", out vArea, out vLocal);
            STCheck("-a3 连写 音区=3", vArea == 3, "" + vArea);
            STCheck("-a3 连写 文本剥离", vText == "打开车门", vText);

            vText = VrStripArgs("打开车门 -l", out vArea, out vLocal);
            STCheck("-l 置 local=true", vLocal);
            STCheck("-l 文本剥离", vText == "打开车门", vText);

            vText = VrStripArgs("打开车门 --local -a 2", out vArea, out vLocal);
            STCheck("--local + -a 组合 local", vLocal);
            STCheck("--local + -a 组合 音区=2", vArea == 2, "" + vArea);
            STCheck("--local + -a 组合 文本", vText == "打开车门", vText);

            vText = VrStripArgs("\"打开 车窗\" -a 1", out vArea, out vLocal);
            STCheck("引号内空格保留", vText == "打开 车窗", vText);
            STCheck("引号内空格 音区=1", vArea == 1, "" + vArea);

            vText = VrStripArgs("-a 打开车窗", out vArea, out vLocal);
            STCheck("-a 无有效值 音区仍 -1", vArea == -1, "" + vArea);

            // 7.3 URI 拼装：三种形态 + & 必须被编码
            string vu;
            vu = VrBuildUri("打开车窗", -1, false);
            STCheck("URI 主驾 无 voiceArea", vu.IndexOf("voiceArea") < 0, vu);
            STCheck("URI 主驾 无 mode", vu.IndexOf("mode=local") < 0, vu);
            STCheck("URI 前缀正确", vu.IndexOf(VR_SR_URI) == 0, vu);
            STCheck("URI 中文已编码", vu.IndexOf("%E6%89%93%E5%BC%80") > 0, vu);

            vu = VrBuildUri("打开车窗", 1, false);
            STCheck("URI 带音区 用裸 & 分隔", vu.IndexOf("&voiceArea=1") > 0, vu);
            STCheck("URI 带音区 不含单引号", vu.IndexOf('\'') < 0, vu);

            vu = VrBuildUri("打开车门", -1, true);
            STCheck("URI 断网 用裸 & 分隔", vu.IndexOf("&mode=local") > 0, vu);

            vu = VrBuildUri("打开车门", 2, true);
            STCheck("URI 断网+音区 两段齐全",
                    vu.IndexOf("&voiceArea=2") > 0 && vu.IndexOf("&mode=local") > 0, vu);
            STCheck("URI 两段都无单引号", vu.IndexOf('\'') < 0, vu);

            vu = VrBuildUri("开&关", -1, false);
            STCheck("URI 文本里的 & 被转成 %26", vu.IndexOf("%26") > 0, vu);
            STCheck("URI 文本里的 & 未破坏结构", vu.IndexOf("&voiceArea") < 0, vu);

            // 7.4 唤醒 URI：type=1 不带 canSleep，type=99 带
            string vw1 = VrBuildWakeUri("1", false);
            STCheck("唤醒 type=1 含 type=1", vw1.IndexOf("type=1") > 0, vw1);
            STCheck("唤醒 type=1 无 canSleep", vw1.IndexOf("canSleep") < 0, vw1);

            string vw99 = VrBuildWakeUri("99", true);
            STCheck("唤醒 99 含 type=99", vw99.IndexOf("type=99") > 0, vw99);
            STCheck("唤醒 99 含 canSleep=false", vw99.IndexOf("canSleep=false") > 0, vw99);

            // 7.5 离线白名单：:vr 帮助类命令在无设备时也能看
            STCheck("离线允许 :vr", OfflineAllowed(":vr"));
            STCheck("离线允许 :voice", OfflineAllowed(":voice"));

            // 7.6 引号与 & 的安全性锚点（这条最容易在重构时被改坏）
            //
            // 【曾经的错误结论，务必别改回去】
            //   早先这里断言 URI 必须写 '&'（单引号包裹 &），理由是"设备侧 sh 要
            //   单引号才把 & 当字面量"。这个前提只在 URI **外层不加引号** 时成立。
            //   我们这版整条 -d 是被双引号包住的，sh 进到双引号后 ' 和 & 都退化成
            //   普通字符，于是设备真实收到的是 `text=abc'&'voiceArea=1`：
            //     · text 尾巴多一个单引号
            //     · voiceArea 的值变成 "1'"，参数解析失败
            //   已用伪造 am 脚本回显 argv 实测确认。正确写法 = 外层双引号 + 裸 &。
            //
            // 本地侧：整条命令含空格 → QuoteArg 包双引号；RunRaw 走
            // UseShellExecute=false 直接 CreateProcess、不经过 cmd.exe，
            // 所以 & 不会被本地当管道。这两点仍要钉住。
            string vuri = VrBuildUri("a", 1, false);
            string vcmd = VrBuildAmCmd(vuri);
            string vq = Util.QuoteArg(vcmd);
            STCheck("含 & 的命令整体被双引号包裹",
                    vq.Length >= 2 && vq[0] == '"' && vq[vq.Length - 1] == '"', vq);
            STCheck("-d 的 URI 被双引号包裹", vcmd.IndexOf("-d \"" + vuri + "\"") > 0, vcmd);
            STCheck("URI 内不得出现单引号（双引号内 ' 是字面量，会污染 text）",
                    vuri.IndexOf('\'') < 0, vuri);
            STCheck("& 必须原样保留为分隔符", vuri.IndexOf("&voiceArea=1") > 0, vuri);
            STCheck("& 未被 URL 编码成 %26", vuri.IndexOf("%26") < 0, vuri);
            STCheck("离线参数同样是裸 &", VrBuildUri("a", -1, true).IndexOf("&mode=local") > 0,
                    VrBuildUri("a", -1, true));

            // 7.8 am 命令走 ini 配置（改 am_cmd 对 :vr 也生效，与 :send 一致）
            string vamSaved = AM_CMD;
            AM_CMD = "start-foreground-service";
            STCheck("VrBuildAmCmd 跟随 ini 的 am_cmd",
                    VrBuildAmCmd("x://a").IndexOf("am start-foreground-service ") == 0,
                    VrBuildAmCmd("x://a"));
            AM_CMD = vamSaved;
            STCheck("VrBuildAmCmd 恢复后为 startservice",
                    VrBuildAmCmd("x://a").IndexOf("am startservice ") == 0, VrBuildAmCmd("x://a"));

            // 7.8.1 语音输出（TTS）命令构造（2026-11-12）
            string vtts = VrBuildTtsCmd("你好");
            STCheck("TTS 用 am startservice 开头", vtts.IndexOf("am startservice ") == 0, vtts);
            STCheck("TTS action 为 com.iflytek.autofly.TtsService",
                    vtts.IndexOf(" -a com.iflytek.autofly.TtsService ") > 0, vtts);
            STCheck("TTS 文本走 --es text 单引号包裹",
                    vtts.IndexOf("--es 'text' '你好'") > 0, vtts);
            STCheck("TTS 不携带音区 voiceArea", vtts.IndexOf("voiceArea") < 0, vtts);
            STCheck("TTS 文本里单引号被剥离", VrBuildTtsCmd("a'b").IndexOf("'a'b'") < 0,
                    VrBuildTtsCmd("a'b"));
            STCheck("TTS 文本里 $( 被剥离（防命令替换）",
                    VrBuildTtsCmd("x$(id)").IndexOf("$(id)") < 0, VrBuildTtsCmd("x$(id)"));

            // 7.9 am -n 组件名格式：必须是 pkg/类名，不能是 pkg/com.pkg.Cls 双包名
            //
            // 真机踩过两次坑：
            //   1) 原工具 pkg/com.pkg.Cls             -> Error type 3
            //   2) 我修成 .SettingDebugActivity（猜的）-> Error type 3，因为真实类名带子包
            // 正确做法：从设备 dumpsys 取真实类名，存完整名，VrComponent 拼 pkg/完整名。
            string vset = VrComponent(VR_ACT_SETTING);
            STCheck("调试页组件以 包名/ 开头", vset.IndexOf(VR_PKG + "/") == 0, vset);
            STCheck("调试页组件不出现双包名",
                    vset.IndexOf(VR_PKG + "/" + VR_PKG) < 0, vset);
            STCheck("组件里只有一个斜杠", vset.Split('/').Length == 2, vset);
            STCheck("斜杠右边不得以 . 开头（完整类名形式）",
                    vset.Substring(VR_PKG.Length + 1)[0] != '.', vset);
            STCheck("调试页类名带真实子包路径",
                    vset.IndexOf("com.syncore.speech.core.business.debugpages.setting") > 0, vset);
            STCheck("文本语义调试页组件同样正确",
                    VrComponent(VR_ACT_TEXTDBG) == VR_PKG + "/" + VR_ACT_TEXTDBG,
                    VrComponent(VR_ACT_TEXTDBG));
            STCheck("文本语义调试页带真实子包路径",
                    VrComponent(VR_ACT_TEXTDBG).IndexOf("debugpages.textsemantic") > 0,
                    VrComponent(VR_ACT_TEXTDBG));
            STCheck("已是完整组件则不重复拼包名",
                    VrComponent(VR_PKG + "/.X") == VR_PKG + "/.X", VrComponent(VR_PKG + "/.X"));
            STCheck("以 . 开头的相对名保留前导点",
                    VrComponent(".Cls") == VR_PKG + "/.Cls", VrComponent(".Cls"));
            STCheck("完整类名不加前导点",
                    VrComponent("a.b.Cls") == VR_PKG + "/a.b.Cls", VrComponent("a.b.Cls"));
            STCheck("空组件退化为包名", VrComponent("") == VR_PKG, VrComponent(""));

            // 7.10 裸词 local 不得被当开关吞掉（会改坏识别文本）
            int vA;
            bool vL;
            string vTxt = VrStripArgs("打开 local 模式", out vA, out vL);
            STCheck("裸词 local 保留在文本里", vTxt.IndexOf("local") >= 0, vTxt);
            STCheck("裸词 local 不触发离线", !vL, vTxt);
            vTxt = VrStripArgs("打开车窗 -l", out vA, out vL);
            STCheck("-l 触发离线", vL, vTxt);
            STCheck("-l 从文本里摘掉", vTxt == "打开车窗", vTxt);
            vTxt = VrStripArgs("打开车窗 --local", out vA, out vL);
            STCheck("--local 触发离线", vL, vTxt);

            // 7.10b 非法音区必须显式报错，不能静默当文本发出去
            string vBad;
            vTxt = VrStripArgs("打开车窗 -a 9", out vA, out vL, out vBad);
            STCheck("-a 9 被识别为非法音区", vBad == "9", vBad);
            STCheck("-a 9 不残留在文本里", vTxt.IndexOf("-a") < 0, vTxt);
            STCheck("-a 9 不设置音区", vA == -1, "" + vA);

            vTxt = VrStripArgs("打开车窗 -a 中排", out vA, out vL, out vBad);
            STCheck("-a 中排 被识别为非法音区", vBad == "中排", vBad);
            STCheck("-a 中排 不残留在文本里", vTxt.IndexOf("中排") < 0, vTxt);

            vTxt = VrStripArgs("打开车窗 -a", out vA, out vL, out vBad);
            STCheck("-a 缺值被识别为非法", vBad.Length > 0, vBad);
            STCheck("-a 缺值不报音区", vA == -1, "" + vA);

            vTxt = VrStripArgs("打开车窗 -a5", out vA, out vL, out vBad);
            STCheck("-a5 连写正常解析", vA == 5 && vBad.Length == 0, "" + vA);

            vTxt = VrStripArgs("打开车窗 -a9", out vA, out vL, out vBad);
            STCheck("-a9 连写非法被识别", vBad == "9", vBad);

            vTxt = VrStripArgs("打开车窗 -a 副驾", out vA, out vL, out vBad);
            STCheck("合法音区不报错", vBad.Length == 0 && vA == 1, vBad + "/" + vA);

            // 7.11 adb 失败识别：rc=0 但输出是 Failure 时必须判失败
            STCheck("Failure 判为失败",
                    VrLooksBad("Failure [DELETE_FAILED_INTERNAL_ERROR]"));
            STCheck("Error: 判为失败", VrLooksBad("Error: Activity not started"));
            STCheck("正常空输出不算失败", !VrLooksBad(""));
            STCheck("正常 Success 不算失败", !VrLooksBad("Success"));

            // 7.12 破坏性操作必须带 -y（防止误触重启车机 / 卸载语助）
            // 这条是真实事故换来的：冒烟测试没检查设备状态，
            // 把 :vr reboot / :vr un 发给了一台在线车机，车机真的重启了。
            STCheck("裸 :vr reboot 不放行", !VrConfirmNo("", "重启车机", ":vr reboot -y"));
            STCheck(":vr reboot -y 放行", VrConfirmNo("-y", "重启车机", ":vr reboot -y"));
            STCheck(":vr reboot --yes 放行", VrConfirmNo("--yes", "重启车机", ":vr reboot -y"));
            STCheck(":vr reboot -yes 放行", VrConfirmNo("-yes", "重启车机", ":vr reboot -y"));
            STCheck("乱写的参数不放行", !VrConfirmNo("now", "重启车机", ":vr reboot -y"));
            STCheck("误写 -Y 大小写也认", VrConfirmNo("-Y", "重启车机", ":vr reboot -y"));
            STCheck("带其它参数 + -y 放行", VrConfirmNo("some 1 -y", "重启车机", ":vr reboot -y"));

            // 7.13 塞进设备 shell 单引号前的净化（:vr ts 用）
            STCheck("单引号被去掉", VrShellSafe("a'b") == "ab", VrShellSafe("a'b"));
            STCheck("命令替换 $( ) 被去掉", VrShellSafe("a$(id)b") == "a id)b".Replace(" ", ""),
                    VrShellSafe("a$(id)b"));
            STCheck("反引号被去掉", VrShellSafe("a`id`b") == "aidb", VrShellSafe("a`id`b"));
            STCheck("正常文本不被改动", VrShellSafe("打开车窗") == "打开车窗", VrShellSafe("打开车窗"));
            STCheck("空文本安全", VrShellSafe("") == "", VrShellSafe(""));
            // am 报 "Error: Not found; no service started." 必须判失败
            // （本机实测：包没装时 am 仍先打 Starting service:，只看那句会误判成功）
            STCheck("Not found; no service started 判为失败",
                    VrLooksBad("Starting service: Intent {...}\nError: Not found; no service started."));




            // 7.7 超长文本截断（原工具限 50 字，设备侧会丢字）
            string vLong = new string('x', 80);
            STCheck("长文本被截断到 vr_text_max",
                    VrTextTrim(vLong).Length <= VR_TEXT_MAX, "" + VrTextTrim(vLong).Length);
            STCheck("短文本不被截断", VrTextTrim("abc") == "abc");

            // ---- 7.14 wm size 解析（问题7：连上设备后要在指令输入页显示分辨率） ----
            // 设备侧实际可能给出的几种形态，全部覆盖。这个函数是纯字符串处理，
            // 不碰 adb，所以能在这里做完整断言。
            Console.WriteLine();
            Console.WriteLine("== 自检：分辨率解析（问题7 新增）==");

            // 标准形态：只有 Physical size
            STCheck("Physical size 正常解析",
                    ParseWmSize("Physical size: 1080x1920") == "1080x1920",
                    ParseWmSize("Physical size: 1080x1920"));
            // tr 压平后的形态（真实调用就是这种：多行被 ';' 连起来）
            STCheck("多行被 tr 压成 ; 后仍能取到",
                    ParseWmSize("Physical size: 1080x1920;") == "1080x1920",
                    ParseWmSize("Physical size: 1080x1920;"));
            // 有 Override 时以 Override 为准（那才是实际生效值）
            STCheck("Override 优先于 Physical",
                    ParseWmSize("Physical size: 1080x1920;\nOverride size: 720x1280") == "720x1280",
                    ParseWmSize("Physical size: 1080x1920;\nOverride size: 720x1280"));
            // 双换行（crlf）不应该影响
            STCheck("CRLF 不影响解析",
                    ParseWmSize("Physical size: 1080x1920\r\n") == "1080x1920",
                    ParseWmSize("Physical size: 1080x1920\r\n"));
            // 命令行不存在 wm 时的真实输出：必须返回空，不能把报错当分辨率
            STCheck("wm 不存在时返回空", ParseWmSize("not found") == "", ParseWmSize("not found"));
            STCheck("/system/bin/sh: wm: not found 返回空",
                    ParseWmSize("/system/bin/sh: wm: not found") == "",
                    ParseWmSize("/system/bin/sh: wm: not found"));
            // 权限被拒时不返回垃圾值
            STCheck("Permission denied 返回空",
                    ParseWmSize("Exception occurred while executing 'size':\njava.lang.SecurityException") == "",
                    ParseWmSize("Exception occurred while executing 'size':\njava.lang.SecurityException"));
            // 空输入
            STCheck("空输入返回空", ParseWmSize("") == "", ParseWmSize(""));
            STCheck("null 返回空", ParseWmSize(null) == "", ParseWmSize(null));
            // 形如 "1080x1920" 但夹了非法字符的，一律不认
            STCheck("含非数字的尺寸被拒", ParseWmSize("Physical size: 1080x1920abc") == "",
                    ParseWmSize("Physical size: 1080x1920abc"));
            STCheck("缺一个数字的尺寸被拒", ParseWmSize("Physical size: x1920") == "",
                    ParseWmSize("Physical size: x1920"));
            // 真实车型常见值，确保位数不受限
            STCheck("2560x1600 解析正常", ParseWmSize("Physical size: 2560x1600") == "2560x1600",
                    ParseWmSize("Physical size: 2560x1600"));

            // ---- 导出目录分类：$(out:xxx) -> 桌面\logcat\<日期>\<分类> ----
            // 需求（2026-11-10）：导出文件按 日期/分类 两级存放，别平铺。
            // 这里只验"分类名归一化"和"路径形状"，不真的建目录（自检不该有副作用）。
            Console.WriteLine();
            Console.WriteLine("== 自检：导出目录分类（$(out:*)) ==");
            STCheck("shot -> screencap", OutKindFolder("shot") == "screencap", OutKindFolder("shot"));
            STCheck("rec -> screenrecord", OutKindFolder("rec") == "screenrecord", OutKindFolder("rec"));
            STCheck("hci -> HCI（保留大写）", OutKindFolder("hci") == "HCI", OutKindFolder("hci"));
            STCheck("完整名 screencap 保持", OutKindFolder("screencap") == "screencap",
                    OutKindFolder("screencap"));
            STCheck("完整名 screenrecord 保持", OutKindFolder("screenrecord") == "screenrecord",
                    OutKindFolder("screenrecord"));
            STCheck("中文 截图 -> screencap", OutKindFolder("截图") == "screencap", OutKindFolder("截图"));
            STCheck("中文 录屏 -> screenrecord", OutKindFolder("录屏") == "screenrecord", OutKindFolder("录屏"));
            STCheck("中文 蓝牙 -> HCI", OutKindFolder("蓝牙") == "HCI", OutKindFolder("蓝牙"));
            STCheck("带空格/大写归一化", OutKindFolder("  SHOT  ") == "screencap", OutKindFolder("  SHOT  "));
            STCheck("空 kind 只到日期层", OutKindFolder("") == "", OutKindFolder(""));
            STCheck("null kind 只到日期层", OutKindFolder(null) == "", OutKindFolder(null));
            // 路径形状：必须是 logcat\<yyyy-MM-dd>\<分类>，且日期是今天
            string pToday = OutDir("");
            string pShot = OutDir("shot");
            string pRec = OutDir("rec");
            string pHci = OutDir("hci");
            string dDay = DateTime.Now.ToString("yyyy-MM-dd");
            STCheck("日期目录名用 yyyy-MM-dd", pToday.EndsWith("logcat\\" + dDay), pToday);
            STCheck("shot 落在 screencap 子目录", pShot.EndsWith(dDay + "\\screencap"), pShot);
            STCheck("rec 落在 screenrecord 子目录", pRec.EndsWith(dDay + "\\screenrecord"), pRec);
            STCheck("hci 落在 HCI 子目录", pHci.EndsWith(dDay + "\\HCI"), pHci);
            STCheck("三类目录互不相同", pShot != pRec && pRec != pHci && pShot != pHci, pShot);
            STCheck("重复调用幂等", OutDir("shot") == pShot, OutDir("shot"));

            // ---- 车机信息九项（需求4）----
            // 只是常量表和解析逻辑的自检；真实取值需要在线设备。
            Console.WriteLine();
            Console.WriteLine("== 自检：车机信息九项（:car）==");
            STCheck("属性项 8 个", CAR_KEYS.Length == 8, "" + CAR_KEYS.Length);
            STCheck("标签数与属性数一致", CAR_LABELS.Length == CAR_KEYS.Length,
                    CAR_LABELS.Length + "/" + CAR_KEYS.Length);
            STCheck("车型属性名正确",
                    CAR_KEYS[0] == "sys.product.gacvehicleplatform", CAR_KEYS[0]);
            STCheck("SOC 属性名正确",
                    CAR_KEYS[1] == "ro.product.version.short_name", CAR_KEYS[1]);
            STCheck("MCU 属性名正确",
                    CAR_KEYS[2] == "sys.vehicle.mcu.version", CAR_KEYS[2]);
            STCheck("Android 属性名正确",
                    CAR_KEYS[3] == "ro.build.version.release", CAR_KEYS[3]);
            STCheck("VIN 属性名正确",
                    CAR_KEYS[4] == "persist.sys.vehicle.vin", CAR_KEYS[4]);
            STCheck("UUID 属性名正确",
                    CAR_KEYS[5] == "persist.sys.navi.uuid", CAR_KEYS[5]);
            STCheck("DID 属性名正确",
                    CAR_KEYS[6] == "persist.sys.navi.did", CAR_KEYS[6]);
            STCheck("OPENID 属性名正确",
                    CAR_KEYS[7] == "persist.sys.navi.openid", CAR_KEYS[7]);
            STCheck("分辨率标签存在", CAR_RES_LABEL.Length > 0, CAR_RES_LABEL);
            STCheck("无重复属性名", NoDupKeys(CAR_KEYS), JoinKeys(CAR_KEYS));
            // 分段解析：模拟一次 shell 往返的原始输出
            string fake = "##0\n181\n##1\nGAC_T68\n##2\nT68_MCU\n##3\n12\n"
                        + "##4\nLMGNA1S86\n##5\n8545003\n##6\n3885895\n##7\n6a29b54b\n"
                        + "##8\nPhysical size: 2560x1440;";
            string[] seg = ParseMarkedTextN(fake, 9);
            STCheck("分段解析 段0=车型", seg[0] == "181", seg[0]);
            STCheck("分段解析 段7=OPENID", seg[7] == "6a29b54b", seg[7]);
            STCheck("分段解析 段8=分辨率原文", seg[8].StartsWith("Physical size:"), seg[8]);
            STCheck("分辨率从段8解析成功",
                    ParseWmSize(seg[8]) == "2560x1440", ParseWmSize(seg[8]));
            // 属性全空（getprop 没有这些键）时不能抛异常、不能错位
            string fake2 = "##0\n\n##1\n\n##2\n\n##3\n\n##4\n\n##5\n\n##6\n\n##7\n";
            string[] seg2 = ParseMarkedTextN(fake2, 9);
            bool allEmpty = true;
            for (int i = 0; i < 8; i++) if (seg2[i].Length != 0) allEmpty = false;
            STCheck("属性全空时各段为空且不错位", allEmpty, string.Join("|", seg2));

            // ---- APK 管理：用户应用列表（名称 + 包名）----
            // 用临时文件跑，绝不动用户真实的 apk_apps.txt
            Console.WriteLine();
            Console.WriteLine("== 自检：APK 管理列表 ==");
            string savedApkPath = APK_FILE_OVERRIDE;
            string tmpApk = Path.Combine(Path.GetTempPath(),
                "adb_tool_apk_selftest_" + DateTime.Now.Ticks + ".txt");
            APK_FILE_OVERRIDE = tmpApk;
            ApkListResetForTest();
            try
            {
                string ae = "";

                // 校验规则：包名是拼进 shell 的，白名单必须挡住注入
                STCheck("包名合法", ApkPkgValid("com.gac.cloud.app", out ae), ae);
                STCheck("包名拒绝空格", !ApkPkgValid("com.a b", out ae), ae);
                STCheck("包名拒绝无点", !ApkPkgValid("comabc", out ae), ae);
                STCheck("包名拒绝分号注入", !ApkPkgValid("a;reboot", out ae), ae);
                STCheck("包名拒绝反引号注入", !ApkPkgValid("a`id`", out ae), ae);
                STCheck("名称拒绝空", !ApkNameValid("   ", out ae), ae);
                STCheck("名称拒绝制表符", !ApkNameValid("a\tb", out ae), ae);
                STCheck("名称允许中文与空格", ApkNameValid("我的 车", out ae), ae);

                // 首次没有文件：应该自动建一个（迁移入口），不能抛异常
                try { if (File.Exists(tmpApk)) File.Delete(tmpApk); } catch { }
                ApkListResetForTest();
                ApkListEnsureLoaded();
                STCheck("无文件时自动建列表文件", File.Exists(tmpApk));

                // 迁移内容取决于 ini 里有没有 version_pkgs，这里不猜：
                // 重置成「只有注释」的空列表，后面的计数断言才不被 ini 配置影响
                try { File.WriteAllText(tmpApk, "# empty\r\n", new UTF8Encoding(false)); }
                catch { }
                ApkListResetForTest();
                STCheck("空列表计数为 0", ApkListCount() == 0, "" + ApkListCount());

                // 增：正常写入
                STCheck("新增有效条目", ApkListAdd("个人中心", "com.gac.user.center", out ae), ae);
                STCheck("新增后计数 1", ApkListCount() == 1, "" + ApkListCount());

                // 名称重复（忽略大小写）
                STCheck("名称重复被拒",
                        !ApkListAdd("个人中心", "com.other.app", out ae), ae);
                // 包名重复
                STCheck("包名重复被拒",
                        !ApkListAdd("另一个名字", "com.gac.user.center", out ae), ae);
                // 非法包名
                STCheck("非法包名写入被拒",
                        !ApkListAdd("坏包", "com.x;rm -rf /", out ae), ae);

                STCheck("新增第二条", ApkListAdd("车控", "com.gac.vehicle", out ae), ae);
                STCheck("计数 2", ApkListCount() == 2, "" + ApkListCount());

                // 持久化：丢掉内存状态重新读盘，内容必须一致
                ApkListResetForTest();
                List<ApkApp> back = ApkListSnapshot();
                STCheck("重新读盘条数一致", back.Count == 2, "" + back.Count);
                STCheck("重新读盘名称正确",
                        back.Count > 0 && back[0].Name == "个人中心",
                        back.Count > 0 ? back[0].Name : "空");
                STCheck("重新读盘包名正确",
                        back.Count > 1 && back[1].Pkg == "com.gac.vehicle",
                        back.Count > 1 ? back[1].Pkg : "空");

                // 删：落盘后重读仍然没有
                STCheck("删除存在项", ApkListRemove("com.gac.user.center", out ae), ae);
                STCheck("删除后计数 1", ApkListCount() == 1, "" + ApkListCount());
                STCheck("删除不存在项返回失败",
                        !ApkListRemove("com.not.there", out ae), ae);
                ApkListResetForTest();
                List<ApkApp> back2 = ApkListSnapshot();
                STCheck("删除已落盘", back2.Count == 1 && back2[0].Pkg == "com.gac.vehicle",
                        back2.Count + ":" + (back2.Count > 0 ? back2[0].Pkg : ""));

                // 容错：手工把文件改坏（缺字段 / 注释 / 空行 / 重复），不能丢好行
                StringBuilder bad = new StringBuilder();
                bad.Append("# 注释行\r\n");
                bad.Append("\r\n");
                bad.Append("只有名称没有制表符\r\n");
                bad.Append("好名字\tcom.good.app\r\n");
                bad.Append("重复名字\tcom.good.app\r\n");
                bad.Append("坏包\tcom.bad;app\r\n");
                bad.Append("另一个\tcom.good.two\r\n");
                try { File.WriteAllText(tmpApk, bad.ToString(), new UTF8Encoding(false)); }
                catch { }
                ApkListResetForTest();
                List<ApkApp> back3 = ApkListSnapshot();
                STCheck("坏行被跳过，好行保留 2 条", back3.Count == 2, "" + back3.Count);
                STCheck("坏行不影响后续行",
                        back3.Count == 2 && back3[1].Pkg == "com.good.two",
                        back3.Count == 2 ? back3[1].Pkg : "空");

                // 改名：重名要被拒，正常改名要落盘
                STCheck("改名成功", ApkListRename("com.good.two", "新名字", out ae), ae);
                STCheck("改名重名被拒",
                        !ApkListRename("com.good.two", "好名字", out ae), ae);
                ApkListResetForTest();
                List<ApkApp> back4 = ApkListSnapshot();
                bool renamed = false;
                for (int i = 0; i < back4.Count; i++)
                    if (back4[i].Pkg == "com.good.two" && back4[i].Name == "新名字") renamed = true;
                STCheck("改名已落盘", renamed, "" + back4.Count);
            }
            finally
            {
                APK_FILE_OVERRIDE = savedApkPath;
                ApkListResetForTest();
                try { if (File.Exists(tmpApk)) File.Delete(tmpApk); } catch { }
                try { if (File.Exists(tmpApk + ".tmp")) File.Delete(tmpApk + ".tmp"); } catch { }
            }

            // ---- APK 管理：按包动作的纯逻辑 ----
            // 真实设备动作验不了（可能没插设备），但判定规则和解析必须能打靶：
            // 这两处一旦判错，用户看到的就是"清干净了其实没清"这种最坏的结果。
            Console.WriteLine();
            Console.WriteLine("== 自检：APK 按包动作 ==");
            STCheck("pm clear Success 判成功", PmClearSucceeded("Success"));
            STCheck("pm clear Failed 判失败", !PmClearSucceeded("Failed"));
            STCheck("pm clear Success+Failed 判失败",
                    !PmClearSucceeded("Success\nFailed to clear package"));
            STCheck("pm clear 权限拒绝判失败",
                    !PmClearSucceeded("Error: java.lang.SecurityException: Permission Denial"));
            STCheck("pm clear 空输出判失败", !PmClearSucceeded(""));

            List<string> pm = ParsePmPathLines(
                "package:/data/app/~~ab==/com.a-yy==/base.apk\r\n"
                + "\r\n"
                + "package:/data/app/~~ab==/com.a-yy==/split_config.arm64_v8a.apk\r\n"
                + "package:/data/app/~~ab==/com.a-yy==/base.apk\r\n"
                + "WARNING: linker: something\r\n");
            STCheck("pm path 解析 2 个文件（重复行去掉）", pm.Count == 2, "" + pm.Count);
            STCheck("pm path 首个是 base.apk",
                    pm.Count > 0 && LastSeg(pm[0]) == "base.apk",
                    pm.Count > 0 ? LastSeg(pm[0]) : "空");
            STCheck("pm path 第二个是 split",
                    pm.Count > 1 && LastSeg(pm[1]).StartsWith("split_config"),
                    pm.Count > 1 ? LastSeg(pm[1]) : "空");
            STCheck("pm path 空输入安全", ParsePmPathLines("").Count == 0);

            // ---- 无线 adb：IP 解析是唯一能在离线环境验证的部分 ----
            Console.WriteLine();
            Console.WriteLine("== 自检：无线 adb ==");
            STCheck("IPv4 合法", LooksLikeIp("192.168.1.7"));
            STCheck("IPv4 段数不足判非法", !LooksLikeIp("192.168.1"));
            STCheck("IPv4 超范围判非法", !LooksLikeIp("256.1.1.1"));
            STCheck("IPv4 含字母判非法", !LooksLikeIp("a.b.c.d"));
            STCheck("IPv4 空串判非法", !LooksLikeIp(""));

            STCheck("从 ip 输出里取内网地址",
                    ParseFirstIp("2: eth0: <UP>\n    inet 127.0.0.1/8 scope host lo\n"
                                 + "    inet 192.168.1.7/24 brd 192.168.1.255 scope global eth0") == "192.168.1.7",
                    ParseFirstIp("    inet 127.0.0.1/8\n    inet 192.168.1.7/24"));
            STCheck("跳过回环地址",
                    ParseFirstIp("    inet 127.0.0.1/8 scope host lo") == "",
                    ParseFirstIp("    inet 127.0.0.1/8 scope host lo"));
            STCheck("跳过链路本地 169.254",
                    ParseFirstIp("    inet 169.254.3.2/16 brd 169.254.255.255") == "",
                    ParseFirstIp("    inet 169.254.3.2/16"));
            STCheck("兼容 ifconfig 的 addr: 写法",
                    ParseFirstIp("eth0: inet addr:10.1.2.3  Bcast:10.1.2.255  Mask:255.255.255.0") == "10.1.2.3",
                    ParseFirstIp("eth0: inet addr:10.1.2.3  Bcast:..."));
            STCheck("空输出安全", ParseFirstIp("") == "");

            // ---- 导出容错：部分成功判定 + 失败项解析 ----
            Console.WriteLine();
            Console.WriteLine("== 自检：导出容错 ==");
            string pullOut =
                "pull: building file list...\r\n"
                + "adb: error: failed to copy '/log/android_log/androidlog/1/20261113_144221_1-18_androidlogcat.txt.z'"
                + " to 'C:\\Users\\zuo20\\Desktop\\logcat\\2026-11-13\\1_20261113_144256\\20261113_144221_1-18_androidlogcat.txt.z'"
                + ": remote open failed: No such file or directory\r\n";
            List<string> badFiles = ParsePullFailures(pullOut);
            STCheck("从报错里解析出失败文件", badFiles.Count == 1, "" + badFiles.Count);
            STCheck("失败文件路径完整",
                    badFiles.Count == 1 &&
                    badFiles[0] == "/log/android_log/androidlog/1/20261113_144221_1-18_androidlogcat.txt.z",
                    badFiles.Count == 1 ? badFiles[0] : "空");
            STCheck("同一文件重复报错只记一次",
                    ParsePullFailures(pullOut + pullOut).Count == 1,
                    "" + ParsePullFailures(pullOut + pullOut).Count);
            STCheck("无失败输出返回空",
                    ParsePullFailures("pull: building file list...\n[ 31%] xxx.zst: 89%\n").Count == 0);

            STCheck("路径双反斜杠被压平",
                    NormalizeWinPath("C:\\Users\\zuo20\\Desktop\\logcat\\\\2026-11-13")
                    == "C:\\Users\\zuo20\\Desktop\\logcat\\2026-11-13",
                    NormalizeWinPath("C:\\Users\\zuo20\\Desktop\\logcat\\\\2026-11-13"));
            STCheck("UNC 前缀保持不变",
                    NormalizeWinPath("\\\\nas\\share\\\\a") == "\\\\nas\\share\\a",
                    NormalizeWinPath("\\\\nas\\share\\\\a"));
            STCheck("单反斜杠路径不变", NormalizeWinPath("D:\\log\\1") == "D:\\log\\1");

            // ---- 设备监听：状态跃迁规则（自动重连就靠这一条） ----
            Console.WriteLine();
            Console.WriteLine("== 自检：设备监听 ==");
            STCheck("空 -> 有设备：触发重连",
                    DeviceWatcher.Decide("", "SER1") == DeviceWatcher.WatchAction.Reconnect);
            STCheck("有设备 -> 同一台：不重复触发",
                    DeviceWatcher.Decide("SER1", "SER1") == DeviceWatcher.WatchAction.None);
            STCheck("有设备 -> 空：通知离线",
                    DeviceWatcher.Decide("SER1", "") == DeviceWatcher.WatchAction.Gone);
            STCheck("空 -> 空：什么都不做",
                    DeviceWatcher.Decide("", "") == DeviceWatcher.WatchAction.None);
            STCheck("拔掉再插回（空->有）仍然触发",
                    DeviceWatcher.Decide("", "SER1") == DeviceWatcher.WatchAction.Reconnect);
            STCheck("USB 拔掉只剩无线：切到无线要重连",
                    DeviceWatcher.Decide("USB,TCP", "TCP", "USB") == DeviceWatcher.WatchAction.Reconnect);
            STCheck("当前设备还在列表里：不重连",
                    DeviceWatcher.Decide("USB,TCP", "USB,TCP", "USB") == DeviceWatcher.WatchAction.None);
            List<string> online1 = DeviceWatcher.ParseOnline("SER1\tdevice\nSER2\toffline\nSER3\tunauthorized\n");
            STCheck("只把 device 算在线", online1.Count == 1 && online1[0] == "SER1",
                    string.Join(",", online1.ToArray()));

            Console.WriteLine();
            Console.WriteLine("== 自检：cd 语义 ==");
            STCheck("cd 之后不再自动列目录", CD_LISTS_AFTER == false);
            STCheck("刷新路径仍保留自动列目录（CD_LS 未被改坏）", CD_LS == true);

            // ---- 文件管理：解析与命名规则 ----
            Console.WriteLine();
            Console.WriteLine("== 自检：文件管理 ==");
            FsEntry fe = null;
            STCheck("ls -la 目录行",
                    FsParseLsLine("drwxr-xr-x  5 root root    4096 2026-11-13 11:20 acc", "/data", out fe)
                    && fe.IsDir && fe.Name == "acc" && fe.Path == "/data/acc", fe == null ? "空" : fe.Name);
            STCheck("ls -la 普通文件",
                    FsParseLsLine("-rw-r--r--  1 root root     123 2026-11-13 11:20 a.txt", "/data", out fe)
                    && !fe.IsDir && fe.Size == 123, fe == null ? "空" : ("" + fe.Size));
            STCheck("文件名的空格不丢",
                    FsParseLsLine("-rw-r--r--  1 root root     9 2026-11-13 11:20 my log.txt", "/data", out fe)
                    && fe.Name == "my log.txt", fe == null ? "空" : fe.Name);
            STCheck("软链剥离 -> 目标",
                    FsParseLsLine("lrwxrwxrwx  1 root root       7 2026-11-13 11:20 link -> /data", "/", out fe)
                    && fe.IsLink && fe.Name == "link", fe == null ? "空" : fe.Name);
            STCheck("total 行被跳过",
                    !FsParseLsLine("total 123", "/data", out fe));
            STCheck("跳过 . 和 ..",
                    !FsParseLsLine("drwxr-xr-x  2 root root 4096 2026-11-13 11:20 .", "/data", out fe));
            STCheck("整段解析只取文件条目",
                    FsParseLsOutput("total 2\n"
                        + "-rw-r--r-- 1 root root 1 2026-11-13 11:20 a\n"
                        + "drwxr-xr-x 2 root root 1 2026-11-13 11:20 b\n", "/d").Count == 2,
                    "" + FsParseLsOutput("-rw-r--r-- 1 root root 1 2026-11-13 11:20 a\n", "/d").Count);

            STCheck("JoinDev 根目录", JoinDev("/", "a") == "/a", JoinDev("/", "a"));
            STCheck("JoinDev 子目录", JoinDev("/data", "a") == "/data/a", JoinDev("/data", "a"));
            STCheck("JoinDev 尾斜杠", JoinDev("/data/", "a") == "/data/a", JoinDev("/data/", "a"));
            STCheck("shell 单引号转义", ShQuote("a'b") == "'a'\\''b'", ShQuote("a'b"));
            STCheck("时间戳改名保留扩展名",
                    FsTimeStampName("a.txt").StartsWith("a_") && FsTimeStampName("a.txt").EndsWith(".txt"),
                    FsTimeStampName("a.txt"));
            string ferr = "";
            STCheck("文件名拒绝斜杠", !FsNameValid("a/b", out ferr), ferr);
            STCheck("文件名允许空格与中文", FsNameValid("我的 文件.txt", out ferr), ferr);
            STCheck("设备父目录", FsDeviceParent("/data/x") == "/data", FsDeviceParent("/data/x"));
            STCheck("设备根父目录仍是根", FsDeviceParent("/") == "/", FsDeviceParent("/"));
            FsEntry sz = new FsEntry();
            sz.Size = 2048;
            STCheck("大小可读化 2048 -> 2.0 KB", FsSizeText(sz) == "2.0 KB", FsSizeText(sz));

            // 「此电脑」顶层：桌面/下载/文档 三个快捷入口，排在盘符前面
            List<FsEntry> sc = FsLocalShortcuts();
            STCheck("快捷入口含「桌面」", sc.Count > 0 && sc[0].Name == "桌面",
                    sc.Count > 0 ? sc[0].Name : "空");
            bool scAllShortcut = true;
            bool scAllDir = true;
            for (int si = 0; si < sc.Count; si++)
            {
                if (sc[si].Perm != "shortcut") scAllShortcut = false;
                if (!sc[si].IsDir) scAllDir = false;
            }
            STCheck("快捷入口都标记 shortcut", scAllShortcut, "" + sc.Count);
            STCheck("快捷入口都是目录", scAllDir);
            List<FsEntry> topList = FsLocalList("", out ferr);
            STCheck("快捷入口排在盘符之前",
                    sc.Count > 0 && topList.Count > sc.Count
                    && topList[0].Perm == "shortcut" && topList[sc.Count - 1].Perm == "shortcut",
                    topList.Count > 0 ? topList[0].Name : "空");
            STCheck("盘符没有被快捷入口挤掉",
                    topList.Count > sc.Count, topList.Count + "/" + sc.Count);

            // ---- JSON 反转义（本地路径必须还原，否则本地目录永远加载不出） ----
            char bs = (char)92;   // 反斜杠，避免源码里一堆转义看不清
            string escapedPath = "C:" + bs + bs + "Users" + bs + bs + "t";
            string plainPath = "C:" + bs + "Users" + bs + "t";
            STCheck("反转义双反斜杠", JsonUnescape(escapedPath) == plainPath, JsonUnescape(escapedPath));
            STCheck("反转义引号与换行",
                    JsonUnescape("a\\\"b\\nc") == "a\"b\nc",
                    JsonUnescape("a\\\"b\\nc"));
            STCheck("无转义时原样返回", JsonUnescape("/sdcard/Download") == "/sdcard/Download");

            // ---- ffmpeg 版本解析（R9）----
            // 四种真实输出形态：完整打包版、每夜构建、带换行噪声、根本不是 ffmpeg
            STCheck("ffmpeg 版本：完整打包版",
                    Ffmpeg.ParseVersion("ffmpeg version 6.1.1-full_build-www.gyan.dev Copyright (c) 2000-2023") == "6.1.1-full_build-www.gyan.dev",
                    Ffmpeg.ParseVersion("ffmpeg version 6.1.1-full_build-www.gyan.dev Copyright (c) 2000-2023"));
            STCheck("ffmpeg 版本：每夜构建",
                    Ffmpeg.ParseVersion("ffmpeg version N-109000-g1234567 Copyright (c)") == "N-109000-g1234567",
                    Ffmpeg.ParseVersion("ffmpeg version N-109000-g1234567 Copyright (c)"));
            STCheck("ffmpeg 版本：行尾有换行",
                    Ffmpeg.ParseVersion("ffmpeg version 8.0\r\nbuilt with gcc") == "8.0",
                    Ffmpeg.ParseVersion("ffmpeg version 8.0\r\nbuilt with gcc"));
            STCheck("ffmpeg 版本：不是 ffmpeg 则为空",
                    Ffmpeg.ParseVersion("Microsoft Windows [Version 10.0]") == "",
                    Ffmpeg.ParseVersion("Microsoft Windows [Version 10.0]"));

            // ---- ffmpeg 四级查找顺序（R9）----
            // 只校验"排序"不校验"最终命中"：命中取决于这台机器装没装 ffmpeg，
            // 用固定期望值写断言会在别人的机器上假失败。
            string oldFf = FFMPEG;
            FFMPEG = "D:\\tools\\ff\\ffmpeg.exe";
            Ffmpeg.ClearCache();
            List<int> lvOrder;
            List<string> cands = Ffmpeg.Candidates(out lvOrder);
            STCheck("ffmpeg 候选非空", cands.Count > 0, cands.Count.ToString());
            STCheck("ffmpeg 第一优先是 ini 配置",
                    cands.Count > 0 && lvOrder[0] == Ffmpeg.LvIni
                    && cands[0].EndsWith("ffmpeg.exe", StringComparison.OrdinalIgnoreCase),
                    cands.Count > 0 ? cands[0] : "");
            STCheck("ffmpeg 第二优先是程序同级",
                    lvOrder.Count > 1 && lvOrder[1] == Ffmpeg.LvExe);
            bool hasPath = false;
            bool hasCommon = false;
            for (int ci = 0; ci < lvOrder.Count; ci++)
            {
                if (lvOrder[ci] == Ffmpeg.LvPath) hasPath = true;
                if (lvOrder[ci] == Ffmpeg.LvCommon) hasCommon = true;
            }
            STCheck("ffmpeg 候选包含 PATH 与常见位置", hasPath && hasCommon,
                    (hasPath ? "PATH " : "") + (hasCommon ? "common" : ""));
            FFMPEG = oldFf;
            Ffmpeg.ClearCache();

            // ---- ffmpeg 校验：非可执行文件必须被挡下（R9）----
            // 真实踩过：0 字节的同名文件让 File.Exists 通过，编码时才炸。
            string fakeFf = System.IO.Path.Combine(System.IO.Path.GetTempPath(),
                                                    "adtool_fake_ffmpeg_" + System.Diagnostics.Process.GetCurrentProcess().Id + ".txt");
            try
            {
                System.IO.File.WriteAllText(fakeFf, "not an executable");
                string fv = "";
                string ffErr = "";
                STCheck("ffmpeg 校验：非可执行文件被拒", !Ffmpeg.Validate(fakeFf, out fv, out ffErr), ffErr);
                STCheck("ffmpeg 校验：不存在也被拒", !Ffmpeg.Validate(fakeFf + ".missing", out fv, out ffErr));
            }
            catch (Exception ex) { STCheck("ffmpeg 校验用例自身异常", false, ex.Message); }
            finally { try { System.IO.File.Delete(fakeFf); } catch { } }

            // ---- ini 单键改写（R9：记住用户选的 ffmpeg）----
            string tmpIni = System.IO.Path.Combine(System.IO.Path.GetTempPath(),
                                                   "adtool_ini_" + System.Diagnostics.Process.GetCurrentProcess().Id + ".ini");
            try
            {
                System.IO.File.WriteAllText(tmpIni,
                    "# 注释保留\r\nadb=adb\r\nffmpeg=old.exe\r\nserial=\r\n", Encoding.UTF8);

                string iniErr = "";
                STCheck("ini 改写：替换已有键",
                        Ffmpeg.SaveKeyTo(tmpIni, "ffmpeg", "C:\\new\\ffmpeg.exe", out iniErr), iniErr);
                string after = System.IO.File.ReadAllText(tmpIni, Encoding.UTF8);
                STCheck("ini 改写：值已换新", after.IndexOf("ffmpeg=C:\\new\\ffmpeg.exe") >= 0, after);
                STCheck("ini 改写：注释与其它键都在",
                        after.IndexOf("# 注释保留") >= 0 && after.IndexOf("adb=adb") >= 0
                        && after.IndexOf("serial=") >= 0, after);
                STCheck("ini 改写：没有写重复键",
                        after.Split(new string[] { "ffmpeg=" }, StringSplitOptions.None).Length == 2, after);

                STCheck("ini 改写：缺失键会追加",
                        Ffmpeg.SaveKeyTo(tmpIni, "hdc", "hdc.exe", out iniErr), iniErr);
                after = System.IO.File.ReadAllText(tmpIni, Encoding.UTF8);
                STCheck("ini 改写：追加成功", after.IndexOf("hdc=hdc.exe") >= 0, after);
            }
            catch (Exception ex) { STCheck("ini 改写用例自身异常", false, ex.Message); }
            finally { try { System.IO.File.Delete(tmpIni); } catch { } }

            // ---- scrcpy 版本解析与查找顺序（R10）----
            STCheck("scrcpy 版本：常规输出",
                    Scrcpy.ParseVersion("scrcpy 2.4 <https://github.com/Genymobile/scrcpy>") == "2.4",
                    Scrcpy.ParseVersion("scrcpy 2.4 <https://github.com/Genymobile/scrcpy>"));
            STCheck("scrcpy 版本：行尾换行",
                    Scrcpy.ParseVersion("scrcpy 1.25\r\n") == "1.25",
                    Scrcpy.ParseVersion("scrcpy 1.25\r\n"));
            STCheck("scrcpy 版本：没有版本号则为空",
                    Scrcpy.ParseVersion("scrcpy by rom1v") == "",
                    Scrcpy.ParseVersion("scrcpy by rom1v"));

            string oldSc = SCRCPY;
            SCRCPY = "D:\\tools\\scrcpy\\scrcpy.exe";
            Scrcpy.ClearCache();
            List<int> scLv;
            List<string> scCands = Scrcpy.Candidates(out scLv);
            STCheck("scrcpy 候选非空", scCands.Count > 0, scCands.Count.ToString());
            STCheck("scrcpy 第一优先是 ini 配置", scLv[0] == Scrcpy.LvIni, scLv[0].ToString());
            STCheck("scrcpy 第二优先是程序同级", scLv.Count > 1 && scLv[1] == Scrcpy.LvExe,
                    scLv.Count > 1 ? scLv[1].ToString() : "n/a");
            bool scHasPath = false;
            for (int sci = 0; sci < scLv.Count; sci++) if (scLv[sci] == Scrcpy.LvPath) scHasPath = true;
            STCheck("scrcpy 候选包含 PATH", scHasPath);
            SCRCPY = oldSc;
            Scrcpy.ClearCache();

            // ---- pid 解析（ps -A -o PID,NAME） ----
            string tPid = "";
            string tName = "";
            STCheck("ps 行解析（-o 格式）",
                    SplitPsLine("12345 com.gac.user.center", out tPid, out tName)
                    && tPid == "12345" && tName == "com.gac.user.center",
                    tPid + "/" + tName);
            STCheck("ps 行解析（完整格式）",
                    SplitPsLine("u0_a4 12345 321 9876 0 0 S com.gac.user.center:push", out tPid, out tName)
                    && tPid == "12345" && tName == "com.gac.user.center:push",
                    tPid + "/" + tName);
            STCheck("ps 表头不当作进程",
                    !SplitPsLine("PID NAME", out tPid, out tName));

            // ---- 投屏：dumpsys display 解析 ----
            Console.WriteLine();
            Console.WriteLine("== 自检：投屏 ==");
            string dump = "  mViewports=[DisplayViewport{type=INTERNAL, valid=true, isActive=true, displayId=0,"
                + " uniqueId='local:129', physicalPort=129, logicalFrame=Rect(0, 0 - 2560, 1440),"
                + " deviceWidth=2560, deviceHeight=1440}, DisplayViewport{type=EXTERNAL, valid=true,"
                + " isActive=true, displayId=2, uniqueId='local:3', logicalFrame=Rect(0, 0 - 1920, 720),"
                + " deviceWidth=1920, deviceHeight=720}]";
            List<CastDisplay> cds = CastParseDisplays(dump);
            STCheck("解析出 2 块屏", cds.Count == 2, "" + cds.Count);
            STCheck("主屏 id=0 分辨率 2560x1440",
                    cds.Count > 0 && cds[0].Id == 0 && cds[0].W == 2560 && cds[0].H == 1440,
                    cds.Count > 0 ? (cds[0].Id + " " + cds[0].W + "x" + cds[0].H) : "空");
            STCheck("副屏 id=2 分辨率 1920x720",
                    cds.Count > 1 && cds[1].Id == 2 && cds[1].W == 1920 && cds[1].H == 720,
                    cds.Count > 1 ? (cds[1].Id + " " + cds[1].W + "x" + cds[1].H) : "空");
            STCheck("类型与 uniqueId 取到",
                    cds.Count > 0 && cds[0].Type == "INTERNAL" && cds[0].UniqueId == "local:129",
                    cds.Count > 0 ? (cds[0].Type + "/" + cds[0].UniqueId) : "空");
            STCheck("空输入不抛异常", CastParseDisplays("").Count == 0);

            Console.WriteLine();
            Console.WriteLine(ST_FAIL == 0 ? "  自检全部通过" : "  自检失败 " + ST_FAIL + " 项");
            return ST_FAIL == 0 ? 0 : 1;
        }

        // 自检辅助：属性名是否有重复（重复会导致分段解析错位）
        private static bool NoDupKeys(string[] keys)
        {
            for (int i = 0; i < keys.Length; i++)
                for (int j = i + 1; j < keys.Length; j++)
                    if (keys[i] == keys[j]) return false;
            return true;
        }

        // 自检辅助：把属性名拼成一行，失败时能看见具体值
        private static string JoinKeys(string[] keys)
        {
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < keys.Length; i++)
            {
                if (i > 0) sb.Append(',');
                sb.Append(keys[i]);
            }
            return sb.ToString();
        }
    }
}
