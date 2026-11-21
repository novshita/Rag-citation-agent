// Page flow and form rules: no DOM, no network, so they can be unit-tested with Node.
//   landing (#/)  ->  login (#/login)  ->  the product (#/app)        plus the public evaluation page.

export const ROUTES = ["landing", "login", "verify", "app", "evaluation"];

/** Sections of the landing page that "#/example" and friends scroll to. */
export const ANCHORS = ["example", "principles", "evidence"];

function firstSegment(hash) {
  return String(hash || "").replace(/^#\/?/, "").split(/[/?]/)[0];
}

/** "#/app" -> "app"; a landing section ("#/example") is the landing page; anything unknown or empty too. */
export function parseRoute(hash) {
  const name = firstSegment(hash);
  return ROUTES.includes(name) ? name : "landing";
}

/** "#/example" -> "example": which landing section to scroll to, or null. */
export function parseAnchor(hash) {
  const name = firstSegment(hash);
  return ANCHORS.includes(name) ? name : null;
}

/**
 * Where to send the visitor instead of the page they asked for, or null to show it.
 * The product needs a session; the login page is pointless once there is one. When accounts are off
 * (me.enabled is false) everyone counts as signed in and the login page is never shown.
 */
export function guard(route, me) {
  if (route === "app" && !me.authenticated) return "#/login";
  if (route === "login" && me.authenticated) return "#/app";
  return null;
}

/** "3 of 5 questions left today" and, for guests, what an account gets. Empty when nothing is limited. */
export function quotaText(me) {
  if (!me || me.remaining == null || me.limit == null) return "";
  const base = `${me.remaining} of ${me.limit} questions left today`;
  if (me.kind === "guest") return `${base} as a guest. A free account gets ${me.user_limit} a day.`;
  return `${base}.`;
}

const EMAIL = /^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$/;

/** First problem with the sign-in or sign-up fields, or null. The server checks again; this just saves a round trip. */
export function checkCredentials(mode, email, password) {
  if (!EMAIL.test(String(email).trim())) return "Enter a valid email address.";
  if (mode === "signup" && (password.length < 8 || password.length > 128)) return "Use a password of 8 to 128 characters.";
  if (!password) return "Enter your password.";
  return null;
}

/** Who the header says is signed in. */
export function whoLabel(me) {
  if (!me || !me.authenticated || !me.enabled) return "";
  return me.kind === "guest" ? "Guest" : me.email;
}

/** 49333 -> "49,000": the landing page says "about 49,000 words". */
export function approxWords(n) {
  return Number.isFinite(n) && n > 0 ? (Math.round(n / 1000) * 1000).toLocaleString("en-US") : "";
}

/* ---------- the visitor's own document ---------- */

export const FILE_TYPES = [".pdf", ".md", ".markdown", ".txt"];
export const ACCEPT = FILE_TYPES.join(",");

/** 2457600 -> "2.3 MB"; small files in KB. */
export function formatBytes(n) {
  return n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`;
}

/** The same quick checks the server makes, so an obviously bad file never leaves the browser. Returns a message or null. */
export function checkFile(file, limits) {
  const maxMb = limits?.max_mb ?? 5, maxPages = limits?.max_pages ?? 50;
  if (!FILE_TYPES.some((type) => file.name.toLowerCase().endsWith(type))) return "That file type isn't supported. Upload a PDF, Markdown or text file.";
  if (file.size <= 0) return `${file.name} is empty.`;
  if (file.size > maxMb * 1048576) return `This file is too large. ${file.name} is ${formatBytes(file.size)}. The limit is ${maxMb} MB or ${maxPages} pages.`;
  return null;
}

/** 60 -> "an hour", 120 -> "2 hours", 30 -> "30 minutes" */
export function ttlText(minutes) {
  if (minutes >= 60 && minutes % 60 === 0) return minutes === 60 ? "an hour" : `${minutes / 60} hours`;
  return `${minutes} minutes`;
}

/** The privacy note, worded to match what the server really does. */
export function privacyText(limits) {
  return `Your file is deleted when you remove it, sign out, or after ${ttlText(limits?.ttl_minutes ?? 60)} of no activity, and is never added to the sample docs.`;
}

/** The three progress rows while a document is indexed. */
export function stageRows(doc) {
  const order = ["reading", "splitting", "indexing"];
  const at = order.indexOf(doc.stage);
  const status = (i) => (i < at ? "done" : i === at ? "active" : "todo");
  return [
    { label: "Reading the file", state: status(0), detail: "" },
    { label: "Splitting into passages", state: status(1), detail: "" },
    { label: "Building the search index", state: status(2),
      detail: at === 2 && doc.passages_total ? `${doc.passages_done} of ${doc.passages_total} passages` : "" },
  ];
}

/** The quota meter: dashes when the limit is small, otherwise one bar. */
export function meterModel(me) {
  if (!me || me.limit == null || me.remaining == null) return null;
  return { remaining: me.remaining, limit: me.limit, segmented: me.limit <= 10 };
}

/** What the workspace is asking: the sample docs, the visitor's file, or nothing yet. */
export function sourceLabel(source, doc, corpus) {
  if (source === "sample") return corpus.name || "the documents";
  return doc?.state === "ready" ? doc.filename : "your document";
}

/** Text in the header's document pill. */
export function docPillText(source, doc, corpus) {
  if (source === "sample") return `${corpus.name || "Documents"}${corpus.pages ? ` · ${corpus.pages} pages` : ""}`;
  if (doc?.state === "ready") return doc.filename;
  if (doc?.state === "indexing") return `Indexing ${doc.filename}…`;
  return "No document";
}

/** Footer line under each example card, by kind. */
export const EXAMPLE_NOTES = {
  answered: "One answer, one verified quote",
  multi: "Combines passages from several pages",
  abstain: "Stops at the gate, no model call",
};

/** "#/verify?token=abc.def" -> "abc.def" (or "" when there is none). */
export function parseToken(hash) {
  const query = String(hash || "").split("?")[1] || "";
  return new URLSearchParams(query).get("token") || "";
}
