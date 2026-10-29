import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

// Every response. The Content-Security-Policy is per request (nonce): src/proxy.ts.
const SECURITY_HEADERS = [
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" }, // ignored over http
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=()" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
];

// The static demo's sample data is only bundled into the demo build; elsewhere a stub with the
// same exports takes its place (see src/demo/disabled.ts).
const DEMO = process.env.NEXT_PUBLIC_DEMO_STATIC === "true";
const DEMO_BACKEND = DEMO ? "./src/demo/backend.ts" : "./src/demo/disabled.ts";

const config: NextConfig = {
  output: "standalone", // small Docker image: `node server.js`
  turbopack: { resolveAlias: { "escalate-demo-backend": DEMO_BACKEND } },
  poweredByHeader: false,
  // No telemetry, analytics or third-party requests at runtime: fonts are self-hosted by next/font.
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
};

export default withNextIntl(config);
