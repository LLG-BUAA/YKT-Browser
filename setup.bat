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

echo ========================================
echo   YKT Browser - 环境安装
echo ========================================
echo.

echo [1/2] 安装 Python 依赖...
%PY_CMD% -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [错误] 依赖安装失败，请确认 Python 和 pip 可用。
    pause
    exit /b 1
)

echo.
echo [2/2] 安装 Playwright 浏览器（Chromium）...
%PY_CMD% -m playwright install chromium
if %errorlevel% neq 0 (
    echo [错误] Playwright 浏览器安装失败。
    pause
    exit /b 1
)

echo.
echo ========================================
echo   安装完成！运行 run.bat 即可启动程序。
echo ========================================
pause
