import json
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError
from PIL import Image

from site_safety.adapters.base import MaskInstance
from site_safety.factory import build_inspector
from site_safety.pipeline.mask_builder import RiskMaskBuilder
from site_safety.pipeline.orchestrator import TrainingFreeInspector
from site_safety.risk_operators import load_default_risk_operator_registry
from site_safety.prompting.first_pass import (
    build_open_risk_discovery_prompt,
    build_person_risk_discovery_prompt,
)
from site_safety.prompting.risk_audit import build_structured_risk_audit_prompt
from site_safety.screening import parse_screening_trigger, screening_prompt_context


def test_malformed_mllm_json_uses_a_format_only_repair_retry(tmp_path: Path) -> None:
    class RepairingMLLM:
        def __init__(self) -> None:
            self.calls: list[tuple[list[object], str]] = []

        def generate_json(self, images: object, prompt: str) -> str:
            self.calls.append((list(images), prompt))
            return '{"scene_summary": "修复成功", "has_possible_anomaly": false}'

    inspector = object.__new__(TrainingFreeInspector)
    mllm = RepairingMLLM()
    inspector.mllm = mllm
    payload = inspector._parse_mllm_json(
        '{"scene_summary": "缺少结束引号}', tmp_path, "mllm_discovery"
    )

    assert payload["scene_summary"] == "修复成功"
    assert len(mllm.calls) == 1
    assert mllm.calls[0][0] == []
    assert "只做 JSON 格式修复" in mllm.calls[0][1]
    assert (tmp_path / "mllm_discovery_json_repair_raw.txt").exists()
    assert (tmp_path / "mllm_discovery_json_repaired.json").exists()


def test_structured_audit_prompt_requires_all_rules_and_marks_clip_as_hint() -> None:
    prompt = build_structured_risk_audit_prompt(
        clip_hints={"risk_ranking": [{"risk_id": "machinery_proximity", "score": 0.8}]},
        image_manifest=["Image 1: full image", "Image 2: region R11"],
    )
    for risk_id in (
        "missing_helmet",
        "missing_edge_protection",
        "missing_fall_protection",
        "machinery_proximity",
    ):
        assert risk_id in prompt
    assert "CLIP结果只是注意力提示" in prompt
    assert "不得只凭“前景/背景”断言距离安全" in prompt
    assert "confidence禁止填写0" in prompt
    assert '"confidence": 0.85' in prompt


def test_recovers_zero_confidence_only_for_explicit_visible_fall_protection_gap() -> None:
    payload = {
        "hazards": [
            {
                "risk_name_zh": "高处作业未系安全带",
                "risk_description": "工人在高处作业，但未见安全带及连接绳。",
                "confidence": 0.0,
                "visible_evidence": ["工人腰背部未见安全带或连接绳固定点。"],
                "counter_evidence": [],
            },
            {
                "risk_name_zh": "高处作业风险",
                "risk_description": "工人位于脚手架上。",
                "confidence": 0.0,
                "visible_evidence": ["人员处于高处。"],
                "counter_evidence": [],
            },
            {
                "risk_name_zh": "高处作业未系安全绳",
                "risk_description": "未见安全绳。",
                "confidence": 0.0,
                "visible_evidence": ["腰部未见安全绳连接。"],
                "counter_evidence": ["安全绳已连接固定锚点。"],
            },
            {
                "risk_name_zh": "未佩戴反光背心",
                "risk_description": "工人未穿反光背心。",
                "confidence": 0.0,
                "visible_evidence": ["未见反光背心。"],
                "counter_evidence": [],
            },
        ]
    }

    TrainingFreeInspector._recover_fall_protection_discovery_confidence(
        payload, enabled=True, recovered_confidence=0.60
    )

    recovered, generic_height, contradicted, other_ppe = payload["hazards"]
    assert recovered["confidence"] == 0.60
    assert recovered["confidence_recovered"] is True
    assert recovered["original_confidence"] == 0.0
    assert generic_height["confidence"] == 0.0
    assert contradicted["confidence"] == 0.0
    assert other_ppe["confidence"] == 0.0


def test_default_fall_operator_requires_visible_anchor_connection() -> None:
    registry = load_default_risk_operator_registry()
    operator = registry.operators["missing_fall_protection"]
    prompt = operator.tasks[1].prompt

    assert "physically linking" in prompt
    assert "fixed structural anchor or lifeline" in prompt
    assert operator.relation.type == "missing_association"
    assert operator.relation.task_scope == "canonical"


def test_screening_trigger_is_a_review_prior_not_visual_evidence() -> None:
    trigger = parse_screening_trigger(
        {
            "triggered": True,
            "anomaly_score": 0.81,
            "suspected_regions": [
                {
                    "region_id": "r1",
                    "bbox_xyxy": [10, 20, 100, 200],
                    "score": 0.9,
                    "label": "person",
                }
            ],
            "suspected_concepts": ["missing helmet"],
            "source_model": "edge-detector-v1",
        }
    )
    context = screening_prompt_context(trigger)
    assert trigger is not None
    assert trigger.suspected_regions[0].region_id == "r1"
    assert "粗略关注区域" in context
    assert "不是异常成立的视觉证据" in context
    assert "允许输出无可见异常或uncertain" in context
    assert "不是精确实例掩码" in context


def test_screening_context_is_empty_when_detector_did_not_trigger() -> None:
    context = screening_prompt_context(
        {
            "triggered": False,
            "anomaly_score": 0.1,
            "source_model": "edge-detector-v1",
        }
    )
    assert context == ""


def test_bare_anomaly_prior_is_routing_only() -> None:
    context = screening_prompt_context(
        {
            "triggered": True,
            "anomaly_score": 0.8,
            "source_model": "coarse-yolo",
        }
    )
    assert context == ""


def test_open_risk_discovery_prompt_accepts_person_crop_manifest() -> None:
    prompt = build_open_risk_discovery_prompt(
        ["Image 1: original full construction-site image", "Image 2: person crop 1"]
    )
    assert '"hazards"' in prompt
    assert "开放风险发现" in prompt
    assert "counter_evidence" in prompt
    assert "Image 2: person crop 1" in prompt
    person_prompt = build_person_risk_discovery_prompt(
        ["Image 1: original full construction-site image", "Image 2: person crop 1"]
    )
    assert "普通草帽" in person_prompt


def test_dual_view_discovery_merge_keeps_and_deduplicates_hazards() -> None:
    scene = {
        "scene_summary": "通道和人员场景",
        "hazards": [
            {
                "risk_name_zh": "通道堵塞",
                "confidence": 0.9,
                "visible_evidence": ["钢管占用通道"],
            },
            {
                "risk_name_zh": "未佩戴安全帽",
                "confidence": 0.8,
                "visible_evidence": ["全景可见裸露头部"],
            },
        ],
    }
    people = {
        "hazards": [
            {
                "risk_name_zh": "未佩戴安全帽",
                "confidence": 0.99,
                "visible_evidence": ["人员裁剪可见裸露头部"],
            }
        ]
    }
    merged = TrainingFreeInspector._merge_discovery_payloads(scene, people)
    assert [item["risk_name_zh"] for item in merged["hazards"]] == [
        "通道堵塞",
        "未佩戴安全帽",
    ]
    assert merged["hazards"][1]["confidence"] == 0.99
    assert len(merged["hazards"][1]["visible_evidence"]) == 2
    assert "通道和人员场景" in merged["scene_summary"]


