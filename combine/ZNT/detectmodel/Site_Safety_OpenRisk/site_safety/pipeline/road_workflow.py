"""Bounded observation -> planning workflow. Planner cannot rewrite observations."""
import json
import re
from typing import Literal
from pydantic import BaseModel, Field, model_validator


class RoadObservation(BaseModel):
    risk_id: str
    risk_name_zh: str
    status: Literal['present', 'uncertain', 'absent']
    observed_facts: list[str] = Field(default_factory=list)
    counter_evidence: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    region_xyxy: list[float] | None = None

    @model_validator(mode='after')
    def validate_region(self):
        b = self.region_xyxy
        if b is not None and (len(b) != 4 or not all(0 <= x <= 1 for x in b)
                              or b[0] >= b[2] or b[1] >= b[3]):
            self.region_xyxy = None
        return self


class RoadObservationResponse(BaseModel):
    scene_summary: str
    visibility: Literal['adequate', 'limited', 'unassessable'] = 'limited'
    quality_issues: list[str] = Field(default_factory=list)
    observations: list[RoadObservation] = Field(default_factory=list)
    road_surface_state: Literal['dry', 'wet_only', 'standing_water', 'flooded', 'uncertain'] = 'uncertain'
    water_evidence: list[str] = Field(default_factory=list)
    scene_elements: list[Literal['road', 'traffic_sign', 'guardrail']] = Field(default_factory=list)
    road_type: Literal['highway', 'urban', 'unknown'] = 'unknown'


class LocalizationPlan(BaseModel):
    risk_id: str
    road_prompt: str = Field(min_length=1, max_length=300)
    target_prompt: str = Field(min_length=1, max_length=300)

    @model_validator(mode='after')
    def atomic_concept(self):
        # Reject scene captions rather than silently sending them to SAM3.
        words = re.findall(r"[A-Za-z]+(?:-[A-Za-z]+)?", self.target_prompt)
        if not 1 <= len(words) <= 6 or re.search(r'[,;/]|\b(and|or|with|covering|emitting|across|surrounded)\b', self.target_prompt, re.I):
            raise ValueError('target_prompt must name ONE concrete concept in 1-6 English words; split different objects into separate plans')
        return self


class RoadPlanResponse(BaseModel):
    plans: list[LocalizationPlan] = Field(default_factory=list)


def observation_prompt(catalog):
    return '\n'.join([
        '你是道路图像观察员。本阶段只描述可见事实，不安排工具，不打置信度分数，不确认通行安全。',
        '先检查视角、遮挡、模糊与黑色无数据区域，输出visibility及quality_issues。',
        '按火焰或烟雾、碰撞或侧翻、具体车辆占道、散落物、积水或泥沙覆盖、道路损伤、交通设施损坏和行人动物侵入逐项检查。无可见异常时observations为空，不必凑齐类别。',
        '每条发现先写具体外观及图像位置，再映射目录；同一类别合并描述。不要把车辆统一叫散落物。',
        '仅因遮挡或无数据无法判断时只写quality_issues，不生成塌方等风险。没有可见事实不要创建风险。',
        '修补与破损、湿润与积水、路外停放与占道难区分时，记录备选解释及uncertain。',
        '必须先判断road_surface_state：dry干燥；wet_only雨后湿润、反光或薄水膜（正常天气状态，不列为异常）；standing_water有明确水洼边界、积聚水体；flooded有大片水体淹没道路、横向漫流或车辆涉水；uncertain证据不足。water_evidence只写积聚水体的直接迹象，不能把反光、下雨、湿润写成淹水证据。',
        '仅湿润、镜面反射、水膜、正常车轮轻微溅水时，water_evidence为空，不输出water_accumulation；明显浑浊水体漫过车道、成片淹没才保留积水异常。不得用road_condition_anomaly或open_类别绕过这个边界。',
        '一张图可以有多个风险标签，同类多个实体也要全部描述。火焰和烟雾分别描述；轮胎、木托盘、纸箱、横倒金属构件分别描述；不要只描述车而忽略旁边散落物。',
        '只有车辆相互接触伴随明显破损、侧翻等直接证据才列traffic_collision。车辆旁有杂物不等于事故。城市路口正常过街行人、正常排队车辆不属于高速闯入或阻塞。先区分road_type。',
        'scene_elements仅列画面可见的基础对象road、traffic_sign、guardrail，用于独立的场景标注，不代表损坏。完好的路牌不要当风险；倒伏、断裂、横在车道上的路牌或构件需另列设施损坏或阻塞。',
        'region_xyxy是有依据时提供的粗略图像归一化范围[x1,y1,x2,y2]，不是精确定位或地理坐标；无法定位填null。',
        '车辆火焰归vehicle_fire；碰撞或侧翻归traffic_collision；普通行驶车辆不是占道。烟雾无明火时保留蒸汽、扬尘等解释。静态图不能证明抛锚、违停、逆行或超速。目录外道路相关的明确可见异常可用open_开头ID；不检查工人防护装备。不推断水深、尺寸、成因或严重等级。',
        '目录：'+json.dumps(catalog,ensure_ascii=False),
        '严格JSON Schema：'+json.dumps(RoadObservationResponse.model_json_schema(),ensure_ascii=False),
    ])


