"""Reviewed road cases, immutable memory versions and evidence-based replay gates.

The business service is the sole writer. The detection process only reads immutable
snapshots; neither predictions nor demonstration data are promoted to ground truth.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import secrets
import threading
from datetime import datetime
from pathlib import Path

from PIL import Image
from site_safety.utils.json_store import read_json, update_json

ROOT = Path(__file__).resolve().parents[2]
KINDS = {"false_positive", "false_negative", "wrong_category", "localization", "novel_class", "normal", "uncertain"}
PARTITIONS = {"train", "validation", "holdout"}


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value):
        raise ValueError("记录编号无效")
    return value


def write(path, value):
    return update_json(Path(path), lambda doc: (doc.clear(), doc.update(value)), {})


def validate_feedback(data, catalog):
    kind, partition = data.get("kind"), data.get("partition", "train")
    if not isinstance(kind, str) or not isinstance(partition, str) or kind not in KINDS or partition not in PARTITIONS:
        raise ValueError("请选择纠错类型和数据用途")
    reason = str(data.get("reason", "")).strip()
    group = str(data.get("group_key", "")).strip()
    if not 4 <= len(reason) <= 2000 or not 3 <= len(group) <= 160:
        raise ValueError("请填写至少4字的可见证据和来源分组（同一视频/同一采集批次使用相同分组）")
    complete = data.get("complete") is True
    labels = data.get("labels", [])
    if not isinstance(labels, list) or len(labels) > 30:
        raise ValueError("单张图最多标注30项")
    allowed = {row["risk_id"] for row in catalog}
    from site_safety.road_domain import LEGACY_RISK_IDS
    cleaned = []
    for label in labels:
        if not isinstance(label, dict):
            raise ValueError("人工标签必须是结构化对象")
        rid = label.get("risk_id", "")
        if not isinstance(rid, str) or (rid not in allowed and not re.fullmatch(r"open_[a-z0-9_]{2,60}", rid)) or rid.removeprefix("open_") in LEGACY_RISK_IDS:
            raise ValueError("风险类别须为道路目录项或 open_ 开头的新类别")
        name = str(label.get("name", "")).strip()
        if not 1 <= len(name) <= 100 or type(label.get("present")) is not bool:
            raise ValueError("请填写类别名称和存在/不存在判断")
        box = label.get("bbox")
        if box is not None:
            if (not isinstance(box, list) or len(box) != 4 or
                any(type(x) not in (int, float) or not math.isfinite(x) or not 0 <= x <= 1 for x in box) or
                box[0] >= box[2] or box[1] >= box[3]):
                raise ValueError("标注框必须是有效的图像归一化范围")
            if not label["present"]:
                raise ValueError("不存在的风险无需画框")
        cleaned.append({"risk_id": rid, "name": name, "present": label["present"], "bbox": box})
    ids = [item["risk_id"] for item in cleaned]
    if len(ids) != len(set(ids)):
        raise ValueError("同类目标请合并到一个范围框；当前版本按图像类别评测")
    if kind == "normal" and (not complete or any(item["present"] for item in cleaned)):
        raise ValueError("正常样本必须完成整图复查，且无确认异常")
    if kind not in {"normal", "uncertain"} and not cleaned:
        raise ValueError("请添加至少一项人工判断")
    if kind in {"false_negative", "localization", "novel_class"} and not any(x["present"] and x["bbox"] for x in cleaned):
        raise ValueError("漏检、定位纠正或新类别须提供可见目标范围框")
    if kind == "false_positive" and not any(not x["present"] for x in cleaned):
        raise ValueError("误报纠正须明确排除的风险类别")
    if kind == "novel_class" and not any(x["risk_id"].startswith("open_") for x in cleaned):
        raise ValueError("新类别请填写 open_ 开头的候选编号")
    if kind == "wrong_category" and not ({True, False} <= {x["present"] for x in cleaned}):
        raise ValueError("类别纠正须同时填写原类别不存在和正确类别存在")
    if partition != "train" and (not complete or kind == "uncertain"):
        raise ValueError("评测样本必须是整图复核且结论明确")
    return dict(kind=kind, partition=partition, reason=reason, group_key=group, complete=complete, labels=cleaned)


class LearningStore:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def path(self, kind, ident):
        if kind not in {"cases", "versions", "runs"}:
            raise ValueError("记录类型无效")
        return self.root / kind / (safe_id(ident) + ".json")

    def get(self, kind, ident):
        path = self.path(kind, ident)
        if not path.is_file():
            raise ValueError("记录不存在")
        return read_json(path, {})

    def rows(self, kind):
        return [read_json(p, {}) for p in sorted((self.root / kind).glob("*.json"), reverse=True)]

    def active(self):
        return read_json(self.root / "active.json", {"version_id": "none", "history": []})

    def image(self, case):
        relative = case["image"]
        path = (self.root / relative).resolve()
        if not path.is_relative_to((self.root / "images").resolve()) or not path.is_file():
            raise ValueError("案例原图缺失或路径无效")
        if file_hash(path) != case["image_sha256"]:
            raise ValueError("案例原图校验失败")
        return path

    def submit(self, data, job, image_path, catalog, reviewer):
        feedback = validate_feedback(data, catalog)
        if job.get("status") != "done" or job.get("profile") == "demo" or job.get("source") == "learning_evaluation":
            raise ValueError("仅支持已完成的真实检测或历史档案，演示和回放结果不能作为新标注来源")
        image_path = Path(image_path)
        with Image.open(image_path) as im:
            width, height = im.size
            im.verify()
        content = image_path.read_bytes()
        sha = hashlib.sha256(content).hexdigest()
        with self.lock:
            ident = "CASE-" + datetime.now().strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(4)
            relative = f"images/{ident}{image_path.suffix.lower()}"
            (self.root / "images").mkdir(exist_ok=True)
            (self.root / relative).write_bytes(content)
            row = dict(feedback, case_id=ident, job_id=job["job_id"], image=relative, image_sha256=sha,
                       width=width, height=height, created_at=now(), submitted_by=reviewer,
                       status="pending", reviews=[], original_result=copy.deepcopy(job.get("result", {})),
                       source=dict(profile=job.get("profile"), device_id=job.get("device_id"),
                                   archive=job.get("archive", {}), created_at=job.get("created_at")))
            write(self.path("cases", ident), row)
            return row

    def review(self, ident, decision, reviewer, note):
        if decision not in {"approved", "rejected", "withdrawn"} or not str(note).strip():
            raise ValueError("审核结论或依据缺失")
        with self.lock:
            row = self.get("cases", ident)
            if decision == "approved":
                if row["kind"] == "uncertain":
                    raise ValueError("无法判断的样本需补充证据后重新提交，不能用于学习")
                self.image(row)
                for other in self.rows("cases"):
                    if other["case_id"] == ident or other["status"] != "approved":
                        continue
                    same_image = other["image_sha256"] == row["image_sha256"]
                    same_group = other["group_key"] == row["group_key"]
                    if (same_image or same_group) and other["partition"] != row["partition"]:
                        raise ValueError("同图或同来源分组不能同时进入训练、验证和保留测试集")
                    if same_image:
                        raise ValueError("此图已有审核样本，请先撤回旧样本再批准新标注")
            # Used versions remain immutable, but can no longer be activated if a
            # reviewer withdraws a source case. Active versions are suspended too.
            row["status"] = decision
            row["reviews"].append(dict(decision=decision, reviewer=reviewer, note=str(note)[:2000], time=now()))
            write(self.path("cases", ident), row)
            return row

    def snapshot_valid(self, case):
        current = self.get("cases", case["case_id"])
        if current["status"] != "approved" or digest(current) != digest(case):
            raise ValueError("来源案例审核状态发生变化，请重建版本并重跑评测")
        self.image(case)

    def build_version(self, creator):
        with self.lock:
            cases = [r for r in self.rows("cases") if r["status"] == "approved" and r["partition"] == "train"]
            if not cases:
                raise ValueError("尚无审核通过的训练案例")
            if len(cases) > 1000:
                raise ValueError("小试经验版本最多1000个案例，请先整理样本")
            for case in cases:
                self.image(case)
            ident = "MEM-" + datetime.now().strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(3)
            version = dict(version_id=ident, created_at=now(), creator=creator, cases=cases,
                           digest=digest(cases), method="reviewed-text-bigram-top2-v1")
            write(self.path("versions", ident), version)
            return version

    def snapshot(self, ident):
        if ident == "none":
            return {"version_id": "none", "cases": [], "digest": digest([])}
        version = self.get("versions", ident)
        if version["digest"] != digest(version["cases"]):
            raise ValueError("经验版本校验失败")
        for case in version["cases"]:
            if case["partition"] != "train":
                raise ValueError("评测数据不得进入案例检索")
            self.snapshot_valid(case)
        return version

    def activate(self, run_id, reviewer, fingerprint):
        with self.lock:
            run = self.get("runs", run_id)
            if run.get("status") != "done" or run.get("cancel_requested") or not (run.get("gate") or {}).get("passed"):
                raise ValueError("仅能启用通过真实模型回放门槛的候选版本")
            if run["baseline"] != self.active()["version_id"] or run["fingerprint"] != fingerprint:
                raise ValueError("当前版本或运行配置已变化，请重新回放")
            self.snapshot(run["candidate"])
            for case in run["cases"]:
                self.snapshot_valid(case)
            active = self.active()
            active["history"].append(dict(from_version=active["version_id"], to_version=run["candidate"],
                                          run_id=run_id, reviewer=reviewer, time=now(), action="activate"))
            active.update(version_id=run["candidate"], run_id=run_id, fingerprint=fingerprint, updated_at=now())
            write(self.root / "active.json", active)
            return active

    def rollback(self, reviewer):
        # A safe, deterministic rollback to the original pipeline; arbitrary
        # older versions cannot bypass their source-review validity checks.
        with self.lock:
            active = self.active()
            active["history"].append(dict(from_version=active["version_id"], to_version="none", reviewer=reviewer, time=now(), action="rollback"))
            active.update(version_id="none", updated_at=now())
            write(self.root / "active.json", active)
            return active


def _tokens(text):
    text = re.sub(r"\s+", "", text.lower())
    return set(re.findall(r"[a-z0-9_]+", text)) | {text[i:i+2] for i in range(len(text)-1)}


def retrieve_cases(snapshot, observation, image_sha256, group_key=""):
    """Lexical scene retrieval, deliberately not advertised as visual similarity."""
    query = _tokens(json.dumps(observation, ensure_ascii=False))
    matches = []
    for case in snapshot.get("cases", []):
        if case["partition"] != "train" or case["status"] != "approved":
            continue
        if case["image_sha256"] == image_sha256 or (group_key and case["group_key"] == group_key):
            continue
        tokens = _tokens(case["reason"] + " " + " ".join(x["name"] for x in case["labels"]))
        score = len(query & tokens) / max(1, len(query | tokens))
        if score > 0.01:
            matches.append((score, case))
    matches.sort(key=lambda pair: (-pair[0], pair[1]["case_id"]))
    return [(round(score, 5), case) for score, case in matches[:2]]


def box_iou(a, b):
    if not a or not b:
        return 0.0
    intersect = max(0, min(a[2], b[2])-max(a[0], b[0])) * max(0, min(a[3], b[3])-max(a[1], b[1]))
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - intersect
    return intersect / union if union > 0 else 0.0


def score_case(case, job):
    if job.get("status") != "done" or job.get("profile") not in {"standard", "offline"}:
        raise ValueError("评测必须使用完成的真实模型任务")
    result = job.get("result") or {}
    risks = (job.get("event") or {}).get("risks", result.get("risks", []))
    positive = {x["risk_id"] for x in case["labels"] if x["present"]}
    negative = {x["risk_id"] for x in case["labels"] if not x["present"]}
    predicted = {x["risk_id"] for x in risks if x.get("verified") is True}
    candidates = {x["risk_id"] for x in risks}
    fp = predicted-positive if case["complete"] else predicted & negative
    fn = positive-predicted
    abstain = (result.get("assessment_quality") or {}).get("result_status") == "unable_to_assess"
    boxes = {}
    for label in case["labels"]:
        if label["present"] and label["bbox"]:
            pred_boxes = [(r.get("geometry") or {}).get("bbox_xyxy_norm") or r.get("bbox_xyxy_norm")
                          for r in risks if r["risk_id"] == label["risk_id"] and r.get("verified") is True]
            boxes[label["risk_id"]] = max([box_iou(label["bbox"], b) for b in pred_boxes] or [0.0])
    return dict(case_id=case["case_id"], job_id=job["job_id"], fp=sorted(fp), fn=sorted(fn),
                tp=sorted(positive & predicted), candidate_misses=sorted(positive-candidates),
                abstain=bool(abstain), normal=not positive and case["complete"], box_iou=boxes)


def regression_gate(cases, results, version):
    reasons = []
    if len(cases) < 4 or len({x["group_key"] for x in cases}) < 2:
        reasons.append("至少4张整图复核样本、2个独立来源分组")
    if not any(not any(l["present"] for l in c["labels"]) for c in cases):
        reasons.append("缺少正常场景对照")
    positive_ids = {l["risk_id"] for c in cases for l in c["labels"] if l["present"]}
    affected_ids = {l["risk_id"] for c in version["cases"] for l in c["labels"]}
    if not positive_ids or not affected_ids <= positive_ids:
        reasons.append("评测未覆盖经验版本涉及的全部风险类别的正例")
    if not any(l["present"] and l["bbox"] for c in cases for l in c["labels"]):
        reasons.append("缺少人工范围框，无法验证定位")
    if len(results) != len(cases):
        reasons.append("回放结果不完整")
    improvement = False
    for result in results:
        before, after = result["baseline"], result["candidate"]
        for metric in ("fp", "fn", "candidate_misses"):
            if set(after[metric])-set(before[metric]):
                reasons.append(result["case_id"] + " 新增" + metric)
            improvement |= bool(set(before[metric])-set(after[metric]))
        if after["abstain"]:
            reasons.append(result["case_id"] + " 候选版本无法判断")
        for rid, old_iou in before["box_iou"].items():
            new_iou = after["box_iou"].get(rid, 0)
            if new_iou + 0.02 < old_iou:
                reasons.append(result["case_id"] + " 定位范围退步：" + rid)
            improvement |= new_iou > old_iou + 0.05
    if not improvement:
        reasons.append("尚未观察到误报、漏检或范围定位的改善")
    return dict(passed=not reasons, reasons=reasons, scope="实验室所选样本的配对回放；不代表全场景精度或像素掩码质量", sample_count=len(cases))


def runtime_fingerprint(root, profile):
    """Hash code/config and model identities, never return keys or raw settings."""
    from site_safety.runtime_settings import load_runtime_settings
    root = Path(root)
    parts = {"profile": profile, "runtime": load_runtime_settings()}
    paths = list((root / "site_safety").rglob("*.py")) + list((root / "configs").glob("road*"))
    paths += list((root / "examples").glob("road*.json")) + [root / "detect_bridge.py", root / "learning_service.py", root / ".env"]
    parts["files"] = {str(p.relative_to(root)): file_hash(p) for p in paths if p.is_file()}
    parts["weights"] = {}
    for key, value in parts["runtime"].items():
        if key.endswith("_path") and isinstance(value, str) and Path(value).is_file():
            stat = Path(value).stat()
            parts["weights"][key] = [value, stat.st_size, stat.st_mtime_ns]
    return digest(parts)
