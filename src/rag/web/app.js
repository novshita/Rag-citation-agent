// RAG Citation Agent: front end. Plain JavaScript, no build step.
// Pages: landing (#/), login (#/login), the product (#/app) and the evaluation (#/evaluation).
// All text from the server is inserted with textContent, never as HTML, so a document passage
// cannot inject markup. The only innerHTML in the front end is the fixed icon set in dom.js.

import {
  barPercent, errorInfo, excerpt, formatMeta, gateLabel, gateReason, plural, splitHighlight, statusInfo, verifiedLabel,
} from "./format.js";
import { h, icon } from "./dom.js";
import {
  ACCEPT, EXAMPLE_NOTES, checkFile, docPillText, formatBytes, guard, meterModel, parseAnchor, parseRoute, privacyText, sourceLabel, stageRows,
} from "./flow.js";
import { renderHeader } from "./header.js";
import { getDocument, removeDocument, sendDocument } from "./upload.js";
import { closeViewer, openViewer } from "./viewer.js";
import { buildLanding } from "./landing.js";
import { buildLogin } from "./login.js";
import { buildVerify } from "./verify.js";

/* ---------- state ---------- */

const state = {
  corpus: { name: "Indexed documents", note: "", tagline: "", pages: 0, groups: [], examples: [], top_k: 5, min_score: 0, llm: "" },
  topK: 5,
  phase: "idle", // idle | loading | done | error
  question: "",
  result: null,
  error: null,
  controller: null,
  expanded: new Set(),     // sample-doc groups that are open
  showAll: new Set(),      // groups that show every file, not just the first few
  source: "sample",         // what questions are answered from: "sample" or "mine" (the visitor's upload)
  doc: { state: "none" },   // the visitor's uploaded document, as the server reports it
  uploadError: null,
  showcase: [],   // example pages for the "page to proof" demo (static/showcase.json)
  me: { enabled: false, authenticated: true, kind: null, email: null, remaining: null, limit: null, user_limit: null, guest_limit: null },
};
let page = null;   // the page on screen, so its animation can be stopped when the visitor leaves
let currentView = null;

const ui = {}; // elements of the ask view, set when it is built

/* ---------- the workspace: source, ask, how it works ---------- */

const PREVIEW_DOCS = 3;
let pollTimer = null;

const canAsk = () => state.source === "sample" || state.doc.state === "ready";
const sourceName = () => sourceLabel(state.source, state.doc, state.corpus);
const uploadLimits = () => state.corpus.uploads;      // null when this server has no uploads

/** Replace one of the workspace's pieces with a freshly built one. */
function swap(key, make) {
  if (!ui[key]) return;
  const next = make();
  ui[key].replaceWith(next);
  ui[key] = next;
}

function repaintSource() { swap("source", renderSourceCard); }

function repaintAsk() {
  const typed = ui.input ? ui.input.value : state.question;
  swap("ask", renderAskCard);
  ui.input.value = typed;
  paintResult();
}

function afterDocumentChange() {
  repaintSource();
  repaintAsk();
  paintHeader();
  if (state.doc.state === "indexing") schedulePoll();
}

/* ---- source card ---- */

function renderSourceCard() {
  const limits = uploadLimits();
  const tab = (name, text) => h("button", { type: "button", role: "tab", "aria-selected": String(state.source === name),
    onclick: () => setSource(name) }, text);
  return h("section", { class: "panel", id: "source" },
    h("p", { class: "eyebrow" }, "Source"),
    h("h2", { class: "panel-title" }, "What should I answer from?"),
    limits ? h("div", { class: "seg", role: "tablist", "aria-label": "Choose what to answer from" }, tab("sample", "Sample docs"), tab("mine", "Your document")) : null,
    state.source === "sample" ? renderSample() : renderMine(limits));
}

function renderSample() {
  const c = state.corpus;
  const total = c.groups.reduce((n, g) => n + g.pages, 0) || 1;
  return h("div", { class: "sample" },
    h("h3", { class: "sample-name" }, c.name),
    h("p", { class: "sample-note" }, [plural(c.pages, "page"), c.note, "ready now"].filter(Boolean).join(" · ")),
    c.groups.map((g) => renderGroup(g, total)));
}

