@echo off
setlocal
cd /d "%~dp0"
title Veilmind
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 start.py %*
  goto :end
)
where python >nul 2>nul
if %errorlevel%==0 (
  python start.py %*
  goto :end
)
echo.
echo Python 3.10 or newer is not installed.
echo Opening the download page. During setup, tick "Add python.exe to PATH", then double-click this file again.
start "" https://www.python.org/downloads/
:end
echo.
pause
