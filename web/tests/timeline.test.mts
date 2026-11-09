// The case timeline: retries collapse into one entry; times are the viewer's, with UTC on hover.
import assert from "node:assert/strict";
import { test } from "node:test";
import { formatDateTime, formatLocalDateTime } from "../src/lib/datetime.ts";
import { collapseRetries } from "../src/lib/timeline.ts";

const ev = (n: number, type: string) => ({ id: `ev-${n}`, type, payload: {}, created_at: `2026-11-02T10:00:${String(n).padStart(2, "0")}` });

test("repeated starts become one entry with the number of retries", () => {
  const out = collapseRetries(Array.from({ length: 13 }, (_, i) => ev(i + 2, "case_started")));
  assert.equal(out.length, 1);
  assert.equal(out[0].id, "ev-2");
  assert.equal(out[0].retries, 12);
});

test("starts split by other events still collapse; the other events stay in order", () => {
  const out = collapseRetries([ev(1, "case_created"), ev(2, "case_started"), ev(3, "classified"), ev(4, "case_started"), ev(5, "draft_created")]);
  assert.deepEqual(out.map((e) => [e.type, e.retries]), [
    ["case_created", 0],
    ["case_started", 1],
    ["classified", 0],
    ["draft_created", 0],
  ]);
});

test("one start is not a retry, and a timeline without one is unchanged", () => {
  assert.equal(collapseRetries([ev(1, "case_started")])[0].retries, 0);
  assert.deepEqual(collapseRetries([]), []);
  assert.equal(collapseRetries([ev(1, "classified")])[0].retries, 0);
});

test("the same instant shows in the viewer's zone, and the UTC tooltip stays UTC", () => {
  const at = "2026-11-02T22:30:00";
  assert.match(formatLocalDateTime(at, "en-GB", "Asia/Karachi") ?? "", /3 Nov 2026.*03:30/);
  assert.match(formatLocalDateTime(at, "en-GB", "America/New_York") ?? "", /2 Nov 2026.*17:30/);
  assert.match(formatDateTime(at, "en-GB") ?? "", /2 Nov 2026.*22:30.*UTC/);
});
