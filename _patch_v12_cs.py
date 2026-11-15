# -*- coding: utf-8 -*-
"""
v12 C# 补丁（2026-11-15 第二轮需求）
  1. 自绘标题栏：FormBorderStyle.None + 拖动/缩放/最小化/最大化/关闭
  2. 偏好持久化：prefs（字体/字号/动效）写入 ini，启动回推
  3. 文本编辑器后端：textopen / textsave（编码与换行符保留）
可重复执行：第二次跑会因为锚点已消失而 assert 失败，属预期（改动已在文件里）。
"""
import io, os, sys

CS = r'C:\Users\李亦\Desktop\Adb_Tool\_cs'
def rd(p):  return io.open(os.path.join(CS, p), encoding='utf-8-sig').read()
def wr(p, s): io.open(os.path.join(CS, p), 'w', encoding='utf-8-sig', newline='').write(s)

changed = []

# ============================================================ GuiWeb.cs
p = 'GuiWeb.cs'
s = rd(p)
orig = s

# ---- 1. 无边框窗口 ----
a = "            MinimumSize = new Size(820, 560);\n"
b = a + """
            // ---- 2026-11-15：自绘标题栏 ----
            // 原生 DWM 标题栏实测在深色 / 浅色下都是纯黑 #000、文字恒白：
            // 既跟不上应用主题，字体也改不了（用户连续三条反馈：颜色不跟随、
            // 切模式没变化、字体和全局不一致）。改成无边框窗口，标题栏画进 ui.html，
            // 颜色走 CSS 令牌、字体跟随全局字体设置，窗口按钮也统一成一套视觉。
            FormBorderStyle = FormBorderStyle.None;
"""
assert a in s, 'ctor anchor'
s = s.replace(a, b, 1)

# ---- 2. 拖动/缩放/状态同步 + PushRaw ----
a = """        private void ApplyDarkTitleBar()
        {
            SetTitleBarDark(true);
        }
"""
b = a + """
        // ---------------- 自绘标题栏：原生能力桥接（2026-11-15） ----------------
        // 无边框后这些能力都得自己接：拖动 = 伪造一次"点在标题栏上"，
        // 边缘缩放 = 伪造一次"点在某条边框上"，都交回系统做（含 DPI、最小尺寸、
        // 贴边分屏），不自己算坐标 —— 自己算在缩放/多屏下必翻车。
        [System.Runtime.InteropServices.DllImport("user32.dll")]
        private static extern bool ReleaseCapture();

        [System.Runtime.InteropServices.DllImport("user32.dll")]
        private static extern IntPtr SendMessage(IntPtr hWnd, int msg, IntPtr wParam, IntPtr lParam);

        private const int WM_NCLBUTTONDOWN = 0x00A1;
        private const int HTCAPTION = 2;

        // 无边框窗口默认最大化会铺满整屏、盖住任务栏：限制到当前屏工作区。
        // 拖到别的显示器后要重算，否则在副屏最大化会跑偏。
        private void UpdateMaximizedBounds()
        {
            try
            {
                if (WindowState != FormWindowState.Normal) return;
                Rectangle wa = Screen.FromControl(this).WorkingArea;
                if (MaximizedBounds != wa) MaximizedBounds = wa;
            }
            catch { }
        }

        protected override void OnLoad(EventArgs e)
        {
            base.OnLoad(e);
            UpdateMaximizedBounds();
        }

        protected override void OnResize(EventArgs e)
        {
            base.OnResize(e);
            PushWinState();
        }

        // 最大化 / 还原后要告诉页面：最大化按钮图标要换成"还原"，边缘热区要藏起来。
        private void PushWinState()
        {
            try
            {
                if (_web == null || _web.CoreWebView2 == null) return;
                _web.CoreWebView2.PostWebMessageAsJson(
                    "{\\"kind\\":\\"winstate\\",\\"max\\":"
                    + (WindowState == FormWindowState.Maximized ? "1" : "0") + "}");
            }
            catch { }
        }

        private void PushRaw(string json)
        {
            try
            {
                if (_web != null && _web.CoreWebView2 != null)
                    _web.CoreWebView2.PostWebMessageAsJson(json);
            }
            catch { }
        }
"""
assert a in s, 'ApplyDarkTitleBar anchor'
s = s.replace(a, b, 1)

