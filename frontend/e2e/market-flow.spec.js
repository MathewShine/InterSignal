import { expect, test } from "@playwright/test";

const snapshotPath = "/api/market/snapshot";
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

test("Home Market context enters the backend-backed recorded snapshot", async ({ page }) => {
  const marketRequests = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === snapshotPath) marketRequests.push(request.method());
  });
  await page.goto("/auth?mode=signin");
  await page.getByLabel("Email address").fill("demo@example.com");
  await page.getByLabel("Password", { exact: true }).fill("prototype-only");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByText("Sample market data", { exact: true })).toBeVisible();
  await page.locator(".market-canvas__open-market").click();
  await expect(page).toHaveURL(/\/app\/market$/);
  await expect(page.getByRole("heading", { name: "Market Intelligence", level: 1 })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("Recorded 7 Sep 2026", { exact: true })).toBeVisible();
  await expect(page.getByText("Historical snapshot", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("498/501 · 99.4012%", { exact: true })).toBeVisible();
  expect(marketRequests).toEqual(["GET"]);
});

test("Market workspace flows from indices through stock analysis to sectors", async ({ page }) => {
  await page.goto("/auth?mode=signin");
  await page.getByLabel("Email address").fill("demo@example.com");
  await page.getByLabel("Password", { exact: true }).fill("prototype-only");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.locator('.app-rail__link[aria-label="Market"]').click();
  await expect(page).toHaveURL(/\/app\/market$/);

  await page.getByRole("navigation", { name: "Market sections" }).getByRole("link", { name: "Indices" }).click();
  await expect(page).toHaveURL(/\/app\/market\/indices$/);
  await page.locator('a[href="/app/market/indices/NIFTY_50"]').click();
  await expect(page).toHaveURL(/\/app\/market\/indices\/NIFTY_50$/);
  await expect(page.getByRole("heading", { name: "Historical chart" })).toBeVisible();

  await page.getByRole("navigation", { name: "Market sections" }).getByRole("link", { name: "Stocks" }).click();
  await page.getByRole("searchbox").fill("RELIANCE");
  await page.getByRole("link", { name: /Reliance Industries/ }).first().click();
  await expect(page).toHaveURL(/\/app\/market\/instruments\/RELIANCE$/);
  await expect(page.getByRole("heading", { name: "Reliance Industries" })).toBeVisible();
  await expect(page.getByText("Market closed", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Chart" }).click();
  await expect(page.getByRole("img", { name: /Line chart/ })).toBeVisible();
  await page.getByRole("button", { name: "Candlestick" }).click();
  await expect(page.getByRole("img", { name: /Candlestick chart/ })).toBeVisible();
  await page.getByRole("tab", { name: "Depth" }).click();
  await expect(page.getByText("Market depth unavailable.")).toBeVisible();

  await page.getByRole("navigation", { name: "Market sections" }).getByRole("link", { name: "Sectors" }).click();
  await expect(page).toHaveURL(/\/app\/market\/sectors$/);
  const sector = page.locator(".market-table-wrap tbody a").first();
  const sectorName = await sector.textContent();
  await sector.click();
  await expect(page.getByRole("heading", { name: sectorName.trim() })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Historical chart" })).toBeVisible();
  await expect(page.getByText(/Buy|Sell|Trade|Order ticket/, { exact: false })).toHaveCount(0);
});

for (const viewport of [{ width: 1920, height: 1080 }, { width: 1536, height: 960 }, { width: 1024, height: 768 }, { width: 768, height: 1024 }, { width: 390, height: 844 }]) {
  test(`Instrument workspace ${viewport.width}x${viewport.height} is responsive`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/app/market/instruments/RELIANCE");
    await expect(page.getByRole("heading", { name: "Reliance Industries" })).toBeVisible();
    await page.getByRole("tab", { name: "Chart" }).click();
    await expect(page.getByRole("img", { name: /Line chart/ })).toBeVisible();
    const dimensions = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, width: window.innerWidth }));
    expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.width + 1);
  });
}

test("Market renders the full recorded breadth, sector, volume and limitation truth", async ({ page }) => {
  await page.goto("/app/market");
  await expect(page.getByRole("heading", { name: "NIFTY 500", exact: true, level: 2 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "NIFTY 50", exact: true, level: 2 })).toBeVisible();
  await expect(page.getByText("171", { exact: true })).toBeVisible();
  await expect(page.getByText("325", { exact: true })).toBeVisible();
  await expect(page.getByText("2", { exact: true })).toBeVisible();
  await expect(page.getByText("34.3373%", { exact: true })).toBeVisible();
  await expect(page.getByText("6,434,397.70", { exact: true })).toBeVisible();
  await expect(page.getByText("0.9296×", { exact: true })).toBeVisible();
  await expect(page.getByText(/213.*members above 20-session baseline/)).toBeVisible();
  const vwap = page.getByText("Above VWAP", { exact: true }).locator("..");
  await expect(vwap).toContainText("Unavailable");
  const table = page.getByRole("table", { name: "Sector performance" });
  await expect(table).toBeVisible();
  await expect(table.getByRole("row")).toHaveCount(24);
  await expect(page.getByText("The snapshot is recorded NSE end-of-day data; no live market source is configured.", { exact: true })).toBeVisible();
  await expect(page.getByText(/buy|sell|order ticket|entry signal|exit signal/i)).toHaveCount(0);
});

