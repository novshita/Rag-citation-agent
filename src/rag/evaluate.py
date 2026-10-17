"""Evaluation: run the question set through three systems and compare them.

Systems
  baseline  plain LLM, no retrieval
  naive     retrieval + generation, no gate and no verification
  full      gate + generation + citation verification + fallback

Grading (stated in the results file too)
  - Abstention, retrieval hit, and citation validity are computed deterministically.
    Citation validity is measured on naive answers too, by running the verifier's check
    on them without changing the answer.
  - Correctness of non-abstained answers to answerable questions is graded by an LLM
    judge against the hand-written expected answer. Spot-check its grades by hand
    (the per-question table in results.md makes that easy).
  - The baseline has no structured status, so the judge also decides whether it declined.

Hallucination, two measures:
  - on unanswerable questions: the system gave an answer instead of abstaining;
  - unsupported-claim rate: an answer that contains a claim whose citation failed
    verification (always 0 for `full`, since it removes those claims).
"""

import json
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from rag.generator import generate
from rag.llm import LLM
from rag.pipeline import answer_question
from rag.retriever import retrieve
from rag.schemas import RetrievedChunk
from rag.verifier import verify

SYSTEMS = ("baseline", "naive", "full")
GROUPS = ("single", "multi", "unanswerable", "adversarial")


class Source(BaseModel):
    doc_id: str
    page: int | None = None


class Question(BaseModel):
    id: str
    group: Literal["single", "multi", "unanswerable", "adversarial"]
    question: str
    answerable: bool
    expected_answer: str | None = None
    expected_sources: list[Source] = Field(default_factory=list)


def load_questions(path: str | Path) -> list[Question]:
    questions = [Question.model_validate(q) for q in json.loads(Path(path).read_text())]
    ids = [q.id for q in questions]
    if len(set(ids)) != len(ids):
        raise ValueError("question ids must be unique")
    for q in questions:
        if q.answerable and not (q.expected_answer and q.expected_sources):
            raise ValueError(f"{q.id}: answerable questions need expected_answer and expected_sources")
    return questions


@dataclass
class Outcome:
    question: Question
    system: str
    abstained: bool
    answer_text: str
    hit: bool | None = None               # retrieval hit; None for baseline
    citations_total: int = 0
    citations_valid: int = 0
    unsupported_claims: int = 0
    correct: bool | None = None           # judged; None if not applicable
    latency_ms: int = 0
    tokens: int = 0


# --- running one question through each system ---------------------------------

BASELINE_SYSTEM = (
    "Answer the question concisely. If you do not know or are not sure, say so instead of guessing."
)


def run_baseline(q: Question, llm: LLM) -> Outcome:
    started = time.perf_counter()
    reply = llm.complete(BASELINE_SYSTEM, [{"role": "user", "content": q.question}])
    return Outcome(
        q, "baseline", abstained=False, answer_text=reply.text.strip(),   # abstained set by the judge
        latency_ms=_ms(started), tokens=reply.input_tokens + reply.output_tokens,
    )


def run_naive(q: Question, chunks: list[RetrievedChunk], llm: LLM, max_retries: int) -> Outcome:
    started = time.perf_counter()
    generation = generate(q.question, chunks, llm, max_retries)
    answer = generation.answer
    checks = verify(answer, chunks)   # measured only; the answer is returned as the model wrote it
    return Outcome(
        q, "naive", abstained=answer.status == "abstained", answer_text=answer.answer,
        hit=_hit(q, chunks),
        citations_total=len(checks.checks),
        citations_valid=sum(c.passed for c in checks.checks),
        unsupported_claims=checks.claims_total - checks.claims_passed,
        latency_ms=_ms(started), tokens=generation.input_tokens + generation.output_tokens,
    )


