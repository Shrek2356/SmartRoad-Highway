"""YOLO realtime screening adapter for the Site Safety OpenRisk bridge.

The adapter deliberately produces routing metadata, not final safety facts.
Explicit violation classes can trigger the heavy pipeline, while neutral entity
classes are retained as attention regions and for cheap geometric heuristics.
"""
from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

from PIL import Image, ImageDraw


EXPLICIT_CONCEPTS = {
    "no-hardhat": "missing_helmet",
    "no-mask": "missing_mask",
    "no-safety-vest": "missing_safety_vest",
    "rule_1_violation": "construction_rule_1_violation",
    "rule_2_violation": "construction_rule_2_violation",
    "rule_3_violation": "construction_rule_3_violation",
    "rule_4_violation": "construction_rule_4_violation",
}

PERSON_LABELS = {"person", "worker-with-white-hard-hat"}
MACHINE_LABELS = {"machinery", "vehicle", "excavator"}
ATTENTION_LABELS = PERSON_LABELS | MACHINE_LABELS | {
    "hardhat",
    "mask",
    "safety-cone",
    "safety-vest",
    "rebar",
}


def _normalise_label(value: str) -> str:
    return value.strip().lower().replace("_", "-").replace(" ", "-")


def _concept_for_label(label: str) -> Optional[str]:
    normalised = _normalise_label(label)
    if normalised in EXPLICIT_CONCEPTS:
        return EXPLICIT_CONCEPTS[normalised]
    # Dataset rule classes use underscores in their canonical names.
    underscored = normalised.replace("-", "_")
    return EXPLICIT_CONCEPTS.get(underscored)


