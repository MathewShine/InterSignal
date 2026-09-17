import { mkdir } from "node:fs/promises";
import { expect, test } from "@playwright/test";

const viewports = [
  { width: 1440, height: 900 },
  { width: 1366, height: 768 },
  { width: 390, height: 844 },
];

for (const viewport of viewports) {
  for (const mode of ["signin", "signup"]) {
    test(`${viewport.width}x${viewport.height} ${mode} screenshot`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.goto(`/auth?mode=${mode}`);
      await page.evaluate(() => document.fonts.ready);
      await expect(page.locator(".auth-panel")).toBeVisible();
      await page.waitForTimeout(1500);
      await mkdir("test-results/auth-qa", { recursive: true });
      await page.screenshot({
        animations: "disabled",
        path: `test-results/auth-qa/${viewport.width}x${viewport.height}-${mode}.png`,
      });
    });
  }
}
