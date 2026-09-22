"""Read-only deployment guidance and explicit, serialized environment checks."""
from __future__ import annotations

import importlib.util
import json
import sys
import threading
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[3]
_check_lock = threading.Lock()


def deployment_manifest() -> dict:
    path = APP_ROOT / "requirements/deployment-manifest.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(manifest.get("models"), dict):
            raise ValueError("models missing")
    except (OSError, ValueError, AttributeError) as exc:
        raise RuntimeError("部署清单缺失或损坏，请使用包含 requirements 目录的完整交付包。") from exc
    return {"manifest": manifest, "app_root": str(APP_ROOT), "python_executable": sys.executable}


def check_environment(mode: str) -> dict:
    if mode not in {"demo", "offline", "cloud"}:
        raise ValueError("请选择演示、本地或云端模式")
    if not _check_lock.acquire(blocking=False):
        raise RuntimeError("已有环境检查进行中，请等待结果后再试。")
    try:
        script = APP_ROOT / "requirements/preflight_check.py"
        if not script.is_file():
            raise RuntimeError("缺少 requirements/preflight_check.py，请使用完整交付包。")
        spec = importlib.util.spec_from_file_location("sitesafe_preflight", script)
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        return checker.run_probe(Path(sys.executable), mode)
    finally:
        _check_lock.release()
