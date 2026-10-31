"""HTTP API: POST /ask returns a cited answer as JSON.

Run with:  uvicorn rag.api:create_default_app --factory --port 8000   (needs: pip install -e ".[api]")

Set RAG_API_KEY to require an `X-API-Key` header on /ask. Do that for any deployment
reachable from the internet, because every request spends LLM quota.
"""

import os
import secrets
import time

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from rag.pipeline import PipelineResult
from rag.schemas import Claim


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)


class Source(BaseModel):
    chunk_id: str
    doc_id: str
    page: int | None
    score: float


class AskResponse(BaseModel):
    status: str                       # answered / partial / abstained
    answer: str
    confidence: float
    reason: str | None
    claims: list[Claim]               # each with its verified citations (doc, page, exact quote)
    retrieved: list[Source]
    gate_passed: bool
    latency_ms: int
    tokens: int


def to_response(result: PipelineResult, latency_ms: int) -> AskResponse:
    answer, generation = result.answer, result.generation
    return AskResponse(
        status=answer.status, answer=answer.answer, confidence=answer.confidence, reason=answer.reason,
        claims=answer.claims,
        retrieved=[Source(chunk_id=c.chunk_id, doc_id=c.doc_id, page=c.page, score=round(c.score, 4))
                   for c in result.chunks],
        gate_passed=result.gate.passed,
        latency_ms=latency_ms,
        tokens=(generation.input_tokens + generation.output_tokens) if generation else 0,
    )


def create_app(ask, api_key: str | None = None, log_db: str | None = None) -> FastAPI:
    """`ask(question, top_k) -> PipelineResult` is passed in so tests can use a fake."""
    app = FastAPI(title="RAG Citation Agent", description="Answers only from the indexed documents, with verified quotes.")

    def check_key(x_api_key: str | None = Header(default=None)) -> None:
        if api_key and not (x_api_key and secrets.compare_digest(x_api_key, api_key)):
            raise HTTPException(status_code=401, detail="missing or invalid X-API-Key")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

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
        return to_response(result, latency_ms)

    return app


def create_default_app() -> FastAPI:
    from rag.config import load_settings
    from rag.runtime import build_ask

    settings = load_settings()
    return create_app(build_ask(settings), api_key=os.getenv("RAG_API_KEY") or None, log_db=settings.log_db)
