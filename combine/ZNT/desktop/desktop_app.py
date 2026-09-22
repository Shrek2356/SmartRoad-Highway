"""SmartRoad-Inspection Windows desktop shell.

This process owns the embedded frontend server and starts the existing business
backend and detection bridge. Model weights remain external and configurable.
"""

from __future__ import annotations

import argparse
import ctypes
import html
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import IO, Any
from urllib.parse import unquote, urlsplit

import webview
from gateway import GatewayMixin
from environment_check import check_python, assert_data_services_stopped
from export_service import save_export
from workspace_archive import WorkspaceMaintenance


APP_NAME = "SmartRoad-Inspection"
APP_TITLE = "路安智巡 · SmartRoad-Inspection"
DEFAULT_CONFIG = {
    "profile": "demo",
    "backend_python": "python-runtime/python.exe",
    "business_port": 8800,
    "bridge_port": 8810,
    "frontend_port": 5173,
    "window_width": 1440,
    "window_height": 900,
    "confirm_close": True,
}
PROFILE_CONFIG = {
    "demo": "configs/road_demo.yaml",
    "offline": "configs/road_offline.yaml",
    "standard": "configs/road_standard.yaml",
}
ERROR_ALREADY_EXISTS = 183


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        for candidate in (exe_dir, exe_dir.parent):
            if (candidate / "pc-admin" / "dist" / "index.html").is_file():
                return candidate
        return exe_dir
    return Path(__file__).resolve().parent.parent


ROOT = app_root()
RUNTIME_DIR = ROOT / "runtime" / "desktop"
LOG_DIR = RUNTIME_DIR / "logs"
CONFIG_PATH = ROOT / "desktop-settings.json"


def load_config() -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.is_file():
        try:
            user_config = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
            if isinstance(user_config, dict):
                config.update(user_config)
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"桌面配置文件无法读取：{exc}") from exc
    return config


def resolve_local_path(value: str) -> Path:
    path = Path(os.path.expandvars(value)).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def port_is_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def http_ready(url: str, timeout: float = 1.5, *, service: str = "") -> bool:
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=timeout) as response:
            if response.status != 200:
                return False
            if service:
                data = json.load(response)
                return isinstance(data, dict) and data.get("ok") is True and data.get("service") == service
            return True
    except Exception:
        return False


class SpaHandler(GatewayMixin, SimpleHTTPRequestHandler):
    server_version = "SmartRoadDesktop/1.4"
    MIME_OVERRIDES = {
        ".css": "text/css; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".mjs": "text/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".svg": "image/svg+xml",
        ".wasm": "application/wasm",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
    }

    def __init__(self, *args: Any, directory: str, proxy_routes=None, **kwargs: Any) -> None:
        self.proxy_routes = proxy_routes or {}
        super().__init__(*args, directory=directory, **kwargs)

    def send_head(self):
        requested = unquote(urlsplit(self.path).path).lstrip("/")
        candidate = Path(self.directory, requested)
        if requested == "vite.svg" and not candidate.exists():
            fallback = Path(self.directory, "icons.svg")
            if fallback.exists():
                self.path = "/icons.svg"
                return super().send_head()
        if requested and not candidate.exists() and "." not in Path(requested).name:
            self.path = "/index.html"
        return super().send_head()

    def guess_type(self, path: str) -> str:
        override = self.MIME_OVERRIDES.get(Path(path).suffix.lower())
        return override or super().guess_type(path)

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        super().end_headers()

    def log_message(self, _format: str, *_args: Any) -> None:
        return


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


@dataclass
class ManagedProcess:
    name: str
    process: subprocess.Popen
    log_handle: IO[bytes]


