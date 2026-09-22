"""Probe the chosen interpreter, not the desktop build interpreter's packages."""
import json
import os
import subprocess
from pathlib import Path

BASE_MODULES = ['fastapi', 'uvicorn', 'yaml', 'httpx', 'sqlite3', 'psutil', 'dotenv',
                'python_multipart', 'pydantic', 'PIL', 'numpy', 'sklearn', 'pypdf', 'docx']
PROBE = r'''
import importlib, json, struct, sys
missing = []
for name in json.loads(sys.argv[1]):
    try: importlib.import_module(name)
    except Exception: missing.append(name)
print('SITESAFE_ENV=' + json.dumps({'version':list(sys.version_info[:3]), 'bits':struct.calcsize('P')*8, 'missing':missing}))
'''


def check_python(python: Path, *, runner=subprocess.run) -> dict:
    # Never let the Codex/dev PYTHONPATH accidentally make an incomplete target pass.
    env = {k: v for k, v in os.environ.items() if k.upper() not in {'PYTHONPATH', 'PYTHONHOME'}}
    try:
        completed = runner([str(python), '-B', '-I', '-c', PROBE, json.dumps(BASE_MODULES)],
                           capture_output=True, text=True, encoding='utf-8', errors='replace',
                           timeout=30, env=env,
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('所选 Python 无法运行或环境检查超时（30秒），请使用随包基础环境或 requirements 创建的完整环境') from exc
    try:
        line = next(line for line in completed.stdout.splitlines() if line.startswith('SITESAFE_ENV='))
        result = json.loads(line[len('SITESAFE_ENV='):])
        if completed.returncode or result['version'][:2] < [3, 10] or result['bits'] != 64:
            raise ValueError()
    except (StopIteration, ValueError, KeyError, TypeError) as exc:
        raise ValueError('所选程序不是可用的 64 位 Python 3.10+；推荐 Python 3.12，未保存配置') from exc
    if result['missing']:
        raise ValueError('Python 缺少或无法加载基础依赖：' + ', '.join(result['missing']) + '。请运行 requirements/setup_env.bat；原配置未修改')
    return result


def assert_data_services_stopped(python: Path, backend: Path, *, runner=subprocess.run):
    script = r'''
import json, os, psutil, sys
base = os.path.normcase(os.path.realpath(sys.argv[1]))
scripts = ['app_server.py', 'detect_bridge.py', 'stream_bridge_worker.py', 'serve_demo.py']
busy = []
for process in psutil.process_iter(['pid','cmdline','cwd']):
    args = process.info.get('cmdline') or []
    if not any(os.path.basename(arg).lower() in scripts for arg in args): continue
    cwd = process.info.get('cwd')
    if (cwd and os.path.normcase(os.path.realpath(cwd)) == base) or any(os.path.normcase(os.path.realpath(arg)) == os.path.join(base,name) for arg in args for name in scripts):
        busy.append(process.pid)
print('SITESAFE_BUSY=' + json.dumps(busy))
'''
    env = {k:v for k,v in os.environ.items() if k.upper() not in {'PYTHONHOME','PYTHONPATH'}}
    try:
        result = runner([str(python),'-B','-I','-c',script,str(backend)],capture_output=True,text=True,
                        encoding='utf-8',errors='replace',env=env,timeout=15,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        line = next(line for line in result.stdout.splitlines() if line.startswith('SITESAFE_BUSY='))
        if result.returncode or json.loads(line[len('SITESAFE_BUSY='):]): raise ValueError()
    except Exception as exc:
        raise RuntimeError('无法确认业务目录已停止写入，未执行备份/恢复。请关闭使用此目录的后台程序后重试') from exc
