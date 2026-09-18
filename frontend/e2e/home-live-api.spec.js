import { expect, test } from "@playwright/test";

const HOME_API_PATH = "/api/home/snapshot";

test("dummy auth enters an API-backed truthful Intelligence Home", async ({ page }) => {
  const homeRequests = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === HOME_API_PATH) homeRequests.push(request);
  });

  await page.goto("/auth?mode=signin");
  await page.getByLabel("Email address").fill("demo@example.com");
  await page.getByLabel("Password", { exact: true }).fill("prototype-only");
  const responsePromise = page.waitForResponse(
    (response) => new URL(response.url()).pathname === HOME_API_PATH,
  );
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  const response = await responsePromise;
  await response.finished();

  expect(response.status()).toBe(200);
  const payload = await response.json();
  expect(payload.version).toBe("INTERSIGNAL_HOME_SNAPSHOT_V1");
  expect(payload.market.status).toBe("UNAVAILABLE");
  expect(payload.research.family_count).toBe(7);
  expect(payload.portfolio.source_type).toBe("SYNTHETIC");
  expect(payload.governance.paper_readiness).toBe("NOT_READY");
  expect(payload.data_health.lineage_integrity).toBe("HEALTHY");
  expect(payload.attention.length).toBeGreaterThan(0);
  expect(payload.recent_activity.length).toBeGreaterThan(0);

  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByRole("heading", { name: "Overview", exact: true })).toBeVisible();
  await expect(page.getByText("Demo portfolio", { exact: true })).toBeVisible();
  await expect(page.getByText("Paused", { exact: true })).toBeVisible();
  await expect(page.getByText("Compression evidence retained", { exact: true })).toBeVisible();
  await expect(page.getByText("Family D and Family F remain limited", { exact: true })).toBeVisible();
  await expect(page.locator(".research-pulse__summary div").filter({ hasText: "Production-ready" })).toHaveText(/Production-ready\s*0/);
  await expect(page.getByText("Lineage integrity", { exact: true })).toBeVisible();
  await expect(page.getByText("Healthy", { exact: true })).toBeVisible();
  await expect(page.getByText("Limited", { exact: true })).toBeVisible();
  await expect(page.getByText("Pending", { exact: true })).toBeVisible();
  await expect(page.getByText("Available", { exact: true })).toBeVisible();
  await expect(page.getByText("Broker", { exact: true })).toBeVisible();
  await expect(page.getByText("Not connected", { exact: true })).toBeVisible();
  await expect(page.getByText("Not ready", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Sample market data", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Important today" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recent activity" })).toBeVisible();
  await expect(page.locator(".attention-item")).toHaveCount(4);
  await expect(page.locator(".recent-activity > div > p")).toHaveCount(5);
  await expect(page.getByText("Some data couldn’t be refreshed.", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Portfolio information is unavailable right now.", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Research information is unavailable right now.", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Activity is unavailable right now.", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Readiness information is unavailable.", { exact: true })).toHaveCount(0);

  await page.waitForTimeout(200);
  expect(homeRequests).toHaveLength(1);
  expect(response.request().timing().responseEnd).toBeLessThan(500);

  const pageText = (await page.locator("body").innerText()).toLowerCase();
  expect(pageText).not.toContain("live market");
  expect(pageText).not.toContain("real-time");
  expect(pageText).not.toContain("streaming");
  expect(pageText).not.toContain("your live portfolio");
  expect(pageText).not.toContain("backend");
  expect(pageText).not.toContain("synthetic");
  expect(pageText).not.toContain("source_blocked");
  expect(pageText).not.toContain("data_blocked");

  const serializedPayload = JSON.stringify(payload).toLowerCase();
  for (const forbidden of [
    "api_key",
    "access_token",
    "authorization_token",
    "broker_secret",
    "client_secret",
    "totp",
    "c:\\users\\",
    "/users/",
    ".env",
  ]) {
    expect(serializedPayload).not.toContain(forbidden);
  }
});

for (const viewport of [
  { width: 1440, height: 900 },
  { width: 1366, height: 768 },
  { width: 390, height: 844 },
]) {
  test(`${viewport.width}x${viewport.height} API-backed Home stays usable`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/app");
    await expect(page.getByRole("heading", { name: "Overview", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Market overview" })).toBeVisible();
    await expect(page.getByText("Demo portfolio", { exact: true })).toBeVisible();
    const dimensions = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      width: window.innerWidth,
    }));
    expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.width + 1);
  });
}
