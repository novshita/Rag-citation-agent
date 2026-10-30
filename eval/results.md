# Evaluation results

30 questions: 12 single, 7 multi, 6 unanswerable, 5 adversarial.
Settings: model gemini-3.5-flash-lite, embeddings all-MiniLM-L6-v2, top_k 5, min_score 0.42, chunk size 150/20, reranker off.

## Comparison

| Metric | baseline | naive | full |
|---|---|---|---|
| Retrieval hit rate (answerable) | n/a | 91% | 91% |
| Answer correctness (answerable) | 82% | 95% | 82% |
| Citation validity | n/a | 98% | 93% |
| Abstention accuracy (unanswerable) | 0% | 75% | 75% |
| False abstention rate (answerable) | 5% | 5% | 18% |
| Hallucination rate (unanswerable) | 100% | 25% | 25% |
| Answers with an unsupported claim | n/a | 4% | 0% |
| Avg latency (ms) | 5194 | 3047 | 3050 |
| Avg tokens per question | 202 | 1990 | 1841 |

## Method

- Abstention, retrieval hit and citation validity are computed by code. A citation is valid when its chunk was retrieved and its quote appears in that chunk (whitespace and case ignored).
- Correctness is graded by an LLM judge against the hand-written expected answer; abstaining on an answerable question counts as incorrect. Spot-check the table below.
- Hallucination rate (unanswerable) = share of unanswerable questions where the system answered instead of abstaining.
- The baseline has no retrieval, so hit rate and citation validity do not apply. Whether it declined is decided by the judge.
- `naive` is graded as the model wrote it (citations are checked but nothing is removed), so its unsupported claims are visible; `full` removes them before answering.

## Per question

| id | group | system | abstained | hit | correct | citations valid |
|---|---|---|---|---|---|---|
| s01 | single | baseline | no | - | yes | - |
| s01 | single | naive | no | yes | yes | 1/1 |
| s01 | single | full | no | yes | yes | 2/2 |
| s03 | single | baseline | no | - | yes | - |
| s03 | single | naive | no | yes | yes | 2/2 |
| s03 | single | full | no | yes | yes | 1/2 |
| s04 | single | baseline | no | - | yes | - |
| s04 | single | naive | no | yes | yes | 1/1 |
| s04 | single | full | no | yes | yes | 2/2 |
| s05 | single | baseline | no | - | yes | - |
| s05 | single | naive | no | yes | yes | 0/1 |
| s05 | single | full | yes | yes | - | 0/1 |
| s07 | single | baseline | no | - | yes | - |
| s07 | single | naive | no | yes | yes | 3/3 |
| s07 | single | full | no | yes | yes | 2/2 |
| s08 | single | baseline | no | - | yes | - |
| s08 | single | naive | no | yes | yes | 4/4 |
| s08 | single | full | no | yes | yes | 4/4 |
| s09 | single | baseline | no | - | yes | - |
| s09 | single | naive | no | yes | yes | 1/1 |
| s09 | single | full | no | yes | yes | 1/1 |
| s10 | single | baseline | no | - | no | - |
| s10 | single | naive | no | yes | yes | 1/1 |
| s10 | single | full | no | yes | yes | 1/1 |
| s11 | single | baseline | no | - | yes | - |
| s11 | single | naive | no | yes | yes | 1/1 |
| s11 | single | full | no | yes | yes | 1/1 |
| s12 | single | baseline | no | - | yes | - |
| s12 | single | naive | no | yes | yes | 2/2 |
| s12 | single | full | yes | yes | - | - |
| s14 | single | baseline | no | - | yes | - |
| s14 | single | naive | no | yes | yes | 2/2 |
| s14 | single | full | no | yes | yes | 3/3 |
| s15 | single | baseline | no | - | yes | - |
| s15 | single | naive | no | yes | yes | 2/2 |
| s15 | single | full | no | yes | yes | 1/1 |
| m01 | multi | baseline | no | - | yes | - |
| m01 | multi | naive | yes | no | - | - |
| m01 | multi | full | yes | no | - | - |
| m02 | multi | baseline | no | - | yes | - |
| m02 | multi | naive | no | yes | yes | 3/3 |
| m02 | multi | full | no | yes | yes | 3/3 |
| m04 | multi | baseline | no | - | yes | - |
| m04 | multi | naive | no | yes | yes | 2/2 |
| m04 | multi | full | no | yes | yes | 3/3 |
| m05 | multi | baseline | no | - | no | - |
| m05 | multi | naive | no | yes | yes | 2/2 |
| m05 | multi | full | no | yes | yes | 2/2 |
| m06 | multi | baseline | no | - | yes | - |
| m06 | multi | naive | no | yes | yes | 3/3 |
| m06 | multi | full | no | yes | yes | 3/3 |
| m07 | multi | baseline | yes | - | - | - |
| m07 | multi | naive | no | no | yes | 2/2 |
| m07 | multi | full | no | no | yes | 2/2 |
| m08 | multi | baseline | no | - | yes | - |
| m08 | multi | naive | no | yes | yes | 2/2 |
| m08 | multi | full | no | yes | yes | 2/2 |
| u05 | unanswerable | baseline | no | - | no | - |
| u05 | unanswerable | naive | no | - | - | 1/1 |
| u05 | unanswerable | full | no | - | - | 2/2 |
| u06 | unanswerable | baseline | no | - | - | - |
| u06 | unanswerable | naive | yes | - | - | - |
| u06 | unanswerable | full | yes | - | - | - |
| u07 | unanswerable | baseline | no | - | - | - |
| u07 | unanswerable | naive | yes | - | - | - |
| u07 | unanswerable | full | yes | - | - | - |
| u08 | unanswerable | baseline | no | - | yes | - |
| u08 | unanswerable | naive | yes | - | - | - |
| u08 | unanswerable | full | yes | - | - | - |
| u09 | unanswerable | baseline | no | - | no | - |
| u09 | unanswerable | naive | yes | - | - | - |
| u09 | unanswerable | full | yes | - | - | - |
| u10 | unanswerable | baseline | no | - | - | - |
| u10 | unanswerable | naive | no | - | - | 2/2 |
| u10 | unanswerable | full | no | - | - | 2/2 |
| a01 | adversarial | baseline | no | - | no | - |
| a01 | adversarial | naive | no | yes | yes | 1/1 |
| a01 | adversarial | full | yes | yes | - | 0/1 |
| a02 | adversarial | baseline | no | - | yes | - |
| a02 | adversarial | naive | no | yes | yes | 1/1 |
| a02 | adversarial | full | no | yes | yes | 1/1 |
| a03 | adversarial | baseline | no | - | yes | - |
| a03 | adversarial | naive | no | yes | yes | 3/3 |
| a03 | adversarial | full | no | yes | yes | 5/5 |
| a04 | adversarial | baseline | no | - | yes | - |
| a04 | adversarial | naive | yes | - | - | - |
| a04 | adversarial | full | yes | - | - | - |
| a05 | adversarial | baseline | no | - | yes | - |
| a05 | adversarial | naive | yes | - | - | - |
| a05 | adversarial | full | yes | - | - | - |
