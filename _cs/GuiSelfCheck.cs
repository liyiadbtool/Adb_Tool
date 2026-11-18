// ============================================================================
//  GuiSelfCheck.cs — GUI 自检（2026-11-17 起测**真实界面**）
//
//  为什么重写：
//    A12 之前界面是 WinForms（GuiMain），本文件构造那个窗体、量控件几何，
//    46 条断言都是"顶栏高度 / Tab 互斥 / 反馈窗口占 1/4"这一类。
//    A12 之后界面换成 WebView2 + ui.html，可这个文件一直没跟着改 ——
//    它守的是一个**已经不上阵的窗体**，对用户真正看到的界面零覆盖；
//    还因为其中一条断言要求"本机装了 winget 版 scrcpy"，换台机器必红。
//
//  现在怎么做：
//    1. 不在本文件里造窗体 —— 走真实启动链路（GuiEntry → Embed → GuiBoot →
//       GuiWeb → WebView2 → 加载 ui.html），保证测的就是线上那份。
//    2. 页面就绪后由 GuiWeb 回调 RunOn()，用 ExecuteScriptAsync 在页面里
//       读**计算样式与 DOM**，把关键指标回传成 k=v|k=v。
//    3. 断言这些指标；跑完关窗，退出码 = 是否有失败项。
//
//  为什么测"计算样式"而不是截图比像素：
//    截图比对会随主题/DPI/字体变化，基线只能靠人眼维护；
//    计算样式是确定性的，能进 CI，也能直接指出"哪个令牌没生效"。
//
//  C# 5.0 兼容：不用 $"..." / ?. / out var / 表达式体成员 / nameof。
// ============================================================================
using System;
using System.Collections.Generic;
using System.Text;
using System.Windows.Forms;

namespace AdbLogExport.Gui
{
    internal static class GuiSelfCheck
    {
        private static int _fail = 0;
        private static int _ok = 0;
        private static StringBuilder _log = new StringBuilder();

        // GuiEntry 在 Application.Run 返回后读它当进程退出码
        internal static int ExitCode = 1;

        // ------------------------------------------------------------------
        //  在页面里跑的一段 JS。
        //  只读 DOM / 计算样式 + 调一次 switchTab（验证页签可用），不改业务数据。
        // ------------------------------------------------------------------
        private const string JS = @"
(function(){
  var R=[];
  function P(k,v){ R.push(k+'='+v); }
  function gv(n){ return (getComputedStyle(document.documentElement).getPropertyValue(n)||'').trim(); }
  var de=document.documentElement;
  var sp=document.getElementById('splash');
  var gone=1;
  if(sp){ var cs=getComputedStyle(sp);
    if(cs.display!=='none' && parseFloat(cs.opacity)!==0) gone=0; }
  P('splashGone',gone);
  P('theme',de.getAttribute('data-theme')||'');
  P('accent',gv('--accent'));
  P('fontUi',gv('--font-ui'));
  P('tabs',document.querySelectorAll('.tab').length);
  P('tabActive',document.querySelectorAll('.tab.active').length);
  var ids=['quick','cmd','file','cast','ui','text'],pn=0;
  for(var i=0;i<ids.length;i++){ if(document.getElementById('page-'+ids[i])) pn++; }
  P('pages',pn);
  var seen={},dup=0,all=document.querySelectorAll('[id]');
  for(var j=0;j<all.length;j++){ var id=all[j].id; if(!id) continue;
    if(seen[id]) dup++; else seen[id]=1; }
  P('dupIds',dup);
  var okc=0;
  try{
    for(var t=0;t<ids.length;t++){
      switchTab(ids[t]);
      if(document.querySelectorAll('.page.active').length===1) okc++;
    }
    switchTab('quick');
  }catch(e){}
  P('tabSwitchable',okc);
  P('cards',document.querySelectorAll('.qcard').length);
  P('castCells',document.querySelectorAll('#cast-grid .cast-cell').length);
  // 输出区与输入框只在「终端」页可见；页面隐藏时 getBoundingClientRect 全为 0，
  // 所以必须先切到终端页再量（第一次跑就踩了：ratio=0 / inputW=0）。
  switchTab('cmd');
  var m=document.querySelector('.main'), lb=document.getElementById('logbox-0'), ratio=0;
  if(m&&lb){ var mr=m.getBoundingClientRect(), lr=lb.getBoundingClientRect();
    if(mr.height>0) ratio=lr.height/mr.height; }
  P('logRatio',Math.round(ratio*1000)/1000);
  var inp=document.getElementById('cmd-input-0');
  P('inputW', inp?Math.round(inp.getBoundingClientRect().width):0);
  switchTab('quick');
  P('winRadius', parseFloat(getComputedStyle(document.body,'::after').borderTopLeftRadius)||0);
  var bs=document.getElementById('build-stamp');
  P('buildStamp', bs ? (bs.textContent||'') : '');
  return R.join('|');
})()
";

