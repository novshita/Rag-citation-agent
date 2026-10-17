import json

from rag.logger import connect, log_query
from rag.pipeline import answer_question
from test_generator import FakeLLM, answered_json, chunk


def only_row(conn):
    rows = conn.execute("SELECT * FROM queries").fetchall()
    assert len(rows) == 1
    return rows[0]


def test_logs_an_answered_query():
    conn = connect(":memory:")
    chunks = [chunk(score=0.8)]
    result = answer_question("What is the capital?", chunks, FakeLLM(answered_json()), 0.3, 2)

    row_id = log_query(conn, "What is the capital?", result, latency_ms=42)

    row = only_row(conn)
    assert row["id"] == row_id
    assert row["question"] == "What is the capital?"
    assert json.loads(row["retrieved"]) == [{"chunk_id": "a.md::0", "score": 0.8}]
    assert row["gate_passed"] == 1 and row["status"] == "answered"
    assert (row["claims_total"], row["claims_passed"], row["attempts"]) == (1, 1, 1)
    assert (row["input_tokens"], row["output_tokens"], row["latency_ms"]) == (10, 5, 42)


def test_logs_gate_failure_without_generation_fields():
    conn = connect(":memory:")
    result = answer_question("q", [chunk(score=0.1)], FakeLLM(), 0.3, 2)

    log_query(conn, "q", result, latency_ms=3)

    row = only_row(conn)
    assert row["gate_passed"] == 0 and "MIN_SCORE" in row["gate_reason"]
    assert row["status"] == "abstained"
    assert row["claims_total"] is None and row["attempts"] is None
    assert row["input_tokens"] == 0


def test_logs_a_query_with_no_chunks():
    conn = connect(":memory:")
    result = answer_question("q", [], FakeLLM(), 0.3, 2)

    log_query(conn, "q", result, latency_ms=1)

    row = only_row(conn)
    assert json.loads(row["retrieved"]) == [] and row["top_score"] is None


def test_creates_parent_folder_for_file_db(tmp_path):
    conn = connect(str(tmp_path / "nested" / "logs.sqlite"))
    assert conn.execute("SELECT COUNT(*) FROM queries").fetchone()[0] == 0
