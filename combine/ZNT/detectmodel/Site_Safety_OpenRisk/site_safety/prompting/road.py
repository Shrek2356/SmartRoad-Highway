"""Road-domain prompts; construction discovery/audit paths are not used."""
import json


def build_road_first_pass_prompt(candidate_risks, **kwargs):
    schema = {
        "scene_summary": "可见道路与拍摄视角",
        "has_possible_anomaly": True,
        "candidate_assessments": [{
            "risk_id": "目录ID", "risk_name_zh": "中文名称",
            "status": "present|absent|uncertain", "confidence": 0.0,
            "observed_facts": [], "counter_evidence": [],
            "sam3_tasks": [
                {"task_id": "唯一道路任务编号", "role": "subject", "prompt": "可见道路区域的英文描述", "expected_count": 1},
                {"task_id": "唯一目标任务编号", "role": "hazard_source", "prompt": "当前具体物体或表面的英文外观描述", "expected_count": 1}],
            "relation_checks": [{"type": "overlap", "subject_task_ids": ["唯一道路任务编号"],
                                  "object_task_ids": ["唯一目标任务编号"], "params": {}}],
            "mask_strategy": "object_only", "uncertainties": []}],
        "open_discoveries": []}
    return "\n".join([
        "分析道路图像，只依据像素可见证据，不参考文件名或目录名。",
        "先在scene_summary记录视角、道路可见性、遮挡和无数据区域；先写observed_facts再映射风险类别。不得为了匹配目录改变物体名称。",
        "修补或破损、泥沙或积水、路外停放或占道无法区分时，保留uncertain观察与备选解释；即使confidence为0也不要删除不确定性。模型分数不是校准概率。",
        "定位任务必须忠实对应观察：白色拖车定位white trailer，泥沙覆盖定位mud or sediment covering road。不得将具体车辆、树木或泥沙统称debris。",
        "淹水、泥沙覆盖、道路缺口可遮住道路本体；道路不可见时记录这一限制，不虚构道路区域。路侧异常与已经占道必须区分。",
        "逐项检查候选风险，仅输出有可见证据或需要复核的项目。存在候选词不代表风险成立。阴影、标线、修补痕迹不自动算病害。",
        "画质、遮挡或视角不足时标记uncertain。不能推断积水深度、坑槽尺寸、成因或通行安全。",
        "道路主体用subject任务，异常区域用hazard_source任务，检验异常是否与道路重叠。",
        "task_id必须在整份响应中唯一，例如water_accumulation_road和water_accumulation_hazard。定位提示应准确描述当前图中的可见实体，不机械复制示例debris。",
        "黑色拼接空洞和无数据区域不是路面塌陷；无法观察的区域应写入uncertainties。",
        "仅描述已提供的道路位置；图像像素位置不能当作GPS、桩号或车道定位。",
        "目录外明确可见风险可用open_开头ID；不得凭想象增加风险。"
        if kwargs.get("allow_open_discovery") else "不添加目录外风险。",
        "候选风险：" + json.dumps(candidate_risks, ensure_ascii=False),
        "输入说明：" + json.dumps(kwargs.get("image_manifest") or [], ensure_ascii=False),
        "严格输出以下结构JSON，替换示例值；无风险时has_possible_anomaly为false：",
        json.dumps(schema, ensure_ascii=False)])


def road_second_pass(prompt):
    evidence_and_schema = prompt.split("图片顺序与含义：", 1)[1]
    return "\n".join([
        "你是道路风险视觉复核助手。结合原始道路图像、定位叠加图和结构化证据复核。",
        "检查道路破损、覆盖物、障碍、积水、火情、事故及交通设施异常，不执行人员防护装备检查。",
        "SAM3掩码是模型预测，不是真值；道路主体未定位、遮挡或淹水时不能仅凭不重叠判定无风险。",
        "候选证据冲突或定位失败时保留该risk_id并标记manual_review_required，不把待核实写成道路安全。",
        "保留候选中的不确定性和反证；不编造病害成因、积水深度、桩号、通行能力或工程等级。",
        "黑色无数据区域不是道路缺口。未观察到风险不等于全图路况安全。非防护物缺失型风险的absence_status统一为not_applicable。",
        "图片顺序与含义：", evidence_and_schema])


