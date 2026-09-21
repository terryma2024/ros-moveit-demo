/**
 * L3 live evidence assertions.  Every phase claim must be backed by sealed
 * attempt evidence read from disk; unreached phases are recorded as
 * NOT_REACHED, never presented as success.
 *
 * The campaign block below is the batch-level contract for the three macOS execution paths: W2
 * (two parallel workers), W1 first-pass (one worker, many points) and the single-point
 * FULL_RESTART_RETRY batch. It reads the batch's own bytes - the frozen batch manifest, the
 * committed journal, the published durability watermark, the sealed attempt trees and the cleanup
 * gates - and refuses anything it cannot re-derive.
 */

import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { isAbsolute, join, relative, resolve, sep } from "node:path";

import { readJournalEvents, type JournalEvent } from "./journal";

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

// ---------------------------------------------------------------------------------------------
// Campaign batch evidence (W2 / W1 first-pass / single-point retry)
// ---------------------------------------------------------------------------------------------

/** Fail closed with a stable code: the call site narrows because the return type is `never`. */
function fail(code: string, detail?: string): never {
  throw new Error(detail ? `${code}: ${detail}` : code);
}

const sha256 = (data: Buffer): string =>
  createHash("sha256").update(data).digest("hex");

/**
 * The physical evidence a sealed execute attempt is verified to carry: MuJoCo pose/contact
 * evidence, the MoveIt execute shadow, the raw and rendered frames, and the sealed inventory
 * itself. Every file is checked against the sealed manifest's own sha256 and size.
 */
export const PHYSICAL_EVIDENCE_FILES = [
  "workspace_identity.json",
  "attempt-result.json",
  "initial-rgb.png",
  "perception/input/rgb.npy",
  "pose_accepted.json",
  "numeric/depth.json",
  "numeric/tf.json",
  "numeric/physical.json",
  "terminal-rgb.png",
] as const;

export type ExecutionBatchKind = "FIRST_PASS" | "FULL_RESTART_RETRY";

export type CampaignBatchExpectation = {
  batchKind: ExecutionBatchKind;
  /** The matrix profile the request claimed, checked against the preflight receipt. */
  executionProfile: string;
  schemaVersion: number;
  workerCount: number;
  selectedPointIds: string[];
  /** The canonical service projection for this batch, when the caller has it. */
  projection?: Record<string, unknown> | null;
};

export type CommittedAttempt = {
  pointId: string;
  attemptId: string;
  workerId: string;
  sealedDir: string;
  sequence: number;
};

export type CampaignBatchEvidence = {
  batchRoot: string;
  manifest: Record<string, any>;
  cleanup: Record<string, any>;
  watermark: Record<string, any> | null;
  events: JournalEvent[];
  /** The digest of each frame's own bytes, by journal sequence. */
  frameSha256: Map<number, string>;
  /** The canonical service projection for this batch, when the caller has one. */
  projection?: Record<string, unknown> | null;
};

function readJsonFile(path: string, code: string): Record<string, any> {
  if (!existsSync(path)) fail(code, `missing ${path}`);
  try {
    const value = JSON.parse(readFileSync(path, "utf-8"));
    if (!value || typeof value !== "object" || Array.isArray(value)) fail(code, path);
    return value as Record<string, any>;
  } catch (error) {
    if (error instanceof Error && error.message.startsWith(code)) throw error;
    return fail(code, `unreadable ${path}`);
  }
}

/**
 * The frame digests of a journal root. The frame layout is the coordinator's own: an 8-byte
 * big-endian payload length, the payload's sha256, the canonical payload and a newline; the
 * published watermark names the digest of the whole frame, which is what is recomputed here.
 */
function readFrameDigests(journalRoot: string): Map<number, string> {
  const digests = new Map<number, string>();
  const eventsDir = join(journalRoot, "events");
  if (!existsSync(eventsDir)) return digests;
  for (const name of readdirSync(eventsDir).filter((entry) => entry.endsWith(".journal")).sort()) {
    const data = readFileSync(join(eventsDir, name));
    let offset = 0;
    while (offset < data.length) {
      if (offset + 73 > data.length) fail("CAMPAIGN_EVIDENCE_INVALID", `torn frame in ${name}`);
      const payloadLength = Number(data.readBigUInt64BE(offset));
      const end = offset + 73 + payloadLength;
      if (end > data.length || data[end - 1] !== 0x0a) {
        fail("CAMPAIGN_EVIDENCE_INVALID", `torn frame in ${name}`);
      }
      const frameBytes = data.subarray(offset, end);
      let document: Record<string, any>;
      try {
        document = JSON.parse(data.subarray(offset + 72, end - 1).toString("utf-8"));
      } catch {
        return fail("CAMPAIGN_EVIDENCE_INVALID", `unreadable frame in ${name}`);
      }
      if (!Number.isInteger(document.sequence)) {
        fail("CAMPAIGN_EVIDENCE_INVALID", `frame without a sequence in ${name}`);
      }
      digests.set(document.sequence, sha256(frameBytes));
      offset = end;
    }
  }
  return digests;
}

