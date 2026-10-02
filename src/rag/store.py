"""Access to the persistent Chroma vector store."""

import chromadb
from chromadb.api.models.Collection import Collection


def get_collection(chroma_dir: str, name: str) -> Collection:
    client = chromadb.PersistentClient(path=chroma_dir)
    # Cosine distance, so retrieval scores are 1 - distance (higher is more similar).
    return client.get_or_create_collection(name, metadata={"hnsw:space": "cosine"})
