import json

from rag.corpus import build_corpus_info, group_documents, load_manifest, manifest_path

IDS = [
    "tutorial/body.md", "tutorial/first-steps.md", "tutorial/path-params.md",
    "advanced/events.md", "advanced/websockets.md",
    "async.md", "python-types.md",
    "deployment/docker.md",
]


def test_documents_are_grouped_by_top_folder_biggest_group_first_and_loose_files_last():
    groups = group_documents(IDS)

    assert [(g["name"], g["pages"]) for g in groups] == [("Tutorial", 3), ("Advanced", 2), ("Deployment", 1), ("Other", 2)]
    assert groups[0]["docs"] == ["tutorial/body.md", "tutorial/first-steps.md", "tutorial/path-params.md"]


def test_duplicate_ids_count_once_and_folder_names_are_made_readable():
    groups = group_documents(["my-notes/a.pdf", "my-notes/a.pdf", "my_notes/b.pdf"])
    assert [(g["name"], g["pages"]) for g in groups] == [("My Notes", 2)]


def test_corpus_info_uses_the_manifest_and_only_valid_examples():
    manifest = {
        "name": "FastAPI documentation", "note": "MIT licensed", "tagline": "Grounded Q&A",
        "examples": [
            {"tag": "Answered", "kind": "answered", "question": "Q1?"},
            {"tag": "Bad kind", "kind": "nonsense", "question": "Q2?"},        # unknown kind: dropped
            {"tag": "No question", "kind": "multi"},                            # missing question: dropped
            "not a dict",                                                       # wrong type: dropped
        ],
    }
    info = build_corpus_info(IDS, manifest, top_k=5, min_score=0.42, llm_provider="gemini")

    assert (info["name"], info["note"], info["pages"], info["llm"]) == ("FastAPI documentation", "MIT licensed", 8, "Gemini")
    assert info["examples"] == [{"tag": "Answered", "kind": "answered", "question": "Q1?"}]
    assert (info["top_k"], info["min_score"]) == (5, 0.42)


def test_without_a_manifest_the_ui_gets_generic_text_and_no_examples():
    info = build_corpus_info(["a.pdf"], {}, top_k=5, min_score=0.3, llm_provider="anthropic")
    assert info["name"] == "Indexed documents" and info["examples"] == [] and info["llm"] == "Claude"


def test_manifest_loading_never_raises(tmp_path):
    good = tmp_path / "CORPUS.json"
    good.write_text(json.dumps({"name": "X"}))
    broken = tmp_path / "broken.json"
    broken.write_text("{ not json")
    listy = tmp_path / "list.json"
    listy.write_text("[1, 2]")

    assert load_manifest(str(good)) == {"name": "X"}
    assert load_manifest(str(broken)) == {} and load_manifest(str(listy)) == {}
    assert load_manifest(str(tmp_path / "missing.json")) == {} and load_manifest(None) == {}


def test_the_bundled_manifest_is_only_used_for_the_default_collection():
    assert manifest_path("", "corpus") == "data/raw/CORPUS.json"
    assert manifest_path("", "mine") is None                 # your own PDFs must not be labelled as FastAPI docs
    assert manifest_path("custom.json", "mine") == "custom.json"


def test_the_shipped_manifest_is_valid():
    manifest = load_manifest("data/raw/CORPUS.json")
    info = build_corpus_info(IDS, manifest, top_k=5, min_score=0.42, llm_provider="gemini")
    assert info["name"] == "FastAPI documentation" and [e["kind"] for e in info["examples"]] == ["answered", "multi", "abstain"]
