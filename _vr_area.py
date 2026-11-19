# -*- coding: utf-8 -*-
"""语音助手：按音区唤醒 + 卡片重排。

1) Voice.cs：VrBuildWakeUri 增加 area，URL 拼 &voiceArea=N（area<0 时与原来逐字节一致）
2) VrWake：解析 -a N / -a 副驾（复用 VrStripArgs）
3) ui.html：语音助手组 → 唤醒 6 张 + 调试 5 张；删「唤醒(原参)」「语音识别」「断网识别」「音区对照表」
4) Render.cs 自检：唤醒带/不带 voiceArea 各一条
"""
import io

ROOT = r"C:\Users\SunWwei\Desktop\Adb_Tool"

# ---------------- 1) Voice.cs ----------------
v = ROOT + r"\_cs\Voice.cs"
s = io.open(v, encoding="utf-8").read()

old = '''        internal static string VrBuildWakeUri(string type, bool withSleep)
        {
            string uri = VR_VR_URI + "?type=" + type;
            if (withSleep) uri += "&canSleep=false";
            return uri;
        }'''
new = '''        internal static string VrBuildWakeUri(string type, bool withSleep, int area = -1)
        {
            string uri = VR_VR_URI + "?type=" + type;
            if (withSleep) uri += "&canSleep=false";
            // 2026-11-19：按音区唤醒。voiceArea 与识别侧同一套取值（0主驾 1副驾
            // 2二排左 3二排右 4三排左 5三排右），复用 VR_AREAS 的顺序。
            // area<0 时不拼任何东西 —— 旧调用方（含自检）行为逐字节不变。
            if (area >= 0) uri += "&voiceArea=" + area;
            return uri;
        }'''
assert s.count(old) == 1
s = s.replace(old, new, 1)

old2 = '''            string t = (rest == null) ? "" : rest.Trim();
            string type = VR_WAKE_TYPE;
            bool withSleep = false;'''
new2 = '''            // 2026-11-19：支持 -a <音区>，例如 `:vr wake -a 副驾` / `:vr wake 1 -a 1`
            int area; bool _localM; string areaBad;
            string t = VrStripArgs(rest ?? "", out area, out _localM, out areaBad).Trim();
            if (areaBad.Length > 0)
            {
                Fail("音区不合法：" + areaBad);
                Hint("可用：-a 0~5 或 -a 主驾/副驾/二排左/二排右/三排左/三排右");
                return;
            }
            string type = VR_WAKE_TYPE;
            bool withSleep = false;'''
assert s.count(old2) == 1
s = s.replace(old2, new2, 1)

old3 = '''            string uri = VrBuildWakeUri(type, withSleep);

            string cmd = VrBuildAmCmd(uri);
            if (VrAdb(new List<string> { "shell", cmd }, "唤醒指令已下发（type=" + type + "）"))
            {
                Hint("URI：" + UrlDecodeForDisplay(uri));
            }'''
new3 = '''            string uri = VrBuildWakeUri(type, withSleep, area);

            string cmd = VrBuildAmCmd(uri);
            string tail = (area >= 0) ? "，音区=" + VrAreaName(area) : "";
            if (VrAdb(new List<string> { "shell", cmd }, "唤醒指令已下发（type=" + type + tail + "）"))
            {
                Hint("URI：" + UrlDecodeForDisplay(uri));
                if (area >= 0)
                    Hint("提示：该参数仅在 AH8 项目（0626apk 起）生效；换音区前先让上一个音区休眠");
            }'''
assert s.count(old3) == 1
s = s.replace(old3, new3, 1)
io.open(v, "w", encoding="utf-8", newline="\n").write(s)
print("Voice.cs：唤醒支持 -a 音区")

# ---------------- 2) Render.cs 自检 ----------------
r = ROOT + r"\_cs\Render.cs"
t = io.open(r, encoding="utf-8").read()
old4 = '''            // 7.4b TBOX 帧表（2026-11-19）'''
new4 = '''            // 7.4a 按音区唤醒（2026-11-19）
            string vwA = VrBuildWakeUri("1", false, 1);
            STCheck("唤醒带 voiceArea=1", vwA.IndexOf("voiceArea=1") > 0, vwA);
            STCheck("唤醒默认不带 voiceArea", VrBuildWakeUri("1", false).IndexOf("voiceArea") < 0,
                    VrBuildWakeUri("1", false));

            // 7.4b TBOX 帧表（2026-11-19）'''