def test_dual_view_discovery_merge_keeps_distinct_scene_summaries() -> None:
    merged = TrainingFreeInspector._merge_discovery_payloads(
        {"scene_summary": "现场有挖掘机。", "hazards": []},
        {"scene_summary": "一名工人在挖掘机旁。", "hazards": []},
    )
    assert merged["scene_summary"] == "现场有挖掘机。；一名工人在挖掘机旁。"


def test_machinery_fallback_routes_summary_cooccurrence_without_declaring_verdict() -> None:
    inspector = object.__new__(TrainingFreeInspector)
    inspector.config = {
        "pipeline": {
            "deterministic_candidate_fallbacks": {
                "enabled": True,
                "rules": [
                    {
                        "risk_id": "machinery_proximity",
                        "all_of_any": [["挖掘机", "重型机械"], ["工人", "人员"]],
                        "confidence": 0.60,
                    }
                ],
            }
        }
    }
    payload = {
        "scene_summary": "泥泞工地上有多台挖掘机，左侧有工人站立。",
        "has_possible_anomaly": False,
        "candidate_assessments": [],
    }
    inspector._apply_deterministic_candidate_fallbacks(
        payload,
        [{"risk_id": "machinery_proximity", "name_zh": "人机距离过近"}],
    )
    candidate = payload["candidate_assessments"][0]
    assert candidate["risk_id"] == "machinery_proximity"
    assert candidate["status"] == "uncertain"
    assert candidate["confidence"] == 0.60
    assert payload["has_possible_anomaly"]


def test_machinery_fallback_requires_both_person_and_machine_terms() -> None:
    inspector = object.__new__(TrainingFreeInspector)
    inspector.config = {
        "pipeline": {
            "deterministic_candidate_fallbacks": {
                "enabled": True,
                "rules": [
                    {
                        "risk_id": "machinery_proximity",
                        "all_of_any": [["挖掘机"], ["工人"]],
                    }
                ],
            }
        }
    }
    payload = {
        "scene_summary": "施工道路上停放着一台挖掘机。",
        "has_possible_anomaly": False,
        "candidate_assessments": [],
    }
    inspector._apply_deterministic_candidate_fallbacks(payload, [])
    assert payload["candidate_assessments"] == []
    assert not payload["has_possible_anomaly"]


@pytest.mark.parametrize(
    "summary",
    [
        "一台挖掘机在深沟内作业，沟壁陡峭，周围无人员。",
        "多名工人在泥泞的工地斜坡上作业，背景有在建高楼。",
        "多名工人在钢筋结构旁的脚手架上作业。",
    ],
)
def test_edge_fallback_routes_explicit_edge_anchors(summary: str) -> None:
    inspector = object.__new__(TrainingFreeInspector)
    inspector.config = {
        "pipeline": {
            "deterministic_candidate_fallbacks": {
                "enabled": True,
                "rules": [
                    {
                        "risk_id": "missing_edge_protection",
                        "all_of_any": [["基坑", "深沟", "沟槽", "斜坡", "洞口"]],
                        "confidence": 0.60,
                    },
                    {
                        "risk_id": "missing_edge_protection",
                        "all_of_any": [["脚手架", "平台"], ["工人", "人员", "作业"]],
                        "confidence": 0.60,
                    },
                ],
            }
        }
    }
    payload = {
        "scene_summary": summary,
        "has_possible_anomaly": False,
        "candidate_assessments": [],
    }
    inspector._apply_deterministic_candidate_fallbacks(
        payload,
        [{"risk_id": "missing_edge_protection", "name_zh": "临边防护缺失"}],
    )
    assert payload["candidate_assessments"][0]["risk_id"] == "missing_edge_protection"
    assert payload["candidate_assessments"][0]["status"] == "uncertain"


def test_generic_partial_word_does_not_downgrade_edge_visibility() -> None:
    registry = load_default_risk_operator_registry()
    candidate = {
        "risk_id": "missing_edge_protection",
        "status": "uncertain",
        "confidence": 0.60,
        "observed_facts": ["脚手架上作业，部分人员佩戴安全帽。"],
    }
    registry.complete_candidate(candidate)
    params = candidate["relation_checks"][0]["params"]
    assert params["inspection_zone_visibility"] == "clear"


def test_explicit_occlusion_downgrades_edge_visibility() -> None:
    registry = load_default_risk_operator_registry()
    candidate = {
        "risk_id": "missing_edge_protection",
        "status": "uncertain",
        "confidence": 0.60,
        "observed_facts": ["平台边缘被材料部分遮挡，无法确认护栏。"],
    }
    registry.complete_candidate(candidate)
    params = candidate["relation_checks"][0]["params"]
    assert params["inspection_zone_visibility"] == "partial"


def test_locked_discovery_selects_matching_riskspec_not_first_item() -> None:
    hazard = {
        "risk_name_zh": "未封闭洞口",
        "risk_description": "地面方形开口没有盖板或围栏。",
        "visible_evidence": ["方形开口无盖板"],
    }
    candidates = [
        {
            "risk_id": "missing_helmet",
            "risk_name_zh": "施工人员未佩戴安全帽",
            "observed_facts": ["人员头部可见"],
        },
        {
            "risk_id": "missing_edge_protection",
            "risk_name_zh": "临边防护缺失",
            "observed_facts": ["方形开口无盖板或围栏"],
        },
    ]
    selected = TrainingFreeInspector._select_compiled_candidate(hazard, candidates)
    assert selected is not None
    assert selected["risk_id"] == "missing_edge_protection"


def test_structured_audit_compiles_only_active_core_risks() -> None:
    payload = {
        "scene_inventory": {
            "persons": [
                {
                    "person_id": "person_1",
                    "location": "right|foreground",
                    "nearest_machine": "machine_1",
                }
            ],
            "machines": [
                {
                    "machine_id": "machine_1",
                    "type": "excavator",
                    "location": "center|foreground",
                }
            ],
            "risk_regions": [],
        },
        "risk_audits": [
            {
                "risk_id": "missing_helmet",
                "status": "present",
                "confidence": 0.86,
                "visible_evidence": ["person_1头部裸露"],
                "counter_evidence": [],
                "uncertainties": [],
                "subject_ids": ["person_1"],
                "anchor_ids": [],
            },
            {
                "risk_id": "machinery_proximity",
                "status": "uncertain",
                "confidence": 0.42,
                "visible_evidence": ["人员与挖掘机同时可见"],
                "counter_evidence": [],
                "uncertainties": ["单图透视距离不确定"],
                "subject_ids": ["person_1"],
                "anchor_ids": [],
            },
            {
                "risk_id": "missing_fall_protection",
                "status": "absent",
                "confidence": 0.95,
                "visible_evidence": [],
                "counter_evidence": ["未见高处人员"],
                "uncertainties": [],
            },
        ]
    }
    catalog = [
        {"risk_id": "missing_helmet", "name_zh": "施工人员未佩戴安全帽"},
        {"risk_id": "machinery_proximity", "name_zh": "人机距离过近"},
    ]
    candidates = TrainingFreeInspector._audit_payload_to_candidates(payload, catalog)
    assert [item["risk_id"] for item in candidates] == [
        "missing_helmet",
        "machinery_proximity",
    ]
    assert candidates[0]["risk_name_zh"] == "施工人员未佩戴安全帽"
    machinery = candidates[1]
    assert [entity["category"] for entity in machinery["target_entities"]] == [
        "construction worker",
        "excavator",
    ]
    assert machinery["target_entities"][0]["location"] == "right foreground"
    assert machinery["relation_spec"]["type"] == "near"
    assert machinery["relation_spec"]["object_entity_ids"] == ["machine_1"]


