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
  test(`${viewport.width}x${viewport.height} Portfolio screenshot`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/app/portfolio");
    await page.evaluate(() => document.fonts.ready);
    await expect(page.locator(".portfolio-summary-primary strong")).toHaveText("₹52,393");
    await expect(page.locator(".portfolio-summary-primary").getByText("Demo portfolio", { exact: true })).toBeVisible();
    await page.waitForTimeout(400);
    await page.screenshot({ path: path.join("test-results", "portfolio-qa", `${viewport.width}x${viewport.height}.png`) });
  });
}

for (const capture of [
  { name: "holdings", route: "/app/portfolio/holdings", heading: "Holdings", marker: "Synthetic Mutual Fund One" },
  { name: "performance", route: "/app/portfolio/performance", heading: "Performance", marker: "2 valuation dates" },
  { name: "activity", route: "/app/portfolio/activity", heading: "Portfolio activity", marker: "TXN-MANUAL-SELL-001" },
]) {
  test(`1440x900 populated ${capture.name} screenshot`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(capture.route);
    await page.evaluate(() => document.fonts.ready);
    await expect(page.getByRole("heading", { name: capture.heading, exact: true, level: 1 })).toBeVisible();
    await expect(page.getByText(capture.marker, { exact: false }).first()).toBeVisible();
    await page.waitForTimeout(400);
    await page.screenshot({ path: path.join("test-results", "portfolio-qa", `1440x900-${capture.name}.png`) });
  });
}
