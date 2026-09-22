import { chmodSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import os from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

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
  return {
    ...process.env,
    SO101_ENABLE_LIVE_SIM_E2E: "1",
    // The contract declares the inputs it depends on instead of inheriting whatever the developer's
    // shell happens to hold. Each case below that wants a missing or wrong input deletes or
    // overrides exactly one of them, so the gates keep their own coverage.
    SO101_LIVE_SIM_HOST: process.env.SO101_LIVE_SIM_HOST ?? os.hostname(),
    SO101_E2E_INSTALL_PREFIX:
      process.env.SO101_E2E_INSTALL_PREFIX ?? "/opt/data/so101/workspace/install",
    // The contract declares the commit it is validating too; the live runner passes the real one.
    SO101_DEBUG_SOURCE_COMMIT:
      process.env.SO101_DEBUG_SOURCE_COMMIT ?? "0".repeat(40),
  };
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

/**
 * The contract's own entry point.
 *
 * A contract case must never depend on whatever happens to be running on the host: this repository
 * is shared with other task families, and their processes legitimately match the stack patterns. The
 * wrapper therefore injects an empty inventory unless a case asks for a specific one, and the
 * foreign-inventory refusal is covered by its own case below. The real scanner stays in production -
 * `fixtures/live-sim.ts` still reads `ps` for the live specs.
 */
function contractPreconditions(
  env: NodeJS.ProcessEnv = process.env,
  deps: {
    hostname?: string;
    stackScan?: () => string;
    platform?: NodeJS.Platform;
    pathExists?: (path: string) => boolean;
  } = {},
) {
  // The host is the host this contract runs on, and the process table is empty. Both are inputs, so
  // a case that wants a mismatch asks for one explicitly (the ai-station case below does) and an
  // explicit `env.SO101_LIVE_SIM_HOST` still wins over the declared default.
  return validateLiveSimPreconditions(
    { SO101_LIVE_SIM_HOST: os.hostname(), ...env },
    { stackScan: () => "", hostname: os.hostname(), ...deps },
  );
}

test("live gate requires the explicit opt-in", () => {
  const env = baseEnv();
  delete env.SO101_ENABLE_LIVE_SIM_E2E;
  expect(() => contractPreconditions(env)).toThrowError(LiveSimGateError);
  expect(() => contractPreconditions(env)).toThrow("LIVE_SIM_OPT_IN_REQUIRED");
  env.SO101_ENABLE_LIVE_SIM_E2E = "0";
  expect(() => contractPreconditions(env)).toThrow("LIVE_SIM_OPT_IN_REQUIRED");
});

test("live gate requires the registered ai-station host", () => {
  expect(() =>
    contractPreconditions(baseEnv(), { hostname: "some-other-host" }),
  ).toThrow("LIVE_SIM_HOST_MISMATCH");
});

test("live gate requires a durable evidence root", () => {
  const env = baseEnv();
  delete env.SO101_E2E_EVIDENCE_ROOT;
  expect(() => contractPreconditions(env)).toThrow("LIVE_SIM_EVIDENCE_ROOT_REQUIRED");
  env.SO101_E2E_EVIDENCE_ROOT = "/tmp/not-durable";
  expect(() => contractPreconditions(env)).toThrow("LIVE_SIM_EVIDENCE_ROOT_REQUIRED");
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
  expect(contractPreconditions(env, deps).evidenceRoot).toBe(evidenceRoot);

  // A relative root is never a registered root.
  expect(() =>
    contractPreconditions({ ...env, SO101_E2E_EVIDENCE_ROOT: "run" }, deps),
  ).toThrow("LIVE_SIM_EVIDENCE_ROOT_REQUIRED");

  // An absolute root outside the registered root is refused, never silently adopted.
  expect(() =>
    contractPreconditions(
      { ...env, SO101_E2E_EVIDENCE_ROOT: privateDir("so101-live-gate-outside-") },
      deps,
    ),
  ).toThrow("LIVE_SIM_EVIDENCE_ROOT_REQUIRED");

  // Without a registered task root there is nothing to be inside of.
  const unregistered: NodeJS.ProcessEnv = { ...env };
  delete unregistered.SO101_TASK_ROOT;
  expect(() => contractPreconditions(unregistered, deps)).toThrow(
    "LIVE_SIM_EVIDENCE_ROOT_REQUIRED",
  );

  // Inside the registered root but not private: refused, not downgraded.
  const loose = privateDirUnder(taskRoot, "loose");
  chmodSync(loose, 0o755);
  expect(() =>
    contractPreconditions({ ...env, SO101_E2E_EVIDENCE_ROOT: loose }, deps),
  ).toThrow("LIVE_SIM_EVIDENCE_ROOT_NOT_PRIVATE");

  // The reused service's state root follows the same rule.
  expect(() =>
    contractPreconditions(
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
    contractPreconditions(
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
    contractPreconditions(
      {
        ...baseEnv(),
        SO101_TASK_ROOT: privateDir("so101-live-gate-linux-root-"),
        SO101_E2E_EVIDENCE_ROOT: privateRun,
      },
      deps,
    ),
  ).toThrow("LIVE_SIM_EVIDENCE_ROOT_REQUIRED");
  expect(() =>
    contractPreconditions(
      { ...baseEnv(), SO101_E2E_EVIDENCE_ROOT: "/tmp/so101-evidence" },
      deps,
    ),
  ).toThrow("LIVE_SIM_EVIDENCE_ROOT_REQUIRED");
  // The registered tree itself is accepted; the existence check is the only thing standing between
  // this host and the ai-station path, so it is injected here rather than faked on disk.
  expect(
    contractPreconditions(
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
  expect(() => contractPreconditions(env)).toThrow("LIVE_SIM_SERVICE_STATE_ROOT_REQUIRED");

  env.SO101_LIVE_SERVICE_STATE_ROOT = "/tmp/not-an-evidence-root";
  expect(() => contractPreconditions(env)).toThrow("LIVE_SIM_SERVICE_STATE_ROOT_INVALID");

  env.SO101_LIVE_SERVICE_STATE_ROOT = roots.stateRoot;
  mkdirSync(roots.stateRoot, { recursive: true, mode: 0o700 });
  chmodSync(roots.stateRoot, 0o700);
  expect(contractPreconditions(env).serviceStateRoot).toBe(roots.stateRoot);
});

test("live gate requires the installed prefix", () => {
  const roots = liveRoots();
  const env = baseEnv();
  env.SO101_E2E_EVIDENCE_ROOT = roots.evidenceRoot;
  if (roots.taskRoot) env.SO101_TASK_ROOT = roots.taskRoot;
  delete env.SO101_E2E_INSTALL_PREFIX;
  expect(() => contractPreconditions(env)).toThrow("LIVE_SIM_INSTALL_PREFIX_INVALID");
});

test("live gate refuses to start over an existing stack", () => {
  const scan = () => "1234 ruby gz sim --headless\n2235 /opt/ros/jazzy/lib/moveit_ros_move_group/move_group";
  // The stack is a *foreign* inventory injected here: the production scanner is what the live specs
  // use, and this case proves the refusal without reading the host's real process table.
  const roots = liveRoots();
  const env = baseEnv();
  env.SO101_E2E_EVIDENCE_ROOT = roots.evidenceRoot;
  if (roots.taskRoot) env.SO101_TASK_ROOT = roots.taskRoot;
  expect(() => contractPreconditions(env, { stackScan: scan })).toThrow(
    /LIVE_SIM_STACK_PRESENT:/,
  );
  const codes = (() => {
    try {
      contractPreconditions(env, { stackScan: scan });
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
  // The retired operator document takes no part: the opt-in flag and the roots are the whole
  // admission contract, so the variable is not merely absent from this environment - it is
  // deleted here to prove it is not consulted.
  delete env.SO101_UNIFIED_LIVE_AUTHORIZATION;
  const result = contractPreconditions(env, { stackScan: () => "" });
  expect(result.evidenceRoot).toBe(roots.evidenceRoot);
  expect(result.sourceCommit).toMatch(/^[0-9a-f]{40}$/);
  expect(result.installPrefix).toBe(env.SO101_E2E_INSTALL_PREFIX);
  // Without a reused service the fixture owns its own state root under the run directory.
  expect(result.serviceStateRoot).toBeNull();
});

/**
 * The retired operator gate.
 *
 * `SO101_UNIFIED_LIVE_AUTHORIZATION` and `requireUnifiedLiveAuthorization` were removed in full by
 * operator instruction: the live-sim projects run against a live unified service with the opt-in
 * flag and the roots alone.  Everything else stays fail closed, and the negatives below are run on
 * the same environment that a passing document used to satisfy - so the removal cannot have
 * quietly widened the host, opt-in, durable-root, install-prefix or stack conditions.
 */
test("the retired authorization gate is gone from the fixture", () => {
  const fixture = readFileSync(
    join(dirname(fileURLToPath(import.meta.url)), "../fixtures/live-sim.ts"),
    "utf-8",
  );
  for (const retired of [
    "SO101_UNIFIED_LIVE_AUTHORIZATION",
    "UnifiedLiveAuthorization",
    "requireUnifiedLiveAuthorization",
    "LIVE_SIM_UNIFIED_AUTHORIZATION_REQUIRED",
    "LIVE_SIM_UNIFIED_AUTHORIZATION_UNREADABLE",
    "LIVE_SIM_AUTHORIZATION_MUST_NOT_CARRY_PROOFS",
    "LIVE_SIM_AUTHORIZATION_SCOPE_MISMATCH",
    "LIVE_SIM_AUTHORIZATION_DEADLINE_REQUIRED",
    "LIVE_SIM_AUTHORIZATION_EXPIRED",
    "LIVE_SIM_AUTHORIZATION_RUNTIME_IDENTITIES_REQUIRED",
  ]) {
    expect(fixture, `${retired} must not survive in the live gate`).not.toContain(retired);
  }
});

test("a plausible authorization document is ignored, never honoured", () => {
  // The shape the removed reader used to accept: in scope, unexpired, with runtime identities.
  const documentPath = join(privateDir("so101-live-auth-retired-"), "authorization.json");
  writeFileSync(
    documentPath,
    JSON.stringify({
      scope: "unified",
      deadline: "2999-01-01T00:00:00Z",
      runtime_identities: ["service01"],
      owned_process_rule: "task-owned only",
    }),
  );
  const roots = liveRoots();
  const env = baseEnv();
  env.SO101_E2E_EVIDENCE_ROOT = roots.evidenceRoot;
  if (roots.taskRoot) env.SO101_TASK_ROOT = roots.taskRoot;
  env.SO101_LIVE_SIM_HOST = os.hostname();
  delete env.SO101_LIVE_SERVICE_BASE_URL;
  env.SO101_UNIFIED_LIVE_AUTHORIZATION = documentPath;
  const result = contractPreconditions(env, { stackScan: () => "" });
  expect(result.evidenceRoot).toBe(roots.evidenceRoot);
  expect(Object.values(result)).not.toContain(documentPath);
  // ...and a bogus path is not even looked at.
  env.SO101_UNIFIED_LIVE_AUTHORIZATION = "/nonexistent/authorization.json";
  expect(contractPreconditions(env, { stackScan: () => "" }).evidenceRoot).toBe(
    roots.evidenceRoot,
  );
});

test("the remaining gates still bite without the retired document", () => {
  const roots = liveRoots();
  const env = baseEnv();
  env.SO101_E2E_EVIDENCE_ROOT = roots.evidenceRoot;
  if (roots.taskRoot) env.SO101_TASK_ROOT = roots.taskRoot;
  delete env.SO101_UNIFIED_LIVE_AUTHORIZATION;

  // 1. No opt-in -> refusal, on an otherwise complete environment.
  const withoutOptIn: NodeJS.ProcessEnv = { ...env };
  delete withoutOptIn.SO101_ENABLE_LIVE_SIM_E2E;
  expect(() => contractPreconditions(withoutOptIn)).toThrow("LIVE_SIM_OPT_IN_REQUIRED");

  // 2. Wrong host -> refusal.
  expect(() =>
    contractPreconditions(env, { hostname: "some-other-host" }),
  ).toThrow("LIVE_SIM_HOST_MISMATCH");

  // 3. A non-registered evidence root -> refusal.
  expect(() =>
    contractPreconditions({ ...env, SO101_E2E_EVIDENCE_ROOT: "run" }),
  ).toThrow("LIVE_SIM_EVIDENCE_ROOT_REQUIRED");

  // 4. A private-looking root outside the registered tree -> refusal.
  expect(() =>
    contractPreconditions(
      { ...env, SO101_E2E_EVIDENCE_ROOT: privateDir("so101-live-gate-outside-") },
      { platform: "darwin", hostname: os.hostname() },
    ),
  ).toThrow("LIVE_SIM_EVIDENCE_ROOT_REQUIRED");

  // 5. A world-readable run root inside the registered tree -> refusal.
  const taskRoot = privateDir("so101-live-gate-negatives-");
  const loose = privateDirUnder(taskRoot, "loose");
  chmodSync(loose, 0o755);
  expect(() =>
    contractPreconditions(
      { ...baseEnv(), SO101_TASK_ROOT: taskRoot, SO101_E2E_EVIDENCE_ROOT: loose },
      { platform: "darwin", hostname: os.hostname() },
    ),
  ).toThrow("LIVE_SIM_EVIDENCE_ROOT_NOT_PRIVATE");

  // 6. The install prefix is still mandatory.
  const withoutPrefix: NodeJS.ProcessEnv = { ...env };
  delete withoutPrefix.SO101_E2E_INSTALL_PREFIX;
  expect(() => contractPreconditions(withoutPrefix)).toThrow(
    "LIVE_SIM_INSTALL_PREFIX_INVALID",
  );
});

test("stack scanner ignores itself and unrelated processes", () => {
  const scan = () =>
    `${process.pid} node playwright test:e2e:live-sim\n999 sleep 3600\n`;
  expect(stackConflicts(scan)).toEqual([]);
});

test("the contract never consults the host's real process table", () => {
  const source = readFileSync(fileURLToPath(import.meta.url), "utf-8");
  // One raw call, and it is the wrapper that injects the deterministic empty inventory.
  expect(source.match(/validateLiveSimPreconditions\(/g) ?? []).toHaveLength(1);
  expect(source).toContain('stackScan: () => ""');
  // The live specs keep the real scanner: production fail-closed is not weakened by this isolation.
  const liveSpec = readFileSync(
    join(
      dirname(fileURLToPath(import.meta.url)),
      "..",
      "live-sim",
      "01-sequential.spec.ts",
    ),
    "utf-8",
  );
  expect(liveSpec).not.toContain("stackScan");
});
