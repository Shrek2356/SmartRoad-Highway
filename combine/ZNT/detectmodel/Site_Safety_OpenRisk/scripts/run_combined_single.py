"""Run one image through the integrated YOLO + local Qwen/SAM3 pipeline."""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from detect_bridge import DetectBridge, ROOT


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    image_path = args.image.resolve()
    if not image_path.is_file():
        raise FileNotFoundError(image_path)

    load_dotenv(ROOT / ".env")
    out_dir = ROOT / "outputs" / f"combined_{image_path.stem}_{datetime.now():%Y%m%d_%H%M%S}"
    out_dir.mkdir(parents=True, exist_ok=False)
    bridge = DetectBridge(default_profile="offline")
    started = time.perf_counter()
    response = bridge.create_job(
        source="upload",
        device_id="EXAMPLE-BATCH",
        data_mode="offline",
        image_bytes=image_path.read_bytes(),
        filename=image_path.name,
        profile="offline",
        force_inspection=True,
    )
    job_id = response["job_id"]
    print(f"START {image_path.name} job={job_id}", flush=True)
    while True:
        job = bridge.get_job(job_id)
        if job["status"] in {"done", "error"}:
            break
        time.sleep(0.5)
    result = job.get("result") or {}
    payload = {
        "image": image_path.name,
        "job_id": job_id,
        "status": job["status"],
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "screening": job.get("screening"),
        "routed_to_vlm": job.get("routed_to_vlm"),
        "result": result,
        "job_output_dir": job.get("output_dir"),
        "error": job.get("error"),
    }
    (out_dir / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
    print(f"OUTPUT_DIR={out_dir}", flush=True)
    return 0 if job["status"] == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
