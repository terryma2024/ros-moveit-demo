import { defineConfig } from "@playwright/test";

import { evidenceOutputDir, evidenceReportFile, sharedUse } from "./e2e/support/config";

const baseURL = process.env.SO101_TELEOP_BASE_URL || "http://127.0.0.1:4173";

export default defineConfig({
  testDir: "./e2e",
  outputDir: evidenceOutputDir("default"),
  reporter: [
    ["list"],
    ...(evidenceReportFile("default")
      ? [["json", { outputFile: evidenceReportFile("default")! }] as ["json", { outputFile: string }]]
      : []),
  ],
  use: {
    ...sharedUse,
    baseURL,
  },
  webServer: process.env.SO101_TELEOP_BASE_URL ? undefined : {
    command: "bun run dev -- --host 127.0.0.1 --port 4173",
    url: baseURL,
    reuseExistingServer: true,
  },
});
