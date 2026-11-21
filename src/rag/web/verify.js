// The page the confirmation link opens: it sends the link's token to the server, then signs the person in.

import { h, icon } from "./dom.js";
import { parseToken } from "./flow.js";

export function buildVerify({ api, onDone }) {
  const token = parseToken(location.hash);
  history.replaceState(null, "", "#/verify");           // keep the one-time token out of the address bar and history

  const state = h("p", { class: "verify-state", role: "status" }, h("span", { class: "spin" }), "Confirming your email…");
  const card = h("div", { class: "auth-card" },
    h("span", { class: "mail-ico" }, icon("mail", 24)),
    h("h1", {}, "Confirming your email"),
    state);

  const fail = (message) => card.replaceChildren(
    h("span", { class: "mail-ico" }, icon("alertc", 24)),
    h("h1", {}, "We couldn't confirm that link"),
    h("div", { class: "verify-fail", role: "alert" }, h("p", {}, message)),
    h("a", { class: "btn-secondary btn-link", href: "#/login" }, "Back to sign in"));

  if (!token) fail("This confirmation link isn't valid. Open the link from the email, or sign up again to get a new one.");
  else api("/auth/verify", { token }).then(onDone, (error) => fail(error.message));

  return { element: h("section", { class: "auth-wrap" }, card) };
}
