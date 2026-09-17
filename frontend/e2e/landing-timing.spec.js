import { expect, test } from "@playwright/test";

async function settle(page) {
  await page.goto("/");
  await page.locator('[data-scene="resolve"]').waitFor();
  await page.evaluate(() => document.fonts.ready);
}

test.describe("mobile product deck timing", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("paces the hero device and floating data across the full entrance", async ({ page }) => {
    await page.goto("/");
    const deviceEntry = page.locator(".signal-hero__mobile .perspective-surface__entry");
    await deviceEntry.waitFor({ state: "attached" });

    const timeline = await page.evaluate(async () => {
      const elements = {
        breadth: document.querySelector('[data-datum="breadth"]'),
        cta: document.querySelector(".signal-hero__cta-emphasis"),
        device: document.querySelector(".signal-hero__mobile .perspective-surface__entry"),
        exposure: document.querySelector('[data-datum="market-exposure"]'),
      };
      const opacity = (element) => Number(getComputedStyle(element).opacity);
      const initial = Object.fromEntries(Object.entries(elements).map(([name, element]) => [name, opacity(element)]));
      const thresholds = {};
      const startedAt = performance.now();

      await new Promise((resolve) => {
        function sample() {
          const elapsed = performance.now() - startedAt;
          const values = Object.fromEntries(Object.entries(elements).map(([name, element]) => [name, opacity(element)]));
          if (thresholds.device75 === undefined && values.device > 0.75) thresholds.device75 = elapsed;
          if (thresholds.breadth50 === undefined && values.breadth > 0.5) thresholds.breadth50 = elapsed;
          if (thresholds.breadth90 === undefined && values.breadth > 0.9) thresholds.breadth90 = elapsed;
          if (thresholds.exposure90 === undefined && values.exposure > 0.9) thresholds.exposure90 = elapsed;
          if (thresholds.cta90 === undefined && values.cta > 0.9) thresholds.cta90 = elapsed;

          if (Object.keys(thresholds).length === 5 || elapsed > 6000) {
            resolve();
            return;
          }
          requestAnimationFrame(sample);
        }
        sample();
      });

      return { initial, thresholds };
    });

    expect(timeline.initial.device).toBeLessThan(0.2);
    expect(timeline.initial.breadth).toBeLessThan(0.5);
    expect(timeline.initial.exposure).toBeLessThan(0.5);
    expect(timeline.thresholds.device75).toBeLessThan(timeline.thresholds.breadth50);
    expect(typeof timeline.thresholds.breadth90).toBe("number");
    expect(typeof timeline.thresholds.exposure90).toBe("number");
    expect(typeof timeline.thresholds.cta90).toBe("number");
  });

  test("holds Market, cycles in order, and honors the manual pause", async ({ page }) => {
    await settle(page);
    const prototype = page.locator('[data-qa="hero-mobile-prototype"]');

    await expect(prototype).toHaveAttribute("data-active-screen", "market");
    await prototype.evaluate((element) => {
      window.__deckTiming = [{ screen: element.dataset.activeScreen, time: performance.now() }];
      window.__deckObserver = new MutationObserver(() => {
        window.__deckTiming.push({ screen: element.dataset.activeScreen, time: performance.now() });
      });
      window.__deckObserver.observe(element, { attributeFilter: ["data-active-screen"] });
    });
    await expect.poll(
      () => page.evaluate(() => window.__deckTiming.length),
      { timeout: 12_000 },
    ).toBeGreaterThanOrEqual(3);

    const timings = await page.evaluate(() => window.__deckTiming.slice(0, 3));
    expect(timings.map(({ screen }) => screen)).toEqual(["market", "portfolio", "research"]);
    expect(timings[2].time - timings[1].time).toBeGreaterThanOrEqual(3100);

    await page.getByRole("tab", { name: "Market" }).click();
    await expect(prototype).toHaveAttribute("data-active-screen", "market");
    await page.waitForTimeout(7500);
    await expect(prototype).toHaveAttribute("data-active-screen", "market");
  });

  test("pauses the cycle when the prototype leaves the viewport", async ({ page }) => {
    await settle(page);
    const prototype = page.locator('[data-qa="hero-mobile-prototype"]');
    await page.locator('[data-scene="focus"]').scrollIntoViewIfNeeded();
    const state = await prototype.getAttribute("data-active-screen");
    await page.waitForTimeout(4000);
    await expect(prototype).toHaveAttribute("data-active-screen", state);
  });

  test("does not auto-cycle with reduced motion", async ({ browser }) => {
    const context = await browser.newContext({ reducedMotion: "reduce", viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();
    await settle(page);
    const prototype = page.locator('[data-qa="hero-mobile-prototype"]');
    await page.waitForTimeout(6000);
    await expect(prototype).toHaveAttribute("data-active-screen", "market");
    await page.getByRole("tab", { name: "Research" }).click();
    await expect(prototype).toHaveAttribute("data-active-screen", "research");
    await context.close();
  });
});
