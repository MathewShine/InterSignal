import { expect, test } from "@playwright/test";

test("dummy sign in to Home to Portfolio uses the real backend end to end", async ({ page }) => {
  const portfolioResponses = [];
  page.on("response", (response) => {
    if (new URL(response.url()).pathname.startsWith("/api/portfolio/")) portfolioResponses.push(response);
  });

  await page.goto("/auth?mode=signin");
  await page.getByLabel("Email address").fill("demo@example.com");
  await page.getByLabel("Password", { exact: true }).fill("prototype-only");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/app$/);
  const homeValue = await page.locator(".portfolio-strip__value strong").innerText();
  await page.getByRole("link", { name: "View portfolio →" }).click();

  await expect(page).toHaveURL(/\/app\/portfolio$/);
  await expect(page.getByRole("heading", { name: "Portfolio", exact: true })).toBeVisible();
  await expect(page.locator(".portfolio-summary-primary strong")).toHaveText(homeValue);
  await expect(page.getByText("Demo portfolio", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Synthetic Mutual Fund One", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Diversified", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Sell", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("19.09%", { exact: true }).first()).toBeVisible();
  expect(portfolioResponses.some((response) => new URL(response.url()).pathname === "/api/portfolio/overview" && response.status() === 200)).toBe(true);
});

for (const [path, heading, endpoint] of [
  ["/app/portfolio", "Portfolio", "/api/portfolio/overview"],
  ["/app/portfolio/holdings", "Holdings", "/api/portfolio/holdings"],
  ["/app/portfolio/activity", "Portfolio activity", "/api/portfolio/activity"],
  ["/app/portfolio/performance", "Performance", "/api/portfolio/performance"],
]) {
  test(`${path} is a working backend-backed route`, async ({ page }) => {
    const responsePromise = page.waitForResponse((response) => new URL(response.url()).pathname === endpoint);
    await page.goto(path);
    const response = await responsePromise;
    expect(response.status()).toBe(200);
    expect((await response.json()).version).toBe("INTERSIGNAL_PORTFOLIO_OS_V1");
    await expect(page.getByRole("heading", { name: heading, exact: true, level: 1 })).toBeVisible();
    await expect(page.getByText("Portfolio data couldn’t be loaded.")).toHaveCount(0);
  });
}

test("overview uses one aggregated request without holding-level calls", async ({ page }) => {
  const requests = [];
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (path.startsWith("/api/portfolio/")) requests.push(path);
  });
  await page.goto("/app/portfolio");
  await expect(page.getByText("Synthetic Mutual Fund One", { exact: true }).first()).toBeVisible();
  expect(requests).toEqual(["/api/portfolio/overview"]);
});

test("portfolio selector reads the second first-class backend portfolio", async ({ page }) => {
  await page.goto("/app/portfolio");
  await page.getByRole("combobox", { name: "Select portfolio" }).selectOption("PORT-RESEARCH-SYNTHETIC-001");
  await expect(page).toHaveURL(/portfolio_id=PORT-RESEARCH-SYNTHETIC-001/);
  await expect(page.locator(".portfolio-summary-primary strong")).toHaveText("₹1,00,980");
  await expect(page.getByText("Synthetic Equity One", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Synthetic Technology", { exact: true }).first()).toBeVisible();
});

test("holding detail is read-only, keyboard accessible and includes FIFO lots", async ({ page }) => {
  await page.goto("/app/portfolio/holdings");
  await page.getByRole("button", { name: "View" }).first().click();
  const dialog = page.getByRole("dialog", { name: /Synthetic Mutual Fund One holding detail/ });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("FIFO lots")).toBeVisible();
  await expect(dialog.getByText("Partly realised")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Close holding detail" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("button", { name: /^Buy$/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Sell$/i })).toHaveCount(0);
});

test("holdings search, sector filter and sort work locally", async ({ page }) => {
  await page.goto("/app/portfolio/holdings");
  await expect(page.getByText("Synthetic Mutual Fund One", { exact: true }).first()).toBeVisible();
  await page.getByRole("searchbox", { name: "Search" }).fill("missing");
  await expect(page.getByText("No holdings in this portfolio.")).toBeVisible();
  await page.getByRole("searchbox", { name: "Search" }).fill("");
  await page.getByRole("combobox", { name: "Sector" }).selectOption("Diversified");
  await page.getByRole("button", { name: "Sort by Security" }).click();
  await expect(page.getByText(/sorted by name ascending/i)).toBeVisible();
});

test("command palette exposes every Portfolio destination", async ({ page }) => {
  await page.goto("/app/portfolio");
  await expect(page.getByRole("heading", { name: "Portfolio", exact: true, level: 1 })).toBeVisible();
  await page.keyboard.press("Control+K");
  const dialog = page.getByRole("dialog", { name: "Command palette" });
  const input = page.getByRole("textbox", { name: "Search commands" });
  for (const [query, expected] of [["Portfolio", "Portfolio"], ["Holdings", "Holdings"], ["Portfolio activity", "Portfolio activity"], ["Performance", "Performance"]]) {
    await input.fill(query);
    await expect(dialog.getByRole("option", { name: expected, exact: false }).first()).toBeVisible();
  }
});

test("Portfolio error retries into live backend data without a fallback", async ({ page }) => {
  let failOnce = true;
  await page.route("**/api/portfolio/overview", async (route) => {
    if (failOnce) { failOnce = false; await route.abort("failed"); return; }
    await route.continue();
  });
  await page.goto("/app/portfolio");
  await expect(page.getByRole("alert")).toContainText("Portfolio data couldn’t be loaded.");
  await expect(page.getByText("No demo holdings have been substituted.")).toBeVisible();
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByText("Synthetic Mutual Fund One", { exact: true }).first()).toBeVisible();
});

const viewports = [
  { width: 1920, height: 1080 }, { width: 1536, height: 960 }, { width: 1440, height: 900 }, { width: 1366, height: 768 },
  { width: 1280, height: 800 }, { width: 1024, height: 768 }, { width: 768, height: 1024 }, { width: 390, height: 844 },
];

for (const viewport of viewports) {
  test(`${viewport.width}x${viewport.height} Portfolio avoids page-level horizontal overflow`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/app/portfolio");
    await expect(page.locator(".portfolio-summary-primary strong")).toHaveText("₹52,393");
    const dimensions = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, width: window.innerWidth }));
    expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.width + 1);
  });
}

test("1366 desktop keeps value, allocation and holdings visible", async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto("/app/portfolio");
  for (const item of [page.getByText("Portfolio value", { exact: true }), page.getByText("Invested", { exact: true }).first(), page.getByText("Cash", { exact: true }).first(), page.getByText("Period change", { exact: true }), page.getByRole("heading", { name: "Holdings", exact: true }).first(), page.getByRole("heading", { name: "Allocation & exposure" })]) await expect(item).toBeVisible();
  await expect(page.getByText("Synthetic Mutual Fund One", { exact: true }).first()).toBeVisible();
});

test("mobile uses holding cards, allocation-first flow and bottom navigation", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/app/portfolio");
  await expect(page.getByRole("navigation", { name: "Mobile app" })).toBeVisible();
  await expect(page.locator(".portfolio-table-wrap")).toBeHidden();
  await expect(page.locator(".holding-card")).toHaveCount(1);
  const order = await page.locator(".portfolio-overview-grid > article").evaluateAll((items) => items.map((item) => getComputedStyle(item).order));
  expect(order).toEqual(["2", "1"]);
});
