import { expect, test } from "@playwright/test";

test("authenticated Home to Research flow uses the real backend", async ({ page }) => {
  const researchResponses = [];
  page.on("response", (response) => {
    if (new URL(response.url()).pathname.startsWith("/api/research/")) researchResponses.push(response);
  });

  await page.goto("/auth?mode=signin");
  await page.getByLabel("Email address").fill("demo@example.com");
  await page.getByLabel("Password", { exact: true }).fill("prototype-only");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/app$/);
  await page.getByRole("link", { name: "View research →" }).click();

  await expect(page).toHaveURL(/\/app\/research$/);
  await expect(page.getByRole("heading", { name: "Research", exact: true })).toBeVisible();
  await expect(page.getByText("A–G complete", { exact: true })).toBeVisible();
  await expect(page.getByText("EDGE-EVIDENCE-C-COMPRESSION-001", { exact: true })).toBeVisible();
  await expect(page.getByText("Not production strategy", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "Open Family A" }).click();
  await expect(page).toHaveURL(/\/app\/research\/families\/A$/);
  await expect(page.getByRole("heading", { name: "Medium-Term Cross-Sectional Momentum" })).toBeVisible();
  await expect(page.getByText(/INCONCLUSIVE — an implementation logic defect/)).toBeVisible();
  await expect(page.getByText(/FAIL \/ UNSUPPORTIVE/)).toBeVisible();
  await expect(page.getByText(/2025–26 holdout contaminated/)).toBeVisible();
  await expect(page.getByText("Family A validation failed", { exact: false })).toHaveCount(0);

  await page.getByRole("navigation", { name: "Research sections" }).getByRole("link", { name: "Evidence" }).click();
  await expect(page.getByRole("heading", { name: "Evidence registry" })).toBeVisible();
  await expect(page.getByText("EDGE-EVIDENCE-C-COMPRESSION-001", { exact: true })).toBeVisible();
  await expect(page.getByText("EDGE-NEGATIVE-G-SMA200-GATE-001", { exact: true })).toBeVisible();

  await page.getByRole("navigation", { name: "Research sections" }).getByRole("link", { name: "Blocked" }).click();
  await expect(page.getByRole("heading", { name: "Data blocker" })).toBeVisible();
  await expect(page.getByText(/77.826%/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Source authorization blocker" })).toBeVisible();
  await expect(page.getByText(/authorized historical announcement source/i)).toBeVisible();

  expect(researchResponses.some((response) => new URL(response.url()).pathname === "/api/research/overview" && response.status() === 200)).toBe(true);
  expect(researchResponses.some((response) => new URL(response.url()).pathname === "/api/research/families/A" && response.status() === 200)).toBe(true);
  expect(researchResponses.some((response) => new URL(response.url()).pathname === "/api/research/evidence" && response.status() === 200)).toBe(true);
  expect(researchResponses.some((response) => new URL(response.url()).pathname === "/api/research/blocked" && response.status() === 200)).toBe(true);
});

for (const [path, heading, endpoint] of [
  ["/app/research", "Research", "/api/research/overview"],
  ["/app/research/families", "Research families", "/api/research/families"],
  ["/app/research/families/A", "Medium-Term Cross-Sectional Momentum", "/api/research/families/A"],
  ["/app/research/evidence", "Evidence registry", "/api/research/evidence"],
  ["/app/research/evidence/EDGE-EVIDENCE-C-COMPRESSION-001", "Family C compression signal evidence", "/api/research/evidence/EDGE-EVIDENCE-C-COMPRESSION-001"],
  ["/app/research/validation", "Validation", "/api/research/validation"],
  ["/app/research/blocked", "Blocked research", "/api/research/blocked"],
  ["/app/research/timeline", "Research timeline", "/api/research/timeline"],
]) {
  test(`${path} is a working backend-backed route`, async ({ page }) => {
    const responsePromise = page.waitForResponse((response) => new URL(response.url()).pathname === endpoint);
    await page.goto(path);
    const response = await responsePromise;
    expect(response.status()).toBe(200);
    expect((await response.json()).version).toBe("INTERSIGNAL_RESEARCH_WORKBENCH_V1");
    await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible();
    await expect(page.getByText("Research data couldn’t be loaded.")).toHaveCount(0);
  });
}

for (const [family, heading, marker] of [
  ["A", "Medium-Term Cross-Sectional Momentum", "FAIL / UNSUPPORTIVE"],
  ["B", "Relative Plus Absolute Momentum", "B001 was redundant"],
  ["C", "Breakout Continuation", "EDGE-EVIDENCE-C-COMPRESSION-001"],
  ["D", "Opening-Range Stocks in Play", "77.826%"],
  ["E", "Pullback Reclaim Continuation", "The control result was negative"],
  ["F", "Catalyst Momentum", "No performance claim is made"],
  ["G", "Quarterly Regime Volatility Participation", "Control CAGR 24.11%"],
]) {
  test(`Family ${family} detail is populated from the backend`, async ({ page }) => {
    await page.goto(`/app/research/families/${family}`);
    await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible();
    await expect(page.getByText(marker, { exact: false }).first()).toBeVisible();
  });
}

test("Overview uses one aggregated Research request without family-detail N+1 calls", async ({ page }) => {
  const requests = [];
  page.on("request", (request) => {
    const pathname = new URL(request.url()).pathname;
    if (pathname.startsWith("/api/research/")) requests.push(pathname);
  });
  await page.goto("/app/research");
  await expect(page.getByText("A–G complete", { exact: true })).toBeVisible();
  expect(requests).toEqual(["/api/research/overview"]);
});

test("command palette exposes Research destinations and opens populated Family C", async ({ page }) => {
  await page.goto("/app/research");
  await expect(page.getByRole("heading", { name: "Research", exact: true })).toBeVisible();
  const searches = [
    ["Research", "Go to Research"],
    ["Family A", "Family A"],
    ["Family C", "Family C"],
    ["Evidence", "Evidence"],
    ["Validation", "Validation"],
    ["Blocked Research", "Blocked Research"],
  ];
  await page.keyboard.press("Control+K");
  const input = page.getByRole("textbox", { name: "Search commands" });
  for (const [query, option] of searches) {
    await input.fill(query);
    await expect(page.getByRole("option", { name: option, exact: false }).first()).toBeVisible();
  }
  await input.fill("Family C");
  await page.getByRole("option", { name: "Family C", exact: false }).first().click();
  await expect(page).toHaveURL(/\/app\/research\/families\/C$/);
  await expect(page.getByText("EDGE-EVIDENCE-C-COMPRESSION-001", { exact: true })).toBeVisible();
});

test("Research error state retries into live backend data", async ({ page }) => {
  let failOverviewOnce = true;
  await page.route("**/api/research/overview", async (route) => {
    if (failOverviewOnce) {
      failOverviewOnce = false;
      await route.abort("failed");
      return;
    }
    await route.continue();
  });
  await page.goto("/app/research");
  await expect(page.getByRole("alert")).toContainText("Research data couldn’t be loaded.");
  await expect(page.getByText(/no demo data has been substituted/i)).toBeVisible();
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByText("A–G complete", { exact: true })).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("1366 desktop shows summary and at least five family rows without page overflow", async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto("/app/research");
  await expect(page.getByText("Production-ready", { exact: true })).toBeVisible();
  await expect(page.locator(".family-matrix thead")).toBeVisible();
  const visibleRows = page.locator(".family-matrix tbody tr");
  await expect(visibleRows).toHaveCount(7);
  for (let index = 0; index < 5; index += 1) await expect(visibleRows.nth(index)).toBeVisible();
  const dimensions = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.width + 1);
});

test("mobile uses intentional family cards and preserves bottom navigation", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/app/research");
  await expect(page.getByRole("navigation", { name: "Mobile app" })).toBeVisible();
  await expect(page.locator(".family-matrix")).toBeHidden();
  await expect(page.locator(".family-mobile-card")).toHaveCount(7);
  await expect(page.getByText("Family A · Medium-Term Cross-Sectional Momentum")).toBeVisible();
  const dimensions = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.width + 1);
});
