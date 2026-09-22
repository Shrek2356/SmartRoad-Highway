"""道路损毁全自动异常检测 + 五类掩码labelme标注入口。

对每张图：跑完整检测链路（两遍MLLM + SAM3 + CLIP + 证据门控），
再把实体掩码按五类体系映射导出labelme JSON（与gold100_workspace互通）。

用法：
  python run_road_annotation.py --input <图或目录> \
      --config configs/road_offline.yaml --workspace outputs/road_anno_smoke [--limit 8]
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
import traceback
from pathlib import Path

from site_safety.factory import build_inspector
from site_safety.pipeline.labelme_export import (
    build_background_shapes,
    build_shapes_from_result,
    load_catalog_classes,
    shapes_occupancy,
    write_labelme_json,
    write_labels_txt,
)
from site_safety.utils.config import load_yaml

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Road damage auto-annotation (5-class labelme export)")
    parser.add_argument("--input", required=True, help="输入图像或目录")
    parser.add_argument("--config", default="configs/road_offline.yaml")
    parser.add_argument("--workspace", default="outputs/road_annotation")
    parser.add_argument("--limit", type=int, default=0, help="最多处理张数（0=全部）")
    parser.add_argument("--no-background", action="store_true", help="跳过背景类分割")
    return parser.parse_args()


def collect_images(input_path: Path, limit: int) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    images = sorted(
        p for p in input_path.rglob("*") if p.suffix.lower() in IMAGE_SUFFIXES
    )
    return images[:limit] if limit > 0 else images


def main() -> None:
    args = parse_args()
    project_root = Path(__file__).resolve().parent
    config = load_yaml(project_root / args.config)
    from site_safety.runtime_settings import apply_runtime_settings, load_runtime_settings
    config = apply_runtime_settings(config, load_runtime_settings())
    inspector = build_inspector(config, project_root)

    catalog_path = project_root / config["risk_catalog"]["path"]
    catalog_classes = load_catalog_classes(catalog_path)

    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = project_root / input_path
    images = collect_images(input_path, args.limit)
    if not images:
        raise SystemExit(f"未找到图像: {input_path}")

    workspace = project_root / args.workspace
    images_dir = workspace / "images"
    runs_dir = workspace / "runs"
    images_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)
    write_labels_txt(workspace)

    annotation_cfg = config.get("annotation", {})
    background_prompts = annotation_cfg.get(
        "background_prompts", ["vegetation", "sky", "building"]
    )

    manifest: list[dict] = []
    for index, image_path in enumerate(images):
        stem = f"{index:03d}_{image_path.stem}"
        run_dir = runs_dir / stem
        entry: dict = {"index": index, "source": str(image_path), "stem": stem}
        started = time.time()
        try:
            result_model = inspector.inspect(image_path, run_dir)
            result = result_model.model_dump()

            shapes = build_shapes_from_result(result, run_dir, catalog_classes)
            from PIL import Image

            with Image.open(image_path) as im:
                height, width = im.height, im.width
                if not args.no_background:
                    occupied = shapes_occupancy(shapes, height, width)
                    shapes += build_background_shapes(
                        inspector.sam3,
                        im.convert("RGB"),
                        occupied,
                        prompts=background_prompts,
                        min_score=float(annotation_cfg.get("background_min_score", 0.30)),
                    )

            target_image = images_dir / f"{stem}{image_path.suffix.lower()}"
            shutil.copy2(image_path, target_image)
            write_labelme_json(
                images_dir / f"{stem}.json",
                target_image.name,
                shapes,
                height,
                width,
                extra_flags={"pipeline": "site_safety_openrisk"},
            )
            label_counts: dict[str, int] = {}
            for shape in shapes:
                label_counts[shape["label"]] = label_counts.get(shape["label"], 0) + 1
            entry.update(
                {
                    "status": "ok",
                    "seconds": round(time.time() - started, 1),
                    "shapes": label_counts,
                    "overall_has_anomaly": bool(
                        (result.get("final_report") or {}).get("overall_has_anomaly", False)
                    ),
                }
            )
            print(f"[{index + 1}/{len(images)}] {image_path.name}: {label_counts}")
        except Exception as exc:  # 单图失败不中断批处理
            entry.update({"status": "error", "error": f"{type(exc).__name__}: {exc}"})
            (run_dir / "error.txt").parent.mkdir(parents=True, exist_ok=True)
            (run_dir / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            print(f"[{index + 1}/{len(images)}] {image_path.name}: FAILED {exc}")
        manifest.append(entry)
        (workspace / "workspace_manifest.json").write_text(
            json.dumps(
                {"config": args.config, "input": str(input_path), "items": manifest},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    ok = sum(1 for item in manifest if item.get("status") == "ok")
    print(f"完成: {ok}/{len(manifest)} 张，工作区: {workspace}")


if __name__ == "__main__":
    main()
