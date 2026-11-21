"""配置文件导出 / 导入（Profile.cs）回归测试。

背景（2026-11-21）：靠手工造数据实测，发现两个真实缺陷，都已修复，
本脚本把它们钉住，防止回归：

  缺陷 1：ini 路径没跟随「exe + internal\\」新布局
    Profile.IniPath 只拼 BaseDirectory，发布包里 ini 在 internal 下，
    于是 WriteIniKey 找不到文件、静默返回 false。
    表现：导入提示"已导入 3 项"，实际 prefs 没写进 ini —— 界面偏好导入无效且不报错。

  缺陷 2：prefs 导入不做合法性校验
    损坏/伪造的 .adtprofile 带垃圾 prefs（如 {"test":"true"}）会直接覆盖
    用户真实偏好。前端 parsePrefs 的 try/catch 只保证不崩，保证不了偏好不丢。

本测试的做法：
  1) 备份当前数据（apk_apps.txt / custom_cmds.b64 / ini）
  2) 造测试数据（3 条自定义指令 + 5 条 APK + prefs）
  3) 导出 → 检查 zip 结构、manifest、白名单（无绝对路径/密钥）
  4) 篡改数据 → 导入 → 验证恢复
  5) 测异常文件（schema 过高 / 非 zip / 空内容 / 垃圾 prefs）
  6) 恢复现场

运行：python 377/_test_profile.py
"""
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXE = os.path.join(ROOT, "adb_log_gui", "dist", "adb_Tool.exe")
if not os.path.exists(EXE):
    EXE = os.path.join(ROOT, "adb_log_gui", "adb_Tool.exe")

LOCALAPPDATA = os.environ.get("LOCALAPPDATA") or os.path.expandvars(r"%LOCALAPPDATA%")
DATA = os.path.join(LOCALAPPDATA, "adb_Tool")
APK = os.path.join(DATA, "apk_apps.txt")
CMDS = os.path.join(DATA, "custom_cmds.b64")
# ini 两套布局：发布包在 internal 下，源码在 exe 同级
INI_CANDS = [
    os.path.join(os.path.dirname(EXE), "internal", "adb_log_export.ini"),
    os.path.join(os.path.dirname(EXE), "adb_log_export.ini"),
]

R = []          # 断言结果
TMP = tempfile.mkdtemp(prefix="adtprofile_")


def ok(name, cond, extra=""):
    R.append((bool(cond), name, extra))
    print(("  PASS | " if cond else "  FAIL | ") + name
          + ("" if cond else "  -> " + str(extra)))


def run_exec(cmd, timeout=90):
    """走 GUI 真实管道的无头执行（GuiHeadless --exec）。

    注意编码：GuiHeadless 的输出是 **UTF-8**（不是控制台的 GBK）。
    早先按 gbk 解会抛 UnicodeDecodeError / 变成乱码，导致所有中文断言假红。
    """
    p = subprocess.run([EXE, "--exec", cmd], capture_output=True,
                       timeout=timeout)
    raw = p.stdout + p.stderr
    try:
        out = raw.decode("utf-8")
    except UnicodeDecodeError:
        out = raw.decode("utf-8", "replace")
    return p.returncode, out


def ini_path():
    for c in INI_CANDS:
        if os.path.exists(c):
            return c
    return INI_CANDS[0]


def read_prefs_line():
    p = ini_path()
    if not os.path.exists(p):
        return ""
    for ln in open(p, encoding="utf-8", errors="replace"):
        t = ln.strip()
        if t.lower().startswith("prefs="):
            return t[6:]
    return ""


def set_prefs_line(val):
    p = ini_path()
    lines = open(p, encoding="utf-8", errors="replace").read().split("\n")
    hit = False
    for i, ln in enumerate(lines):
        if ln.strip().lower().startswith("prefs="):
            lines[i] = "prefs=" + val
            hit = True
    if not hit:
        lines.append("prefs=" + val)
    open(p, "w", encoding="utf-8", newline="").write("\n".join(lines))


