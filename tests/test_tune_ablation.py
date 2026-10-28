import json

import pytest

from conftest import KeywordEmbedder
from rag.ablation import Variant, render_ablation, run_ablation
from rag.evaluate import Question, load_questions
from rag.ingest import ingest_folder
from rag.tune import render, sweep
from test_evaluate import ScriptedLLM, cited


def q(qid, answerable):
    return Question(
        id=qid, group="single" if answerable else "unanswerable", question=qid, answerable=answerable,
        expected_answer="a" if answerable else None,
        expected_sources=[{"doc_id": "d"}] if answerable else [],
    )


def test_sweep_separable_picks_threshold_between_groups():
    scored = [(q("a1", True), 0.7), (q("a2", True), 0.6), (q("u1", False), 0.2), (q("u2", False), 0.3)]
    result = sweep(scored)

    assert result.separable
    assert 0.3 < result.best.threshold <= 0.6
    assert (result.best.abstention_accuracy, result.best.false_abstention_rate) == (1.0, 0.0)


def test_sweep_overlap_is_reported_and_best_is_still_chosen():
    scored = [(q("a1", True), 0.7), (q("a2", True), 0.35), (q("u1", False), 0.2), (q("u2", False), 0.5)]
    result = sweep(scored)

    assert not result.separable
    assert result.best.balanced == 0.75
    assert "overlap" in render(result, 2, 2)


def test_sweep_needs_both_kinds_of_question():
    with pytest.raises(ValueError, match="both"):
        sweep([(q("a1", True), 0.7)])


def test_split_defaults_to_test(tmp_path):
    path = tmp_path / "q.json"
    path.write_text(json.dumps([
        {"id": "a", "group": "unanswerable", "question": "q", "answerable": False},
        {"id": "b", "group": "unanswerable", "question": "q", "answerable": False, "split": "dev"}]))
    questions = load_questions(path)
    assert [x.split for x in questions] == ["test", "dev"]


def test_ablation_compares_variants(collection, tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "fruit.md").write_text("apple apple apple is the best fruit in the world")
    ingest_folder(str(docs), collection, KeywordEmbedder(), chunk_size=50, chunk_overlap=5)
    questions = [Question(id="s1", group="single", question="apple", answerable=True,
                          expected_answer="apple", expected_sources=[{"doc_id": "fruit.md"}])]

    rows = run_ablation(
        questions, [Variant("top-k 1", collection, 1), Variant("top-k 3", collection, 3)],
        embedder=KeywordEmbedder(),
        llm=ScriptedLLM(cited("apple apple apple is the best"), '{"declined": false, "correct": true}'),
        min_score=0.3, max_retries=0,
    )

    assert [v.label for v, _ in rows] == ["top-k 1", "top-k 3"]
    assert all(m.correctness == 1.0 for _, m in rows)
    report = render_ablation(rows, "note")
    assert "| top-k 1 | 100% | 100% |" in report


def test_retrieval_hit_rates_compare_variants_without_an_llm(collection, tmp_path):
    from rag.ablation import render_hit_rates, retrieval_hit_rates

    class PreferLongest:
        def score(self, question, texts):
            return [len(t) for t in texts]

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "apple.md").write_text("apple apple apple orchard notes")
    (docs / "banana.md").write_text("banana banana plantation notes for everyone to read")
    ingest_folder(str(docs), collection, KeywordEmbedder(), chunk_size=50, chunk_overlap=5)
    questions = [
        Question(id="s1", group="single", question="apple", answerable=True,
                 expected_answer="a", expected_sources=[{"doc_id": "apple.md"}]),
        Question(id="u1", group="unanswerable", question="durian", answerable=False),
    ]
    variants = [
        Variant("plain", collection, 1),
        Variant("reranked", collection, 1, reranker=PreferLongest(), candidates=2),
    ]

    rows = retrieval_hit_rates(questions, variants, embedder=KeywordEmbedder())

    assert [rate for _, rate in rows] == [1.0, 0.0]   # the fake reranker picks the wrong passage
    assert "| plain | 100% |" in render_hit_rates(rows, "note")
