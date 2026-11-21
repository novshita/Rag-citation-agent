"""Builds the real retrieve -> answer pipeline from settings. Shared by the web UI and the API."""

from dataclasses import dataclass

from rag.config import Settings
from rag.pipeline import PipelineResult


@dataclass
class Runtime:
    ask: object        # ask(question, top_k=None) -> PipelineResult, over the sample documents
    ask_in: object     # ask_in(question, top_k, collection) -> PipelineResult, over any one collection
    embedder: object
    settings: Settings


def build_runtime(settings: Settings) -> Runtime:
    """Load the models and open the index once."""
    from rag.embeddings import SentenceTransformerEmbedder
    from rag.llm import make_llm
    from rag.pipeline import answer_question
    from rag.rerank import make_reranker
    from rag.retriever import retrieve
    from rag.store import get_collection
    from rag.web import DuckDuckGoSearch

    if not settings.llm_model:
        raise RuntimeError("Set LLM_MODEL in .env (see .env.example)")
    collection = get_collection(settings.chroma_dir, settings.collection)
    embedder = SentenceTransformerEmbedder(settings.embedding_model)
    llm = make_llm(settings.llm_provider, settings.llm_model)
    reranker = make_reranker(settings)
    web_search = DuckDuckGoSearch() if settings.web_fallback else None

    def ask(question: str, top_k: int | None = None) -> PipelineResult:
        chunks = retrieve(
            question, collection=collection, embedder=embedder, top_k=top_k or settings.top_k,
            reranker=reranker, candidates=settings.rerank_candidates, hybrid=settings.hybrid,
        )
        return answer_question(question, chunks, llm, settings.min_score, settings.max_retries,
                               web_search=web_search, web_results=settings.web_results)

    def ask_in(question: str, top_k: int | None, other) -> PipelineResult:
        # A visitor's own document: no keyword index (small and temporary) and never the web fallback,
        # so a question about a private file is never sent to a search service.
        chunks = retrieve(
            question, collection=other, embedder=embedder, top_k=top_k or settings.top_k,
            reranker=reranker, candidates=settings.rerank_candidates, hybrid=False,
        )
        return answer_question(question, chunks, llm, settings.min_score, settings.max_retries)

    return Runtime(ask, ask_in, embedder, settings)


def build_ask(settings: Settings):
    """ask(question, top_k=None) -> PipelineResult over the sample documents (used by the CLI and Streamlit)."""
    return build_runtime(settings).ask
