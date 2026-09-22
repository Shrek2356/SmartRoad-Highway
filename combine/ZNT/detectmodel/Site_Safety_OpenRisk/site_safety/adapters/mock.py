from __future__ import annotations

import json
from typing import List, Sequence

import numpy as np
from PIL import Image

from site_safety.adapters.base import CLIPAdapter, MLLMAdapter, MaskInstance, SAM3Adapter
from site_safety.schemas import SAM3Task


class MockMLLMAdapter(MLLMAdapter):
    """Deterministic mock that demonstrates the complete orchestration path."""

    def __init__(self) -> None:
        self.calls = 0

    def generate_json(self, images: Sequence[Image.Image], prompt: str) -> str:
        self.calls += 1
        # 按提示词内容判别阶段（不能用调用计数：流式worker会对同一适配器连续多帧调用）
        if "candidate_assessments" in prompt or "候选风险" in prompt:
            return json.dumps(
                {
                    "scene_summary": "模拟工地画面：一名施工人员位于悬吊构件下方。",
                    "has_possible_anomaly": True,
                    "candidate_assessments": [
                        {
                            "risk_id": "worker_under_suspended_load",
                            "risk_name_zh": "人员位于悬吊物下方",
                            "status": "present",
                            "confidence": 0.88,
                            "observed_facts": [
                                "画面中存在一名施工人员",
                                "人员上方存在悬吊构件",
                            ],
                            "sam3_tasks": [
                                {
                                    "task_id": "worker_01",
                                    "role": "subject",
                                    "prompt": "construction worker",
                                    "expected_count": 1,
                                },
                                {
                                    "task_id": "load_01",
                                    "role": "hazard_source",
                                    "prompt": "suspended construction load",
                                    "expected_count": 1,
                                },
                            ],
                            "relation_checks": [
                                {
                                    "type": "below_and_horizontal_overlap",
                                    "subject_task_ids": ["worker_01"],
                                    "object_task_ids": ["load_01"],
                                    "params": {"horizontal_overlap_threshold": 0.2},
                                }
                            ],
                            "mask_strategy": "projected_below",
                            "uncertainties": ["模拟数据不代表真实模型判断"],
                        },
                        {
                            "risk_id": "smoke_or_fire",
                            "risk_name_zh": "现场存在烟雾或火焰",
                            "status": "absent",
                            "confidence": 0.92,
                            "observed_facts": ["未观察到烟雾或火焰"],
                            "sam3_tasks": [],
                            "relation_checks": [],
                            "mask_strategy": "entity_union",
                            "uncertainties": [],
                        },
                    ],
                    "open_discoveries": [],
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "overall_has_anomaly": True,
                "overall_summary": "定位证据支持人员位于悬吊物下方，建议人工确认现场作业状态。",
                "final_risks": [
                    {
                        "risk_id": "worker_under_suspended_load",
                        "risk_name_zh": "人员位于悬吊物下方",
                        "verified": True,
                        "confidence": 0.91,
                        "visible_evidence": [
                            "SAM3定位到施工人员",
                            "SAM3定位到人员上方的悬吊构件",
                            "几何核验显示两者水平投影重叠",
                        ],
                        "risk_description": "若悬吊物摆动或坠落，可能对下方人员造成物体打击。",
                        "uncertainties": ["单张图像无法确认吊装设备是否正在运行"],
                        "manual_review_required": True,
                    }
                ],
            },
            ensure_ascii=False,
        )


class MockSAM3Adapter(SAM3Adapter):
    def __init__(self) -> None:
        self.image: Image.Image | None = None

    def set_image(self, image: Image.Image) -> None:
        self.image = image

    def segment(self, task: SAM3Task) -> List[MaskInstance]:
        if self.image is None:
            raise RuntimeError("set_image must be called before segment")
        width, height = self.image.size
        mask = np.zeros((height, width), dtype=np.uint8)
        prompt = task.prompt.lower()
        if "worker" in prompt or "person" in prompt:
            x1, y1, x2, y2 = int(width * 0.43), int(height * 0.45), int(width * 0.58), int(height * 0.90)
            score = 0.94
        elif "load" in prompt or "suspended" in prompt:
            x1, y1, x2, y2 = int(width * 0.38), int(height * 0.18), int(width * 0.63), int(height * 0.38)
            score = 0.90
        else:
            return []
        mask[y1:y2, x1:x2] = 1
        return [
            MaskInstance(
                task_id=task.task_id,
                role=task.role,
                prompt=task.prompt,
                score=score,
                mask=mask,
                box_xyxy=[float(x1), float(y1), float(x2), float(y2)],
            )
        ]


class MockCLIPAdapter(CLIPAdapter):
    def score(self, image: Image.Image, texts: Sequence[str]) -> List[float]:
        return [0.82 for _ in texts]
