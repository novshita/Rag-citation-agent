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
    assert c.get("/corpus").json() == {**info, "uploads": None}      # None: this server has no uploads
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


# ---- the visitor's own uploaded document ----

from pdfmaker import make_pdf  # noqa: E402
from rag.uploads import UploadManager  # noqa: E402

DOC = ("Employees accrue vacation at two days per month. " * 30).encode()


class _Vectors:
    def embed(self, texts):
        return [[1.0, float(len(t) % 5), 0.5, 0.25] for t in texts]


def with_uploads(tmp_path, with_auth=True, **kwargs):
    chromadb = pytest.importorskip("chromadb")
    asked = []

    def answer(question, top_k, collection):
        asked.append((question, top_k, collection.count()))
        return make_result("answered")

    manager = UploadManager(_Vectors(), answer, background=False, client=chromadb.EphemeralClient(), chunk_size=30, chunk_overlap=5)
    extra = {}
    if with_auth:
        extra["auth"] = AuthService(str(tmp_path / "auth.sqlite"), "a-test-secret-that-is-long-enough", guest_limit=3, user_limit=5)
    c, seen = client(uploads=manager, **extra, **kwargs)
    if with_auth:
        c.post("/auth/guest")
    return c, seen, asked, manager


def put(c, name, data):
    return c.post("/documents", content=data, headers={"X-Filename": name})


def test_corpus_says_when_uploads_are_available(tmp_path):
    c, *_ = with_uploads(tmp_path)
    assert c.get("/corpus").json()["uploads"] == {"max_mb": 5, "max_pages": 50, "ttl_minutes": 60}


def test_upload_then_status_then_ask_it(tmp_path):
    c, seen, asked, _ = with_uploads(tmp_path)
    assert c.get("/documents").json()["state"] == "none"
    response = put(c, "handbook.md", DOC)
    assert response.status_code == 202 and response.json()["state"] == "ready" and response.json()["filename"] == "handbook.md"
    assert response.headers["cache-control"] == "no-store"

    answer = c.post("/ask", json={"question": "how much vacation?", "top_k": 3, "source": "mine"})
    assert answer.status_code == 200 and answer.headers["x-questions-remaining"] == "2"
    assert asked == [("how much vacation?", 3, c.get("/documents").json()["passages_total"])] and seen == []   # the sample index was not used


def test_asking_the_sample_docs_still_works_and_is_the_default(tmp_path):
    c, seen, asked, _ = with_uploads(tmp_path)
    put(c, "handbook.md", DOC)
    assert c.post("/ask", json={"question": "q"}).status_code == 200
    assert len(seen) == 1 and asked == []


def test_asking_your_document_before_uploading_does_not_use_a_question(tmp_path):
    c, seen, asked, _ = with_uploads(tmp_path)
    blocked = c.post("/ask", json={"question": "q", "source": "mine"})
    assert blocked.status_code == 409 and "Upload a document first" in blocked.json()["detail"]
    assert c.get("/auth/me").json()["remaining"] == 3 and seen == [] and asked == []


def test_one_visitors_document_is_invisible_to_another(tmp_path):
    first, *_ , manager = with_uploads(tmp_path)
    put(first, "secret.md", DOC)
    other = TestClient(first.app)
    other.post("/auth/guest")                                    # a different guest session
    assert other.get("/documents").json()["state"] == "none"
    assert other.post("/ask", json={"question": "q", "source": "mine"}).status_code == 409
    assert first.get("/documents").json()["filename"] == "secret.md"


def test_documents_need_a_session_when_accounts_are_on(tmp_path):
    c, *_ = with_uploads(tmp_path)
    c.post("/auth/logout")
    for response in (c.get("/documents"), put(c, "a.md", DOC), c.delete("/documents")):
        assert response.status_code == 401


def test_remove_and_sign_out_both_delete_the_document(tmp_path):
    c, *_ , manager = with_uploads(tmp_path)
    put(c, "a.md", DOC)
    assert c.delete("/documents").json()["state"] == "none" and c.get("/documents").json()["state"] == "none"
    put(c, "b.md", DOC)
    assert c.get("/documents").json()["state"] == "ready"
    subject = next(iter(manager._states))
    c.post("/auth/logout")
    assert manager._states == {} and subject not in manager._states


def test_upload_problems_come_back_as_plain_messages(tmp_path):
    c, *_ = with_uploads(tmp_path)
    too_big = c.post("/documents", content=b"x" * (6 * 1024 * 1024), headers={"X-Filename": "annual-report.pdf"})
    assert too_big.status_code == 413
    assert too_big.json()["detail"] == "This file is too large. annual-report.pdf is 6.0 MB. The limit is 5 MB or 50 pages."
    assert put(c, "a.exe", b"data").status_code == 415
    scanned = put(c, "scan.pdf", make_pdf([""]))
    assert scanned.status_code == 202 and scanned.json()["state"] == "error" and "scanned" in scanned.json()["error"]


