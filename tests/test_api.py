import pytest

pytest.importorskip("fastapi", reason="pip install -e \".[api]\"")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

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
    assert [(s["chunk_id"], s["doc_id"], s["score"]) for s in body["retrieved"]] == [("g.md:c0", "g.md", 0.81)]
    assert "python-multipart" in body["retrieved"][0]["text"]            # the passage text, for previews
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


def test_each_citation_carries_its_passage_and_where_the_quote_sits_in_it():
    c, _ = client()
    citation = c.post("/ask", json={"question": "q"}).json()["claims"][0]["citations"][0]

    start, end = citation["highlight"]
    assert citation["passage"][start:end].lower().replace("`", "").startswith("first install [")  \
        or "python-multipart" in citation["passage"][start:end]
    assert citation["quote"] == "first install python-multipart"


def test_gate_and_verification_details_are_reported():
    c, _ = client(min_score=0.42)
    body = c.post("/ask", json={"question": "q"}).json()

    assert body["gate"] == {"passed": True, "top_score": 0.81, "threshold": 0.42, "reason": None}
    assert body["gate_passed"] is True and body["model_called"] is False   # the fake result has no generation
    assert body["verification"] is None


def test_a_gate_stop_reports_no_model_call():
    from rag.fallback import ABSTAIN_MESSAGE
    from rag.gate import GateDecision
    from rag.pipeline import PipelineResult
    from rag.schemas import RAGAnswer

    def stopped(question, top_k):
        answer = RAGAnswer(status="abstained", answer=ABSTAIN_MESSAGE, confidence=0.0, reason="below threshold")
        return PipelineResult(answer, [], GateDecision(False, 0.25, 0.0, "Best match score 0.250 is below MIN_SCORE 0.420."))

    body = client(stopped, min_score=0.42)[0].post("/ask", json={"question": "q"}).json()

    assert body["status"] == "abstained" and body["model_called"] is False and body["tokens"] == 0
    assert body["gate"]["passed"] is False and body["gate"]["top_score"] == 0.25 and body["gate"]["threshold"] == 0.42
    assert body["claims"] == [] and body["retrieved"] == []


def test_corpus_endpoint_serves_what_the_ui_displays():
    info = {"name": "Docs", "note": "MIT", "tagline": "t", "pages": 1, "groups": [], "examples": [],
            "top_k": 5, "min_score": 0.42, "llm": "Gemini"}
    c, _ = client(corpus=info)
    assert c.get("/corpus").json() == info
    assert client()[0].get("/corpus").json()["name"] == "Indexed documents"      # sensible default


def test_the_web_ui_is_served_at_the_root_and_can_be_turned_off():
    from fastapi.testclient import TestClient

    page = client()[0].get("/")
    assert page.status_code == 200 and "RAG Citation Agent" in page.text
    assert client()[0].get("/static/app.js").status_code == 200
    assert TestClient(create_app(lambda q, k: None, serve_ui=False)).get("/").status_code == 404


# ---- accounts, guest sessions and daily limits ----

from rag.auth import AuthService  # noqa: E402


def with_auth(tmp_path, ask=None, **kwargs):
    auth = AuthService(str(tmp_path / "auth.sqlite"), "a-test-secret-that-is-long-enough", guest_limit=2, user_limit=3)
    c, seen = client(ask, auth=auth, **kwargs)
    return c, seen, auth


def test_ask_needs_a_session_when_accounts_are_on(tmp_path):
    c, seen, _ = with_auth(tmp_path)
    response = c.post("/ask", json={"question": "q"})
    assert response.status_code == 401 and "Sign in" in response.json()["detail"]
    assert seen == []


def test_me_reports_who_is_signed_in(tmp_path):
    c, _, _ = with_auth(tmp_path)
    assert c.get("/auth/me").json()["authenticated"] is False
    c.post("/auth/signup", json={"email": "Ada@Example.com", "password": "longenough1"})
    me = c.get("/auth/me").json()
    assert me["authenticated"] and me["kind"] == "user" and me["email"] == "ada@example.com"
    assert me["remaining"] == 3 and me["limit"] == 3


def test_signup_sets_a_secure_cookie_and_logout_clears_it(tmp_path):
    c, seen, _ = with_auth(tmp_path)
    response = c.post("/auth/signup", json={"email": "ada@example.com", "password": "longenough1"})
    assert response.status_code == 201
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "rag_session=" in cookie
    assert response.headers["cache-control"] == "no-store"
    assert "longenough1" not in response.text

    assert c.post("/ask", json={"question": "q"}).status_code == 200
    c.post("/auth/logout")
    assert c.post("/ask", json={"question": "q"}).status_code == 401
    assert len(seen) == 1


def test_login_errors_are_clear_and_generic(tmp_path):
    c, _, _ = with_auth(tmp_path)
    c.post("/auth/signup", json={"email": "ada@example.com", "password": "longenough1"})
    c.post("/auth/logout")
    wrong = c.post("/auth/login", json={"email": "ada@example.com", "password": "nope-nope-1"})
    unknown = c.post("/auth/login", json={"email": "who@example.com", "password": "nope-nope-1"})
    assert wrong.status_code == unknown.status_code == 401 and wrong.json() == unknown.json()
    assert c.post("/auth/signup", json={"email": "ada@example.com", "password": "otherpass99"}).status_code == 409
    assert c.post("/auth/signup", json={"email": "bad", "password": "longenough1"}).status_code == 422
    assert c.post("/auth/login", json={"email": "ada@example.com", "password": "longenough1"}).status_code == 200


def test_guest_session_has_a_daily_limit_and_a_remaining_header(tmp_path):
    c, seen, _ = with_auth(tmp_path)
    assert c.post("/auth/guest").json()["kind"] == "guest"
    first = c.post("/ask", json={"question": "q"})
    assert first.status_code == 200 and first.headers["x-questions-remaining"] == "1"
    assert c.post("/ask", json={"question": "q"}).headers["x-questions-remaining"] == "0"
    blocked = c.post("/ask", json={"question": "q"})
    assert blocked.status_code == 429 and "free account" in blocked.json()["detail"]
    assert len(seen) == 2                                         # the blocked question never reached the model


def test_a_failed_question_does_not_use_up_the_limit(tmp_path):
    def broken(question, top_k):
        raise RuntimeError("RESOURCE_EXHAUSTED: quota")

    c, _, auth = with_auth(tmp_path, ask=broken)
    c.post("/auth/guest")
    assert c.post("/ask", json={"question": "q"}).status_code == 502
    assert c.get("/auth/me").json()["remaining"] == 2


def test_a_forged_cookie_is_not_a_session(tmp_path):
    c, _, _ = with_auth(tmp_path)
    c.cookies.set("rag_session", "eyJrIjoidXNlciIsInMiOiJ1OjEiLCJlIjo5OTk5OTk5OTk5fQ.forged")
    assert c.get("/auth/me").json()["authenticated"] is False
    assert c.post("/ask", json={"question": "q"}).status_code == 401


def test_the_api_key_still_lets_scripts_skip_the_session(tmp_path):
    c, seen, _ = with_auth(tmp_path, api_key="secret")
    assert c.post("/ask", json={"question": "q"}).status_code == 401
    assert c.post("/ask", json={"question": "q"}, headers={"X-API-Key": "secret"}).status_code == 200
    assert len(seen) == 1


def test_without_accounts_everyone_is_let_in():
    c, _ = client()
    me = c.get("/auth/me").json()
    assert me["enabled"] is False and me["authenticated"] is True
    assert c.post("/auth/guest").status_code == 404               # no auth routes exist