def test_structured_audit_merges_without_duplicate_or_losing_open_risk() -> None:
    first = {
        "scene_summary": "工地",
        "has_possible_anomaly": True,
        "candidate_assessments": [
            {
                "risk_id": "missing_helmet",
                "status": "uncertain",
                "confidence": 0.4,
                "observed_facts": ["头部较小"],
                "counter_evidence": [],
                "uncertainties": [],
            }
        ],
        "open_discoveries": [
            {"risk_id": "open_smoking", "status": "present", "confidence": 0.8}
        ],
    }
    audit = [
        {
            "risk_id": "missing_helmet",
            "status": "present",
            "confidence": 0.86,
            "observed_facts": ["person_1头部裸露"],
            "counter_evidence": [],
            "uncertainties": [],
        },
        {
            "risk_id": "machinery_proximity",
            "status": "uncertain",
            "confidence": 0.45,
            "observed_facts": ["人机同时可见"],
            "counter_evidence": [],
            "uncertainties": [],
        },
    ]
    TrainingFreeInspector._merge_audit_candidates(first, audit)
    assert len(first["candidate_assessments"]) == 2
    helmet = first["candidate_assessments"][0]
    assert helmet["status"] == "present"
    assert helmet["confidence"] == 0.86
    assert "person_1头部裸露" in helmet["observed_facts"]
    assert first["open_discoveries"][0]["risk_id"] == "open_smoking"


def test_namespaced_audit_entities_and_relation_specs_do_not_overwrite_roi_rounds() -> None:
    payload = {
        "scene_inventory": {
            "persons": [
                {
                    "person_id": "person_1",
                    "nearest_machine": "machine_1",
                    "nearest_edge_or_opening": "region_1",
                }
            ],
            "machines": [{"machine_id": "machine_1"}],
            "risk_regions": [{"region_id": "region_1"}],
        },
        "risk_audits": [
            {
                "risk_id": "machinery_proximity",
                "subject_ids": ["person_1"],
                "anchor_ids": ["machine_1"],
            }
        ],
    }
    TrainingFreeInspector._namespace_audit_entities(payload, "ppe_roi_02")
    person = payload["scene_inventory"]["persons"][0]
    assert person["person_id"] == "ppe_roi_02_person_1"
    assert person["nearest_machine"] == "ppe_roi_02_machine_1"
    assert person["nearest_edge_or_opening"] == "ppe_roi_02_region_1"
    assert payload["risk_audits"][0]["subject_ids"] == ["ppe_roi_02_person_1"]

    first = {
        "candidate_assessments": [
            {
                "risk_id": "missing_helmet",
                "status": "present",
                "confidence": 0.8,
                "target_entities": [],
                "relation_spec": {
                    "type": "missing_association",
                    "subject_entity_ids": ["main_person_1"],
                    "object_entity_ids": ["helmet"],
                    "params": {},
                },
            }
        ],
        "open_discoveries": [],
    }
    TrainingFreeInspector._merge_audit_candidates(
        first,
        [
            {
                "risk_id": "missing_helmet",
                "status": "uncertain",
                "confidence": 0.5,
                "relation_spec": {
                    "type": "missing_association",
                    "subject_entity_ids": ["ppe_roi_02_person_1"],
                    "object_entity_ids": ["helmet"],
                    "params": {},
                },
            }
        ],
    )
    assert first["candidate_assessments"][0]["relation_spec"][
        "subject_entity_ids"
    ] == ["main_person_1", "ppe_roi_02_person_1"]


def test_audit_status_consistency_promotes_only_category_specific_missing_evidence() -> None:
    payload = {
        "risk_audits": [
            {
                "risk_id": "missing_edge_protection",
                "status": "absent",
                "confidence": 0.95,
                "visible_evidence": ["所有临边区域均无防护栏杆或盖板"],
                "uncertainties": [],
            },
            {
                "risk_id": "missing_edge_protection",
                "status": "absent",
                "confidence": 0.95,
                "visible_evidence": ["未观察到临边或洞口防护缺失"],
                "uncertainties": [],
            },
            {
                "risk_id": "missing_helmet",
                "status": "absent",
                "confidence": 0.9,
                "visible_evidence": ["person_1未佩戴安全帽"],
                "uncertainties": [],
            },
            {
                "risk_id": "missing_edge_protection",
                "status": "absent",
                "confidence": 0.95,
                "visible_evidence": ["图中未见明显临边或洞口，无防护需求"],
                "uncertainties": [],
            },
            {
                "risk_id": "missing_edge_protection",
                "status": "present",
                "confidence": 0.8,
                "visible_evidence": ["region_1平台边缘有绿色临时护栏"],
                "uncertainties": [],
            },
        ]
    }

    TrainingFreeInspector._correct_audit_status_consistency(payload)

    corrected_edge, safe_edge, corrected_helmet, no_edge_needed, guardrail_present = payload[
        "risk_audits"
    ]
    assert corrected_edge["status"] == "uncertain"
    assert corrected_edge["status_consistency_corrected"] is True
    assert corrected_edge["confidence"] == 0.57
    assert safe_edge["status"] == "absent"
    assert corrected_helmet["status"] == "uncertain"
    assert no_edge_needed["status"] == "absent"
    assert guardrail_present["status"] == "uncertain"
    assert guardrail_present["confidence"] == 0.48


def test_first_pass_multiscale_views_include_edge_head_and_fall_rois() -> None:
    class OnePersonSAM:
        def set_image(self, image: Image.Image) -> None:
            self.image = image

        def segment(self, task: object) -> list[MaskInstance]:
            mask = np.zeros((480, 640), dtype=np.uint8)
            mask[80:400, 220:340] = 1
            return [
                MaskInstance(
                    task_id="person_precheck",
                    role="subject",
                    prompt="person",
                    score=0.9,
                    mask=mask,
                    box_xyxy=[220.0, 80.0, 340.0, 400.0],
                )
            ]

    inspector = object.__new__(TrainingFreeInspector)
    inspector.sam3 = OnePersonSAM()
    inspector.config = {
        "pipeline": {
            "person_precheck": {
                "enabled": True,
                "max_crops": 1,
                "max_total_views": 5,
                "upscale_min_side": 128,
            },
            "structured_risk_audit": {
                "specialized_views": {
                    "enabled": True,
                    "upscale_min_side": 128,
                    "scene_tiling": {"enabled": True, "columns": 3},
                    "ppe_roi": {
                        "enabled": True,
                        "max_people": 1,
                        "min_score": 0.45,
                    },
                }
            },
        }
    }

    views, manifest = inspector._build_first_pass_images(Image.new("RGB", (640, 480)))
    batches = inspector._build_specialized_audit_batches(
        Image.new("RGB", (640, 480))
    )

    assert manifest is not None
    assert len(views) == 2
    assert len(inspector._last_person_precheck_instances) == 1
    assert all(len(batch_views) <= 5 for _, batch_views, _ in batches)
    specialized_manifest = [
        value for _, _, batch_manifest in batches for value in batch_manifest
    ]
    assert any("scene tile" in value for value in specialized_manifest)
    assert any("head ROI" in value for value in specialized_manifest)
    assert any("waist-back-hook ROI" in value for value in specialized_manifest)


