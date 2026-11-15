@echo off
rem 用系统自带编译器打一个"会挂住"的假 adb，只用于本地验证
"%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe" /nologo /target:exe /out:"%~dp0fake_adb.exe" "%~dp0fake_adb.cs"
if errorlevel 1 (
    echo [ERROR] fake adb build failed
    exit /b 1
)
echo ok
