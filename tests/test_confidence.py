import pytest

from rag.confidence import final_confidence
from rag.pipeline import answer_question
from rag.schemas import RAGAnswer
from test_generator import FakeLLM, answered_json, chunk


def answered():
    return RAGAnswer(
        status="answered", answer="x", confidence=0.9,
        claims=[{"text": "c", "citations": [
            {"chunk_id": "a", "doc_id": "d", "quote": "0123456789"}]}],
    )


def test_blends_retrieval_and_model_confidence():
    assert final_confidence(answered(), 0.8, 1.0, 0.9) == pytest.approx(0.3 * 0.8 + 0.7 * 0.9)


def test_failed_citations_scale_confidence_down():
    full = final_confidence(answered(), 0.8, 1.0, 0.9)
    assert final_confidence(answered(), 0.8, 0.5, 0.9) == pytest.approx(full / 2)


def test_abstained_is_zero():
    abstained = RAGAnswer(status="abstained", answer="x", confidence=0.7, reason="r")
    assert final_confidence(abstained, 0.8, 1.0, 0.7) == 0.0


def test_pipeline_reports_the_final_confidence_not_the_models():
    result = answer_question("q", [chunk(score=0.8)], FakeLLM(answered_json()), 0.3, 2)
    assert result.answer.confidence == pytest.approx(0.3 * 0.8 + 0.7 * 0.9, abs=1e-4)
