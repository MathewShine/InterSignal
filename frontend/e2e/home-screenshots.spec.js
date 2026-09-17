import { expect, test } from "@playwright/test";
import path from "node:path";

const viewports = [
  { width: 1920, height: 1080 },
  { width: 1536, height: 960 },
  { width: 1440, height: 900 },
  { width: 1366, height: 768 },
  { width: 1280, height: 800 },
  { width: 1024, height: 768 },
  { width: 768, height: 1024 },
  { width: 390, height: 844 },
];

for (const viewport of viewports) {
  test(`${viewport.width}x${viewport.height} Intelligence Home screenshot`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/app");
    await page.evaluate(() => document.fonts.ready);
    await expect(page.getByRole("heading", { name: "Here’s what matters." })).toBeVisible();
    await page.waitForTimeout(700);
    await page.screenshot({ path: path.join("test-results", "home-qa", `${viewport.width}x${viewport.height}.png`) });
  });
}
