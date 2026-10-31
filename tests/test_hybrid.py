import pytest

from conftest import KeywordEmbedder
from rag.hybrid import BM25, rrf, tokenize
from rag.ingest import ingest_folder
from rag.retriever import retrieve


def test_tokenize_lowercases_and_splits_on_punctuation():
    assert tokenize("Run --forwarded-allow-ips, now!") == ["run", "forwarded", "allow", "ips", "now"]


def test_bm25_prefers_the_text_with_the_rare_query_word():
    texts = ["the cat sat on the mat", "the dog barked at the mailman", "a zebra crossed the road"]
    scores = BM25(texts).scores("zebra")
    assert scores.index(max(scores)) == 2
    assert scores[0] == 0 and scores[1] == 0


def test_bm25_repeated_terms_help_but_saturate():
    scores = BM25(["zebra", "zebra zebra", "zebra zebra zebra zebra zebra zebra", "other words here"]).scores("zebra")
    assert scores[0] < scores[1] < scores[2]
    assert scores[2] - scores[1] < scores[1] - scores[0] * 0.5 + 1     # diminishing returns, not linear growth


def test_bm25_top_skips_texts_without_any_matching_word():
    bm25 = BM25(["alpha beta", "gamma delta", "beta gamma"])
    assert bm25.top("beta", 5) == [0, 2] or bm25.top("beta", 5) == [2, 0]
    assert bm25.top("nothing", 5) == []
    assert BM25([]).top("anything", 3) == []


def test_rrf_rewards_agreement_between_rankings():
    fused = rrf([["a", "b", "c"], ["c", "b", "d"]])
    assert set(fused[:2]) == {"b", "c"} and set(fused[2:]) == {"a", "d"}       # in both lists beats in one
    assert rrf([["a", "b"]]) == ["a", "b"]
    assert rrf([]) == []


@pytest.fixture
def filled(tmp_path, collection):
    folder = tmp_path / "raw"
    folder.mkdir()
    (folder / "mixed.md").write_text("apple banana cherry durian fruit salad")
    (folder / "apple.md").write_text("apple apple apple orchard notes")
    (folder / "zebra.md").write_text("zebra apple crossing safety facts")
    ingest_folder(folder, collection, KeywordEmbedder(), chunk_size=50, chunk_overlap=5)
    return collection


def test_hybrid_finds_a_rare_word_that_vector_search_cannot_see(filled):
    plain = retrieve("zebra", filled, KeywordEmbedder(), top_k=1)
    hybrid = retrieve("zebra", filled, KeywordEmbedder(), top_k=1, hybrid=True)

    assert plain[0].doc_id != "zebra.md"        # the toy embedder only knows four fruit words
    assert hybrid[0].doc_id == "zebra.md"


def test_hybrid_keeps_vector_similarity_as_the_score(filled):
    hybrid = retrieve("zebra", filled, KeywordEmbedder(), top_k=1, hybrid=True)
    everything = {c.chunk_id: c.score for c in retrieve("zebra", filled, KeywordEmbedder(), top_k=3)}

    assert hybrid[0].score == pytest.approx(everything[hybrid[0].chunk_id], abs=1e-4)


def test_hybrid_respects_top_k_and_keeps_the_strong_matches(filled):
    results = retrieve("apple", filled, KeywordEmbedder(), top_k=2, hybrid=True)
    assert len(results) == 2
    assert "apple.md" in {c.doc_id for c in results}          # the strong vector and keyword match is kept


def test_hybrid_index_is_rebuilt_when_the_collection_grows(tmp_path, collection):
    folder = tmp_path / "raw"
    folder.mkdir()
    (folder / "a.md").write_text("apple orchard notes")
    ingest_folder(folder, collection, KeywordEmbedder(), chunk_size=50, chunk_overlap=5)
    retrieve("zebra", collection, KeywordEmbedder(), top_k=1, hybrid=True)      # builds the index

    (folder / "z.md").write_text("zebra apple crossing safety facts")
    ingest_folder(folder, collection, KeywordEmbedder(), chunk_size=50, chunk_overlap=5)

    assert retrieve("zebra", collection, KeywordEmbedder(), top_k=1, hybrid=True)[0].doc_id == "z.md"