function renderGroup(group, total) {
  const open = state.expanded.has(group.name);
  const all = state.showAll.has(group.name);
  const docs = open && !all ? group.docs.slice(0, PREVIEW_DOCS) : group.docs;
  const hidden = group.docs.length - docs.length;
  const toggle = () => { open ? state.expanded.delete(group.name) : state.expanded.add(group.name); repaintSource(); };
  return h("div", { class: "group" },
    h("button", { class: "group-head", type: "button", "aria-expanded": String(open), onclick: toggle },
      icon("folder", 18), h("span", { class: "gname" }, group.name), h("span", { class: "gcount" }, plural(group.pages, "page")),
      h("span", { class: `chev-i${open ? " open" : ""}` }, icon("chevron", 16))),
    h("div", { class: "gbar", "aria-hidden": "true" }, h("i", { style: `width:${Math.round(group.pages / total * 100)}%` })),
    open ? h("ul", { class: "doclist" }, docs.map((d) => h("li", { title: d }, d))) : null,
    open && hidden > 0
      ? h("button", { class: "more-btn", type: "button", onclick: () => { state.showAll.add(group.name); repaintSource(); } },
          `+ ${hidden} more ${hidden === 1 ? "page" : "pages"}`)
      : null);
}

function renderMine(limits) {
  const doc = state.doc;
  const problem = state.uploadError || (doc.state === "error" ? doc.error : null);
  const note = h("div", { class: "privacy" }, icon("lock", 16),
    h("p", {}, h("b", {}, "Private to this session. "), privacyText(limits)));
  if (doc.state === "indexing") return h("div", { class: "mine" }, renderIndexing(doc), note);
  if (doc.state === "ready" && !problem) return h("div", { class: "mine" }, renderReady(doc), note);
  return h("div", { class: "mine" },
    problem ? h("div", { class: "upload-error", role: "alert" }, icon("alertc", 18), h("p", {}, problem)) : null,
    renderDropzone(problem ? "Try another file" : "Drop a file here", limits), note);
}

function renderDropzone(title, limits) {
  const zone = h("div", { class: "dropzone", role: "button", tabindex: "0", "aria-label": `${title}, or browse your computer`,
    onclick: pickFile,
    onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pickFile(); } },
    ondragover: (e) => { e.preventDefault(); zone.classList.add("over"); },
    ondragleave: () => zone.classList.remove("over"),
    ondrop: (e) => {
      e.preventDefault();
      zone.classList.remove("over");
      const files = [...e.dataTransfer.files];
      if (files.length > 1) { state.uploadError = "Upload one file at a time."; repaintSource(); }
      else if (files[0]) handleFile(files[0]);
    } },
    h("span", { class: "dz-ico" }, icon("upload", 22)),
    h("p", { class: "dz-title" }, title),
    h("p", { class: "dz-sub" }, "or ", h("button", { type: "button", class: "dz-browse", onclick: (e) => { e.stopPropagation(); pickFile(); } }, "browse your computer")),
    h("div", { class: "dz-types" }, ["PDF", "Markdown", "Text"].map((t) => h("span", {}, t))),
    h("p", { class: "dz-limits" }, `Up to ${limits.max_mb} MB · ${limits.max_pages} pages · one file at a time`));
  return zone;
}

const extOf = (name) => (name.includes(".") ? name.split(".").pop().toUpperCase().slice(0, 4) : "FILE");

function fileCard(doc, extra) {
  const size = [formatBytes(doc.size_bytes), doc.pages ? plural(doc.pages, "page") : ""].filter(Boolean).join(" · ");
  const view = (event) => openViewer(doc, size, event.currentTarget);
  return h("div", { class: `filecard viewable${extra ? ` ${extra}` : ""}`, role: "button", tabindex: "0", title: "Click to view this document",
    "aria-label": `View ${doc.filename}`, onclick: view,
    onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); view(e); } } },
    h("span", { class: "ftype" }, extOf(doc.filename)),
    h("div", { class: "fmain" }, h("p", { class: "fname", title: doc.filename }, doc.filename),
      extra === "ready" ? h("p", { class: "fready" }, icon("tick", 14), "Ready to ask") : h("p", { class: "fsize" }, size)),
    h("span", { class: "fview", "aria-hidden": "true" }, icon("eye", 17)));
}

function renderIndexing(doc) {
  return h("div", { class: "indexing" },
    fileCard(doc),
    h("div", { class: "prog-head" }, h("b", {}, "Indexing your document"), h("span", {}, `${doc.percent || 0}%`)),
    h("div", { class: "progress", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(doc.percent || 0) },
      h("i", { style: `width:${doc.percent || 0}%` })),
    h("ul", { class: "stages-list" }, stageRows(doc).map((row) =>
      h("li", { class: row.state },
        row.state === "done" ? h("span", { class: "sdone" }, icon("tick", 14)) : row.state === "active" ? h("span", { class: "spin small" }) : h("span", { class: "sdot" }),
        h("div", {}, h("span", { class: "slabel" }, row.label), row.detail ? h("small", {}, row.detail) : null)))),
    h("button", { class: "btn-secondary", type: "button", onclick: removeIt }, "Cancel"));
}