def test_local_normalizer_completes_missing_tasks_and_promotes_lifting_scene() -> None:
    payload = {
        "scene_summary": "多名工人正在观察一个被吊起的混凝土构件。",
        "candidate_assessments": [
            {
                "risk_id": "worker_under_suspended_load",
                "status": "absent",
                "confidence": 0.0,
                "observed_facts": ["工人在吊物侧面。"],
                "sam3_tasks": [],
                "relation_checks": [],
                "mask_strategy": "entity_union",
                "uncertainties": [],
            },
            {
                "risk_id": "missing_edge_protection",
                "status": "uncertain",
                "confidence": 0.0,
                "observed_facts": ["临边部分被遮挡。"],
                "sam3_tasks": [],
                "relation_checks": [],
                "mask_strategy": "entity_union",
                "uncertainties": [],
            },
        ],
        "open_discoveries": ["地面湿滑并存在大量电线，存在触电风险。"],
    }
    catalog = [
        {"risk_id": "worker_under_suspended_load", "name_zh": "人员位于悬吊物下方"},
        {"risk_id": "missing_edge_protection", "name_zh": "临边防护缺失"},
    ]

    TrainingFreeInspector._normalize_first_pass_payload(payload, catalog)

    lifting = payload["candidate_assessments"][0]
    assert lifting["status"] == "uncertain"
    assert lifting["confidence"] == 0.60
    assert len(lifting["sam3_tasks"]) == 2
    assert lifting["relation_checks"][0]["type"] == "below_and_horizontal_overlap"

    edge = payload["candidate_assessments"][1]
    assert edge["confidence"] == 0.0
    assert len(edge["sam3_tasks"]) == 2
    assert edge["relation_checks"][0]["params"]["inspection_zone_visibility"] == "partial"

    discovery = payload["open_discoveries"][0]
    assert len(discovery["sam3_tasks"]) == 2
    assert "electrical cables" in discovery["sam3_tasks"][0]["prompt"]
    assert discovery["relation_checks"][0]["type"] == "overlap"


def test_wet_floor_only_discovery_does_not_invent_electrical_cable() -> None:
    payload = {
        "scene_summary": "施工通道地面存在明显积水。",
        "candidate_assessments": [],
        "open_discoveries": ["地面存在明显积水，可能增加滑倒风险。"],
    }

    TrainingFreeInspector._normalize_first_pass_payload(payload, [])

    discovery = payload["open_discoveries"][0]
    assert len(discovery["sam3_tasks"]) == 1
    assert discovery["sam3_tasks"][0]["role"] == "region"
    assert "wet construction floor" in discovery["sam3_tasks"][0]["prompt"]
    assert discovery["relation_checks"] == []


def test_scaffold_platform_anchor_promotes_only_domain_specific_uncertainty() -> None:
    payload = {
        "scene_summary": "一名工人在脚手架上作业。",
        "candidate_assessments": [
            {
                "risk_id": "unsafe_scaffold_platform",
                "status": "uncertain",
                "confidence": 0.0,
                "observed_facts": ["脚手架平台铺设跳板，但无法确认是否完整或有开口"],
                "sam3_tasks": [],
                "relation_checks": [],
                "mask_strategy": "entity_union",
                "uncertainties": [],
            },
            {
                "risk_id": "machinery_proximity",
                "status": "uncertain",
                "confidence": 0.0,
                "observed_facts": ["未明确是否符合安全距离"],
                "sam3_tasks": [],
                "relation_checks": [],
                "mask_strategy": "entity_union",
                "uncertainties": [],
            },
        ],
        "open_discoveries": [],
    }

    TrainingFreeInspector._normalize_first_pass_payload(payload, [])

    assert payload["candidate_assessments"][0]["confidence"] == 0.50
    assert payload["candidate_assessments"][1]["confidence"] == 0.0


def test_compact_riskspec_compiles_positive_ppe_tasks() -> None:
    payload = {
        "scene_summary": "中央黑衣工人未戴安全帽。",
        "has_possible_anomaly": True,
        "candidate_assessments": [
            {
                "risk_id": "missing_helmet",
                "risk_name_zh": "施工人员未佩戴安全帽",
                "risk_type": "missing_protective_equipment",
                "status": "present",
                "confidence": 0.95,
                "observed_facts": ["中央黑衣工人头发可见。"],
                "target_entities": [
                    {
                        "entity_id": "worker_1",
                        "role": "subject",
                        "category": "construction worker",
                        "attributes": [
                            "black T-shirt",
                            "back facing camera",
                            "wide-brimmed straw hat",
                        ],
                        "location": "center foreground",
                        "expected_count": 1,
                    },
                    {
                        "entity_id": "helmet",
                        "role": "protective_item",
                        "category": "safety helmet",
                        "attributes": [],
                        "location": "",
                    },
                ],
                "relation_spec": {
                    "type": "missing_association",
                    "subject_entity_ids": ["worker_1"],
                    "object_entity_ids": ["helmet"],
                    "params": {"body_region": "head"},
                },
                "mask_strategy": "unmatched_subject",
                "uncertainties": [],
            }
        ],
        "open_discoveries": [],
    }

    TrainingFreeInspector._normalize_first_pass_payload(payload, [])
    risk = payload["candidate_assessments"][0]

    assert len(risk["sam3_tasks"]) == 2
    assert "black T-shirt" in risk["sam3_tasks"][0]["prompt"]
    assert "straw hat" not in risk["sam3_tasks"][0]["prompt"]
    assert "without" not in risk["sam3_tasks"][0]["prompt"]
    assert risk["relation_checks"][0]["type"] == "missing_association"
    assert risk["mask_strategy"] == "unmatched_subject"


def test_compact_known_relation_uses_canonical_anchor_tasks() -> None:
    payload = {
        "scene_summary": "多名工人在吊物下方。",
        "has_possible_anomaly": True,
        "candidate_assessments": [
            {
                "risk_id": "worker_under_suspended_load",
                "risk_name_zh": "人员位于悬吊物下方",
                "status": "present",
                "confidence": 0.9,
                "observed_facts": ["工人与吊物同时可见"],
                "target_entities": [
                    {
                        "entity_id": f"worker_{index}",
                        "role": "subject",
                        "category": "construction worker",
                        "attributes": ["yellow vest"],
                        "location": "center foreground",
                    }
                    for index in range(4)
                ]
                + [
                    {
                        "entity_id": "load",
                        "role": "hazard_source",
                        "category": "suspended concrete structure",
                        "attributes": [],
                        "location": "center middle",
                    }
                ],
                "relation_spec": {
                    "type": "below_and_horizontal_overlap",
                    "subject_entity_ids": [f"worker_{index}" for index in range(4)],
                    "object_entity_ids": ["load"],
                    "params": {},
                },
                "mask_strategy": "projected_below",
                "uncertainties": [],
            }
        ],
        "open_discoveries": [],
    }

    TrainingFreeInspector._normalize_first_pass_payload(payload, [])
    risk = payload["candidate_assessments"][0]

    dynamic_workers = [
        task
        for task in risk["sam3_tasks"]
        if task["task_id"].startswith("worker_under_suspended_load_worker_")
    ]
    assert len(dynamic_workers) == 1
    assert dynamic_workers[0]["expected_count"] == 4
    relation = risk["relation_checks"][0]
    assert relation["subject_task_ids"] == ["worker_under_suspended_load_auto_01"]
    assert relation["object_task_ids"] == ["worker_under_suspended_load_auto_02"]


def test_invalid_missing_mask_alias_is_repaired() -> None:
    item = {
        "mask_strategy": "missing",
        "relation_checks": [{"type": "missing", "subject_task_ids": [], "object_task_ids": []}],
    }
    TrainingFreeInspector._normalize_mask_strategy(item)
    assert item["mask_strategy"] == "missing_subject"
