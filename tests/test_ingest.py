import pytest

from conftest import FakeEmbedder
from rag.ingest import ingest_folder, load_pages


@pytest.fixture
def corpus(tmp_path):
    folder = tmp_path / "raw"
    folder.mkdir()
    (folder / "a.md").write_text("Alpha document. " * 50)
    (folder / "sub").mkdir()
    (folder / "sub" / "b.md").write_text("Beta document. " * 50)
    (folder / "ignored.txt").write_text("not a supported type")
    return folder


def ingest(folder, collection):
    return ingest_folder(folder, collection, FakeEmbedder(), chunk_size=30, chunk_overlap=5)


def test_markdown_loads_as_one_page_without_number(corpus):
    pages = load_pages(corpus / "sub" / "b.md", corpus)
    assert len(pages) == 1
    assert pages[0].doc_id == "sub/b.md"
    assert pages[0].page is None


def test_first_ingest_adds_all_documents(corpus, collection):
    report = ingest(corpus, collection)

    assert report.added == ["a.md", "sub/b.md"]
    assert collection.count() == report.chunks_written > 0


def test_unchanged_files_are_skipped(corpus, collection):
    ingest(corpus, collection)
    report = ingest(corpus, collection)

    assert report.unchanged == ["a.md", "sub/b.md"]
    assert report.added == report.updated == []
    assert report.chunks_written == 0


def test_changed_file_is_replaced(corpus, collection):
    ingest(corpus, collection)
    (corpus / "a.md").write_text("Short new text.")
    report = ingest(corpus, collection)

    assert report.updated == ["a.md"]
    stored = collection.get(where={"doc_id": "a.md"})["documents"]
    assert stored == ["Short new text."]


def test_deleted_file_is_removed(corpus, collection):
    ingest(corpus, collection)
    (corpus / "a.md").unlink()
    report = ingest(corpus, collection)

    assert report.removed == ["a.md"]
    assert collection.get(where={"doc_id": "a.md"})["ids"] == []


def test_empty_file_is_reported(corpus, collection):
    (corpus / "blank.md").write_text("   ")
    report = ingest(corpus, collection)
    assert report.empty == ["blank.md"]


def test_stored_metadata_points_back_to_source(corpus, collection):
    ingest(corpus, collection)
    result = collection.get(where={"doc_id": "a.md"}, include=["documents", "metadatas"])
    source = (corpus / "a.md").read_text()

    for text, meta in zip(result["documents"], result["metadatas"]):
        assert source[meta["char_start"]:meta["char_end"]] == text