# ---- 3. 路由：窗口控制 / 偏好 / 文本 ----
a = """                case "themeget":"""
b = """                // ---------------- 自绘标题栏 / 设置（2026-11-15） ----------------
                case "windrag":
                    try
                    {
                        if (WindowState == FormWindowState.Maximized)
                        {
                            // 最大化时拖动 = 先还原到原尺寸的一半，再跟着鼠标走
                            // （和 Windows 原生标题栏的手感一致）
                            Point cp = PointToClient(Cursor.Position);
                            double rx = (double)cp.X / Math.Max(1, ClientSize.Width);
                            WindowState = FormWindowState.Normal;
                            Location = new Point(
                                (int)(Cursor.Position.X - Width * rx),
                                Math.Max(0, Cursor.Position.Y - 16));
                        }
                        ReleaseCapture();
                        SendMessage(Handle, WM_NCLBUTTONDOWN, (IntPtr)HTCAPTION, IntPtr.Zero);
                    }
                    catch (Exception ex) { GuiEntry.Dump("windrag", ex); }
                    break;

                case "winresize":
                    // 页面在四边/四角放了 6px 透明热区，按下时把命中的 HT* 码回传
                    try
                    {
                        int ht = 10;
                        int.TryParse(GetField(json, "data"), out ht);
                        if (ht < 10 || ht > 17) ht = 10;
                        ReleaseCapture();
                        SendMessage(Handle, WM_NCLBUTTONDOWN, (IntPtr)ht, IntPtr.Zero);
                    }
                    catch (Exception ex) { GuiEntry.Dump("winresize", ex); }
                    break;

                case "winmin":
                    WindowState = FormWindowState.Minimized;
                    break;

                case "winmax":
                    WindowState = (WindowState == FormWindowState.Maximized)
                        ? FormWindowState.Normal : FormWindowState.Maximized;
                    PushWinState();
                    break;

                case "winclose":
                    Close();
                    break;

                case "prefsave":
                    // 字体 / 字号 / 动效：和 accent 一样是不透明串，C# 只存取不解析
                    App.PREFS = GetField(json, "data");
                    SaveIniKey("prefs", App.PREFS == null ? "" : App.PREFS);
                    break;

                // ---------------- 文本编辑器（2026-11-15）----------------
                case "textopen":
                    RunTextOpen();
                    break;

                case "textsave":
                    RunTextSave(json);
                    break;

                case "themeget":"""
assert a in s, 'themeget anchor'
s = s.replace(a, b, 1)

# ---- 4. themeget 回推 prefs ----
a = """                        _web.CoreWebView2.PostWebMessageAsJson(
                            "{\\"kind\\":\\"accent\\",\\"name\\":" + Json(App.ACCENT) + "}");"""
b = a + """
                        // 字体 / 字号 / 动效偏好（base64 不透明串）
                        if (App.PREFS != null && App.PREFS.Length > 0)
                            _web.CoreWebView2.PostWebMessageAsJson(
                                "{\\"kind\\":\\"prefs\\",\\"data\\":" + Json(App.PREFS) + "}");"""
assert a in s, 'accent push anchor'
s = s.replace(a, b, 1)

