// ============================================================================
//  _check_features.js — 功能清单机检（防"功能被改没了没人发现"）
//
//  背景（真实事故）：
//    · #page-file 插到 #feedback 前面，而 feedback 属于 #page-quick，
//      结果整个文件页空白 —— 所有单测都是绿的，因为没人测"页面结构"。
//    · 投屏最大化用 display:none 隐藏其它格，把隐藏那一路的流挂起了。
//
//  做法：_check_features.json 里每条功能登记"关键落点"（文件 + 必须出现的片段）
//        和"验证入口"（测试文件）。这里逐条核对，落点消失就红。
//
//  运行：node _check_features.js
// ============================================================================
const fs = require("fs");
const path = require("path");

const ROOT = __dirname;
const cfgPath = path.join(ROOT, "_check_features.json");
let fail = 0;

function bad(msg) { console.log("  [XX]   " + msg); fail++; }
function good(msg) { console.log("  [OK]   " + msg); }
function warn(msg) { console.log("  [!!]   " + msg); }

console.log("== 功能清单机检 ==");

if (!fs.existsSync(cfgPath)) {
    console.log("  [XX]   找不到 _check_features.json");
    process.exit(1);
}
const cfg = JSON.parse(fs.readFileSync(cfgPath, "utf8"));
const cache = {};
function text(rel) {
    if (cache[rel] !== undefined) return cache[rel];
    const p = path.join(ROOT, rel);
    cache[rel] = fs.existsSync(p) ? fs.readFileSync(p, "utf8") : null;
    return cache[rel];
}

let checked = 0;
for (const f of cfg.features || []) {
    const problems = [];
    for (const a of (f.anchors || [])) {
        const src = text(a.file);
        if (src === null) { problems.push("缺文件 " + a.file); continue; }
        for (const needle of (a.has || [])) {
            if (src.indexOf(needle) < 0) problems.push(a.file + " 里找不到 `" + needle + "`");
        }
    }
    for (const t of (f.tests || [])) {
        const p = path.join(ROOT, t);
        if (!fs.existsSync(p)) { problems.push("缺测试 " + t); continue; }
        if (fs.statSync(p).size < 400) problems.push("测试文件过小（疑似空壳）" + t);
    }
    checked++;
    if (problems.length) bad(f.id + "（" + f.desc + "）：" + problems.join("；"));
    else good(f.id + "  " + f.desc);
}

// ---- bat 只允许 ASCII（真实事故：中文注释被 GBK 拆成命令）----
const bats = ["_cs/build.bat", "adb_log_gui/build_gui.bat", "adb_log_gui/make_min.bat", "release.bat"];
for (const b of bats) {
    const src = text(b);
    if (src === null) { warn("找不到 " + b + "（跳过）"); continue; }
    const badLines = [];
    src.split(/\r?\n/).forEach((line, i) => {
        if (/[^\x00-\x7F]/.test(line)) badLines.push((i + 1) + ": " + line.trim().slice(0, 40));
    });
    if (badLines.length) bad(b + " 含非 ASCII 字符 → " + badLines.slice(0, 3).join(" | "));
    else good(b + " 全 ASCII");
}

// ---- ui.html 里不允许出现"未完成的占位提示"----
const ui = text("adb_log_gui/webview2/ui.html") || "";
const placeholders = ["TODO", "FIXME", "待实现", "占位符", "console.log("];
for (const p of placeholders) {
    if (ui.indexOf(p) >= 0) {
        const n = ui.split(p).length - 1;
        if (p === "console.log(" && n <= 2) { warn("ui.html 有 " + n + " 处 " + p + "（可接受）"); continue; }
        bad("ui.html 含占位/调试残留 " + p + " ×" + n);
    }
}

console.log("");
console.log(fail === 0
    ? "  功能清单机检通过（" + checked + " 项）"
    : "  功能清单机检失败 " + fail + " 项");
process.exit(fail === 0 ? 0 : 1);
