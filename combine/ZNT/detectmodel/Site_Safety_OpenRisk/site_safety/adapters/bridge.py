from __future__ import annotations

import importlib
from typing import Any, List, Sequence

import numpy as np
from PIL import Image

from site_safety.adapters.base import CLIPAdapter, MaskInstance, SAM3Adapter
from site_safety.schemas import SAM3Task


class BridgeSAM3Adapter(SAM3Adapter):
    """Loads a user-written SAM3 bridge without coupling this project to one repo layout."""

    def __init__(self, module_name: str, class_name: str, init_kwargs: dict[str, Any]) -> None:
        module = importlib.import_module(module_name)
        bridge_cls = getattr(module, class_name)
        self.bridge = bridge_cls(**init_kwargs)

    def set_image(self, image: Image.Image) -> None:
        self.bridge.set_image(image)

    def segment(self, task: SAM3Task) -> List[MaskInstance]:
        raw_items = self.bridge.segment(
            prompt=task.prompt,
            task_id=task.task_id,
            role=task.role,
            expected_count=task.expected_count,
        )
        results: List[MaskInstance] = []
        for item in raw_items:
            mask = np.asarray(item["mask"]).astype(np.uint8)
            results.append(
                MaskInstance(
                    task_id=task.task_id,
                    role=task.role,
                    prompt=task.prompt,
                    score=float(item["score"]),
                    mask=mask,
                    box_xyxy=[float(x) for x in item.get("box_xyxy", [])] or None,
                )
            )
        return results


class BridgeCLIPAdapter(CLIPAdapter):
    def __init__(self, module_name: str, class_name: str, init_kwargs: dict[str, Any]) -> None:
        module = importlib.import_module(module_name)
        bridge_cls = getattr(module, class_name)
        self.bridge = bridge_cls(**init_kwargs)

    def score(self, image: Image.Image, texts: Sequence[str]) -> List[float]:
        scores = self.bridge.score(image=image, texts=list(texts))
        return [float(x) for x in scores]
