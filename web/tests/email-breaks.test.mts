// P5: a long recipient address wraps between its parts, never mid-word.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { emailBreakParts } from "../src/lib/email-breaks.ts";

test("an address breaks before @ and after each dot, and loses nothing", () => {
  const a = "refunds.department@brightmart-electronics.example";
  assert.deepEqual(emailBreakParts(a), ["refunds.", "department", "@brightmart-electronics.", "example"]);
  assert.equal(emailBreakParts(a).join(""), a);
  assert.deepEqual(emailBreakParts("a@b"), ["a", "@b"]);
  assert.deepEqual(emailBreakParts(""), []);
});

test("the decision panel no longer lets the address break anywhere", () => {
  const src = readFileSync(new URL("../src/components/recipient-confirm.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(src, /break-all/);
  assert.match(src, /<EmailText address=\{check\.recipient\} \/>/);
  assert.match(src, /wrap-anywhere/);
});
