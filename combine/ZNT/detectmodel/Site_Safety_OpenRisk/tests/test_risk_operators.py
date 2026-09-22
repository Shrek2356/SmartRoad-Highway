from __future__ import annotations

import pytest
from pydantic import ValidationError

from site_safety.risk_operators import (
    RiskOperatorRegistry,
    load_default_risk_operator_registry,
)


def test_default_registry_contains_core_risk_operators() -> None:
    registry = load_default_risk_operator_registry()

    assert registry.version == 1
    assert len(registry.operators) == 11
    assert registry.operators["missing_helmet"].relation.type == "missing_association"
    assert registry.operators["missing_helmet"].mask_strategy == "unmatched_subject"
    edge_relation = registry.operators["missing_edge_protection"].relation
    assert edge_relation.subject_roles == ["subject", "region"]
    assert edge_relation.object_roles == ["protective_item"]


def test_fall_operator_ignores_broad_mllm_harness_in_anchor_decision() -> None:
    registry = load_default_risk_operator_registry()
    item = {
        "risk_id": "missing_fall_protection",
        "status": "present",
        "sam3_tasks": [
            {
                "task_id": "missing_fall_protection_worker_1",
                "role": "subject",
                "prompt": "construction worker in red coverall",
            },
            {
                "task_id": "missing_fall_protection_harness_1",
                "role": "protective_item",
                "prompt": "safety harness on worker back",
            },
        ],
        "observed_facts": ["工人在高处，未见安全绳连接固定锚点。"],
    }

    registry.complete_candidate(item)

    check = item["relation_checks"][0]
    assert check["type"] == "missing_association"
    assert check["subject_task_ids"] == ["missing_fall_protection_auto_01"]
    assert check["object_task_ids"] == ["missing_fall_protection_auto_02"]
    assert "harness_1" not in " ".join(check["object_task_ids"])
    canonical_object = next(
        task
        for task in item["sam3_tasks"]
        if task["task_id"] == "missing_fall_protection_auto_02"
    )
    assert canonical_object["min_score"] == 0.50


def test_new_risk_can_be_compiled_from_configuration_only() -> None:
    registry = RiskOperatorRegistry.model_validate(
        {
            "version": 1,
            "operators": {
                "smoking_worker": {
                    "tasks": [
                        {
                            "role": "subject",
                            "prompt": "construction worker",
                            "expected_count": 2,
                        },
                        {
                            "role": "hazard_source",
                            "prompt": "lit cigarette or visible smoking",
                        },
                    ],
                    "relation": {"type": "near", "task_scope": "canonical"},
                    "mask_strategy": "entity_union",
                    "force_canonical_tasks": True,
                }
            },
        }
    )
    item = {
        "risk_id": "smoking_worker",
        "status": "present",
        "sam3_tasks": [],
        "observed_facts": ["人员手持疑似香烟"],
    }

    registry.complete_candidate(item)

    assert [task["role"] for task in item["sam3_tasks"]] == [
        "subject",
        "hazard_source",
    ]
    assert item["sam3_tasks"][0]["expected_count"] == 2
    assert item["relation_checks"][0]["type"] == "near"
    assert item["relation_checks"][0]["subject_task_ids"] == [
        "smoking_worker_auto_01"
    ]


def test_invalid_operator_role_fails_at_startup_validation() -> None:
    with pytest.raises(ValidationError):
        RiskOperatorRegistry.model_validate(
            {
                "version": 1,
                "operators": {
                    "bad_operator": {
                        "tasks": [{"role": "unknown_role", "prompt": "thing"}]
                    }
                },
            }
        )


def test_anchor_and_promotion_rules_are_configuration_driven() -> None:
    registry = load_default_risk_operator_registry()
    assert registry.is_anchor_scene("画面中人员正在吊装作业")
    assert not registry.is_anchor_scene("画面中只有一台起重机")

    payload = {
        "candidate_assessments": [
            {
                "risk_id": "worker_under_suspended_load",
                "status": "absent",
                "confidence": 0.1,
                "uncertainties": [],
            }
        ]
    }
    registry.promote_candidates(payload, "工人位于悬吊构件附近")

    item = payload["candidate_assessments"][0]
    assert item["status"] == "uncertain"
    assert item["confidence"] == 0.6
