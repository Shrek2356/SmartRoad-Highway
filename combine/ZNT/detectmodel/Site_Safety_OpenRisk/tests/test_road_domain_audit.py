import copy
import json
from pathlib import Path

import pytest

from site_safety.agents.knowledge_base import KnowledgeBase
from site_safety.agents.road_knowledge import ensure_road_knowledge, attach_road_references
from site_safety.agents.risk_reasoning import RiskReasoningAgent
from site_safety.agents.review_learning import ReviewLearningAgent
from site_safety.agents.response import CollaborativeResponseAgent
from site_safety.agents.schemas import DetectionEvent, RiskFinding, TimeInfo, MediaInfo
from site_safety.factory import build_inspector
from site_safety.pipeline.road_workflow import compile_observations
from site_safety.road_domain import ROOT, validate_road_config, build_road_management_prompt
from site_safety.runtime_settings import apply_runtime_settings, load_runtime_settings
from site_safety.utils.config import load_yaml


def make_event(risk_id='pothole'):
    agent = RiskReasoningAgent(ROOT / 'examples/road_regulations.json')
    risk = agent.attach(RiskFinding(risk_id=risk_id, risk_name_zh='路面坑槽', verified=True,
                                   confidence=.91, risk_level='general', risk_level_zh='一般风险',
                                   visible_evidence=['画面右下道路有坑洞']))
    return DetectionEvent(event_id='TEST', data_mode='offline', time=TimeInfo(detected_at='unknown', reported_at='unknown'),
                          media=MediaInfo(image_path='test.png', image_width=100, image_height=100), risks=[risk],
                          assessment_quality={'visibility':'limited','issues':['远景不可判断']})


@pytest.mark.parametrize('override', [
    {'two_stage_open_discovery':True}, {'compact_open_discovery':True},
    {'person_precheck':{'enabled':True}}, {'structured_risk_audit':{'enabled':True}},
])
def test_legacy_pipeline_cannot_enter_road_profile(override):
    cfg = load_yaml(ROOT / 'configs/road_offline.yaml')
    cfg['pipeline'].update(override)
    with pytest.raises(ValueError):
        validate_road_config(cfg, ROOT)


def test_factory_rejects_legacy_default_before_loading_models():
    with pytest.raises(ValueError, match='历史工地配置'):
        build_inspector(load_yaml(ROOT / 'configs/default.yaml'), ROOT)


def test_legacy_runtime_weights_cannot_reactivate_screening(tmp_path):
    config = load_yaml(ROOT / 'configs/road_offline.yaml')
    settings = load_runtime_settings(tmp_path/'missing.json')
    settings.update(yolo_enabled=True, yolo_construction_weights_path='old.pt')
    updated = apply_runtime_settings(config, settings)
    assert updated['screening']['models'] == []
    assert updated['screening']['enabled'] is False


def test_open_id_cannot_smuggle_helmet_into_road_workflow():
    compiled = compile_observations({'scene_summary':'road','observations':[
        {'risk_id':'open_missing_helmet','risk_name_zh':'helmet','status':'present','observed_facts':['person visible']}
    ]}, [])
    assert compiled['candidate_assessments'] == []
    assert compiled['assessment_quality']['issues']


def test_seed_real_law_search_and_deleted_source_is_not_reinstalled(tmp_path):
    kb = KnowledgeBase(ensure_road_knowledge(tmp_path))
    assert kb.summary()['chunk_count'] == 10
    hits = kb.search('道路出现坍塌、坑漕、水毁、隆起等损毁', top_k=1)
    assert hits[0]['section'] == '第三十条'
    assert hits[0]['provenance_status'] == 'verified_checksum'
    assert hits[0]['source_url'].startswith('https://www.beijing.gov.cn/')
    assert '2021' in hits[0]['version']
    kb.delete_document(hits[0]['source_file'])
    ensure_road_knowledge(tmp_path)
    assert KnowledgeBase(tmp_path).summary()['chunk_count'] == 0


