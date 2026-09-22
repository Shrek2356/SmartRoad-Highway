from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List

import numpy as np

from site_safety.adapters.base import MaskInstance
from site_safety.schemas import RelationCheck, RelationEvidence
from site_safety.utils.image import mask_box


@dataclass
class _PairScore:
    score: float
    details: dict


def _box(instance: MaskInstance) -> list[float] | None:
    return instance.box_xyxy or mask_box(instance.mask)


def _center(box: list[float]) -> tuple[float, float]:
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def _box_edge_gap(a: list[float], b: list[float]) -> float:
    """Minimum Euclidean gap between two axis-aligned boxes (zero if touching)."""
    dx = max(a[0] - b[2], b[0] - a[2], 0.0)
    dy = max(a[1] - b[3], b[1] - a[3], 0.0)
    return float((dx**2 + dy**2) ** 0.5)


def _horizontal_overlap_ratio(a: list[float], b: list[float]) -> float:
    overlap = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    denom = max(1.0, min(a[2] - a[0], b[2] - b[0]))
    return overlap / denom


def _protective_item_matches_subject(
    subject_box: list[float],
    object_box: list[float],
    *,
    upper_body_ratio: float = 0.45,
) -> bool:
    """Associate a PPE object with the upper/head region of a person box."""
    sx1, sy1, sx2, sy2 = subject_box
    ox, oy = _center(object_box)
    subject_height = max(1.0, sy2 - sy1)
    horizontal_margin = max(2.0, (sx2 - sx1) * 0.12)
    return (
        sx1 - horizontal_margin <= ox <= sx2 + horizontal_margin
        and sy1 - subject_height * 0.15 <= oy <= sy1 + subject_height * upper_body_ratio
    )


def _mask_iou(a: np.ndarray, b: np.ndarray) -> float:
    inter = np.logical_and(a > 0, b > 0).sum()
    union = np.logical_or(a > 0, b > 0).sum()
    return float(inter / union) if union else 0.0


def _subject_overlap(a: np.ndarray, b: np.ndarray) -> float:
    inter = np.logical_and(a > 0, b > 0).sum()
    denom = max(1, int((a > 0).sum()))
    return float(inter / denom)


def _box_overlap_ratio(a: list[float], b: list[float]) -> float:
    width = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    height = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    intersection = width * height
    area_a = max(1.0, (a[2] - a[0]) * (a[3] - a[1]))
    area_b = max(1.0, (b[2] - b[0]) * (b[3] - b[1]))
    return intersection / min(area_a, area_b)


def _float_param(params: dict, key: str, fallback: float) -> float:
    try:
        return float(params.get(key, fallback))
    except (TypeError, ValueError):
        return float(fallback)


def _bool_param(params: dict, key: str, fallback: bool) -> bool:
    value = params.get(key, fallback)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _visibility_param(params: dict) -> str:
    value = str(
        params.get(
            "inspection_zone_visibility",
            params.get("visibility", "unknown"),
        )
    ).strip().lower()
    aliases = {
        "visible": "clear",
        "fully_visible": "clear",
        "fully visible": "clear",
        "清晰": "clear",
        "清晰可见": "clear",
        "partially_visible": "partial",
        "partially visible": "partial",
        "部分可见": "partial",
        "blocked": "occluded",
        "遮挡": "occluded",
        "被遮挡": "occluded",
    }
    normalized = aliases.get(value, value)
    return normalized if normalized in {"clear", "partial", "occluded"} else "unknown"


