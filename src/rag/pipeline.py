"""The online query flow: retrieve -> gate -> generate -> verify. Used by `ask` and, later, the eval."""

from dataclasses import dataclass

from rag.confidence import final_confidence
from rag.fallback import ABSTAIN_MESSAGE
from rag.gate import GateDecision, check_retrieval
from rag.generator import GenerationResult, generate
from rag.llm import LLM
from rag.schemas import RAGAnswer, RetrievedChunk
from rag.verifier import VerificationResult, verify
from rag.web import WebAnswer, WebSearch, web_fallback


@dataclass
class PipelineResult:
    answer: RAGAnswer
    chunks: list[RetrievedChunk]
    gate: GateDecision
    generation: GenerationResult | None = None      # None when the gate stopped us
    verification: VerificationResult | None = None
    web: WebAnswer | None = None                    # only for abstained answers, and only if enabled


def answer_question(
    question: str,
    chunks: list[RetrievedChunk],
    llm: LLM,
    min_score: float,
    max_retries: int,
    web_search: WebSearch | None = None,
    web_results: int = 5,
) -> PipelineResult:
    result = _grounded(question, chunks, llm, min_score, max_retries)
    if web_search is not None and result.answer.status == "abstained":
        result.web = web_fallback(question, web_search, llm, web_results)
    return result


def _grounded(question: str, chunks: list[RetrievedChunk], llm: LLM, min_score: float, max_retries: int) -> PipelineResult:
    gate = check_retrieval(chunks, min_score)
    if not gate.passed:
        answer = RAGAnswer(
            status="abstained", answer=ABSTAIN_MESSAGE, confidence=0.0, reason=gate.reason,
        )
        return PipelineResult(answer, chunks, gate)

    generation = generate(question, chunks, llm, max_retries)
    verification = verify(generation.answer, chunks)
    confidence = final_confidence(
        verification.answer, gate.top_score,
        verification.claim_pass_rate, generation.answer.confidence,
    )
    answer = verification.answer.model_copy(update={"confidence": confidence})
    if answer.status == "abstained" and not answer.answer.strip():
        answer = answer.model_copy(update={"answer": ABSTAIN_MESSAGE})
    return PipelineResult(answer, chunks, gate, generation, verification)
