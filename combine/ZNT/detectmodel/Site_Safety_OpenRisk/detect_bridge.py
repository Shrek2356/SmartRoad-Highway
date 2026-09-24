"""
前端实时检测桥接服务
-------------------------------------------------------
作用：把 PC 管理端（上传图片 / 摄像头截帧）接到 Site Safety OpenRisk 检测流水线，
      返回各阶段协同进度与最终结果，供平台展示。

业务档位（见 detect_profiles.py，前端可选，无需重启）：
  standard  标准检测 = 云端视觉 + 本地 SAM3（CLIP 可选）
  offline   离线检测 = 本地 Qwen + YOLO + SAM3（CLIP 可选）
  demo      演示联调 = Mock

启动：
  pip install -r requirements-bridge.txt
  python detect_bridge.py --port 8810
  # 可选：指定默认档位
  python detect_bridge.py --profile standard --port 8810

接口：
  GET  /api/detect/health          # 含 profiles / default_profile
  POST /api/detect/cloud-key       # 写入云端 DASHSCOPE_API_KEY
  POST /api/detect/upload          # multipart 可带 profile
  POST /api/detect/camera-frame    # json 可带 profile
  GET  /api/detect/jobs/{job_id}
  GET  /api/detect/jobs/{job_id}/media/{filename}
  GET  /api/detect/recent
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import queue
import threading
import tempfile
import urllib.request
import time
import uuid
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Literal

from PIL import Image, UnidentifiedImageError

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from site_safety.agents.schemas import RoadContext

from detect_profiles import (
    list_profiles,
    normalize_profile,
    pick_default_profile,
    resolve_config,
)

ROOT = Path(__file__).resolve().parent

# 阶段定义（与流水线协同对应，面向前端展示）
STAGE_DEFS = [
    {"id": "ingest", "name": "接收图像", "agent": "接入层"},
    {"id": "screen", "name": "实时视觉注意力初筛", "agent": "YOLO轻量模型"},
    {"id": "first_pass", "name": "视觉初检·候选发现", "agent": "视觉大模型"},
    {"id": "segment", "name": "实体定位与风险掩码", "agent": "SAM3/分割"},
    {"id": "verify", "name": "证据核验与门控", "agent": "空间关系/规则门控"},
    {"id": "second_pass", "name": "二次视觉确认", "agent": "视觉大模型"},
    {"id": "management_report", "name": "生成模型报告", "agent": "报告模型"},
    {"id": "reason", "name": "风险推理与规范映射", "agent": "推理智能体"},
    {"id": "report", "name": "结果归档与接口同步", "agent": "程序编排"},
]


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _new_stages(clip_enabled: bool = False) -> List[Dict[str, Any]]:
    stages = []
    for stage in STAGE_DEFS:
        item = dict(stage)
        if item["id"] == "verify" and clip_enabled:
            item["agent"] = "CLIP/空间关系"
        stages.append(
            {**item, "status": "pending", "message": "", "started_at": None, "finished_at": None}
        )
    return stages


class CameraFrameRequest(BaseModel):
    road_context: RoadContext = Field(default_factory=RoadContext)
    image_base64: str = Field(..., min_length=4, max_length=36_000_000, description="dataURL 或纯 base64")
    device_id: str = Field(default="CAM-WEB-01", min_length=1, max_length=128)
    stream_ref: str = Field(default="", max_length=2048)
    site_id: str = Field(default="SITE-DEFAULT", min_length=1, max_length=128)
    profile: str = ""
    screening: Optional[Dict[str, Any]] = None
    force_inspection: bool = False
    force_full_audit: bool = False
    audit_interval_minutes: Optional[int] = Field(default=None, ge=1, le=1440)


class CloudKeyRequest(BaseModel):
    api_key: str = Field(..., description="阿里云百炼 DASHSCOPE_API_KEY")
    persist: bool = True


class RuntimeSettingsRequest(BaseModel):
    settings: Dict[str, Any] = Field(default_factory=dict)


class RuntimePathPickerRequest(BaseModel):
    field: str
    current: str = ""


class DetectBridge:
    def __init__(self, default_profile: str = "") -> None:
        self.default_profile_explicit = bool(default_profile.strip())
        self.default_profile = (
            normalize_profile(default_profile, ROOT)
            if self.default_profile_explicit
            else pick_default_profile(ROOT)
        )
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()
        self.model_lock = threading.Lock()
        self.inference_lock = threading.Lock()
        self.jobs_root = ROOT / "outputs" / "road_bridge_jobs"
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        self.screeners: Dict[str, Any] = {}
        self.inspectors: Dict[str, Any] = {}
        self.device_frame_counts: Dict[str, int] = {}
        self.max_pending_jobs = max(1, int(os.getenv("ZNT_MAX_PENDING_JOBS", "16")))
        self.worker_count = max(1, int(os.getenv("ZNT_GPU_WORKERS", "1")))
        self.job_queue: queue.Queue[str] = queue.Queue(maxsize=self.max_pending_jobs)
        self.pending_sync_dir = self.jobs_root / "_pending_business_sync"
        self.pending_sync_dir.mkdir(parents=True, exist_ok=True)
        self.retention_days = max(1, int(os.getenv("ZNT_JOB_RETENTION_DAYS", "30")))
        self.retention_max_gb = max(1.0, float(os.getenv("ZNT_JOB_RETENTION_MAX_GB", "20")))
        from site_safety.runtime_timer import FullAuditTimer
        from site_safety.qwen_service import QwenServiceManager

        runtime_root = ROOT / "outputs" / "road_runtime"
        # Pytest/TestClient 必须与正在展示的真实 Qwen 进程及状态文件隔离。
        if os.environ.get("PYTEST_CURRENT_TEST"):
            runtime_root = Path(tempfile.gettempdir()) / "znt-test-runtime" / str(os.getpid())
        self.audit_timer = FullAuditTimer(runtime_root / "full_audit_timer.json")
        self.qwen_service = QwenServiceManager(runtime_root)
        from site_safety.agents.knowledge_base import KnowledgeBase

        from site_safety.agents.road_knowledge import ensure_road_knowledge
        self.knowledge_base = KnowledgeBase(ensure_road_knowledge())
        self.knowledge_base.prepare_index()
        for index in range(self.worker_count):
            threading.Thread(
                target=self._job_worker,
                name=f"znt-gpu-worker-{index + 1}",
                daemon=True,
            ).start()
        self._recover_interrupted_jobs()
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            self.cleanup_old_jobs()
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            threading.Thread(target=self._business_retry_loop, daemon=True).start()

    def autostart_models(self) -> None:
        """Start process-backed models selected for platform startup."""
        from site_safety.runtime_settings import load_runtime_settings

        settings = load_runtime_settings()
        if not settings.get("qwen_enabled", True) or not settings.get("qwen_autostart", True):
            return
        status = self.qwen_service.status(settings)
        if status.get("reachable") or status.get("running"):
            return
        try:
            self.qwen_service.start(settings)
            print("[detect-bridge] local Qwen autostart submitted", flush=True)
        except RuntimeError as exc:
            print(f"[detect-bridge] local Qwen autostart skipped: {exc}", flush=True)

    def health(self) -> dict:
        from site_safety.runtime_settings import load_runtime_settings, validate_runtime_settings

        profiles = list_profiles(ROOT)
        settings = load_runtime_settings()
        default = self.default_profile
        cfg = resolve_config(default, ROOT)
        try:
            cfg_disp = str(cfg.relative_to(ROOT))
        except Exception:
            cfg_disp = str(cfg)
        qwen_status = self.qwen_service.status(settings)
        for profile in profiles:
            if profile.get("id") == "offline":
                profile["service_reachable"] = bool(qwen_status["reachable"])
                profile["runtime_ready"] = bool(profile["ready"] and qwen_status["reachable"])
        return {
            "ok": True,
            "service": "site-OpenRisk-detect-bridge",
            "default_profile": default,
            "profiles": profiles,
            "config": cfg_disp,
            "code_root": str(ROOT),
            "time": _now(),
            "hint": "道路小试：standard=云端视觉；offline=本地视觉；demo=模拟联调。道路初筛待接入。",
            "screening_contract": "ScreeningTrigger",
            "screening_endpoint_modes": ["integrated_yolo", "external_screening_json"],
            "full_audit_modes": ["scheduled_30m", "scheduled_120m", "forced_api"],
            "full_audit_endpoint": "/api/detect/full-audit",
            "timer_endpoint": "/api/detect/timers",
            "runtime_settings_endpoint": "/api/detect/runtime-settings",
            "clip_enabled": bool(settings["clip_enabled"]),
            "qwen_service": qwen_status,
            "offline_runtime_ready": bool(
                next(
                    (
                        item.get("runtime_ready", False)
                        for item in profiles
                        if item.get("id") == "offline"
                    ),
                    False,
                )
            ),
            "runtime_components_ready": {
                key: value["ok"] for key, value in validate_runtime_settings(settings).items()
            },
            "inference_queue": {
                "pending": self.job_queue.qsize(),
                "capacity": self.max_pending_jobs,
                "workers": self.worker_count,
                "cached_inspectors": len(self.inspectors),
                "pending_business_sync": len(list(self.pending_sync_dir.glob("*.json"))),
            },
            "job_retention": {"days": self.retention_days, "max_gb": self.retention_max_gb},
        }

    def create_job(
        self,
        *,
        source: str,
        device_id: str,
        data_mode: str,
        image_bytes: bytes,
        filename: str,
        road_context: Optional[Dict[str, Any]] = None,
        stream_ref: str = "",
        site_id: str = "SITE-DEFAULT",
        profile: str = "",
        screening: Optional[Dict[str, Any]] = None,
        force_inspection: bool = False,
        force_full_audit: bool = False,
        audit_interval_minutes: Optional[int] = None,
        learning_evaluation: Optional[Dict[str, Any]] = None,
    ) -> dict:
        # ``data_mode`` describes the acquisition channel, not the model profile.
        # Older demo clients sent "demo", which is not valid for DetectionEvent.
        if data_mode not in {"realtime", "offline"}:
            data_mode = "realtime" if source == "camera" else "offline"
        requested_profile = profile.strip()
        if requested_profile == "cloud":
            requested_profile = "standard"
        if not requested_profile:
            requested_profile = self.default_profile if self.default_profile_explicit else pick_default_profile(ROOT)
        if requested_profile not in {"standard", "offline", "demo", "weights"}:
            raise HTTPException(400, f"不支持的检测档位: {requested_profile}")
        profile_id = normalize_profile(requested_profile, ROOT)
        profile_meta = next((item for item in list_profiles(ROOT) if item["id"] == profile_id), None)
        if profile_meta and not profile_meta.get("ready"):
            missing = "、".join(profile_meta.get("missing") or [])
            raise HTTPException(409, f"检测档位尚未配置完整: {profile_id}；缺少 {missing}")
        if profile_id == "offline":
            from site_safety.runtime_settings import load_runtime_settings

            qwen = self.qwen_service.status(load_runtime_settings())
            if not qwen.get("reachable"):
                raise HTTPException(503, f"本地 Qwen 服务不可用: {qwen.get('detail') or '请先启动并等待加载完成'}")
        config_path = resolve_config(profile_id, ROOT)
        if not config_path.is_file():
            raise HTTPException(400, f"档位配置不存在: {profile_id} -> {config_path}")

        job_id = f"JOB-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        out_dir = self.jobs_root / job_id
        out_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(filename).suffix.lower() or ".jpg"
        if suffix not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
            suffix = ".jpg"
        image_path = out_dir / f"input{suffix}"
        image_path.write_bytes(image_bytes)

        frame_index = None
        if source == "camera":
            with self.lock:
                frame_index = self.device_frame_counts.get(device_id, 0) + 1
                self.device_frame_counts[device_id] = frame_index

        from site_safety.runtime_settings import load_runtime_settings

        runtime_settings = load_runtime_settings()
        clip_enabled = bool(runtime_settings["clip_enabled"] and profile_id != "demo")
        job = {
            "job_id": job_id,
            "status": "queued",
            "source": source,
            "data_mode": data_mode,
            "profile": profile_id,
            "config_name": config_path.name,
            "device_id": device_id,
            "site_id": site_id,
            "road_context": RoadContext.model_validate(road_context or {}).model_dump(),
            "stream_ref": stream_ref,
            "created_at": _now(),
            "updated_at": _now(),
            "image_name": image_path.name,
            "stages": _new_stages(clip_enabled),
            "result": None,
            "event": None,
            "error": None,
            "output_dir": str(out_dir),
            "config_path": str(config_path),
            "screening": screening,
            "screening_source": "external" if screening is not None else "integrated_yolo",
            "force_inspection": bool(force_inspection),
            "force_full_audit": bool(force_full_audit),
            "audit_interval_minutes": audit_interval_minutes,
            "full_audit": False,
            "audit_mode": "screened",
            "frame_index": frame_index,
            "routed_to_vlm": None,
            "clip_enabled": clip_enabled,
        }
        if profile_id != "demo":
            from site_safety.agents.continuous_learning import LearningStore, runtime_fingerprint
            memory_root = Path(os.getenv("ZNT_LEARNING_DIR", str(ROOT / "road_app_data/continuous_learning")))
            memory = LearningStore(memory_root)
            active = memory.active()
            version_id = learning_evaluation["version_id"] if learning_evaluation else active["version_id"]
            context = {"root": str(memory_root), "version_id": version_id,
                       "group_key": learning_evaluation["group_key"] if learning_evaluation else device_id + ":" + job["created_at"][:10]}
            try:
                context["snapshot"] = memory.snapshot(version_id)
                fingerprint = runtime_fingerprint(ROOT, profile_id)
                if learning_evaluation:
                    if fingerprint != learning_evaluation["fingerprint"]:
                        raise ValueError("回放配置已经变化")
                    job["learning_fingerprint"] = fingerprint
                    job["learning_evaluation"] = learning_evaluation
                    job["archived"] = True  # Keep replay evidence with its evaluation record.
                elif version_id != "none" and fingerprint != active.get("fingerprint"):
                    raise ValueError("运行配置与已验证版本不一致，经验已暂停；请重新回放")
            except (ValueError, OSError, KeyError) as exc:
                if learning_evaluation:
                    raise HTTPException(409, str(exc)) from exc
                context["error"] = str(exc)
            job["learning_context"] = context
        with self.lock:
            self.jobs[job_id] = job
        self._persist_job(job)
        try:
            self.job_queue.put_nowait(job_id)
        except queue.Full as exc:
            with self.lock:
                self.jobs.pop(job_id, None)
            for child in out_dir.iterdir():
                child.unlink(missing_ok=True)
            out_dir.rmdir()
            raise HTTPException(429, "检测任务队列已满，请稍后重试") from exc
        return {"job_id": job_id, "status": "queued", "profile": profile_id}

    def get_job(self, job_id: str) -> dict:
        if Path(job_id).name != job_id or not job_id.startswith("JOB-"):
            raise KeyError(job_id)
        with self.lock:
            job = self.jobs.get(job_id)
        if not job:
            # 尝试从磁盘恢复摘要
            out_dir = self.jobs_root / job_id
            summary = out_dir / "bridge_summary.json"
            if summary.is_file():
                job = json.loads(summary.read_text(encoding="utf-8"))
            else:
                raise KeyError(job_id)
        return self._with_reference_record(job, job_id)

    def _with_reference_record(self, job: dict, job_id: str) -> dict:
        """Expose the saved snapshot without re-querying today's KB or editing archives."""
        if not isinstance(job.get('result'), dict):
            return job
        result = dict(job['result'])
        record = self.jobs_root / job_id / 'regulatory_references.json'
        result['regulatory_references'] = None
        result['reference_record_status'] = 'unavailable'
        if record.is_file():
            try:
                payload = json.loads(record.read_text(encoding='utf-8'))
                if not isinstance(payload, dict) or not isinstance(payload.get('references'), dict):
                    raise ValueError('Invalid reference snapshot')
                retrievals = payload.get('retrievals') or {}
                if not isinstance(retrievals, dict):
                    raise ValueError('Invalid retrieval snapshot')
                result['risks'] = [dict(risk,
                    knowledge_retrieval=retrievals.get(risk.get('risk_id'), risk.get('knowledge_retrieval', {})),
                    knowledge_references=payload['references'].get(risk.get('risk_id'), risk.get('knowledge_references', [])))
                    for risk in result.get('risks', [])]
                result['regulatory_references'] = self._media_url(job_id, record.name)
                result['reference_record_status'] = 'recorded'
            except (OSError, ValueError, TypeError):
                result['reference_record_status'] = 'invalid'
        memory_record = self.jobs_root / job_id / 'case_memory_references.json'
        if memory_record.is_file():
            try:
                memory = json.loads(memory_record.read_text(encoding='utf-8'))
                if not isinstance(memory, dict) or not isinstance(memory.get('references'), list) or not isinstance(memory.get('version_id'), str):
                    raise ValueError('Invalid case memory snapshot')
                result['case_memory'] = memory
            except (OSError, ValueError, TypeError):
                result['case_memory'] = {'version_id': 'unknown', 'status': 'error', 'references': [], 'detail': '历史案例引用记录损坏，请核查原始证据'}
        return {**job, 'result': result}

    def recent(self, limit: int = 20, offset: int = 0, status: str = "", archived_only: bool = False) -> list:
        with self.lock:
            by_id = dict(self.jobs)
        for summary in self.jobs_root.glob("JOB-*/bridge_summary.json"):
            if summary.parent.name in by_id:
                continue
            try:
                by_id[summary.parent.name] = json.loads(summary.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
        items = [j for j in by_id.values() if j.get("source") != "learning_evaluation" and (not status or j.get("status") == status)
                 and (not archived_only or j.get("archived"))]
        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return [
            {
                "job_id": j["job_id"],
                "status": j["status"],
                "source": j["source"],
                "profile": j.get("profile"),
                "device_id": j["device_id"],
                "created_at": j["created_at"],
                "has_anomaly": (j.get("result") or {}).get("overall_has_anomaly"),
                "error": j.get("error"),
                "elapsed_ms": (j.get("timings_ms") or {}).get("total"),
                "updated_at": j.get("updated_at"),
                "archived": bool(j.get("archived")),
                "archive": {k: v for k, v in (j.get("archive") or {}).items() if k != "files"},
                "input_image": (j.get("result") or {}).get("input_image"),
                "preview_image": ((j.get("result") or {}).get("scene_annotation")
                                  or next(iter((j.get("result") or {}).get("overlays") or []), None)
                                  or (j.get("result") or {}).get("input_image")),
            }
            for j in items[offset:offset + limit]
        ]

    def archive_job(self, job_id: str) -> dict:
        if Path(job_id).name != job_id or not job_id.startswith("JOB-"):
            raise KeyError(job_id)
        with self.lock:
            summary = self.jobs_root / job_id / "bridge_summary.json"
            if not summary.is_file():
                raise KeyError(job_id)
            job = self.jobs.get(job_id) or json.loads(summary.read_text(encoding="utf-8"))
            if job["status"] != "done":
                raise HTTPException(409, "检测完成后才可归档留存")
            job["archived"] = True
            job["updated_at"] = _now()
            self._persist_job(job)
            self.jobs[job_id] = job
        return {"ok": True, "job_id": job_id, "archived": True}

    def cancel_job(self, job_id: str) -> dict:
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            if job["status"] == "cancelled":
                return {"ok": True, "job_id": job_id, "status": "cancelled"}
            if job["status"] != "queued":
                raise HTTPException(409, "只能取消尚未开始的任务；正在推理的任务不会被强杀")
            job.update(status="cancelled", updated_at=_now())
            self._persist_job(job)
        return {"ok": True, "job_id": job_id, "status": "cancelled"}

    def retry_job(self, job_id: str) -> dict:
        job = self.get_job(job_id)
        if job.get("source") == "learning_evaluation":
            raise HTTPException(409, "评测任务请在持续改进中心重新发起整组回放")
        if job["status"] not in {"error", "cancelled"}:
            raise HTTPException(409, "仅失败或取消的任务支持重试；重试将产生新任务")
        image = self.media_path(job_id, job["image_name"])
        return self.create_job(
            source=job["source"], device_id=job["device_id"], data_mode=job["data_mode"],
            image_bytes=image.read_bytes(), filename=image.name, profile=job["profile"],
            stream_ref=job.get("stream_ref", ""), site_id=job.get("site_id", "SITE-DEFAULT"),
            screening=job.get("screening"), force_inspection=job.get("force_inspection", False),
            force_full_audit=job.get("force_full_audit", False),
            audit_interval_minutes=job.get("audit_interval_minutes"),
        )

    def media_path(self, job_id: str, filename: str) -> Path:
        try:
            self.get_job(job_id)
        except KeyError:
            raise HTTPException(404, "任务不存在") from None
        path = (self.jobs_root / job_id / filename).resolve()
        root = (self.jobs_root / job_id).resolve()
        if not path.is_relative_to(root):
            raise HTTPException(400, "非法路径")
        if not path.is_file():
            raise HTTPException(404, "文件不存在")
        return path

    # ---- 内部执行 ----

    @staticmethod
    def _persist_job(job: dict) -> None:
        out_dir = Path(job["output_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        temporary = out_dir / f"bridge_summary.{threading.get_ident()}.tmp"
        temporary.write_text(
            json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(out_dir / "bridge_summary.json")

    def _recover_interrupted_jobs(self) -> None:
        """Requeue jobs whose input was persisted before an unexpected bridge restart."""
        for summary in sorted(self.jobs_root.glob("JOB-*/bridge_summary.json")):
            try:
                job = json.loads(summary.read_text(encoding="utf-8"))
                if job.get("status") not in {"queued", "running"}:
                    continue
                job["output_dir"] = str(summary.parent)
                job["config_path"] = str(resolve_config(job.get("profile") or "demo", ROOT))
                input_path = summary.parent / str(job.get("image_name", ""))
                if not input_path.is_file():
                    job.update(status="error", error="重启恢复失败：原始图片缺失", updated_at=_now())
                    self._persist_job(job)
                    continue
                job["status"] = "queued"
                job["updated_at"] = _now()
                with self.lock:
                    self.jobs[job["job_id"]] = job
                try:
                    self.job_queue.put_nowait(job["job_id"])
                except queue.Full:
                    job.update(status="error", error="恢复队列已满，请从任务中心重试", updated_at=_now())
                self._persist_job(job)
            except (OSError, ValueError, KeyError, queue.Full):
                continue

    def cleanup_old_jobs(self) -> dict:
        """Remove completed/error job artifacts by age and total disk budget."""
        now = time.time()
        cutoff = now - self.retention_days * 86400
        candidates = []
        total_bytes = 0
        for directory in self.jobs_root.glob("JOB-*"):
            if not directory.is_dir():
                continue
            summary = directory / "bridge_summary.json"
            status = ""
            try:
                document = json.loads(summary.read_text(encoding="utf-8"))
                if document.get("archived"):
                    continue  # Archives are retained until explicitly removed, never as cache.
                status = document.get("status", "")
            except (OSError, ValueError):
                pass
            size = sum(path.stat().st_size for path in directory.rglob("*") if path.is_file())
            mtime = directory.stat().st_mtime
            total_bytes += size
            if status in {"done", "error"}:
                candidates.append((mtime, size, directory))
        removed = 0
        for mtime, size, directory in sorted(candidates):
            over_budget = total_bytes > self.retention_max_gb * 1024**3
            if mtime >= cutoff and not over_budget:
                continue
            with self.lock:
                try:
                    latest = json.loads((directory / "bridge_summary.json").read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if latest.get("archived"):
                    continue  # A user may have retained it after the initial scan.
                shutil.rmtree(directory, ignore_errors=True)
                if not directory.exists():
                    self.jobs.pop(directory.name, None)
                    total_bytes = max(0, total_bytes - size)
                    removed += 1
        return {"removed": removed, "remaining_bytes": total_bytes, "archives_excluded": True}

    def _job_worker(self) -> None:
        while True:
            job_id = self.job_queue.get()
            try:
                self._run_job(job_id)
            finally:
                self.job_queue.task_done()

    def _get_inspector(self, config_path: Path, config: Dict[str, Any]) -> Any:
        """Reuse heavy SAM3/CLIP adapters; the single GPU queue keeps them thread-safe."""
        from site_safety.factory import build_inspector

        cache_key = f"{config_path.resolve()}::{json.dumps(config, ensure_ascii=False, sort_keys=True, default=str)}"
        with self.model_lock:
            inspector = self.inspectors.get(cache_key)
            if inspector is None:
                inspector = build_inspector(config, ROOT)
                self.inspectors = {cache_key: inspector}
        return inspector

    def _set_stage(self, job: dict, stage_id: str, status: str, message: str = "") -> None:
        for stage in job["stages"]:
            if stage["id"] == stage_id:
                stage["status"] = status
                stage["message"] = message
                if status == "running":
                    stage["started_at"] = _now()
                if status in {"done", "error", "skipped"}:
                    stage["finished_at"] = _now()
        job["updated_at"] = _now()

    def _mark_before(self, job: dict, stage_id: str) -> None:
        self._set_stage(job, stage_id, "running")

    def _mark_done(self, job: dict, stage_id: str, message: str = "") -> None:
        self._set_stage(job, stage_id, "done", message)

    def _get_screener(self, config_path: Path, config: Dict[str, Any]) -> Any:
        del config_path  # screening configuration itself identifies a reusable model set
        key = json.dumps(config.get("screening", {}), ensure_ascii=False, sort_keys=True)
        with self.lock:
            screener = self.screeners.get(key)
            if screener is None:
                from site_safety.yolo_screening import YoloScreeningAdapter

                screener = YoloScreeningAdapter(
                    config=config.get("screening", {}),
                    project_root=ROOT,
                )
                self.screeners[key] = screener
        return screener

    @staticmethod
    def _trigger_schema_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        keys = {
            "triggered",
            "anomaly_score",
            "suspected_regions",
            "suspected_concepts",
            "source_model",
            "calibration_version",
            "reason",
        }
        return {key: value for key, value in payload.items() if key in keys}

    def _run_screening(
        self,
        job: dict,
        image_path: Path,
        out_dir: Path,
        config_path: Path,
        config: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        from site_safety.screening import parse_screening_trigger

        external = job.get("screening")
        if external is not None:
            trigger = parse_screening_trigger(external)
            payload = trigger.model_dump() if trigger is not None else None
            if payload is not None:
                (out_dir / "screening_trigger.json").write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            return payload

        screening_cfg = config.get("screening", {})
        if not screening_cfg.get("enabled", False):
            return None
        try:
            raw = self._get_screener(config_path, config).inspect(image_path, out_dir)
            detections = raw.get("detections", [])
            if detections:
                (out_dir / "yolo_detections.json").write_text(
                    json.dumps(detections, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            payload = self._trigger_schema_payload(raw)
            parse_screening_trigger(payload)
            (out_dir / "screening_trigger.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return payload
        except Exception as exc:  # fail open: never hide a frame because screening failed
            (out_dir / "screening_error.txt").write_text(str(exc), encoding="utf-8")
            job["screening_error"] = str(exc)
            return None

    def _claim_full_audit(
        self,
        job: dict,
        config: Dict[str, Any],
    ) -> tuple[bool, str]:
        """Atomically decide whether this frame must bypass YOLO guidance."""
        if job.get("source") != "camera":
            return False, ""
        screening_cfg = config.get("screening", {})
        default_interval = int(screening_cfg.get("scheduled_full_audit_minutes", 30))
        allowed = {
            int(value)
            for value in screening_cfg.get("allowed_full_audit_minutes", [30, 120])
        }
        requested = int(job.get("audit_interval_minutes") or default_interval)
        interval = requested if requested in allowed else default_interval
        job["audit_interval_minutes"] = interval
        device_id = str(job.get("device_id") or "CAM-DEFAULT")
        return self.audit_timer.claim(
            device_id,
            interval,
            force=bool(job.get("force_full_audit")),
            audit_on_first_frame=bool(screening_cfg.get("full_audit_on_first_frame", False)),
        )

    def _should_route_to_vlm(
        self,
        job: dict,
        trigger: Optional[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> tuple[bool, str]:
        if job.get("force_inspection") or job.get("source") != "camera":
            return True, "人工上传/强制检测"
        screening_cfg = config.get("screening", {})
        if not screening_cfg.get("gate_camera", True):
            return True, "摄像头门控已关闭"
        if trigger and trigger.get("triggered"):
            return True, "YOLO触发"
        if trigger is None:
            return True, "YOLO不可用，故障开放进入VLM"
        interval = int(job.get("audit_interval_minutes") or screening_cfg.get("scheduled_full_audit_minutes", 30))
        return False, f"YOLO未触发；等待后续帧或每{interval}分钟全图检测"

    def _finish_screened_only_job(
        self,
        job: dict,
        out_dir: Path,
        reason: str,
    ) -> None:
        for stage in job["stages"]:
            if stage["id"] not in {"ingest", "screen"} and stage["status"] == "pending":
                self._set_stage(job, stage["id"], "skipped", "实时初筛未触发，未调用重型模型")
        job["result"] = {
            "overall_has_anomaly": False,
            "risk_count": 0,
            "risks": [],
            "report_summary": reason,
            "input_image": self._media_url(job["job_id"], job["image_name"]),
            "overlays": [],
            "masks": [],
            "crops": [],
            "screening": job.get("screening"),
            "screening_overlay": self._media_url(job["job_id"], "screening_overlay.jpg")
            if (out_dir / "screening_overlay.jpg").is_file()
            else None,
            "screening_mask": self._media_url(job["job_id"], "screening_coarse_mask.png")
            if (out_dir / "screening_coarse_mask.png").is_file()
            else None,
            "routed_to_vlm": False,
            "artifacts": {"screening": True},
            "timings_ms": dict(job.get("timings_ms") or {}),
        }
        job["event"] = None
        job["status"] = "done"
        job["updated_at"] = _now()
        (out_dir / "bridge_summary.json").write_text(
            json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _run_job(self, job_id: str) -> None:
        total_started = time.perf_counter()
        with self.lock:
            job = self.jobs[job_id]
            if job.get("status") == "cancelled":
                return
            job["status"] = "running"
            job["timings_ms"] = {}
        self._persist_job(job)
        out_dir = Path(job["output_dir"])
        image_path = out_dir / job["image_name"]

        try:
            ingest_started = time.perf_counter()
            self._mark_before(job, "ingest")
            self._mark_done(job, "ingest", f"已接收 {image_path.name}")
            job["timings_ms"]["ingest"] = round((time.perf_counter() - ingest_started) * 1000, 1)

            # 按任务档位加载检测器（standard/offline/demo）
            from site_safety.runtime_settings import apply_runtime_settings, load_runtime_settings
            from site_safety.utils.config import load_yaml

            config_path = Path(job.get("config_path") or resolve_config(job.get("profile") or self.default_profile, ROOT))
            config = load_yaml(config_path)
            if job.get("profile") != "demo":
                config = apply_runtime_settings(config, load_runtime_settings())
                # Batch evaluation configs deliberately point at an empty
                # override file. Live platform jobs must consume thresholds
                # approved by the ReviewLearning Agent/admin UI.
                config.setdefault("pipeline", {})["threshold_overrides_path"] = (
                    "configs/road_threshold_overrides.json"
                )
            if job.get("learning_evaluation"):
                from site_safety.agents.continuous_learning import LearningStore
                run = LearningStore(job["learning_context"]["root"]).get("runs", job["learning_evaluation"]["run_id"])
                if run["status"] != "running" or run.get("cancel_requested"):
                    raise ValueError("回放已停止，不恢复过期评测任务")
                if config.get("mllm", {}).get("backend") != "openai_compatible" or config.get("sam3", {}).get("backend") != "bridge":
                    raise ValueError("真实回放禁止使用模拟视觉或模拟分割适配器")

            self._mark_before(job, "screen")
            screening_started = time.perf_counter()
            full_audit, full_audit_reason = self._claim_full_audit(job, config)
            if full_audit:
                trigger = None
                route = True
                route_reason = full_audit_reason
                job["screening"] = None
                job["screening_source"] = "bypassed_for_full_audit"
                job["full_audit"] = True
                job["audit_mode"] = "forced_full" if job.get("force_full_audit") else "scheduled_full"
                self._mark_done(job, "screen", f"{route_reason}；绕过YOLO提示直接检查完整图像")
            else:
                trigger = self._run_screening(job, image_path, out_dir, config_path, config)
                job["screening"] = trigger
                route, route_reason = self._should_route_to_vlm(job, trigger, config)
                job["audit_mode"] = "screened"
            job["routed_to_vlm"] = route
            job["timings_ms"]["screening"] = round((time.perf_counter() - screening_started) * 1000, 1)
            if full_audit:
                pass
            elif trigger is None:
                self._mark_done(job, "screen", f"初筛不可用；{route_reason}")
            elif trigger.get("triggered"):
                self._mark_done(
                    job,
                    "screen",
                    f"触发分数 {float(trigger.get('anomaly_score', 0)):.2f}；{route_reason}",
                )
            else:
                self._mark_done(job, "screen", route_reason)
            if not route:
                job["timings_ms"]["total"] = round((time.perf_counter() - total_started) * 1000, 1)
                self._finish_screened_only_job(job, out_dir, route_reason)
                return

            inspector = self._get_inspector(config_path, config)

            # 完整流水线（内部含初检/分割/核验/二检/报告）
            coarse_mask = out_dir / "screening_coarse_mask.png"
            screening_views = config.get("pipeline", {}).get("screening_region_views", {})
            include_mask_overlay = bool(screening_views.get("include_mask_overlay", True))
            pipeline_started = time.perf_counter()
            with self.inference_lock:
                if job.get("learning_evaluation"):
                    from site_safety.agents.continuous_learning import runtime_fingerprint
                    if runtime_fingerprint(ROOT, job["profile"]) != job["learning_fingerprint"]:
                        raise ValueError("回放开始前模型或配置变化")
                result = inspector.inspect(
                    image_path,
                    out_dir,
                    screening_trigger=trigger,
                    screening_mask_path=coarse_mask
                    if coarse_mask.is_file() and include_mask_overlay
                    else None,
                    progress_callback=lambda stage, status, detail="": self._set_stage(job, stage, status, detail),
                    **({"learning_context": job["learning_context"]} if "learning_context" in job else {}),
                )
            job["timings_ms"]["vlm_sam_pipeline"] = round(
                (time.perf_counter() - pipeline_started) * 1000, 1
            )

            # 推理智能体 + 事件契约
            self._mark_before(job, "reason")
            agent_started = time.perf_counter()
            event_payload = self._build_event(job, out_dir)
            job["timings_ms"]["agent_event"] = round(
                (time.perf_counter() - agent_started) * 1000, 1
            )
            self._mark_done(job, "reason", "已映射规范与风险等级")

            self._mark_before(job, "report")
            report_started = time.perf_counter()
            summary = self._build_frontend_result(job, out_dir, result, event_payload)
            job["timings_ms"]["result_compilation"] = round(
                (time.perf_counter() - report_started) * 1000, 1
            )
            self._mark_done(job, "report", "处置建议已生成")

            job["result"] = summary
            memory_trace = out_dir / "case_memory_references.json"
            if memory_trace.is_file():
                summary["case_memory"] = json.loads(memory_trace.read_text(encoding="utf-8"))
            if job.get("profile") == "demo" or job.get("source") == "learning_evaluation":
                business_sync = {
                    "ok": False,
                    "skipped": True,
                    "detail": "evaluation_not_persisted" if job.get("source") == "learning_evaluation" else "demo_profile_not_persisted",
                }
            else:
                business_sync = self._push_business_event(event_payload, job_id=job_id)
            job["business_sync"] = business_sync
            if isinstance(job.get("result"), dict):
                job["result"]["business_sync"] = business_sync
            job["timings_ms"]["total"] = round((time.perf_counter() - total_started) * 1000, 1)
            job["result"]["timings_ms"] = dict(job["timings_ms"])
            job["event"] = event_payload
            job["status"] = "done"
            job["updated_at"] = _now()
            (out_dir / "bridge_summary.json").write_text(
                json.dumps(job, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            job["status"] = "error"
            job["error"] = str(exc)
            job.setdefault("timings_ms", {})["total"] = round(
                (time.perf_counter() - total_started) * 1000, 1
            )
            job["updated_at"] = _now()
            for stage in job["stages"]:
                if stage["status"] == "running":
                    stage["status"] = "error"
                    stage["message"] = str(exc)
                    stage["finished_at"] = _now()
            (out_dir / "bridge_error.txt").write_text(str(exc), encoding="utf-8")
            self._persist_job(job)

    def _build_event(self, job: dict, out_dir: Path) -> Optional[dict]:
        try:
            from site_safety.agents import RiskReasoningAgent, build_event_from_output_dir
            from site_safety.agents.schemas import DeviceInfo

            reasoning = RiskReasoningAgent(ROOT / "examples" / "road_regulations.json")
            device = DeviceInfo(
                device_id=job["device_id"],
                device_type="fixed_camera" if job["source"] == "camera" else "offline_upload",
                site_id=job.get("site_id") or "SITE-DEFAULT",
                road_context=RoadContext.model_validate(job.get("road_context") or {}),
            )
            event = build_event_from_output_dir(
                out_dir,
                reasoning,
                data_mode=job.get("data_mode") or "offline",
                device=device,
                config_name=job.get("config_name") or Path(job.get("config_path", "")).name,
            )
            if event is None:
                return None
            payload = event.model_dump()
            # A restarted job must not create a second semantic event/work order.
            # Deriving the event id from job_id makes business ingestion idempotent.
            stable_job_id = str(job.get("job_id") or "")
            if stable_job_id:
                payload["event_id"] = self.stable_event_id(stable_job_id)
            payload.setdefault("pipeline", {})["job_id"] = job.get("job_id")
            return payload
        except Exception as exc:  # noqa: BLE001
            return {"error": f"event_build_failed: {exc}"}

    @staticmethod
    def stable_event_id(job_id: str) -> str:
        digest = hashlib.sha256(job_id.encode("utf-8")).hexdigest()[:16]
        return f"EVT-JOB-{digest}"

    def _push_business_event(
        self, event_payload: Optional[dict], *, job_id: str = "", persist_failure: bool = True
    ) -> dict:
        """把标准事件写入正式业务后台；失败不破坏检测结果，但写入任务状态。"""
        if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("ZNT_DISABLE_BUSINESS_PUSH") == "1":
            return {"ok": False, "detail": "business_push_disabled"}
        if not event_payload or event_payload.get("error"):
            return {"ok": False, "detail": "no_valid_event"}
        business_api = os.getenv("ZNT_BUSINESS_API", "http://127.0.0.1:8900").rstrip("/")
        if not business_api.endswith("/api"):
            business_api += "/api"
        req = urllib.request.Request(
            f"{business_api}/internal/ingest/event",
            data=json.dumps(event_payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Internal-Key": "local-detect-bridge"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                if job_id:
                    (self.pending_sync_dir / f"{job_id}.json").unlink(missing_ok=True)
                return {"ok": True, "response": json.loads(response.read().decode("utf-8"))}
        except Exception as exc:  # noqa: BLE001
            if persist_failure and event_payload:
                retry_path = self.pending_sync_dir / f"{job_id or uuid.uuid4().hex}.json"
                retry_path.write_text(
                    json.dumps({"job_id": job_id, "event": event_payload}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            return {"ok": False, "detail": str(exc)}

    def retry_business_sync(self) -> dict:
        attempted = succeeded = 0
        for retry_path in sorted(self.pending_sync_dir.glob("*.json")):
            attempted += 1
            try:
                payload = json.loads(retry_path.read_text(encoding="utf-8"))
                result = self._push_business_event(
                    payload.get("event"), job_id=payload.get("job_id", ""), persist_failure=False
                )
                if result.get("ok"):
                    retry_path.unlink(missing_ok=True)
                    succeeded += 1
            except (OSError, ValueError):
                continue
        return {"attempted": attempted, "succeeded": succeeded, "pending": attempted - succeeded}

    def _business_retry_loop(self) -> None:
        while True:
            try:
                self.retry_business_sync()
            except Exception as exc:  # noqa: BLE001
                print(f"[detect-bridge] business retry failed: {exc}", flush=True)
            time.sleep(30)

    def _build_frontend_result(
        self,
        job: dict,
        out_dir: Path,
        result: Any,
        event_payload: Optional[dict],
    ) -> dict:
        overlays = sorted(out_dir.glob("overlay_*.png"))
        masks = sorted(out_dir.glob("risk_mask_*.png"))
        crops = sorted(out_dir.glob("crop_*.*"))

        risks: List[dict] = []
        if event_payload and isinstance(event_payload, dict) and event_payload.get("risks"):
            for r in event_payload["risks"]:
                geom = r.get("geometry") or {}
                risks.append(
                    {
                        "risk_id": r.get("risk_id"),
                        "name": r.get("risk_name_zh") or r.get("risk_id"),
                        "verified": r.get("verified"),
                        "confidence": r.get("confidence"),
                        "level": r.get("risk_level"),
                        "level_zh": r.get("risk_level_zh"),
                        "manual_review": r.get("manual_review_required"),
                        "evidence_state": r.get("evidence_state", {}),
                        "description": r.get("risk_description") or "",
                        "suggestions": r.get("disposal_recommendations") or [],
                        "knowledge_references": r.get("knowledge_references") or [],
                        "knowledge_retrieval": r.get("knowledge_retrieval") or {},
                        "overlay": self._media_url(job["job_id"], Path(geom["overlay_path"]).name)
                        if geom.get("overlay_path")
                        else None,
                        "mask": self._media_url(job["job_id"], Path(geom["mask_path"]).name)
                        if geom.get("mask_path")
                        else None,
                    }
                )
        else:
            # 回退：从 visual_verification / result 粗提取
            vv_path = out_dir / "visual_verification.json"
            if vv_path.exists():
                vv = json.loads(vv_path.read_text(encoding="utf-8"))
                for item in vv.get(
                    "risks", vv.get("verified_risks", vv.get("final_risks", []))
                ) or []:
                    risks.append(
                        {
                            "risk_id": item.get("risk_id") or item.get("id"),
                            "name": item.get("risk_name_zh") or item.get("name") or "风险项",
                            "verified": item.get("verified", True),
                            "confidence": item.get("confidence", 0),
                            "level": item.get("risk_level") or "major",
                            "level_zh": item.get("risk_level_zh") or "",
                            "manual_review": item.get("manual_review_required", False),
                            "evidence_state": item.get("evidence_state", {}),
                            "description": item.get("risk_description") or item.get("analysis") or "",
                            "suggestions": item.get("disposal_recommendations") or [],
                            "overlay": None,
                            "mask": None,
                        }
                    )

        # Bind by risk identity: one missing mask must never borrow another risk's image.
        active_ids={str(r.get('risk_id')) for r in risks}
        overlays=[p for p in overlays if p.stem.removeprefix('overlay_') in active_ids]
        masks=[p for p in masks if p.stem.removeprefix('risk_mask_') in active_ids]
        for r in risks:
            for field,prefix in [('overlay','overlay_'),('mask','risk_mask_')]:
                match=next((p for p in (overlays if field=='overlay' else masks)
                            if p.stem==prefix+str(r.get('risk_id'))),None)
                if not r.get(field) and match:
                    r[field]=self._media_url(job['job_id'],match.name)

        report_summary = ""
        if getattr(result, "final_report", None) is not None:
            report_summary = getattr(result.final_report, "overall_summary", "") or ""
        summary_md = out_dir / "summary.md"
        if not report_summary and summary_md.exists():
            report_summary = summary_md.read_text(encoding="utf-8")[:500]

        quality = (event_payload or {}).get("assessment_quality", {})
        if not quality and (out_dir / "visual_verification.json").is_file():
            quality = json.loads((out_dir / "visual_verification.json").read_text(encoding="utf-8")).get("assessment_quality", {})
        return {
            "assessment_quality": quality,
            "scene_annotation": self._media_url(job['job_id'],'scene_annotation.png') if (out_dir/'scene_annotation.png').exists() else None,
            "issue_report": self._media_url(job["job_id"], "issue_report.md") if (out_dir / "issue_report.md").exists() else None,
            "has_candidates": bool(risks),
            "overall_has_anomaly": any(r.get("verified") for r in risks),
            "risk_count": len(risks),
            "risks": risks,
            "report_summary": report_summary,
            "input_image": self._media_url(job["job_id"], job["image_name"]),
            "overlays": [self._media_url(job["job_id"], p.name) for p in overlays],
            "masks": [self._media_url(job["job_id"], p.name) for p in masks],
            "crops": [self._media_url(job["job_id"], p.name) for p in crops[:6]],
            "screening": job.get("screening"),
            "screening_overlay": self._media_url(job["job_id"], "screening_overlay.jpg")
            if (out_dir / "screening_overlay.jpg").is_file()
            else None,
            "screening_mask": self._media_url(job["job_id"], "screening_coarse_mask.png")
            if (out_dir / "screening_coarse_mask.png").is_file()
            else None,
            "routed_to_vlm": True,
            "full_audit": bool(job.get("full_audit")),
            "audit_mode": job.get("audit_mode") or "screened",
            "audit_interval_minutes": job.get("audit_interval_minutes"),
            "artifacts": {
                "screening": (out_dir / "screening_trigger.json").exists()
                or (out_dir / "yolo_detections.json").exists(),
                "first_pass": (out_dir / "first_pass.json").exists(),
                "evidence": (out_dir / "evidence.json").exists(),
                "visual_verification": (out_dir / "visual_verification.json").exists(),
                "final_report": (out_dir / "final_report.json").exists(),
                "result": (out_dir / "result.json").exists(),
            },
        }

    @staticmethod
    def _media_url(job_id: str, filename: str) -> str:
        return f"/api/detect/jobs/{job_id}/media/{filename}"


def create_app(bridge: DetectBridge) -> FastAPI:
    app = FastAPI(title="Site Safety OpenRisk Detect Bridge", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/detect/health")
    def health() -> dict:
        return bridge.health()

    @app.post("/api/detect/learning-replay")
    def learning_replay(payload: dict) -> dict:
        from site_safety.agents.continuous_learning import LearningStore, runtime_fingerprint
        import secrets
        memory = LearningStore(Path(os.getenv("ZNT_LEARNING_DIR", str(ROOT / "road_app_data/continuous_learning"))))
        try:
            run = memory.get("runs", payload.get("run_id"))
            if not secrets.compare_digest(str(payload.get("token", "")), run["token"]):
                raise HTTPException(403, "回放凭据无效")
            if run["status"] != "running" or run.get("cancel_requested") or payload.get("arm") not in {"baseline", "candidate"}:
                raise ValueError("回放状态无效")
            case = next((c for c in run["cases"] if c["case_id"] == payload.get("case_id")), None)
            if case is None or case["partition"] == "train" or run["profile"] not in {"standard", "offline"}:
                raise ValueError("回放案例或真实模型档位无效")
            memory.snapshot_valid(case)
            version = memory.snapshot(run[payload["arm"]])
            if any(c["image_sha256"] == case["image_sha256"] or c["group_key"] == case["group_key"] for c in version["cases"]):
                raise ValueError("训练与评测数据交叉")
            if runtime_fingerprint(ROOT, run["profile"]) != run["fingerprint"]:
                raise ValueError("回放模型配置变化")
            image = memory.image(case)
            return bridge.create_job(source="learning_evaluation", device_id="REPLAY", data_mode="offline",
                image_bytes=image.read_bytes(), filename=image.name, profile=run["profile"], force_full_audit=True,
                learning_evaluation=dict(version_id=version["version_id"], group_key=case["group_key"],
                                         fingerprint=run["fingerprint"], run_id=run["run_id"], case_id=case["case_id"], arm=payload["arm"]))
        except (ValueError, KeyError, OSError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/detect/deployment")
    def get_deployment_guide() -> dict:
        from site_safety.deployment_service import deployment_manifest
        try:
            return deployment_manifest()
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc

    @app.post("/api/detect/deployment/check")
    def check_deployment(mode: Literal["demo", "offline", "cloud"] = "demo") -> dict:
        from site_safety.deployment_service import check_environment
        try:
            return check_environment(mode)
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/detect/runtime-settings")
    def get_runtime_settings() -> dict:
        from site_safety.runtime_settings import load_initial_settings, load_runtime_settings, validate_runtime_settings

        settings = load_runtime_settings()
        return {
            "settings": settings,
            "initial_settings": load_initial_settings(),
            "validation": validate_runtime_settings(settings),
        }

    @app.get("/api/detect/knowledge")
    def get_knowledge() -> dict:
        return bridge.knowledge_base.summary()

    @app.post("/api/detect/knowledge/upload")
    async def upload_knowledge(file: UploadFile = File(...)) -> dict:
        filename = Path(file.filename or "").name
        suffix = Path(filename).suffix.lower()
        if suffix not in {".md", ".txt", ".pdf", ".docx"}:
            raise HTTPException(400, "仅支持 md、txt、pdf、docx 规范文件")
        content = await file.read()
        if not content or len(content) > 30 * 1024 * 1024:
            raise HTTPException(400, "规范文件为空或超过30MB")
        try:
            chunk_count = bridge.knowledge_base.import_document(filename, content)
        except Exception as exc:
            raise HTTPException(422, f"规范导入失败：{exc}") from exc
        return {
            "ok": True,
            "filename": filename,
            "document_chunk_count": chunk_count,
            **bridge.knowledge_base.summary(),
        }

    @app.delete("/api/detect/knowledge/{filename}")
    def delete_knowledge(filename: str) -> dict:
        safe_name = Path(filename).name
        if safe_name != filename:
            raise HTTPException(400, "文件名无效")
        target = bridge.knowledge_base.kb_dir / safe_name
        if not target.is_file():
            raise HTTPException(404, "规范文件不存在")
        bridge.knowledge_base.delete_document(safe_name)
        return {"ok": True, **bridge.knowledge_base.summary()}

    @app.get("/api/detect/knowledge/search")
    def search_knowledge(q: str, top_k: int = 5) -> dict:
        query = q.strip()
        if not query:
            raise HTTPException(400, "请输入检索问题")
        return {"query": query, "hits": bridge.knowledge_base.search(query, top_k=min(max(top_k, 1), 20))}

    @app.put("/api/detect/runtime-settings/initial")
    def put_initial_runtime_settings(payload: RuntimeSettingsRequest) -> dict:
        from site_safety.runtime_settings import DEFAULTS, save_initial_settings, validate_runtime_settings

        unknown = sorted(set(payload.settings) - set(DEFAULTS))
        if unknown:
            raise HTTPException(422, f"未知设置字段: {', '.join(unknown)}")
        settings = save_initial_settings(payload.settings)
        return {"ok": True, "initial_settings": settings, "validation": validate_runtime_settings(settings)}

    @app.post("/api/detect/runtime-settings/reset-initial")
    def reset_runtime_settings_to_initial() -> dict:
        from site_safety.runtime_settings import load_initial_settings, save_runtime_settings, validate_runtime_settings

        current = load_initial_settings()
        if bridge.qwen_service.status(current).get("managed"):
            raise HTTPException(409, "Qwen正在运行，请先停止服务再恢复初始化配置")
        settings = save_runtime_settings(current)
        return {"ok": True, "settings": settings, "validation": validate_runtime_settings(settings)}

    @app.post("/api/detect/runtime-settings/discover")
    def discover_runtime_settings_endpoint(payload: RuntimeSettingsRequest) -> dict:
        from site_safety.runtime_settings import DEFAULTS, discover_runtime_settings, validate_runtime_settings

        unknown = sorted(set(payload.settings) - set(DEFAULTS))
        if unknown:
            raise HTTPException(422, f"未知设置字段: {', '.join(unknown)}")
        settings = discover_runtime_settings(payload.settings)
        return {"settings": settings, "validation": validate_runtime_settings(settings)}

    @app.put("/api/detect/runtime-settings")
    def put_runtime_settings(payload: RuntimeSettingsRequest) -> dict:
        from site_safety.runtime_settings import (
            DEFAULTS,
            load_runtime_settings,
            save_runtime_settings,
            validate_runtime_settings,
        )

        unknown = sorted(set(payload.settings) - set(DEFAULTS))
        if unknown:
            raise HTTPException(422, f"未知设置字段: {', '.join(unknown)}")
        current = load_runtime_settings()
        candidate = {**current, **payload.settings}
        candidate_validation = validate_runtime_settings(candidate)
        if not candidate_validation["qwen_base_url"]["ok"]:
            raise HTTPException(422, "Qwen地址必须是有效的 http(s) /v1/chat/completions 接口")
        qwen_changed = any(
            str(candidate.get(key)) != str(current.get(key))
            for key in ("qwen_model_path", "qwen_mmproj_path", "qwen_base_url")
        )
        if qwen_changed and bridge.qwen_service.status(current).get("managed"):
            raise HTTPException(409, "Qwen正在运行，请先停止服务再修改模型、mmproj或推理地址")
        settings = save_runtime_settings(payload.settings)
        return {
            "ok": True,
            "applies_to": "new_jobs",
            "settings": settings,
            "validation": validate_runtime_settings(settings),
        }

    @app.post("/api/detect/runtime-settings/pick-path")
    def pick_runtime_settings_path(payload: RuntimePathPickerRequest) -> dict:
        from site_safety.qwen_service import pick_runtime_path
        from site_safety.runtime_settings import PATH_KINDS

        kind = PATH_KINDS.get(payload.field)
        if kind is None:
            raise HTTPException(400, "不支持的模型路径字段")
        try:
            path = pick_runtime_path(payload.field, kind, payload.current)
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"selected": bool(path), "field": payload.field, "path": path}

    @app.get("/api/detect/qwen-service")
    def qwen_service_status() -> dict:
        from site_safety.runtime_settings import load_runtime_settings

        return bridge.qwen_service.status(load_runtime_settings())

    @app.post("/api/detect/qwen-service/start")
    def start_qwen_service() -> dict:
        from site_safety.runtime_settings import load_runtime_settings

        settings = load_runtime_settings()
        if not settings.get("qwen_enabled", True):
            raise HTTPException(409, "Qwen组件尚未激活，请先在模型部件与运行时中开启")
        try:
            return bridge.qwen_service.start(settings)
        except RuntimeError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/detect/qwen-service/stop")
    def stop_qwen_service() -> dict:
        from site_safety.runtime_settings import load_runtime_settings

        return bridge.qwen_service.stop(load_runtime_settings())

    @app.get("/api/detect/timers")
    def timer_status(interval_minutes: int = 30) -> dict:
        if interval_minutes not in {30, 120}:
            raise HTTPException(400, "interval_minutes 仅支持 30 或 120")
        return bridge.audit_timer.status(interval_minutes)

    @app.post("/api/detect/cloud-key")
    def set_cloud_key(payload: CloudKeyRequest) -> dict:
        """运行时写入云端 Key，可选持久化到 .env，便于前端「云端检测」一键配置。"""
        key = (payload.api_key or "").strip()
        if len(key) < 8:
            raise HTTPException(400, "API Key 无效")
        os.environ["DASHSCOPE_API_KEY"] = key
        os.environ["MLLM_API_KEY"] = key
        os.environ["QWEN_MLLM_API_KEY"] = key
        if payload.persist:
            env_path = ROOT / ".env"
            try:
                text = env_path.read_text(encoding="utf-8") if env_path.is_file() else ""
                lines = text.splitlines()
                written = False
                out: List[str] = []
                for line in lines:
                    if line.startswith("DASHSCOPE_API_KEY="):
                        out.append(f"DASHSCOPE_API_KEY={key}")
                        written = True
                    else:
                        out.append(line)
                if not written:
                    out.append(f"DASHSCOPE_API_KEY={key}")
                if "QWEN_MLLM_BASE_URL=" not in text:
                    out.append(
                        "QWEN_MLLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
                    )
                if "QWEN_MLLM_MODEL=" not in text:
                    out.append("QWEN_MLLM_MODEL=qwen-vl-plus")
                if "QWEN_REPORT_BASE_URL=" not in text:
                    out.append(
                        "QWEN_REPORT_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
                    )
                if "QWEN_REPORT_MODEL=" not in text:
                    out.append("QWEN_REPORT_MODEL=qwen-plus")
                env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
            except OSError as exc:
                raise HTTPException(500, f"写入 .env 失败: {exc}") from exc
        return {"ok": True, "persisted": payload.persist, **bridge.health()}

    @app.get("/api/detect/recent")
    def recent(limit: int = 20, offset: int = 0, status: str = "", archived_only: bool = False) -> dict:
        if not 1 <= limit <= 100:
            raise HTTPException(400, "limit 必须在 1 到 100 之间")
        if offset < 0 or status not in {"", "queued", "running", "done", "error", "cancelled"}:
            raise HTTPException(400, "分页或状态参数无效")
        return {"items": bridge.recent(limit, offset, status, archived_only)}

    @app.post("/api/detect/archives/import")
    def import_history(file: UploadFile = File(...)) -> dict:
        import zipfile
        from site_safety.detection_archive import import_archive, MAX_UPLOAD
        if not (file.filename or "").lower().endswith(".zip"):
            raise HTTPException(400, "请选择检测档案ZIP")
        file.file.seek(0, 2)
        size = file.file.tell()
        file.file.seek(0)
        if size > MAX_UPLOAD:
            raise HTTPException(413, "检测档案超过120MB，请分批导入")
        try:
            # Python 3.10's SpooledTemporaryFile lacks the seekable attribute
            # required by ZipFile, while the desktop runtime also supports 3.11+.
            return import_archive(bridge, io.BytesIO(file.file.read()))
        except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile) as exc:
            raise HTTPException(422, f"档案导入失败：{exc}") from exc

    @app.post("/api/detect/jobs/{job_id}/archive")
    def archive_job(job_id: str) -> dict:
        try:
            return bridge.archive_job(job_id)
        except KeyError:
            raise HTTPException(404, "任务不存在") from None

    @app.post("/api/detect/jobs/{job_id}/cancel")
    def cancel_job(job_id: str) -> dict:
        try:
            return bridge.cancel_job(job_id)
        except KeyError:
            raise HTTPException(404, "任务不存在") from None

    @app.post("/api/detect/jobs/{job_id}/retry")
    def retry_job(job_id: str) -> dict:
        try:
            return bridge.retry_job(job_id)
        except KeyError:
            raise HTTPException(404, "任务不存在") from None

    @app.post("/api/detect/business-sync/retry")
    def retry_business_sync() -> dict:
        """Immediately retry events retained while the business API was unavailable."""
        return bridge.retry_business_sync()

    @app.post("/api/detect/jobs/cleanup")
    def cleanup_jobs() -> dict:
        return bridge.cleanup_old_jobs()

    @app.get("/api/detect/jobs/{job_id}")
    def get_job(job_id: str) -> dict:
        try:
            return bridge.get_job(job_id)
        except KeyError:
            raise HTTPException(404, "任务不存在") from None

    @app.get("/api/detect/jobs/{job_id}/media/{filename}")
    def media(job_id: str, filename: str) -> FileResponse:
        path = bridge.media_path(job_id, filename)
        return FileResponse(path)

    @app.post("/api/detect/upload")
    async def upload(
        file: UploadFile = File(...),
        device_id: str = Form("OFFLINE-UPLOAD"),
        data_mode: str = Form("offline"),
        site_id: str = Form("SITE-DEFAULT"),
        profile: str = Form(""),
        screening_json: str = Form(""),
        force_inspection: bool = Form(True),
    ) -> dict:
        raw = await file.read()
        if not raw:
            raise HTTPException(400, "空文件")
        if len(raw) > 25 * 1024 * 1024:
            raise HTTPException(400, "文件过大（限制 25MB）")
        _validate_image_bytes(raw)
        screening = None
        if screening_json.strip():
            try:
                screening = json.loads(screening_json)
            except json.JSONDecodeError as exc:
                raise HTTPException(422, f"screening_json无效: {exc}") from exc
            screening = _validate_screening_payload(screening)
        return bridge.create_job(
            source="upload",
            device_id=device_id,
            data_mode=data_mode,
            image_bytes=raw,
            filename=file.filename or "upload.jpg",
            site_id=site_id,
            profile=profile,
            screening=screening,
            force_inspection=force_inspection,
        )

    @app.post("/api/detect/camera-frame")
    def camera_frame(payload: CameraFrameRequest) -> dict:
        b64 = payload.image_base64
        if "," in b64:
            b64 = b64.split(",", 1)[1]
        try:
            raw = base64.b64decode(b64, validate=True)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, f"base64 解码失败: {exc}") from exc
        if not raw:
            raise HTTPException(400, "空图像")
        if len(raw) > 25 * 1024 * 1024:
            raise HTTPException(400, "图像过大（限制 25MB）")
        _validate_image_bytes(raw)
        screening = _validate_screening_payload(payload.screening) if payload.screening is not None else None
        return bridge.create_job(
            source="camera",
            device_id=payload.device_id,
            data_mode="realtime",
            image_bytes=raw,
            filename="camera_frame.jpg",
            stream_ref=payload.stream_ref,
            road_context=payload.road_context.model_dump(),
            site_id=payload.site_id,
            profile=payload.profile,
            screening=screening,
            force_inspection=payload.force_inspection,
            force_full_audit=payload.force_full_audit,
            audit_interval_minutes=payload.audit_interval_minutes,
        )

    @app.post("/api/detect/full-audit")
    def full_audit(payload: CameraFrameRequest) -> dict:
        """Bypass YOLO guidance and run a complete-image VLM audit immediately."""
        return camera_frame(
            payload.model_copy(
                update={"force_inspection": True, "force_full_audit": True, "screening": None}
            )
        )

    return app


def _validate_image_bytes(raw: bytes) -> None:
    """Reject corrupt/non-image payloads before a background job is queued."""
    try:
        with Image.open(io.BytesIO(raw)) as image:
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(400, "上传内容不是有效图像") from exc


def _validate_screening_payload(value: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from site_safety.screening import parse_screening_trigger

        trigger = parse_screening_trigger(value)
        if trigger is None:
            raise ValueError("screening不可为空")
        return trigger.model_dump()
    except Exception as exc:
        raise HTTPException(422, f"ScreeningTrigger结构无效: {exc}") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Frontend detect bridge for Site Safety OpenRisk")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8810)
    parser.add_argument(
        "--profile",
        default="",
        help="默认业务档位：standard | offline | demo（空则自动探测）",
    )
    parser.add_argument(
        "--config",
        default="",
        help="兼容旧参数：若传入 yaml，则映射为对应档位默认值",
    )
    return parser.parse_args()


def _profile_from_legacy_config(config: str) -> str:
    name = Path(config).name.lower()
    road_profiles = {"road_demo.yaml": "demo", "road_offline.yaml": "offline", "road_standard.yaml": "standard"}
    if name in road_profiles:
        return road_profiles[name]
    if "qwen_visual" in name:
        return "standard"
    if "local_models" in name or "qwen_local" in name or "zero_cost" in name:
        return "offline"
    if "default" in name:
        return "demo"
    return ""


def main() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except Exception:
        pass

    args = parse_args()
    # When no profile was explicitly supplied, keep submission-time selection
    # dynamic so settings completed after startup can activate the offline mode.
    configured_profile = args.profile or _profile_from_legacy_config(args.config)
    bridge = DetectBridge(default_profile=configured_profile)
    if bridge.default_profile == "offline":
        bridge.autostart_models()
    app = create_app(bridge)
    print(f"[detect-bridge] default_profile={bridge.default_profile}")
    print(f"[detect-bridge] profiles={[p['id'] + (':ready' if p['ready'] else ':need-setup') for p in list_profiles(ROOT)]}")
    print(f"[detect-bridge] http://{args.host}:{args.port}/api/detect/health")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
