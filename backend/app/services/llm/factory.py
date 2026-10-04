from app.core.config import get_settings
from app.services.llm.anthropic_provider import AnthropicProvider
from app.services.llm.instrumented_provider import InstrumentedLLMProvider
from app.services.llm.ollama_provider import OllamaProvider
from app.services.llm.provider import LLMProvider


def get_llm_provider() -> LLMProvider:
    provider = get_settings().llm_provider
    if provider == "anthropic":
        return InstrumentedLLMProvider(AnthropicProvider(), provider_name="anthropic")
    if provider == "ollama":
        return InstrumentedLLMProvider(OllamaProvider(), provider_name="ollama")
    raise NotImplementedError(
        f"LLM provider '{provider}' is not implemented yet. "
        "Implemented: ollama, anthropic. See ADR-010."
    )
