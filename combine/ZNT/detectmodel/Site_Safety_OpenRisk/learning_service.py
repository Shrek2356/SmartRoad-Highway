"""Human feedback API and sequential, isolated baseline/candidate replay."""
from __future__ import annotations

import io
import json
import random
import secrets
import threading
import time
import zipfile
from pathlib import Path

import httpx
from fastapi import Depends, HTTPException
from fastapi.responses import Response

from site_safety.agents.continuous_learning import (
    LearningStore, digest, now, regression_gate, runtime_fingerprint, safe_id, score_case, write,
)
from site_safety.utils.json_store import update_json


class LearningService:
    def __init__(self, root, data_root, detect_api):
        self.root = Path(root)
        self.store = LearningStore(Path(data_root) / "continuous_learning")
        self.detect_api = detect_api
        self.stop = threading.Event()
        self.thread = None
        # A process restart cannot silently turn an interrupted replay into a pass.
        for run in self.store.rows("runs"):
            if run["status"] in {"queued", "running"}:
                run.update(status="interrupted", error="服务重启中断回放，请重新运行", finished_at=now())
                self.save_run(run)

    def catalog(self):
        data = json.loads((self.root / "examples/road_damage_catalog.json").read_text(encoding="utf-8"))
        return [row for value in data.values() if isinstance(value, list) for row in value if isinstance(row, dict) and "risk_id" in row]

    def context(self, job_id):
        safe_id(job_id)
        if not job_id.startswith("JOB-"):
            raise ValueError("任务编号无效")
        directory = self.root / "outputs/road_bridge_jobs" / job_id
        if not (directory / "bridge_summary.json").is_file():
            raise ValueError("原始检测任务不存在")
        job = json.loads((directory / "bridge_summary.json").read_text(encoding="utf-8"))
        filename = job.get("image_name", "input.jpg")
        image = (directory / filename).resolve()
        if image.parent != directory.resolve() or not image.is_file():
            raise ValueError("原图缺失，无法形成可复核样本")
        return job, image

    def audits(self):
        seen = {case["job_id"] for case in self.store.rows("cases")}
        rows = []
        for path in (self.root / "outputs/road_bridge_jobs").glob("JOB-*/bridge_summary.json"):
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
                result = job.get("result") or {}
                if (job["job_id"] not in seen and job.get("status") == "done" and job.get("profile") != "demo"
                    and job.get("source") != "learning_evaluation" and not result.get("overall_has_anomaly")
                    and (result.get("assessment_quality") or {}).get("result_status") != "unable_to_assess"):
                    rows.append({"job_id": job["job_id"], "created_at": job.get("created_at"), "device_id": job.get("device_id")})
            except (ValueError, KeyError, OSError):
                continue
        random.SystemRandom().shuffle(rows)
        return rows[:10]

    def save_run(self, run):
        def update(doc):
            cancelled = doc.get("cancel_requested", False) or run.get("cancel_requested", False)
            doc.clear()
            doc.update(run)
            doc["cancel_requested"] = cancelled
        update_json(self.store.path("runs", run["run_id"]), update, {})

    def start(self, version_id, partition, profile, reviewer):
        if profile not in {"standard", "offline"} or partition not in {"validation", "holdout"}:
            raise ValueError("回放仅允许真实标准/离线模型与独立验证/保留测试集")
        with self.store.lock:
            if self.thread and self.thread.is_alive():
                raise ValueError("已有回放进行中")
            candidate = self.store.snapshot(version_id)
            if version_id == "none" or version_id == self.store.active()["version_id"]:
                raise ValueError("请选择尚未启用的候选版本")
            baseline_id = self.store.active()["version_id"]
            baseline = self.store.snapshot(baseline_id)
            cases = [c for c in self.store.rows("cases") if c["status"] == "approved" and c["partition"] == partition]
            if not cases or len(cases) > 50:
                raise ValueError("小试回放需要1至50张已审核评测样本；启用至少需要4张及类别覆盖")
            training = baseline["cases"] + candidate["cases"]
            for case in cases:
                self.store.image(case)
                if not case["complete"] or any(c["image_sha256"] == case["image_sha256"] or c["group_key"] == case["group_key"] for c in training):
                    raise ValueError("评测样本未整图复核或与经验库同图/同来源，禁止回放")
            ident = "RUN-" + secrets.token_hex(8)
            run = dict(run_id=ident, status="queued", profile=profile, partition=partition, candidate=version_id,
                       baseline=baseline_id, cases=cases, results=[], created_at=now(), created_by=reviewer,
                       token=secrets.token_urlsafe(32), fingerprint=runtime_fingerprint(self.root, profile),
                       progress="等待回放", cancel_requested=False, gate=None)
            self.save_run(run)
            self.thread = threading.Thread(target=self._work, args=(ident,), daemon=True, name="road-learning-replay")
            self.thread.start()
            return self.public_run(run)

    def _work(self, ident):
        run = self.store.get("runs", ident)
        try:
            run.update(status="running", started_at=now())
            self.save_run(run)
            with httpx.Client(timeout=30, trust_env=False) as client:
                for index, case in enumerate(run["cases"]):
                    pair = dict(case_id=case["case_id"])
                    for arm in ("baseline", "candidate"):
                        self.check_running(run)
                        run["progress"] = f"{index+1}/{len(run['cases'])} · {'当前版本' if arm == 'baseline' else '候选版本'}"
                        self.save_run(run)
                        response = client.post(self.detect_api + "/api/detect/learning-replay", json={
                            "run_id": ident, "case_id": case["case_id"], "arm": arm, "token": run["token"]})
                        response.raise_for_status()
                        job_id = response.json()["job_id"]
                        run["current_job"] = job_id
                        self.save_run(run)
                        deadline = time.monotonic() + 1800
                        while time.monotonic() < deadline:
                            self.check_running(run)
                            reply = client.get(self.detect_api + "/api/detect/jobs/" + job_id)
                            reply.raise_for_status()
                            job = reply.json()
                            if job["status"] in {"done", "error", "cancelled"}:
                                break
                            if self.stop.wait(2):
                                raise ValueError("服务正在关闭，回放中断")
                        else:
                            raise ValueError("单张图回放超时；当前检测任务可能仍在完成中")
                        if job["status"] != "done":
                            raise ValueError("真实模型回放失败：" + str(job.get("error") or job["status"]))
                        if job.get("learning_fingerprint") != run["fingerprint"]:
                            raise ValueError("回放模型配置不一致，结果不能用于启用")
                        trace = (job.get("result") or {}).get("case_memory", {})
                        if trace.get("status") in {"error", "unavailable"} or trace.get("version_id") != run[arm]:
                            raise ValueError("经验检索未按指定版本完成，禁止将降级结果计入回放")
                        pair[arm] = score_case(case, job)
                    run["results"].append(pair)
                    self.save_run(run)
            self.check_running(run)
            if runtime_fingerprint(self.root, run["profile"]) != run["fingerprint"]:
                raise ValueError("回放期间运行配置变化，请重新运行")
            run.update(status="done", gate=regression_gate(run["cases"], run["results"], self.store.snapshot(run["candidate"])), progress="回放完成")
        except Exception as exc:
            cancelled = self.store.get("runs", ident).get("cancel_requested")
            run.update(status="cancelled" if cancelled else "error", error=str(exc), gate=None)
        finally:
            run["finished_at"] = now()
            self.save_run(run)

    def check_running(self, run):
        if self.stop.is_set() or self.store.get("runs", run["run_id"]).get("cancel_requested"):
            raise ValueError("回放已取消；正在执行的检测会自行结束，不会启用新版本")

    def cancel(self, ident):
        with self.store.lock:
            run = self.store.get("runs", ident)
            if run["status"] not in {"queued", "running"}:
                raise ValueError("该回放已经结束")
            run["cancel_requested"] = True
            self.save_run(run)
            return self.public_run(run)

    @staticmethod
    def public_run(run):
        return {k: v for k, v in run.items() if k not in {"token", "cases"}}

    def export(self, partition):
        if partition not in {"train", "validation", "holdout"}:
            raise ValueError("请选择独立导出的数据用途")
        cases = [c for c in self.store.rows("cases") if c["status"] == "approved" and c["partition"] == partition]
        if not cases:
            raise ValueError("此用途暂无审核通过的案例")
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            lines = []
            for case in cases:
                archive.write(self.store.image(case), case["image"])
                lines.append(json.dumps(case, ensure_ascii=False))
            archive.writestr("cases.jsonl", "\n".join(lines))
            archive.writestr("README.txt", "路安智巡人工审核数据包\n用途：" + partition +
                "\n含原图、人工范围框、原始结果与审核记录。框是图像范围，不是像素掩码。\n" +
                "训练仅使用train；validation用于开发选型；holdout应冻结并限次使用，使用后不得再宣称盲测。\n" +
                "此为通用数据导出，不是已完成LoRA微调。模型适配、训练及独立评估另行执行。")
        return stream.getvalue()


