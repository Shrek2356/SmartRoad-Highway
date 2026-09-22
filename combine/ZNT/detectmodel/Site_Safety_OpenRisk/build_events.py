"""把批量检测输出目录转换为前端可消费的标准化数据。

用法：
  python build_events.py --batch-dir outputs/eval_v1 --output-dir outputs/eval_v1/frontend \
      [--data-mode offline] [--device-id CAM-A3-007] [--device-type fixed_camera] [--site-id SITE-01]

产物：
  events.jsonl               每行一个DetectionEvent
  work_orders.json           自动创建的工单列表
  confirmation_requests.json 待人工确认队列
  notifications.json         通知出站队列
  briefing.md                道路值班风险提示示例
  dashboard_stats.json       统计分析页聚合数据
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from site_safety.agents import (
    CollaborativeResponseAgent,
    ReviewLearningAgent,
    RiskReasoningAgent,
    build_event_from_output_dir,
)
from site_safety.agents.schemas import DeviceInfo


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert pipeline outputs to standardized events")
    parser.add_argument("--batch-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--data-mode", default="offline", choices=["offline", "realtime"])
    parser.add_argument("--device-id", default="OFFLINE-UPLOAD")
    parser.add_argument(
        "--device-type",
        default="offline_upload",
        choices=["fixed_camera", "drone", "mobile", "offline_upload"],
    )
    parser.add_argument("--site-id", default="SITE-DEFAULT")
    parser.add_argument("--config-name", default="")
    parser.add_argument("--mllm-model", default="")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    batch_dir = Path(args.batch_dir)
    output_dir = Path(args.output_dir)
    if not batch_dir.is_absolute():
        batch_dir = root / batch_dir
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    reasoning = RiskReasoningAgent(root / "examples" / "road_regulations.json")
    response = CollaborativeResponseAgent(domain="road")
    learning = ReviewLearningAgent(output_dir / "case_library.jsonl", domain="road")

    device = DeviceInfo(
        device_id=args.device_id,
        device_type=args.device_type,
        site_id=args.site_id,
    )

    events = []
    for run_dir in sorted(p for p in batch_dir.iterdir() if p.is_dir()):
        event = build_event_from_output_dir(
            run_dir,
            reasoning,
            data_mode=args.data_mode,
            device=device,
            config_name=args.config_name,
            mllm_model=args.mllm_model,
        )
        if event is not None:
            events.append(event)

    all_orders, all_confirmations = [], []
    for event in events:
        orders, confirmations = response.process_event(event)
        all_orders.extend(orders)
        all_confirmations.extend(confirmations)

    with (output_dir / "events.jsonl").open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event.model_dump(), ensure_ascii=False) + "\n")
    (output_dir / "work_orders.json").write_text(
        json.dumps([o.model_dump() for o in all_orders], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "confirmation_requests.json").write_text(
        json.dumps([c.model_dump() for c in all_confirmations], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "notifications.json").write_text(
        json.dumps(response.notifications, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "briefing.md").write_text(
        learning.generate_briefing(events), encoding="utf-8"
    )

    level_counter = Counter(
        finding.risk_level for event in events for finding in event.risks
    )
    risk_counter = Counter(
        finding.risk_name_zh
        for event in events
        for finding in event.risks
        if finding.verified
    )
    stats = {
        "total_events": len(events),
        "events_with_anomaly": sum(1 for e in events if e.overall_has_anomaly),
        "risk_level_distribution": dict(level_counter),
        "verified_risk_distribution": dict(risk_counter),
        "work_orders_created": len(all_orders),
        "pending_confirmations": len(all_confirmations),
        "notifications_enqueued": len(response.notifications),
    }
    (output_dir / "dashboard_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"saved to: {output_dir}")


if __name__ == "__main__":
    main()
