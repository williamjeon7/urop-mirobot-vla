@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_local.ps1" %*
set "rgbExit=%errorlevel%"
if not "%rgbExit%"=="0" pause
exit /b %rgbExit%