function renderReady(doc) {
  return h("div", { class: "ready" },
    fileCard(doc, "ready"),
    h("div", { class: "chips" },
      h("span", {}, plural(doc.pages, "page")), h("span", {}, plural(doc.passages_total, "passage")), h("span", {}, `Indexed in ${doc.seconds} s`)),
    h("div", { class: "file-actions" },
      h("button", { class: "btn-secondary", type: "button", onclick: pickFile }, "Replace file"),
      h("button", { class: "danger-link", type: "button", onclick: removeIt }, "Remove and delete")));
}

/* ---- upload actions ---- */

function pickFile() {
  ui.fileInput.value = "";
  ui.fileInput.click();
}

async function handleFile(file) {
  closeViewer(false);
  state.uploadError = null;
  const problem = checkFile(file, uploadLimits());
  if (problem) { state.uploadError = problem; state.doc = { state: "none" }; afterDocumentChange(); return; }
  state.doc = { state: "indexing", stage: "reading", filename: file.name, size_bytes: file.size, percent: 0, pages: 0, passages_done: 0, passages_total: 0 };
  afterDocumentChange();
  try {
    state.doc = await sendDocument(file);
  } catch (error) {
    state.doc = { state: "none" };
    state.uploadError = error.message;
  }
  afterDocumentChange();
}

function schedulePoll() {
  clearTimeout(pollTimer);
  pollTimer = setTimeout(async () => {
    if (state.doc.state !== "indexing" || !ui.source) return;
    try {
      state.doc = await getDocument();
    } catch (error) {
      state.doc = { state: "none" };
      state.uploadError = error.message;
    }
    afterDocumentChange();
  }, 600);
}

async function removeIt() {
  closeViewer(false);
  clearTimeout(pollTimer);
  state.uploadError = null;
  try { await removeDocument(); } catch { /* it is gone, or it will expire */ }
  state.doc = { state: "none" };
  afterDocumentChange();
}

async function refreshDocument() {
  try {
    state.doc = await getDocument();
  } catch {
    state.doc = { state: "none" };
  }
  afterDocumentChange();
}

function setSource(next) {
  if (state.source === next) return;
  closeViewer(false);
  state.controller?.abort();
  state.source = next;
  state.phase = "idle";
  state.result = null;
  state.question = "";
  state.uploadError = null;
  buildAskView();
  paintHeader();
  if (next === "mine") refreshDocument();
}

/* ---- retrieval setting ---- */

function renderRetrievalCard() {
  const set = (value) => { state.topK = Math.min(20, Math.max(1, value)); swap("retrieval", renderRetrievalCard); };
  return h("section", { class: "panel" },
    h("p", { class: "eyebrow" }, "Retrieval setting"),
    h("div", { class: "retr" },
      h("div", {}, h("div", { class: "retr-title", id: "topk-label" }, "Passages to retrieve"),
        h("p", { class: "retr-sub" }, "top-k · more passages, slower answers")),
      h("div", { class: "stepper-ctl", role: "group", "aria-labelledby": "topk-label" },
        h("button", { type: "button", "aria-label": "Fewer passages", disabled: state.topK <= 1, onclick: () => set(state.topK - 1) }, "−"),
        h("output", { "aria-live": "polite" }, String(state.topK)),
        h("button", { type: "button", "aria-label": "More passages", disabled: state.topK >= 20, onclick: () => set(state.topK + 1) }, "+"))));
}

/* ---- ask card ---- */

function renderMeter() {
  const m = meterModel(state.me);
  if (!m) return h("span", { class: "meter-none" });
  const bars = m.segmented
    ? h("span", { class: "dashes", "aria-hidden": "true" }, Array.from({ length: m.limit }, (_, i) => h("i", { class: i < m.remaining ? "on" : "" })))
    : h("span", { class: "meterbar", "aria-hidden": "true" }, h("i", { style: `width:${Math.round(m.remaining / m.limit * 100)}%` }));
  return h("span", { class: "meter" }, bars, h("span", { class: "meter-text", "aria-live": "polite" }, h("b", {}, `${m.remaining} of ${m.limit}`), " questions left today"));
}

