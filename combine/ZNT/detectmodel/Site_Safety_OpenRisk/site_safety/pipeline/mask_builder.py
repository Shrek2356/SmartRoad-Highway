from __future__ import annotations

from typing import Dict, Iterable, List

import numpy as np
from PIL import Image, ImageFilter

from site_safety.adapters.base import MaskInstance
from site_safety.schemas import RiskCandidate
from site_safety.utils.image import mask_box, union_masks


class RiskMaskBuilder:
    def __init__(self, defaults: dict | None = None) -> None:
        self.defaults = defaults or {}

    def build(
        self,
        risk: RiskCandidate,
        by_task: Dict[str, List[MaskInstance]],
        shape: tuple[int, int],
    ) -> np.ndarray:
        all_items = [item for task in risk.sam3_tasks for item in by_task.get(task.task_id, [])]
        subjects = [item for item in all_items if item.role == "subject"]
        objects = [item for item in all_items if item.role in {"hazard_source", "region", "evidence", "protective_item"}]
        strategy = risk.mask_strategy
        if strategy == "subject_only" or strategy == "missing_subject":
            return union_masks((x.mask for x in subjects), shape)
        if strategy == "object_only":
            return union_masks((x.mask for x in objects), shape)
        if strategy == "intersection":
            if not subjects or not objects:
                return union_masks((x.mask for x in all_items), shape)
            subject_mask = union_masks((x.mask for x in subjects), shape)
            object_mask = union_masks((x.mask for x in objects), shape)
            return np.logical_and(subject_mask > 0, object_mask > 0).astype(np.uint8)
        if strategy == "projected_below":
            base = union_masks((x.mask for x in all_items), shape)
            height, width = shape
            projected = np.zeros(shape, dtype=np.uint8)
            subject_boxes = [item.box_xyxy or mask_box(item.mask) for item in subjects]
            subject_boxes = [box for box in subject_boxes if box is not None]
            for item in objects:
                box = item.box_xyxy or mask_box(item.mask)
                if box is None:
                    continue
                x1, y1, x2, y2 = [int(v) for v in box]
                object_height = max(1, y2 - y1)
                width_expand_ratio = float(self.defaults.get("projected_width_expand_ratio", 0.15))
                expand = max(4, int((x2 - x1) * width_expand_ratio))
                max_by_object = int(
                    object_height * float(self.defaults.get("projected_max_object_height_ratio", 4.0))
                )
                max_by_image = int(
                    height * float(self.defaults.get("projected_max_image_height_ratio", 0.55))
                )
                projection_end = min(height, y2 + max(1, min(max_by_object, max_by_image)))
                overlapping_subjects = [
                    subject_box
                    for subject_box in subject_boxes
                    if _horizontal_box_overlap(subject_box, [x1 - expand, y2, x2 + expand, projection_end])
                ]
                if overlapping_subjects:
                    subject_bottom = max(int(subject_box[3]) for subject_box in overlapping_subjects)
                    projection_end = min(projection_end, subject_bottom + max(4, object_height // 4))
                projected[max(0, y2) : projection_end, max(0, x1 - expand) : min(width, x2 + expand)] = 1
            return np.maximum(base, projected)
        if strategy == "expanded_object_zone":
            source = union_masks((x.mask for x in objects), shape)
            if source.max() == 0:
                source = union_masks((x.mask for x in all_items), shape)
            pil = Image.fromarray((source * 255).astype(np.uint8), mode="L")
            kernel = 31 if min(shape) >= 128 else 15
            if kernel % 2 == 0:
                kernel += 1
            expanded = np.asarray(pil.filter(ImageFilter.MaxFilter(kernel))) > 0
            return expanded.astype(np.uint8)
        if strategy == "unmatched_subject":
            unmatched = []
            for subject in subjects:
                subject_box = subject.box_xyxy or mask_box(subject.mask)
                if subject_box is None:
                    continue
                sx1, sy1, sx2, sy2 = subject_box
                subject_height = max(1.0, sy2 - sy1)
                horizontal_margin = max(2.0, (sx2 - sx1) * 0.12)
                matched = False
                for obj in objects:
                    object_box = obj.box_xyxy or mask_box(obj.mask)
                    if object_box is None:
                        continue
                    ox = (object_box[0] + object_box[2]) / 2.0
                    oy = (object_box[1] + object_box[3]) / 2.0
                    if (
                        sx1 - horizontal_margin <= ox <= sx2 + horizontal_margin
                        and sy1 - subject_height * 0.15
                        <= oy
                        <= sy1 + subject_height * 0.45
                    ):
                        matched = True
                        break
                if not matched:
                    unmatched.append(subject)
            return union_masks((item.mask for item in unmatched), shape)
        return union_masks((x.mask for x in all_items), shape)


def _horizontal_box_overlap(a: list[float], b: list[float]) -> bool:
    return min(a[2], b[2]) > max(a[0], b[0])
