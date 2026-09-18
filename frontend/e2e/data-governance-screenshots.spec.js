import { expect, test } from "@playwright/test";
import path from "node:path";

const viewports = [{ width: 1920, height: 1080 }, { width: 1536, height: 960 }, { width: 1440, height: 900 }, { width: 1366, height: 768 }, { width: 1024, height: 768 }, { width: 768, height: 1024 }, { width: 390, height: 844 }];

for (const viewport of viewports) {
  for (const [area, route, marker] of [["data", "/app/data", "77.826%"], ["governance", "/app/governance", "8/8 policy evaluations pass."]]) {
    test(`${viewport.width}x${viewport.height} ${area} screenshot`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.goto(route);
      await page.evaluate(() => document.fonts.ready);
      await expect(page.getByText(marker, { exact: true })).toBeVisible();
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.waitForTimeout(300);
      await page.screenshot({ path: path.join("test-results", "data-governance-qa", `${area}-${viewport.width}x${viewport.height}.png`) });
    });
  }
}

for (const [name, route, heading] of [
  ["data-sources", "/app/data/sources", "Data sources"],
  ["data-lineage", "/app/data/lineage", "Lineage"],
  ["data-limitations", "/app/data/limitations", "Data limitations"],
  ["governance-readiness", "/app/governance/readiness", "Readiness"],
  ["governance-policies", "/app/governance/policies", "Policies"],
  ["governance-authorizations", "/app/governance/authorizations", "Authorizations"],
  ["governance-audit", "/app/governance/audit", "Audit"],
]) {
  test(`1440x900 ${name} populated screenshot`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(route);
    await page.evaluate(() => document.fonts.ready);
    await expect(page.getByRole("heading", { name: heading, exact: true, level: 1 })).toBeVisible();
    await expect(page.getByText("Read-only", { exact: true })).toBeVisible();
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(300);
    await page.screenshot({ path: path.join("test-results", "data-governance-qa", `${name}-1440x900.png`) });
  });
}
