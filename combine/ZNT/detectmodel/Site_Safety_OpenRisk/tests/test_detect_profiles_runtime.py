from pathlib import Path

from detect_profiles import profile_status


def test_clip_requirement_follows_runtime_switch(monkeypatch, tmp_path: Path) -> None:
    import site_safety.runtime_settings as runtime_settings

    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "road_offline.yaml").write_text("project_name: test", encoding="utf-8")
    caps = {
        "local_qwen_config": True,
        "sam3_weights": True,
        "yolo_weights": True,
        "clip_weights": False,
    }
    monkeypatch.setattr(runtime_settings, "SETTINGS_PATH", tmp_path / "runtime.json")
    runtime_settings.save_runtime_settings({"clip_enabled": False})
    status = profile_status("offline", caps, tmp_path)
    assert status["ready"] is True
    assert status["clip_enabled"] is False

    runtime_settings.save_runtime_settings({"clip_enabled": True})
    status = profile_status("offline", caps, tmp_path)
    assert status["ready"] is False
    assert "clip_weights" in status["missing"]
