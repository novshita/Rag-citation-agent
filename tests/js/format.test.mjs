import test from "node:test";
import assert from "node:assert/strict";
import {
  barPercent, errorInfo, excerpt, formatMeta, gateLabel, gateReason, plural, splitHighlight, statusInfo, verifiedLabel,
} from "../../src/rag/web/format.js";

test("splitHighlight cuts the passage around the quoted span", () => {
  assert.deepEqual(splitHighlight("abc DEF ghi", [4, 7]), { before: "abc ", match: "DEF", after: " ghi" });
  assert.deepEqual(splitHighlight("abc", [0, 3]), { before: "", match: "abc", after: "" });
});

test("splitHighlight refuses bad spans instead of mangling the text", () => {
  for (const span of [null, undefined, [], [1], [3, 3], [5, 2], [-1, 2], [0, 99], ["a", "b"], [1.5, 2]]) {
    assert.equal(splitHighlight("abc", span), null, JSON.stringify(span));
  }
  assert.equal(splitHighlight(null, [0, 1]), null);
});

test("formatMeta shows seconds with one decimal and thousands separators", () => {
  assert.equal(formatMeta(2234, 1860), "2.2 s · 1,860 tokens");
  assert.equal(formatMeta(400, 0), "0.4 s · 0 tokens");
  assert.equal(formatMeta(-5, -1), "0.0 s · 0 tokens");
});

test("plural", () => {
  assert.equal(plural(1, "page"), "1 page");
  assert.equal(plural(16, "page"), "16 pages");
});

test("verifiedLabel reports passed of total, and nothing when there were no claims", () => {
  assert.equal(verifiedLabel({ claims_total: 2, claims_passed: 1 }), "1 of 2 quotes verified in code");
  assert.equal(verifiedLabel({ claims_total: 0, claims_passed: 0 }), null);
  assert.equal(verifiedLabel(null), null);
});

test("barPercent clamps to 0-100", () => {
  assert.equal(barPercent(0.61), 61);
  assert.equal(barPercent(-1), 0);
  assert.equal(barPercent(7), 100);
  assert.equal(barPercent(NaN), 0);
  assert.equal(barPercent(undefined), 0);
});

test("statusInfo maps each status, and tolerates an unknown one", () => {
  assert.equal(statusInfo("answered").label, "Answered");
  assert.equal(statusInfo("partial").tone, "warn");
  assert.equal(statusInfo("abstained").label, "Abstained");
  assert.equal(statusInfo("weird").label, "weird");
});

test("gateLabel explains both outcomes", () => {
  assert.equal(gateLabel({ passed: true, top_score: 0.61, threshold: 0.42 }), "Gate passed · best match 0.61");
  assert.equal(gateLabel({ passed: false, top_score: 0.25, threshold: 0.42 }), "Gate stopped · best match 0.25 is below the 0.42 threshold");
  assert.equal(gateLabel({ passed: false, top_score: null, threshold: 0.42 }), "Gate stopped · nothing retrieved");
  assert.equal(gateLabel(null), "");
});

test("errorInfo gives a friendly message for each failure", () => {
  assert.match(errorInfo(502, "ClientError: 429 RESOURCE_EXHAUSTED quota").title, /rate limit/);
  assert.match(errorInfo(429, "Daily question limit reached (5 a day for guests).").title, /Daily question limit/);   // our own limit, shown as written
  assert.match(errorInfo(429, "").title, /Too many requests/);
  assert.match(errorInfo(0, "").title, /reach the server/);
  assert.match(errorInfo(401, "").title, /session has ended/);
  assert.match(errorInfo(422, "").title, /enter a question/);
  assert.equal(errorInfo(500, "boom").hint, "boom");
  assert.equal(errorInfo(404, undefined).hint, "");
});

test("excerpt leaves a short passage whole", () => {
  const parts = { before: "Some context. ", match: "the quote", after: " and more." };
  assert.deepEqual(excerpt(parts, 200), { ...parts, cutBefore: false, cutAfter: false });
});

test("excerpt trims long context at word boundaries and never touches the match", () => {
  const words = (n, w) => Array.from({ length: n }, (_, i) => `${w}${i}`).join(" ");
  const parts = { before: words(100, "b") + " ", match: "THE QUOTE, exactly.", after: " " + words(100, "a") };
  const out = excerpt(parts, 60);

  assert.equal(out.match, "THE QUOTE, exactly.");
  assert.ok(out.cutBefore && out.cutAfter);
  assert.ok(out.before.length <= 60 && out.after.length <= 60);
  assert.match(out.before, /^b\d+ /);          // starts on a whole word
  assert.match(out.after, / a\d+$/);           // ends on a whole word
  assert.ok(parts.before.endsWith(out.before) && parts.after.startsWith(out.after));   // a true slice, nothing altered
});

test("excerpt cuts only the side that is long, and squeezes blank-line runs", () => {
  const out = excerpt({ before: "short ", match: "Q", after: "x ".repeat(300) }, 50);
  assert.equal(out.cutBefore, false);
  assert.equal(out.cutAfter, true);
  assert.equal(excerpt({ before: "a\n\n\n\n\nb", match: "Q", after: "" }, 50).before, "a\n\nb");
});

test("excerpt handles a long unbroken string without crashing", () => {
  const out = excerpt({ before: "z".repeat(500), match: "Q", after: "y".repeat(500) }, 40);
  assert.equal(out.before.length, 40);
  assert.equal(out.after.length, 40);
});

test("gateReason speaks plainly and only when the gate stopped the question", () => {
  assert.equal(gateReason({ passed: false, top_score: 0.246, threshold: 0.42 }),
    "Best match score 0.25 is below the relevance threshold 0.42.");
  assert.equal(gateReason({ passed: false, top_score: null, threshold: 0.42 }), "Nothing relevant was found in the documents.");
  assert.equal(gateReason({ passed: true, top_score: 0.6, threshold: 0.42 }), null);
  assert.equal(gateReason(null), null);
});
