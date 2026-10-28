import { expect, test } from "@playwright/test";
import { settled } from "./helpers";

test("dark mode follows the system and the toggle", async ({ page }) => {
  await page.goto("/cases");
  await settled(page);
  await expect(page.locator("html")).toHaveClass(/dark/);
  const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(bg).toBe("rgb(14, 16, 22)");
  await page.getByTestId("theme-toggle").click(); // system -> light
  await expect(page.locator("html")).not.toHaveClass(/dark/);
  await page.getByTestId("theme-toggle").click(); // light -> dark
  await expect(page.locator("html")).toHaveClass(/dark/);
});
