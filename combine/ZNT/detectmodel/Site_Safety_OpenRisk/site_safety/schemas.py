from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


RiskStatus = Literal["present", "absent", "uncertain"]
AbsenceStatus = Literal[
    "not_applicable",
    "confirmed_absent",
    "not_observed",
    "occluded",
]


class ScreeningRegion(BaseModel):
    region_id: str
    bbox_xyxy: List[float] = Field(min_length=4, max_length=4)
    score: float = Field(ge=0.0, le=1.0)
    label: Optional[str] = None
    coordinate_space: Literal["pixel_xyxy", "normalized_xyxy"] = "pixel_xyxy"

    @field_validator("bbox_xyxy")
    @classmethod
    def validate_box(cls, value: List[float]) -> List[float]:
        x1, y1, x2, y2 = value
        if x2 <= x1 or y2 <= y1:
            raise ValueError("bbox_xyxy must satisfy x2>x1 and y2>y1")
        return value


class ScreeningTrigger(BaseModel):
    """Calibrated routing metadata from a high-recall realtime detector."""

    triggered: bool = True
    anomaly_score: float = Field(ge=0.0, le=1.0)
    suspected_regions: List[ScreeningRegion] = Field(default_factory=list)
    suspected_concepts: List[str] = Field(default_factory=list)
    source_model: str
    calibration_version: Optional[str] = None
    reason: Optional[str] = None


class ScreeningAssessment(BaseModel):
    screening_consistency: Literal[
        "supported", "unsupported", "uncertain", "not_provided"
    ] = "not_provided"
    overall_status: Literal[
        "confirmed_anomaly", "suspected_anomaly", "no_visible_anomaly", "not_evaluated"
    ] = "not_evaluated"


class SAM3Task(BaseModel):
    task_id: str
    role: Literal["subject", "hazard_source", "protective_item", "region", "evidence", "other"] = "other"
    prompt: str = Field(min_length=1)
    expected_count: Optional[int] = None
    min_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class RelationCheck(BaseModel):
    type: Literal[
        "none",
        "below_and_horizontal_overlap",
        "near",
        "inside",
        "overlap",
        "missing",
        "missing_association",
        "blocks_region",
    ] = "none"
    subject_task_ids: List[str] = Field(default_factory=list)
    object_task_ids: List[str] = Field(default_factory=list)
    # Known geometric thresholds are numeric, while multimodal models may add
    # descriptive metadata such as missing_item or relation notes.
    params: Dict[str, Any] = Field(default_factory=dict)


class RiskCandidate(BaseModel):
    region_xyxy: Optional[List[float]] = None
    localization_plan_status: str = "legacy"
    risk_id: str
    risk_name_zh: str
    status: RiskStatus
    confidence: float = Field(ge=0.0, le=1.0)
    observed_facts: List[str] = Field(default_factory=list)
    counter_evidence: List[str] = Field(default_factory=list)
    sam3_tasks: List[SAM3Task] = Field(default_factory=list)
    relation_checks: List[RelationCheck] = Field(default_factory=list)
    mask_strategy: Literal[
        "entity_union",
        "subject_only",
        "object_only",
        "intersection",
        "projected_below",
        "missing_subject",
        "expanded_object_zone",
        "unmatched_subject",
    ] = "entity_union"
    uncertainties: List[str] = Field(default_factory=list)
    risk_type: Optional[str] = None
    target_entities: List[Dict[str, Any]] = Field(default_factory=list)
    relation_spec: Dict[str, Any] = Field(default_factory=dict)


