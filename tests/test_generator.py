import json

from rag.generator import build_user_message, generate, parse_answer
from rag.llm import LLMReply
from rag.pipeline import answer_question
from rag.schemas import RetrievedChunk


class FakeLLM:
    """Returns the queued replies in order and records every call."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, system, messages):
        self.calls.append((system, [dict(m) for m in messages]))
        return LLMReply(self.replies.pop(0), input_tokens=10, output_tokens=5)


def chunk(chunk_id="a.md::0", text="The capital of France is Paris.", score=0.8):
    return RetrievedChunk(
        chunk_id=chunk_id, doc_id="a.md", page=None, text=text,
        char_start=0, char_end=len(text), score=score,
    )


def answered_json(quote="The capital of France is Paris."):
    return json.dumps({
        "status": "answered",
        "answer": "Paris.",
        "claims": [{"text": "Paris is the capital.", "citations": [
            {"chunk_id": "a.md::0", "doc_id": "a.md", "page": None, "quote": quote}]}],
        "confidence": 0.9,
        "reason": None,
    })


def test_parse_answer_accepts_fenced_json_and_surrounding_prose():
    assert parse_answer(f"```json\n{answered_json()}\n```").status == "answered"
    assert parse_answer(f"Here you go: {answered_json()} Hope that helps.").status == "answered"


def test_user_message_contains_chunk_ids_text_and_question():
    message = build_user_message("What is the capital?", [chunk()])
    assert "a.md::0" in message and "Paris" in message and "What is the capital?" in message


def test_valid_reply_needs_one_attempt_and_counts_tokens():
    result = generate("q", [chunk()], FakeLLM(answered_json()))
    assert result.valid and result.attempts == 1
    assert (result.input_tokens, result.output_tokens) == (10, 5)


def test_invalid_reply_is_retried_with_the_error_fed_back():
    llm = FakeLLM("not json at all", answered_json())
    result = generate("q", [chunk()], llm, max_retries=2)

    assert result.valid and result.attempts == 2
    retry_messages = llm.calls[1][1]
    assert retry_messages[1] == {"role": "assistant", "content": "not json at all"}
    assert "invalid" in retry_messages[2]["content"]


def test_inconsistent_answer_is_rejected_then_retried():
    answered_without_claims = json.dumps(
        {"status": "answered", "answer": "x", "claims": [], "confidence": 0.5})
    result = generate("q", [chunk()], FakeLLM(answered_without_claims, answered_json()))
    assert result.valid and result.attempts == 2


def test_abstains_when_retries_run_out():
    llm = FakeLLM("bad", "bad", "bad")
    result = generate("q", [chunk()], llm, max_retries=2)

    assert not result.valid and result.attempts == 3
    assert result.answer.status == "abstained"
    assert llm.replies == []


def test_pipeline_gate_failure_skips_the_llm():
    llm = FakeLLM()
    result = answer_question("q", [chunk(score=0.1)], llm, min_score=0.3, max_retries=2)

    assert result.answer.status == "abstained"
    assert result.generation is None and llm.calls == []


def test_pipeline_removes_fabricated_citation():
    llm = FakeLLM(answered_json(quote="The capital of France is Lyon."))
    result = answer_question("q", [chunk()], llm, min_score=0.3, max_retries=2)

    assert result.answer.status == "abstained"
    assert result.verification.claims_passed == 0


def test_pipeline_returns_verified_answer():
    result = answer_question("q", [chunk()], FakeLLM(answered_json()), min_score=0.3, max_retries=2)
    assert result.answer.status == "answered"
    assert result.verification.claim_pass_rate == 1.0


def test_model_abstention_with_blank_answer_gets_the_standard_message():
    blank = json.dumps({"status": "abstained", "answer": "", "claims": [],
                        "confidence": 0.0, "reason": "Not in the context."})
    result = answer_question("q", [chunk()], FakeLLM(blank), 0.3, 2)

    assert result.answer.status == "abstained"
    assert result.answer.answer == "The provided documents do not contain this information."


def test_parse_answer_survives_a_code_fence_inside_a_quote():
    quote = 'and a JSON response of:\n\n```JSON\n{"detail": "Item not found"}\n```'
    reply = "```json\n" + answered_json(quote=quote) + "\n```"

    answer = parse_answer(reply)

    assert answer.status == "answered"
    assert answer.claims[0].citations[0].quote == quote
