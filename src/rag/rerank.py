"""Optional second-stage ranking with a cross-encoder.

Vector search compares a question and a passage through two separate embeddings, which
is fast but rough. A cross-encoder reads the question and the passage together, which
is slower but better at telling which passage really answers it. So: fetch a wider set
of candidates by vector similarity, rescore them with the cross-encoder, keep the best
top-k. Off by default (RERANK=true to enable); `python -m rag ablate --retrieval-only
--rerank` shows its effect on retrieval hit rate.
"""

from typing import Protocol


class Reranker(Protocol):
    def score(self, question: str, texts: list[str]) -> list[float]:
        """Relevance of each text to the question; higher is better."""
        ...


class CrossEncoderReranker:
    def __init__(self, model_name: str):
        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(model_name)

    def score(self, question: str, texts: list[str]) -> list[float]:
        scores = self._model.predict([(question, text) for text in texts], show_progress_bar=False)
        return [float(s) for s in scores]


def make_reranker(settings) -> Reranker | None:
    return CrossEncoderReranker(settings.rerank_model) if settings.rerank else None