class FirstPassResponse(BaseModel):
    assessment_quality: Dict[str, Any] = Field(default_factory=dict)
    scene_summary: str
    has_possible_anomaly: bool
    candidate_assessments: List[RiskCandidate]
    open_discoveries: List[RiskCandidate] = Field(default_factory=list)

    @model_validator(mode="after")
    def ensure_unique_risk_ids(self) -> "FirstPassResponse":
        risks = self.candidate_assessments + self.open_discoveries
        ids = [x.risk_id for x in risks]
        if len(ids) != len(set(ids)):
            raise ValueError("risk_id must be unique in one response")
        task_ids = [task.task_id for risk in risks for task in risk.sam3_tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("SAM3 task_id must be globally unique in one response")
        for risk in risks:
            risk_task_ids = {task.task_id for task in risk.sam3_tasks}
            for check in risk.relation_checks:
                referenced = set(check.subject_task_ids + check.object_task_ids)
                unknown = referenced - risk_task_ids
                if unknown:
                    raise ValueError(
                        f"risk {risk.risk_id} relation references unknown task_id(s): {sorted(unknown)}"
                    )
        return self


class SegmentationRecord(BaseModel):
    task_id: str
    role: str
    prompt: str
    instance_index: int
    score: float = Field(ge=0.0, le=1.0)
    box_xyxy: List[float]
    mask_path: str
    clip_consistency_score: Optional[float] = None


class RelationEvidence(BaseModel):
    relation_type: str
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    details: Dict[str, Any] = Field(default_factory=dict)


class RiskEvidence(BaseModel):
    risk_id: str
    risk_name_zh: str
    first_pass_status: RiskStatus
    first_pass_confidence: float
    observed_facts: List[str]
    counter_evidence: List[str] = Field(default_factory=list)
    segmentations: List[SegmentationRecord]
    relations: List[RelationEvidence]
    mask_strategy: str
    risk_mask_path: Optional[str] = None
    overlay_path: Optional[str] = None
    crop_path: Optional[str] = None
    evidence_score: float = Field(ge=0.0, le=1.0)
    uncertainties: List[str] = Field(default_factory=list)


class FinalRisk(BaseModel):
    road_impact_verdict: Literal['supported', 'unrelated', 'uncertain'] = 'uncertain'
    localization_verdict: Literal["consistent", "inconsistent", "unavailable", "uncertain"] = "uncertain"
    visual_verdict: Literal["supported", "refuted", "uncertain"] = "uncertain"
    evidence_state: Dict[str, Any] = Field(default_factory=dict)
    risk_id: str
    risk_name_zh: str
    verified: bool
    confidence: float = Field(ge=0.0, le=1.0)
    visible_evidence: List[str] = Field(default_factory=list)
    counter_evidence: List[str] = Field(default_factory=list)
    risk_description: str
    uncertainties: List[str] = Field(default_factory=list)
    manual_review_required: bool = False
    absence_status: AbsenceStatus = "not_applicable"

    @field_validator("absence_status", mode="before")
    @classmethod
    def normalize_absence_status(cls, value: Any) -> str:
        normalized = str(value or "not_applicable").strip().lower()
        aliases = {
            "confirmed missing": "confirmed_absent",
            "confirmed_missing": "confirmed_absent",
            "确认缺失": "confirmed_absent",
            "not visible": "not_observed",
            "not_visible": "not_observed",
            "未观察到": "not_observed",
            "遮挡": "occluded",
            "被遮挡": "occluded",
            "n/a": "not_applicable",
            "none": "not_applicable",
        }
        return aliases.get(normalized, normalized)


class SecondPassResponse(BaseModel):
    assessment_quality: Dict[str, Any] = Field(default_factory=dict)
    overall_has_anomaly: bool
    overall_summary: str
    final_risks: List[FinalRisk]


class ReportRiskSection(BaseModel):
    evidence_state: Dict[str, Any] = Field(default_factory=dict)
    risk_id: str
    risk_name_zh: str
    verified: bool
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    evidence: List[str] = Field(default_factory=list)
    counter_evidence: List[str] = Field(default_factory=list)
    uncertainties: List[str] = Field(default_factory=list)
    manual_review_required: bool = False
    absence_status: AbsenceStatus = "not_applicable"
    management_notes: List[str] = Field(default_factory=list)


class ManagementReport(BaseModel):
    assessment_quality: Dict[str, Any] = Field(default_factory=dict)
    report_title: str = "道路风险检测报告"
    executive_summary: str
    risks: List[ReportRiskSection] = Field(default_factory=list)
    follow_up_actions: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    generated_by: Literal["glm", "qwen_local", "deterministic_template"] = "deterministic_template"


class InspectionResult(BaseModel):
    image_path: str
    output_dir: str
    first_pass: FirstPassResponse
    evidences: List[RiskEvidence]
    visual_verification: Optional[SecondPassResponse] = None
    # Backward-compatible alias retained for existing consumers.
    final_report: Optional[SecondPassResponse] = None
    management_report: Optional[ManagementReport] = None
    screening_trigger: Optional[ScreeningTrigger] = None
    screening_assessment: ScreeningAssessment = Field(default_factory=ScreeningAssessment)
