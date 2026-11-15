@echo off
rem ======================================================================
rem  文件名 : adb_send_chinese.bat     版本 v2
rem  功  能 : 中文文本 → ADB 意图发送工具
rem            输入中文回车立即发送一次；输入 1~9 发送常用语；
rem            输入 b 批量发送 txt 文件（单条失败自动跳过，继续下一条）
rem  编  码 : ANSI/GBK + CRLF（请勿另存为 UTF-8，否则中文会乱码）
rem  环  境 : Windows 7 / 10 / 11，需要 adb 与 PowerShell
rem  说  明 : 请双击运行或在 cmd 窗口内交互使用，不支持管道重定向喂输入
rem ======================================================================
chcp 936 >nul 2>&1
setlocal

rem ------------------------- 可配置区 -------------------------
rem adb 可执行文件：已在 PATH 中保持 adb；否则写完整路径（路径含空格时请改用 PATH）
set "ADB=adb"
rem 设备序列号：只连一台设备留空；连多台必须填（先执行 adb devices 查看）
set "ADB_SERIAL="
rem 意图 action 与 URI 前缀（换接口只改这两行）
set "ACTION=android.intent.action.VIEW"
set "URI_PREFIX=sr://syncore.vpa.sr/test?text="
rem 发送失败后自动重试次数：0 表示不重试
set "RETRY=1"
rem 常用语 1~9：填中文即可，留空表示该编号不可用
set "QUICK_1="
set "QUICK_2="
set "QUICK_3="
set "QUICK_4="
set "QUICK_5="
set "QUICK_6="
set "QUICK_7="
set "QUICK_8="
set "QUICK_9="
rem ------------------------------------------------------------

set "TAG=%RANDOM%%RANDOM%"
set "INFILE=%TEMP%\adbs_%TAG%_in.txt"
set "ECFILE=%TEMP%\adbs_%TAG%_enc.txt"
set "RESFILE=%TEMP%\adbs_%TAG%_res.txt"

rem ==================== 一、环境自检 ====================
"%ADB%" version >nul 2>&1
if errorlevel 1 goto err_noadb

set "PS=powershell"
where powershell >nul 2>&1
if not errorlevel 1 goto ps_ready
set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PS%" goto err_nops
:ps_ready

set "SERIAL_OPT="
if not "%ADB_SERIAL%"=="" set "SERIAL_OPT= -s %ADB_SERIAL%"

rem 统计设备：先输出到临时文件，再逐行解析，避免 for 命令首字符是引号导致解析异常
"%ADB%"%SERIAL_OPT% devices >"%RESFILE%" 2>&1
set /a DEVN=0
set "DEVID="
for /f "usebackq skip=1 tokens=1,2" %%A in ("%RESFILE%") do call :dev_count "%%A" "%%B"

if %DEVN%==0 goto err_nodev
if %DEVN% GTR 1 if "%ADB_SERIAL%"=="" goto err_multidev

echo.
echo ==================================================================
echo   中文 → ADB 意图发送工具          [设备] %DEVN% 台在线  %DEVID%
echo ------------------------------------------------------------------
echo   直接输入中文回车 = 发送    1-9 = 常用语    b = 批量    h = 帮助    q = 退出
echo ==================================================================
echo.

rem ==================== 二、主循环 ====================
:main_menu
rem 哨兵值技巧：直接回车会把 TEXT 置为空字符串，而输入流结束（Ctrl+Z）
rem 不会改动 TEXT，因此可以精确区分"空回车"与"输入结束"
set "TEXT=##EOF##"
set /p "TEXT=请输入 → "
if "%TEXT%"=="##EOF##" goto quit
if not defined TEXT goto main_menu

rem 交给 PowerShell 做 UTF-8 百分号编码：中文经环境变量传递（Unicode），不会乱码
set "SRC=%TEXT%"
call :enc_src
if not defined ENC goto main_menu

rem 功能指令（都是 ASCII，编码后保持不变，不会与中文冲突）
if /i "%ENC%"=="q" goto quit
if /i "%ENC%"=="quit" goto quit
if /i "%ENC%"=="exit" goto quit
if /i "%ENC%"=="b" goto batch_mode
if /i "%ENC%"=="h" goto help
if /i "%ENC%"=="help" goto help

