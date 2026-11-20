@echo off
rem ============================================================================
rem  build.bat - compile the adb tool with the built-in csc.exe
rem  output: adb_log_export.exe  (log browser + exporter + Chinese intent sender)
rem  zero dependency: Windows 7/10/11 ships .NET Framework 4.x + csc.exe
rem
rem  CS0016 (file in use) defence, three layers:
rem    1) kill the target and WAIT until it is really gone
rem    2) compile to a temp name (never touches the locked exe)
rem    3) replace the old exe after compile; if it is still locked,
rem       keep the new build as *_new.exe and tell the user what to do
rem ============================================================================
setlocal EnableExtensions
cd /d "%~dp0"

set "OUT=%~dp0..\adb_log_export.exe"
set "TMPOUT=%~dp0..\adb_log_export_new.exe"
set "CSC="

rem prefer 64-bit compiler, fall back to 32-bit
if exist "%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe" set "CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not defined CSC if exist "%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe" set "CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe"

if not defined CSC (
    echo [ERROR] csc.exe not found. Please install .NET Framework 4.x.
    pause
    exit /b 1
)

rem ---- layer 1: make sure the target is not running ----
call :KillTarget "adb_log_export.exe"
if errorlevel 1 exit /b 1

if exist "%TMPOUT%" del /f /q "%TMPOUT%" >nul 2>&1

echo Compiler: %CSC%
echo.
echo compiling adb_log_export.exe ...

rem /codepage:65001 forces csc to read source as UTF-8 (sources contain Chinese, files have BOM)
rem /langversion:5 locks C# 5.0 so newer syntax does not slip in
rem Common.cs is the shared pure-function utility
"%CSC%" /nologo /optimize+ /target:exe /platform:anycpu /codepage:65001 /main:AdbLogExport.App ^
    /out:"%TMPOUT%" ^
    "%~dp0Program.cs" "%~dp0Prefix.cs" "%~dp0Adb.cs" "%~dp0AdbCmd.cs" "%~dp0CmdRegistry.cs" "%~dp0PkgVer.cs" "%~dp0Env.cs" "%~dp0Render.cs" "%~dp0LineEdit.cs" "%~dp0Send.cs" "%~dp0Voice.cs" "%~dp0Common.cs" "%~dp0Probe.cs" "%~dp0Reconnect.cs" "%~dp0Root.cs" "%~dp0CarInfo.cs" "%~dp0TaskCmds.cs" "%~dp0Hdc.cs" "%~dp0ApkList.cs" "%~dp0ApkCmds.cs" "%~dp0Wireless.cs" "%~dp0DeviceWatcher.cs" "%~dp0FileBrowser.cs" "%~dp0Embed.cs" "%~dp0Ffmpeg.cs" "%~dp0Scrcpy.cs" "%~dp0Tbox.cs" "%~dp0CustomStore.cs"

if errorlevel 1 (
    echo.
    echo [ERROR] compile failed, see errors above
    if exist "%TMPOUT%" del /f /q "%TMPOUT%" >nul 2>&1
    pause
    exit /b 1
)

rem ---- layer 3: replace the old exe ----
if exist "%OUT%" del /f /q "%OUT%" >nul 2>&1

if exist "%OUT%" (
    echo.
    echo [ERROR] cannot replace the old exe - it is still locked:
    echo         %OUT%
    echo.
    echo         Most likely adb_log_export.exe is running as Administrator,
    echo         so a normal taskkill cannot close it.
    echo.
    echo         The new build is ready at:
    echo         %TMPOUT%
    echo.
    echo         Do ONE of these:
    echo           1. close the running adb_log_export.exe, then run this script again
    echo           2. right-click this build.bat - Run as administrator
    echo           3. close the program, then rename *_new.exe to adb_log_export.exe
    pause
    exit /b 1
)

move /y "%TMPOUT%" "%OUT%" >nul
if not exist "%OUT%" (
    echo [ERROR] move failed, new build is at %TMPOUT%
    pause
    exit /b 1
)

echo.
echo Compile success: %OUT%
echo.
echo Double-click adb_log_export.exe to run.
echo   - log browsing / export: ls / cd / pull / push / type a Windows path
echo   - Chinese intent send  : send TEXT  or just type Chinese
echo   - package versions     : ver / now
echo Configure via adb_log_export.ini and cmds.ini in the same folder.
pause
exit /b 0

rem ============================================================================
rem  :KillTarget  <exe name>
rem  Kill the process and WAIT until it is really gone (up to ~3 seconds).
rem  Returns errorlevel 1 if it could not be closed.
rem ============================================================================
:KillTarget
rem [2026-11-12] absolute System32\find.exe and ping.exe.
rem   Plain `find` resolves through PATH; launched from Git Bash that PATH can
rem   reach Git's /usr/bin first, so Unix find runs and dies with
rem       find: '/i': No such file or directory
rem   The check then never matched and the "is it running" probe always said no.
tasklist /fi "imagename eq %~1" 2>nul | "%SystemRoot%\System32\find.exe" /i "%~1" >nul
if errorlevel 1 exit /b 0

echo [WARN] %~1 is running, closing it ...
taskkill /f /t /im %~1 >nul 2>&1

set "__try=0"
:__killwait
set /a "__try+=1"
"%SystemRoot%\System32\ping.exe" -n 2 127.0.0.1 >nul
tasklist /fi "imagename eq %~1" 2>nul | "%SystemRoot%\System32\find.exe" /i "%~1" >nul
if errorlevel 1 (
    echo        closed.
    exit /b 0
)
if %__try% lss 3 goto __killwait

echo.
echo [ERROR] %~1 is still running after 3 attempts.
echo         It is probably started as Administrator, so a normal taskkill fails.
echo         Please close it manually first, or run this script as Administrator.
pause
exit /b 1
