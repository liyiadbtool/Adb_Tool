<#
get-headless.ps1  —  一键获取 chrome-headless-shell（免安装，供 377 的 UI 测试使用）

用法（在项目根目录）：
    powershell -ExecutionPolicy Bypass -File tools\get-headless.ps1

可选参数：
    -Channel stable|beta|dev|canary   默认 stable
    -Force                            已存在也重新下载

为什么需要它：
    UI 交互测试（377/_test_ui_behavior.py，279 条断言）依赖一个能 --dump-dom 的浏览器。
    本机 Edge 曾因启动参数被拼坏而静默退出，且部分环境 msedge --dump-dom 返回空。
    内置一份 headless 内核，测试就不受本机浏览器影响。

安装位置：tools\chrome-headless-shell\chrome-headless-shell.exe
该目录体积较大（约 120MB），不入库、不提交；换机器重新跑本脚本即可。
#>

param(
    [ValidateSet('stable', 'beta', 'dev', 'canary')]
    [string]$Channel = 'stable',
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$root = Split-Path -Parent $PSScriptRoot          # 项目根（tools 的上一级）
$dest = Join-Path $root 'tools\chrome-headless-shell'
$exe  = Join-Path $dest 'chrome-headless-shell.exe'

if ((Test-Path $exe) -and -not $Force) {
    Write-Host "[跳过] 已存在：$exe" -ForegroundColor DarkGray
    Write-Host "       要重新下载请加 -Force" -ForegroundColor DarkGray
    exit 0
}

Write-Host "[1/4] 查询 Chrome for Testing 版本（$Channel）..." -ForegroundColor Cyan
$api = 'https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json'
$data = Invoke-RestMethod -Uri $api -TimeoutSec 60
$ch = $data.channels.($Channel.Substring(0,1).ToUpper() + $Channel.Substring(1))
if (-not $ch) { throw "无法读取通道 $Channel 的版本信息" }

$url = $null
foreach ($item in $ch.downloads.'chrome-headless-shell') {
    if ($item.platform -eq 'win64') { $url = $item.url; break }
}
if (-not $url) { throw "该版本没有 win64 的 chrome-headless-shell 下载包" }
Write-Host "      版本 $($ch.version)" -ForegroundColor DarkGray
Write-Host "      地址 $url" -ForegroundColor DarkGray

$zip = Join-Path $env:TEMP 'chrome-headless-shell-win64.zip'

Write-Host "[2/4] 下载（约 120MB，支持断点续传）..." -ForegroundColor Cyan
$total = 0
try {
    $head = Invoke-WebRequest -Uri $url -Method Head -UseBasicParsing -TimeoutSec 60
    $total = [int64]$head.Headers.'Content-Length'
} catch { }

$have = 0
if (Test-Path $zip) { $have = (Get-Item $zip).Length }
if ($total -gt 0 -and $have -ge $total) {
    Write-Host "      已下载完整，跳过" -ForegroundColor DarkGray
} else {
    if ($have -gt 0) { Write-Host "      续传：已有 $([math]::Round($have/1MB,1)) MB" -ForegroundColor DarkGray }
    # PS 5.1 的 Invoke-WebRequest 不允许自定义 Range 头，这里直接用 .NET 请求
    $req = [System.Net.HttpWebRequest]::Create($url)
    $req.Timeout = 120000
    $req.ReadWriteTimeout = 600000
    if ($have -gt 0) { $req.AddRange($have) }
    $resp = $req.GetResponse()
    $rs = $resp.GetResponseStream()
    $fs = [System.IO.File]::Open($zip, [System.IO.FileMode]::Append, [System.IO.FileAccess]::Write)
    try { $rs.CopyTo($fs) } finally { $fs.Close(); $rs.Close(); $resp.Close() }
    Write-Host "      完成 $([math]::Round((Get-Item $zip).Length/1MB,1)) MB" -ForegroundColor DarkGray
}

Write-Host "[3/4] 解压..." -ForegroundColor Cyan
$tmp = Join-Path $env:TEMP ('chs_' + [guid]::NewGuid().ToString('N').Substring(0, 8))
Expand-Archive -Path $zip -DestinationPath $tmp -Force
$inner = Join-Path $tmp 'chrome-headless-shell-win64'
if (-not (Test-Path $inner)) { throw "压缩包结构与预期不符：$tmp" }

if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
New-Item -ItemType Directory -Path (Split-Path $dest) -Force | Out-Null
Move-Item -Path $inner -Destination $dest
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "[4/4] 自检..." -ForegroundColor Cyan
$probe = Join-Path $env:TEMP 'chs_probe.html'
'<html><body><h1>PROBE</h1></body></html>' | Set-Content -Path $probe -Encoding UTF8
$out = & $exe --headless --disable-gpu --no-sandbox --dump-dom ("file:///" + ($probe -replace '\\', '/')) 2>$null
Remove-Item $probe -ErrorAction SilentlyContinue

if ($out -match 'PROBE') {
    Write-Host "      OK：$exe" -ForegroundColor Green
    Write-Host ""
    Write-Host "完成。运行 UI 测试：" -ForegroundColor Green
    Write-Host "    cd 377; python _test_ui_behavior.py" -ForegroundColor Green
} else {
    Write-Host "      失败：浏览器没有输出 DOM，请检查杀软/策略拦截" -ForegroundColor Red
    exit 1
}
