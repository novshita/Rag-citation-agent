"""Find the chunks most similar to a question."""

from rag.embeddings import Embedder
from rag.rerank import Reranker
from rag.schemas import RetrievedChunk

DEFAULT_CANDIDATES = 20


def retrieve(
    question: str,
    collection,
    embedder: Embedder,
    top_k: int,
    reranker: Reranker | None = None,
    candidates: int = DEFAULT_CANDIDATES,
) -> list[RetrievedChunk]:
    """Return up to `top_k` chunks, most similar first.

    With a reranker, the `candidates` most similar chunks are rescored and the best
    `top_k` kept, ordered by the reranker. Each chunk's `score` stays its vector
    similarity, so the confidence gate means the same thing with or without reranking.
    """
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    if not question.strip() or collection.count() == 0:
        return []

    fetch = max(top_k, candidates) if reranker else top_k
    result = collection.query(
        query_embeddings=embedder.embed([question]),
        n_results=min(fetch, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    chunks = [
        RetrievedChunk(
            chunk_id=chunk_id,
            doc_id=meta["doc_id"],
            page=meta.get("page"),
            text=text,
            char_start=meta["char_start"],
            char_end=meta["char_end"],
            score=1 - distance,   # the collection uses cosine distance
        )
        for chunk_id, text, meta, distance in zip(
            result["ids"][0],
            result["documents"][0],
            result["metadatas"][0],
            result["distances"][0],
        )
    ]
    chunks.sort(key=lambda c: c.score, reverse=True)
    if reranker is None:
        return chunks

    relevance = reranker.score(question, [c.text for c in chunks])
    ranked = sorted(zip(relevance, chunks), key=lambda pair: pair[0], reverse=True)
    return [chunk for _, chunk in ranked[:top_k]]
