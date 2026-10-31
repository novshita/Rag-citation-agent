"""Keyword search (BM25) to combine with vector search.

Vector search matches meaning but can miss exact terms such as option names
(`--forwarded-allow-ips`) or rare words; keyword search is the opposite. Hybrid retrieval
ranks passages both ways and merges the two rankings with reciprocal rank fusion (RRF):
a passage scores 1/(60 + rank) from each ranking it appears in, so one that does well in
both rises to the top. Off by default (HYBRID=true to enable).
"""

import math
import re
from dataclasses import dataclass

RRF_K = 60


def tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


class BM25:
    """Okapi BM25 over a fixed list of texts."""

    def __init__(self, texts: list[str], k1: float = 1.5, b: float = 0.75):
        self._docs = [tokenize(t) for t in texts]
        self._k1, self._b = k1, b
        self._avg_len = (sum(len(d) for d in self._docs) / len(self._docs)) if self._docs else 0.0
        df: dict[str, int] = {}
        for doc in self._docs:
            for term in set(doc):
                df[term] = df.get(term, 0) + 1
        n = len(self._docs)
        self._idf = {t: math.log((n - c + 0.5) / (c + 0.5) + 1) for t, c in df.items()}

    def scores(self, query: str) -> list[float]:
        terms = [t for t in tokenize(query) if t in self._idf]
        out = []
        for doc in self._docs:
            length = len(doc) or 1
            norm = self._k1 * (1 - self._b + self._b * length / (self._avg_len or 1))
            score = 0.0
            for term in terms:
                tf = doc.count(term)
                if tf:
                    score += self._idf[term] * tf * (self._k1 + 1) / (tf + norm)
            out.append(score)
        return out

    def top(self, query: str, n: int) -> list[int]:
        """Indexes of the best matches, best first, leaving out texts with no matching word."""
        scores = self.scores(query)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return [i for i in ranked[:n] if scores[i] > 0]


def rrf(rankings: list[list[str]], k: int = RRF_K) -> list[str]:
    """Merge best-first lists of ids into one best-first list."""
    fused: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            fused[item] = fused.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(fused, key=lambda item: fused[item], reverse=True)


@dataclass
class KeywordIndex:
    collection: object
    ids: list[str]
    texts: list[str]
    metadatas: list[dict]
    embeddings: list[list[float]]
    bm25: BM25


_cache: dict[int, KeywordIndex] = {}


def get_index(collection) -> KeywordIndex:
    """BM25 index over every passage in the collection, rebuilt if the collection changes size."""
    cached = _cache.get(id(collection))
    if cached and cached.collection is collection and len(cached.ids) == collection.count():
        return cached
    data = collection.get(include=["documents", "metadatas", "embeddings"])
    index = KeywordIndex(
        collection=collection,
        ids=list(data["ids"]),
        texts=list(data["documents"]),
        metadatas=list(data["metadatas"]),
        embeddings=[list(e) for e in data["embeddings"]],
        bm25=BM25(list(data["documents"])),
    )
    _cache[id(collection)] = index
    return index
