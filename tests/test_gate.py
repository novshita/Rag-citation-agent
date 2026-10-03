import pytest

from rag.gate import check_retrieval
from rag.schemas import RetrievedChunk


def chunks_with(*scores):
    return [
        RetrievedChunk(chunk_id=f"a.md:c{i}", doc_id="a.md", page=None, text="t",
                       char_start=0, char_end=1, score=s)
        for i, s in enumerate(scores)
    ]


def test_passes_when_top_score_reaches_threshold():
    decision = check_retrieval(chunks_with(0.72, 0.50, 0.41), min_score=0.3)
    assert decision.passed
    assert decision.reason is None


def test_abstains_below_min_score():
    decision = check_retrieval(chunks_with(0.21, 0.18), min_score=0.3)
    assert not decision.passed
    assert "below MIN_SCORE" in decision.reason


def test_score_exactly_at_threshold_passes():
    assert check_retrieval(chunks_with(0.3), min_score=0.3).passed


def test_abstains_when_nothing_retrieved():
    decision = check_retrieval([], min_score=0.3)
    assert not decision.passed
    assert decision.top_score is None


def test_reports_top_score_and_gap_regardless_of_order():
    decision = check_retrieval(chunks_with(0.40, 0.90, 0.55), min_score=0.3)
    assert decision.top_score == 0.90
    assert decision.score_gap == pytest.approx(0.50)
