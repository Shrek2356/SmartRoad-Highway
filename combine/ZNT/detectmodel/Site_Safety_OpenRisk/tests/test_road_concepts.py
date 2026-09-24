import tempfile
from pathlib import Path
import numpy as np
import pytest
from PIL import Image
from site_safety.adapters.base import MaskInstance
from site_safety.pipeline.road_workflow import compile_observations,apply_plans
from site_safety.pipeline.road_concepts import execute_road_concepts,write_scene_annotation
from site_safety.pipeline.road_evidence import reconcile_road_findings
from site_safety.schemas import FirstPassResponse,SecondPassResponse,FinalRisk,RiskEvidence,SegmentationRecord

CAT=[{'risk_id':'water_accumulation','name_zh':'积水'},{'risk_id':'road_debris','name_zh':'散落物'}]

def test_normal_scene_fills_only_segmented_pixels(tmp_path):
    from types import SimpleNamespace
    mask=np.zeros((180,200),dtype=np.uint8)
    mask[80:170,20:180]=1
    mask[100:150,70:130]=0
    report=SimpleNamespace(assessment_quality={'result_status':'no_visible_anomaly'})
    write_scene_annotation(Image.new('RGB',(200,180)),tmp_path,report,
        {'context_road':[SimpleNamespace(mask=mask)]},[SimpleNamespace(task_id='context_road')])
    rendered=np.array(Image.open(tmp_path/'scene_annotation.png'))
    assert rendered[130,40,1]>0
    assert not rendered[130,100].any()  # Hole stays unfilled: not a rectangle mask.
    assert np.array_equal(np.array(Image.open(tmp_path/'scene_mask_road.png'))>0,mask>0)
def payload(state='wet_only',water=None):
    return compile_observations(dict(scene_summary='道路',visibility='adequate',road_surface_state=state,
        water_evidence=water or [],scene_elements=['road'], observations=[dict(risk_id='water_accumulation',
        risk_name_zh='积水',status='present',observed_facts=['反光'])]),CAT,concept_mode=True)

def test_wet_only_is_context_but_flood_is_not_suppressed():
    dry=payload();assert dry['candidate_assessments']==[]
    assert dry['assessment_quality']['dismissed_observations'][0]['disposition']=='weather_only'
    wet=payload('flooded',['浑浊水体覆盖车道'])
    assert len(wet['candidate_assessments'])==1
    contradictory=payload('wet_only',['水体覆盖车道'])
    assert len(contradictory['candidate_assessments'])==1

def test_atomic_multi_targets_no_four_instance_truncation():
    p=payload('flooded',['水体']);rid='water_accumulation'
    with pytest.raises(ValueError):
        apply_plans(p,{'plans':[dict(risk_id=rid,road_prompt='road',target_prompt='tires and debris covering road')]})
    apply_plans(p,{'plans':[dict(risk_id=rid,road_prompt='wet highway in rain',target_prompt=x)
                            for x in ['water','floodwater','muddy water']]})
    row=p['candidate_assessments'][0]
    assert len(row['sam3_tasks'])==4
    assert row['sam3_tasks'][0]['prompt']=='road'
    assert all(t['expected_count']==128 for t in row['sam3_tasks'][1:])

class Segmenter:
    def __init__(self): self.calls=[]
    def segment(self,task):
        self.calls.append(task.prompt)
        return [MaskInstance(task.task_id,task.role,task.prompt,.8,np.ones((16,16),dtype=np.uint8),[0,0,16,16])]

def test_cache_rebinds_ids_and_roles_and_reports_budget_failure(tmp_path):
    p=payload('flooded',['水体'])
    apply_plans(p,{'plans':[dict(risk_id='water_accumulation',road_prompt='road',target_prompt='water')]})
    risk=FirstPassResponse.model_validate(p).candidate_assessments[0]
    sam=Segmenter();by,context=execute_road_concepts(sam,[risk],['road'],tmp_path,.2)
    assert sam.calls==['road','water']
    assert by['context_road'][0].task_id=='context_road' and by['context_road'][0].role=='region'
    assert by['p0_road'][0].role=='subject'
    sam=Segmenter();execute_road_concepts(sam,[risk],[],tmp_path,.2,max_tasks=1)
    assert risk.localization_plan_status=='partial_execution'

def test_refuted_wet_is_not_retained_as_alarm_and_green_needs_road_mask(tmp_path):
    p=payload('uncertain');apply_plans(p,{'plans':[dict(risk_id='water_accumulation',road_prompt='road',target_prompt='water')]})
    first=FirstPassResponse.model_validate(p)
    review=SecondPassResponse(overall_has_anomaly=False,overall_summary='',final_risks=[FinalRisk(
        risk_id='water_accumulation',risk_name_zh='积水',verified=False,confidence=.5,
        visual_verdict='refuted',counter_evidence=['只有湿润反光'],risk_description='湿路面')])
    result=reconcile_road_findings(first,review,[],.25)
    assert not result.final_risks and result.assessment_quality['result_status']=='no_visible_anomaly'
    sam=Segmenter();by,ctx=execute_road_concepts(sam,[],['road'],tmp_path,.2)
    write_scene_annotation(Image.new('RGB',(16,16)),tmp_path,result,by,ctx)
    assert result.assessment_quality['normal_road_box']
    result.assessment_quality['result_status']='pending_review'
    write_scene_annotation(Image.new('RGB',(16,16)),tmp_path,result,by,ctx)
    assert not result.assessment_quality['normal_road_box']

