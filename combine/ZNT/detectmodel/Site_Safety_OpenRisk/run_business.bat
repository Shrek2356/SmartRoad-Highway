@echo off
set "PY=%~1"
set "DATA_DIR=%~2"
if not defined PY set "PY=python"
if not defined DATA_DIR set "DATA_DIR=results\seven_examples_release\frontend"
"%PY%" app_server.py --host 127.0.0.1 --port 8800 --data-dir "%DATA_DIR%"
