import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import { createServer } from "node:net";
import { existsSync, createWriteStream, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import os from "node:os";
import { dirname, join } from "node:path";

import { resolvePackagePrefixes } from "./installed";

import { test as base, expect } from "@playwright/test";

import { proveChrome } from "./chrome";

/**
 * L3 live-simulation fail-closed gate.  Everything here runs before any
 * server or robot stack may spawn; a missing condition is a hard error with
 * a stable code, never a fallback.
 */

export type RuntimeIdentity = {
  workerId: string;
  generation: number;
  rosDomainId: number;
  mujocoSessionId: string;
  portOrSocket: string;
  pid: number;
  startTimeTicks: number;
  rosHome: string;
  logPath: string;
  gzPartition: "not_applicable";
};

export type LiveSimPreconditions = {
  evidenceRoot: string;
  sourceRoot: string;
  sourceCommit: string;
  installPrefix: string;
  /** State root of the reused deployed service; null when this fixture owns its own service. */
  serviceStateRoot: string | null;
};

export class LiveSimGateError extends Error {
  readonly code: string;

  constructor(code: string) {
    super(code);
    this.code = code;
  }
}

const STACK_PATTERNS = [
  "move_group",
  "mujoco_ros2_control_node",
  "so101_parallel_batch",
  "run_so101_adaptive_batch",
  "gz sim",
  "gz-sim",
  "rviz2",
  "so101_expert_validation_server",
  "so101_teleop_server",
];

export function stackConflicts(scan?: () => string): string[] {
  let table: string;
  try {
    table = scan ? scan() : execFileSync("ps", ["-eo", "pid,args"], { encoding: "utf-8" });
  } catch {
    return ["PROCESS_SCAN_UNAVAILABLE"];
  }
  const hits = new Set<string>();
  for (const line of table.split("\n")) {
    const trimmed = line.trim();
    const pid = Number(trimmed.split(/\s+/)[0]);
    if (!pid || pid === process.pid || pid === process.ppid) continue;
    for (const pattern of STACK_PATTERNS) {
      if (trimmed.includes(pattern)) hits.add(`${pattern}@pid${pid}`);
    }
  }
  return [...hits].sort();
}

export function validateLiveSimPreconditions(
  env: NodeJS.ProcessEnv = process.env,
  deps: { hostname?: string; stackScan?: () => string } = {},
): LiveSimPreconditions {
  if (env.SO101_ENABLE_LIVE_SIM_E2E !== "1") {
    throw new LiveSimGateError("LIVE_SIM_OPT_IN_REQUIRED");
  }
  // An opt-in flag is not an authorization: the operator's bound authorization document is
  // read before anything is spawned.
  requireUnifiedLiveAuthorization(env);
  const hostname = deps.hostname ?? os.hostname();
  const expectedHost = env.SO101_LIVE_SIM_HOST ?? "AI-STATION-001";
  if (hostname !== expectedHost) {
    throw new LiveSimGateError("LIVE_SIM_HOST_MISMATCH");
  }
  const evidenceRoot = env.SO101_E2E_EVIDENCE_ROOT ?? "";
  if (
    !evidenceRoot.startsWith("/data/work/so101-evidence/") || !existsSync(evidenceRoot)
  ) {
    throw new LiveSimGateError("LIVE_SIM_EVIDENCE_ROOT_REQUIRED");
  }
  // The retired provenance binding is gone: a source commit, an ament prefix and a binding
  // file are debug/deployment evidence, never an admission gate (the lightweight start guard
  // design removed them from runtime authority). What remains are the real functional
  // preconditions — an owned evidence root, an installed prefix and no foreign stack.
  // Optional debug info only: a source root is not a precondition. Resolving it from the
  // fixture's own location is unreliable under the transpiler, so it is taken from the
  // environment when present and otherwise reported as unknown.
  const sourceRoot = env.SO101_VALIDATION_SOURCE_ROOT ?? "";
  const installPrefix = env.SO101_E2E_INSTALL_PREFIX ?? "";
  if (!installPrefix || !existsSync(join(installPrefix, "so101_teleop"))) {
    throw new LiveSimGateError("LIVE_SIM_INSTALL_PREFIX_INVALID");
  }
  // A *reused* task-owned service is not a conflicting stack: when
  // SO101_LIVE_SERVICE_BASE_URL names the deployed service, the acceptance runs against it by
  // design and the fixture must not start or demand a second one. Without that variable the
  // original conflict check stays in force.
  let serviceStateRoot: string | null = null;
  if (env.SO101_LIVE_SERVICE_BASE_URL) {
    // The reused service keeps its own state root: the coordinator journal, cleanup gates and
    // sealed attempts the specs read live under it, not under the browser run directory. It is
    // named explicitly and must be an owned, existing directory, because a wrong root would
    // otherwise turn every journal assertion into a silent read of an empty directory.
    const root = env.SO101_LIVE_SERVICE_STATE_ROOT ?? "";
    if (!root) {
      throw new LiveSimGateError("LIVE_SIM_SERVICE_STATE_ROOT_REQUIRED");
    }
    if (!root.startsWith("/data/work/so101-evidence/") || !existsSync(root)) {
      throw new LiveSimGateError("LIVE_SIM_SERVICE_STATE_ROOT_INVALID");
    }
    serviceStateRoot = root;
  } else {
    const conflicts = stackConflicts(deps.stackScan);
    if (conflicts.length > 0) {
      throw new LiveSimGateError(`LIVE_SIM_STACK_PRESENT:${conflicts.join(",")}`);
    }
  }
  return {
    evidenceRoot,
    sourceRoot,
    sourceCommit: env.SO101_DEBUG_SOURCE_COMMIT ?? "unknown",
    installPrefix,
    serviceStateRoot,
  };
}

export type UnifiedLiveAuthorization = {
  scope: string;
  runtimeIdentities: string[];
  deadline: string;
  ownedProcessRule: string;
  resourceReferences: string[];
};

/**
 * The operator's explicit live authorization. It is a non-secret JSON document naming the
 * scope, the selected runtime identities and a deadline. It is required *in addition to*
 * the opt-in flag: no environment variable alone grants the right to stop an existing
 * service, to start a stack, or to promote a resource profile. Instance proofs must never
 * be persisted here, so a proof-shaped field is rejected outright.
 */
export function requireUnifiedLiveAuthorization(
  env: NodeJS.ProcessEnv = process.env,
): UnifiedLiveAuthorization {
  const path = env.SO101_UNIFIED_LIVE_AUTHORIZATION ?? "";
  if (!path || !existsSync(path)) {
    throw new LiveSimGateError("LIVE_SIM_UNIFIED_AUTHORIZATION_REQUIRED");
  }
  let document: Record<string, unknown>;
  try {
    document = JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>;
  } catch (error) {
    throw new LiveSimGateError(`LIVE_SIM_UNIFIED_AUTHORIZATION_UNREADABLE:${String(error)}`);
  }
  for (const key of Object.keys(document)) {
    if (/proof/i.test(key)) {
      throw new LiveSimGateError("LIVE_SIM_AUTHORIZATION_MUST_NOT_CARRY_PROOFS");
    }
  }
  const scope = typeof document.scope === "string" ? document.scope : "";
  if (!scope.includes("unified")) {
    throw new LiveSimGateError("LIVE_SIM_AUTHORIZATION_SCOPE_MISMATCH");
  }
  const deadline = typeof document.deadline === "string" ? document.deadline : "";
  const expires = Date.parse(deadline);
  if (!deadline || Number.isNaN(expires)) {
    throw new LiveSimGateError("LIVE_SIM_AUTHORIZATION_DEADLINE_REQUIRED");
  }
  if (expires <= Date.now()) {
    throw new LiveSimGateError("LIVE_SIM_AUTHORIZATION_EXPIRED");
  }
  const runtimeIdentities = Array.isArray(document.runtime_identities)
    ? document.runtime_identities.map((entry) => String(entry))
    : [];
  if (runtimeIdentities.length === 0) {
    throw new LiveSimGateError("LIVE_SIM_AUTHORIZATION_RUNTIME_IDENTITIES_REQUIRED");
  }
  return {
    scope,
    runtimeIdentities,
    deadline,
    ownedProcessRule: String(document.owned_process_rule ?? ""),
    resourceReferences: Array.isArray(document.resource_references)
      ? document.resource_references.map((entry) => String(entry))
      : [],
  };
}

export function gateReceiptPath(evidenceRoot: string, gate: string): string {
  return join(evidenceRoot, "runtime", "gates", `${gate}.passed.json`);
}

export function requireGate(evidenceRoot: string, gate: string): void {
  if (!existsSync(gateReceiptPath(evidenceRoot, gate))) {
    throw new LiveSimGateError(`${gate}_GATE_REQUIRED`);
  }
}

/** A downstream suite re-checks the producing run instead of trusting the receipt file. */
export function requireGateDetail(
  evidenceRoot: string,
  gate: string,
  expected: {
    evidenceRoot?: string;
    executionIdentitySha256?: string | null;
    profileSha256?: string | null;
    qualificationSha256?: string | null;
    manifestSha256?: string | null;
  },
): Record<string, any> {
  const path = gateReceiptPath(evidenceRoot, gate);
  if (!existsSync(path)) throw new LiveSimGateError(`${gate}_GATE_REQUIRED`);
  const receipt = JSON.parse(readFileSync(path, "utf-8"));
  const matches = (actual: unknown, wanted: unknown) =>
    wanted === undefined || wanted === null || actual === wanted;
  if (
    receipt.cleanup_complete !== true
    || (expected.evidenceRoot !== undefined && receipt.evidence_root !== expected.evidenceRoot)
    || !matches(receipt.execution_identity_sha256, expected.executionIdentitySha256)
    || !matches(receipt.profile_sha256, expected.profileSha256)
    || !matches(receipt.qualification_sha256, expected.qualificationSha256)
    || !matches(receipt.manifest_sha256, expected.manifestSha256)
  ) {
    throw new LiveSimGateError(`${gate}_GATE_STALE`);
  }
  return receipt;
}

export function recordGate(evidenceRoot: string, gate: string, detail: object): void {
  const path = gateReceiptPath(evidenceRoot, gate);
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(
    path,
    JSON.stringify({ gate, at: new Date().toISOString(), ...detail }, null, 2) + "\n",
  );
}


// Prefix resolution is shared with the installed fixtures so both gates audit the same
// overlay/underlay origins; see resolvePackagePrefixes in fixtures/installed.ts.

// Functional model/config locations only. The retired budget authority (acceptance and
// fault-injection aggregate paths, qualification environment) is deliberately absent: the
// lightweight start guard needs no profile and no qualification document to admit a start.
const MODEL_ENV: Record<string, string> = {
  SO101_VALIDATION_YOLO_WEIGHTS:
    "/data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/models/yolo/best.pt",
  SO101_VALIDATION_GROUNDED_ROOT: "/data/work/so101-models/grounded-sam-v2-scipy-lock",
  SO101_VALIDATION_BROKER_IMAGE: "so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1",
  SO101_VALIDATION_ADAPTIVE_PERFORMANCE_TIERS: "1,2,4,6,8",
};

async function freePort(): Promise<number> {
  return new Promise((resolvePromise, rejectPromise) => {
    const server = createServer();
    server.once("error", rejectPromise);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (address === null || typeof address === "string") {
        rejectPromise(new Error("PORT_ALLOCATION_FAILED"));
        return;
      }
      server.close(() => resolvePromise(address.port));
    });
  });
}

