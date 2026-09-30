# SPEC: RAG Agent with Citation Grounding (Project 02)

> Goal: prevent hallucinations. Answer questions only from a document corpus, cite the exact source for every claim, and say "I don't know" when the documents don't support an answer.

**Timeline:** 1 weekend (about 12-14 focused hours), built in parallel with Project 01
**Language:** Python 3.11+ | **Core libs:** Pydantic v2, sentence-transformers (or a provider embedding API), ChromaDB, an LLM SDK, pytest
**Depends on:** Project 01 (reuse its `llm.py`, retry controller, and SQLite logger)

---

## 1. Problem statement

A plain LLM does not know your documents and will confidently invent answers. RAG fixes part of this by retrieving relevant text first, but most demos stop there and still hallucinate when retrieval is weak. This agent adds **grounding checks**: every claim must point to a retrieved chunk, citations are verified programmatically, and low-confidence questions trigger a fallback instead of a guess.

## 2. Goals

- G1. Ingest a document corpus into a vector store with traceable chunk metadata.
- G2. Answer questions using only retrieved context.
- G3. Return a structured, Pydantic-validated answer with citations.
- G4. Verify citations programmatically (the quoted text must exist in the cited chunk).
- G5. Detect low-confidence cases and fall back safely.
- G6. Measure grounding quality with a repeatable eval and publish the numbers.

## 3. Non-goals

- No fine-tuning, no agents with many tools, no memory across sessions.
- No multi-modal input (images, tables as images). Text-based PDFs and Markdown only.
- No production-scale vector infrastructure. Local Chroma is fine.
- UI is optional (a small Streamlit app is a stretch goal).

## 4. Corpus (decide first, Saturday morning)

Pick **one** corpus of 10-30 documents on a single topic. Suggested options:

| Option | Why |
|---|---|
| Your college syllabus and lecture notes | Feeds directly into the student chatbot rebuild |
| A public report set (e.g. annual reports, policy documents) | Easy to find, easy to write questions for |
| Technical docs of one open-source tool (e.g. FastAPI docs) | Clear right answers, easy to verify |

Requirements: text-extractable (not scanned images), factual enough that answers can be checked, and large enough that retrieval is not trivial (at least 100 pages total).

## 5. Architecture

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
                                       parse + validate (Pydantic, retry from Project 01)
                                                        │
                                                        ▼
                                          citation verifier (substring check)
                                                        │
                                                        ▼
                                      final answer / partial answer / abstain
```

| Component | Responsibility |
|---|---|
| `ingest.py` | Load PDFs/Markdown, chunk, embed, store with metadata |
| `retriever.py` | Embed query, top-k search, return chunks with scores |
| `gate.py` | Decide whether retrieval is strong enough to attempt an answer |
| `generator.py` | Build the context-only prompt, call the LLM, validate output |
| `verifier.py` | Check each citation's quote appears in the cited chunk |
| `fallback.py` | Abstain message, and optional web search (stretch) |
| `schemas.py` | Pydantic models (imports patterns from Project 01) |
| `logger.py` | SQLite logging of queries, retrievals, decisions |
| `cli.py` | `ingest`, `ask`, `eval` commands |

## 6. Design decisions to make and document

| Decision | Starting point | Notes |
|---|---|---|
| Chunk size | 500-800 tokens, 10-15% overlap | Try one alternative in the eval to justify your choice |
| Splitting | By paragraph/heading first, then by size | Keeps meaning intact |
| Embeddings | `bge-small` or `all-MiniLM-L6-v2` (local, free) | Or a provider embedding API |
| Top-k | 5 | Test 3 vs 5 vs 8 in the eval |
| Vector store | ChromaDB (persistent local) | FAISS is an alternative |
| Reranking | None at first | Stretch: cross-encoder reranker |

## 7. Data schemas

```python
from pydantic import BaseModel, Field, model_validator
from typing import Literal

class Citation(BaseModel):
    chunk_id: str
    doc_id: str
    page: int | None = None
    quote: str = Field(min_length=10)   # exact text from the chunk supporting the claim

class Claim(BaseModel):
    text: str
    citations: list[Citation] = Field(min_length=1)

