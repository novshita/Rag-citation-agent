"""Build the context-only prompt, call the LLM, and validate its output as a RAGAnswer.

If the reply isn't valid JSON for the schema, the validation error is sent back to
the model and it tries again, up to MAX_RETRIES times. If it never produces a valid
answer, we abstain rather than raise: an unparseable answer is not a grounded one.

Citations are not checked here; verifier.py does that on the returned answer.
"""

import json
import re
from dataclasses import dataclass

from pydantic import ValidationError

from rag.fallback import ABSTAIN_MESSAGE
from rag.llm import LLM
from rag.schemas import RAGAnswer, RetrievedChunk

SYSTEM_PROMPT = """\
You answer questions using ONLY the numbered context chunks provided by the user. \
Never use outside knowledge, even if you are sure of the answer.

Rules:
- Split your answer into claims. Every claim needs at least one citation.
- A citation's "quote" must be copied exactly, word for word, from the chunk it cites \
(at least 10 characters). Do not paraphrase inside a quote.
- Copy "chunk_id" and "doc_id" (and "page", if the chunk has one) from the chunk header.
- If the context fully answers the question, use status "answered".
- If it answers only part of it, use status "partial", answer what you can, and say what is missing in "reason".
- If the context does not contain the answer, or the question rests on a false premise, \
use status "abstained", an empty "claims" list, and explain in "reason".
- "confidence" is your own 0-1 estimate that the answer is fully supported.

Reply with a single JSON object and nothing else:
{
  "status": "answered" | "partial" | "abstained",
  "answer": "<the answer in plain prose>",
  "claims": [
    {"text": "<one claim>",
     "citations": [{"chunk_id": "...", "doc_id": "...", "page": 1, "quote": "<exact text from the chunk>"}]}
  ],
  "confidence": 0.0,
  "reason": null
}"""


@dataclass
class GenerationResult:
    answer: RAGAnswer
    attempts: int
    input_tokens: int
    output_tokens: int
    valid: bool   # False when retries ran out and we fell back to abstaining


def format_context(chunks: list[RetrievedChunk]) -> str:
    blocks = []
    for chunk in chunks:
        page = "" if chunk.page is None else f" | page: {chunk.page}"
        blocks.append(f"[chunk_id: {chunk.chunk_id} | doc_id: {chunk.doc_id}{page}]\n{chunk.text}")
    return "\n\n".join(blocks)


def build_user_message(question: str, chunks: list[RetrievedChunk]) -> str:
    return f"Context chunks:\n\n{format_context(chunks)}\n\nQuestion: {question}"


def parse_answer(text: str) -> RAGAnswer:
    """Parse a model reply into a RAGAnswer. Raises ValueError (incl. ValidationError) if invalid."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    elif not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start:end + 1]
    return RAGAnswer.model_validate_json(text)


def generate(
    question: str,
    chunks: list[RetrievedChunk],
    llm: LLM,
    max_retries: int = 2,
) -> GenerationResult:
    messages = [{"role": "user", "content": build_user_message(question, chunks)}]
    input_tokens = output_tokens = 0
    last_error = ""

    for attempt in range(1, max_retries + 2):
        reply = llm.complete(SYSTEM_PROMPT, messages)
        input_tokens += reply.input_tokens
        output_tokens += reply.output_tokens
        try:
            answer = parse_answer(reply.text)
        except (ValueError, json.JSONDecodeError) as error:
            last_error = _short_error(error)
            messages += [
                {"role": "assistant", "content": reply.text},
                {"role": "user", "content": (
                    f"That reply was invalid: {last_error}\n"
                    "Reply again with only a JSON object that follows the schema."
                )},
            ]
            continue
        return GenerationResult(answer, attempt, input_tokens, output_tokens, valid=True)

    failed = RAGAnswer(
        status="abstained",
        answer=ABSTAIN_MESSAGE,
        confidence=0.0,
        reason=f"The model did not return a valid answer after {max_retries + 1} attempts: {last_error}",
    )
    return GenerationResult(failed, max_retries + 1, input_tokens, output_tokens, valid=False)


def _short_error(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return "; ".join(f"{'.'.join(map(str, e['loc'])) or 'root'}: {e['msg']}" for e in error.errors())
    return str(error)
