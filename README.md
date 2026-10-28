# RAG Citation Agent

Ask questions about a set of documents and get answers that are **backed by quotes from those documents**, or an honest "I don't know" when the answer isn't there.

> **Headline result:** Hallucination on out-of-corpus questions dropped from **X%** (naive RAG) to **Y%**, with only **Z%** of answerable questions wrongly refused.
> *(Placeholders until the evaluation has been run. Real numbers only; see [Results](#results).)*

---

## The problem

AI chatbots are confident even when they're wrong. Ask one about your documents and it may invent an answer that sounds right. Giving the model relevant passages first (retrieval-augmented generation, or RAG) helps, but it still makes things up when the passages don't contain the answer.

## What this project does differently

- **Every claim comes with a quote.** The answer points to the exact passage, document and page it came from.
- **Quotes are checked in code.** If the model cites text that isn't actually in the source, that claim is removed. No second AI is asked to judge.
- **It knows when to stay quiet.** If the documents don't cover the question, it says so instead of guessing.

## Example

Real output, from the FastAPI documentation corpus used in the evaluation:

```
$ python -m rag ask "When do background tasks run, and can the task function be async?"

Background tasks run after returning a response. The task function can be either an async def or a normal def function.

status:     answered
confidence: 0.89

[1] Background tasks can be defined to run after returning a response.
    - tutorial/background-tasks.md: "You can define background tasks to be run *after* returning a response."

[2] The task function can be an async def or normal def function.
    - tutorial/background-tasks.md: "It can be an `async def` or normal `def` function, **FastAPI** will know how to handle it correctly."
```

For a question the documents don't cover (the docs mention SQLModel and Alembic, but nothing about Django):

```
$ python -m rag ask "How do I configure Django migrations?"

The provided documents do not contain this information.

status:     abstained
confidence: 0.00
reason:     The provided context does not contain any information about configuring Django migrations; it only mentions Alembic and SQLModel migration utilities.
```

### Catching a made-up citation

The answer model is asked to quote its sources word for word. The verifier then looks for each quote in the passage it cites. Using the example above, if the model had written `"Background tasks always run before the response is sent"` as its quote, that text is not in the passage, so:

- the claim is **removed** from the answer;
- if some claims survive, the status becomes `partial` and the reason says how many were removed;
- if none survive, the status becomes `abstained`.

This behaviour is covered by the unit tests in [tests/test_verifier.py](tests/test_verifier.py) and [tests/test_generator.py](tests/test_generator.py), which use a fabricated quote on purpose.

## How it works

```
INGEST (once)
Your documents ──► split into passages ──► embedded ──► stored in a local index
                   (keeps document, page, position for every passage)

QUERY
Your question ──► find the most relevant passages
                     │
                     ├─ best match too weak? ──► "I don't know" (no AI call)
                     │
                     ▼
              AI writes an answer using only those passages, quoting each one
              (invalid output is sent back to the model to fix, up to MAX_RETRIES times)
                     │
                     ▼
              every quote is checked against the original passage
                     │
                     ▼
              answer (with sources), partial answer, or "I don't know"
              + a confidence score, and a row in the query log
```

| Step | Where | What it does |
|---|---|---|
| Ingest | [ingest.py](src/rag/ingest.py) | Loads PDF/Markdown, splits into passages, embeds, stores. Skips unchanged files |
| Retrieve | [retriever.py](src/rag/retriever.py) | Embeds the question, returns the top-k passages with similarity scores |
| Gate | [gate.py](src/rag/gate.py) | If the best score is below `MIN_SCORE`, abstain without calling the model |
| Generate | [generator.py](src/rag/generator.py) | Context-only prompt, validates the reply against the answer schema, retries on bad output |
| Verify | [verifier.py](src/rag/verifier.py) | Quote must appear in the cited passage (ignoring case, whitespace, curly quotes, PDF ligatures) |
| Confidence | [confidence.py](src/rag/confidence.py) | Combines retrieval score, share of claims that verified, and the model's own estimate |
| Log | [logger.py](src/rag/logger.py) | One SQLite row per query: passages and scores, gate decision, status, tokens, latency |
| Evaluate | [evaluate.py](src/rag/evaluate.py) | Runs the question set through three systems and writes the comparison |

For the full design, including schemas, thresholds and the evaluation method, see [SPEC.md](SPEC.md).

## Quick start

**Requirements:** Python 3.11+ and an API key for one LLM provider. Google Gemini has a free tier; Anthropic is paid.

```bash
git clone https://github.com/novshita/rag-citation-agent.git
cd rag-citation-agent
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env     # then edit .env, see below
```

In `.env`, set the provider, the model id, and the matching key (keep real keys in `.env` only; it is git-ignored):

```
LLM_PROVIDER=gemini            # or anthropic
LLM_MODEL=<a model id from your provider>
GEMINI_API_KEY=<your key>      # or ANTHROPIC_API_KEY
```

Then get the example corpus (30 pages of the FastAPI docs), index it, and ask:

```bash
./scripts/download_corpus.sh                       # or put your own PDFs/Markdown in data/raw
python -m rag ingest data/raw                      # index the documents
python -m rag search "how do background tasks work?"   # see what gets retrieved (no LLM call)
python -m rag ask "how do background tasks work?"      # get a cited answer
```

Evaluation and tuning:

```bash
python -m rag tune     # suggest MIN_SCORE from the dev questions (no LLM calls)
python -m rag eval     # baseline vs naive RAG vs full system -> eval/results.md
python -m rag ablate --top-k 3,5,8    # compare settings -> eval/ablation.md
python -m rag ablate --retrieval-only --rerank   # hit rate with/without reranking, no LLM calls
pytest                 # offline unit tests
pytest -m live         # end-to-end test with the real model (costs a few API calls)
```

## The example corpus

30 pages of the [FastAPI documentation](https://github.com/fastapi/fastapi) (tutorial, advanced and deployment sections), about 49,000 words. The documentation is MIT licensed; the licence text is kept in `data/raw/LICENSE-FastAPI.txt`. [scripts/download_corpus.sh](scripts/download_corpus.sh) rebuilds it from a pinned commit so results are reproducible.

## Results

The system is tested on 30 hand-written questions (8 more are kept aside to tune the threshold), covering questions answerable from one page, from several pages, questions the documents *can't* answer, and trick questions (false premises and near-misses). It is compared against a plain chatbot and a basic RAG setup. The questions are in [eval/questions.json](eval/questions.json).

**Results pending.** The table is filled in from `eval/results.md` after the run.

| | Plain LLM | Basic RAG | This project |
|---|---|---|---|
| Retrieval hit rate | n/a | – | – |
| Correct answers (answerable) | – | – | – |
| Citations verified | n/a | – | – |
| Hallucination rate (unanswerable) | – | – | – |
| Correctly says "I don't know" | – | – | – |
| Wrongly refuses (answerable) | – | – | – |

**How it was graded**
- Retrieval hit, abstention and citation validity are computed by code.
- Answer correctness is graded by an LLM against the hand-written expected answer. It is not perfect, so a sample is checked by hand and the per-question table in `eval/results.md` shows every grade.
- "Hallucination rate" is the share of unanswerable questions where the system gave an answer instead of declining.
- Questions for tuning (`dev`) are kept separate from the ones reported (`test`), so the threshold isn't tuned on the questions it's scored on.

## Design decisions

| Decision | Choice | Why |
|---|---|---|
| Passage size | 150 words, 20 overlap | The embedding model reads at most 256 tokens; this keeps each passage within it |
| Embeddings | `all-MiniLM-L6-v2` (local) | Free and fast; no data leaves the machine for retrieval |
| Top-k | 5 | Ablation over 3, 5 and 8 is available via `python -m rag ablate` |
| Vector store | ChromaDB, local | Enough for tens of documents |
| Reranking | Optional cross-encoder (`RERANK=true`), off by default | Rescores a wider candidate set and keeps the best top-k. On the 22 answerable test questions it changed retrieval hit rate by at most one question (see [eval/retrieval_ablation.md](eval/retrieval_ablation.md)), so it is not worth the extra model by default |
| `MIN_SCORE` | Tuned with `python -m rag tune` | On the 8 dev questions the answerable and unanswerable scores overlapped (answerable from 0.45, unanswerable up to 0.63), so the gate alone can't catch every out-of-corpus question. It is a cheap first filter; the model's own abstention and the verifier do the rest |
| Confidence | `claim_pass_rate × (0.3 × retrieval + 0.7 × model confidence)` | A failed citation should pull confidence down however sure the model sounded, so it is a multiplier. The weights are a starting point |
| Claim removal | A claim survives only if all its citations verify | One fabricated quote is enough to distrust the claim |

## Limitations

- Works with text-based PDFs and Markdown only, not scanned documents or images.
- The quote check confirms the text exists in the cited passage, but not that it fully supports the claim.
- The FastAPI docs pull their code samples in from separate files that aren't part of the corpus, so questions about exact code can't be answered from it.
- The answer-correctness grade comes from an LLM judge, which can be wrong; only a sample is checked by hand.
- The question set is small (30 test, 8 dev), so single questions move the percentages noticeably.
- The retrieval gate can't separate on-topic from off-topic questions that share vocabulary with the corpus (for example any question mentioning "FastAPI" or "deploy").
- Built for small document sets (tens of documents), not large-scale search.

## Built with

Python · ChromaDB · Pydantic · sentence-transformers · Google Gemini / Anthropic Claude · pytest
