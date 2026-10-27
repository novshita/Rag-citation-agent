import pytest
from google.genai import errors

from rag.llm import AnthropicLLM, GeminiLLM, make_llm


class Usage:
    prompt_token_count = 7
    candidates_token_count = 3


class Response:
    text = "hello"
    usage_metadata = Usage()


class FakeModels:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append((model, contents, config))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeClient:
    def __init__(self, *outcomes):
        self.models = FakeModels(outcomes)


def api_error(code):
    return errors.APIError(code, {"error": {"message": "x", "status": "X"}})


def gemini(client, waits):
    return GeminiLLM("m", client=client, sleep=waits.append)


def test_maps_roles_and_reads_usage():
    client = FakeClient(Response())
    reply = gemini(client, []).complete(
        "sys", [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}])

    contents = client.models.calls[0][1]
    assert [c["role"] for c in contents] == ["user", "model"]
    assert client.models.calls[0][2].system_instruction == "sys"
    assert (reply.text, reply.input_tokens, reply.output_tokens) == ("hello", 7, 3)


def test_rate_limit_is_retried_with_waiting():
    waits = []
    client = FakeClient(api_error(429), api_error(503), Response())
    reply = gemini(client, waits).complete("s", [{"role": "user", "content": "q"}])

    assert reply.text == "hello" and waits == [5, 15]


def test_other_errors_are_not_retried():
    waits = []
    with pytest.raises(errors.APIError):
        gemini(FakeClient(api_error(400)), waits).complete("s", [{"role": "user", "content": "q"}])
    assert waits == []


def test_gives_up_after_the_last_retry():
    waits = []
    client = FakeClient(*[api_error(429)] * 5)
    with pytest.raises(errors.APIError):
        gemini(client, waits).complete("s", [{"role": "user", "content": "q"}])
    assert waits == [5, 15, 30, 60]


def test_missing_model_and_unknown_provider_are_rejected():
    with pytest.raises(ValueError, match="LLM_MODEL"):
        make_llm("gemini", "")
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        make_llm("nope", "m")
    with pytest.raises(ValueError, match="LLM_MODEL"):
        AnthropicLLM("")
