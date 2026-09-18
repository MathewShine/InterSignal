import { expect, test } from "@playwright/test";

const dataRoutes = [
  ["/app/data", "Data", "/api/data/overview", "INTERSIGNAL_DATA_HEALTH_V1"],
  ["/app/data/sources", "Data sources", "/api/data/sources", "INTERSIGNAL_DATA_HEALTH_V1"],
  ["/app/data/lineage", "Lineage", "/api/data/lineage", "INTERSIGNAL_DATA_HEALTH_V1"],
  ["/app/data/limitations", "Data limitations", "/api/data/limitations", "INTERSIGNAL_DATA_HEALTH_V1"],
];
const governanceRoutes = [
  ["/app/governance", "Governance", "/api/governance/overview", "INTERSIGNAL_GOVERNANCE_V1"],
  ["/app/governance/readiness", "Readiness", "/api/governance/readiness", "INTERSIGNAL_GOVERNANCE_V1"],
  ["/app/governance/policies", "Policies", "/api/governance/policies", "INTERSIGNAL_GOVERNANCE_V1"],
  ["/app/governance/authorizations", "Authorizations", "/api/governance/authorizations", "INTERSIGNAL_GOVERNANCE_V1"],
  ["/app/governance/audit", "Audit", "/api/governance/audit", "INTERSIGNAL_GOVERNANCE_V1"],
];

for (const [path, heading, endpoint, version] of [...dataRoutes, ...governanceRoutes]) {
  test(`${path} is backend-backed and read-only`, async ({ page }) => {
    const responsePromise = page.waitForResponse((response) => new URL(response.url()).pathname === endpoint);
    await page.goto(path);
    const response = await responsePromise;
    expect(response.status()).toBe(200);
    expect((await response.json()).version).toBe(version);
    await expect(page.getByRole("heading", { name: heading, exact: true, level: 1 })).toBeVisible();
    await expect(page.getByText("Read-only", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: /approve|authorize|override/i })).toHaveCount(0);
  });
}

test("Data overview uses one request and shows the persisted health facts", async ({ page }) => {
  const requests = [];
  page.on("request", (request) => { const path = new URL(request.url()).pathname; if (path.startsWith("/api/data/")) requests.push(path); });
  await page.goto("/app/data");
  await expect(page.getByText("77.826%", { exact: true })).toBeVisible();
  await expect(page.getByText("217", { exact: true })).toBeVisible();
  await expect(page.getByText("Healthy", { exact: true })).toBeVisible();
  await expect(page.getByText("0", { exact: true })).toBeVisible();
  await expect(page.getByText("Source blocked", { exact: true })).toBeVisible();
  expect(requests).toEqual(["/api/data/overview"]);
});

