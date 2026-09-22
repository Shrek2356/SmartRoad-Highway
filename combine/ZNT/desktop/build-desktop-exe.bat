@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

set "BUILD_PY=%LocalAppData%\Programs\Python\Python312\python.exe"
if not exist "%BUILD_PY%" set "BUILD_PY=python"

if not exist ".venv\Scripts\python.exe" (
  echo [1/4] 创建独立构建环境...
  "%BUILD_PY%" -m venv .venv
  if errorlevel 1 goto failed
)

echo [2/4] 安装桌面窗口与打包依赖...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements-desktop.txt
if errorlevel 1 goto failed

echo [3/4] 生成 Windows EXE...
".venv\Scripts\pyinstaller.exe" --noconfirm --clean --onefile --windowed --name "SmartRoad-Inspection" --icon "assets\sitesafe.ico" --version-file "version_info.txt" --distpath "..\desktop-dist" --workpath "build" --specpath "." --hidden-import webview.platforms.edgechromium --exclude-module PyQt5 --exclude-module PyQt6 --exclude-module PySide2 --exclude-module PySide6 "desktop_app.py"
if errorlevel 1 goto failed

echo [4/4] 完成：desktop-dist\SmartRoad-Inspection.exe
pause
exit /b 0

:failed
echo [错误] 桌面 EXE 构建失败。
pause
exit /b 1
