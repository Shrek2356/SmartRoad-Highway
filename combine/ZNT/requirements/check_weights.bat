@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."
title Check runtime and model paths

set "PY="
if exist "%~dp0..\env\Scripts\python.exe" set "PY=%~dp0..\env\Scripts\python.exe"
if not defined PY if exist "%~dp0..\python-runtime\python.exe" set "PY=%~dp0..\python-runtime\python.exe"
if not defined PY if exist "%~dp0..\..\env\python.exe" set "PY=%~dp0..\..\env\python.exe"
if not defined PY (
  where python >nul 2>&1
  if not errorlevel 1 set "PY=python"
)
if not defined PY (
  echo  [错误] 未找到 Python，请先运行 setup_env.bat。
  pause
  exit /b 1
)

echo.
echo  检查哪个模式？
echo    [1] Demo（无需模型）
echo    [2] Offline（Qwen + YOLO + SAM3）
echo    [3] Cloud（云端 VLM + YOLO + SAM3）
echo.
set /p CHOICE="  输入 1 / 2 / 3 后回车（直接回车=2）： "
if "%CHOICE%"=="1" set "CHECK_MODE=demo"
if "%CHOICE%"=="3" set "CHECK_MODE=cloud"
if not defined CHECK_MODE set "CHECK_MODE=offline"

"%PY%" "%~dp0preflight_check.py" --mode %CHECK_MODE% --save
set "RESULT=%ERRORLEVEL%"
echo.
if "%RESULT%"=="0" (
  echo  检查通过。
) else (
  echo  存在阻断项。请按上方真实配置路径修复；代码包不自带模型权重。
)
echo.
pause
exit /b %RESULT%
