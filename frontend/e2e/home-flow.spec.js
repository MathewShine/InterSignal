import { expect, test } from "@playwright/test";

test("dummy sign in enters the Intelligence Home", async ({ page }) => {
  await page.goto("/auth?mode=signin");
  await page.getByLabel("Email address").fill("demo@example.com");
  await page.getByLabel("Password", { exact: true }).fill("prototype-only");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByRole("heading", { name: "Overview", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Market overview" })).toBeVisible();
  await expect(page.getByText("Sample market data")).toBeVisible();
});

test("Home shell exposes the desktop rail and prototype environment", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/app");
  await expect(page.getByRole("complementary", { name: "Application navigation" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Important today" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Research" })).toBeVisible();
});

test("command palette opens from the keyboard and supports search", async ({ page }) => {
  await page.goto("/app");
  await page.keyboard.press("Control+K");
  const dialog = page.getByRole("dialog", { name: "Command palette" });
  await expect(dialog).toBeVisible();
  await page.getByRole("textbox", { name: "Search commands" }).fill("Family D");
  await expect(page.getByRole("option", { name: /Family D.*intraday continuity/ })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();

  await page.keyboard.press("Control+K");
  await expect(dialog).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Search commands" })).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/app\/research$/);
});

test("keyboard focus materializes rail labels", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/app");
  const rail = page.locator(".app-rail");
  await expect(rail).toHaveAttribute("data-expanded", "false");
  await page.getByRole("navigation", { name: "Primary app" }).getByRole("link", { name: "Research" }).focus();
  await expect(rail).toHaveAttribute("data-expanded", "true");
});

test("market preview remains self-contained and interactive", async ({ page }) => {
  await page.goto("/app");
  await expect(page.getByText("Sample market data", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "5D", exact: true }).click();
  await expect(page.getByRole("button", { name: "5D", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: /Technology momentum softened/ })).toHaveCount(0);
});

test("backend attention focuses its source domain without a chart claim", async ({ page }) => {
  await page.goto("/app");
  await page.getByRole("button", { name: /Family D research remains blocked/ }).click();
  await expect(page.locator(".research-pulse")).toHaveClass(/is-context-focused/);
  await expect(page.locator(".market-canvas")).toHaveAttribute("data-active-context", "breadth");
});

test("context drawer opens with supporting domain context", async ({ page }) => {
  await page.goto("/app");
  await page.getByRole("button", { name: "Open contextual drawer" }).first().click();
  await expect(page.getByRole("dialog", { name: "Context drawer" })).toBeVisible();
  await expect(page.getByText("Research", { exact: true }).last()).toBeVisible();
  await expect(page.getByText("Governance", { exact: true }).last()).toBeVisible();
});

test("empty portfolio fixture stays honest and actionable", async ({ page }) => {
  await page.goto("/app?dataMode=demo&fixture=empty-portfolio");
  await expect(page.getByRole("heading", { name: "No portfolio yet" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Connect broker/ })).toBeDisabled();
  await expect(page.getByText("Coming later")).toBeVisible();
});

test("mobile uses bottom navigation and avoids horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/app");
  await expect(page.getByRole("navigation", { name: "Mobile app" })).toBeVisible();
  await expect(page.getByRole("complementary", { name: "Application navigation" })).toBeHidden();
  const dimensions = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.width + 1);
});

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

for (const viewport of viewports) {
  test(`${viewport.width}x${viewport.height} Home has no horizontal overflow`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/app");
    await expect(page.getByRole("heading", { name: "Overview", exact: true })).toBeVisible();
    const dimensions = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, width: window.innerWidth }));
    expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.width + 1);
  });
}

test("1366x768 keeps the essential intelligence relationship visible", async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto("/app");
  for (const locator of [
    page.getByRole("complementary", { name: "Application navigation" }),
    page.getByRole("heading", { name: "Overview", exact: true }),
    page.getByRole("heading", { name: "Market overview" }),
    page.getByRole("heading", { name: "Portfolio" }),
    page.getByRole("heading", { name: "Important today" }),
    page.getByRole("heading", { name: "Research" }),
    page.getByText("Demo portfolio", { exact: true }),
    page.getByRole("button", { name: /Family D research remains blocked/ }),
    page.getByRole("button", { name: /Family F research remains blocked/ }),
  ]) await expect(locator).toBeVisible();
});

for (const viewport of [
  { width: 1440, height: 900 },
  { width: 1366, height: 768 },
]) {
  test(`${viewport.width}x${viewport.height} sidebar expansion reflows the workspace`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/app");
    const rail = page.locator(".app-rail");
    const workspace = page.locator(".app-workspace");
    const collapsedRail = await rail.boundingBox();
    const collapsedWorkspace = await workspace.boundingBox();

    await rail.hover();
    await expect(rail).toHaveAttribute("data-expanded", "true");
    await page.waitForTimeout(300);

    const expandedRail = await rail.boundingBox();
    const expandedWorkspace = await workspace.boundingBox();
    expect(expandedWorkspace.x).toBeGreaterThan(collapsedWorkspace.x + 100);
    expect(expandedWorkspace.x).toBeGreaterThanOrEqual(expandedRail.x + expandedRail.width - 1);
    expect(expandedWorkspace.width).toBeLessThan(collapsedWorkspace.width);
    expect(collapsedWorkspace.x).toBeGreaterThanOrEqual(collapsedRail.x + collapsedRail.width - 1);
  });
}

test("connected Home hides implementation vocabulary", async ({ page }) => {
  await page.goto("/app");
  await expect(page.getByRole("heading", { name: "Overview", exact: true })).toBeVisible();
  const text = (await page.locator("body").innerText()).toUpperCase();
  for (const forbidden of ["BACKEND", "API CONNECTED", "LOCAL DATA", "BACKEND UNAVAILABLE"]) {
    expect(text).not.toContain(forbidden);
  }
});
