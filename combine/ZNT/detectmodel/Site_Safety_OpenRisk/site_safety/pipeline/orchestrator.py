from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
from PIL import Image

from site_safety.adapters.base import CLIPAdapter, MLLMAdapter, MaskInstance, SAM3Adapter
from site_safety.pipeline.mask_builder import RiskMaskBuilder
from site_safety.pipeline.relation import RelationVerifier
from site_safety.prompting.first_pass import (
    build_compact_discovery_prompt,
    build_first_pass_prompt,
    build_anchor_retry_prompt,
    build_open_risk_discovery_prompt,
    build_person_risk_discovery_prompt,
)
from site_safety.prompting.json_repair import build_json_repair_prompt
from site_safety.prompting.risk_audit import build_structured_risk_audit_prompt
from site_safety.prompting.report import build_report_prompt
from site_safety.prompting.second_pass import build_second_pass_prompt
from site_safety.pipeline.road_report import write_road_issue_report
from site_safety.pipeline.road_workflow import observation_prompt, compile_observations, planning_prompt, apply_plans, restore_plans
from site_safety.pipeline.road_evidence import reconcile_road_findings
from site_safety.pipeline.road_concepts import execute_road_concepts, write_scene_annotation
from site_safety.prompting.road import build_road_first_pass_prompt, road_second_pass, namespace_road_tasks, build_road_review_prompt
from site_safety.risk_operators import (
    RiskOperatorRegistry,
    load_default_risk_operator_registry,
    resolve_risk_operator_registry,
)
from site_safety.schemas import (
    FirstPassResponse,
    FinalRisk,
    InspectionResult,
    ManagementReport,
    ReportRiskSection,
    RiskCandidate,
    RiskEvidence,
    ScreeningAssessment,
    ScreeningRegion,
    ScreeningTrigger,
    SecondPassResponse,
    SegmentationRecord,
)
from site_safety.screening import parse_screening_trigger
from site_safety.utils.image import (
    add_image_label,
    crop_around_mask,
    draw_overlay,
    load_rgb,
    mask_box,
    save_binary_mask,
)
from site_safety.utils.json_tools import parse_json_object


