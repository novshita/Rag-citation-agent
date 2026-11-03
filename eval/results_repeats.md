# Evaluation results: repeated runs

3 independent runs of the same 30 questions: 12 single, 7 multi, 6 unanswerable, 5 adversarial.
Settings: model gemini-3.5-flash-lite, embeddings all-MiniLM-L6-v2, top_k 5, min_score 0.42, chunk size 150/20, reranker off, hybrid off.

Each cell is the average over runs, then each run's value in brackets.

| Metric | baseline | naive | full |
|---|---|---|---|
| Retrieval hit rate (answerable) | n/a | 91% (91% / 91% / 91%) | 91% (91% / 91% / 91%) |
| Answer correctness (answerable) | 86% (86% / 86% / 86%) | 95% (95% / 95% / 95%) | 89% (91% / 86% / 91%) |
| Citation validity | n/a | 99% (98% / 100% / 100%) | 99% (100% / 100% / 98%) |
| Abstention accuracy (unanswerable) | 0% (0% / 0% / 0%) | 75% (75% / 75% / 75%) | 75% (75% / 75% / 75%) |
| False abstention rate (answerable) | 3% (5% / 5% / 0%) | 5% (5% / 5% / 5%) | 9% (9% / 9% / 9%) |
| Hallucination rate (unanswerable) | 100% (100% / 100% / 100%) | 25% (25% / 25% / 25%) | 25% (25% / 25% / 25%) |
| Answers with an unsupported claim | n/a | 1% (4% / 0% / 0%) | 0% (0% / 0% / 0%) |
| Avg latency (ms) | 5491 | 4681 | 7023 |

## How to read this

- A gap between two systems that is smaller than the spread between runs of the same system is not evidence that one is better.
- Grading is as described in `eval/results.md` (code for abstention, hits and citations; an LLM judge for correctness).
