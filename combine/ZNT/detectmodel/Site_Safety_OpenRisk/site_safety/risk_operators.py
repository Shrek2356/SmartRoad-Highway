from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import yaml
from pydantic import BaseModel, Field, model_validator


TaskRole = Literal[
    "subject", "hazard_source", "protective_item", "region", "evidence", "other"
]
RelationType = Literal[
    "none",
    "below_and_horizontal_overlap",
    "near",
    "inside",
    "overlap",
    "missing",
    "missing_association",
    "blocks_region",
]
MaskStrategy = Literal[
    "entity_union",
    "subject_only",
    "object_only",
    "intersection",
    "projected_below",
    "missing_subject",
    "expanded_object_zone",
    "unmatched_subject",
]


class OperatorTask(BaseModel):
    role: TaskRole
    prompt: str = Field(min_length=1)
    expected_count: int = Field(default=1, ge=1)
    min_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class OperatorRelation(BaseModel):
    type: RelationType = "none"
    task_scope: Literal["all", "canonical"] = "all"
    subject_roles: List[TaskRole] = Field(default_factory=lambda: ["subject", "evidence"])
    object_roles: List[TaskRole] = Field(
        default_factory=lambda: ["hazard_source", "protective_item", "region"]
    )
    params: Dict[str, Any] = Field(default_factory=dict)
    visibility_aware_missing: bool = False


class RiskPromotion(BaseModel):
    summary_any: List[str] = Field(default_factory=list)
    summary_all_of_any: List[List[str]] = Field(default_factory=list)
    facts_any: List[str] = Field(default_factory=list)
    only_status: Optional[Literal["present", "absent", "uncertain"]] = None
    target_status: Optional[Literal["present", "absent", "uncertain"]] = None
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    uncertainty_message: str = ""

    @model_validator(mode="after")
    def require_signal(self) -> "RiskPromotion":
        if not self.summary_any and not self.summary_all_of_any and not self.facts_any:
            raise ValueError(
                "promotion must define summary_any, summary_all_of_any, or facts_any"
            )
        return self


class RiskOperator(BaseModel):
    name_zh: str = ""
    tasks: List[OperatorTask] = Field(min_length=1)
    relation: OperatorRelation = Field(default_factory=OperatorRelation)
    mask_strategy: MaskStrategy = "entity_union"
    force_canonical_tasks: bool = False
    promotion: Optional[RiskPromotion] = None


class AnchorRule(BaseModel):
    all_of_any: List[List[str]] = Field(min_length=1)


class OpenDiscoveryRule(BaseModel):
    rule_id: str
    match_any: List[str] = Field(default_factory=list)
    match_all: List[str] = Field(default_factory=list)
    all_of_any: List[List[str]] = Field(default_factory=list)
    tasks: List[OperatorTask] = Field(min_length=1)
    relation: OperatorRelation = Field(default_factory=OperatorRelation)
    mask_strategy: MaskStrategy = "entity_union"

    @model_validator(mode="after")
    def require_match_terms(self) -> "OpenDiscoveryRule":
        if not self.match_any and not self.match_all and not self.all_of_any:
            raise ValueError(
                "open discovery rule must define match_any, match_all, or all_of_any"
            )
        return self


