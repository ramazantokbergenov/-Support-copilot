import { defineConfig, devices } from "@playwright/test";

const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
const launchArgs = process.env.PLAYWRIGHT_CHROMIUM_ARGS
  ? JSON.parse(process.env.PLAYWRIGHT_CHROMIUM_ARGS) as string[]
  : undefined;

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:5173",
    trace: "retain-on-failure",
    ...(executablePath ? { launchOptions: { executablePath, args: launchArgs ?? [] } } : {}),
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});