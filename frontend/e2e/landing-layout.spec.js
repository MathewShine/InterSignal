import { expect, test } from "@playwright/test";

const viewports = [
  { width: 1920, height: 1080 },
  { width: 1728, height: 1117 },
  { width: 1536, height: 960 },
  { width: 1440, height: 900 },
  { width: 1366, height: 768 },
  { width: 1280, height: 800 },
  { width: 1024, height: 768 },
  { width: 768, height: 1024 },
  { width: 390, height: 844 },
];

async function settle(page) {
  await page.goto("/");
  await page.locator('[data-scene="resolve"]').waitFor();
  await page.evaluate(() => document.fonts.ready);
}

function boxesIntersect(a, b) {
  return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
}

for (const viewport of viewports) {
  test.describe(`${viewport.width}x${viewport.height}`, () => {
    test.use({ viewport });

    test("keeps the layout inside the viewport and the hero ownership zones safe", async ({ page }) => {
      await settle(page);

      const metrics = await page.evaluate(() => {
        const header = document.querySelector(".public-header__material").getBoundingClientRect();
        const headline = document.querySelector(".kinetic-headline").getBoundingClientRect();
        const product = document.querySelector('[data-qa="hero-mobile-prototype"]').getBoundingClientRect();
        const headlineZone = document.querySelector('[data-qa="hero-headline-zone"]').getBoundingClientRect();
        const cta = document.querySelector('[data-qa="hero-cta-cluster"] a').getBoundingClientRect();
        return {
          scrollWidth: document.documentElement.scrollWidth,
          viewportWidth: window.innerWidth,
          headerBottom: header.bottom,
          headlineTop: headline.top,
          headline: { top: headline.top, right: headline.right, bottom: headline.bottom, left: headline.left },
          product: { top: product.top, right: product.right, bottom: product.bottom, left: product.left },
          overlap: Math.max(0, headlineZone.right - product.left),
          cta: { top: cta.top, right: cta.right, bottom: cta.bottom, left: cta.left },
        };
      });

      expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.viewportWidth + 1);
      expect(metrics.headerBottom).toBeLessThanOrEqual(metrics.headlineTop);
      if (viewport.width >= 1024) expect(metrics.overlap).toBeLessThanOrEqual(2);
      if (viewport.width === 1366 || viewport.width === 1440) expect(boxesIntersect(metrics.headline, metrics.product)).toBe(false);
      expect(metrics.cta.left).toBeGreaterThanOrEqual(0);
      expect(metrics.cta.right).toBeLessThanOrEqual(viewport.width + 1);
      await expect(page.locator('[data-qa="hero-cta-cluster"] a')).toBeVisible();
      await page.locator('[data-qa="hero-cta-cluster"] a').click({ trial: true });
    });

    test("keeps scene headings clear of the materialized header", async ({ page }) => {
      await settle(page);
      const headings = page.locator('[data-scene] h1, [data-scene] h2');

      for (let index = 0; index < await headings.count(); index += 1) {
        const heading = headings.nth(index);
        await heading.evaluate((element) => {
          const top = element.getBoundingClientRect().top + window.scrollY;
          window.scrollTo(0, Math.max(0, top - 112));
        });
        await page.waitForTimeout(80);
        const headingBox = await heading.boundingBox();
        const headerBox = await page.locator(".public-header__material").boundingBox();
        expect(headingBox).not.toBeNull();
        expect(headerBox).not.toBeNull();
        expect(headingBox.y).toBeGreaterThanOrEqual(headerBox.y + headerBox.height + 8);
      }
    });

    test("finishes sticky scenes before the next scene and gates the wordmark", async ({ page }) => {
      await settle(page);

      const boundaries = await page.evaluate(() => {
        const focus = document.querySelector('[data-scene="focus"]');
        const lightDark = document.querySelector('[data-boundary="light-dark"]');
        const darkSky = document.querySelector('[data-boundary="dark-sky"]');
        const portfolio = document.querySelector('[data-scene="portfolio-context"]');
        const decompose = document.querySelector('[data-scene="decompose"]');
        const reassembly = document.querySelector('[data-scene="reassemble"]');
        const closing = document.querySelector('[data-scene="resolve"]');
        return {
          decomposeEnd: decompose.offsetTop + decompose.offsetHeight,
          lightDarkStart: lightDark.offsetTop,
          lightDarkEnd: lightDark.offsetTop + lightDark.offsetHeight,
          focusStart: focus.offsetTop,
          focusEnd: focus.offsetTop + focus.offsetHeight,
          darkSkyStart: darkSky.offsetTop,
          darkSkyEnd: darkSky.offsetTop + darkSky.offsetHeight,
          portfolioStart: portfolio.offsetTop,
          reassemblyEnd: reassembly.offsetTop + reassembly.offsetHeight,
          closingStart: closing.offsetTop,
        };
      });

      expect(Math.abs(boundaries.decomposeEnd - boundaries.lightDarkStart)).toBeLessThanOrEqual(2);
      expect(Math.abs(boundaries.lightDarkEnd - boundaries.focusStart)).toBeLessThanOrEqual(2);
      expect(Math.abs(boundaries.focusEnd - boundaries.darkSkyStart)).toBeLessThanOrEqual(2);
      expect(Math.abs(boundaries.darkSkyEnd - boundaries.portfolioStart)).toBeLessThanOrEqual(2);
      expect(Math.abs(boundaries.reassemblyEnd - boundaries.closingStart)).toBeLessThanOrEqual(2);

      const wordmark = page.locator('[data-qa="reassembly-wordmark"]');
      if (viewport.width >= 1024) {
        const section = page.locator('[data-scene="reassemble"]');
        const box = await section.boundingBox();
        const scrollRange = box.height - viewport.height;
        await page.evaluate(({ top, offset }) => window.scrollTo(0, top + offset), { top: box.y, offset: scrollRange * 0.72 });
        await page.waitForTimeout(450);
        expect(Number(await wordmark.evaluate((element) => getComputedStyle(element).opacity))).toBeLessThan(0.25);
        await page.evaluate(({ top, offset }) => window.scrollTo(0, top + offset), { top: box.y, offset: scrollRange * 0.98 });
        await page.waitForTimeout(650);
        expect(Number(await wordmark.evaluate((element) => getComputedStyle(element).opacity))).toBeGreaterThan(0.7);
      } else {
        const flowWordmark = page.locator('[data-qa="reassembly-flow-wordmark"]');
        await flowWordmark.scrollIntoViewIfNeeded();
        await page.waitForTimeout(700);
        await expect(flowWordmark).toBeVisible();
      }
    });

    if (viewport.width === 1366) {
      test("keeps the laptop hero essentials in the first viewport", async ({ page }) => {
        await settle(page);
        const essentials = await page.evaluate(() => {
          const selectors = [".kinetic-headline", ".signal-hero__mobile", '[data-qa="hero-cta-cluster"]'];
          return selectors.map((selector) => {
            const box = document.querySelector(selector).getBoundingClientRect();
            const visibleHeight = Math.max(0, Math.min(box.bottom, innerHeight) - Math.max(box.top, 0));
            return { selector, ratio: visibleHeight / Math.max(1, box.height) };
          });
        });
        expect(essentials.find((item) => item.selector === ".kinetic-headline").ratio).toBeGreaterThan(0.98);
        expect(essentials.find((item) => item.selector === ".signal-hero__mobile").ratio).toBeGreaterThan(0.72);
        expect(essentials.find((item) => item.selector === '[data-qa="hero-cta-cluster"]').ratio).toBeGreaterThan(0.98);
      });
    }

    if (viewport.width === 1366 || viewport.width === 1440) {
      test("keeps product surfaces, convergence copy, navigation, and final CTA collision-free", async ({ page }) => {
        await settle(page);

        const scene = page.locator('[data-scene="decompose"]');
        const sceneBox = await scene.evaluate((element) => ({ top: element.offsetTop, height: element.offsetHeight }));
        await page.evaluate(({ top, offset }) => window.scrollTo(0, top + offset), {
          top: sceneBox.top,
          offset: Math.max(0, sceneBox.height - viewport.height) * 0.98,
        });
        await page.waitForTimeout(700);

        const spacing = await page.evaluate(() => {
          const rect = (selector) => {
            const box = document.querySelector(selector).getBoundingClientRect();
            return { left: box.left, right: box.right };
          };
          const research = rect('[data-qa="research-surface"]');
          const portfolio = rect('[data-qa="separation-portfolio-surface"]');
          const market = rect('[data-qa="market-surface"]');
          return {
            researchPortfolio: portfolio.left - research.right,
            portfolioMarket: market.left - portfolio.right,
          };
        });
        const requiredGutter = viewport.width >= 1440 ? 56 : 40;
        expect(spacing.researchPortfolio).toBeGreaterThanOrEqual(requiredGutter);
        expect(spacing.portfolioMarket).toBeGreaterThanOrEqual(requiredGutter);

        await page.evaluate(() => window.scrollTo(0, 0));
        await page.waitForTimeout(2300);
        const heroCollisions = await page.evaluate(() => {
          const box = (selector) => {
            const rect = document.querySelector(selector).getBoundingClientRect();
            return { top: rect.top, right: rect.right, bottom: rect.bottom, left: rect.left };
          };
          return {
            breadth: box('[data-datum="breadth"]'),
            deviceHeader: box('.mobile-prototype__header'),
            exposure: box('[data-datum="market-exposure"]'),
            cta: box('[data-qa="hero-cta-cluster"]'),
          };
        });
        expect(boxesIntersect(heroCollisions.breadth, heroCollisions.deviceHeader)).toBe(false);
        expect(boxesIntersect(heroCollisions.exposure, heroCollisions.cta)).toBe(false);

        const focus = page.locator('[data-scene="focus"]');
        const focusBox = await focus.evaluate((element) => ({ top: element.offsetTop, height: element.offsetHeight }));
        await page.evaluate(({ top, offset }) => window.scrollTo(0, top + offset), {
          top: focusBox.top,
          offset: Math.max(0, focusBox.height - viewport.height) * 0.98,
        });
        await page.waitForTimeout(700);
        await expect(page.locator('[data-qa="convergence-copy"]')).toBeVisible();

        const finalCTA = page.locator('[data-qa="final-cta"]');
        await finalCTA.evaluate((element) => element.scrollIntoView({ block: "center" }));
        await expect(finalCTA).toBeVisible();

        const nav = await page.locator(".public-header__nav").boundingBox();
        const actions = await page.locator(".public-header__actions").boundingBox();
        expect(nav).not.toBeNull();
        expect(actions).not.toBeNull();
        expect(nav.x + nav.width).toBeLessThanOrEqual(actions.x);
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width + 1);
      });
    }
  });
}

