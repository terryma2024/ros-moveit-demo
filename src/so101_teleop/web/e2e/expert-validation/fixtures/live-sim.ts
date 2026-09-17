import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import os from "node:os";
import { dirname, join } from "node:path";

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
