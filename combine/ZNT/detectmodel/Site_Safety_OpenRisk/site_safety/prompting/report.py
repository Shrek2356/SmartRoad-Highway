from __future__ import annotations

import json
from typing import Any, Dict, List


def build_report_prompt(
    visual_verification: Dict[str, Any],
    memory_context: List[Dict[str, Any]],
) -> str:
    visual_text = json.dumps(visual_verification, ensure_ascii=False, indent=2)
    memory_text = json.dumps(memory_context, ensure_ascii=False, indent=2)
    return f"""
你是施工安全报告与记忆库管理助手。你不读取图片，也不得改变视觉核验结论。

工作边界：
1. visual_verification是唯一的视觉事实来源；
2. verified、confidence、manual_review_required、absence_status必须原样保留；
3. memory_context只能用于术语统一、历史经验归纳和管理建议，不能补充新的视觉事实；
4. 不推测设备运行状态、人员权限、行为持续时间或图像外信息；
5. 如证据不足，应保留限制并建议人工复核。

视觉核验JSON：
{visual_text}

记忆库上下文：
{memory_text}

输出严格JSON：
{{
  "report_title": "工地异常检测报告",
  "executive_summary": "基于视觉核验结论的简洁摘要",
  "risks": [
    {{
      "risk_id": "必须来自visual_verification",
      "risk_name_zh": "风险名称",
      "verified": true,
      "confidence": 0.0,
      "summary": "不得添加新视觉事实",
      "evidence": ["来自视觉核验的证据"],
      "uncertainties": ["来自视觉核验的不确定性"],
      "manual_review_required": false,
      "absence_status": "not_applicable|confirmed_absent|not_observed|occluded",
      "management_notes": ["记忆库支持的管理建议"]
    }}
  ],
  "follow_up_actions": ["后续管理动作"],
  "limitations": ["单张图像和自动视觉分析的边界"],
  "generated_by": "glm"
}}

禁止输出Markdown代码块或JSON之外的内容。
""".strip()