class RAGAnswer(BaseModel):
    status: Literal["answered", "partial", "abstained"]
    answer: str
    claims: list[Claim] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    reason: str | None = None           # required when abstained or partial

    @model_validator(mode="after")
    def check_consistency(self):
        if self.status == "answered" and not self.claims:
            raise ValueError("answered status requires at least one cited claim")
        if self.status != "answered" and not self.reason:
            raise ValueError("partial/abstained requires a reason")
        return self
```

## 8. Grounding and confidence logic (the core of this project)

**Step 1: Retrieval gate (before calling the LLM)**
- Compute the top similarity score and the score gap between top-1 and top-k.
- If top score is below `MIN_SCORE`, skip generation and go to fallback.
- Tune `MIN_SCORE` on a small dev set, not by guessing.

**Step 2: Context-only generation**
- Prompt rule: answer only from the provided chunks; each claim must quote the supporting text and give the chunk id; if the context is insufficient, return `abstained`.

**Step 3: Citation verification (deterministic, no LLM needed)**
- For each citation: `chunk_id` must be among the retrieved chunks, and `quote` must appear in that chunk's text (normalize whitespace and case before comparing).
- Claims whose citations fail are removed. If no claims survive, status becomes `abstained`. If some survive, status becomes `partial`.

**Step 4: Final confidence**
- Combine: retrieval score, fraction of claims that passed verification, and the model's self-reported confidence. Document your formula and why.

**Step 5: Fallback options**
- Default: abstain with a clear message ("The provided documents do not contain this information").
- Stretch: web search fallback, clearly labeled as external and not grounded in the corpus.

## 9. Functional requirements

- **FR1.** `python -m rag ingest <folder>` builds or updates the vector store, skipping unchanged files.
- **FR2.** `python -m rag ask "question"` prints the answer, status, confidence, and citations with doc and page.
- **FR3.** Every returned answer conforms to `RAGAnswer`; invalid model output goes through the Project 01 retry loop.
- **FR4.** Citation verification runs on every answered response.
- **FR5.** Each query is logged: question, retrieved chunk ids and scores, gate decision, final status, latency, tokens.
- **FR6.** Config via environment variables: model, embedding model, `TOP_K`, `MIN_SCORE`, `MAX_RETRIES`.
- **FR7.** `python -m rag eval` runs the full evaluation and writes `eval/results.md`.

## 10. Evaluation plan (this is what makes it a resume project)

**Question set: 30-40 questions, hand-written, in four groups**

| Group | Count | Purpose |
|---|---|---|
| Answerable, single-source | 12-15 | Basic correctness and citation accuracy |
| Answerable, multi-source | 5-8 | Needs info from 2+ chunks or docs |
| Unanswerable (not in corpus) | 8-10 | Tests abstention, the key hallucination check |
| Tricky/adversarial | 5 | Near-miss topics, questions with false premises |

For each answerable question, store the expected answer (short) and the expected source doc/page.

**Metrics**

| Metric | How measured |
|---|---|
| Retrieval hit rate @k | Expected source chunk appears in top-k |
| Answer correctness | Manual grading on a subset (at least 20), or LLM-as-judge with a stated rubric and spot-checked by you |
| Citation validity | % of citations passing the substring check |
| Citation precision | % of citations that truly support the claim (manual on a sample) |
| Abstention accuracy | On unanswerable questions, % correctly abstained |
| False abstention rate | On answerable questions, % wrongly abstained |
| Hallucination rate | % of answers containing unsupported claims |

**Comparisons to report**
1. **Baseline:** plain LLM, no retrieval.
2. **Naive RAG:** retrieval, no verification, no gate.
3. **Full system:** gate + verification + fallback.
4. One ablation: chunk size or top-k.

Headline result to aim for: "Hallucination rate on unanswerable questions dropped from X% (naive RAG) to Y% (full system), with false-abstention of Z%."

## 11. Testing

Unit tests (no network, fake LLM and fake embeddings where possible):
- chunker respects size and overlap, and preserves metadata
- verifier accepts a real quote, rejects a fabricated one, and handles whitespace differences
- gate abstains below `MIN_SCORE`
- status logic: all pass gives `answered`, some fail gives `partial`, all fail gives `abstained`
- schema validators reject inconsistent answers

One integration test marked `@pytest.mark.live`, skipped by default.

## 12. Repo structure

```
rag-citation-agent/
├── README.md
├── SPEC.md
├── pyproject.toml
├── .env.example
├── data/
│   ├── raw/                 # source documents (or a download script)
│   └── chroma/              # vector store (gitignored)
├── src/rag/
│   ├── __init__.py
│   ├── ingest.py
│   ├── retriever.py
│   ├── gate.py
│   ├── generator.py
│   ├── verifier.py
│   ├── fallback.py
│   ├── schemas.py
│   ├── logger.py
│   └── cli.py
├── eval/
│   ├── questions.json
│   └── results.md
└── tests/
```

## 13. Weekend schedule (running in parallel with Project 01)

Because you are also finishing Project 01, treat that project as "maintenance mode" on the weekend: reuse its code, and only touch it for the eval and README.

**Friday evening (optional, 1 hour)**
- Choose the corpus, download it, create the repo, and start writing eval questions while it's fresh.

**Saturday**
| Time | Task | Done when |
|---|---|---|
| Morning (3h) | Corpus loading, chunking, embeddings, Chroma ingest | `ingest` runs; you can query chunks by hand |
| Afternoon (3h) | Retriever + generator with context-only prompt, `RAGAnswer` schema, reuse the retry loop from 01 | `ask` returns a validated cited answer |
| Evening (1h) | Write remaining eval questions and expected answers | 30+ questions saved |

**Sunday**
| Time | Task | Done when |
|---|---|---|
| Morning (3h) | Citation verifier, gate, abstain/partial logic, logging | Fake citations are caught; unanswerable questions abstain |
| Midday (2h) | Eval harness and first full run (baseline, naive, full) | `eval/results.md` generated |
| Afternoon (2h) | README, architecture diagram, results table, push to GitHub | A stranger can run it |
| Evening (1h) | Buffer, or return to Project 01's eval and README | Both repos pushed |

**If you run short on time, cut in this order:** UI, web-search fallback, reranking, ablation study. **Never cut:** the verifier, the unanswerable questions, or the eval.

## 14. Acceptance criteria

- [ ] Every answered response has at least one citation, and all citations pass verification.
- [ ] The system abstains on out-of-corpus questions, measured on at least 8 unanswerable questions.
- [ ] Eval compares baseline, naive RAG, and the full system on 30+ questions.
- [ ] Hallucination and abstention rates are reported with the method used to grade.
- [ ] Unit tests pass offline.
- [ ] README includes problem, architecture diagram, quick start, results table, limitations.
- [ ] No API keys committed; raw data license checked.

## 15. Stretch goals

- Cross-encoder reranking and its effect on hit rate.
- Hybrid search (BM25 + vectors).
- Web-search fallback clearly labeled as ungrounded.
- Streamlit UI showing the answer with highlighted source passages.
- Reuse for your student chatbot: swap the corpus for your syllabus and call it the "cited course assistant."
- Deploy the API (FastAPI + Docker) for a live demo link.

## 16. README outline

1. One-line pitch plus the headline metric
2. Architecture diagram (ingest and query flows)
3. Quick start (install, ingest, ask)
4. How grounding works (gate, verifier, abstain), with one example of a caught fake citation
5. Evaluation results table and method
6. Design decisions (chunk size, top-k, thresholds) and why
7. Limitations and next steps

## 17. Resume bullet template

> **Cited RAG Agent** | Python, ChromaDB, Pydantic, [LLM API] | [GitHub] | [demo]
> - Built a retrieval-augmented QA system with programmatic citation verification and confidence-gated abstention over [N] documents ([M] pages).
> - Reduced hallucination on out-of-corpus questions from [X]% to [Y]% versus naive RAG; [Z]% of citations verified against source text.
> - Evaluated on [N] hand-labeled questions across answerable, multi-source, unanswerable, and adversarial categories.

Fill in real measured numbers only.

## 18. Risks

| Risk | Mitigation |
|---|---|
| Corpus too easy, so results look perfect | Include multi-source and adversarial questions |
| Weekend runs out before the eval | Write questions Saturday evening; protect Sunday midday |
| LLM-as-judge is unreliable | Manually check a sample and report agreement |
| Scanned or messy PDFs break extraction | Test loading on all documents Saturday morning; drop bad ones |
| Two projects at once cause context switching | Only touch Project 01 for its eval and README |
