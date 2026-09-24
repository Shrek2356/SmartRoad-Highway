"""Workflow fixtures verify safety/contracts, not road-model accuracy."""
import copy
import io
import json
import threading
import zipfile
from types import SimpleNamespace

import pytest
from PIL import Image
from fastapi.testclient import TestClient

from site_safety.agents.continuous_learning import (
    LearningStore, box_iou, digest, regression_gate, retrieve_cases, score_case, validate_feedback, write,
)
from learning_service import LearningService

CATALOG = [{"risk_id": "water_accumulation", "name_zh": "道路积水"}, {"risk_id": "road_debris", "name_zh": "道路散落物"}]
BOX = [.2, .2, .7, .7]


def label(rid="water_accumulation", present=True, box=BOX):
    return dict(risk_id=rid, name="道路积水" if rid == "water_accumulation" else "道路散落物", present=present, bbox=box if present else None)


def feedback(**changes):
    return dict(dict(kind="false_negative", partition="train", reason="浑浊水体淹没右侧车道，有连续漫流边界", group_key="group-A", complete=True, labels=[label()]), **changes)


def create_case(store, tmp_path, number=0, **changes):
    image = tmp_path / f"image-{number}.png"
    Image.new("RGB", (80, 60), (number, 100, 100)).save(image)
    return store.submit(feedback(**changes), dict(job_id=f"JOB-{number}", status="done", profile="archive", result={"risks": []}), image, CATALOG, "operator")


def approve(store, case):
    return store.review(case["case_id"], "approved", "reviewer", "已检查原图中可见依据")


@pytest.mark.parametrize("change", [
    {"kind":"bad"}, {"partition":"both"}, {"reason":""}, {"group_key":"x"},
    {"labels":[label(box=[0,0,0,1])]}, {"labels":[label(box=[0,0,float('nan'),1])]},
    {"labels":[label(box=[-.1,0,1,1])]}, {"labels":[label(rid="no_helmet")]},
    {"labels":[label(rid="open_missing_helmet")]}, {"labels":[label(present=False)]},
    {"kind":"normal", "labels":[]}, {"kind":"normal", "complete":False, "labels":[]},
    {"partition":"validation", "complete":False}, {"kind":"wrong_category"},
    {"kind":"false_positive"}, {"labels":[label(), label()]},
])
def test_invalid_feedback(change):
    # An explicit normal + complete empty-label case is valid (tested separately).
    if change == {"kind":"normal", "labels":[]}:
        assert validate_feedback(feedback(**change), CATALOG)["complete"]
    else:
        with pytest.raises(ValueError):
            validate_feedback(feedback(**change), CATALOG)


def test_original_evidence_is_copied_and_not_rewritten(tmp_path):
    store = LearningStore(tmp_path / "memory")
    case = create_case(store, tmp_path)
    original = (tmp_path / "image-0.png").read_bytes()
    assert store.image(case).read_bytes() == original
    approve(store, case)
    assert store.get("cases", case["case_id"])["original_result"] == {"risks": []}
    (tmp_path / "image-0.png").unlink()
    assert store.image(case).read_bytes() == original


def test_split_leakage_by_group_or_image_and_duplicate_labels(tmp_path):
    store = LearningStore(tmp_path / "memory")
    approve(store, create_case(store, tmp_path))
    for number, group in [(1, "group-A"), (0, "different-group")]:
        case = create_case(store, tmp_path, number, partition="validation", group_key=group)
        with pytest.raises(ValueError, match="同图或同来源"):
            approve(store, case)
    duplicate = create_case(store, tmp_path)
    with pytest.raises(ValueError, match="已有审核"):
        approve(store, duplicate)


