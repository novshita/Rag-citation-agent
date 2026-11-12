// The landing page: what the project is, the live "page to proof" animation, and a way in.

import { h, icon } from "./dom.js";
import { createBelt } from "./belt.js";

function feature(name, title, text) {
  return h("div", { class: "feature" }, icon(name, 20), h("h3", {}, title), h("p", {}, text));
}

/** Returns { element, destroy }. `destroy` stops the animation when the visitor leaves the page. */
export function buildLanding({ corpus, showcase, me }) {
  const belt = showcase.length ? createBelt(showcase) : null;
  const way = me.enabled ? "Continue as a guest, or create a free account. No credit card, no email sent." : "";

  const element = h("div", { class: "landing" },
    h("section", { class: "land-hero" },
      h("span", { class: "pill" }, corpus.tagline || "Grounded question answering"),
      h("h1", { class: "land-title" }, "Ask the documents.", h("br"), "See the proof."),
      h("p", { class: "land-text" },
        "Every answer is written only from passages in the indexed documents. Every quote is checked against its source by code, not by AI. If the documents don't say, it says so."),
      h("div", { class: "cta-row" },
        h("a", { class: "btn-primary btn-link", href: "#/login", id: "cta-try" }, "Try the demo", icon("arrow", 18)),
        h("a", { class: "btn-secondary btn-link", href: "#/evaluation" }, "How it was evaluated")),
      way ? h("p", { class: "hint" }, way) : null),
    belt ? belt.element : null,
    h("section", { class: "land-features" },
      feature("book", "Only your documents", "No outside knowledge. Answers use retrieved passages only."),
      feature("shield", "Every quote verified", "Code checks each quote against its source. Fake quotes are removed."),
      feature("minus", "Refuses to guess", "If no passage is relevant enough, it stops. No model is called.")),
    h("section", { class: "land-proof" },
      h("p", {}, "On questions the documents can't answer, a plain chatbot answered 100% of them anyway. This system answered 25%, and 136 of its 137 citations checked out."),
      h("a", { href: "#/evaluation" }, "See how it was measured, including what it does not show →")),
  );
  return { element, destroy: () => belt?.destroy() };
}
