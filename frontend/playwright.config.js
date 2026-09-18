import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendDirectory = path.dirname(fileURLToPath(import.meta.url));
const backendDirectory = path.resolve(frontendDirectory, "../backend");

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./test-results/run",
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  reporter: "line",
  use: {
    ...devices["Desktop Chrome"],
    baseURL: "http://127.0.0.1:4173",
    colorScheme: "light",
    reducedMotion: "no-preference",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: ".venv\\Scripts\\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765",
      cwd: backendDirectory,
      env: {
        ...process.env,
        FRONTEND_URL: "http://127.0.0.1:4173",
      },
      url: "http://127.0.0.1:8765/api/home/snapshot",
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "node ./node_modules/vite/bin/vite.js --host 127.0.0.1 --port 4173 --strictPort",
      cwd: frontendDirectory,
      env: {
        ...process.env,
        VITE_API_BASE_URL: "http://127.0.0.1:8765",
        VITE_HOME_DATA_MODE: "api",
      },
      url: "http://127.0.0.1:4173",
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
