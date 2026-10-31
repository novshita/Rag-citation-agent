import pytest

from rag.fallback import ABSTAIN_MESSAGE
from rag.gate import GateDecision
from rag.highlight import find_quote, highlight_html
from rag.pipeline import PipelineResult
from rag.schemas import Citation, Claim, RAGAnswer, RetrievedChunk

CHUNK_TEXT = "To receive uploaded files, first install [`python-multipart`](https://example.com/pm).\n\nThis is because <b>form data</b>."


def test_find_quote_exact_and_case_insensitive():
    text = "Hello there. The Quick brown fox jumps."
    start, end = find_quote(text, "the quick BROWN fox")
    assert text[start:end] == "The Quick brown fox"


def test_find_quote_through_markdown_formatting():
    start, end = find_quote(CHUNK_TEXT, "first install python-multipart")
    assert CHUNK_TEXT[start:end] == "first install [`python-multipart"


def test_find_quote_missing_or_empty():
    assert find_quote("some text here", "not present at all") is None
    assert find_quote("some text", "...") is None


def test_highlight_wraps_the_quote():
    out = highlight_html(CHUNK_TEXT, "first install python-multipart")
    assert "<mark>first install [`python-multipart</mark>" in out


def test_highlight_escapes_html_in_the_passage():
    out = highlight_html("Use <script>alert(1)</script> now", "use script alert")
    assert "<script>" not in out and "&lt;script&gt;" in out      # never rendered as live HTML
    assert "<mark>" in out


def test_highlight_without_a_match_returns_escaped_text_only():
    assert highlight_html("a <b> c", "zzz yyy") == "a &lt;b&gt; c"


def make_result(status="answered"):
    chunk = RetrievedChunk(chunk_id="g.md:c0", doc_id="g.md", page=None, text=CHUNK_TEXT,
                           char_start=0, char_end=len(CHUNK_TEXT), score=0.81)
    gate = GateDecision(True, 0.81, 0.1)
    if status == "abstained":
        answer = RAGAnswer(status="abstained", answer=ABSTAIN_MESSAGE, confidence=0.0, reason="Not covered.")
    else:
        answer = RAGAnswer(
            status="answered", answer="Install python-multipart.", confidence=0.9,
            claims=[Claim(text="You must install python-multipart.", citations=[
                Citation(chunk_id="g.md:c0", doc_id="g.md", quote="first install python-multipart")])],
        )
    return PipelineResult(answer, [chunk], gate)


APP = """
from rag.ui import run_app
from test_ui import make_result
run_app(lambda question: make_result(__import__("os").environ.get("FAKE_STATUS", "answered")))
"""


def run_app_with(monkeypatch, status, question="how do uploads work?"):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("FAKE_STATUS", status)
    app = AppTest.from_string(APP, default_timeout=30).run()
    app.text_input[0].set_value(question).run()
    app.button[0].click().run()
    return app


def test_ui_shows_answer_citation_and_highlighted_source(monkeypatch):
    app = run_app_with(monkeypatch, "answered")

    assert not app.exception
    text = " ".join(m.value for m in app.markdown)
    assert "Answered" in text and "confidence 0.90" in text
    assert "You must install python-multipart." in text
    assert any("<mark>" in m.value for m in app.markdown)       # the source passage, highlighted
    assert [e.label for e in app.expander][0] == "Source: g.md"


def test_ui_shows_abstention_with_reason(monkeypatch):
    app = run_app_with(monkeypatch, "abstained")

    assert not app.exception
    assert any("Abstained" in m.value for m in app.markdown)
    assert any("Not covered." in c.value for c in app.caption)


def test_ui_ignores_blank_questions(monkeypatch):
    app = run_app_with(monkeypatch, "answered", question="   ")
    assert not app.exception
    assert not any("Answered" in m.value for m in app.markdown)