def run_full(
    q: Question, chunks: list[RetrievedChunk], llm: LLM, min_score: float, max_retries: int,
) -> Outcome:
    started = time.perf_counter()
    result = answer_question(q.question, chunks, llm, min_score, max_retries)
    answer = result.answer
    checks = result.verification.checks if result.verification else []
    tokens = result.generation.input_tokens + result.generation.output_tokens if result.generation else 0
    return Outcome(
        q, "full", abstained=answer.status == "abstained", answer_text=answer.answer,
        hit=_hit(q, chunks),
        citations_total=len(checks), citations_valid=sum(c.passed for c in checks),
        unsupported_claims=0,   # verification removed them; they are not in the final answer
        latency_ms=_ms(started), tokens=tokens,
    )


def _hit(q: Question, chunks: list[RetrievedChunk]) -> bool | None:
    """Every expected source appears among the retrieved chunks. None for unanswerable questions."""
    if not q.answerable:
        return None
    return all(
        any(c.doc_id == s.doc_id and (s.page is None or c.page == s.page) for c in chunks)
        for s in q.expected_sources
    )


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


# --- LLM judge ---------------------------------------------------------------

JUDGE_SYSTEM = """\
You grade answers to questions. You are given the question, a reference answer (or "none" if the \
question cannot be answered from the documents), and the system's answer.

Decide:
- "declined": true if the system's answer says it does not know / cannot answer / the information is not available.
- "correct": true if the system's answer states the same facts as the reference answer, with no \
contradiction of it. Extra detail is fine. If the answer declined, or the reference is "none", use null.

Reply with only JSON: {"declined": true|false, "correct": true|false|null}"""


def judge(q: Question, answer_text: str, llm: LLM) -> tuple[bool, bool | None]:
    """Returns (declined, correct). Falls back to (False, False) if the judge's reply can't be parsed."""
    prompt = (
        f"Question: {q.question}\n"
        f"Reference answer: {q.expected_answer or 'none'}\n"
        f"System answer: {answer_text}"
    )
    reply = llm.complete(JUDGE_SYSTEM, [{"role": "user", "content": prompt}])
    try:
        text = reply.text
        data = json.loads(text[text.index("{"): text.rindex("}") + 1])
        return bool(data["declined"]), data.get("correct")
    except (ValueError, KeyError):
        return False, False


# --- the whole run -------------------------------------------------------------

def evaluate(
    questions: list[Question],
    *,
    collection,
    embedder,
    llm: LLM,
    judge_llm: LLM | None = None,
    top_k: int,
    min_score: float,
    max_retries: int,
    systems: tuple[str, ...] = SYSTEMS,
) -> list[Outcome]:
    judge_llm = judge_llm or llm
    outcomes: list[Outcome] = []

    for q in questions:
        chunks = retrieve(q.question, collection=collection, embedder=embedder, top_k=top_k)
        for system in systems:
            if system == "baseline":
                outcome = run_baseline(q, llm)
                outcome.abstained, outcome.correct = judge(q, outcome.answer_text, judge_llm)
                if outcome.abstained:
                    outcome.correct = None
            else:
                outcome = (
                    run_naive(q, chunks, llm, max_retries) if system == "naive"
                    else run_full(q, chunks, llm, min_score, max_retries)
                )
                if q.answerable and not outcome.abstained:
                    _, outcome.correct = judge(q, outcome.answer_text, judge_llm)
            outcomes.append(outcome)
    return outcomes


# --- metrics -------------------------------------------------------------------

@dataclass
class Metrics:
    n: int = 0
    hit_rate: float | None = None
    correctness: float | None = None             # answerable questions; abstaining counts as wrong
    citation_validity: float | None = None
    abstention_accuracy: float | None = None     # unanswerable questions
    false_abstention_rate: float | None = None   # answerable questions
    hallucination_unanswerable: float | None = None
    unsupported_claim_rate: float | None = None  # answers with a failed citation
    avg_latency_ms: float = 0.0
    avg_tokens: float = 0.0


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def compute_metrics(outcomes: list[Outcome]) -> Metrics:
    answerable = [o for o in outcomes if o.question.answerable]
    unanswerable = [o for o in outcomes if not o.question.answerable]
    answered = [o for o in outcomes if not o.abstained and o.system != "baseline"]   # baseline has no citations
    hits = [o for o in answerable if o.hit is not None]
    cited = sum(o.citations_total for o in outcomes)

    return Metrics(
        n=len(outcomes),
        hit_rate=_rate(sum(bool(o.hit) for o in hits), len(hits)),
        correctness=_rate(sum(o.correct is True for o in answerable), len(answerable)),
        citation_validity=_rate(sum(o.citations_valid for o in outcomes), cited),
        abstention_accuracy=_rate(sum(o.abstained for o in unanswerable), len(unanswerable)),
        false_abstention_rate=_rate(sum(o.abstained for o in answerable), len(answerable)),
        hallucination_unanswerable=_rate(sum(not o.abstained for o in unanswerable), len(unanswerable)),
        unsupported_claim_rate=_rate(sum(o.unsupported_claims > 0 for o in answered), len(answered)),
        avg_latency_ms=sum(o.latency_ms for o in outcomes) / len(outcomes) if outcomes else 0.0,
        avg_tokens=sum(o.tokens for o in outcomes) / len(outcomes) if outcomes else 0.0,
    )


