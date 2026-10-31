// One vercel.json, two Vercel projects: the public static demo (default) and the hosted beta
// ("escalate-beta", which sets NEXT_PUBLIC_DEPLOY_MODE=hosted). The demo build is unchanged.
import { spawnSync } from "node:child_process";

export function buildScript(env = process.env) {
  return env.NEXT_PUBLIC_DEPLOY_MODE === "hosted" ? "build:hosted" : "build:demo";
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const script = buildScript();
  console.log(`vercel-build: npm run ${script}`);
  const r = spawnSync("npm", ["run", script], { stdio: "inherit" });
  process.exit(r.status ?? 1);
}
