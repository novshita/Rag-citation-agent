import hashlib
import math

import pytest

from rag.store import get_collection


class FakeEmbedder:
    """Deterministic 8-dimensional vectors derived from a hash of the text."""

    def embed(self, texts):
        return [[b / 255 for b in hashlib.sha256(t.encode()).digest()[:8]] for t in texts]


class KeywordEmbedder:
    """Counts a few fixed keywords, so texts sharing keywords are similar."""

    VOCAB = ["apple", "banana", "cherry", "durian"]

    def embed(self, texts):
        vectors = []
        for text in texts:
            words = text.lower().split()
            counts = [words.count(w) + 0.01 for w in self.VOCAB]   # never all zero
            norm = math.sqrt(sum(c * c for c in counts))
            vectors.append([c / norm for c in counts])
        return vectors


@pytest.fixture
def collection(tmp_path):
    return get_collection(str(tmp_path / "chroma"), "test")
