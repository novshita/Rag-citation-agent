// A slide-over panel that shows the visitor's own uploaded document, so they can check it is the right file.
// The server keeps the file in memory for the session and sends it back only to the session that uploaded it.
// PDFs are shown by the browser's own viewer; text and Markdown are shown as plain text (never parsed as HTML).

import { h, icon } from "./dom.js";

let open = null;   // { close } while the panel is on screen

/** Fetch the file as a Blob. Throws an Error with a readable message. */
async function fetchFile() {
  let response;
  try {
    response = await fetch("/documents/file", { cache: "no-store" });
  } catch {
    throw new Error("Couldn't reach the server. Check your connection and try again.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : "Couldn't open the document.");
  }
  return response.blob();
}

export const isPdf = (name) => /\.pdf$/i.test(name || "");

/** Show the document panel for `doc` ({ filename, size_bytes, pages }). `meta` is the line under the name. */
export function openViewer(doc, meta, opener) {
  closeViewer(false);
  const pdf = isPdf(doc.filename);
  const body = h("div", { class: "viewer-body" }, h("div", { class: "viewer-state" }, h("span", { class: "spin small" }), h("p", {}, "Opening your document…")));
  const newTab = h("a", { class: "btn-secondary viewer-tab", target: "_blank", rel: "noopener", hidden: true }, "Open in a new tab");
  const closeButton = h("button", { class: "viewer-close", type: "button", "aria-label": "Close the document", onclick: () => closeViewer() }, icon("close", 18));
  const panel = h("aside", { class: "viewer", role: "dialog", "aria-modal": "true", "aria-labelledby": "viewer-title", tabindex: "-1" },
    h("header", { class: "viewer-head" },
      h("div", { class: "viewer-title" }, h("h2", { id: "viewer-title", title: doc.filename }, doc.filename), meta ? h("p", {}, meta) : null),
      newTab, closeButton),
    body);
  const backdrop = h("div", { class: "viewer-backdrop", onclick: () => closeViewer() });
  const root = h("div", { class: "viewer-root" }, backdrop, panel);
  let url = null;
  let alive = true;

  const onKey = (event) => {
    if (event.key === "Escape") { event.preventDefault(); closeViewer(); }
    else if (event.key === "Tab") {                        // keep keyboard focus inside the panel
      const items = [...panel.querySelectorAll("a[href],button,iframe")].filter((el) => !el.hidden && !el.disabled);
      if (!items.length) return;
      const first = items[0], last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  };
  document.addEventListener("keydown", onKey);
  document.body.append(root);
  document.body.classList.add("viewer-open");
  requestAnimationFrame(() => root.classList.add("in"));
  closeButton.focus();

  open = {
    close(restoreFocus = true) {
      alive = false;
      document.removeEventListener("keydown", onKey);
      if (url) URL.revokeObjectURL(url);
      root.remove();
      document.body.classList.remove("viewer-open");
      if (restoreFocus && opener?.isConnected) opener.focus();
    },
  };

  fetchFile().then(async (blob) => {
    if (!alive) return;
    if (pdf) {
      url = URL.createObjectURL(new Blob([blob], { type: "application/pdf" }));
      body.replaceChildren(h("iframe", { class: "viewer-pdf", src: url, title: `${doc.filename}, shown as in the file` }));
    } else {
      const text = await blob.text();
      if (!alive) return;
      url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
      body.replaceChildren(h("pre", { class: "viewer-text", tabindex: "0" }, text));
    }
    newTab.href = url;
    newTab.hidden = false;
  }).catch((error) => {
    if (!alive) return;
    body.replaceChildren(h("div", { class: "viewer-state error", role: "alert" }, icon("alertc", 22), h("p", {}, error.message)));
  });
}

export function closeViewer(restoreFocus = true) {
  const current = open;
  open = null;
  current?.close(restoreFocus);
}