rem 常用语 1~9
if "%ENC%"=="1" goto quick_1
if "%ENC%"=="2" goto quick_2
if "%ENC%"=="3" goto quick_3
if "%ENC%"=="4" goto quick_4
if "%ENC%"=="5" goto quick_5
if "%ENC%"=="6" goto quick_6
if "%ENC%"=="7" goto quick_7
if "%ENC%"=="8" goto quick_8
if "%ENC%"=="9" goto quick_9

rem 普通文本：直接发送
call :send_enc
goto main_menu

rem ==================== 三、常用语分支 ====================
:quick_1
set "SRC=%QUICK_1%"
goto quick_run
:quick_2
set "SRC=%QUICK_2%"
goto quick_run
:quick_3
set "SRC=%QUICK_3%"
goto quick_run
:quick_4
set "SRC=%QUICK_4%"
goto quick_run
:quick_5
set "SRC=%QUICK_5%"
goto quick_run
:quick_6
set "SRC=%QUICK_6%"
goto quick_run
:quick_7
set "SRC=%QUICK_7%"
goto quick_run
:quick_8
set "SRC=%QUICK_8%"
goto quick_run
:quick_9
set "SRC=%QUICK_9%"

:quick_run
if not defined SRC (
    echo   [!] 该编号的常用语未配置
    goto main_menu
)
call :enc_src
if not defined ENC (
    echo   [!] 文本编码失败
    goto main_menu
)
call :send_enc
goto main_menu

rem ==================== 四、批量模式 ====================
:batch_mode
echo.
echo   [批量] 把 txt 文件直接拖进窗口，或输入完整路径（输入 q 取消）
set "TEXT=##EOF##"
set /p "TEXT=  路径 → "
if "%TEXT%"=="##EOF##" goto quit
if not defined TEXT goto main_menu

rem 先把路径编码，用编码结果判断是否为取消指令，避免路径里的引号干扰 if 比较
set "SRC=%TEXT%"
call :enc_src
if /i "%ENC%"=="q" goto main_menu
call :batch_read
if "%BSTATE%"=="##NOFILE##" (
    echo   [!] 文件不存在，请检查路径
    goto main_menu
)
if "%BSTATE%"=="##BOM##" (
    echo   [!] 该 txt 是 UTF-8 BOM 编码，请用记事本另存为 ANSI 后重试
    goto main_menu
)
if "%BSTATE%"=="##BAD##" (
    echo   [!] 该 txt 疑似 UTF-8 编码，请用记事本另存为 ANSI 后重试
    goto main_menu
)
if not "%BSTATE%"=="##OK##" (
    echo   [!] 读取文件失败
    goto main_menu
)

rem 统计待发送条数并确认：无 BOM 的 UTF-8 文件无法可靠识别，
rem 显示条数可让用户在执行前确认文件读对了
set /a BCNT=0
for /f "usebackq delims=" %%L in ("%ECFILE%") do set /a BCNT+=1
set /a BCNT-=1
if %BCNT%==0 (
    echo   [!] 文件里没有可发送的内容（空行会被自动跳过）
    goto main_menu
)
echo   共 %BCNT% 条待发送，直接回车开始，输入 n 取消
echo   提示：txt 需为 ANSI 编码，若发出的内容是乱码请另存为 ANSI
set "TEXT="
set /p "TEXT=  "
if /i "%TEXT%"=="n" goto main_menu

set /a BLN=0
set /a BOK=0
set /a BNG=0
set "BFIRST="
set "BFERR="
echo.
<nul set /p "=  发送中 "
for /f "usebackq delims=" %%L in ("%ECFILE%") do (
    set "SRC=%%L"
    call :batch_step
)
call :batch_report
goto main_menu

rem ==================== 五、帮助 ====================
:help
echo.
echo   用法说明
echo   ------------------------------------------------------------
echo     直接输入中文 + 回车   发送一次
echo     1 ~ 9                 发送对应常用语（在可配置区设置）
echo     b                     批量发送 txt 文件（失败自动跳过）
echo     h 或 help             显示本帮助
echo     q                     退出
echo   ------------------------------------------------------------
echo     当前目标：%URI_PREFIX%
echo     失败重试：%RETRY% 次
echo.

rem ==================== 六、子程序 ====================
goto main_menu

:dev_count
rem 只统计状态为 device 的行，过滤 offline / unauthorized 等
if /i "%~2"=="device" (
    set /a DEVN+=1
    set "DEVID=%~1"
)
exit /b