class RiskOperatorRegistry(BaseModel):
    version: int = Field(ge=1)
    operators: Dict[str, RiskOperator]
    discovery_retry_anchors: List[AnchorRule] = Field(default_factory=list)
    open_discovery_rules: List[OpenDiscoveryRule] = Field(default_factory=list)

    def is_anchor_scene(self, scene_summary: str) -> bool:
        return any(
            all(any(token in scene_summary for token in group) for group in rule.all_of_any)
            for rule in self.discovery_retry_anchors
        )

    def promote_candidates(
        self, payload: Dict[str, Any], scene_summary: str
    ) -> None:
        for item in payload.get("candidate_assessments", []) or []:
            if not isinstance(item, dict):
                continue
            operator = self.operators.get(str(item.get("risk_id") or ""))
            promotion = operator.promotion if operator else None
            if promotion is None:
                continue
            if promotion.only_status and item.get("status") != promotion.only_status:
                continue
            facts = " ".join(str(value) for value in item.get("observed_facts", []))
            if promotion.summary_any and not any(
                token in scene_summary for token in promotion.summary_any
            ):
                continue
            if promotion.summary_all_of_any and not all(
                any(token in scene_summary for token in group)
                for group in promotion.summary_all_of_any
            ):
                continue
            if promotion.facts_any and not any(
                token in facts for token in promotion.facts_any
            ):
                continue
            if promotion.target_status:
                item["status"] = promotion.target_status
            item["confidence"] = max(
                float(item.get("confidence") or 0.0), promotion.min_confidence
            )
            if promotion.uncertainty_message:
                uncertainties = item.setdefault("uncertainties", [])
                if promotion.uncertainty_message not in uncertainties:
                    uncertainties.append(promotion.uncertainty_message)

    def complete_candidate(self, item: Dict[str, Any]) -> None:
        if item.get("status") not in {"present", "uncertain"}:
            return
        risk_id = str(item.get("risk_id") or "")
        operator = self.operators.get(risk_id)
        if operator is None:
            return
        self._apply_operator(item, risk_id, operator)

    def complete_open_discovery(self, item: Dict[str, Any]) -> bool:
        searchable = " ".join(
            str(item.get(key) or "")
            for key in ("description", "risk_name_zh", "evidence", "discovery_type")
        )
        for rule in self.open_discovery_rules:
            matches_all = all(token in searchable for token in rule.match_all)
            matches_any = not rule.match_any or any(
                token in searchable for token in rule.match_any
            )
            matches_groups = all(
                any(token in searchable for token in group)
                for group in rule.all_of_any
            )
            if matches_all and matches_any and matches_groups:
                operator = RiskOperator(
                    tasks=rule.tasks,
                    relation=rule.relation,
                    mask_strategy=rule.mask_strategy,
                    force_canonical_tasks=True,
                )
                self._apply_operator(item, str(item["risk_id"]), operator)
                return True
        return False

    @staticmethod
    def _apply_operator(
        item: Dict[str, Any], risk_id: str, operator: RiskOperator
    ) -> None:
        tasks = list(item.get("sam3_tasks") or [])
        existing_roles = {
            str(task.get("role")) for task in tasks if isinstance(task, dict)
        }
        for index, task_spec in enumerate(operator.tasks, start=1):
            if (
                task_spec.role in existing_roles
                and not operator.force_canonical_tasks
            ):
                continue
            task_id = f"{risk_id}_auto_{index:02d}"
            if any(
                isinstance(task, dict) and task.get("task_id") == task_id
                for task in tasks
            ):
                continue
            tasks.append(
                {
                    "task_id": task_id,
                    "role": task_spec.role,
                    "prompt": task_spec.prompt,
                    "expected_count": task_spec.expected_count,
                    **(
                        {"min_score": task_spec.min_score}
                        if task_spec.min_score is not None
                        else {}
                    ),
                }
            )
        item["sam3_tasks"] = tasks
        item["mask_strategy"] = operator.mask_strategy

        relation = operator.relation
        if relation.type == "none":
            return
        relation_tasks = tasks
        if relation.task_scope == "canonical":
            relation_tasks = [
                task
                for task in tasks
                if str(task.get("task_id", "")).startswith(f"{risk_id}_auto_")
            ]
        subject_ids = [
            task["task_id"]
            for task in relation_tasks
            if task.get("role") in relation.subject_roles
        ]
        object_ids = [
            task["task_id"]
            for task in relation_tasks
            if task.get("role") in relation.object_roles
        ]
        params = dict(relation.params)
        if relation.visibility_aware_missing:
            facts = " ".join(str(value) for value in item.get("observed_facts", []))
            # “部分人员佩戴安全帽”等普通数量描述不能被误读成检查区
            # 可见性不足；只匹配明确描述遮挡或画质的短语。
            uncertain_visibility = any(
                token in facts
                for token in (
                    "遮挡",
                    "部分遮挡",
                    "局部遮挡",
                    "未完整可见",
                    "不清晰",
                    "看不清",
                    "无法确认",
                )
            )
            params["inspection_zone_visibility"] = (
                "partial" if uncertain_visibility else "clear"
            )
            protective_task = next(
                (
                    task
                    for task in reversed(relation_tasks)
                    if task.get("role") == "protective_item"
                ),
                None,
            )
            if protective_task:
                params["required_item"] = protective_task["prompt"]
        item["relation_checks"] = [
            {
                "type": relation.type,
                "subject_task_ids": subject_ids,
                "object_task_ids": object_ids,
                "params": params,
            }
        ]


def load_risk_operator_registry(path: str | Path) -> RiskOperatorRegistry:
    registry_path = Path(path)
    payload = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    return RiskOperatorRegistry.model_validate(payload)


def resolve_risk_operator_registry(
    config: Dict[str, Any], project_root: str | Path
) -> RiskOperatorRegistry:
    configured_path = config.get("risk_operators", {}).get(
        "path", "configs/risk_operators.yaml"
    )
    path = Path(configured_path)
    if not path.is_absolute():
        path = Path(project_root) / path
    return load_risk_operator_registry(path)


def load_default_risk_operator_registry() -> RiskOperatorRegistry:
    project_root = Path(__file__).resolve().parents[1]
    return load_risk_operator_registry(project_root / "configs" / "risk_operators.yaml")