test("sector sort controls preserve all 23 recorded rows", async ({ page }) => {
  await page.goto("/app/market");
  const table = page.getByRole("table", { name: "Sector performance" });
  const sort = page.getByRole("combobox", { name: "Sort sectors" });
  await sort.selectOption("name");
  await expect(table.getByRole("row").nth(1)).toContainText("NIFTY AUTO");
  await sort.selectOption("breadth");
  await expect(table.getByRole("row").nth(1)).toContainText("NIFTY HEALTHCARE");
  await sort.selectOption("performance");
  await expect(table.getByRole("row").nth(1)).toContainText("NIFTY500 HEALTH");
  await expect(table.getByRole("row")).toHaveCount(24);
});

test("Market command palette exposes overview, breadth and sector context", async ({ page }) => {
  await page.goto("/app/market");
  await page.getByRole("button", { name: "Open command palette" }).click();
  const input = page.getByRole("textbox", { name: "Search commands" });
  await input.fill("Market breadth");
  await page.getByRole("option", { name: /Market breadth/ }).click();
  await expect(page).toHaveURL(/\/app\/market#breadth$/);
  await expect(page.getByRole("heading", { name: "Market breadth" })).toBeVisible();
  await page.getByRole("button", { name: "Open command palette" }).click();
  await input.fill("Sector context");
  await page.getByRole("option", { name: /Sector context/ }).click();
  await expect(page).toHaveURL(/\/app\/market#sectors$/);
});

test("global search resolves a normalized Market instrument", async ({ page }) => {
  await page.goto("/app/market");
  await page.getByRole("button", { name: "Open command palette" }).click();
  await page.getByRole("textbox", { name: "Search commands" }).fill("RELIANCE");
  const option = page.getByRole("option", { name: /Reliance Industries.*NSE.*RELIANCE/i });
  await expect(option).toBeVisible();
  await option.click();
  await expect(page).toHaveURL(/\/app\/market\/instruments\/RELIANCE$/);
  await expect(page.getByRole("heading", { name: "Reliance Industries" })).toBeVisible();
});

test("missing depth does not affect the instrument overview or chart", async ({ page }) => {
  await page.route("**/api/market/instruments/RELIANCE/quote", async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    payload.quote.buy_depth = [];
    payload.quote.sell_depth = [];
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) });
  });
  await page.goto("/app/market/instruments/RELIANCE");
  await expect(page.getByRole("heading", { name: "Reliance Industries" })).toBeVisible();
  await page.getByRole("tab", { name: "Chart" }).click();
  await expect(page.getByRole("img", { name: /Line chart/ })).toBeVisible();
  await page.getByRole("tab", { name: "Depth" }).click();
  await expect(page.getByText("Market depth unavailable.")).toBeVisible();
});

test("missing candles leave the instrument quote and depth usable", async ({ page }) => {
  await page.route("**/api/market/instruments/RELIANCE/candles**", (route) => route.abort("failed"));
  await page.goto("/app/market/instruments/RELIANCE");
  await expect(page.getByRole("heading", { name: "Reliance Industries" })).toBeVisible();
  await page.getByRole("tab", { name: "Chart" }).click();
  await expect(page.getByText("Historical candles are unavailable for this range.")).toBeVisible();
  await expect(page.getByText("Historical candles unavailable; the current quote remains usable.")).toBeVisible();
  await page.getByRole("tab", { name: "Depth" }).click();
  await expect(page.getByText("Market depth unavailable.")).toBeVisible();
});

