"""What the web UI shows about the indexed documents: name, grouped file list, example questions.

The list of documents comes from the index itself. The name, note and example questions come
from an optional manifest (a small JSON file next to the documents), so the UI works for any
corpus and never claims anything about documents it wasn't told about.

Manifest example (data/raw/CORPUS.json):
    {"name": "FastAPI documentation", "note": "MIT licensed",
     "tagline": "Grounded Q&A over the FastAPI docs",
     "examples": [{"tag": "Answered", "kind": "answered", "question": "..."}]}
"""

import json
from pathlib import Path

DEFAULT_MANIFEST = "data/raw/CORPUS.json"
LLM_LABELS = {"gemini": "Gemini", "anthropic": "Claude"}
KINDS = {"answered", "multi", "abstain"}


def manifest_path(configured: str, collection: str) -> str | None:
    """The configured manifest, or the bundled FastAPI one only for the default collection."""
    if configured:
        return configured
    return DEFAULT_MANIFEST if collection == "corpus" else None


def load_manifest(path: str | None) -> dict:
    if not path or not Path(path).is_file():
        return {}
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def group_documents(doc_ids: list[str]) -> list[dict]:
    """Group file paths by their top folder; files in the root go under "Other". Biggest group first."""
    groups: dict[str, list[str]] = {}
    for doc_id in sorted(set(doc_ids)):
        name = doc_id.split("/", 1)[0].replace("-", " ").replace("_", " ").title() if "/" in doc_id else "Other"
        groups.setdefault(name, []).append(doc_id)
    ordered = sorted(groups.items(), key=lambda item: (item[0] == "Other", -len(item[1]), item[0]))
    return [{"name": name, "pages": len(docs), "docs": docs} for name, docs in ordered]


def build_corpus_info(doc_ids: list[str], manifest: dict, *, top_k: int, min_score: float, llm_provider: str) -> dict:
    examples = [
        {"tag": str(e["tag"]), "kind": e["kind"], "question": str(e["question"])}
        for e in manifest.get("examples", [])
        if isinstance(e, dict) and e.get("question") and e.get("tag") and e.get("kind") in KINDS
    ][:6]
    return {
        "name": str(manifest.get("name") or "Indexed documents"),
        "note": str(manifest.get("note") or ""),
        "tagline": str(manifest.get("tagline") or ""),
        "pages": len(set(doc_ids)),
        "groups": group_documents(doc_ids),
        "examples": examples,
        "top_k": top_k,
        "min_score": min_score,
        "llm": LLM_LABELS.get(llm_provider, llm_provider.title()),
    }
