"""The online query flow: retrieve -> gate -> generate -> verify. Used by `ask` and, later, the eval."""

from dataclasses import dataclass

from rag.confidence import final_confidence
from rag.fallback import ABSTAIN_MESSAGE
from rag.gate import GateDecision, check_retrieval
from rag.generator import GenerationResult, generate
from rag.llm import LLM
from rag.schemas import RAGAnswer, RetrievedChunk
from rag.verifier import VerificationResult, verify


@dataclass
class PipelineResult:
    answer: RAGAnswer
    chunks: list[RetrievedChunk]
    gate: GateDecision
    generation: GenerationResult | None = None      # None when the gate stopped us
    verification: VerificationResult | None = None


def answer_question(
    question: str,
    chunks: list[RetrievedChunk],
    llm: LLM,
    min_score: float,
    max_retries: int,
) -> PipelineResult:
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