def test_refutation_without_counterevidence_stays_uncertain():
    p=payload('flooded',['浑浊水体'])
    first=FirstPassResponse.model_validate(p)
    review=SecondPassResponse(overall_has_anomaly=False,overall_summary='',final_risks=[FinalRisk(
        risk_id='water_accumulation',risk_name_zh='积水',verified=False,confidence=.3,
        visual_verdict='refuted',risk_description='未说明')])
    result=reconcile_road_findings(first,review,[],.25)
    assert len(result.final_risks)==1 and result.assessment_quality['result_status']=='pending_review'

def test_flood_can_occlude_road_without_synthetic_overlap():
    p=payload('flooded',['浑浊水体横跨车道']);apply_plans(p,{'plans':[dict(risk_id='water_accumulation',road_prompt='road',target_prompt='water')]})
    first=FirstPassResponse.model_validate(p)
    ev=RiskEvidence(risk_id='water_accumulation',risk_name_zh='积水',first_pass_status='present',
        first_pass_confidence=0,observed_facts=['水体'],relations=[],mask_strategy='object_only',evidence_score=.5,
        segmentations=[SegmentationRecord(task_id='p0_target0',role='hazard_source',prompt='water',
        instance_index=0,score=.8,box_xyxy=[0,0,8,8],mask_path='real.png')])
    review=SecondPassResponse(overall_has_anomaly=True,overall_summary='',final_risks=[FinalRisk(
        risk_id='water_accumulation',risk_name_zh='积水',verified=True,confidence=.8,
        visual_verdict='supported',localization_verdict='consistent',road_impact_verdict='supported',risk_description='淹水')])
    result=reconcile_road_findings(first,review,[ev],.25)
    assert result.final_risks[0].verified
    assert result.final_risks[0].evidence_state['road_relation']=='visual_supported'
    assert result.final_risks[0].manual_review_required
    result=reconcile_road_findings(first,review,[ev],.25,threshold_overrides={'water_accumulation':{'min_verified_confidence':.9}})
    assert not result.final_risks[0].verified

def test_review_prompt_is_bounded_for_hundreds_of_instances():
    import json
    from site_safety.prompting.road import compact_road_evidence
    evidence=dict(risk_id='road_debris',segmentations=[dict(role='hazard_source',prompt='debris',
        score=.7,box_xyxy=[1,2,10,20],mask_path=f'entity_{i}.png') for i in range(500)],relations=[])
    packed=compact_road_evidence([evidence])
    assert len(json.dumps(packed))<1500
    assert packed[0]['concepts'][0]['instance_count']==500
    assert len(packed[0]['concepts'][0]['representative_boxes'])==3

def test_frontend_never_assigns_another_risks_mask(tmp_path):
    from detect_bridge import DetectBridge
    from types import SimpleNamespace
    (tmp_path/'overlay_road_debris.png').write_bytes(b'fixture')
    (tmp_path/'risk_mask_road_debris.png').write_bytes(b'fixture')
    (tmp_path/'overlay_water_accumulation.png').write_bytes(b'dismissed fixture')
    (tmp_path/'scene_annotation.png').write_bytes(b'context fixture')
    bridge=object.__new__(DetectBridge)
    event={'risks':[{'risk_id':'traffic_collision'},{'risk_id':'road_debris'}]}
    result=bridge._build_frontend_result({'job_id':'test','image_name':'input.png'},tmp_path,SimpleNamespace(),event)
    assert result['risks'][0]['overlay'] is None
    assert result['risks'][1]['overlay'].endswith('/overlay_road_debris.png')
    assert len(result['overlays'])==1
    assert result['scene_annotation'].endswith('/scene_annotation.png')

def test_known_concepts_are_grounded_in_observation_not_planner_scene_hallucination():
    from site_safety.pipeline.road_workflow import grounded_target_concepts
    assert grounded_target_concepts({'risk_id':'road_debris','observed_facts':['轮胎与金属杆件散落路面']})==['loose tire','metal debris']
    assert grounded_target_concepts({'risk_id':'vehicle_fire','observed_facts':['车辆附近有明火和浓烟']})==['flame','smoke']
    p=compile_observations(dict(scene_summary='散落物',visibility='adequate',observations=[dict(
        risk_id='road_debris',risk_name_zh='杂物',status='present',observed_facts=['轮胎与金属碎片'])]),CAT,concept_mode=True)
    apply_plans(p,{'plans':[dict(risk_id='road_debris',road_prompt='road',target_prompt='traffic sign')]})
    prompts=[t['prompt'] for t in p['candidate_assessments'][0]['sam3_tasks']]
    assert 'traffic sign' not in prompts and 'loose tire' in prompts
    assert p['assessment_quality']['concept_compilation'][0]['planner_proposals']==['traffic sign']
