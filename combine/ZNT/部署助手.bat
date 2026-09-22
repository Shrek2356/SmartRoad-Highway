@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title 路安智巡 新设备模型部署引导

rem The bootstrap Python only reads desktop-settings and starts the selected checker.
set "GUIDE_PY=%~dp0python-runtime\python.exe"
if not exist "%GUIDE_PY%" set "GUIDE_PY=%~dp0env\Scripts\python.exe"
if not exist "%GUIDE_PY%" set "GUIDE_PY=%~dp0env\python.exe"
if not exist "%GUIDE_PY%" set "GUIDE_PY=python"

echo.
echo  新设备可先打开 SmartRoad-Inspection.exe 进行道路模拟联调，无需下载模型。
echo  本助手按桌面设置中的 Python 检查，不下载文件、不安装依赖、不启动模型。
echo  新建官方 SAM3 环境请按 requirements\DEPLOYMENT_GUIDE.md 使用 Python 3.12。
echo.
echo  [1] 演示 Demo（默认，无 GPU 和权重要求）
echo  [2] 本地离线 Qwen + YOLO + SAM3
echo  [3] 云端视觉 API + 本地 YOLO / SAM3
set "GUIDE_MODE=1"
set /p GUIDE_MODE="输入 1 / 2 / 3（回车默认 1）："
set "GUIDE_PROFILE=demo"
if "%GUIDE_MODE%"=="2" set "GUIDE_PROFILE=offline"
if "%GUIDE_MODE%"=="3" set "GUIDE_PROFILE=cloud"

"%GUIDE_PY%" -I -X utf8 "%~dp0requirements\preflight_check.py" --mode %GUIDE_PROFILE% --use-desktop-python --save
set "GUIDE_RESULT=%ERRORLEVEL%"
echo.
echo  下一步：前端「模型与规则 - 新设备部署」查看逐步引导。
echo  Python 在「系统设置 - 桌面与连接」选择；模型在「模型部件与运行时」选择。
echo  检查通过不等于模型已运行；配置完成后仍需提交一张真实图片验收。
pause
exit /b %GUIDE_RESULT%
