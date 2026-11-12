// The login page: sign in, create an account, or continue as a guest. Then the product.

import { h } from "./dom.js";
import { checkCredentials } from "./flow.js";

/**
 * `api(path, body)` posts JSON and resolves to the parsed reply, or throws an Error with a readable message.
 * `onDone(me)` is called with the new session once the visitor is in.
 */
export function buildLogin({ api, onDone, me }) {
  let mode = "login";            // "login" | "signup"
  let busy = false;

  const email = h("input", { id: "email", name: "email", type: "email", autocomplete: "email", required: true, maxlength: "254", spellcheck: "false" });
  const password = h("input", { id: "password", name: "password", type: "password", autocomplete: "current-password", required: true, maxlength: "128" });
  const passwordHint = h("p", { class: "field-hint", id: "password-hint", hidden: true }, "At least 8 characters.");
  const error = h("p", { class: "form-error", role: "alert", id: "form-error" });
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
  }

  function setBusy(value) {
    busy = value;
    for (const control of [submit, guestButton, email, password, tabs.login, tabs.signup]) control.disabled = value;
    form.setAttribute("aria-busy", String(value));
  }

  async function run(path, body, problem = null) {
    error.textContent = "";
    if (problem) { error.textContent = problem; return; }
    setBusy(true);
    try {
      onDone(await api(path, body));
    } catch (failure) {
      error.textContent = failure.message;
      setBusy(false);
      (path === "/auth/guest" ? guestButton : password).focus();
    }
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
    submit);

  guestButton.addEventListener("click", () => { if (!busy) run("/auth/guest", {}); });
  setMode("login");

  const element = h("section", { class: "auth-wrap" },
    h("a", { class: "back", href: "#/" }, "← Back"),
    h("div", { class: "auth-card" },
      h("h1", {}, "Try the demo"),
      h("p", { class: "auth-sub" }, "Sign in to ask questions about the FastAPI documentation, or look around as a guest."),
      h("div", { class: "tabs", role: "tablist", "aria-label": "Sign in or create an account" }, tabs.login, tabs.signup),
      form,
      h("div", { class: "divider" }, h("span", {}, "or")),
      guestButton,
      h("p", { class: "field-hint center" },
        `Guests can ask ${me.guest_limit ?? 5} questions a day, no sign-up. A free account gets ${me.user_limit ?? 30}.`)),
    h("p", { class: "fine" }, "Passwords are stored hashed, never in plain text. The questions you ask are saved in the server's query log."));
  return { element, focus: () => email.focus() };
}
