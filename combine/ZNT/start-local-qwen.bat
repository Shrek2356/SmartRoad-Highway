@echo off
chcp 65001 >nul
title 本地 Qwen3-VL 服务 8080
set "PY=%~dp0env\Scripts\python.exe"
if not exist "%PY%" set "PY=%~dp0env\python.exe"
if not exist "%PY%" set "PY=%~dp0python-runtime\python.exe"
if not exist "%PY%" set "PY=%~dp0..\env\python.exe"
if not exist "%PY%" set "PY=python"
REM 模型与 mmproj 路径从网页设置保存的 runtime_settings.json 读取。
"%PY%" "%~dp0detectmodel\Site_Safety_OpenRisk\scripts\run_local_qwen_server.py"
pause
