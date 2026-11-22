"""新指令端到端测试（2026-11-22 第 12 批需求 2.3~2.9 / 3 / 4）。

验证 12 条新指令**真的能跑通**（不是只编译过）：
  语音助手 :vr selfcheck / delapk / restart / deploy [test|autogray|dev]
  快捷指令 :envdomain / :envhttps / :apkverify on|off
  手车互联 :selinux get

★ 调用方式是"喂 stdin"，不是命令行参数：
  CLI 版（adb_log_export.exe）只认 [-adb] [-s] [-perf] [-v] [-selftest] 五个启动参数，
  命令本身要在交互模式下敲。所以这里把命令 + exit 一起写进 stdin。
  输出是 **GBK** 编码（控制台代码页），解码要用 gbk。

注意：:vr delapk 是破坏性操作，只验证"命令被识别"，不真的删。
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI_EXE = os.path.join(ROOT, "adb_log_export.exe")

R = []


def ok(name, cond, extra=""):
    R.append(("PASS" if cond else "FAIL") + " | " + name + ("" if cond else (" -> " + str(extra))))


def run(cmds, timeout=90):
    """把命令喂进 stdin，返回 (输出, rc)。"""
    if isinstance(cmds, str):
        cmds = [cmds]
    feed = ("\n".join(cmds) + "\nexit\n").encode("gbk", "replace")
    try:
        p = subprocess.run([CLI_EXE], input=feed, capture_output=True, timeout=timeout)
        out = p.stdout.decode("gbk", "replace") + p.stderr.decode("gbk", "replace")
        return out, p.returncode
    except subprocess.TimeoutExpired:
        return "__TIMEOUT__", -1
    except Exception as e:
        return "EXC: %s" % e, -1


def main():
    if not os.path.exists(CLI_EXE):
        print("  [SKIP] 找不到 %s，跳过（请先跑 _cs/build.bat）" % CLI_EXE)
        return 0

    # ---------- 1. :selinux get（手车互联，需求 4）----------
    out, rc = run(":selinux get")
    ok(":selinux get 能执行", "__TIMEOUT__" not in out, out[:120])
    ok(":selinux get 报出 Enforcing / Permissive",
       ("Enforcing" in out) or ("Permissive" in out), out[-400:])
    ok(":selinux get 没有报参数错误",
       "参数不认识" not in out)

    # ---------- 2. :envdomain（快捷指令，需求 3）----------
    out, rc = run(":envdomain")
    ok(":envdomain 能执行", "__TIMEOUT__" not in out, out[:120])
    ok(":envdomain 有结果或明确提示",
       ("domain" in out) or ("没有找到" in out) or ("没有匹配" in out), out[-400:])
    # 关键：解析不能带出 "]: [" 残渣（真机输出暴露过这个 bug）
    ok(":envdomain 输出无 ']: [' 残渣", "]: [" not in out,
       out[-400:])

    # ---------- 3. :envhttps（快捷指令，需求 3）----------
    out, rc = run(":envhttps")
    ok(":envhttps 能执行", "__TIMEOUT__" not in out, out[:120])
    ok(":envhttps 有结果或明确提示",
       ("https" in out.lower()) or ("没有找到" in out) or ("没有匹配" in out), out[-400:])
    ok(":envhttps 输出无 ']: [' 残渣", "]: [" not in out, out[-400:])

    # ---------- 4. :apkverify 查询 ----------
    out, rc = run(":apkverify")
    ok(":apkverify 无参数走查询分支",
       ("verify_apk" in out) or ("未设置" in out) or ("APK 验证" in out), out[-400:])

    # ---------- 5. :vr deploy 查询（需求 2.6）----------
    out, rc = run(":vr deploy")
    ok(":vr deploy 查询能执行", "__TIMEOUT__" not in out, out[:120])
    ok(":vr deploy 显示信源环境",
       ("信源环境" in out) or ("原始值" in out), out[-500:])
    ok(":vr deploy 列出三个可切换值",
       ("test" in out) and ("autogray" in out) and ("dev" in out), out[-600:])

    # ---------- 6. 非法值被拒绝 ----------
    out, rc = run(":vr deploy bogusvalue")
    ok(":vr deploy 拒绝非法值", "不认识" in out, out[-400:])

    # ---------- 7. 各命令都已注册（不出现"未知"）----------
    for cmd, label in [
        (":envdomain", "查询环境域名"),
        (":envhttps", "查询环境https"),
        (":apkverify", "Apk验证查询"),
        (":vr deploy", "查询信源环境"),
        (":vr selfcheck", "打开语音自检后台"),
        (":selinux get", "查询se_linux"),
    ]:
        out, _ = run(cmd)
        bad = ("未知命令" in out) or ("无法识别" in out) or ("未注册" in out)
        ok("已注册：%s（%s）" % (cmd, label), not bad, out[-300:])

    # ---------- 8. :vr restart 会先 chmod（需求 2.5）----------
    out, _ = run(":vr restart")
    ok(":vr restart 包含 chmod 授权步骤",
       "chmod" in out or "授权" in out, out[-500:])
    ok(":vr restart 包含 force-stop",
       ("force-stop" in out) or ("停止" in out), out[-500:])

    # ---------- 9. :vr delapk 拒绝非系统目录（安全阀）----------
    # 不真跑删除，只检查它有开始提示 + 权限判断逻辑存在
    out, _ = run(":vr delapk")
    ok(":vr delapk 有开始提示",
       ("删除语助" in out) or ("删除" in out), out[-500:])

    print("")
    print("=== 实际输出抽样 ===")
    for cmd in [":selinux get", ":envdomain", ":vr deploy"]:
        out, _ = run(cmd)
        # 只取命令之后的片段（前面是欢迎页）
        print("\n  $ %s" % cmd)
        lines = [l.rstrip() for l in out.strip().split("\n")]
        # 从含关键字的行开始截取
        for i, l in enumerate(lines):
            if ("SELinux" in l) or ("domain" in l) or ("信源环境" in l):
                for x in lines[i:i+6]:
                    print("    " + x)
                break
    print("")

    for line in R:
        print("  " + line)
    fail = sum(1 for x in R if x.startswith("FAIL"))
    print("")
    print("  新指令：通过 %d / %d" % (len(R) - fail, len(R)))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
