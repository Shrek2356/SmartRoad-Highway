"""协同响应Agent：确认请求、工单生成与状态机、通知分发。

设计约定：
- verified风险（critical/major/general）→ 自动创建工单，状态pending_confirmation，
  并附带风险推理Agent给出的现场处置建议；
- pending_review风险 → 只创建确认请求，安全员确认后升级为工单；
- 通知统一进notifications出站队列；配置NotificationGateway后同步分发
  （file审计底账/console/webhook企业微信机器人）。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from site_safety.agents.notify_gateway import NotificationGateway
from site_safety.agents.schemas import (
    RISK_LEVEL_ZH,
    ConfirmationRequest,
    DetectionEvent,
    WorkOrder,
    WorkOrderHistoryItem,
)

# 各等级整改时限（小时）
SLA_HOURS = {"critical": 2, "major": 24, "general": 72}

# 工单状态机：当前状态 → 允许迁移到的状态
ALLOWED_TRANSITIONS: Dict[str, set] = {
    "pending_confirmation": {"confirmed", "rejected_false_alarm"},
    "confirmed": {"assigned"},
    "assigned": {"rectifying"},
    "rectifying": {"rectified"},
    "rectified": {"closed", "rectifying"},  # 复验不通过可退回
    "closed": set(),
    "rejected_false_alarm": set(),
}


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _short_uid() -> str:
    return uuid.uuid4().hex[:8]


class CollaborativeResponseAgent:
    def __init__(
        self,
        *,
        notify_targets: Optional[Dict[str, List[str]]] = None,
        gateway: Optional[NotificationGateway] = None,
        domain: str = "road",
    ) -> None:
        # 按等级配置通知对象（前端"系统配置"页可改写后重新注入）
        self.notify_targets = notify_targets or {
            "critical": ["safety_director", "site_manager", "area_foreman"],
            "major": ["safety_officer", "area_foreman"],
            "general": ["safety_officer"],
        }
        from site_safety.road_domain import ROAD_NOTIFY_TARGETS, ROAD_RESPONSE_HOURS
        self.domain = domain
        self.sla_hours = ROAD_RESPONSE_HOURS if domain == "road" else SLA_HOURS
        if domain == "road" and notify_targets is None:
            self.notify_targets = ROAD_NOTIFY_TARGETS
        self.gateway = gateway
        self.notifications: List[dict] = []

    def process_event(
        self, event: DetectionEvent
    ) -> Tuple[List[WorkOrder], List[ConfirmationRequest]]:
        """对单个事件生成工单与确认请求，并回填event中的work_order_id。"""
        now = _now_iso()
        work_orders: List[WorkOrder] = []
        confirmations: List[ConfirmationRequest] = []
        date_tag = datetime.now().strftime("%Y%m%d")
        for finding in event.risks:
            if finding.risk_level in self.sla_hours and finding.verified and not finding.manual_review_required:
                due_at = (
                    datetime.now().astimezone()
                    + timedelta(hours=self.sla_hours[finding.risk_level])
                ).isoformat(timespec="seconds")
                order = WorkOrder(
                    work_order_id=f"WO-{date_tag}-{_short_uid()}",
                    event_id=event.event_id,
                    risk_id=finding.risk_id,
                    risk_name_zh=finding.risk_name_zh,
                    risk_level=finding.risk_level,
                    risk_level_zh=RISK_LEVEL_ZH[finding.risk_level],
                    created_at=now,
                    due_at=due_at,
                    site_id=event.device.site_id,
                    device_id=event.device.device_id,
                    notify_targets=list(self.notify_targets.get(finding.risk_level, [])),
                    disposal_recommendations=list(finding.disposal_recommendations),
                    history=[
                        WorkOrderHistoryItem(
                            at=now, to_status="pending_confirmation", note="系统自动创建"
                        )
                    ],
                )
                finding.work_order_id = order.work_order_id
                work_orders.append(order)
                self._enqueue_notification(order, event)
            elif finding.risk_level == "pending_review":
                confirmations.append(
                    ConfirmationRequest(
                        request_id=f"CR-{date_tag}-{_short_uid()}",
                        event_id=event.event_id,
                        risk_id=finding.risk_id,
                        risk_name_zh=finding.risk_name_zh,
                        reason="；".join(finding.uncertainties) or "自动证据不足，需人工确认",
                        model_verified=finding.verified,
                        model_confidence=finding.confidence,
                        model_judgment=finding.risk_description,
                        visible_evidence=list(finding.visible_evidence),
                        counter_evidence=list(finding.counter_evidence),
                        absence_status=finding.absence_status,
                        crop_path=finding.geometry.crop_path,
                        overlay_path=finding.geometry.overlay_path,
                        image_path=event.media.image_path or None,
                        created_at=now,
                    )
                )
        return work_orders, confirmations

    def transition(
        self,
        order: WorkOrder,
        to_status: str,
        *,
        by: str,
        note: str = "",
        assignee: Optional[str] = None,
    ) -> WorkOrder:
        """工单状态迁移，非法迁移抛出ValueError。"""
        allowed = ALLOWED_TRANSITIONS.get(order.status, set())
        if to_status not in allowed:
            raise ValueError(f"工单{order.work_order_id}不允许从{order.status}迁移到{to_status}")
        history_item = WorkOrderHistoryItem(
            at=_now_iso(),
            from_status=order.status,
            to_status=to_status,
            by=by,
            note=note,
        )
        order.status = to_status  # type: ignore[assignment]
        if assignee:
            order.assignee = assignee
        order.history.append(history_item)
        return order

    def _enqueue_notification(self, order: WorkOrder, event: DetectionEvent) -> None:
        first_action = (
            order.disposal_recommendations[0] if order.disposal_recommendations else ""
        )
        notification = {
            "notification_id": f"NT-{_short_uid()}",
            "created_at": order.created_at,
            "channel": "outbox",
            "targets": order.notify_targets,
            "title": f"[{order.risk_level_zh}] {order.risk_name_zh}",
            "body": (
                f"设备{order.device_id}检测到{order.risk_name_zh}，"
                f"工单{order.work_order_id}，请在{order.due_at}前反馈处置进展（内部响应时限）。"
                + (f"首要处置：{first_action}" if first_action else "")
            ),
            "event_id": event.event_id,
            "work_order_id": order.work_order_id,
        }
        if self.gateway is not None:
            notification = self.gateway.dispatch(notification)
        self.notifications.append(notification)