test.describe("reduced motion", () => {
  test.use({ reducedMotion: "reduce", viewport: { width: 1440, height: 900 } });

  test("renders every scene in a stable non-sticky final state", async ({ page }) => {
    await settle(page);

    const state = await page.evaluate(() => ({
      convergencePosition: getComputedStyle(document.querySelector(".convergence-scene__sticky")).position,
      reassemblyPosition: getComputedStyle(document.querySelector(".reassembly-scene__sticky")).position,
      convergenceCopyOpacity: Number(getComputedStyle(document.querySelector('[data-qa="convergence-copy"]')).opacity),
      wordmarkOpacity: Number(getComputedStyle(document.querySelector('[data-qa="reassembly-wordmark"]')).opacity),
      prototypeOpacity: Number(getComputedStyle(document.querySelector('[data-qa="hero-mobile-prototype"]')).opacity),
    }));

    expect(state.convergencePosition).not.toBe("sticky");
    expect(state.reassemblyPosition).not.toBe("sticky");
    expect(state.convergenceCopyOpacity).toBeGreaterThan(0.95);
    expect(state.wordmarkOpacity).toBeGreaterThan(0.95);
    expect(state.prototypeOpacity).toBeGreaterThan(0.95);
    await expect(page.locator('[data-qa="research-surface"]')).toBeVisible();
    await expect(page.locator('[data-qa="separation-portfolio-surface"]')).toBeVisible();
    await expect(page.locator('[data-qa="market-surface"]')).toBeVisible();
  });
});
