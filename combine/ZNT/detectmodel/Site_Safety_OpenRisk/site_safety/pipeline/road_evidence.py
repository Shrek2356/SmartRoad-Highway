"""Road-specific evidence accounting, independent of construction/PPE guards."""
from site_safety.schemas import FinalRisk, SecondPassResponse


def reconcile_road_findings(first, report, evidences, minimum_confidence, threshold_overrides=None):
    """Preserve observations without promoting uncertain or unlocalized findings."""
    if first.assessment_quality.get('workflow_version') == 'road-concepts-v5':
        return reconcile_concept_findings(first, report, evidences, threshold_overrides or {})
    finals = {item.risk_id: item for item in report.final_risks}
    evidence_map = {item.risk_id: item for item in evidences}
    result = []
    for candidate in first.candidate_assessments + first.open_discoveries:
        if candidate.status not in {"present", "uncertain"}:
            continue
        if not (candidate.observed_facts or candidate.uncertainties):
            continue
        risk = finals.get(candidate.risk_id)
        if risk is None:
            risk = FinalRisk(risk_id=candidate.risk_id, risk_name_zh=candidate.risk_name_zh,
                             verified=False, confidence=candidate.confidence,
                             risk_description="；".join(candidate.observed_facts or candidate.uncertainties),
                             manual_review_required=True)
        evidence = evidence_map.get(candidate.risk_id)
        roles = {s.role for s in evidence.segmentations} if evidence else set()
        localization = "not_attempted" if evidence is None else (
            "missing" if not roles else "partial" if not {"subject", "hazard_source"} <= roles else "predicted")
        relations = evidence.relations if evidence else []
        relation_state = "passed" if relations and all(r.passed for r in relations) else "unresolved"
        reasons = []
        v4 = candidate.localization_plan_status != 'legacy'
        if v4 and candidate.localization_plan_status != 'planned':
            localization = 'not_attempted'
        if not v4 and candidate.confidence < minimum_confidence:
            reasons.append("候选低于定位阈值，保留观察与不确定性，未执行定位。")
        if v4 and localization == 'not_attempted':
            reasons.append("未执行定位，计划状态："+candidate.localization_plan_status)
        if v4 and risk.localization_verdict == 'inconsistent':
            reasons.append("视觉复核认为定位与目标不一致。")
        if v4 and risk.visual_verdict != 'supported':
            reasons.append("独立视觉复核未支持异常成立。")
        if localization in {"missing", "partial"}:
            reasons.append("道路或异常目标定位不足；不能据此否定原图观察。")
        if relation_state == "unresolved":
            reasons.append("道路影响尚未确定；关系核验失败不等于道路未受影响。")
        if not risk.verified:
            reasons.append("视觉复核未确认该风险。")
        risk.visible_evidence = list(dict.fromkeys(candidate.observed_facts + risk.visible_evidence))
        risk.counter_evidence = list(dict.fromkeys(candidate.counter_evidence + risk.counter_evidence))
        risk.uncertainties = list(dict.fromkeys(candidate.uncertainties + risk.uncertainties + reasons))
        if reasons or candidate.status == "uncertain":
            risk.verified = False
            risk.manual_review_required = True
        risk.evidence_state = {
            "observation": candidate.status,
            "localization": localization,
            "localization_quality": risk.localization_verdict if v4 else "not_independently_validated",
            "visual_verdict": risk.visual_verdict,
            "planning_status": candidate.localization_plan_status,
            "score_source": "review_model_uncalibrated" if v4 else "legacy_uncalibrated",
            "road_relation": relation_state,
            "road_impact": "supported" if risk.verified else "undetermined",
            "review_reasons": reasons,
            "confirmation_source": "machine_evidence" if risk.verified else "unconfirmed",
        }
        facts = "；".join(candidate.observed_facts or candidate.uncertainties)
        risk.risk_description = facts.rstrip("。； ") + "。" + ("自动证据支持，仍需业务复核。" if risk.verified else "结论尚待核实，未确认道路安全。")
        result.append(risk)
    quality = dict(first.assessment_quality)
    if quality:
        quality['result_status'] = ('pending_review' if result else 'unable_to_assess'
                                   if quality.get('visibility') != 'adequate' or quality.get('issues')
                                   else 'no_visible_anomaly')
    quality_text = " 存在可见性限制，需补充图像或人工核对。" if quality.get('issues') or quality.get('visibility') in {'limited','unassessable'} else ""
    return SecondPassResponse(overall_has_anomaly=any(r.verified for r in result), assessment_quality=quality,
        overall_summary=f"保留{len(result)}项道路观察，其中{sum(r.manual_review_required for r in result)}项需复核；未检出不等于道路安全。"+quality_text,
        final_risks=result)


