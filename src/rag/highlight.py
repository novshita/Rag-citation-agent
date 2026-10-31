"""Find a cited quote inside its source passage, for showing it highlighted.

The verifier already decided the quote is in the passage, ignoring case, whitespace and
Markdown marks. Here we locate the same words in the raw passage text. The match is on
the quote's words in order, with any punctuation or formatting allowed between them, so a
plain-text quote still finds its place in Markdown source such as ``first install [`pkg`](url)``.
"""

import html
import re


def find_quote(text: str, quote: str) -> tuple[int, int] | None:
    """(start, end) of the quote in `text`, or None if it can't be located."""
    words = re.findall(r"\w+", quote)
    if not words:
        return None
    pattern = r"[\W_]+".join(re.escape(w) for w in words)
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return (match.start(), match.end()) if match else None


def highlight_html(text: str, quote: str) -> str:
    """The passage as HTML-safe text, with the quote wrapped in <mark>. No highlight if not found."""
    span = find_quote(text, quote)
    if span is None:
        return html.escape(text)
    start, end = span
    return f"{html.escape(text[:start])}<mark>{html.escape(text[start:end])}</mark>{html.escape(text[end:])}"
