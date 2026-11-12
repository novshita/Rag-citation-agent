import test from "node:test";
import assert from "node:assert/strict";
import { checkCredentials, guard, parseRoute, quotaText, whoLabel } from "../../src/rag/web/flow.js";

const out = { enabled: true, authenticated: false };
const guest = { enabled: true, authenticated: true, kind: "guest", email: null, remaining: 3, limit: 5, user_limit: 30 };
const user = { enabled: true, authenticated: true, kind: "user", email: "ada@example.com", remaining: 27, limit: 30, user_limit: 30 };
const open = { enabled: false, authenticated: true };

test("routes parse from the hash, and unknown ones are the landing page", () => {
  assert.equal(parseRoute(""), "landing");
  assert.equal(parseRoute("#/"), "landing");
  assert.equal(parseRoute("#/login"), "login");
  assert.equal(parseRoute("#/app"), "app");
  assert.equal(parseRoute("#/evaluation?x=1"), "evaluation");
  assert.equal(parseRoute("#/nonsense"), "landing");
  assert.equal(parseRoute(undefined), "landing");
});

test("the product needs a session, the login page doesn't once there is one", () => {
  assert.equal(guard("app", out), "#/login");
  assert.equal(guard("app", guest), null);
  assert.equal(guard("login", user), "#/app");
  assert.equal(guard("login", out), null);
  assert.equal(guard("landing", out), null);
  assert.equal(guard("evaluation", out), null);
});

test("with accounts off, everyone goes straight to the product", () => {
  assert.equal(guard("app", open), null);
  assert.equal(guard("login", open), "#/app");
});

test("quota text explains what is left, and what an account adds", () => {
  assert.equal(quotaText(guest), "3 of 5 questions left today as a guest. A free account gets 30 a day.");
  assert.equal(quotaText(user), "27 of 30 questions left today.");
  assert.equal(quotaText(open), "");
  assert.equal(quotaText(null), "");
});

test("credentials are checked the same way the server checks them", () => {
  assert.match(checkCredentials("login", "nope", "x"), /valid email/);
  assert.match(checkCredentials("signup", "a@b.co", "short"), /8 to 128/);
  assert.match(checkCredentials("login", "a@b.co", ""), /password/);
  assert.equal(checkCredentials("signup", "a@b.co", "longenough1"), null);
  assert.equal(checkCredentials("login", " a@b.co ", "x"), null);          // any password may be tried when signing in
});

test("the header names who is signed in", () => {
  assert.equal(whoLabel(guest), "Guest");
  assert.equal(whoLabel(user), "ada@example.com");
  assert.equal(whoLabel(out), "");
  assert.equal(whoLabel(open), "");
});
