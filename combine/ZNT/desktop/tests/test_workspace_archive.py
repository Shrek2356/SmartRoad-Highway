import json
from pathlib import Path
import sqlite3
import sys
import zipfile

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace_archive import BACKEND, WorkspaceMaintenance, export_workspace, inspect_archive


def workspace(root, label='original'):
    backend=root/BACKEND
    for directory in ['road_app_data','road_knowledge_base','outputs/road_bridge_jobs/JOB-1','outputs/road_runtime','configs']:
        (backend/directory).mkdir(parents=True,exist_ok=True)
    image=backend/'outputs/road_bridge_jobs/JOB-1/overlay.png';image.write_bytes(label.encode())
    with sqlite3.connect(backend/'road_app_data/road_safety.db') as conn:
        conn.executescript('CREATE TABLE docs(id TEXT,kind TEXT,json TEXT);CREATE TABLE users(username TEXT);')
        conn.execute('INSERT INTO docs VALUES(?,?,?)',('event','event',json.dumps({'image':str(image)})))
        conn.execute('INSERT INTO docs VALUES(?,?,?)',('camera','camera_source',json.dumps({'desired_running':True})))
        conn.execute('INSERT INTO users VALUES(?)',(label,))
    conn.close()
    (backend/'road_knowledge_base/rules.txt').write_text('道路巡检规则：发现路面障碍物后记录位置与可见证据。', encoding='utf-8')
    (backend/'outputs/road_bridge_jobs/JOB-1/bridge_summary.json').write_text(json.dumps({'status':'queued','output_dir':str(image.parent)}), encoding='utf-8')
    (backend/'outputs/road_runtime/runtime_settings.json').write_text(json.dumps({'qwen_autostart':True,'qwen_model_path':'E:/external/model.gguf'}), encoding='utf-8')
    (backend/'configs/road_threshold_overrides.json').write_text(json.dumps({'risk_overrides':{label:{'min_verified_confidence':.65}}}), encoding='utf-8')
    (backend/'.env').write_text('DO_NOT_EXPORT=secret', encoding='utf-8')
    (backend/'road_app_data/weight.pt').write_bytes(b'weight')
    return backend


def test_offline_roundtrip_preserves_evidence_rebases_paths_and_pauses_models(tmp_path):
    source=tmp_path/'source';workspace(source)
    archive=tmp_path/'snapshot.zip'
    result=export_workspace(source,archive)
    assert result['status']=='saved'
    names=[item['path'] for item in inspect_archive(archive)['files']]
    assert 'road_knowledge_base/rules.txt' in names and 'road_app_data/road_safety.db' in names
    assert all('.env' not in name and not name.endswith('.pt') for name in names)
    target=tmp_path/'target';backend=workspace(target,'existing')
    maintenance=WorkspaceMaintenance(target)
    maintenance.schedule('restore',archive)
    assert (backend/'outputs/road_bridge_jobs/JOB-1/overlay.png').read_bytes()==b'existing'
    result=maintenance.run(lambda:None)
    assert result['status']=='restored', result
    assert Path(result['recovery_backup']).is_file()
    assert (backend/'outputs/road_bridge_jobs/JOB-1/overlay.png').read_bytes()==b'original'
    with sqlite3.connect(backend/'road_app_data/road_safety.db') as conn:
        assert Path(json.loads(conn.execute("SELECT json FROM docs WHERE id='event'").fetchone()[0])['image']).is_relative_to(target)
        assert not json.loads(conn.execute("SELECT json FROM docs WHERE id='camera'").fetchone()[0])['desired_running']
        assert conn.execute('SELECT username FROM users').fetchone()[0]=='original'
    assert not json.loads((backend/'outputs/road_runtime/runtime_settings.json').read_text(encoding='utf-8'))['qwen_autostart']
    assert json.loads((backend/'outputs/road_bridge_jobs/JOB-1/bridge_summary.json').read_text(encoding='utf-8'))['status']=='error'
    assert (backend/'.env').read_text(encoding='utf-8')=='DO_NOT_EXPORT=secret'
    assert (backend/'road_knowledge_base/rules.txt').read_text(encoding='utf-8')=='道路巡检规则：发现路面障碍物后记录位置与可见证据。'


