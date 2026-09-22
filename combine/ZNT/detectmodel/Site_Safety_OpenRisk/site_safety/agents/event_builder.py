"""把检测流水线输出目录转换为标准化DetectionEvent。

offline模式：输入为已完成的输出目录（含visual_verification.json与evidence.json）；
realtime模式：由流媒体工作进程逐帧调用，额外传入device与frame信息。
掩码多边形优先用cv2轮廓提取；cv2不可用时退化为bbox矩形。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image

from site_safety.agents.risk_reasoning import RiskReasoningAgent
from site_safety.agents.schemas import (
    DetectionEvent,
    DeviceInfo,
    GeometryInfo,
    MediaInfo,
    PipelineInfo,
    RiskFinding,
    TimeInfo,
)

try:  # pragma: no cover - 环境相关
    import cv2
except Exception:  # pragma: no cover
    cv2 = None


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _mask_polygons(mask_path: Path, *, epsilon_ratio: float = 0.01, max_polygons: int = 8) -> List[List[List[float]]]:
    """从二值掩码PNG提取简化多边形轮廓（像素坐标）。"""
    if cv2 is None or not mask_path.is_file():
        return []
    mask = np.array(Image.open(mask_path).convert("L"))
    binary = (mask > 127).astype(np.uint8)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:max_polygons]
    polygons: List[List[List[float]]] = []
    for contour in contours:
        if cv2.contourArea(contour) < 16:
            continue
        epsilon = epsilon_ratio * cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, epsilon, True)
        points = [[float(p[0][0]), float(p[0][1])] for p in approx]
        if len(points) >= 3:
            polygons.append(points)
    return polygons


def _union_box(boxes: List[List[float]]) -> Optional[List[float]]:
    valid = [b for b in boxes if b and len(b) == 4 and (b[2] > b[0] or b[3] > b[1])]
    if not valid:
        return None
    return [
        min(b[0] for b in valid),
        min(b[1] for b in valid),
        max(b[2] for b in valid),
        max(b[3] for b in valid),
    ]


def build_event_from_output_dir(
    output_dir: str | Path,
    reasoning: RiskReasoningAgent,
    *,
    data_mode: str = "offline",
    device: Optional[DeviceInfo] = None,
    captured_at: Optional[str] = None,
    frame_id: Optional[str] = None,
    stream_ref: Optional[str] = None,
    config_name: str = "",
    mllm_model: str = "",
) -> Optional[DetectionEvent]:
    """输出目录 → DetectionEvent；缺少visual_verification.json时返回None。"""
    output_dir = Path(output_dir)
    vv_path = output_dir / "visual_verification.json"
    result_path = output_dir / "result.json"
    if not vv_path.is_file():
        return None
    visual = json.loads(vv_path.read_text(encoding="utf-8"))
    evidence_path = output_dir / "evidence.json"
    evidences: Dict[str, Dict[str, Any]] = {}
    if evidence_path.is_file():
        for item in json.loads(evidence_path.read_text(encoding="utf-8")):
            evidences[item["risk_id"]] = item

    image_path = ""
    scene_summary = ""
    if result_path.is_file():
        result = json.loads(result_path.read_text(encoding="utf-8"))
        image_path = result.get("image_path", "")
        scene_summary = (result.get("first_pass") or {}).get("scene_summary", "")
    width = height = 0
    if image_path and Path(image_path).is_file():
        with Image.open(image_path) as img:
            width, height = img.size

    detected_at = datetime.fromtimestamp(vv_path.stat().st_mtime).astimezone().isoformat(
        timespec="seconds"
    )
    risks: List[RiskFinding] = []
    for item in visual.get("final_risks", []):
        evidence = evidences.get(item.get("risk_id"), {})
        boxes = [seg.get("box_xyxy") for seg in evidence.get("segmentations", [])]
        bbox = _union_box([b for b in boxes if b])
        mask_rel = evidence.get("risk_mask_path")
        if mask_rel and (output_dir / mask_rel).is_file():
            # Report the risk mask extent, not the union with its road/context entities.
            with Image.open(output_dir / mask_rel) as mask_image:
                mask_bbox = mask_image.convert("L").point(lambda value: 255 if value > 127 else 0).getbbox()
            bbox = list(mask_bbox) if mask_bbox else None
        bbox_norm = None
        if bbox and width and height:
            bbox_norm = [
                round(bbox[0] / width, 4),
                round(bbox[1] / height, 4),
                round(bbox[2] / width, 4),
                round(bbox[3] / height, 4),
            ]
        mask_rel = evidence.get("risk_mask_path")
        geometry = GeometryInfo(
            bbox_xyxy=bbox,
            bbox_xyxy_norm=bbox_norm,
            mask_polygons=_mask_polygons(output_dir / mask_rel) if mask_rel else [],
            mask_path=str(output_dir / mask_rel) if mask_rel else None,
            overlay_path=(
                str(output_dir / evidence["overlay_path"]) if evidence.get("overlay_path") else None
            ),
            crop_path=(
                str(output_dir / evidence["crop_path"]) if evidence.get("crop_path") else None
            ),
        )
        finding = RiskFinding(
            risk_id=item.get("risk_id", "unknown"),
            risk_name_zh=item.get("risk_name_zh", item.get("risk_id", "unknown")),
            verified=bool(item.get("verified")),
            confidence=float(item.get("confidence", 0.0)),
            absence_status=item.get("absence_status", "not_applicable"),
            risk_level="info",
            risk_level_zh="提示信息",
            geometry=geometry,
            visible_evidence=item.get("visible_evidence", []),
            counter_evidence=item.get("counter_evidence", []),
            risk_description=item.get("risk_description", ""),
            evidence_state=item.get("evidence_state", {}),
            uncertainties=item.get("uncertainties", []),
            manual_review_required=bool(item.get("manual_review_required")),
        )
        risks.append(reasoning.attach(finding))

    event = DetectionEvent(
        assessment_quality=visual.get("assessment_quality", {}),
        event_id=f"EVT-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}",
        data_mode=data_mode,  # type: ignore[arg-type]
        device=device or DeviceInfo(),
        time=TimeInfo(
            captured_at=captured_at,
            detected_at=detected_at,
            reported_at=_now_iso(),
        ),
        media=MediaInfo(
            image_path=image_path,
            image_width=width,
            image_height=height,
            frame_id=frame_id,
            stream_ref=stream_ref,
        ),
        scene_summary=scene_summary,
        overall_has_anomaly=bool(visual.get("overall_has_anomaly")),
        risks=risks,
        pipeline=PipelineInfo(
            config_name=config_name,
            mllm_model=mllm_model,
            output_dir=str(output_dir),
            evidence_path=str(evidence_path) if evidence_path.is_file() else None,
            visual_verification_path=str(vv_path),
        ),
    )

    if reasoning.domain == "road":
        from site_safety.agents.road_knowledge import attach_road_references
        attach_road_references(event, output_dir)
    return event