from site_safety.pipeline.relation import RelationVerifier
from site_safety.schemas import (
    FirstPassResponse,
    ManagementReport,
    RelationCheck,
    RelationEvidence,
    RiskCandidate,
    RiskEvidence,
    SAM3Task,
    SecondPassResponse,
    SegmentationRecord,
)
from site_safety.utils.config import load_yaml


def _instance(task_id: str, role: str, box: list[int], shape=(200, 200)) -> MaskInstance:
    x1, y1, x2, y2 = box
    mask = np.zeros(shape, dtype=np.uint8)
    mask[y1:y2, x1:x2] = 1
    return MaskInstance(
        task_id=task_id,
        role=role,
        prompt=task_id,
        score=0.9,
        mask=mask,
        box_xyxy=[float(x) for x in box],
    )


def test_missing_relation_is_inconclusive_by_default() -> None:
    verifier = RelationVerifier({"allow_missing_from_non_detection": False})
    check = RelationCheck(type="missing", subject_task_ids=["worker"], object_task_ids=["helmet"])
    result = verifier.verify(
        check,
        {"worker": [_instance("worker", "subject", [20, 20, 60, 100])]},
        (200, 200),
    )
    assert not result.passed
    assert result.details["inconclusive"]


def test_near_distance_threshold_is_not_applied_twice() -> None:
    verifier = RelationVerifier({"near_distance_ratio": 0.30})
    check = RelationCheck(
        type="near",
        subject_task_ids=["worker"],
        object_task_ids=["machine"],
    )
    # Centers are about 0.20 image diagonals apart: inside 0.30 and outside
    # the old accidental 0.15 effective threshold.
    result = verifier.verify(
        check,
        {
            "worker": [_instance("worker", "subject", [10, 90, 30, 110])],
            "machine": [_instance("machine", "hazard_source", [66, 90, 86, 110])],
        },
        (200, 200),
    )
    assert result.passed
    assert result.details["distance_ratio"] < 0.30
    assert result.details["effective_pass_distance_ratio"] == 0.30

    far = verifier.verify(
        check,
        {
            "worker": [_instance("worker", "subject", [0, 0, 20, 20])],
            "machine": [_instance("machine", "hazard_source", [120, 120, 140, 140])],
        },
        (200, 200),
    )
    assert not far.passed


def test_near_uses_machine_edge_danger_zone_for_large_equipment() -> None:
    verifier = RelationVerifier(
        {"near_distance_ratio": 0.30, "near_edge_gap_machine_ratio": 0.35}
    )
    check = RelationCheck(
        type="near",
        subject_task_ids=["worker"],
        object_task_ids=["machine"],
    )
    result = verifier.verify(
        check,
        {
            "worker": [_instance("worker", "subject", [5, 150, 25, 190])],
            "machine": [_instance("machine", "hazard_source", [30, 10, 195, 195])],
        },
        (200, 200),
    )
    assert result.passed
    assert result.details["near_method"] == "machine_edge_danger_zone"
    assert result.details["edge_gap_machine_ratio"] < 0.35


def test_near_rejects_low_confidence_person_subject() -> None:
    verifier = RelationVerifier(
        {
            "near_distance_ratio": 0.30,
            "near_edge_gap_machine_ratio": 0.35,
            "near_min_subject_score": 0.35,
        }
    )
    check = RelationCheck(
        type="near",
        subject_task_ids=["worker"],
        object_task_ids=["machine"],
    )
    worker = _instance("worker", "subject", [20, 20, 40, 80])
    worker.score = 0.22
    result = verifier.verify(
        check,
        {
            "worker": [worker],
            "machine": [_instance("machine", "hazard_source", [35, 10, 180, 190])],
        },
        (200, 200),
    )
    assert not result.passed
    assert result.details["raw_subject_count"] == 1
    assert result.details["qualified_subject_count"] == 0
    assert result.details["near_min_subject_score"] == 0.35


def test_missing_relation_passes_for_clear_visible_inspection_zone() -> None:
    verifier = RelationVerifier(
        {
            "allow_missing_from_non_detection": False,
            "allow_missing_from_visible_zone": True,
        }
    )
    check = RelationCheck(
        type="missing",
        subject_task_ids=["worker_at_height"],
        object_task_ids=["safety_harness"],
        params={
            "inspection_zone_visibility": "clear",
            "required_item": "safety harness",
        },
    )
    result = verifier.verify(
        check,
        {
            "worker_at_height": [
                _instance("worker_at_height", "subject", [20, 20, 80, 160])
            ]
        },
        (200, 200),
    )
    assert result.passed
    assert result.score == 0.90
    assert result.details["visible_zone_confirmation"]
    assert result.details["required_item"] == "safety harness"


def test_missing_association_and_mask_select_unhelmeted_subject() -> None:
    worker_with_helmet = _instance("workers", "subject", [10, 20, 60, 180])
    worker_without_helmet = _instance("workers", "subject", [100, 20, 150, 180])
    helmet = _instance("helmets", "protective_item", [20, 15, 50, 48])
    by_task = {
        "workers": [worker_with_helmet, worker_without_helmet],
        "helmets": [helmet],
    }
    check = RelationCheck(
        type="missing_association",
        subject_task_ids=["workers"],
        object_task_ids=["helmets"],
        params={"body_region": "head"},
    )
    result = RelationVerifier({}).verify(check, by_task, (200, 200))
    assert result.passed
    assert result.details["unmatched_subject_indexes"] == [1]

    risk = RiskCandidate(
        risk_id="missing_helmet",
        risk_name_zh="未戴安全帽",
        status="present",
        confidence=0.9,
        sam3_tasks=[
            SAM3Task(task_id="workers", role="subject", prompt="construction worker"),
            SAM3Task(task_id="helmets", role="protective_item", prompt="safety helmet"),
        ],
        relation_checks=[check],
        mask_strategy="unmatched_subject",
    )
    mask = RiskMaskBuilder({}).build(risk, by_task, (200, 200))
    assert mask[50, 120] == 1
    assert mask[50, 30] == 0


def test_missing_association_requires_clear_zone_when_visibility_is_explicit() -> None:
    worker = _instance("worker", "subject", [20, 20, 80, 160])
    verifier = RelationVerifier({})

    partial = verifier.verify(
        RelationCheck(
            type="missing_association",
            subject_task_ids=["worker"],
            object_task_ids=["lanyard"],
            params={"inspection_zone_visibility": "partial"},
        ),
        {"worker": [worker]},
        (200, 200),
    )
    clear = verifier.verify(
        RelationCheck(
            type="missing_association",
            subject_task_ids=["worker"],
            object_task_ids=["lanyard"],
            params={"inspection_zone_visibility": "clear"},
        ),
        {"worker": [worker]},
        (200, 200),
    )

    assert not partial.passed
    assert partial.score == 0.45
    assert partial.details["visibility_supports_absence"] is False
    assert clear.passed
    assert clear.score == 0.90


def test_projected_below_is_bounded() -> None:
    source = _instance("load", "hazard_source", [60, 20, 100, 40])
    risk = RiskCandidate(
        risk_id="suspended",
        risk_name_zh="悬吊物",
        status="present",
        confidence=0.9,
        sam3_tasks=[SAM3Task(task_id="load", role="hazard_source", prompt="load")],
        mask_strategy="projected_below",
    )
    builder = RiskMaskBuilder(
        {
            "projected_max_object_height_ratio": 2.0,
            "projected_max_image_height_ratio": 0.20,
        }
    )
    mask = builder.build(risk, {"load": [source]}, (200, 200))
    assert mask[:80].max() == 1
    assert mask[80:].max() == 0


