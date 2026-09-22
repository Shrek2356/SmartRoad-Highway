"""Runtime-selectable model paths and optional CLIP feature switch."""
from __future__ import annotations

import copy
import json
import os
import shutil
import threading
from pathlib import Path
from typing import Any, Dict, Mapping
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT.parents[1]
COMBINE_ROOT = PROJECT_ROOT.parents[2]
SETTINGS_PATH = PROJECT_ROOT / "outputs" / "road_runtime" / "runtime_settings.json"
INITIAL_SETTINGS_PATH = PROJECT_ROOT / "configs" / "road_runtime_initial_settings.json"
_SETTINGS_LOCK = threading.RLock()

DEFAULTS: Dict[str, Any] = {
    "qwen_enabled": True,
    "llama_server_path": "",
    "qwen_autostart": False,
    "yolo_enabled": False,
    "sam3_enabled": True,
    "clip_enabled": False,
    "qwen_model_path": str(APP_ROOT / "models/qwen/Qwen3-VL-8B-Instruct-Q4_K_M.gguf"),
    "qwen_mmproj_path": str(APP_ROOT / "models/qwen/mmproj-BF16.gguf"),
    "qwen_base_url": "http://127.0.0.1:8080/v1/chat/completions",
    "sam3_repo_path": str(APP_ROOT / "third_party/sam3-main"),
    "sam3_checkpoint_path": str(APP_ROOT / "models/sam3/sam3.pt"),
    "clip_checkpoint_path": str(APP_ROOT / "models/clip/ViT-L-14.pt"),
    "yolo_css_weights_path": "",
    "yolo_construction_weights_path": "",
}

PATH_KINDS = {
    "llama_server_path": "file",
    "qwen_model_path": "file",
    "qwen_mmproj_path": "file",
    "sam3_repo_path": "directory",
    "sam3_checkpoint_path": "file",
    "clip_checkpoint_path": "file",
    "yolo_css_weights_path": "file",
    "yolo_construction_weights_path": "file",
}


def resolve_component_path(value: str) -> Path:
    """Relative component paths always start at the detection project, never cwd."""
    path = Path(os.path.expandvars(value)).expanduser()
    return (path if path.is_absolute() else PROJECT_ROOT / path).resolve()


def portable_settings(data: Mapping[str, Any]) -> Dict[str, Any]:
    """Keep in-package models portable; externally selected paths remain explicit."""
    result = dict(data)
    for key in PATH_KINDS:
        if not result.get(key):
            continue
        path = resolve_component_path(str(result[key]))
        if path.is_relative_to(APP_ROOT.resolve()):
            result[key] = os.path.relpath(path, PROJECT_ROOT)
    return result


def _normalise(raw: Mapping[str, Any]) -> Dict[str, Any]:
    data = dict(DEFAULTS)
    for key in DEFAULTS:
        if key in raw:
            data[key] = (
                bool(raw[key])
                if key.endswith("_enabled") or key.endswith("_autostart")
                else str(raw[key]).strip()
            )
    for key in PATH_KINDS:
        if data[key]:
            data[key] = str(resolve_component_path(data[key]))
    # Road edge detection is deferred; do not reactivate old PPE weights via saved settings.
    data["yolo_enabled"] = False
    data["yolo_css_weights_path"] = ""
    data["yolo_construction_weights_path"] = ""
    return data


def load_runtime_settings(path: str | Path | None = None) -> Dict[str, Any]:
    target = Path(path or SETTINGS_PATH)
    with _SETTINGS_LOCK:
        try:
            raw = json.loads(target.read_text(encoding="utf-8-sig"))
            return _normalise(raw)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            if path is None and target == SETTINGS_PATH:
                return load_initial_settings()
            return dict(DEFAULTS)


def load_initial_settings(path: str | Path | None = None) -> Dict[str, Any]:
    target = Path(path or INITIAL_SETTINGS_PATH)
    try:
        raw = json.loads(target.read_text(encoding="utf-8-sig"))
        return _normalise(raw)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return dict(DEFAULTS)


def save_initial_settings(raw: Mapping[str, Any], path: str | Path | None = None) -> Dict[str, Any]:
    target = Path(path or INITIAL_SETTINGS_PATH)
    data = _normalise(raw)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(portable_settings(data), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)
    return data


def save_runtime_settings(raw: Mapping[str, Any], path: str | Path | None = None) -> Dict[str, Any]:
    target = Path(path or SETTINGS_PATH)
    with _SETTINGS_LOCK:
        current = load_runtime_settings(target)
        current.update({key: raw[key] for key in DEFAULTS if key in raw})
        data = _normalise(current)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f"{target.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(portable_settings(data), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)
        return data