def compile_observations(raw, catalog, concept_mode=False):
    parsed = RoadObservationResponse.model_validate(raw)
    names = {r['risk_id']:r.get('name_zh',r['risk_id']) for r in catalog}
    quality = list(parsed.quality_issues)
    candidates = {}
    dismissed = []
    for observation in parsed.observations:
        row = observation.model_dump()
        row['observed_facts'] = [f.strip() for f in row['observed_facts'] if f.strip()]
        if not row['observed_facts']:
            quality.extend(row['uncertainties'])
            continue
        if row['status'] == 'absent':
            continue
        rid = row['risk_id']
        if concept_mode and rid == 'water_accumulation' and parsed.road_surface_state in {'dry', 'wet_only'} and not parsed.water_evidence:
            dismissed.append(dict(row, disposition='weather_only', reason='仅干燥或湿润反光，无积聚水体证据'))
            continue
        from site_safety.road_domain import LEGACY_RISK_IDS
        if rid.removeprefix('open_') in LEGACY_RISK_IDS:
            quality.append('排除非道路领域候选：'+rid)
            continue
        if rid not in names and not rid.startswith('open_'):
            quality.append('未识别的风险类别：'+rid)
            continue
        row.update(confidence=0.0, sam3_tasks=[], relation_checks=[], mask_strategy='object_only',
                   localization_plan_status='not_planned', risk_name_zh=names.get(rid,row['risk_name_zh']))
        if rid in candidates:
            old=candidates[rid]
            for field in ['observed_facts','counter_evidence','uncertainties']:
                old[field]=list(dict.fromkeys(old[field]+row[field]))
            old['region_xyxy']=None  # merged regions need full-image review
            if row['status']=='uncertain': old['status']='uncertain'
        else:
            candidates[rid]=row
    assessment = {'visibility':parsed.visibility,'issues':list(dict.fromkeys(quality)),
                  'source':'model_visual_assessment','scope':'current_image'}
    if concept_mode:
        assessment.update(workflow_version='road-concepts-v5', road_surface_state=parsed.road_surface_state,
                          water_evidence=parsed.water_evidence, scene_elements=parsed.scene_elements,
                          road_type=parsed.road_type, dismissed_observations=dismissed)
    return dict(scene_summary=parsed.scene_summary, has_possible_anomaly=bool(candidates),
                candidate_assessments=list(candidates.values()),open_discoveries=[],
                assessment_quality=assessment)


def planning_prompt(candidates):
    facts = [{k:r[k] for k in ['risk_id','risk_name_zh','observed_facts','counter_evidence','uncertainties']} for r in candidates]
    return '\n'.join([
        '你是道路定位任务规划员，只为输入risk_id生成定位文本，不改变观察、类别或结论，不新增risk_id。',
        'road_prompt固定为road。target_prompt每项只允许一个具体实体概念，1至6个英文单词，优先1至3词。禁止整句、并列and/or、with/covering/emitting、位置关系、数量或行为。',
        '保留颜色和实体类别，例如white trailer、mud covering road；不要把车辆改成debris。',
        '同一risk_id可以重复出现，每次是一个不同目标，最多6种概念。散落物按可见对象分别给tire、wooden pallet、cardboard box、debris；火情分别给flame和smoke；淹水用water或floodwater；路牌用traffic sign，金属横挡物用metal barrier。示例仅约束命名，不能增加原图未观察到的实体。',
        '背景正常车轮不是散落轮胎，优先用loose tire。不要把道路场景写入目标短语。每个已观察到的risk_id至少有一个计划。',
        '目标不可见或没有可定位实体时省略该计划。不要编造道路区域。',
        json.dumps(facts,ensure_ascii=False),
        '严格JSON Schema：'+json.dumps(RoadPlanResponse.model_json_schema(),ensure_ascii=False),
    ])


