import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from detect_bridge import create_app
from site_safety import deployment_service, runtime_settings as rs

SCRIPT = Path(__file__).resolve().parents[3] / "requirements/preflight_check.py"


@pytest.fixture
def preflight():
    spec = importlib.util.spec_from_file_location("test_preflight", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_desktop_python_supports_bom_spaces_and_unicode(tmp_path, preflight):
    path = tmp_path / "新设备 with space"
    path.mkdir()
    (path / "desktop-settings.json").write_text(json.dumps({"backend_python": "env/Scripts/python.exe"}), encoding="utf-8-sig")
    assert preflight.desktop_python(path) == (path / "env/Scripts/python.exe").resolve()


def test_invalid_selected_python_never_falls_back(tmp_path, preflight):
    (tmp_path / "desktop-settings.json").write_text('{"backend_python":"missing/python.exe"}')
    target = preflight.desktop_python(tmp_path)
    assert target == (tmp_path / "missing/python.exe").resolve()
    with pytest.raises(RuntimeError, match="不存在"):
        preflight.run_probe(target, "demo")


def test_corrupt_desktop_config_is_actionable(tmp_path, preflight):
    (tmp_path / "desktop-settings.json").write_text("{invalid")
    with pytest.raises(RuntimeError, match="无法读取"):
        preflight.desktop_python(tmp_path)


def test_probe_checks_explicit_interpreter_without_shell_or_environment_leak(tmp_path, preflight, monkeypatch):
    python = tmp_path / "环境 with space.exe"
    python.touch()
    monkeypatch.setenv("PYTHONPATH", "unrelated")
    monkeypatch.setenv("PYTHONHOME", "unrelated")
    def runner(args, **kwargs):
        assert args[:4] == [str(python), "-I", "-X", "utf8"]
        assert kwargs["timeout"] == 90
        assert "PYTHONPATH" not in kwargs["env"] and "PYTHONHOME" not in kwargs["env"]
        assert "shell" not in kwargs
        return SimpleNamespace(stdout='{"ready":false,"mode":"offline","system":{}}', returncode=2)
    assert preflight.run_probe(python, "offline", runner=runner)["ready"] is False


@pytest.mark.parametrize("mode", ["bad", "offline; exit", "standard"])
def test_probe_rejects_unknown_mode(preflight, mode):
    with pytest.raises(ValueError):
        preflight.run_probe(Path(sys.executable), mode)


@pytest.mark.parametrize("output", ["not json", "[]", '{"ready":true,"mode":"cloud"}'])
def test_probe_invalid_output_is_not_success(preflight, output):
    with pytest.raises(RuntimeError, match="有效诊断"):
        preflight.run_probe(Path(sys.executable), "demo", runner=lambda *a, **k: SimpleNamespace(stdout=output, returncode=0))


def test_probe_timeout_is_bounded(preflight):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("python", 90)
    with pytest.raises(RuntimeError, match="90 秒"):
        preflight.run_probe(Path(sys.executable), "demo", runner=timeout)


def test_child_probe_error_has_actionable_message(preflight):
    with pytest.raises(RuntimeError, match="依赖损坏"):
        preflight.run_probe(Path(sys.executable), "demo", runner=lambda *a, **k: SimpleNamespace(
            stdout='{"ready":false,"mode":"demo","error":"依赖损坏"}', returncode=2))


@pytest.fixture
def clean_machine(tmp_path, monkeypatch, preflight):
    root = tmp_path / "新设备 空目录"
    detect = root / "detectmodel/Site_Safety_OpenRisk"
    (detect / "configs").mkdir(parents=True)
    (root / "pc-admin/dist").mkdir(parents=True)
    (root / "pc-admin/dist/index.html").write_text("demo")
    monkeypatch.setattr(preflight, "ROOT", root)
    monkeypatch.setattr(preflight, "DETECT_ROOT", detect)
    monkeypatch.setattr(preflight, "SETTINGS_PATH", detect / "configs/runtime_initial_settings.json")
    # Manifest stays the real release's shared source, settings are isolated.
    monkeypatch.setattr(preflight, "command_output", lambda *a: "")
    monkeypatch.setattr(preflight.shutil, "which", lambda *a: None)
    monkeypatch.setattr(preflight, "dependency_info", lambda *a: {"ready": True, "missing": [], "checked": [], "failures": {}})
    monkeypatch.setattr(preflight, "gpu_info", lambda: {"available": False, "devices": []})
    monkeypatch.setattr(preflight, "desktop_python", lambda: Path(sys.executable).resolve())
    return preflight


def test_demo_does_not_import_cuda_or_require_models_or_node(clean_machine, monkeypatch):
    def forbidden():
        raise AssertionError("Demo must not initialize torch")
    monkeypatch.setattr(clean_machine, "torch_info", forbidden)
    report = clean_machine.collect("demo")
    assert report["ready"]
    assert report["system"]["prebuilt_frontend"]
    assert not any(m["required"] for m in report["models"].values())


def test_missing_models_produces_actionable_errors(clean_machine, monkeypatch):
    monkeypatch.setattr(clean_machine, "torch_info", lambda: {"installed": False, "cuda_available": False})
    report = clean_machine.collect("offline")
    assert not report["ready"]
    messages = str(report["issues"])
    assert "CUDA" in messages and "SAM3" in messages and "llama-server" in messages
    assert not any(word in messages for word in ["SYS03", "E:\\model", "D:\\Anaconda"])


def test_changed_desktop_python_requires_restart(clean_machine, monkeypatch, tmp_path):
    monkeypatch.setattr(clean_machine, "desktop_python", lambda: tmp_path / "other-python.exe")
    report = clean_machine.collect("demo")
    assert not report["ready"]
    assert any("重新打开" in x["message"] for x in report["issues"])


def test_relative_engine_path_resolves_from_detect_root(clean_machine, monkeypatch):
    engine = clean_machine.ROOT / "third_party/llama.cpp/llama-server.exe"
    engine.parent.mkdir(parents=True)
    engine.touch()
    clean_machine.SETTINGS_PATH.write_text(json.dumps({"llama_server_path": "../../third_party/llama.cpp/llama-server.exe"}))
    report = clean_machine.collect("demo")
    assert report["models"]["llama_server_path"]["exists"]
    assert Path(report["system"]["llama_server"]) == engine


def test_invalid_gpu_driver_output_is_not_a_crash(preflight, monkeypatch):
    monkeypatch.setattr(preflight, "command_output", lambda *a: "GPU, N/A, N/A")
    assert preflight.gpu_info() == {"available": False, "devices": []}


def test_path_validation_uses_project_not_working_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(rs, "PROJECT_ROOT", tmp_path)
    checkpoint = tmp_path / "模型/sam3.pt"
    checkpoint.parent.mkdir()
    checkpoint.touch()
    monkeypatch.chdir(tmp_path.parent)
    result = rs.validate_runtime_settings({"sam3_checkpoint_path": "模型/sam3.pt", "sam3_repo_path": ""})
    assert result["sam3_checkpoint_path"]["ok"]
    assert result["sam3_repo_path"]["ok"] is False


def test_in_package_models_persist_as_portable_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(rs, "APP_ROOT", tmp_path)
    project = tmp_path / "detectmodel/Site_Safety_OpenRisk"
    monkeypatch.setattr(rs, "PROJECT_ROOT", project)
    initial = tmp_path / "initial.json"
    model = tmp_path / "models/qwen/model.gguf"
    rs.save_initial_settings({"qwen_model_path": str(model)}, initial)
    stored = json.loads(initial.read_text())["qwen_model_path"]
    assert not Path(stored).is_absolute()
    assert rs.load_initial_settings(initial)["qwen_model_path"] == str(model)
    new_root = tmp_path / "another-device"
    monkeypatch.setattr(rs, "APP_ROOT", new_root)
    monkeypatch.setattr(rs, "PROJECT_ROOT", new_root / "detectmodel/Site_Safety_OpenRisk")
    assert rs.load_initial_settings(initial)["qwen_model_path"] == str(new_root / "models/qwen/model.gguf")


def test_discovery_finds_documented_layout_and_engine(tmp_path, monkeypatch):
    monkeypatch.setattr(rs, "APP_ROOT", tmp_path)
    defaults = dict(rs.DEFAULTS)
    for key, relative in [("qwen_model_path", "models/qwen/model.gguf"), ("sam3_repo_path", "third_party/sam3-main")]:
        path = tmp_path / relative
        if key == "sam3_repo_path": path.mkdir(parents=True)
        else:
            path.parent.mkdir(parents=True)
            path.touch()
        defaults[key] = str(path)
    monkeypatch.setattr(rs, "DEFAULTS", defaults)
    engine = tmp_path / "third_party/llama.cpp/llama-server.exe"
    engine.parent.mkdir(parents=True)
    engine.touch()
    found = rs.discover_runtime_settings({"qwen_model_path": "missing", "sam3_repo_path": "missing"})
    assert found["qwen_model_path"] == defaults["qwen_model_path"]
    assert found["sam3_repo_path"] == defaults["sam3_repo_path"]
    assert found["llama_server_path"] == str(engine)


def test_project_downloads_are_explicitly_empty_but_public_sources_exist():
    manifest = deployment_service.deployment_manifest()["manifest"]
    for key in ("yolo_css_weights_path", "yolo_construction_weights_path"):
        assert key not in manifest["models"]
    assert manifest["models"]["qwen_model_path"]["download_url"].startswith("https://")


def test_guidance_api_is_read_only_and_check_is_explicit(monkeypatch):
    calls = []
    monkeypatch.setattr(deployment_service, "check_environment", lambda mode: calls.append(mode) or {"ready": False, "mode": mode})
    client = TestClient(create_app(SimpleNamespace()))
    assert client.get("/api/detect/deployment").status_code == 200
    assert calls == []
    assert client.post("/api/detect/deployment/check?mode=cloud").json()["mode"] == "cloud"
    assert client.post("/api/detect/deployment/check?mode=invalid").status_code == 422
    assert calls == ["cloud"]


def test_duplicate_check_and_missing_script_fail_cleanly(tmp_path, monkeypatch):
    deployment_service._check_lock.acquire()
    try:
        with pytest.raises(RuntimeError, match="进行中"):
            deployment_service.check_environment("demo")
    finally:
        deployment_service._check_lock.release()
    monkeypatch.setattr(deployment_service, "APP_ROOT", tmp_path)
    with pytest.raises(RuntimeError, match="缺少"):
        deployment_service.check_environment("demo")
    assert not deployment_service._check_lock.locked()
