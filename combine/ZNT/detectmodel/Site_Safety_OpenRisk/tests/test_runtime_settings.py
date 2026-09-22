import os
from pathlib import Path

from site_safety.runtime_settings import (
    apply_runtime_settings,
    load_initial_settings,
    load_runtime_settings,
    save_initial_settings,
    save_runtime_settings,
    validate_runtime_settings,
)
from site_safety.runtime_timer import FullAuditTimer


def test_runtime_settings_persist_and_overlay(tmp_path: Path, monkeypatch) -> None:
    checkpoint = tmp_path / "clip.pt"
    checkpoint.write_bytes(b"test")
    path = tmp_path / "runtime.json"
    saved = save_runtime_settings(
        {"clip_enabled": True, "clip_checkpoint_path": str(checkpoint)}, path
    )
    assert load_runtime_settings(path) == saved
    assert validate_runtime_settings(saved)["clip_runtime"]["ok"] is True

    config = {
        "sam3": {"init_kwargs": {}},
        "screening": {"models": [{"name": "a"}, {"name": "b"}]},
        "clip": {"enabled": False},
    }
    monkeypatch.delenv("LOCAL_QWEN_API_KEY", raising=False)
    monkeypatch.delenv("LOCAL_QWEN_MODEL", raising=False)
    merged = apply_runtime_settings(config, saved)
    assert merged["clip"]["enabled"] is True
    assert merged["clip"]["init_kwargs"]["checkpoint"] == str(checkpoint)
    assert config["clip"]["enabled"] is False
    assert os.environ["LOCAL_QWEN_API_KEY"] == "local-no-key"
    assert os.environ["LOCAL_QWEN_MODEL"] == "Qwen3-VL-8B-Instruct"


def test_full_audit_timer_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / "timer.json"
    timer = FullAuditTimer(path)
    claimed, _ = timer.claim("CAM-01", 30, now=1000)
    assert claimed is False
    restarted = FullAuditTimer(path)
    claimed, reason = restarted.claim("CAM-01", 30, now=2801)
    assert claimed is True
    assert "30分钟" in reason


def test_qwen_url_validation_requires_chat_completions_endpoint() -> None:
    assert validate_runtime_settings(
        {"qwen_base_url": "http://127.0.0.1:8080/v1/chat/completions"}
    )["qwen_base_url"]["ok"] is True
    assert validate_runtime_settings(
        {"qwen_base_url": "http://127.0.0.1:8080/v1/models"}
    )["qwen_base_url"]["ok"] is False


def test_component_switches_persist_and_disable_yolo_gate(tmp_path: Path) -> None:
    path = tmp_path / "runtime.json"
    saved = save_runtime_settings(
        {
            "qwen_enabled": True,
            "yolo_enabled": False,
            "sam3_enabled": True,
            "clip_enabled": False,
        },
        path,
    )
    assert saved["yolo_enabled"] is False
    assert saved["sam3_enabled"] is True

    config = {
        "sam3": {"init_kwargs": {}},
        "screening": {"enabled": True, "gate_camera": True, "models": []},
        "clip": {"enabled": True},
    }
    merged = apply_runtime_settings(config, saved)
    assert merged["screening"]["enabled"] is False
    assert merged["screening"]["gate_camera"] is False
    assert merged["clip"]["enabled"] is False


def test_initial_settings_can_be_updated_and_loaded(tmp_path: Path) -> None:
    initial_path = tmp_path / "runtime_initial.json"
    saved = save_initial_settings(
        {"clip_enabled": True, "qwen_model_path": str(tmp_path / "qwen.gguf")},
        initial_path,
    )
    loaded = load_initial_settings(initial_path)
    assert loaded == saved
    assert loaded["clip_enabled"] is True
    assert loaded["qwen_model_path"].endswith("qwen.gguf")
