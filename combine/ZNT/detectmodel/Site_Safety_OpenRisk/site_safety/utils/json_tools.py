from __future__ import annotations

import json
import re
from typing import Any


def extract_json_text(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", stripped, re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1)
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return stripped[start : end + 1]
    raise ValueError("No JSON object found in model output")


def parse_json_object(text: str) -> dict[str, Any]:
    data = json.loads(extract_json_text(text))
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    return data
