"""Minimal client for the standalone detection API."""
from __future__ import annotations

import argparse
import base64
from pathlib import Path

import httpx


def encoded(path: str | Path) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode("ascii")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8810")
    parser.add_argument("--image", required=True)
    parser.add_argument("--mask")
    parser.add_argument("--mode", choices=["realtime", "direct"], default="direct")
    args = parser.parse_args()

    if args.mode == "realtime":
        payload = {
            "image_base64": encoded(args.image),
            "image_format": Path(args.image).suffix.lstrip(".") or "jpeg",
            "screening": {
                "triggered": True,
                "anomaly_score": 0.75,
                "suspected_regions": [],
                "suspected_concepts": [],
                "source_model": "realtime_detector",
            },
            "coarse_mask_base64": encoded(args.mask) if args.mask else None,
        }
        endpoint = "/api/v1/detect/realtime"
    else:
        payload = {
            "image_base64": encoded(args.image),
            "image_format": Path(args.image).suffix.lstrip(".") or "jpeg",
            "source": "manual_upload",
        }
        endpoint = "/api/v1/detect/anomaly-image"

    response = httpx.post(f"{args.url}{endpoint}", json=payload, timeout=1800)
    response.raise_for_status()
    print(response.json())


if __name__ == "__main__":
    main()