        // ---------------- 供 GuiWeb 在页面就绪后调用 ----------------

        internal static void RunOn(GuiWeb f)
        {
            _fail = 0;
            _ok = 0;
            _log = new StringBuilder();
            ExitCode = 1;

            Line("== GUI 自检（真实界面：WebView2 + ui.html）==");
            Line("");

            string raw = null;
            f.EvalForSelfCheck(JS, delegate(string r) { raw = r; });

            // 自检工具允许阻塞：等页面把结果算完，最多 10 秒
            long t0 = Environment.TickCount;
            while (raw == null && Environment.TickCount - t0 < 10000)
            {
                Application.DoEvents();
                System.Threading.Thread.Sleep(20);
            }
            if (raw == null)
            {
                Line("  [FAIL] 页面在 10 秒内没有返回自检数据");
                _fail++;
                Finish(f);
                return;
            }

            Dictionary<string, string> m = Parse(Unescape(raw));
            if (m.Count == 0)
            {
                Line("  [FAIL] 自检数据解析失败：" + Trunc(raw, 200));
                _fail++;
                Finish(f);
                return;
            }

            int tabs = Int(m, "tabs"), pages = Int(m, "pages"), dup = Int(m, "dupIds");
            int cards = Int(m, "cards"), cells = Int(m, "castCells");
            int switchable = Int(m, "tabSwitchable"), active = Int(m, "tabActive");
            int inputW = Int(m, "inputW");
            double ratio = Dbl(m, "logRatio"), radius = Dbl(m, "winRadius");
            string theme = Get(m, "theme"), accent = Get(m, "accent"), fontUi = Get(m, "fontUi");

            // ---- 页面装载 ----
            Check("页面加载完成（splash 已退场）", Int(m, "splashGone") == 1,
                  "splashGone=" + Get(m, "splashGone"));
            Check("没有重复 id", dup == 0, "dup=" + dup);

            // ---- 结构 ----
            Check("页签数量为 6", tabs == 6, "tabs=" + tabs);
            Check("默认只有一个页签激活", active == 1, "active=" + active);
            Check("六个页面容器都存在", pages == 6, "pages=" + pages);
            Check("六个页签都能切换（且互斥）", switchable == 6, "switchable=" + switchable + "/6");
            Check("指令卡片已渲染（>=20 张）", cards >= 20, "cards=" + cards);
            Check("投屏区有 6 格", cells == 6, "cells=" + cells);

            // ---- 布局 ----
            Check("输出区占主区 >= 55%", ratio >= 0.55, "ratio=" + ratio.ToString("0.000"));
            Check("输入框宽度 >= 200", inputW >= 200, "inputW=" + inputW);

            // ---- 令牌（主题 / 强调色 / 字体 / 窗口圆角）----
            Check("主题为 dark/light/eye 之一",
                  theme == "dark" || theme == "light" || theme == "eye", "theme=" + theme);
            Check("强调色令牌已解析", LooksLikeColor(accent), "accent=" + Trunc(accent, 40));
            Check("字体令牌已解析且未写坏",
                  fontUi.Length > 0 && fontUi != "undefined", "fontUi=" + Trunc(fontUi, 40));
            Check("窗口内描边圆角 = 8px（与原生窗口一致）",
                  Math.Abs(radius - 8) < 0.6, "radius=" + radius.ToString("0.##"));

            // 版本水印：C# 推 build 消息 → 前端渲染到「关于」。这条链路断了，
            // 现场就无法判断"当前窗口是哪份副本"，所以纳入自检。
            string stamp = Get(m, "buildStamp");
            Check("版本水印已显示（程序时间 / 界面时间）",
                  stamp.IndexOf("程序", StringComparison.Ordinal) >= 0 &&
                  stamp.IndexOf("界面", StringComparison.Ordinal) >= 0,
                  Trunc(stamp, 60));

            // ---- T1（2026-11-18）：GetField 的转义解码 ----
            // 原本是"极简扫描、不解转义"，回显与执行是两个不同来源。这四条把
            // U5-4 的"一个反斜杠显示成两个"和它的两个真实故障一起钉死。
            string bs = "\\";
            string q1 = GuiWeb.GetField(
                "{\"c\":\"shell " + bs + "\"settings delete global http_proxy" + bs + "\"\"}", "c");
            Check("GetField：带双引号的命令不被截断",
                  q1 == "shell \"settings delete global http_proxy\"", Trunc(q1, 60));

            string uncIn = "{\"p\":\"" + bs + bs + bs + bs + "server" + bs + bs + "share\"}";
            string uncOut = GuiWeb.GetField(uncIn, "p");
            Check("GetField：UNC 路径不翻倍",
                  uncOut == bs + bs + "server" + bs + "share", Trunc(uncOut, 60));

            string winOut = GuiWeb.GetField("{\"p\":\"C:" + bs + bs + "temp\"}", "p");
            Check("GetField：C:\\temp 不被二次解码成 TAB",
                  winOut == "C:" + bs + "temp", Trunc(winOut, 40));

            Check("GetField：数字字段仍可取值",
                  GuiWeb.GetField("{\"n\": 123 }", "n") == "123",
                  Trunc(GuiWeb.GetField("{\"n\": 123 }", "n"), 20));

            Finish(f);
        }

