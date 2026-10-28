"""Ablation: run the full system under different top-k / chunk-size settings and compare.

Each variant is a (collection, top_k) pair. Different chunk sizes need separate
collections, built by `python -m rag ablate --chunk-size ...` (ingest is skipped for
unchanged files, so rebuilding is cheap after the first time).
"""

from dataclasses import dataclass

from rag.evaluate import Metrics, Question, compute_metrics, evaluate, retrieval_hit
from rag.llm import LLM
from rag.retriever import DEFAULT_CANDIDATES, retrieve


@dataclass
class Variant:
    label: str
    collection: object
    top_k: int
    reranker: object | None = None
    candidates: int = DEFAULT_CANDIDATES


def run_ablation(
    questions: list[Question],
    variants: list[Variant],
    *,
    embedder,
    llm: LLM,
    min_score: float,
    max_retries: int,
) -> list[tuple[Variant, Metrics]]:
    rows = []
    for v in variants:
        outcomes = evaluate(
            questions, collection=v.collection, embedder=embedder, llm=llm,
            top_k=v.top_k, min_score=min_score, max_retries=max_retries, systems=("full",),
            reranker=v.reranker, candidates=v.candidates,
        )
        rows.append((v, compute_metrics(outcomes)))
    return rows


def retrieval_hit_rates(questions: list[Question], variants: list[Variant], *, embedder) -> list[tuple[Variant, float | None]]:
    """Retrieval hit rate per variant on the answerable questions. No LLM calls."""
    rows = []
    for v in variants:
        hits = []
        for q in questions:
            if not q.answerable:
                continue
            chunks = retrieve(q.question, collection=v.collection, embedder=embedder, top_k=v.top_k,
                              reranker=v.reranker, candidates=v.candidates)
            hits.append(bool(retrieval_hit(q, chunks)))
        rows.append((v, sum(hits) / len(hits) if hits else None))
    return rows


def render_hit_rates(rows: list[tuple[Variant, float | None]], note: str) -> str:
    lines = [
        "# Retrieval hit rate by variant", "", note, "",
        "| Variant | Hit rate (answerable questions) |", "|---|---|",
    ]
    lines += [f"| {v.label} | {_pct(rate)} |" for v, rate in rows]
    return "\n".join(lines) + "\n"


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0%}"


def render_ablation(rows: list[tuple[Variant, Metrics]], note: str) -> str:
    lines = [
        "# Ablation (full system)",
        "",
        f"{note}",
        "",
        "| Variant | Hit rate | Correctness | Abstention acc. | False abstention | Citation validity | Avg tokens |",
        "|---|---|---|---|---|---|---|",
    ]
    for v, m in rows:
        lines.append(
            f"| {v.label} | {_pct(m.hit_rate)} | {_pct(m.correctness)} | {_pct(m.abstention_accuracy)} "
            f"| {_pct(m.false_abstention_rate)} | {_pct(m.citation_validity)} | {m.avg_tokens:.0f} |"
        )
    return "\n".join(lines) + "\n"