export type LiveServer = {
  port: number;
  baseURL: string;
  caseDir: string;
  stateDir: string;
  preconditions: LiveSimPreconditions;
  stop: () => Promise<void>;
};

/**
 * The L3 live fixture: production console entry, real upstream executables,
 * no test execution port.  Requires the global-setup gate to have passed.
 */
export const liveSimTest = base.extend<{ liveServer: LiveServer }>({
  baseURL: async ({ liveServer }, use) => {
    await use(liveServer.baseURL);
  },
  liveServer: async ({ }, use, testInfo) => {
    const preconditions = validateLiveSimPreconditions();
    const slug = testInfo.title.replace(/[^a-zA-Z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60);
    const caseDir = join(preconditions.evidenceRoot, "runtime", `${slug}-${Date.now().toString(36)}`);
    // A reused service already owns its state root; only a fixture-spawned service gets a fresh
    // one under this run's case directory.
    const stateDir = preconditions.serviceStateRoot ?? join(caseDir, "state");
    mkdirSync(caseDir, { recursive: true });
    if (preconditions.serviceStateRoot === null) {
      mkdirSync(stateDir, { recursive: true });
    }
    proveChrome(caseDir);

    const prefixes = resolvePackagePrefixes(
      preconditions.installPrefix,
      process.env.SO101_E2E_DEPENDENCY_PREFIX ?? "/data/work/ws_moveit/install",
    );
    const sitePackages = prefixes.map((entry) => join(entry, "lib/python3.12/site-packages"));
    const libraryPaths = prefixes.map((entry) => join(entry, "lib"));
    // One installed launcher: the unified server. The deprecated per-domain scripts only
    // delegate to it, so a live acceptance can never raise a second web listener.
    const entry = join(
      preconditions.installPrefix, "so101_teleop/lib/so101_teleop/so101_unified_web_server.py",
    );
    // A deployed service wins: the acceptance must not start a second stack while the
    // task-owned service is already running (the plan's SO101_LIVE_SERVICE_BASE_URL).
    const deployed = process.env.SO101_LIVE_SERVICE_BASE_URL;
    if (deployed) {
      await use({
        port: 0,
        baseURL: deployed,
        caseDir,
        stateDir,
        preconditions,
        stop: async () => {},
        reusedDeployedService: true,
      });
      return;
    }
    if (!existsSync(entry)) throw new Error(`INSTALLED_ENTRY_MISSING: ${entry}`);
    const python = process.env.SO101_E2E_PYTHON;
    if (!python || !existsSync(python)) throw new Error("SO101_E2E_PYTHON_REQUIRED");

    const port = await freePort();
    const logStream = createWriteStream(join(caseDir, "server.log"), { flags: "a" });
    const child: ChildProcess = spawn(python, [entry], {
      env: {
        ...process.env,
        ...MODEL_ENV,
        SO101_DISABLE_KIMI_EDITABLE_FINDER: "1",
        PYTHONNOUSERSITE: "1",
        PYTHONPATH: [...sitePackages, "/opt/ros/jazzy/lib/python3.12/site-packages"].join(":"),
        AMENT_PREFIX_PATH: [...prefixes, "/opt/ros/jazzy"].join(":"),
        LD_LIBRARY_PATH: [...libraryPaths, process.env.LD_LIBRARY_PATH ?? ""]
          .filter(Boolean)
          .join(":"),
        ROS_HOME: join(stateDir, "ros-home"),
        ROS_LOG_DIR: join(stateDir, "ros-home", "log"),
        ROS_DOMAIN_ID: process.env.SO101_LIVE_ROS_DOMAIN_ID ?? "179",
        SO101_VALIDATION_EVIDENCE_ROOT: stateDir,
        // The lightweight start guard keeps its lock and cleanup state in one task-owned
        // directory; without it the guard fails closed (PROBE_STATE_ROOT_UNSET).
        SO101_TASK_ROOT:
          process.env.SO101_TASK_ROOT ?? "/data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main/unbounded-queue-resource-budget",
        SO101_VALIDATION_PORT: String(port),
        SO101_VALIDATION_WEB_ROOT: join(
          preconditions.installPrefix, "so101_teleop/share/so101_teleop/web",
        ),
      },
      stdio: ["ignore", "pipe", "pipe"],
    });
    child.stdout?.pipe(logStream);
    child.stderr?.pipe(logStream);

    const deadline = Date.now() + 60_000;
    for (;;) {
      if (child.exitCode !== null || child.signalCode !== null) {
        throw new Error(`LIVE_SERVER_EXITED:${child.exitCode}:${child.signalCode}`);
      }
      try {
        const response = await fetch(`http://127.0.0.1:${port}/health`);
        if (response.ok) break;
      } catch {
        // not up yet
      }
      if (Date.now() > deadline) {
        child.kill("SIGKILL");
        throw new Error("LIVE_SERVER_READY_TIMEOUT");
      }
      await new Promise((resolvePromise) => setTimeout(resolvePromise, 250));
    }

    const stop = async () => {
      if (child.exitCode !== null || child.signalCode !== null) return;
      child.kill("SIGINT");
      const stopDeadline = Date.now() + 30_000;
      while (child.exitCode === null && child.signalCode === null) {
        if (Date.now() > stopDeadline) {
          child.kill("SIGKILL");
          break;
        }
        await new Promise((resolvePromise) => setTimeout(resolvePromise, 200));
      }
    };

    await use({
      port,
      baseURL: `http://127.0.0.1:${port}`,
      caseDir,
      stateDir,
      preconditions,
      stop,
    });
    await stop();
    const leftovers = stackConflicts();
    if (leftovers.length > 0) {
      throw new Error(`LIVE_STACK_LEAK: ${leftovers.join(",")}`);
    }
  },
});

export { expect };
