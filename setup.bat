@echo off
chcp 65001 >nul
echo ========================================
echo   YKT Browser - 环境安装
echo ========================================
echo.

echo [1/2] 安装 Python 依赖...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [错误] 依赖安装失败！请确认已安装 Python 和 pip。
    pause
    exit /b 1
)

echo.
echo [2/2] 安装 Playwright 浏览器 (Chromium)...
python -m playwright install chromium
if %errorlevel% neq 0 (
    echo [错误] Playwright 浏览器安装失败！
    pause
    exit /b 1
)

echo.
echo ========================================
echo   安装完成！运行 run.bat 启动程序。
echo ========================================
pause
