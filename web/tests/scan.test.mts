// The hosted bundle check (scripts/hosted-secrets.mjs) and the Vercel build switch.
import assert from "node:assert/strict";
import { test } from "node:test";
import { hostedEnvProblems, hostedRules } from "../scripts/hosted-secrets.mjs";
import { buildScript } from "../scripts/vercel-build.mjs";

const jwt = (payload: object) =>
  ["eyJhbGciOiJIUzI1NiJ9", Buffer.from(JSON.stringify(payload)).toString("base64url"), "c2lnbmF0dXJlLXNpZ25hdHVyZQ"].join(".");

function findings(bundle: string, env: Record<string, string>) {
  return hostedRules(env).filter(([rx, , confirm]) =>
    confirm ? [...bundle.matchAll(new RegExp(rx, "g"))].some(confirm) : rx.test(bundle),
  );
}

test("the allowed public values may be in the bundle", () => {
  const env = { NEXT_PUBLIC_SUPABASE_URL: "https://abc.supabase.co", NEXT_PUBLIC_SUPABASE_ANON_KEY: jwt({ role: "anon" }) };
  assert.deepEqual(hostedEnvProblems(env), []);
  assert.deepEqual(findings(`const k="${env.NEXT_PUBLIC_SUPABASE_ANON_KEY}";`, env), []);
});

test("any secret-like build variable's value in the bundle is a finding", () => {
  const env = { SUPABASE_SERVICE_ROLE_KEY: "sb_secret_abcdefghijklmnop", FERNET_KEY: "q".repeat(44), DATABASE_URL: "postgresql://u:p@h/db" };
  for (const [name, value] of Object.entries(env)) {
    const hit = findings(`x="${value}"`, env).map(([, what]) => what);
    assert.ok(hit.includes(`the value of ${name}`), name);
  }
});

test("a service_role JWT anywhere in the bundle is a finding, after an anon one too", () => {
  const bundle = `a="${jwt({ role: "anon" })}";b="${jwt({ role: "service_role" })}"`;
  assert.equal(findings(bundle, {}).length, 1);
});

test("NEXT_PUBLIC_ variables that look secret fail the build", () => {
  const problems = hostedEnvProblems({ NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY: "x", NEXT_PUBLIC_API_URL: "https://api" });
  assert.equal(problems.length, 1);
  assert.match(problems[0], /NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY/);
});

test("Vercel builds the demo unless the project is the hosted beta", () => {
  assert.equal(buildScript({}), "build:demo");
  assert.equal(buildScript({ NEXT_PUBLIC_DEPLOY_MODE: "local" }), "build:demo");
  assert.equal(buildScript({ NEXT_PUBLIC_DEPLOY_MODE: "hosted" }), "build:hosted");
});
