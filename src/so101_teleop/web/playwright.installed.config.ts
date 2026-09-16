import { defineConfig } from "@playwright/test";

import { evidenceOutputDir, evidenceReportFile, sharedUse } from "./e2e/expert-validation/fixtures/config";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "expert-validation/installed/**/*.spec.ts",
  workers: 1,
  outputDir: evidenceOutputDir("installed"),
  reporter: [
    ["list"],
    ...(evidenceReportFile("installed")
      ? [["json", { outputFile: evidenceReportFile("installed")! }] as ["json", { outputFile: string }]]
      : []),
  ],
  use: {
    ...sharedUse,
  },
});
