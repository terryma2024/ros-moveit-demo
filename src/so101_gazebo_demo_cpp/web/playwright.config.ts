import { defineConfig } from "@playwright/test";

const baseURL = process.env.SO101_TELEOP_BASE_URL || "http://127.0.0.1:4173";

export default defineConfig({
  testDir: "./e2e",
  use: {
    baseURL,
    browserName: "chromium",
    launchOptions: { executablePath: "/usr/bin/google-chrome" },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: process.env.SO101_TELEOP_BASE_URL ? undefined : {
    command: "bun run dev -- --host 127.0.0.1 --port 4173",
    url: baseURL,
    reuseExistingServer: true,
  },
});
