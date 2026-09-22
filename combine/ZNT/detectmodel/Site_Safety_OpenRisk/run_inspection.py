from __future__ import annotations

import argparse
from pathlib import Path

from site_safety.factory import build_inspector
from site_safety.screening import parse_screening_trigger
from site_safety.utils.config import load_yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Training-free MLLM + SAM3 site-safety inspection")
    parser.add_argument("--image", required=True, help="Input road image")
    parser.add_argument("--config", default="configs/road_offline.yaml")
    parser.add_argument("--output-dir", default="outputs/run_001")
    parser.add_argument(
        "--screening-json",
        help="Optional upstream detector trigger JSON; treated as routing metadata, not evidence.",
    )
    parser.add_argument(
        "--screening-mask",
        help="Optional coarse anomaly mask image from the realtime detector.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path(__file__).resolve().parent
    config = load_yaml(project_root / args.config)
    inspector = build_inspector(config, project_root)
    screening_path = Path(args.screening_json) if args.screening_json else None
    if screening_path is not None and not screening_path.is_absolute():
        screening_path = project_root / screening_path
    trigger = parse_screening_trigger(screening_path) if screening_path else None
    screening_mask = Path(args.screening_mask) if args.screening_mask else None
    if screening_mask is not None and not screening_mask.is_absolute():
        screening_mask = project_root / screening_mask
    result = inspector.inspect(
        project_root / args.image if not Path(args.image).is_absolute() else args.image,
        project_root / args.output_dir,
        screening_trigger=trigger,
        screening_mask_path=screening_mask,
    )
    print(f"Completed. Result: {Path(result.output_dir) / 'result.json'}")
    if result.final_report:
        print(result.final_report.overall_summary)


if __name__ == "__main__":
    main()
