import { mkdir } from "node:fs/promises";
import { expect, test } from "@playwright/test";

const viewports = [
  { width: 1440, height: 900 },
  { width: 1366, height: 768 },
  { width: 1536, height: 960 },
  { width: 1024, height: 768 },
  { width: 390, height: 844 },
];

const scenes = [
  ["hero", "signal", 0.03],
  ["decomposition-intro", "decompose", 0.12],
  ["decomposition", "decompose", 0.99],
  ["convergence", "focus", 1],
  ["portfolio", "portfolio-context", 0.24],
  ["reassembly-portfolio", "reassemble", 0.22],
  ["reassembly-research", "reassemble", 0.52],
  ["reassembly-market", "reassemble", 0.78],
  ["reassembly", "reassemble", 0.99],
  ["closing", "resolve", 0.12],
];

const boundaries = ["light-dark", "dark-sky"];

for (const viewport of viewports) {
  test(`${viewport.width}x${viewport.height} scene screenshots`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/");
    await page.locator('[data-scene="resolve"]').waitFor();
    await page.evaluate(async () => {
      await document.fonts.ready;
      document.documentElement.style.scrollBehavior = "auto";
    });
    await mkdir("test-results/landing-qa", { recursive: true });

    for (const [name, sceneName, progress] of scenes) {
      const scene = page.locator(`[data-scene="${sceneName}"]`);
      await expect(scene).toBeVisible();
      const box = await scene.evaluate((element) => ({ top: element.offsetTop, height: element.offsetHeight }));
      const available = Math.max(0, box.height - viewport.height);
      await page.evaluate(({ top, offset }) => window.scrollTo(0, top + offset), {
        top: box.top,
        offset: available * progress,
      });
      await page.waitForTimeout(800);
      await page.screenshot({
        animations: "disabled",
        path: `test-results/landing-qa/${viewport.width}x${viewport.height}-${name}.png`,
      });
    }

    for (const name of boundaries) {
      const boundary = page.locator(`[data-boundary="${name}"]`);
      const top = await boundary.evaluate((element) => element.offsetTop);
      await page.evaluate(({ boundaryTop, viewportHeight }) => {
        document.documentElement.style.scrollBehavior = "auto";
        window.scrollTo({ behavior: "instant", top: boundaryTop - viewportHeight * 0.46 });
      }, { boundaryTop: top, viewportHeight: viewport.height });
      await page.waitForTimeout(450);
      await page.screenshot({
        animations: "disabled",
        path: `test-results/landing-qa/${viewport.width}x${viewport.height}-${name}.png`,
      });
    }

    if (viewport.width < 1024) {
      const wordmark = page.locator('[data-qa="reassembly-flow-wordmark"]');
      await wordmark.evaluate((element) => element.scrollIntoView({ block: "center", behavior: "instant" }));
      await page.waitForTimeout(700);
      await page.screenshot({
        animations: "disabled",
        path: `test-results/landing-qa/${viewport.width}x${viewport.height}-reassembly-wordmark.png`,
      });
    }
  });
}