def test_a_pdf_upload_keeps_page_numbers(tmp_path):
    c, *_ = with_uploads(tmp_path)
    status = put(c, "two.pdf", make_pdf(["Alpha beta gamma", "Delta epsilon zeta"])).json()
    assert status["state"] == "ready" and status["pages"] == 2 and status["passages_total"] == 2


def test_the_filename_header_is_url_decoded_and_cleaned(tmp_path):
    c, *_ = with_uploads(tmp_path)
    assert put(c, "my%20notes%20%E2%80%93%20v2.md", DOC).json()["filename"] == "my notes – v2.md"
    assert put(c, "..%2F..%2Fetc%2Fpasswd.md", DOC).json()["filename"] == "passwd.md"


def test_uploads_work_without_accounts_for_local_use(tmp_path):
    c, *_ = with_uploads(tmp_path, with_auth=False)
    assert put(c, "a.md", DOC).json()["state"] == "ready"
    assert c.post("/ask", json={"question": "q", "source": "mine"}).status_code == 200


def test_servers_without_uploads_say_so():
    c, _ = client()
    assert c.get("/documents").status_code == 404
    refused = c.post("/ask", json={"question": "q", "source": "mine"})
    assert refused.status_code == 400 and "isn't enabled" in refused.json()["detail"]


def test_the_page_and_its_files_are_revalidated_so_an_update_is_never_half_applied():
    c, _ = client()
    for path in ("/", "/static/app.js", "/static/site.css"):
        response = c.get(path)
        assert response.status_code == 200 and response.headers["cache-control"] == "no-cache", path
    first = c.get("/static/app.js")
    again = c.get("/static/app.js", headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304                                  # unchanged files still cost almost nothing


# ---- email verification over HTTP ----

class _Outbox:
    def __init__(self):
        self.sent = []

    def send(self, to, subject, body):
        self.sent.append((to, subject, body))

    def token(self):
        import re
        return re.search(r"token=([\w\-.=]+)", self.sent[-1][2]).group(1)


def with_verification(tmp_path, public_url="https://demo.example"):
    box = _Outbox()
    auth = AuthService(str(tmp_path / "auth.sqlite"), "a-test-secret-that-is-long-enough", require_verification=True, mailer=box)
    c, seen = client(auth=auth, public_url=public_url)
    return c, seen, box


def test_signup_asks_for_the_email_instead_of_signing_in(tmp_path):
    c, seen, box = with_verification(tmp_path)
    response = c.post("/auth/signup", json={"email": "Ada@Example.com", "password": "longenough1"})
    assert response.status_code == 202 and response.json() == {"verify": True, "email": "ada@example.com"}
    assert "set-cookie" not in response.headers and response.headers["cache-control"] == "no-store"
    assert c.get("/auth/me").json()["authenticated"] is False
    assert c.post("/ask", json={"question": "q"}).status_code == 401 and seen == []
    assert box.sent[0][0] == "ada@example.com" and "https://demo.example/#/verify?token=" in box.sent[0][2]


def test_signing_in_before_confirming_is_a_403_and_the_link_then_signs_in(tmp_path):
    c, seen, box = with_verification(tmp_path)
    c.post("/auth/signup", json={"email": "ada@example.com", "password": "longenough1"})
    early = c.post("/auth/login", json={"email": "ada@example.com", "password": "longenough1"})
    assert early.status_code == 403 and "Confirm your email" in early.json()["detail"]

    confirmed = c.post("/auth/verify", json={"token": box.token()})
    assert confirmed.status_code == 200 and "rag_session=" in confirmed.headers["set-cookie"]
    me = c.get("/auth/me").json()
    assert me["authenticated"] and me["email"] == "ada@example.com"
    assert c.post("/ask", json={"question": "q"}).status_code == 200


def test_a_bad_or_used_link_gets_a_plain_message(tmp_path):
    c, _, box = with_verification(tmp_path)
    c.post("/auth/signup", json={"email": "ada@example.com", "password": "longenough1"})
    assert c.post("/auth/verify", json={"token": "nonsense"}).status_code == 400
    token = box.token()
    assert c.post("/auth/verify", json={"token": token}).status_code == 200
    again = c.post("/auth/verify", json={"token": token})
    assert again.status_code == 409 and "already used" in again.json()["detail"]


def test_resend_answers_the_same_for_any_address(tmp_path):
    c, _, box = with_verification(tmp_path)
    c.post("/auth/signup", json={"email": "ada@example.com", "password": "longenough1"})
    for email in ("ada@example.com", "nobody@example.com"):
        response = c.post("/auth/resend", json={"email": email})
        assert response.status_code == 202 and response.json() == {"ok": True}
    assert len(box.sent) == 1                                                   # the recent email was not repeated; nobody@ got nothing


def test_the_link_points_at_public_url_or_the_request_when_it_is_not_set(tmp_path):
    c, _, box = with_verification(tmp_path, public_url="")
    c.post("/auth/signup", json={"email": "ada@example.com", "password": "longenough1"})
    assert "http://testserver/#/verify?token=" in box.sent[0][2]