# --- report --------------------------------------------------------------------

def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0%}"


def render_report(questions: list[Question], outcomes: list[Outcome], settings_note: str) -> str:
    by_system: dict[str, list[Outcome]] = defaultdict(list)
    for o in outcomes:
        by_system[o.system].append(o)
    systems = [s for s in SYSTEMS if s in by_system]
    metrics = {s: compute_metrics(by_system[s]) for s in systems}

    counts = {g: sum(q.group == g for q in questions) for g in GROUPS}
    lines = [
        "# Evaluation results",
        "",
        f"{len(questions)} questions: " + ", ".join(f"{counts[g]} {g}" for g in GROUPS) + ".",
        f"Settings: {settings_note}.",
        "",
        "## Comparison",
        "",
        "| Metric | " + " | ".join(systems) + " |",
        "|---|" + "---|" * len(systems),
    ]
    rows = [
        ("Retrieval hit rate (answerable)", "hit_rate"),
        ("Answer correctness (answerable)", "correctness"),
        ("Citation validity", "citation_validity"),
        ("Abstention accuracy (unanswerable)", "abstention_accuracy"),
        ("False abstention rate (answerable)", "false_abstention_rate"),
        ("Hallucination rate (unanswerable)", "hallucination_unanswerable"),
        ("Answers with an unsupported claim", "unsupported_claim_rate"),
    ]
    for label, attr in rows:
        lines.append(f"| {label} | " + " | ".join(_pct(getattr(metrics[s], attr)) for s in systems) + " |")
    lines.append("| Avg latency (ms) | " + " | ".join(f"{metrics[s].avg_latency_ms:.0f}" for s in systems) + " |")
    lines.append("| Avg tokens per question | " + " | ".join(f"{metrics[s].avg_tokens:.0f}" for s in systems) + " |")

    lines += [
        "",
        "## Method",
        "",
        "- Abstention, retrieval hit and citation validity are computed by code. A citation is valid "
        "when its chunk was retrieved and its quote appears in that chunk (whitespace and case ignored).",
        "- Correctness is graded by an LLM judge against the hand-written expected answer; "
        "abstaining on an answerable question counts as incorrect. Spot-check the table below.",
        "- Hallucination rate (unanswerable) = share of unanswerable questions where the system answered instead of abstaining.",
        "- The baseline has no retrieval, so hit rate and citation validity do not apply. "
        "Whether it declined is decided by the judge.",
        "- `naive` is graded as the model wrote it (citations are checked but nothing is removed), so its "
        "unsupported claims are visible; `full` removes them before answering.",
        "",
        "## Per question",
        "",
        "| id | group | system | abstained | hit | correct | citations valid |",
        "|---|---|---|---|---|---|---|",
    ]
    for o in outcomes:
        cites = f"{o.citations_valid}/{o.citations_total}" if o.citations_total else "-"
        lines.append(
            f"| {o.question.id} | {o.question.group} | {o.system} | {'yes' if o.abstained else 'no'} "
            f"| {_mark(o.hit)} | {_mark(o.correct)} | {cites} |"
        )
    return "\n".join(lines) + "\n"


def _mark(value: bool | None) -> str:
    return "-" if value is None else ("yes" if value else "no")