def test_duplicate_sam3_task_ids_are_rejected() -> None:
    payload = {
        "scene_summary": "test",
        "has_possible_anomaly": True,
        "candidate_assessments": [
            {
                "risk_id": risk_id,
                "risk_name_zh": risk_id,
                "status": "present",
                "confidence": 0.8,
                "sam3_tasks": [
                    {
                        "task_id": "duplicate",
                        "role": "subject",
                        "prompt": prompt,
                    }
                ],
            }
            for risk_id, prompt in [("risk_a", "worker"), ("risk_b", "helmet")]
        ],
    }
    with pytest.raises(ValidationError, match="globally unique"):
        FirstPassResponse.model_validate(payload)


def test_failed_required_relation_overrides_mllm_verification() -> None:
    root = Path(__file__).resolve().parents[1]
    config = load_yaml(root / "configs" / "default.yaml")
    inspector = build_inspector(config, root, allow_legacy=True)
    evidence = RiskEvidence(
        risk_id="risk_a",
        risk_name_zh="关系风险",
        first_pass_status="present",
        first_pass_confidence=0.9,
        observed_facts=[],
        segmentations=[
            SegmentationRecord(
                task_id="worker",
                role="subject",
                prompt="worker",
                instance_index=0,
                score=0.9,
                box_xyxy=[0, 0, 10, 10],
                mask_path="mask.png",
            )
        ],
        relations=[
            RelationEvidence(
                relation_type="near",
                passed=False,
                score=0.1,
                details={},
            )
        ],
        mask_strategy="entity_union",
        evidence_score=0.8,
    )
    report = SecondPassResponse.model_validate(
        {
            "overall_has_anomaly": True,
            "overall_summary": "模型声称风险成立",
            "final_risks": [
                {
                    "risk_id": "risk_a",
                    "risk_name_zh": "关系风险",
                    "verified": True,
                    "confidence": 0.95,
                    "risk_description": "test",
                }
            ],
        }
    )
    guarded = inspector._apply_evidence_guards(report, [evidence])
    assert not guarded.final_risks[0].verified
    assert guarded.final_risks[0].confidence <= 0.45
    assert guarded.final_risks[0].manual_review_required
    assert not guarded.overall_has_anomaly


def test_failed_relation_skips_redundant_second_pass(tmp_path: Path) -> None:
    class FailingIfCalledMLLM:
        def generate_json(self, images: object, prompt: str) -> str:
            raise AssertionError("MLLM second pass must be skipped")

    inspector = object.__new__(TrainingFreeInspector)
    inspector.config = {"pipeline": {"skip_second_pass_on_failed_relation": True}}
    inspector.mllm = FailingIfCalledMLLM()
    evidence = RiskEvidence(
        risk_id="missing_edge_protection",
        risk_name_zh="临边防护缺失",
        first_pass_status="uncertain",
        first_pass_confidence=0.60,
        observed_facts=["可见基坑"],
        segmentations=[
            SegmentationRecord(
                task_id="edge",
                role="subject",
                prompt="construction edge",
                instance_index=0,
                score=0.8,
                box_xyxy=[0, 0, 50, 50],
                mask_path="edge.png",
            ),
            SegmentationRecord(
                task_id="rail",
                role="protective_item",
                prompt="guardrail",
                instance_index=0,
                score=0.9,
                box_xyxy=[0, 0, 50, 20],
                mask_path="rail.png",
            ),
        ],
        relations=[
            RelationEvidence(
                relation_type="missing", passed=False, score=0.0, details={}
            )
        ],
        mask_strategy="missing_subject",
        evidence_score=0.72,
    )
    report = inspector._run_per_risk_second_pass(
        Image.new("RGB", (100, 100)), tmp_path, [evidence]
    )
    risk = report.final_risks[0]
    assert not risk.verified
    assert risk.manual_review_required
    assert risk.confidence == 0.45


def test_audited_missing_operator_bypasses_redundant_second_pass(tmp_path: Path) -> None:
    class FailingIfCalledMLLM:
        def generate_json(self, images: object, prompt: str) -> str:
            raise AssertionError("audited operator must not call the second-pass MLLM")

    inspector = object.__new__(TrainingFreeInspector)
    inspector.config = {
        "pipeline": {
            "skip_second_pass_on_failed_relation": True,
            "second_pass_bypass_risk_ids": ["missing_helmet"],
        }
    }
    inspector.mllm = FailingIfCalledMLLM()
    evidence = RiskEvidence(
        risk_id="missing_helmet",
        risk_name_zh="施工人员未佩戴安全帽",
        first_pass_status="present",
        first_pass_confidence=0.92,
        observed_facts=["工人头部清晰可见且未佩戴安全帽"],
        counter_evidence=[],
        segmentations=[
            SegmentationRecord(
                task_id="worker",
                role="subject",
                prompt="construction worker",
                instance_index=0,
                score=0.88,
                box_xyxy=[10, 10, 50, 90],
                mask_path="worker.png",
            )
        ],
        relations=[
            RelationEvidence(
                relation_type="missing", passed=True, score=0.90, details={}
            )
        ],
        mask_strategy="unmatched_subject",
        evidence_score=0.90,
    )

    report = inspector._run_per_risk_second_pass(
        Image.new("RGB", (100, 100)), tmp_path, [evidence]
    )

    risk = report.final_risks[0]
    assert risk.verified
    assert risk.absence_status == "confirmed_absent"
    assert risk.confidence == 0.90
    assert "未调用二次MLLM复核" in risk.uncertainties[-1]
    audit_payload = json.loads(
        (tmp_path / "mllm_second_per_risk.json").read_text(encoding="utf-8")
    )
    assert audit_payload == [
        {"risk_id": "missing_helmet", "review_mode": "programmatic_evidence_bypass"}
    ]


def test_reliable_machinery_relation_can_survive_mllm_denial() -> None:
    root = Path(__file__).resolve().parents[1]
    config = load_yaml(root / "configs" / "default.yaml")
    config["pipeline"]["relation_evidence_preservation"] = {
        "enabled": True,
        "risk_ids": ["machinery_proximity"],
        "relation_types": ["near"],
        "min_relation_score": 0.70,
        "min_evidence_score": 0.70,
    }
    inspector = build_inspector(config, root, allow_legacy=True)
    evidence = RiskEvidence(
        risk_id="machinery_proximity",
        risk_name_zh="人机距离过近",
        first_pass_status="uncertain",
        first_pass_confidence=0.60,
        observed_facts=["人员和挖掘机同时可见"],
        segmentations=[
            SegmentationRecord(
                task_id="worker", role="subject", prompt="worker", instance_index=0,
                score=0.85, box_xyxy=[10, 10, 40, 100], mask_path="worker.png",
                clip_consistency_score=0.60,
            ),
            SegmentationRecord(
                task_id="machine", role="hazard_source", prompt="excavator", instance_index=0,
                score=0.95, box_xyxy=[45, 5, 180, 150], mask_path="machine.png",
                clip_consistency_score=0.62,
            ),
        ],
        relations=[
            RelationEvidence(
                relation_type="near", passed=True, score=0.82,
                details={"qualified_subject_count": 1},
            )
        ],
        mask_strategy="expanded_object_zone",
        risk_mask_path="risk.png",
        evidence_score=0.76,
    )
    report = SecondPassResponse.model_validate(
        {
            "overall_has_anomaly": False,
            "overall_summary": "二次模型未确认",
            "final_risks": [
                {
                    "risk_id": "machinery_proximity",
                    "risk_name_zh": "人机距离过近",
                    "verified": False,
                    "confidence": 0.60,
                    "risk_description": "单图距离不确定",
                    "manual_review_required": True,
                }
            ],
        }
    )
    guarded = inspector._apply_evidence_guards(report, [evidence])
    risk = guarded.final_risks[0]
    assert risk.verified
    assert risk.manual_review_required
    assert risk.confidence == pytest.approx(0.76)
    assert guarded.overall_has_anomaly


