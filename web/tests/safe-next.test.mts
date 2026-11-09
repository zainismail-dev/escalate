// M1: the post-sign-in redirect only ever follows a path on this site.
import assert from "node:assert/strict";
import { test } from "node:test";
import { DEFAULT_NEXT, safeNext } from "../src/lib/safe-next.ts";

const ORIGIN = "https://app.escalate.test";

test("same-site paths are kept, with their query and hash", () => {
  assert.equal(safeNext("/cases/12", ORIGIN), "/cases/12");
  assert.equal(safeNext("/cases/12?tab=letter#draft", ORIGIN), "/cases/12?tab=letter#draft");
  assert.equal(safeNext("/settings", ORIGIN), "/settings");
});

test("missing or relative values fall back to My cases", () => {
  for (const v of [null, undefined, "", "cases", "evil.example", "https://evil.example/"]) {
    assert.equal(safeNext(v, ORIGIN), DEFAULT_NEXT);
  }
});

test("every off-site bypass from the review is refused", () => {
  // As received by searchParams.get (already percent-decoded once) and still encoded.
  const bypasses = [
    "//evil.example/",
    "/\\evil.example/",
    "/%5Cevil.example/",
    "/\\\\evil.example/",
    "/%5C%5Cevil.example/",
    "/\tevil.example/",
    "/%09/evil.example/",
    "/\t/evil.example/",
    "/\n/evil.example/",
    "/%0A/evil.example/",
    "/%0D/evil.example/",
    "/\r\n/evil.example/",
    "/ /evil.example/",
    "/%20/evil.example/",
    "/%2F/evil.example/",
    "/\u0000/evil.example/",
    "/ /evil.example/",
    "/%E0%A4%A", // malformed escape
    "/\\/evil.example",
    ["java", "script:alert(1)"].join(""),
    "/javascript:alert(1)//",
  ];
  for (const v of bypasses) {
    const got = safeNext(v, ORIGIN);
    assert.equal(new URL(got, ORIGIN).origin, ORIGIN, `${JSON.stringify(v)} -> ${got}`);
    if (v !== "/javascript:alert(1)//") assert.equal(got, DEFAULT_NEXT, JSON.stringify(v));
  }
});

test("sign-in and the OAuth callback both use the shared helper", async () => {
  const { readFileSync } = await import("node:fs");
  for (const f of ["../src/app/signin/view.tsx", "../src/app/auth/callback/view.tsx"]) {
    const src = readFileSync(new URL(f, import.meta.url), "utf8");
    assert.match(src, /safeNext\(/, f);
    assert.doesNotMatch(src, /startsWith\("\/\/"\)/, f);
  }
});
