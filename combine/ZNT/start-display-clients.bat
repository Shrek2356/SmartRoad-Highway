@echo off
chcp 65001 >nul
title 启动安全大屏与移动端
cd /d "%~dp0"
if exist "%~dp0node-runtime\node.exe" set "PATH=%~dp0node-runtime;%PATH%"
set "PID_DIR=%~dp0runtime\pids"
if not exist "%PID_DIR%" mkdir "%PID_DIR%" >nul 2>&1
set "STARTED_BIG=0"
set "STARTED_MOBILE=0"

for %%d in (big-screen mobile) do (
  if not exist "%~dp0%%d\node_modules\" (
    echo 正在安装 %%d 前端依赖...
    pushd "%~dp0%%d"
    call npm install
    if errorlevel 1 (
      echo [错误] %%d 前端依赖不完整；标准展示包应已包含全部依赖与便携 Node.js。
      popd
      pause
      exit /b 1
    )
    popd
  )
)

netstat -ano | findstr ":5174" | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
  set "STARTED_BIG=1"
  start "big-screen-5174" /D "%~dp0big-screen" cmd.exe /c "npm run dev -- --force"
)
netstat -ano | findstr ":5175" | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
  set "STARTED_MOBILE=1"
  start "mobile-5175" /D "%~dp0mobile" cmd.exe /c "npm run dev -- --force"
)

timeout /t 3 /nobreak >nul
if "%STARTED_BIG%"=="1" powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$p=Get-NetTCPConnection -LocalPort 5174 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess; if($p){Set-Content -LiteralPath '%PID_DIR%\big-screen-5174.pid' -Value $p -Encoding ascii}"
if "%STARTED_MOBILE%"=="1" powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$p=Get-NetTCPConnection -LocalPort 5175 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess; if($p){Set-Content -LiteralPath '%PID_DIR%\mobile-5175.pid' -Value $p -Encoding ascii}"
start "" "http://localhost:5174"
start "" "http://localhost:5175"
echo 大屏和移动端已启动；两者默认连接 http://127.0.0.1:8800。
pause