def test_version_excludes_pending_and_evaluation_and_invalidates_withdrawal(tmp_path):
    store = LearningStore(tmp_path / "memory")
    with pytest.raises(ValueError): store.build_version("admin")
    training = approve(store, create_case(store, tmp_path))
    approve(store, create_case(store, tmp_path, 1, group_key="evaluation-group", partition="validation"))
    create_case(store, tmp_path, 2)
    version = store.build_version("admin")
    assert [r["case_id"] for r in version["cases"]] == [training["case_id"]]
    original_version = store.path("versions", version["version_id"]).read_bytes()
    store.review(training["case_id"], "withdrawn", "reviewer", "标注需修正")
    with pytest.raises(ValueError, match="审核状态"):
        store.snapshot(version["version_id"])
    assert store.path("versions", version["version_id"]).read_bytes() == original_version


def test_tampered_image_or_path_cannot_be_used(tmp_path):
    store = LearningStore(tmp_path / "memory")
    case = create_case(store, tmp_path)
    with pytest.raises(ValueError): store.get("cases", "../escape")
    case["image"] = "../image-0.png"
    with pytest.raises(ValueError, match="路径"): store.image(case)
    case = store.get("cases", case["case_id"])
    (store.root / case["image"]).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="校验"): approve(store, case)


def test_uncertain_and_mock_samples_cannot_become_training_truth(tmp_path):
    store = LearningStore(tmp_path / "memory")
    case = create_case(store, tmp_path, kind="uncertain", labels=[])
    with pytest.raises(ValueError, match="无法判断"): approve(store, case)
    with pytest.raises(ValueError, match="演示"):
        store.submit(feedback(), dict(status="done", profile="demo"), tmp_path / "image-0.png", CATALOG, "test")


def test_retrieval_excludes_same_image_same_group_and_test_partition(tmp_path):
    store = LearningStore(tmp_path / "memory")
    case = approve(store, create_case(store, tmp_path))
    snapshot = store.build_version("admin")
    query = {"scene_summary": "浑浊水体淹没右侧车道，有连续漫流边界"}
    assert len(retrieve_cases(snapshot, query, "new-image", "new-group")) == 1
    assert not retrieve_cases(snapshot, query, case["image_sha256"])
    assert not retrieve_cases(snapshot, query, "other", case["group_key"])
    snapshot["cases"][0]["partition"] = "holdout"
    assert not retrieve_cases(snapshot, query, "new-image")


def job(risks=(), unable=False):
    return dict(job_id="JOB-test", status="done", profile="standard", result={"assessment_quality": {"result_status": "unable_to_assess" if unable else "pending_review"}}, event={"risks": list(risks)})


def prediction(rid="water_accumulation", verified=True, box=BOX):
    return dict(risk_id=rid, verified=verified, geometry={"bbox_xyxy_norm":box})


def test_metrics_report_partial_labels_review_candidates_abstention_and_boxes():
    case = dict(feedback(), case_id="C")
    score = score_case(case, job([prediction(verified=False), prediction("road_debris")]))
    assert score["fn"] == ["water_accumulation"] and score["fp"] == ["road_debris"]
    assert score["candidate_misses"] == [] and score["box_iou"]["water_accumulation"] == 0
    case["complete"] = False
    assert score_case(case, job([prediction("road_debris")]))["fp"] == []
    assert score_case(case, job([prediction()]))["box_iou"]["water_accumulation"] == 1
    assert score_case(dict(case, complete=True, labels=[]), job(unable=True))["abstain"]
    assert box_iou(BOX, BOX) == 1 and box_iou(None, BOX) == 0
    with pytest.raises(ValueError): score_case(case, dict(job(), profile="demo"))


def evaluation_fixture(store, tmp_path):
    training = approve(store, create_case(store, tmp_path))
    version = store.build_version("admin")
    cases = [approve(store, create_case(store, tmp_path, i, group_key=f"evaluation-{i%2}", partition="validation",
                 **({"kind":"normal", "labels":[]} if i % 2 == 0 else {}))) for i in range(1, 5)]
    results = [dict(case_id=c["case_id"], baseline=score_case(c, job()), candidate=score_case(c, job([prediction()] if c["labels"] else []))) for c in cases]
    return training, version, cases, results


