"""Regression checks for the 1.1 desktop/productization fixes (no model weights)."""
import json
import queue
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from detect_bridge import DetectBridge, create_app
from site_safety.agents.knowledge_base import KnowledgeBase
from site_safety.qwen_service import QwenServiceManager


def test_failed_same_name_import_preserves_document_and_search(tmp_path):
    kb = KnowledgeBase(tmp_path)
    client = TestClient(create_app(SimpleNamespace(knowledge_base=kb)))
    text = '第一条 高处作业必须连接安全绳并检查固定锚点。第二条 作业区禁止无关人员进入。'.encode()
    assert client.post('/api/detect/knowledge/upload', files={'file': ('rule.txt', text)}).status_code == 200
    before = kb.search('安全绳 固定锚点')
    bad = client.post('/api/detect/knowledge/upload', files={'file': ('rule.txt', b'   ')})
    assert bad.status_code == 422
    assert (tmp_path / 'rule.txt').read_bytes() == text
    assert kb.search('安全绳 固定锚点') == before
    assert len(kb.summary()['documents']) == 1


def test_corrupt_pdf_never_replaces_previous_bytes(tmp_path):
    kb = KnowledgeBase(tmp_path)
    original = b'previous document'
    (tmp_path / 'rule.pdf').write_bytes(original)
    with pytest.raises(Exception):
        kb.import_document('rule.pdf', b'not a PDF')
    assert (tmp_path / 'rule.pdf').read_bytes() == original


def make_bridge(tmp_path):
    bridge = DetectBridge.__new__(DetectBridge)
    bridge.jobs_root = tmp_path
    bridge.jobs = {}
    bridge.lock = threading.Lock()
    bridge.job_queue = queue.Queue(maxsize=1)
    return bridge


def persist_job(bridge, identifier, status='done'):
    folder = bridge.jobs_root / identifier
    folder.mkdir()
    (folder / 'input.jpg').write_bytes(b'input')
    job = dict(job_id=identifier, status=status, source='upload', device_id='test',
               data_mode='offline', profile='demo', created_at='2026-09-07',
               image_name='input.jpg', output_dir=str(folder), stages=[], result=None)
    bridge._persist_job(job)
    return job


def test_finished_history_survives_restart_and_supports_pages(tmp_path):
    bridge = make_bridge(tmp_path)
    persist_job(bridge, 'JOB-1')
    persist_job(bridge, 'JOB-2', 'error')
    bridge._recover_interrupted_jobs()
    assert len(bridge.recent()) == 2
    assert bridge.recent(status='error')[0]['job_id'] == 'JOB-2'
    assert len(bridge.recent(limit=1, offset=1)) == 1
    assert bridge.get_job('JOB-1')['status'] == 'done'


def test_recovery_queue_overflow_is_not_stranded(tmp_path):
    bridge = make_bridge(tmp_path)
    persist_job(bridge, 'JOB-1', 'queued')
    persist_job(bridge, 'JOB-2', 'running')
    bridge._recover_interrupted_jobs()
    assert bridge.job_queue.qsize() == 1
    assert bridge.get_job('JOB-2')['status'] == 'error'
    assert '重试' in bridge.get_job('JOB-2')['error']


def test_cancel_is_idempotent_and_worker_does_not_run_it(tmp_path):
    bridge = make_bridge(tmp_path)
    job = persist_job(bridge, 'JOB-1', 'queued')
    bridge.jobs['JOB-1'] = job
    assert bridge.cancel_job('JOB-1')['status'] == 'cancelled'
    bridge.cancel_job('JOB-1')
    bridge._run_job('JOB-1')
    assert job['status'] == 'cancelled'
    assert json.loads((tmp_path / 'JOB-1/bridge_summary.json').read_text())['status'] == 'cancelled'


def test_running_job_cannot_be_cancelled(tmp_path):
    bridge = make_bridge(tmp_path)
    bridge.jobs['JOB-1'] = persist_job(bridge, 'JOB-1', 'running')
    with pytest.raises(Exception) as error:
        bridge.cancel_job('JOB-1')
    assert error.value.status_code == 409


def test_job_id_path_traversal_is_rejected(tmp_path):
    with pytest.raises(KeyError):
        make_bridge(tmp_path).get_job('../JOB-1')


def test_ambiguous_media_name_does_not_select_wrong_case(tmp_path):
    from app_server import AppState
    state = AppState.__new__(AppState)
    state.media_roots = [tmp_path]
    for folder in ['JOB-a', 'JOB-b']:
        (tmp_path / folder).mkdir()
        (tmp_path / folder / 'overlay.png').write_bytes(folder.encode())
    assert state.resolve_media(str(tmp_path / 'missing/overlay.png')) is None
    assert state.resolve_media('C:/old/computer/JOB-b/overlay.png') == (tmp_path / 'JOB-b/overlay.png').resolve()


def test_custom_llama_path_is_validated_before_launch(tmp_path, monkeypatch):
    manager = QwenServiceManager(tmp_path)
    monkeypatch.setattr(manager, 'status', lambda settings: {'running': False, 'reachable': False})
    with pytest.raises(RuntimeError, match='可执行文件路径无效'):
        manager.start({'llama_server_path': str(tmp_path / 'missing.exe')})
