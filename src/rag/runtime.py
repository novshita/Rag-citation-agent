"""Builds the real retrieve -> answer pipeline from settings. Shared by the web UI and the API."""

from rag.config import Settings
from rag.pipeline import PipelineResult


def build_ask(settings: Settings):
    """Load the models and open the index once; return ask(question, top_k=None) -> PipelineResult."""
    from rag.embeddings import SentenceTransformerEmbedder
    from rag.llm import make_llm
    from rag.pipeline import answer_question
    from rag.rerank import make_reranker
    from rag.retriever import retrieve
    from rag.store import get_collection

    if not settings.llm_model:
        raise RuntimeError("Set LLM_MODEL in .env (see .env.example)")
    collection = get_collection(settings.chroma_dir, settings.collection)
    embedder = SentenceTransformerEmbedder(settings.embedding_model)
    llm = make_llm(settings.llm_provider, settings.llm_model)
    reranker = make_reranker(settings)

    def ask(question: str, top_k: int | None = None) -> PipelineResult:
        chunks = retrieve(
            question, collection=collection, embedder=embedder, top_k=top_k or settings.top_k,
            reranker=reranker, candidates=settings.rerank_candidates, hybrid=settings.hybrid,
        )
        return answer_question(question, chunks, llm, settings.min_score, settings.max_retries)

    return ask
