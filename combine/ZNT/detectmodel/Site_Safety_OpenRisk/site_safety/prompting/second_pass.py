from __future__ import annotations

import json
from typing import Any, Dict, List


def build_second_pass_prompt(
    evidences: List[Dict[str, Any]],
    image_manifest: List[str] | None = None,
) -> str:
    evidence_text = json.dumps(evidences, ensure_ascii=False, indent=2)
    manifest_text = json.dumps(image_manifest or [], ensure_ascii=False, indent=2)
    return f"""
你将看到原始工地图像，以及由SAM3和几何关系模块生成的异常叠加图或局部裁剪图。
请基于这些证据确认、修正或撤销第一次判断。SAM3定位结果是辅助证据，不应被无条件视为真值。
只描述图像中可见事实，不推测设备是否运行、人员是否授权、施工阶段或不可见管理信息。
本阶段只输出精简的视觉核验JSON，不撰写管理报告、不查询记忆库、不生成整改建议。

缺失型风险必须填写absence_status：
- confirmed_absent：应检查区域在原图或裁剪图中清晰可见，危险锚点已定位，且明确看不到应有防护物；
- not_observed：没有观察到防护物，但区域只部分可见、分辨率不足或定位证据不足；
- occluded：腰背部、连接点、临边或其他关键检查区域被遮挡；
- not_applicable：非缺失型风险。
不得仅因SAM3没有返回防护物实例就填写confirmed_absent。

图片顺序与含义：
{manifest_text}

结构化证据：
{evidence_text}

输出严格JSON：
{{
  "overall_has_anomaly": true,
  "overall_summary": "总体结论",
  "final_risks": [
    {{
      "risk_id": "风险ID",
      "risk_name_zh": "风险名称",
      "verified": true,
      "confidence": 0.0,
      "visible_evidence": ["支持风险成立的证据"],
      "counter_evidence": ["反对风险成立的证据"],
      "risk_description": "仅基于可见证据的一句话说明",
      "uncertainties": ["无法确认的信息"],
      "manual_review_required": false,
      "absence_status": "not_applicable|confirmed_absent|not_observed|occluded"
    }}
  ]
}}

如关键实体未定位、关系核验失败或证据冲突，应降低置信度、撤销风险或标记manual_review_required。
必须重新检查第一阶段counter_evidence，不得只保留支持风险的证据。若反证被图像确认，
应降低置信度、改为人工复核或撤销风险。
禁止输出Markdown代码块或JSON之外的解释。
""".strip()