function renderAskCard() {
  const limits = uploadLimits();
  const sample = state.source === "sample";
  const name = sourceName();
  ui.meter = renderMeter();
  ui.input = h("input", { id: "question", name: "question", type: "text", autocomplete: "off", maxlength: "2000", disabled: !canAsk(),
    placeholder: canAsk() ? (sample ? "e.g. Which package do I need for file uploads?" : "e.g. What does this document say about…") : "Upload a document to start asking",
    "aria-describedby": "ask-hint" });
  ui.button = h("button", { class: "btn-primary", type: "submit", disabled: !canAsk() || state.phase === "loading" }, "Ask", icon("arrow", 18));
  const guest = state.me.kind === "guest" && state.me.user_limit;
  const hint = sample
    ? `Press Enter to ask. Answers come only from the indexed ${name.replace(/ documentation$/, "")} pages.${guest ? ` A free account gets ${state.me.user_limit} questions a day.` : ""}`
    : canAsk() ? "Press Enter to ask. Answers come only from your document." : "Upload a PDF, Markdown or text file on the left, then ask about it.";
  return h("section", { class: "panel ask-panel" },
    h("div", { class: "ask-top" },
      h("span", { class: "asking" }, icon("file", 16), h("span", { class: "asking-k" }, "Asking:"), h("b", {}, name),
        limits ? h("button", { class: "change", type: "button", onclick: () => { setSource(sample ? "mine" : "sample"); document.getElementById("source")?.scrollIntoView({ block: "nearest", behavior: "smooth" }); } }, "Change") : null),
      ui.meter),
    h("h1", { class: "ws-h1" }, "Ask your documents. ", h("span", {}, "See the proof.")),
    h("form", { class: "ask", onsubmit: (e) => { e.preventDefault(); ask(ui.input.value); } },
      h("label", { for: "question" }, `Ask a question about ${sample ? `the ${name.replace(/ documentation$/, " docs")}` : name}`),
      h("div", { class: "ask-row" }, h("div", { class: "input-wrap" }, icon("search", 18), ui.input), ui.button),
      h("p", { class: "hint", id: "ask-hint" }, hint)));
}

function paintQuota() { swap("meter", renderMeter); }

/* ---- examples, legend and the right column ---- */

function renderExamples() {
  const examples = state.corpus.examples;
  if (!examples.length) return h("span", { hidden: true });
  return h("section", { class: "examples-ws" },
    h("div", { class: "ex-head" }, h("h2", {}, "Not sure what to ask? Start here."), h("span", {}, "Click one to fill the box")),
    h("div", { class: "ex-grid" }, examples.map((e) =>
      h("button", { class: `ex-card ${e.kind}`, type: "button", onclick: () => { ui.input.value = e.question; ui.input.focus(); } },
        h("span", { class: `kind ${e.kind}` }, e.kind === "abstain" ? "Can't answer" : e.tag),
        h("span", { class: "ex-q" }, e.question),
        h("span", { class: "ex-note" }, icon("arrow", 14), EXAMPLE_NOTES[e.kind] || "")))));
}

function renderLegend() {
  const item = (cls, name, text, wide) => h("div", { class: `lg ${cls}${wide ? " wide" : ""}` }, h("span", { class: `lg-pill ${cls}` }, name), h("p", {}, text));
  return h("section", { class: "panel legend" },
    h("h2", { class: "panel-title" }, "Every question ends in one of three results"),
    h("p", { class: "lg-sub" }, "Each is labelled at the top of the answer"),
    h("div", { class: "lg-grid" },
      item("ok", "Answered", "The document covers it. You get the answer and a verified quote for every claim."),
      item("warn", "Partial answer", "Only part is covered. You see what is proven and what the document doesn't say."),
      item("muted", "Abstained", "Nothing relevant enough. It says so instead of guessing, and no model is called.", true)));
}

function renderSteps() {
  const step = (n, title, tag, text, model) => h("li", {},
    h("span", { class: "sn" }, String(n)),
    h("div", {}, h("div", { class: "st-title" }, title, h("span", { class: `tag${model ? " model" : ""}` }, tag)), h("p", {}, text)));
  const llm = state.corpus.llm || "model";
  return h("section", { class: "panel" },
    h("p", { class: "eyebrow" }, "How an answer is made"),
    h("h2", { class: "panel-title" }, "Four steps, checked in code"),
    h("ol", { class: "steps-ws" },
      step(1, "Retrieve", "code", "Find the most relevant passages."),
      step(2, "Relevance gate", "code", "If none is close enough, stop and say “I don't know”."),
      step(3, "Answer with quotes", llm, "The model writes the answer and must quote exact text for every claim.", true),
      step(4, "Verify in code", "code", "Every quote is checked against its source. Fake quotes are removed.")));
}

