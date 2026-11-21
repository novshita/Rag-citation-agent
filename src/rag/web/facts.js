// Fill the numbers in the static page templates from what the server says is indexed.
// Values are set as text, never as HTML.

import { approxWords } from "./flow.js";

export function fillFacts(root, corpus) {
  const values = {
    pages: corpus.pages ? String(corpus.pages) : null,
    words: approxWords(corpus.words) || null,
    threshold: corpus.min_score ? Number(corpus.min_score).toFixed(2) : null,
    llm: corpus.llm || null,
  };
  for (const el of root.querySelectorAll("[data-fill]")) {
    const value = values[el.dataset.fill];
    if (value) el.textContent = value;       // otherwise the template's own default stays
  }
}