def test_gate_does_not_accept_empty_identical_or_regressed_replays(tmp_path):
    store = LearningStore(tmp_path / "memory")
    _, version, cases, results = evaluation_fixture(store, tmp_path)
    assert regression_gate(cases, results, version)["passed"]
    assert not regression_gate([], [], version)["passed"]
    equal = copy.deepcopy(results)
    for item in equal: item["candidate"] = copy.deepcopy(item["baseline"])
    assert not regression_gate(cases, equal, version)["passed"]
    results[0]["candidate"]["fp"] = ["road_debris"]
    assert not regression_gate(cases, results, version)["passed"]


def test_activation_checks_fresh_data_baseline_and_runtime_then_rollback(tmp_path):
    store = LearningStore(tmp_path / "memory")
    _, version, cases, results = evaluation_fixture(store, tmp_path)
    run = dict(run_id="RUN-test", status="done", candidate=version["version_id"], baseline="none", cases=cases,
               fingerprint="fingerprint", gate=regression_gate(cases, results, version))
    write(store.path("runs", "RUN-test"), run)
    with pytest.raises(ValueError, match="配置"): store.activate("RUN-test", "admin", "changed")
    assert store.activate("RUN-test", "admin", "fingerprint")["version_id"] == version["version_id"]
    with pytest.raises(ValueError): store.activate("RUN-test", "admin", "fingerprint")
    assert store.rollback("admin")["version_id"] == "none"
    store.review(cases[0]["case_id"], "withdrawn", "admin", "修正标签")
    with pytest.raises(ValueError, match="审核状态"): store.activate("RUN-test", "admin", "fingerprint")


def test_visual_memory_records_exact_cases_and_validates_reply(tmp_path):
    from site_safety.pipeline.case_memory import recheck_with_memory
    store = LearningStore(tmp_path / "memory")
    approve(store, create_case(store, tmp_path))
    snapshot = store.build_version("admin")
    Image.new("RGB", (100, 70), "blue").save(tmp_path / "current.png")
    out = tmp_path / "output"; out.mkdir()
    observation = dict(scene_summary="浑浊水体淹没右侧车道，有连续漫流边界", observations=[])
    context = dict(root=str(store.root), version_id=snapshot["version_id"], snapshot=snapshot)
    class Model:
        def generate_json(self, images, prompt):
            assert len(images) == 2 and images[0].size == (100, 70)
            assert "图1是唯一待检测图像" in prompt and "不是SAM3提示词" in prompt
            return json.dumps(observation)
    result = recheck_with_memory(Model(), tmp_path / "current.png", out, observation, CATALOG, context)
    trace = json.loads((out / "case_memory_references.json").read_text(encoding="utf-8"))
    assert trace["status"] == "applied" and len(trace["references"]) == 1
    assert result["scene_summary"] == observation["scene_summary"]
    broken = SimpleNamespace(generate_json=lambda *args: '{invalid')
    assert recheck_with_memory(broken, tmp_path / "current.png", out, observation, CATALOG, context) == observation
    assert json.loads((out / "case_memory_references.json").read_text(encoding="utf-8"))["status"] == "error"


def test_dataset_export_includes_images_and_only_chosen_partition(tmp_path):
    svc = LearningService(tmp_path, tmp_path / "data", "http://127.0.0.1:1")
    _, _, cases, _ = evaluation_fixture(svc.store, tmp_path)
    with zipfile.ZipFile(io.BytesIO(svc.export("validation"))) as archive:
        records = [json.loads(line) for line in archive.read("cases.jsonl").decode().splitlines()]
        assert len(records) == 4 and all(r["partition"] == "validation" for r in records)
        assert all(c["image"] in archive.namelist() for c in cases)
    with pytest.raises(ValueError): svc.export("all")


def test_cancel_flag_survives_worker_save_and_restart_marks_interrupted(tmp_path):
    svc = LearningService(tmp_path, tmp_path / "data", "http://127.0.0.1:1")
    stale = dict(run_id="RUN-test", status="running", cancel_requested=False)
    svc.save_run(stale)
    svc.cancel("RUN-test")
    svc.save_run(stale)
    assert svc.store.get("runs", "RUN-test")["cancel_requested"]
    with pytest.raises(ValueError): svc.check_running(stale)
    resumed = LearningService(tmp_path, tmp_path / "data", "http://127.0.0.1:1")
    assert resumed.store.get("runs", "RUN-test")["status"] == "interrupted"


