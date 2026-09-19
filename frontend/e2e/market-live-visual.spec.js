import { expect, test } from "@playwright/test";
import path from "node:path";

test.skip(process.env.MARKET_LIVE_QA !== "1", "Opt-in read-only real-provider QA");
test.describe.configure({ mode: "serial" });

const output = path.join(process.cwd(), "test-results", "market-live-qa");

async function healthy(page) {
  await expect(page.getByText("Market unavailable", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Market data is unavailable.", { exact: true })).toHaveCount(0);
  await expect(page.getByText("This market surface is unavailable.", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Retry" })).toHaveCount(0);
}

async function capture(page, name) {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(output, name) });
}

test("captures populated Groww Market workspace at 1440x900", async ({ page }) => {
  test.setTimeout(240_000);
  const nonLocalRequests = [];
  const authorizationHeaders = [];
  const socketUrls = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (!["localhost", "127.0.0.1"].includes(url.hostname)) nonLocalRequests.push(url.origin);
    if (request.headers().authorization) authorizationHeaders.push(request.url());
  });
  page.on("websocket", (socket) => socketUrls.push(socket.url()));
  await page.setViewportSize({ width: 1440, height: 900 });

  await page.goto("/app/market");
  await expect(page.getByRole("heading", { name: "Market Intelligence" })).toBeVisible();
  await expect(page.locator(".market-live-indicator")).toHaveText(/Market closed/i);
  await healthy(page);
  await capture(page, "market-live-1440-overview.png");

  await page.goto("/app/market/indices");
  await expect(page.locator('a[href="/app/market/indices/NIFTY_50"]')).toBeVisible();
  await expect(page.getByRole("link", { name: /NIFTY Bank/ })).toBeVisible();
  await healthy(page);
  await capture(page, "market-live-1440-indices.png");

  await page.goto("/app/market/indices/NIFTY_50");
  await expect(page.getByRole("heading", { name: "NIFTY 50" })).toBeVisible();
  await expect(page.getByRole("img", { name: /Line chart/ })).toBeVisible();
  await healthy(page);
  await capture(page, "market-live-1440-nifty-50.png");

  await page.goto("/app/market/stocks");
  await page.getByRole("searchbox").fill("RELIANCE");
  await expect(page.getByRole("link", { name: /Reliance Industries.*NSE/ }).first()).toBeVisible();
  await healthy(page);
  await capture(page, "market-live-1440-stocks-reliance.png");

  await page.goto("/app/market/instruments/RELIANCE");
  await expect(page.getByRole("heading", { name: "Reliance Industries" })).toBeVisible();
  await expect(page.locator(".market-live-indicator")).toHaveText(/Market closed/i);
  await healthy(page);
  await capture(page, "market-live-1440-reliance-overview.png");

  await page.getByRole("tab", { name: "Chart" }).click();
  await expect(page.getByRole("img", { name: /Line chart/ })).toBeVisible();
  await capture(page, "market-live-1440-reliance-chart.png");

  await page.getByRole("tab", { name: "Depth" }).click();
  await expect(page.getByText("Market depth unavailable.")).toBeVisible();
  await capture(page, "market-live-1440-reliance-depth.png");

  await page.getByRole("tab", { name: "Research" }).click();
  await expect(page.getByText("No instrument-specific research linked.")).toBeVisible();
  await page.getByRole("tab", { name: "Portfolio" }).click();
  await expect(page.getByText(/Not currently held|Current holding/)).toBeVisible();

  await page.goto("/app/market/sectors");
  await expect(page.getByRole("link", { name: "NIFTY IT" })).toBeVisible();
  await healthy(page);
  await capture(page, "market-live-1440-sectors.png");

  await page.goto("/app/market/sectors/NIFTY_IT");
  await expect(page.getByRole("heading", { name: "NIFTY IT" })).toBeVisible();
  await expect(page.getByRole("img", { name: /Line chart/ })).toBeVisible();
  await healthy(page);
  await capture(page, "market-live-1440-sector-nifty-it.png");

  expect(nonLocalRequests).toEqual([]);
  expect(authorizationHeaders).toEqual([]);
  expect(socketUrls.every((url) => ["localhost", "127.0.0.1"].includes(new URL(url).hostname))).toBe(true);
});

test("captures populated Groww overview at 1366x768", async ({ page }) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto("/app/market");
  await expect(page.getByRole("heading", { name: "Market Intelligence" })).toBeVisible();
  await healthy(page);
  await capture(page, "market-live-1366-overview.png");
});

test("captures populated Groww mobile overview and instrument detail", async ({ page }) => {
  test.setTimeout(180_000);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/app/market");
  await expect(page.getByRole("heading", { name: "Market Intelligence" })).toBeVisible();
  await healthy(page);
  await capture(page, "market-live-390-overview.png");

  await page.goto("/app/market/instruments/RELIANCE");
  await expect(page.getByRole("heading", { name: "Reliance Industries" })).toBeVisible();
  await healthy(page);
  const dimensions = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.width + 1);
  await capture(page, "market-live-390-reliance.png");
});

test("global search resolves the real Groww RELIANCE instrument", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/app/market");
  await page.getByRole("button", { name: "Open command palette" }).click();
  await page.getByRole("textbox", { name: "Search commands" }).fill("RELIANCE");
  const option = page.getByRole("option", { name: /Reliance Industries.*NSE.*RELIANCE/i });
  await expect(option).toBeVisible();
  await option.click();
  await expect(page).toHaveURL(/\/app\/market\/instruments\/RELIANCE$/);
  await expect(page.getByRole("heading", { name: "Reliance Industries" })).toBeVisible();
  await healthy(page);
});
