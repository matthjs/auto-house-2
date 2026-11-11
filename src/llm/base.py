"""
The interface every LLM provider implements.
"""

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class LLMError(RuntimeError):
    """
    Raised when a provider call fails or returns output that does not fit the schema.
    """


class LLMProvider(ABC):
    """
    A chat model that answers with JSON matching a Pydantic schema.

    Subclasses wrap one vendor SDK. They never send ``temperature`` or other sampling
    parameters, because several current models reject them.
    """

    name: str = ""

    def __init__(self, model: str, api_key: str | None) -> None:
        """
        Configure the provider.

        :param model: Model id to call.
        :param api_key: API key, or ``None`` to let the SDK find one itself.
        """
        self.model = model
        self.api_key = api_key

    @abstractmethod
    def generate(self, system: str, prompt: str, schema: type[SchemaT]) -> SchemaT:
        """
        Run one request and parse the answer into ``schema``.

        :param system: System prompt with the instructions.
        :param prompt: User message with the data to work on.
        :param schema: Pydantic model the answer must match.
        :return: The parsed answer.
        :raises LLMError: If the call fails, is refused, or the answer does not parse.
        """
