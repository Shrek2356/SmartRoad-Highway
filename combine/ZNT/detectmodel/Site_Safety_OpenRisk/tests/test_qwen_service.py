from pathlib import Path

import pytest

from site_safety.qwen_service import QwenServiceManager


def test_qwen_manager_rejects_missing_model_paths(tmp_path: Path, monkeypatch) -> None:
    manager = QwenServiceManager(tmp_path)
    monkeypatch.setattr(manager, "status", lambda _settings: {"running": False, "reachable": False})
    monkeypatch.setattr("site_safety.qwen_service.shutil.which", lambda _name: "llama-server.exe")
    with pytest.raises(RuntimeError, match="路径无效"):
        manager.start(
            {
                "qwen_model_path": str(tmp_path / "missing.gguf"),
                "qwen_mmproj_path": str(tmp_path / "missing-mmproj.gguf"),
                "qwen_base_url": "http://127.0.0.1:8080/v1/chat/completions",
            }
        )


def test_qwen_manager_will_not_launch_remote_endpoint(tmp_path: Path, monkeypatch) -> None:
    manager = QwenServiceManager(tmp_path)
    model = tmp_path / "model.gguf"
    mmproj = tmp_path / "mmproj.gguf"
    model.write_bytes(b"x")
    mmproj.write_bytes(b"x")
    monkeypatch.setattr(manager, "status", lambda _settings: {"running": False, "reachable": False})
    monkeypatch.setattr("site_safety.qwen_service.shutil.which", lambda _name: "llama-server.exe")
    with pytest.raises(RuntimeError, match="本机 Qwen"):
        manager.start(
            {
                "qwen_model_path": str(model),
                "qwen_mmproj_path": str(mmproj),
                "qwen_base_url": "https://example.com/v1/chat/completions",
            }
        )
