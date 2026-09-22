import io
import json
import os
import threading
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from detect_bridge import DetectBridge, create_app
from site_safety.detection_archive import build_archive, import_archive


def bridge_at(path):
    bridge = DetectBridge.__new__(DetectBridge)
    bridge.jobs_root, bridge.jobs, bridge.lock = path, {}, threading.Lock()
    bridge.retention_days, bridge.retention_max_gb = 1, 1
    return bridge


def sample_at(folder, normal=False):
    folder.mkdir()
    for name in ['input.png', 'scene_annotation.png', 'overlay_water_accumulation.png', 'risk_mask_water_accumulation.png']:
        Image.new('RGB', (12, 8), 'green' if normal else 'blue').save(folder / name)
    event = {
        'event_id': 'original-event', 'data_mode': 'offline',
        'time': {'detected_at': '2026-01-01T12:00:00+00:00', 'reported_at': '2026-01-01T12:00:00+00:00'},
        'media': {'image_path': 'Z:/old/input.png', 'image_width': 12, 'image_height': 8},
        'assessment_quality': {'result_status': 'no_visible_anomaly' if normal else 'pending_review'},
        'risks': [] if normal else [{
            'risk_id': 'water_accumulation', 'risk_name_zh': '路面积水', 'verified': False,
            'confidence': 0.6, 'risk_level': 'pending_review', 'risk_level_zh': '待复核',
            'manual_review_required': True,
            'geometry': {'overlay_path': 'Z:/old/overlay_water_accumulation.png',
                         'mask_path': 'Z:/old/risk_mask_water_accumulation.png'},
        }],
    }
    (folder / 'detection_event.json').write_text(json.dumps(event), encoding='utf-8')
    (folder / 'visual_verification.json').write_text(json.dumps({'final_risks': event['risks']}), encoding='utf-8')
    (folder / 'result.json').write_text('{}', encoding='utf-8')
    (folder / 'issue_report.md').write_text('# 原始检测报告\n原结论待复核', encoding='utf-8')
    return {'sample_id': folder.name, 'output_dir': str(folder), 'image_name': 'input.png', 'dataset': '测试样本'}


def package(tmp_path):
    items = [sample_at(tmp_path/'S01'), sample_at(tmp_path/'N01', normal=True)]
    target = tmp_path/'history.zip'
    build_archive(target, title='历史批次', items=items)
    return target


def test_import_preserves_images_verdicts_and_normal_records_after_restart(tmp_path):
    archive = package(tmp_path)
    bridge = bridge_at(tmp_path/'jobs')
    client = TestClient(create_app(bridge))
    response = client.post('/api/detect/archives/import', files={'file': ('history.zip', archive.read_bytes())})
    assert response.status_code == 200, response.text
    assert response.json()['imported'] == 2
    restarted = bridge_at(bridge.jobs_root)
    client = TestClient(create_app(restarted))
    records = client.get('/api/detect/recent?archived_only=true').json()['items']
    assert len(records) == 2
    for row in records:
        sample = row['archive']['sample_id']
        job = client.get('/api/detect/jobs/'+row['job_id']).json()
        assert job['source'] == 'archive' and job['archived']
        assert job['created_at'] == '2026-01-01T12:00:00+00:00'
        assert job['business_sync']['skipped']
        assert client.get(row['input_image']).content == (tmp_path/sample/'input.png').read_bytes()
        for artifact in (bridge.jobs_root / row['job_id']).iterdir():
            if artifact.name != 'bridge_summary.json':
                assert artifact.read_bytes() == (tmp_path/sample/artifact.name).read_bytes()
        if sample == 'N01':
            assert not job['result']['risks']
            assert job['result']['scene_annotation']
        else:
            risk = job['result']['risks'][0]
            assert not risk['verified'] and risk['manual_review']
            assert client.get(risk['mask']).content == (tmp_path/sample/'risk_mask_water_accumulation.png').read_bytes()
        os.utime(bridge.jobs_root/row['job_id'], (0, 0))
    assert restarted.cleanup_old_jobs()['removed'] == 0
    assert import_archive(restarted, archive)['existing'] == 2
    assert len(list(bridge.jobs_root.glob('JOB-*'))) == 2


@pytest.mark.parametrize('damage', ['hash', 'traversal', 'extra', 'missing', 'invalid_image'])
def test_invalid_package_never_publishes_partial_history(tmp_path, damage):
    archive = package(tmp_path)
    with zipfile.ZipFile(archive) as source:
        entries = {i.filename: source.read(i) for i in source.infolist()}
    if damage == 'hash': entries['samples/N01/input.png'] += b'corrupt'
    if damage == 'traversal': entries['../outside.txt'] = b'bad'
    if damage == 'extra': entries['unlisted.txt'] = b'bad'
    if damage == 'missing': del entries['samples/N01/input.png']
    if damage == 'invalid_image':
        import hashlib
        entries['samples/N01/input.png'] = b'not an image'
        manifest = json.loads(entries['detection-archive.json'])
        for item in manifest['items']:
            for record in item['files']:
                if item['sample_id'] == 'N01' and record['name'] == 'input.png':
                    record.update(bytes=12, sha256=hashlib.sha256(b'not an image').hexdigest())
        entries['detection-archive.json'] = json.dumps(manifest).encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as target:
        for name, data in entries.items(): target.writestr(name, data)
    bridge = bridge_at(tmp_path/'jobs')
    response = TestClient(create_app(bridge)).post('/api/detect/archives/import', files={'file': ('broken.zip', buffer.getvalue())})
    assert response.status_code == 422
    assert not list(bridge.jobs_root.glob('JOB-*'))


def test_archive_existing_task_is_durable_and_media_is_scoped(tmp_path):
    bridge = bridge_at(tmp_path/'jobs')
    record = {'job_id': 'JOB-existing', 'source': 'upload', 'status': 'done',
              'output_dir': str(bridge.jobs_root/'JOB-existing'), 'created_at': '2026-01-01', 'device_id': 'test'}
    bridge._persist_job(record)
    assert bridge.archive_job('JOB-existing')['archived']
    assert bridge_at(bridge.jobs_root).get_job('JOB-existing')['archived']
    outside = bridge.jobs_root/'outside.txt'
    outside.write_text('private', encoding='utf-8')
    with pytest.raises(Exception): bridge.media_path('JOB-existing', '../outside.txt')
