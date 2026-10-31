// Scans a production build for things that must never ship to browsers: secrets, private keys,
// and internal or local URLs (the static demo talks to no server). Exit 1 on any finding.
//   node scripts/scan-bundle.mjs [--demo | --hosted]      (after `next build`)
// --hosted (the beta): also fails on the value of any secret-like build variable, a Supabase
// secret or service_role key, or a NEXT_PUBLIC_ variable that looks secret. Only
// NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY may reach the browser.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { hostedEnvProblems, hostedRules } from "./hosted-secrets.mjs";

const demo = process.argv.includes("--demo");
const hosted = process.argv.includes("--hosted");
const root = join(process.cwd(), ".next");
// What browsers download: static chunks and prerendered pages. Server-only files (e.g. the
// prerender manifest's preview keys) are never served and are not scanned.
const dirs = [join(root, "static"), join(root, "server", "app")];

const SECRETS = [
  [/-----BEGIN [A-Z ]*PRIVATE KEY-----/, "private key"],
  [/\bsk-(?:live|proj|ant)?-?[A-Za-z0-9_-]{20,}/, "API key (sk-…)"],
  [/\bgsk_[A-Za-z0-9]{20,}/, "Groq key"],
  [/\bghp_[A-Za-z0-9]{30,}/, "GitHub token"],
  [/\bAKIA[0-9A-Z]{16}\b/, "AWS key"],
  [/\bAIza[0-9A-Za-z_-]{35}\b/, "Google API key"],
  [/\bxox[abp]-[A-Za-z0-9-]{10,}/, "Slack token"],
  [/FERNET_KEY|SMTP_APP_PASSWORD|LLM_API_KEY|APP_PASSCODE|SUPABASE_SERVICE_ROLE_KEY|TICK_SECRET/, "server setting name"],
  [/\bsb_secret_[A-Za-z0-9_-]{10,}/, "Supabase secret key"],
];
// Self-hosted and demo builds carry no hosted-beta code at all.
const NO_HOSTED = [[/supabase-js|GoTrueClient|createBrowserClient/, "Supabase client in a non-hosted build"]];
const INTERNAL = [
  [/https?:\/\/(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\])/, "local URL"],
  [/https?:\/\/(?:10|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d+\.\d+/, "private network URL"],
  [/169\.254\.169\.254/, "cloud metadata address"],
  [/https?:\/\/(?:api|ollama|host\.docker\.internal)(?::\d+)/, "docker-internal URL"],
  [/\/Users\/|\/home\/runner\/|C:\\\\Users/, "build machine path"],
];
// Shown to users as a suggestion, not a server the app talks to: the Ollama preset in Settings.
const ALLOWED = ["http://localhost:11434/v1"];
// A self-hosted build must not carry the demo's sample cases (web/src/demo/*.json).
const DEMO_DATA = [[/BrightMart Electronics|PulseFit Gyms/, "demo sample data in a non-demo build"]];
const rules = demo
  ? [...SECRETS, ...INTERNAL, ...NO_HOSTED]
  : hosted
    ? [...SECRETS, ...DEMO_DATA, ...hostedRules(process.env)]
    : [...SECRETS, ...DEMO_DATA, ...NO_HOSTED];

function* files(dir) {
  let names = [];
  try {
    names = readdirSync(dir);
  } catch {
    return;
  }
  for (const name of names) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) yield* files(p);
    else if (/\.(js|css|html|json|rsc|txt|map)$/.test(name)) yield p;
  }
}

let count = 0;
const findings = hosted ? hostedEnvProblems(process.env) : [];
for (const dir of dirs) {
  for (const file of files(dir)) {
    count++;
    let text = readFileSync(file, "utf8");
    for (const ok of ALLOWED) text = text.replaceAll(ok, "");
    for (const [rx, what, confirm] of rules) {
      // Rules with a check (e.g. "is this JWT a service_role key?") look at every match.
      const m = confirm ? [...text.matchAll(new RegExp(rx, "g"))].find(confirm) : text.match(rx);
      // Only the start of a match is printed: the log must not repeat a leaked secret.
      if (m) findings.push(`${file.slice(root.length + 1)}: ${what}: ${m[0].slice(0, 12)}…`);
    }
  }
}
for (const f of findings) console.error(f);
const kind = demo ? "demo: secrets + internal URLs" : hosted ? "hosted: secrets + build env values" : "secrets";
console.log(`scanned ${count} files (${kind}): ${findings.length} finding(s)`);
process.exit(findings.length ? 1 : 0);
