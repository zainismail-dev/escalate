// What a hosted-beta browser bundle must never contain (used by scan-bundle.mjs --hosted).
export const PUBLIC_OK = new Set(["NEXT_PUBLIC_SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_ANON_KEY"]);
const SECRET_NAME = /(SECRET|SERVICE_ROLE|PRIVATE|PASSWORD|PASSCODE|FERNET|DATABASE_URL|TOKEN|API_KEY|_KEY)$/i;

/** Escape a value for a RegExp (values are matched literally). */
const literal = (v) => new RegExp(v.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));

/** NEXT_PUBLIC_ variables that look secret: they would be inlined into the bundle. */
export function hostedEnvProblems(env) {
  return Object.keys(env)
    .filter((k) => k.startsWith("NEXT_PUBLIC_") && SECRET_NAME.test(k) && !PUBLIC_OK.has(k))
    .map((k) => `build env: ${k} is public (NEXT_PUBLIC_) but looks like a secret`);
}

/** Rules for the scan: each secret-like build variable's value, and Supabase server keys. */
export function hostedRules(env) {
  const values = Object.entries(env)
    .filter(([k, v]) => SECRET_NAME.test(k) && !PUBLIC_OK.has(k) && typeof v === "string" && v.length >= 12)
    .map(([k, v]) => [literal(v), `the value of ${k}`]);
  return [...values, [/eyJ[A-Za-z0-9_-]{8,}\.(eyJ[A-Za-z0-9_-]{8,})\.[A-Za-z0-9_-]{8,}/, "a JWT", serviceRole]];
}

/** A JWT in the bundle is only a finding when it is a service_role key (the anon key is public). */
function serviceRole(match) {
  try {
    const payload = JSON.parse(Buffer.from(match[1], "base64url").toString("utf8"));
    return payload.role === "service_role";
  } catch {
    return false;
  }
}
