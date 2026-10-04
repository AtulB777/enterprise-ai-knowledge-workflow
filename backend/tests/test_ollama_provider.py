"""Tests for OllamaProvider's own logic (request construction, response
parsing) — mocking the httpx transport layer with a real MockTransport,
not a hand-rolled stub, so requests actually flow through httpx's real
request-building code.
"""

import json

import httpx
import pytest

from app.services.llm.ollama_provider import OllamaProvider
from app.services.llm.provider import LLMMessage


def _patch_httpx_client_with_mock_transport(monkeypatch, handler) -> None:
    mock_transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = mock_transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched_client)


async def test_complete_sends_correct_request_shape(monkeypatch) -> None:
    captured_request = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["json"] = json.loads(request.content)
        captured_request["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "model": "llama3.1:8b",
                "message": {"role": "assistant", "content": "Test response."},
                "prompt_eval_count": 15,
                "eval_count": 5,
            },
        )

    _patch_httpx_client_with_mock_transport(monkeypatch, handler)

    provider = OllamaProvider(base_url="http://localhost:11434", model="llama3.1:8b")
    result = await provider.complete(
        system="You are a test assistant.",
        messages=[LLMMessage(role="user", content="Hello")],
        max_tokens=50,
    )

    assert captured_request["url"] == "http://localhost:11434/api/chat"
    assert captured_request["json"]["model"] == "llama3.1:8b"
    assert captured_request["json"]["messages"][0] == {
        "role": "system",
        "content": "You are a test assistant.",
    }
    assert captured_request["json"]["messages"][1] == {"role": "user", "content": "Hello"}
    assert captured_request["json"]["options"]["num_predict"] == 50
    assert captured_request["json"]["stream"] is False

    assert result.content == "Test response."
    assert result.model == "llama3.1:8b"
    assert result.input_tokens == 15
    assert result.output_tokens == 5


async def test_complete_raises_on_http_error(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "internal error"})

    _patch_httpx_client_with_mock_transport(monkeypatch, handler)

    provider = OllamaProvider(base_url="http://localhost:11434", model="llama3.1:8b")
    with pytest.raises(httpx.HTTPStatusError):
        await provider.complete(
            system="sys", messages=[LLMMessage(role="user", content="q")], max_tokens=50
        )
