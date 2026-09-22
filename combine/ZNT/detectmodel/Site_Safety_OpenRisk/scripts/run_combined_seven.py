"""Run the seven delivery examples through integrated YOLO + local VLM/SAM3."""
from __future__ import annotations

import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from detect_bridge import DetectBridge, ROOT


SOURCE = Path(r"E:\work\competition\example")


def main() -> int:
    load_dotenv(ROOT / ".env")
    images = sorted(SOURCE.glob("*.png"), key=lambda path: path.name)
    if len(images) != 7:
        raise RuntimeError(f"Expected 7 PNG images, found {len(images)} in {SOURCE}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_dir = ROOT / "outputs" / f"combined_seven_{stamp}"
    batch_dir.mkdir(parents=True, exist_ok=False)
    bridge = DetectBridge(default_profile="offline")
    rows: list[dict] = []

    for index, image_path in enumerate(images, 1):
        started = time.perf_counter()
        print(f"[{index}/7] START {image_path.name}", flush=True)
        response = bridge.create_job(
            source="upload",
            device_id="EXAMPLE-BATCH",
            data_mode="offline",
            image_bytes=image_path.read_bytes(),
            filename=image_path.name,
            profile="offline",
            force_inspection=True,
        )
        job_id = response["job_id"]
        while True:
            job = bridge.get_job(job_id)
            if job["status"] in {"done", "error"}:
                break
            time.sleep(0.5)
        elapsed = round(time.perf_counter() - started, 2)
        result = job.get("result") or {}
        risks = result.get("risks") or []
        row = {
            "index": index,
            "image": image_path.name,
            "job_id": job_id,
            "status": job["status"],
            "elapsed_seconds": elapsed,
            "screening_triggered": bool((job.get("screening") or {}).get("triggered")),
            "screening_concepts": (job.get("screening") or {}).get("suspected_concepts", []),
            "routed_to_vlm": bool(job.get("routed_to_vlm")),
            "risk_count": len(risks),
            "risks": [
                {
                    "name": risk.get("name"),
                    "confidence": risk.get("confidence"),
                    "verified": risk.get("verified"),
                    "manual_review": risk.get("manual_review"),
                }
                for risk in risks
            ],
            "error": job.get("error"),
            "job_output_dir": job.get("output_dir"),
        }
        rows.append(row)
        (batch_dir / "progress.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            f"[{index}/7] {job['status'].upper()} {elapsed:.2f}s "
            f"risks={[risk.get('name') for risk in risks]}",
            flush=True,
        )

    summary = {
        "mode": "integrated_yolo_then_local_qwen_sam3_clip_agent",
        "source": str(SOURCE),
        "profile": "offline",
        "count": len(rows),
        "done": sum(row["status"] == "done" for row in rows),
        "with_risk": sum(row["risk_count"] > 0 for row in rows),
        "total_seconds": round(sum(row["elapsed_seconds"] for row in rows), 2),
        "average_seconds": round(sum(row["elapsed_seconds"] for row in rows) / len(rows), 2),
        "items": rows,
    }
    (batch_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    shutil.copy2(ROOT / "configs" / "qwen_local_production.yaml", batch_dir / "config_snapshot.yaml")

    md = [
        "# 七张范例组合模式测试",
        "",
        f"- 完成：{summary['done']}/7",
        f"- 输出风险：{summary['with_risk']}/7",
        f"- 总耗时：{summary['total_seconds']} 秒",
        f"- 平均耗时：{summary['average_seconds']} 秒/张",
        "",
        "| # | 图片 | 状态 | YOLO触发 | 最终风险 | 耗时(s) |",
        "|---:|---|---|---|---|---:|",
    ]
    for row in rows:
        names = "；".join(risk.get("name") or "未命名" for risk in row["risks"]) or "无"
        md.append(
            f"| {row['index']} | {row['image']} | {row['status']} | "
            f"{'是' if row['screening_triggered'] else '否'} | {names} | {row['elapsed_seconds']} |"
        )
    (batch_dir / "SUMMARY.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"BATCH_DIR={batch_dir}", flush=True)
    return 0 if summary["done"] == 7 else 1


if __name__ == "__main__":
    raise SystemExit(main())
