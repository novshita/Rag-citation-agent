"""Command-line entry point: `python -m rag <command>`."""

import argparse
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

    args = parser.parse_args(argv)
    if args.command == "ingest":
        return _ingest(args.folder)
    if args.command == "search":
        return _search(args.question, args.top_k)
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
    from rag.retriever import retrieve
    from rag.store import get_collection

    settings = load_settings()
    chunks = retrieve(
        question,
        collection=get_collection(settings.chroma_dir, settings.collection),
        embedder=SentenceTransformerEmbedder(settings.embedding_model),
        top_k=top_k or settings.top_k,
    )
    if not chunks:
        print("no chunks found (has the corpus been ingested?)")
        return 0

    for rank, chunk in enumerate(chunks, start=1):
        where = chunk.doc_id if chunk.page is None else f"{chunk.doc_id}, page {chunk.page}"
        preview = " ".join(chunk.text.split())[:160]
        print(f"{rank}. [{chunk.score:.3f}] {chunk.chunk_id}  ({where})")
        print(f"   {preview}")
    return 0
