"""Load documents, split them into chunks, embed them, and store them in Chroma."""

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

from rag.embeddings import Embedder
from rag.schemas import Chunk

SUPPORTED_SUFFIXES = {".pdf", ".md", ".markdown"}

_WORD = re.compile(r"\S+")
_PARAGRAPH_BREAK = re.compile(r"\n[ \t]*\n")


@dataclass
class Page:
    doc_id: str
    page: int | None
    text: str


@dataclass
class IngestReport:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    empty: list[str] = field(default_factory=list)   # no extractable text, e.g. scanned PDFs
    chunks_written: int = 0


# --- Loading ---------------------------------------------------------------

def load_pages(path: Path, root: Path) -> list[Page]:
    """Return the text of a file, one Page per PDF page (or one for a Markdown file)."""
    doc_id = path.relative_to(root).as_posix()
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(path)
        return [
            Page(doc_id, number, text)
            for number, pdf_page in enumerate(reader.pages, start=1)
            if (text := pdf_page.extract_text() or "").strip()
        ]
    text = path.read_text(encoding="utf-8")
    return [Page(doc_id, None, text)] if text.strip() else []


# --- Chunking --------------------------------------------------------------

def chunk_page(page: Page, size: int, overlap: int) -> list[Chunk]:
    """Split a page into chunks of at most `size` words, overlapping by `overlap` words.

    A chunk prefers to end at a paragraph break if one falls in the second half of
    its window. Chunk text is an exact slice of the page text, so quotes can later
    be checked against it. Chunks never span pages, so every chunk has one page number.
    """
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("need size > 0 and 0 <= overlap < size")

    text = page.text
    words = [m.span() for m in _WORD.finditer(text)]
    if not words:
        return []

    # Word indices that begin a new paragraph.
    paragraph_starts = {
        i for i in range(1, len(words))
        if _PARAGRAPH_BREAK.search(text, words[i - 1][1], words[i][0])
    }

    chunks: list[Chunk] = []
    start = 0
    while True:
        end = min(start + size, len(words))
        if end < len(words):
            for boundary in range(end, start + size // 2, -1):
                if boundary in paragraph_starts:
                    end = boundary
                    break

        char_start, char_end = words[start][0], words[end - 1][1]
        page_part = f"p{page.page}:" if page.page is not None else ""
        chunks.append(Chunk(
            chunk_id=f"{page.doc_id}:{page_part}c{len(chunks)}",
            doc_id=page.doc_id,
            page=page.page,
            text=text[char_start:char_end],
            char_start=char_start,
            char_end=char_end,
        ))

        if end == len(words):
            return chunks
        start = max(end - overlap, start + 1)


# --- Ingest ----------------------------------------------------------------

def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def find_documents(root: Path) -> list[Path]:
    return sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
    )


def ingest_folder(
    folder: str | Path,
    collection,
    embedder: Embedder,
    chunk_size: int,
    chunk_overlap: int,
) -> IngestReport:
    """Bring the collection in line with the folder.

    New and changed files are (re)chunked and embedded, unchanged files are skipped,
    and files that were deleted from the folder are removed from the store.
    """
    root = Path(folder)
    report = IngestReport()

    stored = collection.get(include=["metadatas"])["metadatas"] or []
    stored_hashes = {m["doc_id"]: m["file_hash"] for m in stored}

    seen: set[str] = set()
    for path in find_documents(root):
        doc_id = path.relative_to(root).as_posix()
        seen.add(doc_id)
        digest = file_hash(path)

        if stored_hashes.get(doc_id) == digest:
            report.unchanged.append(doc_id)
            continue
        if doc_id in stored_hashes:
            collection.delete(where={"doc_id": doc_id})

        chunks = [
            chunk
            for page in load_pages(path, root)
            for chunk in chunk_page(page, chunk_size, chunk_overlap)
        ]
        if not chunks:
            report.empty.append(doc_id)
            continue

        collection.add(
            ids=[c.chunk_id for c in chunks],
            documents=[c.text for c in chunks],
            embeddings=embedder.embed([c.text for c in chunks]),
            metadatas=[_metadata(c, digest) for c in chunks],
        )
        report.chunks_written += len(chunks)
        (report.updated if doc_id in stored_hashes else report.added).append(doc_id)

    for doc_id in sorted(stored_hashes.keys() - seen):
        collection.delete(where={"doc_id": doc_id})
        report.removed.append(doc_id)

    return report


def _metadata(chunk: Chunk, digest: str) -> dict:
    meta = {
        "doc_id": chunk.doc_id,
        "char_start": chunk.char_start,
        "char_end": chunk.char_end,
        "file_hash": digest,
    }
    if chunk.page is not None:   # Chroma metadata values can't be None
        meta["page"] = chunk.page
    return meta