class DesktopRuntime:
    def __init__(self, config: dict[str, Any], profile_override: str | None = None) -> None:
        self.config = config
        self.profile = profile_override or str(config.get("profile", "demo"))
        if self.profile not in PROFILE_CONFIG:
            raise RuntimeError(f"不支持的运行档位：{self.profile}")
        self.frontend_port = int(config["frontend_port"])
        self.business_port = int(config["business_port"])
        self.bridge_port = int(config["bridge_port"])
        self.python = resolve_local_path(str(config["backend_python"]))
        self.detect_root = ROOT / "detectmodel" / "Site_Safety_OpenRisk"
        self.frontend_root = ROOT / "pc-admin" / "dist"
        self.server: ReusableThreadingHTTPServer | None = None
        self.server_thread: threading.Thread | None = None
        self.processes: list[ManagedProcess] = []
        self.started_frontend = False
        self._stopped = False
        self._lifecycle_lock = threading.RLock()
        self._maintenance_lock = threading.Lock()
        self._export_lock = threading.Lock()
        self.workspace = WorkspaceMaintenance(ROOT)

    def validate(self, *, check_environment: bool = True) -> None:
        ports = [self.frontend_port, self.business_port, self.bridge_port]
        if len(set(ports)) != 3 or any(not 1024 <= p <= 65535 for p in ports):
            raise RuntimeError("前端、业务与检测桥端口须互不相同且在1024–65535之间")
        missing = []
        for path in (
            self.python,
            self.frontend_root / "index.html",
            self.detect_root / "app_server.py",
            self.detect_root / "detect_bridge.py",
            self.detect_root / PROFILE_CONFIG[self.profile],
        ):
            if not path.is_file():
                missing.append(str(path))
        if missing:
            raise RuntimeError("桌面版文件不完整：\n" + "\n".join(missing))
        if check_environment:
            check_python(self.python)

    def _spawn(self, name: str, args: list[str], cwd: Path) -> None:
        with self._lifecycle_lock:
            if self._stopped:
                raise RuntimeError("桌面已关闭，取消后续服务启动")
            self._spawn_owned(name, args, cwd)

    def _spawn_owned(self, name: str, args: list[str], cwd: Path) -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d")
        log_handle = open(LOG_DIR / f"{name}-{stamp}.log", "ab", buffering=0)
        creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        env = dict(os.environ)
        env["ZNT_BUSINESS_API"] = f"http://127.0.0.1:{self.business_port}"
        env["ZNT_DETECT_API"] = f"http://127.0.0.1:{self.bridge_port}"
        env["NO_PROXY"] = ",".join(filter(None, [env.get("NO_PROXY", env.get("no_proxy", "")), "127.0.0.1", "localhost", "::1"]))
        env["no_proxy"] = env["NO_PROXY"]
        process = subprocess.Popen(
            args,
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
            env=env,
        )
        self.processes.append(ManagedProcess(name, process, log_handle))

    def start_frontend(self) -> None:
        with self._lifecycle_lock:
            if self._stopped:
                raise RuntimeError("桌面启动已取消")
            self._start_frontend_owned()

    def _start_frontend_owned(self) -> None:
        if port_is_open(self.frontend_port):
            raise RuntimeError(f"前端端口 {self.frontend_port} 已被占用。请关闭旧平台，或修改 desktop-settings.json 端口。")

        def handler(*args: Any, **kwargs: Any):
            return SpaHandler(*args, directory=str(self.frontend_root), proxy_routes={
                "/business-api": self.business_port, "/detect-api": self.bridge_port,
            }, **kwargs)

        self.server = ReusableThreadingHTTPServer(
            ("127.0.0.1", self.frontend_port), handler
        )
        self.server_thread = threading.Thread(
            target=self.server.serve_forever, name="frontend-http", daemon=True
        )
        self.server_thread.start()
        self.started_frontend = True

    def start_services(self) -> None:
        self.validate()
        self.workspace.run(self._assert_workspace_offline)
        self.start_frontend()

        if not port_is_open(self.business_port):
            self._spawn(
                "business",
                [
                    str(self.python),
                    "app_server.py",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(self.business_port),
                    "--data-dir",
                    "outputs/road_import/frontend",
                ],
                self.detect_root,
            )

        if not port_is_open(self.bridge_port):
            self._spawn(
                "detect-bridge",
                [
                    str(self.python),
                    "detect_bridge.py",
                    "--config",
                    PROFILE_CONFIG[self.profile],
                    "--port",
                    str(self.bridge_port),
                ],
                self.detect_root,
            )

        checks = {
            "PC前端": (f"http://127.0.0.1:{self.frontend_port}/desktop-api/health", "sitesafe-desktop"),
            "业务后台": (f"http://127.0.0.1:{self.frontend_port}/business-api/api/health", "znt-business-api"),
            "检测桥": (f"http://127.0.0.1:{self.frontend_port}/detect-api/api/detect/health", "site-OpenRisk-detect-bridge"),
        }
        deadline = time.monotonic() + 90
        pending = dict(checks)
        while pending and time.monotonic() < deadline:
            if self._stopped:
                raise RuntimeError("桌面启动已取消")
            for name, (url, service) in list(pending.items()):
                if http_ready(url, service=service):
                    pending.pop(name)
            if pending:
                time.sleep(0.4)
        if pending:
            names = "、".join(pending)
            raise RuntimeError(f"以下服务未能启动：{names}\n请查看 {LOG_DIR}")

    def stop(self) -> None:
        with self._lifecycle_lock:
            if self._stopped:
                return
            self._stopped = True
        # The owned process tree includes models launched by this bridge. Never call
        # a global model-stop API: a pre-existing model may be used by another app.

        if self.server and self.started_frontend:
            self.server.stopping = True
            self.server.shutdown()
            self.server.server_close()

        for item in reversed(self.processes):
            if item.process.poll() is None:
                subprocess.run(
                    ["taskkill", "/PID", str(item.process.pid), "/T", "/F"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    check=False,
                )
            item.log_handle.close()

    def get_desktop_settings(self) -> dict:
        saved = load_config()
        return {**saved, "app_root": str(ROOT), "restart_required": saved != self.config}

    def open_support_folder(self, kind: str) -> dict:
        folders = {"logs": LOG_DIR, "application": ROOT}
        if kind not in folders:
            raise ValueError("只能打开应用目录或本平台日志目录")
        target = folders[kind]
        target.mkdir(parents=True, exist_ok=True)
        os.startfile(str(target))
        return {"opened": True}

    def save_desktop_settings(self, values: dict) -> dict:
        allowed = {"profile", "backend_python", "business_port", "bridge_port", "frontend_port"}
        updated = {**load_config(), **{k: v for k, v in values.items() if k in allowed}}
        candidate = DesktopRuntime(updated)
        candidate.validate()
        temporary = CONFIG_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(CONFIG_PATH)
        return {"ok": True, "restart_required": True}

    def save_export(self, filename: str, encoded: str) -> dict:
        def choose(name, suffix):
            selected = webview.windows[0].create_file_dialog(
                webview.FileDialog.SAVE, save_filename=name,
                file_types=(f"导出文件 (*{suffix})",))
            return selected[0] if selected else None
        if not self._export_lock.acquire(blocking=False): raise ValueError('已有文件保存窗口，请先完成或取消上一次保存')
        try: return save_export(filename, encoded, choose)
        finally: self._export_lock.release()

    def _assert_workspace_offline(self):
        # Also check standard ports when this copy uses custom ports. Never stop
        # a pre-existing service just to perform maintenance.
        for port in {self.business_port, self.bridge_port, 8900, 8910}:
            if port_is_open(port):
                raise RuntimeError('备份/恢复未执行：业务或检测服务仍在运行。请关闭其他平台后台后重新安排维护')
        assert_data_services_stopped(self.python, self.detect_root)

    def _require_workspace_admin(self, token: str):
        if not isinstance(token, str) or not token or len(token) > 4096:
            raise ValueError('请先使用本机管理员账号登录')
        request = urllib.request.Request(f'http://127.0.0.1:{self.business_port}/api/whoami',
                                         headers={'Authorization': f'Bearer {token}'})
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(request, timeout=5) as response:
                if json.load(response).get('role') != 'admin': raise ValueError()
        except Exception as exc:
            raise ValueError('完整工作空间维护需要本机业务服务的管理员权限') from exc

    def workspace_status(self, token: str):
        self._require_workspace_admin(token)
        return self.workspace.status()

    def schedule_workspace(self, action: str, token: str):
        self._require_workspace_admin(token)
        if action not in {'backup', 'restore'}: raise ValueError('无效维护操作')
        with self._maintenance_lock:
            window = webview.windows[0]
            selected = window.create_file_dialog(
                webview.FileDialog.SAVE if action == 'backup' else webview.FileDialog.OPEN,
                save_filename='SmartRoad-工作空间-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.zip',
                file_types=('SmartRoad 工作空间 (*.zip)',))
            if not selected: return {**self.workspace.status(), 'cancelled': True}
            if action == 'restore' and not window.create_confirmation_dialog(
                '确认安排工作空间恢复',
                '仅恢复你信任的本软件备份。下次启动将替换当前业务库、规范、检测历史和用户模型设置，'
                '先保留原工作空间以便回滚。此操作不会现在中断任务；模型权重和云端密钥不会导入。继续吗？'):
                return {**self.workspace.status(), 'cancelled': True}
            return self.workspace.schedule(action, Path(selected[0]))

    def cancel_workspace(self, token: str):
        self._require_workspace_admin(token)
        with self._maintenance_lock:
            return self.workspace.cancel()


LOADING_HTML = """
<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<style>
html,body{height:100%;margin:0;background:#091b28;color:#e9f7ff;font-family:"Microsoft YaHei",sans-serif}
body{display:grid;place-items:center;background-image:radial-gradient(circle at 50% 35%,#123d55 0,#091b28 48%,#06131d 100%)}
.panel{text-align:center}.mark{width:82px;height:82px;border:2px solid #43d9d0;border-radius:24px;margin:auto;display:grid;place-items:center;box-shadow:0 0 38px #2dcabd55;font-size:38px}
h1{font-size:28px;letter-spacing:2px;margin:22px 0 8px}.sub{color:#83aabe;font-size:15px}.bar{width:360px;height:4px;background:#17364a;border-radius:9px;margin:28px auto;overflow:hidden}
.bar:after{content:"";display:block;height:100%;width:45%;background:linear-gradient(90deg,#31d9e7,#52dfa7);animation:run 1.25s ease-in-out infinite}
@keyframes run{0%{transform:translateX(-110%)}100%{transform:translateX(330%)}}
</style></head><body><div class="panel"><div class="mark">🛡</div><h1>SmartRoad-Inspection</h1>
<div class="sub">正在连接工作空间、业务后台与检测桥…</div><div class="bar"></div>
<div class="sub">模型是否自动启动取决于你的配置；首次打开可能需要稍候。</div></div></body></html>
"""


def error_html(message: str) -> str:
    return f"""
<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><style>
body{{margin:0;padding:64px;background:#101923;color:#e7edf3;font-family:'Microsoft YaHei',sans-serif}}
.box{{max-width:900px;margin:auto;padding:32px;border:1px solid #8d4550;border-radius:16px;background:#1a2530}}
h1{{color:#ff8794}}pre{{white-space:pre-wrap;line-height:1.7;color:#cbd7e0}}
</style></head><body><div class="box"><h1>桌面平台启动失败</h1>
<p>你的项目文件仍在。请按下列步骤检查，再关闭并重新打开软件。</p>
<ol style="line-height:2;color:#bdcec9"><li>提示文件缺失：确认完整解压了交付包，没有只复制 EXE。</li><li>提示依赖或 Python 问题：检查 desktop-settings.json 中的后台环境；演示可使用随包 Python。</li><li>提示端口冲突：关闭重复的平台窗口，或在桌面配置中选择不同端口。</li></ol>
<details><summary style="cursor:pointer;padding:16px 0">展开具体错误信息</summary><pre>{html.escape(message)}</pre></details>
<p><button onclick="openFolder('logs')">打开运行日志文件夹</button> <button onclick="openFolder('application')">打开软件与配置文件夹</button></p>
<p id="support-status" aria-live="polite"></p></div>
<style>button{{padding:12px 20px;border:1px solid #76958b;border-radius:8px;background:#26403e;color:#f0f7f4;cursor:pointer}}button:hover{{background:#36534f}}button:focus-visible{{outline:2px solid #edb69c;outline-offset:3px}}</style>
<script>async function openFolder(kind){{try{{if(!window.pywebview?.api)throw new Error('窗口接口尚未就绪，请稍后再试');await window.pywebview.api.open_support_folder(kind);document.getElementById('support-status').textContent='文件夹已打开。请勿在分享日志时附带密钥或敏感现场信息。'}}catch(e){{document.getElementById('support-status').textContent=e.message||'打开失败，请从软件所在目录查看配置与日志。'}}}}</script></body></html>
"""


def acquire_single_instance() -> Any:
    if os.name != "nt":
        return None
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.CreateMutexW(None, False, "Local\\SmartRoadInspectionDesktop")
    if not handle or kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        ctypes.windll.user32.MessageBoxW(
            None, "SmartRoad-Inspection 已经在运行。", APP_TITLE, 0x40
        )
        raise SystemExit(0)
    return handle


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=not getattr(sys, "frozen", False))
    parser.add_argument("--profile", choices=sorted(PROFILE_CONFIG), default=None)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--headless-smoke-seconds", type=int, choices=range(1, 121), default=0, help=argparse.SUPPRESS)
    parser.add_argument(
        "--smoke-test-seconds",
        type=float,
        default=0,
        help=argparse.SUPPRESS,
    )
    return parser.parse_args()


