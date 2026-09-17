import { expect, test } from "@playwright/test";

async function openAuthFromLanding(page) {
  await page.goto("/");
  await page.getByRole("link", { name: "Sign in" }).first().click();
  await expect(page).toHaveURL(/\/auth\?mode=signin$/);
}

test("landing sign in completes the dummy flow to /app", async ({ page }) => {
  await openAuthFromLanding(page);
  await page.getByLabel("Email address").fill("demo@example.com");
  await page.getByLabel("Password", { exact: true }).fill("prototype-only");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByRole("heading", { name: "Authenticated prototype entry" })).toBeVisible();
  await expect(page.getByText("AUTHENTICATION_BACKEND = NOT_IMPLEMENTED")).toBeVisible();
  expect(await page.evaluate(() => ({ local: { ...localStorage }, session: { ...sessionStorage } }))).toEqual({ local: {}, session: {} });
});

test("landing sign in reaches create account, verification, and /app", async ({ page }) => {
  await openAuthFromLanding(page);
  await page.getByRole("button", { name: /Create account/ }).click();
  await expect(page).toHaveURL(/\/auth\?mode=signup$/);

  await page.getByLabel("Full name").fill("Asha Patel");
  await page.getByLabel("Email address").fill("asha@example.com");
  await page.getByLabel("Password", { exact: true }).fill("prototype-pass");
  await page.getByLabel("Confirm password", { exact: true }).fill("prototype-pass");
  await page.getByLabel(/I agree to the Terms/).check();
  await page.getByRole("button", { name: "Create account" }).click();

  await expect(page).toHaveURL(/\/auth\?mode=verify$/);
  await expect(page.getByRole("heading", { name: "Verify your email" })).toBeVisible();
  await expect(page.getByText("asha@example.com")).toBeVisible();
  await page.getByRole("button", { name: /Continue/ }).click();
  await expect(page).toHaveURL(/\/app$/);
});

const desktopViewports = [
  { width: 1920, height: 1080 },
  { width: 1728, height: 1117 },
  { width: 1536, height: 960 },
  { width: 1440, height: 900 },
  { width: 1366, height: 768 },
  { width: 1280, height: 800 },
];

for (const viewport of desktopViewports) {
  for (const mode of ["signin", "signup"]) {
    test(`${viewport.width}x${viewport.height} ${mode} fits one viewport`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.goto(`/auth?mode=${mode}`);
      await page.evaluate(() => document.fonts.ready);

      const ctaName = mode === "signin" ? "Sign in" : "Create account";
      const headingName = mode === "signin" ? "Welcome back." : "Create your InterSignal account";
      const cta = page.getByRole("button", { name: ctaName, exact: true });
      const modeSwitch = page.locator(".auth-switch");
      await expect(page.getByRole("heading", { name: headingName })).toBeVisible();
      await expect(cta).toBeVisible();
      await expect(modeSwitch).toBeVisible();

      const metrics = await page.evaluate(() => {
        const panel = document.querySelector(".auth-panel");
        const cta = document.querySelector('.auth-form > .auth-button--primary');
        const modeSwitch = document.querySelector(".auth-switch");
        const signupHeading = document.querySelector('[data-auth-mode="signup"] .auth-mode__header h1');
        return {
          bodyScrollHeight: document.body.scrollHeight,
          ctaBottom: cta.getBoundingClientRect().bottom,
          documentScrollHeight: document.documentElement.scrollHeight,
          headingHeight: signupHeading?.getBoundingClientRect().height ?? 0,
          modeSwitchBottom: modeSwitch.getBoundingClientRect().bottom,
          panelClientHeight: panel.clientHeight,
          panelScrollHeight: panel.scrollHeight,
          scrollWidth: document.documentElement.scrollWidth,
          viewportHeight: window.innerHeight,
          viewportWidth: window.innerWidth,
        };
      });

      expect(metrics.documentScrollHeight).toBeLessThanOrEqual(metrics.viewportHeight + 2);
      expect(metrics.bodyScrollHeight).toBeLessThanOrEqual(metrics.viewportHeight + 2);
      expect(metrics.ctaBottom).toBeLessThan(metrics.viewportHeight);
      expect(metrics.modeSwitchBottom).toBeLessThan(metrics.viewportHeight);
      expect(metrics.panelScrollHeight).toBeLessThanOrEqual(metrics.panelClientHeight + 2);
      expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.viewportWidth + 1);
      if (mode === "signup" && viewport.width === 1366) expect(metrics.headingHeight).toBeLessThanOrEqual(120);
    });
  }
}

test("1366x768 signup exposes the complete form without scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto("/auth?mode=signup");
  await page.evaluate(() => document.fonts.ready);

  await expect(page.getByRole("heading", { name: "Create your InterSignal account" })).toBeVisible();
  await expect(page.getByLabel("Full name")).toBeVisible();
  await expect(page.getByLabel("Email address")).toBeVisible();
  await expect(page.getByLabel("Password", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Confirm password", { exact: true })).toBeVisible();
  await expect(page.getByLabel(/I agree to the Terms/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Create account", exact: true })).toBeVisible();
  await expect(page.getByText("Already have an account?", { exact: false })).toBeVisible();
  await expect(page.getByRole("link", { name: "Back to InterSignal home" })).toBeVisible();
  await expect(page.locator(".auth-return")).toHaveCount(0);
});

for (const mode of ["forgot", "verify"]) {
  test(`1366x768 ${mode} fits one viewport`, async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.goto(`/auth?mode=${mode}`);
    const metrics = await page.evaluate(() => ({ height: window.innerHeight, scrollHeight: document.documentElement.scrollHeight }));
    expect(metrics.scrollHeight).toBeLessThanOrEqual(metrics.height + 2);
  });
}

test("390x844 auth retains natural mobile flow without horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/auth?mode=signup");
  const dimensions = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.width + 1);
});
