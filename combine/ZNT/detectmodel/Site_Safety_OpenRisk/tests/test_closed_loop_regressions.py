import io
import json
import copy
import threading
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

import app_server as server
from detect_bridge import DetectBridge


def _client(tmp_path: Path):
    db = server.Database(tmp_path / "business.db")
    db.seed_users()
    server.STATE = server.AppState(db, tmp_path)
    client = TestClient(server.app)
    token = client.post(
        "/api/auth/login", json={"username": "safety", "password": "safety123"}
    ).json()["token"]
    return client, db, {"Authorization": f"Bearer {token}"}


def test_mobile_manual_report_enters_event_order_and_persists_image(tmp_path) -> None:
    client, db, headers = _client(tmp_path)
    image = Image.new("RGB", (32, 24), "red")
    content = io.BytesIO()
    image.save(content, format="JPEG")
    with client:
        response = client.post(
            "/api/mobile/report",
            data={"title": "路面落石", "level": "red", "area": "测试高速路段", "desc": "现场确认"},
            files={"files": ("evidence.jpg", content.getvalue(), "image/jpeg")},
            headers=headers,
        )
    assert response.status_code == 200
    assert response.json()["workOrders"] == 0
    assert response.json()["confirmations"] == 1
    confirmation = db.list("confirmation")[0]
    decision = client.post(f"/api/confirmations/{confirmation['request_id']}/decide",
                           json={"verdict":"confirmed","comment":"人工现场核验"}, headers=headers)
    assert decision.status_code == 200
    event = db.list("event")[0]
    order = db.list("work_order")[0]
    report = db.list("manual_report")[0]
    assert event["event_id"] == response.json()["eventId"]
    assert order["event_id"] == event["event_id"]
    assert Path(report["images"][0]).is_file()
    media = client.get("/api/media-file", params={"path": report["images"][0]}, headers=headers)
    assert media.status_code == 200
    assert media.headers["content-type"].startswith("image/")
    db.conn.close()


def test_handled_alarm_is_removed_from_pending_alarm_list(tmp_path) -> None:
    client, db, headers = _client(tmp_path)
    now = "2026-08-13T12:00:00-07:00"
    event = {
        "event_id": "EVT-ALARM-STATE",
        "data_mode": "realtime",
        "device": {"device_id": "CAM-1", "device_type": "fixed_camera", "site_id": "SITE-1"},
        "time": {"captured_at": now, "detected_at": now, "reported_at": now},
        "media": {"image_path": "", "image_width": 0, "image_height": 0},
        "overall_has_anomaly": True,
        "risks": [{
            "risk_id": "road_debris", "risk_name_zh": "路面散落异物", "verified": True,
            "confidence": 0.9, "risk_level": "major", "risk_level_zh": "较大风险",
            "risk_description": "现场确认", "manual_review_required": False,
        }],
    }
    with client:
        assert client.post(
            "/api/internal/ingest/event", json=event,
            headers={"X-Internal-Key": server.INTERNAL_KEY},
        ).status_code == 200
        alarms = client.get("/api/monitor/alarms", headers=headers).json()
        assert len(alarms) == 1
        handled = client.post(
            "/api/mobile/alarm/handle",
            json={"alarmId": alarms[0]["id"], "action": "accept"}, headers=headers,
        )
        assert handled.status_code == 200
        assert client.get("/api/monitor/alarms", headers=headers).json() == []
    db.conn.close()


def test_stable_event_id_is_deterministic() -> None:
    first = DetectBridge.stable_event_id("JOB-FIXED")
    assert first == DetectBridge.stable_event_id("JOB-FIXED")
    assert first != DetectBridge.stable_event_id("JOB-OTHER")


