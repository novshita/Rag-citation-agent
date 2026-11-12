"""The "page to proof" demo shows real quotes from real pages. Check they really are there."""

import json
from pathlib import Path

import pytest

from rag.verifier import normalize

ROOT = Path(__file__).parent.parent
SHOWCASE = ROOT / "src" / "rag" / "web" / "showcase.json"
RAW = ROOT / "data" / "raw"

CARDS = json.loads(SHOWCASE.read_text())["cards"]
needs_corpus = pytest.mark.skipif(not RAW.is_dir(), reason="the FastAPI documents are not downloaded")


def test_there_are_enough_cards_to_fill_the_belt():
    assert len(CARDS) >= 4          # the belt must be longer than the screen so wrapping is invisible


def test_every_card_has_the_fields_the_page_needs():
    for card in CARDS:
        for key in ("doc", "title", "paragraphs", "question", "quote", "page_words", "quote_words"):
            assert card.get(key), f"{card.get('doc')}: missing {key}"
        assert any(card["quote"] in p for p in card["paragraphs"]), f"{card['doc']}: the quote is not shown on the page"
        assert card["quote_words"] == len(card["quote"].split())


@needs_corpus
@pytest.mark.parametrize("card", CARDS, ids=lambda c: c["doc"])
def test_quotes_and_excerpts_come_from_the_real_document(card):
    raw = (RAW / card["doc"]).read_text()
    text = normalize(raw)
    assert normalize(card["quote"]) in text, "the quote is not in the document"
    for paragraph in card["paragraphs"]:
        assert normalize(paragraph) in text, f"not in the document: {paragraph[:50]}"
    if card.get("code"):
        assert card["code"] in raw
    assert card["page_words"] == len(raw.split()), "the word count is out of date"
