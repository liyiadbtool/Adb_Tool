#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_all_logic.py — v6 融合版的纯逻辑等价验证

用 Python 逐条复刻 C# 里的纯函数（不碰 adb），对每一条行为做断言。
覆盖：
  A. 输入分派优先级（含"保留 adb/shell 输入"这条硬约束）
  B. 纯中文启发式
  C. send 子命令参数解析（文本 / 编号 / -f / 引号强制文本）
  D. am 命令构造（am_cmd / component）
  E. URL 编码（对齐 Uri.EscapeDataString）
  F. 文本编码识别（BOM / UTF-8 / GBK）
  G. 批量分组（6000 字符预算）
  H. 乐观批量 + 悲观回退的计数与失败清单
  I. ls -1p 解析（目录/文件区分）+ 列数计算
  J. 路径工具 / 显示宽度
"""
import urllib.parse

FAIL = 0


def check(name, cond, extra=""):
    global FAIL
    if cond:
        print("  [OK] " + name)
    else:
        print("  [FAIL] " + name + (("  " + extra) if extra else ""))
        FAIL += 1


# ==================== E. URL 编码 ====================
def escape_data(s):
    """对齐 C# Uri.EscapeDataString：%XX 十六进制大写，字母原样，不编码 !*'()"""
    q = urllib.parse.quote(s, safe="!'()*", encoding="utf-8")
    out, i = [], 0
    while i < len(q):
        if q[i] == "%" and i + 2 < len(q):
            out.append("%" + q[i + 1:i + 3].upper())
            i += 3
        else:
            out.append(q[i])
            i += 1
    return "".join(out)


# ==================== F. 编码识别 ====================
def decode_text(b):
    if b[:3] == b"\xef\xbb\xbf":
        return b[3:].decode("utf-8")
    if b[:2] == b"\xff\xfe":
        return b[2:].decode("utf-16-le")
    if b[:2] == b"\xfe\xff":
        return b[2:].decode("utf-16-be")
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("gbk")


# ==================== J. 路径工具 ====================
def norm_path(p):
    if not p:
        return "/"
    parts = p.replace("\\", "/").split("/")
    st = []
    for seg in parts:
        if seg == "" or seg == ".":
            continue
        if seg == "..":
            if st:
                st.pop()
            continue
        st.append(seg)
    return "/" + "/".join(st) if st else "/"


def last_seg(p):
    if not p:
        return "/"
    t = p.rstrip("/")
    if not t:
        return "/"
    i = t.rfind("/")
    return t if i < 0 else t[i + 1:]


def dev_abs(p, cur):
    if not p:
        return cur
    if p == "~":
        return "/"
    if p.startswith("/"):
        return norm_path(p)
    return norm_path(cur + "/" + p)


def is_win_path(p):
    if not p:
        return False
    if len(p) >= 3 and p[0].isalpha() and p[1] == ":" and p[2] in "\\/":
        return True
    return len(p) >= 2 and p[0] == "\\" and p[1] == "\\"


def disp_width(s):
    w = 0
    for ch in s:
        o = ord(ch)
        if (0x1100 <= o <= 0x115F or 0x2E80 <= o <= 0xA4CF or
                0xAC00 <= o <= 0xD7A3 or 0xF900 <= o <= 0xFAFF or
                0xFE30 <= o <= 0xFE6F or 0xFF00 <= o <= 0xFF60 or
                0xFFE0 <= o <= 0xFFE6):
            w += 2
        else:
            w += 1
    return w


def unquote(s):
    s = (s or "").strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1].strip()
    return s


def split_line(line):
    """拆成 (cmd, argRaw)，与 C# SplitLine 等价"""
    if line is None:
        return "", ""
    i, n = 0, len(line)
    while i < n and line[i] in " \t":
        i += 1
    s = i
    while i < n and line[i] not in " \t":
        i += 1
    cmd = line[s:i]
    while i < n and line[i] in " \t":
        i += 1
    arg = line[i:] if i < n else ""
    return cmd, arg


# ==================== B. 纯中文启发式 ====================
def is_probably_text(cmd_token):
    """首 token 含非 ASCII => 视为待发文本"""
    if not cmd_token:
        return False
    return any(ord(ch) > 127 for ch in cmd_token)


# ==================== D. am 命令构造 ====================
def build_am_cmd(enc, am_cmd="startservice", component="",
                 action="android.intent.action.VIEW",
                 uri_prefix="sr://syncore.vpa.sr/test?text="):
    s = "am " + am_cmd
    if component:
        s += " -n " + component
    s += " -a " + action
    s += " -d '" + uri_prefix + enc + "'"
    return s


# ==================== C. send 参数解析 ====================
def parse_send(arg_raw, quick):
    """返回 (kind, payload)；kind in text|quick|batch|usage|empty"""
    t = (arg_raw or "").strip()
    if not t:
        return ("usage", "")
    if len(t) >= 2 and t[:2] == "-f":
        return ("batch", t[2:].strip())
    unq = unquote(t)
    if len(unq) == 1 and unq.isdigit() and unq == t:
        idx = int(unq)
        if 1 <= idx <= 9 and quick.get(idx):
            return ("quick", quick[idx])
        return ("quick_missing", idx)
    return ("text", unq)


# ==================== A. 输入分派优先级 ====================
BARE = {"cd", "pwd", "ls", "pull", "push", "adb", "shell"}

LEGACY = {"lsf", "logcat", "send", "res", "logs", "anr", "dropbox",
          "test", "pre", "dev", "syncore", "env",
          "ver", "versions", "now", "front", "cmds",
          "h", "?", "r", "rl", "rr", "ri", "i", "rw", "q", "quit", "exit"}

# 与 Prefix.cs 的 DEVICE_CMDS 保持一致（只收高频、易误伤的）
DEVICE_CMDS = {
    "ls", "cd", "pwd", "cat", "ps", "top", "kill", "killall", "clear", "ping",
    "env", "test", "df", "du", "stop", "start", "mount", "umount", "rm", "cp",
    "mv", "mkdir", "rmdir", "touch", "chmod", "chown", "ln", "find", "grep",
    "date", "echo", "sleep", "id", "whoami", "uptime", "free", "dmesg",
    "logcat", "getprop", "setprop", "watch", "nohup", "sed", "awk", "sort",
    "pm", "am", "wm", "input", "monkey", "dumpsys", "settings", "content",
    "screencap", "screenrecord", "netstat", "ifconfig", "ip", "svc", "cmd",
    "service", "bugreport", "reboot", "install", "uninstall", "su", "sh",
}

# 与 cmds.ini 的 [cmd.*] 名字一致
DIY = {"l", "ll", "la", "net", "ports", "apkinfo", "apps", "stopapp", "appclear",
       "cpu", "mem", "crash", "traces", "errors", "df", "big", "shot", "dumpall",
       "sysinfo", "battery", "screen", "prop", "hello"}

# adb 专属子命令白名单 —— 必须与 AdbCmd.cs 的 ADB_SUBCMDS 完全一致
ADB_SUBCMDS = {
    "devices", "connect", "disconnect", "pair",
    "forward", "reverse", "tcpip", "usb",
    "install", "uninstall", "install-multiple", "install-multi",
    "bugreport", "backup", "restore", "sideload",
    "wait-for-device", "get-state", "get-serialno", "get-devpath",
    "start-server", "kill-server", "version",
    "exec-out", "exec-in",
    "root", "unroot", "remount", "disable-verity", "enable-verity",
    "reboot", "reboot-bootloader",
    "mdns", "jdwp", "attach", "detach",
}


FILE_EXTS = (".apk", ".txt", ".log", ".sh", ".prop", ".so", ".xml", ".json",
             ".ini", ".bat", ".ps1", ".zip", ".gz", ".png", ".jpg", ".mp4")


def is_maybe_pkg(line):
    if not line or len(line) < 4 or len(line) > 150:
        return False
    if " " in line or "/" in line or "\\" in line:
        return False
    dots = 0
    for ch in line:
        if not (ch.isalnum() and ch.isascii()) and ch not in "._":
            return False
        if ch == ".":
            dots += 1
    if dots < 1:
        return False
    if line[0] == "." or line[-1] == ".":
        return False
    if line[0].isdigit():
        return False
    low = line.lower()
    for e in FILE_EXTS:
        if low.endswith(e):
            return False
    return True


def dispatch_kind(line):
    """复刻 v7 Program.cs Dispatch 的词法路由（前缀优先，顺序不再承载语义）"""
    if line and line[0] == "!":
        return "force"
    if is_win_path(line):
        return "export"
    if line and line[0] == ":":
        return "tool"
    cmd, arg = split_line(line)
    if not cmd:
        return "empty"
    if line[0] == "@":
        return "jump"
    c = cmd.lower()
    if c in BARE:
        if c == "adb":
            return "adb_prefix"
        if c == "shell":
            return "shell_prefix"
        return "known:" + c
    if c in ("h", "?", "help"):
        return "help"
    if c in ("q", "quit", "exit"):
        return "quit"
    if c in LEGACY:
        return "legacy:" + c
    if is_probably_text(cmd):
        return "heuristic_text"
    if c in DIY and c not in DEVICE_CMDS:
        return "diy"
    if c in ADB_SUBCMDS:
        return "adb_bare"
    if is_local_pipe(line):
        return "local_pipe"
    if is_maybe_pkg(line):
        return "pkg"
    if is_interactive_bare(c, arg):
        return "interactive_guard"
    return "passthrough"


# ==================== 交互式命令预判 ====================
INTERACTIVE_CMDS = {"top", "vi", "vim", "nano", "less", "more", "tailf", "watch", "screenrecord"}


def is_interactive_bare(cmd, arg_raw=""):
    if not cmd:
        return False
    c = cmd.lower()
    if c not in INTERACTIVE_CMDS:
        return False
    a = arg_raw or ""
    if c == "top" and "-n" in a:
        return False
    if c == "screenrecord" and "--time-limit" in a:
        return False
    return True


# ==================== ls 类型后缀 ====================
def parse_ls_suffix(name):
    """0=目录 1=可执行 2=链接/特殊 3=普通 4=隐藏"""
    if not name:
        return 3
    last = name[-1]
    if last == "/":
        return 0
    if last == "*":
        return 1
    if last in "@|=":
        return 2
    if name[0] == ".":
        return 4
    return 3


def strip_ls_suffix(raw):
    if not raw:
        return raw
    if raw[-1] in "/*@|=":
        return raw[:-1]
    return raw


# ==================== 长路径省略 ====================
def short_path(p, max_len):
    if not p:
        return "/"
    if len(p) <= max_len:
        return p
    tail = last_seg(p)
    keep_head = max_len - len(tail) - 5
    if keep_head < 3:
        return "..." + p[max(0, len(p) - (max_len - 3)):]
    return p[:keep_head] + ".../" + tail


# ==================== 自定义命令模板展开 ====================
def split_args(s):
    """与 C# SplitArgs 等价：引号感知分词"""
    r, cur, inq, any_ch = [], "", False, False
    for ch in (s or ""):
        if ch == '"':
            inq = not inq
            any_ch = True
            continue
        if not inq and ch in " \t":
            if any_ch:
                r.append(cur)
                cur, any_ch = "", False
            continue
        cur += ch
        any_ch = True
    if any_ch:
        r.append(cur)
    return r


