"""Command-line entry point: `python -m rag <command>`."""

import argparse
import os
import sys
from pathlib import Path

from rag.config import load_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rag", description="RAG agent with citation grounding")
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="index the documents in a folder")
    ingest.add_argument("folder", help="folder of PDF and Markdown files")

    search = commands.add_parser("search", help="show the chunks retrieved for a question")
    search.add_argument("question")
    search.add_argument("-k", "--top-k", type=int, help="number of chunks (default: TOP_K)")

    ask = commands.add_parser("ask", help="answer a question from the documents, with citations")
    ask.add_argument("question")
    ask.add_argument("-k", "--top-k", type=int, help="number of chunks (default: TOP_K)")

    evaluate = commands.add_parser("eval", help="run the evaluation and write the results file")
    evaluate.add_argument("--questions", default="eval/questions.json")
    evaluate.add_argument("--out", default="eval/results.md")

    tune = commands.add_parser("tune", help="suggest MIN_SCORE from the dev questions (no LLM calls)")
    tune.add_argument("--questions", default="eval/questions.json")

    ablate = commands.add_parser("ablate", help="compare top-k / chunk-size settings on the full system")
    ablate.add_argument("--questions", default="eval/questions.json")
    ablate.add_argument("--top-k", default="3,5,8", help="comma-separated, e.g. 3,5,8")
    ablate.add_argument("--chunk-size", help="comma-separated words, e.g. 100,150,300 (re-ingests the corpus)")
    ablate.add_argument("--corpus", default="data/raw", help="folder to ingest for each chunk size")
    ablate.add_argument("--out", default="eval/ablation.md")
    ablate.add_argument("--rerank", action="store_true", help="also run every variant with the cross-encoder reranker")
    ablate.add_argument("--retrieval-only", action="store_true", help="compare retrieval hit rate only (no LLM calls)")

    args = parser.parse_args(argv)
    try:
        return _run(args)
    except Exception as error:
        if os.getenv("RAG_DEBUG"):
            raise
        # Provider errors can be very long (API dumps); show the first line only.
        message = (str(error).strip().splitlines() or [""])[0]
        print(f"error: {type(error).__name__}: {message}", file=sys.stderr)
        print("(set RAG_DEBUG=1 for the full traceback)", file=sys.stderr)
        return 1


def _run(args) -> int:
    if args.command == "ingest":
        return _ingest(args.folder)
    if args.command == "search":
        return _search(args.question, args.top_k)
    if args.command == "ask":
        return _ask(args.question, args.top_k)
    if args.command == "eval":
        return _eval(args.questions, args.out)
    if args.command == "tune":
        return _tune(args.questions)
    if args.command == "ablate":
        return _ablate(args)
    return 1


def _ingest(folder: str) -> int:
    if not Path(folder).is_dir():
        print(f"error: {folder} is not a folder", file=sys.stderr)
        return 1

    from rag.embeddings import SentenceTransformerEmbedder
    from rag.ingest import ingest_folder
    from rag.store import get_collection

    settings = load_settings()
    report = ingest_folder(
        folder,
        collection=get_collection(settings.chroma_dir, settings.collection),
        embedder=SentenceTransformerEmbedder(settings.embedding_model),
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )

    print(f"added:     {len(report.added)}")
    print(f"updated:   {len(report.updated)}")
    print(f"unchanged: {len(report.unchanged)}")
    print(f"removed:   {len(report.removed)}")
    print(f"chunks written: {report.chunks_written}")
    for doc_id in report.empty:
        print(f"warning: no extractable text in {doc_id} (scanned PDF?)", file=sys.stderr)
    return 0