class TrainingFreeInspector:
    def __init__(
        self,
        *,
        config: Dict[str, Any],
        mllm: MLLMAdapter,
        sam3: SAM3Adapter,
        clip: Optional[CLIPAdapter],
        report_llm: Optional[MLLMAdapter],
        project_root: str | Path,
    ) -> None:
        self.config = config
        self.mllm = mllm
        self.sam3 = sam3
        self.clip = clip
        self.report_llm = report_llm
        self.project_root = Path(project_root)
        self.risk_operators = resolve_risk_operator_registry(config, self.project_root)
        random.seed(int(config.get("random_seed", 42)))
        self.relation_verifier = RelationVerifier(config["pipeline"].get("relation_defaults", {}))
        self.mask_builder = RiskMaskBuilder(config["pipeline"].get("mask_defaults", {}))

    def _parse_mllm_json(
        self,
        raw_output: str,
        output_dir: Path,
        artifact_stem: str,
    ) -> Dict[str, Any]:
        """Parse an MLLM response, repairing only malformed JSON when necessary.

        A malformed answer is a transport/formatting defect, not visual evidence.
        The original response is saved by the caller; this method records the
        repair response alongside it for auditability.  The retry has no images,
        so it cannot introduce a second visual inference pass.
        """
        try:
            return parse_json_object(raw_output)
        except (json.JSONDecodeError, ValueError) as initial_error:
            repair_raw = self.mllm.generate_json(
                [], build_json_repair_prompt(raw_output)
            )
            repair_path = output_dir / f"{artifact_stem}_json_repair_raw.txt"
            repair_path.write_text(repair_raw, encoding="utf-8")
            try:
                payload = parse_json_object(repair_raw)
            except (json.JSONDecodeError, ValueError) as repair_error:
                error_path = output_dir / f"{artifact_stem}_json_repair_error.txt"
                error_path.write_text(
                    "initial_parse_error="
                    f"{type(initial_error).__name__}: {initial_error}\n"
                    "repair_parse_error="
                    f"{type(repair_error).__name__}: {repair_error}\n",
                    encoding="utf-8",
                )
                raise RuntimeError(
                    "MLLM returned malformed JSON and the format-only repair "
                    "retry also failed."
                ) from repair_error
            (output_dir / f"{artifact_stem}_json_repaired.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return payload

    def _load_candidates(self) -> List[Dict[str, Any]]:
        catalog_path = self.project_root / self.config["risk_catalog"]["path"]
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        candidates: List[Dict[str, Any]] = []
        if self.config["risk_catalog"].get("include_all_core", True):
            candidates.extend(catalog.get("core", []))
        distractors = catalog.get("distractors", [])
        count = min(int(self.config["risk_catalog"].get("distractor_count", 0)), len(distractors))
        if count:
            candidates.extend(random.sample(distractors, count))
        return candidates

    @staticmethod
    def _merge_discovery_payloads(
        *payloads: Dict[str, Any],
    ) -> Dict[str, Any]:
        merged_hazards: List[Dict[str, Any]] = []
        by_name: Dict[str, Dict[str, Any]] = {}
        for payload in payloads:
            for source in payload.get("hazards") or []:
                if not isinstance(source, dict):
                    continue
                key = re.sub(
                    r"[\s，。、“”‘’（）()_-]+",
                    "",
                    str(source.get("risk_name_zh") or "").lower(),
                )
                if not key:
                    key = f"unnamed_{len(merged_hazards)}"
                existing = by_name.get(key)
                if existing is None:
                    copied = dict(source)
                    copied["visible_evidence"] = list(
                        source.get("visible_evidence") or []
                    )
                    copied["counter_evidence"] = list(
                        source.get("counter_evidence") or []
                    )
                    by_name[key] = copied
                    merged_hazards.append(copied)
                    continue
                existing["confidence"] = max(
                    float(existing.get("confidence") or 0.0),
                    float(source.get("confidence") or 0.0),
                )
                for field in ("risk_description", "subject_description"):
                    value = str(source.get(field) or "").strip()
                    if value and value not in str(existing.get(field) or ""):
                        existing[field] = (
                            str(existing.get(field) or "").rstrip("。") + "；" + value
                        ).lstrip("；")
                for fact in source.get("visible_evidence") or []:
                    if fact not in existing["visible_evidence"]:
                        existing["visible_evidence"].append(fact)
                for fact in source.get("counter_evidence") or []:
                    if fact not in existing["counter_evidence"]:
                        existing["counter_evidence"].append(fact)
        summaries: List[str] = []
        for payload in payloads:
            summary = str(payload.get("scene_summary") or "").strip()
            if summary and summary not in summaries:
                summaries.append(summary)
        scene_summary = "；".join(summaries)
        return {
            "scene_summary": scene_summary,
            "has_possible_anomaly": bool(merged_hazards),
            "hazards": merged_hazards,
        }

    @staticmethod
    def _recover_fall_protection_discovery_confidence(
        payload: Dict[str, Any],
        *,
        enabled: bool = False,
        recovered_confidence: float = 0.60,
    ) -> None:
        """Recover template confidence=0 for explicit fall-protection findings.

        Recovery is deliberately narrow: both the hazard description and its
        visible evidence must say that a harness/lanyard/anchor connection is
        missing. Generic high-place scenes and contradicted findings stay at 0.
        """
        if not enabled:
            return
        confidence = min(1.0, max(0.0, float(recovered_confidence)))
        missing_pattern = re.compile(
            r"(?:未(?:见|佩戴|系|连接|固定|挂接)|没有|无|缺少).{0,16}"
            r"(?:安全带|安全绳|连接绳|防坠绳|生命线|挂点|锚点)|"
            r"(?:安全带|安全绳|连接绳|防坠绳).{0,12}(?:未连接|未固定|未挂接|缺失)|"
            r"(?:without|no|missing).{0,16}(?:harness|lanyard|lifeline|anchor)",
            re.IGNORECASE,
        )
        present_pattern = re.compile(
            r"(?:安全带|安全绳|连接绳|防坠绳).{0,12}(?:已连接|已固定|已挂接|连接可见)|"
            r"(?:attached|connected|secured).{0,12}(?:harness|lanyard|lifeline)",
            re.IGNORECASE,
        )
        for hazard in payload.get("hazards") or []:
            if not isinstance(hazard, dict):
                continue
            try:
                original_confidence = float(hazard.get("confidence") or 0.0)
            except (TypeError, ValueError):
                original_confidence = 0.0
            if original_confidence > 0.0:
                continue
            identity_text = " ".join(
                str(hazard.get(key) or "")
                for key in ("risk_name_zh", "risk_description")
            )
            evidence_text = " ".join(
                str(value) for value in hazard.get("visible_evidence", []) or []
            )
            counter_text = " ".join(
                str(value) for value in hazard.get("counter_evidence", []) or []
            )
            if (
                not evidence_text
                or not missing_pattern.search(identity_text)
                or not missing_pattern.search(evidence_text)
                or present_pattern.search(counter_text)
            ):
                continue
            hazard["confidence"] = confidence
            hazard["confidence_recovered"] = True
            hazard["original_confidence"] = original_confidence
            hazard["confidence_recovery_reason"] = (
                "明确的防坠装备/锚点缺失描述及可见证据；原置信度为缺省值0。"
            )

    @staticmethod
    def _select_compiled_candidate(
        hazard: Dict[str, Any],
        candidates: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Select the RiskSpec that is semantically tied to the locked discovery.

        Small local models sometimes prepend an unrelated candidate even when told
        to compile exactly one hazard. Chinese character bigrams make the choice
        deterministic without invoking another model or enumerating the catalog.
        """
        if not candidates:
            return None

        def bigrams(value: Any) -> set[str]:
            text = json.dumps(value, ensure_ascii=False)
            compact = re.sub(r"[^\u4e00-\u9fffa-zA-Z0-9]+", "", text.lower())
            return {
                compact[index : index + 2]
                for index in range(max(0, len(compact) - 1))
            }

        hazard_tokens = bigrams(hazard)
        if not hazard_tokens:
            return candidates[0]
        scored = []
        for index, candidate in enumerate(candidates):
            candidate_tokens = bigrams(
                {
                    "risk_name_zh": candidate.get("risk_name_zh"),
                    "risk_type": candidate.get("risk_type"),
                    "observed_facts": candidate.get("observed_facts"),
                    "counter_evidence": candidate.get("counter_evidence"),
                }
            )
            overlap = len(hazard_tokens & candidate_tokens)
            scored.append((overlap, -index, candidate))
        return max(scored, key=lambda item: (item[0], item[1]))[2]

    @staticmethod
    def _namespace_audit_entities(payload: Dict[str, Any], namespace: str) -> None:
        """Prevent entity-id collisions when several ROI audit rounds are merged."""
        prefix = re.sub(r"[^a-zA-Z0-9_]+", "_", namespace).strip("_")
        if not prefix:
            return
        inventory = payload.get("scene_inventory") or {}
        mappings: Dict[str, str] = {}
        for list_key, id_key in (
            ("persons", "person_id"),
            ("machines", "machine_id"),
            ("risk_regions", "region_id"),
        ):
            for item in inventory.get(list_key, []) or []:
                if not isinstance(item, dict) or not item.get(id_key):
                    continue
                old_id = str(item[id_key])
                new_id = f"{prefix}_{old_id}"
                mappings[old_id] = new_id
                item[id_key] = new_id
        for person in inventory.get("persons", []) or []:
            if not isinstance(person, dict):
                continue
            for key in ("nearest_machine", "nearest_edge_or_opening"):
                value = str(person.get(key) or "")
                if value in mappings:
                    person[key] = mappings[value]
        for audit in payload.get("risk_audits", []) or []:
            if not isinstance(audit, dict):
                continue
            for key in ("subject_ids", "anchor_ids"):
                audit[key] = [
                    mappings.get(str(value), str(value))
                    for value in audit.get(key, []) or []
                ]

    @staticmethod
    def _correct_audit_status_consistency(payload: Dict[str, Any]) -> None:
        """Downgrade contradictory ``absent`` audit rows to reviewable candidates.

        Local VLMs occasionally describe a missing protection item correctly but
        emit the opposite enum.  The correction is deliberately conservative:
        it creates an ``uncertain`` candidate instead of asserting that the risk
        is present.  Category-specific phrases avoid matching generic statements
        such as "未观察到临边防护缺失".
        """
        positive_missing_patterns = {
            "missing_helmet": re.compile(
                r"(未(?:佩戴|戴).{0,8}(?:安全帽|头盔)|无安全帽|裸头|"
                r"bareheaded|without.{0,12}(?:helmet|hard[ -]?hat))",
                re.IGNORECASE,
            ),
            "missing_edge_protection": re.compile(
                r"((?:临边|边缘|洞口|基坑|平台).{0,18}(?:无|没有|未设置|缺少).{0,12}"
                r"(?:护栏|栏杆|盖板|防护|围挡)|(?:无|没有|未设置|缺少).{0,12}"
                r"(?:护栏|栏杆|盖板|临边防护)|unprotected.{0,12}(?:edge|opening)|"
                r"(?:edge|opening).{0,16}(?:without|no).{0,10}(?:guardrail|cover))",
                re.IGNORECASE,
            ),
            "missing_fall_protection": re.compile(
                r"((?:未见|未佩戴|未系|没有|无).{0,12}(?:安全带|安全绳|连接绳|挂点)|"
                r"without.{0,12}(?:harness|lanyard)|no.{0,12}(?:harness|lanyard))",
                re.IGNORECASE,
            ),
        }
        suppress_patterns = {
            "missing_helmet": re.compile(
                r"(无可见人员|未见人员|无需.{0,6}(?:安全帽|头盔)|无安全帽需求)",
                re.IGNORECASE,
            ),
            "missing_edge_protection": re.compile(
                r"(未见.{0,10}(?:临边|边缘|洞口|基坑|平台)|不存在.{0,10}"
                r"(?:临边|边缘|洞口|基坑|平台)|无防护需求|无需防护)",
                re.IGNORECASE,
            ),
            "missing_fall_protection": re.compile(
                r"(未见.{0,10}(?:高处人员|高处作业)|无高处人员|无需.{0,8}"
                r"(?:安全带|安全绳|连接绳|挂点))",
                re.IGNORECASE,
            ),
        }
        protective_present_patterns = {
            "missing_helmet": re.compile(
                r"(佩戴.{0,6}(?:安全帽|工业头盔)|(?:安全帽|工业头盔).{0,6}可见)",
                re.IGNORECASE,
            ),
            "missing_edge_protection": re.compile(
                r"((?:有|设有|设置|安装).{0,10}(?:护栏|栏杆|盖板|防护设施))",
                re.IGNORECASE,
            ),
            "missing_fall_protection": re.compile(
                r"(佩戴.{0,8}安全带|安全带.{0,8}可见|连接绳.{0,8}(?:可见|连接|挂接))",
                re.IGNORECASE,
            ),
        }
        defect_pattern = re.compile(
            r"(未|无|没有|缺失|缺少|不足|不完整|破损|中断|不连续|仅部分|过低|敞开|"
            r"not attached|missing|incomplete|damaged)",
            re.IGNORECASE,
        )
        for item in payload.get("risk_audits", []) or []:
            if not isinstance(item, dict):
                continue
            risk_id = str(item.get("risk_id") or "")
            evidence = " ".join(str(value) for value in item.get("visible_evidence", []) or [])
            if item.get("status") == "present":
                protective_pattern = protective_present_patterns.get(risk_id)
                if (
                    protective_pattern is not None
                    and protective_pattern.search(evidence)
                    and not defect_pattern.search(evidence)
                ):
                    original_confidence = float(item.get("confidence") or 0.0)
                    item["original_status"] = "present"
                    item["status"] = "uncertain"
                    item["confidence"] = min(0.59, max(0.35, original_confidence * 0.6))
                    item["status_consistency_corrected"] = True
                    uncertainties = item.setdefault("uncertainties", [])
                    message = (
                        "缺失型风险状态与防护物存在证据矛盾，已降级为uncertain并送入后续视觉核验。"
                    )
                    if message not in uncertainties:
                        uncertainties.append(message)
                continue
            if item.get("status") != "absent":
                continue
            pattern = positive_missing_patterns.get(risk_id)
            if pattern is None:
                continue
            suppress = suppress_patterns.get(risk_id)
            if suppress is not None and suppress.search(evidence):
                continue
            match = pattern.search(evidence)
            if match is None:
                continue
            original_confidence = float(item.get("confidence") or 0.0)
            item["original_status"] = "absent"
            item["status"] = "uncertain"
            item["confidence"] = min(0.59, max(0.35, original_confidence * 0.6))
            item["status_consistency_corrected"] = True
            uncertainties = item.setdefault("uncertainties", [])
            message = (
                "结构化状态与缺失型可见证据矛盾，已降级为uncertain并送入后续视觉核验。"
            )
            if message not in uncertainties:
                uncertainties.append(message)

    @staticmethod
    def _audit_payload_to_candidates(
        payload: Dict[str, Any],
        catalog_items: List[Dict[str, Any]],
        *,
        minimum_confidence: float = 0.25,
    ) -> List[Dict[str, Any]]:
        """Compile active audit findings while retaining referenced entities."""
        names = {
            str(item.get("risk_id")): str(
                item.get("risk_name_zh")
                or item.get("name_zh")
                or item.get("risk_id")
            )
            for item in catalog_items
            if item.get("risk_id")
        }
        inventory = payload.get("scene_inventory") or {}
        persons = {
            str(value.get("person_id")): value
            for value in inventory.get("persons", []) or []
            if isinstance(value, dict) and value.get("person_id")
        }
        machines = {
            str(value.get("machine_id")): value
            for value in inventory.get("machines", []) or []
            if isinstance(value, dict) and value.get("machine_id")
        }
        regions = {
            str(value.get("region_id")): value
            for value in inventory.get("risk_regions", []) or []
            if isinstance(value, dict) and value.get("region_id")
        }

        def location(value: Any) -> str:
            return re.sub(r"[|_/]+", " ", str(value or "")).strip()

        def inventory_entity(entity_id: str) -> Optional[Dict[str, Any]]:
            if entity_id in persons:
                value = persons[entity_id]
                return {
                    "entity_id": entity_id,
                    "role": "subject",
                    "category": "construction worker",
                    "attributes": [],
                    "location": location(value.get("location")),
                    "expected_count": 1,
                }
            if entity_id in machines:
                value = machines[entity_id]
                machine_type = str(value.get("type") or "other").lower()
                category = {
                    "excavator": "excavator",
                    "loader": "wheel loader",
                }.get(machine_type, "heavy construction machinery")
                return {
                    "entity_id": entity_id,
                    "role": "hazard_source",
                    "category": category,
                    "attributes": [],
                    "location": location(value.get("location")),
                    "expected_count": 1,
                }
            if entity_id in regions:
                value = regions[entity_id]
                region_type = str(value.get("type") or "construction edge")
                category = {
                    "platform_edge": "construction platform edge",
                    "opening": "construction floor opening",
                    "slope": "construction slope edge",
                    "scaffold": "scaffold platform edge",
                }.get(region_type, "construction edge or floor opening")
                return {
                    "entity_id": entity_id,
                    "role": "region",
                    "category": category,
                    "attributes": [],
                    "location": location(value.get("location")),
                    "expected_count": 1,
                }
            return None

        candidates: List[Dict[str, Any]] = []
        for item in payload.get("risk_audits", []) or []:
            if not isinstance(item, dict):
                continue
            risk_id = str(item.get("risk_id") or "").strip()
            status = str(item.get("status") or "").strip()
            try:
                confidence = float(item.get("confidence") or 0.0)
            except (TypeError, ValueError):
                confidence = 0.0
            if (
                not risk_id
                or status not in {"present", "uncertain"}
                or confidence < minimum_confidence
            ):
                continue
            subject_ids = [str(value) for value in item.get("subject_ids", []) or []]
            anchor_ids = [str(value) for value in item.get("anchor_ids", []) or []]
            if risk_id == "machinery_proximity" and not anchor_ids:
                anchor_ids = list(
                    dict.fromkeys(
                        str(persons[person_id].get("nearest_machine"))
                        for person_id in subject_ids
                        if person_id in persons
                        and persons[person_id].get("nearest_machine") not in {None, "", "none"}
                    )
                )
            if risk_id == "missing_edge_protection" and not anchor_ids:
                anchor_ids = list(regions)

            referenced_ids = list(dict.fromkeys([*subject_ids, *anchor_ids]))
            target_entities = [
                entity
                for entity_id in referenced_ids
                if (entity := inventory_entity(entity_id)) is not None
            ]
            relation_type = "none"
            relation_subject_ids = [
                entity["entity_id"]
                for entity in target_entities
                if entity["role"] in {"subject", "region"}
            ]
            relation_object_ids = [
                entity["entity_id"]
                for entity in target_entities
                if entity["role"] == "hazard_source"
            ]
            protective_specs = {
                "missing_helmet": (
                    "safety_helmet_audit",
                    "safety helmet",
                    "missing_association",
                ),
                "missing_fall_protection": (
                    "fall_protection_audit",
                    "visible fall-arrest lanyard physically linking the worker "
                    "body harness to a fixed structural anchor or lifeline",
                    "missing",
                ),
                "missing_edge_protection": (
                    "edge_protection_audit",
                    "safety guardrail or opening cover",
                    "missing",
                ),
            }
            if risk_id == "machinery_proximity":
                relation_type = "near"
            elif risk_id in protective_specs:
                protective_id, category, relation_type = protective_specs[risk_id]
                target_entities.append(
                    {
                        "entity_id": protective_id,
                        "role": "protective_item",
                        "category": category,
                        "attributes": [],
                        "location": "",
                        "expected_count": 1,
                    }
                )
                relation_object_ids.append(protective_id)

            candidates.append(
                {
                    "risk_id": risk_id,
                    "risk_name_zh": names.get(risk_id, risk_id),
                    "status": status,
                    "confidence": confidence,
                    "observed_facts": list(item.get("visible_evidence") or []),
                    "counter_evidence": list(item.get("counter_evidence") or []),
                    "sam3_tasks": [],
                    "relation_checks": [],
                    "mask_strategy": "entity_union",
                    "uncertainties": list(item.get("uncertainties") or []),
                    "target_entities": target_entities,
                    "relation_spec": {
                        "type": relation_type,
                        "subject_entity_ids": relation_subject_ids,
                        "object_entity_ids": relation_object_ids,
                        "params": {},
                    },
                }
            )
        return candidates

    @staticmethod
    def _merge_audit_candidates(
        first_payload: Dict[str, Any],
        audit_candidates: List[Dict[str, Any]],
    ) -> None:
        """Merge recall candidates without deleting open-risk discoveries."""
        primary = first_payload.setdefault("candidate_assessments", [])
        open_items = first_payload.setdefault("open_discoveries", [])
        existing_by_id = {
            str(item.get("risk_id")): item
            for item in [*primary, *open_items]
            if isinstance(item, dict) and item.get("risk_id")
        }
        for audit in audit_candidates:
            risk_id = str(audit.get("risk_id") or "")
            existing = existing_by_id.get(risk_id)
            if existing is None:
                primary.append(audit)
                existing_by_id[risk_id] = audit
                continue
            if audit.get("status") == "present" or existing.get("status") != "present":
                existing["status"] = audit.get("status", "uncertain")
            existing["confidence"] = max(
                float(existing.get("confidence") or 0.0),
                float(audit.get("confidence") or 0.0),
            )
            for field in ("observed_facts", "counter_evidence", "uncertainties"):
                values = existing.setdefault(field, [])
                for value in audit.get(field, []) or []:
                    if value not in values:
                        values.append(value)
            existing_entities = existing.setdefault("target_entities", [])
            known_entity_ids = {
                str(value.get("entity_id"))
                for value in existing_entities
                if isinstance(value, dict) and value.get("entity_id")
            }
            for entity in audit.get("target_entities", []) or []:
                if str(entity.get("entity_id")) not in known_entity_ids:
                    existing_entities.append(entity)
            audit_spec = audit.get("relation_spec") or {}
            existing_spec = existing.get("relation_spec") or {}
            if audit_spec:
                if existing_spec.get("type") == audit_spec.get("type"):
                    for key in ("subject_entity_ids", "object_entity_ids"):
                        merged_ids = list(existing_spec.get(key) or [])
                        for entity_id in audit_spec.get(key) or []:
                            if entity_id not in merged_ids:
                                merged_ids.append(entity_id)
                        existing_spec[key] = merged_ids
                    existing_spec["params"] = {
                        **(existing_spec.get("params") or {}),
                        **(audit_spec.get("params") or {}),
                    }
                    existing["relation_spec"] = existing_spec
                elif not existing_spec or existing_spec.get("type") in {None, "", "none"}:
                    existing["relation_spec"] = audit_spec
        first_payload["has_possible_anomaly"] = bool(primary or open_items)

    @staticmethod
    def _dedupe_tasks(risks: Iterable[RiskCandidate], max_tasks: int) -> list:
        tasks = []
        seen = set()
        for risk in risks:
            for task in risk.sam3_tasks:
                key = (task.task_id, task.prompt.strip().lower())
                if key in seen:
                    continue
                seen.add(key)
                tasks.append(task)
                if len(tasks) >= max_tasks:
                    return tasks
        return tasks

    def inspect(
        self,
        image_path: str | Path,
        output_dir: str | Path,
        screening_trigger: ScreeningTrigger | Dict[str, Any] | str | Path | None = None,
        screening_mask_path: str | Path | None = None,
        progress_callback=None,
    ) -> InspectionResult:
        def progress(stage, status, detail=""):
            if progress_callback is not None:
                progress_callback(stage, status, detail)

        progress("first_pass", "running", "模型正在发现风险并编译候选描述")
        image_path = Path(image_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        image = load_rgb(image_path)
        trigger = parse_screening_trigger(screening_trigger)
        candidate_risks = self._load_candidates()

        first_images, first_manifest = self._build_first_pass_images(image)
        first_images, first_manifest, trigger = self._append_screening_views(
            image=image,
            images=first_images,
            manifest=first_manifest,
            trigger=trigger,
            screening_mask_path=screening_mask_path,
            output_dir=output_dir,
        )
        trigger_payload = trigger.model_dump() if trigger is not None else None
        if trigger is not None:
            (output_dir / "screening_trigger.json").write_text(
                json.dumps(trigger_payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        if self.config["pipeline"].get("two_stage_open_discovery", False):
            has_screening_views = bool(
                trigger
                and trigger.triggered
                and (trigger.suspected_regions or trigger.suspected_concepts)
            )
            discovery_images = first_images if has_screening_views else [image]
            discovery_manifest = first_manifest if has_screening_views else None
            raw_discovery = self.mllm.generate_json(
                discovery_images,
                build_open_risk_discovery_prompt(
                    discovery_manifest, screening_trigger=trigger_payload
                ),
            )
            (output_dir / "mllm_discovery_raw.txt").write_text(
                raw_discovery, encoding="utf-8"
            )
            discovery_payload = self._parse_mllm_json(
                raw_discovery, output_dir, "mllm_discovery"
            )
            if (
                self.config["pipeline"].get("dual_view_open_discovery", False)
                and first_manifest
                and len(first_images) > 1
            ):
                raw_people = self.mllm.generate_json(
                    first_images,
                    build_person_risk_discovery_prompt(
                        first_manifest, screening_trigger=trigger_payload
                    ),
                )
                (output_dir / "mllm_discovery_people_raw.txt").write_text(
                    raw_people, encoding="utf-8"
                )
                people_payload = self._parse_mllm_json(
                    raw_people, output_dir, "mllm_discovery_people"
                )
                discovery_payload = self._merge_discovery_payloads(
                    discovery_payload, people_payload
                )
                (output_dir / "mllm_discovery_merged.json").write_text(
                    json.dumps(discovery_payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            recovery_cfg = self.config["pipeline"].get(
                "fall_protection_confidence_recovery", {}
            )
            self._recover_fall_protection_discovery_confidence(
                discovery_payload,
                enabled=bool(recovery_cfg.get("enabled", False)),
                recovered_confidence=float(recovery_cfg.get("confidence", 0.60)),
            )
            hazards = [
                hazard
                for hazard in discovery_payload.get("hazards") or []
                if isinstance(hazard, dict)
                and float(hazard.get("confidence") or 0.0)
                >= float(
                    self.config["pipeline"].get(
                        "minimum_discovery_confidence", 0.25
                    )
                )
            ]
            discovery_payload["hazards"] = hazards
            discovery_payload["has_possible_anomaly"] = bool(hazards)
            summary_text = str(discovery_payload.get("scene_summary") or "")
            anchor_scene = self.risk_operators.is_anchor_scene(summary_text)
            if (
                not hazards
                and anchor_scene
                and self.config["pipeline"].get("retry_empty_anchor_scene", False)
            ):
                raw_anchor = self.mllm.generate_json(
                    [image], build_anchor_retry_prompt(summary_text)
                )
                (output_dir / "mllm_discovery_anchor_retry_raw.txt").write_text(
                    raw_anchor, encoding="utf-8"
                )
                anchor_payload = self._parse_mllm_json(
                    raw_anchor, output_dir, "mllm_discovery_anchor_retry"
                )
                discovery_payload = self._merge_discovery_payloads(
                    discovery_payload, anchor_payload
                )
                self._recover_fall_protection_discovery_confidence(
                    discovery_payload,
                    enabled=bool(recovery_cfg.get("enabled", False)),
                    recovered_confidence=float(
                        recovery_cfg.get("confidence", 0.60)
                    ),
                )
                hazards = [
                    hazard
                    for hazard in discovery_payload.get("hazards") or []
                    if float(hazard.get("confidence") or 0.0)
                    >= float(
                        self.config["pipeline"].get(
                            "minimum_discovery_confidence", 0.25
                        )
                    )
                ]
                discovery_payload["hazards"] = hazards
                discovery_payload["has_possible_anomaly"] = bool(hazards)
            if hazards:
                if self.config["pipeline"].get(
                    "structure_each_discovered_hazard", False
                ):
                    compiled_candidates: List[Dict[str, Any]] = []
                    compiled_risk_ids: set[str] = set()
                    compiled_open: List[Any] = []
                    for hazard_index, hazard in enumerate(hazards, start=1):
                        locked_payload = {
                            "scene_summary": discovery_payload.get("scene_summary", ""),
                            "has_possible_anomaly": True,
                            "hazards": [hazard],
                        }
                        first_prompt = build_compact_discovery_prompt(
                            candidate_risks,
                            allow_open_discovery=bool(
                                self.config["risk_catalog"].get(
                                    "allow_open_discovery", True
                                )
                            ),
                            image_manifest=first_manifest,
                            discovery_payload=locked_payload,
                            screening_trigger=trigger_payload,
                        )
                        raw_part = self.mllm.generate_json(first_images, first_prompt)
                        (output_dir / f"mllm_structuring_raw_{hazard_index:02d}.txt").write_text(
                            raw_part, encoding="utf-8"
                        )
                        part_payload = self._parse_mllm_json(
                            raw_part,
                            output_dir,
                            f"mllm_structuring_{hazard_index:02d}",
                        )
                        # 一个发现只允许编译一个RiskSpec。即使小模型无视提示追加
                        # 其他风险，程序也不会把它们带入SAM3阶段。
                        part_candidates = part_payload.get("candidate_assessments") or []
                        if part_candidates:
                            candidate = self._select_compiled_candidate(
                                hazard, part_candidates
                            )
                            if candidate is None:
                                continue
                            risk_id = str(candidate.get("risk_id") or "")
                            if risk_id and risk_id not in compiled_risk_ids:
                                compiled_candidates.append(candidate)
                                compiled_risk_ids.add(risk_id)
                        compiled_open.extend(part_payload.get("open_discoveries") or [])
                    raw_first = json.dumps(
                        {
                            "scene_summary": discovery_payload.get("scene_summary", ""),
                            "has_possible_anomaly": bool(compiled_candidates),
                            "candidate_assessments": compiled_candidates,
                            "open_discoveries": compiled_open,
                        },
                        ensure_ascii=False,
                    )
                else:
                    first_prompt = build_compact_discovery_prompt(
                        candidate_risks,
                        allow_open_discovery=bool(
                            self.config["risk_catalog"].get("allow_open_discovery", True)
                        ),
                        image_manifest=first_manifest,
                        discovery_payload=discovery_payload,
                        screening_trigger=trigger_payload,
                    )
                    raw_first = self.mllm.generate_json(first_images, first_prompt)
            else:
                raw_first = json.dumps(
                    {
                        "scene_summary": discovery_payload.get("scene_summary", ""),
                        "has_possible_anomaly": False,
                        "candidate_assessments": [],
                        "open_discoveries": [],
                    },
                    ensure_ascii=False,
                )
        else:
            first_prompt = (build_road_first_pass_prompt if self.config.get("domain") == "road" else build_first_pass_prompt)(
                candidate_risks,
                allow_open_discovery=bool(
                    self.config["risk_catalog"].get("allow_open_discovery", True)
                ),
                image_manifest=first_manifest,
                compact_discovery=bool(
                    self.config["pipeline"].get("compact_open_discovery", False)
                ),
                screening_trigger=trigger_payload,
            )
            if self.config.get("domain") == "road" and self.config["pipeline"].get("road_observation_planning", False):
                first_prompt = observation_prompt(candidate_risks)
            (output_dir / "first_prompt.txt").write_text(first_prompt, encoding="utf-8")
            raw_first = self.mllm.generate_json(first_images, first_prompt)
        (output_dir / "mllm_first_raw.txt").write_text(raw_first, encoding="utf-8")
        first_payload = self._parse_mllm_json(raw_first, output_dir, "mllm_first")
        road_v4 = self.config.get("domain") == "road" and self.config["pipeline"].get("road_observation_planning", False)
        road_v5 = road_v4 and self.config['pipeline'].get('road_concept_segmentation', False)
        locked_road_plans = {}
        if road_v4:
            first_payload = compile_observations(first_payload, candidate_risks, concept_mode=road_v5)
            if first_payload["candidate_assessments"]:
                plan_prompt = planning_prompt(first_payload["candidate_assessments"])
                (output_dir / "planning_prompt.txt").write_text(plan_prompt, encoding="utf-8")
                progress("planning", "running", "正在按可见事实规划定位，不使用模型自报分数阻断")
                try:
                    repair_message = ""
                    for attempt in range(2):
                        effective_prompt = plan_prompt + repair_message
                        (output_dir / f"planning_prompt_{attempt}.txt").write_text(effective_prompt, encoding="utf-8")
                        raw_plan = self.mllm.generate_json(first_images, effective_prompt)
                        (output_dir / f"planning_raw_{attempt}.txt").write_text(raw_plan, encoding="utf-8")
                        (output_dir / "planning_raw.txt").write_text(raw_plan, encoding="utf-8")
                        try:
                            plan_payload = self._parse_mllm_json(raw_plan, output_dir, f"planning_{attempt}")
                            apply_plans(first_payload, plan_payload, int(self.config["pipeline"].get("road_max_planned_risks", 8)))
                            missing = [r["risk_id"] for r in first_payload["candidate_assessments"] if r["localization_plan_status"] == "no_plan"]
                            if missing and attempt == 0:
                                repair_message = "\n上一遍遗漏这些已观察到的目标，请仅修复定位计划：" + json.dumps(missing,ensure_ascii=False)
                                continue
                            break
                        except Exception as plan_error:
                            if attempt == 1:
                                raise
                            repair_message = "\n上一遍结构校验失败，请修复，保持risk_id唯一，不新增风险：" + str(plan_error)
                except Exception as exc:
                    (output_dir / "planning_error.txt").write_text(str(exc), encoding="utf-8")
                    for row in first_payload["candidate_assessments"]:
                        row["sam3_tasks"] = []
                        row["relation_checks"] = []
                        row["localization_plan_status"] = "planner_failed"
                        row["uncertainties"].append("定位规划失败，观察保留待复核。")
                progress("planning", "done", "定位计划已记录")
            locked_road_plans = {r["risk_id"]: json.loads(json.dumps(r)) for r in first_payload["candidate_assessments"]}
            (output_dir / "localization_plan.json").write_text(json.dumps(locked_road_plans, ensure_ascii=False, indent=2), encoding="utf-8")
        audit_cfg = self.config["pipeline"].get("structured_risk_audit", {})
        if audit_cfg.get("enabled", False):
            audit_prompt = build_structured_risk_audit_prompt(
                image_manifest=first_manifest,
                screening_trigger=trigger_payload,
            )
            (output_dir / "structured_risk_audit_prompt.txt").write_text(
                audit_prompt, encoding="utf-8"
            )
            raw_audit = self.mllm.generate_json(first_images, audit_prompt)
            (output_dir / "structured_risk_audit_raw.txt").write_text(
                raw_audit, encoding="utf-8"
            )
            audit_payload = self._parse_mllm_json(
                raw_audit, output_dir, "structured_risk_audit"
            )
            self._correct_audit_status_consistency(audit_payload)
            (output_dir / "structured_risk_audit.json").write_text(
                json.dumps(audit_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            audit_candidates = self._audit_payload_to_candidates(
                audit_payload,
                candidate_risks,
                minimum_confidence=float(
                    audit_cfg.get("minimum_confidence", 0.25)
                ),
            )
            self._merge_audit_candidates(first_payload, audit_candidates)
            for batch_name, batch_images, batch_manifest in self._build_specialized_audit_batches(
                image
            ):
                batch_prompt = build_structured_risk_audit_prompt(
                    image_manifest=batch_manifest,
                    screening_trigger=trigger_payload,
                )
                artifact_stem = f"structured_risk_audit_{batch_name}"
                (output_dir / f"{artifact_stem}_prompt.txt").write_text(
                    batch_prompt, encoding="utf-8"
                )
                raw_batch = self.mllm.generate_json(batch_images, batch_prompt)
                (output_dir / f"{artifact_stem}_raw.txt").write_text(
                    raw_batch, encoding="utf-8"
                )
                batch_payload = self._parse_mllm_json(
                    raw_batch, output_dir, artifact_stem
                )
                self._namespace_audit_entities(batch_payload, batch_name)
                self._correct_audit_status_consistency(batch_payload)
                (output_dir / f"{artifact_stem}.json").write_text(
                    json.dumps(batch_payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                batch_candidates = self._audit_payload_to_candidates(
                    batch_payload,
                    candidate_risks,
                    minimum_confidence=float(
                        audit_cfg.get("minimum_confidence", 0.25)
                    ),
                )
                self._merge_audit_candidates(first_payload, batch_candidates)
        self._apply_deterministic_candidate_fallbacks(first_payload, candidate_risks)
        self._normalize_first_pass_payload(
            first_payload, candidate_risks, self.risk_operators,
            preserve_confidence=self.config.get("domain") == "road",
        )
        if road_v4:
            restore_plans(first_payload, locked_road_plans)
        if self.config.get("domain") == "road":
            namespace_road_tasks(first_payload)
        first = FirstPassResponse.model_validate(first_payload)
        self._road_regions = {r.risk_id: r.region_xyxy for r in first.candidate_assessments if r.region_xyxy} if road_v4 else {}
        (output_dir / "first_pass.json").write_text(
            json.dumps(first.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

        progress("first_pass", "done", "候选风险描述已生成")
        progress("segment", "running", "正在定位候选实体；无候选时不生成风险掩码")
        segment_statuses = set(self.config["pipeline"].get("segment_statuses", ["present", "uncertain"]))
        min_conf = float(self.config["pipeline"].get("min_mllm_candidate_confidence", 0.25))
        active_risks = [
            risk
            for risk in first.candidate_assessments + first.open_discoveries
            if risk.status in segment_statuses and (
                (bool(risk.observed_facts) and risk.localization_plan_status != "budget_exceeded")
                if road_v4 else risk.confidence >= min_conf
            )
        ]
        tasks = self._dedupe_tasks(active_risks, int(self.config["pipeline"].get("max_sam3_tasks", 24)))

        self.sam3.set_image(image)
        by_task: Dict[str, List[MaskInstance]] = {}
        min_sam3 = float(self.config["pipeline"].get("min_sam3_score", 0.20))
        helmet_subject_task_ids = [
            task.task_id
            for risk in active_risks
            if risk.risk_id == "missing_helmet"
            for task in risk.sam3_tasks
            if task.role == "subject"
        ]
        helmet_fallback_task_id = next(
            (
                task_id
                for task_id in helmet_subject_task_ids
                if task_id.endswith("_auto_01")
            ),
            helmet_subject_task_ids[0] if helmet_subject_task_ids else None,
        )
        context_tasks = []
        if road_v5:
            by_task, context_tasks = execute_road_concepts(self.sam3, active_risks,
                first.assessment_quality.get('scene_elements', []), output_dir, min_sam3,
                max_tasks=int(self.config['pipeline'].get('max_sam3_tasks',48)))
        for task in ([] if road_v5 else tasks):
            task_min_score = max(
                min_sam3,
                float(task.min_score) if task.min_score is not None else min_sam3,
            )
            items = [
                item
                for item in self.sam3.segment(task)
                if item.score >= task_min_score
            ]
            if (
                not items
                and task.task_id == helmet_fallback_task_id
                and self.config["pipeline"].get("person_precheck_fallback", True)
            ):
                items = [
                    MaskInstance(
                        task_id=task.task_id,
                        role=task.role,
                        prompt=task.prompt,
                        score=item.score,
                        mask=item.mask,
                        box_xyxy=item.box_xyxy,
                    )
                    for item in getattr(self, "_last_person_precheck_instances", [])
                ]
            by_task[task.task_id] = items

        progress("segment", "done", f"已处理 {len(tasks)} 个定位提示")
        progress("verify", "running", "正在整理分割证据与空间关系")
        evidences: List[RiskEvidence] = []
        height, width = image.height, image.width
        for risk_index, risk in enumerate(active_risks, start=1):
            records: List[SegmentationRecord] = []
            boxes_for_overlay: List[tuple[list[float], str, float]] = []
            for task_index, task in enumerate(risk.sam3_tasks, start=1):
                for index, item in enumerate(by_task.get(task.task_id, [])):
                    if item.mask.shape != (height, width):
                        raise ValueError(
                            f"SAM3 mask shape for {task.task_id} is {item.mask.shape}, expected {(height, width)}"
                        )
                    box = item.box_xyxy or mask_box(item.mask) or [0.0, 0.0, 0.0, 0.0]
                    clip_score = None
                    if self.clip is not None:
                        clip_score = self.clip.score(image, [item.prompt])[0]
                    # Keep artifact names compact. Deep Windows deployment paths can
                    # otherwise exceed MAX_PATH when risk/task identifiers are long.
                    mask_name = f"entity_{risk_index:02d}_{task_index:02d}_{index:02d}.png"
                    if self.config["pipeline"].get("save_entity_masks", True):
                        save_binary_mask(item.mask, output_dir / mask_name)
                    else:
                        mask_name = ""
                    records.append(
                        SegmentationRecord(
                            task_id=task.task_id,
                            role=task.role,
                            prompt=task.prompt,
                            instance_index=index,
                            score=float(item.score),
                            box_xyxy=box,
                            mask_path=mask_name,
                            clip_consistency_score=clip_score,
                        )
                    )
                    boxes_for_overlay.append((box, task.prompt, float(item.score)))

            relations = [
                self.relation_verifier.verify(check, by_task, (height, width)) for check in risk.relation_checks
            ]
            risk_mask = self.mask_builder.build(risk, by_task, (height, width))
            risk_mask_path = None
            overlay_path = None
            crop_path = None
            if risk_mask.max() > 0:
                risk_mask_path = f"risk_mask_{risk.risk_id}.png"
                save_binary_mask(risk_mask, output_dir / risk_mask_path)
                overlay_path = f"overlay_{risk.risk_id}.png"
                overlay = draw_overlay(image, risk_mask, boxes_for_overlay, risk.risk_name_zh)
                overlay.save(output_dir / overlay_path)
                if self.config["pipeline"].get("save_risk_crops", True):
                    crop = crop_around_mask(image, risk_mask)
                    if crop is not None:
                        crop_path = f"crop_{risk.risk_id}.jpg"
                        crop.save(output_dir / crop_path, quality=92)

            sam_scores = [record.score for record in records]
            relation_scores = [rel.score for rel in relations]
            entity_score = max(sam_scores) if sam_scores else 0.0
            relation_score = sum(relation_scores) / len(relation_scores) if relation_scores else entity_score
            clip_scores = [record.clip_consistency_score for record in records if record.clip_consistency_score is not None]
            clip_score = sum(clip_scores) / len(clip_scores) if clip_scores else None
            components = [risk.confidence, entity_score, relation_score]
            if clip_score is not None:
                components.append(float(clip_score))
            evidence_score = float(sum(components) / len(components))
            evidences.append(
                RiskEvidence(
                    risk_id=risk.risk_id,
                    risk_name_zh=risk.risk_name_zh,
                    first_pass_status=risk.status,
                    first_pass_confidence=risk.confidence,
                    observed_facts=risk.observed_facts,
                    counter_evidence=risk.counter_evidence,
                    segmentations=records,
                    relations=relations,
                    mask_strategy=risk.mask_strategy,
                    risk_mask_path=risk_mask_path,
                    overlay_path=overlay_path,
                    crop_path=crop_path,
                    evidence_score=max(0.0, min(1.0, evidence_score)),
                    uncertainties=risk.uncertainties,
                )
            )

        evidence_dump = [x.model_dump() for x in evidences]
        (output_dir / "evidence.json").write_text(
            json.dumps(evidence_dump, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        final_report = None
        management_report = None
        progress("verify", "done", f"已整理 {len(evidences)} 项风险证据")
        if self.config["pipeline"].get("run_second_pass", True):
            progress("second_pass", "running", "正在核实候选视觉证据")
            if self.config["pipeline"].get("second_pass_per_risk", False):
                final_report = self._run_per_risk_second_pass(image, output_dir, evidences)
            else:
                final_report = self._run_combined_second_pass(image, output_dir, evidences)
            if not road_v5:
                final_report = self._apply_evidence_guards(
                    final_report, evidences, image_size=(image.width, image.height)
                )
            if self.config.get("domain") == "road":
                final_report = reconcile_road_findings(first, final_report, evidences, min_conf,
                                                       threshold_overrides=self._load_threshold_overrides())
            if road_v5:
                write_scene_annotation(image, output_dir, final_report, by_task, context_tasks)
            (output_dir / "visual_verification.json").write_text(
                json.dumps(final_report.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
            )
            progress("second_pass", "done", "视觉事实已锁定")
            progress("management_report", "running", "正在生成模型处置报告")
            management_report = self._generate_management_report(output_dir, final_report)
            (output_dir / "final_report.json").write_text(
                json.dumps(management_report.model_dump(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._write_summary(output_dir, management_report)
            if road_v4:
                write_road_issue_report(image_path, output_dir, first, final_report, self.config)
            progress("management_report", "done", "模型报告已写入")
        else:
            progress("second_pass", "skipped", "当前配置未启用二次视觉确认")
            progress("management_report", "skipped", "当前配置未启用模型报告")

        screening_assessment = self._build_screening_assessment(
            trigger, first, final_report
        )
        result = InspectionResult(
            image_path=str(image_path),
            output_dir=str(output_dir),
            first_pass=first,
            evidences=evidences,
            visual_verification=final_report,
            final_report=final_report,
            management_report=management_report,
            screening_trigger=trigger,
            screening_assessment=screening_assessment,
        )
        (output_dir / "result.json").write_text(
            json.dumps(result.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return result

    def _append_screening_views(
        self,
        *,
        image: Image.Image,
        images: List[Image.Image],
        manifest: Optional[List[str]],
        trigger: Optional[ScreeningTrigger],
        screening_mask_path: str | Path | None,
        output_dir: Path,
    ) -> tuple[List[Image.Image], Optional[List[str]], Optional[ScreeningTrigger]]:
        """Add coarse detector overlay/crops as attention views, never as evidence."""
        if trigger is None or not trigger.triggered:
            return images, manifest, trigger

        region_boxes: List[tuple[str, List[float], float]] = []
        for region in trigger.suspected_regions:
            box = list(region.bbox_xyxy)
            if region.coordinate_space == "normalized_xyxy":
                box = [
                    box[0] * image.width,
                    box[1] * image.height,
                    box[2] * image.width,
                    box[3] * image.height,
                ]
            region_boxes.append((region.region_id, box, region.score))

        overlay: Optional[Image.Image] = None
        if screening_mask_path is not None:
            mask = Image.open(screening_mask_path).convert("L")
            if mask.size != image.size:
                mask = mask.resize(image.size, Image.NEAREST)
            binary = mask.point(lambda value: 255 if value > 0 else 0)
            saved_mask = output_dir / "screening_mask.png"
            binary.save(saved_mask)
            mask_box_xyxy = binary.getbbox()
            if mask_box_xyxy:
                if not region_boxes:
                    generated = ScreeningRegion(
                        region_id="coarse_mask_1",
                        bbox_xyxy=[float(value) for value in mask_box_xyxy],
                        score=trigger.anomaly_score,
                        label="coarse anomaly region",
                    )
                    trigger.suspected_regions.append(generated)
                    region_boxes.append(
                        (generated.region_id, list(generated.bbox_xyxy), generated.score)
                    )
                red = Image.new("RGB", image.size, (220, 30, 30))
                tinted = Image.blend(image, red, 0.38)
                overlay = Image.composite(tinted, image, binary)
                overlay.save(output_dir / "screening_overlay.jpg", quality=92)

        if not region_boxes and overlay is None:
            return images, manifest, trigger

        labels = list(manifest or [("Image 1: original road image" if self.config.get("domain") == "road" else "Image 1: original full construction-site image")])
        enriched = list(images)
        if overlay is not None:
            label = (
                f"Image {len(enriched) + 1}: upstream coarse anomaly mask overlay; "
                "red area is attention guidance, not confirmed risk"
            )
            labels.append(label)
            enriched.append(add_image_label(overlay, label))

        view_cfg = self.config["pipeline"].get("screening_region_views", {})
        margin = float(view_cfg.get("crop_margin_ratio", 0.25))
        max_crops = int(view_cfg.get("max_crops", 3))
        for region_id, box, score in region_boxes[:max_crops]:
            x1, y1, x2, y2 = box
            width, height = x2 - x1, y2 - y1
            if width <= 2 or height <= 2:
                continue
            crop = image.crop(
                (
                    max(0, int(x1 - margin * width)),
                    max(0, int(y1 - margin * height)),
                    min(image.width, int(x2 + margin * width)),
                    min(image.height, int(y2 + margin * height)),
                )
            )
            label = (
                f"Image {len(enriched) + 1}: expanded crop of coarse region "
                f"{region_id}, upstream_score={score:.3f}"
            )
            labels.append(label)
            enriched.append(add_image_label(crop, label))
        return enriched, labels, trigger

    @staticmethod
    def _build_screening_assessment(
        trigger: Optional[ScreeningTrigger],
        first: FirstPassResponse,
        final_report: Optional[SecondPassResponse],
    ) -> ScreeningAssessment:
        if trigger is None or not trigger.triggered:
            return ScreeningAssessment()
        if final_report is not None:
            if any(risk.verified for risk in final_report.final_risks):
                return ScreeningAssessment(
                    screening_consistency="supported",
                    overall_status="confirmed_anomaly",
                )
            if any(
                risk.manual_review_required or risk.confidence >= 0.25
                for risk in final_report.final_risks
            ):
                return ScreeningAssessment(
                    screening_consistency="uncertain",
                    overall_status="suspected_anomaly",
                )
            return ScreeningAssessment(
                screening_consistency="unsupported",
                overall_status="no_visible_anomaly",
            )
        if first.has_possible_anomaly:
            return ScreeningAssessment(
                screening_consistency="uncertain",
                overall_status="suspected_anomaly",
            )
        return ScreeningAssessment(
            screening_consistency="unsupported",
            overall_status="no_visible_anomaly",
        )

    def _run_combined_second_pass(
        self,
        image: Image.Image,
        output_dir: Path,
        evidences: List[RiskEvidence],
    ) -> SecondPassResponse:
            evidence_dump = [item.model_dump() for item in evidences]
            image_manifest = [("Image 1: original road image" if self.config.get("domain") == "road" else "Image 1: original construction-site image")]
            second_images: List[Image.Image] = [add_image_label(image, image_manifest[0])]
            max_overlays = int(self.config["pipeline"].get("second_pass_max_overlays", 6))
            ranked_evidences = sorted(evidences, key=lambda item: item.evidence_score, reverse=True)
            for evidence in ranked_evidences[:max_overlays]:
                if evidence.overlay_path:
                    label = (
                        f"Image {len(second_images) + 1}: overlay for risk_id={evidence.risk_id}"
                    )
                    image_manifest.append(label)
                    second_images.append(
                        add_image_label(load_rgb(output_dir / evidence.overlay_path), label)
                    )
                if evidence.crop_path:
                    label = (
                        f"Image {len(second_images) + 1}: crop for risk_id={evidence.risk_id}"
                    )
                    image_manifest.append(label)
                    second_images.append(
                        add_image_label(load_rgb(output_dir / evidence.crop_path), label)
                    )
            second_prompt = build_second_pass_prompt(evidence_dump, image_manifest)
            if self.config.get("domain") == "road":
                second_prompt = build_road_review_prompt(evidence_dump, image_manifest)
            raw_second = self.mllm.generate_json(second_images, second_prompt)
            (output_dir / "mllm_second_raw.txt").write_text(raw_second, encoding="utf-8")
            second_payload = self._parse_mllm_json(
                raw_second, output_dir, "mllm_second"
            )
            self._fill_risk_names(
                second_payload,
                [
                    {"risk_id": evidence.risk_id, "name_zh": evidence.risk_name_zh}
                    for evidence in evidences
                ],
                list_key="final_risks",
            )
            return SecondPassResponse.model_validate(second_payload)

    def _run_per_risk_second_pass(
        self,
        image: Image.Image,
        output_dir: Path,
        evidences: List[RiskEvidence],
    ) -> SecondPassResponse:
        """复核时一次只看一个风险，避免小模型在多风险证据间串线。"""
        final_risks: List[FinalRisk] = []
        raw_payloads: List[Dict[str, Any]] = []
        bypass_risk_ids = set(
            self.config["pipeline"].get("second_pass_bypass_risk_ids", [])
        )
        for evidence in evidences:
            if not evidence.segmentations and not self.config["pipeline"].get("road_observation_planning", False):
                final_risks.append(
                    FinalRisk(
                        risk_id=evidence.risk_id,
                        risk_name_zh=evidence.risk_name_zh,
                        verified=False,
                        confidence=min(evidence.first_pass_confidence, 0.35),
                        visible_evidence=[],
                        risk_description="未获得足够的实体定位证据，当前无法自动确认该风险。",
                        uncertainties=[*evidence.uncertainties, "关键实体未被SAM3定位。"],
                        manual_review_required=True,
                        absence_status="not_observed" if evidence.mask_strategy == "missing_subject" else "not_applicable",
                    )
                )
                continue

            if self.config["pipeline"].get(
                "skip_second_pass_on_failed_relation", False
            ):
                failed_relations = [
                    relation.relation_type
                    for relation in evidence.relations
                    if relation.relation_type != "none" and not relation.passed
                ]
                if failed_relations:
                    final_risks.append(
                        FinalRisk(
                            risk_id=evidence.risk_id,
                            risk_name_zh=evidence.risk_name_zh,
                            verified=False,
                            confidence=min(evidence.evidence_score, 0.45),
                            visible_evidence=[
                                f"SAM3共定位到{len(evidence.segmentations)}个相关实体实例。",
                                "必要空间或缺失关系核验未通过。",
                            ],
                            risk_description="必要的程序化关系核验未通过，当前不自动确认该风险。",
                            uncertainties=[
                                *evidence.uncertainties,
                                "关系核验失败：" + "、".join(sorted(set(failed_relations))),
                            ],
                            manual_review_required=True,
                            absence_status=(
                                "not_observed"
                                if evidence.mask_strategy == "missing_subject"
                                else "not_applicable"
                            ),
                        )
                    )
                    continue

            # Repeated validation showed that a second MLLM pass does not change
            # the outcome of these deterministic missing-association operators.
            # Allow a configuration to compile their already-localized evidence
            # directly, while retaining MLLM review for pose/open risks where it
            # demonstrably rejects false positives.
            if evidence.risk_id in bypass_risk_ids:
                has_missing_relation = any(
                    relation.relation_type == "missing"
                    for relation in evidence.relations
                )
                confirms_absence = has_missing_relation or evidence.mask_strategy in {
                    "missing_subject",
                    "unmatched_subject",
                }
                visible_evidence = list(evidence.observed_facts)
                visible_evidence.append(
                    f"SAM3定位到{len(evidence.segmentations)}个相关实体实例，必要关系核验通过。"
                )
                final_risks.append(
                    FinalRisk(
                        risk_id=evidence.risk_id,
                        risk_name_zh=evidence.risk_name_zh,
                        verified=True,
                        confidence=evidence.evidence_score,
                        visible_evidence=visible_evidence,
                        counter_evidence=list(evidence.counter_evidence),
                        risk_description=(
                            "第一遍可见风险描述已由SAM3实体定位和程序化关系核验支持。"
                        ),
                        uncertainties=[
                            *evidence.uncertainties,
                            "该风险使用经批次审计验证的程序化证据路径，未调用二次MLLM复核。",
                        ],
                        manual_review_required=False,
                        absence_status=(
                            "confirmed_absent" if confirms_absence else "not_applicable"
                        ),
                    )
                )
                raw_payloads.append(
                    {
                        "risk_id": evidence.risk_id,
                        "review_mode": "programmatic_evidence_bypass",
                    }
                )
                continue

            image_manifest = [("Image 1: original road image" if self.config.get("domain") == "road" else "Image 1: original construction-site image")]
            second_images: List[Image.Image] = [add_image_label(image, image_manifest[0])]
            for path_value, kind in (
                (evidence.overlay_path, "overlay"),
                (evidence.crop_path, "crop"),
            ):
                if not path_value:
                    continue
                label = f"Image {len(second_images) + 1}: {kind} for risk_id={evidence.risk_id}"
                image_manifest.append(label)
                second_images.append(add_image_label(load_rgb(output_dir / path_value), label))

            region = getattr(self, "_road_regions", {}).get(evidence.risk_id)
            if region and not evidence.crop_path:
                # A bounded observation-guided view is an aid, not a validated mask.
                x1,y1,x2,y2 = region
                margin = 0.05
                box = (int(max(0,x1-margin)*image.width), int(max(0,y1-margin)*image.height),
                       int(min(1,x2+margin)*image.width), int(min(1,y2+margin)*image.height))
                if box[2]>box[0] and box[3]>box[1]:
                    crop = image.crop(box)
                    crop.save(output_dir / f"review_region_{evidence.risk_id}.png")
                    label = f"Image {len(second_images)+1}: approximate observation region, not segmentation ground truth"
                    image_manifest.append(label)
                    second_images.append(add_image_label(crop,label))
            evidence_payload = [evidence.model_dump()]
            review_prompt = (build_road_review_prompt(evidence_payload, image_manifest)
                             if self.config.get("domain") == "road" else build_second_pass_prompt(evidence_payload, image_manifest))
            (output_dir / f"review_prompt_{evidence.risk_id}.txt").write_text(review_prompt, encoding="utf-8")
            raw = self.mllm.generate_json(second_images, review_prompt)
            (output_dir / f"mllm_second_{evidence.risk_id}_raw.txt").write_text(raw, encoding="utf-8")
            payload = self._parse_mllm_json(
                raw, output_dir, f"mllm_second_{evidence.risk_id}"
            )
            self._fill_risk_names(
                payload,
                [{"risk_id": evidence.risk_id, "name_zh": evidence.risk_name_zh}],
                list_key="final_risks",
            )
            parsed = SecondPassResponse.model_validate(payload)
            matching = next(
                (item for item in parsed.final_risks if item.risk_id == evidence.risk_id),
                None,
            )
            if matching is None:
                matching = FinalRisk(
                    risk_id=evidence.risk_id,
                    risk_name_zh=evidence.risk_name_zh,
                    verified=False,
                    confidence=min(evidence.evidence_score, 0.50),
                    visible_evidence=[],
                    risk_description="逐风险复核未返回对应风险结论。",
                    uncertainties=["本地模型输出遗漏当前risk_id。"],
                    manual_review_required=True,
                    absence_status="not_applicable",
                )
            final_risks.append(matching)
            raw_payloads.append(payload)

        (output_dir / "mllm_second_per_risk.json").write_text(
            json.dumps(raw_payloads, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        has_anomaly = any(item.verified for item in final_risks)
        return SecondPassResponse(
            overall_has_anomaly=has_anomaly,
            overall_summary=(
                "逐风险视觉复核确认存在可见风险。"
                if has_anomaly
                else "逐风险视觉复核未自动确认风险；未检出不代表已确认安全。"
            ),
            final_risks=final_risks,
        )

    def _build_first_pass_images(
        self, image: Image.Image
    ) -> tuple[List[Image.Image], Optional[List[str]]]:
        """Build bounded multi-scale views for small PPE and edge hazards.

        SAM3 person boxes provide attention only.  They are expanded into person,
        head and waist/hook views, while deterministic overlapping scene tiles
        preserve person-independent edge/opening discovery.  The original image
        remains the sole global scene and ``max_total_views`` bounds VLM cost.
        """
        precheck = self.config["pipeline"].get("person_precheck", {})
        if not precheck.get("enabled", False):
            self._last_person_precheck_instances = []
            return [image], None
        from site_safety.schemas import SAM3Task

        task = SAM3Task(
            task_id="person_precheck",
            role="subject",
            prompt=str(precheck.get("prompt", "person")),
        )
        self.sam3.set_image(image)
        min_score = float(precheck.get("min_score", 0.30))
        instances = [item for item in self.sam3.segment(task) if item.score >= min_score]
        instances.sort(key=lambda item: item.score, reverse=True)
        margin = float(precheck.get("crop_margin_ratio", 0.35))
        max_crops = int(precheck.get("max_crops", 6))
        min_side = int(precheck.get("upscale_min_side", 448))
        max_total_views = max(1, int(precheck.get("max_total_views", 12)))

        manifest = [("Image 1: original road image" if self.config.get("domain") == "road" else "Image 1: original full construction-site image")]
        labeled: List[Image.Image] = [add_image_label(image, manifest[0])]
        self._last_person_precheck_instances = list(instances[:max_crops])
        person_boxes: List[tuple[int, tuple[float, float, float, float]]] = []

        def append_crop(box: tuple[float, float, float, float], label: str) -> bool:
            if len(labeled) >= max_total_views:
                return False
            x1, y1, x2, y2 = box
            x1 = max(0, min(image.width, int(x1)))
            y1 = max(0, min(image.height, int(y1)))
            x2 = max(0, min(image.width, int(x2)))
            y2 = max(0, min(image.height, int(y2)))
            if x2 - x1 <= 4 or y2 - y1 <= 4:
                return False
            crop = image.crop((x1, y1, x2, y2))
            short_side = min(crop.size)
            if short_side and short_side < min_side:
                scale = min_side / short_side
                crop = crop.resize(
                    (int(crop.width * scale), int(crop.height * scale)), Image.LANCZOS
                )
            numbered_label = f"Image {len(labeled) + 1}: {label}"
            manifest.append(numbered_label)
            labeled.append(add_image_label(crop, numbered_label))
            return True

        for index, instance in enumerate(instances[:max_crops], start=1):
            box = instance.box_xyxy or mask_box(instance.mask)
            if not box:
                continue
            x1, y1, x2, y2 = box
            width, height = x2 - x1, y2 - y1
            if width <= 4 or height <= 4:
                continue
            person_boxes.append((index, (x1, y1, x2, y2)))
            append_crop(
                (
                    x1 - margin * width,
                    y1 - margin * height,
                    x2 + margin * width,
                    y2 + margin * height,
                ),
                f"person crop {index}; inspect the same worker only",
            )

        if len(labeled) == 1:
            return [image], None
        return labeled, manifest

    def _build_specialized_audit_batches(
        self, image: Image.Image
    ) -> List[tuple[str, List[Image.Image], List[str]]]:
        """Create service-safe PPE and edge batches with at most five images each."""
        audit_cfg = self.config["pipeline"].get("structured_risk_audit", {})
        views_cfg = audit_cfg.get("specialized_views", {})
        if not views_cfg.get("enabled", False):
            return []

        from site_safety.schemas import SAM3Task

        min_side = int(views_cfg.get("upscale_min_side", 448))

        def labeled_crop(
            box: tuple[float, float, float, float], label: str
        ) -> Optional[Image.Image]:
            x1, y1, x2, y2 = box
            x1 = max(0, min(image.width, int(x1)))
            y1 = max(0, min(image.height, int(y1)))
            x2 = max(0, min(image.width, int(x2)))
            y2 = max(0, min(image.height, int(y2)))
            if x2 - x1 <= 4 or y2 - y1 <= 4:
                return None
            crop = image.crop((x1, y1, x2, y2))
            short_side = min(crop.size)
            if short_side and short_side < min_side:
                scale = min_side / short_side
                crop = crop.resize(
                    (int(crop.width * scale), int(crop.height * scale)), Image.LANCZOS
                )
            return add_image_label(crop, label)

        batches: List[tuple[str, List[Image.Image], List[str]]] = []
        tile_cfg = views_cfg.get("scene_tiling", {})
        if tile_cfg.get("enabled", False):
            columns = max(1, min(4, int(tile_cfg.get("columns", 3))))
            overlap = min(0.45, max(0.0, float(tile_cfg.get("overlap_ratio", 0.15))))
            tile_width = image.width / max(1.0, columns - overlap * (columns - 1))
            step_x = tile_width * (1.0 - overlap)
            manifest = [("Image 1: original road image" if self.config.get("domain") == "road" else "Image 1: original full construction-site image")]
            images = [add_image_label(image, manifest[0])]
            for column in range(columns):
                x1 = min(image.width - tile_width, column * step_x)
                label = (
                    f"Image {len(images) + 1}: scene tile c{column + 1}; "
                    "audit platform, excavation, opening and road edges"
                )
                crop = labeled_crop((x1, 0, x1 + tile_width, image.height), label)
                if crop is not None:
                    manifest.append(label)
                    images.append(crop)
            batches.append(("edge_tiles", images, manifest))

        ppe_cfg = views_cfg.get("ppe_roi", {})
        if ppe_cfg.get("enabled", False):
            task = SAM3Task(
                task_id="specialized_person_precheck",
                role="subject",
                prompt=str(ppe_cfg.get("prompt", "person")),
            )
            self.sam3.set_image(image)
            min_score = float(ppe_cfg.get("min_score", 0.45))
            instances = [
                item for item in self.sam3.segment(task) if item.score >= min_score
            ]
            instances.sort(key=lambda item: item.score, reverse=True)
            max_people = max(0, int(ppe_cfg.get("max_people", 4)))
            boxes = []
            for instance in instances[:max_people]:
                box = instance.box_xyxy or mask_box(instance.mask)
                if box and box[2] - box[0] > 4 and box[3] - box[1] > 4:
                    boxes.append(tuple(float(value) for value in box))
            for batch_index in range(0, len(boxes), 2):
                manifest = [("Image 1: original road image" if self.config.get("domain") == "road" else "Image 1: original full construction-site image")]
                images = [add_image_label(image, manifest[0])]
                for local_index, (x1, y1, x2, y2) in enumerate(
                    boxes[batch_index : batch_index + 2], start=batch_index + 1
                ):
                    width, height = x2 - x1, y2 - y1
                    definitions = [
                        (
                            (
                                x1 - 0.35 * width,
                                y1 - 0.12 * height,
                                x2 + 0.35 * width,
                                y1 + 0.42 * height,
                            ),
                            f"person {local_index} head ROI; verify industrial safety helmet",
                        ),
                        (
                            (
                                x1 - 0.80 * width,
                                y1 + 0.18 * height,
                                x2 + 0.80 * width,
                                y2 + 0.25 * height,
                            ),
                            f"person {local_index} waist-back-hook ROI; verify harness, lanyard and anchor",
                        ),
                    ]
                    for box, description in definitions:
                        label = f"Image {len(images) + 1}: {description}"
                        crop = labeled_crop(box, label)
                        if crop is not None:
                            manifest.append(label)
                            images.append(crop)
                if len(images) > 1:
                    batches.append(
                        (f"ppe_roi_{batch_index // 2 + 1:02d}", images, manifest)
                    )
        return batches

    @staticmethod
    def _fill_risk_names(
        payload: Dict[str, Any],
        catalog_items: List[Dict[str, Any]],
        list_key: str | None = None,
    ) -> None:
        names = {
            str(item.get("risk_id")): str(
                item.get("risk_name_zh") or item.get("name_zh") or item.get("risk_id")
            )
            for item in catalog_items
            if item.get("risk_id")
        }
        keys = [list_key] if list_key else ["candidate_assessments", "open_discoveries"]
        for key in keys:
            for item in payload.get(key, []) or []:
                if not isinstance(item, dict):
                    continue
                if not item.get("risk_name_zh"):
                    risk_id = str(item.get("risk_id", "unknown_risk"))
                    item["risk_name_zh"] = item.get("name_zh") or names.get(risk_id, risk_id)

    def _apply_deterministic_candidate_fallbacks(
        self,
        payload: Dict[str, Any],
        catalog_items: List[Dict[str, Any]],
    ) -> None:
        """Recover a bounded candidate from facts the MLLM already stated.

        This is routing, not a final risk verdict: the synthesized candidate is
        ``uncertain`` and must still pass SAM3 entity and geometric checks.
        No additional model request is made.
        """
        cfg = self.config["pipeline"].get("deterministic_candidate_fallbacks", {})
        if not cfg.get("enabled", False):
            return
        candidates = payload.setdefault("candidate_assessments", [])
        existing = {
            str(item.get("risk_id"))
            for item in candidates
            if isinstance(item, dict) and item.get("risk_id")
        }
        names = {
            str(item.get("risk_id")): str(
                item.get("risk_name_zh") or item.get("name_zh") or item.get("risk_id")
            )
            for item in catalog_items
            if item.get("risk_id")
        }
        scene_summary = str(payload.get("scene_summary") or "")
        if not scene_summary:
            return
        for rule in cfg.get("rules", []) or []:
            if not isinstance(rule, dict):
                continue
            risk_id = str(rule.get("risk_id") or "").strip()
            groups = rule.get("all_of_any") or []
            if not risk_id or risk_id in existing or not groups:
                continue
            if not all(
                any(str(token) in scene_summary for token in group)
                for group in groups
                if group
            ):
                continue
            candidates.append(
                {
                    "risk_id": risk_id,
                    "risk_name_zh": names.get(risk_id, risk_id),
                    "status": "uncertain",
                    "confidence": float(rule.get("confidence", 0.60)),
                    "observed_facts": [scene_summary],
                    "counter_evidence": [],
                    "uncertainties": [
                        str(
                            rule.get("uncertainty_message")
                            or "由场景摘要中的实体共现线索回填候选，仍需SAM3和几何关系核验。"
                        )
                    ],
                }
            )
            existing.add(risk_id)
            payload["has_possible_anomaly"] = True

    @classmethod
    def _normalize_first_pass_payload(
        cls,
        payload: Dict[str, Any],
        catalog_items: List[Dict[str, Any]],
        operator_registry: Optional[RiskOperatorRegistry] = None,
        preserve_confidence: bool = False,
    ) -> None:
        operator_registry = operator_registry or load_default_risk_operator_registry()
        discoveries = payload.get("open_discoveries", []) or []
        normalized_discoveries = []
        for item in discoveries:
            # 本地小模型有时会把开放发现简写成字符串；统一转换为结构化对象。
            if isinstance(item, str):
                normalized_discoveries.append({"description": item})
            elif isinstance(item, dict):
                normalized_discoveries.append(item)
        payload["open_discoveries"] = normalized_discoveries
        cls._fill_risk_names(payload, catalog_items)
        scene_summary = str(payload.get("scene_summary") or "")
        operator_registry.promote_candidates(payload, scene_summary)
        for item in payload.get("candidate_assessments", []) or []:
            if not isinstance(item, dict):
                continue
            if not preserve_confidence:
                cls._normalize_candidate_confidence(item)
            cls._compile_target_entities(item)
            operator_registry.complete_candidate(item)
            cls._normalize_mask_strategy(item)
        for index, item in enumerate(normalized_discoveries, start=1):
            discovery_type = str(item.get("discovery_type") or "").strip()
            name = str(
                item.get("name_zh")
                or item.get("description")
                or item.get("risk_name_zh")
                or f"开放发现{index}"
            ).strip()
            if not item.get("risk_id"):
                slug_source = discovery_type or f"discovery_{index}"
                slug = re.sub(r"[^a-z0-9]+", "_", slug_source.lower()).strip("_")
                item["risk_id"] = f"open_{slug or f'discovery_{index}'}"
            item["risk_name_zh"] = name[:80]
            item.setdefault("status", "present")
            item.setdefault("confidence", 0.0 if preserve_confidence else 0.65)
            if not preserve_confidence:
                cls._normalize_candidate_confidence(item)
            cls._compile_target_entities(item)
            if not item.get("observed_facts"):
                description = item.get("description")
                item["observed_facts"] = [str(description)] if description else []
            if not item.get("sam3_tasks"):
                operator_registry.complete_open_discovery(item)
                if not item.get("sam3_tasks"):
                    prompt = item.get("evidence") or discovery_type.replace("_", " ")
                    if prompt:
                        item["sam3_tasks"] = [
                            {
                                "task_id": f"{item['risk_id']}_evidence_01",
                                "role": "evidence",
                                "prompt": str(prompt),
                                "expected_count": 1,
                            }
                        ]
                    else:
                        item["sam3_tasks"] = []
            item.setdefault("relation_checks", [])
            item.setdefault("mask_strategy", "entity_union")
            cls._normalize_mask_strategy(item)
            item.setdefault("uncertainties", [])
            item.setdefault("counter_evidence", [])

    @staticmethod
    def _normalize_candidate_confidence(item: Dict[str, Any]) -> None:
        status = str(item.get("status") or "uncertain")
        try:
            confidence = float(item.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        if status == "present" and confidence < 0.25:
            item["confidence"] = 0.65

    @staticmethod
    def _compile_target_entities(item: Dict[str, Any]) -> None:
        """Compile compact semantic RiskSpec into positive SAM3 tasks."""
        entities = item.get("target_entities") or []
        if not isinstance(entities, list) or not entities:
            return
        risk_id = str(item.get("risk_id") or "dynamic_risk")
        allowed_roles = {
            "subject",
            "protective_item",
            "hazard_source",
            "region",
            "evidence",
            "other",
        }
        forbidden = re.compile(
            r"\b(without|missing|unsafe|dangerous|violation|risk|hazardous)\b",
            flags=re.IGNORECASE,
        )
        tasks: List[Dict[str, Any]] = []
        task_by_signature: Dict[tuple[str, str], Dict[str, Any]] = {}
        entity_to_task: Dict[str, str] = {}
        for index, entity in enumerate(entities, start=1):
            if not isinstance(entity, dict):
                continue
            entity_id = str(entity.get("entity_id") or f"entity_{index}")
            role = str(entity.get("role") or "other")
            if role not in allowed_roles:
                role = "other"
            category = forbidden.sub("", str(entity.get("category") or "")).strip(" ,-")
            if not category:
                continue
            attributes = entity.get("attributes") or []
            if isinstance(attributes, str):
                attributes = [attributes]
            clean_attributes = [
                forbidden.sub("", str(value)).strip(" ,-")
                for value in attributes
                if forbidden.sub("", str(value)).strip(" ,-")
            ]
            location = forbidden.sub("", str(entity.get("location") or "")).strip(" ,-")
            if role == "subject":
                prompt_attributes = clean_attributes
                if risk_id == "missing_helmet":
                    # “缺安全帽”场景中，MLLM有时会把黑发/头部轮廓误写成普通帽子。
                    # 头部服饰属性一旦拼入提示会导致SAM3漏掉目标人员，因此这里只
                    # 保留衣着/姿态等非头部属性，帽子由独立PPE关系任务判断。
                    headwear = re.compile(
                        r"\b(helmet|hard[ -]?hat|hat|cap|beanie|headwear)\b",
                        flags=re.IGNORECASE,
                    )
                    prompt_attributes = [
                        value for value in clean_attributes if not headwear.search(value)
                    ]
            elif role == "protective_item":
                color_words = {
                    "yellow",
                    "red",
                    "orange",
                    "white",
                    "blue",
                    "green",
                    "black",
                }
                prompt_attributes = [
                    value for value in clean_attributes if value.lower() in color_words
                ]
            else:
                # SAM3 generalizes better from a positive noun phrase plus location;
                # long action/state attributes often suppress otherwise valid masks.
                prompt_attributes = []
            prompt_parts = [category, *prompt_attributes]
            if location:
                prompt_parts.append(f"at {location}")
            prompt = " ".join(part for part in prompt_parts if part)
            signature = (role, prompt.lower())
            if signature in task_by_signature:
                existing = task_by_signature[signature]
                current_count = existing.get("expected_count") or 1
                new_count = entity.get("expected_count") or 1
                existing["expected_count"] = int(current_count) + int(new_count)
                entity_to_task[entity_id] = str(existing["task_id"])
                continue
            task_id = f"{risk_id}_{re.sub(r'[^a-zA-Z0-9_]+', '_', entity_id)}"
            entity_to_task[entity_id] = task_id
            task = {
                "task_id": task_id,
                "role": role,
                "prompt": prompt,
                "expected_count": entity.get("expected_count"),
            }
            tasks.append(task)
            task_by_signature[signature] = task
        if not tasks:
            return
        item["sam3_tasks"] = tasks

        relation_spec = item.get("relation_spec") or {}
        if not isinstance(relation_spec, dict):
            relation_spec = {}
        relation_type = str(relation_spec.get("type") or "none")
        allowed_relations = {
            "none",
            "below_and_horizontal_overlap",
            "near",
            "inside",
            "overlap",
            "missing",
            "missing_association",
            "blocks_region",
        }
        if relation_type not in allowed_relations:
            relation_type = "none"
        subject_ids = [
            entity_to_task[value]
            for value in relation_spec.get("subject_entity_ids", []) or []
            if value in entity_to_task
        ]
        object_ids = [
            entity_to_task[value]
            for value in relation_spec.get("object_entity_ids", []) or []
            if value in entity_to_task
        ]
        if not subject_ids:
            subject_ids = [
                task["task_id"] for task in tasks if task["role"] in {"subject", "evidence"}
            ]
        if not object_ids:
            object_ids = [
                task["task_id"]
                for task in tasks
                if task["role"] in {"protective_item", "hazard_source", "region"}
            ]
        item["relation_checks"] = (
            [
                {
                    "type": relation_type,
                    "subject_task_ids": subject_ids,
                    "object_task_ids": object_ids,
                    "params": relation_spec.get("params") or {},
                }
            ]
            if relation_type != "none"
            else []
        )
        if relation_type == "missing_association":
            item["mask_strategy"] = "unmatched_subject"
        else:
            item.setdefault("mask_strategy", "entity_union")

    @staticmethod
    def _normalize_mask_strategy(item: Dict[str, Any]) -> None:
        valid = {
            "entity_union",
            "subject_only",
            "object_only",
            "intersection",
            "projected_below",
            "missing_subject",
            "expanded_object_zone",
            "unmatched_subject",
        }
        strategy = str(item.get("mask_strategy") or "")
        if strategy in valid:
            return
        relation_checks = item.get("relation_checks") or []
        relation_type = (
            str(relation_checks[0].get("type"))
            if relation_checks and isinstance(relation_checks[0], dict)
            else "none"
        )
        aliases = {
            "missing_association": "unmatched_subject",
            "missing": "missing_subject",
            "below_and_horizontal_overlap": "projected_below",
            "blocks_region": "intersection",
        }
        item["mask_strategy"] = aliases.get(relation_type, "entity_union")

    def _generate_management_report(
        self,
        output_dir: Path,
        visual_report: SecondPassResponse,
    ) -> ManagementReport:
        if self.report_llm is None:
            return self._build_template_report(visual_report)

        try:
            memory_context = self._load_report_memory()
            if self.config.get("domain") == "road":
                from site_safety.road_domain import build_road_management_prompt
                prompt = build_road_management_prompt(visual_report.model_dump(), memory_context)
            else:
                prompt = build_report_prompt(visual_report.model_dump(), memory_context)
            raw_report = self.report_llm.generate_json([], prompt)
            report_tag = str(self.config.get("report_llm", {}).get("generated_by", "glm"))
            (output_dir / f"{report_tag}_report_raw.txt").write_text(raw_report, encoding="utf-8")
            report = ManagementReport.model_validate(parse_json_object(raw_report))
            report.generated_by = report_tag
            return self._guard_management_report(report, visual_report)
        except Exception as exc:
            report_tag = str(self.config.get("report_llm", {}).get("generated_by", "glm"))
            (output_dir / f"{report_tag}_report_error.txt").write_text(
                f"{type(exc).__name__}: {exc}",
                encoding="utf-8",
            )
            return self._build_template_report(visual_report)

    def _load_report_memory(self) -> List[Dict[str, Any]]:
        memory: List[Dict[str, Any]] = []
        for configured_path in self.config.get("report_llm", {}).get("memory_paths", []):
            path = Path(configured_path)
            if not path.is_absolute():
                path = self.project_root / path
            if not path.is_file():
                continue
            value = json.loads(path.read_text(encoding="utf-8"))
            memory.append({"source": str(configured_path), "content": value})
        return memory

    @staticmethod
    def _build_template_report(visual_report: SecondPassResponse) -> ManagementReport:
        return ManagementReport(
            assessment_quality=visual_report.assessment_quality,
            executive_summary=visual_report.overall_summary,
            risks=[
                ReportRiskSection(
                    risk_id=risk.risk_id,
                    risk_name_zh=risk.risk_name_zh,
                    verified=risk.verified,
                    confidence=risk.confidence,
                    summary=risk.risk_description,
                    evidence_state=risk.evidence_state,
                    evidence=risk.visible_evidence,
                    counter_evidence=risk.counter_evidence,
                    uncertainties=risk.uncertainties,
                    manual_review_required=risk.manual_review_required,
                    absence_status=risk.absence_status,
                    management_notes=[],
                )
                for risk in visual_report.final_risks
            ],
            follow_up_actions=(
                ["对标记为需人工复核的风险进行现场或原图复核。"]
                if any(risk.manual_review_required for risk in visual_report.final_risks)
                else []
            ),
            limitations=["报告仅基于单张图像及自动视觉证据，不代表完整现场安全评估。"],
            generated_by="deterministic_template",
        )

    @staticmethod
    def _guard_management_report(
        report: ManagementReport,
        visual_report: SecondPassResponse,
    ) -> ManagementReport:
        visual_by_risk = {risk.risk_id: risk for risk in visual_report.final_risks}
        guarded_sections: List[ReportRiskSection] = []
        for section in report.risks:
            visual = visual_by_risk.get(section.risk_id)
            if visual is None:
                continue
            section.summary = visual.risk_description
            section.risk_name_zh = visual.risk_name_zh
            section.verified = visual.verified
            section.confidence = visual.confidence
            section.evidence = list(visual.visible_evidence)
            section.counter_evidence = list(visual.counter_evidence)
            section.uncertainties = list(visual.uncertainties)
            section.manual_review_required = visual.manual_review_required
            section.evidence_state = visual.evidence_state
            section.absence_status = visual.absence_status
            guarded_sections.append(section)
        existing = {section.risk_id for section in guarded_sections}
        for visual in visual_report.final_risks:
            if visual.risk_id not in existing:
                guarded_sections.append(
                    ReportRiskSection(
                        risk_id=visual.risk_id,
                        risk_name_zh=visual.risk_name_zh,
                        verified=visual.verified,
                        confidence=visual.confidence,
                        summary=visual.risk_description,
                        evidence_state=visual.evidence_state,
                        evidence=visual.visible_evidence,
                        counter_evidence=visual.counter_evidence,
                        uncertainties=visual.uncertainties,
                        manual_review_required=visual.manual_review_required,
                        absence_status=visual.absence_status,
                    )
                )
        report.risks = guarded_sections
        report.assessment_quality = visual_report.assessment_quality
        report.executive_summary = visual_report.overall_summary
        return report

    def _apply_evidence_guards(
        self,
        report: SecondPassResponse,
        evidences: List[RiskEvidence],
        *,
        image_size: Optional[tuple[int, int]] = None,
    ) -> SecondPassResponse:
        evidence_by_risk = {evidence.risk_id: evidence for evidence in evidences}
        clip_threshold = float(self.config.get("clip", {}).get("minimum_consistency_score", 0.20))
        threshold_overrides = self._load_threshold_overrides()
        downgraded = False

        for risk in report.final_risks:
            semantic_disproven = False
            # 审批生效的按风险阈值覆盖：verified但低于人工批准的下限 → 降级转人工
            override = threshold_overrides.get(risk.risk_id)
            if override is not None and risk.verified:
                min_conf = float(override.get("min_verified_confidence", 0.0))
                if risk.confidence < min_conf:
                    risk.verified = False
                    risk.manual_review_required = True
                    self._append_unique(
                        risk.uncertainties,
                        f"置信度低于该风险经人工审批的自动确认下限{min_conf:.2f}，转人工复核。",
                    )
                    downgraded = True

            evidence = evidence_by_risk.get(risk.risk_id)
            if evidence is None:
                risk.verified = False
                risk.confidence = min(risk.confidence, 0.25)
                risk.manual_review_required = True
                self._append_unique(risk.uncertainties, "最终风险没有对应的结构化定位证据。")
                downgraded = True
                continue

            if risk.risk_id == "missing_helmet" and risk.verified:
                semantic_text = " ".join(
                    [risk.risk_description, *risk.visible_evidence]
                )
                supports_missing = bool(
                    re.search(
                        r"(未佩戴安全帽|未戴安全帽|无安全帽|未见安全帽|裸头|裸发|普通帽)",
                        semantic_text,
                    )
                )
                explicit_negative = not supports_missing and bool(
                    re.search(
                        r"(未发现.{0,10}未佩戴安全帽|(?:所有|全部|均).{0,20}"
                        r"(?:已|有|正确)?佩戴.{0,5}安全帽)",
                        semantic_text,
                    )
                )
                if explicit_negative:
                    semantic_disproven = True
                    risk.verified = False
                    risk.confidence = min(risk.confidence, 0.05)
                    risk.manual_review_required = False
                    self._append_unique(
                        risk.uncertainties,
                        "二次复核文字明确否定安全帽缺失，已纠正与verified布尔值的矛盾。",
                    )
                    downgraded = True

            if not evidence.segmentations:
                risk.verified = False
                risk.confidence = min(risk.confidence, 0.35)
                risk.manual_review_required = True
                risk.visible_evidence = []
                risk.risk_description = "未获得足够的实体定位证据，当前无法自动确认该风险。"
                self._append_unique(risk.uncertainties, "关键实体未被SAM3定位。")
                downgraded = True

            advisory_relation_types = set(
                self.config["pipeline"]
                .get("relation_policy", {})
                .get("advisory_types", [])
            )
            failed_required_relations = [
                relation.relation_type
                for relation in evidence.relations
                if relation.relation_type not in {"none", "missing"}
                and relation.relation_type not in advisory_relation_types
                and not relation.passed
            ]
            if failed_required_relations:
                risk.verified = False
                risk.confidence = min(risk.confidence, 0.45)
                risk.manual_review_required = True
                if evidence.segmentations:
                    risk.visible_evidence = [
                        f"SAM3共定位到{len(evidence.segmentations)}个相关实体实例。",
                        "必要空间关系核验未通过。",
                    ]
                self._append_unique(
                    risk.uncertainties,
                    "必要空间关系核验失败：" + "、".join(sorted(set(failed_required_relations))),
                )
                downgraded = True

            # confirmed_absent置信度上限必须无条件生效：
            # 第一遍未生成missing关系检查时，下方分支不会执行，上限仍需兜底。
            if risk.absence_status == "confirmed_absent":
                confirmed_cap = float(
                    self.config["pipeline"]
                    .get("relation_defaults", {})
                    .get("confirmed_absence_confidence_cap", 0.90)
                )
                risk.confidence = min(risk.confidence, confirmed_cap)

            # 锚点过小守卫：目标在原图中过小时，裁剪画质不足以支撑"确认缺失"，
            # 只允许not_observed转人工（防止两阶段放大裁剪导致的过度自信）。
            if risk.absence_status == "confirmed_absent" and image_size is not None:
                min_ratio = float(
                    self.config["pipeline"]
                    .get("relation_defaults", {})
                    .get("min_confirmed_subject_height_ratio", 0.10)
                )
                subject_boxes = [
                    record.box_xyxy
                    for record in evidence.segmentations
                    if record.role == "subject" and record.box_xyxy
                ] or [record.box_xyxy for record in evidence.segmentations if record.box_xyxy]
                height = float(image_size[1]) or 1.0
                max_ratio = max(
                    ((box[3] - box[1]) / height for box in subject_boxes), default=0.0
                )
                if 0.0 < max_ratio < min_ratio:
                    risk.verified = False
                    risk.absence_status = "not_observed"
                    risk.confidence = min(risk.confidence, 0.60)
                    risk.manual_review_required = True
                    self._append_unique(
                        risk.uncertainties,
                        f"缺失锚点目标过小（高度占比{max_ratio:.2f}<{min_ratio:.2f}），"
                        "画质不足以自动确认缺失，转人工复核。",
                    )
                    downgraded = True

            missing_relations = [
                relation
                for relation in evidence.relations
                if relation.relation_type == "missing"
            ]
            if missing_relations:
                confirmed_by_relation = all(relation.passed for relation in missing_relations)
                confirmed_by_visual = risk.absence_status == "confirmed_absent"
                has_visible_evidence = bool(risk.visible_evidence)
                if confirmed_by_relation and confirmed_by_visual and has_visible_evidence:
                    confirmed_cap = float(
                        self.config["pipeline"]
                        .get("relation_defaults", {})
                        .get("confirmed_absence_confidence_cap", 0.90)
                    )
                    risk.confidence = min(risk.confidence, confirmed_cap)
                elif risk.absence_status == "occluded":
                    risk.verified = False
                    risk.confidence = min(risk.confidence, 0.35)
                    risk.manual_review_required = True
                    self._append_unique(
                        risk.uncertainties,
                        "关键防护检查区域被遮挡，无法确认防护物缺失。",
                    )
                    downgraded = True
                else:
                    risk.verified = False
                    risk.absence_status = "not_observed"
                    risk.confidence = min(risk.confidence, 0.60)
                    risk.manual_review_required = True
                    self._append_unique(
                        risk.uncertainties,
                        "仅未观察到防护物，尚未形成可见区域内的确认缺失证据。",
                    )
                    downgraded = True

            clip_scores = [
                record.clip_consistency_score
                for record in evidence.segmentations
                if record.clip_consistency_score is not None
            ]
            if clip_scores and min(clip_scores) < clip_threshold:
                risk.confidence = min(risk.confidence, 0.55)
                risk.manual_review_required = True
                self._append_unique(
                    risk.uncertainties,
                    f"存在低于阈值{clip_threshold:.2f}的CLIP语义一致性结果。",
                )

            relation_preservation = self.config["pipeline"].get(
                "relation_evidence_preservation", {}
            )
            allowed_risks = set(
                relation_preservation.get("risk_ids", ["machinery_proximity"])
            )
            qualifying_relations = [
                relation
                for relation in evidence.relations
                if relation.relation_type
                in set(relation_preservation.get("relation_types", ["near"]))
                and relation.passed
                and relation.score
                >= float(relation_preservation.get("min_relation_score", 0.70))
            ]
            if (
                relation_preservation.get("enabled", False)
                and not semantic_disproven
                and not risk.verified
                and risk.risk_id in allowed_risks
                and evidence.evidence_score
                >= float(relation_preservation.get("min_evidence_score", 0.70))
                and bool(qualifying_relations)
                and not failed_required_relations
                and (not clip_scores or min(clip_scores) >= clip_threshold)
            ):
                best_relation_score = max(item.score for item in qualifying_relations)
                risk.verified = True
                risk.confidence = max(
                    risk.confidence,
                    min(evidence.evidence_score, best_relation_score),
                )
                risk.manual_review_required = True
                self._append_unique(
                    risk.uncertainties,
                    "可靠实体定位与必要空间关系均通过；保留程序化风险结论并要求人工复核。",
                )

            preservation = self.config["pipeline"].get("strong_evidence_preservation", {})
            if (
                preservation.get("enabled", False)
                and not semantic_disproven
                and not risk.verified
                and evidence.first_pass_status == "present"
                and evidence.first_pass_confidence
                >= float(preservation.get("min_first_pass_confidence", 0.85))
                and evidence.evidence_score >= float(preservation.get("min_evidence_score", 0.70))
                and bool(evidence.segmentations)
                and not failed_required_relations
                and (not clip_scores or min(clip_scores) >= clip_threshold)
            ):
                risk.verified = True
                risk.confidence = max(
                    risk.confidence,
                    min(evidence.first_pass_confidence, evidence.evidence_score),
                )
                risk.manual_review_required = True
                self._append_unique(
                    risk.uncertainties,
                    "二次视觉结论与第一遍高置信度判断及定位证据冲突；保留风险并要求人工复核。",
                )

            # 最终一致性守卫：任何自动确认都必须达到全局最低置信度。
            # 防止模型返回 verified=true、confidence=0 之类自相矛盾的结果。
            global_min_verified = float(
                self.config["pipeline"].get("global_min_verified_confidence", 0.0)
            )
            if risk.verified and risk.confidence < global_min_verified:
                risk.verified = False
                risk.manual_review_required = True
                self._append_unique(
                    risk.uncertainties,
                    f"自动确认置信度低于全局下限{global_min_verified:.2f}，转人工复核。",
                )
                downgraded = True

        report.overall_has_anomaly = any(risk.verified for risk in report.final_risks)
        if downgraded and not report.overall_has_anomaly:
            report.overall_summary = (
                "自动证据门控未确认任何风险；存在定位缺失或空间关系校验失败的候选，需人工复核。"
            )
        return report

    def _load_threshold_overrides(self) -> Dict[str, Dict[str, Any]]:
        """加载经人工审批生效的按风险阈值覆盖（复盘学习闭环的最后一环）。

        文件由审批流写入（serve_demo/正式后端），每次inspect时重读，
        审批通过即刻生效、无需重启。文件不存在时返回空。
        """
        path = Path(
            self.config["pipeline"].get(
                "threshold_overrides_path", "configs/threshold_overrides.json"
            )
        )
        if not path.is_absolute():
            path = self.project_root / path
        if not path.is_file():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        overrides = payload.get("risk_overrides", {})
        return overrides if isinstance(overrides, dict) else {}

    @staticmethod
    def _append_unique(items: List[str], message: str) -> None:
        if message not in items:
            items.append(message)

    @staticmethod
    def _write_summary(output_dir: Path, report: ManagementReport) -> None:
        lines = [f"# {report.report_title}", "", report.executive_summary, ""]
        for risk in report.risks:
            lines.extend(
                [
                    f"## {risk.risk_name_zh}",
                    "",
                    f"- 是否确认：{'是' if risk.verified else '否'}",
                    f"- 置信度：{risk.confidence:.3f}",
                    f"- 需人工复核：{'是' if risk.manual_review_required else '否'}",
                    f"- 防护缺失状态：{risk.absence_status}",
                    f"- 风险说明：{risk.summary}",
                    "- 可见证据：",
                ]
            )
            lines.extend([f"  - {x}" for x in risk.evidence] or ["  - 无"])
            lines.append("- 不确定信息：")
            lines.extend([f"  - {x}" for x in risk.uncertainties] or ["  - 无"])
            lines.append("- 管理备注：")
            lines.extend([f"  - {x}" for x in risk.management_notes] or ["  - 无"])
            lines.append("")
        if report.follow_up_actions:
            lines.extend(["## 后续动作", ""])
            lines.extend([f"- {x}" for x in report.follow_up_actions])
            lines.append("")
        if report.limitations:
            lines.extend(["## 使用边界", ""])
            lines.extend([f"- {x}" for x in report.limitations])
            lines.append("")
        (output_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")
