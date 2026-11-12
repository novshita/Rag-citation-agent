// Page flow and form rules: no DOM, no network, so they can be unit-tested with Node.
//   landing (#/)  ->  login (#/login)  ->  the product (#/app)        plus the public evaluation page.

export const ROUTES = ["landing", "login", "app", "evaluation"];

/** "#/app" -> "app"; anything unknown or empty is the landing page. */
export function parseRoute(hash) {
  const name = String(hash || "").replace(/^#\/?/, "").split(/[/?]/)[0];
  return ROUTES.includes(name) ? name : "landing";
}

/**
 * Where to send the visitor instead of the page they asked for, or null to show it.
 * The product needs a session; the login page is pointless once there is one. When accounts are off
 * (me.enabled is false) everyone counts as signed in and the login page is never shown.
 */
export function guard(route, me) {
  if (route === "app" && !me.authenticated) return "#/login";
  if (route === "login" && me.authenticated) return "#/app";
  return null;
}

/** "3 of 5 questions left today" and, for guests, what an account gets. Empty when nothing is limited. */
export function quotaText(me) {
  if (!me || me.remaining == null || me.limit == null) return "";
  const base = `${me.remaining} of ${me.limit} questions left today`;
  if (me.kind === "guest") return `${base} as a guest. A free account gets ${me.user_limit} a day.`;
  return `${base}.`;
}

const EMAIL = /^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$/;

/** First problem with the sign-in or sign-up fields, or null. The server checks again; this just saves a round trip. */
export function checkCredentials(mode, email, password) {
  if (!EMAIL.test(String(email).trim())) return "Enter a valid email address.";
  if (mode === "signup" && (password.length < 8 || password.length > 128)) return "Use a password of 8 to 128 characters.";
  if (!password) return "Enter your password.";
  return null;
}

/** Who the header says is signed in. */
export function whoLabel(me) {
  if (!me || !me.authenticated || !me.enabled) return "";
  return me.kind === "guest" ? "Guest" : me.email;
}