def test_confirmed_absence_keeps_high_confidence_with_double_confirmation() -> None:
    root = Path(__file__).resolve().parents[1]
    config = load_yaml(root / "configs" / "default.yaml")
    inspector = build_inspector(config, root, allow_legacy=True)
    evidence = RiskEvidence(
        risk_id="missing_fall_protection",
        risk_name_zh="高处作业防坠落装备缺失",
        first_pass_status="present",
        first_pass_confidence=0.95,
        observed_facts=["高处作业人员腰背部和连接区域清晰可见"],
        segmentations=[
            SegmentationRecord(
                task_id="worker_at_height",
                role="subject",
                prompt="worker performing work at height",
                instance_index=0,
                score=0.94,
                box_xyxy=[20, 10, 80, 180],
                mask_path="worker.png",
            )
        ],
        relations=[
            RelationEvidence(
                relation_type="missing",
                passed=True,
                score=0.90,
                details={
                    "inspection_zone_visibility": "clear",
                    "visible_zone_confirmation": True,
                    "object_not_detected": True,
                },
            )
        ],
        mask_strategy="missing_subject",
        evidence_score=0.91,
    )
    report = SecondPassResponse.model_validate(
        {
            "overall_has_anomaly": True,
            "overall_summary": "确认缺少防坠落装备",
            "final_risks": [
                {
                    "risk_id": "missing_fall_protection",
                    "risk_name_zh": "高处作业防坠落装备缺失",
                    "verified": True,
                    "confidence": 0.95,
                    "visible_evidence": [
                        "高处作业人员腰背部及连接区域清晰可见，未见安全带或安全绳"
                    ],
                    "risk_description": "可见区域内确认缺少防坠落装备",
                    "manual_review_required": False,
                    "absence_status": "confirmed_absent",
                }
            ],
        }
    )
    guarded = inspector._apply_evidence_guards(report, [evidence])
    risk = guarded.final_risks[0]
    assert risk.verified
    assert risk.confidence == 0.90
    assert not risk.manual_review_required
    assert risk.absence_status == "confirmed_absent"


def test_not_observed_missing_risk_is_revoked() -> None:
    root = Path(__file__).resolve().parents[1]
    config = load_yaml(root / "configs" / "default.yaml")
    inspector = build_inspector(config, root, allow_legacy=True)
    evidence = RiskEvidence(
        risk_id="missing_fall_protection",
        risk_name_zh="高处作业防坠落装备缺失",
        first_pass_status="uncertain",
        first_pass_confidence=0.75,
        observed_facts=[],
        segmentations=[
            SegmentationRecord(
                task_id="worker_at_height",
                role="subject",
                prompt="worker performing work at height",
                instance_index=0,
                score=0.90,
                box_xyxy=[20, 10, 80, 180],
                mask_path="worker.png",
            )
        ],
        relations=[
            RelationEvidence(
                relation_type="missing",
                passed=False,
                score=0.45,
                details={
                    "inspection_zone_visibility": "partial",
                    "inconclusive": True,
                },
            )
        ],
        mask_strategy="missing_subject",
        evidence_score=0.65,
    )
    report = SecondPassResponse.model_validate(
        {
            "overall_has_anomaly": True,
            "overall_summary": "疑似缺失",
            "final_risks": [
                {
                    "risk_id": "missing_fall_protection",
                    "risk_name_zh": "高处作业防坠落装备缺失",
                    "verified": True,
                    "confidence": 0.88,
                    "visible_evidence": ["未观察到安全绳"],
                    "risk_description": "仅未观察到防护物",
                    "manual_review_required": False,
                    "absence_status": "not_observed",
                }
            ],
        }
    )
    guarded = inspector._apply_evidence_guards(report, [evidence])
    risk = guarded.final_risks[0]
    assert not risk.verified
    assert risk.confidence == 0.60
    assert risk.manual_review_required
    assert not guarded.overall_has_anomaly


def test_management_report_cannot_override_visual_verdict() -> None:
    visual = SecondPassResponse.model_validate(
        {
            "overall_has_anomaly": False,
            "overall_summary": "视觉证据不足",
            "final_risks": [
                {
                    "risk_id": "risk_a",
                    "risk_name_zh": "关系风险",
                    "verified": False,
                    "confidence": 0.35,
                    "visible_evidence": [],
                    "risk_description": "未确认",
                    "uncertainties": ["关键实体未定位"],
                    "manual_review_required": True,
                }
            ],
        }
    )
    glm_report = ManagementReport.model_validate(
        {
            "executive_summary": "错误地声称风险成立",
            "generated_by": "glm",
            "risks": [
                {
                    "risk_id": "risk_a",
                    "risk_name_zh": "错误名称",
                    "verified": True,
                    "confidence": 0.99,
                    "summary": "错误结论",
                    "evidence": ["虚构证据"],
                    "manual_review_required": False,
                }
            ],
        }
    )
    guarded = TrainingFreeInspector._guard_management_report(glm_report, visual)
    section = guarded.risks[0]
    assert not section.verified
    assert section.confidence == 0.35
    assert section.evidence == []
    assert section.manual_review_required


def test_open_discovery_is_normalized_from_loose_qwen_shape() -> None:
    payload = {
        "candidate_assessments": [],
        "open_discoveries": [
            {
                "name_zh": "电缆浸水隐患",
                "description": "电缆铺设在积水中",
                "sam3_tasks": [],
            }
        ],
    }
    TrainingFreeInspector._normalize_first_pass_payload(payload, [])
    discovery = payload["open_discoveries"][0]
    assert discovery["risk_id"] == "open_discovery_1"
    assert discovery["risk_name_zh"] == "电缆浸水隐患"
    assert discovery["status"] == "present"
    assert discovery["confidence"] == 0.65
    assert discovery["observed_facts"] == ["电缆铺设在积水中"]


def test_confirmed_absent_cap_applies_without_missing_relation() -> None:
    """第一遍未生成missing关系时，confirmed_absent的0.90上限仍必须生效。"""
    root = Path(__file__).resolve().parents[1]
    config = load_yaml(root / "configs" / "default.yaml")
    inspector = build_inspector(config, root, allow_legacy=True)
    evidence = RiskEvidence(
        risk_id="missing_helmet",
        risk_name_zh="施工人员未佩戴安全帽",
        first_pass_status="present",
        first_pass_confidence=0.95,
        observed_facts=[],
        segmentations=[
            SegmentationRecord(
                task_id="worker",
                role="subject",
                prompt="construction worker",
                instance_index=0,
                score=0.9,
                box_xyxy=[10, 10, 60, 120],
                mask_path="worker.png",
            )
        ],
        relations=[],  # 关键：无missing关系
        mask_strategy="missing_subject",
        evidence_score=0.9,
    )
    report = SecondPassResponse.model_validate(
        {
            "overall_has_anomaly": True,
            "overall_summary": "确认未佩戴安全帽",
            "final_risks": [
                {
                    "risk_id": "missing_helmet",
                    "risk_name_zh": "施工人员未佩戴安全帽",
                    "verified": True,
                    "confidence": 1.0,
                    "visible_evidence": ["裁剪图中头部清晰可见，无安全帽"],
                    "risk_description": "确认缺失",
                    "manual_review_required": False,
                    "absence_status": "confirmed_absent",
                }
            ],
        }
    )
    guarded = inspector._apply_evidence_guards(report, [evidence])
    assert guarded.final_risks[0].confidence <= 0.90


