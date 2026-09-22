from __future__ import annotations

import json
from typing import Any

from site_safety.screening import screening_prompt_context


RISK_AUDIT_RULES = [
    {
        "risk_id": "missing_helmet",
        "name_zh": "施工人员未佩戴安全帽",
        "audit": "逐个检查所有人员头部；裸发、普通帽子不等于工业安全帽。",
    },
    {
        "risk_id": "missing_edge_protection",
        "name_zh": "临边或洞口防护缺失",
        "audit": "检查人员附近的平台边缘、楼板洞口、边坡和护栏或盖板。",
    },
    {
        "risk_id": "missing_fall_protection",
        "name_zh": "高处作业防坠落装备缺失",
        "audit": "检查每个高处人员腰背部的安全带、连接绳和可靠挂点。",
    },
    {
        "risk_id": "machinery_proximity",
        "name_zh": "人员过度靠近施工机械",
        "audit": "逐一检查人员与挖掘机、装载机、铲斗、动臂和回转区域的关系。",
    },
]


def build_structured_risk_audit_prompt(
    *,
    clip_hints: dict[str, Any] | None = None,
    image_manifest: list[str] | None = None,
    screening_trigger: dict[str, Any] | None = None,
) -> str:
    """Build a recall-oriented perception-then-audit prompt for local VLMs."""
    hint_block = ""
    if clip_hints:
        hint_block = f"""
以下CLIP结果只是注意力提示，不是风险事实，可能误检。必须回到对应图像区域核验，
但不得在未查看提示区域的情况下忽略它：
{json.dumps(clip_hints, ensure_ascii=False)}
"""
    rules = json.dumps(RISK_AUDIT_RULES, ensure_ascii=False)
    manifest = json.dumps(
        image_manifest or ["Image 1: original construction-site image"],
        ensure_ascii=False,
    )
    screening_context = screening_prompt_context(screening_trigger)
    return f"""
你是施工现场视觉审核员。只依据输入图像像素判断，不参考文件名。

{screening_context}

本轮重点是避免漏检。不要只选“最重要的三个风险”，也不要用全场概括代替逐人、
逐机械和逐区域检查。先在内部完成实体清点，再对下面四项规则逐项输出审核结果。

图片清单：{manifest}
Image 1是唯一完整场景；person、head、waist-back-hook ROI和scene tile均来自同一张图，
只能用于放大核验，不能把同一人员或同一风险重复计数。
{hint_block}
审核规则：{rules}

判定要求：
1. 每个可见人员必须单独编号，检查头部、腰背部、所处高度、最近临边和最近机械；
2. 每台挖掘机、装载机或其他大型机械必须单独编号，并检查每个person-machine组合；
3. 不得只凭“前景/背景”断言距离安全；单张图透视不足但风险锚点存在时填uncertain；
4. 只有风险主体或环境锚点明确不存在时才能填absent；目标过小、遮挡或细节不清填uncertain；
5. 缺失型风险必须说明检查区域是否清晰，以及具体“未观察到”的防护物；
6. CLIP分数不能作为风险成立证据，只用于提醒你检查可能被忽略的区域；
7. 四个risk_id必须各返回一次，不得新增或遗漏。confidence表示当前图像对该状态的支持度。
8. confidence禁止填写0或沿用模板占位值：present必须在0.60至1.00之间，
   uncertain必须在0.25至0.59之间，absent必须在0.60至1.00之间。
9. visible_evidence列支持风险成立的直接证据；counter_evidence列与风险成立相反的
   可见事实。存在证据冲突时不得忽略反证，应降低置信度或填写uncertain。
10. 一旦人员位于脚手架、钢结构、屋面、平台顶部或明显高差区域，必须审核其
    安全带、连接绳和可见挂点；细节过小或被遮挡时填uncertain，不得直接填absent。
11. 临边和洞口审核不得以“附近没有人员”为跳过条件；scene tile中可见的平台、
    基坑、楼板或道路坠落边缘都必须记录到risk_regions后再判断防护情况。
12. status必须与证据方向一致：写出“无护栏、未戴安全帽、未系安全带、无连接绳、
    无挂点”等缺失事实时，status只能是present或uncertain，禁止填absent。

只输出严格JSON：
{{
  "scene_inventory": {{
    "persons": [{{
      "person_id": "person_1",
      "location": "left|center|right + foreground|middle|background",
      "head_observation": "可见头部及头部防护",
      "waist_observation": "腰背部和连接区域可见情况",
      "height_context": "ground|elevated|uncertain",
      "nearest_edge_or_opening": "region_id或none",
      "nearest_machine": "machine_id或none"
    }}],
    "machines": [{{
      "machine_id": "machine_1",
      "type": "excavator|loader|other",
      "location": "位置",
      "visible_parts": ["body", "boom", "bucket"]
    }}],
    "risk_regions": [{{
      "region_id": "region_1",
      "type": "platform_edge|opening|slope|scaffold",
      "location": "位置",
      "protection_observation": "护栏、盖板等可见情况"
    }}]
  }},
  "risk_audits": [
    {{
      "risk_id": "missing_helmet",
      "status": "present|uncertain|absent",
      "confidence": 0.85,
      "subject_ids": ["person_1"],
      "anchor_ids": [],
      "visible_evidence": ["图中直接可见事实"],
      "counter_evidence": ["反对风险成立的可见事实；没有则为空数组"],
      "uncertainties": []
    }}
  ]
}}

禁止Markdown、解释文字和JSON之外的内容。
""".strip()
