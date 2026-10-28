import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const config: NextConfig = {
  output: "standalone", // small Docker image: `node server.js`
  poweredByHeader: false,
  // No telemetry, analytics or third-party requests at runtime: fonts are self-hosted by next/font.
};

export default withNextIntl(config);
