import { chmodSync, mkdirSync, mkdtempSync } from "node:fs";
import os from "node:os";
import { join } from "node:path";

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

/** A private directory, the way a registered task root is expected to be. */
function privateDir(prefix: string): string {
  const path = mkdtempSync(join(os.tmpdir(), prefix));
  chmodSync(path, 0o700);
  return path;
}

function privateDirUnder(parent: string, name: string): string {
  const path = join(parent, name);
  mkdirSync(path, { recursive: true, mode: 0o700 });
  chmodSync(path, 0o700);
  return path;
}

/**
 * The durable roots this platform accepts.  ai-station (Linux) has the registered
 * `/data/work/so101-evidence/` tree; macOS has no `/data` volume at all - its root is a sealed,
 * read-only system volume - so the registered root is the task's own evidence root, named by
 * `SO101_TASK_ROOT`, and the run lives in a private directory inside it.
 */
function liveRoots(): { taskRoot?: string; evidenceRoot: string; stateRoot: string } {
  if (process.platform === "darwin") {
    const taskRoot = privateDir("so101-live-gate-");
    const evidenceRoot = privateDirUnder(taskRoot, "web-live");
    return { taskRoot, evidenceRoot, stateRoot: join(evidenceRoot, "state") };
  }
  const evidenceRoot = process.env.SO101_E2E_EVIDENCE_ROOT ?? "";
  return { evidenceRoot, stateRoot: join(evidenceRoot, "state") };
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

test("darwin takes a private root inside the registered task root and refuses the rest", () => {
  // macOS has no /data/work/so101-evidence tree to point at: the sealed system volume has no /data
  // at all. The registered root is therefore the task's own evidence root ($SO101_TASK_ROOT), and
  // the run directory has to be a private directory inside it. Everything else still fails closed.
  const taskRoot = privateDir("so101-live-gate-darwin-task-");
  const evidenceRoot = privateDirUnder(taskRoot, "run");
  const deps = { platform: "darwin" as const, hostname: os.hostname() };
  const env: NodeJS.ProcessEnv = {
    ...baseEnv(),
    SO101_TASK_ROOT: taskRoot,
    SO101_E2E_EVIDENCE_ROOT: evidenceRoot,
  };
  expect(validateLiveSimPreconditions(env, deps).evidenceRoot).toBe(evidenceRoot);

  // A relative root is never a registered root.
  expect(() =>
    validateLiveSimPreconditions({ ...env, SO101_E2E_EVIDENCE_ROOT: "run" }, deps),
  ).toThrow("LIVE_SIM_EVIDENCE_ROOT_REQUIRED");

  // An absolute root outside the registered root is refused, never silently adopted.
  expect(() =>
    validateLiveSimPreconditions(
      { ...env, SO101_E2E_EVIDENCE_ROOT: privateDir("so101-live-gate-outside-") },
      deps,
    ),
  ).toThrow("LIVE_SIM_EVIDENCE_ROOT_REQUIRED");

  // Without a registered task root there is nothing to be inside of.
  const unregistered: NodeJS.ProcessEnv = { ...env };
  delete unregistered.SO101_TASK_ROOT;
  expect(() => validateLiveSimPreconditions(unregistered, deps)).toThrow(
    "LIVE_SIM_EVIDENCE_ROOT_REQUIRED",
  );

  // Inside the registered root but not private: refused, not downgraded.
  const loose = privateDirUnder(taskRoot, "loose");
  chmodSync(loose, 0o755);
  expect(() =>
    validateLiveSimPreconditions({ ...env, SO101_E2E_EVIDENCE_ROOT: loose }, deps),
  ).toThrow("LIVE_SIM_EVIDENCE_ROOT_NOT_PRIVATE");

  // The reused service's state root follows the same rule.
  expect(() =>
    validateLiveSimPreconditions(
      {
        ...env,
        SO101_LIVE_SERVICE_BASE_URL: "http://127.0.0.1:8013",
        SO101_LIVE_SERVICE_STATE_ROOT: loose,
      },
      deps,
    ),
  ).toThrow("LIVE_SIM_SERVICE_STATE_ROOT_NOT_PRIVATE");
  const stateRoot = privateDirUnder(evidenceRoot, "state");
  expect(
    validateLiveSimPreconditions(
      {
        ...env,
        SO101_LIVE_SERVICE_BASE_URL: "http://127.0.0.1:8013",
        SO101_LIVE_SERVICE_STATE_ROOT: stateRoot,
      },
      deps,
    ).serviceStateRoot,
  ).toBe(stateRoot);
});

test("linux keeps the registered /data/work/so101-evidence requirement", () => {
  // The ai-station rule is not relaxed by the macOS branch: a private root under a task root is
  // still refused there, and only the registered durable tree is accepted.
  const deps = { platform: "linux" as const, hostname: os.hostname() };
  const privateRun = privateDirUnder(privateDir("so101-live-gate-linux-task-"), "run");
  expect(() =>
    validateLiveSimPreconditions(
      {
        ...baseEnv(),
        SO101_TASK_ROOT: privateDir("so101-live-gate-linux-root-"),
        SO101_E2E_EVIDENCE_ROOT: privateRun,
      },
      deps,
    ),
  ).toThrow("LIVE_SIM_EVIDENCE_ROOT_REQUIRED");
  expect(() =>
    validateLiveSimPreconditions(
      { ...baseEnv(), SO101_E2E_EVIDENCE_ROOT: "/tmp/so101-evidence" },
      deps,
    ),
  ).toThrow("LIVE_SIM_EVIDENCE_ROOT_REQUIRED");
  // The registered tree itself is accepted; the existence check is the only thing standing between
  // this host and the ai-station path, so it is injected here rather than faked on disk.
  expect(
    validateLiveSimPreconditions(
      { ...baseEnv(), SO101_E2E_EVIDENCE_ROOT: "/data/work/so101-evidence/task/run-1" },
      { ...deps, pathExists: () => true },
    ).evidenceRoot,
  ).toBe("/data/work/so101-evidence/task/run-1");
});

test("live gate requires the deployed service state root when a service is reused", () => {
  // A reused deployed service keeps its own evidence root, and the batch journal the specs read
  // lives there rather than under the browser run directory.  Without an explicit root the
  // journal assertions would quietly read an empty directory, so the validator fails closed.
  const roots = liveRoots();
  const env = baseEnv();
  env.SO101_E2E_EVIDENCE_ROOT = roots.evidenceRoot;
  if (roots.taskRoot) env.SO101_TASK_ROOT = roots.taskRoot;
  env.SO101_LIVE_SERVICE_BASE_URL = "http://127.0.0.1:8013";
  delete env.SO101_LIVE_SERVICE_STATE_ROOT;
  expect(() => validateLiveSimPreconditions(env)).toThrow("LIVE_SIM_SERVICE_STATE_ROOT_REQUIRED");

  env.SO101_LIVE_SERVICE_STATE_ROOT = "/tmp/not-an-evidence-root";
  expect(() => validateLiveSimPreconditions(env)).toThrow("LIVE_SIM_SERVICE_STATE_ROOT_INVALID");

  env.SO101_LIVE_SERVICE_STATE_ROOT = roots.stateRoot;
  mkdirSync(roots.stateRoot, { recursive: true, mode: 0o700 });
  chmodSync(roots.stateRoot, 0o700);
  expect(validateLiveSimPreconditions(env).serviceStateRoot).toBe(roots.stateRoot);
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
  const roots = liveRoots();
  const env = baseEnv();
  env.SO101_E2E_EVIDENCE_ROOT = roots.evidenceRoot;
  if (roots.taskRoot) env.SO101_TASK_ROOT = roots.taskRoot;
  env.SO101_LIVE_SIM_HOST = os.hostname();
  delete env.SO101_LIVE_SERVICE_BASE_URL;
  const result = validateLiveSimPreconditions(env, { stackScan: () => "" });
  expect(result.evidenceRoot).toBe(roots.evidenceRoot);
  expect(result.sourceCommit).toMatch(/^[0-9a-f]{40}$/);
  expect(result.installPrefix).toBe(process.env.SO101_E2E_INSTALL_PREFIX);
  // Without a reused service the fixture owns its own state root under the run directory.
  expect(result.serviceStateRoot).toBeNull();
});

test("stack scanner ignores itself and unrelated processes", () => {
  const scan = () =>
    `${process.pid} node playwright test:e2e:live-sim\n999 sleep 3600\n`;
  expect(stackConflicts(scan)).toEqual([]);
});