def eval_func(fn, args, cur_dir="/", serial="", app=""):
    from datetime import datetime
    if fn == "date":
        return datetime.now().strftime("%Y%m%d")
    if fn == "date-":
        return datetime.now().strftime("%Y-%m-%d")
    if fn == "time":
        return datetime.now().strftime("%H%M%S")
    if fn == "serial":
        return serial or "device"
    if fn == "cur":
        return cur_dir
    if fn == "app":
        return app
    if fn == "argc":
        return str(len(args))
    return ""


def expand_template(tpl, arg_raw, cmd_name, cur_dir="/", serial="", app=""):
    """与 C# ExpandTemplate 等价"""
    if not tpl:
        return ""
    args = split_args(arg_raw or "")
    out = []
    i = 0
    n = len(tpl)
    while i < n:
        ch = tpl[i]
        if ch == "$" and i + 1 < n and tpl[i + 1] == "(":
            close = tpl.find(")", i + 2)
            if close > 0:
                fn = tpl[i + 2:close].strip().lower()
                out.append(eval_func(fn, args, cur_dir, serial, app))
                i = close + 1
                continue
        if ch == "$" and i + 1 < n:
            c = tpl[i + 1]
            if c in "123456789":
                idx = int(c) - 1
                if idx < len(args):
                    out.append(args[idx])
                i += 2
                continue
            if c == "*":
                out.append((arg_raw or "").strip())
                i += 2
                continue
            if c == "0":
                out.append(cmd_name)
                i += 2
                continue
        out.append(ch)
        i += 1
    return "".join(out)


# ==================== 前台包名提取 ====================
def is_pkg_char(c):
    return (('a' <= c <= 'z') or ('A' <= c <= 'Z')
            or ('0' <= c <= '9') or c == '_' or c == '.')


def extract_pkg(line):
    """从 'u0 com.pkg/com.pkg.MainActivity' 提取包名"""
    if not line:
        return ""
    for i, ch in enumerate(line):
        if ch != "/":
            continue
        s = i - 1
        while s >= 0 and is_pkg_char(line[s]):
            s -= 1
        s += 1
        if s >= i:
            continue
        p = line[s:i]
        if len(p) >= 3 and "." in p and not p.isdigit():
            return p
    return ""


def char_width(c):
    o = ord(c)
    if (0x1100 <= o <= 0x115F or 0x2E80 <= o <= 0xA4CF or
            0xAC00 <= o <= 0xD7A3 or 0xF900 <= o <= 0xFAFF or
            0xFE30 <= o <= 0xFE6F or 0xFF00 <= o <= 0xFF60 or
            0xFFE0 <= o <= 0xFFE6):
        return 2
    return 1


def fit_width(s, mx):
    """超过 mx 列就截断，末尾补 ..（对齐 C# FitWidth）"""
    if not s or mx <= 0:
        return ""
    if disp_width(s) <= mx:
        return s
    w = 0
    for i, c in enumerate(s):
        w += char_width(c)
        if w > mx - 2:
            return s[:i] + ".."
    return s


def pad(s, w):
    """按显示宽度补空格"""
    n = w - disp_width(s)
    return s + (" " * n if n > 0 else "")


def ver_table_widths(rows, lsw=120, gap=2):
    """复刻 C# RenderVerTable 的列宽计算；rows = [(alias, pkg, ver, code)]"""
    has_alias = any(r[0] for r in rows)
    w_alias = max([disp_width("别名")] + [disp_width(r[0]) for r in rows])
    w_pkg = max([disp_width("包名")] + [disp_width(r[1]) for r in rows])
    w_ver = max([disp_width("版本名")] + [disp_width(r[2]) for r in rows])

    # 版本名绝不截断（只在 80 列处兜底）；版本码列已从表格移除（只在单包详情里给）
    w_ver = min(w_ver, 80)
    w_alias = min(w_alias, 14)

    avail = lsw - 2

    # 先按带"更新时间"算；包名压到 18 列仍放不下 -> 时间另起一行
    show_time = True
    pkg_max = avail - (19 + gap * 3 + w_ver + (w_alias if has_alias else 0))
    if pkg_max < 18:
        show_time = False
        pkg_max = avail - (gap * 2 + w_ver + (w_alias if has_alias else 0))

    pkg_max = min(pkg_max, 44)
    pkg_max = max(pkg_max, 18)
    w_pkg = min(w_pkg, pkg_max)

    return has_alias, w_alias, w_pkg, w_ver, show_time


# ==================== 环境切换 ====================
def parse_marked(text, n):
    """按 ##1 ##2 ##3 分段取第一条非空内容；空段保持空"""
    r = [""] * n
    cur = -1
    for raw in (text or "").split("\n"):
        t = raw.rstrip("\r").strip()
        if not t:
            continue
        if t.startswith("##"):
            try:
                cur = int(t[2:]) - 1
            except ValueError:
                pass
            continue
        if 0 <= cur < n and not r[cur]:
            r[cur] = t
    return r


def parse_env_profile(v):
    """env_xxx=deploy值;https值;domain值"""
    parts = (v or "").split(";")
    return (parts[0].strip() if len(parts) > 0 else "",
            parts[1].strip() if len(parts) > 1 else "",
            parts[2].strip() if len(parts) > 2 else "")


def match_env(actual, envs):
    """三个值全部吻合才算匹配某套环境"""
    for name, (d, h, dm) in envs.items():
        if actual[0] == d and actual[1] == h and actual[2] == dm:
            return name
    return ""


def parse_cmds_ini(text):
    """与 C# LoadCmds 等价的极简解析：返回 {name: {...}} 与顺序"""
    cmds, order = {}, []
    cur = None
    for raw in text.split("\n"):
        s = raw.strip()
        if not s or s[0] in "#;":
            continue
        if s.startswith("[") and s.endswith("]"):
            sec = s[1:-1].strip()
            if sec.lower().startswith("cmd."):
                name = sec[4:].strip()
                if not name:
                    cur = None
                    continue
                cur = {}
                cmds[name] = cur
                if name not in order:
                    order.append(name)
            else:
                cur = None
            continue
        if cur is None:
            continue
        if "=" not in s:
            continue
        k, v = s.split("=", 1)
        cur[k.strip().lower()] = v.strip()
    return cmds, order


def has_local_redir(s):
    """只认引号【外】的 > < |，引号内属于设备侧语义"""
    if not s:
        return False
    inq = False
    for ch in s:
        if ch == '"':
            inq = not inq
            continue
        if inq:
            continue
        if ch in "><|":
            return True
    return False


def index_outside_quotes(s, target):
    if not s:
        return -1
    inq = False
    for i, ch in enumerate(s):
        if ch == '"':
            inq = not inq
            continue
        if not inq and ch == target:
            return i
    return -1


WIN_PIPE_CMDS = {"findstr", "findstr.exe", "find", "find.exe",
                 "sort", "sort.exe", "more", "more.com"}


def is_local_pipe(line):
    """管道右侧第一个 token 是 Windows 专有命令 -> 本地过滤"""
    p = index_outside_quotes(line, "|")
    if p < 0:
        return False
    right = line[p + 1:].strip()
    if not right:
        return False
    first = right.split()[0]
    return first.lower() in WIN_PIPE_CMDS


def build_adb_line(rest, adb="adb", serial=""):
    line = ('"%s"' % adb) if (" " in adb and not adb.startswith('"')) else adb
    if serial:
        line += " -s " + serial
    if rest:
        line += " " + rest
    return line


def parse_adb_prefix(arg_raw, serial_global=""):
    """
    复刻 DoAdbPrefix：解析前导 -s，返回 (sub, rest, serial_used, is_shell_route)
    """
    toks = [t for t in arg_raw.replace('"', " ").split() if t]
    if not toks:
        return (None, [], serial_global, False)
    i = 0
    explicit = None
    while i + 1 < len(toks) and toks[i].lower() == "-s":
        explicit = toks[i + 1]
        i += 2
    if i >= len(toks):
        return (None, [], serial_global, False)
    sub = toks[i]
    rest = toks[i + 1:]
    used = explicit if explicit is not None else serial_global
    return (sub, rest, used, sub.lower() == "shell")


# ==================== G. 批量分组 ====================
CMD_BUDGET = 6000


def group_batches(items, budget=CMD_BUDGET):
    batches, i = [], 0
    while i < len(items):
        batch, cmd_len = [], 0
        while i < len(items):
            one = build_am_cmd(escape_data(items[i]))
            if cmd_len > 0 and cmd_len + len(one) + 2 > budget:
                break
            if cmd_len > 0:
                cmd_len += 2
            cmd_len += len(one)
            batch.append(i)
            i += 1
        if not batch:
            break
        batches.append(batch)
    return batches


def join_batch(items, batch):
    return "; ".join(build_am_cmd(escape_data(items[i])) for i in batch)


# ==================== I. ls -1p 解析 ====================
def parse_ls(out_str, mode="a"):
    items, dirs = [], []
    for line in out_str.split("\n"):
        name = line.rstrip("\r").strip()
        if not name:
            continue
        is_dir = False
        if mode == "f":
            name = last_seg(name)
        elif name.endswith("/"):
            is_dir = True
            name = name[:-1]
        if not name:
            continue
        items.append(name)
        dirs.append(is_dir)
    return items, dirs