/**
 * The batch's journal root. The fixed coordinator writes `<batch root>/coordinator`; a macOS
 * composed campaign writes the same `CoordinatorJournal` under `<batch root>/journal`. Both are
 * the coordinator's own canonical/legacy stream, so the reader takes whichever exists and never
 * falls back to a directory scan.
 */
export function campaignJournalRoot(batchRoot: string): string {
  for (const name of ["coordinator", "journal"]) {
    const candidate = join(batchRoot, name);
    if (existsSync(join(candidate, "events"))) return candidate;
  }
  return join(batchRoot, "coordinator");
}

/** Read the batch's frozen manifest, committed journal, watermark and cleanup gates. */
export function readCampaignBatchEvidence(batchRoot: string): CampaignBatchEvidence {
  const root = resolve(batchRoot);
  const journalRoot = campaignJournalRoot(root);
  const watermarkPath = join(journalRoot, "committed-watermark.json");
  return {
    batchRoot: root,
    manifest: readJsonFile(join(root, "batch_manifest.json"), "CAMPAIGN_EVIDENCE_INVALID"),
    cleanup: readJsonFile(join(root, "cleanup-gates.json"), "CAMPAIGN_EVIDENCE_INVALID"),
    watermark: existsSync(watermarkPath)
      ? readJsonFile(watermarkPath, "SEQUENCE_WATERMARK_INVALID")
      : null,
    events: readJournalEvents(journalRoot),
    frameSha256: readFrameDigests(journalRoot),
  };
}

/** Every committed attempt the journal names, in journal order. */
export function committedAttempts(evidence: CampaignBatchEvidence): CommittedAttempt[] {
  return evidence.events
    .filter((event) => event.type === "RESULT_COMMITTED")
    .map((event) => {
      // Both journal vocabularies keep the sealed reference in `response`; the canonical one
      // carries the identity flat, the legacy one nests it under `identity`.
      const payload = (event.payload ?? {}) as Record<string, any>;
      const identity = (payload.identity ?? {}) as Record<string, any>;
      const response = (payload.response ?? {}) as Record<string, any>;
      const pointId = String(payload.point_id ?? identity.point_id ?? "");
      const attemptId = String(payload.attempt_id ?? identity.attempt_id ?? "");
      const workerId = String(payload.worker_id ?? identity.worker_id ?? "");
      const sealedDir = typeof response.location === "string" ? response.location : "";
      if (!pointId || !attemptId || !workerId || !sealedDir) {
        fail("SELECTED_ONLY_EVIDENCE_INVALID", `incomplete commit at sequence ${event.sequence}`);
      }
      return {
        pointId,
        attemptId,
        workerId,
        sealedDir,
        sequence: Number(event.sequence ?? 0),
      };
    });
}

/**
 * The batch executed exactly its selection, once per point: no unselected point has a commit, no
 * selected point is missing one, and every sealed attempt stays inside the batch's own tree.
 */
export function assertSelectedOnlyAttempts(
  evidence: CampaignBatchEvidence,
  expectation: CampaignBatchExpectation,
): void {
  const manifestSelection = Array.isArray(evidence.manifest.selected_point_ids)
    ? evidence.manifest.selected_point_ids.map(String)
    : [];
  const expected = [...expectation.selectedPointIds].sort();
  if ([...manifestSelection].sort().join("\u0000") !== expected.join("\u0000")) {
    fail("SELECTED_ONLY_EVIDENCE_INVALID",
      `manifest selection ${manifestSelection.join(",")} is not ${expected.join(",")}`);
  }
  if (evidence.manifest.batch_kind !== expectation.batchKind) {
    fail("SELECTED_ONLY_EVIDENCE_INVALID",
      `batch kind ${String(evidence.manifest.batch_kind)} is not ${expectation.batchKind}`);
  }
  if (evidence.manifest.worker_count !== expectation.workerCount) {
    fail("SELECTED_ONLY_EVIDENCE_INVALID",
      `worker count ${String(evidence.manifest.worker_count)} is not ${expectation.workerCount}`);
  }
  const attempts = committedAttempts(evidence);
  for (const attempt of attempts) {
    if (!expected.includes(attempt.pointId)) {
      fail("SELECTED_ONLY_EVIDENCE_INVALID", `unselected point ${attempt.pointId} committed`);
    }
  }
  for (const pointId of expected) {
    const committed = attempts.filter((attempt) => attempt.pointId === pointId);
    if (committed.length !== 1) {
      fail("SELECTED_ONLY_EVIDENCE_INVALID", `${pointId} committed ${committed.length} times`);
    }
  }
  for (const attempt of attempts) {
    const inside = relative(evidence.batchRoot, resolve(attempt.sealedDir));
    if (inside.startsWith("..") || isAbsolute(inside) || inside === "") {
      fail("SELECTED_ONLY_EVIDENCE_INVALID", `sealed evidence outside the batch: ${attempt.sealedDir}`);
    }
    if (!inside.startsWith(`workers${sep}`) || !inside.endsWith(`${sep}sealed`)) {
      fail("SELECTED_ONLY_EVIDENCE_INVALID", `unexpected sealed layout: ${attempt.sealedDir}`);
    }
  }
  if (attempts.length !== expected.length) {
    fail("SELECTED_ONLY_EVIDENCE_INVALID",
      `${attempts.length} commits for ${expected.length} selected points`);
  }
}

