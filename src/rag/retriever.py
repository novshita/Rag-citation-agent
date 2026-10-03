"""Find the chunks most similar to a question."""

from rag.embeddings import Embedder
from rag.schemas import RetrievedChunk


def retrieve(question: str, collection, embedder: Embedder, top_k: int) -> list[RetrievedChunk]:
    """Return up to `top_k` chunks, most similar first."""
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    if not question.strip() or collection.count() == 0:
        return []

    result = collection.query(
        query_embeddings=embedder.embed([question]),
        n_results=min(top_k, collection.count()),
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
    return sorted(chunks, key=lambda c: c.score, reverse=True)
