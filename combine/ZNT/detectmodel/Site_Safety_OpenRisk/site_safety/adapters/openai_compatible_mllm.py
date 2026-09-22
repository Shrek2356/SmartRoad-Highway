from __future__ import annotations

import base64
import io
import json
import time
from typing import Any, Dict, Sequence

import httpx
from PIL import Image

from site_safety.adapters.base import MLLMAdapter


class OpenAICompatibleMLLMAdapter(MLLMAdapter):
    """Generic multimodal chat-completions adapter.

    Many providers accept the OpenAI-style image_url payload. If your provider
    uses a different schema, edit only `_build_payload`; the rest of the project
    can remain unchanged.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        system_prompt: str,
        timeout_seconds: float = 120,
        temperature: float = 0.1,
        use_response_format: bool = True,
        payload_extra: Dict[str, Any] | None = None,
        max_retries: int = 2,
        trust_env: bool = True,
    ) -> None:
        if not api_key:
            raise ValueError("MLLM API key is empty")
        if not base_url:
            raise ValueError("MLLM base URL is empty")
        if not model:
            raise ValueError("MLLM model is empty")
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.system_prompt = system_prompt
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.use_response_format = use_response_format
        self.payload_extra = dict(payload_extra or {})
        self.max_retries = max(0, int(max_retries))
        self.trust_env = bool(trust_env)

    @staticmethod
    def _to_data_url(image: Image.Image) -> str:
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="JPEG", quality=90)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{encoded}"

    def _build_payload(self, images: Sequence[Image.Image], prompt: str) -> Dict[str, Any]:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for image in images:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": self._to_data_url(image)},
                }
            )
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": content},
            ],
            "temperature": self.temperature,
        }
        if self.use_response_format:
            payload["response_format"] = {"type": "json_object"}
        payload.update(self.payload_extra)
        return payload

    def generate_json(self, images: Sequence[Image.Image], prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = self._build_payload(images, prompt)
        with httpx.Client(
            timeout=self.timeout_seconds,
            trust_env=self.trust_env,
        ) as client:
            for attempt in range(self.max_retries + 1):
                try:
                    response = client.post(self.base_url, headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()
                    break
                except httpx.HTTPStatusError as exc:
                    retryable = exc.response.status_code == 429 or exc.response.status_code >= 500
                    if attempt >= self.max_retries or not retryable:
                        body = exc.response.text[:2000]
                        raise RuntimeError(
                            f"MLLM HTTP {exc.response.status_code}: {body or '<empty response>'}"
                        ) from exc
                    time.sleep(1.5 * (attempt + 1))
                except (httpx.TransportError, json.JSONDecodeError):
                    # llama.cpp may occasionally close a successful HTTP response
                    # after emitting only part of its OpenAI-compatible JSON body.
                    # This is an adapter/transport failure, not a model verdict;
                    # retry the exact request before exposing it to the pipeline.
                    if attempt >= self.max_retries:
                        raise
                    time.sleep(1.5 * (attempt + 1))
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected MLLM response schema: {data}") from exc
        if not isinstance(content, str):
            raise RuntimeError(f"MLLM content is not a string: {type(content)!r}")
        return content
