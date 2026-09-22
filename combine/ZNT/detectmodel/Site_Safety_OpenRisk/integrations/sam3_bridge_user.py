"""Local SAM3 image bridge for the Site Safety OpenRisk pipeline."""
from __future__ import annotations

import sys
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image


class SAM3Bridge:
    def __init__(
        self,
        checkpoint: str,
        repo_path: str = r"k:\ZNT\sam3-main",
        device: str = "cuda",
        confidence_threshold: float = 0.20,
        amp_dtype: str = "bfloat16",
        **_: Any,
    ) -> None:
        checkpoint_path = Path(checkpoint)
        repo = Path(repo_path)
        if not checkpoint_path.is_file():
            raise FileNotFoundError(f"SAM3 checkpoint not found: {checkpoint_path}")
        if not (repo / "sam3").is_dir():
            raise FileNotFoundError(f"SAM3 repository not found: {repo}")
        if str(repo) not in sys.path:
            sys.path.insert(0, str(repo))

        import torch
        from sam3.model.sam3_image_processor import Sam3Processor
        from sam3.model_builder import build_sam3_image_model

        if device.startswith("cuda") and not torch.cuda.is_available():
            device = "cpu"
        self.device = device
        self.torch = torch
        self.amp_dtype = getattr(torch, amp_dtype)
        self.model = build_sam3_image_model(
            checkpoint_path=str(checkpoint_path),
            load_from_HF=False,
            device=device,
            eval_mode=True,
        )
        self.processor = Sam3Processor(
            self.model,
            device=device,
            confidence_threshold=float(confidence_threshold),
        )
        self.state: Optional[Dict[str, Any]] = None

    def set_image(self, image: Image.Image) -> None:
        with self._autocast():
            self.state = self.processor.set_image(image.convert("RGB"))

    def segment(
        self,
        *,
        prompt: str,
        task_id: str,
        role: str,
        expected_count: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        if self.state is None:
            raise RuntimeError("set_image must be called before segment")

        with self._autocast():
            output = self.processor.set_text_prompt(state=self.state, prompt=prompt)
        masks = output["masks"].detach().to("cpu").numpy()
        boxes = output["boxes"].detach().to("cpu").numpy()
        scores = output["scores"].detach().float().to("cpu").numpy()

        results: List[Dict[str, Any]] = []
        for index in range(len(scores)):
            mask = np.asarray(masks[index]).squeeze()
            if mask.ndim != 2:
                raise ValueError(
                    f"SAM3 returned mask with shape {masks[index].shape}; expected a 2-D mask"
                )
            results.append(
                {
                    "mask": (mask > 0).astype(np.uint8),
                    "score": float(np.clip(scores[index], 0.0, 1.0)),
                    "box_xyxy": [float(x) for x in np.asarray(boxes[index]).reshape(-1)[:4]],
                }
            )

        results.sort(key=lambda item: item["score"], reverse=True)
        if expected_count is not None and expected_count > 0:
            results = results[:expected_count]
        return results

    def _autocast(self):
        if self.device.startswith("cuda"):
            return self.torch.autocast(device_type="cuda", dtype=self.amp_dtype)
        return nullcontext()