def validate_runtime_settings(settings: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    data = _normalise(settings)
    result: Dict[str, Dict[str, Any]] = {}
    for key, kind in PATH_KINDS.items():
        value = data[key]
        if key == "llama_server_path" and not value:
            value = shutil.which("llama-server") or shutil.which("llama-server.exe") or ""
        path = Path(str(value)).expanduser()
        exists = bool(value) and (path.is_dir() if kind == "directory" else path.is_file())
        result[key] = {"ok": exists, "kind": kind, "resolved": str(path.resolve()) if value else ""}
    base_url = str(data["qwen_base_url"])
    parsed = urlparse(base_url)
    url_ok = (
        parsed.scheme in {"http", "https"}
        and bool(parsed.hostname)
        and parsed.path.rstrip("/").endswith("/v1/chat/completions")
    )
    result["qwen_base_url"] = {
        "ok": url_ok,
        "kind": "url",
        "resolved": base_url,
    }
    result["clip_runtime"] = {
        "ok": (not data["clip_enabled"]) or result["clip_checkpoint_path"]["ok"],
        "kind": "switch",
        "resolved": "enabled" if data["clip_enabled"] else "disabled",
    }
    result["qwen_runtime"] = {
        "ok": (not data["qwen_enabled"]) or (
            result["qwen_model_path"]["ok"]
            and result["qwen_mmproj_path"]["ok"]
            and result["qwen_base_url"]["ok"]
        ),
        "kind": "switch",
        "resolved": "enabled" if data["qwen_enabled"] else "disabled",
    }
    result["sam3_runtime"] = {
        "ok": (not data["sam3_enabled"]) or (
            result["sam3_repo_path"]["ok"] and result["sam3_checkpoint_path"]["ok"]
        ),
        "kind": "switch",
        "resolved": "enabled" if data["sam3_enabled"] else "disabled",
    }
    result["yolo_runtime"] = {
        "ok": (not data["yolo_enabled"]) or (
            result["yolo_css_weights_path"]["ok"]
            and result["yolo_construction_weights_path"]["ok"]
        ),
        "kind": "switch",
        "resolved": "enabled" if data["yolo_enabled"] else "disabled",
    }
    return result


def discover_runtime_settings(current: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    """Select the first existing path from known portable and workstation locations."""
    data = _normalise(current or {})
    candidates = {
        "llama_server_path": [data["llama_server_path"], APP_ROOT / "third_party/llama.cpp/llama-server.exe", shutil.which("llama-server") or ""],
        "qwen_model_path": [data["qwen_model_path"], COMBINE_ROOT / "weights" / Path(DEFAULTS["qwen_model_path"]).name, DEFAULTS["qwen_model_path"]],
        "qwen_mmproj_path": [data["qwen_mmproj_path"], COMBINE_ROOT / "weights" / Path(DEFAULTS["qwen_mmproj_path"]).name, DEFAULTS["qwen_mmproj_path"]],
        "sam3_repo_path": [data["sam3_repo_path"], COMBINE_ROOT / "sam3-main", DEFAULTS["sam3_repo_path"]],
        "sam3_checkpoint_path": [data["sam3_checkpoint_path"], COMBINE_ROOT / "weights" / "sam3.pt", DEFAULTS["sam3_checkpoint_path"]],
        "clip_checkpoint_path": [data["clip_checkpoint_path"], COMBINE_ROOT / "weights" / "ViT-L-14.pt", DEFAULTS["clip_checkpoint_path"]],
        "yolo_css_weights_path": [data["yolo_css_weights_path"], DEFAULTS["yolo_css_weights_path"]],
        "yolo_construction_weights_path": [data["yolo_construction_weights_path"], DEFAULTS["yolo_construction_weights_path"]],
    }
    # Prefer documented in-package locations; retain old sibling layouts as fallback.
    for key in candidates:
        if DEFAULTS[key]:
            candidates[key].insert(1, DEFAULTS[key])
    candidates["sam3_checkpoint_path"].append(COMBINE_ROOT / "weights/sam3.pt")
    candidates["clip_checkpoint_path"].append(Path.home() / ".cache/clip/ViT-L-14.pt")
    for key in ("yolo_css_weights_path", "yolo_construction_weights_path"):
        candidates[key].append(COMBINE_ROOT / "yolo_site_workspace_portable/weights" / Path(DEFAULTS[key]).name)
    for key, values in candidates.items():
        kind = PATH_KINDS[key]
        for value in values:
            if not value:
                continue
            path = resolve_component_path(str(value))
            if (kind == "directory" and path.is_dir()) or (kind == "file" and path.is_file()):
                data[key] = str(path.resolve())
                break
    return data


def apply_runtime_settings(config: Mapping[str, Any], settings: Mapping[str, Any]) -> Dict[str, Any]:
    """Overlay runtime choices on a loaded YAML config without rewriting YAML."""
    data = _normalise(settings)
    merged = copy.deepcopy(dict(config))
    os.environ["LOCAL_QWEN_BASE_URL"] = data["qwen_base_url"]
    # llama.cpp accepts a non-secret local token and a stable model alias.  Do
    # not require legacy .env entries after paths are configured in the UI.
    os.environ.setdefault("LOCAL_QWEN_API_KEY", "local-no-key")
    os.environ.setdefault("LOCAL_QWEN_MODEL", "Qwen3-VL-8B-Instruct")

    sam = merged.setdefault("sam3", {}).setdefault("init_kwargs", {})
    sam["repo_path"] = data["sam3_repo_path"]
    sam["checkpoint"] = data["sam3_checkpoint_path"]

    screening = merged.setdefault("screening", {})
    model_paths = [data["yolo_css_weights_path"], data["yolo_construction_weights_path"]]
    for model, weight in zip(screening.get("models", []), model_paths):
        model["weights"] = weight
    if not data["yolo_enabled"]:
        screening["enabled"] = False
        screening["gate_camera"] = False

    if merged.get("domain") == "road":
        screening.update(enabled=False, gate_camera=False, models=[])

    if data["clip_enabled"]:
        merged["clip"] = {
            "enabled": True,
            "backend": "bridge",
            "bridge_module": "integrations.clip_bridge_user",
            "bridge_class": "CLIPBridge",
            "init_kwargs": {
                "model_name": "ViT-L-14",
                "checkpoint": data["clip_checkpoint_path"],
                "device": "cuda",
                "precision": "fp16",
            },
            "minimum_consistency_score": 0.20,
        }
    else:
        merged.setdefault("clip", {})["enabled"] = False
    return merged
