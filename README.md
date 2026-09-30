# RAG Citation Agent

A question-answering agent that answers **only** from a document corpus, cites the exact source text for every claim, and says "I don't know" when the documents don't support an answer.

> **Headline result:** Hallucination rate on unanswerable questions dropped from **X%** (naive RAG) to **Y%** (full system), with a false-abstention rate of **Z%**.
> *(Numbers are filled in from `eval/results.md` after the evaluation runs.)*

> **Status:** Work in progress. See [SPEC.md](SPEC.md) for the full design.

---

## Why this exists

A plain LLM doesn't know your documents and will confidently make up answers. Retrieval-augmented generation (RAG) helps, but most RAG demos still hallucinate when retrieval is weak. This project adds **grounding checks**:

- Every claim must point to a retrieved chunk.
- Citations are checked in code: the quoted text must actually appear in the cited chunk.
- Weak retrieval triggers a fallback instead of a guess.

## Architecture

```
INGEST (offline)
docs ─► loader ─► chunker ─► embedder ─► vector store (Chroma)
                    │
                    └─ metadata: doc_id, page, chunk_id, char range

QUERY (online)
question ─► embed ─► retrieve top-k ─► confidence gate ─┬─► LOW ─► fallback
                                                        │
                                                        ▼ OK
                                         generate answer (LLM, context only)
                                                        │
                                                        ▼
                                          parse + validate (Pydantic, retry)
                                                        │
                                                        ▼
                                          citation verifier (substring check)
                                                        │
                                                        ▼
                                      final answer / partial answer / abstain
```

| Module | Responsibility |
|---|---|
| `ingest.py` | Load PDFs/Markdown, chunk, embed, store with metadata |
| `retriever.py` | Embed the query, run top-k search, return chunks with scores |
| `gate.py` | Decide whether retrieval is strong enough to attempt an answer |
| `generator.py` | Build the context-only prompt, call the LLM, validate output |
| `verifier.py` | Check that each citation's quote appears in the cited chunk |
| `fallback.py` | Abstain message (web-search fallback is a stretch goal) |
| `schemas.py` | Pydantic models for answers, claims, and citations |
| `logger.py` | SQLite logging of queries, retrievals, and decisions |
| `cli.py` | `ingest`, `ask`, and `eval` commands |

## Quick start

**Requirements:** Python 3.11+

```bash
# 1. Install
git clone <repo-url>
cd rag-citation-agent
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Configure
cp .env.example .env        # then add your LLM API key

# 3. Ingest documents (unchanged files are skipped on re-runs)
python -m rag ingest data/raw

# 4. Ask a question
python -m rag ask "What does the report say about X?"

# 5. Run the evaluation (writes eval/results.md)
python -m rag eval
```

### Configuration

Set these in `.env`:

| Variable | Purpose |
|---|---|
| `LLM_MODEL` | Model used for answer generation |
| `EMBEDDING_MODEL` | Embedding model (default: a local sentence-transformers model) |
| `TOP_K` | Number of chunks to retrieve |
| `MIN_SCORE` | Minimum top similarity score needed to attempt an answer |
| `MAX_RETRIES` | Retries when the model returns invalid structured output |

## How grounding works

1. **Retrieval gate.** Before calling the LLM, the top similarity score is checked. If it's below `MIN_SCORE`, the agent abstains without generating anything. `MIN_SCORE` is tuned on a dev set, not guessed.
2. **Context-only generation.** The prompt tells the model to answer only from the provided chunks, to quote the supporting text for each claim with its chunk id, and to return `abstained` if the context isn't enough.
3. **Citation verification (deterministic, no LLM).** For each citation, the `chunk_id` must be one of the retrieved chunks, and the `quote` must appear in that chunk's text (after normalizing whitespace and case). Claims with failed citations are dropped:
   - all claims pass → `answered`
   - some pass → `partial`
   - none pass → `abstained`
4. **Final confidence.** A combination of the retrieval score, the fraction of claims that passed verification, and the model's self-reported confidence.

Every response is validated against this schema:

```python
class RAGAnswer(BaseModel):
    status: Literal["answered", "partial", "abstained"]
    answer: str
    claims: list[Claim]          # each claim has one or more citations
    confidence: float            # 0 to 1
    reason: str | None           # required when partial or abstained
```

### Example: a caught fake citation

*(To be added: a real example from the logs where the model cited a quote that does not exist in the chunk, and the verifier removed the claim.)*

## Evaluation

The question set has 30-40 hand-written questions in four groups:

| Group | Count | Purpose |
|---|---|---|
| Answerable, single-source | 12-15 | Basic correctness and citation accuracy |
| Answerable, multi-source | 5-8 | Needs information from 2+ chunks or documents |
| Unanswerable | 8-10 | Tests abstention, the main hallucination check |
| Tricky / adversarial | 5 | Near-miss topics and false premises |

### Results

*(Filled in from `eval/results.md`. Only measured numbers are reported.)*

| Metric | Baseline (no retrieval) | Naive RAG | Full system |
|---|---|---|---|
| Retrieval hit rate @k | n/a | – | – |
| Answer correctness | – | – | – |
| Citation validity | n/a | – | – |
| Citation precision | n/a | – | – |
| Abstention accuracy | – | – | – |
| False abstention rate | – | – | – |
| Hallucination rate | – | – | – |

**Grading method:** *(state whether correctness was graded manually or by an LLM judge, the rubric, and the agreement rate from manual spot checks)*

**Ablation:** *(chunk size or top-k comparison)*

## Design decisions

| Decision | Choice | Why |
|---|---|---|
| Chunk size | 500-800 tokens, 10-15% overlap | *(justify with ablation result)* |
| Splitting | By paragraph/heading first, then by size | Keeps meaning intact |
| Embeddings | Local sentence-transformers model | Free and runs offline |
| Top-k | 5 | *(justify with 3 vs 5 vs 8 comparison)* |
| Vector store | ChromaDB (persistent, local) | Simple, no infrastructure needed |
| `MIN_SCORE` | *(tuned value)* | Tuned on a dev set |

## Project structure

```
rag-citation-agent/
├── README.md
├── SPEC.md
├── pyproject.toml
├── .env.example
├── data/
│   ├── raw/          # source documents
│   └── chroma/       # vector store (gitignored)
├── src/rag/          # agent source code
├── eval/
│   ├── questions.json
│   └── results.md
└── tests/
```

## Testing

```bash
pytest                # offline unit tests (fake LLM and embeddings)
pytest -m live        # integration test against a real LLM (needs an API key)
```

## Limitations

- Text-based PDFs and Markdown only; scanned documents and images aren't supported.
- The substring check proves a quote exists in the source, not that it actually supports the claim. Citation precision is measured manually on a sample.
- Local ChromaDB, sized for a small corpus, not production scale.
- No memory across sessions.

## Next steps

- Cross-encoder reranking
- Hybrid search (BM25 + vectors)
- Web-search fallback, clearly labeled as not grounded in the corpus
- Streamlit UI that highlights source passages
- FastAPI + Docker deployment
