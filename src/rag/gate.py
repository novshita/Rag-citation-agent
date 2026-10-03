"""Decide, before calling the LLM, whether retrieval found anything worth answering from.

If the best chunk's score is below MIN_SCORE, the question is probably not covered
by the documents, so we abstain without generating. This saves an LLM call and
removes the chance of a confident made-up answer.

The score gap (top-1 minus the last retrieved score) is reported for logging and
tuning. It isn't used in the decision yet: a large gap means one chunk clearly
stands out, a small gap means several chunks are similarly (ir)relevant.
"""

from dataclasses import dataclass

from rag.schemas import RetrievedChunk


@dataclass(frozen=True)
class GateDecision:
    passed: bool
    top_score: float | None
    score_gap: float | None
    reason: str | None = None   # set when the gate fails


def check_retrieval(chunks: list[RetrievedChunk], min_score: float) -> GateDecision:
    if not chunks:
        return GateDecision(False, None, None, "No chunks were retrieved.")

    scores = sorted((c.score for c in chunks), reverse=True)
    top, gap = scores[0], scores[0] - scores[-1]

    if top < min_score:
        return GateDecision(
            False, top, gap,
            f"Best match score {top:.3f} is below MIN_SCORE {min_score:.3f}.",
        )
    return GateDecision(True, top, gap)
