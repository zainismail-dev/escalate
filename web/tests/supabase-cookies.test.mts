// L1: the Supabase session cookie is Secure, SameSite=Lax and lasts a week, not 400 days.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { SESSION_MAX_AGE_S, sessionCookieOptions } from "../src/lib/supabase-cookies.ts";

test("on https the session cookie is Secure, Lax and short-lived", () => {
  const o = sessionCookieOptions("https:");
  assert.equal(o.secure, true);
  assert.equal(o.sameSite, "lax");
  assert.equal(o.path, "/");
  assert.equal(o.maxAge, 7 * 24 * 60 * 60);
  assert.ok(SESSION_MAX_AGE_S < 400 * 24 * 60 * 60);
});

test("plain-http local development still works (no Secure flag the browser would drop)", () => {
  assert.equal(sessionCookieOptions("http:").secure, false);
});

test("the browser client passes the options to @supabase/ssr", () => {
  const src = readFileSync(new URL("../src/lib/supabase-client.ts", import.meta.url), "utf8");
  assert.match(src, /cookieOptions:\s*sessionCookieOptions\(\)/);
});