test("search failure does not disturb an already-open instrument", async ({ page }) => {
  await page.goto("/app/market/instruments/RELIANCE");
  await expect(page.getByRole("heading", { name: "Reliance Industries" })).toBeVisible();
  await page.route("**/api/market/instruments/search**", (route) => route.abort("failed"));
  await page.getByRole("button", { name: "Open command palette" }).click();
  await page.getByRole("textbox", { name: "Search commands" }).fill("RELIANCE");
  await expect(page.getByRole("option", { name: /Reliance Industries.*NSE.*RELIANCE/i })).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("heading", { name: "Reliance Industries" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Session overview" })).toBeVisible();
});

test("a transport failure stays compact and retries without sample fallback", async ({ page }) => {
  let failOnce = true;
  await page.route(`**${snapshotPath}`, async (route) => {
    if (failOnce) { failOnce = false; await route.abort("failed"); } else await route.continue();
  });
  await page.goto("/app/market");
  const alert = page.getByRole("alert");
  await expect(alert).toContainText("Market data is unavailable.");
  await expect(alert).toContainText("Research and Portfolio remain accessible.");
  await expect(alert).toContainText("No sample market records have been substituted.");
  const box = await alert.boundingBox();
  expect(box.height).toBeLessThan(300);
  expect(box.y).toBeLessThan(300);
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByRole("heading", { name: "Market Intelligence" })).toBeVisible();
});

test("partial sector failure retains breadth and volume context", async ({ page }) => {
  await page.route(`**${snapshotPath}`, async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    payload.sectors = [];
    payload.availability.sectors = { status: "UNAVAILABLE", reason: "SECTOR_TEST_UNAVAILABLE" };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) });
  });
  await page.goto("/app/market");
  await expect(page.getByText("Sector context is unavailable for this snapshot.")).toBeVisible();
  await expect(page.getByText("171", { exact: true })).toBeVisible();
  await expect(page.getByText("6,434,397.70", { exact: true })).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("controlled unavailable mode does not substitute recorded values", async ({ page }) => {
  await page.route(`**${snapshotPath}`, async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    payload.status = "UNAVAILABLE";
    payload.provider.mode = "UNAVAILABLE";
    payload.indices = [];
    payload.breadth = null;
    payload.sectors = [];
    payload.volume = null;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) });
  });
  await page.goto("/app/market");
  await expect(page.getByRole("status")).toContainText("Market data is unavailable.");
  await expect(page.getByText("23,156.20", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Sample market data", { exact: true })).toHaveCount(0);
});

for (const viewport of [{ width: 1440, height: 900 }, { width: 1366, height: 768 }]) {
  test(`Market sidebar reflows content at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/app/market");
    const workspace = page.locator(".app-workspace");
    await expect(page.getByRole("heading", { name: "Market Intelligence" })).toBeVisible();
    const before = await workspace.boundingBox();
    await page.locator(".app-rail").hover();
    await expect(page.locator(".authenticated-shell")).toHaveAttribute("data-rail-expanded", "true");
    await expect.poll(async () => (await workspace.boundingBox())?.x).toBeGreaterThan(before.x + 100);
    await expect.poll(async () => (await workspace.boundingBox())?.width).toBeLessThan(before.width - 100);
  });
}

for (const viewport of viewports) {
  test(`Market ${viewport.width}x${viewport.height} has no page overflow`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/app/market");
    await expect(page.getByRole("heading", { name: "Market Intelligence" })).toBeVisible();
    const dimensions = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, width: window.innerWidth }));
    expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.width + 1);
    if (viewport.width === 390) await expect(page.getByRole("navigation", { name: "Mobile app" })).toBeVisible();
  });
}

for (const viewport of [{ width: 1440, height: 900 }, { width: 1366, height: 768 }]) {
  test(`${viewport.width}x${viewport.height} first view contains the complete market summary`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/app/market");
    for (const locator of [
      page.getByRole("heading", { name: "NIFTY 500", exact: true }),
      page.getByRole("heading", { name: "NIFTY 50", exact: true }),
      page.getByRole("heading", { name: "Market breadth" }),
      page.getByRole("heading", { name: "Sector leadership" }),
      page.getByRole("heading", { name: "Volume context" }),
      page.getByText("Historical snapshot", { exact: true }).first(),
    ]) {
      const box = await locator.boundingBox();
      expect(box.y).toBeGreaterThanOrEqual(0);
      expect(box.y + box.height).toBeLessThanOrEqual(viewport.height);
    }
  });
}

test("mobile order and accessibility remain explicit", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.route(`**${snapshotPath}`, async (route) => { await new Promise((resolve) => setTimeout(resolve, 250)); await route.continue(); });
  await page.goto("/app/market");
  const loading = page.getByRole("status", { name: "Loading Market" });
  await expect(loading).toBeVisible();
  await expect(loading.locator(".market-skeleton").first()).toHaveCSS("animation-name", "none");
  await expect(page.getByRole("table", { name: "Sector performance" })).toBeVisible();
  const order = await Promise.all([
    page.locator(".market-primary-panel"),
    page.locator(".market-reference-panel"),
    page.locator("#breadth"),
    page.locator("#volume"),
    page.locator(".market-sector-pulse"),
    page.locator("#quality"),
  ].map(async (locator) => (await locator.boundingBox()).y));
  expect(order).toEqual([...order].sort((a, b) => a - b));
  await page.getByRole("combobox", { name: "Sort sectors" }).focus();
  await expect(page.getByRole("combobox", { name: "Sort sectors" })).toBeFocused();
});
