import base64
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export_service import save_export
from environment_check import check_python


def test_native_export_save_and_cancel(tmp_path):
    target=tmp_path/'报告.md';content='中文交底'.encode()
    result=save_export('报告.md',base64.b64encode(content).decode(),lambda *args:target)
    assert result == {'status':'saved','filename':'报告.md'}
    assert target.read_bytes() == content
    assert save_export('报告.md','YWJj',lambda *args:None) == {'status':'cancelled'}
    assert target.read_bytes() == content


def test_export_failure_never_truncates_previous_file(tmp_path,monkeypatch):
    target=tmp_path/'old.pdf';target.write_bytes(b'original')
    def fail(*args): raise PermissionError('read-only')
    monkeypatch.setattr(Path,'replace',fail)
    with pytest.raises(PermissionError): save_export('old.pdf','YWJj',lambda *args:target)
    assert target.read_bytes() == b'original'
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize('name,body',[('bad.exe','YWJj'),('test.pdf','%%%')])
def test_invalid_export_rejected_before_dialog(name,body):
    with pytest.raises(ValueError): save_export(name,body,lambda *args: pytest.fail('must not open dialog'))


def test_environment_checks_target_interpreter_and_removes_inherited_pythonpath(monkeypatch):
    monkeypatch.setenv('PYTHONPATH','C:/wrong/packages')
    def runner(args,**kwargs):
        assert args[0] == 'target-python.exe' and '-I' in args and '-B' in args
        assert 'PYTHONPATH' not in kwargs['env']
        return SimpleNamespace(returncode=0,stdout='SITESAFE_ENV='+json.dumps({'version':[3,12,10],'bits':64,'missing':[]}))
    assert check_python(Path('target-python.exe'),runner=runner)['version'] == [3,12,10]


@pytest.mark.parametrize('result',[
    {'version':[3,12,10],'bits':64,'missing':['fastapi']},
    {'version':[3,9,10],'bits':64,'missing':[]},
    {'version':[3,12,10],'bits':32,'missing':[]},
])
def test_environment_rejects_unsupported_or_missing(result):
    with pytest.raises(ValueError): check_python(Path('target.exe'),runner=lambda *a,**k:SimpleNamespace(returncode=0,stdout='SITESAFE_ENV='+json.dumps(result)))


def test_environment_rejects_non_python_and_timeout():
    with pytest.raises(ValueError): check_python(Path('node.exe'),runner=lambda *a,**k:SimpleNamespace(returncode=1,stdout='not python'))
    def timeout(*a,**k): raise subprocess.TimeoutExpired('test',30)
    with pytest.raises(ValueError): check_python(Path('python.exe'),runner=timeout)


def test_incomplete_environment_cannot_replace_desktop_settings(tmp_path,monkeypatch):
    import desktop_app
    # A source checkout need not bundle Python; use the current test interpreter.
    config = {**desktop_app.DEFAULT_CONFIG, 'backend_python': sys.executable}
    target=tmp_path/'desktop-settings.json';target.write_text(json.dumps(config), encoding='utf-8')
    monkeypatch.setattr(desktop_app,'CONFIG_PATH',target)
    def reject(*a,**k): raise ValueError('missing dependencies')
    monkeypatch.setattr(desktop_app,'check_python',reject)
    runtime=desktop_app.DesktopRuntime(config)
    with pytest.raises(ValueError): runtime.save_desktop_settings({'frontend_port':55173})
    assert json.loads(target.read_text(encoding='utf-8')) == config
