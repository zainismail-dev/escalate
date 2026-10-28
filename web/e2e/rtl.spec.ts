import { expect, test } from "@playwright/test";
import { demoCases, settled } from "./helpers";

// v0.1 ships English-only (ENABLED_LOCALES=["en"]), so the Arabic UI cannot be selected. RTL
// support stays in the code; re-enable this spec with NEXT_PUBLIC_ENABLED_LOCALES=en,ar.
test.skip(
  !(process.env.NEXT_PUBLIC_ENABLED_LOCALES || "en").split(",").includes("ar"),
  "v0.1 is English-only; build with NEXT_PUBLIC_ENABLED_LOCALES=en,ar to run the RTL spec",
);

test.beforeEach(async ({ context, baseURL }) => {
  await context.addCookies([{ name: "NEXT_LOCALE", value: "ar", url: baseURL! }]);
});

test("Arabic UI is right-to-left, letters keep their own direction", async ({ page }) => {
  await page.goto("/cases");
  await settled(page);
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.locator("html")).toHaveAttribute("lang", "ar");
  await expect(page.getByTestId("translate-banner")).toBeVisible();
  const { PK } = await demoCases();
  await page.goto(`/cases/${PK.id}/review`);
  await settled(page);
  await expect(page.getByTestId("letter")).toHaveAttribute("dir", "ltr"); // English letter
  // Logical layout: the decision card sits at the inline end, which is the left in RTL.
  const letterBox = await page.getByTestId("letter").boundingBox();
  const decisionBox = await page.getByTestId("decision-card").boundingBox();
  expect(decisionBox!.x).toBeLessThan(letterBox!.x);
});
