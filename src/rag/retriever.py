"""Find the chunks most similar to a question."""

from rag.embeddings import Embedder
from rag.hybrid import get_index, rrf
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
    hybrid: bool = False,
) -> list[RetrievedChunk]:
    """Return up to `top_k` chunks, most similar first.

    With a reranker, the `candidates` most similar chunks are rescored and the best
    `top_k` kept, ordered by the reranker. Each chunk's `score` stays its vector
    similarity, so the confidence gate means the same thing with or without reranking.

    With `hybrid`, keyword (BM25) matches are merged with the vector matches by reciprocal
    rank fusion before the top `top_k` are chosen. Passages found only by keywords get their
    vector similarity computed, so `score` is always the vector similarity.
    """
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    if not question.strip() or collection.count() == 0:
        return []

    fetch = max(top_k, candidates) if (reranker or hybrid) else top_k
    query_vector = embedder.embed([question])
    result = collection.query(
        query_embeddings=query_vector,
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
    if hybrid:
        chunks = _fuse_with_keywords(question, collection, query_vector[0], chunks, fetch)
    if reranker is None:
        return chunks[:top_k]

    relevance = reranker.score(question, [c.text for c in chunks])
    ranked = sorted(zip(relevance, chunks), key=lambda pair: pair[0], reverse=True)
    return [chunk for _, chunk in ranked[:top_k]]


def _fuse_with_keywords(question, collection, query_vector, vector_chunks, limit) -> list[RetrievedChunk]:
    """Best `limit` passages by RRF of the vector ranking and the keyword ranking."""
    index = get_index(collection)
    keyword_ids = [index.ids[i] for i in index.bm25.top(question, limit)]
    by_id = {c.chunk_id: c for c in vector_chunks}

    position = {chunk_id: i for i, chunk_id in enumerate(index.ids)}
    for chunk_id in keyword_ids:
        if chunk_id in by_id:
            continue
        i = position[chunk_id]
        meta = index.metadatas[i]
        by_id[chunk_id] = RetrievedChunk(
            chunk_id=chunk_id, doc_id=meta["doc_id"], page=meta.get("page"), text=index.texts[i],
            char_start=meta["char_start"], char_end=meta["char_end"],
            score=sum(a * b for a, b in zip(query_vector, index.embeddings[i])),   # unit vectors: dot = cosine
        )

    fused = rrf([[c.chunk_id for c in vector_chunks], keyword_ids])
    return [by_id[chunk_id] for chunk_id in fused[:limit]]
