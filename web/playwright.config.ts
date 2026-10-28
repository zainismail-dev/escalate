import { defineConfig, devices } from "@playwright/test";

/**
 * Smoke tests against a running web app (WEB_URL) and API (API_URL) seeded with demo data.
 * `make web-e2e` starts both; CI does the same. E2E_RESET=1 wipes and re-seeds the API first,
 * so never set it against an instance with real cases.
 */
const WEB_URL = process.env.WEB_URL || "http://localhost:3000";

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  // PW_CHANNEL=chrome uses an installed Google Chrome instead of Playwright's Chromium.
  use: { baseURL: WEB_URL, trace: "retain-on-failure", channel: process.env.PW_CHANNEL || undefined },
  projects: [
    { name: "smoke", testMatch: /smoke\.spec\.ts/, use: { ...devices["Desktop Chrome"] } },
    { name: "rtl", testMatch: /rtl\.spec\.ts/, use: { ...devices["Desktop Chrome"], locale: "ar" } },
    { name: "dark", testMatch: /dark\.spec\.ts/, use: { ...devices["Desktop Chrome"], colorScheme: "dark" } },
    { name: "mobile", testMatch: /mobile\.spec\.ts/, use: { ...devices["Pixel 7"] } },
    { name: "screenshots", testMatch: /screenshots\.spec\.ts/, use: { ...devices["Desktop Chrome"], viewport: { width: 1360, height: 900 } } },
  ],
});
