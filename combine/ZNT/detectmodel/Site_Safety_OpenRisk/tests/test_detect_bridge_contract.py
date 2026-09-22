import base64
import io
import json
import time

from fastapi.testclient import TestClient
from PIL import Image

from detect_bridge import DetectBridge, create_app
from site_safety.runtime_timer import FullAuditTimer


def test_demo_profile_normalizes_acquisition_mode_and_final_risk_fallback(
    tmp_path, monkeypatch
) -> None:
    bridge = DetectBridge(default_profile="demo")
    bridge.jobs_root = tmp_path
    monkeypatch.setattr(bridge.job_queue, "put_nowait", lambda _job_id: None)
    response = bridge.create_job(
        source="upload",
        device_id="DEMO",
        data_mode="demo",
        image_bytes=b"image",
        filename="image.jpg",
        profile="demo",
    )
    job = bridge.jobs[response["job_id"]]
    assert job["data_mode"] == "offline"

    output_dir = tmp_path / "fallback"
    output_dir.mkdir()
    (output_dir / "visual_verification.json").write_text(
        json.dumps(
            {
                "overall_has_anomaly": True,
                "final_risks": [
                    {
                        "risk_id": "test_risk",
                        "risk_name_zh": "测试风险",
                        "verified": True,
                        "confidence": 0.9,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    result = type("Result", (), {"final_report": None})()
    summary = bridge._build_frontend_result(job, output_dir, result, None)
    assert summary["overall_has_anomaly"] is True
    assert summary["risk_count"] == 1


def test_upload_accepts_external_screening_contract(tmp_path) -> None:
    bridge = DetectBridge(default_profile="demo")
    bridge.jobs_root = tmp_path
    client = TestClient(create_app(bridge))

    image = Image.new("RGB", (64, 64), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    trigger = {
        "triggered": False,
        "anomaly_score": 0.0,
        "suspected_regions": [],
        "suspected_concepts": [],
        "source_model": "external-test",
        "reason": "contract test",
    }
    response = client.post(
        "/api/detect/upload",
        files={"file": ("blank.jpg", buffer.getvalue(), "image/jpeg")},
        data={
            "profile": "demo",
            "force_inspection": "true",
            "screening_json": json.dumps(trigger),
        },
    )
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    for _ in range(100):
        job = client.get(f"/api/detect/jobs/{job_id}").json()
        if job["status"] in {"done", "error"}:
            break
        time.sleep(0.05)

    assert job["status"] == "done"
    assert job["screening"]["source_model"] == "external-test"
    assert job["result"]["routed_to_vlm"] is True
    assert job["result"]["screening"]["triggered"] is False
    assert job["timings_ms"]["screening"] >= 0
    assert job["timings_ms"]["total"] >= job["timings_ms"]["screening"]


def test_health_exposes_screening_contract(tmp_path) -> None:
    bridge = DetectBridge(default_profile="demo")
    bridge.jobs_root = tmp_path
    payload = TestClient(create_app(bridge)).get("/api/detect/health").json()
    assert payload["screening_contract"] == "ScreeningTrigger"
    assert "integrated_yolo" in payload["screening_endpoint_modes"]
    assert payload["full_audit_endpoint"] == "/api/detect/full-audit"


def test_claim_full_audit_supports_forced_and_scheduled_modes(tmp_path) -> None:
    bridge = DetectBridge(default_profile="demo")
    bridge.audit_timer = FullAuditTimer(tmp_path / "timer.json")
    config = {
        "screening": {
            "scheduled_full_audit_minutes": 30,
            "allowed_full_audit_minutes": [30, 120],
            "full_audit_on_first_frame": False,
        }
    }
    forced = {
        "source": "camera",
        "device_id": "CAM-FORCED",
        "force_full_audit": True,
        "audit_interval_minutes": 30,
    }
    claimed, reason = bridge._claim_full_audit(forced, config)
    assert claimed is True
    assert "强制" in reason

    scheduled = {
        "source": "camera",
        "device_id": "CAM-SCHEDULED",
        "force_full_audit": False,
        "audit_interval_minutes": 30,
    }
    bridge.audit_timer.set_last("CAM-SCHEDULED", time.time() - 1801)
    claimed, reason = bridge._claim_full_audit(scheduled, config)
    assert claimed is True
    assert "30分钟" in reason


def test_full_audit_endpoint_bypasses_screening(tmp_path) -> None:
    bridge = DetectBridge(default_profile="demo")
    bridge.jobs_root = tmp_path
    client = TestClient(create_app(bridge))
    image = Image.new("RGB", (64, 64), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    payload = {
        "image_base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
        "device_id": "CAM-AUDIT",
        "profile": "demo",
        "audit_interval_minutes": 120,
    }
    response = client.post("/api/detect/full-audit", json=payload)
    assert response.status_code == 200
    job_id = response.json()["job_id"]
    for _ in range(100):
        job = client.get(f"/api/detect/jobs/{job_id}").json()
        if job["status"] in {"done", "error"}:
            break
        time.sleep(0.05)
    assert job["status"] == "done"
    assert job["result"]["full_audit"] is True
    assert job["result"]["audit_mode"] == "forced_full"
    assert job["result"]["screening"] is None
    assert job["business_sync"]["skipped"] is True
    assert job["business_sync"]["detail"] == "demo_profile_not_persisted"


def test_runtime_settings_and_timer_endpoints(tmp_path, monkeypatch) -> None:
    from site_safety import runtime_settings

    bridge = DetectBridge(default_profile="demo")
    bridge.audit_timer = FullAuditTimer(tmp_path / "timer.json")
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(runtime_settings, "SETTINGS_PATH", settings_path)
    monkeypatch.setattr(runtime_settings, "INITIAL_SETTINGS_PATH", tmp_path / "initial.json")
    client = TestClient(create_app(bridge))

    response = client.put(
        "/api/detect/runtime-settings",
        json={"settings": {"clip_enabled": True, "qwen_base_url": "http://127.0.0.1:8080/v1/chat/completions"}},
    )
    assert response.status_code == 200
    assert response.json()["settings"]["clip_enabled"] is True
    assert "api_key" not in json.dumps(response.json()).lower()

    initial = client.put(
        "/api/detect/runtime-settings/initial",
        json={"settings": response.json()["settings"]},
    )
    assert initial.status_code == 200
    restored = client.post("/api/detect/runtime-settings/reset-initial")
    assert restored.status_code == 200
    assert restored.json()["settings"]["clip_enabled"] is True

    timer = client.get("/api/detect/timers", params={"interval_minutes": 30})
    assert timer.status_code == 200
    assert timer.json()["interval_minutes"] == 30

    qwen = client.get("/api/detect/qwen-service")
    assert qwen.status_code == 200
    assert {"running", "reachable", "managed", "detail"} <= qwen.json().keys()


def test_knowledge_document_upload_search_and_delete(tmp_path) -> None:
    from site_safety.agents.knowledge_base import KnowledgeBase

    bridge = DetectBridge(default_profile="demo")
    bridge.knowledge_base = KnowledgeBase(tmp_path / "knowledge")
    client = TestClient(create_app(bridge))

    uploaded = client.post(
        "/api/detect/knowledge/upload",
        files={
            "file": (
                "高处作业规范.txt",
                "第一条 高处作业人员必须正确使用安全带并连接可靠锚点。".encode("utf-8"),
                "text/plain",
            )
        },
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["chunk_count"] >= 1
    assert uploaded.json()["document_chunk_count"] == 1

    searched = client.get("/api/detect/knowledge/search", params={"q": "安全带锚点"})
    assert searched.status_code == 200
    assert searched.json()["hits"][0]["source_file"] == "高处作业规范.txt"

    deleted = client.delete("/api/detect/knowledge/高处作业规范.txt")
    assert deleted.status_code == 200
    assert deleted.json()["file_count"] == 0


def test_bridge_rejects_invalid_profile_and_non_image_before_queue(tmp_path) -> None:
    bridge = DetectBridge(default_profile="demo")
    bridge.jobs_root = tmp_path
    client = TestClient(create_app(bridge))

    bad_profile = client.post(
        "/api/detect/upload",
        files={"file": ("image.jpg", b"not-an-image", "image/jpeg")},
        data={"profile": "unknown"},
    )
    # Payload validation deliberately happens before profile/model checks.
    assert bad_profile.status_code == 400
    assert "有效图像" in bad_profile.json()["detail"]

    image = Image.new("RGB", (16, 16), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    bad_profile = client.post(
        "/api/detect/upload",
        files={"file": ("image.jpg", buffer.getvalue(), "image/jpeg")},
        data={"profile": "unknown"},
    )
    assert bad_profile.status_code == 400
    assert "检测档位" in bad_profile.json()["detail"]
    assert bridge.jobs == {}


def test_cloud_profile_alias_and_queue_health(tmp_path, monkeypatch) -> None:
    import detect_bridge as bridge_module

    bridge = DetectBridge(default_profile="demo")
    bridge.jobs_root = tmp_path
    monkeypatch.setattr(
        bridge_module,
        "list_profiles",
        lambda _root: [{"id": "standard", "ready": True, "missing": []}],
    )
    response = bridge.create_job(
        source="upload",
        device_id="CLOUD-ALIAS",
        data_mode="offline",
        image_bytes=b"test",
        filename="image.jpg",
        profile="cloud",
    )
    assert response["profile"] == "standard"
    queue_state = bridge.health()["inference_queue"]
    assert queue_state["workers"] >= 1
    assert queue_state["capacity"] >= 1


def test_camera_frame_rejects_invalid_base64_and_recent_limit(tmp_path) -> None:
    bridge = DetectBridge(default_profile="demo")
    bridge.jobs_root = tmp_path
    client = TestClient(create_app(bridge))
    response = client.post(
        "/api/detect/camera-frame",
        json={"image_base64": "%%%%", "profile": "demo"},
    )
    assert response.status_code == 400
    assert client.get("/api/detect/recent", params={"limit": 101}).status_code == 400


def test_bridge_validates_screening_and_runtime_settings_at_boundary(tmp_path, monkeypatch) -> None:
    from site_safety import runtime_settings

    bridge = DetectBridge(default_profile="demo")
    bridge.jobs_root = tmp_path
    monkeypatch.setattr(runtime_settings, "SETTINGS_PATH", tmp_path / "runtime.json")
    client = TestClient(create_app(bridge))
    image = Image.new("RGB", (16, 16), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")

    response = client.post(
        "/api/detect/upload",
        files={"file": ("image.jpg", buffer.getvalue(), "image/jpeg")},
        data={"profile": "demo", "screening_json": json.dumps({"triggered": True})},
    )
    assert response.status_code == 422
    assert "ScreeningTrigger" in response.json()["detail"]
    assert bridge.jobs == {}

    unknown = client.put(
        "/api/detect/runtime-settings", json={"settings": {"surprise": "value"}}
    )
    assert unknown.status_code == 422
    invalid_url = client.put(
        "/api/detect/runtime-settings", json={"settings": {"qwen_base_url": "not-a-url"}}
    )
    assert invalid_url.status_code == 422
    discover_unknown = client.post(
        "/api/detect/runtime-settings/discover", json={"settings": {"surprise": "value"}}
    )
    assert discover_unknown.status_code == 422


def test_implicit_profile_is_resolved_at_submission_time(monkeypatch, tmp_path) -> None:
    import detect_bridge as bridge_module

    monkeypatch.setattr(bridge_module, "pick_default_profile", lambda _root: "demo")
    bridge = DetectBridge(default_profile="")
    assert bridge.default_profile == "demo"
    # Configuration may become available after the bridge has already started.
    monkeypatch.setattr(bridge_module, "pick_default_profile", lambda _root: "offline")
    monkeypatch.setattr(
        bridge_module,
        "list_profiles",
        lambda _root: [{"id": "offline", "ready": True, "missing": []}],
    )
    monkeypatch.setattr(
        bridge.qwen_service,
        "status",
        lambda _settings: {"reachable": True, "detail": "ok"},
    )
    bridge.jobs_root = tmp_path
    response = bridge.create_job(
        source="upload",
        device_id="TEST",
        data_mode="offline",
        image_bytes=b"test",
        filename="image.jpg",
        profile="",
    )
    assert response["profile"] == "offline"
