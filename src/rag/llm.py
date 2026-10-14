"""Thin LLM client. The pipeline depends on the `LLM` protocol, so tests use a fake."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LLMReply:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


class LLM(Protocol):
    def complete(self, system: str, messages: list[dict[str, str]]) -> LLMReply: ...


class AnthropicLLM:
    """Uses ANTHROPIC_API_KEY from the environment."""

    def __init__(self, model: str, max_tokens: int = 2048):
        if not model:
            raise ValueError("LLM_MODEL is not set")
        import anthropic

        self._client = anthropic.Anthropic()
        self._model = model
        self._max_tokens = max_tokens

    def complete(self, system: str, messages: list[dict[str, str]]) -> LLMReply:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=0,
            system=system,
            messages=messages,
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return LLMReply(text, response.usage.input_tokens, response.usage.output_tokens)
