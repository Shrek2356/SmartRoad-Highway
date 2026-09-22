@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."
title Setup portable env

set "NONINTERACTIVE=0"
set "INSTALL_MODE=%~1"
if /I "%INSTALL_MODE%"=="demo" set "NONINTERACTIVE=1"
if /I "%INSTALL_MODE%"=="full" set "NONINTERACTIVE=1"
if /I "%INSTALL_MODE%"=="demo" goto mode_ready
if /I "%INSTALL_MODE%"=="full" goto mode_ready

echo.
echo  请选择环境类型：
echo    [1] Demo / 前端展示 + 业务后台 + 检测桥 + RAG（不要求 CUDA）
echo    [2] Full / 离线或云端检测（要求 CUDA PyTorch）
echo.
set /p SETUP_CHOICE="  输入 1 / 2 后回车（直接回车=1）： "
if "%SETUP_CHOICE%"=="2" (
  set "INSTALL_MODE=full"
) else (
  set "INSTALL_MODE=demo"
)

:mode_ready

echo.
echo  ========================================
echo   创建便携 Python 环境：ZNT\env（%INSTALL_MODE%）
echo  ========================================
echo.

if exist "%~dp0..\env\Scripts\python.exe" (
  echo  [已存在] env\Scripts\python.exe
  goto install
)

where python >nul 2>&1
if errorlevel 1 (
  echo  [错误] 未找到 python，请先安装 Python 3.10+
  pause
  exit /b 1
)

echo  [1/3] python -m venv env ...
python -m venv "%~dp0..\env"
if errorlevel 1 (
  echo  [错误] 创建虚拟环境失败
  pause
  exit /b 1
)

:install
if /I "%INSTALL_MODE%"=="demo" goto install_dependencies

echo  [2/3] 检查 CUDA PyTorch...
"%~dp0..\env\Scripts\python.exe" -c "import torch, torchvision; assert torch.cuda.is_available(); print('torch', torch.__version__, 'cuda', torch.version.cuda, 'torchvision', torchvision.__version__)" >nul 2>&1
if errorlevel 1 (
  echo.
  echo  [需要人工选择] 未检测到可用的 CUDA PyTorch + torchvision。
  echo  请访问 https://pytorch.org/get-started/locally/ ，按本机显卡和驱动复制安装命令，
  echo  用以下 Python 执行后，再重新运行本脚本：
  echo    %~dp0..\env\Scripts\python.exe
  echo.
  echo  系统不会自动猜测 CUDA 版本，以免误装 CPU 版或不兼容版本。
  pause
  exit /b 1
)

:install_dependencies
if /I "%INSTALL_MODE%"=="demo" (
  set "REQ_FILE=detect-bridge.txt"
  echo  [2/3] Demo 模式跳过 CUDA 检查。
) else (
  set "REQ_FILE=detect-full.txt"
)

echo  [3/3] 安装 %REQ_FILE% ...
"%~dp0..\env\Scripts\python.exe" -m pip install -U pip
"%~dp0..\env\Scripts\python.exe" -m pip install -r "%~dp0%REQ_FILE%"
if errorlevel 1 (
  echo.
  echo  [错误] 依赖安装失败，请检查上方 pip 输出。
  if /I "%INSTALL_MODE%"=="full" echo  若缺少 torch，请先按 https://pytorch.org 安装 CUDA 版 PyTorch。
  pause
  exit /b 1
)

echo.
echo  %INSTALL_MODE% 环境安装完成。请继续：
echo    1. 双击根目录 部署助手.bat
if /I "%INSTALL_MODE%"=="full" echo    2. 按提示取得独立模型分卷，并在前端保存初始化路径
if /I "%INSTALL_MODE%"=="demo" echo    2. 启动时选择演示 demo；无需模型权重或 CUDA
echo    3. 无 ERROR 后双击根目录 start-platform.bat
echo.
if "%NONINTERACTIVE%"=="0" pause
endlocal
