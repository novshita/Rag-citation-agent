// The landing page: a static template in index.html, with the live "page to proof" animation in its middle.

import { h } from "./dom.js";
import { createBelt } from "./belt.js";
import { fillFacts } from "./facts.js";

/** Returns { element, destroy }. `destroy` stops the animation when the visitor leaves the page. */
export function buildLanding({ corpus, showcase }) {
  const fragment = document.getElementById("tpl-landing").content.cloneNode(true);
  fillFacts(fragment, corpus);
  const slot = fragment.querySelector('[data-slot="belt"]');
  const belt = showcase.length ? createBelt(showcase) : null;
  if (belt) slot.replaceWith(belt.element); else slot.remove();
  const element = h("div", { class: "landing" });
  element.append(fragment);
  return { element, destroy: () => belt?.destroy() };
}
