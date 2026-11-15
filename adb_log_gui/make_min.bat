@echo off
rem ============================================================================
rem  make_min.bat - build the minimal share package (no ffmpeg.exe)
rem
rem  Why: the full dist\ is ~102 MB because ffmpeg.exe alone is ~105 MB.
rem  Most users only need commands / logs / APK management; screen recording
rem  is the only feature that needs ffmpeg, and it already fails with a clear
rem  message when the file is missing.
rem
rem  Output: dist_min\        (exe + WebView2 dlls + ui.html + ini + manual)
rem          adb_Tool_min.zip (same content, ready to share)
rem
rem  NOTE: keep every comment and path ASCII. cmd runs under the OEM codepage
rem  (GBK here); UTF-8 Chinese in a .bat gets split into command fragments.
rem        The manual is copied from ..\docs\*.md to manual.md for that reason.
rem ============================================================================
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

rem NO_PAUSE=1 -> automated build, never wait for a keypress
set "DOPAUSE=pause"
if defined NO_PAUSE set "DOPAUSE=rem"

set "DIST=%~dp0dist_min"
set "ZIP=%~dp0adb_Tool_min.zip"

rem [2026-11-14] Take the exe from dist\ when present.
rem   Reason: build_gui.bat may have to keep the fresh build as
rem   adb_Tool_new.exe (the old adb_Tool.exe is locked by a running window),
rem   while dist\ always receives whichever binary is actually new.
set "BIN=%~dp0adb_Tool.exe"
if exist "%~dp0dist\adb_Tool.exe" set "BIN=%~dp0dist\adb_Tool.exe"

if not exist "%BIN%" (
    echo [ERROR] adb_Tool.exe not found. Run build_gui.bat first.
    %DOPAUSE%
    exit /b 1
)

if exist "%DIST%" rmdir /s /q "%DIST%" >nul 2>&1
mkdir "%DIST%" >nul 2>&1
mkdir "%DIST%\webview2" >nul 2>&1

copy /y "%BIN%"                                        "%DIST%\adb_Tool.exe" >nul
copy /y "%~dp0Microsoft.Web.WebView2.Core.dll"          "%DIST%\" >nul
copy /y "%~dp0Microsoft.Web.WebView2.WinForms.dll"      "%DIST%\" >nul
copy /y "%~dp0WebView2Loader.dll"                       "%DIST%\" >nul
copy /y "%~dp0adb_log_export.ini"                       "%DIST%\" >nul
copy /y "%~dp0cmds.ini"                                 "%DIST%\" >nul
copy /y "%~dp0webview2\ui.html"                         "%DIST%\webview2\" >nul
rem [2026-11-15] Keep the external window icon in sync with the embedded one.
copy /y "%~dp0adb_Tool.ico"                             "%DIST%\" >nul

rem manual: ..\docs\*.md -> dist_min\manual.md
for %%F in ("%~dp0..\docs\*.md") do copy /y "%%~fF" "%DIST%\manual.md" >nul

set "MISSING="
for %%F in ("%DIST%\adb_Tool.exe" "%DIST%\Microsoft.Web.WebView2.Core.dll" "%DIST%\Microsoft.Web.WebView2.WinForms.dll" "%DIST%\WebView2Loader.dll" "%DIST%\adb_log_export.ini" "%DIST%\cmds.ini" "%DIST%\webview2\ui.html" "%DIST%\adb_Tool.ico") do (
    if not exist %%F set "MISSING=!MISSING! %%~nxF"
)
if defined MISSING (
    echo.
    echo [ERROR] missing files:!MISSING!
    echo         check webview2\ subfolder and the ini files
    %DOPAUSE%
    exit /b 1
)

rem ---- zip ----
if exist "%ZIP%" del /f /q "%ZIP%" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Compress-Archive -Path '%DIST%\*' -DestinationPath '%ZIP%' -Force" >nul 2>&1
if not exist "%ZIP%" (
    echo [WARN] zip failed; the folder dist_min is still usable.
)

set /a "TOTAL=0"
for /r "%DIST%" %%F in (*) do set /a "TOTAL+=%%~zF"
set /a "TMB=TOTAL/1048576"
set /a "TKB=(TOTAL%%1048576)*100/1048576"

echo.
echo Minimal package ready: %DIST%  (%TMB%.%TKB% MB)
if exist "%ZIP%" echo Shareable zip      : %ZIP%
echo Notes: no ffmpeg.exe - screen recording needs it, everything else works.
%DOPAUSE%
exit /b 0
