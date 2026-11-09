// Hosted beta helpers: mailto links and the "Waking the server…" retries.
import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import { errorBodyKey, reviewKey } from "../src/lib/hosted-copy.ts";
import { letterText, mailtoHref } from "../src/lib/mailto.ts";
import { WAKE_DELAYS_MS, isWakingResponse, withWakeRetries } from "../src/lib/waking.ts";

const en = JSON.parse(readFileSync(new URL("../messages/en.json", import.meta.url), "utf8"));

test("mailto carries recipient, subject and body with CRLF line breaks", () => {
  const { href, bodyIncluded } = mailtoHref("support@shop.example", "Refund: order #12 & more", "Dear Sir,\nPlease refund.");
  assert.equal(bodyIncluded, true);
  assert.equal(href, "mailto:support@shop.example?subject=Refund%3A%20order%20%2312%20%26%20more&body=Dear%20Sir%2C%0D%0APlease%20refund.");
});

test("a long letter is left out of the link", () => {
  const { href, bodyIncluded } = mailtoHref("a@b.example", "S", "x".repeat(5000));
  assert.equal(bodyIncluded, false);
  assert.equal(href, "mailto:a@b.example?subject=S");
});

test("a recipient that isn't an email address (or tries header injection) is dropped", () => {
  for (const bad of ["Customer Care, PO Box 7", "a@b.example?bcc=evil@x.example", "a@b.example\r\nBcc: x@y.z", null, ""]) {
    assert.match(mailtoHref(bad, "S", "B").href, /^mailto:\?subject=S&body=B$/);
  }
});

test("copy text includes the subject", () => {
  assert.equal(letterText("Hello", "Body"), "Subject: Hello\n\nBody");
  assert.equal(letterText(null, "Body"), "Body");
});

const res = (status: number, type = "text/html") => new Response("x", { status, headers: { "content-type": type } });

test("proxy error pages and network errors mean the server is waking; our JSON errors don't", () => {
  assert.equal(isWakingResponse(502, "text/html"), true);
  assert.equal(isWakingResponse(503, null), true);
  assert.equal(isWakingResponse(503, "application/json"), false); // the API's own "AI unavailable"
  assert.equal(isWakingResponse(500, "text/html"), false);
});

test("retries with backoff, reports waking, then succeeds", async () => {
  const answers: (Response | Error)[] = [new TypeError("fetch failed"), res(502), res(200, "application/json")];
  const states: boolean[] = [];
  const slept: number[] = [];
  const r = await withWakeRetries(
    async () => {
      const a = answers.shift()!;
      if (a instanceof Error) throw a;
      return a;
    },
    (w) => states.push(w),
    async (ms) => void slept.push(ms),
  );
  assert.equal(r.status, 200);
  assert.deepEqual(states, [true, false]);
  assert.deepEqual(slept, WAKE_DELAYS_MS.slice(0, 2));
});

test("gives up after about 90 seconds", async () => {
  const total = WAKE_DELAYS_MS.reduce((a, b) => a + b, 0);
  assert.ok(total >= 80_000 && total <= 100_000, `${total}`);
  const r = await withWakeRetries(async () => res(504), () => {}, async () => {});
  assert.equal(r.status, 504);
  await assert.rejects(withWakeRetries(async () => Promise.reject(new TypeError("down")), () => {}, async () => {}));
});

test("a write that fails while the API is up is not sent again (the 12× Agent started)", async () => {
  let attempts = 0;
  const failing = async () => {
    attempts++;
    throw new TypeError("Failed to fetch");
  };
  await assert.rejects(withWakeRetries(failing, () => {}, async () => {}, async () => true));
  assert.equal(attempts, 1);
});

test("a write that fails while the API is asleep is retried until it wakes", async () => {
  let attempts = 0;
  const wakes = async () => {
    if (++attempts < 3) throw new TypeError("Failed to fetch");
    return res(200);
  };
  const out = await withWakeRetries(wakes, () => {}, async () => {}, async () => false);
  assert.equal(out.status, 200);
  assert.equal(attempts, 3);
});

test("hosted errors use their own wording; local ones keep theirs", () => {
  assert.equal(errorBodyKey("offline_api", true), "offline_api.hostedBody");
  assert.equal(errorBodyKey("offline_api", false), "offline_api.body");
  assert.equal(errorBodyKey("ai_misconfigured", true), "ai_misconfigured.hostedBody");
  assert.equal(errorBodyKey("ai_unavailable", true), "ai_unavailable.body");
});

test("hosted copy: no local commands, encrypted on our server, the right EU regions", () => {
  assert.equal(en.errors.offline_api.hostedBody, "The server is waking up or unavailable — try again in a minute.");
  assert.doesNotMatch(en.errors.offline_api.hostedBody, /make up|uvicorn/);
  assert.match(en.wizard.dropHintHosted, /Encrypted on our server/);
  assert.equal(en.dashboard.encryptedHosted, "Encrypted on our server.");
  const { processors, region } = en.hosted.privacyPage;
  for (const text of [processors, region]) {
    assert.match(text, /Supabase[^.]*Ireland/);
    assert.match(text, /Render[^.]*Frankfurt/);
    assert.doesNotMatch(text, /Supabase[^.,]*Frankfurt/);
  }
  assert.match(en.hosted.account.where, /Ireland/);
});

// P2: the beta never sends, so its approve button and dialog never say "send".
test("hosted review copy says Approve, never Approve & send", () => {
  const at = (key: string): unknown =>
    key.split(".").reduce<unknown>((o, k) => (o && typeof o === "object" ? (o as Record<string, unknown>)[k] : undefined), en.review);
  for (const key of ["decision.title", "decision.body", "decision.approve", "confirm.title", "confirm.body", "confirm.cta"]) {
    const hosted = at(reviewKey(key, true));
    assert.equal(typeof hosted, "string", key);
    assert.doesNotMatch(hosted as string, /send this|& send|and send\?|once sent/i, key);
    assert.equal(reviewKey(key, false), key); // self-hosted wording unchanged
  }
  assert.equal(at(reviewKey("decision.approve", true)), "Approve");
  assert.equal(at(reviewKey("confirm.cta", true)), "Approve");
  assert.equal(at("decision.approve"), "Approve & send");
  const src = readFileSync(new URL("../src/app/cases/[id]/review/view.tsx", import.meta.url), "utf8");
  for (const key of ["decision.approve", "confirm.cta", "confirm.title", "confirm.body"]) {
    assert.ok(src.includes(`reviewKey("${key}", HOSTED)`), key);
  }
});
