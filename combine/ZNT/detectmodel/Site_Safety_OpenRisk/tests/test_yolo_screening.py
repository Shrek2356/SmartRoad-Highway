from site_safety.yolo_screening import YoloDetection, YoloScreeningAdapter


def _adapter() -> YoloScreeningAdapter:
    return YoloScreeningAdapter(
        {"models": [{"weights": "unused.pt"}], "trigger_threshold": 0.35},
        ".",
        model_factory=lambda _: None,
    )


def test_explicit_violation_triggers_and_keeps_context_regions() -> None:
    payload = _adapter().compile_trigger(
        [
            YoloDetection("css", "NO-Hardhat", 0.82, [10, 10, 50, 80]),
            YoloDetection("css", "Person", 0.91, [5, 5, 60, 150]),
        ],
        (640, 480),
    )
    assert payload["triggered"] is True
    assert "missing_helmet" in payload["suspected_concepts"]
    assert {region["label"] for region in payload["suspected_regions"]} == {
        "NO-Hardhat",
        "Person",
    }


def test_neutral_person_does_not_claim_anomaly() -> None:
    payload = _adapter().compile_trigger(
        [YoloDetection("css", "Person", 0.95, [5, 5, 60, 150])],
        (640, 480),
    )
    assert payload["triggered"] is False
    assert payload["suspected_concepts"] == []
    assert payload["anomaly_score"] == 0.0


def test_person_near_machine_is_a_routing_concept() -> None:
    payload = _adapter().compile_trigger(
        [
            YoloDetection("css", "Person", 0.88, [100, 100, 160, 260]),
            YoloDetection("css", "machinery", 0.86, [165, 80, 400, 300]),
        ],
        (640, 480),
    )
    assert payload["triggered"] is True
    assert "person_near_machinery" in payload["suspected_concepts"]
    assert len(payload["suspected_regions"]) == 2
