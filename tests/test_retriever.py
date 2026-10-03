import pytest

from conftest import KeywordEmbedder
from rag.ingest import ingest_folder
from rag.retriever import retrieve


@pytest.fixture
def filled(tmp_path, collection):
    folder = tmp_path / "raw"
    folder.mkdir()
    (folder / "apple.md").write_text("apple apple apple orchard notes")
    (folder / "banana.md").write_text("banana banana plantation notes")
    (folder / "mixed.md").write_text("apple banana cherry fruit salad")
    ingest_folder(folder, collection, KeywordEmbedder(), chunk_size=50, chunk_overlap=5)
    return collection


def ask(collection, question, top_k=5):
    return retrieve(question, collection, KeywordEmbedder(), top_k)


def test_best_match_comes_first(filled):
    results = ask(filled, "tell me about apple")
    assert results[0].doc_id == "apple.md"


def test_scores_are_sorted_and_in_range(filled):
    scores = [c.score for c in ask(filled, "banana")]
    assert scores == sorted(scores, reverse=True)
    assert all(-1 <= s <= 1.0001 for s in scores)


def test_identical_text_scores_about_one(filled):
    assert ask(filled, "banana banana plantation notes")[0].score == pytest.approx(1, abs=1e-3)


def test_top_k_limits_results(filled):
    assert len(ask(filled, "apple", top_k=2)) == 2


def test_top_k_larger_than_store_returns_everything(filled):
    assert len(ask(filled, "apple", top_k=50)) == 3


def test_returns_chunk_text_and_metadata(filled):
    chunk = ask(filled, "apple")[0]
    assert chunk.text == "apple apple apple orchard notes"
    assert chunk.chunk_id == "apple.md:c0"
    assert chunk.page is None
    assert (chunk.char_start, chunk.char_end) == (0, len(chunk.text))


def test_page_number_comes_back_for_pdf_chunks(collection):
    collection.add(
        ids=["report.pdf:p4:c0"],
        documents=["cherry figures"],
        embeddings=KeywordEmbedder().embed(["cherry figures"]),
        metadatas=[{"doc_id": "report.pdf", "page": 4, "char_start": 0,
                    "char_end": 14, "file_hash": "x"}],
    )
    assert ask(collection, "cherry")[0].page == 4


def test_empty_store_returns_nothing(collection):
    assert ask(collection, "apple") == []


def test_blank_question_returns_nothing(filled):
    assert ask(filled, "   ") == []


def test_rejects_non_positive_top_k(filled):
    with pytest.raises(ValueError):
        ask(filled, "apple", top_k=0)
