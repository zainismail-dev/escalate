// Checks the UI message catalogs: every key the code uses exists in messages/en.json, the
// dynamic key families exist, and translations only contain keys that English has.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const root = new URL("..", import.meta.url).pathname;
const en = JSON.parse(readFileSync(join(root, "messages/en.json"), "utf8"));
const has = (path) => path.split(".").reduce((o, k) => (o && typeof o === "object" ? o[k] : undefined), en) !== undefined;
const errors = [];

function* files(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) yield* files(p);
    else if (/\.tsx?$/.test(name)) yield p;
  }
}

for (const file of files(join(root, "src"))) {
  const src = readFileSync(file, "utf8");
  // Each use resolves to the nearest earlier declaration of that name (functions reuse `t`).
  const decls = [...src.matchAll(/const (\w+) = (?:await )?(?:useTranslations|getTranslations)\("([\w.]+)"\)/g)].map(
    (m) => ({ name: m[1], ns: m[2], at: m.index }),
  );
  for (const m of src.matchAll(/getTranslations\("([\w.]+)"\)\)\("([\w.]+)"/g)) {
    if (!has(`${m[1]}.${m[2]}`)) errors.push(`${file}: missing ${m[1]}.${m[2]}`);
  }
  for (const v of new Set(decls.map((d) => d.name))) {
    for (const m of src.matchAll(new RegExp(`\\b${v}\\("([\\w.]+)"`, "g"))) {
      const d = decls.filter((x) => x.name === v && x.at < m.index).at(-1);
      if (d && !has(`${d.ns}.${m[1]}`)) errors.push(`${file}: missing ${d.ns}.${m[1]}`);
    }
  }
}

// Keys built at runtime from API values.
const DYNAMIC = {
  status: ["intake", "urgent_checklist", "drafting", "awaiting_approval", "waiting_reply", "pick_next", "confirm_resolution", "resolved", "closed_unresolved", "withdrawn"],
  waiting: ["questions", "urgent_checklist", "approve_draft", "confirm_delivery", "waiting_reply", "confirm_resolution"],
  verdict: ["resolved", "partial", "refused", "no_reply"],
  channel: ["email", "post", "court", "web_form", "info"],
  caseType: ["refund_refused", "subscription_cancel", "scam", "other", "unknown"],
  ladder: ["done", "current", "future", "skipped"],
  "why.level": ["company", "region", "country", "generic"],
  "why.reasons": ["first_step", "after_verdict", "skipped", "position", "channel", "channel_only", "wait", "proof", "deadline", "deadline_late", "playbook"],
  "errors": ["model_offline.title", "model_offline.body", "offline_api.title", "offline_api.body", "fact_check.title", "rate_limited.title", "other.title", "other.body"],
  "review.checks": ["facts", "blanks", "tone", "disclaimer", "no_secrets"],
  "cases.cta": ["open", "approve_draft", "questions", "urgent_checklist", "confirm_delivery", "confirm_resolution"],
  "progress.steps": ["classify", "playbook", "facts", "draft", "check", "reply", "judge", "next"],
  "wizard.steps": ["where", "what", "evidence", "missing", "review"],
  "wizard.titles": ["where", "what", "evidence", "missing", "review"],
  "wizard.intros": ["where", "what", "evidence", "missing", "review"],
};
for (const k of ["approve_draft", "questions", "urgent_checklist", "confirm_delivery", "waiting_reply", "confirm_resolution", "start", "resolved", "closed_unresolved", "withdrawn", "none"]) {
  for (const f of ["title", "body", "cta"]) (DYNAMIC.nextMove ??= []).push(`${k}.${f}`);
}
for (const [ns, keys] of Object.entries(DYNAMIC)) for (const k of keys) if (!has(`${ns}.${k}`)) errors.push(`dynamic key missing: ${ns}.${k}`);

function walk(obj, prefix, out) {
  for (const [k, v] of Object.entries(obj)) {
    if (k.startsWith("_")) continue;
    const p = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object") walk(v, p, out);
    else out.push(p);
  }
  return out;
}
for (const name of readdirSync(join(root, "messages"))) {
  if (name === "en.json") continue;
  let data;
  try {
    data = JSON.parse(readFileSync(join(root, "messages", name), "utf8"));
  } catch (e) {
    errors.push(`${name}: invalid JSON (${e.message})`);
    continue;
  }
  for (const k of walk(data, "", [])) if (!has(k)) errors.push(`${name}: key ${k} is not in en.json`);
}

if (errors.length) {
  console.error(errors.join("\n"));
  process.exit(1);
}
console.log("messages OK");
