"""End-to-end check with the real embedding model and the real LLM from .env.

Skipped by default (it costs a few LLM calls). Run it with:  pytest -m live
"""

import pytest

from rag.config import load_settings
from rag.embeddings import SentenceTransformerEmbedder
from rag.ingest import ingest_folder
from rag.llm import make_llm
from rag.pipeline import answer_question
from rag.retriever import retrieve
from rag.store import get_collection
from rag.verifier import verify

pytestmark = pytest.mark.live

DOC = """# Pangolin Care Guide

Pangolins eat ants and termites, and they use their long sticky tongues to collect them.

When threatened, a pangolin rolls itself into a tight ball, and its hard scales protect it.

Pangolins are nocturnal. They sleep through the day in burrows and forage at night.
"""


@pytest.fixture(scope="module")
def setup(tmp_path_factory):
    settings = load_settings()
    if not settings.llm_model:
        pytest.skip("LLM_MODEL is not set")

    docs = tmp_path_factory.mktemp("docs")
    (docs / "pangolins.md").write_text(DOC)
    embedder = SentenceTransformerEmbedder(settings.embedding_model)
    collection = get_collection(str(tmp_path_factory.mktemp("chroma")), "live")
    ingest_folder(str(docs), collection, embedder, chunk_size=settings.chunk_size,
                  chunk_overlap=settings.chunk_overlap)
    return settings, embedder, collection, make_llm(settings.llm_provider, settings.llm_model)


def ask(setup, question):
    settings, embedder, collection, llm = setup
    chunks = retrieve(question, collection=collection, embedder=embedder, top_k=settings.top_k)
    return answer_question(question, chunks, llm, settings.min_score, settings.max_retries)


def test_answerable_question_gets_a_verified_cited_answer(setup):
    result = ask(setup, "What do pangolins eat?")

    assert result.answer.status in ("answered", "partial")
    assert result.answer.claims
    # re-verifying the final answer finds nothing to remove: every quote is in its chunk
    recheck = verify(result.answer, result.chunks)
    assert recheck.claims_passed == recheck.claims_total == len(result.answer.claims)
    assert all(c.doc_id == "pangolins.md" for claim in result.answer.claims for c in claim.citations)
    assert "ant" in result.answer.answer.lower()


def test_out_of_corpus_question_abstains(setup):
    result = ask(setup, "How do I add JWT authentication to a web API?")

    assert result.answer.status == "abstained"
    assert result.answer.claims == []