def namespace_road_tasks(payload):
    """Repair cross-risk ID collisions while preserving each risk's relations."""
    risks=(payload.get('candidate_assessments') or [])+(payload.get('open_discoveries') or [])
    for index,risk in enumerate(risks):
        mapping={}
        for task_index,task in enumerate(risk.get('sam3_tasks') or []):
            old=task['task_id']
            if old in mapping:
                raise ValueError('Ambiguous duplicate task_id inside one risk')
            mapping[old]=f'r{index}_t{task_index}'
            task['task_id']=mapping[old]
        for relation in risk.get('relation_checks') or []:
            for field in ['subject_task_ids','object_task_ids']:
                relation[field]=[mapping[value] for value in relation.get(field,[])]


def build_road_review_prompt(evidences, image_manifest):
    """Standalone road review: never splice a construction prompt."""
    from site_safety.schemas import SecondPassResponse
    return "\n".join([
        "你是道路视觉证据复核助手。仅处理输入中的risk_id，不创建新发现。",
        "分别判断原图观察、定位掩码是否对应具体目标、道路影响是否有证据。SAM3预测不是标注真值。",
        "掩码大范围覆盖草地、建筑或无关区域时，说明定位不合理并转人工复核，不删除原始观察。",
        "必须填写visual_verdict为supported/refuted/uncertain，localization_verdict为consistent/inconsistent/unavailable/uncertain。没有掩码时为unavailable，不是consistent。",
        "对于积水和泥沙覆盖：道路可能被遮住；可见道路掩码缺失不能证明没有覆盖。",
        "本项目不将雨后湿润、反光或薄水膜作为积水异常。只有明确水体积聚、淹没道路、漫流或明显涉水才支持water_accumulation。若只是湿润或水膜，visual_verdict=refuted，并在counter_evidence写清理由，不要为了保留候选改为uncertain。",
        "必须填写road_impact_verdict：有像素证据表明异常占据行车区域或直接影响道路为supported；明确路外且无道路影响为unrelated；看不清为uncertain。淹水、塌陷会遮蔽道路，火焰和烟在道路上方，不能硬性要求目标掩码与可见路面相交。",
        "正常车辆与散落物共现不能支持traffic_collision；没有接触破损或侧翻直接迹象时应refuted。城市路口正常过街、正常排队不直接属于侵入或道路阻塞。",
        "检查每一种目标和所有实例，尤其是路面杂物与车辆正常轮胎是否混入。掩码未覆盖全部散落物、混入正常设施或湿路面时标为inconsistent，不得仅因部分匹配就写定位准确。",
        "对于道路缺口：检查边界和连续性，不能要求缺失区域仍有路面掩码。",
        "对于火情：区分火焰、烟雾、蒸汽、扬尘和灯光；对于事故：描述接触、破损或侧翻迹象，不能推断伤亡或责任。静态图不能证明抛锚、逆行、超速或持续违停。",
        "对于阻塞：区分物体存在与占道，保留路外停放的备选解释。对于损伤：区分修补、阴影与实际破损。",
        "无法判断时verified=false、manual_review_required=true；保留支持证据、反证和不确定性。absence_status为not_applicable。",
        "不推断水深、成因、承载能力、通行安全或工程等级。不要因目录命名而改写观察事实。",
        "图片顺序与含义：" + json.dumps(image_manifest, ensure_ascii=False),
        "候选证据（实例按概念汇总；完整实例与掩码保存在evidence.json，不能把代表框当作全部实例）：" + json.dumps(compact_road_evidence(evidences), ensure_ascii=False),
        "严格输出以下JSON Schema对应的对象：" + json.dumps(SecondPassResponse.model_json_schema(), ensure_ascii=False),
    ])


def compact_road_evidence(evidences):
    """Bound review context independently of the number of segmented objects."""
    compact=[]
    for evidence in evidences:
        row={k:evidence.get(k) for k in ['risk_id','risk_name_zh','first_pass_status','observed_facts',
             'counter_evidence','uncertainties','mask_strategy']}
        groups={}
        for item in evidence.get('segmentations',[]):
            key=(item['role'],item['prompt'])
            groups.setdefault(key,[]).append(item)
        row['concepts']=[]
        for (role,prompt),items in groups.items():
            largest=sorted(items,key=lambda x:(x['box_xyxy'][2]-x['box_xyxy'][0])*(x['box_xyxy'][3]-x['box_xyxy'][1]),reverse=True)
            row['concepts'].append(dict(role=role,prompt=prompt,instance_count=len(items),
                representative_boxes=[{'xyxy':[round(v) for v in x['box_xyxy']], 'score':round(x['score'],3)} for x in largest[:3]]))
        row['relations']=[dict(type=r['relation_type'],passed=r['passed'],score=round(r['score'],3))
                          for r in evidence.get('relations',[])]
        row['has_target_mask']=bool(evidence.get('risk_mask_path'))
        compact.append(row)
    return compact
