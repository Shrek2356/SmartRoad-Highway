import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from site_safety.pipeline.road_workflow import compile_observations, apply_plans
from site_safety.factory import build_inspector
from site_safety.utils.config import load_yaml
from site_safety.agents.event_builder import build_event_from_output_dir
from site_safety.agents.risk_reasoning import RiskReasoningAgent

ROOT=Path(__file__).resolve().parents[1]
CAT=[{'risk_id':'road_obstruction','name_zh':'道路阻塞'}]


class QueueModel:
    def __init__(self, answers): self.answers=iter(answers);self.prompts=[]
    def generate_json(self, images, prompt):
        self.prompts.append(prompt)
        return json.dumps(next(self.answers),ensure_ascii=False)


class NoMasks:
    def __init__(self): self.calls=[]
    def set_image(self,image): pass
    def segment(self,task): self.calls.append(task);return []


class RoadWorkflowTests(unittest.TestCase):
    def test_quality_only_does_not_become_collapse(self):
        payload=compile_observations({'scene_summary':'遮挡','visibility':'unassessable','quality_issues':['无数据'],
            'observations':[{'risk_id':'road_collapse','risk_name_zh':'塌方','status':'uncertain','observed_facts':[],
                             'uncertainties':['看不清道路']}]},CAT)
        self.assertEqual(payload['candidate_assessments'],[])
        self.assertIn('看不清道路',payload['assessment_quality']['issues'])

    def test_planner_cannot_invent_risk(self):
        payload={'candidate_assessments':[]}
        with self.assertRaises(ValueError):
            apply_plans(payload,{'plans':[{'risk_id':'invented','road_prompt':'road','target_prompt':'car'}]})

    def test_multiple_objects_share_risk_without_losing_tasks(self):
        payload=compile_observations({'scene_summary':'占道','observations':[{'risk_id':'road_obstruction',
            'risk_name_zh':'道路阻塞','status':'present','observed_facts':['拖车与轿车位于路面']}]},CAT)
        apply_plans(payload,{'plans':[{'risk_id':'road_obstruction','road_prompt':'road','target_prompt':t}
                                     for t in ['white trailer','white car','white car']]})
        row=payload['candidate_assessments'][0]
        self.assertEqual(len(row['sam3_tasks']),3)
        self.assertEqual(len(row['relation_checks']),2)
        self.assertEqual(len({t['task_id'] for t in row['sam3_tasks']}),3)

    def test_zero_score_with_facts_reaches_segmentation_and_review(self):
        observation={'scene_summary':'道路有拖车','visibility':'adequate','quality_issues':[],
            'observations':[{'risk_id':'road_obstruction','risk_name_zh':'道路阻塞','status':'uncertain',
                'observed_facts':['白色拖车靠近道路中心'],'uncertainties':['是否侵入道路需核对'],
                'region_xyxy':[.2,.2,.8,.8]}]}
        plan={'plans':[{'risk_id':'road_obstruction','road_prompt':'road surface','target_prompt':'white trailer'}]}
        review={'overall_has_anomaly':False,'overall_summary':'待核实','final_risks':[{
            'risk_id':'road_obstruction','risk_name_zh':'道路阻塞','verified':False,'confidence':.2,
            'risk_description':'疑似占道','manual_review_required':True,'visual_verdict':'uncertain',
            'localization_verdict':'unavailable'}]}
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);source=base/'input.png';Image.new('RGB',(96,96),'gray').save(source)
            cfg=load_yaml(ROOT/'configs/road_demo.yaml')
            cfg['pipeline'].update(road_observation_planning=True,second_pass_per_risk=True)
            inspector=build_inspector(cfg,ROOT);inspector.mllm=QueueModel([observation,plan,review]);inspector.sam3=NoMasks()
            result=inspector.inspect(source,base/'run')
            self.assertEqual(len(inspector.sam3.calls),2)
            self.assertEqual(inspector.sam3.calls[1].prompt,'white trailer')
            self.assertEqual(len(inspector.mllm.prompts),3)
            self.assertEqual(result.first_pass.candidate_assessments[0].confidence,0)
            self.assertEqual(result.visual_verification.final_risks[0].evidence_state['localization'],'missing')
            self.assertTrue((base/'run/review_region_road_obstruction.png').exists())
            self.assertTrue((base/'run/issue_report.md').exists())
            event=build_event_from_output_dir(base/'run',RiskReasoningAgent(ROOT/'examples/road_regulations.json'))
            self.assertEqual(event.assessment_quality['visibility'],'adequate')
            self.assertTrue(event.risks[0].manual_review_required)

    def test_unassessable_pipeline_outputs_quality_report_without_fake_risk(self):
        observation={'scene_summary':'不可见','visibility':'unassessable','quality_issues':['黑色无数据'], 'observations':[]}
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);source=base/'input.png';Image.new('RGB',(48,48),'black').save(source)
            cfg=load_yaml(ROOT/'configs/road_demo.yaml');cfg['pipeline'].update(road_observation_planning=True,second_pass_per_risk=True)
            inspector=build_inspector(cfg,ROOT);inspector.mllm=QueueModel([observation]);inspector.sam3=NoMasks()
            result=inspector.inspect(source,base/'run')
            self.assertEqual(result.visual_verification.final_risks,[])
            self.assertEqual(result.visual_verification.assessment_quality['result_status'],'unable_to_assess')
            self.assertEqual(inspector.sam3.calls,[])
            self.assertIn('黑色无数据',(base/'run/issue_report.md').read_text(encoding='utf-8'))
            event=build_event_from_output_dir(base/'run',RiskReasoningAgent(ROOT/'examples/road_regulations.json'))
            from app_server import Database, AppState
            db=Database(base/'quality.db')
            try:
                state=AppState(db,base/'data');state.ingest_event(event.model_dump())
                restored=state.events()[0]
                self.assertEqual(restored.assessment_quality['result_status'],'unable_to_assess')
                self.assertEqual(restored.risks,[])
                self.assertEqual(db.count('work_order'),0)
            finally: db.conn.close()

    def test_planner_failure_is_bounded_and_observation_still_reviewed(self):
        observation={'scene_summary':'拖车','visibility':'adequate','observations':[{
            'risk_id':'road_obstruction','risk_name_zh':'道路阻塞','status':'uncertain','observed_facts':['白色拖车靠近道路']}]}
        bad={'plans':[{'risk_id':'invented','road_prompt':'road','target_prompt':'car'}]}
        review={'overall_has_anomaly':False,'overall_summary':'待核对','final_risks':[{
            'risk_id':'road_obstruction','risk_name_zh':'道路阻塞','verified':False,'confidence':0,
            'risk_description':'待核对','manual_review_required':True}]}
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);source=base/'input.png';Image.new('RGB',(48,48),'gray').save(source)
            cfg=load_yaml(ROOT/'configs/road_demo.yaml');cfg['pipeline'].update(road_observation_planning=True,second_pass_per_risk=True)
            inspector=build_inspector(cfg,ROOT);inspector.mllm=QueueModel([observation,bad,bad,review]);inspector.sam3=NoMasks()
            result=inspector.inspect(source,base/'run')
            self.assertEqual(len(inspector.mllm.prompts),4)
            self.assertEqual(inspector.sam3.calls,[])
            self.assertEqual(result.visual_verification.final_risks[0].evidence_state['planning_status'],'planner_failed')
            self.assertIn('白色拖车靠近道路',result.visual_verification.final_risks[0].visible_evidence)


if __name__=='__main__': unittest.main()
