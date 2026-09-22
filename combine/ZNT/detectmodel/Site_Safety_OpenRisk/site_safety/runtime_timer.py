"""Persistent timer used by realtime camera full-image audits."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


class FullAuditTimer:
    """Keep per-device full-audit deadlines across bridge restarts.

    The timer does not capture camera frames itself. Each incoming frame calls
    :meth:`claim`; a due frame is routed to the complete VLM pipeline.
    """

    def __init__(self, state_path: str | Path) -> None:
        self.state_path = Path(state_path)
        self._lock = threading.Lock()
        self._last: Dict[str, float] = {}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            values = raw.get("last_full_audit_epoch", {})
            self._last = {str(k): float(v) for k, v in values.items()}
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            self._last = {}

    def _save_locked(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(
                {"last_full_audit_epoch": self._last, "updated_at": time.time()},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        tmp.replace(self.state_path)

    def claim(
        self,
        device_id: str,
        interval_minutes: int,
        *,
        force: bool = False,
        audit_on_first_frame: bool = False,
        now: Optional[float] = None,
    ) -> Tuple[bool, str]:
        epoch = float(time.time() if now is None else now)
        device = str(device_id or "CAM-DEFAULT")
        with self._lock:
            if force:
                self._last[device] = epoch
                self._save_locked()
                return True, "调度器/人工强制全图检测"
            last = self._last.get(device)
            if last is None:
                self._last[device] = epoch
                self._save_locked()
                if audit_on_first_frame:
                    return True, "设备首帧基线全图检测"
                return False, ""
            if epoch - last >= int(interval_minutes) * 60:
                self._last[device] = epoch
                self._save_locked()
                return True, f"定时全图检测：每{int(interval_minutes)}分钟"
        return False, ""

    def set_last(self, device_id: str, epoch: float) -> None:
        """Test/maintenance helper that also persists the supplied timestamp."""
        with self._lock:
            self._last[str(device_id)] = float(epoch)
            self._save_locked()

    def status(self, interval_minutes: int = 30) -> Dict[str, Any]:
        now = time.time()
        with self._lock:
            items = []
            for device, last in sorted(self._last.items()):
                next_epoch = last + int(interval_minutes) * 60
                items.append(
                    {
                        "device_id": device,
                        "last_full_audit_at": datetime.fromtimestamp(last).astimezone().isoformat(timespec="seconds"),
                        "next_full_audit_at": datetime.fromtimestamp(next_epoch).astimezone().isoformat(timespec="seconds"),
                        "due": now >= next_epoch,
                    }
                )
        return {
            "interval_minutes": int(interval_minutes),
            "state_path": str(self.state_path),
            "devices": items,
        }
