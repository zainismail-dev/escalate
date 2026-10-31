// Hosted beta helpers: mailto links and the "Waking the server…" retries.
import assert from "node:assert/strict";
import { test } from "node:test";
import { letterText, mailtoHref } from "../src/lib/mailto.ts";
import { WAKE_DELAYS_MS, isWakingResponse, withWakeRetries } from "../src/lib/waking.ts";

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