def test_tiny_subject_cannot_confirm_absence() -> None:
    """锚点目标过小时，confirmed_absent必须降级为not_observed转人工。"""
    root = Path(__file__).resolve().parents[1]
    config = load_yaml(root / "configs" / "default.yaml")
    inspector = build_inspector(config, root, allow_legacy=True)
    evidence = RiskEvidence(
        risk_id="missing_helmet",
        risk_name_zh="施工人员未佩戴安全帽",
        first_pass_status="present",
        first_pass_confidence=0.9,
        observed_facts=[],
        segmentations=[
            SegmentationRecord(
                task_id="worker",
                role="subject",
                prompt="construction worker",
                instance_index=0,
                score=0.9,
                box_xyxy=[300, 300, 320, 340],  # 高40px / 图高640 = 0.0625 < 0.10
                mask_path="worker.png",
            )
        ],
        relations=[],
        mask_strategy="missing_subject",
        evidence_score=0.9,
    )
    report = SecondPassResponse.model_validate(
        {
            "overall_has_anomaly": True,
            "overall_summary": "确认未佩戴安全帽",
            "final_risks": [
                {
                    "risk_id": "missing_helmet",
                    "risk_name_zh": "施工人员未佩戴安全帽",
                    "verified": True,
                    "confidence": 0.9,
                    "visible_evidence": ["放大裁剪中似乎未见安全帽"],
                    "risk_description": "确认缺失",
                    "manual_review_required": False,
                    "absence_status": "confirmed_absent",
                }
            ],
        }
    )
    guarded = inspector._apply_evidence_guards(report, [evidence], image_size=(640, 640))
    risk = guarded.final_risks[0]
    assert not risk.verified
    assert risk.absence_status == "not_observed"
    assert risk.confidence <= 0.60
    assert risk.manual_review_required


def test_approved_threshold_override_downgrades_low_confidence(tmp_path: Path) -> None:
    """人工审批的按风险置信度下限必须在门控中生效。"""
    root = Path(__file__).resolve().parents[1]
    config = load_yaml(root / "configs" / "default.yaml")
    override_file = tmp_path / "threshold_overrides.json"
    override_file.write_text(
        '{"risk_overrides": {"missing_helmet": {"min_verified_confidence": 0.9}}}',
        encoding="utf-8",
    )
    config["pipeline"]["threshold_overrides_path"] = str(override_file)
    inspector = build_inspector(config, root, allow_legacy=True)
    evidence = RiskEvidence(
        risk_id="missing_helmet",
        risk_name_zh="施工人员未佩戴安全帽",
        first_pass_status="present",
        first_pass_confidence=0.8,
        observed_facts=[],
        segmentations=[
            SegmentationRecord(
                task_id="worker", role="subject", prompt="worker", instance_index=0,
                score=0.9, box_xyxy=[10, 10, 80, 200], mask_path="w.png",
            )
        ],
        relations=[],
        mask_strategy="missing_subject",
        evidence_score=0.8,
    )
    report = SecondPassResponse.model_validate(
        {
            "overall_has_anomaly": True,
            "overall_summary": "s",
            "final_risks": [
                {
                    "risk_id": "missing_helmet",
                    "risk_name_zh": "施工人员未佩戴安全帽",
                    "verified": True,
                    "confidence": 0.8,
                    "visible_evidence": ["e"],
                    "risk_description": "d",
                }
            ],
        }
    )
    guarded = inspector._apply_evidence_guards(report, [evidence], image_size=(640, 640))
    risk = guarded.final_risks[0]
    assert not risk.verified
    assert risk.manual_review_required
    # 高于下限的不受影响
    report2 = SecondPassResponse.model_validate(
        {
            "overall_has_anomaly": True,
            "overall_summary": "s",
            "final_risks": [
                {
                    "risk_id": "missing_helmet",
                    "risk_name_zh": "施工人员未佩戴安全帽",
                    "verified": True,
                    "confidence": 0.95,
                    "visible_evidence": ["e"],
                    "risk_description": "d",
                }
            ],
        }
    )
    guarded2 = inspector._apply_evidence_guards(report2, [evidence], image_size=(640, 640))
    assert guarded2.final_risks[0].verified


def test_global_minimum_confidence_rejects_inconsistent_verified_flag() -> None:
    root = Path(__file__).resolve().parents[1]
    config = load_yaml(root / "configs" / "default.yaml")
    config["pipeline"]["global_min_verified_confidence"] = 0.25
    inspector = build_inspector(config, root, allow_legacy=True)
    evidence = RiskEvidence(
        risk_id="risk_a",
        risk_name_zh="低置信度风险",
        first_pass_status="uncertain",
        first_pass_confidence=0.3,
        observed_facts=[],
        segmentations=[],
        relations=[],
        mask_strategy="entity_union",
        evidence_score=0.2,
    )
    report = SecondPassResponse.model_validate(
        {
            "overall_has_anomaly": True,
            "overall_summary": "模型输出自相矛盾",
            "final_risks": [
                {
                    "risk_id": "risk_a",
                    "risk_name_zh": "低置信度风险",
                    "verified": True,
                    "confidence": 0.0,
                    "visible_evidence": [],
                    "risk_description": "缺少可靠证据",
                }
            ],
        }
    )
    guarded = inspector._apply_evidence_guards(report, [evidence])
    risk = guarded.final_risks[0]
    assert not risk.verified
    assert risk.manual_review_required
    assert not guarded.overall_has_anomaly


def test_helmet_missing_text_is_not_misread_as_all_workers_wearing_helmets(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[1]
    config = load_yaml(root / "configs" / "default.yaml")
    empty_overrides = tmp_path / "empty_thresholds.json"
    empty_overrides.write_text('{"risk_overrides": {}}', encoding="utf-8")
    config["pipeline"]["threshold_overrides_path"] = str(empty_overrides)
    inspector = build_inspector(config, root, allow_legacy=True)
    evidence = RiskEvidence(
        risk_id="missing_helmet",
        risk_name_zh="施工人员未佩戴安全帽",
        first_pass_status="present",
        first_pass_confidence=0.95,
        observed_facts=["所有可见人员均未佩戴安全帽"],
        segmentations=[
            SegmentationRecord(
                task_id="worker",
                role="subject",
                prompt="worker",
                instance_index=0,
                score=0.9,
                box_xyxy=[10, 10, 100, 220],
                mask_path="w.png",
            )
        ],
        relations=[
            RelationEvidence(
                relation_type="missing_association",
                passed=True,
                score=0.9,
                details={},
            )
        ],
        mask_strategy="unmatched_subject",
        risk_mask_path="risk.png",
        evidence_score=0.9,
    )
    report = SecondPassResponse.model_validate(
        {
            "overall_has_anomaly": True,
            "overall_summary": "确认缺失",
            "final_risks": [
                {
                    "risk_id": "missing_helmet",
                    "risk_name_zh": "施工人员未佩戴安全帽",
                    "verified": True,
                    "confidence": 0.95,
                    "visible_evidence": ["所有可见人员头部均未佩戴安全帽"],
                    "risk_description": "多名施工人员头部未见安全帽。",
                    "absence_status": "confirmed_absent",
                }
            ],
        }
    )
    guarded = inspector._apply_evidence_guards(report, [evidence], image_size=(640, 640))
    assert guarded.final_risks[0].verified
