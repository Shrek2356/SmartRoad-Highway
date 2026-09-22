from concurrent.futures import ThreadPoolExecutor
import json

import pytest
from fastapi import HTTPException
import app_server
from site_safety.utils.json_store import update_json


def test_concurrent_real_threshold_endpoints_preserve_all_risks(tmp_path, monkeypatch):
    target = tmp_path / 'thresholds.json'
    monkeypatch.setattr(app_server, 'THRESHOLD_OVERRIDES_PATH', target)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda i: app_server.frontend_threshold({'key':f'risk_{i}','value':.6+i*.001}, {'username':'tester'}),range(40)))
    saved = json.loads(target.read_text())
    assert len(saved['risk_overrides']) == 40
    assert all(item['success'] for item in results)
    assert saved['risk_overrides']['risk_0']['source'] == 'manual'


@pytest.mark.parametrize('value', [None, 'wrong', float('nan'), float('inf'), -1, 1.1])
def test_threshold_rejects_invalid_values_without_writing(tmp_path,monkeypatch,value):
    target=tmp_path/'thresholds.json'
    monkeypatch.setattr(app_server,'THRESHOLD_OVERRIDES_PATH',target)
    with pytest.raises(HTTPException) as error:
        app_server.frontend_threshold({'key':'risk','value':value},{'username':'tester'})
    assert error.value.status_code == 422
    assert not target.exists()


def test_failed_atomic_save_preserves_original(tmp_path,monkeypatch):
    target=tmp_path/'thresholds.json';target.write_text('{"value":1}')
    from pathlib import Path
    def fail(*args): raise OSError('disk failure')
    monkeypatch.setattr(Path,'replace',fail)
    with pytest.raises(OSError): update_json(target, lambda obj: obj.update(value=2),{})
    assert json.loads(target.read_text()) == {'value':1}
    assert list(tmp_path.iterdir()) == [target]
