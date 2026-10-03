"""Pydantic models shared across the pipeline."""

from pydantic import BaseModel


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
