"""Visitor uploads: one private, temporary document per session.

A visitor uploads one PDF, Markdown or text file. It is read, split into passages, embedded and put in
an in-memory index that only that session can ask. Questions about it go through the same retrieve ->
relevance gate -> quoted answer -> verify pipeline as the sample documents.

The index is deleted when the visitor removes the file, replaces it, signs out, or leaves it idle for
`ttl_seconds`. It lives in this process's memory, so it also disappears when the server restarts, and it
is never written to the sample documents' index. Run one server process: a second one would not see it.
"""

import io
import logging
import math
import re
import secrets
import threading
import time
from dataclasses import dataclass, field

from rag.ingest import Page, chunk_page
from rag.schemas import Chunk

log = logging.getLogger(__name__)

MB = 1024 * 1024
ALLOWED_SUFFIXES = (".pdf", ".md", ".markdown", ".txt")
WORDS_PER_PAGE = 500           # a text or Markdown file has no pages, so this estimates them
_STAGE_SHARE = {"reading": (0, 10), "splitting": (10, 20), "indexing": (20, 100)}   # share of the progress bar


class UploadError(Exception):
    """A problem the visitor can act on. `status` is the HTTP status to answer with."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def human_size(n: int) -> str:
    return f"{n / MB:.1f} MB" if n >= MB else f"{max(1, round(n / 1024))} KB"


def clean_filename(name: str) -> str:
    base = re.split(r"[\\/]", name or "")[-1]
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip()
    return (base[:120] or "document")


def limit_text(max_bytes: int, max_pages: int) -> str:
    return f"The limit is {max_bytes // MB} MB or {max_pages} pages."


def check_upload(filename: str, size: int, max_bytes: int, max_pages: int) -> None:
    """The quick checks that need no parsing. Raises UploadError."""
    if not filename.lower().endswith(ALLOWED_SUFFIXES):
        raise UploadError(415, "That file type isn't supported. Upload a PDF, Markdown or text file.")
    if size <= 0:
        raise UploadError(422, f"{filename} is empty.")
    if size > max_bytes:
        raise UploadError(413, f"This file is too large. {filename} is {human_size(size)}. {limit_text(max_bytes, max_pages)}")


def extract_pages(filename: str, data: bytes, max_pages: int, max_bytes: int, on_page=None) -> tuple[list[Page], int]:
    """The text of the file as pages, and its page count. Raises UploadError."""
    if filename.lower().endswith(".pdf"):
        return _pdf_pages(filename, data, max_pages, max_bytes, on_page)
    text = _decode(data)
    words = len(text.split())
    estimated = max(1, math.ceil(words / WORDS_PER_PAGE))
    if estimated > max_pages:
        raise UploadError(413, f"This file is too long. {filename} is about {estimated} pages. {limit_text(max_bytes, max_pages)}")
    if not text.strip():
        raise UploadError(422, f"No readable text found in {filename}.")
    return [Page(filename, None, text)], estimated


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _pdf_pages(filename, data, max_pages, max_bytes, on_page) -> tuple[list[Page], int]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise UploadError(422, f"{filename} is password-protected. Remove the password and upload it again.")
        total = len(reader.pages)
    except UploadError:
        raise
    except Exception:
        raise UploadError(422, f"{filename} couldn't be read as a PDF. It may be damaged.") from None
    if total > max_pages:
        raise UploadError(413, f"This file is too long. {filename} has {total} pages. {limit_text(max_bytes, max_pages)}")

    pages = []
    for number, pdf_page in enumerate(reader.pages, start=1):
        try:
            text = pdf_page.extract_text() or ""
        except Exception:
            text = ""
        if text.strip():
            pages.append(Page(filename, number, text))
        if on_page:
            on_page(number, total)
    if not pages:
        raise UploadError(422, f"No readable text found in {filename}. It may be a scanned document; upload a version with selectable text.")
    return pages, total


@dataclass
class UploadState:
    filename: str
    size_bytes: int
    started: float
    touched: float
    state: str = "indexing"                 # indexing | ready | error
    stage: str = "reading"                  # reading | splitting | indexing
    pages: int = 0
    pages_done: int = 0
    pages_total: int = 0
    passages_total: int = 0
    passages_done: int = 0
    error: str | None = None
    finished: float | None = None
    collection: object = None
    name: str = field(default_factory=lambda: "u" + secrets.token_hex(12))   # unique per upload, so a late cleanup can't touch a newer index
    cancel: threading.Event = field(default_factory=threading.Event)


class UploadManager:
    def __init__(self, embedder, answer, *, chunk_size: int = 150, chunk_overlap: int = 20, max_bytes: int = 5 * MB,
                 max_pages: int = 50, ttl_seconds: int = 3600, max_concurrent: int = 2, uploads_per_hour: int = 10,
                 batch_size: int = 16, background: bool = True, clock=time.time, client=None):
        """`answer(question, top_k, collection) -> PipelineResult` asks one collection."""
        self.embedder, self._answer = embedder, answer
        self.chunk_size, self.chunk_overlap = chunk_size, chunk_overlap
        self.max_bytes, self.max_pages, self.ttl = max_bytes, max_pages, ttl_seconds
        self.max_concurrent, self.uploads_per_hour = max_concurrent, uploads_per_hour
        self.batch_size, self.background, self.clock = batch_size, background, clock
        self._client = client
        self._states: dict[str, UploadState] = {}
        self._starts: dict[str, list[float]] = {}
        self._lock = threading.RLock()
        self._sweeper_stop = threading.Event()

    # -- public ---------------------------------------------------------------------------------

    def limits(self) -> dict:
        return {"max_mb": self.max_bytes // MB, "max_pages": self.max_pages, "ttl_minutes": self.ttl // 60}

    def start(self, subject: str, filename: str, data: bytes) -> dict:
        filename = clean_filename(filename)
        check_upload(filename, len(data), self.max_bytes, self.max_pages)
        self.sweep()
        with self._lock:
            current = self._states.get(subject)
            if current and current.state == "indexing":
                raise UploadError(409, "Your last file is still being indexed. Cancel it first, or wait for it to finish.")
            recent = [t for t in self._starts.get(subject, []) if self.clock() - t < 3600]
            if len(recent) >= self.uploads_per_hour:
                raise UploadError(429, "You've uploaded a lot of files this hour. Try again later.")
            if sum(1 for s in self._states.values() if s.state == "indexing") >= self.max_concurrent:
                raise UploadError(429, "The server is busy indexing other documents. Try again in a minute.")
            if current:
                self._drop(subject)
            self._starts[subject] = recent + [self.clock()]
            now = self.clock()
            state = UploadState(filename=filename, size_bytes=len(data), started=now, touched=now)
            self._states[subject] = state
        if self.background:
            threading.Thread(target=self._run, args=(subject, state, data), daemon=True, name="indexing").start()
        else:
            self._run(subject, state, data)
        return self.status(subject)

    def status(self, subject: str) -> dict:
        self.sweep()
        with self._lock:
            state = self._states.get(subject)
            if state is None:
                return {"state": "none", "limits": self.limits()}
            state.touched = self.clock()
            return self._snapshot(state)

    def delete(self, subject: str) -> None:
        with self._lock:
            self._drop(subject)

    def check_ready(self, subject: str) -> None:
        """Raise UploadError unless this session has a finished, usable document."""
        with self._lock:
            state = self._states.get(subject)
            if state is None:
                raise UploadError(409, "Upload a document first, or switch to the sample docs.")
            if state.state == "indexing":
                raise UploadError(409, "Your document is still being indexed. Try again in a moment.")
            if state.state == "error":
                raise UploadError(409, "Your document couldn't be indexed. Upload it again, or switch to the sample docs.")

    def ask(self, subject: str, question: str, top_k: int | None):
        self.check_ready(subject)
        with self._lock:
            state = self._states[subject]
            state.touched = self.clock()
            collection = state.collection
        return self._answer(question, top_k, collection)

    def sweep(self) -> None:
        """Delete documents that have been idle longer than the time limit."""
        with self._lock:
            now = self.clock()
            for subject in [s for s, st in self._states.items() if now - st.touched > self.ttl]:
                self._drop(subject)

    def start_sweeper(self, every_seconds: int = 300) -> None:
        def loop():
            while not self._sweeper_stop.wait(every_seconds):
                self.sweep()
        threading.Thread(target=loop, daemon=True, name="upload-sweeper").start()

    def stop(self) -> None:
        self._sweeper_stop.set()

    # -- internals ------------------------------------------------------------------------------

    def _snapshot(self, s: UploadState) -> dict:
        percent = 100
        if s.state == "indexing":
            lo, hi = _STAGE_SHARE[s.stage]
            if s.stage == "reading":
                fraction = s.pages_done / s.pages_total if s.pages_total else 0
            elif s.stage == "indexing":
                fraction = s.passages_done / s.passages_total if s.passages_total else 0
            else:
                fraction = 0
            percent = int(lo + (hi - lo) * fraction)
        elif s.state == "error":
            percent = 0
        end = s.finished if s.finished is not None else self.clock()
        return {
            "state": s.state, "stage": s.stage, "filename": s.filename, "size_bytes": s.size_bytes, "pages": s.pages,
            "passages_total": s.passages_total, "passages_done": s.passages_done, "percent": percent,
            "seconds": round(max(0.0, end - s.started), 1), "error": s.error, "limits": self.limits(),
        }

    def _chroma(self):
        if self._client is None:
            import chromadb
            self._client = chromadb.EphemeralClient()
        return self._client

    def _drop(self, subject: str) -> None:
        state = self._states.pop(subject, None)
        if state is None:
            return
        state.cancel.set()
        self._cleanup(state.name)

    def _run(self, subject: str, state: UploadState, data: bytes) -> None:
        name = state.name
        try:
            def on_page(done, total):
                state.pages_done, state.pages_total = done, total
            pages, total_pages = extract_pages(state.filename, data, self.max_pages, self.max_bytes, on_page)
            state.pages = total_pages

            state.stage = "splitting"
            chunks: list[Chunk] = [c for p in pages for c in chunk_page(p, self.chunk_size, self.chunk_overlap)]
            if not chunks:
                raise UploadError(422, f"No readable text found in {state.filename}.")
            state.passages_total = len(chunks)

            state.stage = "indexing"
            collection = self._chroma().create_collection(name, metadata={"hnsw:space": "cosine"})
            for i in range(0, len(chunks), self.batch_size):
                if state.cancel.is_set():
                    self._cleanup(name)
                    return
                batch = chunks[i:i + self.batch_size]
                collection.add(
                    ids=[c.chunk_id for c in batch], documents=[c.text for c in batch],
                    embeddings=self.embedder.embed([c.text for c in batch]),
                    metadatas=[_metadata(c) for c in batch])
                state.passages_done = min(len(chunks), i + len(batch))
            with self._lock:
                if state.cancel.is_set() or self._states.get(subject) is not state:
                    self._cleanup(name)
                    return
                state.collection, state.state, state.finished = collection, "ready", self.clock()
        except UploadError as error:
            self._fail(subject, state, name, error.message)
        except Exception:
            log.exception("indexing an uploaded file failed")
            self._fail(subject, state, name, "Something went wrong while reading that file. Try another one.")

    def _fail(self, subject, state, name, message) -> None:
        self._cleanup(name)
        with self._lock:
            if self._states.get(subject) is state:
                state.state, state.error, state.finished = "error", message, self.clock()

    def _cleanup(self, name: str) -> None:
        try:
            self._chroma().delete_collection(name)
        except Exception:
            pass


def _metadata(chunk: Chunk) -> dict:
    meta = {"doc_id": chunk.doc_id, "char_start": chunk.char_start, "char_end": chunk.char_end}
    if chunk.page is not None:
        meta["page"] = chunk.page
    return meta
