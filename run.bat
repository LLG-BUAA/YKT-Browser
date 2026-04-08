@echo off
chcp 65001 >nul
python main.py
if %errorlevel% neq 0 pause