test("Data detail pages preserve the recorded research semantics", async ({ page }) => {
  await page.goto("/app/data/sources");
  await expect(page.getByText("Intraday data quality is insufficient for trustworthy formal evaluation.", { exact: true })).toBeVisible();
  await expect(page.getByText("Historical catalyst source is not yet authorized for full research use.", { exact: true })).toBeVisible();
  await expect(page.getByText("Available with caveats", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("77.826%", { exact: true })).toBeVisible();
  await expect(page.getByText("217", { exact: true })).toBeVisible();

  await page.goto("/app/data/lineage");
  await expect(page.getByText("Healthy", { exact: true })).toBeVisible();
  for (const value of ["33", "11", "22", "0"]) await expect(page.getByText(value, { exact: true }).first()).toBeVisible();

  await page.goto("/app/data/limitations");
  await expect(page.getByText("Family D research", { exact: true })).toBeVisible();
  await expect(page.getByText("Family F research", { exact: true })).toBeVisible();
  await expect(page.getByText("Adjusted-history consumers", { exact: true })).toBeVisible();
});

test("Governance overview keeps policy compliance separate from readiness", async ({ page }) => {
  const requests = [];
  page.on("request", (request) => { const path = new URL(request.url()).pathname; if (path.startsWith("/api/governance/")) requests.push(path); });
  await page.goto("/app/governance");
  await expect(page.getByText("8/8 policy evaluations pass.", { exact: true })).toBeVisible();
  await expect(page.getByText(/do not imply trading readiness/i)).toBeVisible();
  await expect(page.getByText("Not connected", { exact: true })).toBeVisible();
  await expect(page.getByText("Not ready", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("1", { exact: true })).toBeVisible();
  await expect(page.getByText("0", { exact: true })).toBeVisible();
  expect(requests).toEqual(["/api/governance/overview"]);
});

test("Home deep-links into truthful Data and Governance detail", async ({ page }) => {
  await page.goto("/app");
  await expect(page.getByText("Healthy", { exact: true })).toBeVisible();
  await expect(page.getByText("Production", { exact: true })).toBeVisible();
  await expect(page.getByText("Pending authorization", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Review limitations →" }).click();
  await expect(page).toHaveURL(/\/app\/data\/limitations$/);
  await expect(page.getByText(/77\.826177% exact prior-20 continuity/)).toBeVisible();
  await page.goto("/app");
  await page.getByRole("link", { name: "View data health →" }).click();
  await expect(page).toHaveURL(/\/app\/data$/);
  await page.goto("/app");
  await page.getByRole("link", { name: "View governance →" }).click();
  await expect(page).toHaveURL(/\/app\/governance$/);
  await expect(page.getByText("Not ready", { exact: true }).first()).toBeVisible();
});

test("section command palettes open every populated Data and Governance destination", async ({ page }) => {
  const destinations = [
    ["/app/data", "Data sources", "/app/data/sources"],
    ["/app/data", "Lineage", "/app/data/lineage"],
    ["/app/data", "Data limitations", "/app/data/limitations"],
    ["/app/governance", "Readiness", "/app/governance/readiness"],
    ["/app/governance", "Policies", "/app/governance/policies"],
    ["/app/governance", "Authorizations", "/app/governance/authorizations"],
    ["/app/governance", "Audit", "/app/governance/audit"],
  ];
  for (const [start, label, destination] of destinations) {
    await page.goto(start);
    await page.getByRole("button", { name: "Open command palette" }).click();
    const input = page.getByRole("textbox", { name: "Search commands" });
    await input.fill(label);
    await page.getByRole("option").filter({ hasText: label }).first().click();
    await expect(page).toHaveURL(new RegExp(`${destination}$`));
  }
});

for (const [area, path, endpoint, text] of [
  ["Data", "/app/data", "**/api/data/overview", "Data health couldn’t be loaded."],
  ["Governance", "/app/governance", "**/api/governance/overview", "Governance data couldn’t be loaded."],
]) {
  test(`${area} error retries into live data without fixtures`, async ({ page }) => {
    let failOnce = true;
    await page.route(endpoint, async (route) => { if (failOnce) { failOnce = false; await route.abort("failed"); } else await route.continue(); });
    await page.goto(path);
    await expect(page.getByRole("alert")).toContainText(text);
    await expect(page.getByText("No demo records have been substituted.")).toBeVisible();
    const navigation = page.getByRole("navigation", { name: `${area} sections` });
    const links = navigation.getByRole("link");
    const boxes = await links.evaluateAll((elements) => elements.map((element) => element.getBoundingClientRect()).map(({ left, right }) => ({ left, right })));
    for (let index = 1; index < boxes.length; index += 1) expect(boxes[index].left - boxes[index - 1].right).toBeGreaterThanOrEqual(12);
    const typography = await page.getByRole("alert").evaluate((panel) => {
      const title = getComputedStyle(panel.querySelector("h1"));
      const body = getComputedStyle(panel.querySelector("p"));
      const eyebrow = getComputedStyle(panel.querySelector(".technical-label"));
      const box = panel.getBoundingClientRect();
      return { body: parseFloat(body.fontSize), eyebrow: parseFloat(eyebrow.fontSize), height: box.height, textAlign: getComputedStyle(panel).textAlign, title: parseFloat(title.fontSize), top: box.top };
    });
    expect(typography.eyebrow).toBeGreaterThanOrEqual(12);
    expect(typography.eyebrow).toBeLessThanOrEqual(13);
    expect(typography.title).toBeGreaterThanOrEqual(24);
    expect(typography.title).toBeLessThanOrEqual(32);
    expect(typography.body).toBeGreaterThanOrEqual(14);
    expect(typography.body).toBeLessThanOrEqual(16);
    expect(typography.top).toBeLessThan(300);
    expect(typography.height).toBeLessThan(300);
    expect(typography.textAlign).toBe("left");
    await page.getByRole("button", { name: "Retry" }).click();
    await expect(page.getByRole("heading", { name: area, exact: true, level: 1 })).toBeVisible();
  });
}

test("Data overview keeps healthy subsections when lineage is unavailable", async ({ page }) => {
  await page.route("**/api/data/overview", async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    payload.status = "PARTIAL";
    payload.reason = "DATA_SECTIONS_UNAVAILABLE";
    payload.meta.unavailable_sections = ["lineage"];
    payload.lineage = null;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) });
  });
  await page.goto("/app/data");
  await expect(page.getByRole("status")).toContainText("lineage");
  await expect(page.getByText("Lineage unavailable", { exact: true })).toBeVisible();
  await expect(page.getByText("Intraday research", { exact: true })).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("Governance overview keeps readiness and policy state when audit is unavailable", async ({ page }) => {
  await page.route("**/api/governance/overview", async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    payload.status = "PARTIAL";
    payload.reason = "GOVERNANCE_SECTIONS_UNAVAILABLE";
    payload.meta.unavailable_sections = ["audit"];
    payload.recent_audit = [];
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) });
  });
  await page.goto("/app/governance");
  await expect(page.getByRole("status")).toContainText("audit");
  await expect(page.getByText("8/8 policy evaluations pass.", { exact: true })).toBeVisible();
  await expect(page.getByText("No audit events", { exact: true })).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
});

