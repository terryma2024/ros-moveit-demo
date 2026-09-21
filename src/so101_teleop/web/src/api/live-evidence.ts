/**
 * Verified v2 live evidence: hashes and independent physical facts, never filenames.
 *
 * The verifier is deliberately offline and pure: it reads one evidence root produced by an
 * owned live run and refuses anything it cannot re-derive. A tampered hash, a missing
 * runtime slot, a policy DONE without independent physics, an identity mismatch, or evidence
 * for a point outside the declared selection (a count is not a selection) all fail closed with
 * the stable code QUALIFICATION_EVIDENCE_INVALID.
 */
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

export class LiveEvidenceError extends Error {
  constructor(public readonly code: string, detail?: string) {
    super(detail ? `${code}: ${detail}` : code);
    this.name = "LiveEvidenceError";
  }
}

export type ExpectedLiveEvidence = {
  workerCount: number;
  pointCount: number;
  profileSha256: string;
  qualificationSha256: string;
  executionIdentitySha256: string;
  /**
   * The selected point ids. When given, the batch may carry evidence for exactly those points: a
   * document that ran the same *number* of points but a different set is not this batch.
   */
  selectedPointIds?: string[];
};

type ManifestWorker = {
  worker_id?: string;
  generation?: number;
  pid?: number;
  starttime_ticks?: number;
};

type Manifest = {
  schema_version?: number;
  worker_count?: number;
  selected_point_ids?: string[];
  profile_sha256?: string;
  qualification_sha256?: string;
  execution_identity_sha256?: string;
  workers?: ManifestWorker[];
  concurrent_window?: [number, number] | null;
};

type PointEvidence = {
  point_id?: string;
  status?: string;
  policy_state?: string;
  physics?: {
    cup_pose_world?: number[];
    support_contact?: boolean;
    gravity_verified?: boolean;
    release_epoch?: string;
    verification?: string;
  };
  moveit?: { plan_result?: string; execute_result?: string; shadow_detached?: boolean };
  artifacts?: { path?: string; sha256?: string }[];
};

function readJson(path: string): unknown {
  if (!existsSync(path)) throw new LiveEvidenceError("QUALIFICATION_EVIDENCE_INVALID", path);
  try {
    return JSON.parse(readFileSync(path, "utf-8"));
  } catch {
    throw new LiveEvidenceError("QUALIFICATION_EVIDENCE_INVALID", path);
  }
}

function sha256(path: string): string {
  if (!existsSync(path)) throw new LiveEvidenceError("QUALIFICATION_EVIDENCE_INVALID", path);
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function requireEqual(actual: unknown, expected: unknown, detail: string): void {
  if (actual !== expected) throw new LiveEvidenceError("QUALIFICATION_EVIDENCE_INVALID", detail);
}

/** The selection is a set, not a count: the same ids, once each, in either order. */
function requireSameSelection(actual: unknown, expected: string[], detail: string): void {
  if (!Array.isArray(actual)) {
    throw new LiveEvidenceError("QUALIFICATION_EVIDENCE_INVALID", detail);
  }
  const observed = [...new Set(actual.map((value) => String(value)))].sort();
  const wanted = [...new Set(expected.map(String))].sort();
  if (
    observed.length !== wanted.length
    || observed.some((value, index) => value !== wanted[index])
  ) {
    throw new LiveEvidenceError("QUALIFICATION_EVIDENCE_INVALID", detail);
  }
}

export async function verifyV2LiveEvidence(
  batchRoot: string, expected: ExpectedLiveEvidence,
): Promise<void> {
  const manifest = readJson(join(batchRoot, "manifest.json")) as Manifest;
  requireEqual(manifest.schema_version, 2, "manifest schema");
  requireEqual(manifest.worker_count, expected.workerCount, "manifest worker count");
  requireEqual(manifest.selected_point_ids?.length, expected.pointCount, "manifest point count");
  if (expected.selectedPointIds !== undefined) {
    requireSameSelection(manifest.selected_point_ids, expected.selectedPointIds, "manifest selection");
  }
  requireEqual(manifest.profile_sha256, expected.profileSha256, "manifest profile");
  requireEqual(manifest.qualification_sha256, expected.qualificationSha256, "manifest qualification");
  requireEqual(
    manifest.execution_identity_sha256, expected.executionIdentitySha256, "manifest identity");

  const workers = manifest.workers ?? [];
  requireEqual(workers.length, expected.workerCount, "runtime slots");
  const identities = new Set<string>();
  for (const worker of workers) {
    if (
      typeof worker.worker_id !== "string" || !worker.worker_id
      || !Number.isInteger(worker.pid) || !Number.isInteger(worker.starttime_ticks)
      || (worker.generation ?? 0) < 1
    ) {
      throw new LiveEvidenceError("QUALIFICATION_EVIDENCE_INVALID", "runtime slot identity");
    }
    identities.add(`${worker.pid}:${worker.starttime_ticks}`);
  }
  requireEqual(identities.size, expected.workerCount, "distinct runtime slots");
  if (manifest.concurrent_window === null || manifest.concurrent_window === undefined) {
    throw new LiveEvidenceError("QUALIFICATION_EVIDENCE_INVALID", "no concurrent window");
  }

  const receipt = readJson(join(batchRoot, "receipt.json")) as Record<string, unknown>;
  requireEqual(receipt.schema_version, 2, "receipt schema");
  requireEqual(receipt.profile_sha256, expected.profileSha256, "receipt profile");
  requireEqual(receipt.qualification_sha256, expected.qualificationSha256, "receipt qualification");
  requireEqual(receipt.cleanup_complete, true, "receipt cleanup");

  const points = readJson(join(batchRoot, "points.json")) as PointEvidence[];
  if (!Array.isArray(points)) {
    throw new LiveEvidenceError("QUALIFICATION_EVIDENCE_INVALID", "points");
  }
  requireEqual(points.length, expected.pointCount, "point evidence count");
  if (expected.selectedPointIds !== undefined) {
    requireSameSelection(
      points.map((point) => point.point_id), expected.selectedPointIds, "point evidence selection");
  }
  for (const point of points) {
    if (typeof point.point_id !== "string" || !point.point_id) {
      throw new LiveEvidenceError("QUALIFICATION_EVIDENCE_INVALID", "point id");
    }
    if (point.policy_state === "DONE" && point.status === "PASSED") {
      const physics = point.physics;
      if (
        !physics || physics.verification !== "INDEPENDENT"
        || !Array.isArray(physics.cup_pose_world) || physics.cup_pose_world.length !== 7
        || physics.support_contact !== true || physics.gravity_verified !== true
        || typeof physics.release_epoch !== "string" || !physics.release_epoch
      ) {
        throw new LiveEvidenceError(
          "QUALIFICATION_EVIDENCE_INVALID", `policy DONE without physics: ${point.point_id}`);
      }
      if (
        point.moveit?.plan_result !== "SUCCESS" || point.moveit?.execute_result !== "SUCCESS"
        || point.moveit?.shadow_detached !== true
      ) {
        throw new LiveEvidenceError(
          "QUALIFICATION_EVIDENCE_INVALID", `incomplete moveit shadow: ${point.point_id}`);
      }
    }
    for (const artifact of point.artifacts ?? []) {
      if (typeof artifact.path !== "string" || typeof artifact.sha256 !== "string") {
        throw new LiveEvidenceError("QUALIFICATION_EVIDENCE_INVALID", "artifact record");
      }
      requireEqual(sha256(join(batchRoot, artifact.path)), artifact.sha256, artifact.path);
    }
  }
}
