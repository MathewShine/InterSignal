import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "market-live-visual.spec.js",
  outputDir: "./test-results/live-run",
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  reporter: "line",
  expect: { timeout: 120_000 },
  use: {
    ...devices["Desktop Chrome"],
    baseURL: "http://localhost:5173",
    colorScheme: "light",
    reducedMotion: "reduce",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
});
