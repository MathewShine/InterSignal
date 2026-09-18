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
  test(`${viewport.width}x${viewport.height} Research Workbench screenshot`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/app/research");
    await page.evaluate(() => document.fonts.ready);
    await expect(page.getByRole("heading", { name: "Research", exact: true })).toBeVisible();
    await expect(page.getByText("A–G complete", { exact: true })).toBeVisible();
    await page.waitForTimeout(400);
    await page.screenshot({ path: path.join("test-results", "research-qa", `${viewport.width}x${viewport.height}.png`) });
  });
}

for (const capture of [
  {
    name: "family-a",
    route: "/app/research/families/A",
    heading: "Medium-Term Cross-Sectional Momentum",
    marker: "FAIL / UNSUPPORTIVE — a separate, non-pristine post-outcome evaluation that does not replace the formal one-shot result.",
  },
  {
    name: "evidence",
    route: "/app/research/evidence",
    heading: "Evidence registry",
    marker: "EDGE-EVIDENCE-C-COMPRESSION-001",
  },
  {
    name: "validation",
    route: "/app/research/validation",
    heading: "Validation",
    marker: "Formal one-shot",
  },
  {
    name: "blocked",
    route: "/app/research/blocked",
    heading: "Blocked research",
    marker: "77.826%",
  },
]) {
  test(`1440x900 populated ${capture.name} screenshot`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(capture.route);
    await page.evaluate(() => document.fonts.ready);
    await expect(page.getByRole("heading", { name: capture.heading, exact: true })).toBeVisible();
    await expect(page.getByText(capture.marker, { exact: false }).first()).toBeVisible();
    await expect(page.getByText("Research data couldn’t be loaded.")).toHaveCount(0);
    await page.waitForTimeout(400);
    await page.screenshot({ path: path.join("test-results", "research-qa", `1440x900-${capture.name}.png`) });
  });
}
