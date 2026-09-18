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
  projects: [
    { name: "live-preflight", testMatch: "**/live-sim/preflight.spec.ts" },
    {
      name: "r01-sequential",
      testMatch: "**/live-sim/01-sequential.spec.ts",
      dependencies: ["live-preflight"],
    },
    {
      name: "parallel-resource",
      testMatch: /\/live-sim\/(02-parallel|04-start-guard)\.spec\.ts$/,
      dependencies: ["r01-sequential"],
    },
    {
      name: "adaptive",
      testMatch: "**/live-sim/03-adaptive.spec.ts",
      dependencies: ["r01-sequential"],
    },
  ],
});
