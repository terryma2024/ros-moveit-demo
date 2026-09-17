import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { test, expect } from "@playwright/test";

import liveSimGlobalSetup from "../fixtures/live-sim-global-setup";
import { LiveSimGateError } from "../fixtures/live-sim";

/**
 * Proof that the live-sim Playwright config fails closed in its global
 * setup, before any test file or server exists.
 */

test("live config gates through the shared validator in global setup", () => {
  const configPath = join(
    dirname(fileURLToPath(import.meta.url)), "../../../playwright.live-sim.config.ts",
  );
  const configSource = readFileSync(configPath, "utf-8");
  expect(configSource).toContain("live-sim-global-setup");
  const setupSource = readFileSync(
    join(dirname(fileURLToPath(import.meta.url)), "../fixtures/live-sim-global-setup.ts"),
    "utf-8",
  );
  expect(setupSource).toContain("validateLiveSimPreconditions");
});

test("global setup throws LIVE_SIM_OPT_IN_REQUIRED without the opt-in", () => {
  const saved = process.env.SO101_ENABLE_LIVE_SIM_E2E;
  delete process.env.SO101_ENABLE_LIVE_SIM_E2E;
  try {
    expect(() => liveSimGlobalSetup()).toThrowError(LiveSimGateError);
    expect(() => liveSimGlobalSetup()).toThrow("LIVE_SIM_OPT_IN_REQUIRED");
  } finally {
    if (saved !== undefined) process.env.SO101_ENABLE_LIVE_SIM_E2E = saved;
  }
});
