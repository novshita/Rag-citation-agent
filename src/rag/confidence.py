"""Final confidence of an answer, combining three signals.

    confidence = claim_pass_rate * (0.3 * retrieval_score + 0.7 * model_confidence)

- claim_pass_rate (fraction of claims whose citations verified) is a multiplier, not a
  weighted term: a fabricated citation is hard evidence of a problem, so it should pull
  confidence down no matter how sure the model sounded.
- retrieval_score (top cosine similarity) says whether the documents were on topic.
- model_confidence is the model's self-report. It is the least trustworthy signal
  (models tend to be overconfident), but the only one that sees the answer text, so it
  gets the largest weight inside the bracket, not the whole say.

Abstained answers get 0.0: there is no answer to be confident in.

The 0.3 / 0.7 weights are a starting point. Check calibration in the eval (are
high-confidence answers actually correct more often?) before trusting them.
"""

from rag.schemas import RAGAnswer

RETRIEVAL_WEIGHT = 0.3
MODEL_WEIGHT = 0.7


def final_confidence(
    answer: RAGAnswer,
    top_score: float | None,
    claim_pass_rate: float,
    model_confidence: float,
) -> float:
    if answer.status == "abstained" or top_score is None:
        return 0.0
    retrieval = min(max(top_score, 0.0), 1.0)
    blended = RETRIEVAL_WEIGHT * retrieval + MODEL_WEIGHT * model_confidence
    return round(claim_pass_rate * blended, 4)
