"""Optional web-search fallback for questions the documents can't answer.

Only used when the system has abstained AND WEB_FALLBACK=true. The result is kept apart
from the grounded answer: it has no verified quotes, it is always shown with WEB_DISCLAIMER,
and it never changes the answer's status. The question is sent to a web search service
and the result snippets to the LLM, so leave this off for private questions.
"""

from dataclasses import dataclass
from typing import Protocol

from rag.llm import LLM

WEB_DISCLAIMER = (
    "Not from your documents. This comes from a web search, and none of it has been "
    "checked against your sources."
)

SYSTEM_PROMPT = """\
Answer the question using ONLY the numbered web search results below. Keep it to 2-4 sentences \
and cite results like [1]. If the results do not clearly answer the question, say you could not \
find a reliable answer. Do not add facts that are not in the results."""


@dataclass(frozen=True)
class WebResult:
    title: str
    url: str
    snippet: str


class WebSearch(Protocol):
    def search(self, query: str, max_results: int) -> list[WebResult]: ...


class DuckDuckGoSearch:
    """Keyless web search through the `ddgs` package (pip install -e ".[web]")."""

    def search(self, query: str, max_results: int) -> list[WebResult]:
        from ddgs import DDGS

        rows = DDGS().text(query, max_results=max_results) or []
        return [WebResult(r.get("title", ""), r.get("href", ""), r.get("body", "")) for r in rows]


@dataclass(frozen=True)
class WebAnswer:
    answer: str
    sources: list[WebResult]
    disclaimer: str = WEB_DISCLAIMER


def web_fallback(question: str, search: WebSearch, llm: LLM, max_results: int = 5) -> WebAnswer | None:
    """A labelled answer from web results, or None if the search failed or found nothing."""
    try:
        results = [r for r in search.search(question, max_results) if r.snippet.strip()]
        if not results:
            return None
        listing = "\n\n".join(f"[{i}] {r.title}\n{r.snippet}" for i, r in enumerate(results, start=1))
        reply = llm.complete(SYSTEM_PROMPT, [{"role": "user", "content": f"Web search results:\n\n{listing}\n\nQuestion: {question}"}])
    except Exception:   # a flaky search or model call must not break the grounded answer path
        return None
    text = reply.text.strip()
    return WebAnswer(text, results) if text else None
