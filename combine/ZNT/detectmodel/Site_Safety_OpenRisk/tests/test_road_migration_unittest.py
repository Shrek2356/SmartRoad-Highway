"""Software checks using synthetic pixels only; not a CRASAR benchmark."""
import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from site_safety.factory import build_inspector
from site_safety.utils.config import load_yaml
from site_safety.agents.risk_reasoning import RiskReasoningAgent
from site_safety.agents.event_builder import build_event_from_output_dir
from site_safety.agents.schemas import RiskFinding
from site_safety.prompting.road import build_road_first_pass_prompt

ROOT = Path(__file__).resolve().parents[1]

class RoadMigrationTests(unittest.TestCase):
    def test_duplicate_ids_across_risks_keep_local_relations(self):
        from site_safety.prompting.road import namespace_road_tasks
        from copy import deepcopy
        risk={'sam3_tasks':[{'task_id':'road'},{'task_id':'hazard'}],
              'relation_checks':[{'subject_task_ids':['road'],'object_task_ids':['hazard']}]}
        payload={'candidate_assessments':[deepcopy(risk),deepcopy(risk)]}
        namespace_road_tasks(payload)
        first,second=payload['candidate_assessments']
        self.assertNotEqual(first['sam3_tasks'][0]['task_id'],second['sam3_tasks'][0]['task_id'])
        self.assertEqual(second['relation_checks'][0]['subject_task_ids'],[second['sam3_tasks'][0]['task_id']])

    def test_road_normalization_does_not_invent_confidence_or_duplicate_tasks(self):
        from site_safety.pipeline.orchestrator import TrainingFreeInspector
        from site_safety.risk_operators import load_risk_operator_registry
        payload={'candidate_assessments':[{'risk_id':'road_debris','status':'present','confidence':0.1,
            'sam3_tasks':[{'task_id':'r','role':'subject','prompt':'road surface','expected_count':1},
                          {'task_id':'o','role':'hazard_source','prompt':'white trailer','expected_count':1}]}]}
        TrainingFreeInspector._normalize_first_pass_payload(payload,[],
            load_risk_operator_registry(ROOT/'configs/road_risk_operators.yaml'),preserve_confidence=True)
        item=payload['candidate_assessments'][0]
        self.assertEqual(item['confidence'],0.1)
        self.assertEqual(len(item['sam3_tasks']),2)
        self.assertEqual(item['sam3_tasks'][1]['prompt'],'white trailer')
        self.assertEqual(item['relation_checks'][0]['subject_task_ids'],['r'])

    def test_road_second_pass_removes_construction_checklist(self):
        from site_safety.prompting.second_pass import build_second_pass_prompt
        from site_safety.prompting.road import road_second_pass
        prompt=road_second_pass(build_second_pass_prompt([]))
        self.assertNotIn('腰背部',prompt)
        self.assertNotIn('confirmed_absent：',prompt)
        self.assertIn('道路',prompt)

    def test_manual_review_precedes_verified(self):
        agent = RiskReasoningAgent(ROOT/'examples/road_regulations.json')
        self.assertEqual(agent.assess_level(risk_id='road_debris',verified=True,
                         confidence=.99,manual_review_required=True), 'pending_review')

    def test_profiles_and_prompts_are_road_only(self):
        from detect_profiles import resolve_config
        from detect_bridge import _profile_from_legacy_config
        for profile in ['demo','offline','standard']:
            cfg = load_yaml(resolve_config(profile))
            self.assertEqual(cfg['domain'],'road')
            self.assertFalse(cfg['screening']['enabled'])
            self.assertEqual(cfg['screening']['models'],[])
            self.assertEqual(_profile_from_legacy_config(resolve_config(profile).name),profile)
        prompt = build_road_first_pass_prompt([],allow_open_discovery=True)
        self.assertNotIn('安全帽',prompt)
        self.assertIn('candidate_assessments',prompt)

    def test_synthetic_pipeline_storage_roundtrip(self):
        from app_server import Database, AppState
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base/'synthetic.png'
            Image.new('RGB',(128,96),(120,120,120)).save(source)
            inspector = build_inspector(load_yaml(ROOT/'configs/road_demo.yaml'),ROOT)
            inspector.inspect(source,base/'run')
            agent = RiskReasoningAgent(ROOT/'examples/road_regulations.json')
            event = build_event_from_output_dir(base/'run',agent,config_name='road_demo.yaml')
            self.assertIsNotNone(event)
            self.assertTrue(event.risks)
            self.assertTrue(all(r.risk_id == 'road_debris' for r in event.risks))
            self.assertTrue(all(r.manual_review_required for r in event.risks))
            # A context entity's large box must not enlarge the reported risk area.
            evidence=json.loads((base/'run/evidence.json').read_text(encoding='utf-8'))
            if evidence and evidence[0].get('risk_mask_path'):
                from PIL import ImageDraw
                mask=Image.new('L',(128,96),0)
                ImageDraw.Draw(mask).rectangle((20,30,39,49),fill=255)
                mask.save(base/'run'/evidence[0]['risk_mask_path'])
                rebuilt=build_event_from_output_dir(base/'run',agent)
                self.assertEqual(rebuilt.risks[0].geometry.bbox_xyxy,[20,30,40,50])
            event.device.road_context.road_name='合成测试道路'
            event.risks[0].knowledge_references=[{'source_file':'synthetic','text':'test reference'}]
            db=Database(base/'data/test.db')
            try:
                state=AppState(db,base/'data')
                self.assertIsNone(state.gateway.webhook_url)
                state.ingest_event(event.model_dump())
                restored=state.events()[0]
                self.assertEqual(restored.device.road_context.road_name,'合成测试道路')
                self.assertEqual(restored.risks[0].knowledge_references,event.risks[0].knowledge_references)
                self.assertEqual(db.count('work_order'),0)
            finally:
                db.conn.close()

if __name__ == '__main__':
    unittest.main()
