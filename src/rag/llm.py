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


class GeminiLLM:
    """Google Gemini via the google-genai SDK. Uses GEMINI_API_KEY from the environment.

    The free tier is rate limited, so rate-limit and overload errors are retried with a wait.
    """

    RETRY_WAITS = (5, 15, 30, 60)   # seconds before each retry
    RETRYABLE = (429, 500, 503)

    def __init__(self, model: str, max_tokens: int = 8192, client=None, sleep=None):
        if not model:
            raise ValueError("LLM_MODEL is not set")
        import time

        if client is None:
            from google import genai

            client = genai.Client()
        self._client = client
        self._model = model
        self._max_tokens = max_tokens
        self._sleep = sleep or time.sleep

    def complete(self, system: str, messages: list[dict[str, str]]) -> LLMReply:
        from google.genai import errors, types

        contents = [
            {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
            for m in messages
        ]
        config = types.GenerateContentConfig(
            system_instruction=system, temperature=0, max_output_tokens=self._max_tokens,
        )
        for wait in (*self.RETRY_WAITS, None):
            try:
                response = self._client.models.generate_content(
                    model=self._model, contents=contents, config=config,
                )
                break
            except errors.APIError as error:
                if wait is None or error.code not in self.RETRYABLE:
                    raise
                self._sleep(wait)
        usage = response.usage_metadata
        return LLMReply(
            response.text or "",
            getattr(usage, "prompt_token_count", 0) or 0,
            getattr(usage, "candidates_token_count", 0) or 0,
        )


def make_llm(provider: str, model: str) -> LLM:
    if provider == "gemini":
        return GeminiLLM(model)
    if provider == "anthropic":
        return AnthropicLLM(model)
    raise ValueError(f"unknown LLM_PROVIDER {provider!r} (use 'gemini' or 'anthropic')")
