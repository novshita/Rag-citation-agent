# RAG Citation Agent

Ask questions about a set of documents and get answers that are **backed by quotes from those documents**, or an honest "I don't know" when the answer isn't there.

> **Headline result:** Hallucination on out-of-corpus questions dropped from **X%** (naive RAG) to **Y%**, with only **Z%** of answerable questions wrongly refused.
> *(Filled in once the evaluation runs.)*

> **Status:** Work in progress.

---

## The problem

AI chatbots are confident even when they're wrong. Ask one about your documents and it may invent an answer that sounds right. Giving the model relevant passages first (retrieval-augmented generation, or RAG) helps, but it still makes things up when the passages don't contain the answer.

## What this project does differently

- **Every claim comes with a quote.** The answer points to the exact passage, document and page it came from.
- **Quotes are checked in code.** If the model cites text that isn't actually in the source, that claim is removed. No second AI is asked to judge.
- **It knows when to stay quiet.** If the documents don't cover the question, it says so instead of guessing.

## Example

*(Illustrative. Real output will be added once the agent is built.)*

```
$ python -m rag ask "When was the policy last updated?"

Answer:     The policy was last updated in March 2024.
Status:     answered
Confidence: 0.87

Sources:
  [1] policy_handbook.pdf, page 3
      "This policy was last revised in March 2024"
```

For a question the documents don't cover:

```
$ python -m rag ask "What is the CEO's favourite colour?"

Status: abstained
The provided documents do not contain this information.
```

## How it works

```
Your documents ──► split into passages ──► stored in a searchable index

Your question ──► find the most relevant passages
                     │
                     ├─ not relevant enough? ──► "I don't know"
                     │
                     ▼
              AI writes an answer using only those passages, quoting each one
                     │
                     ▼
              every quote is checked against the original text
                     │
                     ▼
              answer (with sources), partial answer, or "I don't know"
```

For the full design, including components, schemas, thresholds and the evaluation method, see [SPEC.md](SPEC.md).

## Quick start

**Requirements:** Python 3.11+ and an LLM API key.

```bash
git clone https://github.com/novshita/rag-citation-agent.git
cd rag-citation-agent
python -m venv .venv && source .venv/bin/activate
pip install -e .

cp .env.example .env              # add your API key here

python -m rag ingest data/raw     # index your documents
python -m rag ask "your question" # ask a question
python -m rag eval                # run the evaluation
```

## Results

The system is tested on 30+ hand-written questions, including questions the documents *can't* answer, to see whether it refuses correctly or makes something up. It's compared against a plain chatbot and a basic RAG setup.

*(Measured numbers will be added here.)*

| | Plain LLM | Basic RAG | This project |
|---|---|---|---|
| Correct answers | – | – | – |
| Hallucination rate | – | – | – |
| Correctly says "I don't know" | – | – | – |
| Citations verified | n/a | – | – |

## Limitations

- Works with text-based PDFs and Markdown only, not scanned documents or images.
- The quote check confirms the text exists in the source, but not that it fully supports the claim.
- Built for small document sets (tens of documents), not large-scale search.

## Built with

Python · ChromaDB · Pydantic · sentence-transformers · pytest
