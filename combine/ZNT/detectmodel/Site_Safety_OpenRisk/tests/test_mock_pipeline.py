from pathlib import Path

from PIL import Image

from site_safety.factory import build_inspector
from site_safety.utils.config import load_yaml


def test_mock_pipeline(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    image_path = tmp_path / "image.jpg"
    Image.new("RGB", (320, 240), "gray").save(image_path)
    config = load_yaml(root / "configs" / "default.yaml")
    config["mllm"]["backend"] = "mock"
    config["sam3"]["backend"] = "mock"
    inspector = build_inspector(config, root, allow_legacy=True)
    result = inspector.inspect(image_path, tmp_path / "out")
    assert result.final_report is not None
    assert result.final_report.overall_has_anomaly
    assert result.management_report is not None
    assert result.management_report.generated_by == "deterministic_template"
    assert (tmp_path / "out" / "result.json").exists()
    assert (tmp_path / "out" / "visual_verification.json").exists()
    assert (tmp_path / "out" / "final_report.json").exists()
    assert (tmp_path / "out" / "overlay_worker_under_suspended_load.png").exists()
    entity_masks = list((tmp_path / "out").glob("entity_*.png"))
    assert entity_masks
    assert all(len(path.name) <= len("entity_00_00_00.png") for path in entity_masks)


def test_mock_pipeline_records_and_evaluates_screening_trigger(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    image_path = tmp_path / "image.jpg"
    Image.new("RGB", (320, 240), "gray").save(image_path)
    config = load_yaml(root / "configs" / "default.yaml")
    config["mllm"]["backend"] = "mock"
    config["sam3"]["backend"] = "mock"
    inspector = build_inspector(config, root, allow_legacy=True)

    result = inspector.inspect(
        image_path,
        tmp_path / "triggered_out",
        screening_trigger={
            "triggered": True,
            "anomaly_score": 0.8,
            "suspected_concepts": ["worker under suspended load"],
            "source_model": "test-screening-model",
        },
    )

    assert result.screening_trigger is not None
    assert result.screening_assessment.screening_consistency == "supported"
    assert result.screening_assessment.overall_status == "confirmed_anomaly"
    assert (tmp_path / "triggered_out" / "screening_trigger.json").exists()


def test_coarse_screening_mask_generates_overlay_crop_and_region(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    image_path = tmp_path / "image.jpg"
    Image.new("RGB", (320, 240), "gray").save(image_path)
    mask_path = tmp_path / "coarse_mask.png"
    mask = Image.new("L", (320, 240), 0)
    for x in range(80, 220):
        for y in range(50, 190):
            mask.putpixel((x, y), 255)
    mask.save(mask_path)
    config = load_yaml(root / "configs" / "default.yaml")
    config["mllm"]["backend"] = "mock"
    config["sam3"]["backend"] = "mock"
    inspector = build_inspector(config, root, allow_legacy=True)

    result = inspector.inspect(
        image_path,
        tmp_path / "mask_out",
        screening_trigger={
            "triggered": True,
            "anomaly_score": 0.77,
            "source_model": "coarse-yolo",
        },
        screening_mask_path=mask_path,
    )

    assert result.screening_trigger is not None
    assert result.screening_trigger.suspected_regions[0].region_id == "coarse_mask_1"
    assert (tmp_path / "mask_out" / "screening_mask.png").exists()
    assert (tmp_path / "mask_out" / "screening_overlay.jpg").exists()
