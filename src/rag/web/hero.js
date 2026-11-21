// The empty ask page: headline, call to action and the animated example trace (a static template in index.html).

import { h } from "./dom.js";
import { fillFacts } from "./facts.js";

export function buildHero(corpus) {
  const fragment = document.getElementById("tpl-hero").content.cloneNode(true);
  fillFacts(fragment, corpus);
  const element = h("div", { class: "hero-wrap" });
  element.append(fragment);
  for (const link of element.querySelectorAll("a[data-focus]")) {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      document.getElementById(link.dataset.focus)?.focus();
    });
  }
  return element;
}
