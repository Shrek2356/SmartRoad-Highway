"""实时流接入worker：视频文件/RTSP流按间隔抽帧 → 逐帧检测 → realtime事件。

用法：
  python run_stream_inspection.py --source rtsp://... --device-id CAM-A3-007 \
      --config configs/road_offline.yaml --output-root outputs/stream_cam007 \
      --frontend-dir outputs/eval_v1/frontend --interval-seconds 10

事件以data_mode=realtime追加进frontend目录（events.jsonl等），
演示前端刷新即可看到实时告警；通知经NotificationGateway分发。
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import cv2

from site_safety.agents import (
    CollaborativeResponseAgent,
    RiskReasoningAgent,
    build_event_from_output_dir,
)
from site_safety.agents.notify_gateway import NotificationGateway
from site_safety.agents.schemas import DeviceInfo
from site_safety.factory import build_inspector
from site_safety.screening import load_trigger_for_stem
from site_safety.utils.config import load_yaml

ROOT = Path(__file__).resolve().parent


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _append_json_list(path: Path, items: list[dict]) -> None:
    existing = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    existing.extend(items)
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Realtime stream inspection worker")
    parser.add_argument("--source", required=True, help="视频文件路径或RTSP URL")
    parser.add_argument("--config", default="configs/road_offline.yaml")
    parser.add_argument("--output-root", default="outputs/stream")
    parser.add_argument("--frontend-dir", default="outputs/eval_v1/frontend")
    parser.add_argument("--interval-seconds", type=float, default=10.0)
    parser.add_argument("--max-frames", type=int, default=0, help="0表示不限")
    parser.add_argument("--device-id", default="CAM-STREAM-01")
    parser.add_argument(
        "--device-type", default="fixed_camera", choices=["fixed_camera", "drone", "mobile"]
    )
    parser.add_argument("--site-id", default="SITE-DEFAULT")
    parser.add_argument(
        "--screening-dir",
        help="Optional detector hand-off directory containing frame_<frame_id>.json files.",
    )
    parser.add_argument(
        "--only-triggered",
        action="store_true",
        help="Only invoke the heavy MLLM pipeline for frames with triggered=true metadata.",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    output_root = Path(args.output_root)
    frontend_dir = Path(args.frontend_dir)
    for path in [config_path, output_root, frontend_dir]:
        pass
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    if not output_root.is_absolute():
        output_root = ROOT / output_root
    if not frontend_dir.is_absolute():
        frontend_dir = ROOT / frontend_dir
    screening_dir = Path(args.screening_dir) if args.screening_dir else None
    if screening_dir is not None and not screening_dir.is_absolute():
        screening_dir = ROOT / screening_dir
    if args.only_triggered and screening_dir is None:
        parser.error("--only-triggered requires --screening-dir")
    (output_root / "frames").mkdir(parents=True, exist_ok=True)
    frontend_dir.mkdir(parents=True, exist_ok=True)

    config = load_yaml(config_path)
    inspector = build_inspector(config, ROOT)
    reasoning = RiskReasoningAgent(ROOT / "examples" / "road_regulations.json")
    gateway = NotificationGateway(outbox_path=frontend_dir / "notify_outbox.jsonl")
    response = CollaborativeResponseAgent(gateway=gateway, domain="road")
    device = DeviceInfo(
        device_id=args.device_id,
        device_type=args.device_type,  # type: ignore[arg-type]
        site_id=args.site_id,
    )

    is_stream = args.source.startswith(("rtsp://", "rtmp://", "http://", "https://"))
    capture = cv2.VideoCapture(args.source)
    if not capture.isOpened():
        raise RuntimeError(f"无法打开视频源：{args.source}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
    frame_step = max(1, int(round(fps * args.interval_seconds)))
    print(
        f"stream worker: source={args.source} fps={fps:.1f} "
        f"every {frame_step} frames (~{args.interval_seconds}s)",
        flush=True,
    )

    frame_index = 0
    processed = 0
    while True:
        grabbed = capture.grab()
        if not grabbed:
            break
        frame_index += 1
        if frame_index % frame_step != 1 and frame_step > 1:
            continue
        ok, frame = capture.retrieve()
        if not ok:
            continue
        captured_at = _now_iso()
        frame_id = f"{frame_index:08d}"
        frame_path = output_root / "frames" / f"frame_{frame_id}.jpg"
        cv2.imwrite(str(frame_path), frame)
        run_dir = output_root / f"frame_{frame_id}"
        trigger = (
            load_trigger_for_stem(screening_dir, f"frame_{frame_id}")
            if screening_dir is not None
            else None
        )
        mask_path = (
            screening_dir / f"frame_{frame_id}.mask.png"
            if screening_dir is not None
            else None
        )
        if mask_path is not None and not mask_path.is_file():
            mask_path = None
        if args.only_triggered and (trigger is None or not trigger.triggered):
            print(f"[frame {frame_id}] skipped: no active screening trigger", flush=True)
            continue
        started = time.time()
        try:
            inspector.inspect(
                frame_path,
                run_dir,
                screening_trigger=trigger,
                screening_mask_path=mask_path,
            )
        except Exception as exc:  # noqa: BLE001 — 单帧失败不中断流
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "error.txt").write_text(f"{type(exc).__name__}: {exc}", encoding="utf-8")
            print(f"[frame {frame_id}] failed: {exc}", flush=True)
            continue
        event = build_event_from_output_dir(
            run_dir,
            reasoning,
            data_mode="realtime",
            device=device,
            captured_at=captured_at,
            frame_id=frame_id,
            stream_ref=args.source,
            config_name=config_path.stem,
        )
        if event is None:
            continue
        event.time.processing_ms = int((time.time() - started) * 1000)
        orders, confirmations = response.process_event(event)
        with (frontend_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.model_dump(), ensure_ascii=False) + "\n")
        if orders:
            _append_json_list(
                frontend_dir / "work_orders.json", [o.model_dump() for o in orders]
            )
        if confirmations:
            _append_json_list(
                frontend_dir / "confirmation_requests.json",
                [c.model_dump() for c in confirmations],
            )
        if response.notifications:
            _append_json_list(frontend_dir / "notifications.json", response.notifications)
            response.notifications = []
        processed += 1
        verified = [r.risk_id for r in event.risks if r.verified]
        print(
            f"[frame {frame_id}] event={event.event_id} verified={verified} "
            f"orders={len(orders)} confirmations={len(confirmations)} "
            f"({event.time.processing_ms}ms)",
            flush=True,
        )
        if args.max_frames and processed >= args.max_frames:
            break
        # 实时流按墙钟节流；文件则按帧号快进
        if is_stream:
            time.sleep(max(0.0, args.interval_seconds))
    capture.release()
    print(f"stream worker done: processed {processed} frames", flush=True)


if __name__ == "__main__":
    main()