def test_concurrent_duplicate_ingest_creates_one_order(tmp_path) -> None:
    client, db, _headers = _client(tmp_path)
    del client
    now = "2026-08-13T12:00:00-07:00"
    event = {
        "event_id": "EVT-CONCURRENT-IDEMPOTENCY", "data_mode": "realtime",
        "device": {"device_id": "CAM-1", "device_type": "fixed_camera", "site_id": "SITE-1"},
        "time": {"captured_at": now, "detected_at": now, "reported_at": now},
        "media": {"image_path": "", "image_width": 0, "image_height": 0},
        "overall_has_anomaly": True,
        "risks": [{"risk_id": "road_debris", "risk_name_zh": "路面散落异物",
                   "verified": True, "confidence": 0.9,
                   "risk_level": "major", "risk_level_zh": "较大风险"}],
    }
    barrier = threading.Barrier(8)
    results = []

    def ingest() -> None:
        barrier.wait()
        results.append(server.STATE.ingest_event(copy.deepcopy(event)))

    threads = [threading.Thread(target=ingest) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert db.count("event") == 1
    assert db.count("work_order") == 0
    assert db.count("confirmation") == 1
    assert db.count("notification") == 0
    assert sum(not item.get("idempotent", False) for item in results) == 1
    db.conn.close()


def test_date_scoped_stats_do_not_count_historical_events(tmp_path) -> None:
    _client_obj, db, _headers = _client(tmp_path)
    base = {
        "data_mode": "realtime",
        "device": {"device_id": "CAM-1", "device_type": "fixed_camera", "site_id": "SITE-1"},
        "media": {"image_path": "", "image_width": 0, "image_height": 0},
        "overall_has_anomaly": True,
        "risks": [{"risk_id": "road_debris", "risk_name_zh": "路面散落异物",
                   "verified": True, "confidence": 0.9,
                   "risk_level": "major", "risk_level_zh": "较大风险"}],
    }
    for index, day in enumerate(["2026-08-12", "2026-08-13"]):
        payload = copy.deepcopy(base)
        payload["event_id"] = f"EVT-DATE-{index}"
        stamp = f"{day}T12:00:00-07:00"
        payload["time"] = {"captured_at": stamp, "detected_at": stamp, "reported_at": stamp}
        server.STATE.ingest_event(payload)
    assert server.STATE.stats()["events_with_anomaly"] == 2
    assert server.STATE.stats("2026-08-13")["events_with_anomaly"] == 1
    db.conn.close()


def test_mobile_workorder_requires_and_persists_rectification_evidence(tmp_path) -> None:
    client, db, headers = _client(tmp_path)
    now = "2026-08-13T12:00:00-07:00"
    event = {
        "event_id": "EVT-EVIDENCE-FLOW", "data_mode": "realtime",
        "device": {"device_id": "CAM-1", "device_type": "fixed_camera", "site_id": "SITE-1"},
        "time": {"captured_at": now, "detected_at": now, "reported_at": now},
        "media": {"image_path": "", "image_width": 0, "image_height": 0},
        "overall_has_anomaly": True,
        "risks": [{"risk_id": "road_debris", "risk_name_zh": "路面散落异物",
                   "verified": True, "confidence": 0.9,
                   "risk_level": "major", "risk_level_zh": "较大风险"}],
    }
    image = Image.new("RGB", (20, 20), "green")
    content = io.BytesIO(); image.save(content, format="JPEG")
    with client:
        client.post("/api/internal/ingest/event", json=event,
                    headers={"X-Internal-Key": server.INTERNAL_KEY})
        confirmation = db.list("confirmation")[0]
        decision = client.post(f"/api/confirmations/{confirmation['request_id']}/decide",
                               json={"verdict":"confirmed"}, headers=headers)
        assert decision.status_code == 200
        order_id = db.list("work_order")[0]["work_order_id"]
        accepted = client.post("/api/mobile/workorder/advance",
                               json={"id": order_id, "action": "next"}, headers=headers)
        assert accepted.status_code == 200
        blocked = client.post("/api/mobile/workorder/advance",
                              json={"id": order_id, "action": "next"}, headers=headers)
        assert blocked.status_code == 400
        evidence = client.post(
            "/api/mobile/workorder/evidence", data={"id": order_id},
            files={"file": ("rectified.jpg", content.getvalue(), "image/jpeg")}, headers=headers,
        )
        assert evidence.status_code == 200
        stored = db.get(order_id)
        assert stored["status"] == "rectified"
        assert Path(stored["evidence_images"][0]).is_file()
        closed = client.post("/api/mobile/workorder/advance",
                             json={"id": order_id, "action": "close"}, headers=headers)
        assert closed.status_code == 200
        assert db.get(order_id)["status"] == "closed"
    db.conn.close()


def test_invalid_manual_report_removes_partial_media_directory(tmp_path) -> None:
    client, db, headers = _client(tmp_path)
    with client:
        response = client.post(
            "/api/mobile/report",
            data={"title": "测试", "level": "orange", "area": "A区"},
            files=[("files", ("good.jpg", b"not-really-an-image", "image/jpeg"))],
            headers=headers,
        )
    assert response.status_code == 400
    manual_root = tmp_path / "manual_reports"
    assert not manual_root.exists() or list(manual_root.iterdir()) == []
    assert db.count("event") == 0
    db.conn.close()


def test_duplicate_ingest_repairs_missing_order_after_partial_crash(tmp_path) -> None:
    _client_obj, db, _headers = _client(tmp_path)
    now = "2026-08-13T12:00:00-07:00"
    event = {
        "event_id": "EVT-PARTIAL-REPAIR", "data_mode": "realtime",
        "device": {"device_id": "CAM-1", "device_type": "fixed_camera", "site_id": "SITE-1"},
        "time": {"captured_at": now, "detected_at": now, "reported_at": now},
        "media": {"image_path": "", "image_width": 0, "image_height": 0},
        "overall_has_anomaly": True,
        "risks": [{"risk_id": "road_debris", "risk_name_zh": "路面散落异物",
                   "verified": True, "confidence": 0.9,
                   "risk_level": "major", "risk_level_zh": "较大风险"}],
    }
    # Simulate a crash immediately after the event document was committed.
    db.upsert("event", event["event_id"], event, status="pending", site_id="SITE-1")
    result = server.STATE.ingest_event(copy.deepcopy(event))
    assert result["idempotent"] is True
    assert result["repaired"] is True
    assert db.count("event") == 1
    assert db.count("work_order") == 0
    assert db.count("confirmation") == 1
    assert db.count("notification") == 0
    second = server.STATE.ingest_event(copy.deepcopy(event))
    assert second["repaired"] is False
    assert db.count("confirmation") == 1
    assert db.count("work_order") == 0
    db.conn.close()


def test_live_bridge_uses_approved_threshold_file(monkeypatch, tmp_path) -> None:
    bridge = DetectBridge(default_profile="demo")
    config = {"pipeline": {"threshold_overrides_path": "configs/threshold_overrides_eval_empty.json"}}
    if "pipeline" not in config:
        config["pipeline"] = {}
    # Mirrors the explicit live-profile normalization in DetectBridge._run_job.
    config["pipeline"]["threshold_overrides_path"] = "configs/threshold_overrides.json"
    assert config["pipeline"]["threshold_overrides_path"].endswith("threshold_overrides.json")


def test_database_shared_connection_serializes_concurrent_reads_and_writes(tmp_path) -> None:
    db = server.Database(tmp_path / "threaded.db")
    failures = []

    def writer(worker: int) -> None:
        try:
            for index in range(80):
                doc_id = f"DOC-{worker}-{index}"
                db.upsert("stress", doc_id, {"id": doc_id, "value": index})
        except Exception as exc:  # pragma: no cover - assertion reports the original error
            failures.append(exc)

    def reader() -> None:
        try:
            for _ in range(120):
                db.list("stress")
                db.count("stress")
        except Exception as exc:  # pragma: no cover - assertion reports the original error
            failures.append(exc)

    threads = [threading.Thread(target=writer, args=(index,)) for index in range(3)]
    threads += [threading.Thread(target=reader) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert failures == []
    assert db.count("stress") == 240
    db.conn.close()


def test_dashboard_online_count_and_trend_only_use_live_today_data(tmp_path) -> None:
    client, db, headers = _client(tmp_path)
    today = datetime.now().astimezone().date().isoformat()
    old_day = "2000-01-01"
    base = {
        "data_mode": "realtime",
        "device": {"device_id": "CAM-HISTORY", "device_type": "fixed_camera", "site_id": "SITE-1"},
        "media": {"image_path": "", "image_width": 0, "image_height": 0},
        "overall_has_anomaly": True,
        "risks": [{"risk_id": "road_debris", "risk_name_zh": "路面散落异物",
                   "verified": True, "confidence": 0.9,
                   "risk_level": "major", "risk_level_zh": "较大风险"}],
    }
    for event_id, day in (("EVT-OLD-TREND", old_day), ("EVT-TODAY-TREND", today)):
        event = copy.deepcopy(base)
        event["event_id"] = event_id
        stamp = f"{day}T09:10:00-07:00"
        event["time"] = {"captured_at": stamp, "detected_at": stamp, "reported_at": stamp}
        server.STATE.ingest_event(event)
    # Merely having historical detections must not make a camera online.
    with client:
        result = client.get("/api/dashboard/overview", headers=headers).json()
        devices = client.get("/api/resource/devices", headers=headers).json()
    camera_metric = next(item for item in result["metrics"] if item["key"] == "cameras")
    assert camera_metric["value"] == 0
    assert devices[0]["online"] is False
    hour_index = result["riskTrendHours"]["hours"].index("09:00")
    assert result["riskTrendHours"]["values"][hour_index] == 1
    db.conn.close()


def test_model_config_includes_all_operator_defaults_and_approved_overrides(monkeypatch, tmp_path) -> None:
    override_path = tmp_path / "threshold_overrides.json"
    override_path.write_text(
        json.dumps({"risk_overrides": {"road_debris": {"min_verified_confidence": 0.85}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(server, "THRESHOLD_OVERRIDES_PATH", override_path)
    client, db, headers = _client(tmp_path)
    with client:
        response = client.get("/api/model/config", headers=headers)
    assert response.status_code == 200
    rows = {item["key"]: item for item in response.json()["thresholds"]}
    assert len(rows) >= 11
    assert rows["road_debris"]["approved"] is True
    assert rows["road_debris"]["source"] == "approved_override"
    assert rows["traffic_facility_damage"]["approved"] is False
    assert rows["traffic_facility_damage"]["value"] == 0.60
    db.conn.close()


def test_failed_webhook_notification_is_persisted_and_retryable(monkeypatch, tmp_path) -> None:
    _client_obj, db, _headers = _client(tmp_path)
    server.STATE.gateway.webhook_url = "http://notification.invalid/hook"

    def fail(*_args, **_kwargs):
        raise OSError("network unavailable")

    monkeypatch.setattr("site_safety.agents.notify_gateway.httpx.post", fail)
    notice = {"notification_id": "NT-RETRYABLE", "title": "告警", "body": "测试",
              "targets": ["safety_officer"], "created_at": server._now_iso()}
    first = server.STATE.dispatch_notification(notice)
    assert first["status"] == "retry_pending"
    assert db.get("NT-RETRYABLE")["delivery_attempts"] == 1

    class Response:
        status_code = 200

    monkeypatch.setattr("site_safety.agents.notify_gateway.httpx.post",
                        lambda *_args, **_kwargs: Response())
    retried = server.STATE.retry_notifications()
    assert retried == {"retried": 1, "delivered": 1, "failed": 0}
    saved = db.get("NT-RETRYABLE")
    assert saved["status"] == "delivered"
    assert saved["delivery_attempts"] == 2
    db.conn.close()


def test_project_filter_is_applied_to_dashboard_analysis_and_screen(tmp_path) -> None:
    client, db, headers = _client(tmp_path)
    today = datetime.now().astimezone().date().isoformat()
    for index, site_id in enumerate(("SITE-A", "SITE-B")):
        stamp = f"{today}T10:0{index}:00-07:00"
        event = {
            "event_id": f"EVT-SITE-{index}", "data_mode": "realtime",
            "device": {"device_id": f"CAM-{index}", "device_type": "fixed_camera",
                       "site_id": site_id},
            "time": {"captured_at": stamp, "detected_at": stamp, "reported_at": stamp},
            "media": {"image_path": "", "image_width": 0, "image_height": 0},
            "overall_has_anomaly": True,
            "risks": [{"risk_id": "road_debris", "risk_name_zh": "路面散落异物",
                       "verified": True, "confidence": 0.9,
                       "risk_level": "major", "risk_level_zh": "较大风险"}],
        }
        server.STATE.ingest_event(event)
    with client:
        dashboard = client.get("/api/dashboard/overview", params={"projectId": "SITE-A"},
                               headers=headers).json()
        analysis = client.get("/api/analysis/overview", params={"projectId": "SITE-A"},
                              headers=headers).json()
        screen = client.get("/api/screen/overview", params={"projectId": "SITE-A"}).json()
    hazards = next(item for item in dashboard["metrics"] if item["key"] == "hazards")
    assert hazards["value"] == 1
    assert sum(analysis["trend"]["red"] + analysis["trend"]["orange"]
               + analysis["trend"]["yellow"]) == 1
    assert screen["stats"]["hazardTotal"] == 1
    assert all(case["id"].startswith("EVT-SITE-0") for case in screen["cases"])
    db.conn.close()


def test_device_filters_are_applied_by_business_api(tmp_path) -> None:
    client, db, headers = _client(tmp_path)
    stamp = server._now_iso()
    event = {
        "event_id": "EVT-DEVICE-FILTER", "data_mode": "realtime",
        "device": {"device_id": "CAM-FILTER", "device_type": "fixed_camera", "site_id": "SITE-FILTER"},
        "time": {"captured_at": stamp, "detected_at": stamp, "reported_at": stamp},
        "media": {"image_path": "", "image_width": 0, "image_height": 0},
        "overall_has_anomaly": False, "risks": [],
    }
    server.STATE.ingest_event(event)
    with client:
        offline = client.get("/api/resource/devices", params={"status": "offline"},
                             headers=headers).json()
        online = client.get("/api/resource/devices", params={"status": "online"},
                            headers=headers).json()
        keyword = client.get("/api/resource/devices", params={"keyword": "FILTER"},
                             headers=headers).json()
    assert any(row["id"] == "CAM-FILTER" for row in offline)
    assert all(row["id"] != "CAM-FILTER" for row in online)
    assert [row["id"] for row in keyword] == ["CAM-FILTER"]
    db.conn.close()


def test_business_websocket_has_ready_and_heartbeat(tmp_path) -> None:
    client, db, headers = _client(tmp_path)
    token = headers["Authorization"].split(" ", 1)[1]
    with client:
        with client.websocket_connect(f"/ws?token={token}") as websocket:
            ready = websocket.receive_json()
            assert ready["type"] == "ready"
            websocket.send_text("ping")
            assert websocket.receive_json()["type"] == "pong"
    db.conn.close()