# ---- 5. SaveIniKey + 文本 IO ----
a = """        private void PushStatus(bool online, long ms, string msg)"""
b = """        // 通用 ini 键写入：只改那一行，其它原样保留；没有这个键就追加。
        // 不新建 ini（单 exe 目录本来就没有配置文件，凭空造一个反而是垃圾）。
        private static void SaveIniKey(string key, string val)
        {
            try
            {
                string p = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "adb_log_export.ini");
                if (!File.Exists(p)) return;
                string[] lines = File.ReadAllLines(p);
                bool found = false;
                for (int i = 0; i < lines.Length; i++)
                {
                    if (lines[i].TrimStart().StartsWith(key + "=", StringComparison.OrdinalIgnoreCase))
                    {
                        lines[i] = key + "=" + val;
                        found = true;
                        break;
                    }
                }
                if (!found)
                {
                    List<string> list = new List<string>(lines);
                    list.Add(key + "=" + val);
                    lines = list.ToArray();
                }
                File.WriteAllLines(p, lines, new UTF8Encoding(false));
            }
            catch (Exception ex) { App.Trace(key + ": 保存失败 " + ex.Message); }
        }

        // ================= 文本编辑器：本地文件读写（2026-11-15） =================
        // 为什么要走 C# 而不是浏览器的 File API：
        //   页面是内嵌的，没有"打开/另存为"的系统对话框；而且编码（GBK）和
        //   换行符（CRLF/LF）必须原样保留 —— 用户拿它改 ini / 脚本，编码一乱
        //   就等于把这个文件改坏了。
        private static string B64(string s)
        {
            try { return Convert.ToBase64String(Encoding.UTF8.GetBytes(s == null ? "" : s)); }
            catch { return ""; }
        }

        private static string FromB64(string s)
        {
            try { return Encoding.UTF8.GetString(Convert.FromBase64String(s == null ? "" : s)); }
            catch { return ""; }
        }

        private const int TEXT_MAX = 2 * 1024 * 1024;   // 2MB：再大就不该用这个编辑器

        private void RunTextOpen()
        {
            string path = "";
            try
            {
                using (OpenFileDialog d = new OpenFileDialog())
                {
                    d.Title = "打开文本文件（最大 2 MB）";
                    d.Filter = "文本与配置|*.txt;*.log;*.json;*.xml;*.ini;*.cfg;*.conf;*.md;*.csv;"
                             + "*.bat;*.sh;*.prop;*.java;*.js;*.cs;*.py|所有文件 (*.*)|*.*";
                    d.CheckFileExists = true;
                    d.CheckPathExists = true;
                    if (d.ShowDialog(this) != DialogResult.OK) return;
                    path = d.FileName;
                }
            }
            catch (Exception ex)
            {
                GuiEntry.Dump("textopen 对话框", ex);
                PushRaw("{\\"kind\\":\\"texterr\\",\\"text\\":" + Json("打开文件失败：" + ex.Message) + "}");
                return;
            }

            // 读盘放后台：网络盘、大文件都会卡住 UI 线程（连带投屏掉帧）
            string p2 = path;
            Thread th = new Thread(new ThreadStart(delegate { ReadTextFile(p2); }));
            th.IsBackground = true;
            th.Start();
        }

        private void ReadTextFile(string path)
        {
            string name = "", enc = "UTF-8", eol = "CRLF", text = "";
            bool trunc = false;
            try
            {
                name = Path.GetFileName(path);
                byte[] all;
                using (FileStream fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                {
                    int len = (int)Math.Min(fs.Length, (long)TEXT_MAX);
                    all = new byte[len];
                    int off = 0;
                    while (off < len)
                    {
                        int r = fs.Read(all, off, len - off);
                        if (r <= 0) break;
                        off += r;
                    }
                    trunc = fs.Length > (long)TEXT_MAX;
                }

                if (all.Length >= 3 && all[0] == 0xEF && all[1] == 0xBB && all[2] == 0xBF)
                {
                    enc = "UTF-8 BOM";
                    text = new UTF8Encoding(false).GetString(all, 3, all.Length - 3);
                }
                else if (all.Length >= 2 && all[0] == 0xFF && all[1] == 0xFE)
                {
                    enc = "UTF-16 LE";
                    text = Encoding.Unicode.GetString(all, 2, all.Length - 2);
                }
                else
                {
                    // 先按严格 UTF-8 解，解不动再退 GBK —— 反过来做会把 UTF-8 中文变乱码
                    try
                    {
                        text = new UTF8Encoding(false, true).GetString(all);
                        enc = "UTF-8";
                    }
                    catch
                    {
                        try { text = Encoding.GetEncoding(936).GetString(all); enc = "GBK"; }
                        catch { text = Encoding.Default.GetString(all); enc = "ANSI"; }
                    }
                }

                eol = text.IndexOf("\\r\\n", StringComparison.Ordinal) >= 0
                    ? "CRLF" : (text.IndexOf('\\n') >= 0 ? "LF" : "CRLF");
                // 统一成 \\n 交给页面（textarea 只认 \\n），保存时按 eol 还原
                text = text.Replace("\\r\\n", "\\n").Replace("\\r", "\\n");
            }
            catch (Exception ex)
            {
                PushRaw("{\\"kind\\":\\"texterr\\",\\"text\\":" + Json("读取失败：" + ex.Message) + "}");
                return;
            }

            PushRaw("{\\"kind\\":\\"textfile\\",\\"name\\":" + Json(name)
                    + ",\\"path\\":" + Json(path)
                    + ",\\"enc\\":" + Json(enc)
                    + ",\\"eol\\":" + Json(eol)
                    + ",\\"trunc\\":" + (trunc ? "1" : "0")
                    + ",\\"data\\":" + Json(B64(text)) + "}");
        }

        private void RunTextSave(string json)
        {
            string path = App.JsonUnescape(GetField(json, "path"));
            string enc = GetField(json, "enc");
            string eol = GetField(json, "eol");
            string name = App.JsonUnescape(GetField(json, "name"));
            string text = FromB64(GetField(json, "data"));

            if (path == null || path.Length == 0)
            {
                try
                {
                    using (SaveFileDialog d = new SaveFileDialog())
                    {
                        d.Title = "保存文本文件";
                        d.Filter = "文本文件 (*.txt)|*.txt|所有文件 (*.*)|*.*";
                        if (name != null && name.Length > 0) d.FileName = name;
                        if (d.ShowDialog(this) != DialogResult.OK) return;
                        path = d.FileName;
                    }
                }
                catch (Exception ex)
                {
                    GuiEntry.Dump("textsave 对话框", ex);
                    PushRaw("{\\"kind\\":\\"texterr\\",\\"text\\":" + Json("保存失败：" + ex.Message) + "}");
                    return;
                }
            }

            try
            {
                string outText = text;
                if (eol == "CRLF") outText = outText.Replace("\\r\\n", "\\n").Replace("\\n", "\\r\\n");

                byte[] bytes;
                if (enc == "UTF-8 BOM")
                {
                    byte[] body = new UTF8Encoding(false).GetBytes(outText);
                    bytes = new byte[body.Length + 3];
                    bytes[0] = 0xEF; bytes[1] = 0xBB; bytes[2] = 0xBF;
                    Array.Copy(body, 0, bytes, 3, body.Length);
                }
                else if (enc == "UTF-16 LE")
                {
                    byte[] body = Encoding.Unicode.GetBytes(outText);
                    bytes = new byte[body.Length + 2];
                    bytes[0] = 0xFF; bytes[1] = 0xFE;
                    Array.Copy(body, 0, bytes, 2, body.Length);
                }
                else if (enc == "GBK")
                {
                    bytes = Encoding.GetEncoding(936).GetBytes(outText);
                }
                else
                {
                    bytes = new UTF8Encoding(false).GetBytes(outText);
                }

                File.WriteAllBytes(path, bytes);
                PushRaw("{\\"kind\\":\\"textsaved\\",\\"path\\":" + Json(path)
                        + ",\\"name\\":" + Json(Path.GetFileName(path))
                        + ",\\"enc\\":" + Json(enc == null || enc.Length == 0 ? "UTF-8" : enc)
                        + ",\\"eol\\":" + Json(eol == null || eol.Length == 0 ? "CRLF" : eol) + "}");
            }
            catch (Exception ex)
            {
                PushRaw("{\\"kind\\":\\"texterr\\",\\"text\\":" + Json("保存失败：" + ex.Message) + "}");
            }
        }

        private void PushStatus(bool online, long ms, string msg)"""
