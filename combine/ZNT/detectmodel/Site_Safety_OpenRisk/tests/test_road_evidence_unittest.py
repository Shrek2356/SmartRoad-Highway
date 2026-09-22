import unittest
from site_safety.schemas import FirstPassResponse, SecondPassResponse, RiskEvidence
from site_safety.pipeline.road_evidence import reconcile_road_findings
from site_safety.prompting.road import build_road_review_prompt


class RoadEvidenceTests(unittest.TestCase):
    def test_low_confidence_observation_survives_without_localization(self):
        first = FirstPassResponse(scene_summary='road', has_possible_anomaly=True,
            candidate_assessments=[dict(risk_id='pothole',risk_name_zh='坑槽',status='uncertain',confidence=0,
                observed_facts=['边缘有碎石'],uncertainties=['无法区分修补与破损'])])
        report = SecondPassResponse(overall_has_anomaly=False,overall_summary='',final_risks=[])
        out = reconcile_road_findings(first,report,[],.25)
        self.assertEqual(len(out.final_risks),1)
        risk = out.final_risks[0]
        self.assertEqual(risk.confidence,0)
        self.assertFalse(risk.verified)
        self.assertTrue(risk.manual_review_required)
        self.assertIn('边缘有碎石',risk.visible_evidence)
        self.assertEqual(risk.evidence_state['localization'],'not_attempted')

    def test_missing_masks_do_not_erase_flood_observation(self):
        first = FirstPassResponse(scene_summary='road',has_possible_anomaly=True,
            candidate_assessments=[dict(risk_id='water_accumulation',risk_name_zh='积水',status='present',confidence=.95,observed_facts=['道路被水覆盖'])])
        evidence = RiskEvidence(risk_id='water_accumulation',risk_name_zh='积水',first_pass_status='present',first_pass_confidence=.95,observed_facts=['道路被水覆盖'],segmentations=[],relations=[],mask_strategy='object_only',evidence_score=0)
        report = SecondPassResponse(overall_has_anomaly=False,overall_summary='',final_risks=[])
        risk = reconcile_road_findings(first,report,[evidence],.25).final_risks[0]
        self.assertEqual(risk.visible_evidence,['道路被水覆盖'])
        self.assertFalse(risk.verified)
        self.assertEqual(risk.evidence_state['road_impact'],'undetermined')

    def test_standalone_review_has_no_construction_instruction(self):
        prompt=build_road_review_prompt([],['original road image'])
        for value in ['工地','施工','安全帽','腰背']:
            self.assertNotIn(value,prompt)
        self.assertIn('泥沙',prompt)
        self.assertIn('路外停放',prompt)


if __name__ == '__main__':
    unittest.main()
