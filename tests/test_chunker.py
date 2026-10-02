import pytest

from rag.ingest import Page, chunk_page


def make_page(text, page=3):
    return Page(doc_id="docs/report.pdf", page=page, text=text)


def words_of(chunk):
    return chunk.text.split()


def test_chunks_respect_size_and_overlap():
    text = " ".join(f"w{i}" for i in range(1000))
    chunks = chunk_page(make_page(text), size=100, overlap=15)

    assert all(len(words_of(c)) <= 100 for c in chunks)
    for prev, nxt in zip(chunks, chunks[1:]):
        assert words_of(prev)[-15:] == words_of(nxt)[:15]


def test_chunks_cover_the_whole_page():
    text = " ".join(f"w{i}" for i in range(250))
    chunks = chunk_page(make_page(text), size=100, overlap=10)

    assert words_of(chunks[0])[0] == "w0"
    assert words_of(chunks[-1])[-1] == "w249"


def test_chunk_text_is_exact_slice_of_page():
    text = "First   line\nwith odd    spacing.\n\nSecond paragraph here.\n" * 40
    page = make_page(text)
    for chunk in chunk_page(page, size=30, overlap=5):
        assert chunk.text == text[chunk.char_start:chunk.char_end]


def test_chunks_keep_metadata_and_unique_ids():
    chunks = chunk_page(make_page("word " * 300, page=7), size=100, overlap=10)

    assert all(c.doc_id == "docs/report.pdf" and c.page == 7 for c in chunks)
    assert chunks[0].chunk_id == "docs/report.pdf:p7:c0"
    assert len({c.chunk_id for c in chunks}) == len(chunks)


def test_markdown_chunk_ids_have_no_page():
    chunks = chunk_page(Page("notes.md", None, "hello world"), size=10, overlap=2)
    assert chunks[0].chunk_id == "notes.md:c0"
    assert chunks[0].page is None


def test_prefers_ending_at_a_paragraph_break():
    first = " ".join(f"a{i}" for i in range(70))
    second = " ".join(f"b{i}" for i in range(70))
    chunks = chunk_page(make_page(f"{first}\n\n{second}"), size=100, overlap=10)

    assert words_of(chunks[0])[-1] == "a69"


def test_empty_page_gives_no_chunks():
    assert chunk_page(make_page("   \n\n  "), size=100, overlap=10) == []


@pytest.mark.parametrize("size, overlap", [(0, 0), (100, 100), (100, -1)])
def test_rejects_bad_settings(size, overlap):
    with pytest.raises(ValueError):
        chunk_page(make_page("some text"), size=size, overlap=overlap)
