from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from site_safety.schemas import ScreeningTrigger


def parse_screening_trigger(value: Any) -> Optional[ScreeningTrigger]:
    """Validate an optional upstream high-recall screening result."""
    if value is None:
        return None
    if isinstance(value, ScreeningTrigger):
        return value
    if isinstance(value, (str, Path)):
        payload = json.loads(Path(value).read_text(encoding="utf-8"))
    elif isinstance(value, dict):
        payload = value
    else:
        raise TypeError("screening trigger must be a mapping, path, or ScreeningTrigger")
    return ScreeningTrigger.model_validate(payload)


def screening_prompt_context(trigger: ScreeningTrigger | Dict[str, Any] | None) -> str:
    """Render routing metadata while explicitly preventing confirmation bias."""
    validated = parse_screening_trigger(trigger)
    if validated is None or not validated.triggered:
        return ""
    # A bare "likely anomalous" prior did not improve local-8B recall and
    # increased control alerts. Keep empty triggers for routing/audit only.
    if not validated.suspected_regions and not validated.suspected_concepts:
        return ""
    payload = json.dumps(validated.model_dump(), ensure_ascii=False)
    return f"""
上游轻量筛查模型发现了初步异常并给出粗略关注区域，路由信息如下：
{payload}

重要约束：该信息只表示本图值得优先审核，不是异常成立的视觉证据。
- suspected_regions可能同时包含多人、背景和无关物体，不是精确实例掩码；
- 检查粗区域内部、外扩邻域及其在完整图像中的上下文关系；
- suspected_concepts如存在也只是粗类别提示，不代表具体风险已经识别；
- 只能依据输入图像像素确认风险，不得照抄上游类别或置信度；
- 若没有足够视觉证据，必须允许输出无可见异常或uncertain，禁止为了迎合触发结果编造风险。
""".strip()


def load_trigger_for_stem(directory: str | Path, stem: str) -> Optional[ScreeningTrigger]:
    """Load `<stem>.json` from a detector hand-off directory when present."""
    path = Path(directory) / f"{stem}.json"
    return parse_screening_trigger(path) if path.is_file() else None
