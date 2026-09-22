"""Agent层标准化数据契约。

所有模块输出统一为 DetectionEvent / WorkOrder 两类JSON对象，
供前端（实时告警、工单管理、统计分析、系统配置）直接消费。
字段说明见 docs/AGENT_PROTOCOL.md。
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from site_safety.schemas import AbsenceStatus

SCHEMA_VERSION = "1.0"

DataMode = Literal["realtime", "offline"]
DeviceType = Literal["fixed_camera", "drone", "mobile", "offline_upload"]
RiskLevel = Literal["critical", "major", "general", "info", "pending_review"]
ReviewStatus = Literal["pending", "confirmed", "rejected", "auto_closed"]
WorkOrderStatus = Literal[
    "pending_confirmation",
    "confirmed",
    "assigned",
    "rectifying",
    "rectified",
    "closed",
    "rejected_false_alarm",
]

RISK_LEVEL_ZH: Dict[str, str] = {
    "critical": "重大风险",
    "major": "较大风险",
    "general": "一般风险",
    "info": "提示信息",
    "pending_review": "待人工复核",
}


class RoadContext(BaseModel):
    road_name: Optional[str] = None
    section: Optional[str] = None
    direction: Optional[str] = None
    lane: Optional[str] = None
    chainage: Optional[str] = None
    location_source: str = "unknown"


class DeviceInfo(BaseModel):
    device_id: str = "OFFLINE-UPLOAD"
    device_type: DeviceType = "offline_upload"
    site_id: str = "SITE-DEFAULT"
    location_desc: str = ""
    road_context: RoadContext = Field(default_factory=RoadContext)


class TimeInfo(BaseModel):
    # offline数据可能无法得知拍摄时间，captured_at允许为空
    captured_at: Optional[str] = None
    detected_at: str
    reported_at: str
    processing_ms: Optional[int] = None


class MediaInfo(BaseModel):
    image_path: str
    image_width: int
    image_height: int
    # realtime流媒体专用；offline为None
    frame_id: Optional[str] = None
    stream_ref: Optional[str] = None


class GeometryInfo(BaseModel):
    """掩码与定位坐标。像素坐标以原图左上角为原点。"""

    bbox_xyxy: Optional[List[float]] = None
    bbox_xyxy_norm: Optional[List[float]] = None
    # 风险区域掩码的多边形轮廓（像素坐标，可能多个连通域）
    mask_polygons: List[List[List[float]]] = Field(default_factory=list)
    mask_path: Optional[str] = None
    overlay_path: Optional[str] = None
    crop_path: Optional[str] = None


class RegulationRef(BaseModel):
    regulation_id: str
    name_zh: str
    clause: str = ""
    requirement_zh: str = ""
    source_url: str = ""
    version: str = ""
    applicability: str = ""
    source_file: str = ""
    source_sha256: str = ""
    citation_status: str = "reference_only_not_violation_finding"


class RiskFinding(BaseModel):
    evidence_state: Dict[str, Any] = Field(default_factory=dict)
    risk_id: str
    risk_name_zh: str
    verified: bool
    confidence: float = Field(ge=0.0, le=1.0)
    absence_status: AbsenceStatus = "not_applicable"
    risk_level: RiskLevel
    risk_level_zh: str
    knowledge_references: List[Dict[str, Any]] = Field(default_factory=list)
    regulation_ids: List[str] = Field(default_factory=list)
    regulations: List[RegulationRef] = Field(default_factory=list)
    geometry: GeometryInfo = Field(default_factory=GeometryInfo)
    visible_evidence: List[str] = Field(default_factory=list)
    counter_evidence: List[str] = Field(default_factory=list)
    risk_description: str = ""
    uncertainties: List[str] = Field(default_factory=list)
    manual_review_required: bool = False
    # 现场处置建议（风险推理Agent按risk_id从处置动作库附带）
    disposal_recommendations: List[str] = Field(default_factory=list)
    # 生成工单后回填；未生成为None
    work_order_id: Optional[str] = None


class ReviewInfo(BaseModel):
    status: ReviewStatus = "pending"
    reviewer: Optional[str] = None
    reviewed_at: Optional[str] = None
    comment: str = ""


class PipelineInfo(BaseModel):
    config_name: str = ""
    job_id: Optional[str] = None
    mllm_model: str = ""
    output_dir: str = ""
    evidence_path: Optional[str] = None
    visual_verification_path: Optional[str] = None


class DetectionEvent(BaseModel):
    assessment_quality: Dict[str, Any] = Field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION
    event_id: str
    data_mode: DataMode
    device: DeviceInfo = Field(default_factory=DeviceInfo)
    time: TimeInfo
    media: MediaInfo
    scene_summary: str = ""
    overall_has_anomaly: bool = False
    risks: List[RiskFinding] = Field(default_factory=list)
    pipeline: PipelineInfo = Field(default_factory=PipelineInfo)
    review: ReviewInfo = Field(default_factory=ReviewInfo)


class WorkOrderHistoryItem(BaseModel):
    at: str
    from_status: Optional[str] = None
    to_status: str
    by: str = "system"
    note: str = ""


class WorkOrder(BaseModel):
    schema_version: str = SCHEMA_VERSION
    work_order_id: str
    event_id: str
    risk_id: str
    risk_name_zh: str
    risk_level: RiskLevel
    risk_level_zh: str
    status: WorkOrderStatus = "pending_confirmation"
    created_at: str
    due_at: Optional[str] = None
    site_id: str = "SITE-DEFAULT"
    device_id: str = "OFFLINE-UPLOAD"
    assignee: Optional[str] = None
    notify_targets: List[str] = Field(default_factory=list)
    disposal_recommendations: List[str] = Field(default_factory=list)
    rectification_note: str = ""
    evidence_images: List[str] = Field(default_factory=list)
    history: List[WorkOrderHistoryItem] = Field(default_factory=list)


class ConfirmationRequest(BaseModel):
    """协同响应Agent发给安全员的确认请求（待复核队列条目）。"""

    schema_version: str = SCHEMA_VERSION
    request_id: str
    event_id: str
    risk_id: str
    risk_name_zh: str
    reason: str
    model_verified: bool = False
    model_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    model_judgment: str = ""
    visible_evidence: List[str] = Field(default_factory=list)
    counter_evidence: List[str] = Field(default_factory=list)
    absence_status: AbsenceStatus = "not_applicable"
    crop_path: Optional[str] = None
    overlay_path: Optional[str] = None
    # 原图路径：掩码证据缺失时前端用它兜底展示
    image_path: Optional[str] = None
    created_at: str
    status: ReviewStatus = "pending"


class ThresholdProposal(BaseModel):
    """复盘学习Agent生成的阈值调整建议，须人工审批后方可生效。"""

    schema_version: str = SCHEMA_VERSION
    proposal_id: str
    risk_id: str
    risk_name_zh: str
    false_alarm_rate: float = Field(ge=0.0, le=1.0)
    sample_count: int
    # 建议的最低自动确认置信度：verified且低于此值将被降级转人工
    proposed_min_verified_confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = ""
    status: Literal["pending", "approved", "rejected"] = "pending"
    created_at: str = ""
    decided_by: Optional[str] = None
    decided_at: Optional[str] = None
    decision_note: str = ""


class CaseRecord(BaseModel):
    """复盘学习Agent写入案例库的一条记录。"""

    schema_version: str = SCHEMA_VERSION
    case_id: str
    event_id: str
    risk_id: str
    risk_name_zh: str
    model_verified: bool
    model_confidence: float
    human_verdict: Literal["confirmed", "rejected"]
    reviewer: str = ""
    comment: str = ""
    image_path: str = ""
    crop_path: Optional[str] = None
    recorded_at: str = ""
    lessons: List[str] = Field(default_factory=list)
