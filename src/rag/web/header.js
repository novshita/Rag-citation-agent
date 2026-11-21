// The site header. Its look and links depend on the page: a light bar on the landing page, and a
// transparent bar over the purple ribbon on the product pages. Everything is set as text, never as HTML.

import { h, icon } from "./dom.js";
import { whoLabel } from "./flow.js";

export const REPO = "https://github.com/novshita/rag-citation-agent";

function brand(tone) {
  return h("a", { class: "sh-brand", href: "#/", "aria-label": "RAG Citation Agent, home" },
    h("img", { src: tone === "dark" ? "/static/logo-dark.svg" : "/static/logo.svg", width: "46", height: "39", alt: "" }),
    h("span", { class: "sh-rule", "aria-hidden": "true" }),
    h("span", { class: "sh-name" }, h("span", { class: "sh-rag" }, "RAG"), h("span", { class: "sh-sub" }, "Citation Agent")));
}

function account(me, onSignOut, tone) {
  if (!me.enabled) return null;
  const who = whoLabel(me);
  if (!who) return h("a", { class: "sh-link", href: "#/login" }, "Sign in");
  return h("span", { class: "sh-account" },
    h("span", { class: "sh-who", title: who }, who),
    h("button", { class: "link-btn", type: "button", onclick: onSignOut }, "Sign out"));
}

/**
 * Replace the contents of the header element for `view` ("landing", "login", "app" or "evaluation").
 * `me` is the session; `onSignOut` and `onMenu` are callbacks.
 */
export function renderHeader(el, { view, me, onSignOut, onMenu }) {
  const tone = view === "landing" ? "light" : "dark";
  el.dataset.tone = tone;
  const current = (name) => (view === name ? "page" : null);

  let nav, actions;
  if (tone === "light") {
    nav = h("nav", { class: "sh-nav", "aria-label": "Sections" },
      h("a", { href: "#/example" }, "How it works"), h("a", { href: "#/principles" }, "Principles"),
      h("a", { href: "#/evidence" }, "Evidence"), h("a", { href: "#/evaluation", "aria-current": current("evaluation") }, "Evaluation"));
    actions = h("div", { class: "sh-actions" },
      h("a", { class: "sh-link", href: REPO, target: "_blank", rel: "noopener" }, icon("github", 18), h("span", { class: "sh-link-text" }, "GitHub")),
      account(me, onSignOut, tone),
      h("a", { class: "sh-cta", href: "#/login", "data-cta": "" }, "Try the demo"));
  } else {
    nav = h("nav", { class: "sh-nav", "aria-label": "Sections" },
      h("a", { href: "#/app", "aria-current": current("app") }, "Ask"), h("a", { href: "#/example" }, "How it works"),
      h("a", { href: "#/app" }, "Documents"), h("a", { href: "#/evaluation", "aria-current": current("evaluation") }, "Evaluation"));
    actions = h("div", { class: "sh-actions" },
      account(me, onSignOut, tone),
      h("a", { class: "sh-pill", href: REPO, target: "_blank", rel: "noopener" }, "GitHub"),
      view === "app"
        ? h("button", { class: "sh-menu", id: "menu-btn", type: "button", "aria-controls": "sidebar", "aria-expanded": "false",
            "aria-label": "Show documents and settings", onclick: onMenu }, icon("menu", 18), h("span", { class: "sh-menu-text" }, "Documents"))
        : null);
  }

  el.replaceChildren(h("div", { class: "sh-in" }, brand(tone), tone === "light" ? nav : null, h("span", { class: "sh-spacer" }),
    tone === "dark" ? nav : null, tone === "dark" ? h("span", { class: "sh-spacer" }) : null, actions));
}
