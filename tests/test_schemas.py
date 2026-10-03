import pytest
from pydantic import ValidationError

from rag.schemas import Citation, Claim, RAGAnswer

CITATION = Citation(chunk_id="a.md:c0", doc_id="a.md", quote="a long enough quote")
CLAIM = Claim(text="A claim.", citations=[CITATION])


def test_valid_answered():
    assert RAGAnswer(status="answered", answer="x", claims=[CLAIM], confidence=0.9).status == "answered"


def test_valid_abstained():
    assert RAGAnswer(status="abstained", answer="x", confidence=0, reason="nothing found").claims == []


@pytest.mark.parametrize("fields", [
    {"status": "answered", "claims": []},                          # answered needs claims
    {"status": "partial", "claims": [CLAIM]},                      # partial needs a reason
    {"status": "abstained"},                                       # abstained needs a reason
    {"status": "answered", "claims": [CLAIM], "confidence": 1.5},  # confidence above 1
    {"status": "unsure", "claims": [CLAIM]},                       # unknown status
])
def test_rejects_inconsistent_answers(fields):
    data = {"answer": "x", "confidence": 0.5, **fields}
    with pytest.raises(ValidationError):
        RAGAnswer(**data)


def test_claim_needs_a_citation():
    with pytest.raises(ValidationError):
        Claim(text="Unsupported.", citations=[])


def test_quote_must_be_at_least_10_characters():
    with pytest.raises(ValidationError):
        Citation(chunk_id="a.md:c0", doc_id="a.md", quote="too short")
