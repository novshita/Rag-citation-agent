// RAG Citation Agent: front end. Plain JavaScript, no build step.
// Pages: landing (#/), login (#/login), the product (#/app) and the evaluation (#/evaluation).
// All text from the server is inserted with textContent, never as HTML, so a document passage
// cannot inject markup. The only innerHTML in the front end is the fixed icon set in dom.js.

import {
  barPercent, errorInfo, excerpt, formatMeta, gateLabel, gateReason, plural, splitHighlight, statusInfo, verifiedLabel,
} from "./format.js";
import { h, icon } from "./dom.js";
import { guard, parseRoute, quotaText, whoLabel } from "./flow.js";
import { buildLanding } from "./landing.js";
import { buildLogin } from "./login.js";

/* ---------- state ---------- */

const state = {
  corpus: { name: "Indexed documents", note: "", tagline: "", pages: 0, groups: [], examples: [], top_k: 5, min_score: 0, llm: "" },
  topK: 5,
  phase: "idle", // idle | loading | done | error
  question: "",
  result: null,
  error: null,
  controller: null,
  expanded: new Set(),
  showcase: [],   // example pages for the "page to proof" demo (static/showcase.json)
  me: { enabled: false, authenticated: true, kind: null, email: null, remaining: null, limit: null, user_limit: null, guest_limit: null },
};
let page = null;   // the page on screen, so its animation can be stopped when the visitor leaves

const ui = {}; // elements of the ask view, set when it is built

/* ---------- sidebar ---------- */

const PREVIEW_DOCS = 3;

function renderSidebar() {
  const c = state.corpus;
  const side = document.getElementById("sidebar");
  side.replaceChildren(
    h("section", { class: "side-section" },
      h("p", { class: "label" }, "Indexed documents"),
      h("p", { class: "corpus-name" }, c.name),
      h("p", { class: "corpus-note" }, [plural(c.pages, "page"), c.note].filter(Boolean).join(" · ")),
      ...c.groups.map(renderGroup),
    ),
    h("section", { class: "side-section" },
      h("p", { class: "label" }, "How it works"),
      h("ol", { class: "steps" },
        step(1, "Retrieve", "code", "Find the most relevant passages."),
        step(2, "Relevance gate", "code", 'If none is close enough, stop and say "I don\'t know".'),
        step(3, "Answer with quotes", c.llm || "model", "The model writes the answer and must quote exact text for every claim.", true),
        step(4, "Verify in code", "code", "Every quote is checked against its source. Fake quotes are removed."),
      ),
    ),
    h("section", { class: "side-section" },
      h("p", { class: "label" }, "Advanced"),
      h("div", { class: "stepper" },
        h("span", { id: "topk-label" }, "Passages to retrieve (top-k)"),
        h("div", { class: "stepper-ctl", role: "group", "aria-labelledby": "topk-label" },
          h("button", { type: "button", "aria-label": "Fewer passages", disabled: state.topK <= 1, onclick: () => setTopK(state.topK - 1) }, "−"),
          h("output", { "aria-live": "polite" }, String(state.topK)),
          h("button", { type: "button", "aria-label": "More passages", disabled: state.topK >= 20, onclick: () => setTopK(state.topK + 1) }, "+"),
        ),
      ),
    ),
  );
}

function renderGroup(group) {
  const open = state.expanded.has(group.name);
  const docs = open ? group.docs : group.docs.slice(0, PREVIEW_DOCS);
  const hidden = group.docs.length - docs.length;
  return h("div", { class: "group" },
    h("div", { class: "group-head" }, icon("folder"), group.name, h("span", { class: "pill-count" }, plural(group.pages, "page"))),
    h("ul", { class: "doclist" }, docs.map((d) => h("li", { title: d }, d))),
    group.docs.length > PREVIEW_DOCS
      ? h("button", { class: "more-btn", type: "button", "aria-expanded": String(open), onclick: () => toggleGroup(group.name) },
          open ? "Show fewer" : `+ ${hidden} more ${hidden === 1 ? "page" : "pages"}`)
      : null,
  );
}

function step(n, title, tag, text, isModel = false) {
  return h("li", { class: "step" },
    h("span", { class: "step-num" }, String(n)),
    h("div", {},
      h("div", { class: "step-title" }, title, h("span", { class: `tag${isModel ? " model" : ""}` }, tag)),
      h("p", { class: "step-desc" }, text)),
  );
}

function toggleGroup(name) {
  state.expanded.has(name) ? state.expanded.delete(name) : state.expanded.add(name);
  renderSidebar();
}

function setTopK(value) {
  state.topK = Math.min(20, Math.max(1, value));
  renderSidebar();
}

/* ---------- ask view ---------- */

