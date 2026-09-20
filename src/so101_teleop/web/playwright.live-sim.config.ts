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
      name: "functional-cases",
      testMatch: "**/live-sim/05-functional-manifest.spec.ts",
      dependencies: ["live-preflight"],
    },
    {
      name: "adaptive",
      testMatch: "**/live-sim/03-adaptive.spec.ts",
      dependencies: ["r01-sequential"],
    },
    {
      // One real campaign per supported configured option; declared last because it is the long
      // project, and gated only on preflight so it can also be run on its own.
      name: "fixed-n-execution",
      testMatch: "**/live-sim/06-fixed-n-execution.spec.ts",
      dependencies: ["live-preflight"],
    },
    {
      // The manual single-point failure retry: needs a service started with the fault-injection
      // points catalog, so it stays its own project rather than running with the sweep.
      name: "retry-full-restart",
      testMatch: "**/live-sim/07-retry-full-restart.spec.ts",
      dependencies: ["live-preflight"],
    },
    {
      // The five consecutive valid physical batches: long by construction (five twenty-point
      // campaigns), so it is a project of its own and never part of a mixed run.
      name: "five-consecutive",
      testMatch: "**/live-sim/08-five-consecutive.spec.ts",
      dependencies: ["live-preflight"],
    },
    {
      // The unified single-service acceptance: one owned launcher, one web port, both domain
      // surfaces on the same origin. It consumes the R01 producer instead of producing another
      // one, so it can never be the first acceptance of a fresh runtime.
      name: "unified",
      testMatch: "**/unified/live-sim.spec.ts",
      dependencies: ["r01-sequential"],
    },
  ],
});