:read_input
rem 已改为 set /p 读取，此子程序保留为空实现以兼容旧调用（不再使用）
exit /b

:enc_src
rem 输入 SRC（中文原文，经环境变量传递）  输出 ENC（UTF-8 百分号编码）
del "%ECFILE%" >nul 2>&1
"%PS%" -NoProfile -ExecutionPolicy Bypass -Command "[IO.File]::WriteAllText($env:ECFILE,[uri]::EscapeDataString($env:SRC),[Text.Encoding]::ASCII)"
set "ENC="
if exist "%ECFILE%" for /f "usebackq delims=" %%E in ("%ECFILE%") do set "ENC=%%E"
exit /b

:batch_read
rem 输入 SRC（路径原文），输出 BSTATE 与 ECFILE
rem 读文件 → 校验存在 → 检测 BOM / 疑似 UTF-8 → 逐行做 UTF-8 百分号编码
del "%ECFILE%" >nul 2>&1
"%PS%" -NoProfile -ExecutionPolicy Bypass -Command "$p=$env:SRC; if(-not $p){[IO.File]::WriteAllText($env:ECFILE,'##NOFILE##',[Text.Encoding]::ASCII); exit}; $p=$p.Trim([char]34).Trim(); if(-not (Test-Path -LiteralPath $p)){[IO.File]::WriteAllText($env:ECFILE,'##NOFILE##',[Text.Encoding]::ASCII); exit}; $b=[IO.File]::ReadAllBytes($p); if($b.Length -ge 3 -and $b[0] -eq 239 -and $b[1] -eq 187 -and $b[2] -eq 191){[IO.File]::WriteAllText($env:ECFILE,'##BOM##',[Text.Encoding]::ASCII); exit}; $t=[Text.Encoding]::GetEncoding(936).GetString($b); if($t.Contains([char]0xFFFD)){[IO.File]::WriteAllText($env:ECFILE,'##BAD##',[Text.Encoding]::ASCII); exit}; $o=New-Object System.Collections.ArrayList; [void]$o.Add('##OK##'); foreach($l in $t.Split([char[]]@(13,10))){ if($l.Trim().Length -gt 0){ [void]$o.Add([uri]::EscapeDataString($l)) } }; [IO.File]::WriteAllLines($env:ECFILE,$o,[Text.Encoding]::ASCII)"
set "BSTATE="
if exist "%ECFILE%" for /f "usebackq delims=" %%E in ("%ECFILE%") do if not defined BSTATE set "BSTATE=%%E"
exit /b

:batch_step
rem 第 1 行是状态标记，之后每行一条待发送文本
set /a BLN+=1
if %BLN% EQU 1 exit /b
set "ENC=%SRC%"
call :send_quiet
if "%SENDOK%"=="1" (
    set /a BOK+=1
) else (
    set /a BNG+=1
    if not defined BFIRST set /a BFIRST=%BLN%-1
    if not defined BFERR set "BFERR=%ERRMSG%"
)
<nul set /p "=."
exit /b

:batch_report
echo.
if %BNG%==0 goto rep_ok
set "MSG=完成：成功 %BOK% 条，失败 %BNG% 条"
call :p_fail
if defined BFERR echo        首个失败：第 %BFIRST% 条 - %BFERR%
exit /b
:rep_ok
set "MSG=全部成功（%BOK% 条）"
call :p_ok
exit /b

:send_enc
rem 交互模式发送：带重试，结果着色输出
set /a TRY=0
:send_try
set /a TRY+=1
call :do_adb
set "SENDOK=0"
findstr /i /c:"Error" /c:"Exception" /c:"not allowed" /c:"does not exist" /c:"Permission Denial" "%RESFILE%" >nul 2>&1
if not errorlevel 1 goto send_failed
if not "%RC%"=="0" goto send_failed
set "SENDOK=1"
set "MSG=发送成功"
call :p_ok
exit /b

:send_failed
if %TRY% LEQ %RETRY% (
    ping -n 3 127.0.0.1 >nul 2>&1
    goto send_try
)
call :build_errmsg
set "MSG=发送失败：%ERRMSG%"
call :p_fail
if defined TIP echo        建议：%TIP%
exit /b