def install_routes(app, state, auth_viewer, auth_officer, auth_admin):
    def service():
        return state().continuous_learning

    def invoke(fn, *args):
        try:
            return fn(*args)
        except (ValueError, KeyError, OSError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/learning/overview")
    def overview(user=Depends(auth_viewer)):
        svc = service()
        cases = svc.store.rows("cases")
        cases = [dict(case, image_url=state().media_url(str(svc.store.root / case["image"]))) for case in cases]
        versions = [{k: v for k, v in row.items() if k != "cases"} | {"case_count": len(row["cases"])} for row in svc.store.rows("versions")]
        return dict(cases=cases, versions=versions, runs=[svc.public_run(r) for r in svc.store.rows("runs")], active=svc.store.active(), catalog=svc.catalog())

    @app.get("/api/learning/audit-samples")
    def audits(user=Depends(auth_officer)):
        return service().audits()

    @app.get("/api/learning/context/{job_id}")
    def context(job_id: str, user=Depends(auth_officer)):
        job, image = invoke(service().context, job_id)
        group = (job.get("archive") or {}).get("dataset") or ((job.get("device_id") or "upload") + ":" + str(job.get("created_at", ""))[:10])
        return dict(job_id=job_id, image_url=state().media_url(str(image)), group_key=group, catalog=service().catalog(), result=job.get("result"))

    @app.post("/api/learning/cases")
    def submit(payload: dict, user=Depends(auth_officer)):
        svc = service()
        job, image = invoke(svc.context, payload.get("job_id"))
        return invoke(svc.store.submit, payload, job, image, svc.catalog(), user["username"])

    @app.get("/api/learning/cases/{case_id}/image")
    def case_image(case_id: str, user=Depends(auth_viewer)):
        from fastapi.responses import FileResponse
        case = invoke(service().store.get, "cases", case_id)
        return FileResponse(invoke(service().store.image, case))

    @app.post("/api/learning/cases/{case_id}/review")
    def review(case_id: str, payload: dict, user=Depends(auth_officer)):
        return invoke(service().store.review, case_id, payload.get("decision"), user["username"], payload.get("note", ""))

    @app.post("/api/learning/versions")
    def version(user=Depends(auth_admin)):
        row = invoke(service().store.build_version, user["username"])
        return {k: v for k, v in row.items() if k != "cases"}

    @app.post("/api/learning/runs")
    def replay(payload: dict, user=Depends(auth_admin)):
        return invoke(service().start, payload.get("version_id"), payload.get("partition", "validation"), payload.get("profile", "standard"), user["username"])

    @app.post("/api/learning/runs/{run_id}/cancel")
    def cancel(run_id: str, user=Depends(auth_admin)):
        return invoke(service().cancel, run_id)

    @app.post("/api/learning/runs/{run_id}/activate")
    def activate(run_id: str, user=Depends(auth_admin)):
        svc = service()
        run = invoke(svc.store.get, "runs", run_id)
        return invoke(svc.store.activate, run_id, user["username"], runtime_fingerprint(svc.root, run["profile"]))

    @app.post("/api/learning/rollback")
    def rollback(user=Depends(auth_admin)):
        return service().store.rollback(user["username"])

    @app.get("/api/learning/export/{partition}")
    def export(partition: str, user=Depends(auth_officer)):
        return Response(invoke(service().export, partition), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="road-cases-{partition}.zip"'})