def test_api_roles_and_no_client_supplied_pass_override(tmp_path, monkeypatch):
    import app_server as server
    db = server.Database(tmp_path / "app.db"); db.seed_users()
    state = server.AppState(db, tmp_path)
    monkeypatch.setattr(server, "STATE", state)
    client = TestClient(server.app)
    def headers(name):
        token = client.post("/api/auth/login", json={"username":name,"password":name+"123"}).json()["token"]
        return {"Authorization":"Bearer "+token}
    viewer, safety, admin = headers("viewer"), headers("safety"), headers("admin")
    assert client.get("/api/learning/overview").status_code == 401
    assert client.get("/api/learning/overview", headers=viewer).status_code == 200
    for route in ["/api/learning/cases", "/api/learning/versions", "/api/learning/runs", "/api/learning/rollback"]:
        assert client.post(route, json={}, headers=viewer).status_code == 403
    assert client.post("/api/learning/versions", headers=safety).status_code == 403
    assert client.post("/api/learning/versions", headers=admin).status_code == 422
    assert client.post("/api/learning/runs/MISSING/activate", json={"passed":True}, headers=admin).status_code == 422
    db.conn.close()


def test_replay_endpoint_refuses_bad_token_and_demo(tmp_path, monkeypatch):
    from detect_bridge import create_app
    monkeypatch.setenv("ZNT_LEARNING_DIR", str(tmp_path / "memory"))
    store = LearningStore(tmp_path / "memory")
    write(store.path("runs", "RUN-test"), dict(run_id="RUN-test", token="server-secret", status="running", cases=[], profile="demo"))
    client = TestClient(create_app(SimpleNamespace()))
    assert client.post("/api/detect/learning-replay", json={"run_id":"RUN-test", "token":"bad"}).status_code == 403
    assert client.post("/api/detect/learning-replay", json={"run_id":"RUN-test", "token":"server-secret", "arm":"candidate"}).status_code == 422


def test_evaluation_jobs_hidden_from_production_recent(tmp_path):
    from detect_bridge import DetectBridge
    bridge = DetectBridge.__new__(DetectBridge)
    bridge.jobs_root, bridge.lock = tmp_path, threading.Lock()
    bridge.jobs = {"JOB-EVAL":dict(job_id="JOB-EVAL", status="done", source="learning_evaluation")}
    assert bridge.recent() == []
    from fastapi import HTTPException
    bridge.jobs["JOB-EVAL"]["status"] = "error"
    with pytest.raises(HTTPException, match="整组回放"):
        bridge.retry_job("JOB-EVAL")


@pytest.mark.parametrize("fail", [False, True])
def test_replay_worker_pairs_cases_without_sending_ground_truth(tmp_path, monkeypatch, fail):
    import learning_service as module
    svc = LearningService(tmp_path, tmp_path / "data", "http://127.0.0.1:1")
    _, version, cases, _ = evaluation_fixture(svc.store, tmp_path)
    monkeypatch.setattr(module, "runtime_fingerprint", lambda *args: "fixture-fingerprint")
    monkeypatch.setattr(module.threading, "Thread", lambda **kwargs: SimpleNamespace(start=lambda:None, is_alive=lambda:False))
    pending = {}
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, json):
            assert set(json) == {"run_id", "case_id", "arm", "token"}  # No test labels in model request.
            ident = "JOB-"+json["case_id"]+json["arm"]
            pending[ident] = json
            return SimpleNamespace(raise_for_status=lambda:None, json=lambda:{"job_id":ident})
        def get(self, url):
            item = pending[url.rsplit("/",1)[-1]]
            case = next(c for c in cases if c["case_id"] == item["case_id"])
            response = job([prediction()] if item["arm"] == "candidate" and case["labels"] else [])
            response.update(learning_fingerprint="fixture-fingerprint", status="error" if fail else "done", error="fixture failure")
            response["result"]["case_memory"] = {"version_id":"none" if item["arm"] == "baseline" else version["version_id"], "status":"disabled" if item["arm"] == "baseline" else "applied"}
            return SimpleNamespace(raise_for_status=lambda:None, json=lambda:response)
    monkeypatch.setattr(module.httpx, "Client", Client)
    public = svc.start(version["version_id"], "validation", "standard", "admin")
    assert "token" not in public and "cases" not in public
    svc._work(public["run_id"])
    run = svc.store.get("runs", public["run_id"])
    if fail:
        assert run["status"] == "error" and run["gate"] is None
    else:
        assert run["status"] == "done" and run["gate"]["passed"] and len(pending) == 8


