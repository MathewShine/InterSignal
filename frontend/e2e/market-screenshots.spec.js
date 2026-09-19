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
  test(`${viewport.width}x${viewport.height} Market screenshot`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/app/market");
    await page.evaluate(() => document.fonts.ready);
    await expect(page.getByText("Recorded 7 Sep 2026", { exact: true })).toBeVisible();
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(300);
    await page.screenshot({ path: path.join("test-results", "market-qa", `market-${viewport.width}x${viewport.height}.png`) });
  });
}

for (const viewport of [{ width: 1920, height: 1080 }, { width: 768, height: 1024 }, { width: 390, height: 844 }]) {
  test(`${viewport.width}x${viewport.height} instrument workspace screenshot`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/app/market/instruments/RELIANCE");
    await page.getByRole("tab", { name: "Chart" }).click();
    await page.evaluate(() => document.fonts.ready);
    await expect(page.getByRole("img", { name: /Line chart/ })).toBeVisible();
    await page.screenshot({ path: path.join("test-results", "market-qa", `market-instrument-${viewport.width}x${viewport.height}.png`) });
  });
}
