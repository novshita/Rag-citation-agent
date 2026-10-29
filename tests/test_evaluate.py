import json
import re

import pytest

from conftest import KeywordEmbedder
from rag.evaluate import (
    Question, compute_metrics, evaluate, load_questions, render_report,
)
from rag.generator import SYSTEM_PROMPT
from rag.ingest import ingest_folder
from rag.llm import LLMReply


class ScriptedLLM:
    """Routes by system prompt: generator, judge, or baseline."""

    def __init__(self, generator, judge, baseline="I think it is X."):
        self.generator, self.judge, self.baseline = generator, judge, baseline

    def complete(self, system, messages):
        if system == SYSTEM_PROMPT:
            text = self.generator(messages[0]["content"])
        elif "grade answers" in system:
            text = self.judge
        else:
            text = self.baseline
        return LLMReply(text, 10, 5)


def cited(quote):
    """A generator that cites the first chunk in the prompt with the given quote."""
    def generate(prompt):
        chunk_id = re.search(r"chunk_id: (\S+)", prompt).group(1)
        return json.dumps({
            "status": "answered", "answer": "ok", "confidence": 0.9, "reason": None,
            "claims": [{"text": "claim", "citations": [
                {"chunk_id": chunk_id, "doc_id": "fruit.md", "quote": quote}]}],
        })
    return generate


@pytest.fixture
def corpus(collection, tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "fruit.md").write_text("apple apple apple is the best fruit in the world")
    ingest_folder(str(docs), collection, KeywordEmbedder(), chunk_size=50, chunk_overlap=5)
    return collection


QUESTIONS = [
    Question(id="s1", group="single", question="apple", answerable=True,
             expected_answer="apple", expected_sources=[{"doc_id": "fruit.md"}]),
    Question(id="u1", group="unanswerable", question="durian durian", answerable=False),
]


def run(corpus, generator, judge='{"declined": false, "correct": true}', min_score=0.5):
    return evaluate(
        QUESTIONS, collection=corpus, embedder=KeywordEmbedder(),
        llm=ScriptedLLM(generator, judge), top_k=3, min_score=min_score, max_retries=0,
    )


def by(outcomes, system, qid):
    return next(o for o in outcomes if o.system == system and o.question.id == qid)


def test_full_abstains_on_unanswerable_while_naive_answers(corpus):
    outcomes = run(corpus, cited("apple apple apple is the best"))

    assert by(outcomes, "full", "u1").abstained          # gate stops it (no overlap with the corpus)
    assert not by(outcomes, "naive", "u1").abstained     # naive happily answers
    assert by(outcomes, "full", "s1").correct is True and by(outcomes, "full", "s1").hit is True


def test_naive_keeps_fabricated_citation_but_counts_it(corpus):
    outcomes = run(corpus, cited("this quote was invented"))

    naive = by(outcomes, "naive", "s1")
    assert not naive.abstained
    assert (naive.citations_valid, naive.citations_total, naive.unsupported_claims) == (0, 1, 1)
    assert by(outcomes, "full", "s1").abstained          # verifier removed the only claim


def test_baseline_abstention_comes_from_judge(corpus):
    outcomes = run(corpus, cited("apple apple apple is the best"),
                   judge='{"declined": true, "correct": null}')
    assert by(outcomes, "baseline", "s1").abstained


def test_metrics_and_report(corpus):
    outcomes = run(corpus, cited("apple apple apple is the best"))
    full = compute_metrics([o for o in outcomes if o.system == "full"])
    naive = compute_metrics([o for o in outcomes if o.system == "naive"])

    assert full.abstention_accuracy == 1.0 and full.hallucination_unanswerable == 0.0
    assert naive.hallucination_unanswerable == 1.0
    assert full.correctness == 1.0 and full.hit_rate == 1.0
    assert full.citation_validity == 1.0

    report = render_report(QUESTIONS, outcomes, "test settings")
    assert "| Hallucination rate (unanswerable) | 100% | 100% | 0% |" in report
    assert "| s1 | single | full |" in report


def test_load_questions_validates(tmp_path):
    path = tmp_path / "q.json"
    path.write_text(json.dumps([
        {"id": "a", "group": "single", "question": "q", "answerable": True}]))
    with pytest.raises(ValueError, match="expected_answer"):
        load_questions(path)

    path.write_text(json.dumps([
        {"id": "a", "group": "unanswerable", "question": "q", "answerable": False},
        {"id": "a", "group": "unanswerable", "question": "q2", "answerable": False}]))
    with pytest.raises(ValueError, match="unique"):
        load_questions(path)


def test_checkpoint_saves_results_and_a_rerun_skips_finished_work(corpus, tmp_path):
    from rag.evaluate import Checkpoint

    path = tmp_path / "ck.jsonl"
    calls = []

    def generator(prompt):
        calls.append(prompt)
        return cited("apple apple apple is the best")(prompt)

    def run_once(**kwargs):
        return evaluate(
            QUESTIONS, collection=corpus, embedder=KeywordEmbedder(),
            llm=ScriptedLLM(generator, '{"declined": false, "correct": true}'),
            top_k=3, min_score=0.5, max_retries=0,
            checkpoint=Checkpoint(path, "fp-1"), **kwargs,
        )

    first = run_once()
    calls_first_run = len(calls)
    progress = []
    second = run_once(on_progress=lambda n, total, qid, resumed: progress.append((qid, resumed)))

    assert calls_first_run > 0 and len(calls) == calls_first_run    # nothing was recomputed
    assert progress == [("s1", True), ("u1", True)]
    assert [(o.system, o.question.id, o.abstained, o.correct) for o in second] == \
           [(o.system, o.question.id, o.abstained, o.correct) for o in first]


def test_checkpoint_resumes_after_an_interruption(corpus, tmp_path):
    from rag.evaluate import Checkpoint

    path = tmp_path / "ck.jsonl"

    class Boom(Exception):
        pass

    seen = []

    def crashing(prompt):
        seen.append(1)
        if "durian" in prompt:
            raise Boom
        return cited("apple apple apple is the best")(prompt)

    def run(generator):
        return evaluate(
            QUESTIONS, collection=corpus, embedder=KeywordEmbedder(),
            llm=ScriptedLLM(generator, '{"declined": false, "correct": true}'),
            top_k=3, min_score=0.0, max_retries=0, checkpoint=Checkpoint(path, "fp"),
        )

    with pytest.raises(Boom):
        run(crashing)                       # dies on the second question
    saved = len(path.read_text().splitlines()) - 1
    assert saved >= 3                       # the first question's results were already on disk

    outcomes = run(cited("apple apple apple is the best"))
    assert len(outcomes) == 6 and {o.question.id for o in outcomes} == {"s1", "u1"}


def test_checkpoint_from_different_settings_is_refused(corpus, tmp_path):
    from rag.evaluate import Checkpoint

    path = tmp_path / "ck.jsonl"
    llm = ScriptedLLM(cited("apple apple apple is the best"), '{"declined": false, "correct": true}')
    kwargs = dict(collection=corpus, embedder=KeywordEmbedder(), llm=llm, top_k=3, min_score=0.5, max_retries=0)
    evaluate(QUESTIONS, checkpoint=Checkpoint(path, "min_score 0.5"), **kwargs)

    with pytest.raises(ValueError, match="--fresh"):
        evaluate(QUESTIONS, checkpoint=Checkpoint(path, "min_score 0.9"), **kwargs)
