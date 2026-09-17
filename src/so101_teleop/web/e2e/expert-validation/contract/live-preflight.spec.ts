import { mkdirSync, readFileSync, writeFileSync } from "node:fs";

import { test, expect } from "@playwright/test";

import {
  LiveSimGateError,
  stackConflicts,
  validateLiveSimPreconditions,
} from "../fixtures/live-sim";

/**
 * Pure fail-closed validator coverage.  Every removed condition must throw
 * its stable code; the validator never spawns anything, so a throw here
 * proves zero server/stack side effects.
 */

function baseEnv(): NodeJS.ProcessEnv {
  return { ...process.env, SO101_ENABLE_LIVE_SIM_E2E: "1" };
}

test("live gate requires the explicit opt-in", () => {
  const env = baseEnv();
  delete env.SO101_ENABLE_LIVE_SIM_E2E;
  expect(() => validateLiveSimPreconditions(env)).toThrowError(LiveSimGateError);
  expect(() => validateLiveSimPreconditions(env)).toThrow("LIVE_SIM_OPT_IN_REQUIRED");
  env.SO101_ENABLE_LIVE_SIM_E2E = "0";
  expect(() => validateLiveSimPreconditions(env)).toThrow("LIVE_SIM_OPT_IN_REQUIRED");
});

test("live gate requires the registered ai-station host", () => {
  expect(() =>
    validateLiveSimPreconditions(baseEnv(), { hostname: "some-other-host" }),
  ).toThrow("LIVE_SIM_HOST_MISMATCH");
});

test("live gate requires a durable evidence root", () => {
  const env = baseEnv();
  delete env.SO101_E2E_EVIDENCE_ROOT;
  expect(() => validateLiveSimPreconditions(env)).toThrow("LIVE_SIM_EVIDENCE_ROOT_REQUIRED");
  env.SO101_E2E_EVIDENCE_ROOT = "/tmp/not-durable";
  expect(() => validateLiveSimPreconditions(env)).toThrow("LIVE_SIM_EVIDENCE_ROOT_REQUIRED");
});

test("live gate requires a valid provenance binding", ({ }, testInfo) => {
  const env = baseEnv();
  delete env.SO101_VALIDATION_PROVENANCE_BINDING;
  expect(() => validateLiveSimPreconditions(env)).toThrow("LIVE_SIM_PROVENANCE_INVALID");

  const tampered = testInfo.outputPath("tampered-binding.json");
  mkdirSync(testInfo.outputPath(), { recursive: true });
  writeFileSync(
    tampered,
    JSON.stringify({
      schema_version: 1,
      source_root: JSON.parse(
        readFileSync(process.env.SO101_VALIDATION_PROVENANCE_BINDING!, "utf-8"),
      ).source_root,
      source_commit: "0".repeat(40),
    }),
  );
  env.SO101_VALIDATION_PROVENANCE_BINDING = tampered;
  expect(() => validateLiveSimPreconditions(env)).toThrow("LIVE_SIM_PROVENANCE_INVALID");
});

test("live gate requires the installed prefix", () => {
  const env = baseEnv();
  delete env.SO101_E2E_INSTALL_PREFIX;
  expect(() => validateLiveSimPreconditions(env)).toThrow("LIVE_SIM_INSTALL_PREFIX_INVALID");
});

test("live gate refuses to start over an existing stack", () => {
  const scan = () => "1234 ruby gz sim --headless\n2235 /opt/ros/jazzy/lib/moveit_ros_move_group/move_group";
  expect(() => validateLiveSimPreconditions(baseEnv(), { stackScan: scan })).toThrow(
    /LIVE_SIM_STACK_PRESENT:/,
  );
  const codes = (() => {
    try {
      validateLiveSimPreconditions(baseEnv(), { stackScan: scan });
    } catch (error) {
      return String(error);
    }
    return "";
  })();
  expect(codes).toContain("gz sim@pid1234");
  expect(codes).toContain("move_group@pid2235");
});

test("live gate accepts the fully qualified environment", () => {
  const result = validateLiveSimPreconditions(baseEnv(), { stackScan: () => "" });
  expect(result.evidenceRoot).toBe(process.env.SO101_E2E_EVIDENCE_ROOT);
  expect(result.sourceCommit).toMatch(/^[0-9a-f]{40}$/);
  expect(result.installPrefix).toBe(process.env.SO101_E2E_INSTALL_PREFIX);
});

test("stack scanner ignores itself and unrelated processes", () => {
  const scan = () =>
    `${process.pid} node playwright test:e2e:live-sim\n999 sleep 3600\n`;
  expect(stackConflicts(scan)).toEqual([]);
});
