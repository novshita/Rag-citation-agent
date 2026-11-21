// The login page: sign in, create an account, or continue as a guest. Then the workspace.
// With email confirmation on, creating an account ends in "check your email" instead of a session.

import { h, icon } from "./dom.js";
import { checkCredentials } from "./flow.js";

const RESEND_WAIT = 60;      // seconds before the resend button works again (the server also limits it)

/**
 * `api(path, body)` posts JSON and resolves to the parsed reply, or throws an Error with a readable message
 * (and the HTTP `status`). `onDone(me)` is called with the new session once the visitor is in.
 */
export function buildLogin({ api, onDone, me }) {
  let mode = "login";            // "login" | "signup"
  let busy = false;
  let waitTimer = null;

  const email = h("input", { id: "email", name: "email", type: "email", autocomplete: "email", required: true, maxlength: "254", spellcheck: "false" });
  const password = h("input", { id: "password", name: "password", type: "password", autocomplete: "current-password", required: true, maxlength: "128" });
  const passwordHint = h("p", { class: "field-hint", id: "password-hint", hidden: true },
    me.verification ? "At least 8 characters. We'll email you a link to confirm your address." : "At least 8 characters.");
  const error = h("p", { class: "form-error", role: "alert", id: "form-error" });
  const resend = h("button", { class: "btn-secondary wide", type: "button", id: "resend-login", hidden: true,
    onclick: () => sendAgain(resend) }, "Send me a new confirmation email");
  const submit = h("button", { class: "btn-primary", type: "submit" }, "Sign in");
  const guestButton = h("button", { class: "btn-secondary wide", type: "button", id: "guest" }, "Continue as a guest");
  const tabs = {
    login: h("button", { type: "button", role: "tab", id: "tab-login", onclick: () => setMode("login") }, "Sign in"),
    signup: h("button", { type: "button", role: "tab", id: "tab-signup", onclick: () => setMode("signup") }, "Create account"),
  };

  function setMode(next) {
    mode = next;
    for (const [name, tab] of Object.entries(tabs)) tab.setAttribute("aria-selected", String(name === mode));
    submit.textContent = mode === "login" ? "Sign in" : "Create account";
    password.setAttribute("autocomplete", mode === "login" ? "current-password" : "new-password");
    password.setAttribute("aria-describedby", mode === "signup" ? "password-hint" : "form-error");
    passwordHint.hidden = mode !== "signup";
    error.textContent = "";
    resend.hidden = true;
  }

  function setBusy(value) {
    busy = value;
    for (const control of [submit, guestButton, email, password, tabs.login, tabs.signup, resend]) control.disabled = value;
    form.setAttribute("aria-busy", String(value));
  }

  async function run(path, body, problem = null) {
    error.textContent = "";
    resend.hidden = true;
    if (problem) { error.textContent = problem; return; }
    setBusy(true);
    try {
      const reply = await api(path, body);
      if (reply && reply.verify) { setBusy(false); showPending(reply.email); return; }       // account made, email not confirmed yet
      onDone(reply);
    } catch (failure) {
      error.textContent = failure.message;
      resend.hidden = failure.status !== 403;                  // "confirm your email first": offer a new link
      setBusy(false);
      (path === "/auth/guest" ? guestButton : password).focus();
    }
  }

  /** Ask for a new confirmation email, then keep the button quiet for a minute. */
  async function sendAgain(button, note = null) {
    button.disabled = true;
    try {
      await api("/auth/resend", { email: email.value.trim() });
      if (note) { note.textContent = "Sent again. If it doesn't arrive within a minute, check your spam folder."; note.className = "mail-note ok"; }
      else { error.textContent = "If that account is waiting for confirmation, a new link is on its way."; }
    } catch (failure) {
      if (note) { note.textContent = failure.message; note.className = "mail-note"; } else { error.textContent = failure.message; }
    }
    let left = RESEND_WAIT;
    const label = button.textContent;
    button.textContent = `${label} (${left}s)`;
    clearInterval(waitTimer);
    waitTimer = setInterval(() => {
      left -= 1;
      if (left <= 0) { clearInterval(waitTimer); button.disabled = false; button.textContent = label; }
      else button.textContent = `${label} (${left}s)`;
    }, 1000);
  }

  const form = h("form", { class: "auth-form", novalidate: true,
    onsubmit: (event) => {
      event.preventDefault();
      if (busy) return;
      const problem = checkCredentials(mode, email.value, password.value);
      run(mode === "login" ? "/auth/login" : "/auth/signup", { email: email.value.trim(), password: password.value }, problem);
    } },
    h("div", { class: "field" }, h("label", { for: "email" }, "Email"), email),
    h("div", { class: "field" }, h("label", { for: "password" }, "Password"), password, passwordHint),
    error,
    resend,
    submit);

  guestButton.addEventListener("click", () => { if (!busy) run("/auth/guest", {}); });
  setMode("login");

  const formView = [
    h("h1", {}, "Try the demo"),
    h("p", { class: "auth-sub" }, "Sign in to ask questions about the FastAPI documentation or your own document, or look around as a guest."),
    h("div", { class: "tabs", role: "tablist", "aria-label": "Sign in or create an account" }, tabs.login, tabs.signup),
    form,
    h("div", { class: "divider" }, h("span", {}, "or")),
    guestButton,
    h("p", { class: "field-hint center" },
      `Guests can ask ${me.guest_limit ?? 5} questions a day, no sign-up. A free account gets ${me.user_limit ?? 30}.`),
  ];
  const card = h("div", { class: "auth-card" }, ...formView);

  function showPending(address) {
    const note = h("p", { class: "mail-note", role: "status" });
    const again = h("button", { class: "btn-secondary", type: "button", id: "resend-pending", onclick: () => sendAgain(again, note) }, "Resend email");
    card.replaceChildren(
      h("span", { class: "mail-ico" }, icon("mail", 24)),
      h("h1", {}, "Check your email"),
      h("p", { class: "auth-sub mail-sent" }, "We sent a confirmation link to ", h("b", {}, address),
        ". Open it to finish creating your account. The link works for 24 hours."),
      h("div", { class: "mail-actions" }, again,
        h("button", { class: "link-btn", type: "button", id: "other-email", onclick: () => { clearInterval(waitTimer); card.replaceChildren(...formView); setMode("signup"); email.focus(); } }, "Use a different email")),
      note,
      h("p", { class: "field-hint" }, "Can't find it? Check your spam folder. Your email is used only to confirm your account."));
  }

  const element = h("section", { class: "auth-wrap" },
    h("a", { class: "back", href: "#/" }, "← Back"),
    card,
    h("p", { class: "fine" }, "Passwords are stored hashed, never in plain text. The questions you ask are saved in the server's query log, including questions about your own document. Your own document itself is never saved."));
  return { element, focus: () => email.focus() };
}
