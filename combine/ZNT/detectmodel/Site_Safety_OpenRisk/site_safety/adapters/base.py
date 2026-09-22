from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Sequence

import numpy as np
from PIL import Image

from site_safety.schemas import SAM3Task


@dataclass
class MaskInstance:
    task_id: str
    role: str
    prompt: str
    score: float
    mask: np.ndarray
    box_xyxy: Optional[List[float]] = None


class MLLMAdapter(ABC):
    @abstractmethod
    def generate_json(self, images: Sequence[Image.Image], prompt: str) -> str:
        """Return a JSON string. The caller validates it with Pydantic."""
        raise NotImplementedError


class SAM3Adapter(ABC):
    @abstractmethod
    def set_image(self, image: Image.Image) -> None:
        raise NotImplementedError

    @abstractmethod
    def segment(self, task: SAM3Task) -> List[MaskInstance]:
        raise NotImplementedError


class CLIPAdapter(ABC):
    @abstractmethod
    def score(self, image: Image.Image, texts: Sequence[str]) -> List[float]:
        """Return one normalized similarity score per text."""
        raise NotImplementedError
