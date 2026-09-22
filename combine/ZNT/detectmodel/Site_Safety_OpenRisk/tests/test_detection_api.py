import base64
import io
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

import detection_api
from detection_api import app


def test_standalone_detection_api_exposes_both_input_routes() -> None:
    paths = app.openapi()["paths"]
    assert "/api/v1/detect/realtime" in paths
    assert "/api/v1/detect/anomaly-image" in paths
    assert "/health" in paths


def _encoded_image(mode: str, size: tuple[int, int] = (160, 120)) -> str:
    buffer = io.BytesIO()
    Image.new(mode, size, 255 if mode == "L" else "gray").save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def test_direct_detection_api_runs_without_agent_changes(
    tmp_path: Path, monkeypatch
) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("DETECTION_CONFIG", str(root / "configs" / "road_demo.yaml"))
    monkeypatch.setenv("DETECTION_OUTPUT_ROOT", str(tmp_path / "api_outputs"))
    detection_api._state["inspector"] = None
    response = TestClient(app).post(
        "/api/v1/detect/anomaly-image",
        json={
            "image_base64": _encoded_image("RGB"),
            "image_format": "png",
            "source": "test_upload",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["screening_trigger"]["source_model"] == "test_upload"
    assert payload["screening_assessment"]["screening_consistency"] == "uncertain"
    assert all(r["risk_id"] == "road_debris" for r in payload["final_report"]["final_risks"])


def test_realtime_detection_api_accepts_coarse_mask(
    tmp_path: Path, monkeypatch
) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("DETECTION_CONFIG", str(root / "configs" / "road_demo.yaml"))
    monkeypatch.setenv("DETECTION_OUTPUT_ROOT", str(tmp_path / "api_outputs"))
    detection_api._state["inspector"] = None
    response = TestClient(app).post(
        "/api/v1/detect/realtime",
        json={
            "image_base64": _encoded_image("RGB"),
            "image_format": "png",
            "screening": {
                "triggered": True,
                "anomaly_score": 0.8,
                "source_model": "test_yolo",
            },
            "coarse_mask_base64": _encoded_image("L"),
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["screening_trigger"]["suspected_regions"][0]["region_id"] == "coarse_mask_1"
