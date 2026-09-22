import json

from site_safety.adapters.openai_compatible_mllm import OpenAICompatibleMLLMAdapter


def test_retries_truncated_openai_response_json(monkeypatch) -> None:
    class Response:
        def __init__(self, attempt: int) -> None:
            self.attempt = attempt

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            if self.attempt == 1:
                raise json.JSONDecodeError("truncated", "{", 1)
            return {"choices": [{"message": {"content": "{\"ok\": true}"}}]}

    class Client:
        posts = 0

        def __init__(self, **_: object) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def post(self, *_: object, **__: object) -> Response:
            type(self).posts += 1
            return Response(type(self).posts)

    monkeypatch.setattr(
        "site_safety.adapters.openai_compatible_mllm.httpx.Client", Client
    )
    monkeypatch.setattr(
        "site_safety.adapters.openai_compatible_mllm.time.sleep", lambda _: None
    )
    adapter = OpenAICompatibleMLLMAdapter(
        api_key="test",
        base_url="http://127.0.0.1:8088/v1/chat/completions",
        model="test-model",
        system_prompt="json only",
        max_retries=1,
    )

    assert adapter.generate_json([], "return JSON") == '{"ok": true}'
    assert Client.posts == 2
