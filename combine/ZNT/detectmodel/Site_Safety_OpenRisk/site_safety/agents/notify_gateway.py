"""通知网关：把出站通知分发到可插拔渠道。

渠道：
- file    ：追加写outbox JSONL（默认，永远开启，作为审计底账）；
- console ：打印到stdout（调试用）；
- webhook ：POST到企业微信群机器人兼容的webhook URL（仅在配置了URL时启用；
            默认读环境变量 SAFETY_WEBHOOK_URL，不配置则完全不发外部请求）。

发送失败不抛异常，结果写回通知记录的delivery字段，保证主流程不被通知层阻塞。
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import httpx


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class NotificationGateway:
    def __init__(
        self,
        *,
        outbox_path: str | Path,
        webhook_url: Optional[str] = None,
        console: bool = False,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.outbox_path = Path(outbox_path)
        self.outbox_path.parent.mkdir(parents=True, exist_ok=True)
        self.webhook_url = webhook_url or os.getenv("SAFETY_WEBHOOK_URL") or None
        self.console = console
        self.timeout_seconds = timeout_seconds
        self.lock = threading.RLock()

    @property
    def channels(self) -> List[str]:
        active = ["file"]
        if self.console:
            active.append("console")
        if self.webhook_url:
            active.append("webhook")
        return active

    def dispatch(self, notification: dict) -> dict:
        """分发一条通知，返回带delivery结果的记录。"""
        record = dict(notification)
        record["delivery"] = {"channels": self.channels, "dispatched_at": _now_iso()}
        if self.console:
            print(f"[通知] {record.get('title')} -> {record.get('targets')}", flush=True)
        if self.webhook_url:
            record["delivery"]["webhook"] = self._send_webhook(record)
        with self.lock:
            with self.outbox_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def _send_webhook(self, record: dict) -> dict:
        """企业微信群机器人markdown格式；失败降级为记录错误。"""
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": (
                    f"**{record.get('title', '安全告警')}**\n"
                    f"> {record.get('body', '')}\n"
                    f"> 事件：{record.get('event_id', '-')} 工单：{record.get('work_order_id', '-')}"
                )
            },
        }
        try:
            response = httpx.post(
                self.webhook_url, json=payload, timeout=self.timeout_seconds
            )
            return {"status_code": response.status_code, "ok": response.status_code == 200}
        except Exception as exc:  # noqa: BLE001 — 通知失败不阻塞主流程
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
