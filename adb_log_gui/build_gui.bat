@echo off
rem ============================================================================
rem  build_gui.bat - build the GUI edition
rem
rem  output: adb_log_gui.exe  (in this folder)
rem
rem  The ONLY difference from _cs\build.bat is /main: pointing at GuiEntry
rem  plus the WinForms references. Command logic is NOT duplicated - both
rem  exes are compiled from the same .cs files under _cs.
rem
rem  Keeps the project rules: /langversion:5 (C# 5.0) and /codepage:65001
rem  (sources are UTF-8 with BOM).
rem ============================================================================
rem  pause policy  [2026-11-12]
rem
rem  `pause` waits for a keypress forever. That is what we want when the user
rem  double-clicks this script (otherwise the window closes instantly and the
rem  error message is never seen). But it hangs the caller when the script is
rem  driven from automation -- one failed build here sat on `pause` for 55 min.
rem
rem  So: still pause by default, but skip it when the caller sets NO_PAUSE=1.
rem      automated build:  set NO_PAUSE=1 && build_gui.bat
rem
rem  NOTE: keep every comment in this file ASCII. The script runs under the
rem  OEM codepage (GBK here); UTF-8 Chinese comments get mis-split into
rem  command fragments and cmd tries to execute the tails of those lines.
rem ============================================================================
set "DOPAUSE=pause"
if defined NO_PAUSE set "DOPAUSE=rem"

setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "SRC=%~dp0..\_cs"
set "OUT=%~dp0adb_Tool.exe"
set "TMPOUT=%~dp0adb_Tool_new.exe"
set "CSC="

if exist "%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe" set "CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not defined CSC if exist "%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe" set "CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe"

if not defined CSC (
    echo [ERROR] csc.exe not found. Please install .NET Framework 4.x.
    %DOPAUSE%
    exit /b 1
)

rem [2026-11-12] use the absolute System32\find.exe.
rem   Calling plain `find` resolves through PATH, and when this script is launched
rem   from Git Bash the inherited PATH can reach Git's /usr/bin first -- Unix find
rem   then runs and dies with:  find: '/i': No such file or directory
rem   The check silently never matched, so adb_Tool.exe was never auto-closed and
rem   the later `move` over a running exe failed. Harmless but misleading.
tasklist /fi "imagename eq adb_Tool.exe" 2>nul | "%SystemRoot%\System32\find.exe" /i "adb_Tool.exe" >nul
if not errorlevel 1 (
    echo [WARN] adb_Tool.exe is running, closing it ...
    taskkill /f /t /im adb_Tool.exe >nul 2>&1
    "%SystemRoot%\System32\ping.exe" -n 2 127.0.0.1 >nul
)

if exist "%TMPOUT%" del /f /q "%TMPOUT%" >nul 2>&1

echo Compiler: %CSC%
echo.
echo compiling adb_Tool.exe ...

rem ---- config files: GUI shares the same ini as the CLI edition ----
rem [2026-11-14] Moved BEFORE the compile: both ini files are embedded as
rem   default templates (see /resource below), so they must exist when the
rem   compiler runs. Missing templates used to be harmless; now they would
rem   silently produce an exe with no default config, so fail loudly here.
if not exist "%~dp0adb_log_export.ini" (
    if exist "%~dp0..\adb_log_export.ini" copy /y "%~dp0..\adb_log_export.ini" "%~dp0adb_log_export.ini" >nul
)
rem 2026-11-19: always sync cmds.ini (used to be "copy only if missing", so edits
rem to the repo copy were silently ignored and new commands never got embedded).
if exist "%~dp0..\cmds.ini" copy /y "%~dp0..\cmds.ini" "%~dp0cmds.ini" >nul
if not exist "%~dp0adb_log_export.ini" (
    echo [ERROR] adb_log_export.ini not found - it is embedded as the default config
    %DOPAUSE%
    exit /b 1
)

rem WebView2 SDK (net462), bundled under webview2\ folder
set "WV2=%~dp0webview2"

rem ============================================================================
rem  Single-exe resources (R8)
rem
rem  Everything the app used to need NEXT TO the exe is compiled in:
rem    adb.ui.html               the whole UI (inline CSS/JS, self-contained)
rem    adb.WebView2.Core.dll     managed SDK assemblies
rem    adb.WebView2.WinForms.dll
rem    adb.WebView2Loader.dll    native loader (extracted at startup)
rem    adb.default.ini           default config, written only when missing
rem    adb.default.cmds.ini
rem
rem  External files still win at runtime (_cs/Embed.cs), so dist\ keeps
rem  shipping them for debugging. The single-file package is just this exe.
rem ============================================================================
set "RES="
if exist "%WV2%\ui.html" set "RES=%RES% /resource:"%WV2%\ui.html",adb.ui.html"
if exist "%WV2%\Microsoft.Web.WebView2.Core.dll" set "RES=%RES% /resource:"%WV2%\Microsoft.Web.WebView2.Core.dll",adb.WebView2.Core.dll"
if exist "%WV2%\Microsoft.Web.WebView2.WinForms.dll" set "RES=%RES% /resource:"%WV2%\Microsoft.Web.WebView2.WinForms.dll",adb.WebView2.WinForms.dll"
if exist "%WV2%\WebView2Loader.dll" set "RES=%RES% /resource:"%WV2%\WebView2Loader.dll",adb.WebView2Loader.dll"
if exist "%~dp0adb_log_export.ini" set "RES=%RES% /resource:"%~dp0adb_log_export.ini",adb.default.ini"
if exist "%~dp0cmds.ini" set "RES=%RES% /resource:"%~dp0cmds.ini",adb.default.cmds.ini"
rem 2026-11-22: System.Management.dll is required by Diag.cs
rem   (WMI queries: CPU model / SMBIOS memory type / OS build number).
rem   WARNING: never put a "rem" line INSIDE the multi-line compile command
rem   below. The line-continuation makes "rem" an ordinary argument, and the
rem   compiler then treats the comment words as source file names (CS2001).
echo Single-exe resources:%RES%

"%CSC%" /nologo /optimize+ /target:winexe /platform:x64 /codepage:65001 /langversion:5 /main:AdbLogExport.Gui.GuiEntry /win32icon:"%~dp0adb_Tool.ico" /out:"%TMPOUT%" %RES% /reference:System.dll /reference:System.Core.dll /reference:System.Drawing.dll /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll /reference:System.Windows.Forms.dll /reference:System.Management.dll /reference:"%WV2%\Microsoft.Web.WebView2.Core.dll" /reference:"%WV2%\Microsoft.Web.WebView2.WinForms.dll" "%SRC%\Program.cs" "%SRC%\Prefix.cs" "%SRC%\Adb.cs" "%SRC%\AdbCmd.cs" "%SRC%\CmdRegistry.cs" "%SRC%\PkgVer.cs" "%SRC%\Env.cs" "%SRC%\Render.cs" "%SRC%\LineEdit.cs" "%SRC%\Send.cs" "%SRC%\Voice.cs" "%SRC%\Common.cs" "%SRC%\Probe.cs" "%SRC%\Reconnect.cs" "%SRC%\Root.cs" "%SRC%\CarInfo.cs" "%SRC%\TaskCmds.cs" "%SRC%\Hdc.cs" "%SRC%\ApkList.cs" "%SRC%\ApkCmds.cs" "%SRC%\Wireless.cs" "%SRC%\DeviceWatcher.cs" "%SRC%\FileBrowser.cs" "%SRC%\Embed.cs" "%SRC%\Ffmpeg.cs" "%SRC%\Scrcpy.cs" "%SRC%\Tbox.cs" "%SRC%\CustomStore.cs" "%SRC%\Profile.cs" "%SRC%\GuiSink.cs" "%SRC%\GuiMain.cs" "%SRC%\GuiWeb.cs" "%SRC%\Diag.cs" "%SRC%\NetSim.cs" "%SRC%\GuiSelfCheck.cs" "%SRC%\GuiHeadless.cs" "%SRC%\GuiEntry.cs"

if errorlevel 1 (
    echo.
    echo [ERROR] compile failed, see errors above
    if exist "%TMPOUT%" del /f /q "%TMPOUT%" >nul 2>&1
    %DOPAUSE%
    exit /b 1
)

rem ---- swap in the new build ----
rem [2026-11-14] The old flow printed "Compile success" even when the swap
rem   failed: it only tested `if not exist "%OUT%"`, and the STALE exe is
rem   still there, so the check passed while the fresh build sat in
rem   adb_Tool_new.exe. That shipped yesterday's binary at least once.
rem   Now we test the temp file instead (it only survives if the move failed)
rem   and keep track of which file the packaging step must copy.
rem   A stale window (or a ghost process from a killed parent) is the usual
rem   culprit; the message says so instead of pretending everything is fine.
if exist "%OUT%" del /f /q "%OUT%" >nul 2>&1
set "BIN=%OUT%"
move /y "%TMPOUT%" "%OUT%" >nul 2>&1
if exist "%TMPOUT%" (
    set "BIN=%TMPOUT%"
    echo.
    echo [WARN] cannot replace %OUT% - it is locked by a running process.
    echo        new build kept as: %TMPOUT%
    echo        dist\ will ship THIS file. Close the old window
    echo        ^(a ghost process needs a reboot^) to restore the normal name.
)

rem ---- WebView2 runtime files: managed DLLs must sit next to the exe ----
rem (the .NET loader only probes the exe dir + GAC, not subfolders).
rem This copies the SDK DLLs AND the x64 native loader to the exe directory.
copy /y "%WV2%\Microsoft.Web.WebView2.Core.dll" "%~dp0" >nul
copy /y "%WV2%\Microsoft.Web.WebView2.WinForms.dll" "%~dp0" >nul
copy /y "%WV2%\WebView2Loader.dll" "%~dp0" >nul

rem ---- clean up the WebView2 user-data dir left by previous runs ----
rem [2026-11-12] Deleting wb2data here is only cleanup, not the real fix.
rem   Root cause: GuiWeb.cs pointed the WebView2 user-data folder at the exe
rem   directory, so one run wrote ~70 MB of browser cache next to the program.
rem   The code now uses %LOCALAPPDATA%\adb_Tool\WebView2 instead.
rem   This line remains to reclaim the legacy folder on existing machines.
if exist "%~dp0wb2data" rmdir /s /q "%~dp0wb2data" >nul 2>&1

rem ============================================================================
rem  Build a clean release folder:  dist\
rem
rem  Why: this folder doubles as the dev workspace. It also holds icons/,
rem  ui_draft/, run logs and compiler leftovers. Zipping it directly would ship
rem  all of that -- and, before the fix above, the 70 MB WebView2 cache too.
rem
rem  So dist\ is rebuilt from an explicit WHITELIST of runtime files:
rem     adb_Tool.exe                       main program
rem     Microsoft.Web.WebView2.*.dll       SDK assemblies (the .NET loader only
rem                                        probes the exe dir, not subfolders)
rem     WebView2Loader.dll                 x64 native loader
rem     webview2\ui.html                   the page (read from disk at runtime,
rem                                        so it must ship alongside)
rem     adb_log_export.ini / cmds.ini      configuration
rem  Everything else stays out. dist\ should settle around 1.2 MB.
rem ============================================================================
set "DIST=%~dp0dist"
rem Rebuild in place: wipe first so stale files cannot skew the checks below
if exist "%DIST%" rmdir /s /q "%DIST%" >nul 2>&1
mkdir "%DIST%" >nul 2>&1
rem 2026-11-19: clean layout - exe at root, everything else under internal\,
rem runtime logs under log\. Matches what the reference tool ships and keeps
rem the folder readable for hand-off.
rem Backward compatible: Embed.cs probes internal\ first, then the old flat
rem layout, so an old package still runs.
mkdir "%DIST%\internal" >nul 2>&1
mkdir "%DIST%\log" >nul 2>&1

copy /y "%BIN%"                                     "%DIST%\adb_Tool.exe" >nul
copy /y "%~dp0Microsoft.Web.WebView2.Core.dll"      "%DIST%\internal\" >nul
copy /y "%~dp0Microsoft.Web.WebView2.WinForms.dll"  "%DIST%\internal\" >nul
copy /y "%~dp0WebView2Loader.dll"                   "%DIST%\internal\" >nul
copy /y "%~dp0adb_log_export.ini"                   "%DIST%\internal\" >nul
copy /y "%~dp0cmds.ini"                             "%DIST%\internal\" >nul
copy /y "%~dp0webview2\ui.html"                     "%DIST%\internal\" >nul
rem [2026-11-15] Window icon: TrySetCatIcon reads adb_Tool.ico next to the exe.
rem The /win32icon embedded resource only covers taskbar / Alt+Tab. Ship both.
copy /y "%~dp0adb_Tool.ico"                         "%DIST%\internal\" >nul
rem [2026-11-22] ffmpeg.exe and scrcpy are NOT bundled anymore.
rem
rem   Why: both are optional external tools that the app already locates at
rem   runtime through a 4-level fallback (ini value -> exe folder -> PATH ->
rem   well-known install dirs). See _cs/Ffmpeg.cs and _cs/Scrcpy.cs.
rem
rem   ffmpeg alone was 101 MB -- 89% of the whole package. Shipping it made
rem   every hand-off a 113 MB zip for a feature most users never touch.
rem   Users who want frame-grab recording point ini `ffmpeg=` at their own
rem   copy (or just install ffmpeg), and scrcpy is normally already installed
rem   on a tester machine anyway.
rem
rem   Result: dist drops from ~113 MB to ~12 MB.

rem [2026-11-22] Fastbot runtime bundle: 3 jars + native .so per ABI.
rem C# looks for it at <exe dir>\fastbot\ (GuiWeb.cs case "fbdeploy").
rem ~8.6 MB total. Shipped inside the package so users need no setup:
rem they just click "one-click deploy" and the files get pushed to the device.
if exist "%~dp0..\fastbot" (
    xcopy /e /i /y /q "%~dp0..\fastbot" "%DIST%\fastbot" >nul 2>&1
    echo Fastbot bundle: copied to dist\fastbot
) else (
    echo.
    echo [WARN] fastbot\ folder not found - the Fastbot tab will report
    echo        "not deployed" and one-click deploy will fail.
    echo        expected at: %~dp0..\fastbot
)

rem [2026-11-22] Built-in platform-tools (adb 35.0.0).
rem
rem   Why: some tester machines have no adb at all, and those that do often have
rem   a stale or conflicting copy. Shipping one lets the tool work out of the box.
rem
rem   IMPORTANT: this is a LAST-RESORT fallback, not the preferred source.
rem   Program.cs ResolveAdb() tries PATH -> exe dir -> ANDROID_HOME -> common
rem   install dirs -> and only then this one. Reason: the Windows adb server is
rem   a global singleton on port 5037; picking a different version than the one
rem   the user normally runs makes the two clients kill each other's server
rem   ("adb server version (41) doesn't match this client"), which shows up as
rem   random disconnects.
rem
rem   Only 3 files are needed. fastboot / mke2fs / etc1tool are deliberately
rem   left out (~5 MB saved). NOTICE.txt is kept for license compliance.
if exist "%~dp0..\platform-tools\adb.exe" (
    mkdir "%DIST%\platform-tools" >nul 2>&1
    copy /y "%~dp0..\platform-tools\adb.exe"           "%DIST%\platform-tools\" >nul
    copy /y "%~dp0..\platform-tools\AdbWinApi.dll"     "%DIST%\platform-tools\" >nul
    copy /y "%~dp0..\platform-tools\AdbWinUsbApi.dll"  "%DIST%\platform-tools\" >nul
    copy /y "%~dp0..\platform-tools\NOTICE.txt"        "%DIST%\platform-tools\" >nul
    echo Built-in adb: copied to dist\platform-tools
) else (
    echo.
    echo [WARN] platform-tools\adb.exe not found - the tool will only work on
    echo        machines that already have adb installed.
    echo        expected at: %~dp0..\platform-tools
)

rem Guard: if any required file is missing, say so loudly. Shipping a package
rem that "looks built" but will not start is worse than failing visibly here.
set "MISSING="
for %%F in ("%DIST%\adb_Tool.exe" "%DIST%\internal\Microsoft.Web.WebView2.Core.dll" "%DIST%\internal\Microsoft.Web.WebView2.WinForms.dll" "%DIST%\internal\WebView2Loader.dll" "%DIST%\internal\adb_log_export.ini" "%DIST%\internal\cmds.ini" "%DIST%\internal\ui.html" "%DIST%\internal\adb_Tool.ico") do (
    if not exist %%F set "MISSING=!MISSING! %%~nxf"
)
if defined MISSING (
    echo.
    echo [WARN] dist is missing:%MISSING%
    echo        check the webview2 subfolder and the ini files
)

rem Optional-tools hint (not a failure -- both are found at runtime or optional).
echo.
echo Optional tools (not bundled, located at runtime):
echo   ffmpeg  - only needed by the frame-grab recorder; set ini ffmpeg= if it is
echo             not on PATH. Without it, recording falls back with a clear error.
echo   scrcpy  - the external mirror window; if missing, the built-in frame-grab
echo             channel is used instead.

rem Size guard: a healthy dist is ~12 MB now (app ~3 MB + fastbot ~8.6 MB).
rem Warn past 30 MB -- that means ffmpeg slipped back in, or cache/logs leaked.
rem Accumulate byte sizes with plain cmd (no external tools, no quoting traps).
set /a "DTOTAL=0"
for /r "%DIST%" %%F in (*) do set /a "DTOTAL+=%%~zF"
if %DTOTAL% LEQ 0 set "DTOTAL=1"
set /a "DMB=DTOTAL/1048576"
set /a "DKb=(DTOTAL%%1048576)*100/1048576"
if %DMB% GEQ 30 (
    echo.
    echo [WARN] dist size looks wrong: %DMB% MB ^(expected ~12 MB^)
    echo        ffmpeg.exe or runtime cache/logs probably leaked into the package
)

echo.
echo Compile success: %BIN%
echo Package ready  : %DIST%   (%DMB%.%DKb% MB)
echo Double-click adb_Tool.exe to run.
%DOPAUSE%
exit /b 0