function renderMeasured() {
  const stat = (value, small, text) => h("div", { class: "m-stat" },
    h("div", { class: "m-num" }, value, small ? h("small", {}, small) : null), h("p", {}, text));
  return h("section", { class: "panel measured" },
    h("p", { class: "eyebrow" }, "Measured, not claimed"),
    h("div", { class: "m-stats" },
      stat("136 / 137", null, "quotes verified in code"),
      stat("25%", "vs 100%", "of unanswerable questions answered")),
    h("a", { class: "m-link", href: "#/evaluation" }, "How it was evaluated", icon("arrow", 15)));
}

/* ---------- ask view ---------- */

function buildAskView() {
  const main = document.getElementById("main");
  ui.fileInput = h("input", { type: "file", accept: ACCEPT, hidden: true, "aria-hidden": "true", tabindex: "-1",
    onchange: (e) => { const file = e.target.files[0]; if (file) handleFile(file); } });
  ui.source = renderSourceCard();
  ui.retrieval = renderRetrievalCard();
  ui.ask = renderAskCard();
  ui.examples = renderExamples();
  ui.legend = renderLegend();
  ui.result = h("div", { id: "result", "aria-live": "polite" });
  main.replaceChildren(h("div", { class: "ws" },
    h("div", { class: "ws-left" }, ui.source, ui.retrieval),
    h("div", { class: "ws-main" }, ui.ask, ui.result, ui.examples, ui.legend),
    h("div", { class: "ws-right" }, renderSteps(), renderMeasured()),
    ui.fileInput));
  paintResult();
}

async function ask(raw) {
  const question = (raw || "").trim();
  if (!question) { ui.input.focus(); return; }
  if (!canAsk()) return;
  state.question = question;
  ui.input.value = question;
  state.controller?.abort();
  state.controller = new AbortController();
  state.phase = "loading";
  paintResult();
  try {
    const response = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, top_k: state.topK, source: state.source }),
      signal: state.controller.signal,
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      const detail = Array.isArray(body.detail) ? "" : body.detail;
      throw Object.assign(new Error(detail || "request failed"), { status: response.status, detail });
    }
    const remaining = response.headers.get("X-Questions-Remaining");
    if (remaining !== null) state.me.remaining = Number(remaining);
    state.result = await response.json();
    state.phase = "done";
  } catch (error) {
    if (error.name === "AbortError") return;
    if (error.status === 401 && state.me.enabled) {      // the session ended: sign in again
      state.me = { ...state.me, authenticated: false };
      location.hash = "#/login";
      return;
    }
    if (error.status === 429) await refreshMe();          // show the real count
    state.error = errorInfo(error.status ?? 0, error.detail);
    state.phase = "error";
  }
  paintQuota();
  paintResult();
}

function paintResult() {
  if (!ui.result) return;
  const idle = state.phase === "idle";
  ui.examples.hidden = !idle || state.source !== "sample";
  ui.legend.hidden = !idle;
  ui.button.disabled = state.phase === "loading" || !canAsk();
  const node = { idle: null, loading: renderLoading, done: () => renderResult(state.result), error: renderError }[state.phase];
  ui.result.replaceChildren(...(node ? [node()] : []));
}

/* ---------- result states ---------- */

function renderLoading() {
  return h("section", { class: "card", "aria-busy": "true" },
    h("div", { class: "loading-title" }, h("span", { class: "spin" }), "Searching and answering..."),
    h("div", { class: "stages" },
      h("span", {}, "Retrieve passages"), h("span", {}, "Relevance gate"),
      h("span", {}, "Write answer with quotes"), h("span", {}, "Verify quotes in code")),
    h("div", { class: "skeleton w80" }), h("div", { class: "skeleton w60" }), h("div", { class: "skeleton block" }),
  );
}

function renderError() {
  const e = state.error;
  return h("section", { class: "card" },
    h("div", { class: "card-head" },
      h("span", { class: "badge err" }, icon("alertc"), "Error"),
      h("span", { class: "conf" }, "No answer was produced")),
    h("p", { class: "err-title" }, e.title),
    h("div", { class: "notice" }, icon("check"),
      h("span", {}, "Nothing was guessed in its place." + (e.hint ? ` ${e.hint}` : ""))),
    h("button", { class: "btn-secondary", type: "button", onclick: () => ask(state.question) }, "Try again"),
  );
}