def main() -> int:
    mutex = acquire_single_instance()
    args = parse_args()
    try:
        config = load_config()
        runtime = DesktopRuntime(config, args.profile)
    except Exception as exc:
        ctypes.windll.user32.MessageBoxW(None, str(exc), APP_TITLE, 0x10)
        return 1

    # Installer QA runs the actual frozen executable and its services without opening a window.
    if args.headless_smoke_seconds:
        record = {"mode": "headless-services", "native_window_tested": False, "ok": False}
        try:
            runtime.start_services()
            time.sleep(args.headless_smoke_seconds)
            record["ok"] = True
        except Exception as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            runtime.stop()
            RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
            (RUNTIME_DIR / "headless-smoke.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            if mutex and os.name == "nt":
                ctypes.windll.kernel32.CloseHandle(mutex)
        return 0 if record["ok"] else 1

    # Native save_export is used by all platform exports. Permit other standard
    # downloads as a fallback; WebView2 still presents its own Save dialog.
    webview.settings['ALLOW_DOWNLOADS'] = True
    window = webview.create_window(
        APP_TITLE,
        html=LOADING_HTML,
        width=int(config["window_width"]),
        height=int(config["window_height"]),
        min_size=(1100, 720),
        background_color="#091b28",
        confirm_close=bool(config.get("confirm_close", True))
        and args.smoke_test_seconds <= 0,
        js_api=type("DesktopSettingsAPI", (), {
            "get_desktop_settings": lambda _self: runtime.get_desktop_settings(),
            "save_desktop_settings": lambda _self, values: runtime.save_desktop_settings(values),
            "open_support_folder": lambda _self, kind: runtime.open_support_folder(kind),
            "save_export": lambda _self, filename, encoded: runtime.save_export(filename, encoded),
            "workspace_status": lambda _self, token: runtime.workspace_status(token),
            "schedule_workspace": lambda _self, action, token: runtime.schedule_workspace(action, token),
            "cancel_workspace": lambda _self, token: runtime.cancel_workspace(token),
            "choose_backend_python": lambda _self: (webview.windows[0].create_file_dialog(
                webview.FileDialog.OPEN, allow_multiple=False, file_types=("Python (*.exe)",)
            ) or [""])[0],
        })(),
    )

    def startup() -> None:
        try:
            runtime.start_services()
            window.load_url(f"http://127.0.0.1:{runtime.frontend_port}/login")
            if args.smoke_test_seconds > 0:
                timer = threading.Timer(args.smoke_test_seconds, window.destroy)
                timer.daemon = True
                timer.start()
            if args.debug:
                time.sleep(3)
                state = window.evaluate_js(
                    "JSON.stringify({readyState:document.readyState,title:document.title,"
                    "bodyText:document.body.innerText.slice(0,500),"
                    "appHtml:document.querySelector('#app')?.innerHTML.slice(0,500),"
                    "url:location.href})"
                )
                print(f"DESKTOP_WEB_STATE={state}", flush=True)
        except Exception as exc:
            if not runtime._stopped:
                runtime.stop()
                window.load_html(error_html(str(exc)))

    try:
        webview.start(startup, gui="edgechromium", debug=args.debug,
                      private_mode=False, storage_path=str(RUNTIME_DIR / "webview-profile"))
    finally:
        runtime.stop()
        if mutex and os.name == "nt":
            ctypes.windll.kernel32.CloseHandle(mutex)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
