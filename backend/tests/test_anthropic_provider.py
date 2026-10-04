"""Tests for AnthropicProvider's own logic (request construction, response
parsing) — mocking the actual network call via the real installed SDK's
client, not the import boundary (unlike ADR-008/009's providers, the
`anthropic` SDK is lightweight and genuinely installed here — see ADR-010).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.llm.anthropic_provider import AnthropicProvider
from app.services.llm.provider import LLMMessage


def _fake_anthropic_response(
    *, text: str = "A test response.", model: str = "claude-sonnet-4-5-20250929"
) -> SimpleNamespace:
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        model=model,
        usage=SimpleNamespace(input_tokens=42, output_tokens=7),
    )


async def test_complete_sends_system_and_messages_correctly() -> None:
    provider = AnthropicProvider(api_key="fake-test-key", model="fake-model")
    provider._client.messages.create = AsyncMock(return_value=_fake_anthropic_response())

    await provider.complete(
        system="You are a test assistant.",
        messages=[LLMMessage(role="user", content="What is the capital of France?")],
        max_tokens=100,
    )

    call_kwargs = provider._client.messages.create.call_args.kwargs
    assert call_kwargs["system"] == "You are a test assistant."
    assert call_kwargs["model"] == "fake-model"
    assert call_kwargs["max_tokens"] == 100
    assert call_kwargs["messages"] == [
        {"role": "user", "content": "What is the capital of France?"}
    ]


async def test_complete_parses_response_correctly() -> None:
    provider = AnthropicProvider(api_key="fake-test-key")
    provider._client.messages.create = AsyncMock(
        return_value=_fake_anthropic_response(text="Paris is the capital.")
    )

    result = await provider.complete(
        system="sys", messages=[LLMMessage(role="user", content="q")], max_tokens=100
    )

    assert result.content == "Paris is the capital."
    assert result.model == "claude-sonnet-4-5-20250929"
    assert result.input_tokens == 42
    assert result.output_tokens == 7


async def test_complete_concatenates_multiple_text_blocks() -> None:
    provider = AnthropicProvider(api_key="fake-test-key")
    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="First part. "),
            SimpleNamespace(type="text", text="Second part."),
        ],
        model="fake-model",
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )
    provider._client.messages.create = AsyncMock(return_value=response)

    result = await provider.complete(
        system="sys", messages=[LLMMessage(role="user", content="q")], max_tokens=100
    )

    assert result.content == "First part. Second part."


def test_missing_api_key_raises_clear_error() -> None:
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        AnthropicProvider(api_key=None)
