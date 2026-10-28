import { expect, type Page, test } from "@playwright/test";
import { demoCases, settled } from "./helpers";

/**
 * Fails any page that logs a console error or warning (React warnings, hydration mismatches,
 * "Encountered a script tag", failed API calls) or throws. Runs every page in light and dark.
 * Run it against `next dev` too: React's detailed warnings only exist in development builds.
 */
function watch(page: Page): string[] {
  const problems: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error" || m.type() === "warning") problems.push(`${m.type()}: ${m.text()}`);
  });
  page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
  return problems;
}

async function paths(): Promise<string[]> {
  const { PK, IN, GB, US } = await demoCases();
  return [
    "/",
    "/cases",
    "/cases/new",
    "/settings",
    `/cases/${PK.id}`,
    `/cases/${PK.id}/review`,
    `/cases/${PK.id}/questions`,
    `/cases/${US.id}/review`,
    `/cases/${IN.id}`,
    `/cases/${IN.id}/urgent`,
    `/cases/${GB.id}/reply`,
  ];
}

for (const colorScheme of ["light", "dark"] as const) {
  test.describe(colorScheme, () => {
    test.use({ colorScheme });
    test(`no console errors, warnings or hydration errors on any page (${colorScheme})`, async ({ page }) => {
      test.setTimeout(180_000); // `next dev` compiles each page on first visit
      const problems = watch(page);
      for (const path of await paths()) {
        const before = problems.length;
        await page.goto(path);
        await settled(page);
        await page.waitForLoadState("networkidle");
        await expect(page.locator("html")).toHaveClass(colorScheme === "dark" ? /dark/ : /^(?!.*\bdark\b).*/);
        expect(problems.slice(before), `console problems on ${path}`).toEqual([]);
      }
    });
  });
}
