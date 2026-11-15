# -*- coding: utf-8 -*-
"""
【离线参考 · 不参与回归】
本文件把 C# 的核心纯逻辑（路径工具 / 分词 / 显示宽度 / 排版算法）用 Python
重写了一遍，只用于"当年没有 csc 可用"的环境下做题面验证。

注意：它是**镜像实现**，C# 改了它不会跟着变，跑通不代表 C# 正确。
现在的回归基线是：
    adb_log_export.exe -selftest     （真实 C# 代码，360+ 条断言）
    adb_Tool.exe --selfcheck         （界面自检）
    377/_test_*.py                   （ui.html 的真实 DOM 行为）
改 C# 逻辑时不要靠这个文件判断对错。
"""
import sys

# ============ 对应 Program.cs 的工具函数 ============
def last_seg(p):
    if not p:
        return "/"
    t = p.rstrip('/')
    if len(t) == 0:
        return "/"
    i = t.rfind('/')
    if i < 0:
        return t
    return t[i+1:]

def norm_path(p):
    if not p:
        return "/"
    parts = p.replace('\\', '/').split('/')
    st = []
    for seg in parts:
        if seg == '' or seg == '.':
            continue
        if seg == '..':
            if st:
                st.pop()
            continue
        st.append(seg)
    if not st:
        return "/"
    return '/' + '/'.join(st)

def dev_abs(p, cur):
    if not p:
        return cur
    if p == '~':
        return '/'
    if p[0] == '/':
        return norm_path(p)
    return norm_path(cur + '/' + p)

def is_winpath(p):
    if p is None:
        return False
    if len(p) >= 3:
        c0 = p[0]
        alpha = ('A' <= c0 <= 'Z') or ('a' <= c0 <= 'z')
        if alpha and p[1] == ':' and p[2] in ('\\', '/'):
            return True
    if len(p) >= 2 and p[0] == '\\' and p[1] == '\\':
        return True
    return False

def split_line(line):
    if line is None:
        return ('', '')
    i = 0
    while i < len(line) and line[i] in (' ', '\t'):
        i += 1
    s = i
    while i < len(line) and line[i] not in (' ', '\t'):
        i += 1
    cmd = line[s:i]
    while i < len(line) and line[i] in (' ', '\t'):
        i += 1
    arg = line[i:] if i < len(line) else ''
    return (cmd, arg)

def split_args(s):
    r = []
    if s is None:
        return r
    cur = []
    inq = False
    any_ = False
    for ch in s:
        if ch == '"':
            inq = not inq
            any_ = True
            continue
        if not inq and ch in (' ', '\t'):
            if any_:
                r.append(''.join(cur))
                cur = []
                any_ = False
            continue
        cur.append(ch)
        any_ = True
    if any_:
        r.append(''.join(cur))
    return r

def unquote(s):
    if s is None:
        return ''
    s = s.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1].strip()
    return s

def disp_width(s):
    if not s:
        return 0
    w = 0
    for c in s:
        o = ord(c)
        if 0x1100 <= o <= 0x115F or 0x2E80 <= o <= 0xA4CF or 0xAC00 <= o <= 0xD7A3 \
           or 0xF900 <= o <= 0xFAFF or 0xFE30 <= o <= 0xFE6F or 0xFF00 <= o <= 0xFF60 \
           or 0xFFE0 <= o <= 0xFFE6:
            w += 2
        else:
            w += 1
    return w

# ============ 对应 Adb.cs 的排版算法 ============
def ls_layout(items, lsw, ls_gap=3, ls_maxcol=10):
    maxl = 0
    for n in items:
        w = disp_width(n)
        if w > maxl:
            maxl = w
    cw = maxl + ls_gap
    if cw < 4:
        cw = 4
    avail = lsw - 2
    if avail < cw:
        avail = cw
    nc = avail // cw
    if nc < 1:
        nc = 1
    if ls_maxcol > 0 and nc > ls_maxcol:
        nc = ls_maxcol
    return (maxl, cw, nc)

