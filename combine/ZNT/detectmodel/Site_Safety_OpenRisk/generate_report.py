from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from site_safety.factory import build_report_adapter
from site_safety.pipeline.orchestrator import TrainingFreeInspector
from site_safety.road_domain import build_road_management_prompt as build_report_prompt, validate_road_config
from site_safety.schemas import ManagementReport, SecondPassResponse
from site_safety.utils.config import load_yaml
from site_safety.utils.json_tools import parse_json_object


def _load_memory(config: Dict[str, Any], root: Path) -> List[Dict[str, Any]]:
    memory: List[Dict[str, Any]] = []
    for configured_path in config.get("report_llm", {}).get("memory_paths", []):
        path = Path(configured_path)
        if not path.is_absolute():
            path = root / path
        if path.is_file():
            memory.append(
                {
                    "source": str(configured_path),
                    "content": json.loads(path.read_text(encoding="utf-8")),
                }
            )
    return memory


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate or regenerate a management report without rerunning vision models"
    )
    parser.add_argument("--visual-verification", required=True)
    parser.add_argument("--config", default="configs/road_offline.yaml")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument(
        "--reuse-existing-final",
        action="store_true",
        help="Synchronize an existing final_report.json into result.json without another API call",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = root / config_path
    visual_path = Path(args.visual_verification)
    if not visual_path.is_absolute():
        visual_path = root / visual_path
    output_dir = Path(args.output_dir) if args.output_dir else visual_path.parent
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    config = load_yaml(config_path)
    if config.get("domain") != "road":
        raise ValueError("Use a road-domain config for report generation")
    validate_road_config(config, root)
    visual = SecondPassResponse.model_validate(
        json.loads(visual_path.read_text(encoding="utf-8"))
    )
    final_report_path = output_dir / "final_report.json"
    if args.reuse_existing_final:
        report = ManagementReport.model_validate(
            json.loads(final_report_path.read_text(encoding="utf-8"))
        )
    else:
        report_llm = build_report_adapter(config, root)
        if report_llm is None:
            report = TrainingFreeInspector._build_template_report(visual)
        else:
            try:
                prompt = build_report_prompt(visual.model_dump(), _load_memory(config, root))
                raw = report_llm.generate_json([], prompt)
                report_tag = str(config.get("report_llm", {}).get("generated_by", "glm"))
                (output_dir / f"{report_tag}_report_raw.txt").write_text(raw, encoding="utf-8")
                report = ManagementReport.model_validate(parse_json_object(raw))
                report.generated_by = report_tag
                report = TrainingFreeInspector._guard_management_report(report, visual)
            except Exception as exc:
                report_tag = str(config.get("report_llm", {}).get("generated_by", "glm"))
                (output_dir / f"{report_tag}_report_error.txt").write_text(
                    f"{type(exc).__name__}: {exc}",
                    encoding="utf-8",
                )
                report = TrainingFreeInspector._build_template_report(visual)

    report_payload = report.model_dump()
    final_report_path.write_text(
        json.dumps(report_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    result_path = output_dir / "result.json"
    if result_path.is_file():
        result_payload = json.loads(result_path.read_text(encoding="utf-8"))
        result_payload["management_report"] = report_payload
        result_path.write_text(
            json.dumps(result_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    report_tag = str(config.get("report_llm", {}).get("generated_by", "glm"))
    if report.generated_by == report_tag:
        (output_dir / f"{report_tag}_report_error.txt").unlink(missing_ok=True)
    TrainingFreeInspector._write_summary(output_dir, report)
    print(f"Report completed: {output_dir / 'final_report.json'}")


if __name__ == "__main__":
    main()
