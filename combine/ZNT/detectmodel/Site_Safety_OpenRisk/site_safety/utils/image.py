from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional, Sequence

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def image_font(size=18):
    for path in ['C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/simhei.ttf',
                 '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc', 'DejaVuSans.ttf']:
        try:
            return ImageFont.truetype(path,size)
        except OSError:
            pass
    return ImageFont.load_default()


def load_rgb(path: str | Path) -> Image.Image:
    return Image.open(path).convert("RGB")


def mask_box(mask: np.ndarray) -> Optional[list[float]]:
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return None
    return [float(xs.min()), float(ys.min()), float(xs.max() + 1), float(ys.max() + 1)]


def save_binary_mask(mask: np.ndarray, path: str | Path) -> None:
    out = (mask.astype(np.uint8) * 255)
    Image.fromarray(out, mode="L").save(path)


def union_masks(masks: Iterable[np.ndarray], shape: tuple[int, int]) -> np.ndarray:
    merged = np.zeros(shape, dtype=np.uint8)
    for mask in masks:
        if mask.shape != shape:
            raise ValueError(f"Mask shape mismatch: expected {shape}, got {mask.shape}")
        merged = np.maximum(merged, (mask > 0).astype(np.uint8))
    return merged


def crop_around_mask(image: Image.Image, mask: np.ndarray, padding_ratio: float = 0.12) -> Optional[Image.Image]:
    box = mask_box(mask)
    if box is None:
        return None
    x1, y1, x2, y2 = box
    width, height = image.size
    pad_x = max(8, int((x2 - x1) * padding_ratio))
    pad_y = max(8, int((y2 - y1) * padding_ratio))
    crop_box = (
        max(0, int(x1) - pad_x),
        max(0, int(y1) - pad_y),
        min(width, int(x2) + pad_x),
        min(height, int(y2) + pad_y),
    )
    return image.crop(crop_box)


def draw_overlay(
    image: Image.Image,
    risk_mask: np.ndarray,
    entity_boxes: Sequence[tuple[list[float], str, float]],
    title: str,
) -> Image.Image:
    base = image.convert("RGBA")
    rgba = np.zeros((risk_mask.shape[0], risk_mask.shape[1], 4), dtype=np.uint8)
    rgba[..., 0] = 255
    rgba[..., 1] = 60
    rgba[..., 2] = 40
    rgba[..., 3] = (risk_mask > 0).astype(np.uint8) * 95
    mask_layer = Image.fromarray(rgba, mode="RGBA")
    composed = Image.alpha_composite(base, mask_layer)
    draw = ImageDraw.Draw(composed)
    font = image_font(18)
    for box_index, (box, label, score) in enumerate(sorted(entity_boxes,key=lambda x:x[2],reverse=True)):
        x1, y1, x2, y2 = box
        draw.rectangle((x1, y1, x2, y2), outline=(255, 230, 40, 255), width=3)
        if box_index < 10:
            draw.text((x1 + 3, max(31, y1 - 20)), f"{label} {score:.2f}", fill=(255, 255, 255, 255), font=font)
    draw.rectangle((0, 0, composed.width, 30), fill=(0, 0, 0, 180))
    draw.text((8, 5), title, fill=(255, 255, 255, 255), font=font)
    return composed.convert("RGB")


def add_image_label(image: Image.Image, label: str) -> Image.Image:
    labeled = image.convert("RGB").copy()
    draw = ImageDraw.Draw(labeled)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
    banner_height = 32
    draw.rectangle((0, 0, labeled.width, banner_height), fill=(0, 0, 0))
    draw.text((8, 6), label, fill=(255, 255, 255), font=font)
    return labeled