def _search(question: str, top_k: int | None) -> int:
    from rag.embeddings import SentenceTransformerEmbedder
    from rag.gate import check_retrieval
    from rag.rerank import make_reranker
    from rag.retriever import retrieve
    from rag.store import get_collection

    settings = load_settings()
    chunks = retrieve(
        question,
        collection=get_collection(settings.chroma_dir, settings.collection),
        embedder=SentenceTransformerEmbedder(settings.embedding_model),
        top_k=top_k or settings.top_k,
        reranker=make_reranker(settings),
        candidates=settings.rerank_candidates,
    )
    if not chunks:
        print("no chunks found (has the corpus been ingested?)")
        return 0

    for rank, chunk in enumerate(chunks, start=1):
        where = chunk.doc_id if chunk.page is None else f"{chunk.doc_id}, page {chunk.page}"
        preview = " ".join(chunk.text.split())[:160]
        print(f"{rank}. [{chunk.score:.3f}] {chunk.chunk_id}  ({where})")
        print(f"   {preview}")

    gate = check_retrieval(chunks, settings.min_score)
    verdict = "pass" if gate.passed else f"fail ({gate.reason})"
    print(f"\ngate: {verdict}  top={gate.top_score:.3f}  gap={gate.score_gap:.3f}")
    return 0


