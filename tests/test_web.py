from rag.llm import LLMReply
from rag.pipeline import answer_question
from rag.web import WEB_DISCLAIMER, WebResult, web_fallback
from test_generator import FakeLLM, answered_json, chunk


class FakeSearch:
    def __init__(self, results=None, error=None):
        self.results, self.error, self.queries = results or [], error, []

    def search(self, query, max_results):
        self.queries.append((query, max_results))
        if self.error:
            raise self.error
        return self.results


HITS = [WebResult("Rate limiting guide", "https://example.com/rl", "Use slowapi to add rate limits."),
        WebResult("Empty", "https://example.com/e", "   ")]


def test_web_fallback_answers_from_the_results_and_labels_it():
    llm = FakeLLM("Use slowapi [1].")
    web = web_fallback("how to rate limit?", FakeSearch(HITS), llm, max_results=3)

    assert web.answer == "Use slowapi [1]."
    assert web.disclaimer == WEB_DISCLAIMER and "Not from your documents" in web.disclaimer
    assert [s.url for s in web.sources] == ["https://example.com/rl"]     # results without a snippet are dropped
    prompt = llm.calls[0][1][0]["content"]
    assert "Use slowapi to add rate limits." in prompt and "how to rate limit?" in prompt


def test_web_fallback_returns_none_when_nothing_is_found_or_anything_fails():
    assert web_fallback("q", FakeSearch([]), FakeLLM()) is None
    assert web_fallback("q", FakeSearch(error=RuntimeError("network down")), FakeLLM()) is None
    assert web_fallback("q", FakeSearch(HITS), FakeLLM("   ")) is None


def test_pipeline_only_searches_the_web_after_an_abstention():
    search = FakeSearch(HITS)
    # gate stops it (score below min_score) -> abstained -> web fallback runs
    result = answer_question("q", [chunk(score=0.1)], FakeLLM("From the web."), 0.3, 2, web_search=search)
    assert result.answer.status == "abstained" and result.web.answer == "From the web."
    assert result.answer.answer == "The provided documents do not contain this information."   # grounded answer untouched

    # a grounded answer never triggers a web search
    search2 = FakeSearch(HITS)
    result2 = answer_question("q", [chunk()], FakeLLM(answered_json()), 0.3, 2, web_search=search2)
    assert result2.answer.status == "answered" and result2.web is None and search2.queries == []


def test_pipeline_is_unchanged_when_the_fallback_is_off():
    result = answer_question("q", [chunk(score=0.1)], FakeLLM(), 0.3, 2)
    assert result.answer.status == "abstained" and result.web is None


def test_api_and_ui_show_the_web_result_with_its_label():
    import pytest

    pytest.importorskip("fastapi")
    pytest.importorskip("streamlit")
    from fastapi.testclient import TestClient
    from streamlit.testing.v1 import AppTest

    from rag.api import create_app
    from rag.web import WebAnswer
    from test_ui import make_result

    def ask(question, top_k):
        result = make_result("abstained")
        result.web = WebAnswer("Use slowapi [1].", [WebResult("Guide", "https://example.com/rl", "snippet")])
        return result

    body = TestClient(create_app(ask)).post("/ask", json={"question": "q"}).json()
    assert body["status"] == "abstained" and body["claims"] == []
    assert body["web"]["disclaimer"] == WEB_DISCLAIMER and body["web"]["sources"][0]["url"] == "https://example.com/rl"

    app = AppTest.from_string(
        "from rag.ui import run_app\nfrom test_web import make_web_result\nrun_app(lambda q: make_web_result())",
        default_timeout=30,
    ).run()
    app.text_input[0].set_value("q").run()
    app.button[0].click().run()
    assert not app.exception
    assert any("Not from your documents" in w.value for w in app.warning)


def make_web_result():
    from rag.web import WebAnswer
    from test_ui import make_result

    result = make_result("abstained")
    result.web = WebAnswer("Use slowapi [1].", [WebResult("Guide", "https://example.com/rl", "snippet")])
    return result
