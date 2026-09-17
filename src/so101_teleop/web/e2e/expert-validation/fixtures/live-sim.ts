import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import { createServer } from "node:net";
import { existsSync, createWriteStream, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import os from "node:os";
import { dirname, join } from "node:path";

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
  const bindingPath = env.SO101_VALIDATION_PROVENANCE_BINDING ?? "";
  if (!bindingPath || !existsSync(bindingPath)) {
    throw new LiveSimGateError("LIVE_SIM_PROVENANCE_INVALID");
  }
  let binding: { source_root?: string; source_commit?: string };
  try {
    binding = JSON.parse(readFileSync(bindingPath, "utf-8"));
  } catch {
    throw new LiveSimGateError("LIVE_SIM_PROVENANCE_INVALID");
  }
  const sourceRoot = binding.source_root ?? "";
  if (!sourceRoot || !existsSync(join(sourceRoot, ".git"))) {
    throw new LiveSimGateError("LIVE_SIM_PROVENANCE_INVALID");
  }
  const head = execFileSync("git", ["-C", sourceRoot, "rev-parse", "HEAD"], {
    encoding: "utf-8",
  }).trim();
  const dirty = execFileSync(
    "git", ["-C", sourceRoot, "status", "--porcelain", "--untracked-files=no"],
    { encoding: "utf-8" },
  );
  if (binding.source_commit !== head || dirty.trim() !== "") {
    throw new LiveSimGateError("LIVE_SIM_PROVENANCE_INVALID");
  }
  const installPrefix = env.SO101_E2E_INSTALL_PREFIX ?? "";
  if (!installPrefix || !existsSync(join(installPrefix, "so101_teleop"))) {
    throw new LiveSimGateError("LIVE_SIM_INSTALL_PREFIX_INVALID");
  }
  const conflicts = stackConflicts(deps.stackScan);
  if (conflicts.length > 0) {
    throw new LiveSimGateError(`LIVE_SIM_STACK_PRESENT:${conflicts.join(",")}`);
  }
  return {
    evidenceRoot,
    sourceRoot,
    sourceCommit: binding.source_commit ?? "",
    installPrefix,
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

export function recordGate(evidenceRoot: string, gate: string, detail: object): void {
  const path = gateReceiptPath(evidenceRoot, gate);
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(
    path,
    JSON.stringify({ gate, at: new Date().toISOString(), ...detail }, null, 2) + "\n",
  );
}


const PACKAGE_PREFIXES = [
  "mujoco_3d_lidar", "mujoco_ros2_control_msgs", "mujoco_ros2_control_plugins",
  "mujoco_ros2_control", "so101_mujoco_support", "so101_demo_py", "so101_teleop",
];

const QUALIFICATION_ENV: Record<string, string> = {
  SO101_VALIDATION_YOLO_WEIGHTS:
    "/data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/models/yolo/best.pt",
  SO101_VALIDATION_GROUNDED_ROOT: "/data/work/so101-models/grounded-sam-v2-scipy-lock",
  SO101_VALIDATION_BROKER_IMAGE: "so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1",
  SO101_VALIDATION_PARALLEL_ACCEPTANCE:
    "/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-20-f91/aggregate_results.json",
  SO101_VALIDATION_ADAPTIVE_ACCEPTANCE:
    "/data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/e2001/aggregate_results.json",
  SO101_VALIDATION_ADAPTIVE_FAULT_INJECTION:
    "/data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/su09/aggregate_results.json",
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
    const stateDir = join(caseDir, "state");
    mkdirSync(stateDir, { recursive: true });
    proveChrome(caseDir);

    const prefixes = PACKAGE_PREFIXES.map((name) => join(preconditions.installPrefix, name))
      .filter((path) => existsSync(path));
    const sitePackages = prefixes.map((entry) => join(entry, "lib/python3.12/site-packages"));
    const entry = join(
      preconditions.installPrefix, "so101_teleop/lib/so101_teleop/so101_expert_validation_server.py",
    );
    if (!existsSync(entry)) throw new Error(`INSTALLED_ENTRY_MISSING: ${entry}`);
    const python = process.env.SO101_E2E_PYTHON;
    if (!python || !existsSync(python)) throw new Error("SO101_E2E_PYTHON_REQUIRED");

    const port = await freePort();
    const logStream = createWriteStream(join(caseDir, "server.log"), { flags: "a" });
    const child: ChildProcess = spawn(python, [entry], {
      env: {
        ...process.env,
        ...QUALIFICATION_ENV,
        SO101_DISABLE_KIMI_EDITABLE_FINDER: "1",
        PYTHONNOUSERSITE: "1",
        PYTHONPATH: [...sitePackages, "/opt/ros/jazzy/lib/python3.12/site-packages"].join(":"),
        AMENT_PREFIX_PATH: [...prefixes, "/opt/ros/jazzy"].join(":"),
        ROS_HOME: join(stateDir, "ros-home"),
        ROS_LOG_DIR: join(stateDir, "ros-home", "log"),
        ROS_DOMAIN_ID: process.env.SO101_LIVE_ROS_DOMAIN_ID ?? "179",
        SO101_VALIDATION_EVIDENCE_ROOT: stateDir,
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
