"""
实时检测模式

standard  标准：云端视觉 + 本地 SAM3（CLIP 可选）
offline   离线：本地 Qwen + SAM3（CLIP 可选）
demo      演示：Mock
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent

PROFILES: Dict[str, Dict[str, Any]] = {
    "standard": {
        "id": "standard",
        "name": "标准",
        "recommend": False,
        "summary": "云端视觉 + 本地 SAM3/CLIP",
        "stack": "云端视觉大模型 + 本地 SAM3 + CLIP",
        "config": "configs/road_standard.yaml",
        "needs": ["cloud_api", "sam3_weights", "clip_weights"],
    },
    "offline": {
        "id": "offline",
        "name": "离线",
        "recommend": True,
        "summary": "道路本地Qwen + SAM3；初筛待接入",
        "stack": "本地Qwen3-VL + SAM3",
        "config": "configs/road_offline.yaml",
        "needs": ["local_qwen_config", "sam3_weights"],
    },
    "demo": {
        "id": "demo",
        "name": "演示",
        "recommend": False,
        "summary": "道路模拟联调（非真实检测）",
        "stack": "道路模拟数据",
        "config": "configs/road_demo.yaml",
        "needs": [],
    },
    # 兼容旧前端/旧启动参数；与 offline 相同，走本地 SAM
    "weights": {
        "id": "weights",
        "name": "离线",
        "recommend": False,
        "summary": "道路本地Qwen + SAM3；初筛待接入",
        "stack": "本地Qwen3-VL + SAM3",
        "config": "configs/road_offline.yaml",
        "needs": ["local_qwen_config", "sam3_weights"],
    },
}


def resolve_config(profile_id: str, root: Path = ROOT) -> Path:
    meta = PROFILES.get(profile_id) or PROFILES["demo"]
    path = Path(meta["config"])
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def _has_env(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def _weight_exists(rel: str, root: Path) -> bool:
    return (root / rel).resolve().is_file() or (root.parent.parent / Path(rel).name).is_file()


def probe_capabilities(root: Path = ROOT) -> Dict[str, bool]:
    from site_safety.runtime_settings import load_runtime_settings, validate_runtime_settings

    runtime = load_runtime_settings()
    checks = validate_runtime_settings(runtime)
    sam3 = bool(runtime["sam3_enabled"]) and (
        checks["sam3_checkpoint_path"]["ok"]
        or
        _weight_exists("../../sam3.pt", root)
        or (root.parent.parent / "sam3.pt").is_file()
        or Path(r"E:\SAM3_MAIN\SAM3\sam3.pt").is_file()
    )
    clip = (
        checks["clip_checkpoint_path"]["ok"]
        or
        _weight_exists("../../ViT-L-14.pt", root)
        or (root.parent.parent / "ViT-L-14.pt").is_file()
        or (Path.home() / ".cache" / "clip" / "ViT-L-14.pt").is_file()
    )
    yolo = False  # Road edge model is deferred.
    cloud = _has_env("DASHSCOPE_API_KEY") or _has_env("MLLM_API_KEY") or _has_env("QWEN_MLLM_API_KEY")
    local_qwen = bool(runtime["qwen_enabled"]) and (
        checks["qwen_base_url"]["ok"]
        and checks["qwen_model_path"]["ok"]
        and checks["qwen_mmproj_path"]["ok"]
    )
    return {
        "cloud_api": cloud,
        "sam3_weights": sam3,
        "clip_weights": clip,
        "yolo_weights": yolo,
        "local_qwen_config": local_qwen,
    }


def profile_status(profile_id: str, caps: Dict[str, bool], root: Path = ROOT) -> Dict[str, Any]:
    meta = dict(PROFILES[profile_id])
    from site_safety.runtime_settings import load_runtime_settings

    clip_enabled = bool(load_runtime_settings().get("clip_enabled", False))
    runtime = load_runtime_settings()
    if profile_id != "demo":
        needs = [item for item in meta.get("needs", []) if item != "clip_weights"]
        if not runtime.get("yolo_enabled", True):
            needs = [item for item in needs if item != "yolo_weights"]
            meta["stack"] = meta["stack"].replace("YOLO26 + ", "")
            meta["summary"] = meta["summary"].replace("YOLO初筛 + ", "")
            meta["yolo_enabled"] = False
        else:
            meta["yolo_enabled"] = False
        if clip_enabled:
            needs.append("clip_weights")
            meta["stack"] = f"{meta['stack'].replace(' + CLIP', '')} + CLIP"
        else:
            meta["stack"] = meta["stack"].replace(" + CLIP", "")
            meta["summary"] = meta["summary"].replace("/CLIP", "").replace(" + CLIP", "")
        meta["needs"] = needs
        meta["clip_enabled"] = clip_enabled
    cfg = resolve_config(profile_id, root)
    missing = [n for n in meta.get("needs", []) if not caps.get(n)]
    ready = cfg.is_file() and not missing
    try:
        meta["config_path"] = str(cfg.relative_to(root)) if cfg.is_file() else meta["config"]
    except ValueError:
        meta["config_path"] = str(cfg)
    meta["config_exists"] = cfg.is_file()
    meta["ready"] = ready
    meta["missing"] = missing
    return meta


def list_profiles(root: Path = ROOT) -> List[Dict[str, Any]]:
    caps = probe_capabilities(root)
    return [profile_status(pid, caps, root) for pid in ("standard", "offline", "demo")]


def pick_default_profile(root: Path = ROOT) -> str:
    """默认优先本地 SAM 离线模式（与最初推荐一致）。"""
    caps = probe_capabilities(root)
    for pid in ("offline", "standard", "demo"):
        if profile_status(pid, caps, root)["ready"]:
            return pid
    return "demo"


def normalize_profile(profile_id: Optional[str], root: Path = ROOT) -> str:
    if profile_id == "weights":
        return "offline"
    if profile_id and profile_id in PROFILES:
        return profile_id
    return pick_default_profile(root)
