import { expect, test } from "@playwright/test";

async function settle(page) {
  await page.goto("/");
  await page.locator('[data-scene="resolve"]').waitFor();
  await page.evaluate(() => document.fonts.ready);
}

async function scrollToProgress(page, selector, progress) {
  const metrics = await page.locator(selector).evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return {
      height: element.offsetHeight,
      top: rect.top + window.scrollY,
      viewportHeight: window.innerHeight,
    };
  });
  await page.evaluate(
    ({ height, progress: targetProgress, top, viewportHeight }) => {
      document.documentElement.style.scrollBehavior = "auto";
      window.scrollTo({
        behavior: "instant",
        top: top + Math.max(0, height - viewportHeight) * targetProgress,
      });
    },
    { ...metrics, progress },
  );
  await page.waitForTimeout(800);
}

async function opacity(page, selector) {
  return page.locator(selector).evaluate((element) => Number(getComputedStyle(element).opacity));
}

test.describe("landing sequence remediation", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("reveals Three Perspectives in the required intro, Research, Portfolio, Market order", async ({ page }) => {
    await settle(page);
    const scene = '[data-scene="decompose"]';
    const research = '[data-qa="research-surface"]';
    const portfolio = '[data-qa="separation-portfolio-surface"]';
    const market = '[data-qa="market-surface"]';
    const connector = '[data-qa="separation-connector"]';

    await scrollToProgress(page, scene, 0.12);
    expect(await opacity(page, research)).toBeLessThan(0.05);
    expect(await opacity(page, portfolio)).toBeLessThan(0.05);
    expect(await opacity(page, market)).toBeLessThan(0.05);
    expect(await opacity(page, connector)).toBeLessThan(0.05);

    await scrollToProgress(page, scene, 0.5);
    expect(await opacity(page, research)).toBeGreaterThan(0.9);
    expect(await opacity(page, portfolio)).toBeLessThan(0.05);
    expect(await opacity(page, market)).toBeLessThan(0.05);

    await scrollToProgress(page, scene, 0.77);
    expect(await opacity(page, research)).toBeGreaterThan(0.9);
    expect(await opacity(page, portfolio)).toBeGreaterThan(0.9);
    expect(await opacity(page, market)).toBeLessThan(0.05);

    await scrollToProgress(page, scene, 0.95);
    expect(await opacity(page, research)).toBeGreaterThan(0.9);
    expect(await opacity(page, portfolio)).toBeGreaterThan(0.9);
    expect(await opacity(page, market)).toBeGreaterThan(0.9);

    await scrollToProgress(page, scene, 0.99);
    expect(await opacity(page, connector)).toBeGreaterThan(0.9);
  });

  test("uses short solid light-to-dark and dark-to-Portfolio handoffs", async ({ page }) => {
    await settle(page);
    const metrics = await page.evaluate(() => {
      const box = (selector) => {
        const element = document.querySelector(selector);
        const rect = element.getBoundingClientRect();
        return {
          backgroundImage: getComputedStyle(element).backgroundImage,
          height: rect.height,
          top: rect.top + window.scrollY,
        };
      };
      const decompose = box('[data-scene="decompose"]');
      const lightDark = box('[data-boundary="light-dark"]');
      const focus = box('[data-scene="focus"]');
      const darkSky = box('[data-boundary="dark-sky"]');
      const portfolio = box('[data-scene="portfolio-context"]');
      const darkHeadline = box(".convergence-scene__headline");
      const portfolioHeadline = box(".portfolio-stage__headline");
      return {
        darkHeadlineOffset: darkHeadline.top - focus.top,
        darkSky,
        decomposeEnd: decompose.top + decompose.height,
        focusEnd: focus.top + focus.height,
        focusStart: focus.top,
        lightDark,
        portfolioHeadlineOffset: portfolioHeadline.top - portfolio.top,
        portfolioStart: portfolio.top,
      };
    });

    expect(await page.locator(".scene-transition-band").count()).toBe(0);
    expect(metrics.lightDark.height).toBeLessThanOrEqual(64.5);
    expect(metrics.lightDark.height).toBeLessThanOrEqual(900 * 0.12);
    expect(metrics.lightDark.backgroundImage).toBe("none");
    expect(Math.abs(metrics.decomposeEnd - metrics.lightDark.top)).toBeLessThanOrEqual(2);
    expect(Math.abs(metrics.lightDark.top + metrics.lightDark.height - metrics.focusStart)).toBeLessThanOrEqual(2);
    expect(metrics.darkHeadlineOffset).toBeGreaterThanOrEqual(95);
    expect(metrics.darkHeadlineOffset).toBeLessThanOrEqual(111);

    expect(metrics.darkSky.height).toBeLessThanOrEqual(72.5);
    expect(metrics.darkSky.height).toBeLessThanOrEqual(900 * 0.12);
    expect(metrics.darkSky.backgroundImage).toBe("none");
    expect(Math.abs(metrics.focusEnd - metrics.darkSky.top)).toBeLessThanOrEqual(2);
    expect(Math.abs(metrics.darkSky.top + metrics.darkSky.height - metrics.portfolioStart)).toBeLessThanOrEqual(2);
    expect(metrics.portfolioHeadlineOffset).toBeGreaterThanOrEqual(80);
    expect(metrics.portfolioHeadlineOffset).toBeLessThanOrEqual(111);
  });

  test("keeps reassembly entries separate, then converges before the wordmark", async ({ page }) => {
    await settle(page);
    const scene = '[data-scene="reassemble"]';
    const portfolio = '[data-qa="reassembly-portfolio"]';
    const research = '[data-qa="reassembly-research"]';
    const market = '[data-qa="reassembly-market"]';
    const connector = '[data-qa="reassembly-connector"]';
    const wordmark = '[data-qa="reassembly-wordmark"]';

    await scrollToProgress(page, scene, 0.22);
    expect(await opacity(page, portfolio)).toBeGreaterThan(0.9);
    expect(await opacity(page, research)).toBeLessThan(0.05);
    expect(await opacity(page, market)).toBeLessThan(0.05);

    await scrollToProgress(page, scene, 0.52);
    expect(await opacity(page, portfolio)).toBeGreaterThan(0.9);
    expect(await opacity(page, research)).toBeGreaterThan(0.9);
    expect(await opacity(page, market)).toBeLessThan(0.05);

    await scrollToProgress(page, scene, 0.78);
    const dwellState = await page.evaluate(({ connector, market, research, wordmark }) => {
      const translateX = (selector) => new DOMMatrixReadOnly(getComputedStyle(document.querySelector(selector)).transform).m41;
      return {
        connectorOpacity: Number(getComputedStyle(document.querySelector(connector)).opacity),
        marketOpacity: Number(getComputedStyle(document.querySelector(market)).opacity),
        marketX: translateX(market),
        researchX: translateX(research),
        wordmarkOpacity: Number(getComputedStyle(document.querySelector(wordmark)).opacity),
      };
    }, { connector, market, research, wordmark });
    expect(dwellState.marketOpacity).toBeGreaterThan(0.9);
    expect(dwellState.connectorOpacity).toBeLessThan(0.05);
    expect(dwellState.wordmarkOpacity).toBeLessThan(0.05);

    await scrollToProgress(page, scene, 0.938);
    const convergenceState = await page.evaluate(({ connector, market, research, wordmark }) => {
      const translateX = (selector) => new DOMMatrixReadOnly(getComputedStyle(document.querySelector(selector)).transform).m41;
      return {
        connectorOpacity: Number(getComputedStyle(document.querySelector(connector)).opacity),
        marketX: translateX(market),
        researchX: translateX(research),
        wordmarkOpacity: Number(getComputedStyle(document.querySelector(wordmark)).opacity),
      };
    }, { connector, market, research, wordmark });
    expect(convergenceState.connectorOpacity).toBeGreaterThan(0.9);
    expect(convergenceState.researchX).toBeGreaterThan(dwellState.researchX + 20);
    expect(convergenceState.marketX).toBeLessThan(dwellState.marketX - 20);
    expect(convergenceState.wordmarkOpacity).toBeLessThan(0.2);

    await scrollToProgress(page, scene, 0.99);
    expect(await opacity(page, wordmark)).toBeGreaterThan(0.9);
  });
});