function renderResult(r) {
  const s = statusInfo(r.status);
  const verified = verifiedLabel(r.verification);
  const reason = (!r.model_called && gateReason(r.gate)) || r.reason;      // gate stops get a plain-language reason
  return h("section", { class: "card" },
    h("div", { class: "card-head" },
      h("span", { class: `badge ${s.tone}` }, icon(s.icon), s.label),
      h("span", { class: "conf" }, "Confidence",
        h("strong", {}, r.confidence.toFixed(2)),
        h("span", { class: "bar", role: "img", "aria-label": `confidence ${r.confidence.toFixed(2)} out of 1` },
          h("i", { style: `width:${barPercent(r.confidence)}%` }))),
      h("span", { class: "meta" }, formatMeta(r.latency_ms, r.tokens))),
    h("p", { class: "answer" }, r.answer),
    reason ? h("p", { class: `notice${r.status === "partial" ? " warn" : ""}` },
      icon("info"), h("span", {}, h("b", {}, "Reason: "), reason)) : null,
    r.status === "abstained" ? renderAbstainNote(r) : null,
    r.claims.length ? h("div", { class: "section-head" },
      h("p", { class: "label" }, "Claims and proof"),
      verified ? h("span", { class: "verified" }, verified) : null) : null,
    r.claims.map((claim, i) => renderClaim(claim, i + 1)),
    renderRetrieved(r),
    r.web ? renderWeb(r.web) : null,
  );
}

function renderAbstainNote(r) {
  return h("div", {},
    r.model_called
      ? h("p", { class: "no-model" }, icon("cpu"), h("b", {}, "The model reviewed the passages"), "and found no answer in them.")
      : h("p", { class: "no-model" }, icon("cpu"), h("b", {}, "No model call was made"), "Stopped at the relevance gate."),
    h("p", { class: "explain" }, "This is the intended behavior: when the documents don't say, the system says so instead of guessing."),
  );
}

function renderClaim(claim, number) {
  return h("div", { class: "claim" },
    h("div", { class: "claim-text" }, h("span", { class: "claim-num" }, `[${number}]`), h("span", {}, claim.text)),
    claim.citations.map(renderProof),
  );
}

function renderProof(c) {
  const where = c.page == null ? c.doc_id : `${c.doc_id}, page ${c.page}`;
  const parts = splitHighlight(c.passage, c.highlight);
  const passage = h("p", { class: "passage" });
  const caption = h("p", { class: "caption" });
  const view = parts ? excerpt(parts) : null;
  const trimmed = parts && (view.before !== parts.before || view.after !== parts.after);
  let expanded = false;

  const toggle = trimmed
    ? h("button", { class: "link-btn", type: "button", "aria-expanded": "false", onclick: () => { expanded = !expanded; paint(); } })
    : null;

  function paint() {
    if (parts) {
      const p = expanded ? parts : view;
      passage.replaceChildren(
        !expanded && view.cutBefore ? "… " : "", p.before, h("mark", {}, p.match), p.after, !expanded && view.cutAfter ? " …" : "");
    } else {
      passage.replaceChildren(c.passage || c.quote);
    }
    caption.textContent = parts
      ? "Highlighted words are the model's quote, matched exactly in the source passage."
      : "The quote was verified in this passage; formatting differences prevent highlighting it here.";
    if (toggle) {
      toggle.textContent = expanded ? "Show less" : "Show full passage";
      toggle.setAttribute("aria-expanded", String(expanded));
    }
  }
  paint();

  return h("div", { class: "proof" },
    h("div", { class: "proof-head" },
      h("span", { class: "file" }, icon("file", 15), where),
      h("span", { class: "found" }, icon("tick", 13), "Quote found in source")),
    passage,
    h("div", { class: "proof-foot" }, caption, toggle),
  );
}

function renderRetrieved(r) {
  const gate = r.gate;
  const threshold = gate.threshold || 0;
  return h("details", { class: "retrieved", open: true },
    h("summary", {},
      h("span", { class: "chev" }, icon("chevron"), `Retrieved passages (${r.retrieved.length})`),
      h("span", { class: `gate-pill ${gate.passed ? "ok" : "stop"}` }, gateLabel(gate))),
    r.retrieved.length ? h("div", { class: "table" },
      r.retrieved.map((p) => h("div", { class: "row" },
        h("div", { class: "row-top" },
          h("span", { class: "score" }, p.score.toFixed(2)),
          h("span", { class: `sbar${p.score < threshold ? " low" : ""}`, "aria-hidden": "true" },
            h("i", { style: `width:${barPercent(p.score)}%` }),
            threshold ? h("b", { style: `left:${barPercent(threshold)}%` }) : null),
          h("span", { class: "rpath" }, p.page == null ? p.doc_id : `${p.doc_id}, page ${p.page}`)),
        h("p", { class: "preview" }, p.text.replace(/\s+/g, " ").trim()))),
      threshold ? h("div", { class: "table-foot" },
        `The dark tick on each bar marks the ${threshold.toFixed(2)} relevance threshold. The gate checks the best match only.`) : null,
    ) : h("p", { class: "caption" }, "Nothing was retrieved."),
  );
}

