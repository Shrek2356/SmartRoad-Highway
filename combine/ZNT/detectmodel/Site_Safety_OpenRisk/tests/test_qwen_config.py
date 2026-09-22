from pathlib import Path

from PIL import Image

from site_safety.adapters.openai_compatible_mllm import OpenAICompatibleMLLMAdapter
from site_safety.utils.config import load_yaml


def test_qwen_visual_config_and_payload() -> None:
    root = Path(__file__).resolve().parents[1]
    config = load_yaml(root / "configs" / "qwen_visual.yaml")
    mllm = config["mllm"]
    assert mllm["api_key_env"] == "DASHSCOPE_API_KEY"
    assert mllm["payload_extra"]["enable_thinking"] is False

    adapter = OpenAICompatibleMLLMAdapter(
        api_key="test-key",
        base_url="https://example.invalid/compatible-mode/v1/chat/completions",
        model="qwen3.7-plus",
        system_prompt="test",
        payload_extra=mllm["payload_extra"],
    )
    payload = adapter._build_payload([Image.new("RGB", (8, 8), "gray")], "inspect")
    assert payload["enable_thinking"] is False
    assert payload["model"] == "qwen3.7-plus"
    assert payload["messages"][1]["content"][1]["type"] == "image_url"