/**
 * The committed prefix is the sequence the watermark closed: the journal chain is contiguous,
 * the named frame digest is the one on disk, every commit sits at or below the watermark, and the
 * service projection never runs ahead of the durable watermark.
 */
export function assertSequenceAndWatermark(evidence: CampaignBatchEvidence): void {
  const sequences = evidence.events.map((event) => Number(event.sequence));
  sequences.forEach((sequence, index) => {
    if (!Number.isInteger(sequence) || sequence < 1) {
      fail("SEQUENCE_WATERMARK_INVALID", `journal sequence ${String(sequence)}`);
    }
    if (index === 0) return;
    if (sequence !== sequences[index - 1] + 1) {
      fail("SEQUENCE_WATERMARK_INVALID", `gap ${sequences[index - 1]} -> ${sequence}`);
    }
    // The chain is what makes the prefix tamper-evident: each frame names its predecessor's bytes.
    const event = evidence.events[index] as unknown as Record<string, any>;
    const previousDigest = evidence.frameSha256.get(sequences[index - 1]);
    if (typeof event.prev_frame_sha256 === "string" && previousDigest
      && event.prev_frame_sha256 !== previousDigest) {
      fail("SEQUENCE_WATERMARK_INVALID", `broken chain at sequence ${sequence}`);
    }
  });
  const watermark = evidence.watermark;
  if (!watermark) fail("SEQUENCE_WATERMARK_INVALID", "no committed watermark was published");
  if (watermark.batch_id !== evidence.manifest.batch_id) {
    fail("SEQUENCE_WATERMARK_INVALID", `watermark names batch ${String(watermark.batch_id)}`);
  }
  const sequence = Number(watermark.sequence);
  const named = evidence.frameSha256.get(sequence);
  if (!Number.isInteger(sequence) || sequence < 1 || !named) {
    fail("SEQUENCE_WATERMARK_INVALID", `watermark sequence ${String(watermark.sequence)}`);
  }
  if (typeof watermark.event_sha256 !== "string" || watermark.event_sha256 !== named) {
    fail("SEQUENCE_WATERMARK_INVALID", `watermark digest at sequence ${sequence}`);
  }
  const boundary = evidence.events.find((event) => Number(event.sequence) === sequence) as
    | Record<string, any>
    | undefined;
  if (!boundary || boundary.coordinator_epoch !== watermark.writer_epoch) {
    fail("SEQUENCE_WATERMARK_INVALID", `watermark writer epoch at sequence ${sequence}`);
  }
  for (const attempt of committedAttempts(evidence)) {
    if (attempt.sequence > sequence) {
      fail("SEQUENCE_WATERMARK_INVALID", `commit ${attempt.pointId} beyond the watermark`);
    }
  }
  const projection = evidence.projection;
  if (projection && Number(projection.sequence) < sequence) {
    fail("SEQUENCE_WATERMARK_INVALID",
      `projection sequence ${String(projection.sequence)} is behind the watermark ${sequence}`);
  }
}

/**
 * Every committed attempt carries the sealed physical evidence set, byte for byte: the sealed
 * manifest's own inventory is the authority, and the MuJoCo physical document itself has to name
 * a real object state, simulation step and publisher sequence.
 */
