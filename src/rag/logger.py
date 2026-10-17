"""SQLite log of every query: what was retrieved, what the gate decided, and how it ended."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from rag.pipeline import PipelineResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS queries (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at     TEXT NOT NULL,
    question       TEXT NOT NULL,
    retrieved      TEXT NOT NULL,     -- JSON: [{"chunk_id": ..., "score": ...}, ...]
    gate_passed    INTEGER NOT NULL,
    gate_reason    TEXT,
    top_score      REAL,
    status         TEXT NOT NULL,     -- answered / partial / abstained
    confidence     REAL NOT NULL,
    claims_total   INTEGER,           -- NULL when the gate stopped generation
    claims_passed  INTEGER,
    attempts       INTEGER,           -- LLM calls made (1 = no retry)
    input_tokens   INTEGER NOT NULL,
    output_tokens  INTEGER NOT NULL,
    latency_ms     INTEGER NOT NULL
)
"""


def connect(path: str) -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA)
    return conn


def log_query(
    conn: sqlite3.Connection,
    question: str,
    result: PipelineResult,
    latency_ms: int,
) -> int:
    """Write one row and return its id."""
    generation, verification = result.generation, result.verification
    cursor = conn.execute(
        """
        INSERT INTO queries (
            created_at, question, retrieved, gate_passed, gate_reason, top_score,
            status, confidence, claims_total, claims_passed, attempts,
            input_tokens, output_tokens, latency_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            question,
            json.dumps([{"chunk_id": c.chunk_id, "score": round(c.score, 4)} for c in result.chunks]),
            int(result.gate.passed),
            result.gate.reason,
            result.gate.top_score,
            result.answer.status,
            result.answer.confidence,
            verification.claims_total if verification else None,
            verification.claims_passed if verification else None,
            generation.attempts if generation else None,
            generation.input_tokens if generation else 0,
            generation.output_tokens if generation else 0,
            latency_ms,
        ),
    )
    conn.commit()
    return cursor.lastrowid
