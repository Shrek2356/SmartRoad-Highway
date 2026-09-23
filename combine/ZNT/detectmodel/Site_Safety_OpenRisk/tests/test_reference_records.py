import copy
import json
import threading

from detect_bridge import DetectBridge
from site_safety.agents.knowledge_base import KnowledgeBase
from site_safety.agents.road_knowledge import ensure_road_knowledge, attach_road_references
from site_safety.agents.risk_reasoning import RiskReasoningAgent
from site_safety.agents.schemas import DetectionEvent, RiskFinding, TimeInfo, MediaInfo
from site_safety.road_domain import ROOT


def event_for(risk_id='pothole'):
    risk = RiskReasoningAgent(ROOT / 'examples/road_regulations.json').attach(RiskFinding(
        risk_id=risk_id, risk_name_zh='路面坑槽', verified=False, confidence=.8,
        risk_level='pending_review', risk_level_zh='待复核', visible_evidence=['右侧车道有坑洞']))
    return DetectionEvent(event_id='QA', data_mode='offline', time=TimeInfo(detected_at='unknown', reported_at='unknown'),
                          media=MediaInfo(image_path='input.png', image_width=100, image_height=100), risks=[risk])


def test_new_retrieval_records_exact_query_scope_and_artifact(tmp_path):
    kb = KnowledgeBase(ensure_road_knowledge(tmp_path/'kb'))
    event = event_for()
    before = copy.deepcopy(event.risks[0])
    attach_road_references(event, tmp_path, kb)
    risk = event.risks[0]
    trace = risk.knowledge_retrieval
    assert trace['query'] == ' '.join([before.risk_name_zh, before.risk_description, *before.visible_evidence])
    assert trace['searched_at'].endswith('+00:00')
    assert trace['status'] == 'matched' and trace['hit_count'] == 1
    assert [s['section'] for s in trace['allowed_sections']] == ['第三十条']
    assert risk.verified == before.verified and risk.confidence == before.confidence
    assert risk.visible_evidence == before.visible_evidence
    saved = json.loads((tmp_path/'regulatory_references.json').read_text(encoding='utf-8'))
    assert saved['retrievals']['pothole'] == trace
    assert saved['references']['pothole'] == risk.knowledge_references


def test_empty_and_unconfigured_retrievals_are_not_conflated(tmp_path):
    kb = KnowledgeBase(ensure_road_knowledge(tmp_path/'kb'))
    event = event_for('open_unknown')
    attach_road_references(event, tmp_path, kb)
    assert event.risks[0].knowledge_retrieval['status'] == 'not_configured'
    assert event.risks[0].knowledge_retrieval['searched_at'] is None
    for filename in kb.summary()['files']:
        kb.delete_document(filename)
    event = event_for()
    attach_road_references(event, tmp_path, kb)
    assert event.risks[0].knowledge_retrieval['status'] == 'no_verified_match'
    assert event.risks[0].knowledge_retrieval['searched_at']
    assert event.risks[0].knowledge_references == []


def test_historical_read_restores_only_saved_snapshot_without_modifying_archive_or_searching(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Viewing archives must not search the current knowledge base')
    monkeypatch.setattr(KnowledgeBase, 'search', forbidden)
    bridge = DetectBridge.__new__(DetectBridge)
    bridge.jobs_root, bridge.jobs, bridge.lock = tmp_path, {}, threading.Lock()
    folder = tmp_path/'JOB-ARCHIVE-QA'
    folder.mkdir()
    job = {'job_id': folder.name, 'status': 'done', 'source': 'archive', 'result': {'risks': [
        {'risk_id': 'water'}, {'risk_id': 'debris'}]}}
    payload = {'references': {'water': [{'section': '第三十条', 'retrieved_at': '2026-01-01'}],
                              'debris': [{'section': '第四十八条'}]}}
    (folder/'bridge_summary.json').write_text(json.dumps(job), encoding='utf-8')
    (folder/'regulatory_references.json').write_text(json.dumps(payload), encoding='utf-8')
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    for in_memory in (False, True):
        if in_memory: bridge.jobs[folder.name] = copy.deepcopy(job)
        result = bridge.get_job(folder.name)['result']
        assert result['reference_record_status'] == 'recorded'
        assert result['regulatory_references'].endswith('/media/regulatory_references.json')
        assert result['risks'][0]['knowledge_references'][0]['section'] == '第三十条'
        assert result['risks'][1]['knowledge_references'][0]['section'] == '第四十八条'
        assert result['risks'][0]['knowledge_retrieval'] == {}
    assert bridge.jobs[folder.name] == job
    assert before == {p.name: p.read_bytes() for p in folder.iterdir()}


def test_missing_or_broken_record_does_not_break_image_history(tmp_path):
    bridge = DetectBridge.__new__(DetectBridge)
    bridge.jobs_root, bridge.lock = tmp_path, threading.Lock()
    job = {'result': {'input_image': '/original.png', 'risks': []}}
    bridge.jobs = {'JOB-QA': job}
    assert bridge.get_job('JOB-QA')['result']['reference_record_status'] == 'unavailable'
    folder = tmp_path/'JOB-QA'; folder.mkdir()
    (folder/'regulatory_references.json').write_text('{broken', encoding='utf-8')
    result = bridge.get_job('JOB-QA')['result']
    assert result['reference_record_status'] == 'invalid'
    assert result['input_image'] == '/original.png'
    assert result['regulatory_references'] is None
