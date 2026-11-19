# -*- coding: utf-8 -*-
"""新增两条网联服务指令：打开准上线 / 测试 星河座舱云。

做法与既有 wsconfig / wsalipayset 一致：
  cmds.ini 定义命令（车机侧 am start -a VIEW -d <url> 用默认浏览器打开）
  ui.html 的 quickGroups 里加卡片（引用 cmd id）
"""
import io

# ---------- 1) cmds.ini ----------
P = r"C:\Users\SunWwei\Desktop\Adb_Tool\cmds.ini"
s = io.open(P, encoding="utf-8").read()

anchor = '''[cmd.wsalipayup]'''
add = '''# 2026-11-19：星河座舱云运营平台（准上线 / 测试）。
# 车机上用默认浏览器打开；URL 带 # 与端口，必须整体加引号，否则 shell 会把 # 之后当注释。
[cmd.wsprecloud]
desc = 准上线星河座舱云：打开 web-pre 运营平台
group = 网联服务
usage = wsprecloud
run = shell "am start -a android.intent.action.VIEW -d 'https://web-pre.syncore.space:20443/operation-platform/index.html#/pandect'"

[cmd.wstestcloud]
desc = 测试星河座舱云：打开 web-test 运营平台
group = 网联服务
usage = wstestcloud
run = shell "am start -a android.intent.action.VIEW -d 'https://web-test.syncore.space:20443/operation-platform/index.html#/pandect'"

''' + anchor
assert s.count(anchor) == 1, "cmds.ini 锚点没匹配上"
s = s.replace(anchor, add, 1)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("cmds.ini：已加 wsprecloud / wstestcloud")

# ---------- 2) ui.html 卡片 ----------
Q = r"C:\Users\SunWwei\Desktop\Adb_Tool\adb_log_gui\webview2\ui.html"
u = io.open(Q, encoding="utf-8").read()

old_card = """    {name:'配置中心后台', desc:'space.syncore.cockpit 配置中心默认页', cmd:'wsconfig', cat:'后台入口'},"""
new_card = """    {name:'配置中心后台', desc:'space.syncore.cockpit 配置中心默认页', cmd:'wsconfig', cat:'后台入口'},
    {name:'准上线星河座舱云', desc:'web-pre 运营平台（车机浏览器打开）', cmd:'wsprecloud', cat:'后台入口'},
    {name:'测试星河座舱云', desc:'web-test 运营平台（车机浏览器打开）', cmd:'wstestcloud', cat:'后台入口'},"""
assert u.count(old_card) == 1, "ui.html 卡片锚点没匹配上"
u = u.replace(old_card, new_card)
io.open(Q, "w", encoding="utf-8", newline="\n").write(u)
print("ui.html：已加两张卡片")
