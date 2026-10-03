"""Pydantic models shared across the pipeline."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Chunk(BaseModel):
    """A passage of a source document, with enough metadata to cite it."""

    chunk_id: str
    doc_id: str          # file path relative to the corpus folder
    page: int | None     # 1-based PDF page; None for Markdown
    text: str            # exact slice of the page text
    char_start: int      # offsets of `text` within the page text
    char_end: int


class RetrievedChunk(Chunk):
    """A chunk returned for a question, with its similarity to the question."""

    score: float         # cosine similarity, 1 = identical meaning


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
