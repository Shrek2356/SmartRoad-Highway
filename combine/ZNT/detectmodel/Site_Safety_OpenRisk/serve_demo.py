"""安全管理演示服务：标准化事件/工单数据 + 人机协同闭环API。

仅用标准库HTTP服务，动作层复用site_safety.agents：
- 安全员确认/驳回 → ReviewLearningAgent 写案例库并回写事件；确认的待复核项自动升级为工单；
- 工单状态迁移 → CollaborativeResponseAgent 状态机校验；
- 所有变更写回 outputs/<run>/frontend/ 下的JSON（前端数据即唯一事实源）。

启动：python serve_demo.py [--data-dir outputs/eval_v1/frontend] [--port 8765]
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import re
import uuid
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from site_safety.agents.knowledge_base import KnowledgeBase
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


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class DemoStore:
    """以frontend目录JSON为唯一事实源的读写层。"""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.reasoning = RiskReasoningAgent(ROOT / "examples" / "road_regulations.json")
        # webhook仅在设置SAFETY_WEBHOOK_URL环境变量时启用，默认只写outbox底账
        self.gateway = NotificationGateway(outbox_path=data_dir / "notify_outbox.jsonl")
        self.response = CollaborativeResponseAgent(gateway=self.gateway, domain="road")
        self.learning = ReviewLearningAgent(data_dir / "case_library.jsonl", domain="road")
        from site_safety.agents.road_knowledge import ensure_road_knowledge
        self.kb = KnowledgeBase(ensure_road_knowledge())
        # 图片访问白名单：项目outputs、eval_data与现场实拍示例目录
        self.media_roots = [
            ROOT / "outputs",
            ROOT / "eval_data",
            ROOT / "sample_data",
            ROOT.parent / "example",
        ]

    # ---------- 读 ----------

    def events(self) -> list[DetectionEvent]:
        path = self.data_dir / "events.jsonl"
        if not path.is_file():
            return []
        return [
            DetectionEvent.model_validate(json.loads(line))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def work_orders(self) -> list[WorkOrder]:
        path = self.data_dir / "work_orders.json"
        if not path.is_file():
            return []
        return [WorkOrder.model_validate(x) for x in json.loads(path.read_text(encoding="utf-8"))]

    def confirmations(self) -> list[dict]:
        path = self.data_dir / "confirmation_requests.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []

    def notifications(self) -> list[dict]:
        path = self.data_dir / "notifications.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []

    def stats(self) -> dict:
        events = self.events()
        orders = self.work_orders()
        confirmations = self.confirmations()
        level_counter: dict[str, int] = {}
        risk_counter: dict[str, int] = {}
        for event in events:
            for risk in event.risks:
                level_counter[risk.risk_level] = level_counter.get(risk.risk_level, 0) + 1
                if risk.verified:
                    risk_counter[risk.risk_name_zh] = risk_counter.get(risk.risk_name_zh, 0) + 1
        order_status: dict[str, int] = {}
        for order in orders:
            order_status[order.status] = order_status.get(order.status, 0) + 1
        return {
            "total_events": len(events),
            "events_with_anomaly": sum(1 for e in events if e.overall_has_anomaly),
            "risk_level_distribution": level_counter,
            "verified_risk_distribution": risk_counter,
            "work_order_status": order_status,
            "work_orders_created": len(orders),
            "pending_confirmations": sum(1 for c in confirmations if c.get("status") == "pending"),
            "false_alarm_stats": self.learning.false_alarm_stats(),
            "threshold_suggestions": self.learning.threshold_suggestions(),
        }

    # ---------- 写 ----------

    def _save_events(self, events: list[DetectionEvent]) -> None:
        with (self.data_dir / "events.jsonl").open("w", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event.model_dump(), ensure_ascii=False) + "\n")

    def _save_orders(self, orders: list[WorkOrder]) -> None:
        (self.data_dir / "work_orders.json").write_text(
            json.dumps([o.model_dump() for o in orders], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _save_confirmations(self, items: list[dict]) -> None:
        (self.data_dir / "confirmation_requests.json").write_text(
            json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def decide_confirmation(self, request_id: str, payload: dict) -> dict:
        verdict = payload.get("verdict")
        if verdict not in {"confirmed", "rejected"}:
            raise ValueError("verdict必须是confirmed或rejected")
        reviewer = payload.get("reviewer") or "safety_officer"
        comment = payload.get("comment", "")
        confirmations = self.confirmations()
        target = next((c for c in confirmations if c["request_id"] == request_id), None)
        if target is None:
            raise KeyError(f"确认请求不存在：{request_id}")
        if target.get("status") != "pending":
            raise ValueError("该请求已处理")

        events = self.events()
        event = next((e for e in events if e.event_id == target["event_id"]), None)
        if event is None:
            raise KeyError(f"事件不存在：{target['event_id']}")
        # 回流案例库 + 回写事件复核状态
        self.learning.ingest_confirmation(
            event, target["risk_id"], verdict, reviewer=reviewer, comment=comment
        )
        target["status"] = verdict
        new_order = None
        if verdict == "confirmed":
            # 人工确认的待复核风险 → 升级为工单（等级按基础严重度）
            finding = next(r for r in event.risks if r.risk_id == target["risk_id"])
            level = self.reasoning.base_severity(finding.risk_id)
            now = _now_iso()
            due_at = (
                datetime.now().astimezone() + timedelta(hours=self.response.sla_hours[level])
            ).isoformat(timespec="seconds")
            new_order = WorkOrder(
                work_order_id=f"WO-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}",
                event_id=event.event_id,
                risk_id=finding.risk_id,
                risk_name_zh=finding.risk_name_zh,
                risk_level=level,  # type: ignore[arg-type]
                risk_level_zh=RISK_LEVEL_ZH[level],
                status="confirmed",
                created_at=now,
                due_at=due_at,
                site_id=event.device.site_id,
                device_id=event.device.device_id,
                notify_targets=list(self.response.notify_targets.get(level, [])),
                disposal_recommendations=self.reasoning.disposal_for(finding.risk_id),
                history=[
                    WorkOrderHistoryItem(
                        at=now,
                        to_status="confirmed",
                        by=reviewer,
                        note=f"人工复核确认（{comment or '无备注'}）",
                    )
                ],
            )
            finding.work_order_id = new_order.work_order_id
            orders = self.work_orders()
            orders.append(new_order)
            self._save_orders(orders)

        self._save_events(events)
        self._save_confirmations(confirmations)
        return {
            "request_id": request_id,
            "verdict": verdict,
            "work_order_id": new_order.work_order_id if new_order else None,
        }

    def sites(self) -> list[dict]:
        """站点×设备聚合：事件量、异常量、在办/逾期工单、最近检测时间。"""
        events = self.events()
        orders = self.work_orders()
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        by_site: dict[str, dict] = {}
        for event in events:
            site = by_site.setdefault(
                event.device.site_id,
                {
                    "site_id": event.device.site_id,
                    "events": 0,
                    "anomaly_events": 0,
                    "verified_risks": 0,
                    "open_orders": 0,
                    "overdue_orders": 0,
                    "last_detected_at": None,
                    "devices": {},
                },
            )
            site["events"] += 1
            if event.overall_has_anomaly:
                site["anomaly_events"] += 1
            site["verified_risks"] += sum(1 for r in event.risks if r.verified)
            if event.time.detected_at and (
                site["last_detected_at"] is None
                or event.time.detected_at > site["last_detected_at"]
            ):
                site["last_detected_at"] = event.time.detected_at
            device = site["devices"].setdefault(
                event.device.device_id,
                {
                    "device_id": event.device.device_id,
                    "device_type": event.device.device_type,
                    "data_modes": set(),
                    "events": 0,
                    "verified_risks": 0,
                    "last_detected_at": None,
                },
            )
            device["events"] += 1
            device["data_modes"].add(event.data_mode)
            device["verified_risks"] += sum(1 for r in event.risks if r.verified)
            if event.time.detected_at and (
                device["last_detected_at"] is None
                or event.time.detected_at > device["last_detected_at"]
            ):
                device["last_detected_at"] = event.time.detected_at
        open_statuses = {"pending_confirmation", "confirmed", "assigned", "rectifying"}
        for order in orders:
            site = by_site.get(order.site_id)
            if site is None:
                continue
            if order.status in open_statuses:
                site["open_orders"] += 1
                if order.due_at and now > order.due_at:
                    site["overdue_orders"] += 1
        result = []
        for site in by_site.values():
            site["devices"] = [
                {**d, "data_modes": sorted(d["data_modes"])}
                for d in sorted(site["devices"].values(), key=lambda x: x["device_id"])
            ]
            result.append(site)
        return sorted(result, key=lambda x: x["site_id"])

    # ---------- 阈值审批流 ----------

    def _proposals_path(self) -> Path:
        return self.data_dir / "threshold_proposals.json"

    def load_proposals(self) -> list[ThresholdProposal]:
        path = self._proposals_path()
        if not path.is_file():
            return []
        return [
            ThresholdProposal.model_validate(x)
            for x in json.loads(path.read_text(encoding="utf-8"))
        ]

    def _save_proposals(self, proposals: list[ThresholdProposal]) -> None:
        self._proposals_path().write_text(
            json.dumps([p.model_dump() for p in proposals], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_overrides(self) -> dict:
        if THRESHOLD_OVERRIDES_PATH.is_file():
            return json.loads(THRESHOLD_OVERRIDES_PATH.read_text(encoding="utf-8"))
        return {"risk_overrides": {}, "history": []}

    def proposals(self) -> list[dict]:
        """返回全部提案；先用最新误报统计补充新的pending提案（去重）。"""
        stored = self.load_proposals()
        occupied = {p.risk_id for p in stored if p.status in {"pending", "approved"}}
        occupied |= set(self.load_overrides().get("risk_overrides", {}))
        fresh = self.learning.build_threshold_proposals(exclude_risk_ids=occupied)
        if fresh:
            stored.extend(fresh)
            self._save_proposals(stored)
        return [p.model_dump() for p in stored]

    def decide_proposal(self, proposal_id: str, payload: dict) -> dict:
        decision = payload.get("decision")
        if decision not in {"approve", "reject"}:
            raise ValueError("decision必须是approve或reject")
        by = payload.get("by") or "safety_manager"
        note = payload.get("note", "")
        proposals = self.load_proposals()
        target = next((p for p in proposals if p.proposal_id == proposal_id), None)
        if target is None:
            raise KeyError(f"提案不存在：{proposal_id}")
        if target.status != "pending":
            raise ValueError("该提案已处理")
        target.status = "approved" if decision == "approve" else "rejected"
        target.decided_by = by
        target.decided_at = _now_iso()
        target.decision_note = note
        self._save_proposals(proposals)
        if decision == "approve":
            overrides = self.load_overrides()
            overrides.setdefault("risk_overrides", {})[target.risk_id] = {
                "min_verified_confidence": target.proposed_min_verified_confidence,
                "proposal_id": target.proposal_id,
                "approved_by": by,
                "approved_at": target.decided_at,
            }
            overrides.setdefault("history", []).append(
                {
                    "at": target.decided_at,
                    "action": "approve",
                    "proposal_id": target.proposal_id,
                    "risk_id": target.risk_id,
                    "min_verified_confidence": target.proposed_min_verified_confidence,
                    "by": by,
                    "note": note,
                }
            )
            THRESHOLD_OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
            THRESHOLD_OVERRIDES_PATH.write_text(
                json.dumps(overrides, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return {"proposal_id": proposal_id, "status": target.status}

    def transition_order(self, work_order_id: str, payload: dict) -> dict:
        to_status = payload.get("to_status", "")
        by = payload.get("by") or "safety_officer"
        note = payload.get("note", "")
        assignee = payload.get("assignee")
        orders = self.work_orders()
        order = next((o for o in orders if o.work_order_id == work_order_id), None)
        if order is None:
            raise KeyError(f"工单不存在：{work_order_id}")
        self.response.transition(order, to_status, by=by, note=note, assignee=assignee)
        # 确认/驳回都回流案例库：统计误报率需要完整的分母
        verdict = {"rejected_false_alarm": "rejected", "confirmed": "confirmed"}.get(to_status)
        if verdict:
            events = self.events()
            event = next((e for e in events if e.event_id == order.event_id), None)
            if event is not None:
                try:
                    self.learning.ingest_confirmation(
                        event,
                        order.risk_id,
                        verdict,  # type: ignore[arg-type]
                        reviewer=by,
                        comment=note or ("工单确认" if verdict == "confirmed" else "工单驳回"),
                    )
                    self._save_events(events)
                except ValueError:
                    pass
        self._save_orders(orders)
        return {"work_order_id": work_order_id, "status": order.status}

    def briefing(self) -> str:
        return self.learning.generate_briefing(self.events())

    def resolve_media(self, raw_path: str) -> Path | None:
        try:
            path = Path(raw_path).resolve()
        except OSError:
            return None
        for root in self.media_roots:
            try:
                path.relative_to(root.resolve())
                return path if path.is_file() else None
            except ValueError:
                continue
        return None


STORE: DemoStore | None = None


class DemoHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # 安静一点
        pass

    def _send_json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        assert STORE is not None
        parsed = urlparse(self.path)
        route = parsed.path
        try:
            if route in {"/", "/index.html"}:
                self._send_file(UI_DIR / "index.html")
            elif route == "/api/events":
                self._send_json([e.model_dump() for e in STORE.events()])
            elif route == "/api/work_orders":
                self._send_json([o.model_dump() for o in STORE.work_orders()])
            elif route == "/api/confirmations":
                self._send_json(STORE.confirmations())
            elif route == "/api/notifications":
                self._send_json(STORE.notifications())
            elif route == "/api/stats":
                self._send_json(STORE.stats())
            elif route == "/api/briefing":
                self._send_json({"markdown": STORE.briefing()})
            elif route == "/api/transitions":
                self._send_json({k: sorted(v) for k, v in ALLOWED_TRANSITIONS.items()})
            elif route == "/api/sites":
                self._send_json(STORE.sites())
            elif route == "/api/proposals":
                self._send_json(STORE.proposals())
            elif route == "/api/overrides":
                self._send_json(STORE.load_overrides())
            elif route == "/api/regulations":
                query = parse_qs(parsed.query).get("q", [""])[0]
                if not query.strip():
                    self._send_json(
                        [
                            {"regulation": r.model_dump(), "score": 1.0, "match": "all"}
                            for r in STORE.reasoning.search_regulations("")
                        ]
                    )
                else:
                    results = STORE.reasoning.hybrid_search(query)
                    for hit in STORE.kb.search(query):
                        results.append(
                            {"knowledge": hit, "score": hit["score"], "match": "knowledge_base"}
                        )
                    self._send_json(results)
            elif route == "/api/knowledge":
                self._send_json(STORE.kb.summary())
            elif route == "/api/config":
                self._send_json(
                    {
                        "sla_hours": STORE.response.sla_hours,
                        "notify_targets": STORE.response.notify_targets,
                        "notify_channels": STORE.gateway.channels,
                        "downgrade_threshold": STORE.reasoning.downgrade_threshold,
                        "regulation_count": len(STORE.reasoning.regulations),
                    }
                )
            elif route == "/media":
                raw = parse_qs(parsed.query).get("path", [""])[0]
                resolved = STORE.resolve_media(raw)
                if resolved is None:
                    self._send_json({"error": "路径不在允许范围内"}, 403)
                else:
                    self._send_file(resolved)
            else:
                self._send_json({"error": "not found"}, 404)
        except BrokenPipeError:
            pass
        except Exception as exc:  # noqa: BLE001
            self._send_json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    def do_POST(self) -> None:  # noqa: N802
        assert STORE is not None
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        try:
            match_confirm = re.fullmatch(r"/api/confirmations/([\w-]+)/decide", self.path)
            match_order = re.fullmatch(r"/api/work_orders/([\w-]+)/transition", self.path)
            match_proposal = re.fullmatch(r"/api/proposals/([\w-]+)/decide", self.path)
            if match_confirm:
                self._send_json(STORE.decide_confirmation(match_confirm.group(1), payload))
            elif match_order:
                self._send_json(STORE.transition_order(match_order.group(1), payload))
            elif match_proposal:
                self._send_json(STORE.decide_proposal(match_proposal.group(1), payload))
            else:
                self._send_json({"error": "not found"}, 404)
        except KeyError as exc:
            self._send_json({"error": str(exc)}, 404)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, 400)
        except Exception as exc:  # noqa: BLE001
            self._send_json({"error": f"{type(exc).__name__}: {exc}"}, 500)


def main() -> None:
    global STORE
    parser = argparse.ArgumentParser(description="Site safety demo server")
    parser.add_argument("--data-dir", default="outputs/eval_v1/frontend")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    data_dir = Path(args.data_dir)
    if not data_dir.is_absolute():
        data_dir = ROOT / data_dir
    if not (data_dir / "events.jsonl").is_file():
        raise FileNotFoundError(
            f"{data_dir} 缺少events.jsonl，请先运行 build_events.py 生成前端数据"
        )
    STORE = DemoStore(data_dir)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), DemoHandler)
    print(f"demo server ready: http://127.0.0.1:{args.port}  data={data_dir}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
