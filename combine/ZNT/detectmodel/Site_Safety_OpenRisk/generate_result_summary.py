from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Iterable


def _load_json(path: Path, fallback: Any = None) -> Any:
    if not path.is_file():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def _md_path(target: Path, document_dir: Path) -> str:
    return Path(os.path.relpath(target.resolve(), document_dir.resolve())).as_posix()


def _image(label: str, target: Path, document_dir: Path) -> str:
    return f"![{label}](<{_md_path(target, document_dir)}>)"


def _link(label: str, target: Path, document_dir: Path) -> str:
    return f"[{label}](<{_md_path(target, document_dir)}>)"


def _cell(value: Any) -> str:
    text = str(value if value is not None else "")
    return text.replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _risk_map(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("risk_id")): item
        for item in report.get("risks", [])
        if item.get("risk_id")
    }


def _candidate_map(first_pass: dict[str, Any]) -> dict[str, dict[str, Any]]:
    values = first_pass.get("candidate_assessments", []) + first_pass.get(
        "open_discoveries", []
    )
    return {
        str(item.get("risk_id")): item
        for item in values
        if item.get("risk_id")
    }


def _evidence_map(evidences: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("risk_id")): item
        for item in evidences
        if item.get("risk_id")
    }


def _status_text(risks: list[dict[str, Any]]) -> str:
    verified = [risk for risk in risks if risk.get("verified")]
    if verified:
        return "；".join(str(risk.get("risk_name_zh") or risk.get("risk_id")) for risk in verified)
    if risks:
        return "候选风险未通过自动证据门控"
    return "未发现进入最终核验的风险"


def _collect_runs(batch_dir: Path) -> list[dict[str, Any]]:
    summary = _load_json(batch_dir / "batch_summary.json", [])
    indexed_images = {
        Path(str(item.get("output_dir", ""))).name: Path(str(item["image"]))
        for item in summary
        if item.get("image") and item.get("output_dir")
    }
    runs: list[dict[str, Any]] = []
    for run_dir in sorted((path for path in batch_dir.iterdir() if path.is_dir()), key=lambda p: p.name):
        result = _load_json(run_dir / "result.json")
        if not isinstance(result, dict):
            continue
        image_value = result.get("image_path")
        image_path = Path(str(image_value)) if image_value else indexed_images.get(run_dir.name)
        # Delivery packages may carry a self-contained images/ directory while
        # the archived result.json still records the original machine path.
        # Prefer that package-local copy so generated Markdown remains portable.
        local_images_dir = batch_dir / "images"
        for suffix in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
            local_image = local_images_dir / f"{run_dir.name}{suffix}"
            if local_image.is_file():
                image_path = local_image
                break
        if image_path is None:
            continue
        visual = result.get("visual_verification") or result.get("final_report") or {}
        management = result.get("management_report") or _load_json(
            run_dir / "final_report.json", {}
        )
        runs.append(
            {
                "dir": run_dir,
                "image": image_path,
                "first": result.get("first_pass") or _load_json(run_dir / "first_pass.json", {}),
                "evidences": result.get("evidences")
                or _load_json(run_dir / "evidence.json", []),
                "visual": visual,
                "management": management,
            }
        )
    if not runs:
        raise FileNotFoundError(f"No completed result.json files found in: {batch_dir}")
    return runs


def _append_list(lines: list[str], title: str, values: Iterable[Any]) -> None:
    items = [str(value).strip() for value in values if str(value).strip()]
    lines.append(f"- {title}：")
    lines.extend([f"  - {item}" for item in items] or ["  - 无"])


