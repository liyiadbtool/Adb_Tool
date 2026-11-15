@echo off
rem ============================================================================
rem  release.bat - one click: build + package (double-click friendly)
rem
rem  Produces the two deliverables every time we finish a change:
rem    1) adb_log_gui\dist\         local runnable package (with ffmpeg)
rem    2) release\*.zip             ready-to-share archives (full + minimal)
rem
rem  Equivalent to: python release.py
rem ============================================================================
setlocal EnableExtensions
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] python not found in PATH.
    echo         Use adb_log_gui\build_gui.bat + make_min.bat manually instead.
    pause
    exit /b 1
)

python "%~dp0release.py" %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
    echo.
    echo [ERROR] release.py failed with code %RC%
    pause
    exit /b %RC%
)
pause
exit /b 0
