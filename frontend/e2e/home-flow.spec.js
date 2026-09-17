import { expect, test } from "@playwright/test";

test("dummy sign in enters the Intelligence Home", async ({ page }) => {
  await page.goto("/auth?mode=signin");
  await page.getByLabel("Email address").fill("demo@example.com");
  await page.getByLabel("Password", { exact: true }).fill("prototype-only");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByRole("heading", { name: "Here’s what matters." })).toBeVisible();
  await expect(page.getByRole("heading", { name: "NIFTY 500" })).toBeVisible();
});

test("Home shell exposes the desktop rail and prototype environment", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/app");
  await expect(page.getByRole("complementary", { name: "Application navigation" })).toBeVisible();
  await expect(page.getByText("DEMO / LOCAL DATA")).toBeVisible();
  await expect(page.getByRole("heading", { name: "What deserves attention" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Research pulse" })).toBeVisible();
});

test("command palette opens from the keyboard and supports search", async ({ page }) => {
  await page.goto("/app");
  await page.keyboard.press("Control+K");
  const dialog = page.getByRole("dialog", { name: "Command palette" });
  await expect(dialog).toBeVisible();
  await page.getByRole("textbox", { name: "Search commands" }).fill("Family D");
  await expect(page.getByRole("option", { name: /Family D continuity blocker/ })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();

  await page.keyboard.press("Control+K");
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

test("attention selection updates market and portfolio context", async ({ page }) => {
  await page.goto("/app");
  await page.getByRole("button", { name: /Technology momentum softened/ }).click();
  await expect(page.locator(".market-canvas")).toHaveAttribute("data-active-context", "sector");
  await expect(page.locator('[title="Technology 9%"]')).toHaveClass(/is-active/);
});

test("context drawer opens with supporting domain context", async ({ page }) => {
  await page.goto("/app");
  await page.getByRole("button", { name: "Open contextual drawer" }).first().click();
  await expect(page.getByRole("dialog", { name: "Context drawer" })).toBeVisible();
  await expect(page.getByText("Research", { exact: true }).last()).toBeVisible();
  await expect(page.getByText("Governance", { exact: true }).last()).toBeVisible();
});

test("empty portfolio fixture stays honest and actionable", async ({ page }) => {
  await page.goto("/app?fixture=empty-portfolio");
  await expect(page.getByRole("heading", { name: "No portfolio connected yet." })).toBeVisible();
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
    await expect(page.getByRole("heading", { name: "Here’s what matters." })).toBeVisible();
    const dimensions = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, width: window.innerWidth }));
    expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.width + 1);
  });
}

test("1366x768 keeps the essential intelligence relationship visible", async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto("/app");
  for (const locator of [
    page.getByRole("complementary", { name: "Application navigation" }),
    page.getByRole("heading", { name: "Here’s what matters." }),
    page.getByRole("heading", { name: "NIFTY 500" }),
    page.getByRole("heading", { name: "What deserves attention" }),
    page.getByText("Illustrative portfolio", { exact: true }),
  ]) await expect(locator).toBeVisible();
});
