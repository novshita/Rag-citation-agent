import threading

import pytest

chromadb = pytest.importorskip("chromadb")
pytest.importorskip("pypdf")

from pdfmaker import make_pdf  # noqa: E402

from rag.uploads import MB, UploadError, UploadManager, check_upload, clean_filename, extract_pages, human_size  # noqa: E402


class FakeEmbedder:
    """Deterministic little vectors, so no model is needed."""

    def __init__(self, hold: threading.Event | None = None):
        self.hold = hold
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        if self.hold is not None:
            self.hold.wait(5)
        out = []
        for t in texts:
            v = [float(len(t) % 7 + 1), float(sum(map(ord, t)) % 11 + 1), 1.0, 2.0]
            norm = sum(x * x for x in v) ** 0.5
            out.append([x / norm for x in v])
        return out


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def manager(**kwargs):
    answer = kwargs.pop("answer", lambda q, k, collection: ("answered", collection.count(), q, k))
    kwargs.setdefault("background", False)
    kwargs.setdefault("client", chromadb.EphemeralClient())
    return UploadManager(kwargs.pop("embedder", FakeEmbedder()), answer, **kwargs)


TEXT = ("# Handbook\n\n" + "Employees accrue vacation at two days per month. " * 40 + "\n\n" +
        "Remote work needs manager approval. " * 40).encode()


def test_human_size_and_filenames():
    assert human_size(2_400_000) == "2.3 MB" and human_size(5 * MB) == "5.0 MB" and human_size(900) == "1 KB"
    assert clean_filename("C:\\docs\\a.pdf") == "a.pdf" and clean_filename("../../etc/x.md") == "x.md"
    assert clean_filename("\x00\x1f") == "document"


def test_quick_checks_use_the_wording_from_the_design():
    with pytest.raises(UploadError) as e:
        check_upload("annual-report.pdf", int(12.4 * MB), 5 * MB, 50)
    assert e.value.status == 413
    assert e.value.message == "This file is too large. annual-report.pdf is 12.4 MB. The limit is 5 MB or 50 pages."
    for name, size, status in [("x.exe", 10, 415), ("x.pdf", 0, 422)]:
        with pytest.raises(UploadError) as e:
            check_upload(name, size, 5 * MB, 50)
        assert e.value.status == status


def test_a_text_file_is_one_page_with_an_estimated_page_count():
    pages, total = extract_pages("notes.txt", b"hello " * 1200, 50, 5 * MB)
    assert len(pages) == 1 and pages[0].page is None and pages[0].doc_id == "notes.txt" and total == 3


def test_a_long_text_file_is_refused_by_estimated_pages():
    with pytest.raises(UploadError) as e:
        extract_pages("big.txt", b"word " * 30000, 50, 5 * MB)
    assert "too long" in e.value.message and "50 pages" in e.value.message


def test_non_utf8_text_still_reads():
    pages, _ = extract_pages("old.txt", "caf\xe9 au lait".encode("cp1252") * 3, 50, 5 * MB)
    assert "café" in pages[0].text


def test_a_pdf_gives_one_page_per_page_with_page_numbers():
    pages, total = extract_pages("a.pdf", make_pdf(["First page text", "Second page text"]), 50, 5 * MB)
    assert total == 2 and [p.page for p in pages] == [1, 2] and "Second page" in pages[1].text


def test_pdf_problems_have_plain_messages():
    for data, fragment in [(b"not a pdf at all", "damaged"), (make_pdf([""]), "scanned")]:
        with pytest.raises(UploadError) as e:
            extract_pages("a.pdf", data, 50, 5 * MB)
        assert fragment in e.value.message and e.value.status == 422
    with pytest.raises(UploadError) as e:
        extract_pages("a.pdf", make_pdf(["x"] * 3), 2, 5 * MB)
    assert e.value.message == "This file is too long. a.pdf has 3 pages. The limit is 5 MB or 2 pages."


def test_upload_becomes_ready_and_can_be_asked():
    m = manager(chunk_size=30, chunk_overlap=5)
    status = m.start("g:1", "handbook.md", TEXT)
    assert status["state"] == "ready" and status["percent"] == 100 and status["passages_total"] == status["passages_done"] > 3
    assert status["filename"] == "handbook.md" and status["pages"] >= 1 and status["error"] is None
    assert status["limits"] == {"max_mb": 5, "max_pages": 50, "ttl_minutes": 60}
    kind, count, question, top_k = m.ask("g:1", "how much vacation?", 4)
    assert kind == "answered" and count == status["passages_total"] and (question, top_k) == ("how much vacation?", 4)


def test_the_visitor_can_get_their_file_back_to_check_it():
    m = manager()
    m.start("g:1", "handbook.md", b"\xef\xbb\xbfHello <b>there</b>")
    name, media, content = m.file("g:1")
    assert (name, media, content) == ("handbook.md", "text/plain; charset=utf-8", b"Hello <b>there</b>")   # text is never served as a page
    pdf = make_pdf(["Alpha beta gamma"])
    m.start("g:1", "a.pdf", pdf)
    assert m.file("g:1") == ("a.pdf", "application/pdf", pdf)
    with pytest.raises(UploadError) as e:
        m.file("g:2")                                   # another session has no file
    assert e.value.status == 404


