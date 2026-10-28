import { expect, test } from "@playwright/test";
import { settled } from "./helpers";

test("mobile: bottom tabs, stacked layout", async ({ page }) => {
  await page.goto("/cases");
  await settled(page);
  const tabs = page.getByTestId("bottom-tabs");
  await expect(tabs).toBeVisible();
  await tabs.getByRole("link", { name: "New case" }).click();
  await expect(page).toHaveURL(/\/cases\/new/);
  const width = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(width).toBeLessThanOrEqual(page.viewportSize()!.width);
});
