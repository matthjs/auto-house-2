"""
Providers that speak the OpenAI Chat Completions API: OpenAI and DeepSeek.
"""

import json

import openai
from pydantic import ValidationError

from src.llm.base import LLMError, LLMProvider, SchemaT


class OpenAICompatibleProvider(LLMProvider):
    """
    Base for Chat Completions providers.

    With ``strict_schema`` the request uses Structured Outputs (the answer is
    guaranteed to match the schema). Without it, the request uses JSON mode and the
    schema is described in the system prompt, which is what DeepSeek supports.
    """

    base_url: str | None = None
    strict_schema: bool = True

    def __init__(self, model: str, api_key: str | None) -> None:
        """
        Create a client for this provider's endpoint.

        :param model: Model id.
        :param api_key: API key. ``None`` lets the SDK read ``OPENAI_API_KEY``, which
            is only allowed for OpenAI itself.
        :raises LLMError: If no usable key is available.
        """
        super().__init__(model, api_key)
        if api_key is None and self.base_url is not None:
            # The SDK would fall back to OPENAI_API_KEY and send it to this endpoint.
            raise LLMError(f"No API key for {self.name}; see the README for setup.")
        try:
            self.client = openai.OpenAI(api_key=api_key, base_url=self.base_url)
        except openai.OpenAIError as error:
            raise LLMError(
                f"Could not create the {self.name} client: {error}"
            ) from error

    def generate(self, system: str, prompt: str, schema: type[SchemaT]) -> SchemaT:
        """
        Run one request and parse the answer into ``schema``.

        :param system: System prompt with the instructions.
        :param prompt: User message with the data to work on.
        :param schema: Pydantic model the answer must match.
        :return: The parsed answer.
        :raises LLMError: If the call fails, is refused, or the answer does not parse.
        """
        try:
            if self.strict_schema:
                return self._generate_structured(system, prompt, schema)
            return self._generate_json_mode(system, prompt, schema)
        except openai.APIError as error:
            raise LLMError(f"{self.name} request failed: {error}") from error

    def _generate_structured(
        self, system: str, prompt: str, schema: type[SchemaT]
    ) -> SchemaT:
        """
        Call Chat Completions with Structured Outputs.

        :param system: System prompt.
        :param prompt: User message.
        :param schema: Pydantic model the answer must match.
        :return: The parsed answer.
        :raises LLMError: If the model refuses or returns nothing.
        """
        completion = self.client.chat.completions.parse(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            response_format=schema,
        )
        message = completion.choices[0].message
        if message.refusal:
            raise LLMError(f"{self.name} refused: {message.refusal}")
        if message.parsed is None:
            raise LLMError(f"{self.name} returned no parsable answer")
        return message.parsed

    def _generate_json_mode(
        self, system: str, prompt: str, schema: type[SchemaT]
    ) -> SchemaT:
        """
        Call Chat Completions in JSON mode and validate the answer locally.

        :param system: System prompt; the JSON schema is appended to it.
        :param prompt: User message.
        :param schema: Pydantic model the answer must match.
        :return: The parsed answer.
        :raises LLMError: If the answer is empty or does not match the schema.
        """
        schema_json = json.dumps(schema.model_json_schema())
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": f"{system}\n\nAnswer with one JSON object that "
                    f"matches this JSON schema:\n{schema_json}",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        content = (completion.choices[0].message.content or "").strip()
        if not content:
            raise LLMError(f"{self.name} returned an empty answer")
        try:
            return schema.model_validate_json(content)
        except ValidationError as error:
            raise LLMError(
                f"{self.name} answer did not match {schema.__name__}"
            ) from error


class OpenAIProvider(OpenAICompatibleProvider):
    """
    OpenAI models, with Structured Outputs.
    """

    name = "openai"


class DeepSeekProvider(OpenAICompatibleProvider):
    """
    DeepSeek models through their OpenAI-compatible endpoint, in JSON mode.
    """

    name = "deepseek"
    base_url = "https://api.deepseek.com"
    strict_schema = False
