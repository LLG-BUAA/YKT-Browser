@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"

set "PY_CMD="
where python >nul 2>nul && set "PY_CMD=python"
if not defined PY_CMD where py >nul 2>nul && set "PY_CMD=py -3"

if not defined PY_CMD (
    echo [错误] 未找到 Python。
    echo 请先安装 Python 3.10+，并勾选 "Add Python to PATH"。
    pause
    exit /b 1
)

%PY_CMD% main.py
set "EXIT_CODE=%errorlevel%"

if %EXIT_CODE% neq 0 (
    echo.
    echo [错误] 程序退出，返回码 %EXIT_CODE%。
    echo 如果是首次运行，请先执行 setup.bat 安装依赖和 Chromium。
    pause
)

exit /b %EXIT_CODE%
