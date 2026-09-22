from __future__ import annotations

import json
from typing import Any, Dict, List

from site_safety.screening import screening_prompt_context


def build_first_pass_prompt(
    candidate_risks: List[Dict[str, Any]],
    *,
    allow_open_discovery: bool,
    image_manifest: List[str] | None = None,
    compact_discovery: bool = False,
    screening_trigger: Dict[str, Any] | None = None,
) -> str:
    if compact_discovery:
        return build_compact_discovery_prompt(
            candidate_risks,
            allow_open_discovery=allow_open_discovery,
            image_manifest=image_manifest,
            screening_trigger=screening_trigger,
        )
    risk_text = json.dumps(candidate_risks, ensure_ascii=False, indent=2)
    discovery_instruction = (
        "除候选风险外，如发现明确且重要的其他施工安全异常，可写入open_discoveries。"
        if allow_open_discovery
        else "不要添加候选列表以外的风险，open_discoveries返回空数组。"
    )
    manifest_instruction = ""
    if image_manifest and len(image_manifest) > 1:
        manifest_lines = "\n".join(f"- {item}" for item in image_manifest)
        manifest_instruction = f"""
输入图像清单：
{manifest_lines}

Image 1是唯一的完整场景。其余person crop是同一张图中人员区域的放大裁剪，
仅用于核查中远景小目标人员的安全帽、安全带等个人防护佩戴情况：
- 逐个裁剪检查后，把结论合并回对应候选风险，不要把裁剪当作独立场景；
- 任何人员只要在裁剪图中清晰可见未佩戴防护，就不得因其在全景图中过小而判absent；
- observed_facts与SAM3任务仍以Image 1全景为准。
"""
    screening_context = screening_prompt_context(screening_trigger)
    return f"""
请分析输入的工地图像。候选风险中同时包含真实风险与无关干扰项，这是一种推理时异常暴露机制。
{screening_context}
{manifest_instruction}
必须逐项判断为present、absent或uncertain，不得因为候选词出现在提示中就默认存在。
{discovery_instruction}

对于present或uncertain风险：
1. observed_facts只列支持风险成立的可见事实；counter_evidence列反对风险成立的
   可见事实，例如已看到防护物、距离明显较远或关键区域不可见；没有反证时返回空数组；
2. 将需要SAM3定位的可见实体拆成简短英文名词短语；
3. 不要让SAM3分割“缺失”本身。对于安全帽、安全带、安全绳、防护栏、洞口盖板等缺失型风险：
   - subject任务定位必须设置防护物的危险锚点或检查区域，例如高处作业人员、腰背部、临边、洞口；
   - protective_item任务搜索应存在的防护物，例如safety harness、attached safety lanyard、guardrail；
   - missing关系的subject_task_ids引用危险锚点，object_task_ids引用防护物；
   - params必须包含inspection_zone_visibility（clear|partial|occluded）和required_item；
   - clear仅表示应检查区域在原图中清晰可见，不能仅因为没有检测框就填clear；
4. 为关系型风险给出relation_checks；
5. mask_strategy只能选择：entity_union、subject_only、object_only、intersection、projected_below、missing_subject、expanded_object_zone。

候选风险：
{risk_text}

输出严格JSON，字段结构必须完全符合：
{{
  "scene_summary": "字符串",
  "has_possible_anomaly": true,
  "candidate_assessments": [
    {{
      "risk_id": "与候选risk_id一致",
      "risk_name_zh": "中文名",
      "status": "present|absent|uncertain",
      "confidence": 0.0,
      "observed_facts": ["支持风险成立的可见事实"],
      "counter_evidence": ["反对风险成立的可见事实；没有则为空数组"],
      "sam3_tasks": [
        {{
          "task_id": "本响应内唯一ID",
          "role": "subject|hazard_source|protective_item|region|evidence|other",
          "prompt": "short English noun phrase",
          "expected_count": 1
        }}
      ],
      "relation_checks": [
        {{
          "type": "none|below_and_horizontal_overlap|near|inside|overlap|missing|blocks_region",
          "subject_task_ids": ["task_id"],
          "object_task_ids": ["task_id"],
          "params": {{
            "inspection_zone_visibility": "clear|partial|occluded",
            "required_item": "仅missing关系填写应存在的防护物英文短语"
          }}
        }}
      ],
      "mask_strategy": "entity_union",
      "uncertainties": ["无法确认的信息"]
    }}
  ],
  "open_discoveries": []
}}

禁止输出Markdown代码块或JSON之外的解释。
""".strip()


