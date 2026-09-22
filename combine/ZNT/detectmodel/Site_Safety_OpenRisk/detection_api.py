"""Standalone detection API; does not modify or invoke the downstream Agent layer.

Endpoints:
- POST /api/v1/detect/realtime: image + screening JSON + optional coarse mask
- POST /api/v1/detect/anomaly-image: direct suspected-anomaly image upload
"""
from __future__ import annotations

import argparse
import base64
import binascii
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from PIL import Image
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from site_safety.factory import build_inspector
from site_safety.screening import parse_screening_trigger
from site_safety.utils.config import load_yaml


ROOT = Path(__file__).resolve().parent
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
_state: dict[str, Any] = {"inspector": None}
_load_lock = threading.Lock()
_inference_lock = threading.Lock()

app = FastAPI(
    title="Site Safety OpenRisk Detection API",
    version="1.0.0",
    description="Training-free MLLM + CLIP + SAM3 detection service.",
)


class RealtimeDetectionRequest(BaseModel):
    image_base64: str
    image_format: str = "jpeg"
    screening: dict[str, Any]
    coarse_mask_base64: str | None = None


class DirectDetectionRequest(BaseModel):
    image_base64: str
    image_format: str = "jpeg"
    source: str = Field(default="manual_upload", min_length=1)


def _config_path() -> Path:
    path = Path(os.getenv("DETECTION_CONFIG", "configs/road_offline.yaml"))
    return path if path.is_absolute() else ROOT / path


def _output_root() -> Path:
    path = Path(os.getenv("DETECTION_OUTPUT_ROOT", "outputs/detection_api"))
    return path if path.is_absolute() else ROOT / path


def _get_inspector():
    if _state["inspector"] is None:
        with _load_lock:
            if _state["inspector"] is None:
                config = load_yaml(_config_path())
                _state["inspector"] = build_inspector(config, ROOT)
    return _state["inspector"]


def _save_base64_image(encoded: str, path: Path) -> None:
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status_code=400, detail="invalid base64 image payload") from exc
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="image exceeds 25 MiB limit")
    path.write_bytes(content)
    try:
        with Image.open(path) as image:
            image.verify()
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="invalid image payload") from exc


def _new_run_dir(prefix: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = _output_root() / f"{prefix}_{stamp}_{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _run_detection(
    image_path: Path,
    run_dir: Path,
    trigger: dict[str, Any],
    mask_path: Path | None,
) -> dict[str, Any]:
    # Current local backends share mutable image/model state, so one process
    # serializes inference. Production can scale with multiple worker processes.
    with _inference_lock:
        result = _get_inspector().inspect(
            image_path,
            run_dir,
            screening_trigger=trigger,
            screening_mask_path=mask_path,
        )
    return result.model_dump()


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "model_loaded": _state["inspector"] is not None,
        "config": str(_config_path()),
    }


@app.post("/api/v1/detect/realtime")
async def detect_realtime(request: RealtimeDetectionRequest) -> dict[str, Any]:
    """Accept a realtime detector event with a coarse region/mask."""
    try:
        trigger = parse_screening_trigger(request.screening)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"invalid screening_json: {exc}") from exc
    if trigger is None or not trigger.triggered:
        raise HTTPException(status_code=422, detail="realtime endpoint requires triggered=true")

    run_dir = _new_run_dir("realtime")
    suffix = request.image_format.lower().lstrip(".")
    image_path = run_dir / f"input.{suffix}"
    _save_base64_image(request.image_base64, image_path)
    mask_path = None
    if request.coarse_mask_base64 is not None:
        mask_path = run_dir / "input_coarse_mask.png"
        _save_base64_image(request.coarse_mask_base64, mask_path)
    return await run_in_threadpool(
        _run_detection,
        image_path,
        run_dir,
        trigger.model_dump(),
        mask_path,
    )


@app.post("/api/v1/detect/anomaly-image")
async def detect_anomaly_image(request: DirectDetectionRequest) -> dict[str, Any]:
    """Directly inspect a suspected-anomaly image without forcing a risk verdict."""
    run_dir = _new_run_dir("direct")
    suffix = request.image_format.lower().lstrip(".")
    image_path = run_dir / f"input.{suffix}"
    _save_base64_image(request.image_base64, image_path)
    trigger = {
        "triggered": True,
        "anomaly_score": 0.5,
        "suspected_regions": [],
        "suspected_concepts": [],
        "source_model": request.source,
        "reason": "Direct suspected-anomaly image submission; routing only.",
    }
    return await run_in_threadpool(
        _run_detection,
        image_path,
        run_dir,
        trigger,
        None,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Standalone Site Safety OpenRisk detection API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8810)
    parser.add_argument("--config", default="configs/road_offline.yaml")
    parser.add_argument("--output-root", default="outputs/detection_api")
    args = parser.parse_args()
    os.environ["DETECTION_CONFIG"] = args.config
    os.environ["DETECTION_OUTPUT_ROOT"] = args.output_root
    uvicorn.run(app, host=args.host, port=args.port, workers=1)


if __name__ == "__main__":
    main()
