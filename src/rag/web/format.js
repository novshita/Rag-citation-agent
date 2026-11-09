// Pure helpers for the UI: no DOM, no network, so they can be unit-tested with Node.

/** Split a passage around the quoted span [start, end). Returns null when there is nothing to highlight. */
export function splitHighlight(text, span) {
  if (typeof text !== "string" || !Array.isArray(span) || span.length !== 2) return null;
  const [start, end] = span;
  if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end <= start || end > text.length) return null;
  return { before: text.slice(0, start), match: text.slice(start, end), after: text.slice(end) };
}

/**
 * Keep roughly `radius` characters of context on each side of the highlighted quote, cutting at word
 * boundaries so no word is split. Source passages are whole chunks of raw Markdown; showing a window
 * around the proof keeps the highlight readable. The match itself is never shortened.
 */
export function excerpt(parts, radius = 200) {
  const tidy = (text) => text.replace(/\n{3,}/g, "\n\n");
  let before = tidy(parts.before);
  let after = tidy(parts.after);
  let cutBefore = false;
  let cutAfter = false;

  if (before.length > radius) {
    let from = before.length - radius;
    const space = before.slice(from).search(/\s/);          // start at the next word boundary
    from += space === -1 ? 0 : space + 1;
    before = before.slice(from);
    cutBefore = true;
  }
  if (after.length > radius) {
    let to = radius;
    const space = after.slice(0, to).search(/\s\S*$/);      // end at the last word boundary
    to = space === -1 ? to : space;
    after = after.slice(0, to);
    cutAfter = true;
  }
  return { before, match: parts.match, after, cutBefore, cutAfter };
}

/** "2.2 s · 1,860 tokens" */
export function formatMeta(latencyMs, tokens) {
  const seconds = (Math.max(0, latencyMs) / 1000).toFixed(1);
  return `${seconds} s · ${Math.max(0, tokens).toLocaleString("en-US")} tokens`;
}

export function plural(n, word) {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

/** "1 of 2 quotes verified in code", or null when the model was never called. */
export function verifiedLabel(verification) {
  if (!verification || verification.claims_total === 0) return null;
  return `${verification.claims_passed} of ${verification.claims_total} quotes verified in code`;
}

/** Width (percent, 0 to 100) of a similarity-score bar. */
export function barPercent(score) {
  if (typeof score !== "number" || Number.isNaN(score)) return 0;
  return Math.round(Math.min(1, Math.max(0, score)) * 100);
}

/** Text for the status badge, and which style to use. */
export const STATUS = {
  answered: { label: "Answered", tone: "ok", icon: "check" },
  partial: { label: "Partial answer", tone: "warn", icon: "alert" },
  abstained: { label: "Abstained", tone: "muted", icon: "minus" },
};

export function statusInfo(status) {
  return STATUS[status] || { label: String(status), tone: "muted", icon: "minus" };
}

/** One line for the gate pill above the retrieved passages. */
export function gateLabel(gate) {
  if (!gate) return "";
  const best = gate.top_score == null ? null : gate.top_score.toFixed(2);
  if (gate.passed) return `Gate passed · best match ${best}`;
  if (best == null) return "Gate stopped · nothing retrieved";
  return `Gate stopped · best match ${best} is below the ${gate.threshold.toFixed(2)} threshold`;
}

/** Plain-language reason when the relevance gate stopped the question (no setting names in it). */
export function gateReason(gate) {
  if (!gate || gate.passed) return null;
  if (gate.top_score == null) return "Nothing relevant was found in the documents.";
  return `Best match score ${gate.top_score.toFixed(2)} is below the relevance threshold ${gate.threshold.toFixed(2)}.`;
}

/** Turn a failed request into something a visitor can act on. */
export function errorInfo(status, detail) {
  const text = typeof detail === "string" ? detail : "";
  if (status === 0) return { title: "Couldn't reach the server.", hint: "Check your connection and try again." };
  if (status === 401) return { title: "This server needs an access key.", hint: "The demo is not open to anonymous requests." };
  if (status === 422) return { title: "Please enter a question (up to 2,000 characters).", hint: "" };
  if (status === 429 || /\b429\b|RESOURCE_EXHAUSTED|quota|rate.?limit/i.test(text)) {
    return { title: "The language model is busy (rate limit). Please try again in a minute.", hint: "" };
  }
  if (status >= 500) return { title: "Something went wrong while answering.", hint: text };
  return { title: "The request failed.", hint: text };
}