def build_compact_discovery_prompt(
    candidate_risks: List[Dict[str, Any]],
    *,
    allow_open_discovery: bool,
    image_manifest: List[str] | None = None,
    discovery_payload: Dict[str, Any] | None = None,
    screening_trigger: Dict[str, Any] | None = None,
) -> str:
    compact_catalog = [
        {
            "risk_id": item.get("risk_id"),
            "name_zh": item.get("name_zh"),
            "description": item.get("description"),
        }
        for item in candidate_risks
    ]
    open_rule = (
        "允许发现目录外风险；目录外risk_id必须以open_开头。"
        if allow_open_discovery
        else "只允许输出目录内风险。"
    )
    locked_discovery = ""
    if discovery_payload:
        locked_discovery = f"""
第一阶段已经得到以下初步风险发现：
{json.dumps(discovery_payload, ensure_ascii=False)}

必须为hazards中的每一项生成一个candidate_assessments对象，不得静默丢弃。
本阶段只负责把初步发现转换为可执行RiskSpec；可以降低confidence或写uncertainties，
但不得把初步发现改写成absent，也不得新增hazards之外的风险。
"""
    screening_context = screening_prompt_context(screening_trigger)
    return f"""
你是施工现场视觉风险结构化助手。只依据图像中的可见事实。
{screening_context}
不要逐项回答整个风险目录，不要输出absent风险。
只输出最可能存在的present或uncertain风险，最多5项；没有风险时数组为空。
{open_rule}
{locked_discovery}

在输出前必须快速检查以下高危视觉线索，但不要为不存在的项目输出JSON：
- 高处人员、临边、洞口及安全带/护栏/盖板；
- 悬吊物及其下方或投影区域内的人员；
- 被材料占用的通道；
- 潮湿地面上的电缆或电气设备；
- 脚手架踏板、平台开口、护栏和明显变形；
- 未戴安全帽、人员倒地、烟火、人员靠近大型机械；
- 目录外的明显危险动作或物体。

若输入带有上游粗异常区域，先核验该区域及外扩邻域；之后必须回到完整场景做一次
开放风险扫查，不受粗区域和预设风险目录限制，避免遗漏区域外或未知类别异常。

必须逐个检查每个可见人员的头部：只要任何一人清晰露出头发且未佩戴安全帽，
hazards就必须包含“未佩戴安全帽”，不能因为其他人员戴了安全帽而省略。
必须检查每个高处人员所在平台的护栏/盖板，以及腰背部安全带和连接绳。

图片清单：
{json.dumps(image_manifest or ["Image 1: original construction-site image"], ensure_ascii=False)}

参考风险目录（用于复用risk_id，不要求逐项判断）：
{json.dumps(compact_catalog, ensure_ascii=False)}

每个风险必须描述可被分割的正向目标实体：
- subject：具体风险主体，例如某个工人；
- protective_item：安全帽、安全带、护栏等应存在物；
- hazard_source：吊物、机械、火焰等危险源；
- region：通道、积水、洞口等区域；
- evidence：烟雾、损坏构件等证据。

attributes描述可见外观，例如black T-shirt、yellow vest、back facing camera。
location使用left/center/right和foreground/middle/background。
category中禁止使用without、missing、unsafe、dangerous、violation等否定或抽象词。
缺失型风险必须分别描述subject和protective_item，不得要求SAM3直接分割“缺失”。

relation_spec.type只能使用：
none、below_and_horizontal_overlap、near、overlap、blocks_region、
missing_association（某个subject没有关联到protective_item）、missing（可见区域缺少防护物）。

输出严格JSON：
{{
  "scene_summary": "简短场景摘要",
  "has_possible_anomaly": true,
  "candidate_assessments": [
    {{
      "risk_id": "目录ID或open_动态ID",
      "risk_name_zh": "中文风险名",
      "risk_type": "风险类型",
      "status": "present|uncertain",
      "confidence": 0.0,
      "observed_facts": ["支持风险成立的可见事实"],
      "counter_evidence": ["反对风险成立的可见事实；没有则为空数组"],
      "target_entities": [
        {{
          "entity_id": "worker_1",
          "role": "subject|protective_item|hazard_source|region|evidence",
          "category": "positive English visible object",
          "attributes": ["visible English attribute"],
          "location": "center foreground",
          "expected_count": 1
        }}
      ],
      "relation_spec": {{
        "type": "none|below_and_horizontal_overlap|near|overlap|blocks_region|missing_association|missing",
        "subject_entity_ids": ["worker_1"],
        "object_entity_ids": ["helmet_1"],
        "params": {{
          "body_region": "head",
          "inspection_zone_visibility": "clear|partial|occluded"
        }}
      }},
      "mask_strategy": "entity_union|subject_only|object_only|intersection|projected_below|missing_subject|expanded_object_zone|unmatched_subject",
      "uncertainties": []
    }}
  ],
  "open_discoveries": []
}}

安全帽缺失必须表示为：
subject.category=construction worker并用attributes/location锁定具体人员；
protective_item.category=safety helmet；
relation_spec.type=missing_association；
mask_strategy=unmatched_subject。

不要输出sam3_tasks或relation_checks，它们由程序确定性生成。
禁止输出Markdown或JSON之外的文字。
""".strip()