# ============ 测试 ============
fails = 0
def check(name, cond):
    global fails
    if cond:
        print("  [OK] " + name)
    else:
        print("  [FAIL] " + name)
        fails += 1

print("== 路径工具 ==")
check("NormPath /a/b/../c => /a/c", norm_path("/a/b/../c") == "/a/c")
check("NormPath //a///b// => /a/b", norm_path("//a///b//") == "/a/b")
check("NormPath 多级 .. => /", norm_path("/a/b/../../") == "/")
check("LastSeg /a/b/ => b", last_seg("/a/b/") == "b")
check("LastSeg / => /", last_seg("/") == "/")
check("DevAbs 相对补全", dev_abs("351", "/log/android_log/androidlog") == "/log/android_log/androidlog/351")
check("DevAbs 绝对不变", dev_abs("/a/b", "/log") == "/a/b")
check("DevAbs ~ => /", dev_abs("~", "/log") == "/")
check("DevAbs 多级..", dev_abs("351/../370", "/log/android_log/androidlog") == "/log/android_log/androidlog/370")

print("== 分词 ==")
c, a = split_line("ls 351")
check("SplitLine ls 351", c == "ls" and a == "351")
c, a = split_line("cd   370")
check("SplitLine cd 多空格", c == "cd" and a == "370")
c, a = split_line('pull "C:\\my dir"')
check("SplitLine pull 保留引号", c == "pull" and a == '"C:\\my dir"')
sa = split_args('353 "D:\\my log"')
check("SplitArgs 引号感知 2 段", sa == ["353", "D:\\my log"])
sa = split_args('353 D:\\log')
check("SplitArgs 无引号 2 段", sa == ["353", "D:\\log"])
sa = split_args('"D:\\my log"')
check("SplitArgs 单参数带空格", sa == ["D:\\my log"])
check("IsWinPath C:\\", is_winpath("C:\\xx"))
check("IsWinPath C:/", is_winpath("C:/xx"))
check("IsWinPath UNC", is_winpath("\\\\nas\\share"))
check("IsWinPath 非路径 351", not is_winpath("351"))
check("IsWinPath 非路径 /log", not is_winpath("/log"))

print("== 显示宽度 ==")
check("DispWidth 中文=4", disp_width("中文") == 4)
check("DispWidth 英文=3", disp_width("abc") == 3)
check("DispWidth 混合 a中b=4", disp_width("a中b") == 4)
check("DispWidth 空=0", disp_width("") == 0)

print("== 排版算法（对齐 bat 版验收）==")
# 23 项，120 列窗口 => 预期 9/9/5 三行
items23 = [str(i) for i in range(1, 24)]
maxl, cw, nc = ls_layout(items23, 120)
# 名字最宽 2 字符（"10"~"23"），cw=5，avail=118，nc=min(23, 10)=10
print("  23项/120列: maxl=%d cw=%d nc=%d" % (maxl, cw, nc))
check("23项/120列 每行列数", nc == 10)

# 长文件名（70字符）=> 降为 1 列
longname = ["x" * 70]
maxl, cw, nc = ls_layout(longname, 120)
print("  长名/120列: maxl=%d cw=%d nc=%d" % (maxl, cw, nc))
check("长名 降为 1 列", nc == 1)

# 50 列窗口
maxl, cw, nc = ls_layout(items23, 50)
print("  23项/50列: nc=%d" % nc)
check("23项/50列 列数合理", nc >= 1 and nc <= 10)

print("== Unquote ==")
check("Unquote 去引号", unquote('"C:\\my dir"') == "C:\\my dir")
check("Unquote 无引号", unquote("C:\\log") == "C:\\log")

print()
if fails == 0:
    print("  全部通过")
else:
    print("  失败 %d 项" % fails)
sys.exit(0 if fails == 0 else 1)