function renderWeb(web) {
  return h("aside", { class: "web" },
    h("h3", {}, icon("alert", 15), "Web search result · not verified"),
    h("p", { class: "disclaimer" }, web.disclaimer),
    h("p", {}, web.answer),
    web.sources.length ? h("ol", {}, web.sources.map((s) =>
      h("li", {}, h("a", { href: /^https?:\/\//.test(s.url) ? s.url : "#", target: "_blank", rel: "noopener noreferrer" }, s.title || s.url)))) : null,
  );
}

/* ---------- evaluation page (numbers: eval/results_repeats.md, three runs) ---------- */

const REPO = "https://github.com/novshita/rag-citation-agent";

const CHARTS = [
  { title: "Answered a question the documents can't answer", sub: "Lower is better · 8 unanswerable questions, same result in all 3 runs",
    rows: [["Plain chatbot", 100, "100%"], ["Basic RAG", 25, "25%"], ["This system", 25, "25%", true]] },
  { title: "Correct answers", sub: "Higher is better · 22 answerable questions · graded by an LLM against hand-written answers",
    rows: [["Plain chatbot", 86, "86%"], ["Basic RAG", 95, "95%"], ["This system", 89, "89%", true]] },
  { title: "Wrongly refused an answerable question", sub: "Lower is better · 22 answerable questions",
    rows: [["Plain chatbot", 3, "0–5%"], ["Basic RAG", 5, "5%"], ["This system", 9, "9%", true]] },
  { title: "Citations that check out", sub: "The quote is found in its source passage · all 3 runs",
    rows: [["Basic RAG", 99, "142 / 143"], ["This system", 99, "136 / 137", true]] },
];

function buildEvaluationView() {
  const chart = (c) => h("div", { class: "chart" },
    h("h3", {}, c.title), h("p", { class: "sub" }, c.sub),
    c.rows.map(([name, value, label, us]) => h("div", { class: "brow" },
      h("span", {}, name),
      h("span", { class: "btrack", role: "img", "aria-label": `${name}: ${label}` }, h("i", { class: us ? "us" : "", style: `width:${value}%` })),
      h("span", { class: "bval" }, label))));
  const node = (text, code) => h("span", { class: `node${code ? " code" : ""}` }, text);
  const arrow = () => h("span", { class: "arrow", "aria-hidden": "true" }, "→");

  document.getElementById("main").replaceChildren(h("article", { class: "column prose" },
    h("a", { class: "back", href: state.me.authenticated ? "#/app" : "#/" }, "← Back"),
    h("h1", {}, "How it was evaluated"),
    h("p", {}, "30 held-out questions about the FastAPI documentation: 22 the documents can answer (one page, several pages, and three false-premise questions) and 8 they can't. The whole evaluation was run 3 times and compared against a plain chatbot and a basic RAG setup (retrieval and answering, but no relevance gate and no quote check). A separate set of 8 questions was used to tune the relevance threshold, so it was never tuned on the questions it is scored on."),
    h("h2", {}, "Results"),
    CHARTS.map(chart),
    h("h2", {}, "What this shows"),
    h("ul", {},
      h("li", {}, "Retrieval keeps answers grounded. The plain chatbot answered all 8 questions the documents don't cover, from general knowledge. With retrieval it answered 2, in every run."),
      h("li", {}, 'Those 2 are hedged: the reply says the documents don\'t cover the topic, then adds a related fact that is in the documents, with a citation.'),
      h("li", {}, "Code-based quote checking works: 0 of 66 final answers contained an unsupported claim (basic RAG: 1 of 69)."),
    ),
    h("div", { class: "callout" },
      h("strong", {}, "What it does not show"),
      h("ul", {},
        h("li", {}, "This system is not better than basic RAG at avoiding hallucination: both answer the same 2 of 8 unanswerable questions in every run."),
        h("li", {}, "It is slightly worse on correctness (89% vs 95%) and refusals (9% vs 5%), almost entirely from one question stopped by the relevance gate just under its threshold."),
        h("li", {}, "The test set is small, and the plain chatbot is probably flattered because the FastAPI documentation is public."))),
    h("h2", {}, "How it works"),
    h("p", { class: "flow-label" }, "Once: indexing"),
    h("div", { class: "flow" }, node("Documents"), arrow(), node("Passages", true), arrow(), node("Embeddings", true), arrow(), node("Index", true)),
    h("p", { class: "flow-label" }, "Every question"),
    h("div", { class: "flow" }, node("Question"), arrow(), node("Retrieve", true), arrow(), node("Relevance gate", true), arrow(),
      node("Model answers with quotes"), arrow(), node("Verify quotes in code", true), arrow(), node("Answer + confidence")),
    h("p", {}, "Boxes with a blue outline run as ordinary code; there is no model in the gate or the verifier."),
    h("h2", {}, "Read more"),
    h("ul", {},
      h("li", {}, h("a", { href: `${REPO}/blob/main/eval/results_repeats.md`, target: "_blank", rel: "noopener" }, "Full results of all three runs")),
      h("li", {}, h("a", { href: `${REPO}/blob/main/eval/judge_audit.md`, target: "_blank", rel: "noopener" }, "Audit of the LLM judge")),
      h("li", {}, h("a", { href: REPO, target: "_blank", rel: "noopener" }, "Source code and README"))),
  ));
}

/* ---------- session ---------- */

async function refreshMe() {
  try {
    const response = await fetch("/auth/me", { cache: "no-store" });
    if (response.ok) state.me = await response.json();
  } catch { /* keep what we had; the next request will show a real error */ }
}

/** POST JSON. Resolves to the reply; throws an Error whose message is fit to show on the login form. */
async function post(path, body) {
  let response;
  try {
    response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  } catch {
    throw new Error("Couldn't reach the server. Check your connection and try again.");
  }
  const reply = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw Object.assign(new Error(typeof reply.detail === "string" ? reply.detail : "Something went wrong. Please check the fields and try again."),
      { status: response.status });
  }
  return reply;
}

function paintHeader() {
  renderHeader(document.getElementById("site-header"), {
    view: currentView || "landing", me: state.me, onSignOut: signOut,
    docPill: docPillText(state.source, state.doc, state.corpus),
  });
}

async function signOut() {
  closeViewer(false);
  try { await fetch("/auth/logout", { method: "POST" }); } catch { /* the cookie expires on its own */ }
  clearTimeout(pollTimer);
  state.phase = "idle";
  state.result = null;
  state.question = "";
  state.source = "sample";
  state.doc = { state: "none" };
  state.uploadError = null;
  await refreshMe();
  if (location.hash === "#/" || location.hash === "") { currentView = null; route(); } else { location.hash = "#/"; }
}

function scrollToAnchor(name) {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!name) { window.scrollTo(0, 0); return; }
  document.getElementById(name)?.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
}

/* ---------- routing and start ---------- */

function route() {
  const wanted = parseRoute(location.hash);
  const anchor = parseAnchor(location.hash);
  const redirect = guard(wanted, state.me);
  if (redirect) { location.replace(redirect); return; }   // the hashchange this causes draws the right page

  if (wanted === "landing" && currentView === "landing") { scrollToAnchor(anchor); return; }   // same page, just a different section

  closeViewer(false);
  page?.destroy?.();
  page = null;
  ui.result = null;
  currentView = wanted;
  document.body.dataset.view = wanted;
  clearTimeout(pollTimer);
  paintHeader();
  const main = document.getElementById("main");

  if (wanted === "app") {
    if (!state.expanded.size && state.corpus.groups.length && window.innerWidth > 960) state.expanded.add(state.corpus.groups[0].name);
    buildAskView();
    if (state.source === "mine") refreshDocument();
  } else if (wanted === "evaluation") {
    buildEvaluationView();
  } else if (wanted === "verify") {
    page = buildVerify({ api: post, onDone: (me) => { state.me = me; location.hash = "#/app"; } });
    main.replaceChildren(page.element);
  } else if (wanted === "login") {
    page = buildLogin({
      me: state.me, api: post,
      onDone: (me) => { state.me = me; location.hash = "#/app"; },
    });
    main.replaceChildren(page.element);
    page.focus();
  } else {
    page = buildLanding({ corpus: state.corpus, showcase: state.showcase });
    main.replaceChildren(page.element);
  }
  if (wanted === "landing") scrollToAnchor(anchor); else window.scrollTo(0, 0);
}

async function start() {
  await Promise.all([
    refreshMe(),
    fetch("/corpus").then(async (response) => {
      if (!response.ok) return;
      state.corpus = { ...state.corpus, ...(await response.json()) };
      state.topK = state.corpus.top_k || 5;
    }).catch(() => { /* the page still works with defaults if the corpus call fails */ }),
    fetch("/static/showcase.json").then(async (response) => {
      if (response.ok) state.showcase = (await response.json()).cards || [];
    }).catch(() => { /* the animation is optional */ }),
  ]);
  route();
  window.addEventListener("hashchange", route);
}

start();
