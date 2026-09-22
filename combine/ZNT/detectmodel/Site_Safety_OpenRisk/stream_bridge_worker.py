"""RTSP/视频轻量抽帧 Worker：只采集帧并提交检测桥，不重复加载模型。"""
from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass, field
import json
import math
import time
from typing import Callable
import urllib.request
from urllib.parse import urlparse

import cv2


OPEN_RETRY_SECONDS = 5.0
DROP_RETRY_SECONDS = 2.0
LIVE_STREAM_SCHEMES = frozenset({"rtsp", "rtmp", "udp", "tcp"})


@dataclass
class FrameSubmissionThrottle:
    """按两次提交的起始时间限速，模型耗时会计入间隔，避免固定重复等待。"""

    interval_seconds: float
    clock: Callable[[], float] = field(default=time.monotonic, repr=False)
    sleeper: Callable[[float], None] = field(default=time.sleep, repr=False)
    next_allowed_at: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        self.interval_seconds = max(0.2, float(self.interval_seconds))

    def ready(self, now: float | None = None) -> bool:
        current = self.clock() if now is None else now
        return current >= self.next_allowed_at

    def remaining(self, now: float | None = None) -> float:
        current = self.clock() if now is None else now
        return max(0.0, self.next_allowed_at - current)

    def wait_until_ready(self, now: float | None = None) -> float:
        delay = self.remaining(now)
        if delay > 0:
            self.sleeper(delay)
        return delay

    def mark_submitted(self, now: float | None = None) -> None:
        current = self.clock() if now is None else now
        self.next_allowed_at = current + self.interval_seconds


def capture_source(source: str) -> str | int:
    """OpenCV 的本机摄像头编号必须以整数传入。"""
    clean = str(source).strip()
    return int(clean) if clean.isdigit() else clean


def is_live_capture(source: str, capture: cv2.VideoCapture) -> bool:
    """区分实时流与可快速解码的视频文件，以选择正确的节流方式。"""
    clean = str(source).strip()
    if clean.isdigit() or urlparse(clean).scheme.lower() in LIVE_STREAM_SCHEMES:
        return True
    frame_count = float(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0)
    return not math.isfinite(frame_count) or frame_count <= 0.0


def file_frame_step(fps: float, interval_seconds: float) -> int:
    """离线视频按媒体时间抽帧，不逐帧编码与提交。"""
    safe_fps = fps if math.isfinite(fps) and fps > 0 else 25.0
    return max(1, int(safe_fps * max(0.2, interval_seconds)))


def post_json(url: str, payload: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--site-id", default="SITE-DEFAULT")
    parser.add_argument("--profile", default="offline")
    parser.add_argument("--interval-seconds", type=float, default=2.0)
    parser.add_argument("--audit-minutes", type=int, choices=[30, 120], default=30)
    parser.add_argument("--bridge", default="http://127.0.0.1:8910")
    args = parser.parse_args()
    while True:
        capture = cv2.VideoCapture(capture_source(args.source))
        if not capture.isOpened():
            print(f"open failed, retrying: {args.source}", flush=True)
            capture.release()
            time.sleep(OPEN_RETRY_SECONDS)
            continue
        live_capture = is_live_capture(args.source, capture)
        if live_capture:
            # 后端支持时仅保留最新帧，避免一次慢推理后继续消费旧 RTSP 缓冲。
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
        step = file_frame_step(fps, args.interval_seconds)
        throttle = FrameSubmissionThrottle(args.interval_seconds)
        frame_no = 0
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            frame_no += 1
            if live_capture:
                # 实时流的 read 本身随时钟推进；只做单一墙钟限速，不再按 FPS 抽帧后再 sleep。
                if not throttle.ready():
                    continue
            elif (frame_no - 1) % step != 0:
                continue
            else:
                # 文件可以被瞬间解码，按剩余间隔限速，推理/网络耗时会自动抵扣。
                throttle.wait_until_ready()
            ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
            if not ok:
                continue
            throttle.mark_submitted()
            payload = {"image_base64": base64.b64encode(encoded.tobytes()).decode("ascii"),
                       "device_id": args.device_id, "stream_ref": args.source,
                       "site_id": args.site_id, "profile": args.profile,
                       "force_inspection": False, "force_full_audit": False,
                       "audit_interval_minutes": args.audit_minutes}
            try:
                result = post_json(f"{args.bridge}/api/detect/camera-frame", payload)
                print(f"submitted {result.get('job_id')} frame={frame_no}", flush=True)
            except Exception as exc:
                print(f"submit failed: {exc}", flush=True)
        capture.release()
        time.sleep(DROP_RETRY_SECONDS)


if __name__ == "__main__":
    main()