for (const viewport of [{ width: 768, height: 1024 }, { width: 390, height: 844 }]) {
  test.describe(`${viewport.width}px responsive reassembly`, () => {
    test.use({ viewport });

    test("reveals Portfolio, Research, Market, then INTERSIGNAL in normal flow", async ({ page }) => {
      await settle(page);
      const portfolio = page.locator('[data-qa="reassembly-flow-portfolio"]');
      const research = page.locator('[data-qa="reassembly-flow-research"]');
      const market = page.locator('[data-qa="reassembly-flow-market"]');
      const wordmark = page.locator('[data-qa="reassembly-flow-wordmark"]');

      await expect(page.locator('[data-qa="reassembly-stage"]')).toBeHidden();
      await portfolio.scrollIntoViewIfNeeded();
      await page.waitForTimeout(700);
      expect(await opacity(page, '[data-qa="reassembly-flow-portfolio"]')).toBeGreaterThan(0.9);
      expect(await opacity(page, '[data-qa="reassembly-flow-research"]')).toBeLessThan(0.1);
      expect(await opacity(page, '[data-qa="reassembly-flow-market"]')).toBeLessThan(0.1);

      await research.scrollIntoViewIfNeeded();
      await page.waitForTimeout(700);
      expect(await opacity(page, '[data-qa="reassembly-flow-research"]')).toBeGreaterThan(0.9);
      expect(await opacity(page, '[data-qa="reassembly-flow-market"]')).toBeLessThan(0.1);

      await market.scrollIntoViewIfNeeded();
      await page.waitForTimeout(700);
      expect(await opacity(page, '[data-qa="reassembly-flow-market"]')).toBeGreaterThan(0.9);
      expect(await opacity(page, '[data-qa="reassembly-flow-wordmark"]')).toBeLessThan(0.1);

      await wordmark.evaluate((element) => element.scrollIntoView({ block: "center", behavior: "instant" }));
      await page.waitForTimeout(700);
      expect(await opacity(page, '[data-qa="reassembly-flow-wordmark"]')).toBeGreaterThan(0.9);
    });
  });
}