for (const viewport of [{ width: 1440, height: 900 }, { width: 1366, height: 768 }]) {
  for (const [area, path] of [["Data", "/app/data"], ["Governance", "/app/governance"]]) {
    test(`${area} sidebar reflows content at ${viewport.width}x${viewport.height}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.goto(path);
      const workspace = page.locator(".app-workspace");
      await expect(page.getByRole("heading", { name: area, exact: true, level: 1 })).toBeVisible();
      await expect(workspace).toBeVisible();
      const before = await workspace.boundingBox();
      await page.locator(".app-rail").hover();
      await expect(page.locator(".authenticated-shell")).toHaveAttribute("data-rail-expanded", "true");
      await expect.poll(async () => (await workspace.boundingBox())?.x).toBeGreaterThan(before.x + 100);
      await expect.poll(async () => (await workspace.boundingBox())?.width).toBeLessThan(before.width - 100);
    });
  }
}

test("Data and Governance navigation remains GET-only", async ({ page }) => {
  const observed = [];
  page.on("request", (request) => {
    const pathname = new URL(request.url()).pathname;
    if (pathname.startsWith("/api/data/") || pathname.startsWith("/api/governance/")) observed.push([pathname, request.method()]);
  });
  for (const [path] of [...dataRoutes, ...governanceRoutes]) {
    await page.goto(path);
    await expect(page.getByText("Read-only", { exact: true })).toBeVisible();
  }
  expect(observed.length).toBe(9);
  expect(observed.every(([, method]) => method === "GET")).toBe(true);
});

test("Data and Governance preserve keyboard, semantic-table, and reduced-motion accessibility", async ({ page }) => {
  await page.goto("/app/data/lineage");
  await expect(page.getByRole("table", { name: "Recent lineage records" })).toBeVisible();
  const firstSectionLink = page.getByRole("navigation", { name: "Data sections" }).getByRole("link").first();
  await firstSectionLink.focus();
  await expect(firstSectionLink).toBeFocused();
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.route("**/api/governance/overview", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 300));
    await route.continue();
  });
  await page.goto("/app/governance");
  const loading = page.getByRole("status", { name: "Loading Governance" });
  await expect(loading).toBeVisible();
  await expect(loading.locator(".ops-skeleton").first()).toHaveCSS("animation-name", "none");
  await expect(page.getByRole("heading", { name: "Governance", exact: true, level: 1 })).toBeVisible();
});

for (const viewport of [{ width: 1920, height: 1080 }, { width: 1536, height: 960 }, { width: 1440, height: 900 }, { width: 1366, height: 768 }, { width: 1024, height: 768 }, { width: 768, height: 1024 }, { width: 390, height: 844 }]) {
  for (const [area, path] of [["Data", "/app/data"], ["Governance", "/app/governance"]]) {
    test(`${area} ${viewport.width}x${viewport.height} has no page overflow`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.goto(path);
      await expect(page.getByRole("heading", { name: area, exact: true, level: 1 })).toBeVisible();
      const dimensions = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, width: window.innerWidth }));
      expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.width + 1);
      if (viewport.width === 390) await expect(page.getByRole("navigation", { name: "Mobile app" })).toBeVisible();
    });
  }
}
