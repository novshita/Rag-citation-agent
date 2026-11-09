"""HTTP API and web UI.

    uvicorn rag.api:create_default_app --factory --port 8000      (needs: pip install -e ".[api]")

  GET  /          the web UI (static files in rag/web)
  POST /ask       a cited answer as JSON
  GET  /corpus    what is indexed: name, grouped file list, example questions, settings the UI shows
  GET  /health    liveness check

Set RAG_API_KEY to require an `X-API-Key` header on /ask. That protects API callers; the browser UI
cannot hold a secret, so a deployment that must stay open to visitors needs rate limits instead.
Every request spends LLM quota either way.
"""

import os
import secrets
import time
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from rag.highlight import find_quote
from rag.pipeline import PipelineResult

WEB_DIR = Path(__file__).parent / "web"


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)


class CitationOut(BaseModel):
    chunk_id: str
    doc_id: str
    page: int | None
    quote: str                                  # the exact words the model quoted
    passage: str | None                         # the source passage the quote was found in
    highlight: tuple[int, int] | None           # [start, end) of the quote inside `passage`


class ClaimOut(BaseModel):
    text: str
    citations: list[CitationOut]


class Source(BaseModel):
    chunk_id: str
    doc_id: str
    page: int | None
    score: float                                # vector similarity to the question
    text: str


class GateOut(BaseModel):
    passed: bool
    top_score: float | None
    threshold: float
    reason: str | None


class VerificationOut(BaseModel):
    claims_total: int                           # claims the model wrote
    claims_passed: int                          # claims whose quotes were found in their sources


class WebSource(BaseModel):
    title: str
    url: str
    snippet: str


class WebOut(BaseModel):
    answer: str
    disclaimer: str                             # always present: this is NOT grounded in the documents
    sources: list[WebSource]


class AskResponse(BaseModel):
    status: str                                 # answered / partial / abstained
    answer: str
    confidence: float
    reason: str | None
    claims: list[ClaimOut]                      # each with its verified citations (doc, page, exact quote)
    retrieved: list[Source]
    gate: GateOut
    gate_passed: bool                           # same as gate.passed, kept for older clients
    model_called: bool                          # False when the relevance gate stopped the question
    verification: VerificationOut | None
    latency_ms: int
    tokens: int
    web: WebOut | None = None                   # only when abstained and WEB_FALLBACK is on; never part of `claims`


def to_response(result: PipelineResult, latency_ms: int, min_score: float = 0.0) -> AskResponse:
    answer, generation, verification = result.answer, result.generation, result.verification
    passages = {c.chunk_id: c.text for c in result.chunks}

    claims = []
    for claim in answer.claims:
        citations = []
        for c in claim.citations:
            passage = passages.get(c.chunk_id)
            span = find_quote(passage, c.quote) if passage else None
            citations.append(CitationOut(
                chunk_id=c.chunk_id, doc_id=c.doc_id, page=c.page, quote=c.quote,
                passage=passage, highlight=span,
            ))
        claims.append(ClaimOut(text=claim.text, citations=citations))

    return AskResponse(
        status=answer.status, answer=answer.answer, confidence=answer.confidence, reason=answer.reason,
        claims=claims,
        retrieved=[Source(chunk_id=c.chunk_id, doc_id=c.doc_id, page=c.page, score=round(c.score, 4), text=c.text)
                   for c in result.chunks],
        gate=GateOut(passed=result.gate.passed, top_score=result.gate.top_score,
                     threshold=min_score, reason=result.gate.reason),
        gate_passed=result.gate.passed,
        model_called=generation is not None,
        verification=None if verification is None else VerificationOut(
            claims_total=verification.claims_total, claims_passed=verification.claims_passed),
        latency_ms=latency_ms,
        tokens=(generation.input_tokens + generation.output_tokens) if generation else 0,
        web=None if result.web is None else WebOut(
            answer=result.web.answer, disclaimer=result.web.disclaimer,
            sources=[WebSource(title=s.title, url=s.url, snippet=s.snippet) for s in result.web.sources],
        ),
    )


def create_app(
    ask,
    api_key: str | None = None,
    log_db: str | None = None,
    min_score: float = 0.0,
    corpus: dict | None = None,
    serve_ui: bool = True,
) -> FastAPI:
    """`ask(question, top_k) -> PipelineResult` is passed in so tests can use a fake."""
    app = FastAPI(title="RAG Citation Agent", description="Answers only from the indexed documents, with verified quotes.")

    def check_key(x_api_key: str | None = Header(default=None)) -> None:
        if api_key and not (x_api_key and secrets.compare_digest(x_api_key, api_key)):
            raise HTTPException(status_code=401, detail="missing or invalid X-API-Key")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/corpus")
    def corpus_info() -> dict:
        return corpus or {"name": "Indexed documents", "note": "", "tagline": "", "pages": 0, "groups": [],
                          "examples": [], "top_k": 5, "min_score": min_score, "llm": ""}

    @app.post("/ask", response_model=AskResponse, dependencies=[Depends(check_key)])
    def ask_endpoint(request: AskRequest) -> AskResponse:
        started = time.perf_counter()
        try:
            result = ask(request.question.strip(), request.top_k)
        except Exception as error:   # model/provider failures (rate limits, bad key) are upstream problems
            first_line = (str(error).strip().splitlines() or [""])[0]
            raise HTTPException(status_code=502, detail=f"{type(error).__name__}: {first_line}") from error
        latency_ms = int((time.perf_counter() - started) * 1000)

        if log_db:
            from rag.logger import connect, log_query

            conn = connect(log_db)      # one short-lived connection per request: sqlite objects are per-thread
            try:
                log_query(conn, request.question, result, latency_ms)
            finally:
                conn.close()
        return to_response(result, latency_ms, min_score)

    if serve_ui and WEB_DIR.is_dir():
        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(WEB_DIR / "index.html")

        app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    return app


def create_default_app() -> FastAPI:
    from rag.config import load_settings
    from rag.corpus import build_corpus_info, load_manifest, manifest_path
    from rag.runtime import build_ask
    from rag.store import get_collection

    settings = load_settings()
    collection = get_collection(settings.chroma_dir, settings.collection)
    doc_ids = [m["doc_id"] for m in collection.get(include=["metadatas"])["metadatas"]] if collection.count() else []
    info = build_corpus_info(
        doc_ids, load_manifest(manifest_path(os.getenv("CORPUS_MANIFEST", ""), settings.collection)),
        top_k=settings.top_k, min_score=settings.min_score, llm_provider=settings.llm_provider,
    )
    return create_app(
        build_ask(settings), api_key=os.getenv("RAG_API_KEY") or None, log_db=settings.log_db,
        min_score=settings.min_score, corpus=info,
    )
