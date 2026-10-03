from rag.fallback import ABSTAIN_MESSAGE
from rag.schemas import Chunk, Citation, Claim, RAGAnswer
from rag.verifier import normalize, verify

CHUNKS = [
    Chunk(chunk_id="policy.pdf:p3:c0", doc_id="policy.pdf", page=3,
          text="This policy was last revised in March 2024.\nIt applies to all\n  staff members.",
          char_start=0, char_end=80),
    Chunk(chunk_id="faq.md:c2", doc_id="faq.md", page=None,
          text="Refunds are processed within 14 business days.",
          char_start=0, char_end=47),
]


def claim(text, chunk_id, quote, doc_id="policy.pdf", page=3):
    return Claim(text=text, citations=[Citation(chunk_id=chunk_id, doc_id=doc_id, page=page, quote=quote)])


REAL = claim("Updated March 2024.", "policy.pdf:p3:c0", "last revised in March 2024")
REAL_2 = claim("Refunds take 14 business days.", "faq.md:c2", "processed within 14 business days",
               doc_id="faq.md", page=None)
FAKE_QUOTE = claim("Updated yearly.", "policy.pdf:p3:c0", "is reviewed every single year")
FAKE_CHUNK = claim("Updated March 2024.", "policy.pdf:p9:c4", "last revised in March 2024")


def answered(*claims):
    return RAGAnswer(status="answered", answer="model prose", claims=list(claims), confidence=0.8)


# --- individual citations ---

def test_accepts_a_real_quote():
    result = verify(answered(REAL), CHUNKS)
    assert result.checks[0].passed
    assert result.answer.status == "answered"


def test_rejects_a_fabricated_quote():
    result = verify(answered(FAKE_QUOTE), CHUNKS)
    assert result.checks[0].problem == "quote_not_found"


def test_rejects_a_chunk_that_was_not_retrieved():
    result = verify(answered(FAKE_CHUNK), CHUNKS)
    assert result.checks[0].problem == "unknown_chunk"


def test_ignores_whitespace_and_case_differences():
    quote_across_lines = claim("Applies to staff.", "policy.pdf:p3:c0", "IT APPLIES TO ALL staff   members")
    assert verify(answered(quote_across_lines), CHUNKS).checks[0].passed


def test_ignores_pdf_ligatures_and_curly_quotes():
    assert normalize("ﬁnal “quote”") == normalize('final "quote"')


# --- status logic ---

def test_all_claims_pass_keeps_answered():
    result = verify(answered(REAL, REAL_2), CHUNKS)
    assert result.answer.status == "answered"
    assert result.answer.answer == "model prose"
    assert result.claim_pass_rate == 1.0


def test_some_claims_fail_gives_partial():
    result = verify(answered(REAL, FAKE_QUOTE), CHUNKS)

    assert result.answer.status == "partial"
    assert result.answer.claims == [REAL]
    assert result.answer.answer == "Updated March 2024."   # rebuilt without the removed claim
    assert "1 of 2" in result.answer.reason
    assert result.claim_pass_rate == 0.5


def test_all_claims_fail_gives_abstained():
    result = verify(answered(FAKE_QUOTE, FAKE_CHUNK), CHUNKS)

    assert result.answer.status == "abstained"
    assert result.answer.claims == []
    assert result.answer.answer == ABSTAIN_MESSAGE
    assert result.claim_pass_rate == 0.0


def test_one_bad_citation_removes_the_whole_claim():
    mixed = Claim(text="Updated March 2024.", citations=[
        REAL.citations[0],
        Citation(chunk_id="policy.pdf:p3:c0", doc_id="policy.pdf", page=3, quote="never been revised at all"),
    ])
    assert verify(answered(mixed), CHUNKS).answer.status == "abstained"


def test_already_abstained_answer_is_left_alone():
    abstained = RAGAnswer(status="abstained", answer=ABSTAIN_MESSAGE, confidence=0.1, reason="not in context")
    result = verify(abstained, CHUNKS)
    assert result.answer == abstained
    assert result.checks == []


def test_doc_and_page_are_taken_from_the_chunk():
    wrong_page = claim("Updated March 2024.", "policy.pdf:p3:c0", "last revised in March 2024",
                       doc_id="other.pdf", page=99)
    citation = verify(answered(wrong_page), CHUNKS).answer.claims[0].citations[0]
    assert (citation.doc_id, citation.page) == ("policy.pdf", 3)