def apply_plans(payload, raw, max_risks=8):
    plans=RoadPlanResponse.model_validate(raw).plans
    mapping={}
    for plan in plans:
        group=mapping.setdefault(plan.risk_id,[])
        if not any(p.target_prompt == plan.target_prompt for p in group):
            group.append(plan)
    known={r['risk_id'] for r in payload['candidate_assessments']}
    if set(mapping)-known:
        raise ValueError('Planner introduced unobserved risk IDs')
    for index,row in enumerate(payload['candidate_assessments']):
        group=mapping.get(row['risk_id'])
        if payload.get('assessment_quality',{}).get('workflow_version')=='road-concepts-v5':
            grounded=grounded_target_concepts(row)
            if grounded:
                before=[p.target_prompt for p in group or []]
                group=[LocalizationPlan(risk_id=row['risk_id'],road_prompt='road',target_prompt=p) for p in grounded]
                payload['assessment_quality'].setdefault('concept_compilation',[]).append(dict(
                    risk_id=row['risk_id'],planner_proposals=before,compiled_targets=grounded,
                    source='explicit nouns in observed facts; not dataset labels'))
        if index>=max_risks or not group:
            row['localization_plan_status']='budget_exceeded' if index>=max_risks else 'no_plan'
            continue
        if len(group)>6:
            row['uncertainties'].append('定位预算仅覆盖前六种不同目标，其余目标需人工核对。')
        row['sam3_tasks']=[dict(task_id=f'p{index}_road',role='subject',prompt='road',expected_count=8)]
        row['sam3_tasks'] += [dict(task_id=f'p{index}_target{j}',role='hazard_source',prompt=p.target_prompt.strip().lower(),expected_count=128) for j,p in enumerate(group[:6])]
        row['relation_checks']=[dict(type='overlap',subject_task_ids=[f'p{index}_road'],object_task_ids=[f'p{index}_target{j}'],params={}) for j in range(min(6,len(group)))]
        row['localization_plan_status']='planned'


def grounded_target_concepts(row):
    """Compile common physical nouns only when explicitly present in the observation.

    This is a prompt constraint, not a detector or evidence of mask correctness.
    Unknown concepts retain the bounded planner path and visual review.
    """
    facts=' '.join(row.get('observed_facts',[]))
    rid=row['risk_id']
    if rid=='vehicle_fire':
        rules=[(r'火焰|明火|燃烧|flame|fire','flame'),(r'烟雾|浓烟|黑烟|烟柱|smoke','smoke')]
    elif rid in {'road_debris','rockfall_on_road','slope_debris'}:
        rules=[(r'轮胎|\btire','loose tire'),(r'托盘|pallet','wooden pallet'),
               (r'纸箱|包装箱|cardboard','cardboard box'),(r'木板|木条|plank','wooden plank'),
               (r'金属杆|金属碎片|金属构件|金属部件|metal fragment','metal debris'),
               (r'混凝土|concrete','concrete rubble'),(r'树枝|枝条|branch','branch'),
               (r'树叶|叶片|leaves','leaf'),(r'石块|落石|岩石|rock','rock'),
               (r'标牌|路牌|标志牌|指示牌|traffic sign','traffic sign'),
               (r'护栏|隔离栏|barrier','metal barrier'),
               (r'碎片|残骸|杂物|垃圾|散落物|debris','debris')]
    else:
        return []
    return [concept for pattern,concept in rules if re.search(pattern,facts,re.I)][:6]


def restore_plans(payload, locked):
    """Prevent legacy normalization from inventing fallback tasks or overriding plans."""
    for row in payload['candidate_assessments']+payload.get('open_discoveries',[]):
        original=locked.get(row['risk_id'])
        if original:
            for key in ['sam3_tasks','relation_checks','mask_strategy','localization_plan_status','region_xyxy']:
                row[key]=original[key]