def test_real_profile_replay_never_publishes_business_events(tmp_path, monkeypatch):
    import detect_bridge as module
    from site_safety.agents.continuous_learning import runtime_fingerprint
    memory = LearningStore(tmp_path / "memory")
    monkeypatch.setenv("ZNT_LEARNING_DIR", str(memory.root))
    bridge = module.DetectBridge(default_profile="demo")
    bridge.jobs_root = tmp_path / "jobs"; bridge.jobs_root.mkdir()
    monkeypatch.setattr(bridge.job_queue, "put_nowait", lambda _:None)
    monkeypatch.setattr(module, "list_profiles", lambda _: [{"id":"standard", "ready":True}])
    fingerprint = runtime_fingerprint(module.ROOT, "standard")
    write(memory.path("runs", "RUN-isolated"), {"status":"running"})
    def inspect(image_path, out_dir, **kwargs):
        write(out_dir / "case_memory_references.json", {"version_id":"none", "status":"disabled"})
        return SimpleNamespace(final_report=None)
    monkeypatch.setattr(bridge, "_get_inspector", lambda *args:SimpleNamespace(inspect=inspect))
    monkeypatch.setattr(bridge, "_build_event", lambda *args:None)
    monkeypatch.setattr(bridge, "_build_frontend_result", lambda *args:{})
    def forbidden(*args, **kwargs): raise AssertionError("Replay must not create live alarms")
    monkeypatch.setattr(bridge, "_push_business_event", forbidden)
    response = bridge.create_job(source="learning_evaluation", device_id="REPLAY", data_mode="offline", image_bytes=b"fixture",
        filename="image.png", profile="standard", force_full_audit=True, learning_evaluation=dict(version_id="none", group_key="eval",
        fingerprint=fingerprint, run_id="RUN-isolated"))
    bridge._run_job(response["job_id"])
    saved = bridge.get_job(response["job_id"])
    assert saved["status"] == "done", saved.get("error")
    assert saved["archived"] and saved["business_sync"]["skipped"] and not bridge.recent()


def test_archived_case_memory_reads_saved_evidence_without_current_retrieval(tmp_path, monkeypatch):
    from detect_bridge import DetectBridge
    bridge = DetectBridge.__new__(DetectBridge)
    bridge.jobs_root, bridge.lock = tmp_path, threading.Lock()
    bridge.jobs = {"JOB-ARCHIVE-QA":dict(result={"risks": []})}
    folder = tmp_path / "JOB-ARCHIVE-QA"; folder.mkdir()
    trace = dict(version_id="MEM-old", status="applied", references=[{"case_id":"CASE-old", "score":.2}])
    write(folder / "case_memory_references.json", trace)
    original = (folder / "case_memory_references.json").read_bytes()
    def forbidden(*args): raise AssertionError("Viewing old evidence must not retrieve live cases")
    monkeypatch.setattr(LearningStore, "snapshot", forbidden)
    assert bridge.get_job(folder.name)["result"]["case_memory"] == trace
    assert (folder / "case_memory_references.json").read_bytes() == original
    (folder / "case_memory_references.json").write_text('broken', encoding='utf-8')
    assert bridge.get_job(folder.name)["result"]["case_memory"]["status"] == "error"
