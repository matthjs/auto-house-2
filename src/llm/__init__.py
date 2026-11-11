"""
LLM providers behind one interface. Pick one with :func:`create_provider`.
"""

from src.llm.base import LLMError, LLMProvider

DEFAULT_MODELS: dict[str, str] = {
    "deepseek": "deepseek-flash",
    "openai": "gpt-6-luna",
    "claude": "claude-opus-5-5",
}
PROVIDERS = tuple(DEFAULT_MODELS)

__all__ = ["DEFAULT_MODELS", "PROVIDERS", "LLMError", "LLMProvider", "create_provider"]


def create_provider(
    name: str, api_key: str | None, model: str | None = None
) -> LLMProvider:
    """
    Build a provider by name.

    The vendor SDK is imported here, so a broken or missing SDK only matters for the
    provider you use.

    :param name: One of :data:`PROVIDERS`.
    :param api_key: API key, or ``None`` to let the SDK find one.
    :param model: Model id; defaults to the entry in :data:`DEFAULT_MODELS`.
    :return: A ready-to-use provider.
    :raises ValueError: If ``name`` is not a known provider.
    """
    if name not in DEFAULT_MODELS:
        raise ValueError(
            f"Unknown provider '{name}'. Choose from: {', '.join(PROVIDERS)}"
        )
    model = model or DEFAULT_MODELS[name]
    if name == "deepseek":
        from src.llm.openai_compat import DeepSeekProvider

        return DeepSeekProvider(model, api_key)
    if name == "openai":
        from src.llm.openai_compat import OpenAIProvider

        return OpenAIProvider(model, api_key)
    from src.llm.claude import ClaudeProvider

    return ClaudeProvider(model, api_key)