:send_quiet
rem 批量模式发送：逻辑同上，但不输出过程信息
set /a TRY=0
:sendq_try
set /a TRY+=1
call :do_adb
set "SENDOK=0"
findstr /i /c:"Error" /c:"Exception" /c:"not allowed" /c:"does not exist" /c:"Permission Denial" "%RESFILE%" >nul 2>&1
if not errorlevel 1 goto sendq_failed
if not "%RC%"=="0" goto sendq_failed
set "SENDOK=1"
exit /b

:sendq_failed
if %TRY% LEQ %RETRY% (
    ping -n 3 127.0.0.1 >nul 2>&1
    goto sendq_try
)
call :build_errmsg
exit /b

:do_adb
rem 全脚本唯一真正调用 adb 的地方，集中一处便于维护
"%ADB%"%SERIAL_OPT% shell am startservice -a %ACTION% -d "%URI_PREFIX%%ENC%" >"%RESFILE%" 2>&1
set "RC=%ERRORLEVEL%"
exit /b

:build_errmsg
rem 从设备返回中提取错误行，并给出中文处置建议
set "ERRMSG="
set "TIP="
for /f "usebackq delims=" %%X in (`findstr /i /c:"Error" /c:"Exception" /c:"not allowed" /c:"offline" /c:"unauthorized" "%RESFILE%"`) do if not defined ERRMSG set "ERRMSG=%%X"
if not defined ERRMSG for /f "usebackq delims=" %%X in ("%RESFILE%") do if not defined ERRMSG set "ERRMSG=%%X"
if not defined ERRMSG set "ERRMSG=设备无返回信息"
set "ERRMSG=%ERRMSG:"=%"
set "ERRMSG=%ERRMSG:~0,80%"

findstr /i /c:"not allowed to start service" "%RESFILE%" >nul 2>&1
if not errorlevel 1 if not defined TIP set "TIP=Android 8+ 后台服务限制，请让 App 保持前台，或改用 start-foreground-service"
findstr /i /c:"Activity not started" "%RESFILE%" >nul 2>&1
if not errorlevel 1 if not defined TIP set "TIP=未匹配到 intent-filter，请确认 App 已安装并注册该 scheme，必要时补 -n 包名/组件"
findstr /i /c:"device offline" "%RESFILE%" >nul 2>&1
if not errorlevel 1 if not defined TIP set "TIP=设备离线，请检查数据线与 USB 连接"
findstr /i /c:"unauthorized" "%RESFILE%" >nul 2>&1
if not errorlevel 1 if not defined TIP set "TIP=设备未授权，请在手机弹窗中点允许 USB 调试"
findstr /i /c:"no devices" /c:"more than one device" "%RESFILE%" >nul 2>&1
if not errorlevel 1 if not defined TIP set "TIP=设备数量异常，请执行 adb devices 检查，多设备时填写 ADB_SERIAL"
exit /b

:p_ok
"%PS%" -NoProfile -ExecutionPolicy Bypass -Command "Write-Host ('  ' + [char]0x221A + ' ' + $env:MSG) -ForegroundColor Green"
exit /b

:p_fail
"%PS%" -NoProfile -ExecutionPolicy Bypass -Command "Write-Host ('  ' + [char]0x00D7 + ' ' + $env:MSG) -ForegroundColor Red"
exit /b

rem ==================== 七、错误与退出 ====================
:err_noadb
echo.
echo   [!] 无法执行 adb：%ADB%
echo       请安装 Android platform-tools 并加入 PATH，
echo       或修改脚本可配置区的 ADB 变量为 adb.exe 的完整路径。
echo.
pause
goto quit

:err_nops
echo.
echo   [!] 系统中找不到 PowerShell，无法对中文做 URL 编码
echo.
pause
goto quit

:err_nodev
echo.
echo   [!] 没有检测到已连接设备
echo       1. 手机打开开发者选项并启用 USB 调试
echo       2. 连接数据线，执行 adb devices 确认状态为 device
echo.
pause
goto quit

:err_multidev
echo.
echo   [!] 检测到 %DEVN% 台设备，请在可配置区填写 ADB_SERIAL
"%ADB%" devices
echo.
pause
goto quit

:quit
del "%INFILE%" >nul 2>&1
del "%ECFILE%" >nul 2>&1
del "%RESFILE%" >nul 2>&1
echo   已退出。
endlocal
exit /b 0