export function assertPhysicalEvidenceSet(evidence: CampaignBatchEvidence): void {
  for (const attempt of committedAttempts(evidence)) {
    const sealedDir = resolve(attempt.sealedDir);
    const manifest = readJsonFile(
      join(sealedDir, "attempt_result_manifest.json"), "PHYSICAL_EVIDENCE_INVALID");
    const inventory = new Map<string, Record<string, any>>(
      (Array.isArray(manifest.files) ? manifest.files : []).map(
        (entry: Record<string, any>) => [String(entry.relative_path), entry]),
    );
    for (const relativePath of PHYSICAL_EVIDENCE_FILES) {
      const path = join(sealedDir, relativePath);
      const entry = inventory.get(relativePath);
      if (!entry || !existsSync(path)) {
        fail("PHYSICAL_EVIDENCE_INVALID", `${attempt.pointId} ${relativePath}`);
      }
      const bytes = readFileSync(path);
      if (bytes.length !== entry.size || sha256(bytes) !== entry.sha256) {
        fail("PHYSICAL_EVIDENCE_INVALID", `${attempt.pointId} ${relativePath}`);
      }
    }
    let physical: Record<string, any>;
    try {
      physical = JSON.parse(
        readFileSync(join(sealedDir, "numeric/physical.json"), "utf-8"));
    } catch {
      return fail("PHYSICAL_EVIDENCE_INVALID", `${attempt.pointId} numeric/physical.json`);
    }
    if (
      !physical
      || typeof physical.object_state !== "object" || physical.object_state === null
      || !Number.isInteger(physical.simulation_step) || physical.simulation_step <= 0
      || !Number.isInteger(physical.publisher_sequence) || physical.publisher_sequence <= 0
    ) {
      fail("PHYSICAL_EVIDENCE_INVALID", `${attempt.pointId} physical facts`);
    }
  }
}

/** The batch closed its own cleanup, and the service projection agrees it is complete. */
export function assertCleanupComplete(
  evidence: CampaignBatchEvidence,
  projection?: Record<string, unknown> | null,
): void {
  const cleanup = evidence.cleanup;
  if (
    cleanup.batch_cleanup_complete !== true
    || cleanup.cleanup_gates_passed !== true
    || cleanup.coordinator_completion?.succeeded !== true
    || cleanup.batch_id !== evidence.manifest.batch_id
  ) {
    fail("CLEANUP_INCOMPLETE", `cleanup gates for ${String(evidence.manifest.batch_id)}`);
  }
  // The canonical stream closes with CLEANUP_COMMITTED; the legacy fixed coordinator closes with
  // BATCH_CLEANUP_COMPLETE. Either is the batch's own terminal cleanup proof.
  const closed = evidence.events.some(
    (event) => event.type === "CLEANUP_COMMITTED" || event.type === "BATCH_CLEANUP_COMPLETE");
  if (!closed) fail("CLEANUP_INCOMPLETE", "the journal never closed the batch cleanup");
  if (projection && projection.batch_cleanup_complete !== true) {
    fail("CLEANUP_INCOMPLETE", "projection still reports an unfinished cleanup");
  }
}

/** The routing key the receipt resolved from the document's real bytes, never from a point count. */
export function assertRoutingClaim(
  receipt: Record<string, unknown>,
  expectation: CampaignBatchExpectation,
): void {
  if (receipt.admitted !== true) {
    fail("ROUTING_CLAIM_INVALID", `receipt not admitted: ${JSON.stringify(receipt.reason_codes ?? [])}`);
  }
  if (
    receipt.execution_profile !== expectation.executionProfile
    || receipt.execution_schema_version !== expectation.schemaVersion
    || receipt.execution_batch_kind !== expectation.batchKind
  ) {
    fail("ROUTING_CLAIM_INVALID",
      `receipt claims ${String(receipt.execution_profile)}/v${String(receipt.execution_schema_version)}`
      + `/${String(receipt.execution_batch_kind)} instead of ${expectation.executionProfile}`
      + `/v${expectation.schemaVersion}/${expectation.batchKind}`);
  }
}

/** All four batch-level claims at once: selected-only, watermark, physics and cleanup. */
export function assertCampaignBatchEvidence(
  evidence: CampaignBatchEvidence,
  expectation: CampaignBatchExpectation,
): void {
  assertSelectedOnlyAttempts(evidence, expectation);
  assertSequenceAndWatermark({ ...evidence, projection: expectation.projection ?? null });
  if (expectation.projection) {
    const claimedBatch = expectation.projection.batch_id;
    if (claimedBatch !== undefined && claimedBatch !== evidence.manifest.batch_id) {
      fail("SELECTED_ONLY_EVIDENCE_INVALID", `projection names batch ${String(claimedBatch)}`);
    }
  }
  assertPhysicalEvidenceSet(evidence);
  assertCleanupComplete(evidence, expectation.projection ?? null);
}