assert t.count(old4) == 1
io.open(r, "w", encoding="utf-8", newline="\n").write(t.replace(old4, new4, 1))
print("Render.cs：+2 条唤醒音区自检")

# ---------------- 3) ui.html 语音组 ----------------
u = ROOT + r"\adb_log_gui\webview2\ui.html"
g = io.open(u, encoding="utf-8").read()
old5 = """  { name:'语音助手', color:'var(--accent)', items:[
    {name:'主驾唤醒', desc:'vr:// type=1', cmd:':vr wake'},
    {name:'唤醒(原参)', desc:'type=99 & canSleep=false', cmd:':vr wake 99'},
    {name:'语音识别', desc:'输入文本后回车，-a 可指定音区', cmd:':vr sr ', arg:true, usage:':vr sr <文本> [-a 音区 0~5]'},
    {name:'断网识别', desc:'AH8 离线模式 mode=local', cmd:':vr local ', arg:true, usage:':vr local <文本> [-a 音区 0~5]'},
    {name:'语助版本号', desc:'versionName + versionCode', cmd:':vr ver'},
    {name:'重启语助进程', desc:'force-stop 后由语音拉起', cmd:':vr restart'},
    {name:'打开后台设置', desc:'SettingDebugActivity', cmd:':vr set'},
    {name:'文本语义调试', desc:'DebugTextExecuteSemantic', cmd:':vr dbg'},
    {name:'音区对照表', desc:'0主驾 1副驾 2/3 二排 4/5 三排', cmd:':vr area'},
    {name:'语音日志', desc:'只显示 讲话内容= / 【TTS】 两类行', cmd:':vr log'}
  ]},"""
new5 = """  // 2026-11-19：语音助手按「唤醒 / 调试」两分类重排。
  // 删掉的四张卡与替代入口：
  //   唤醒(原参)   :vr wake 99   → 终端仍可敲
  //   语音识别     :vr sr        → 语音助手页有输入框 + 发送按钮
  //   断网识别     :vr local     → 语音助手页有「断网识别」勾选
  //   音区对照表   :vr area      → 终端仍可敲，且唤醒卡已按音区命名
  { name:'语音助手', color:'var(--accent)', items:[
    {name:'主驾唤醒',   desc:'vr:// type=1 · voiceArea=0', cmd:':vr wake -a 0', cat:'唤醒'},
    {name:'副驾唤醒',   desc:'voiceArea=1', cmd:':vr wake -a 1', cat:'唤醒'},
    {name:'二排左唤醒', desc:'voiceArea=2', cmd:':vr wake -a 2', cat:'唤醒'},
    {name:'二排右唤醒', desc:'voiceArea=3', cmd:':vr wake -a 3', cat:'唤醒'},
    {name:'三排左唤醒', desc:'voiceArea=4', cmd:':vr wake -a 4', cat:'唤醒'},
    {name:'三排右唤醒', desc:'voiceArea=5', cmd:':vr wake -a 5', cat:'唤醒'},
    {name:'语助版本号', desc:'versionName + versionCode', cmd:':vr ver', cat:'调试'},
    {name:'重启语助进程', desc:'force-stop 后由语音拉起', cmd:':vr restart', cat:'调试'},
    {name:'打开后台设置', desc:'SettingDebugActivity', cmd:':vr set', cat:'调试'},
    {name:'文本语义调试', desc:'DebugTextExecuteSemantic', cmd:':vr dbg', cat:'调试'},
    {name:'语音日志', desc:'只显示 讲话内容= / 【TTS】 两类行', cmd:':vr log', cat:'调试'}
  ]},"""
assert g.count(old5) == 1
io.open(u, "w", encoding="utf-8", newline="\n").write(g.replace(old5, new5, 1))
print("ui.html：语音组重排（6 唤醒 + 5 调试）")
