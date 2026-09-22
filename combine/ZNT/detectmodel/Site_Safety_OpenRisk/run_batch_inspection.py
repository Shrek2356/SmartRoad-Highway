from __future__ import annotations

import argparse
import json
from pathlib import Path

from site_safety.factory import build_inspector
from site_safety.screening import load_trigger_for_stem
from site_safety.utils.config import load_yaml


SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch road image inspection")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--config", default="configs/road_offline.yaml")
    parser.add_argument("--output-dir", default="outputs/batch")
    parser.add_argument(
        "--image-names",
        nargs="+",
        help="Optional image filenames or stems to rerun; keeps one inspector loaded.",
    )
    parser.add_argument(
        "--screening-dir",
        help="Optional directory containing one validated <image_stem>.json trigger per image.",
    )
    parser.add_argument(
        "--screening-mask-dir",
        help="Optional directory containing <image_stem>.png coarse anomaly masks.",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    input_dir = Path(args.input_dir)
    config_path = Path(args.config)
    output_root = Path(args.output_dir)
    if not input_dir.is_absolute():
        input_dir = root / input_dir
    if not config_path.is_absolute():
        config_path = root / config_path
    if not output_root.is_absolute():
        output_root = root / output_root
    screening_dir = Path(args.screening_dir) if args.screening_dir else None
    if screening_dir is not None and not screening_dir.is_absolute():
        screening_dir = root / screening_dir
    screening_mask_dir = Path(args.screening_mask_dir) if args.screening_mask_dir else None
    if screening_mask_dir is not None and not screening_mask_dir.is_absolute():
        screening_mask_dir = root / screening_mask_dir

    images = sorted(
        path
        for path in input_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )
    if args.image_names:
        wanted = set(args.image_names)
        images = [path for path in images if path.name in wanted or path.stem in wanted]
    if not images:
        selection = f" matching --image-names={args.image_names}" if args.image_names else ""
        raise FileNotFoundError(f"No supported images found in: {input_dir}{selection}")

    config = load_yaml(config_path)
    inspector = None
    output_root.mkdir(parents=True, exist_ok=True)
    batch_summary = []
    for index, image_path in enumerate(images, start=1):
        print(f"[{index}/{len(images)}] Inspecting: {image_path.name}", flush=True)
        run_dir = output_root / image_path.stem
        existing_result = run_dir / "result.json"
        # A trigger changes the MLLM prior and must not silently reuse an older,
        # untriggered result for the same image.
        if (
            existing_result.is_file()
            and screening_dir is None
            and screening_mask_dir is None
        ):
            data = json.loads(existing_result.read_text(encoding="utf-8"))
            visual = data.get("visual_verification") or data.get("final_report") or {}
            batch_summary.append(
                {
                    "image": str(image_path),
                    "output_dir": str(run_dir),
                    "status": "existing",
                    "overall_has_anomaly": visual.get("overall_has_anomaly"),
                    "verified_risk_ids": [
                        risk.get("risk_id")
                        for risk in visual.get("final_risks", [])
                        if risk.get("verified")
                    ],
                    "report_generated_by": (
                        data.get("management_report") or {}
                    ).get("generated_by"),
                }
            )
            print(f"[{index}/{len(images)}] Existing result reused: {run_dir}", flush=True)
            continue
        try:
            if inspector is None:
                inspector = build_inspector(config, root)
            trigger = (
                load_trigger_for_stem(screening_dir, image_path.stem)
                if screening_dir is not None
                else None
            )
            mask_path = (
                screening_mask_dir / f"{image_path.stem}.png"
                if screening_mask_dir is not None
                else None
            )
            if mask_path is not None and not mask_path.is_file():
                mask_path = None
            result = inspector.inspect(
                image_path,
                run_dir,
                screening_trigger=trigger,
                screening_mask_path=mask_path,
            )
            batch_summary.append(
                {
                    "image": str(image_path),
                    "output_dir": str(run_dir),
                    "status": "completed",
                    "overall_has_anomaly": (
                        result.visual_verification.overall_has_anomaly
                        if result.visual_verification
                        else None
                    ),
                    "verified_risk_ids": (
                        [
                            risk.risk_id
                            for risk in result.visual_verification.final_risks
                            if risk.verified
                        ]
                        if result.visual_verification
                        else []
                    ),
                    "report_generated_by": (
                        result.management_report.generated_by
                        if result.management_report
                        else None
                    ),
                }
            )
            print(f"[{index}/{len(images)}] Completed: {run_dir}", flush=True)
        except Exception as exc:
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "error.txt").write_text(
                f"{type(exc).__name__}: {exc}",
                encoding="utf-8",
            )
            batch_summary.append(
                {
                    "image": str(image_path),
                    "output_dir": str(run_dir),
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            print(f"[{index}/{len(images)}] Failed: {type(exc).__name__}: {exc}", flush=True)

    summary_path = output_root / "batch_summary.json"
    summary_path.write_text(
        json.dumps(batch_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Batch completed: {summary_path}")


if __name__ == "__main__":
    main()
