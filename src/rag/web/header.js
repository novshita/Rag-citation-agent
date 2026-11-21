// The site header: a navigation bar on the landing, login and evaluation pages, and a compact workspace bar
// (current document, links, account) on the ask page. Everything is set as text, never as HTML.

import { h, icon } from "./dom.js";

export const REPO = "https://github.com/novshita/rag-citation-agent";

function brand() {
  return h("a", { class: "sh-brand", href: "#/", "aria-label": "RAG Citation Agent, home" },
    h("img", { src: "/static/logo.svg", width: "46", height: "39", alt: "" }),
    h("span", { class: "sh-rule", "aria-hidden": "true" }),
    h("span", { class: "sh-name" }, h("span", { class: "sh-rag" }, "RAG"), h("span", { class: "sh-sub" }, "Citation Agent")));
}

function accountPill(me, onSignOut) {
  if (!me.enabled || !me.authenticated) return null;
  const label = me.kind === "guest" ? "Guest · Demo" : me.email;
  return h("span", { class: "sh-pillbox" },
    h("i", { class: "dot", "aria-hidden": "true" }),
    h("span", { class: "sh-who", title: label }, label),
    h("button", { class: "sh-signout", type: "button", onclick: onSignOut }, "Sign out"));
}

/**
 * Replace the contents of the header element for `view` ("landing", "login", "app" or "evaluation").
 * `me` is the session, `docPill` the text for the current-document pill, `onSignOut` a callback.
 */
export function renderHeader(el, { view, me, docPill, onSignOut }) {
  el.dataset.view = view;
  const current = (name) => (view === name ? "page" : null);

  if (view === "app") {
    el.replaceChildren(h("div", { class: "sh-in" },
      brand(),
      h("span", { class: "doc-pill", id: "doc-pill" }, icon("file", 16), h("span", {}, docPill || "")),
      h("span", { class: "sh-spacer" }),
      h("nav", { class: "sh-links", "aria-label": "Links" },
        h("a", { href: "#/evaluation" }, "How it was evaluated"),
        h("a", { href: REPO, target: "_blank", rel: "noopener" }, "GitHub")),
      accountPill(me, onSignOut)));
    return;
  }

  const nav = h("nav", { class: "sh-nav", "aria-label": "Sections" },
    h("a", { href: "#/example" }, "How it works"), h("a", { href: "#/principles" }, "Principles"),
    h("a", { href: "#/evidence" }, "Evidence"), h("a", { href: "#/evaluation", "aria-current": current("evaluation") }, "Evaluation"));
  const signedIn = me.enabled && me.authenticated;
  el.replaceChildren(h("div", { class: "sh-in" }, brand(), nav, h("span", { class: "sh-spacer" }),
    h("div", { class: "sh-actions" },
      h("a", { class: "sh-link", href: REPO, target: "_blank", rel: "noopener" }, icon("github", 18), h("span", { class: "sh-link-text" }, "GitHub")),
      signedIn ? accountPill(me, onSignOut) : (me.enabled ? h("a", { class: "sh-link", href: "#/login" }, "Sign in") : null),
      h("a", { class: "sh-cta", href: signedIn || !me.enabled ? "#/app" : "#/login" }, signedIn || !me.enabled ? "Open the workspace" : "Try the demo"))));
}