def b64_prefs(obj):
    return base64.b64encode(
        json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")


# ---------------- 造测试数据 ----------------
DEFS = [
    {"id": "ctest001", "name": "测试-查版本号", "desc": "造数据用",
     "steps": [{"t": "cmd", "v": "getprop ro.build.version.release"},
               {"t": "delay", "ms": 500},
               {"t": "cmd", "v": "getprop ro.product.model"}]},
    {"id": "ctest002", "name": "测试-循环压测", "desc": "循环 3 次",
     "steps": [{"t": "cmd", "v": "dumpsys meminfo | head -5"},
               {"t": "loop", "n": 3}]},
    {"id": "ctest003", "name": "测试-多行命令", "desc": "含换行",
     "steps": [{"t": "cmd", "v": "echo line1\necho line2\necho line3"}]},
]
APK_LINES = [
    "# adb_Tool 应用列表（一行一条：名称<TAB>包名，可直接编辑）",
    "测试语音助手\tcom.test.voiceassistant",
    "测试导航\tcom.test.navigation",
    "测试媒体\tcom.test.mediaplayer",
    "测试蓝牙\tcom.test.bluetooth",
    "测试设置\tcom.test.settings",
]
PREFS_ORIG = {"font": "system", "custom": "", "size": "s"}
PREFS_OTHER = {"font": "system", "size": "l"}      # 用来制造差异


def main():
    print("=" * 70)
    print("配置文件导出 / 导入 回归测试")
    print("exe :", EXE)
    print("data:", DATA)
    print("ini :", ini_path())
    print("=" * 70)

    if not os.path.exists(EXE):
        print("!! 找不到 adb_Tool.exe，先编译")
        return 2

    # ---------- 0. 备份现场 ----------
    bak = os.path.join(TMP, "bak")
    os.makedirs(bak, exist_ok=True)
    for src, name in ((APK, "apk_apps.txt"), (CMDS, "custom_cmds.b64"),
                      (ini_path(), "ini")):
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(bak, name))
    prefs_backup = read_prefs_line()

    try:
        # ---------- 1. 造数据 ----------
        print("\n[1] 造测试数据")
        os.makedirs(DATA, exist_ok=True)
        open(APK, "w", encoding="utf-8", newline="").write("\n".join(APK_LINES) + "\n")
        b64 = base64.b64encode(
            json.dumps(DEFS, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).decode("ascii")
        open(CMDS, "w", encoding="utf-8", newline="").write(b64)
        set_prefs_line(b64_prefs(PREFS_ORIG))
        ok("已写入 3 条自定义指令", os.path.getsize(CMDS) > 100,
           os.path.getsize(CMDS))
        ok("已写入 5 条 APK", len(open(APK, encoding="utf-8").read().splitlines()) == 6)

        # :cfg info 应能识别
        rc, out = run_exec(":cfg info")
        ok(":cfg info 识别到自定义指令", "自定义指令" in out and "（无）" not in
           [l for l in out.splitlines() if "自定义指令" in l][0], out[-300:])

        # ---------- 2. 导出 ----------
        print("\n[2] 导出")
        prof = os.path.join(TMP, "test.adtprofile")
        # 注意：--exec 的路径分隔用 \\\\ 会显示成一串斜杠，用正斜杠最稳
        rc, out = run_exec(":cfg export " + prof.replace("\\", "/"))
        ok("导出返回成功", rc == 0 and "已导出" in out, out[-300:])
        ok("导出文件存在且非空", os.path.exists(prof) and os.path.getsize(prof) > 200,
           os.path.getsize(prof) if os.path.exists(prof) else "缺失")

        if os.path.exists(prof):
            z = zipfile.ZipFile(prof)
            names = set(z.namelist())
            ok("zip 含 manifest.json", "manifest.json" in names, names)
            ok("zip 含 prefs.txt", "prefs.txt" in names, names)
            ok("zip 含 custom_cmds.b64", "custom_cmds.b64" in names, names)
            ok("zip 含 apk_apps.txt", "apk_apps.txt" in names, names)
            ok("zip 含 README.txt", "README.txt" in names, names)

            man = z.read("manifest.json").decode("utf-8")
            ok("manifest 含 schema", '"schema"' in man, man)
            ok("manifest 含 exported 时间", '"exported"' in man, man)
            ok("manifest schema == 1", '"schema":1' in man.replace(" ", ""), man)

            # 白名单安全：不得含绝对路径 / 密钥
            danger = []
            for n in z.namelist():
                t = z.read(n).decode("utf-8", "replace")
                for kw in ("adb_path", "scrcpy_path", "password", "secret", "token"):
                    if kw in t.lower():
                        danger.append((n, kw))
            ok("导出内容不含敏感字段", not danger, danger)

            # 数据完整性：zip 里的 cmd 与造的一致
            zb = z.read("custom_cmds.b64").decode("utf-8").strip()
            ok("zip 内 custom_cmds 与源一致", zb == b64.strip())
            ok("zip 内 apk 条数正确",
               len(z.read("apk_apps.txt").decode("utf-8").splitlines()) == 6)

        # ---------- 3. 篡改 → 导入恢复 ----------
        print("\n[3] 篡改数据后导入，验证恢复")
        open(CMDS, "w", encoding="utf-8").write("W10=")          # 空数组
        open(APK, "w", encoding="utf-8", newline="").write(
            APK_LINES[0] + "\n被篡改\tcom.tampered.x\n")
        set_prefs_line(b64_prefs(PREFS_OTHER))                   # size: l
        ok("已篡改（cmds 变短）", os.path.getsize(CMDS) < 20)
        ok("已篡改（prefs=size:l）", read_prefs_line() == b64_prefs(PREFS_OTHER))

        rc, out = run_exec(":cfg import " + prof.replace("\\", "/"))
        ok("导入返回成功", rc == 0 and "已导入" in out, out[-400:])
        # 缺陷 1 的回归断言：必须真的导入 3 项（含 prefs）
        ok("导入 3 项（含 prefs）—— 缺陷1回归",
           "已导入 3 项" in out, [l for l in out.splitlines() if "已导入" in l])

        ok("custom_cmds 已恢复", os.path.getsize(CMDS) > 100,
           os.path.getsize(CMDS))
        bk = base64.b64decode(open(CMDS, encoding="utf-8").read().strip()).decode("utf-8")
        ok("恢复后指令条数为 3", len(json.loads(bk)) == 3, bk[:80])

        apk_now = open(APK, encoding="utf-8").read()
        ok("apk 已恢复 5 条", apk_now.count("com.test.") == 5, apk_now)
        ok("apk 不再含篡改项", "com.tampered.x" not in apk_now)

        # 缺陷 1 的核心：prefs 必须真的写回 ini
        ok("prefs 已写回 ini —— 缺陷1核心",
           read_prefs_line() == b64_prefs(PREFS_ORIG),
           "实际=" + read_prefs_line() + " 期望=" + b64_prefs(PREFS_ORIG))

        # 备份文件应生成
        baks = [f for f in os.listdir(DATA) if ".bak." in f]
        ok("导入前生成了备份文件", len(baks) > 0, baks)

        # ---------- 4. 异常文件 ----------
        print("\n[4] 异常文件")

        # 4.1 schema 过高
        p1 = os.path.join(TMP, "bad_schema.adtprofile")
        with zipfile.ZipFile(p1, "w") as z:
            z.writestr("manifest.json",
                       '{"schema":99,"appVersion":"9.9.9.9","exported":"2030-01-01T00:00:00"}')
            z.writestr("prefs.txt", b64_prefs(PREFS_ORIG))
        rc, out = run_exec(":cfg import " + p1.replace("\\", "/"))
        ok("schema 过高被拒", rc != 0 and "更新版本" in out, out[-200:])

        # 4.2 非 zip
        p2 = os.path.join(TMP, "not_zip.adtprofile")
        open(p2, "w", encoding="utf-8").write("not a zip")
        rc, out = run_exec(":cfg import " + p2.replace("\\", "/"))
        ok("非 zip 被拒", rc != 0 and ("失败" in out or "格式" in out), out[-200:])

        # 4.3 空内容
        p3 = os.path.join(TMP, "empty.adtprofile")
        with zipfile.ZipFile(p3, "w") as z:
            z.writestr("README.txt", "nothing")
        rc, out = run_exec(":cfg import " + p3.replace("\\", "/"))
        ok("无可用内容被拒", rc != 0 and "没有可导入" in out, out[-200:])

        # 4.4 垃圾 prefs（缺陷 2 回归）—— 结构合法但字段全不认识
        p4 = os.path.join(TMP, "garbage_prefs.adtprofile")
        with zipfile.ZipFile(p4, "w") as z:
            z.writestr("prefs.txt", b64_prefs({"test": "true"}))
        before = read_prefs_line()
        rc, out = run_exec(":cfg import " + p4.replace("\\", "/"))
        ok("垃圾 prefs 被拒 —— 缺陷2回归", rc != 0, out[-250:])
        ok("垃圾 prefs 未污染 ini —— 缺陷2回归",
           read_prefs_line() == before,
           "前=" + before + " 后=" + read_prefs_line())

        # 4.5 非法 base64
        p5 = os.path.join(TMP, "bad_b64.adtprofile")
        with zipfile.ZipFile(p5, "w") as z:
            z.writestr("prefs.txt", "!!!not-base64!!!")
        rc, out = run_exec(":cfg import " + p5.replace("\\", "/"))
        ok("非法 base64 prefs 被拒", rc != 0, out[-200:])

        # 4.6 文件不存在
        rc, out = run_exec(":cfg import " + os.path.join(TMP, "nope.adtprofile").replace("\\", "/"))
        ok("文件不存在提示正确", rc != 0 and "不存在" in out, out[-200:])

        # 4.7 缺参数 / 未知子命令
        rc, out = run_exec(":cfg import")
        ok("缺参数有用法提示", rc != 0 and "路径" in out, out[-200:])
        rc, out = run_exec(":cfg badcmd")
        ok("未知子命令有用法提示", rc != 0 and "用法" in out, out[-200:])

    finally:
        # ---------- 5. 恢复现场 ----------
        print("\n[5] 恢复现场")
        try:
            for src, name in ((APK, "apk_apps.txt"), (CMDS, "custom_cmds.b64")):
                b = os.path.join(bak, name)
                if os.path.exists(b):
                    shutil.copy2(b, src)
                elif os.path.exists(src):
                    os.remove(src)
            # 清理本次测试产生的备份文件
            for f in os.listdir(DATA):
                if ".bak." in f:
                    try:
                        os.remove(os.path.join(DATA, f))
                    except Exception:
                        pass
            if prefs_backup:
                set_prefs_line(prefs_backup)
            shutil.rmtree(TMP, ignore_errors=True)
            print("  已恢复")
        except Exception as e:
            print("  恢复失败：", e)

    # ---------- 汇总 ----------
    npass = sum(1 for r in R if r[0])
    nfail = len(R) - npass
    print("\n" + "=" * 70)
    print("  配置文件导入导出：通过 %d / %d" % (npass, len(R)))
    if nfail:
        print("  有 %d 项失败：" % nfail)
        for good, name, extra in R:
            if not good:
                print("    -", name, "->", extra)
    print("=" * 70)
    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
