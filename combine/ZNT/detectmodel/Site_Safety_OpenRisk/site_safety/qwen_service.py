"""Lifecycle control for the local llama-server used by the desktop demo."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
from urllib.parse import urlparse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Mapping


_PICKER_LOCK = threading.Lock()


class QwenServiceManager:
    """Start and stop only the llama-server process created by this manager."""

    def __init__(self, runtime_dir: str | Path) -> None:
        self.runtime_dir = Path(runtime_dir)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.runtime_dir / "qwen_service.json"
        self.log_path = self.runtime_dir / "qwen_service.log"
        self._lock = threading.Lock()
        self._process: subprocess.Popen[Any] | None = None

    @staticmethod
    def _endpoint(settings: Mapping[str, Any]) -> str:
        url = str(settings.get("qwen_base_url") or "http://127.0.0.1:8080/v1/chat/completions")
        return url.split("/v1/", 1)[0].rstrip("/") + "/v1/models"

    @staticmethod
    def _listen_address(settings: Mapping[str, Any]) -> tuple[str, int]:
        parsed = urlparse(str(settings.get("qwen_base_url") or "http://127.0.0.1:8080"))
        host = parsed.hostname or "127.0.0.1"
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise RuntimeError("平台只能启动本机 Qwen；远程地址请使用“测试连接”")
        return host, int(parsed.port or 8080)

    def _read_state(self) -> Dict[str, Any]:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {}

    def _write_state(self, data: Mapping[str, Any]) -> None:
        self.state_path.write_text(json.dumps(dict(data), ensure_ascii=False, indent=2), encoding="utf-8")

    def _managed_process(self):
        state = self._read_state()
        pid = int(state.get("pid") or 0)
        if not pid:
            return None
        try:
            import psutil

            proc = psutil.Process(pid)
            cmdline = " ".join(proc.cmdline()).lower()
            expected = str(state.get("model_path") or "").lower()
            if "llama-server" not in cmdline or (expected and expected not in cmdline):
                return None
            return proc
        except Exception:
            return None

    def status(self, settings: Mapping[str, Any]) -> Dict[str, Any]:
        proc = self._managed_process()
        reachable = False
        detail = "未运行"
        try:
            with urllib.request.urlopen(self._endpoint(settings), timeout=0.8) as response:
                reachable = 200 <= int(response.status) < 500
                detail = "本地推理接口可访问"
        except (OSError, urllib.error.URLError, ValueError):
            if proc is not None:
                detail = "进程已启动，模型仍在加载或接口暂不可用"
        state = self._read_state()
        return {
            "running": proc is not None,
            "reachable": reachable,
            "managed": proc is not None,
            "pid": proc.pid if proc is not None else None,
            "detail": detail,
            "started_at": state.get("started_at"),
            "log_path": str(self.log_path),
            "endpoint": self._endpoint(settings),
        }

    def start(self, settings: Mapping[str, Any]) -> Dict[str, Any]:
        with self._lock:
            current = self.status(settings)
            if current["running"]:
                return {"ok": True, **current, "detail": "平台管理的 Qwen 已在运行"}
            if current["reachable"]:
                return {"ok": False, **current, "detail": "端口已有其他 Qwen 服务；平台不会重复启动或接管"}
            configured_server = str(settings.get("llama_server_path") or "").strip()
            server = configured_server or shutil.which("llama-server") or shutil.which("llama-server.exe")
            if configured_server and not Path(configured_server).is_file():
                raise RuntimeError("llama-server 可执行文件路径无效，请在模型配置中修改")
            if not server:
                raise RuntimeError("找不到 llama-server.exe，请在模型配置中选择程序路径，或加入 PATH")
            model = Path(str(settings.get("qwen_model_path") or ""))
            mmproj = Path(str(settings.get("qwen_mmproj_path") or ""))
            host, port = self._listen_address(settings)
            if not model.is_file() or not mmproj.is_file():
                raise RuntimeError("Qwen GGUF 或 mmproj 路径无效，请先选择并保存")
            log = self.log_path.open("ab")
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            try:
                self._process = subprocess.Popen(
                    [
                        server, "-m", str(model), "--mmproj", str(mmproj),
                        "--host", host, "--port", str(port),
                        "-ngl", "99", "-c", "8192", "-np", "1",
                    ],
                    cwd=str(self.runtime_dir),
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    creationflags=flags,
                )
            finally:
                log.close()
            self._write_state(
                {
                    "pid": self._process.pid,
                    "model_path": str(model.resolve()),
                    "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                }
            )
            # Detect an immediate launch failure (bad flag, occupied port, etc.)
            try:
                self._process.wait(timeout=0.35)
            except subprocess.TimeoutExpired:
                pass
            else:
                code = self._process.returncode
                try:
                    self.state_path.unlink()
                except OSError:
                    pass
                tail = ""
                try:
                    tail = self.log_path.read_text(encoding="utf-8", errors="replace")[-1000:]
                except OSError:
                    pass
                raise RuntimeError(f"llama-server 启动后立即退出（code={code}）: {tail}".strip())
            return {"ok": True, **self.status(settings)}

    def stop(self, settings: Mapping[str, Any]) -> Dict[str, Any]:
        with self._lock:
            proc = self._managed_process()
            if proc is None:
                return {"ok": False, **self.status(settings), "detail": "没有由平台启动的 Qwen 进程可停止"}
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()
            try:
                self.state_path.unlink()
            except OSError:
                pass
            self._process = None
            return {"ok": True, **self.status(settings), "detail": "Qwen 已停止"}


def pick_runtime_path(field: str, kind: str, current: str = "") -> str:
    """Open a native Windows picker from the local backend and return an absolute path."""
    if os.name != "nt":
        raise RuntimeError("本地路径选择器目前仅支持 Windows")
    initial = Path(current).expanduser()
    if initial.is_file():
        initial = initial.parent
    if not initial.is_dir():
        initial = Path.cwd()
    env = os.environ.copy()
    env["ZNT_PICK_INITIAL"] = str(initial)
    if kind == "directory":
        script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$d=New-Object System.Windows.Forms.FolderBrowserDialog; "
            "$d.SelectedPath=$env:ZNT_PICK_INITIAL; "
            "if($d.ShowDialog() -eq 'OK'){[Console]::Write($d.SelectedPath)}"
        )
    else:
        filter_text = ("Executable (*.exe)|*.exe|All files (*.*)|*.*" if field == "llama_server_path"
                       else "Model files (*.gguf;*.pt)|*.gguf;*.pt|All files (*.*)|*.*")
        script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$d=New-Object System.Windows.Forms.OpenFileDialog; "
            "$d.InitialDirectory=$env:ZNT_PICK_INITIAL; "
            f"$d.Filter='{filter_text}'; "
            "if($d.ShowDialog() -eq 'OK'){[Console]::Write($d.FileName)}"
        )
    if not _PICKER_LOCK.acquire(blocking=False):
        raise RuntimeError("已有模型路径选择窗口打开，请先完成或取消该窗口")
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-STA", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=300,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("模型路径选择超时，请重新打开") from exc
    finally:
        _PICKER_LOCK.release()
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"无法打开 {field} 路径选择器")
    return result.stdout.strip()