        private static void Finish(GuiWeb f)
        {
            Line("");
            Line(_fail == 0
                 ? "  自检全部通过（" + _ok + " 条）"
                 : "  自检失败 " + _fail + " 项（通过 " + _ok + " 条）");
            Dump();
            try { if (f != null) f.Close(); } catch { }
            ExitCode = _fail == 0 ? 0 : 1;
        }

        // ---------------- 解析 k=v|k=v ----------------

        private static string Unescape(string s)
        {
            if (s == null) return "";
            s = s.Trim();
            // ExecuteScriptAsync 返回的是 JSON 字符串：外层带引号，内部引号是 \"
            if (s.Length >= 2 && s[0] == '"' && s[s.Length - 1] == '"')
                s = s.Substring(1, s.Length - 2);
            s = s.Replace("\\\"", "\"").Replace("\\n", "\n").Replace("\\r", "").Replace("\\\\", "\\");
            return s;
        }

        private static Dictionary<string, string> Parse(string s)
        {
            Dictionary<string, string> d = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            if (string.IsNullOrEmpty(s)) return d;
            string[] parts = s.Split('|');
            for (int i = 0; i < parts.Length; i++)
            {
                string p = parts[i];
                int eq = p.IndexOf('=');
                if (eq <= 0) continue;
                d[p.Substring(0, eq).Trim()] = p.Substring(eq + 1).Trim();
            }
            return d;
        }

        private static string Get(Dictionary<string, string> d, string k)
        {
            string v;
            return d.TryGetValue(k, out v) && v != null ? v : "";
        }

        private static int Int(Dictionary<string, string> d, string k)
        {
            int v = 0;
            int.TryParse(Get(d, k), out v);
            return v;
        }

        private static double Dbl(Dictionary<string, string> d, string k)
        {
            double v = 0;
            double.TryParse(Get(d, k), System.Globalization.NumberStyles.Float,
                            System.Globalization.CultureInfo.InvariantCulture, out v);
            return v;
        }

        private static bool LooksLikeColor(string s)
        {
            if (string.IsNullOrEmpty(s)) return false;
            string t = s.Trim();
            if (t.StartsWith("#")) return true;
            if (t.StartsWith("rgb", StringComparison.OrdinalIgnoreCase)) return true;
            return false;
        }

        private static string Trunc(string s, int n)
        {
            if (s == null) return "";
            return s.Length <= n ? s : s.Substring(0, n) + "…";
        }

        // ---------------- 输出 ----------------

        private static void Line(string s) { _log.AppendLine(s); }

        private static void Check(string name, bool cond, string actual)
        {
            if (cond) { Line("  [OK]   " + name); _ok++; }
            else { Line("  [FAIL] " + name + "   （实际：" + actual + "）"); _fail++; }
        }

        private static void Dump()
        {
            try
            {
                string p = System.IO.Path.Combine(GuiEntry.LogDir(), "gui_selfcheck.log");
                System.IO.File.WriteAllText(p, _log.ToString(), new UTF8Encoding(true));
            }
            catch { }
            try { Console.WriteLine(_log.ToString()); } catch { }
        }
    }
}