def _edge_gap_ratio(a: List[float], b: List[float], image_size: tuple[int, int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    dx = max(bx1 - ax2, ax1 - bx2, 0.0)
    dy = max(by1 - ay2, ay1 - by2, 0.0)
    diagonal = max(math.hypot(*image_size), 1.0)
    return math.hypot(dx, dy) / diagonal


@dataclass(frozen=True)
class YoloDetection:
    model_name: str
    label: str
    score: float
    bbox_xyxy: List[float]


class YoloScreeningAdapter:
    """Run one or more Ultralytics models and compile ScreeningTrigger JSON."""

    def __init__(
        self,
        config: Mapping[str, Any],
        project_root: str | Path,
        *,
        model_factory: Optional[Callable[[str], Any]] = None,
    ) -> None:
        self.config = dict(config)
        self.project_root = Path(project_root).resolve()
        self.device = self.config.get("device", 0)
        self.imgsz = int(self.config.get("imgsz", 640))
        self.confidence = float(self.config.get("confidence", 0.25))
        self.iou = float(self.config.get("iou", 0.70))
        self.max_regions = int(self.config.get("max_regions", 16))
        self.trigger_threshold = float(self.config.get("trigger_threshold", 0.35))
        self.proximity_threshold = float(self.config.get("proximity_threshold", 0.08))
        self.calibration_version = str(
            self.config.get("calibration_version", "yolo-screening-v1")
        )
        self._lock = threading.Lock()
        self._model_factory = model_factory
        self._models: Optional[List[tuple[str, Any]]] = None

    def _resolve_weights(self, value: str) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = self.project_root / path
        path = path.resolve()
        if not path.is_file():
            raise FileNotFoundError(f"YOLO weights not found: {path}")
        return path

    def _load_models(self) -> List[tuple[str, Any]]:
        if self._models is not None:
            return self._models
        factory = self._model_factory
        if factory is None:
            from ultralytics import YOLO

            factory = YOLO
        loaded: List[tuple[str, Any]] = []
        for index, item in enumerate(self.config.get("models", [])):
            weights = self._resolve_weights(str(item["weights"]))
            name = str(item.get("name") or weights.stem or f"yolo_{index}")
            loaded.append((name, factory(str(weights))))
        if not loaded:
            raise ValueError("screening.models must contain at least one YOLO model")
        self._models = loaded
        return loaded

    def inspect(self, image_path: str | Path, output_dir: str | Path) -> Dict[str, Any]:
        image_path = Path(image_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        image = Image.open(image_path).convert("RGB")
        detections: List[YoloDetection] = []
        with self._lock:
            for model_name, model in self._load_models():
                results = model.predict(
                    source=str(image_path),
                    imgsz=self.imgsz,
                    conf=self.confidence,
                    iou=self.iou,
                    device=self.device,
                    verbose=False,
                    save=False,
                )
                if results:
                    detections.extend(self._extract_result(model_name, results[0]))
        payload = self.compile_trigger(detections, image.size)
        self._save_attention_artifacts(image, detections, payload, output_dir)
        return payload

    @staticmethod
    def _extract_result(model_name: str, result: Any) -> List[YoloDetection]:
        names = getattr(result, "names", {}) or {}
        boxes = getattr(result, "boxes", None)
        if boxes is None or len(boxes) == 0:
            return []
        xyxy = boxes.xyxy.detach().cpu().tolist()
        scores = boxes.conf.detach().float().cpu().tolist()
        classes = boxes.cls.detach().long().cpu().tolist()
        return [
            YoloDetection(
                model_name=model_name,
                label=str(names.get(int(class_id), class_id)),
                score=float(score),
                bbox_xyxy=[float(value) for value in box[:4]],
            )
            for box, score, class_id in zip(xyxy, scores, classes)
        ]

    def compile_trigger(
        self,
        detections: Iterable[YoloDetection],
        image_size: tuple[int, int],
    ) -> Dict[str, Any]:
        ordered = sorted(detections, key=lambda item: item.score, reverse=True)
        explicit = [
            item
            for item in ordered
            if _concept_for_label(item.label) and item.score >= self.trigger_threshold
        ]
        people = [item for item in ordered if _normalise_label(item.label) in PERSON_LABELS]
        machines = [item for item in ordered if _normalise_label(item.label) in MACHINE_LABELS]
        proximity_pairs: List[tuple[YoloDetection, YoloDetection, float]] = []
        for person in people:
            for machine in machines:
                gap = _edge_gap_ratio(person.bbox_xyxy, machine.bbox_xyxy, image_size)
                if gap <= self.proximity_threshold:
                    proximity_pairs.append((person, machine, gap))

        triggered = bool(explicit or proximity_pairs)
        concepts = [_concept_for_label(item.label) for item in explicit]
        if proximity_pairs:
            concepts.append("person_near_machinery")
        concepts = list(dict.fromkeys(value for value in concepts if value))

        selected: List[YoloDetection] = list(explicit)
        for person, machine, _ in proximity_pairs:
            selected.extend([person, machine])
        if triggered:
            selected.extend(
                item
                for item in ordered
                if _normalise_label(item.label) in ATTENTION_LABELS
            )
        deduped: List[YoloDetection] = []
        seen = set()
        for item in selected:
            key = (item.model_name, item.label, tuple(round(x, 2) for x in item.bbox_xyxy))
            if key not in seen:
                seen.add(key)
                deduped.append(item)
        deduped = deduped[: self.max_regions]

        anomaly_scores = [item.score for item in explicit]
        anomaly_scores.extend(max(pair[0].score, pair[1].score) for pair in proximity_pairs)
        anomaly_score = max(anomaly_scores, default=0.0)
        model_names = list(dict.fromkeys(item.model_name for item in ordered))
        reasons = []
        if explicit:
            reasons.append(
                "explicit=" + ",".join(f"{item.label}:{item.score:.2f}" for item in explicit)
            )
        if proximity_pairs:
            reasons.append(f"person_machine_pairs={len(proximity_pairs)}")
        if not reasons:
            reasons.append("no calibrated YOLO trigger; periodic/manual audit may still route")

        return {
            "triggered": triggered,
            "anomaly_score": min(max(float(anomaly_score), 0.0), 1.0),
            "suspected_regions": [
                {
                    "region_id": f"yolo_{index:02d}",
                    "bbox_xyxy": item.bbox_xyxy,
                    "score": min(max(item.score, 0.0), 1.0),
                    "label": item.label,
                    "coordinate_space": "pixel_xyxy",
                }
                for index, item in enumerate(deduped, start=1)
            ],
            "suspected_concepts": concepts,
            "source_model": "+".join(model_names) if model_names else "integrated_yolo",
            "calibration_version": self.calibration_version,
            "reason": "; ".join(reasons),
            "detections": [
                {
                    "model": item.model_name,
                    "label": item.label,
                    "score": item.score,
                    "bbox_xyxy": item.bbox_xyxy,
                }
                for item in ordered
            ],
        }

    @staticmethod
    def _save_attention_artifacts(
        image: Image.Image,
        detections: List[YoloDetection],
        payload: Mapping[str, Any],
        output_dir: Path,
    ) -> None:
        overlay = image.copy()
        draw = ImageDraw.Draw(overlay)
        selected_boxes = {
            tuple(round(v, 2) for v in region["bbox_xyxy"])
            for region in payload.get("suspected_regions", [])
        }
        for item in detections:
            box_key = tuple(round(v, 2) for v in item.bbox_xyxy)
            colour = "#ff3b30" if box_key in selected_boxes else "#f5a623"
            draw.rectangle(item.bbox_xyxy, outline=colour, width=3)
            draw.text(
                (item.bbox_xyxy[0] + 3, max(0, item.bbox_xyxy[1] - 14)),
                f"{item.label} {item.score:.2f}",
                fill=colour,
            )
        overlay.save(output_dir / "screening_overlay.jpg", quality=92)

        mask = Image.new("L", image.size, 0)
        mask_draw = ImageDraw.Draw(mask)
        for region in payload.get("suspected_regions", []):
            mask_draw.rectangle(region["bbox_xyxy"], fill=255)
        mask.save(output_dir / "screening_coarse_mask.png")
