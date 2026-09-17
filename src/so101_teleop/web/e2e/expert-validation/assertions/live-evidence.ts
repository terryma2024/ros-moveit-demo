/**
 * L3 live evidence assertions.  Every phase claim must be backed by sealed
 * attempt evidence read from disk; unreached phases are recorded as
 * NOT_REACHED, never presented as success.
 */

import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

export type LivePhase =
  | "perception"
  | "plan"
  | "execute"
  | "grasp"
  | "lift"
  | "transport"
  | "release";

export type PhaseEvidence = {
  pointId: string;
  phase: LivePhase | "NOT_REACHED";
  evidencePath: string | null;
};

const PHASE_FILES: Record<LivePhase, string[]> = {
  perception: ["perception/input/rgb.npy", "initial-rgb.png"],
  plan: ["dynamic/reachability-observed.json", "numeric/tf.json"],
  execute: ["dynamic/dynamic-execute-manifest.json"],
  grasp: ["numeric/physical.json"],
  lift: ["numeric/physical.json"],
  transport: ["numeric/physical.json"],
  release: ["attempt-result.json"],
};

export function readSealedAttempt(sealedDir: string): {
  manifest: Record<string, any>;
  files: Set<string>;
} {
  const manifestPath = join(sealedDir, "attempt_result_manifest.json");
  if (!existsSync(manifestPath)) {
    throw new Error(`SEALED_MANIFEST_MISSING: ${sealedDir}`);
  }
  const manifest = JSON.parse(readFileSync(manifestPath, "utf-8"));
  const files = new Set<string>(
    (manifest.files as Array<{ relative_path: string }>).map((f) => f.relative_path),
  );
  return { manifest, files };
}

export function assertReachedPhaseEvidence(
  pointId: string,
  sealedDir: string,
  phase: LivePhase,
): PhaseEvidence {
  const { files } = readSealedAttempt(sealedDir);
  const candidates = PHASE_FILES[phase];
  const found = candidates.find((relative) => files.has(relative));
  if (!found) {
    throw new Error(`PHASE_EVIDENCE_MISSING: ${pointId} ${phase} in ${sealedDir}`);
  }
  return { pointId, phase, evidencePath: join(sealedDir, found) };
}

export function notReached(pointId: string): PhaseEvidence {
  return { pointId, phase: "NOT_REACHED", evidencePath: null };
}

export function assertNoMotionSideEffects(sealedDir: string): void {
  // A point whose controller goal was never submitted must not contain
  // execution-phase artifacts.
  const { files } = readSealedAttempt(sealedDir);
  const executionArtifacts = [...files].filter((relative) =>
    relative.startsWith("dynamic/") || relative === "numeric/physical.json"
  );
  if (executionArtifacts.length > 0) {
    throw new Error(`UNEXPECTED_MOTION_EVIDENCE: ${executionArtifacts.join(",")}`);
  }
}