class RelationVerifier:
    def __init__(self, defaults: dict[str, float]) -> None:
        self.defaults = defaults

    def verify(
        self,
        check: RelationCheck,
        by_task: Dict[str, List[MaskInstance]],
        image_shape: tuple[int, int],
    ) -> RelationEvidence:
        subjects = [item for task_id in check.subject_task_ids for item in by_task.get(task_id, [])]
        objects = [item for task_id in check.object_task_ids for item in by_task.get(task_id, [])]
        relation_type = check.type
        if relation_type == "none":
            passed = bool(subjects or objects)
            return RelationEvidence(relation_type=relation_type, passed=passed, score=1.0 if passed else 0.0, details={})
        if relation_type == "missing":
            subject_present = bool(subjects)
            object_not_detected = not bool(objects)
            visibility = _visibility_param(check.params)
            allow_non_detection = _bool_param(
                check.params,
                "allow_missing_from_non_detection",
                self.defaults.get("allow_missing_from_non_detection", False),
            )
            allow_visible_zone = _bool_param(
                check.params,
                "allow_missing_from_visible_zone",
                self.defaults.get("allow_missing_from_visible_zone", True),
            )
            visible_zone_confirmation = visibility == "clear" and allow_visible_zone
            inference_enabled = allow_non_detection or visible_zone_confirmation
            passed = subject_present and object_not_detected and inference_enabled
            if passed:
                score = 0.90 if visible_zone_confirmation else 1.0
            elif subject_present and object_not_detected:
                score = {
                    "clear": 0.70,
                    "partial": 0.45,
                    "occluded": 0.20,
                    "unknown": 0.35,
                }[visibility]
            else:
                score = 0.0
            return RelationEvidence(
                relation_type=relation_type,
                passed=passed,
                score=score,
                details={
                    "subject_count": len(subjects),
                    "object_count": len(objects),
                    "object_not_detected": object_not_detected,
                    "inspection_zone_visibility": visibility,
                    "required_item": check.params.get("required_item"),
                    "absence_inference_enabled": inference_enabled,
                    "visible_zone_confirmation": visible_zone_confirmation,
                    "inconclusive": subject_present and object_not_detected and not inference_enabled,
                },
            )
        if relation_type == "missing_association":
            subject_boxes = [(_box(item), item) for item in subjects]
            object_boxes = [(_box(item), item) for item in objects]
            subject_boxes = [(box, item) for box, item in subject_boxes if box is not None]
            object_boxes = [(box, item) for box, item in object_boxes if box is not None]
            upper_ratio = _float_param(check.params, "upper_body_ratio", 0.45)
            unmatched_indexes = []
            matched_pairs = []
            for subject_index, (subject_box, _) in enumerate(subject_boxes):
                matches = [
                    object_index
                    for object_index, (object_box, _) in enumerate(object_boxes)
                    if _protective_item_matches_subject(
                        subject_box,
                        object_box,
                        upper_body_ratio=upper_ratio,
                    )
                ]
                if matches:
                    matched_pairs.extend(
                        {"subject_index": subject_index, "object_index": object_index}
                        for object_index in matches
                    )
                else:
                    unmatched_indexes.append(subject_index)
            visibility_is_explicit = any(
                key in check.params
                for key in ("inspection_zone_visibility", "visibility")
            )
            visibility = _visibility_param(check.params)
            visibility_supports_absence = (
                not visibility_is_explicit or visibility == "clear"
            )
            passed = bool(unmatched_indexes) and visibility_supports_absence
            if passed:
                score = 0.90
            elif unmatched_indexes and visibility_is_explicit:
                score = {
                    "clear": 0.90,
                    "partial": 0.45,
                    "occluded": 0.20,
                    "unknown": 0.35,
                }[visibility]
            else:
                score = 0.0
            return RelationEvidence(
                relation_type=relation_type,
                passed=passed,
                score=score,
                details={
                    "subject_count": len(subject_boxes),
                    "object_count": len(object_boxes),
                    "unmatched_subject_indexes": unmatched_indexes,
                    "matched_pairs": matched_pairs,
                    "upper_body_ratio": upper_ratio,
                    "inspection_zone_visibility": visibility,
                    "visibility_supports_absence": visibility_supports_absence,
                },
            )
        near_subject_filter_details: dict = {}
        if relation_type == "near":
            raw_subject_count = len(subjects)
            min_subject_score = _float_param(
                check.params,
                "near_min_subject_score",
                self.defaults.get("near_min_subject_score", 0.0),
            )
            subjects = [
                item for item in subjects if float(item.score) >= min_subject_score
            ]
            near_subject_filter_details = {
                "raw_subject_count": raw_subject_count,
                "qualified_subject_count": len(subjects),
                "near_min_subject_score": min_subject_score,
            }
        if not subjects or not objects:
            return RelationEvidence(
                relation_type=relation_type,
                passed=False,
                score=0.0,
                details={
                    "subject_count": len(subjects),
                    "object_count": len(objects),
                    **near_subject_filter_details,
                },
            )

        pair_scores: List[_PairScore] = []
        height, width = image_shape
        diag = max(1.0, float((height**2 + width**2) ** 0.5))
        for subject in subjects:
            for obj in objects:
                sbox, obox = _box(subject), _box(obj)
                if sbox is None or obox is None:
                    continue
                if relation_type == "below_and_horizontal_overlap":
                    overlap = _horizontal_overlap_ratio(sbox, obox)
                    below = _center(sbox)[1] > _center(obox)[1]
                    score = overlap if below else 0.0
                    pair_scores.append(_PairScore(score, {"horizontal_overlap": overlap, "subject_below": below}))
                elif relation_type == "near":
                    sx, sy = _center(sbox)
                    ox, oy = _center(obox)
                    distance_ratio = (((sx - ox) ** 2 + (sy - oy) ** 2) ** 0.5) / diag
                    threshold = _float_param(
                        check.params,
                        "near_distance_ratio",
                        self.defaults.get("near_distance_ratio", 0.30),
                    )
                    # Generic relation gating below uses score>=0.5.  Scale the
                    # score so that this boundary corresponds exactly to the
                    # configured distance threshold.  The previous formula
                    # made 0.30 behave like 0.15 (the threshold was applied
                    # once here and a second time by the 0.5 gate).
                    center_score = max(
                        0.0,
                        1.0 - distance_ratio / max(2.0 * threshold, 1e-6),
                    )
                    object_width = max(1.0, obox[2] - obox[0])
                    object_height = max(1.0, obox[3] - obox[1])
                    object_diag = max(1.0, float((object_width**2 + object_height**2) ** 0.5))
                    edge_gap = _box_edge_gap(sbox, obox)
                    edge_gap_machine_ratio = edge_gap / object_diag
                    edge_threshold = _float_param(
                        check.params,
                        "near_edge_gap_machine_ratio",
                        self.defaults.get("near_edge_gap_machine_ratio", 0.35),
                    )
                    edge_score = max(
                        0.0,
                        1.0
                        - edge_gap_machine_ratio / max(2.0 * edge_threshold, 1e-6),
                    )
                    score = max(center_score, edge_score)
                    pair_scores.append(
                        _PairScore(
                            score,
                            {
                                "distance_ratio": distance_ratio,
                                "threshold": threshold,
                                "effective_pass_distance_ratio": threshold,
                                "center_score": center_score,
                                "edge_gap_pixels": edge_gap,
                                "edge_gap_machine_ratio": edge_gap_machine_ratio,
                                "edge_gap_machine_threshold": edge_threshold,
                                "edge_score": edge_score,
                                "near_method": (
                                    "center_distance"
                                    if center_score >= edge_score
                                    else "machine_edge_danger_zone"
                                ),
                            },
                        )
                    )
                elif relation_type in {"overlap", "blocks_region"}:
                    iou = _mask_iou(subject.mask, obj.mask)
                    subject_overlap = _subject_overlap(subject.mask, obj.mask)
                    box_overlap = _box_overlap_ratio(sbox, obox)
                    score = max(iou, subject_overlap, box_overlap)
                    pair_scores.append(
                        _PairScore(
                            score,
                            {
                                "iou": iou,
                                "subject_overlap": subject_overlap,
                                "box_overlap": box_overlap,
                            },
                        )
                    )
                elif relation_type == "inside":
                    overlap = _subject_overlap(subject.mask, obj.mask)
                    pair_scores.append(_PairScore(overlap, {"subject_inside_ratio": overlap}))

        if not pair_scores:
            return RelationEvidence(relation_type=relation_type, passed=False, score=0.0, details={})
        best = max(pair_scores, key=lambda item: item.score)
        if relation_type == "below_and_horizontal_overlap":
            threshold = _float_param(
                check.params,
                "horizontal_overlap_threshold",
                self.defaults.get("horizontal_overlap_threshold", 0.25),
            )
        elif relation_type in {"overlap", "blocks_region"}:
            threshold = _float_param(
                check.params,
                "overlap_threshold",
                self.defaults.get("overlap_threshold", 0.10),
            )
        elif relation_type == "inside":
            threshold = _float_param(
                check.params,
                "inside_threshold",
                self.defaults.get("inside_threshold", 0.50),
            )
        else:
            threshold = 0.5
        return RelationEvidence(
            relation_type=relation_type,
            passed=best.score >= threshold,
            score=min(1.0, max(0.0, best.score)),
            details={
                **best.details,
                **near_subject_filter_details,
                "pass_threshold": threshold,
            },
        )
