"""Portable detection history, with original evidence retained byte for byte.

Import creates completed, retention-protected jobs. It never runs inference,
dispatches business events, or turns model predictions into human verdicts.
"""
from __future__ import annotations

import hashlib
import json
import re
import stat
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath

from PIL import Image

from site_safety.agents.schemas import DetectionEvent

FORMAT = "smartroad-detection-archive-v1"
MANIFEST = "detection-archive.json"
MAX_UPLOAD = 120 * 1024**2
MAX_EXPANDED = 512 * 1024**2
ALLOWED = {".json", ".md", ".txt", ".png", ".jpg", ".jpeg", ".webp", ".bmp"}
REQUIRED = {"detection_event.json", "visual_verification.json", "result.json"}


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _safe_name(value):
    if (not isinstance(value, str) or not value or value in {".", ".."}
            or re.search(r'[\\/:<>"|?*\x00-\x1f]', value) or value.endswith((".", " "))
            or value.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(10)], *[f"LPT{i}" for i in range(10)]}):
        raise ValueError("档案包含非法文件名")
    return value


def build_archive(destination, *, title, items):
    """items: sample_id, output_dir, image_name and optional dataset/elapsed_ms."""
    manifest = {"format": FORMAT, "title": title, "items": []}
    sources = []
    for item in items:
        sample = _safe_name(item["sample_id"])
        folder = Path(item["output_dir"])
        entry = {k: item[k] for k in ("sample_id", "image_name", "dataset", "elapsed_ms") if k in item}
        entry["files"] = []
        for path in sorted(folder.iterdir()):
            if not path.is_file() or path.suffix.lower() not in ALLOWED or path.name == "bridge_summary.json":
                continue
            _safe_name(path.name)
            data = path.read_bytes()
            name = f"samples/{sample}/{path.name}"
            entry["files"].append({"name": path.name, "bytes": len(data), "sha256": _digest(data)})
            sources.append((name, data))
        manifest["items"].append(entry)
    if len(_json_bytes(manifest)) > 4 * 1024**2 or sum(len(v) for _, v in sources) > MAX_EXPANDED:
        raise ValueError("档案过大，请分批导出")
    with zipfile.ZipFile(destination, "x", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(MANIFEST, _json_bytes(manifest))
        for name, data in sources:
            archive.writestr(name, data)
    return manifest


def import_archive(bridge, stream):
    """Validate the entire ZIP before publishing any job; retries are idempotent."""
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    with zipfile.ZipFile(stream) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(infos) > 8000 or len(set(n.casefold() for n in names)) != len(names):
            raise ValueError("档案文件数量过多或存在重名文件")
        if sum(i.file_size for i in infos) > MAX_EXPANDED:
            raise ValueError("解压后超过512MB，请分批导入")
        for info in infos:
            path = PurePosixPath(info.filename)
            if (path.is_absolute() or str(path) != info.filename or info.is_dir()
                    or stat.S_ISLNK(info.external_attr >> 16)):
                raise ValueError("档案路径非法或包含链接")
            for part in path.parts:
                _safe_name(part)
        if MANIFEST not in names or archive.getinfo(MANIFEST).file_size > 4 * 1024**2:
            raise ValueError("请选择检测档案ZIP，普通HTML报告不能恢复原始检测记录")
        manifest = json.loads(archive.read(MANIFEST))
        if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
            raise ValueError("不支持的检测档案格式")
        entries = manifest.get("items")
        if not isinstance(entries, list) or not 1 <= len(entries) <= 1000:
            raise ValueError("检测档案必须包含1至1000条记录")
        expected = {MANIFEST}
        seen_samples = set()
        prepared = []
        bridge.jobs_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".archive-import-", dir=bridge.jobs_root) as staging:
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(entry.get("files"), list):
                    raise ValueError("档案记录或文件清单格式错误")
                sample = _safe_name(entry["sample_id"])
                if sample.casefold() in seen_samples:
                    raise ValueError("样本编号重复")
                seen_samples.add(sample.casefold())
                image_name = _safe_name(entry["image_name"])
                records = entry["files"]
                if any(not isinstance(f, dict) for f in records):
                    raise ValueError("档案文件清单格式错误")
                file_names = [_safe_name(f["name"]) for f in records]
                if (len(set(n.casefold() for n in file_names)) != len(file_names)
                        or not REQUIRED.issubset(file_names) or image_name not in file_names
                        or "bridge_summary.json" in file_names):
                    raise ValueError(f"{sample} 缺少原图/结构化结果，或文件重复")
                identity = _digest(_json_bytes(entry))
                job_id = "JOB-ARCHIVE-" + identity[:24]
                folder = Path(staging) / job_id
                folder.mkdir()
                for record in records:
                    name = record["name"]
                    if Path(name).suffix.lower() not in ALLOWED:
                        raise ValueError("检测档案仅支持图像和文本证据")
                    zipped = f"samples/{sample}/{name}"
                    expected.add(zipped)
                    data = archive.read(zipped)
                    if len(data) != record["bytes"] or _digest(data) != record["sha256"]:
                        raise ValueError(f"{sample}/{name} 校验失败，未导入")
                    (folder / name).write_bytes(data)
                with Image.open(folder / image_name) as image:
                    image.verify()
                event = DetectionEvent.model_validate_json((folder / "detection_event.json").read_text(encoding="utf-8")).model_dump()
                # Keep source files unchanged. Only the service view uses local media paths.
                target = bridge.jobs_root / job_id
                event["media"]["image_path"] = str(target / image_name)
                for risk in event["risks"]:
                    for key in ("overlay_path", "mask_path", "crop_path"):
                        value = risk["geometry"].get(key)
                        if value:
                            name = PureWindowsPath(value).name
                            if name not in file_names:
                                raise ValueError(f"{sample} 缺少引用的图像：{name}")
                            risk["geometry"][key] = str(target / name)
                detected_at = event["time"]["detected_at"]
                job = {
                    "job_id": job_id, "status": "done", "source": "archive",
                    "data_mode": "offline", "profile": "archive", "image_name": image_name,
                    "device_id": event["device"]["device_id"], "site_id": event["device"]["site_id"],
                    "created_at": detected_at, "updated_at": now, "output_dir": str(folder),
                    "event": event, "error": None, "archived": True,
                    "archive": {"identity": identity, "batch_title": str(manifest.get("title", ""))[:200],
                                "sample_id": sample, "dataset": str(entry.get("dataset", "未注明"))[:200],
                                "imported_at": now, "original_event_id": event["event_id"],
                                "original_pipeline": event["pipeline"], "files": records},
                    "stages": [{"id": "archive", "name": "历史检测归档", "agent": "档案管理",
                                "status": "done", "message": "原始证据校验通过；未重新推理，保留原检测结论。"}],
                    "timings_ms": {"total": entry.get("elapsed_ms")},
                    "business_sync": {"ok": False, "skipped": True, "detail": "historical_archive_no_dispatch"},
                }
                job["result"] = bridge._build_frontend_result(job, folder, None, event)
                job["result"]["business_sync"] = job["business_sync"]
                bridge._persist_job(job)
                prepared.append((folder, target, job))
            if set(names) != expected:
                raise ValueError("档案包含未登记文件或缺少登记文件")
            imported, existing = [], []
            with bridge.lock:
                for folder, target, job in prepared:
                    if target.exists():
                        old = json.loads((target / "bridge_summary.json").read_text(encoding="utf-8"))
                        if old.get("archive", {}).get("identity") != job["archive"]["identity"]:
                            raise ValueError("历史记录编号冲突，未覆盖已有记录")
                        for record in job["archive"]["files"]:
                            existing_file = target / record["name"]
                            if (not existing_file.is_file() or existing_file.is_symlink()
                                    or _digest(existing_file.read_bytes()) != record["sha256"]):
                                raise ValueError("已有档案证据缺失或损坏，请先备份并核查：" + str(existing_file))
                for folder, target, job in prepared:
                    if target.exists():
                        existing.append(job["job_id"])
                        continue
                    job["output_dir"] = str(target)
                    (folder / "bridge_summary.json").write_bytes(_json_bytes(job))
                    folder.rename(target)
                    bridge.jobs[job["job_id"]] = job
                    imported.append(job["job_id"])
            return {"ok": True, "imported": len(imported), "existing": len(existing), "job_ids": imported + existing}