def build_open_risk_discovery_prompt(
    image_manifest: List[str] | None = None,
    screening_trigger: Dict[str, Any] | None = None,
) -> str:
    crop_instruction = ""
    if image_manifest and len(image_manifest) > 1:
        crop_instruction = f"""
图片清单：
{json.dumps(image_manifest, ensure_ascii=False)}
Image 1是完整场景，其余图片是Image 1中不同人员的放大裁剪。
必须逐张检查人员裁剪的头部、腰背部和连接区域，再把发现合并回同一场景。
"""
    screening_context = screening_prompt_context(screening_trigger)
    return f"""
检查这张施工现场图片，只根据像素识别最主要的安全异常，不参考文件名。
{screening_context}
先自由观察，不要遍历固定风险目录，不要输出不存在的风险。
{crop_instruction}
重点注意人物动作与防护、上下/远近/遮挡关系、高处与临边、吊物、通道、
潮湿用电、脚手架平台、人员倒地、烟火，以及目录外的明显危险。
最多输出3个最重要异常；若没有明显异常，hazards返回空数组。

完成上游粗区域核验后，必须回到完整图像进行一次开放风险发现。不得因为异常位于
粗区域之外，或不属于上游模型类别，就忽略人员倒地、烟火、危险动作等明显风险。

必须逐个检查每个可见人员及每个人员裁剪的头部和躯干。只要有一人清晰露出
头发、头顶或普通帽子而没有安全帽，就必须报告“未佩戴安全帽”；不能因为同图
其他人员佩戴了安全帽而判定全场合格。人员未穿反光背心、倒地、吸烟等也按
可见事实独立报告，不要求风险必须属于预设目录。

输出严格JSON：
{{
  "scene_summary": "一句场景描述",
  "has_possible_anomaly": true,
  "hazards": [
    {{
      "risk_name_zh": "简短风险名",
      "risk_description": "一句异常说明",
      "confidence": 0.0,
      "subject_description": "人物或风险主体的衣着、位置、姿态",
      "visible_evidence": ["支持风险成立的直接可见证据"],
      "counter_evidence": ["反对风险成立的可见事实；没有则为空数组"]
    }}
  ]
}}

禁止输出Markdown或JSON之外的解释。
""".strip()


def build_person_risk_discovery_prompt(
    image_manifest: List[str],
    screening_trigger: Dict[str, Any] | None = None,
) -> str:
    return (
        """
这是第二个互补视角，只审核图中人员，不重复做全局场景总结。
Image 1是完整场景，其余图片是不同人员的放大裁剪。逐人建立清单并核对：
头部安全帽、躯干反光背心、高处安全带及连接绳、吸烟、倒地、危险动作，
以及人员与吊物、机械、洞口、临边的关系。
普通草帽、布帽、裸露头发都不等于安全帽。只有硬质壳体、帽檐和帽带外观
明确符合工业安全帽时，才判定已佩戴安全帽。不得用其他人的装备替代当前人员。
只报告能绑定到具体人员或人员裁剪的异常；最多3项。

"""
        + build_open_risk_discovery_prompt(
            image_manifest, screening_trigger=screening_trigger
        )
    )


def build_anchor_retry_prompt(scene_summary: str) -> str:
    return f"""
上一轮场景摘要是：
{scene_summary}

上一轮没有输出风险，但摘要中已经出现高危作业主体与环境锚点。请只复核摘要中
已经出现的实体及其空间/防护关系，不遍历风险目录：
- 若有悬吊物和人员，检查人员是否位于吊物下方或投影区；
- 若有脚手架和作业人员，检查踏板连续性、平台开口、护栏及防坠连接；
- 若有高处、临边或洞口，检查护栏、盖板、安全带和连接绳。
只有像素支持时才输出；最多2项。输出格式与此前hazards JSON完全相同。
严格JSON格式：
{{
  "scene_summary": "复核后的场景摘要",
  "has_possible_anomaly": true,
  "hazards": [
    {{
      "risk_name_zh": "简短风险名",
      "risk_description": "异常说明",
      "confidence": 0.0,
      "subject_description": "主体外观、位置、姿态",
      "visible_evidence": ["支持风险成立的直接可见证据"],
      "counter_evidence": ["反对风险成立的可见事实；没有则为空数组"]
    }}
  ]
}}
禁止Markdown和JSON以外的文字。
""".strip()
