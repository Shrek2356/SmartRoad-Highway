@echo off
chcp 65001 >nul
cd /d "%~dp0"
REM 用法: run_bridge.bat <python.exe> <config> <port>
set "PY=%~1"
set "CFG=%~2"
set "PORT=%~3"
if "%PY%"=="" set "PY=python"
if "%CFG%"=="" set "CFG=configs\default.yaml"
if "%PORT%"=="" set "PORT=8810"

echo  Python: %PY%
echo  Config: %CFG%
echo  Port:   %PORT%
echo.

"%PY%" -c "import fastapi,uvicorn,dotenv,psutil,yaml,pydantic,PIL,numpy,sklearn,pypdf,docx,multipart,httpx" 2>nul
if errorlevel 1 (
  echo  [安装] 桥接依赖...
  "%PY%" -m pip install -r "%~dp0..\..\requirements\detect-bridge.txt"
)

"%PY%" detect_bridge.py --config "%CFG%" --port %PORT%
pause