def build_markdown(batch_dir: Path, output_path: Path, title: str) -> str:
    runs = _collect_runs(batch_dir)
    document_dir = output_path.parent
    verified_images = sum(
        any(risk.get("verified") for risk in run["visual"].get("final_risks", []))
        for run in runs
    )
    review_images = sum(
        any(risk.get("manual_review_required") for risk in run["visual"].get("final_risks", []))
        for run in runs
    )
    verified_risks = sum(
        sum(bool(risk.get("verified")) for risk in run["visual"].get("final_risks", []))
        for run in runs
    )
    review_risks = sum(
        sum(
            bool(risk.get("manual_review_required"))
            for risk in run["visual"].get("final_risks", [])
        )
        for run in runs
    )
    missing_mask_images = sum(
        not any(
            evidence.get("risk_mask_path")
            and (run["dir"] / str(evidence["risk_mask_path"])).is_file()
            for evidence in run["evidences"]
        )
        for run in runs
    )
    report_sources = {
        str(run["management"].get("generated_by", "unknown")) for run in runs
    }
    if report_sources == {"qwen_local"}:
        report_label = "本地 Qwen"
    elif report_sources == {"glm"}:
        report_label = "GLM"
    else:
        report_label = "配置的报告模型（" + "、".join(sorted(report_sources)) + "）"

    lines = [
        f"# {title}",
        "",
        "## 1. 输出说明",
        "",
        "本报告由批次检测结构化产物自动生成。视觉事实以 `visual_verification.json` 为准，"
        f"{report_label} 管理报告仅补充摘要、管理建议和整改动作，不得改变风险确认状态、置信度、"
        "可见证据或人工复核要求。",
        "",
        "## 2. 固定处理流程",
        "",
        "```mermaid",
        "flowchart LR",
        '    A["输入图像"] --> B["SAM3 人员预检与局部裁剪"]',
        '    A --> C["Qwen 全景开放风险发现"]',
        '    B --> D["Qwen 人员视角开放风险发现"]',
        '    C --> E["去重、低置信过滤与条件复询"]',
        '    D --> E',
        '    E --> F["逐风险 RiskSpec 编译"]',
        '    F --> G["SAM3 实体定位与分割"]',
        '    G --> H["几何空间关系核验（CLIP为可选适配器）"]',
        '    H --> I["风险掩码、叠加图与裁剪图"]',
        '    I --> J["Qwen 第二遍视觉核验"]',
        '    J --> K["硬证据门控"]',
        f'    K --> L["{report_label} 管理报告"]',
        "```",
        "",
        "1. SAM3 先定位人员并生成少量人员裁剪，保留原始全景。",
        "2. Qwen 分别从全景和人员裁剪开放发现风险，不遍历固定风险目录。",
        "3. 程序合并两路发现、过滤低置信项，并只对摘要已出现但被遗漏的高危关系条件复询。",
        "4. 每个已发现风险单独编译为实体、关系与掩码策略明确的 RiskSpec。",
        "5. SAM3 执行正向实体定位；几何关系模块核验证据。CLIP适配器保留用于消融，但当前当前生产配置关闭。",
        "6. 生成风险掩码、原图叠加证据图和风险裁剪图。",
        "7. Qwen 根据原图及证据图进行第二遍视觉核验。",
        "8. 硬证据门控决定确认、撤销或转人工复核。",
        f"9. {report_label} 根据锁定的视觉事实生成管理报告。",
        "",
        "## 3. 批次总览",
        "",
        f"- 完成图像：{len(runs)}",
        f"- 包含自动确认风险的图像：{verified_images}",
        f"- 自动确认风险总数：{verified_risks}",
        f"- 包含人工复核项的图像：{review_images}",
        f"- 人工复核风险总数：{review_risks}",
        f"- 未生成有效风险掩码的图像：{missing_mask_images}",
        "",
        "| 编号 | 图像 | 最终视觉结果 | 最高置信度 | 自动确认 | 人工复核 | 报告来源 |",
        "|---:|---|---|---:|:---:|:---:|---|",
    ]

    for index, run in enumerate(runs, start=1):
        risks = run["visual"].get("final_risks", [])
        max_conf = max((float(risk.get("confidence", 0.0)) for risk in risks), default=0.0)
        lines.append(
            "| {index} | {name} | {status} | {confidence:.2f} | {verified} | {review} | {source} |".format(
                index=index,
                name=_cell(run["image"].stem),
                status=_cell(_status_text(risks)),
                confidence=max_conf,
                verified="是" if any(risk.get("verified") for risk in risks) else "否",
                review="是" if any(risk.get("manual_review_required") for risk in risks) else "否",
                source=_cell(run["management"].get("generated_by", "unknown")),
            )
        )

    lines.extend(["", "## 4. 分图证据与分析", ""])
    for index, run in enumerate(runs, start=1):
        run_dir: Path = run["dir"]
        visual = run["visual"]
        risks = visual.get("final_risks", [])
        reports = _risk_map(run["management"])
        candidates = _candidate_map(run["first"])
        evidences = _evidence_map(run["evidences"])
        overlays = sorted(run_dir.glob("overlay_*.png"))
        masks = sorted(run_dir.glob("risk_mask_*.png"))

        lines.extend(
            [
                f"### 4.{index} {run['image'].stem}",
                "",
                f"**场景摘要：** {run['first'].get('scene_summary', '无')}",
                "",
                "| 原图 | 风险叠加图 | 风险掩码 |",
                "|---|---|---|",
                "| {original} | {overlays} | {masks} |".format(
                    original=_image(f"样例{index}原图", run["image"], document_dir),
                    overlays="<br>".join(
                        _image(f"样例{index}叠加图{n}", path, document_dir)
                        for n, path in enumerate(overlays, start=1)
                    )
                    or "未生成有效风险叠加图",
                    masks="<br>".join(
                        _image(f"样例{index}掩码{n}", path, document_dir)
                        for n, path in enumerate(masks, start=1)
                    )
                    or "未生成有效风险掩码",
                ),
                "",
            ]
        )

        if not risks:
            lines.extend(["- 最终状态：未产生进入第二遍核验的风险。", ""])
        for risk in risks:
            risk_id = str(risk.get("risk_id", "unknown"))
            report_risk = reports.get(risk_id, {})
            candidate = candidates.get(risk_id, {})
            evidence = evidences.get(risk_id, {})
            absence_status = risk.get("absence_status")
            if absence_status is None:
                absence_status = (
                    "未记录"
                    if any(
                        relation.get("relation_type") == "missing"
                        for relation in evidence.get("relations", [])
                    )
                    else "not_applicable"
                )
            lines.extend(
                [
                    f"#### {risk.get('risk_name_zh') or risk_id}",
                    "",
                    f"- 风险编号：`{risk_id}`",
                    f"- 第一遍状态：`{candidate.get('status', evidence.get('first_pass_status', 'unknown'))}`",
                    f"- 最终确认：{'是' if risk.get('verified') else '否'}",
                    f"- 置信度：`{float(risk.get('confidence', 0.0)):.2f}`",
                    f"- 人工复核：{'是' if risk.get('manual_review_required') else '否'}",
                    f"- 防护缺失状态：`{absence_status}`",
                    f"- 分析结论：{report_risk.get('summary') or risk.get('risk_description') or '无'}",
                ]
            )
            _append_list(lines, "可见证据", risk.get("visible_evidence", []))
            _append_list(lines, "不确定信息", risk.get("uncertainties", []))
            records = evidence.get("segmentations", [])
            if records:
                lines.append("- 定位实体：")
                for record in records:
                    clip_score = record.get("clip_consistency_score")
                    clip_text = (
                        f"，CLIP={float(clip_score):.2f}" if clip_score is not None else ""
                    )
                    lines.append(
                        "  - `{prompt}`：SAM3={score:.2f}{clip}".format(
                            prompt=record.get("prompt", record.get("task_id", "entity")),
                            score=float(record.get("score", 0.0)),
                            clip=clip_text,
                        )
                    )
            else:
                lines.append("- 定位实体：未获得有效 SAM3 实体定位。")
            relations = evidence.get("relations", [])
            if relations:
                lines.append("- 空间关系：")
                for relation in relations:
                    lines.append(
                        "  - `{kind}`：{state}，分数 `{score:.2f}`".format(
                            kind=relation.get("relation_type", "unknown"),
                            state="通过" if relation.get("passed") else "未通过",
                            score=float(relation.get("score", 0.0)),
                        )
                    )
            lines.append("")

        actions = run["management"].get("follow_up_actions", [])
        if actions:
            lines.append("**建议动作：**")
            lines.extend([f"- {action}" for action in actions])
            lines.append("")
        artifact_links = []
        for name in (
            "result.json",
            "first_pass.json",
            "evidence.json",
            "visual_verification.json",
            "final_report.json",
            "summary.md",
        ):
            path = run_dir / name
            if path.is_file():
                artifact_links.append(_link(name, path, document_dir))
        lines.extend(
            [
                "**结构化产物：** " + " · ".join(artifact_links),
                "",
            ]
        )

    lines.extend(
        [
            "## 5. 解释边界",
            "",
            "- 未生成掩码表示关键实体未被稳定定位，不能用语言描述替代视觉证据。",
            "- 对防护栏、安全绳等缺失型风险，应区分“确认缺失”“未观察到”和“被遮挡”。",
            "- 单张图像不能证明设备运行状态、人员权限、施工阶段或画面外情况。",
            "- 所有 `manual_review_required=true` 的风险必须进入现场或原图人工复核。",
            "",
            "## 6. 批次文件",
            "",
        ]
    )
    batch_summary = batch_dir / "batch_summary.json"
    if batch_summary.is_file():
        lines.append(f"- {_link('batch_summary.json', batch_summary, document_dir)}")
    lines.extend(
        [
            "- 每个样例目录中的 `result.json` 是该样例的机器可读总结果。",
            "- `overlay_*.png`、`risk_mask_*.png` 和 `entity_*.png` 构成可审计视觉证据。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a reusable Markdown report from site-safety batch outputs"
    )
    parser.add_argument("--batch-dir", default="outputs/examples_qwen")
    parser.add_argument("--output", default=None)
    parser.add_argument("--title", default="施工现场多模态异常检测最终结果汇总")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    batch_dir = Path(args.batch_dir)
    if not batch_dir.is_absolute():
        batch_dir = root / batch_dir
    output = Path(args.output) if args.output else batch_dir / "FINAL_RESULT_SUMMARY.md"
    if not output.is_absolute():
        output = root / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        build_markdown(batch_dir.resolve(), output.resolve(), args.title),
        encoding="utf-8",
    )
    print(f"Summary completed: {output.resolve()}")


if __name__ == "__main__":
    main()