def reconcile_concept_findings(first, report, evidences, thresholds):
    """Keep existence, mask quality, road impact and business review separate."""
    finals={r.risk_id:r for r in report.final_risks}
    evidence_map={e.risk_id:e for e in evidences}
    quality=dict(first.assessment_quality)
    dismissed=list(quality.get('dismissed_observations',[]))
    result=[]
    for candidate in first.candidate_assessments+first.open_discoveries:
        if candidate.status not in {'present','uncertain'}:
            continue
        risk=finals.get(candidate.risk_id) or FinalRisk(risk_id=candidate.risk_id,
            risk_name_zh=candidate.risk_name_zh,verified=False,confidence=0,
            risk_description='模型未返回该候选的复核结论。',manual_review_required=True)
        if risk.visual_verdict=='refuted' and risk.counter_evidence:
            dismissed.append(dict(risk.model_dump(),original_observation=candidate.model_dump(),
                                  disposition='refuted_after_review'))
            continue
        evidence=evidence_map.get(candidate.risk_id)
        targets=[s for s in evidence.segmentations if s.role=='hazard_source'] if evidence else []
        subjects=[s for s in evidence.segmentations if s.role=='subject'] if evidence else []
        planned={t.task_id for t in candidate.sam3_tasks if t.role=='hazard_source'}
        found={s.task_id for s in targets}
        location='missing' if not targets else 'partial' if planned-found else 'predicted'
        # Per-target relations are alternatives, not requirements that every object overlaps road.
        geometry=bool(evidence and any(r.passed for r in evidence.relations))
        impact=bool(risk.road_impact_verdict=='supported' or (geometry and risk.road_impact_verdict!='unrelated'))
        relation='passed' if geometry else 'visual_supported' if risk.road_impact_verdict=='supported' else 'unresolved'
        supported=(risk.visual_verdict=='supported' and risk.localization_verdict=='consistent'
                   and bool(targets) and impact and candidate.status=='present'
                   and candidate.localization_plan_status=='planned')
        reasons=[]
        if risk.visual_verdict!='supported': reasons.append('异常存在性尚无充分视觉支持。')
        if not targets: reasons.append('异常目标未定位，保留原图观察并优先补充定位。')
        elif planned-found: reasons.append('部分目标未定位，现有掩码不代表全部目标。')
        if risk.localization_verdict!='consistent': reasons.append('定位范围尚未获得一致性支持。')
        if not impact: reasons.append('道路影响待核实；与可见路面不重叠不能证明无影响。')
        if candidate.localization_plan_status!='planned': reasons.append('定位任务未完整执行：'+candidate.localization_plan_status)
        override=thresholds.get(candidate.risk_id,{})
        if supported and risk.confidence<float(override.get('min_verified_confidence',0)):
            supported=False;reasons.append('低于该风险经审批的自动确认下限。')
        risk.verified=supported
        risk.manual_review_required=True  # Lab output always requires business confirmation.
        risk.visible_evidence=list(dict.fromkeys(candidate.observed_facts+risk.visible_evidence))
        risk.uncertainties=list(dict.fromkeys(candidate.uncertainties+risk.uncertainties+reasons))
        risk.evidence_state=dict(observation=candidate.status,localization=location,
            localization_quality=risk.localization_verdict,visual_verdict=risk.visual_verdict,
            planning_status=candidate.localization_plan_status,road_relation=relation,
            road_impact='supported' if impact else 'undetermined',
            road_impact_source='geometry' if geometry else 'visual_review' if impact else 'unresolved',
            score_source='review_model_uncalibrated',review_reasons=reasons,
            confirmation_source='machine_evidence' if supported else 'unconfirmed',
            review_priority='high' if risk.visual_verdict=='supported' and candidate.risk_id in
                {'vehicle_fire','water_accumulation','road_collapse','road_obstruction'} else 'normal',
            requires_business_review=True)
        risk.risk_description=risk.risk_description.rstrip('。')+'。'+('自动证据支持，待业务复核。' if supported else '观察保留，待核实；不代表道路安全。')
        result.append(risk)
    quality['dismissed_observations']=dismissed
    quality['result_status']='pending_review' if result else ('unable_to_assess' if
        quality.get('visibility')!='adequate' or quality.get('issues') else 'no_visible_anomaly')
    quality['has_pending_observations']=any(not r.verified for r in result)
    confirmed=sum(r.verified for r in result)
    summary=(f'保留{len(result)}项观察：{confirmed}项自动证据支持，{len(result)-confirmed}项待判断；全部需业务复核。'
             if result else '本图未见可见异常；湿润反光本身不构成积水异常。' if quality['result_status']=='no_visible_anomaly'
             else '可见性不足，不能判断；需补充图像。')
    return SecondPassResponse(overall_has_anomaly=bool(confirmed),overall_summary=summary,
                              assessment_quality=quality,final_risks=result)
