"""
Anthropic Claude provider, using the official ``anthropic`` SDK.
"""

import anthropic

from src.llm.base import LLMError, LLMProvider, SchemaT

# Models that accept the server-side refusal fallback (re-run on another model).
FALLBACK_MODELS = (
    "claude-fable-5-2",
    "claude-fable-5-1",
    "claude-opus-5-5",
    "claude-opus-5",
    "claude-sonnet-5-5",
)
# Model families that accept output_config.effort.
EFFORT_PREFIXES = (
    "claude-fable-5",
    "claude-mythos-5",
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-haiku-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-sonnet-4-6",
)
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeProvider(LLMProvider):
    """
    Claude with Structured Outputs (``messages.parse`` with a Pydantic model).

    On models that support it, refused requests fall back to another model on the
    server (``fallbacks="default"``).
    """

    name = "claude"

    def __init__(self, model: str, api_key: str | None, effort: str = "medium") -> None:
        """
        Create a Claude client.

        :param model: Claude model id, for example ``claude-opus-5-5``.
        :param api_key: API key; ``None`` lets the SDK find credentials itself
            (``ANTHROPIC_API_KEY`` or an ``ant auth login`` profile).
        :param effort: Thinking effort, ``low`` to ``max``; ignored on older models.
        """
        super().__init__(model, api_key)
        self.effort = effort
        self.client = anthropic.Anthropic(api_key=api_key)

    def generate(self, system: str, prompt: str, schema: type[SchemaT]) -> SchemaT:
        """
        Run one request and parse the answer into ``schema``.

        :param system: System prompt with the instructions.
        :param prompt: User message with the data to work on.
        :param schema: Pydantic model the answer must match.
        :return: The parsed answer.
        :raises LLMError: If the call fails, is refused, is cut off, or does not parse.
        """
        options: dict = {}
        if self.model.startswith(EFFORT_PREFIXES):
            options["output_config"] = {"effort": self.effort}
        if self.model in FALLBACK_MODELS:
            options["betas"] = [FALLBACK_BETA]
            options["fallbacks"] = "default"

        try:
            response = self.client.beta.messages.parse(
                model=self.model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_format=schema,
                **options,
            )
        except anthropic.APIError as error:
            raise LLMError(f"Claude request failed: {error}") from error

        if response.stop_reason == "refusal":
            raise LLMError("Claude declined this request")
        if response.stop_reason == "max_tokens":
            raise LLMError("Claude's answer was cut off at max_tokens")
        if response.parsed_output is None:
            raise LLMError(f"Claude answer did not match {schema.__name__}")
        return response.parsed_output
