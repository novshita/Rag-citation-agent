"""Settings loaded from environment variables (and .env, if present)."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    llm_model: str
    embedding_model: str
    top_k: int
    min_score: float
    max_retries: int
    chunk_size: int
    chunk_overlap: int
    chroma_dir: str
    collection: str


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        llm_model=os.getenv("LLM_MODEL", ""),
        embedding_model=os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
        top_k=int(os.getenv("TOP_K", "5")),
        min_score=float(os.getenv("MIN_SCORE", "0.3")),
        max_retries=int(os.getenv("MAX_RETRIES", "2")),
        chunk_size=int(os.getenv("CHUNK_SIZE", "150")),
        chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "20")),
        chroma_dir=os.getenv("CHROMA_DIR", "data/chroma"),
        collection=os.getenv("CHROMA_COLLECTION", "corpus"),
    )
