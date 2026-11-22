"""诊断页 —— 真实 C# 采集链路验证（2026-11-22）。

为什么需要这个测试：
  377/_test_diag.py 用 headless Edge 跑，只能验证**渲染层**（喂造数据）。
  它验证不了最关键的一环：C# 的 Diag.CollectLocal() 到底能不能拿到真数据、
  JSON 拼得对不对、消息能不能送到页面。

  这个脚本走 --uitest：在**真实 WebView2** 里加载 ui.html，
  真的触发 diagRefresh()，等 C# 把 WMI 采集结果推回来，再断言字段。

  注意：需要先编译（build_gui.bat 产出 adb_Tool.exe）。
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "adb_log_gui", "webview2", "ui.html")
EXE = os.path.join(ROOT, "adb_log_gui", "dist", "adb_Tool.exe")

PROBE = r"""
<script>
/* 端到端探针：切到诊断页 -> 真触发 C# 采集 -> 轮询等回包 -> 写 #RESULT */
(function(){
  var out = { ok:false, stage:'init', rows:[], adb:'', adbsrc:'', err:null };
  function done(){
    var pre = document.createElement('pre');
    pre.id = 'RESULT';
    pre.textContent = JSON.stringify(out);
    document.body.appendChild(pre);
  }
  setTimeout(function(){
    try {
      switchTab('diag');
      out.stage = 'switched';
      diagRefresh();
      out.stage = 'requested';
    } catch(e){ out.err = String(e); done(); return; }

    var waited = 0;
    var iv = setInterval(function(){
      waited += 300;
      // C# 的 diaglocal 回包会填 _diag.local
      if (_diag.local && _diag.local.length){
        clearInterval(iv);
        out.ok = true;
        out.stage = 'got-local';
        out.rows = _diag.local;
        out.adb = _diag.adb;
        out.adbsrc = _diag.adbsrc;
        // 再等车机（可能慢/可能没设备），但不阻塞主结论
        setTimeout(function(){
          out.carOnline = _diag.car ? !!_diag.car.online : null;
          out.carRows = (_diag.car && _diag.car.rows) ? _diag.car.rows.length : 0;
          out.carRoot = _diag.car ? _diag.car.root : null;
          done();
        }, 2500);
        return;
      }
      if (waited >= 12000){
        clearInterval(iv);
        out.stage = 'timeout';
        out.err = 'C# 12 秒内没有回 diaglocal';
        done();
      }
    }, 300);
  }, 2500);
})();
</script>
"""


def main():
    if not os.path.exists(EXE):
        # 没编译过就跳过，不要报失败 —— 门禁的 --fast 档本来就不编译，
        # 这个用例只在 normal/full 档有意义。
        print("  [SKIP] 找不到 %s，跳过端到端（请先跑 build_gui.bat）" % EXE)
        print("  跳过 1 项")
        return 0

    src = open(UI, encoding="utf-8").read()
    tmp = os.path.join(tempfile.gettempdir(), "_diag_uitest.html")
    open(tmp, "w", encoding="utf-8", newline="").write(src.replace("</body>", PROBE + "</body>"))

    try:
        p = subprocess.run([EXE, "--uitest", tmp, "18000"],
                           capture_output=True, timeout=120)
        out = p.stdout.decode("utf-8", "replace")
        err = p.stderr.decode("utf-8", "replace")
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass

    m = re.search(r'<pre id="RESULT">(.*?)</pre>', out, re.S)
    if m:
        raw = m.group(1)
    else:
        # --uitest 会把 RESULT 文本原样打到 stdout。
        # 用 raw_decode 从第一个 '{' 开始解析，它会告诉我们 JSON 在哪结束 ——
        # 比贪婪正则可靠（后面可能还跟着 SDK / 程序自己的输出）。
        i = out.find('{"ok"')
        if i < 0:
            print("!! 没拿到结果")
            print("   stdout 前 800 字：")
            print(out[:800])
            if err.strip():
                print("   stderr 前 400 字：")
                print(err[:400])
            return 2
        raw = out[i:]

    raw = raw.replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    try:
        dec = json.JSONDecoder()
        data, _end = dec.raw_decode(raw.strip())
    except Exception as e:
        print("!! JSON 解析失败：%s" % e)
        print(raw[:600])
        return 2

    R = []

    def ok(name, cond, extra=""):
        R.append(("PASS" if cond else "FAIL") + " | " + name + ("" if cond else (" -> " + str(extra))))

    ok("C# 采集成功回包", data.get("ok") is True, data.get("stage") or data.get("err"))
    rows = data.get("rows") or []
    ok("拿到本机信息行", len(rows) > 0, len(rows))

    keys = [r.get("k", "") for r in rows]
    vals = {r.get("k", ""): r.get("v", "") for r in rows}
    ok("含 CPU 项", "CPU" in keys, keys)
    ok("含内存项", "内存" in keys, keys)
    ok("含 Windows 项", "Windows" in keys, keys)
    ok("含系统类型", "系统类型" in keys, keys)
    ok("含设备名称", "设备名称" in keys, keys)
    ok("含屏幕分辨率", "屏幕分辨率" in keys, keys)
    ok("含存储项", any(k.startswith("存储") for k in keys), keys)

    # 值非空且不是"读取失败"
    bad = [k for k, v in vals.items() if (not v) or ("读取失败" in v)]
    ok("所有项都有有效值", len(bad) == 0, bad)

    # CPU 应该是真实型号名，不是空
    cpu = vals.get("CPU", "")
    ok("CPU 是真实型号", len(cpu) > 5 and ("读取失败" not in cpu), cpu)

    # 分辨率应形如 1920 × 1080
    res = vals.get("屏幕分辨率", "")
    ok("分辨率格式正确", bool(re.search(r"\d+\s*×\s*\d+", res)), res)

    # adb 来源应该被识别出来
    ok("adb 来源已识别", bool(data.get("adbsrc")), data.get("adbsrc"))
    ok("adb 路径非空", bool(data.get("adb")), data.get("adb"))

    print("")
    print("=== C# 实采数据（真实 WMI）===")
    for r in rows:
        print("  %-14s %s" % (r.get("k", ""), r.get("v", "")))
    print("")
    print("  adb = %s" % data.get("adb", ""))
    print("  adb 来源 = %s" % data.get("adbsrc", ""))
    if data.get("carOnline") is not None:
        print("  车机在线 = %s，车机行数 = %s，root = %s"
              % (data.get("carOnline"), data.get("carRows"), data.get("carRoot")))
    print("")

    for line in R:
        print("  " + line)
    fail = sum(1 for x in R if x.startswith("FAIL"))
    print("")
    print("  诊断页端到端：通过 %d / %d" % (len(R) - fail, len(R)))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
