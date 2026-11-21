import test from "node:test";
import assert from "node:assert/strict";
import { checkCredentials, guard, parseRoute, quotaText, whoLabel } from "../../src/rag/web/flow.js";

const out = { enabled: true, authenticated: false };
const guest = { enabled: true, authenticated: true, kind: "guest", email: null, remaining: 3, limit: 5, user_limit: 30 };
const user = { enabled: true, authenticated: true, kind: "user", email: "ada@example.com", remaining: 27, limit: 30, user_limit: 30 };
const open = { enabled: false, authenticated: true };

test("routes parse from the hash, and unknown ones are the landing page", () => {
  assert.equal(parseRoute(""), "landing");
  assert.equal(parseRoute("#/"), "landing");
  assert.equal(parseRoute("#/login"), "login");
  assert.equal(parseRoute("#/app"), "app");
  assert.equal(parseRoute("#/evaluation?x=1"), "evaluation");
  assert.equal(parseRoute("#/nonsense"), "landing");
  assert.equal(parseRoute(undefined), "landing");
});

test("the product needs a session, the login page doesn't once there is one", () => {
  assert.equal(guard("app", out), "#/login");
  assert.equal(guard("app", guest), null);
  assert.equal(guard("login", user), "#/app");
  assert.equal(guard("login", out), null);
  assert.equal(guard("landing", out), null);
  assert.equal(guard("evaluation", out), null);
});

test("with accounts off, everyone goes straight to the product", () => {
  assert.equal(guard("app", open), null);
  assert.equal(guard("login", open), "#/app");
});

test("quota text explains what is left, and what an account adds", () => {
  assert.equal(quotaText(guest), "3 of 5 questions left today as a guest. A free account gets 30 a day.");
  assert.equal(quotaText(user), "27 of 30 questions left today.");
  assert.equal(quotaText(open), "");
  assert.equal(quotaText(null), "");
});

test("credentials are checked the same way the server checks them", () => {
  assert.match(checkCredentials("login", "nope", "x"), /valid email/);
  assert.match(checkCredentials("signup", "a@b.co", "short"), /8 to 128/);
  assert.match(checkCredentials("login", "a@b.co", ""), /password/);
  assert.equal(checkCredentials("signup", "a@b.co", "longenough1"), null);
  assert.equal(checkCredentials("login", " a@b.co ", "x"), null);          // any password may be tried when signing in
});

test("the header names who is signed in", () => {
  assert.equal(whoLabel(guest), "Guest");
  assert.equal(whoLabel(user), "ada@example.com");
  assert.equal(whoLabel(out), "");
  assert.equal(whoLabel(open), "");
});

import { parseAnchor } from "../../src/rag/web/flow.js";

test("landing sections are anchors on the landing page", () => {
  assert.equal(parseRoute("#/example"), "landing");
  assert.equal(parseAnchor("#/example"), "example");
  assert.equal(parseAnchor("#/evidence"), "evidence");
  assert.equal(parseAnchor("#/app"), null);
  assert.equal(parseAnchor(""), null);
});

import { approxWords } from "../../src/rag/web/flow.js";

test("word counts are rounded to the nearest thousand", () => {
  assert.equal(approxWords(49333), "49,000");
  assert.equal(approxWords(1499), "1,000");
  assert.equal(approxWords(0), "");
  assert.equal(approxWords(null), "");
});

import { ACCEPT, checkFile, docPillText, formatBytes, meterModel, privacyText, sourceLabel, stageRows, ttlText } from "../../src/rag/web/flow.js";

const limits = { max_mb: 5, max_pages: 50, ttl_minutes: 60 };

test("file sizes read naturally", () => {
  assert.equal(formatBytes(2_400_000), "2.3 MB");
  assert.equal(formatBytes(12.4 * 1048576), "12.4 MB");
  assert.equal(formatBytes(900), "1 KB");
});

test("a bad file is turned away with the design's wording", () => {
  assert.equal(checkFile({ name: "annual-report.pdf", size: 12.4 * 1048576 }, limits), "This file is too large. annual-report.pdf is 12.4 MB. The limit is 5 MB or 50 pages.");
  assert.match(checkFile({ name: "a.exe", size: 10 }, limits), /isn't supported/);
  assert.match(checkFile({ name: "a.pdf", size: 0 }, limits), /is empty/);
  assert.equal(checkFile({ name: "Notes.MD", size: 1000 }, limits), null);
  assert.ok(ACCEPT.includes(".pdf") && ACCEPT.includes(".txt"));
});

test("the privacy note says what the server really does", () => {
  assert.equal(ttlText(60), "an hour");
  assert.equal(ttlText(120), "2 hours");
  assert.equal(ttlText(30), "30 minutes");
  assert.match(privacyText(limits), /remove it, sign out, or after an hour of no activity/);
});

test("progress rows follow the stage", () => {
  const reading = stageRows({ stage: "reading" });
  assert.deepEqual(reading.map((r) => r.state), ["active", "todo", "todo"]);
  const indexing = stageRows({ stage: "indexing", passages_done: 42, passages_total: 124 });
  assert.deepEqual(indexing.map((r) => r.state), ["done", "done", "active"]);
  assert.equal(indexing[2].detail, "42 of 124 passages");
});

test("the quota meter is dashes for small limits and a bar for large ones", () => {
  assert.deepEqual(meterModel({ remaining: 3, limit: 5 }), { remaining: 3, limit: 5, segmented: true });
  assert.equal(meterModel({ remaining: 27, limit: 30 }).segmented, false);
  assert.equal(meterModel({ remaining: null, limit: null }), null);
});

test("labels follow the chosen source", () => {
  const corpus = { name: "FastAPI documentation", pages: 30 };
  assert.equal(sourceLabel("sample", null, corpus), "FastAPI documentation");
  assert.equal(sourceLabel("mine", { state: "ready", filename: "handbook.pdf" }, corpus), "handbook.pdf");
  assert.equal(sourceLabel("mine", { state: "none" }, corpus), "your document");
  assert.equal(docPillText("sample", null, corpus), "FastAPI documentation · 30 pages");
  assert.equal(docPillText("mine", { state: "indexing", filename: "a.pdf" }, corpus), "Indexing a.pdf…");
  assert.equal(docPillText("mine", { state: "none" }, corpus), "No document");
});

import { parseToken } from "../../src/rag/web/flow.js";

test("the confirmation page reads its token from the link", () => {
  assert.equal(parseRoute("#/verify?token=abc.def"), "verify");
  assert.equal(parseToken("#/verify?token=abc.def-123_x"), "abc.def-123_x");
  assert.equal(parseToken("#/verify"), "");
  assert.equal(parseToken(""), "");
  assert.equal(guard("verify", { enabled: true, authenticated: true, kind: "guest" }), null);   // a guest opening the link must still be confirmed
});