def test_report_uses_scoped_reference_without_changing_vision(tmp_path):
    kb = KnowledgeBase(ensure_road_knowledge(tmp_path/'kb'))
    event = make_event()
    before = event.risks[0].model_dump()
    (tmp_path/'issue_report.json').write_text('{}', encoding='utf-8')
    (tmp_path/'issue_report.md').write_text('# 道路图像问题报告', encoding='utf-8')
    attach_road_references(event, tmp_path, kb)
    refs = event.risks[0].knowledge_references
    assert [r['section'] for r in refs] == ['第三十条']
    assert event.risks[0].verified == before['verified']
    assert event.risks[0].visible_evidence == before['visible_evidence']
    assert event.risks[0].risk_level == 'pending_review'
    attach_road_references(event, tmp_path, kb)
    report = (tmp_path/'issue_report.md').read_text(encoding='utf-8')
    assert report.count('<!-- road-regulatory-references -->') == 1
    assert '不构成违法认定' in report and 'beijing.gov.cn' in report
    stored = json.loads((tmp_path/'issue_report.json').read_text(encoding='utf-8'))
    assert stored['regulatory_references']['references']['pothole']


def test_source_replacement_revokes_verified_citations(tmp_path):
    kb = KnowledgeBase(ensure_road_knowledge(tmp_path/'kb'))
    filename = kb.summary()['files'][0]
    kb.import_document(filename, '## 第三十条\n\n这是一份替换后的未经核验材料，不是官方法规。'.encode())
    assert kb.summary()['documents'][0]['provenance_status'] == 'checksum_mismatch'
    event = make_event()
    attach_road_references(event, tmp_path, kb)
    assert event.risks[0].knowledge_references == []
    assert event.risks[0].regulations == []


def test_unknown_open_risk_does_not_get_random_legal_clause(tmp_path):
    kb = KnowledgeBase(ensure_road_knowledge(tmp_path/'kb'))
    event = make_event('open_unclassified')
    attach_road_references(event, tmp_path, kb)
    assert event.risks[0].knowledge_references == []


def test_road_learning_distinguishes_machine_and_human_verdict(tmp_path):
    event = make_event()
    learning = ReviewLearningAgent(tmp_path/'cases.jsonl', domain='road')
    text = learning.generate_briefing([event])
    assert '暂无人工确认记录' in text and '路面坑槽：1次' in text
    assert '安全帽' not in text and '吊装' not in text
    learning.ingest_confirmation(event, 'pothole', 'confirmed', reviewer='tester')
    text = learning.generate_briefing([event])
    assert '暂无待复核候选' in text
    response = CollaborativeResponseAgent(domain='road')
    assert response.notify_targets['critical'][0] == 'traffic_control_center'
    orders, confirmations = response.process_event(make_event())
    assert not orders and len(confirmations) == 1


def test_report_prompt_is_road_scoped_and_freezes_evidence():
    prompt = build_road_management_prompt({}, [])
    assert '道路巡检问题报告' in prompt and 'assessment_quality' in prompt
    assert '施工安全' not in prompt


def test_business_rejects_legacy_ingest_and_threshold(tmp_path):
    from fastapi.testclient import TestClient
    import app_server
    database = app_server.Database(tmp_path/'business.db')
    database.seed_users()
    old_state = app_server.STATE
    try:
        app_server.STATE = app_server.AppState(database, tmp_path)
        client = TestClient(app_server.app)
        login = client.post('/api/auth/login', json={'username':'admin','password':'admin123'}).json()
        headers = {'Authorization':'Bearer '+login['token']}
        event = make_event().model_dump()
        event['risks'][0]['risk_id'] = 'missing_helmet'
        assert client.post('/api/internal/ingest/event', json=event,
                           headers={'X-Internal-Key':app_server.INTERNAL_KEY}).status_code == 422
        assert database.count('event') == 0
        assert client.put('/api/model/threshold', json={'key':'missing_helmet','value':.8}, headers=headers).status_code == 422
    finally:
        app_server.STATE = old_state
        database.conn.close()


def test_agent_defaults_are_road_scoped(tmp_path):
    assert CollaborativeResponseAgent().domain == 'road'
    assert '道路值班风险提示' in ReviewLearningAgent(tmp_path/'cases.jsonl').generate_briefing([])


def test_repeated_review_does_not_inflate_false_alarm_sample_count(tmp_path):
    agent = ReviewLearningAgent(tmp_path/'cases.jsonl')
    event = make_event()
    agent.ingest_confirmation(event, 'pothole', 'rejected', reviewer='tester')
    agent.ingest_confirmation(event, 'pothole', 'confirmed', reviewer='tester')
    stat = agent.false_alarm_stats()['pothole']
    assert stat['model_verified_count'] == 1
    assert stat['human_rejected_count'] == 0
    assert agent.build_threshold_proposals() == []
