"""Explicit synthetic fixture for software integration, never a detector."""
import json
from site_safety.adapters.base import MLLMAdapter


class RoadMockMLLMAdapter(MLLMAdapter):
    def generate_json(self, images, prompt):
        if "candidate_assessments" in prompt:
            payload = {"scene_summary": "模拟道路联调数据，不是对输入图像的真实检测",
                       "has_possible_anomaly": True, "open_discoveries": [],
                       "candidate_assessments": [{
                           "risk_id": "road_debris", "risk_name_zh": "路面散落异物（模拟）",
                           "status": "uncertain", "confidence": 0.5,
                           "observed_facts": ["模拟占位证据，未运行视觉模型"],
                           "counter_evidence": [], "sam3_tasks": [
                               {"task_id": "debris", "role": "hazard_source",
                                "prompt": "debris on road", "expected_count": 1}],
                           "relation_checks": [], "mask_strategy": "entity_union",
                           "uncertainties": ["模拟联调，不可用于判断实际路况"]}]}
        else:
            payload = {"overall_has_anomaly": True, "overall_summary": "模拟联调结果，实际路况未判断",
                       "final_risks": [{"risk_id": "road_debris",
                           "risk_name_zh": "路面散落异物（模拟）", "verified": False,
                           "confidence": 0.5, "visible_evidence": ["模拟占位证据"],
                           "counter_evidence": [], "risk_description": "模拟流程，未做真实检测",
                           "uncertainties": ["必须使用真实模型重新检测"],
                           "manual_review_required": True, "absence_status": "not_applicable"}]}
        return json.dumps(payload, ensure_ascii=False)