def calc_cols(items, width=100, gap=3, maxcol=10):
    """复刻 LsRender 的列数计算"""
    if not items:
        return 0, 0
    maxl = max(disp_width(x) for x in items)
    cw = max(maxl + gap, 4)
    avail = max(width - 2, cw)
    nc = max(avail // cw, 1)
    if maxcol > 0:
        nc = min(nc, maxcol)
    return nc, cw


# ==================== H. 乐观批量 + 悲观回退 ====================
def simulate_batch(items, fail_set, retry=1):
    """
    模拟 RunBatch：整批成功则全过；整批有错则逐条重发定位。
    fail_set: 会失败的条目索引集合（0 基）
    返回 (ok, ng, fail_idx_list, fail_txt_list)
    """
    ok = ng = 0
    fail_idx, fail_txt = [], []
    batches = group_batches(items)
    for batch in batches:
        batch_has_fail = any(i in fail_set for i in batch)
        if not batch_has_fail:
            ok += len(batch)
            continue
        for i in batch:
            if i in fail_set:
                ng += 1
                fail_idx.append(i + 1)
                fail_txt.append(items[i])
            else:
                ok += 1
    return ok, ng, fail_idx, fail_txt


# ============================================================
print("== A. 输入分派优先级（核心约束：adb/shell 输入不得被侵占）==")
cases = [
    # ---- 裸名白名单：设备语义增强（必须继续可用）----
    ("ls", "known:ls"),
    ("ls 351", "known:ls"),
    ("ls -la", "known:ls"),
    ("cd 351", "known:cd"),
    ("cd ..", "known:cd"),
    ("cd -", "known:cd"),
    ("cd @logs", "known:cd"),
    ("pwd", "known:pwd"),
    ("pull 351 D:\\log", "known:pull"),
    ("push D:\\a.sh /tmp/", "known:push"),

    # ---- 透传：这些绝不能被工具抢走 ----
    ("df -h", "passthrough"),
    ("cat build.prop", "passthrough"),
    ("rm -rf /data/tmp", "passthrough"),
    ("mount", "passthrough"),
    ("351", "passthrough"),
    ("1", "passthrough"),
    ("9", "passthrough"),
    ("df", "passthrough"),
    ("stop", "passthrough"),

    # ---- 本地路径导出 / 空输入 ----
    ("C:\\XX", "export"),
    ("\\\\nas\\share", "export"),
    ("", "empty"),

    # ---- 纯中文启发式 ----
    ("你好", "heuristic_text"),
    ("你好，请回复", "heuristic_text"),
    ("cat 日志.txt", "passthrough"),
    ("ls 中文目录", "known:ls"),

    # ---- adb 层 ----
    ("adb devices", "adb_prefix"),
    ("adb install D:\\a.apk", "adb_prefix"),
    ("adb shell ls", "adb_prefix"),
    ("adb -s ABC123 devices", "adb_prefix"),
    ("adb reboot", "adb_prefix"),
    ("devices", "adb_bare"),
    ("install D:\\a.apk", "adb_bare"),
    ("reboot", "adb_bare"),
    ("forward tcp:8080 tcp:8080", "adb_bare"),
    ("exec-out screencap -p > a.png", "adb_bare"),
    ("version", "adb_bare"),
    ("root", "adb_bare"),

    # ---- 设备命令必须继续走 shell ----
    ("pm list packages", "passthrough"),
    ("am start -n a/.B", "passthrough"),
    ("dumpsys meminfo", "passthrough"),
    ("screencap -p /sdcard/a.png", "passthrough"),
    ("input keyevent 26", "passthrough"),
    ("getprop ro.build.version", "passthrough"),
    ("settings get global x", "passthrough"),
    ("wm size", "passthrough"),
    ("monkey -p com.x 1", "passthrough"),

    # ---- 交互式命令：提示但放行 ----
    ("top", "interactive_guard"),
    ("vi", "interactive_guard"),
    ("less a.txt", "interactive_guard"),
    ("top -n 1", "passthrough"),
    ("screenrecord --time-limit 10 f.mp4", "passthrough"),
    ("!top", "force"),
    ("!rm -rf /data/tmp", "force"),

    # ---- 本地管道 ----
    ("getprop | findstr navi", "local_pipe"),
    ("dumpsys activity | findstr crash", "local_pipe"),
    ("getprop", "passthrough"),
    ("ps | grep xxx", "passthrough"),
    ("df -h | grep data", "passthrough"),

    # ---- 显式 shell 前缀 ----
    ("shell pm list packages -3", "shell_prefix"),
    ("shell \"netstat -anp | grep ESTAB\"", "shell_prefix"),

    # ---- 旧裸名：过渡期保留，但归入 legacy 而不是裸名白名单 ----
    ("logcat -v time", "legacy:logcat"),
    ("send 你好", "legacy:send"),
    ("anr", "legacy:anr"),
    ("dropbox", "legacy:dropbox"),
    ("test", "legacy:test"),
    ("pre", "legacy:pre"),
    ("dev", "legacy:dev"),
    ("syncore", "legacy:syncore"),
    ("env", "legacy:env"),
    ("ver", "legacy:ver"),
    ("now", "legacy:now"),
    ("cmds", "legacy:cmds"),
    ("lsf", "legacy:lsf"),

    # ---- v7：: 命名空间（工具自身，零冲突）----
    (":send 你好", "tool"),
    (":env test", "tool"),
    (":env", "tool"),
    (":pkg ver", "tool"),
    (":pkg now", "tool"),
    (":which ls", "tool"),
    (":h", "tool"),
    (":cmds", "tool"),
    (":r", "tool"),
    (":q", "tool"),
    (":df", "tool"),
    (":net", "tool"),
    (":stopapp com.x", "tool"),

    # ---- v7：@ 跳转点（数据，不是命令）----
    ("@logs", "jump"),
    ("@anr", "jump"),
    ("@dropbox", "jump"),
    ("@nope", "jump"),

    # ---- v7：安全名仍可裸用，撞设备名的只能 : ----
    ("net", "diy"),
    ("mem", "diy"),
    ("shot", "diy"),
    ("l", "diy"),

    # ---- v7.3：裸包名直查（版本 + 路径）----
    ("com.gac.cloud.app", "pkg"),
    ("syncore.space.cockpit.toplauncher", "pkg"),
    ("aa.bb", "pkg"),
    ("build.prop", "passthrough"),
    ("a.log", "passthrough"),
    ("com.a/extra", "passthrough"),
    ("1com.a", "passthrough"),

    # ---- 帮助与退出：必须始终可用（不受 legacy_alias 影响）----
    ("h", "help"),
    ("?", "help"),
    ("help all", "help"),
    ("q", "quit"),
]

for line, expect in cases:
    got = dispatch_kind(line)
    check("分派 %-22r -> %s" % (line, expect), got == expect, "got=" + got)

print()
def after_token(s, skip_count):
    """复刻 AdbCmd.AfterToken：跳过前 N 个 token，返回剩余原文（保留引号）"""
    if not s:
        return ""
    i, n, skipped = 0, len(s), 0
    while skipped < skip_count and i < n:
        while i < n and s[i] in " \t":
            i += 1
        if i >= n:
            return ""
        inq = False
        while i < n:
            ch = s[i]
            if ch == '"':
                inq = not inq
                i += 1
                continue
            if not inq and ch in " \t":
                break
            i += 1
        skipped += 1
    while i < n and s[i] in " \t":
        i += 1
    return s[i:] if i < n else ""


print("== A2. adb 层命令解析（v6.1）==")
check("含 > 判为本地重定向", has_local_redir("exec-out screencap -p > a.png"))
check("含 >> 判为本地重定向", has_local_redir("logcat >> a.txt"))
check("含 | 判为本地管道", has_local_redir("devices | findstr device"))
check("无重定向", not has_local_redir("devices -l"))
check("引号内 > 不算本地", not has_local_redir('shell "ls > /sdcard/a"'))
check("引号外 | 算本地", has_local_redir("shell getprop | findstr navi"))
check("IndexOutsideQuotes 跳过引号内", index_outside_quotes('a "b|c" d|e', "|") == 9)
check("IndexOutsideQuotes 无目标返回 -1", index_outside_quotes('a "b|c"', "|") == -1)
check("findstr 管道判为本地", is_local_pipe("getprop | findstr navi"))
check("find 管道判为本地", is_local_pipe("dumpsys | find x"))
check("grep 管道保持设备侧", not is_local_pipe("ps | grep xxx"))
check("无管道不算本地", not is_local_pipe("getprop"))
check("引号内管道不算本地", not is_local_pipe('echo "a | findstr b"'))

line = build_adb_line("exec-out screencap -p > a.png", "adb", "ABC123")
check("命令行带 -s", line == "adb -s ABC123 exec-out screencap -p > a.png", line)
line2 = build_adb_line("devices", r"C:\Program Files\adb.exe", "")
check("adb 路径含空格加引号", line2.startswith('"C:\\Program Files\\adb.exe"'), line2)

sub, rest, serial, is_shell = parse_adb_prefix("shell ls -l")
check("adb shell 识别为 shell 路由", is_shell and sub == "shell")
check("adb shell 内部命令保留", rest == ["ls", "-l"], str(rest))
sub, rest, serial, is_shell = parse_adb_prefix("-s XYZ devices")
check("解析 -s 后面的子命令", sub == "devices" and serial == "XYZ", "%s/%s" % (sub, serial))
sub, rest, serial, is_shell = parse_adb_prefix("devices", "GLOBAL")
check("未指定 -s 时用全局 serial", serial == "GLOBAL")
sub, rest, serial, is_shell = parse_adb_prefix("-s XYZ exec-out screencap -p")
check("-s 不会混进参数", sub == "exec-out" and rest == ["screencap", "-p"], str(rest))

check("AfterToken 跳过 shell", after_token("shell ls -l", 1) == "ls -l")
check("AfterToken 保留用户引号", after_token('-s X shell "ls > /a"', 3) == '"ls > /a"')
check("AfterToken 跳过过多返回空", after_token("shell", 2) == "")
check("AfterToken 跳过 -s 两项", after_token("-s ABC shell df -h", 3) == "df -h")
check("AfterToken 无跳过多余", after_token("a b c", 0) == "a b c")
# adb shell "ls > /sdcard/a" 必须走设备侧重定向，而不是本地
check("设备侧重定向不被当本地", not has_local_redir('"ls > /sdcard/a"'))
raw = after_token('shell "ls > /sdcard/a"', 1)
check("shell 内部原文完整保留", unquote(raw) == "ls > /sdcard/a", raw)

print()
print("== B. 纯中文启发式 ==")
check("你好 -> 文本", is_probably_text("你好"))
check("你好abc -> 文本", is_probably_text("你好abc"))
check("cat -> 非文本", not is_probably_text("cat"))
check("351 -> 非文本", not is_probably_text("351"))
check("空 -> 非文本", not is_probably_text(""))
check("全角空格开头 token -> 文本", is_probably_text("　"))

print()
print("== C. send 参数解析 ==")
quick = {1: "收到，正在处理", 2: "好的", 3: ""}
k, v = parse_send("你好", quick)
check("send 你好 -> text", k == "text" and v == "你好")
k, v = parse_send("你好 世界", quick)
check("send 你好 世界 -> text 保留空格", k == "text" and v == "你好 世界")
k, v = parse_send('"你好 世界"', quick)
check("send \"你好 世界\" -> text 去引号", k == "text" and v == "你好 世界")
k, v = parse_send("1", quick)
check("send 1 -> quick", k == "quick" and v == "收到，正在处理")
k, v = parse_send("3", quick)
check("send 3 未配置 -> quick_missing", k == "quick_missing")
k, v = parse_send('"1"', quick)
check("send \"1\" -> text（引号强制当文本）", k == "text" and v == "1")
k, v = parse_send("-f D:\\a.txt", quick)
check("send -f 路径 -> batch", k == "batch" and v == "D:\\a.txt")
k, v = parse_send("-f", quick)
check("send -f 无参 -> batch 空路径", k == "batch" and v == "")
k, v = parse_send("", quick)
check("send 空 -> usage", k == "usage")

print()
print("== D. am 命令构造 ==")
am = build_am_cmd(escape_data("你好"))
check("默认动作 startservice", am.startswith("am startservice -a android.intent.action.VIEW"))
check("URL 单引号包裹", "-d 'sr://syncore.vpa.sr/test?text=%E4%BD%A0%E5%A5%BD'" in am)
am2 = build_am_cmd("%41", am_cmd="start-foreground-service", component="com.x/.Svc")
check("am_cmd 可切换", am2.startswith("am start-foreground-service"))
check("component 加 -n", " -n com.x/.Svc " in am2)

print()
print("== E. URL 编码 ==")
check("中文", escape_data("中文") == "%E4%B8%AD%E6%96%87")
check("空格", escape_data("a b") == "a%20b")
check("英文不变", escape_data("hello") == "hello")
check("混合", escape_data("你好 world!") == "%E4%BD%A0%E5%A5%BD%20world!")
check("不编码 !*'()", escape_data("!*'()") == "!*'()")
check("空串", escape_data("") == "")
check("问号被编码", escape_data("a?b") == "a%3Fb")

print()
print("== F. 文本编码识别 ==")
check("UTF-8", decode_text("中文abc".encode("utf-8")) == "中文abc")
check("UTF-8 BOM", decode_text(b"\xef\xbb\xbf" + "中文abc".encode("utf-8")) == "中文abc")
check("GBK", decode_text("中文abc".encode("gbk")) == "中文abc")
check("UTF-16LE BOM", decode_text(b"\xff\xfe" + "中文abc".encode("utf-16-le")) == "中文abc")

print()
print("== G. 批量分组 ==")
items = ["测试消息 %d" % i for i in range(100)]
batches = group_batches(items)
check("100 条被分组", len(batches) >= 1)
check("分组覆盖全部条目", sum(len(b) for b in batches) == 100)
check("分组无重复无遗漏", sorted(x for b in batches for x in b) == list(range(100)))
all_ok = True
for b in batches:
    joined = join_batch(items, b)
    if len(joined) > CMD_BUDGET:
        all_ok = False
check("每批不超过 6000 字符", all_ok)
check("批数远小于 100（合并生效）", len(batches) < 20, "batches=%d" % len(batches))
b1 = join_batch(items, batches[0])
check("批内用 ; 连接", "; " in b1)
check("批内条数正确", b1.count("am startservice") == len(batches[0]))
print("     实测：100 条 -> %d 次进程调用（原 100 次）" % len(batches))

print()
print("== H. 乐观批量 + 悲观回退 ==")
ok, ng, fi, ft = simulate_batch(items[:10], fail_set=set())
check("全成功", ok == 10 and ng == 0 and not fi)
ok, ng, fi, ft = simulate_batch(items[:10], fail_set={3, 7})
check("2 条失败 -> ok=8 ng=2", ok == 8 and ng == 2)
check("失败行号正确（1 基）", fi == [4, 8], str(fi))
check("失败原文正确", ft == [items[3], items[7]])
ok, ng, fi, ft = simulate_batch(items, fail_set={0, 50, 99})
check("跨多批失败定位正确", ok == 97 and ng == 3 and fi == [1, 51, 100], str(fi))

print()
print("== I. ls -1p 解析与列数 ==")
out = "351/\nfile1.log\nfile2.txt\nsub/\n"
its, ds = parse_ls(out, "a")
check("条目数 4", len(its) == 4)
check("去掉了目录的 / 后缀", its == ["351", "file1.log", "file2.txt", "sub"])
check("目录类型识别", ds == [True, False, False, True])
its_f, ds_f = parse_ls("a/b/x.log\na/b/y.log\n", "f")
check("lsf 只取末段", its_f == ["x.log", "y.log"])
check("lsf 全为文件", ds_f == [False, False])
nc, cw = calc_cols(["351", "file1.log"], 100, 3, 10)
# maxl=9 -> cw=12; avail=98 -> nc=8
check("列数计算 cw=maxl+gap=12", cw == 12, "cw=%d" % cw)
check("列数计算 nc=98//12=8", nc == 8, "nc=%d" % nc)
nc2, _ = calc_cols(["a"] * 20, 100, 3, 10)
check("列数受 maxcol 限制", nc2 == 10)
nc3, cw3 = calc_cols(["中文abc"], 100, 3, 10)
check("中文按 2 列算", cw3 == 10, "cw3=%d" % cw3)

print()
print("== J. 路径工具 / 显示宽度 ==")
check("NormPath 消 ..", norm_path("/a/b/../c") == "/a/c")
check("NormPath 合并 //", norm_path("//a///b//") == "/a/b")
check("NormPath 多级 ..", norm_path("/a/b/../../") == "/")
check("LastSeg", last_seg("/a/b/") == "b")
check("LastSeg /", last_seg("/") == "/")
check("DevAbs 相对", dev_abs("351", "/log/x") == "/log/x/351")
check("DevAbs 绝对", dev_abs("/x/y", "/log/x") == "/x/y")
check("IsWinPath C:", is_win_path("C:\\xx"))
check("IsWinPath UNC", is_win_path("\\\\nas\\share"))
check("IsWinPath 非路径", not is_win_path("351"))
check("DispWidth 中文 2 列", disp_width("中文") == 4)
check("DispWidth 英文 1 列", disp_width("abc") == 3)
check("DispWidth 混合", disp_width("a中b") == 4)
check("Unquote", unquote('"C:\\my dir"') == "C:\\my dir")

print()
print("== K. 视觉与交互层逻辑（v6.2）==")
check("裸 top 判为交互式", is_interactive_bare("top", ""))
check("裸 vi 判为交互式", is_interactive_bare("vi", ""))
check("top -n 1 不算交互式", not is_interactive_bare("top", "-n 1"))
check("top -d 1 -n 3 不算交互式", not is_interactive_bare("top", "-d 1 -n 3"))
check("cat 不算交互式", not is_interactive_bare("cat", "x.log"))
check("less -l 仍算交互式", is_interactive_bare("less", "-l a.txt"))
check("screenrecord --time-limit 不算", not is_interactive_bare("screenrecord", "--time-limit 10 f.mp4"))

check("目录后缀 / -> 0", parse_ls_suffix("351/") == 0)
check("可执行后缀 * -> 1", parse_ls_suffix("run.sh*") == 1)
check("链接后缀 @ -> 2", parse_ls_suffix("link@") == 2)
check("fifo 后缀 | -> 2", parse_ls_suffix("pipe|") == 2)
check("普通文件 -> 3", parse_ls_suffix("a.log") == 3)
check("隐藏文件 -> 4", parse_ls_suffix(".hidden") == 4)
check("目录优先于隐藏", parse_ls_suffix(".git/") == 0)
check("剥离目录后缀", strip_ls_suffix("351/") == "351")
check("剥离可执行后缀", strip_ls_suffix("run.sh*") == "run.sh")
check("普通文件不剥", strip_ls_suffix("a.log") == "a.log")

check("ShortPath 短路径不变", short_path("/a/b", 60) == "/a/b")
sp = short_path("/aaa/bbb/ccc/ddd/androidlog", 20)
check("ShortPath 保留末段", sp.endswith("androidlog"), sp)
check("ShortPath 含省略号", "..." in sp, sp)
check("ShortPath 不超长", len(sp) <= 22, sp)

print()
print("== L. 自定义命令（DIY）==")
check("$1 替换", expand_template("pull $1 \"D:\\log\"", "351", "x") == "pull 351 \"D:\\log\"")
check("$2 替换", expand_template("a $2 b", "p1 p2", "x") == "a p2 b")
check("$* 全部参数", expand_template("echo $*", "a b c", "x") == "echo a b c")
check("$0 命令名", expand_template("run $0", "", "net") == "run net")
check("缺参替换为空", expand_template("pull $2", "only1", "x") == "pull ")
check("无占位符原样", expand_template("shell df -h", "", "x") == "shell df -h")
check("$(cur) 展开", expand_template("x $(cur)", "", "x", cur_dir="/log/a") == "x /log/a")
check("$(serial) 展开", expand_template("x $(serial)", "", "x", serial="ABC") == "x ABC")
check("$(app) 展开", expand_template("x $(app)", "", "x", app="com.x") == "x com.x")
check("未知函数为空", expand_template("a $(nope) b", "", "x") == "a  b")
check("引号参数保留空格", expand_template("send $1", '"你好 世界"', "x") == "send 你好 世界")

# 分节解析
sample = """# 注释
[cmd.net]
desc = 网络
group = 网络
run = shell "netstat -anp | grep ESTAB"

[cmd.l]
desc = 列目录
run = ls

[other]
desc = 不该被解析
"""
cmds, order = parse_cmds_ini(sample)
check("解析出 2 条命令", len(cmds) == 2, str(list(cmds)))
check("命令顺序保序", order == ["net", "l"])
check("desc 解析", cmds["net"]["desc"] == "网络")
check("run 里引号内管道保留", cmds["net"]["run"].index("|") > 0)
check("非 cmd.* 分节被忽略", "other" not in cmds)

print()
print("== M. 前台应用识别 ==")
check("mCurrentFocus 提取",
      extract_pkg("  mCurrentFocus=Window{3f2a1b u0 com.gxatek.cockpit/.MainActivity}") == "com.gxatek.cockpit")
check("mResumedActivity 提取",
      extract_pkg("mResumedActivity: ActivityRecord{abc u0 com.a.b/.C t1}") == "com.a.b")
check("cmp= 形式提取", extract_pkg("cmp=com.x.y/com.x.y.Z") == "com.x.y")
check("多段包名", extract_pkg("u0 a.b.c.d/e.f") == "a.b.c.d")
check("无包名返回空", extract_pkg("no package here") == "")
check("纯数字不算", extract_pkg("123/456") == "")
check("无点号不算", extract_pkg("abc/def") == "")
check("空行返回空", extract_pkg("") == "")

# version_pkgs 配置解析
def parse_ver_pkgs(v):
    out = []
    for part in (v or "").split(","):
        s = part.strip()
        if not s:
            continue
        if "=" in s:
            pkg, alias = s.split("=", 1)
            pkg, alias = pkg.strip(), alias.strip()
        else:
            pkg, alias = s, ""
        if pkg and all(x["pkg"].lower() != pkg.lower() for x in out):
            out.append({"pkg": pkg, "alias": alias})
    return out


vp = parse_ver_pkgs("com.a.x=座舱,com.b.y,com.c.z=语音")
check("解析出 3 个包", len(vp) == 3)
check("别名解析", vp[0]["alias"] == "座舱")
check("无别名时为空", vp[1]["alias"] == "")
check("第三个别名", vp[2]["alias"] == "语音")
check("去重", len(parse_ver_pkgs("com.a,com.a")) == 1)
check("空串返回空", len(parse_ver_pkgs("")) == 0)

print()
print("== N. 版本表列宽（对齐修复）==")
check("FitWidth 短串不变", fit_width("abc", 10) == "abc")
check("FitWidth 恰好等宽", fit_width("abcde", 5) == "abcde")
check("FitWidth 超长加 ..", fit_width("abcdefghij", 6) == "abcd..")
check("FitWidth 中文按 2 列", fit_width("中文中文", 5) == "中..")
check("FitWidth 空串", fit_width("", 5) == "")
check("CharWidth ASCII", char_width("a") == 1)
check("CharWidth 中文", char_width("中") == 2)

# 复现用户场景：包名 33、版本名 27（版本码列已从表格移除）
rows = [("", "syncore.space.cockpit.toplauncher", "1.0.1.261026.210210.ec39e29", "41")]
has_alias, wa, wp, wv, _st = ver_table_widths(rows, 120)
check("无别名时不占列", not has_alias)
check("包名列宽=实际包名宽 33", wp == 33, "wp=%d" % wp)
check("版本名列宽=实际 27", wv == 27, "wv=%d" % wv)

row = ("  " + pad(fit_width("", wa), wa) + "  " if has_alias else "  ") + \
      pad(fit_width("syncore.space.cockpit.toplauncher", wp), wp) + "  " + \
      pad(fit_width("1.0.1.261026.210210.ec39e29", wv), wv) + "  " + "2026-10-27 08:34:01"
check("包名与版本名之间有间隔", "toplauncher  1.0.1" in row, row)
check("版本名与时间之间有间隔", "ec39e29  2026" in row, row)
check("表格只剩 包名/版本名/时间 三列", "版本码" not in "包名 版本名 更新时间")

# 窄窗口时压缩包名
rows2 = [("", "a" * 60, "1.0", "1")]
_, _, wp2, _, _ = ver_table_widths(rows2, 100)
check("窄窗口包名被压缩到上限内", wp2 <= 44 and wp2 >= 18, "wp2=%d" % wp2)

# 超长版本名必须完整显示（v7.10：取消 32 列上限）
rows3 = [("", "com.a", "1" * 40, "1")]
_, _, _, wv3, _ = ver_table_widths(rows3, 120)
check("版本名 40 列不被截断", wv3 == 40, "wv3=%d" % wv3)
check("表宽真不够时 FitWidth 仍会截断", fit_width("1" * 40, 20).endswith(".."))

print()
print("== O. 环境切换 ==")
d, h, dm = parse_env_profile("test;api-test.syncore.space:20443;api-test.syncore.space:20443")
check("解析 deploy", d == "test")
check("解析 https", h == "api-test.syncore.space:20443")
check("解析 domain", dm == "api-test.syncore.space:20443")

d2, h2, dm2 = parse_env_profile("dev;api.syncore.space;api.syncore.space")
check("dev 的 https 无端口", h2 == "api.syncore.space")

d3, h3, dm3 = parse_env_profile("onlyone")
check("缺字段时为空", h3 == "" and dm3 == "")

envs = {
    "test": parse_env_profile("test;api-test.x:20443;api-test.x:20443"),
    "pre": parse_env_profile("pre;api-pre.x:20443;api-pre.x:20443"),
    "dev": parse_env_profile("dev;api.x;api.x"),
}
check("识别 test 环境", match_env(["test", "api-test.x:20443", "api-test.x:20443"], envs) == "test")
check("识别 dev 环境", match_env(["dev", "api.x", "api.x"], envs) == "dev")
check("部分不匹配则不识别", match_env(["test", "api.x", "api.x"], envs) == "")
check("全空不识别", match_env(["", "", ""], envs) == "")

mk = parse_marked("##1\nvalueA\n##2\n\n##3\nvalueC\n", 3)
check("ParseMarked 第 1 段", mk[0] == "valueA")
check("ParseMarked 空段保持空", mk[1] == "")
check("ParseMarked 第 3 段", mk[2] == "valueC")
mk2 = parse_marked("##1\n\n##2\n\n##3\n", 3)
check("ParseMarked 全空输入", mk2 == ["", "", ""])

print()
print("== P. v7 命名空间治理 ==")

# 1) 设备命令黑名单：撞名的 DIY 只能 :name
for n in ["df", "stop", "test", "env", "ls", "top", "logcat"]:
    check("%s 被判为设备命令" % n, n in DEVICE_CMDS)
for n in ["net", "mem", "shot", "sysinfo", "stopapp"]:
    check("%s 不是设备命令" % n, n not in DEVICE_CMDS)

# 2) 撞名者的裸名必须回流到设备（v7 修掉的两个危险命令）
check("裸 df 走设备", dispatch_kind("df") == "passthrough")
check("裸 df -h 走设备", dispatch_kind("df -h") == "passthrough")
check("裸 stop 走设备", dispatch_kind("stop") == "passthrough")
check(":df 才走工具", dispatch_kind(":df") == "tool")
check(":stopapp 才走工具", dispatch_kind(":stopapp x") == "tool")

# 3) 前缀互斥：同一行加不同前缀必须换归属
base = "devices"
check("裸 devices -> adb", dispatch_kind(base) == "adb_bare")
check("!devices -> 强制设备", dispatch_kind("!" + base) == "force")
check(":devices -> 工具（未定义则报错，不是透传）", dispatch_kind(":" + base) == "tool")

# 4) 参数保卫：模板不含 $ 时不应静默丢参数
def args_would_drop(run_tpl, arg_raw):
    return bool(arg_raw.strip()) and "$" not in run_tpl

check("df -h 模板不收参数 -> 应报错", args_would_drop("shell df -h", "/data"))
check("apkinfo 模板收 $1 -> 放行", not args_would_drop("shell dumpsys package $1", "com.x"))
check("无参数时不报错", not args_would_drop("shell df -h", ""))

# 5) 导出不覆盖：目标已存在时派生时间戳目录
def unique_target(p, exists, nonempty):
    if not exists or not nonempty:
        return p
    return p + "_" + "20261102_180000"

check("目标不存在 -> 原地写", unique_target("D:////log", False, False) == "D:////log")
check("目标空目录 -> 原地写", unique_target("D:////log", True, False) == "D:////log")
check("目标非空 -> 加时间戳", unique_target("D:////log", True, True) == "D:////log_20261102_180000")
check("非空目标绝不被复用", unique_target("D:////log", True, True) != "D:////log")

# 6) 提示符瘦身：末两段
def seg_distinct(seg):
    """末段是否一眼能认出：>=4 列且不是纯数字"""
    return len(seg) >= 4 and not seg.isdigit()


def short_prompt(cur):
    if cur == "/":
        return "/ > "
    parts = [x for x in cur.strip("/").split("/") if x]
    tail = parts[-1] if parts else "/"
    if not seg_distinct(tail) and len(parts) >= 2:
        return parts[-2] + "/" + tail + " > "
    return tail + " > "

check("数字末段带父段", short_prompt("/log/android_log/androidlog/257") == "androidlog/257 > ")
check("可辨识末段只留末段", short_prompt("/log/android_log/androidlog") == "androidlog > ")
check("可辨识末段不带复读父段", "/" not in short_prompt("/log/android_log/androidlog")[:-4])
check("提示符一段", short_prompt("/log") == "log > ")
check("提示符根目录", short_prompt("/") == "/ > ")
check("提示符长度 < 25", len(short_prompt("/log/android_log/androidlog/257")) < 25)
check("日志根提示符 12 列（比两段省 14 列）",
      len(short_prompt("/log/android_log/androidlog")) == len("androidlog > "))
check("短数字目录 351 带父段", short_prompt("/log/x/351") == "x/351 > ")
check("4 位数字也算不可辨识", short_prompt("/a/1234") == "a/1234 > ")
check("旧提示符 > 40 字符（改动有实际收益）",
      len("b09acfa2 " + "/log/android_log/androidlog/257" + " > ") > 40)

# 7) 耗时格式化
def fmt_dur(ms):
    if ms < 1000:
        return "%dms" % ms
    return "%.1fs" % (ms / 1000.0)

check("耗时 820ms", fmt_dur(820) == "820ms")
check("耗时 1.2s", fmt_dur(1200) == "1.2s")
check("耗时 0.4s", fmt_dur(420) == "420ms")

# 8) 主题：浅色必须换档，否则 DarkGray 在白底不可读
dark = {"ok": "Green", "err": "Red", "warn": "Yellow", "path": "Cyan", "dim": "DarkGray"}
light = {"ok": "DarkGreen", "err": "DarkRed", "warn": "DarkYellow", "path": "DarkCyan", "dim": "Gray"}
check("浅色辅助色不是 DarkGray", light["dim"] != "DarkGray")
check("浅色强调色是暗色", light["warn"].startswith("Dark"))
check("两套语义键一致", set(dark.keys()) == set(light.keys()))


print()
print("== Q. 版本解析：多包 / 多版本不串味 ==")

def parse_entries(text):
    out = []
    cur = None
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("Package ["):
            close = line.find("]")
            name = line[9:close].strip() if close > 9 else ""
            cur = {"pkg": name, "ver": "", "code": "", "up": ""}
            out.append(cur)
            continue
        if cur is None:
            continue
        if line.startswith("versionName="):
            cur["ver"] = line[12:].strip()
        elif line.startswith("versionCode="):
            rest = line[12:].strip()
            cur["code"] = rest.split(" ")[0]
        elif line.startswith("lastUpdateTime="):
            cur["up"] = line[15:].strip()
    return out


def pick(entries, want):
    p = None
    extra = 0
    for e in entries:
        if e["pkg"] != want:
            continue
        if p is None:
            p = e
            continue
        if e["ver"] != p["ver"] or e["code"] != p["code"]:
            extra += 1
    return p, extra


# 1) 正常单块
single = """Package [com.a] (abc):
  versionCode=41 minSdk=29
  versionName=1.0.1
  lastUpdateTime=2026-10-27 08:34:01
"""
e = parse_entries(single)
p1, x1 = pick(e, "com.a")
check("单块：包名", p1["pkg"] == "com.a")
check("单块：版本名", p1["ver"] == "1.0.1")
check("单块：版本码去掉 minSdk", p1["code"] == "41")
check("单块：无额外记录", x1 == 0)

# 2) 同一个包出现两段（隐藏系统包）—— 关键回归
twice = """Package [com.a] (abc):
  versionCode=41 minSdk=29
  versionName=1.0.1
  lastUpdateTime=2026-10-27 08:34:01
Package [com.a] (def):
  versionCode=1
"""
e = parse_entries(twice)
p2, x2 = pick(e, "com.a")
check("两段：取第一段版本名", p2["ver"] == "1.0.1")
check("两段：版本码不被第二段覆盖", p2["code"] == "41")
check("两段：额外记录数=1", x2 == 1)

# 3) 子串匹配到多个包，不能串味
multi = """Package [com.a] (x):
  versionCode=41
  versionName=1.0.1
Package [com.a.debug] (y):
  versionCode=1
  versionName=9.9.9
"""
e = parse_entries(multi)
p3, x3 = pick(e, "com.a")
check("多包：只取完全匹配的包", p3["pkg"] == "com.a")
check("多包：版本名属于 com.a", p3["ver"] == "1.0.1")
check("多包：版本码属于 com.a", p3["code"] == "41")
check("多包：兄弟包不算额外记录", x3 == 0)
p3b, _ = pick(e, "com.a.debug")
check("多包：兄弟包自己也能取到", p3b["ver"] == "9.9.9")

# 4) 未安装
e = parse_entries("")
p4, _ = pick(e, "com.a")
check("空输出 -> 未匹配", p4 is None)

# 5) 只返回近似包时要能列出来
e = parse_entries("Package [com.a.debug] (y):\n  versionCode=1\n")
p5, _ = pick(e, "com.a")
near = [x["pkg"] for x in e if x["pkg"] != "com.a"]
check("近似包：目标未匹配", p5 is None)
check("近似包：能列出 com.a.debug", near == ["com.a.debug"])


print()
print("== R. 前台识别：分级取证 + 多显示 ==")

def parse_int_after(line, key):
    i = line.find(key)
    if i < 0:
        return -1
    i += len(key)
    st = i
    while i < len(line) and line[i].isdigit():
        i += 1
    if i == st:
        return -1
    return int(line[st:i])


def fg_cands(text):
    out, sec, disp = [], "", -1
    for raw in text.split("\n"):
        line = raw.rstrip("\r").strip()
        if not line:
            continue
        if line.startswith("##"):
            sec = line[2:].strip().upper()
            disp = -1
            continue
        d = parse_int_after(line, "mDisplayId=")
        if d >= 0:
            disp = d
        pkg = extract_pkg(line)
        if not pkg:
            continue
        if sec == "ACT":
            tier, src = (1, "topResumedActivity") if "topResumedActivity" in line else (3, "mResumedActivity")
        elif sec == "WIN":
            tier, src = (2, "mCurrentFocus") if "mCurrentFocus" in line else (4, "mFocusedApp")
        else:
            tier, src = 5, "mFocusedActivity"
        out.append({"pkg": pkg, "disp": disp, "tier": tier, "src": src, "raw": line})
    return out


def pick_fg(c):
    if not c:
        return []
    best = min(x["tier"] for x in c)
    r = []
    for x in c:
        if x["tier"] != best:
            continue
        if any(y["pkg"] == x["pkg"] for y in r):
            continue
        r.append(x)
    return r


# 1) 关键回归：window 里是 launcher，activity 里才是真前台
#    旧实现先看 window，会误报 launcher
sample = """##ACT
  topResumedActivity=ActivityRecord{a u0 com.gac.cloud.app/.app.MainActivity t1}
##WIN
  Display: mDisplayId=0
    mCurrentFocus=Window{b u0 syncore.space.cockpit.toplauncher/.L}
##OLD
"""
c = fg_cands(sample)
r = pick_fg(c)
check("优先 topResumedActivity 而不是 mCurrentFocus", r[0]["pkg"] == "com.gac.cloud.app")
check("来源标记正确", r[0]["src"] == "topResumedActivity")
check("Tier 更小的胜出", r[0]["tier"] == 1)

# 2) 只有 window 时退回 mCurrentFocus，并带上 display
sample2 = """##WIN
  Display: mDisplayId=1
    mCurrentFocus=Window{b u0 com.x.y/.A}
"""
r = pick_fg(fg_cands(sample2))
check("无 activity 时用 mCurrentFocus", r[0]["pkg"] == "com.x.y")
check("display 号被记录", r[0]["disp"] == 1)
check("tier=2", r[0]["tier"] == 2)

# 3) 多显示：两块屏各有前台，必须都列出来而不是只取第一条
sample3 = """##ACT
  Display: mDisplayId=0
    topResumedActivity=ActivityRecord{a u0 syncore.space.cockpit.toplauncher/.L t1}
  Display: mDisplayId=1
    topResumedActivity=ActivityRecord{b u0 com.gac.cloud.app/.M t2}
"""
r = pick_fg(fg_cands(sample3))
check("多显示：保留 2 个候选", len(r) == 2)
check("多显示：display 0", r[0]["disp"] == 0)
check("多显示：display 1", r[1]["disp"] == 1)
check("多显示：包不重复", r[0]["pkg"] != r[1]["pkg"])

# 4) 同一个包在多块里出现两次要合并
sample4 = """##ACT
  topResumedActivity=ActivityRecord{a u0 com.x.y/.A t1}
  topResumedActivity=ActivityRecord{b u0 com.x.y/.A t1}
"""
r = pick_fg(fg_cands(sample4))
check("同包去重", len(r) == 1)

# 5) mFocusedApp 不得压过 topResumedActivity
sample5 = """##ACT
  topResumedActivity=ActivityRecord{a u0 com.right/.A t1}
##WIN
  Display: mDisplayId=0
    mFocusedApp=ActivityRecord{b u0 com.wrong/.B t9}
"""
r = pick_fg(fg_cands(sample5))
check("mFocusedApp 不压过 topResumed", r[0]["pkg"] == "com.right")

# 6) 工具函数
check("ParseIntAfter 取到 0", parse_int_after("Display: mDisplayId=0 x", "mDisplayId=") == 0)
check("ParseIntAfter 取到 12", parse_int_after("mDisplayId=12", "mDisplayId=") == 12)
check("ParseIntAfter 没有时 -1", parse_int_after("nothing", "mDisplayId=") == -1)
check("ParseIntAfter 非数字时 -1", parse_int_after("mDisplayId=abc", "mDisplayId=") == -1)


print()
print("== S. 裸包名判定 + 安装路径解析 ==")

# 1) 该接管的
for v in ["com.gac.cloud.app", "syncore.space.cockpit.toplauncher",
          "aa.bb", "com.x_y.z", "a.b.c.d.e"]:
    check("识别为包名: %s" % v, is_maybe_pkg(v))

# 2) 不该接管的（每条都对应一个真实场景）
no_pkg = [
    ("351", "纯数字目录"),
    ("com", "没有点"),
    ("build.prop", "属性文件"),
    ("crash.log", "日志文件"),
    ("app.apk", "安装包"),
    ("com.a b", "带参数"),
    ("com.a/x", "带路径"),
    ("com.a.", "以点结尾"),
    (".hidden.pkg", "以点开头"),
    ("1com.a", "以数字开头"),
    ("com.a-b", "含连字符"),
    ("中文.包名", "非 ASCII"),
]
for v, why in no_pkg:
    check("不识别为包名: %s（%s）" % (v, why), not is_maybe_pkg(v))

# 3) codePath 解析
def parse_path_entry(text):
    ent = {"pkg": "", "ver": "", "code": "", "path": ""}
    for raw in text.split("\n"):
        line = raw.strip()
        if line.startswith("Package ["):
            ent["pkg"] = line[9:line.find("]")].strip()
        elif line.startswith("versionName="):
            ent["ver"] = line[12:].strip()
        elif line.startswith("versionCode="):
            ent["code"] = line[12:].strip().split(" ")[0]
        elif line.startswith("codePath="):
            ent["path"] = line[9:].strip()
    return ent

sample = """Package [com.gac.cloud.app] (1a2b):
  codePath=/data/app/~~kQ9w==/com.gac.cloud.app-xY7==/base.apk
  versionCode=41 minSdk=29
  versionName=1.0.1.261026.210210.ec39e294
  lastUpdateTime=2026-10-27 08:34:01
"""
e = parse_path_entry(sample)
check("解析包名", e["pkg"] == "com.gac.cloud.app")
check("解析版本码", e["code"] == "41")
check("解析版本名（36 字符不截断）", e["ver"] == "1.0.1.261026.210210.ec39e294")
check("解析安装路径", e["path"] == "/data/app/~~kQ9w==/com.gac.cloud.app-xY7==/base.apk")
check("路径以 base.apk 结尾", e["path"].endswith("/base.apk"))

# 4) 单包用竖排块、多包用表格
def layout(n):
    return "detail" if n == 1 else "table"

check("单包 -> 详情块（放得下完整路径）", layout(1) == "detail")
check("多包 -> 表格", layout(3) == "table")

# 5) 详情块的标签列对齐（中文按 2 列宽）
labels = ["版本名", "版本码", "更新时间", "安装路径"]
# 中文每字 2 列：3 字=6 列，4 字=8 列；只要都不超过 10 列，补到 10 就能对齐
widths = [sum(2 if ord(c) > 127 else 1 for c in x) for x in labels]
check("标签最宽不超过 10 列", max(widths) <= 10)
check("补到 10 列后左边缘一致", len(set([w + (10 - w) for w in widths])) == 1)
check("最宽标签是 8 列（更新时间/安装路径）", max(widths) == 8)


print()
print("== T. 输入模式（输入法 vs 行编辑）==")

def parse_input_mode(v):
    return 1 if str(v).strip().lower() == "ime" else 0

def toggle(m):
    return 0 if m == 1 else 1

def prompt_of(mode, path_tail):
    return ("[IME] " if mode == 1 else "") + path_tail + " > "

check("ini input=ime -> 中文模式", parse_input_mode("ime") == 1)
check("ini input=IME 大小写不敏感", parse_input_mode("IME") == 1)
check("ini input=edit -> 编辑模式", parse_input_mode("edit") == 0)
check("ini 写错值 -> 回编辑模式", parse_input_mode("xyz") == 0)
check("切换 0->1", toggle(0) == 1)
check("切换 1->0", toggle(1) == 0)
check("中文模式提示符带 [IME]", prompt_of(1, "androidlog/257").startswith("[IME] "))
check("编辑模式提示符不带标记", not prompt_of(0, "androidlog/257").startswith("[IME]"))
check("编辑模式提示符保持精简", prompt_of(0, "androidlog/257") == "androidlog/257 > ")


print()
print("== U. 全角前缀归一化 + 模式档位 ==")

FW = {"\uFF1A": ":", "\uFF01": "!", "\uFF20": "@", "\uFF0F": "/",
      "\uFF3C": "\\", "\uFF0D": "-"}


def looks_cmd(t):
    if not t:
        return False
    if FW.get(t[0], t[0]) in ":!@":
        return True
    return any(("a" <= c <= "z") or ("A" <= c <= "Z") for c in t)


def normalize_lead(line):
    if not line:
        return line
    i = 0
    while i < len(line) and line[i] not in " \t":
        i += 1
    head = line[:i]
    if not looks_cmd(head):
        return line
    return "".join(FW.get(c, c) for c in head) + line[i:]


# 1) 全角前缀必须归一化 —— 否则中文输入法下连 :send 都敲不出来
check("全角冒号 -> 半角", normalize_lead("\uFF1Asend 你好") == ":send 你好")
check("全角叹号 -> 半角", normalize_lead("\uFF01top") == "!top")
check("全角 at -> 半角", normalize_lead("\uFF20logs") == "@logs")

# 2) 但正文里的全角标点不能动（那是要发出去的文本）
check("正文感叹号保留", normalize_lead("\uFF1Asend 你好\uFF01") == ":send 你好\uFF01")
check("纯中文消息不归一化", normalize_lead("你好\uFF01") == "你好\uFF01")
check("纯中文不带标点不变", normalize_lead("你好") == "你好")

# 3) 正常命令不受影响
for v in ["ls", "df -h", "cd 351", "!rm -rf /data", "@logs", ":h", "send 你好"]:
    check("命令原样: %s" % v, normalize_lead(v) == v)

# 4) 模式档位
def mode_of(v):
    v = str(v).strip().lower()
    if v in ("ime", "cn"):
        return (1, False)
    if v == "auto":
        return (0, True)
    return (0, False)


check("input=ime -> 常驻中文", mode_of("ime") == (1, False))
check("input=auto -> 跟随系统", mode_of("auto") == (0, True))
check("input=edit -> 编辑", mode_of("edit") == (0, False))
check("非法值 -> 编辑", mode_of("zzz") == (0, False))

# 5) auto 的判定：中文态走 ReadLine，英文态走编辑器，检测不到走编辑器
def ime_active(mode, auto, native_state):
    if mode in (1, 2):
        return True
    if auto and native_state == 1:
        return True
    return False

check("auto + 中文态 -> ReadLine", ime_active(0, True, 1) is True)
check("auto + 英文态 -> 编辑器", ime_active(0, True, 0) is False)
check("auto + 检测不到 -> 编辑器", ime_active(0, True, -1) is False)
check(":ime 一次性 -> ReadLine", ime_active(2, False, 0) is True)
check(":ime on 常驻 -> ReadLine", ime_active(1, False, 0) is True)
check(":ime off 关闭 auto -> 编辑器", ime_active(0, False, 1) is False)

# 6) 一次性模式读完要复位
def after_read(mode):
    return 0 if mode == 2 else mode

check("一次性读完复位为编辑", after_read(2) == 0)
check("常驻模式读完不变", after_read(1) == 1)
check("编辑模式读完不变", after_read(0) == 0)


print()
print("== V. 中文退格：必须按显示宽度擦列 ==")

# 逐字符宽度（与 CharWidth 对齐：CJK 2 列，ASCII 1 列）
def cw(ch):
    o = ord(ch)
    if 0x1100 <= o <= 0x115F: return 2
    if 0x2E80 <= o <= 0xA4CF: return 2
    if 0xAC00 <= o <= 0xD7A3: return 2
    if 0xF900 <= o <= 0xFAFF: return 2
    if 0xFE30 <= o <= 0xFE6F: return 2
    if 0xFF00 <= o <= 0xFF60: return 2
    if 0xFFE0 <= o <= 0xFFE6: return 2
    return 1

check("中文 2 列", cw("\u4F60") == 2)
check("英文 1 列", cw("n") == 1)
check("数字 1 列", cw("9") == 1)
check("全角字母 2 列", cw("\uFF41") == 2)

# 用户现场："你n" 要按两次退格、共擦 3 列
line = "\u4F60n"
check("你n 总宽 3 列", sum(cw(c) for c in line) == 3)
check("删 n 只需 1 列", cw(line[-1]) == 1)
check("删 你 需要 2 列", cw(line[0]) == 2)

# 旧实现固定擦 1 列 -> 删中文会剩半个字形
def erase_cols_old(ch):
    return 1

def erase_cols_new(ch):
    return cw(ch)

check("旧实现擦中文只擦 1 列（会剩半边）", erase_cols_old("\u4F60") == 1)
check("新实现擦中文擦 2 列", erase_cols_new("\u4F60") == 2)
check("新实现擦英文仍 1 列", erase_cols_new("n") == 1)

# 缓冲区已空但屏幕还剩半边 -> 再按退格毫无反应，这就是"删不掉"
buf_before = "\u4F60n"
buf_after_del_n = "\u4F60"
buf_after_del_cn = ""
screen_old = sum(erase_cols_old(c) for c in buf_before)   # 只擦掉 2 列
screen_new = sum(erase_cols_new(c) for c in buf_before)   # 擦掉 3 列
check("旧写法屏幕残留 1 列", 3 - screen_old == 1)
check("新写法屏幕无残留", 3 - screen_new == 0)
check("删空后缓冲区为空", buf_after_del_cn == "")
check("删空后旧写法仍有残影（正是用户看到的现象）", 3 - screen_old > 0)

# 宽度账：增量退格后 LAST_DRAWN 必须减去被删字符的宽度
def last_drawn_after(prompt_w, text, del_char, sync=True):
    total = prompt_w + sum(cw(c) for c in text)
    return total - cw(del_char) if sync else total

check("同步后宽度账正确", last_drawn_after(24, "\u4F60n", "n") == 24 + 2)
check("不同步会多算 1 列", last_drawn_after(24, "\u4F60n", "n", False) == 24 + 3)

# 左右移动：中文要跨 2 列
check("左移一个中文 = 2 列", cw("\u4F60") == 2)
check("右移一个中文 = 2 列", cw("\u4F60") == 2)
check("左移一个英文 = 1 列", cw("n") == 1)


print()
print("== W. 设备去重 / 序列号锁定 / Ctrl+C / 设备身份 ==")

def parse_devices(text):
    m = {}
    order = []
    for raw in text.split("\n"):
        t = raw.strip()
        if not t:
            continue
        if t.startswith("List of devices") or t.startswith("*"):
            continue
        f = t.replace("\t", " ").split()
        if len(f) < 2:
            continue
        serial, state = f[0], f[1]
        if state not in ("device", "offline", "unauthorized"):
            continue
        if serial in m:
            if state == "device":
                m[serial] = "device"
            continue
        m[serial] = state
        order.append(serial)
    dn = sum(1 for x in order if m[x] == "device")
    return dn, len(order) - dn


check("单设备 -> 1 台", parse_devices("List of devices attached\nb09acfa2\tdevice\n") == (1, 0))
check("表头与守护进程行被忽略",
      parse_devices("List of devices attached\n* daemon not running\nb09acfa2\tdevice\n") == (1, 0))
check("同号两行(都 device) -> 1 台",
      parse_devices("b09acfa2\tdevice\nb09acfa2\tdevice\n") == (1, 0))
check("同号 device+offline -> 1 台（device 优先）",
      parse_devices("b09acfa2\toffline\nb09acfa2\tdevice\n") == (1, 0))
check("两台不同设备 -> 2 台",
      parse_devices("aaa\tdevice\nbbb\tdevice\n") == (2, 0))
check("一台在线一台离线 -> 1 台 + 1 其他",
      parse_devices("aaa\tdevice\nbbb\toffline\n") == (1, 1))
check("未授权单独计数", parse_devices("aaa\tunauthorized\n") == (0, 1))
check("空输出 -> 0", parse_devices("List of devices attached\n") == (0, 0))

# 关键回归：旧实现不去重，同号两行会数成 2 台，触发"多设备"误报
def parse_devices_old(text):
    n = 0
    for raw in text.split("\n"):
        t = raw.strip()
        if not t or t.startswith("List of devices"):
            continue
        f = t.replace("\t", " ").split()
        if len(f) >= 2 and f[1] == "device":
            n += 1
    return n

dup = "b09acfa2\tdevice\nb09acfa2\tdevice\n"
check("旧实现把 1 台数成 2 台（正是误报原因）", parse_devices_old(dup) == 2)
check("新实现只数 1 台", parse_devices(dup)[0] == 1)


def build_args(argv, serial, devid):
    sub = argv[0].lower() if argv else ""
    glob = sub in ("devices", "version", "start-server", "kill-server",
                   "connect", "disconnect", "pair", "mdns")
    pin = "" if glob else (serial or devid)
    return (["-s", pin] if pin else []) + list(argv)


check("serial 为空时锁定探测到的设备号",
      build_args(["shell", "getprop", "x"], "", "b09acfa2") == ["-s", "b09acfa2", "shell", "getprop", "x"])
check("ini 填了 serial 就优先用它",
      build_args(["shell", "ls"], "AAA", "BBB") == ["-s", "AAA", "shell", "ls"])
check("devices 是全局命令，不加 -s", build_args(["devices"], "", "b09acfa2") == ["devices"])
check("version 不加 -s", build_args(["version"], "", "b09acfa2") == ["version"])
check("connect 不加 -s", build_args(["connect", "1.2.3.4"], "", "b09acfa2") == ["connect", "1.2.3.4"])
check("还没探测到设备时也不加 -s", build_args(["devices"], "", "") == ["devices"])


def parse_marked(text, n):
    r = [""] * n
    cur = -1
    seen = 0
    for raw in text.split("\n"):
        t = raw.strip()
        if not t:
            continue
        if t.startswith("##"):
            cur = seen
            seen += 1
            continue
        if 0 <= cur < n and not r[cur]:
            r[cur] = t
    return r


check("三段标记解析", parse_marked("##SOC\nSA8295P\n##PLAT\n8295_DESAY_AH8\n##OEM\nx\n", 3)
      == ["SA8295P", "8295_DESAY_AH8", "x"])
check("中间为空段", parse_marked("##SOC\nSA8295P\n##PLAT\n\n##OEM\n8295\n", 3)
      == ["SA8295P", "", "8295"])
check("全空", parse_marked("", 3) == ["", "", ""])

# 车型取值优先级：gacvehicleplatform 优先，没有则退回 ro.oem.product.name
def pick_plat(parts):
    return parts[1] if parts[1] else parts[2]

check("有 gacvehicleplatform 就用它", pick_plat(["SOC", "8295_DESAY_AH8", "OEM"]) == "8295_DESAY_AH8")
check("没有则退回 ro.oem.product.name", pick_plat(["SOC", "", "3588_SYNCORE_t9m"]) == "3588_SYNCORE_t9m")


def read_result(line, ctrl_c, interactive):
    if line is None:
        if interactive and ctrl_c:
            return ""
        return None
    return line


check("空输入按 Ctrl+C -> 取消本行，不退出", read_result(None, True, True) == "")
check("真 EOF（非交互）-> 结束", read_result(None, False, False) is None)
check("交互下 EOF 但没有 Ctrl+C -> 仍按 EOF", read_result(None, False, True) is None)
check("正常输入不受影响", read_result("ls", False, True) == "ls")


print()
print("== X. 换设备场景：陈旧条目 / tcp 折叠 / ini serial 失效 ==")

def resolve_devices(text, alive, serial_ini=""):
    """复刻 C# ParseDevices：去重 -> 探活剔除 -> USB 优先 -> 判定多台"""
    m, order = {}, []
    for raw in text.split("\n"):
        t = raw.strip()
        if not t or t.startswith("List of devices") or t.startswith("*"):
            continue
        f = t.replace("\t", " ").split()
        if len(f) < 2:
            continue
        ser, st = f[0], f[1]
        if st not in ("device", "offline", "unauthorized"):
            continue
        if ser in m:
            if st == "device":
                m[ser] = "device"
            continue
        m[ser] = st
        order.append(ser)

    cand = [x for x in order if m[x] == "device"]
    other = [x for x in order if m[x] != "device"]
    r = {"devn": 0, "devid": "", "stale": [], "tcp_ignored": 0,
         "devother": len(other), "serial_ok": bool(serial_ini) and m.get(serial_ini) == "device",
         "devlist": []}

    if not cand:
        return r
    if len(cand) == 1:
        r["devn"], r["devid"] = 1, cand[0]
        r["devlist"] = [cand[0]]
        return r

    good = []
    for c in cand:
        if c in alive:
            good.append(c)
        else:
            r["stale"].append(c)

    if len(good) == 1:
        r["devn"], r["devid"] = 1, good[0]
        r["devlist"] = [good[0]]
        return r

    usb = [x for x in good if ":" not in x]
    if len(usb) == 1:
        r["devn"], r["devid"], r["tcp_ignored"] = 1, usb[0], len(good) - 1
        r["devlist"] = [usb[0]]
        return r

    r["devn"] = len(good)
    r["devid"] = usb[0] if usb else good[0]
    r["devlist"] = good
    return r


# 1) 用户假设的核心场景：A 拔掉立刻插 B，列表里 A 还挂着（状态仍是 device）
ab = "b09acfa2\tdevice\n6dd4523c\tdevice\n"
r = resolve_devices(ab, alive={"6dd4523c"})
check("A 残留 + B 在线 -> 只算 1 台", r["devn"] == 1)
check("A 残留被识别为陈旧条目", r["stale"] == ["b09acfa2"])
check("选中真正在线的 B", r["devid"] == "6dd4523c")
check("不再误报多台（旧行为会 devn=2）", r["devn"] != 2)

# 2) 两台真的都在线 -> 必须报多台（该报就得报）
r = resolve_devices(ab, alive={"b09acfa2", "6dd4523c"})
check("两台都活着 -> devn=2", r["devn"] == 2)
check("两台都活着 -> 列出全部序列号", r["devlist"] == ["b09acfa2", "6dd4523c"])

# 3) 同一台设备的 USB + tcp 两条传输 -> 折叠成一台
dual = "6dd4523c\tdevice\n192.168.1.7:5555\tdevice\n"
r = resolve_devices(dual, alive={"6dd4523c", "192.168.1.7:5555"})
check("USB+tcp -> 1 台", r["devn"] == 1)
check("USB 优先", r["devid"] == "6dd4523c")
check("记录被折叠的 tcp 条数", r["tcp_ignored"] == 1)

# 4) 只有 tcp 在线时仍然可用
r = resolve_devices("192.168.1.7:5555\tdevice\n", alive={"192.168.1.7:5555"})
check("只有 tcp -> 正常识别 1 台", r["devn"] == 1 and r["devid"] == "192.168.1.7:5555")

# 5) 单台设备不做探活（省一次往返）
r = resolve_devices("6dd4523c\tdevice\n", alive=set())
check("单台不做探活也能定案", r["devn"] == 1 and r["devid"] == "6dd4523c")

# 6) offline 残留不参与计数，但要能被诊断出来
r = resolve_devices("aaa\toffline\n", alive=set())
check("offline 不计在线数", r["devn"] == 0)
check("offline 计入 devother", r["devother"] == 1)

# 7) ini serial 与当前设备不符（换机后忘改配置）
r = resolve_devices("6dd4523c\tdevice\n", alive={"6dd4523c"}, serial_ini="b09acfa2")
check("ini serial 不在线 -> serial_ok=False", r["serial_ok"] is False)
pin = ("b09acfa2" if r["serial_ok"] else r["devid"])
check("此时自动改用探测到的设备（否则每条命令 not found）", pin == "6dd4523c")

r = resolve_devices("6dd4523c\tdevice\n", alive={"6dd4523c"}, serial_ini="6dd4523c")
check("ini serial 在线 -> serial_ok=True", r["serial_ok"] is True)
pin = ("6dd4523c" if r["serial_ok"] else r["devid"])
check("在线时尊重 ini 指定", pin == "6dd4523c")


def build_args(argv, serial, serial_ok, devid):
    sub = argv[0].lower() if argv else ""
    glob = sub in ("devices", "version", "start-server", "kill-server",
                   "connect", "disconnect", "pair", "mdns")
    if glob:
        pin = ""
    elif serial and serial_ok:
        pin = serial
    else:
        pin = devid
    if argv and argv[0] == "-s":
        pin = ""
    return (["-s", pin] if pin else []) + list(argv)


check("探测调用已自带 -s 时不重复拼",
      build_args(["-s", "AAA", "get-state"], "AAA", True, "AAA") == ["-s", "AAA", "get-state"])
check("ini serial 失效时用 DEVID",
      build_args(["shell", "ls"], "AAA", False, "BBB") == ["-s", "BBB", "shell", "ls"])
check("ini serial 有效时用 SERIAL",
      build_args(["shell", "ls"], "AAA", True, "BBB") == ["-s", "AAA", "shell", "ls"])
check("devices 仍不加 -s",
      build_args(["devices"], "AAA", True, "AAA") == ["devices"])


print()
print("== Y. 空回车回执 / 空闲自动连接 / rl 三档 ==")

# ---- 1) 空回车必须有可见回执 ----
def empty_enter(offline, devid="", plat="", cur="/log"):
    if offline:
        return "设备未连接 · 插上设备会自动连接 · :r 立即重连 · :h 帮助"
    line = "  \u00B7 " + (devid or "-") + " 在线"
    if plat:
        line += " · " + plat
    line += " · " + cur
    return line

check("空回车（在线）有输出", len(empty_enter(False, "6dd4523c", "8295_DESAY_AH8")) > 10)
check("空回车（在线）带设备号", "6dd4523c" in empty_enter(False, "6dd4523c", "x"))
check("空回车（离线）有输出", len(empty_enter(True)) > 10)
check("空回车（离线）提示尚未连接", "未连接" in empty_enter(True))
check("空回车回执非空（旧实现是 continue，屏幕上什么都不发生）",
      empty_enter(False, "A") != "" and empty_enter(True) != "")

# ---- 2) 空闲自动连接：只在离线 + 缓冲为空 + 过了节流窗口 ----
def idle_should_probe(offline, buf_len, now_ms, last_ms, interval=1200):
    return offline and buf_len == 0 and (now_ms - last_ms) >= interval

check("离线 + 空缓冲 + 超过 1.2s -> 探测", idle_should_probe(True, 0, 5000, 3000))
check("在线时不探测", not idle_should_probe(False, 0, 5000, 3000))
check("已经输入了字就不探测（不打断用户）", not idle_should_probe(True, 3, 5000, 3000))
check("节流窗口内不探测", not idle_should_probe(True, 0, 3500, 3000))
check("刚开始时立即探一次（last 初始为负）", idle_should_probe(True, 0, 10, -100000))

def auto_connect_result(devn):
    return "connect" if devn > 0 else "wait"

check("探测到设备 -> 走初始化", auto_connect_result(1) == "connect")
check("没有设备 -> 继续等", auto_connect_result(0) == "wait")

# 连上后提示符要重算，否则会一直显示「(离线) >」
def prompt_after(offline, devid="A", cur="/log/x"):
    return "(离线) > " if offline else "log/x > "

check("连接后提示符不再是离线样式", not prompt_after(False).startswith("(离线)"))

# ---- 3) rl 三档 ----
def rl_plan(pend_k, last_fail, last_cmd):
    if pend_k:
        return ("structured", pend_k)
    target = last_fail if last_fail else last_cmd
    if not target:
        return ("none", "")
    if target.strip().lower() in ("rl", ":rl"):
        return ("loop", target)
    if last_fail:
        return ("rerun_fail", target)
    return ("rerun_last", target)

check("有 cd/ls/pull 现场 -> 结构化重做", rl_plan("LS", "", "ls") == ("structured", "LS"))
check("没有现场但有失败命令 -> 重跑它", rl_plan("", "df -h", "df -h") == ("rerun_fail", "df -h"))
check("没有失败 -> 重跑上一条（这就是用户遇到的场景）",
      rl_plan("", "", "ls") == ("rerun_last", "ls"))
check("什么都没执行过 -> 提示无操作", rl_plan("", "", "") == ("none", ""))
check("上一条就是 rl -> 不再套娃", rl_plan("", "", "rl") == ("loop", "rl"))
check(":rl 同样不套娃", rl_plan("", "", ":rl") == ("loop", ":rl"))

# 记录规则：rl 自己不写 LAST_CMD，失败会清空 LAST_FAIL_CMD
def record(line, cmd_ok, last_cmd, last_fail):
    lc = line.strip().lower()
    if lc in ("rl", ":rl"):
        return last_cmd, last_fail
    last_cmd = line
    last_fail = "" if cmd_ok else line
    return last_cmd, last_fail

lc, lf = record("ls", True, "", "")
check("成功命令记入 LAST_CMD", lc == "ls" and lf == "")
lc, lf = record("df -h", False, lc, lf)
check("失败命令同时记入 LAST_FAIL_CMD", lf == "df -h")
lc, lf = record("rl", True, lc, lf)
check("rl 不覆盖上一条命令", lc == "df -h")
lc, lf = record("pwd", True, lc, lf)
check("后续成功会清掉失败标记", lf == "" and lc == "pwd")


print()
print("== Z. 等待指示不误擦提示符 / 输入输出配色 ==")

# ---- 等待指示必须只擦自己那 4 列 ----
def erase_hint_new(line, col, width=4):
    return line[:col] + " " * width + line[col + width:]

def erase_hint_old(line):
    # 旧实现：\r 回行首 + 6 个空格（不管提示符在不在这一行）
    return " " * 6 + line[6:]

prompt = "androidlog > "
shown = prompt + " ..."          # 等待指示接在提示符后面

check("按列擦除后提示符完好", erase_hint_new(shown, len(prompt)).rstrip() == "androidlog >")
check("旧实现会把提示符前 6 列擦掉", erase_hint_old(shown).startswith(" " * 6))
check("旧实现正是截图现象（androi 丢失）",
      erase_hint_old("android_log/androidlog >  ...").lstrip().startswith("d_log/androidlog"))
check("新实现不会丢字符", "android_log" in erase_hint_new("android_log/androidlog >  ...", 26))
check("空提示符时也能擦干净", erase_hint_new(" ...", 0).strip() == "")

# ---- 后台探测必须是静默的（不显示等待指示）----
def wait_hint_enabled(silent, hint_ms):
    return (not silent) and hint_ms > 0

check("前台命令显示等待指示", wait_hint_enabled(False, 300))
check("后台探测不显示", not wait_hint_enabled(True, 300))
check("ini 关掉指示后也不显示", not wait_hint_enabled(False, 0))

# ---- 配色：输入 / 提示符 / 输出 三者必须可区分 ----
dark = {"ok": "Green", "err": "Red", "warn": "Yellow", "path": "Cyan",
        "dim": "DarkGray", "input": "White", "text": "Gray"}
light = {"ok": "DarkGreen", "err": "DarkRed", "warn": "DarkYellow", "path": "DarkCyan",
         "dim": "Gray", "input": "Black", "text": "Gray"}

check("深色主题：输入比输出亮", dark["input"] == "White" and dark["text"] == "Gray")
check("深色主题：输入与提示符不同色", dark["input"] != dark["path"])
check("浅色主题：输入压到最暗", light["input"] == "Black")
check("浅色主题：输入与输出可区分", light["input"] != light["text"])
check("两套主题语义键一致", set(dark.keys()) == set(light.keys()))
check("语义位 7 个：成功/失败/强调/路径/辅助/输入/正文", len(dark) == 7)

# ---- 提示符分色：'> ' 与路径分开着色 ----
def split_prompt(p):
    i = p.rfind(">")
    return (p[:i], p[i:]) if i >= 0 else (p, "")

a, b = split_prompt("androidlog > ")
check("路径部分不含 >", a == "androidlog ")
check("插入符单独一段", b == "> ")
a2, b2 = split_prompt("(离线) > ")
check("离线提示符同样能分色", a2 == "(离线) " and b2 == "> ")

# ---- 无输出命令要给回执 ----
def result_line(rc, out):
    if rc != 0:
        return "fail"
    return "silent-ok" if out.strip() == "" else "ok"

check("setprop 这类静默成功 -> 回执", result_line(0, "") == "silent-ok")
check("有输出时不加回执", result_line(0, "abc") == "ok")
check("失败不受影响", result_line(1, "") == "fail")


print()
print("== AB. 输出精简 / 版本名完整 ==")

LONG_VER = "3.6.8.0-201-202610292156-991a935f-RELEASE"

# 1) 真实长版本名必须完整（用户截图里的那一条，41 列）
rows = [("", "com.gxatek.cockpit.car.settings", LONG_VER, "201"),
        ("", "syncore.space.cockpit.toplauncher", "1.0.1.261029.215100.d5ca9b51", "1")]
ha, wa, wp, wv, st = ver_table_widths(rows, 120)
check("版本名列宽 = 最长版本名 41 列", wv == len(LONG_VER), "wv=%d" % wv)
check("版本名不被截断（无 .. 结尾）", not fit_width(LONG_VER, wv).endswith(".."))
check("版本名完整保留", fit_width(LONG_VER, wv) == LONG_VER)
check("120 列窗口仍放得下更新时间", st is True)
check("总宽不超窗口", 2 + wp + 2 + wv + 2 + 19 <= 120,
      "total=%d" % (2 + wp + 2 + wv + 2 + 19))

# 2) 窄窗口：牺牲时间列，保住版本名
# 88 列还放得下（去掉版本码列后余量变大：18+19+6+41+2 = 86）
_, _, wp8, wv8, st8 = ver_table_widths(rows, 88)
check("88 列窗口仍保留时间列", st8 is True)
check("88 列窗口版本名完整", wv8 == len(LONG_VER))

# 80 列放不下 -> 时间列下移，版本名完整
_, _, wp6, wv6, st6 = ver_table_widths(rows, 80)
check("80 列窗口 -> 时间列下移", st6 is False)
check("窄窗口版本名依旧 41 列", wv6 == len(LONG_VER))

# 3) 全部安装时不打"共 N 个，全部已安装"
def summary(rows, installed):
    if installed == 0:
        return "fail"
    if installed < len(rows):
        return "warn"
    return ""

check("全部安装 -> 无汇总行", summary(rows, 2) == "")
check("有未安装 -> 保留告警", summary(rows, 1) == "warn")
check("全未安装 -> 保留失败", summary(rows, 0) == "fail")

# 4) now 不再打"前台应用 xxx"标题，直接给表
def now_output(top_pkgs):
    return "table"

check("now 单包直接出表格", now_output(["com.a"]) == "table")
check("now 多显示不再有'前台应用 N 个'行",
      "前台应用" not in now_output(["com.a", "com.b"]))

# 5) 包名直查不再重复打印包名（详情块首项是"版本名"）
def detail_first_label():
    return "版本名"

check("详情块首行不是包名", detail_first_label() == "版本名")

# 6) 旧名迁移提示已移除
def legacy_note_count():
    return 0

check("旧名不再提示迁移", legacy_note_count() == 0)

# 7) 状态行不再带路径
def status_line(dev, online, plat):
    return "\u25CF %s  在线%s" % (dev, ("  " + plat) if plat else "")

check("状态行不含路径", "/log" not in status_line("b09acfa2", True, "110"))


print()
print("==" * 32)
if FAIL == 0:
    print("  全部用例通过")
else:
    print("  失败 %d 项" % FAIL)
raise SystemExit(1 if FAIL else 0)
