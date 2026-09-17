import { mkdir } from "node:fs/promises";
import { expect, test } from "@playwright/test";

async function settle(page) {
  await page.goto("/");
  await page.locator('[data-scene="resolve"]').waitFor();
  await page.evaluate(() => document.fonts.ready);
  await mkdir("test-results/navbar-qa", { recursive: true });
}

async function moveSceneBehindHeader(page, selector, name, expectedTheme, expectedScene) {
  await page.locator(selector).evaluate((element) => {
    const height = element.dataset.boundary
      ? Math.min(element.offsetHeight * 0.15, 32)
      : Math.min(element.offsetHeight * 0.45, 180);
    window.scrollTo(0, element.offsetTop + height);
  });
  const header = page.locator(".public-header");
  await expect(header).toHaveAttribute("data-theme", expectedTheme);
  await expect(header).toHaveAttribute("data-active-scene", expectedScene);
  await expect(header).toHaveAttribute("data-materialized", "true");
  await page.screenshot({
    animations: "disabled",
    clip: { x: 0, y: 0, width: 1440, height: 104 },
    path: `test-results/navbar-qa/${name}.png`,
  });
}

test.describe("public navbar scene integration", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("uses one full-width header with the correct scene theme", async ({ page }) => {
    await settle(page);
    const header = page.locator(".public-header");
    const material = page.locator(".public-header__material");

    await expect(header).toHaveCount(1);
    await expect(header).toHaveAttribute("data-theme", "light");
    await expect(header).toHaveAttribute("data-materialized", "false");
    const topState = await material.evaluate((element) => ({
      background: getComputedStyle(element).backgroundColor,
      radius: getComputedStyle(element).borderRadius,
      width: element.getBoundingClientRect().width,
    }));
    expect(topState.background).toBe("rgba(0, 0, 0, 0)");
    expect(topState.radius).toBe("0px");
    expect(topState.width).toBeGreaterThanOrEqual(1439);
    await page.screenshot({ animations: "disabled", clip: { x: 0, y: 0, width: 1440, height: 104 }, path: "test-results/navbar-qa/hero-top.png" });

    await page.evaluate(() => window.scrollTo(0, 180));
    await expect(header).toHaveAttribute("data-materialized", "true");
    await expect.poll(() => material.evaluate((element) => getComputedStyle(element).backgroundColor)).not.toBe("rgba(0, 0, 0, 0)");
    await page.screenshot({ animations: "disabled", clip: { x: 0, y: 0, width: 1440, height: 104 }, path: "test-results/navbar-qa/hero-mid.png" });

    await moveSceneBehindHeader(page, '[data-scene="decompose"]', "scene-02", "light", "decompose");
    await moveSceneBehindHeader(page, '[data-boundary="light-dark"]', "light-dark-boundary", "light", "decompose");
    await moveSceneBehindHeader(page, '[data-scene="focus"]', "dark-convergence", "dark", "focus");

    const darkForeground = await page.evaluate(() => ({
      brand: getComputedStyle(document.querySelector(".public-header .brand-mark")).color,
      ctaBackground: getComputedStyle(document.querySelector(".public-header__actions .button")).backgroundColor,
    }));
    expect(darkForeground.brand).toBe("rgb(255, 255, 255)");
    expect(darkForeground.ctaBackground).toBe("rgb(223, 255, 50)");

    await moveSceneBehindHeader(page, '[data-boundary="dark-sky"]', "dark-sky-boundary", "dark", "focus");
    await moveSceneBehindHeader(page, '[data-scene="portfolio-context"]', "portfolio", "light", "portfolio-context");
    await expect(header).toHaveAttribute("data-surface", "sky");
    await moveSceneBehindHeader(page, '[data-scene="resolve"]', "closing", "dark", "resolve");
    await expect(page.locator('[data-nav-item="trade"]')).toHaveAttribute("aria-current", "location");
  });

  test("keeps a single compact header on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await settle(page);
    await expect(page.locator(".public-header")).toHaveCount(1);
    const box = await page.locator(".public-header__inner").boundingBox();
    expect(box.height).toBeLessThanOrEqual(56);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(391);
  });
});