function buildAskView() {
  const main = document.getElementById("main");
  const c = state.corpus;

  ui.quota = h("p", { class: "hint quota", "aria-live": "polite" });
  paintQuota();
  ui.hero = h("section", { class: "hero" },
    h("span", { class: "pill" }, c.tagline || "Grounded question answering"),
    h("h1", { class: "hero-title" }, "Ask the documents. See the proof."),
    h("p", { class: "hero-text" },
      "Every answer is written only from passages in the indexed documents. Every quote is checked against its source by code, not by AI. If the documents don't say, it says so."),
  );

  ui.input = h("input", { id: "question", name: "question", type: "text", autocomplete: "off", maxlength: "2000",
    placeholder: "e.g. Which package do I need for file uploads?", "aria-describedby": "ask-hint" });
  ui.button = h("button", { class: "btn-primary", type: "submit" }, "Ask");
  const form = h("form", { class: "ask", onsubmit: (e) => { e.preventDefault(); ask(ui.input.value); } },
    h("label", { for: "question" }, "Ask a question about the documents"),
    h("div", { class: "ask-row" },
      h("div", { class: "input-wrap" }, icon("search", 18), ui.input),
      ui.button),
    h("p", { class: "hint", id: "ask-hint" }, "Press Enter to ask. Answers come only from the indexed documents."),
    ui.quota,
  );

  ui.examples = c.examples.length
    ? h("section", { class: "examples" },
        h("p", { class: "label" }, "Try an example"),
        h("div", { class: "example-list" }, c.examples.map((e) =>
          h("button", { class: `example ${e.kind}`, type: "button", onclick: () => ask(e.question) },
            icon("arrow"),
            h("span", { class: "badge-row" }, h("span", { class: `kind ${e.kind}` }, e.tag)),
            h("span", { class: "q" }, e.question)))),
      )
    : null;

  ui.input.value = state.question;
  ui.result = h("div", { id: "result", "aria-live": "polite" });
  main.replaceChildren(h("div", { class: "column" }, ui.hero, form, ui.examples, ui.result));
  paintResult();
}

function paintQuota() {
  if (ui.quota) ui.quota.textContent = quotaText(state.me);
}

async function ask(raw) {
  const question = (raw || "").trim();
  if (!question) { ui.input.focus(); return; }
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
      body: JSON.stringify({ question, top_k: state.topK }),
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
  ui.hero.hidden = state.phase !== "idle";
  ui.button.disabled = state.phase === "loading";
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
    h("a", { class: "back", href: "#/" }, "← Back to the demo"),
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
    throw new Error(typeof reply.detail === "string" ? reply.detail : "Something went wrong. Please check the fields and try again.");
  }
  return reply;
}

function renderAccount() {
  const slot = document.getElementById("account");
  const who = whoLabel(state.me);
  if (!state.me.enabled) { slot.replaceChildren(); return; }
  if (!who) {
    slot.replaceChildren(h("a", { class: "signin", href: "#/login" }, "Sign in"));
    return;
  }
  slot.replaceChildren(
    h("a", { class: "signin", href: "#/app" }, "Demo"),
    h("span", { class: "who", title: who }, who),
    h("button", { class: "link-btn", type: "button", onclick: signOut }, "Sign out"));
}

async function signOut() {
  try { await fetch("/auth/logout", { method: "POST" }); } catch { /* the cookie expires on its own */ }
  state.phase = "idle";
  state.result = null;
  state.question = "";
  await refreshMe();
  renderAccount();
  location.hash = "#/";
  route();
}

/* ---------- routing and start ---------- */

function route() {
  const wanted = parseRoute(location.hash);
  const redirect = guard(wanted, state.me);
  if (redirect) { location.replace(redirect); return; }   // the hashchange this causes draws the right page

  page?.destroy?.();
  page = null;
  ui.result = null;
  document.body.dataset.view = wanted;
  document.body.classList.remove("nav-open");
  document.getElementById("menu-btn").setAttribute("aria-expanded", "false");
  document.getElementById("nav-eval").setAttribute("aria-current", wanted === "evaluation" ? "page" : "false");
  renderAccount();
  const main = document.getElementById("main");

  if (wanted === "app") {
    renderSidebar();
    buildAskView();
  } else if (wanted === "evaluation") {
    buildEvaluationView();
  } else if (wanted === "login") {
    page = buildLogin({
      me: state.me, api: post,
      onDone: (me) => { state.me = me; renderAccount(); location.hash = "#/app"; },
    });
    main.replaceChildren(page.element);
    page.focus();
  } else {
    page = buildLanding({ corpus: state.corpus, showcase: state.showcase, me: state.me });
    main.replaceChildren(page.element);
  }
  window.scrollTo(0, 0);
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
  document.getElementById("menu-btn").addEventListener("click", () => {
    const open = document.body.classList.toggle("nav-open");
    document.getElementById("menu-btn").setAttribute("aria-expanded", String(open));
  });
}

start();
