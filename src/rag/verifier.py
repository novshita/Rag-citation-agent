"""Check every citation against the retrieved text. Deterministic: no LLM involved.

A citation passes when its chunk_id is one of the retrieved chunks and its quote
appears in that chunk's text (ignoring case, whitespace, and Unicode look-alikes
such as PDF ligatures and curly quotes).

A claim survives only if *all* its citations pass: one fabricated quote is enough
to distrust the claim. Then the answer's status is set from what survived:
  all claims survive  -> status unchanged
  some survive        -> "partial", answer rebuilt from the surviving claims
  none survive        -> "abstained"
"""

import unicodedata
from dataclasses import dataclass, field
from typing import Literal

from rag.fallback import ABSTAIN_MESSAGE
from rag.schemas import Chunk, Citation, Claim, RAGAnswer

_LOOKALIKES = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "­": None,   # soft hyphen
})


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_LOOKALIKES)
    return " ".join(text.lower().split())


@dataclass
class CitationCheck:
    citation: Citation
    passed: bool
    problem: Literal["unknown_chunk", "quote_not_found"] | None = None


@dataclass
class VerificationResult:
    answer: RAGAnswer
    checks: list[CitationCheck] = field(default_factory=list)
    claims_total: int = 0
    claims_passed: int = 0

    @property
    def claim_pass_rate(self) -> float:
        return self.claims_passed / self.claims_total if self.claims_total else 0.0


def check_citation(citation: Citation, chunks_by_id: dict[str, Chunk]) -> CitationCheck:
    chunk = chunks_by_id.get(citation.chunk_id)
    if chunk is None:
        return CitationCheck(citation, passed=False, problem="unknown_chunk")
    if normalize(citation.quote) not in normalize(chunk.text):
        return CitationCheck(citation, passed=False, problem="quote_not_found")
    return CitationCheck(citation, passed=True)


def verify(answer: RAGAnswer, retrieved: list[Chunk]) -> VerificationResult:
    """Remove claims with bad citations and set the answer's status accordingly."""
    if answer.status == "abstained":
        return VerificationResult(answer)

    chunks_by_id = {c.chunk_id: c for c in retrieved}
    checks: list[CitationCheck] = []
    kept: list[Claim] = []

    for claim in answer.claims:
        claim_checks = [check_citation(c, chunks_by_id) for c in claim.citations]
        checks.extend(claim_checks)
        if all(check.passed for check in claim_checks):
            kept.append(_with_source_from_chunks(claim, chunks_by_id))

    result = VerificationResult(
        answer=answer, checks=checks,
        claims_total=len(answer.claims), claims_passed=len(kept),
    )
    removed = len(answer.claims) - len(kept)

    if not kept:
        result.answer = RAGAnswer(
            status="abstained",
            answer=ABSTAIN_MESSAGE,
            confidence=answer.confidence,
            reason=f"None of the {len(answer.claims)} claims had verifiable citations.",
        )
    elif removed:
        result.answer = RAGAnswer(
            status="partial",
            answer=" ".join(claim.text for claim in kept),
            claims=kept,
            confidence=answer.confidence,
            reason=f"{removed} of {len(answer.claims)} claims removed: citations could not be verified.",
        )
    else:
        result.answer = answer.model_copy(update={"claims": kept})
    return result


def _with_source_from_chunks(claim: Claim, chunks_by_id: dict[str, Chunk]) -> Claim:
    """Take doc_id and page from the stored chunk, not from the model, so sources shown are always right."""
    citations = [
        c.model_copy(update={
            "doc_id": chunks_by_id[c.chunk_id].doc_id,
            "page": chunks_by_id[c.chunk_id].page,
        })
        for c in claim.citations
    ]
    return claim.model_copy(update={"citations": citations})
