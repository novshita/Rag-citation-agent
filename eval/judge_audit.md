# Judge audit

The evaluation uses an LLM to grade answers (correct or not, and whether the plain-LLM baseline declined to answer). This file records a check of those grades against the hand-written expected answers.

**Who checked:** Claude (the AI assistant that helped build this project), reading each answer against the expected answer in `eval/questions.json`. This is *not* a labelling by the project's author. The author should spot-check the same items before relying on the numbers.

**Run audited:** the final run, `MIN_SCORE=0.42`, 30 test questions, model `gemini-3.5-flash-lite` (see `eval/results.md`).

## What was checked

| Set | Items | Judge and audit agree | Notes |
|---|---|---|---|
| Full system, answerable questions answered (judged correct) | 20 | 18 | 2 borderline, see below |
| Baseline answers the judge marked incorrect | 2 | 2 | `s10`, `a01` |
| Baseline answers to unanswerable questions (judge: did not decline) | 8 | 8 | none declined |
| **Total** | **30** | **28** | 2 borderline, 0 clear disagreements |

Not audited: the naive-RAG answers, and the baseline answers judged correct. The two systems' headline numbers rest partly on those grades, so treat them with the same caution.

## Borderline items (judge said correct; the answer is incomplete)

| Question | Expected | What the system said | Why borderline |
|---|---|---|---|
| `m02` Proxy and forwarded headers | The proxy adds `X-Forwarded-*` headers; the server only trusts them if started with `--forwarded-allow-ips` | Names `X-Forwarded-Proto` and `-Host`, and says the server interprets them "if it is configured to trust them" | Right idea, but leaves out the option name and `X-Forwarded-For` |
| `m04` Migrations with several containers | Run them once, in a single separate container before the replicated containers, so processes don't duplicate the work or conflict | Names the Kubernetes Init Container and the case where running steps in parallel is harmless, then says the context has no more detail | Misses the key reason (run once, avoid conflicts) |

If these two were counted as incorrect, the full system's correctness would be 18 of 22 (82%) instead of 20 of 22 (91%). The judge is therefore somewhat lenient on multi-part answers.

## Other observations

- **Baseline on unanswerable questions.** The plain LLM answered all 8 confidently from general knowledge. One answer (`u08`, request timeouts) names `starlette.middleware.timeout.TimeoutMiddleware`; I could not find a class by that name in Starlette, so it may be invented. Treat this as unverified until checked against Starlette's documentation.
- **Baseline on false premises.** On `a01` the baseline went along with the false premise ("the documentation recommends returning or raising an HTTPException"), and the judge correctly marked it wrong.
- **The two "hallucinations" of the RAG systems** (`u05` AWS Lambda, `u10` Celery) are hedged answers: the reply says the documents don't cover the topic, then adds a related fact that is in the documents and cited. They are counted as answers (the conservative reading), but they contain no unsupported claim.
