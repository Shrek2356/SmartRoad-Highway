"""OpenAI ViT-L/14 consistency bridge backed by the local OpenCLIP package."""
from __future__ import annotations

from pathlib import Path
from typing import Any, List

from PIL import Image


class CLIPBridge:
    def __init__(
        self,
        model_name: str = "ViT-L-14",
        checkpoint: str = r"C:\Users\SYS03\.cache\clip\ViT-L-14.pt",
        device: str = "cuda",
        precision: str = "fp16",
        **_: Any,
    ) -> None:
        checkpoint_path = Path(checkpoint)
        if not checkpoint_path.is_file():
            raise FileNotFoundError(f"CLIP checkpoint not found: {checkpoint_path}")

        import open_clip
        import torch

        if device.startswith("cuda") and not torch.cuda.is_available():
            device = "cpu"
        if device == "cpu":
            precision = "fp32"
        self.device = device
        self.torch = torch
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            model_name=model_name,
            pretrained=str(checkpoint_path),
            device=device,
            precision=precision,
            # Official OpenAI .pt files are TorchScript archives. PyTorch 2.6+
            # cannot open them through torch.load(weights_only=True).
            weights_only=False,
        )
        self.tokenizer = open_clip.get_tokenizer(model_name)
        self.model.eval()
        self.model_dtype = self.model.visual.conv1.weight.dtype

    def score(self, *, image: Image.Image, texts: List[str]) -> List[float]:
        if not texts:
            return []
        torch = self.torch
        image_tensor = (
            self.preprocess(image.convert("RGB"))
            .unsqueeze(0)
            .to(device=self.device, dtype=self.model_dtype)
        )
        text_tokens = self.tokenizer(texts).to(self.device)
        with torch.inference_mode():
            image_features = self.model.encode_image(image_tensor)
            text_features = self.model.encode_text(text_tokens)
            image_features = image_features / image_features.norm(dim=-1, keepdim=True).clamp_min(1e-12)
            text_features = text_features / text_features.norm(dim=-1, keepdim=True).clamp_min(1e-12)
            cosine = image_features @ text_features.T
            scores = ((cosine.squeeze(0).float() + 1.0) / 2.0).clamp(0.0, 1.0)
        return [float(x) for x in scores.cpu().tolist()]
