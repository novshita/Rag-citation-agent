import pytest
from fastapi.testclient import TestClient

from rag.api import create_app
from rag.logger import connect
from test_ui import make_result


def client(ask=None, **kwargs):
    seen = []

    def fake_ask(question, top_k):
        seen.append((question, top_k))
        return make_result("answered")

    app = create_app(ask or fake_ask, **kwargs)
    return TestClient(app), seen


def test_health():
    c, _ = client()
    assert c.get("/health").json() == {"status": "ok"}


def test_ask_returns_the_cited_answer():
    c, seen = client()
    response = c.post("/ask", json={"question": "  how do uploads work?  ", "top_k": 3})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "answered" and body["confidence"] == 0.9
    citation = body["claims"][0]["citations"][0]
    assert citation["doc_id"] == "g.md" and citation["quote"] == "first install python-multipart"
    assert body["retrieved"] == [{"chunk_id": "g.md:c0", "doc_id": "g.md", "page": None, "score": 0.81}]
    assert body["gate_passed"] is True and body["latency_ms"] >= 0
    assert seen == [("how do uploads work?", 3)]                  # trimmed, and top_k passed through


@pytest.mark.parametrize("payload", [{}, {"question": ""}, {"question": "x" * 2001}, {"question": "q", "top_k": 0}, {"question": "q", "top_k": 99}])
def test_ask_rejects_invalid_requests(payload):
    c, seen = client()
    assert c.post("/ask", json=payload).status_code == 422
    assert seen == []


def test_api_key_is_required_only_when_configured():
    open_client, _ = client()
    locked, seen = client(api_key="secret")

    assert open_client.post("/ask", json={"question": "q"}).status_code == 200
    assert locked.post("/ask", json={"question": "q"}).status_code == 401
    assert locked.post("/ask", json={"question": "q"}, headers={"X-API-Key": "wrong"}).status_code == 401
    assert locked.post("/ask", json={"question": "q"}, headers={"X-API-Key": "secret"}).status_code == 200
    assert locked.get("/health").status_code == 200               # health stays open for load balancers
    assert len(seen) == 1                                         # rejected requests never reached the model


def test_provider_errors_become_a_short_502():
    def broken(question, top_k):
        raise RuntimeError("429 quota exceeded\nlong provider dump...")

    c, _ = client(broken)
    response = c.post("/ask", json={"question": "q"})

    assert response.status_code == 502
    assert response.json()["detail"] == "RuntimeError: 429 quota exceeded"


def test_queries_are_logged_when_a_log_db_is_given(tmp_path):
    db = str(tmp_path / "logs.sqlite")
    c, _ = client(log_db=db)
    c.post("/ask", json={"question": "how do uploads work?"})
    c.post("/ask", json={"question": "again"})

    rows = connect(db).execute("SELECT question, status FROM queries ORDER BY id").fetchall()
    assert [(r["question"], r["status"]) for r in rows] == [("how do uploads work?", "answered"), ("again", "answered")]
