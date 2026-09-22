"""正式软件后端（FastAPI + SQLite + WebSocket + 角色鉴权）。

与演示服务(serve_demo.py)API同构，前端demo_ui无缝复用；差异：
- SQLite持久化（文档式存储，契约JSON整体入库，按kind/status/site索引）；
- 角色登录：viewer(只读) / safety_officer(确认·工单) / admin(另可审批阈值)；
- WebSocket /ws 实时推送（新事件/工单/状态变化，前端免轮询）；
- POST /api/ingest/event 供实时流worker推送事件。

启动：
  python app_server.py [--port 8800] [--data-dir outputs/eval_v1/frontend] [--db app_data/site_safety.db]
首次启动时自动把 --data-dir 的JSON数据导入SQLite；此后SQLite是唯一事实源。
默认账号（首次启动种子，生产部署前务必修改）：
  admin/admin123  safety/safety123  viewer/viewer123
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import math
import os
import secrets
import shutil
import sqlite3
import subprocess
import sys
import threading
import uuid
from PIL import Image, UnidentifiedImageError
from urllib.parse import quote
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    File,
    Form,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from site_safety.agents.knowledge_base import KnowledgeBase
from site_safety.utils.json_store import read_json, update_json
from site_safety.agents.notify_gateway import NotificationGateway
from site_safety.agents.response import (
    ALLOWED_TRANSITIONS,
    SLA_HOURS,
    CollaborativeResponseAgent,
)
from site_safety.agents.review_learning import ReviewLearningAgent
from site_safety.agents.risk_reasoning import RiskReasoningAgent
from site_safety.agents.schemas import (
    RISK_LEVEL_ZH,
    DetectionEvent,
    ThresholdProposal,
    WorkOrder,
    WorkOrderHistoryItem,
)

ROOT = Path(__file__).resolve().parent
UI_DIR = ROOT / "demo_ui"
THRESHOLD_OVERRIDES_PATH = ROOT / "configs" / "road_threshold_overrides.json"
ROLE_RANK = {"viewer": 0, "safety_officer": 1, "admin": 2}
TOKEN_TTL_HOURS = 12
INTERNAL_KEY = "local-detect-bridge"
PUSH_RULES_PATH = ROOT / "configs" / "road_notify_targets.json"


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- 存储层


class Database:
    """SQLite文档存储：契约JSON整体入库，kind/status/site_id做索引列。"""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        # A single sqlite connection is shared by FastAPI worker threads.  Even
        # reads must be serialized with writes on that connection; RLock also
        # lets backup/repair code safely compose database operations.
        self.lock = threading.RLock()
        with self.lock:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS docs(
                    kind TEXT NOT NULL, id TEXT PRIMARY KEY, json TEXT NOT NULL,
                    status TEXT, site_id TEXT, updated_at TEXT);
                CREATE INDEX IF NOT EXISTS idx_docs_kind ON docs(kind, status);
                CREATE INDEX IF NOT EXISTS idx_docs_site ON docs(kind, site_id);
                CREATE TABLE IF NOT EXISTS users(
                    username TEXT PRIMARY KEY, salt TEXT, password_hash TEXT, role TEXT);
                """
            )
            self.conn.commit()

    def upsert(self, kind: str, doc_id: str, payload: dict, *, status: str = "", site_id: str = "") -> None:
        with self.lock:
            self.conn.execute(
                "INSERT INTO docs(kind,id,json,status,site_id,updated_at) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET json=excluded.json,status=excluded.status,"
                "site_id=excluded.site_id,updated_at=excluded.updated_at",
                (kind, doc_id, json.dumps(payload, ensure_ascii=False), status, site_id, _now_iso()),
            )
            self.conn.commit()

    def get(self, doc_id: str) -> Optional[dict]:
        with self.lock:
            row = self.conn.execute("SELECT json FROM docs WHERE id=?", (doc_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, kind: str, *, status: Optional[str] = None) -> List[dict]:
        sql, args = "SELECT json FROM docs WHERE kind=?", [kind]
        if status is not None:
            sql += " AND status=?"
            args.append(status)
        with self.lock:
            rows = self.conn.execute(sql + " ORDER BY id", args).fetchall()
        return [json.loads(r[0]) for r in rows]

    def count(self, kind: str) -> int:
        with self.lock:
            return self.conn.execute("SELECT COUNT(*) FROM docs WHERE kind=?", (kind,)).fetchone()[0]

    def delete(self, kind: str, doc_id: str) -> bool:
        with self.lock:
            cursor = self.conn.execute("DELETE FROM docs WHERE kind=? AND id=?", (kind, doc_id))
            self.conn.commit()
        return cursor.rowcount > 0

    def seed_users(self) -> None:
        with self.lock:
            if self.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
                return
            for username, password, role in [
                ("admin", "admin123", "admin"),
                ("safety", "safety123", "safety_officer"),
                ("viewer", "viewer123", "viewer"),
            ]:
                salt = secrets.token_hex(8)
                self.conn.execute(
                    "INSERT INTO users VALUES(?,?,?,?)",
                    (username, salt, _hash_password(password, salt), role),
                )
            self.conn.commit()

    def verify_user(self, username: str, password: str) -> Optional[str]:
        with self.lock:
            row = self.conn.execute(
                "SELECT salt,password_hash,role FROM users WHERE username=?", (username,)
            ).fetchone()
        if row and _hash_password(password, row[0]) == row[1]:
            return row[2]
        return None

    def list_users(self) -> List[dict]:
        with self.lock:
            rows = self.conn.execute("SELECT username,role FROM users ORDER BY username").fetchall()
        return [{"username": r[0], "role": r[1]} for r in rows]

    def create_user(self, username: str, password: str, role: str) -> None:
        if role not in ROLE_RANK:
            raise ValueError(f"非法角色：{role}")
        if not username.strip() or len(password) < 6:
            raise ValueError("用户名不能为空且密码至少6位")
        salt = secrets.token_hex(8)
        with self.lock:
            if self.conn.execute(
                "SELECT 1 FROM users WHERE username=?", (username,)
            ).fetchone():
                raise ValueError(f"用户已存在：{username}")
            self.conn.execute(
                "INSERT INTO users VALUES(?,?,?,?)",
                (username, salt, _hash_password(password, salt), role),
            )
            self.conn.commit()

    def set_password(self, username: str, password: str) -> None:
        if len(password) < 6:
            raise ValueError("密码至少6位")
        salt = secrets.token_hex(8)
        with self.lock:
            cursor = self.conn.execute(
                "UPDATE users SET salt=?,password_hash=? WHERE username=?",
                (salt, _hash_password(password, salt), username),
            )
            self.conn.commit()
        if cursor.rowcount == 0:
            raise KeyError(f"用户不存在：{username}")

    def set_role(self, username: str, role: str) -> None:
        if role not in ROLE_RANK:
            raise ValueError(f"非法角色：{role}")
        with self.lock:
            cursor = self.conn.execute(
                "UPDATE users SET role=? WHERE username=?", (role, username)
            )
            self.conn.commit()
        if cursor.rowcount == 0:
            raise KeyError(f"用户不存在：{username}")


# ---------------------------------------------------------------- 应用状态


class AppState:
    def __init__(self, db: Database, app_data: Path) -> None:
        self.db = db
        # Serialize multi-document business transactions. A single event may
        # create an event, orders, confirmations and notifications together.
        self.mutation_lock = threading.RLock()
        self.reasoning = RiskReasoningAgent(ROOT / "examples" / "road_regulations.json")
        self.gateway = NotificationGateway(outbox_path=app_data / "notify_outbox.jsonl")
        # Personal WeChat requires a separate explicitly configured adapter.
        self.gateway.webhook_url = None
        # The application persists business documents before dispatching.  The
        # standalone agent can still accept a gateway, but doing so here would
        # let an external webhook observe an order that was not committed yet.
        self.response = CollaborativeResponseAgent(gateway=None, domain="road")
        if PUSH_RULES_PATH.is_file():
            try:
                saved_targets = json.loads(PUSH_RULES_PATH.read_text(encoding="utf-8"))
                if isinstance(saved_targets, dict):
                    self.response.notify_targets.update(saved_targets)
            except (OSError, ValueError):
                pass
        self.learning = ReviewLearningAgent(app_data / "case_library.jsonl", domain="road")
        from site_safety.agents.road_knowledge import ensure_road_knowledge
        self.kb = KnowledgeBase(ensure_road_knowledge())
        self.tokens: Dict[str, dict] = {}
        self.ws_clients: List[WebSocket] = []
        self.stream_workers: Dict[str, subprocess.Popen] = {}
        self.stream_watchdog_stop = threading.Event()
        self.notification_retry_stop = threading.Event()
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.detect_api = os.environ.get("ZNT_DETECT_API", "http://127.0.0.1:8910").rstrip("/")
        self.media_roots = [ROOT / "outputs", ROOT / "results", ROOT / "eval_data", ROOT / "sample_data",
                            app_data, ROOT.parent.parent / "example"]

    # ---- 鉴权 ----

    def login(self, username: str, password: str) -> dict:
        role = self.db.verify_user(username, password)
        if role is None:
            raise HTTPException(401, "用户名或密码错误")
        token = secrets.token_hex(24)
        self.tokens[token] = {
            "username": username,
            "role": role,
            "expires": (datetime.now() + timedelta(hours=TOKEN_TTL_HOURS)).timestamp(),
        }
        return {"token": token, "username": username, "role": role}

    def auth(self, token: Optional[str]) -> dict:
        info = self.tokens.get(token or "")
        if not info or info["expires"] < datetime.now().timestamp():
            raise HTTPException(401, "未登录或登录已过期")
        return info

    # ---- 导入 ----

    def import_from_dir(self, data_dir: Path) -> dict:
        counts = {}
        events_path = data_dir / "events.jsonl"
        if events_path.is_file():
            for line in events_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                doc = json.loads(line)
                self.db.upsert(
                    "event", doc["event_id"], doc,
                    status=doc.get("review", {}).get("status", "pending"),
                    site_id=doc.get("device", {}).get("site_id", ""),
                )
            counts["events"] = self.db.count("event")
        mapping = [
            ("work_orders.json", "work_order", "work_order_id"),
            ("confirmation_requests.json", "confirmation", "request_id"),
            ("notifications.json", "notification", "notification_id"),
            ("threshold_proposals.json", "proposal", "proposal_id"),
        ]
        for filename, kind, key in mapping:
            path = data_dir / filename
            if path.is_file():
                for doc in json.loads(path.read_text(encoding="utf-8")):
                    self.db.upsert(
                        kind, doc[key], doc,
                        status=doc.get("status", ""), site_id=doc.get("site_id", ""),
                    )
                counts[kind] = self.db.count(kind)
        return counts

    # ---- 推送 ----

    def broadcast(self, message: dict) -> None:
        if self.loop is None:
            return
        for ws in list(self.ws_clients):
            asyncio.run_coroutine_threadsafe(self._safe_send(ws, message), self.loop)

    async def _safe_send(self, ws: WebSocket, message: dict) -> None:
        try:
            await ws.send_json(message)
        except Exception:
            if ws in self.ws_clients:
                self.ws_clients.remove(ws)

    # ---- 业务动作（与serve_demo同构，SQLite版） ----

    def _save_event(self, event: DetectionEvent) -> None:
        self.db.upsert(
            "event", event.event_id, event.model_dump(),
            status=event.review.status, site_id=event.device.site_id,
        )

    def dispatch_notification(self, notification: dict) -> dict:
        """Persist first, then dispatch; failed webhook deliveries stay retryable."""
        record = dict(notification)
        notification_id = record["notification_id"]
        previous = self.db.get(notification_id) or {}
        attempts = int(previous.get("delivery_attempts", 0)) + 1
        record["status"] = "dispatching"
        record["delivery_attempts"] = attempts
        self.db.upsert("notification", notification_id, record, status="dispatching")
        delivered = self.gateway.dispatch(record)
        webhook = delivered.get("delivery", {}).get("webhook")
        status = "retry_pending" if webhook is not None and not webhook.get("ok") else "delivered"
        delivered["status"] = status
        delivered["delivery_attempts"] = attempts
        self.db.upsert("notification", notification_id, delivered, status=status)
        return delivered

    def flush_agent_notifications(self) -> None:
        queued, self.response.notifications = self.response.notifications, []
        for notification in queued:
            self.dispatch_notification(notification)

    def retry_notifications(self, limit: int = 20) -> dict:
        retried = delivered = failed = 0
        for row in self.db.list("notification"):
            if row.get("status") not in {"pending", "retry_pending", "dispatching"}:
                continue
            if retried >= limit:
                break
            retried += 1
            result = self.dispatch_notification(row)
            if result["status"] == "delivered":
                delivered += 1
            else:
                failed += 1
        return {"retried": retried, "delivered": delivered, "failed": failed}

    def start_notification_retry(self) -> None:
        self.notification_retry_stop.clear()

        def loop() -> None:
            while not self.notification_retry_stop.wait(60):
                try:
                    self.retry_notifications()
                except Exception as exc:  # noqa: BLE001 - retry loop must stay alive
                    print(f"notification retry failed: {exc}", flush=True)

        threading.Thread(target=loop, name="notification-retry", daemon=True).start()

    def ingest_event(self, payload: dict) -> dict:
        from site_safety.road_domain import LEGACY_RISK_IDS
        if any(str(r.get("risk_id", "")).removeprefix("open_") in LEGACY_RISK_IDS for r in payload.get("risks", [])):
            raise HTTPException(422, "道路业务不接收历史工地风险类型")
        with self.mutation_lock:
            return self._ingest_event(payload)

    def _ingest_event(self, payload: dict) -> dict:
        event = DetectionEvent.model_validate(payload)
        existing = self.db.get(event.event_id)
        if existing is not None:
            repaired = self._repair_event_derivatives(DetectionEvent.model_validate(existing))
            return {"event_id": event.event_id, "work_orders": repaired["work_orders"],
                    "confirmations": repaired["confirmations"], "idempotent": True,
                    "repaired": bool(repaired["work_orders"] or repaired["confirmations"])}
        for finding in event.risks:
            self.reasoning.attach(finding)
        orders, confirmations = self.response.process_event(event)
        self._save_event(event)
        for order in orders:
            self.db.upsert("work_order", order.work_order_id, order.model_dump(),
                           status=order.status, site_id=order.site_id)
        for confirmation in confirmations:
            self.db.upsert("confirmation", confirmation.request_id, confirmation.model_dump(),
                           status=confirmation.status)
        self.flush_agent_notifications()
        self.broadcast({"type": "event", "event_id": event.event_id,
                        "orders": len(orders), "confirmations": len(confirmations)})
        return {"event_id": event.event_id, "work_orders": len(orders),
                "confirmations": len(confirmations)}

    def _repair_event_derivatives(self, event: DetectionEvent) -> dict:
        """Complete missing order/review documents after a mid-ingest process crash."""
        existing_orders = {(row.get("event_id"), row.get("risk_id"))
                           for row in self.db.list("work_order")}
        existing_confirmations = {(row.get("event_id"), row.get("risk_id"))
                                  for row in self.db.list("confirmation")}
        repaired_orders = repaired_confirmations = 0
        for finding in event.risks:
            key = (event.event_id, finding.risk_id)
            if key in existing_orders or key in existing_confirmations:
                continue
            self.reasoning.attach(finding)
            isolated = event.model_copy(deep=True, update={"risks": [finding]})
            orders, confirmations = self.response.process_event(isolated)
            for order in orders:
                self.db.upsert("work_order", order.work_order_id, order.model_dump(),
                               status=order.status, site_id=order.site_id)
                finding.work_order_id = order.work_order_id
                repaired_orders += 1
            for confirmation in confirmations:
                self.db.upsert("confirmation", confirmation.request_id, confirmation.model_dump(),
                               status=confirmation.status)
                repaired_confirmations += 1
            self.flush_agent_notifications()
        if repaired_orders or repaired_confirmations:
            self._save_event(event)
        return {"work_orders": repaired_orders, "confirmations": repaired_confirmations}

    def decide_confirmation(self, request_id: str, payload: dict, by: str) -> dict:
        with self.mutation_lock:
            return self._decide_confirmation(request_id, payload, by)

    def _decide_confirmation(self, request_id: str, payload: dict, by: str) -> dict:
        verdict = payload.get("verdict")
        if verdict not in {"confirmed", "rejected"}:
            raise HTTPException(400, "verdict必须是confirmed或rejected")
        doc = self.db.get(request_id)
        if doc is None:
            raise HTTPException(404, f"确认请求不存在：{request_id}")
        if doc.get("status") != "pending":
            raise HTTPException(400, "该请求已处理")
        event_doc = self.db.get(doc["event_id"])
        if event_doc is None:
            raise HTTPException(404, f"事件不存在：{doc['event_id']}")
        event = DetectionEvent.model_validate(event_doc)
        self.learning.ingest_confirmation(
            event, doc["risk_id"], verdict, reviewer=by, comment=payload.get("comment", "")
        )
        doc["status"] = verdict
        self.db.upsert("confirmation", request_id, doc, status=verdict)
        new_order = None
        if verdict == "confirmed":
            finding = next(r for r in event.risks if r.risk_id == doc["risk_id"])
            level = self.reasoning.base_severity(finding.risk_id)
            now = _now_iso()
            new_order = WorkOrder(
                work_order_id=f"WO-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}",
                event_id=event.event_id,
                risk_id=finding.risk_id,
                risk_name_zh=finding.risk_name_zh,
                risk_level=level,  # type: ignore[arg-type]
                risk_level_zh=RISK_LEVEL_ZH[level],
                status="confirmed",
                created_at=now,
                due_at=(datetime.now().astimezone() + timedelta(hours=self.response.sla_hours[level])).isoformat(timespec="seconds"),
                site_id=event.device.site_id,
                device_id=event.device.device_id,
                notify_targets=list(self.response.notify_targets.get(level, [])),
                disposal_recommendations=self.reasoning.disposal_for(finding.risk_id),
                history=[WorkOrderHistoryItem(at=now, to_status="confirmed", by=by,
                                              note=f"人工复核确认（{payload.get('comment') or '无备注'}）")],
            )
            finding.work_order_id = new_order.work_order_id
            self.db.upsert("work_order", new_order.work_order_id, new_order.model_dump(),
                           status=new_order.status, site_id=new_order.site_id)
        self._save_event(event)
        self.broadcast({"type": "confirmation", "request_id": request_id, "verdict": verdict})
        return {"request_id": request_id, "verdict": verdict,
                "work_order_id": new_order.work_order_id if new_order else None}

    def transition_order(self, work_order_id: str, payload: dict, by: str) -> dict:
        with self.mutation_lock:
            return self._transition_order(work_order_id, payload, by)

    def _transition_order(self, work_order_id: str, payload: dict, by: str) -> dict:
        doc = self.db.get(work_order_id)
        if doc is None:
            raise HTTPException(404, f"工单不存在：{work_order_id}")
        order = WorkOrder.model_validate(doc)
        try:
            self.response.transition(
                order, payload.get("to_status", ""), by=by,
                note=payload.get("note", ""), assignee=payload.get("assignee"),
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        verdict = {"rejected_false_alarm": "rejected", "confirmed": "confirmed"}.get(order.status)
        if verdict:
            event_doc = self.db.get(order.event_id)
            if event_doc is not None:
                event = DetectionEvent.model_validate(event_doc)
                try:
                    self.learning.ingest_confirmation(
                        event, order.risk_id, verdict, reviewer=by,  # type: ignore[arg-type]
                        comment=payload.get("note") or ("工单确认" if verdict == "confirmed" else "工单驳回"),
                    )
                    self._save_event(event)
                except ValueError:
                    pass
        self.db.upsert("work_order", work_order_id, order.model_dump(),
                       status=order.status, site_id=order.site_id)
        self.broadcast({"type": "work_order", "work_order_id": work_order_id, "status": order.status})
        return {"work_order_id": work_order_id, "status": order.status}

    # ---- 阈值审批 ----

    def load_overrides(self) -> dict:
        return read_json(THRESHOLD_OVERRIDES_PATH, {"risk_overrides": {}, "history": []})

    def proposals(self) -> List[dict]:
        stored = self.db.list("proposal")
        occupied = {p["risk_id"] for p in stored if p.get("status") in {"pending", "approved"}}
        occupied |= set(self.load_overrides().get("risk_overrides", {}))
        for proposal in self.learning.build_threshold_proposals(exclude_risk_ids=occupied):
            self.db.upsert("proposal", proposal.proposal_id, proposal.model_dump(),
                           status=proposal.status)
        return self.db.list("proposal")

    def decide_proposal(self, proposal_id: str, payload: dict, by: str) -> dict:
        decision = payload.get("decision")
        if decision not in {"approve", "reject"}:
            raise HTTPException(400, "decision必须是approve或reject")
        doc = self.db.get(proposal_id)
        if doc is None:
            raise HTTPException(404, f"提案不存在：{proposal_id}")
        proposal = ThresholdProposal.model_validate(doc)
        if proposal.status != "pending":
            raise HTTPException(400, "该提案已处理")
        proposal.status = "approved" if decision == "approve" else "rejected"
        proposal.decided_by = by
        proposal.decided_at = _now_iso()
        proposal.decision_note = payload.get("note", "")
        self.db.upsert("proposal", proposal_id, proposal.model_dump(), status=proposal.status)
        if decision == "approve":
            def approve(overrides):
                overrides.setdefault("risk_overrides", {})[proposal.risk_id] = {
                    "min_verified_confidence": proposal.proposed_min_verified_confidence,
                    "proposal_id": proposal_id, "approved_by": by, "approved_at": proposal.decided_at,
                }
                overrides.setdefault("history", []).append(
                    {"at": proposal.decided_at, "action": "approve", "proposal_id": proposal_id,
                     "risk_id": proposal.risk_id,
                     "min_verified_confidence": proposal.proposed_min_verified_confidence, "by": by}
                )
            update_json(THRESHOLD_OVERRIDES_PATH, approve, {"risk_overrides": {}, "history": []})
        self.broadcast({"type": "proposal", "proposal_id": proposal_id, "status": proposal.status})
        return {"proposal_id": proposal_id, "status": proposal.status}

    # ---- 聚合（与serve_demo同构） ----

    def events(self) -> List[DetectionEvent]:
        return [DetectionEvent.model_validate(d) for d in self.db.list("event")]

    def stats(self, date_prefix: str = "", site_id: str = "") -> dict:
        events = self.events()
        orders = self.db.list("work_order")
        if site_id:
            events = [event for event in events if event.device.site_id == site_id]
            orders = [order for order in orders if order.get("site_id") == site_id]
        if date_prefix:
            events = [event for event in events if event.time.detected_at.startswith(date_prefix)]
            orders = [order for order in orders if str(order.get("created_at", "")).startswith(date_prefix)]
        level_counter: Dict[str, int] = {}
        risk_counter: Dict[str, int] = {}
        for event in events:
            for risk in event.risks:
                level_counter[risk.risk_level] = level_counter.get(risk.risk_level, 0) + 1
                if risk.verified:
                    risk_counter[risk.risk_name_zh] = risk_counter.get(risk.risk_name_zh, 0) + 1
        order_status: Dict[str, int] = {}
        for order in orders:
            order_status[order["status"]] = order_status.get(order["status"], 0) + 1
        return {
            "total_events": len(events),
            "events_with_anomaly": sum(1 for e in events if e.overall_has_anomaly),
            "risk_level_distribution": level_counter,
            "verified_risk_distribution": risk_counter,
            "work_order_status": order_status,
            "work_orders_created": len(orders),
            "pending_confirmations": len(self.db.list("confirmation", status="pending")),
            "false_alarm_stats": self.learning.false_alarm_stats(),
            "threshold_suggestions": self.learning.threshold_suggestions(),
        }

    def sites(self) -> List[dict]:
        events = self.events()
        orders = self.db.list("work_order")
        now = _now_iso()
        by_site: Dict[str, dict] = {}
        for event in events:
            site = by_site.setdefault(event.device.site_id, {
                "site_id": event.device.site_id, "events": 0, "anomaly_events": 0,
                "verified_risks": 0, "open_orders": 0, "overdue_orders": 0,
                "last_detected_at": None, "devices": {}})
            site["events"] += 1
            if event.overall_has_anomaly:
                site["anomaly_events"] += 1
            site["verified_risks"] += sum(1 for r in event.risks if r.verified)
            if event.time.detected_at and (site["last_detected_at"] is None or event.time.detected_at > site["last_detected_at"]):
                site["last_detected_at"] = event.time.detected_at
            device = site["devices"].setdefault(event.device.device_id, {
                "device_id": event.device.device_id, "device_type": event.device.device_type,
                "data_modes": set(), "events": 0, "verified_risks": 0, "last_detected_at": None})
            device["events"] += 1
            device["data_modes"].add(event.data_mode)
            device["verified_risks"] += sum(1 for r in event.risks if r.verified)
            if event.time.detected_at and (device["last_detected_at"] is None or event.time.detected_at > device["last_detected_at"]):
                device["last_detected_at"] = event.time.detected_at
        open_statuses = {"pending_confirmation", "confirmed", "assigned", "rectifying"}
        for order in orders:
            site = by_site.get(order.get("site_id"))
            if site and order["status"] in open_statuses:
                site["open_orders"] += 1
                if order.get("due_at") and now > order["due_at"]:
                    site["overdue_orders"] += 1
        result = []
        for site in by_site.values():
            site["devices"] = [
                {**d, "data_modes": sorted(d["data_modes"])}
                for d in sorted(site["devices"].values(), key=lambda x: x["device_id"])]
            result.append(site)
        return sorted(result, key=lambda x: x["site_id"])

    def backup(self) -> dict:
        """SQLite在线备份到 app_data/backups/，保留最近20份。"""
        backup_dir = self.learning.case_library_path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        target = backup_dir / f"site_safety-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
        with self.db.lock:
            dest = sqlite3.connect(target)
            self.db.conn.backup(dest)
            dest.close()
        backups = sorted(backup_dir.glob("site_safety-*.db"))
        for old in backups[:-20]:
            old.unlink(missing_ok=True)
        return {"backup": str(target), "kept": min(len(backups), 20)}

    def resolve_media(self, raw_path: str) -> Optional[Path]:
        try:
            path = Path(raw_path).resolve()
        except OSError:
            return None
        for media_root in self.media_roots:
            try:
                path.relative_to(media_root.resolve())
                if path.is_file():
                    return path
            except ValueError:
                continue
        # Prefer the owning job/case directory; never select an arbitrary overlay.png.
        if path.name:
            candidates = set()
            for media_root in self.media_roots:
                if not media_root.is_dir():
                    continue
                candidates.update(p.resolve() for p in media_root.rglob(path.name) if p.is_file())
            owner_matches = {p for p in candidates if p.parent.name == path.parent.name}
            if len(owner_matches) == 1:
                return next(iter(owner_matches))
            if len(candidates) == 1:
                return next(iter(candidates))
        return None

    def stream_sources(self) -> List[dict]:
        rows = self.db.list("camera_source")
        for row in rows:
            process = self.stream_workers.get(row["id"])
            row["worker_running"] = bool(process and process.poll() is None)
            row["worker_pid"] = process.pid if row["worker_running"] else None
        return rows

    def start_stream(self, source_id: str) -> dict:
        source = self.db.get(source_id)
        if source is None: raise HTTPException(404, "视频源不存在")
        current = self.stream_workers.get(source_id)
        if current and current.poll() is None:
            return {"ok": True, "running": True, "pid": current.pid}
        log_dir = ROOT / "road_app_data" / "stream_logs"; log_dir.mkdir(parents=True, exist_ok=True)
        log = (log_dir / f"{source_id}.log").open("a", encoding="utf-8")
        cmd = [sys.executable, str(ROOT / "stream_bridge_worker.py"), "--source", source["stream_url"],
               "--device-id", source_id, "--site-id", source.get("site_id", "SITE-DEFAULT"),
               "--profile", source.get("profile", "offline"), "--interval-seconds", str(source.get("interval_seconds", 2)),
               "--audit-minutes", str(source.get("audit_minutes", 30)),
               "--bridge", self.detect_api]
        try:
            process = subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        finally:
            log.close()
        self.stream_workers[source_id] = process
        source["desired_running"] = True
        self.db.upsert("camera_source", source_id, source, status="running", site_id=source.get("site_id", ""))
        return {"ok": True, "running": True, "pid": process.pid, "log": str(log.name)}

    def stop_stream(self, source_id: str) -> dict:
        process = self.stream_workers.get(source_id)
        if process and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill()
        self.stream_workers.pop(source_id, None)
        source = self.db.get(source_id)
        if source is not None:
            source["desired_running"] = False
            self.db.upsert("camera_source", source_id, source, status="configured", site_id=source.get("site_id", ""))
        return {"ok": True, "running": False}

    def restore_streams(self) -> List[dict]:
        """Resume sources that were explicitly running before the backend restarted."""
        restored = []
        for source in self.db.list("camera_source"):
            if not source.get("desired_running"):
                continue
            try:
                restored.append({"id": source["id"], **self.start_stream(source["id"])})
            except Exception as exc:  # noqa: BLE001
                restored.append({"id": source.get("id"), "ok": False, "detail": str(exc)})
        return restored

    def start_stream_watchdog(self) -> None:
        """Keep configured live sources running without requiring an operator refresh."""
        self.stream_watchdog_stop.clear()

        def watch() -> None:
            while not self.stream_watchdog_stop.wait(10):
                for source in self.db.list("camera_source"):
                    if not source.get("desired_running"):
                        continue
                    process = self.stream_workers.get(source["id"])
                    if process is None or process.poll() is not None:
                        try:
                            self.start_stream(source["id"])
                        except Exception as exc:  # noqa: BLE001
                            print(f"stream watchdog retry failed for {source['id']}: {exc}", flush=True)

        threading.Thread(target=watch, name="znt-stream-watchdog", daemon=True).start()

    def shutdown_stream_workers(self) -> None:
        """Stop child processes while preserving desired_running for next startup."""
        self.stream_watchdog_stop.set()
        for source_id, process in list(self.stream_workers.items()):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            self.stream_workers.pop(source_id, None)

    def delete_stream(self, source_id: str) -> dict:
        self.stop_stream(source_id)
        if not self.db.delete("camera_source", source_id):
            raise HTTPException(404, "视频源不存在")
        return {"ok": True, "deleted": source_id}

    def stream_log(self, source_id: str, lines: int = 120) -> dict:
        if self.db.get(source_id) is None:
            raise HTTPException(404, "视频源不存在")
        path = ROOT / "road_app_data" / "stream_logs" / f"{source_id}.log"
        content = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.is_file() else []
        return {"source_id": source_id, "lines": content[-max(1, min(lines, 500)):], "path": str(path)}

    # ---- PC 管理端兼容视图 ----

    @staticmethod
    def _level_color(level: str) -> str:
        return {"critical": "red", "major": "orange", "general": "yellow",
                "pending_review": "orange", "info": "yellow"}.get(level, "yellow")

    @staticmethod
    def _front_status(status: str) -> str:
        if status in {"closed", "rejected_false_alarm"}:
            return "done"
        if status in {"assigned", "rectifying", "rectified"}:
            return "processing"
        return "pending"

    def media_url(self, raw_path: Optional[str]) -> str:
        if not raw_path:
            return ""
        return f"/api/media-file?path={quote(str(raw_path))}"

    def frontend_events(self) -> List[dict]:
        result = []
        for event in reversed(self.db.list("event")):
            for risk in event.get("risks", []):
                geom = risk.get("geometry") or {}
                result.append({
                    "id": f"{event['event_id']}:{risk.get('risk_id', 'risk')}",
                    "eventId": event["event_id"],
                    "siteId": event.get("device", {}).get("site_id", "SITE-DEFAULT"),
                    "expected": risk.get("risk_name_zh") or risk.get("risk_id") or "现场风险",
                    "result": risk.get("risk_description") or event.get("scene_summary") or "检测完成",
                    "confidence": float(risk.get("confidence") or 0),
                    "autoConfirm": bool(risk.get("verified")) and not bool(risk.get("manual_review_required")),
                    "humanReview": bool(risk.get("manual_review_required")) or risk.get("risk_level") == "pending_review",
                    "status": "review" if risk.get("manual_review_required") else "confirmed",
                    "analysis": risk.get("risk_description") or "来自真实检测事件",
                    "suggestion": (risk.get("disposal_recommendations") or ["请结合现场证据处置"])[0],
                    "cover": self.media_url(geom.get("overlay_path") or event.get("media", {}).get("image_path")),
                    "images": {
                        "original": self.media_url(event.get("media", {}).get("image_path")),
                        "overlay": self.media_url(geom.get("overlay_path")),
                        "mask": self.media_url(geom.get("mask_path")),
                    },
                    "detectJobId": event.get("pipeline", {}).get("job_id") or event.get("pipeline", {}).get("output_dir", ""),
                    "profile": event.get("pipeline", {}).get("config_name", ""),
                    "source": "business-backend",
                    "live": event.get("data_mode") == "realtime",
                    "createTime": event.get("time", {}).get("detected_at", ""),
                    "riskCount": len(event.get("risks", [])),
                })
        return result

    def frontend_orders(self) -> List[dict]:
        events = {e["event_id"]: e for e in self.db.list("event")}
        rows = []
        for order in reversed(self.db.list("work_order")):
            event = events.get(order.get("event_id"), {})
            finding = next((r for r in event.get("risks", []) if r.get("risk_id") == order.get("risk_id")), {})
            geom = finding.get("geometry") or {}
            rows.append({
                "id": order["work_order_id"], "title": order.get("risk_name_zh", "现场风险"),
                "siteId": order.get("site_id") or event.get("device", {}).get("site_id", "SITE-DEFAULT"),
                "level": self._level_color(order.get("risk_level", "general")),
                "type": order.get("risk_name_zh", "实时检测"), "area": order.get("device_id", "现场"),
                "team": "待指派", "status": self._front_status(order.get("status", "")),
                "rawStatus": order.get("status", ""), "assignee": order.get("assignee") or "待指派",
                "createTime": order.get("created_at", ""), "deadline": order.get("due_at", ""),
                "snapUrl": self.media_url(event.get("media", {}).get("image_path")),
                "maskUrl": self.media_url(geom.get("mask_path")), "overlayUrl": self.media_url(geom.get("overlay_path")),
                "regulation": finding.get("risk_description") or "见规范映射与检测证据",
                "suggestions": order.get("disposal_recommendations", []), "detectJobId": order.get("event_id"),
                "evidenceImages": [self.media_url(path) for path in order.get("evidence_images", [])],
                "logs": [{"time": h.get("at", "")[-8:], "action": h.get("note") or h.get("to_status", ""),
                          "user": h.get("by", "system")} for h in order.get("history", [])],
            })
        return rows

    def analysis(self, start: str = "", end: str = "", site_id: str = "") -> dict:
        events = self.db.list("event")
        if site_id:
            events = [event for event in events
                      if event.get("device", {}).get("site_id") == site_id]
        def date_of(e: dict) -> str:
            return (e.get("time", {}).get("detected_at") or "")[:10]
        if start: events = [e for e in events if date_of(e) >= start]
        if end: events = [e for e in events if date_of(e) <= end]
        if not end: end = datetime.now().date().isoformat()
        if not start: start = (datetime.now().date() - timedelta(days=6)).isoformat()
        begin, finish = datetime.fromisoformat(start).date(), datetime.fromisoformat(end).date()
        days = max(1, min(31, (finish - begin).days + 1))
        dates = [(begin + timedelta(days=i)).isoformat() for i in range(days)]
        counts = {d: {"red": 0, "orange": 0, "yellow": 0} for d in dates}
        areas: Dict[str, int] = {}
        teams: Dict[str, int] = {}
        for event in events:
            day = date_of(event)
            device = event.get("device", {}).get("device_id", "未知点位")
            for risk in event.get("risks", []):
                color = self._level_color(risk.get("risk_level", "general"))
                if day in counts: counts[day][color] += 1
                areas[device] = areas.get(device, 0) + 1
                teams[risk.get("risk_name_zh", "其他风险")] = teams.get(risk.get("risk_name_zh", "其他风险"), 0) + 1
        return {"trend": {"dates": [d[5:] for d in dates],
                          "red": [counts[d]["red"] for d in dates],
                          "orange": [counts[d]["orange"] for d in dates],
                          "yellow": [counts[d]["yellow"] for d in dates]},
                "areaHeat": [{"name": k, "value": v} for k, v in sorted(areas.items(), key=lambda x: -x[1])[:8]] or [{"name": "暂无事件", "value": 0}],
                "teamViolation": [{"name": k, "count": v} for k, v in sorted(teams.items(), key=lambda x: -x[1])[:8]] or [{"name": "暂无风险", "count": 0}],
                "range": {"start": start, "end": end, "days": days}}


# ---------------------------------------------------------------- FastAPI

STATE: AppState = None  # type: ignore[assignment]


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Bind runtime-only resources to the active ASGI event loop."""
    if STATE is not None:
        STATE.loop = asyncio.get_running_loop()
        restored = STATE.restore_streams()
        STATE.start_stream_watchdog()
        STATE.start_notification_retry()
        if restored:
            print(f"restored stream workers: {restored}", flush=True)
    try:
        yield
    finally:
        if STATE is not None:
            STATE.notification_retry_stop.set()
            STATE.shutdown_stream_workers()
            STATE.loop = None


app = FastAPI(title="路安智巡道路检测小试", version="1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "service": "znt-business-api", "version": app.version}


def _check_role(authorization: Optional[str], min_role: str) -> dict:
    token = (authorization or "").removeprefix("Bearer ").strip()
    info = STATE.auth(token)
    if ROLE_RANK[info["role"]] < ROLE_RANK[min_role]:
        raise HTTPException(403, f"该操作需要{min_role}及以上角色")
    return info


def auth_viewer(authorization: Optional[str] = Header(None)) -> dict:
    return _check_role(authorization, "viewer")


def auth_officer(authorization: Optional[str] = Header(None)) -> dict:
    return _check_role(authorization, "safety_officer")


def auth_admin(authorization: Optional[str] = Header(None)) -> dict:
    return _check_role(authorization, "admin")


@app.post("/api/auth/login")
def login(payload: dict) -> dict:
    username = payload.get("username", "")
    # 演示界面三个角色与正式后台角色保持兼容。
    username = {"director": "viewer"}.get(username, username)
    result = STATE.login(username, payload.get("password", ""))
    front_role = {"safety_officer": "safety", "viewer": "director"}.get(result["role"], result["role"])
    return {"token": result["token"], "user": {"id": f"u-{username}", "username": username,
            "name": {"admin": "系统管理员", "safety": "道路值班员", "viewer": "只读观察员"}.get(username, username),
            "role": front_role}}


@app.get("/api/whoami")
def whoami(user: dict = Depends(auth_viewer)) -> dict:
    return {"username": user["username"], "role": user["role"]}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(UI_DIR / "index.html")


@app.get("/api/events")
def events(user: dict = Depends(auth_viewer)) -> JSONResponse:
    return JSONResponse(STATE.db.list("event"))


@app.get("/api/work_orders")
def work_orders(user: dict = Depends(auth_viewer)) -> JSONResponse:
    return JSONResponse(STATE.db.list("work_order"))


@app.get("/api/confirmations")
def confirmations(user: dict = Depends(auth_viewer)) -> JSONResponse:
    return JSONResponse(STATE.db.list("confirmation"))


@app.get("/api/notifications")
def notifications(user: dict = Depends(auth_viewer)) -> JSONResponse:
    return JSONResponse(STATE.db.list("notification"))


@app.post("/api/notifications/retry")
def retry_notifications(user: dict = Depends(auth_admin)) -> dict:
    """Allow an administrator to immediately retry persisted failed deliveries."""
    return STATE.retry_notifications()


@app.get("/api/stats")
def stats(user: dict = Depends(auth_viewer)) -> dict:
    return STATE.stats()


@app.get("/api/sites")
def sites(user: dict = Depends(auth_viewer)) -> List[dict]:
    return STATE.sites()


@app.get("/api/briefing")
def briefing(user: dict = Depends(auth_viewer)) -> dict:
    return {"markdown": STATE.learning.generate_briefing(STATE.events())}


@app.get("/api/transitions")
def transitions(user: dict = Depends(auth_viewer)) -> dict:
    return {k: sorted(v) for k, v in ALLOWED_TRANSITIONS.items()}


@app.get("/api/config")
def config(user: dict = Depends(auth_viewer)) -> dict:
    return {
        "sla_hours": STATE.response.sla_hours,
        "sla_basis": "内部首次响应目标，不是法定处置期限",
        "notify_targets": STATE.response.notify_targets,
        "notify_channels": STATE.gateway.channels,
        "downgrade_threshold": STATE.reasoning.downgrade_threshold,
        "regulation_count": len(STATE.reasoning.regulations),
        "backend": "fastapi_sqlite",
    }


@app.get("/api/regulations")
def regulations(q: str = Query(""), user: dict = Depends(auth_viewer)) -> List[dict]:
    if not q.strip():
        return [
            {"regulation": r.model_dump(), "score": 1.0, "match": "all"}
            for r in STATE.reasoning.search_regulations("")
        ]
    results = STATE.reasoning.hybrid_search(q)
    for hit in STATE.kb.search(q):
        results.append({"knowledge": hit, "score": hit["score"], "match": "knowledge_base"})
    return results


@app.get("/api/knowledge")
def knowledge(user: dict = Depends(auth_viewer)) -> dict:
    return STATE.kb.summary()


@app.get("/api/proposals")
def proposals(user: dict = Depends(auth_viewer)) -> List[dict]:
    return STATE.proposals()


@app.get("/api/overrides")
def overrides(user: dict = Depends(auth_viewer)) -> dict:
    return STATE.load_overrides()


@app.get("/media")
def media(path: str = Query(...)) -> FileResponse:
    resolved = STATE.resolve_media(path)
    if resolved is None:
        raise HTTPException(403, "路径不在允许范围内")
    return FileResponse(resolved)


@app.post("/api/confirmations/{request_id}/decide")
def decide_confirmation(request_id: str, payload: dict, user: dict = Depends(auth_officer)) -> dict:
    return STATE.decide_confirmation(request_id, payload, user["username"])


@app.post("/api/work_orders/{work_order_id}/transition")
def transition(work_order_id: str, payload: dict, user: dict = Depends(auth_officer)) -> dict:
    return STATE.transition_order(work_order_id, payload, user["username"])


@app.post("/api/proposals/{proposal_id}/decide")
def decide_proposal(proposal_id: str, payload: dict, user: dict = Depends(auth_admin)) -> dict:
    return STATE.decide_proposal(proposal_id, payload, user["username"])


@app.post("/api/ingest/event")
def ingest_event(payload: dict, user: dict = Depends(auth_officer)) -> dict:
    return STATE.ingest_event(payload)


@app.post("/api/internal/ingest/event")
def internal_ingest_event(payload: dict, x_internal_key: Optional[str] = Header(None)) -> dict:
    """仅供同机检测桥写入事件，避免为后台任务伪造交互用户令牌。"""
    if x_internal_key != INTERNAL_KEY:
        raise HTTPException(403, "internal key invalid")
    return STATE.ingest_event(payload)


@app.get("/api/media-file")
def media_file(path: str = Query(...)) -> FileResponse:
    resolved = STATE.resolve_media(path)
    if resolved is None:
        raise HTTPException(403, "路径不在允许范围内")
    return FileResponse(resolved)


@app.get("/api/detection/final-summary")
def frontend_detection_summary(user: dict = Depends(auth_viewer)) -> dict:
    cases = STATE.frontend_events()
    review = sum(1 for c in cases if c["humanReview"])
    return {"summary": {"total": len(cases), "autoConfirmed": sum(1 for c in cases if c["autoConfirm"]),
                        "humanReview": review, "highConfidenceNoReview": sum(1 for c in cases if c["confidence"] >= .9 and not c["humanReview"]),
                        "liveCount": sum(1 for c in cases if c["live"]),
                        "conclusion": f"共 {len(cases)} 条真实持久化检测结果，其中 {review} 条需要人工复核。"},
            "cases": cases,
            "origin": {"summary": "数据来自检测桥写入的标准 DetectionEvent，并由业务后台持久化。",
                       "flow": ["YOLO初筛", "Qwen视觉识别", "SAM3定位", "证据核验", "Agent事件入库"],
                       "codePath": "detectmodel/Site_Safety_OpenRisk", "quickStart": ["start-platform.bat"]}}


@app.get("/api/workorder/list")
def frontend_workorders(keyword: str = "", level: str = "", status: str = "", page: int = 1,
                        pageSize: int = 10, user: dict = Depends(auth_viewer)) -> dict:
    rows = STATE.frontend_orders()
    if keyword: rows = [r for r in rows if keyword.lower() in json.dumps(r, ensure_ascii=False).lower()]
    if level: rows = [r for r in rows if r["level"] == level]
    if status: rows = [r for r in rows if r["status"] == status]
    start = max(0, (page - 1) * pageSize)
    return {"list": rows[start:start + pageSize], "total": len(rows)}


@app.get("/api/workorder/stats")
def frontend_workorder_stats(user: dict = Depends(auth_viewer)) -> dict:
    rows = STATE.frontend_orders()
    return {"all": len(rows), "pending": sum(r["status"] == "pending" for r in rows),
            "processing": sum(r["status"] == "processing" for r in rows),
            "done": sum(r["status"] == "done" for r in rows)}


@app.post("/api/workorder/export")
def frontend_workorder_export(payload: dict, user: dict = Depends(auth_viewer)) -> List[dict]:
    rows = STATE.frontend_orders(); ids = set(payload.get("ids") or [])
    return [r for r in rows if not ids or r["id"] in ids]


@app.get("/api/workorder/{work_order_id}")
def frontend_workorder_detail(work_order_id: str, user: dict = Depends(auth_viewer)) -> dict:
    row = next((r for r in STATE.frontend_orders() if r["id"] == work_order_id), None)
    if row is None: raise HTTPException(404, "工单不存在")
    return row


@app.post("/api/workorder/status")
def frontend_workorder_transition(payload: dict, user: dict = Depends(auth_officer)) -> dict:
    action = payload.get("action")
    order_id = payload.get("id", "")
    row = STATE.db.get(order_id)
    if row is None: raise HTTPException(404, "工单不存在")
    current = row.get("status")
    target = {("pending_confirmation", "accept"): "confirmed", ("confirmed", "accept"): "assigned",
              ("assigned", "accept"): "rectifying", ("rectifying", "complete"): "rectified",
              ("rectified", "complete"): "closed", ("pending_confirmation", "reject"): "rejected_false_alarm"}.get((current, action))
    # 接单允许补齐“确认/指派”中间态；整改完成不得跳过证据复核。
    if action == "accept" and current in {"pending_confirmation", "confirmed", "assigned"}:
        chain = {"pending_confirmation": ["confirmed", "assigned", "rectifying"],
                 "confirmed": ["assigned", "rectifying"], "assigned": ["rectifying"]}[current]
        result = None
        for step in chain: result = STATE.transition_order(order_id, {"to_status": step, "note": "安全员接单处理"}, user["username"])
        return {**(result or {}), "status": "processing"}
    if action == "complete" and current == "rectifying" and not row.get("evidence_images"):
        raise HTTPException(400, "请先上传整改复核证据，再确认完成")
    if not target: raise HTTPException(400, f"当前状态{current}不支持动作{action}")
    result = STATE.transition_order(order_id, {"to_status": target, "note": payload.get("note", "")}, user["username"])
    return {**result, "status": STATE._front_status(result["status"])}


@app.get("/api/analysis/overview")
def frontend_analysis(startDate: str = "", endDate: str = "", projectId: str = "",
                      user: dict = Depends(auth_viewer)) -> dict:
    return STATE.analysis(startDate, endDate, projectId)


@app.post("/api/analysis/export")
def frontend_analysis_export(payload: dict, user: dict = Depends(auth_viewer)) -> dict:
    return {"success": True, "message": "真实统计数据已就绪"}


@app.get("/api/resource/projects")
def frontend_projects(user: dict = Depends(auth_viewer)) -> List[dict]:
    sites = STATE.sites()
    if not sites:
        return [{"id": "SITE-DEFAULT", "name": "高速公路道路检测实验室", "shortName": "道路小试", "address": "本地演示项目"}]
    return [{"id": s["site_id"], "name": s["site_id"], "shortName": s["site_id"], "address": "已接入检测现场"} for s in sites]


@app.post("/api/resource/switch-project")
def frontend_switch_project(payload: dict, user: dict = Depends(auth_viewer)) -> dict:
    project_id = payload.get("projectId") or "SITE-DEFAULT"
    return {"id": project_id, "name": project_id, "shortName": project_id, "address": "已接入检测现场"}


@app.get("/api/resource/devices")
def frontend_devices(status: str = "", keyword: str = "",
                     user: dict = Depends(auth_viewer)) -> List[dict]:
    configured = {source["id"]: source for source in STATE.stream_sources()}
    rows = []
    known = set()
    for site in STATE.sites():
        for device in site.get("devices", []):
            known.add(device["device_id"])
            source = configured.get(device["device_id"])
            online = bool(source and source.get("worker_running"))
            rows.append({"id": device["device_id"], "name": device["device_id"], "area": site["site_id"],
                         "status": "online" if online else "offline", "online": online,
                         "type": device.get("device_type", "camera"),
                         "lastOnline": device.get("last_detected_at")})
    for source_id, source in configured.items():
        if source_id in known:
            continue
        online = bool(source.get("worker_running"))
        rows.append({"id": source_id, "name": source.get("name", source_id),
                     "area": source.get("site_id", "SITE-DEFAULT"),
                     "status": "online" if online else "offline", "online": online,
                     "type": "camera", "lastOnline": None})
    if status:
        rows = [row for row in rows if row["status"] == status]
    if keyword:
        needle = keyword.casefold()
        rows = [row for row in rows if needle in json.dumps(row, ensure_ascii=False).casefold()]
    return rows


@app.get("/api/resource/org-tree")
def frontend_org(user: dict = Depends(auth_viewer)) -> List[dict]:
    return [{"title": "项目安全管理部", "key": "org-root", "children": [
        {"title": "安全员", "key": "org-safety"}, {"title": "项目管理", "key": "org-admin"}]}]


@app.get("/api/monitor/device-tree")
def frontend_device_tree(user: dict = Depends(auth_viewer)) -> List[dict]:
    devices = frontend_devices(user=user)
    known = {d["id"] for d in devices}
    devices.extend({"id": s["id"], "name": s["name"], "online": bool(s.get("worker_running"))}
                   for s in STATE.stream_sources() if s["id"] not in known)
    return [{"title": "已接入设备", "key": "root", "children": [
        {"title": d["name"], "key": d["id"], "id": d["id"], "isLeaf": True,
         "online": bool(d.get("online", False))} for d in devices]}]


@app.get("/api/monitor/cameras")
def frontend_cameras(user: dict = Depends(auth_viewer)) -> List[dict]:
    configured = {s["id"]: s for s in STATE.stream_sources()}
    ids = {d["id"] for d in frontend_devices(user=user)} | set(configured)
    return [{"id": device_id, "name": configured.get(device_id, {}).get("name", device_id),
             "streamUrl": configured.get(device_id, {}).get("preview_url", ""),
             "online": bool(configured.get(device_id, {}).get("worker_running", False)), "masks": []}
            for device_id in sorted(ids)]


@app.get("/api/monitor/sources")
def stream_sources(user: dict = Depends(auth_viewer)) -> List[dict]:
    return STATE.stream_sources()


@app.post("/api/monitor/sources")
def save_stream_source(payload: dict, user: dict = Depends(auth_admin)) -> dict:
    source_id = (payload.get("id") or payload.get("device_id") or "").strip()
    if not source_id or not payload.get("stream_url"):
        raise HTTPException(400, "id和stream_url必填")
    existing = STATE.db.get(source_id) or {}
    row = {"id": source_id, "name": payload.get("name") or source_id,
           "stream_url": payload["stream_url"], "preview_url": payload.get("preview_url", ""),
           "site_id": payload.get("site_id", "SITE-DEFAULT"), "profile": payload.get("profile", "offline"),
           "interval_seconds": float(payload.get("interval_seconds", 2)),
           "audit_minutes": int(payload.get("audit_minutes", 30)),
           "desired_running": bool(payload.get("desired_running", existing.get("desired_running", False)))}
    STATE.db.upsert("camera_source", source_id, row, status="configured", site_id=row["site_id"])
    return row


@app.post("/api/monitor/sources/{source_id}/start")
def start_stream_source(source_id: str, user: dict = Depends(auth_admin)) -> dict:
    return STATE.start_stream(source_id)


@app.post("/api/monitor/sources/{source_id}/stop")
def stop_stream_source(source_id: str, user: dict = Depends(auth_admin)) -> dict:
    return STATE.stop_stream(source_id)


@app.delete("/api/monitor/sources/{source_id}")
def delete_stream_source(source_id: str, user: dict = Depends(auth_admin)) -> dict:
    return STATE.delete_stream(source_id)


@app.get("/api/monitor/sources/{source_id}/log")
def stream_source_log(source_id: str, lines: int = 120,
                      user: dict = Depends(auth_admin)) -> dict:
    return STATE.stream_log(source_id, lines)


@app.get("/api/monitor/alarms")
def frontend_alarms(user: dict = Depends(auth_viewer)) -> List[dict]:
    alarms = []
    orders = {(row.get("event_id"), row.get("risk_id")): row
              for row in STATE.db.list("work_order")}
    confirmations = {(row.get("event_id"), row.get("risk_id")): row
                     for row in STATE.db.list("confirmation")}
    for event in reversed(STATE.db.list("event")):
        for risk in event.get("risks", []):
            if not risk.get("verified") and not risk.get("manual_review_required"): continue
            key = (event.get("event_id"), risk.get("risk_id"))
            order = orders.get(key)
            confirmation = confirmations.get(key)
            # Only actionable items belong in the alarm queue. In-progress and
            # terminal work orders remain visible on the work-order page.
            if order and order.get("status") != "pending_confirmation":
                continue
            if not order and confirmation and confirmation.get("status") != "pending":
                continue
            if not order and not confirmation:
                continue
            alarms.append({"id": f"{event['event_id']}:{risk.get('risk_id')}",
                           "title": risk.get("risk_name_zh", "现场风险"),
                           "level": STATE._level_color(risk.get("risk_level", "general")),
                           "camera": event.get("device", {}).get("device_id", "未知设备"),
                           "time": (event.get("time", {}).get("detected_at") or "")[-8:], "status": "pending"})
    return alarms[:30]


@app.get("/api/dashboard/overview")
def frontend_dashboard(projectId: str = "", user: dict = Depends(auth_viewer)) -> dict:
    now = datetime.now().astimezone()
    today = now.date().isoformat()
    site_filter = projectId if projectId and projectId != "SITE-DEFAULT" else ""
    stats = STATE.stats(today, site_filter)
    orders = [row for row in STATE.frontend_orders()
              if not site_filter or row.get("siteId") == site_filter]
    alarms = frontend_alarms(user)
    if site_filter:
        device_ids = {device["id"] for device in frontend_devices(user=user)
                      if device.get("area") == site_filter}
        alarms = [alarm for alarm in alarms if alarm.get("camera") in device_ids]
    today_orders = [row for row in orders if str(row.get("createTime", "")).startswith(today)]
    hours = [f"{h:02d}:00" for h in range(8, 18)]
    hour_counts = {h: 0 for h in hours}
    for event in STATE.db.list("event"):
        if site_filter and event.get("device", {}).get("site_id") != site_filter:
            continue
        detected = event.get("time", {}).get("detected_at") or ""
        if not detected.startswith(today):
            continue
        key = detected[11:13] + ":00" if len(detected) >= 13 else ""
        if key in hour_counts: hour_counts[key] += len(event.get("risks", []))
    risk_dist = stats["verified_risk_distribution"]
    return {"projectId": projectId or "SITE-DEFAULT", "projectName": projectId or "高速公路道路检测实验室",
            "projectAddress": "真实业务数据库", "metrics": [
                {"key": "hazards", "label": "今日隐患", "value": stats["events_with_anomaly"], "unit": "件", "trend": "真实累计"},
                {"key": "pending", "label": "待整改工单", "value": sum(r["status"] == "pending" for r in today_orders), "unit": "件", "trend": "今日"},
                {"key": "completion", "label": "整改完成率", "value": round(100 * sum(r["status"] == "done" for r in today_orders) / max(1, len(today_orders)), 1), "unit": "%", "trend": "今日"},
                {"key": "cameras", "label": "在线摄像头",
                 "value": sum(bool(device.get("online")) for device in frontend_devices(user=user)
                              if not site_filter or device.get("area") == site_filter),
                 "unit": "路", "trend": "实时进程"},
                {"key": "highRisk", "label": "待处置高危", "value": sum(a["level"] == "red" for a in alarms), "unit": "件", "trend": "当前待跟进"}],
            "sitePoints": [], "highRiskVideos": [],
            "riskTrendHours": {"hours": hours, "values": [hour_counts[h] for h in hours]},
            "hazardTypes": [{"name": k, "value": v} for k, v in risk_dist.items()],
            "teamRank": [{"name": "当前项目", "fixed": sum(r["status"] == "done" for r in orders),
                          "total": len(orders), "rate": round(100 * sum(r["status"] == "done" for r in orders) / max(1, len(orders)), 1)}],
            "topHazards": [{"name": k, "count": v} for k, v in risk_dist.items()]}


@app.get("/api/screen/overview")
def public_screen_overview(projectId: str = "") -> dict:
    """门口展示屏只读汇总；不暴露人员、路径、令牌或模型配置。"""
    today = datetime.now().astimezone().date().isoformat()
    site_filter = projectId if projectId and projectId != "SITE-DEFAULT" else ""
    stats = STATE.stats(today, site_filter)
    orders = [row for row in STATE.frontend_orders()
              if not site_filter or row.get("siteId") == site_filter]
    events = [row for row in STATE.frontend_events()
              if not site_filter or row.get("siteId") == site_filter]
    open_orders = [row for row in orders if row["status"] != "done"]
    alerts = [{"id": row["id"], "level": row["level"],
               "text": f"{row['title']} · {row['area']} · {row['createTime'][-8:]}"}
              for row in open_orders[:20]]
    cases = [{"id": item["id"], "title": item["expected"],
              "area": item.get("result", "现场")[:30], "time": item.get("createTime", "")[-8:],
              "level": "orange" if item.get("humanReview") else "red",
              "image": item.get("cover") or item.get("images", {}).get("original", "")}
             for item in events[:10]]
    today_orders = [row for row in orders if str(row.get("createTime", "")).startswith(today)]
    done = sum(row["status"] == "done" for row in today_orders)
    return {"alerts": alerts, "stats": {"hazardTotal": stats["events_with_anomaly"],
            "fixedRate": round(done * 100 / max(1, len(today_orders)), 1),
            "highRisk": sum(row["level"] == "red" for row in open_orders), "pending": len(open_orders)},
            "cases": cases, "teamRank": [{"name": "当前项目", "rate": round(done * 100 / max(1, len(today_orders)), 1)}],
            "projectId": projectId or "SITE-DEFAULT", "source": "business-backend"}


@app.get("/api/mobile/reminders")
def mobile_reminders(user: dict = Depends(auth_viewer)) -> List[dict]:
    return STATE.frontend_orders()[:20]


@app.get("/api/mobile/alarm/latest")
def mobile_latest_alarm(user: dict = Depends(auth_viewer)) -> dict:
    alarms = frontend_alarms(user)
    if not alarms:
        return {"id": "", "level": "yellow", "title": "暂无实时告警", "area": "-",
                "camera": "-", "time": "-", "snapTip": "当前没有待处置告警", "regulation": "-"}
    alarm = alarms[0]
    return {**alarm, "area": alarm["camera"], "snapTip": "请在PC检测结果页查看证据图",
            "regulation": "请依据已导入的行业规范和现场证据进行处置。"}


@app.post("/api/mobile/alarm/handle")
def mobile_handle_alarm(payload: dict, user: dict = Depends(auth_officer)) -> dict:
    alarm_id = str(payload.get("alarmId") or "")
    action = str(payload.get("action") or "")
    if action not in {"accept", "ignore", "escalate"}:
        raise HTTPException(400, "action必须是accept、ignore或escalate")
    if ":" not in alarm_id:
        raise HTTPException(400, "告警ID无效")
    event_id, risk_id = alarm_id.split(":", 1)
    order = next((row for row in STATE.db.list("work_order")
                  if row.get("event_id") == event_id and row.get("risk_id") == risk_id), None)
    confirmation = next((row for row in STATE.db.list("confirmation")
                         if row.get("event_id") == event_id and row.get("risk_id") == risk_id
                         and row.get("status") == "pending"), None)
    result: dict = {}
    if action in {"accept", "ignore"}:
        if order is not None:
            front_action = "accept" if action == "accept" else "reject"
            result = frontend_workorder_transition(
                {"id": order["work_order_id"], "action": front_action,
                 "note": "移动端接单" if action == "accept" else "移动端标记误报"},
                user,
            )
        elif confirmation is not None:
            result = STATE.decide_confirmation(
                confirmation["request_id"],
                {"verdict": "confirmed" if action == "accept" else "rejected",
                 "comment": "移动端人工复核"},
                user["username"],
            )
        else:
            raise HTTPException(404, "该告警没有待处理的工单或复核请求")
    else:
        notification_id = f"NT-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
        notice = {"notification_id": notification_id, "event_id": event_id, "risk_id": risk_id,
                  "channel": "management", "status": "pending", "created_at": _now_iso(),
                  "created_by": user["username"], "title": "现场告警升级上报",
                  "body": f"安全员已将事件{event_id}中的风险{risk_id}升级至管理人员处理。",
                  "targets": ["project_manager"]}
        STATE.dispatch_notification(notice)
        STATE.broadcast({"type": "alarm_escalated", "event_id": event_id, "risk_id": risk_id})
        result = {"notification_id": notification_id, "status": "escalated"}
    action_id = f"MA-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
    STATE.db.upsert("mobile_alarm_action", action_id,
                    {"id": action_id, "alarm_id": alarm_id, "action": action,
                     "handled_by": user["username"], "handled_at": _now_iso(), "result": result},
                    status=action)
    return {"success": True, "alarmId": alarm_id, "action": action,
            "handledBy": user["username"], **result}


@app.get("/api/mobile/workorder/list")
def mobile_workorders(status: str = "", user: dict = Depends(auth_viewer)) -> List[dict]:
    rows = STATE.frontend_orders()
    if status: rows = [row for row in rows if row["status"] == status]
    steps = ["接单", "现场整改", "拍照复核", "关闭工单"]
    progress = {"pending": 0, "processing": 1, "done": 3}
    return [{**row, "steps": steps, "currentStep": progress.get(row["status"], 0)} for row in rows]


@app.post("/api/mobile/workorder/advance")
def mobile_advance_workorder(payload: dict, user: dict = Depends(auth_officer)) -> dict:
    action = payload.get("action")
    order_id = str(payload.get("id") or "")
    order = STATE.db.get(order_id)
    if order is None:
        raise HTTPException(404, "工单不存在")
    current = order.get("status")
    if action == "next" and current in {"pending_confirmation", "confirmed", "assigned"}:
        return frontend_workorder_transition(
            {"id": order_id, "action": "accept", "note": "移动端接单并开始整改"}, user)
    if action in {"next", "close"} and current == "rectified":
        return frontend_workorder_transition(
            {"id": order_id, "action": "complete", "note": "移动端复核通过并关闭工单"}, user)
    if current == "rectifying":
        raise HTTPException(400, "整改中的工单请先上传现场复核照片")
    raise HTTPException(400, f"当前状态{current}不支持动作{action}")


@app.post("/api/workorder/evidence")
@app.post("/api/mobile/workorder/evidence")
def mobile_workorder_evidence(
    id: str = Form(...), file: UploadFile = File(...),
    note: str = Form("移动端现场拍照复核"),
    user: dict = Depends(auth_officer),
) -> dict:
    with STATE.mutation_lock:
        order = STATE.db.get(id)
        if order is None:
            raise HTTPException(404, "工单不存在")
        if order.get("status") != "rectifying":
            raise HTTPException(400, "只有整改中的工单可以提交复核照片")
        content = file.file.read()
        if not content or len(content) > 15 * 1024 * 1024:
            raise HTTPException(400, "复核图片为空或超过15MB")
        evidence_dir = STATE.learning.case_library_path.parent / "workorder_evidence" / id
        evidence_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            suffix = ".jpg"
        target = evidence_dir / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}{suffix}"
        target.write_bytes(content)
        try:
            with Image.open(target) as image:
                image.verify()
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            target.unlink(missing_ok=True)
            raise HTTPException(400, "复核内容不是有效图片") from exc
        result = STATE.transition_order(
            id, {"to_status": "rectified", "note": note, "assignee": user["username"]},
            user["username"],
        )
        order = STATE.db.get(id) or {}
        evidence = list(order.get("evidence_images") or [])
        evidence.append(str(target.resolve()))
        order["evidence_images"] = evidence
        order["rectification_note"] = note
        STATE.db.upsert("work_order", id, order, status=order.get("status", "rectified"),
                        site_id=order.get("site_id", ""))
        return {**result, "status": "processing", "evidence": STATE.media_url(str(target.resolve()))}


@app.get("/api/mobile/case/list")
def mobile_cases(keyword: str = "", user: dict = Depends(auth_viewer)) -> List[dict]:
    return frontend_cases(keyword=keyword, user=user)


@app.post("/api/mobile/report")
def mobile_report(
    title: str = Form(...),
    level: str = Form("orange"),
    area: str = Form("现场"),
    desc: str = Form(""),
    site_id: str = Form("SITE-DEFAULT"),
    files: List[UploadFile] = File(default=[]),
    user: dict = Depends(auth_officer),
) -> dict:
    from site_safety.agents.schemas import (
        DetectionEvent, DeviceInfo, GeometryInfo, MediaInfo, ReviewInfo,
        RiskFinding, TimeInfo,
    )

    title = title.strip()
    area = area.strip() or "现场"
    if not title:
        raise HTTPException(400, "隐患标题不能为空")
    if level not in {"red", "orange", "yellow"}:
        raise HTTPException(400, "level必须是red、orange或yellow")
    report_id = f"RP-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
    media_dir = STATE.learning.case_library_path.parent / "manual_reports" / report_id
    media_dir.mkdir(parents=True, exist_ok=True)
    saved_images: List[str] = []
    image_width = image_height = 0
    try:
        for index, upload in enumerate(files[:3]):
            content = upload.file.read()
            if not content or len(content) > 15 * 1024 * 1024:
                raise HTTPException(400, "上报图片为空或超过15MB")
            suffix = Path(upload.filename or "").suffix.lower()
            if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
                suffix = ".jpg"
            target = media_dir / f"image_{index + 1}{suffix}"
            target.write_bytes(content)
            with Image.open(target) as image:
                image.verify()
            with Image.open(target) as image:
                if not saved_images:
                    image_width, image_height = image.size
            saved_images.append(str(target.resolve()))
    except HTTPException:
        shutil.rmtree(media_dir, ignore_errors=True)
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        shutil.rmtree(media_dir, ignore_errors=True)
        raise HTTPException(400, "上报内容包含无效图片") from exc
    now = _now_iso()
    risk_id = {"red": "manual_report_critical", "orange": "manual_report_major",
               "yellow": "manual_report_general"}[level]
    confidence = 0.0  # Human submission is not a model confidence score.
    event = DetectionEvent(
        event_id=f"EVT-{report_id}", data_mode="realtime",
        device=DeviceInfo(device_id="MOBILE-REPORT", device_type="mobile",
                          site_id=site_id or "SITE-DEFAULT", location_desc=area),
        time=TimeInfo(captured_at=None, detected_at=now, reported_at=now),
        media=MediaInfo(image_path=saved_images[0] if saved_images else "",
                        image_width=image_width, image_height=image_height),
        scene_summary=f"道路值班员人工上报：{title}", overall_has_anomaly=True,
        risks=[RiskFinding(
            risk_id=risk_id, risk_name_zh=title, verified=False, confidence=confidence,
            risk_level="general", risk_level_zh="一般风险",
            geometry=GeometryInfo(), visible_evidence=[desc.strip() or "人工上报，待复核"],
            risk_description=desc.strip() or f"{area}发现{title}",
            manual_review_required=True,
        )],
        review=ReviewInfo(status="pending", comment="道路值班员移动端人工上报，待复核"),
    )
    try:
        ingested = STATE.ingest_event(event.model_dump())
    except Exception:
        shutil.rmtree(media_dir, ignore_errors=True)
        raise
    report = {"id": report_id, "title": title, "level": level, "area": area,
              "desc": desc, "images": saved_images, "event_id": event.event_id,
              "createdAt": now, "createdBy": user["username"]}
    STATE.db.upsert("manual_report", report_id, report, status="ingested", site_id=site_id)
    return {"success": True, "reportId": report_id, "eventId": event.event_id,
            "workOrders": ingested.get("work_orders", 0),
            "confirmations": ingested.get("confirmations", 0),
            "message": "上报成功，已进入道路风险复核队列"}


@app.get("/api/model/config")
def frontend_model_config(user: dict = Depends(auth_viewer)) -> dict:
    risk_names = {
        "critical": "高危告警", "major": "中危告警", "general": "一般告警",
    }
    from site_safety.road_domain import road_risk_names
    operator_names = road_risk_names()
    overrides = STATE.load_overrides().get("risk_overrides", {})
    all_keys = list(operator_names)
    from site_safety.road_domain import LEGACY_RISK_IDS
    all_keys.extend(key for key in overrides if key not in operator_names and key.removeprefix("open_") not in LEGACY_RISK_IDS)
    thresholds = []
    for key in all_keys:
        override = overrides.get(key, {})
        approved = "min_verified_confidence" in override
        value = float(override.get("min_verified_confidence", .60))
        thresholds.append({
            "key": key,
            "label": operator_names.get(key, key),
            "name": operator_names.get(key, key),
            "desc": "复盘学习已批准的风险专属阈值" if approved else "风险算子默认确认阈值；调整后持久保存为专属覆盖",
            "value": value,
            "source": "manual_override" if override.get("source") == "manual" else "approved_override" if approved else "operator_default",
            "approved": approved,
        })
    return {"thresholds": thresholds,
            "pushRules": [{"id": k, "level": k, "label": risk_names.get(k, k),
                           "channels": v, "delayMin": 0}
                          for k, v in STATE.response.notify_targets.items()],
            "knowledge": [], "trainProgress": {"modelName": "外部训练流程", "status": "未启动",
            "epoch": 0, "eta": "-", "progress": 0}}


@app.put("/api/model/threshold")
def frontend_threshold(payload: dict, user: dict = Depends(auth_admin)) -> dict:
    key = payload.get("key")
    try:
        value = float(payload["value"])
        if not isinstance(key, str) or not key.strip() or len(key) > 100 or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError()
    except (KeyError, TypeError, ValueError, OverflowError):
        raise HTTPException(422, "请提供风险标识和 0–1 之间的有限阈值")
    from site_safety.road_domain import LEGACY_RISK_IDS
    if key.removeprefix("open_") in LEGACY_RISK_IDS:
        raise HTTPException(422, "道路模式不能配置历史工地风险阈值")
    def save(overrides):
        overrides.setdefault("risk_overrides", {})[key] = {
            "min_verified_confidence": value, "source": "manual",
            "updated_by": user.get("username", "admin"), "updated_at": _now_iso(),
        }
    update_json(THRESHOLD_OVERRIDES_PATH, save, {"risk_overrides": {}, "history": []})
    return {"success": True, "key": key, "value": value}


@app.put("/api/model/push-rule")
def frontend_push_rule(payload: dict, user: dict = Depends(auth_admin)) -> dict:
    level = payload.get("level") or payload.get("id")
    if level:
        STATE.response.notify_targets[level] = list(payload.get("channels") or payload.get("targets") or [])
        PUSH_RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
        PUSH_RULES_PATH.write_text(json.dumps(STATE.response.notify_targets, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"success": True, **payload}


@app.get("/api/case/list")
def frontend_cases(keyword: str = "", type: str = "", user: dict = Depends(auth_viewer)) -> List[dict]:
    rows = [{"id": c.case_id, "title": c.risk_name_zh, "summary": c.comment or "人工复核案例",
             "tags": c.lessons, "type": c.risk_id, "level": "confirmed" if c.human_verdict == "confirmed" else "rejected",
             "date": c.recorded_at[:10]} for c in STATE.learning.load_cases()]
    if keyword:
        rows = [r for r in rows if keyword in json.dumps(r, ensure_ascii=False)]
    if type:
        rows = [r for r in rows if type in {r["type"], r["title"]}]
    return rows


@app.get("/api/case/materials")
def frontend_materials(user: dict = Depends(auth_viewer)) -> List[dict]:
    return list(reversed(STATE.db.list("training_material")))


@app.post("/api/case/generate")
def frontend_generate_material(payload: dict, user: dict = Depends(auth_officer)) -> dict:
    cases = {c["id"]: c for c in frontend_cases(user=user)}
    case = cases.get(payload.get("caseId"))
    if case is None: raise HTTPException(404, "案例不存在")
    kind = payload.get("format", "doc")
    text_content = (f"# 安全培训材料：{case['title']}\n\n案例结论：{case['summary']}\n\n"
               f"人工经验：{'；'.join(case.get('tags') or ['请结合现场规范复核'])}\n\n"
               f"补充要求：{payload.get('prompt') or '落实班前安全交底与整改闭环。'}")
    content: Any = text_content
    material_type = {"poster": "海报", "video": "视频脚本", "doc": "文档"}.get(kind, "文档")
    if kind == "poster":
        content = {"headline": case["title"], "summary": case["summary"],
                   "actions": case.get("tags") or ["立即停止危险作业", "由安全员现场复核", "完成整改闭环"],
                   "footer": payload.get("prompt") or "安全第一，预防为主"}
    elif kind == "video":
        content = f"【镜头1】展示风险现场：{case['title']}。\n【旁白】{case['summary']}\n【镜头2】安全员核查并整改。\n【字幕】{payload.get('prompt') or '发现风险立即上报，确认后闭环处置。'}"
    material_id = f"material-{uuid.uuid4().hex[:8]}"
    material = {"id": material_id, "title": f"培训材料 · {case['title']}", "type": material_type,
                "format": kind, "createTime": _now_iso(), "size": f"{max(1, len(json.dumps(content, ensure_ascii=False))//1024)}KB",
                "caseId": case['id'], "content": content, "status": "done"}
    STATE.db.upsert("training_material", material_id, material, status="done")
    return {"success": True, "taskId": material_id, "status": "done",
            "message": "已基于真实复盘案例生成并保存", "material": material}


@app.get("/api/users")
def list_users(user: dict = Depends(auth_admin)) -> List[dict]:
    return STATE.db.list_users()


@app.post("/api/users")
def create_user(payload: dict, user: dict = Depends(auth_admin)) -> dict:
    try:
        STATE.db.create_user(
            payload.get("username", ""), payload.get("password", ""),
            payload.get("role", "viewer"),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True}


@app.post("/api/users/{username}/password")
def set_password(username: str, payload: dict, user: dict = Depends(auth_admin)) -> dict:
    try:
        STATE.db.set_password(username, payload.get("password", ""))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    return {"ok": True}


@app.post("/api/users/{username}/role")
def set_role(username: str, payload: dict, user: dict = Depends(auth_admin)) -> dict:
    try:
        STATE.db.set_role(username, payload.get("role", ""))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    return {"ok": True}


@app.post("/api/admin/backup")
def backup_now(user: dict = Depends(auth_admin)) -> dict:
    return STATE.backup()


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = Query("")) -> None:
    try:
        STATE.auth(token)
    except HTTPException:
        await ws.close(code=4401)
        return
    await ws.accept()
    STATE.ws_clients.append(ws)
    await ws.send_json({"type": "ready", "service": "znt-business-api", "at": _now_iso()})
    try:
        while True:
            message = await ws.receive_text()
            if message == "ping":
                await ws.send_json({"type": "pong", "at": _now_iso()})
    except WebSocketDisconnect:
        if ws in STATE.ws_clients:
            STATE.ws_clients.remove(ws)


def main() -> None:
    global STATE
    parser = argparse.ArgumentParser(description="Site safety production server")
    parser.add_argument("--port", type=int, default=8800)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--data-dir", default="outputs/road_import/frontend")
    parser.add_argument("--db", default="road_app_data/road_safety.db")
    # HTTPS：传入证书即启用（自签测试证书可用 openssl 或 mkcert 生成，见docs/DEPLOYMENT.md）
    parser.add_argument("--ssl-certfile", default=None)
    parser.add_argument("--ssl-keyfile", default=None)
    args = parser.parse_args()
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    db = Database(db_path)
    db.seed_users()
    STATE = AppState(db, db_path.parent)
    if db.count("event") == 0:
        data_dir = Path(args.data_dir)
        if not data_dir.is_absolute():
            data_dir = ROOT / data_dir
        if data_dir.is_dir():
            counts = STATE.import_from_dir(data_dir)
            print(f"imported from {data_dir}: {counts}", flush=True)
    else:
        # 每次启动做一次在线备份（保留最近20份）
        print(f"startup backup: {STATE.backup()['backup']}", flush=True)
    scheme = "https" if args.ssl_certfile else "http"
    print(f"production server: {scheme}://{args.host}:{args.port}  db={db_path}", flush=True)
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="warning",
        ssl_certfile=args.ssl_certfile,
        ssl_keyfile=args.ssl_keyfile,
    )


if __name__ == "__main__":
    main()