assert a in s, 'PushStatus anchor'
s = s.replace(a, b, 1)

if s != orig:
    wr(p, s); changed.append(p)

# ============================================================ Prefix.cs
p = 'Prefix.cs'
s = rd(p); orig = s
a = '        internal static string ACCENT = "blue";'
b = a + """
        // 字体 / 字号 / 动效偏好：base64 不透明串（前端 JSON → base64），
        // C# 只存取不解析，和 CustomStore 同一条思路。ini: prefs=
        internal static string PREFS = "";"""
assert a in s, 'ACCENT anchor'
s = s.replace(a, b, 1)
if s != orig:
    wr(p, s); changed.append(p)

# ============================================================ Program.cs
p = 'Program.cs'
s = rd(p); orig = s
a = """                        case "accent":
                            {"""
assert a in s, 'accent case anchor'
# 在 accent 分支之后插入 prefs 分支：定位 accent 分支结尾（break; }）
i = s.index(a)
j = s.index('case "', i + len(a))
seg = s[i:j]
assert 'break;' in seg, 'accent seg'
ins = """case "prefs":
                            // 字体 / 字号 / 动效（base64 不透明串），原样存回
                            PREFS = v == null ? "" : v.Trim();
                            break;
                        """
s = s[:j] + ins + s[j:]
if s != orig:
    wr(p, s); changed.append(p)

print('patched:', ', '.join(changed) if changed else '(无变化)')
