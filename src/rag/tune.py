"""Pick MIN_SCORE from data instead of guessing (spec §8, step 1).

The gate abstains when the best retrieval score is below MIN_SCORE. For each candidate
threshold we measure, using retrieval only (no LLM calls):
  abstention accuracy    unanswerable questions the gate would stop
  false abstention rate  answerable questions the gate would wrongly stop
and pick the threshold with the best balance of the two.

Run it on the dev split only. If you tune on the questions you then report results
on, the numbers look better than they really are.
"""

from dataclasses import dataclass

from rag.evaluate import Question
from rag.retriever import retrieve


@dataclass(frozen=True)
class ThresholdRow:
    threshold: float
    abstention_accuracy: float
    false_abstention_rate: float

    @property
    def balanced(self) -> float:
        return (self.abstention_accuracy + (1 - self.false_abstention_rate)) / 2


@dataclass
class TuneResult:
    rows: list[ThresholdRow]
    best: ThresholdRow
    answerable_min: float        # lowest top score among answerable questions
    unanswerable_max: float      # highest top score among unanswerable questions

    @property
    def separable(self) -> bool:
        """True if some threshold gets every question right."""
        return self.unanswerable_max < self.answerable_min


def top_scores(questions: list[Question], collection, embedder, top_k: int) -> list[tuple[Question, float]]:
    scored = []
    for q in questions:
        chunks = retrieve(q.question, collection=collection, embedder=embedder, top_k=top_k)
        scored.append((q, max((c.score for c in chunks), default=0.0)))
    return scored


def sweep(scored: list[tuple[Question, float]]) -> TuneResult:
    answerable = [s for q, s in scored if q.answerable]
    unanswerable = [s for q, s in scored if not q.answerable]
    if not answerable or not unanswerable:
        raise ValueError("tuning needs both answerable and unanswerable questions")

    distinct = sorted({s for _, s in scored})
    candidates = [0.0] + [(a + b) / 2 for a, b in zip(distinct, distinct[1:])]

    rows = [
        ThresholdRow(
            threshold=t,
            abstention_accuracy=sum(s < t for s in unanswerable) / len(unanswerable),
            false_abstention_rate=sum(s < t for s in answerable) / len(answerable),
        )
        for t in candidates
    ]
    # max() returns the first best row, i.e. the lowest threshold: ties favour answering.
    best = max(rows, key=lambda r: r.balanced)
    return TuneResult(rows, best, min(answerable), max(unanswerable))


def render(result: TuneResult, n_answerable: int, n_unanswerable: int) -> str:
    lines = [
        f"{n_answerable} answerable and {n_unanswerable} unanswerable dev questions.",
        f"Top score range: answerable >= {result.answerable_min:.3f}, unanswerable <= {result.unanswerable_max:.3f}.",
        "",
        "threshold  abstention-acc  false-abstention",
    ]
    for r in result.rows:
        marker = "  <- best" if r is result.best else ""
        lines.append(
            f"{r.threshold:9.3f}  {r.abstention_accuracy:14.0%}  {r.false_abstention_rate:16.0%}{marker}"
        )
    lines.append("")
    if result.separable:
        lines.append("The two groups separate cleanly: any threshold between them gets every dev question right.")
    else:
        lines.append(
            "The groups overlap: some unanswerable questions score as high as answerable ones, so the gate "
            "alone cannot catch them. That is what citation verification and the model's own abstention are for."
        )
    lines.append(f"Suggested: MIN_SCORE={result.best.threshold:.3f}")
    return "\n".join(lines)
