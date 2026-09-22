"""五类掩码分类映射器 + labelme JSON导出。

把检测流水线的产物（SAM3实体掩码 + 关系核验 + 证据门控结论）映射为
道路损毁论文的五类掩码体系，并导出与 gold100_workspace 兼容的 labelme JSON：

- RoadSupport            正常主体（道路本体，subject角色）
- DamageCore             道路本体损伤（坑槽/裂缝/沉陷等，且与道路关系核验通过）
- ConnectedHazard        与道路相邻/覆盖的异常（积水/落石/堆积物等，关系核验通过）
- IrrelevantAnomaly      无关异常（异常实体与道路的关系核验未通过，或开放发现无法挂接道路）
- IrrelevantBackground   背景（独立SAM3背景任务产生，扣除已标注区域）

不变式：视觉结论(verified/confidence/manual_review_required)由证据门控产生，
本模块只读，原样写入shape的flags与description，不做任何改判。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
from PIL import Image

FIVE_CLASSES = [
    "RoadSupport",
    "DamageCore",
    "ConnectedHazard",
    "IrrelevantAnomaly",
    "IrrelevantBackground",
]

LABELS_TXT = ["__ignore__"] + FIVE_CLASSES

# 关系核验里视为"实体与道路发生几何关联"的关系类型
_GEOMETRIC_RELATIONS = {
    "overlap",
    "inside",
    "blocks_region",
    "near",
    "below_and_horizontal_overlap",
}

# 兜底像素判定：无关系核验时，异常掩码与道路掩码的重叠占比阈值
_PIXEL_CONNECT_RATIO = 0.02


def load_catalog_classes(catalog_path: str | Path) -> Dict[str, str]:
    """risk_id -> annotation_class（DamageCore/ConnectedHazard）。"""
    catalog = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    mapping: Dict[str, str] = {}
    for item in catalog.get("core", []):
        cls = item.get("annotation_class")
        if item.get("risk_id") and cls in FIVE_CLASSES:
            mapping[str(item["risk_id"])] = str(cls)
    return mapping


def _load_mask(output_dir: Path, mask_path: str) -> Optional[np.ndarray]:
    if not mask_path:
        return None
    path = output_dir / mask_path
    if not path.is_file():
        return None
    return (np.asarray(Image.open(path).convert("L")) > 127).astype(np.uint8)


def mask_to_polygons(
    mask: np.ndarray,
    *,
    min_area: float = 64.0,
    epsilon_ratio: float = 0.008,
) -> List[List[List[float]]]:
    """二值掩码 -> 简化多边形列表（每个外轮廓一个多边形）。"""
    import cv2

    contours, _ = cv2.findContours(
        (mask > 0).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    polygons: List[List[List[float]]] = []
    for contour in contours:
        if cv2.contourArea(contour) < min_area:
            continue
        epsilon = epsilon_ratio * cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, epsilon, True)
        if len(approx) < 3:
            continue
        polygons.append([[float(p[0][0]), float(p[0][1])] for p in approx])
    return polygons


def _relation_connected(relations: Sequence[Dict[str, Any]]) -> Optional[bool]:
    """关系核验结论：True/False；无几何关系核验时返回None。"""
    geometric = [r for r in relations if r.get("relation_type") in _GEOMETRIC_RELATIONS]
    if not geometric:
        return None
    return any(bool(r.get("passed")) for r in geometric)


def _pixel_connected(hazard_mask: np.ndarray, road_mask: Optional[np.ndarray]) -> bool:
    if road_mask is None:
        return False
    inter = np.logical_and(hazard_mask > 0, road_mask > 0).sum()
    denom = max(1, int((hazard_mask > 0).sum()))
    return (inter / denom) >= _PIXEL_CONNECT_RATIO


def _is_road_prompt(prompt: str) -> bool:
    lowered = prompt.lower()
    return any(k in lowered for k in ("road", "pavement", "asphalt", "street", "highway"))


def build_shapes_from_result(
    result: Dict[str, Any],
    output_dir: str | Path,
    catalog_classes: Dict[str, str],
    *,
    min_polygon_area: float = 64.0,
) -> List[Dict[str, Any]]:
    """把单图 InspectionResult(dict) 映射为labelme shapes（不含背景类）。"""
    output_dir = Path(output_dir)
    final_by_risk: Dict[str, Dict[str, Any]] = {}
    for risk in ((result.get("final_report") or {}).get("final_risks") or []):
        final_by_risk[str(risk.get("risk_id"))] = risk

    shapes: List[Dict[str, Any]] = []
    seen_instances: set[tuple[str, int]] = set()

    for evidence in result.get("evidences", []):
        risk_id = str(evidence.get("risk_id"))
        final = final_by_risk.get(risk_id, {})
        base_class = catalog_classes.get(risk_id)  # None => 开放发现/未登记
        connected = _relation_connected(evidence.get("relations", []))

        # 道路主体掩码（用于像素兜底判定）
        road_masks = []
        for record in evidence.get("segmentations", []):
            if record.get("role") == "subject" and _is_road_prompt(record.get("prompt", "")):
                mask = _load_mask(output_dir, record.get("mask_path", ""))
                if mask is not None:
                    road_masks.append(mask)
        road_union = None
        if road_masks:
            road_union = np.zeros_like(road_masks[0])
            for mask in road_masks:
                road_union = np.maximum(road_union, mask)

        facts = "；".join(evidence.get("observed_facts", [])[:4])
        risk_desc = str(final.get("risk_description", "")).strip()
        verified = bool(final.get("verified", False))
        confidence = float(final.get("confidence", evidence.get("first_pass_confidence", 0.0)))
        manual_review = bool(final.get("manual_review_required", True))
        desc_common = (
            f"{risk_id}|{evidence.get('risk_name_zh', '')}"
            f"; facts: {facts}"
            + (f"; risk: {risk_desc}" if risk_desc else "")
            + f"; verified={verified}, conf={confidence:.2f}, manual_review={manual_review}"
        )

        for record in evidence.get("segmentations", []):
            key = (str(record.get("task_id")), int(record.get("instance_index", 0)))
            if key in seen_instances:
                continue
            role = str(record.get("role", "other"))
            prompt = str(record.get("prompt", ""))
            mask = _load_mask(output_dir, record.get("mask_path", ""))
            if mask is None:
                continue

            if role == "subject" and _is_road_prompt(prompt):
                label = "RoadSupport"
            elif role in {"hazard_source", "evidence", "other", "region"}:
                is_connected = connected
                if is_connected is None:
                    is_connected = _pixel_connected(mask, road_union)
                if not is_connected:
                    label = "IrrelevantAnomaly"
                elif base_class in {"DamageCore", "ConnectedHazard"}:
                    label = base_class
                else:
                    label = "ConnectedHazard"
            else:
                # protective_item等在道路场景无对应类别
                continue

            seen_instances.add(key)
            for points in mask_to_polygons(mask, min_area=min_polygon_area):
                shapes.append(
                    {
                        "label": label,
                        "points": points,
                        "group_id": None,
                        "shape_type": "polygon",
                        "flags": {
                            "verified": verified,
                            "manual_review_required": manual_review,
                        },
                        "description": f"{desc_common}; entity: {prompt}"
                        f" (sam3_score={float(record.get('score', 0.0)):.2f})",
                    }
                )
    return shapes


def build_background_shapes(
    sam3,
    image: Image.Image,
    occupied: Optional[np.ndarray],
    *,
    prompts: Sequence[str] = ("vegetation", "sky", "building"),
    min_score: float = 0.30,
    min_area_ratio: float = 0.005,
    min_polygon_area: float = 64.0,
) -> List[Dict[str, Any]]:
    """独立SAM3背景任务 -> IrrelevantBackground shapes（扣除已标注区域）。"""
    from site_safety.schemas import SAM3Task

    height, width = image.height, image.width
    min_area = min_area_ratio * height * width
    shapes: List[Dict[str, Any]] = []
    sam3.set_image(image)
    for index, prompt in enumerate(prompts):
        task = SAM3Task(task_id=f"background_{index:02d}", role="region", prompt=str(prompt))
        for item in sam3.segment(task):
            if item.score < min_score:
                continue
            mask = (item.mask > 0).astype(np.uint8)
            if occupied is not None:
                mask = np.logical_and(mask > 0, occupied == 0).astype(np.uint8)
            if mask.sum() < min_area:
                continue
            for points in mask_to_polygons(mask, min_area=min_polygon_area):
                shapes.append(
                    {
                        "label": "IrrelevantBackground",
                        "points": points,
                        "group_id": None,
                        "shape_type": "polygon",
                        "flags": {},
                        "description": f"background: {prompt} (sam3_score={float(item.score):.2f})",
                    }
                )
    return shapes


def shapes_occupancy(shapes: Sequence[Dict[str, Any]], height: int, width: int) -> np.ndarray:
    """shapes并集的占用掩码（供背景扣除）。"""
    import cv2

    occupied = np.zeros((height, width), dtype=np.uint8)
    for shape in shapes:
        points = np.asarray(shape.get("points", []), dtype=np.int32)
        if len(points) >= 3:
            cv2.fillPoly(occupied, [points], 1)
    return occupied


def write_labelme_json(
    target_path: str | Path,
    image_filename: str,
    shapes: List[Dict[str, Any]],
    height: int,
    width: int,
    *,
    extra_flags: Optional[Dict[str, Any]] = None,
) -> None:
    payload = {
        "version": "6.3.1",
        "flags": {"auto_drafted": True, **(extra_flags or {})},
        "shapes": shapes,
        "imagePath": image_filename,
        "imageData": None,
        "imageHeight": int(height),
        "imageWidth": int(width),
    }
    Path(target_path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def write_labels_txt(workspace: str | Path) -> None:
    Path(workspace, "labels.txt").write_text("\n".join(LABELS_TXT) + "\n", encoding="utf-8")
