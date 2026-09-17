import { defineConfig } from "@playwright/test";

import { evidenceOutputDir, evidenceReportFile, sharedUse } from "./e2e/expert-validation/fixtures/config";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "expert-validation/live-sim/**/*.spec.ts",
  globalSetup: "./e2e/expert-validation/fixtures/live-sim-global-setup.ts",
  workers: 1,
  retries: 0,
  outputDir: evidenceOutputDir("live-sim"),
  reporter: [
    ["list"],
    ...(evidenceReportFile("live-sim")
      ? [["json", { outputFile: evidenceReportFile("live-sim")! }] as ["json", { outputFile: string }]]
      : []),
  ],
  use: {
    ...sharedUse,
  },
});