def _ask(question: str, top_k: int | None) -> int:
    import time

    from rag.embeddings import SentenceTransformerEmbedder
    from rag.llm import make_llm
    from rag.logger import connect, log_query
    from rag.pipeline import answer_question
    from rag.rerank import make_reranker
    from rag.retriever import retrieve
    from rag.store import get_collection

    settings = load_settings()
    if not settings.llm_model:
        print("error: set LLM_MODEL (see .env.example)", file=sys.stderr)
        return 1

    started = time.perf_counter()
    chunks = retrieve(
        question,
        collection=get_collection(settings.chroma_dir, settings.collection),
        embedder=SentenceTransformerEmbedder(settings.embedding_model),
        top_k=top_k or settings.top_k,
        reranker=make_reranker(settings),
        candidates=settings.rerank_candidates,
    )
    result = answer_question(
        question, chunks,
        llm=make_llm(settings.llm_provider, settings.llm_model),
        min_score=settings.min_score,
        max_retries=settings.max_retries,
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    log_query(connect(settings.log_db), question, result, latency_ms)

    answer = result.answer
    print(f"{answer.answer}\n")
    print(f"status:     {answer.status}")
    print(f"confidence: {answer.confidence:.2f}")
    if answer.reason:
        print(f"reason:     {answer.reason}")
    for number, claim in enumerate(answer.claims, start=1):
        print(f"\n[{number}] {claim.text}")
        for citation in claim.citations:
            where = citation.doc_id if citation.page is None else f"{citation.doc_id}, page {citation.page}"
            print(f'    - {where}: "{citation.quote}"')
    return 0


def _eval(questions_path: str, out_path: str) -> int:
    from rag.embeddings import SentenceTransformerEmbedder
    from rag.evaluate import evaluate, load_questions, render_report
    from rag.rerank import make_reranker
    from rag.llm import make_llm
    from rag.store import get_collection

    settings = load_settings()
    if not settings.llm_model:
        print("error: set LLM_MODEL (see .env.example)", file=sys.stderr)
        return 1
    if not Path(questions_path).is_file():
        print(f"error: {questions_path} not found (see eval/questions.example.json)", file=sys.stderr)
        return 1

    questions = [q for q in load_questions(questions_path) if q.split == "test"]
    if not questions:
        print("error: no test-split questions (dev questions are only used by `tune`)", file=sys.stderr)
        return 1
    outcomes = evaluate(
        questions,
        collection=get_collection(settings.chroma_dir, settings.collection),
        embedder=SentenceTransformerEmbedder(settings.embedding_model),
        llm=make_llm(settings.llm_provider, settings.llm_model),
        top_k=settings.top_k,
        min_score=settings.min_score,
        max_retries=settings.max_retries,
        reranker=make_reranker(settings),
        candidates=settings.rerank_candidates,
    )
    note = (
        f"model {settings.llm_model}, embeddings {settings.embedding_model}, top_k {settings.top_k}, "
        f"min_score {settings.min_score}, chunk size {settings.chunk_size}/{settings.chunk_overlap}, "
        f"reranker {settings.rerank_model if settings.rerank else 'off'}"
    )
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(render_report(questions, outcomes, note))
    print(f"wrote {out_path}")
    return 0


def _tune(questions_path: str) -> int:
    from rag.embeddings import SentenceTransformerEmbedder
    from rag.evaluate import load_questions
    from rag.store import get_collection
    from rag.rerank import make_reranker
    from rag.tune import render, sweep, top_scores

    settings = load_settings()
    if not Path(questions_path).is_file():
        print(f"error: {questions_path} not found (see eval/questions.example.json)", file=sys.stderr)
        return 1
    dev = [q for q in load_questions(questions_path) if q.split == "dev"]
    scored = top_scores(
        dev,
        collection=get_collection(settings.chroma_dir, settings.collection),
        embedder=SentenceTransformerEmbedder(settings.embedding_model),
        top_k=settings.top_k,
        reranker=make_reranker(settings),
        candidates=settings.rerank_candidates,
    )
    if scored and not any(score for _, score in scored):
        print("error: nothing was retrieved for any dev question (has the corpus been ingested?)", file=sys.stderr)
        return 1
    try:
        result = sweep(scored)
    except ValueError as error:
        print(f'error: {error}. Mark some questions with "split": "dev".', file=sys.stderr)
        return 1
    print(render(result, sum(q.answerable for q in dev), sum(not q.answerable for q in dev)))
    return 0


def _ablate(args) -> int:
    from rag.ablation import (
        Variant, render_ablation, render_hit_rates, retrieval_hit_rates, run_ablation,
    )
    from rag.embeddings import SentenceTransformerEmbedder
    from rag.evaluate import load_questions
    from rag.ingest import ingest_folder
    from rag.llm import make_llm
    from rag.rerank import CrossEncoderReranker
    from rag.store import get_collection

    settings = load_settings()
    if not args.retrieval_only and not settings.llm_model:
        print("error: set LLM_MODEL (see .env.example)", file=sys.stderr)
        return 1
    if not Path(args.questions).is_file():
        print(f"error: {args.questions} not found", file=sys.stderr)
        return 1

    try:
        top_ks = [int(k) for k in args.top_k.split(",")]
        sizes = [int(n) for n in args.chunk_size.split(",")] if args.chunk_size else [settings.chunk_size]
    except ValueError:
        print("error: --top-k and --chunk-size take comma-separated integers", file=sys.stderr)
        return 1
    if args.chunk_size and not Path(args.corpus).is_dir():
        print(f"error: {args.corpus} is not a folder", file=sys.stderr)
        return 1

    embedder = SentenceTransformerEmbedder(settings.embedding_model)
    reranker = CrossEncoderReranker(settings.rerank_model) if args.rerank else None
    variants = []
    for size in sizes:
        if size == settings.chunk_size:
            collection = get_collection(settings.chroma_dir, settings.collection)
        else:
            collection = get_collection(settings.chroma_dir, f"{settings.collection}-chunk{size}")
            overlap = round(size * settings.chunk_overlap / settings.chunk_size)
            ingest_folder(args.corpus, collection=collection, embedder=embedder,
                          chunk_size=size, chunk_overlap=overlap)
        for k in top_ks:
            variants.append(Variant(f"chunk {size}, top-k {k}", collection, k))
            if reranker:
                variants.append(Variant(
                    f"chunk {size}, top-k {k}, reranked", collection, k,
                    reranker=reranker, candidates=settings.rerank_candidates,
                ))

    questions = [q for q in load_questions(args.questions) if q.split == "test"]
    if args.retrieval_only:
        hit_rows = retrieval_hit_rates(questions, variants, embedder=embedder)
        note = f"{sum(q.answerable for q in questions)} answerable test questions; no LLM calls."
        report = render_hit_rates(hit_rows, note)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(report)
        print(report)
        print(f"wrote {args.out}")
        return 0

    rows = run_ablation(
        questions, variants, embedder=embedder, llm=make_llm(settings.llm_provider, settings.llm_model),
        min_score=settings.min_score, max_retries=settings.max_retries,
    )
    note = f"{len(questions)} test questions, model {settings.llm_model}, min_score {settings.min_score}."
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(render_ablation(rows, note))
    print(f"wrote {args.out}")
    return 0