def test_existing_archive_is_never_overwritten_and_pending_can_be_cancelled(tmp_path):
    root=tmp_path/'source';workspace(root);archive=tmp_path/'backup.zip'
    archive.write_bytes(b'old')
    with pytest.raises(ValueError): export_workspace(root,archive)
    assert archive.read_bytes()==b'old'
    manager=WorkspaceMaintenance(root)
    manager.schedule('backup',tmp_path/'new.zip')
    with pytest.raises(ValueError): manager.schedule('backup',tmp_path/'another.zip')
    assert manager.cancel()['pending'] is None
    assert not (tmp_path/'new.zip').exists()


def test_busy_services_abort_without_modifying_workspace(tmp_path):
    root=tmp_path/'source';backend=workspace(root)
    manager=WorkspaceMaintenance(root);archive=tmp_path/'new.zip'
    manager.schedule('backup',archive)
    def busy(): raise RuntimeError('service running')
    assert manager.run(busy)['status']=='error'
    assert not archive.exists() and not manager.pending.exists()
    assert (backend/'outputs/road_bridge_jobs/JOB-1/overlay.png').read_bytes()==b'original'


def test_tampered_backup_rejected_before_replacing_data(tmp_path):
    source=tmp_path/'source';workspace(source);archive=tmp_path/'backup.zip';export_workspace(source,archive)
    target=tmp_path/'target';backend=workspace(target,'existing')
    manager=WorkspaceMaintenance(target);manager.schedule('restore',archive)
    with archive.open('ab') as stream: stream.write(b'changed')
    assert manager.run(lambda:None)['status']=='error'
    assert (backend/'outputs/road_bridge_jobs/JOB-1/overlay.png').read_bytes()==b'existing'


@pytest.mark.parametrize('malicious',['../escape.txt','road_app_data/../../escape.txt','road_app_data/C:evil','road_app_data/folder./evil.txt'])
def test_manifest_traversal_is_rejected(tmp_path,malicious):
    source=tmp_path/'source';workspace(source);archive=tmp_path/'backup.zip';export_workspace(source,archive)
    manifest=inspect_archive(archive)
    import hashlib
    manifest['files']=[{'path':malicious,'bytes':1,'sha256':hashlib.sha256(b'x').hexdigest()}]
    evil=tmp_path/'bad.zip'
    with zipfile.ZipFile(evil,'w') as output:
        output.writestr('workspace-manifest.json',json.dumps(manifest));output.writestr(malicious,b'x')
    with pytest.raises(ValueError): inspect_archive(evil)


@pytest.mark.parametrize('interrupted',[False,True])
def test_restore_failure_and_crash_journal_roll_back(tmp_path,monkeypatch,interrupted):
    source=tmp_path/'source';workspace(source);archive=tmp_path/'backup.zip';export_workspace(source,archive)
    target=tmp_path/'target';backend=workspace(target,'existing');manager=WorkspaceMaintenance(target)
    manager.schedule('restore',archive)
    original=Path.rename;failed=False
    def fail_once(path,dest):
        nonlocal failed
        if not failed and 'incoming' in path.parts and path.name=='road_knowledge_base':
            failed=True
            if interrupted: raise KeyboardInterrupt('simulate power loss')
            raise OSError('locked directory')
        return original(path,dest)
    monkeypatch.setattr(Path,'rename',fail_once)
    if interrupted:
        with pytest.raises(KeyboardInterrupt): manager.run(lambda:None)
        assert manager.journal.is_file()
        manager.run(lambda:None)
    else: assert manager.run(lambda:None)['status']=='error'
    assert not manager.journal.exists()
    assert (backend/'outputs/road_bridge_jobs/JOB-1/overlay.png').read_bytes()==b'existing'
    with sqlite3.connect(backend/'road_app_data/road_safety.db') as conn:
        assert conn.execute('SELECT username FROM users').fetchone()[0]=='existing'
