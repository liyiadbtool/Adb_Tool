// ============================================================================
//  _check_build_list.js — 编译列表完整性
//
//  真实事故：新增 _cs/Cast.cs 时只加进了 build_gui.bat，没加进 build.bat，
//  结果 CLI 编译照样打印 "Compile success"（那个文件根本没参与编译），
//  直到 GUI 侧报错才发现。
//
//  规则：_cs 下每个 .cs 都必须出现在两个 bat 的显式列表里
//        （GUI 独有的 6 个文件可以不被 CLI 编，但必须在白名单里显式声明）。
//
//  运行：node _check_build_list.js
// ============================================================================
const fs = require("fs");
const path = require("path");

const ROOT = __dirname;
const SRC = path.join(ROOT, "_cs");
const CLI_BAT = path.join(SRC, "build.bat");
const GUI_BAT = path.join(ROOT, "adb_log_gui", "build_gui.bat");

// GUI 专用文件：只在 GUI 版编译，CLI 不需要（必须显式列在这里，防止"漏了"被当成正常）
//
// Diag.cs（2026-11-22）：诊断页的本机信息采集。
//   为什么 GUI-only：它用了 System.Windows.Forms（Screen / Application）读
//   屏幕分辨率和缩放，还调了 GuiEntry.LogDir() 算日志目录体积 ——
//   这两个依赖 CLI 版都没有（CLI 不引用 WinForms，也不编译 GuiEntry）。
//   CLI 版本身没有诊断界面，不存在"编出半成品 exe"的风险。
const GUI_ONLY = ["GuiSink.cs", "GuiMain.cs", "GuiWeb.cs", "GuiSelfCheck.cs", "GuiHeadless.cs", "GuiEntry.cs", "NetSim.cs", "Diag.cs"];

let fail = 0;
function bad(m) { console.log("  [XX]   " + m); fail++; }
function good(m) { console.log("  [OK]   " + m); }

console.log("== 编译列表机检 ==");

if (!fs.existsSync(CLI_BAT) || !fs.existsSync(GUI_BAT)) {
    console.log("  [XX]   找不到 build.bat / build_gui.bat");
    process.exit(1);
}

const cliTxt = fs.readFileSync(CLI_BAT, "utf8");
const guiTxt = fs.readFileSync(GUI_BAT, "utf8");

const all = fs.readdirSync(SRC).filter(f => f.endsWith(".cs")).sort();
let nCli = 0, nGui = 0;

for (const f of all) {
    const inCli = cliTxt.indexOf(f) >= 0;
    const inGui = guiTxt.indexOf(f) >= 0;
    const guiOnly = GUI_ONLY.indexOf(f) >= 0;

    if (!inGui) { bad("GUI 列表漏了 " + f); continue; }
    nGui++;

    if (guiOnly) {
        if (inCli) { bad(f + " 是 GUI 专用，不该出现在 CLI 列表"); continue; }
        nCli++;      // 计入"已确认"
        continue;
    }

    if (!inCli) bad("CLI 列表漏了 " + f + "（GUI 有、CLI 没有 → CLI 会编出一个不完整的 exe）");
    else nCli++;
}

// 反向检查：两个 bat 里列了但文件不存在
for (const [name, txt] of [["build.bat", cliTxt], ["build_gui.bat", guiTxt]]) {
    const re = /"([A-Za-z0-9_]+\.cs)"/g;
    let m, seen = {};
    while ((m = re.exec(txt)) !== null) seen[m[1]] = 1;
    for (const f of Object.keys(seen)) {
        if (!fs.existsSync(path.join(SRC, f))) bad(name + " 列了不存在的文件 " + f);
    }
}

good("源文件 " + all.length + " 个：CLI 覆盖 " + nCli + "，GUI 覆盖 " + nGui);
console.log("");
console.log(fail === 0 ? "  编译列表完整" : "  编译列表有 " + fail + " 处问题");
process.exit(fail === 0 ? 0 : 1);