def test_the_file_is_gone_after_remove_expiry_or_a_failed_read():
    clock = Clock()
    m = manager(clock=clock, ttl_seconds=60)
    m.start("g:1", "a.md", TEXT)
    m.delete("g:1")
    with pytest.raises(UploadError):
        m.file("g:1")
    m.start("g:1", "a.md", TEXT)
    clock.now += 61
    with pytest.raises(UploadError):
        m.file("g:1")
    m.start("g:1", "bad.pdf", b"%PDF-not really")
    assert m.status("g:1")["state"] == "error"
    with pytest.raises(UploadError):
        m.file("g:1")


def test_asking_before_there_is_a_document_is_a_clear_409():
    m = manager()
    with pytest.raises(UploadError) as e:
        m.ask("g:1", "q", 5)
    assert e.value.status == 409 and "Upload a document first" in e.value.message


def test_each_session_only_sees_its_own_document():
    m = manager(chunk_size=30, chunk_overlap=5)
    m.start("g:1", "a.md", TEXT)
    m.start("g:2", "b.txt", b"short note about parking " * 30)
    a, b = m.status("g:1"), m.status("g:2")
    assert a["filename"] == "a.md" and b["filename"] == "b.txt" and a["passages_total"] != b["passages_total"]
    assert m.ask("g:1", "q", 3)[1] == a["passages_total"] and m.ask("g:2", "q", 3)[1] == b["passages_total"]
    assert m.status("g:3")["state"] == "none"


def test_remove_deletes_the_index():
    m = manager()
    m.start("g:1", "a.md", TEXT)
    name = m._states["g:1"].name
    m.delete("g:1")
    assert m.status("g:1")["state"] == "none"
    with pytest.raises(Exception):
        m._chroma().get_collection(name)


def test_replacing_a_file_swaps_the_index():
    m = manager(chunk_size=30, chunk_overlap=5)
    m.start("g:1", "a.md", TEXT)
    first = m._states["g:1"].name
    m.start("g:1", "b.txt", b"other content here " * 30)
    assert m.status("g:1")["filename"] == "b.txt"
    with pytest.raises(Exception):
        m._chroma().get_collection(first)


def test_idle_documents_expire_and_activity_keeps_them():
    clock = Clock()
    m = manager(clock=clock, ttl_seconds=3600)
    m.start("g:1", "a.md", TEXT)
    clock.now += 3000
    assert m.status("g:1")["state"] == "ready"           # looking at it counts as activity
    clock.now += 3000
    assert m.status("g:1")["state"] == "ready"
    clock.now += 3601
    assert m.status("g:1")["state"] == "none"


def test_a_file_that_cannot_be_read_ends_in_an_error_state_with_the_message():
    m = manager()
    status = m.start("g:1", "scan.pdf", make_pdf([""]))
    assert status["state"] == "error" and "scanned" in status["error"]
    with pytest.raises(UploadError):
        m.ask("g:1", "q", 3)
    assert m.start("g:1", "ok.md", TEXT)["state"] == "ready"      # trying again works


def test_progress_is_reported_while_indexing_and_cancel_stops_it():
    hold = threading.Event()
    m = manager(embedder=FakeEmbedder(hold), background=True, chunk_size=20, chunk_overlap=2, batch_size=4)
    m.start("g:1", "a.md", TEXT)
    for _ in range(100):
        if m.status("g:1").get("stage") == "indexing":
            break
        threading.Event().wait(0.02)
    status = m.status("g:1")
    assert status["state"] == "indexing" and 20 <= status["percent"] < 100 and status["passages_total"] > 4
    with pytest.raises(UploadError) as e:                          # one file at a time
        m.start("g:1", "b.md", TEXT)
    assert e.value.status == 409
    name = m._states["g:1"].name
    m.delete("g:1")                                                # cancel
    hold.set()
    for _ in range(100):
        try:
            m._chroma().get_collection(name)
        except Exception:
            break
        threading.Event().wait(0.02)
    with pytest.raises(Exception):
        m._chroma().get_collection(name)
    assert m.status("g:1")["state"] == "none"


def test_a_late_cleanup_cannot_delete_a_newer_upload():
    hold = threading.Event()
    m = manager(embedder=FakeEmbedder(hold), background=True, chunk_size=20, chunk_overlap=2, batch_size=4)
    m.start("g:1", "a.md", TEXT)
    m.delete("g:1")                                                # cancelled, but its thread is still holding
    m.embedder = FakeEmbedder()                                    # the next upload runs freely
    m.background = False
    status = m.start("g:1", "b.md", TEXT)
    hold.set()
    threading.Event().wait(0.3)                                    # let the old thread notice and clean up
    assert status["state"] == "ready" and m.status("g:1")["state"] == "ready"
    assert m.ask("g:1", "q", 3)[1] > 0


def test_too_many_uploads_or_a_busy_server_get_a_429():
    m = manager(uploads_per_hour=2)
    m.start("g:1", "a.md", TEXT)
    m.start("g:1", "b.md", TEXT)
    with pytest.raises(UploadError) as e:
        m.start("g:1", "c.md", TEXT)
    assert e.value.status == 429

    hold = threading.Event()
    busy = manager(embedder=FakeEmbedder(hold), background=True, max_concurrent=1)
    busy.start("g:1", "a.md", TEXT)
    with pytest.raises(UploadError) as e:
        busy.start("g:2", "b.md", TEXT)
    assert e.value.status == 429 and "busy" in e.value.message
    hold.set()
