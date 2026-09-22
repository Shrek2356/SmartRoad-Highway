@echo off
cd /d "%~dp0"
if exist "SmartRoad-Inspection.exe" (
  start "" "SmartRoad-Inspection.exe"
) else (
  echo Please extract the complete desktop package before starting.
  pause
)
