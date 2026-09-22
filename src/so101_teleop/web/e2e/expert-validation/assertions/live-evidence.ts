/**
 * L3 live evidence assertions.  Every phase claim must be backed by sealed
 * attempt evidence read from disk; unreached phases are recorded as
 * NOT_REACHED, never presented as success.
 *
 * The campaign block below is the batch-level contract for the three macOS execution paths: W2
 * (two parallel workers), W1 first-pass (one worker, many points) and the single-point
 * FULL_RESTART_RETRY batch. It reads the batch's own bytes - the committed journal, the published
 * durability watermark, the batch's own selection, the committed per-point results with their
 * hashed evidence manifests, the lease/worker-result documents and the cleanup gates - and refuses
 * anything it cannot re-derive.
 *
 * Two batch layouts exist, and the verifier picks the branch from the batch's own bytes rather than
 * from the caller's platform:
 *
 *   - `LINUX_FIXED`   - the fixed coordinator's batch: `batch_manifest.json`,
 *                       `cleanup-gates.json`, `workers/<id>/attempts/<point>/<attempt>/sealed`.
 *   - `MACOS_COMPOSED` - the composed campaign's batch: `selection-binding.json`,
 *                       `journal/` (segmented coordinator epochs), `points/<point>.yaml`,
 *                       `point-results/<point>.json`, the per-attempt station trees and
 *                       `campaign-result.json`.
 *
 * A root that matches neither branch, or both, is an error; there is no third, lenient path.
 */

import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync, realpathSync } from "node:fs";
import { dirname, isAbsolute, join, relative, resolve, sep } from "node:path";

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

/**
 * The batch layout the root actually carries. The verifier never guesses it from the caller's
 * platform: it reads the batch's own documents and refuses a root that matches both or neither.
 */
export type CampaignBatchLayout = "LINUX_FIXED" | "MACOS_COMPOSED";

/** The document schema every composed-campaign dynamic execute manifest carries. */
export const MACOS_DYNAMIC_MANIFEST_SCHEMA = "so101-dynamic-mujoco-execute-v1";

/** The verdicts the composed campaign's own `campaign-result.json` may close on. */
export const MACOS_TERMINAL_STATUSES = [
  "W2_CAMPAIGN_PASS",
  "W2_CAMPAIGN_INCOMPLETE",
  "N1_CAMPAIGN_PASS",
  "N1_CAMPAIGN_INCOMPLETE",
] as const;

const SHA256_HEX = /^[0-9a-f]{64}$/;
const ZERO_SHA256 = "0".repeat(64);
const MACOS_SEGMENT_FILE = /^segment-\d{20}\.journal$/;
const MACOS_EVENT_KEYS = [
  "batch_id", "coordinator_epoch", "idempotency_key", "kind", "payload",
  "prev_frame_sha256", "sequence", "type",
];

function isRecord(value: unknown): value is Record<string, any> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function exactKeys(document: Record<string, any>, expected: string[]): boolean {
  const keys = Object.keys(document);
  return keys.length === expected.length && expected.every((key) => keys.includes(key));
}

function isSha256(value: unknown): boolean {
  return typeof value === "string" && SHA256_HEX.test(value);
}

/** A sorted, duplicate-free point selection; anything else is a refusal. */
function pointIds(value: unknown, code: string): string[] {
  if (
    !Array.isArray(value) || value.length === 0
    || value.some((entry) => typeof entry !== "string" || entry === "")
  ) {
    fail(code, "invalid point selection");
  }
  const ids = [...(value as string[])].sort();
  if (new Set(ids).size !== ids.length) fail(code, "duplicate point in the selection");
  return ids;
}

function physicalPath(path: string): string {
  try {
    return realpathSync(path);
  } catch {
    return path;
  }
}

/** Two document paths name the same directory, whichever alias they were written through. */
function samePath(left: unknown, right: unknown): boolean {
  if (typeof left !== "string" || typeof right !== "string") return false;
  if (left === "" || right === "") return false;
  return physicalPath(resolve(left)) === physicalPath(resolve(right));
}

/**
 * The path of `candidate` inside `batchRoot`, or `null`. A document may address the batch through a
 * physically identical alias of the root - Darwin's `/tmp` is `/private/tmp`, and a service that
 * resolved its evidence root writes the other spelling than the caller inspected - so containment is
 * checked against the inspected root and against its resolved form. The result is always expressed
 * against the inspected root, so every path this module returns lives in one namespace.
 */
function batchRelativeInside(batchRoot: string, candidate: string): string | null {
  for (const root of [batchRoot, physicalPath(batchRoot)]) {
    const inside = relative(root, candidate);
    if (inside !== "" && !inside.startsWith("..") && !isAbsolute(inside)) return inside;
  }
  return null;
}

/** Resolve a batch-relative path and refuse anything that leaves the batch's own tree. */
function insideBatch(batchRoot: string, candidate: unknown, code: string): string {
  if (typeof candidate !== "string" || candidate === "" || isAbsolute(candidate)) {
    fail(code, `path ${String(candidate)}`);
  }
  const inside = batchRelativeInside(batchRoot, resolve(batchRoot, candidate));
  if (inside === null) fail(code, `path outside the batch: ${candidate}`);
  return join(batchRoot, inside);
}

/** Resolve a path a document recorded (absolute or relative) and require it inside the batch. */
function withinBatch(batchRoot: string, candidate: unknown, code: string, detail: string): string {
  if (typeof candidate !== "string" || candidate === "") fail(code, `${detail} ${String(candidate)}`);
  const inside = batchRelativeInside(batchRoot, resolve(batchRoot, candidate));
  if (inside === null) fail(code, `${detail} outside the batch: ${candidate}`);
  return join(batchRoot, inside);
}

/** Resolve a path inside a directory, refusing a relative entry that escapes it. */
function insideDirectory(root: string, candidate: unknown, code: string, detail: string): string {
  if (typeof candidate !== "string" || candidate === "" || isAbsolute(candidate)) {
    fail(code, `${detail} ${String(candidate)}`);
  }
  const target = resolve(root, candidate);
  assertInside(root, target, code, detail);
  return target;
}

/** Refuse an already-resolved path that is not inside the directory it claims to belong to. */
function assertInside(root: string, target: string, code: string, detail: string): void {
  const inside = relative(root, target);
  if (inside === "" || inside.startsWith("..") || isAbsolute(inside)) {
    fail(code, `${detail} outside ${root}: ${target}`);
  }
}

function parseDocument(bytes: Buffer, code: string, detail: string): Record<string, any> {
  let value: unknown;
  try {
    value = JSON.parse(bytes.toString("utf-8"));
  } catch {
    return fail(code, `unreadable ${detail}`);
  }
  if (!isRecord(value)) fail(code, `not a document: ${detail}`);
  return value;
}

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
  /**
   * The attempt's own evidence directory, always inside the batch: the sealed attempt tree on the
   * Linux layout, the point's evidence directory (holding its point result and dynamic manifest) on
   * the macOS one.
   */
  sealedDir: string;
  sequence: number;
};

/** One journal frame: a sequence-carrying event, or a segment header that only chains epochs. */
export type JournalFrame = {
  kind: string;
  /** `event` frames carry the coordinator's sequence; `segment` headers deliberately do not. */
  sequence: number | null;
  /** The digest of the frame's own bytes: successors and the watermark name this value. */
  sha256: string;
  document: Record<string, any>;
};

export type CampaignBatchEvidence = {
  batchRoot: string;
  /** Which layout the root carries; every assertion below dispatches on it. */
  layout: CampaignBatchLayout;
  /** The batch's own selection: `batch_manifest.json` (Linux) or `selection-binding.json` (macOS). */
  manifest: Record<string, any>;
  /** The batch's own end state: `cleanup-gates.json` (Linux) or `campaign-result.json` (macOS). */
  cleanup: Record<string, any>;
  watermark: Record<string, any> | null;
  events: JournalEvent[];
  /** The digest of each frame's own bytes, by journal sequence. */
  frameSha256: Map<number, string>;
  /** macOS only: every frame in written order, segment headers included. */
  journalFrames: JournalFrame[] | null;
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

/**
 * The layout the root carries, from the batch's own documents. A root that carries both layouts is
 * ambiguous and a root that carries neither is not a batch: both are refusals, never a fallback.
 */
export function campaignBatchLayout(batchRoot: string): CampaignBatchLayout {
  const root = resolve(batchRoot);
  const linux = existsSync(join(root, "batch_manifest.json"));
  const macos = existsSync(join(root, "selection-binding.json"));
  if (linux && macos) fail("CAMPAIGN_EVIDENCE_INVALID", `both batch layouts under ${root}`);
  if (linux) return "LINUX_FIXED";
  if (macos) return "MACOS_COMPOSED";
  return fail("CAMPAIGN_EVIDENCE_INVALID", `no batch layout under ${root}`);
}

/**
 * The composed campaign's journal frames, in written order and validated to the producer's own
 * contract before any claim is read out of them: `segment-<20-digit epoch>.journal` files in
 * ascending epoch order, each starting with a segment header that chains onto the previous
 * segment's last frame, then event frames whose sequence is the running event count, whose epoch is
 * their segment's, and whose `prev_frame_sha256` is the digest of the frame before them. A segment
 * header deliberately carries no sequence, so the chain is followed over the frames themselves
 * rather than over the events alone.
 */
function readMacosJournalFrames(journalRoot: string, batchId: string): JournalFrame[] {
  const code = "CAMPAIGN_EVIDENCE_INVALID";
  const eventsDir = join(journalRoot, "events");
  if (!existsSync(eventsDir)) fail(code, `missing ${eventsDir}`);
  const names = readdirSync(eventsDir).filter((entry) => entry.endsWith(".journal")).sort();
  if (names.length === 0) fail(code, `no journal segment in ${eventsDir}`);
  const frames: JournalFrame[] = [];
  const idempotencyKeys = new Set<string>();
  let terminal = ZERO_SHA256;
  let lastEpoch = 0;
  let eventCount = 0;
  for (const name of names) {
    if (!MACOS_SEGMENT_FILE.test(name)) fail(code, `unexpected journal file ${name}`);
    const epoch = Number(name.slice("segment-".length, -".journal".length));
    if (epoch <= lastEpoch) fail(code, `segment order at ${name}`);
    lastEpoch = epoch;
    const data = readFileSync(join(eventsDir, name));
    let offset = 0;
    let headerSeen = false;
    while (offset < data.length) {
      if (offset + 73 > data.length) fail(code, `torn frame in ${name}`);
      const payloadLength = Number(data.readBigUInt64BE(offset));
      const end = offset + 73 + payloadLength;
      if (payloadLength <= 0 || end > data.length || data[end - 1] !== 0x0a) {
        fail(code, `torn frame in ${name}`);
      }
      const payloadBytes = data.subarray(offset + 72, end - 1);
      if (data.subarray(offset + 8, offset + 72).toString("ascii") !== sha256(payloadBytes)) {
        fail(code, `frame digest mismatch in ${name}`);
      }
      const document = parseDocument(payloadBytes, code, `frame in ${name}`);
      const frameSha = sha256(data.subarray(offset, end));
      if (document.kind === "segment") {
        if (headerSeen) fail(code, `second segment header in ${name}`);
        const keys = [
          "batch_id", "coordinator_epoch", "kind", "prev_segment_sha256", "prev_tail_sha256",
        ];
        if (document.schema_version !== undefined) keys.push("schema_version");
        if (
          !exactKeys(document, keys)
          || document.batch_id !== batchId
          || document.coordinator_epoch !== epoch
          || (document.prev_tail_sha256 !== null && !isSha256(document.prev_tail_sha256))
        ) {
          fail(code, `segment header in ${name}`);
        }
        if (document.prev_segment_sha256 !== terminal) {
          fail("SEQUENCE_WATERMARK_INVALID", `segment chain at ${name}`);
        }
        headerSeen = true;
      } else if (document.kind === "event") {
        if (!headerSeen) fail(code, `event before the segment header in ${name}`);
        if (
          !exactKeys(document, [...MACOS_EVENT_KEYS])
          || document.batch_id !== batchId
          || document.coordinator_epoch !== epoch
          || typeof document.type !== "string" || document.type === ""
          || typeof document.idempotency_key !== "string" || document.idempotency_key === ""
          || idempotencyKeys.has(document.idempotency_key)
          || !isRecord(document.payload)
        ) {
          fail(code, `event frame in ${name}`);
        }
        if (document.sequence !== eventCount + 1) {
          fail("SEQUENCE_WATERMARK_INVALID", `journal sequence ${String(document.sequence)}`);
        }
        if (document.prev_frame_sha256 !== terminal) {
          fail("SEQUENCE_WATERMARK_INVALID", `broken chain at sequence ${String(document.sequence)}`);
        }
        idempotencyKeys.add(document.idempotency_key);
        eventCount += 1;
      } else {
        fail(code, `unexpected frame kind in ${name}`);
      }
      frames.push({
        kind: document.kind,
        sequence: document.kind === "event" ? Number(document.sequence) : null,
        sha256: frameSha,
        document,
      });
      terminal = frameSha;
      offset = end;
    }
    if (!headerSeen) fail(code, `segment without a header in ${name}`);
  }
  return frames;
}

/** Read the batch's own selection, end state, committed journal, watermark and frames. */
export function readCampaignBatchEvidence(batchRoot: string): CampaignBatchEvidence {
  const root = resolve(batchRoot);
  const layout = campaignBatchLayout(root);
  const journalRoot = campaignJournalRoot(root);
  const watermarkPath = join(journalRoot, "committed-watermark.json");
  const watermark = existsSync(watermarkPath)
    ? readJsonFile(watermarkPath, "SEQUENCE_WATERMARK_INVALID")
    : null;
  if (layout === "LINUX_FIXED") {
    return {
      batchRoot: root,
      layout,
      manifest: readJsonFile(join(root, "batch_manifest.json"), "CAMPAIGN_EVIDENCE_INVALID"),
      cleanup: readJsonFile(join(root, "cleanup-gates.json"), "CAMPAIGN_EVIDENCE_INVALID"),
      watermark,
      events: readJournalEvents(journalRoot),
      frameSha256: readFrameDigests(journalRoot),
      journalFrames: null,
    };
  }
  const manifest = readJsonFile(join(root, "selection-binding.json"), "CAMPAIGN_EVIDENCE_INVALID");
  if (typeof manifest.batch_id !== "string" || manifest.batch_id === "") {
    fail("CAMPAIGN_EVIDENCE_INVALID", `no batch identity in ${join(root, "selection-binding.json")}`);
  }
  if (!existsSync(join(root, "point-results"))) {
    fail("CAMPAIGN_EVIDENCE_INVALID", `missing ${join(root, "point-results")}`);
  }
  const journalFrames = readMacosJournalFrames(journalRoot, manifest.batch_id);
  const headers = journalFrames.filter((frame) => frame.kind === "segment");
  const epoch = readJsonFile(join(journalRoot, "coordinator_epoch.json"), "CAMPAIGN_EVIDENCE_INVALID");
  if (
    epoch.batch_id !== manifest.batch_id
    || epoch.coordinator_epoch !== headers[headers.length - 1].document.coordinator_epoch
  ) {
    fail("CAMPAIGN_EVIDENCE_INVALID", `coordinator epoch in ${journalRoot}`);
  }
  return {
    batchRoot: root,
    layout,
    manifest,
    cleanup: readJsonFile(join(root, "campaign-result.json"), "CAMPAIGN_EVIDENCE_INVALID"),
    watermark,
    events: readJournalEvents(journalRoot),
    frameSha256: new Map(journalFrames
      .filter((frame) => frame.sequence !== null)
      .map((frame) => [frame.sequence as number, frame.sha256])),
    journalFrames,
  };
}

/** Every committed point result of a macOS batch, keyed by point; unreadable ones are refusals. */
function macosPointResults(evidence: CampaignBatchEvidence): Map<string, Record<string, any>> {
  const directory = join(evidence.batchRoot, "point-results");
  if (!existsSync(directory)) fail("CAMPAIGN_EVIDENCE_INVALID", `missing ${directory}`);
  const names = readdirSync(directory).filter((entry) => entry.endsWith(".json")).sort();
  if (names.length === 0) fail("CAMPAIGN_EVIDENCE_INVALID", `no point result in ${directory}`);
  const results = new Map<string, Record<string, any>>();
  for (const name of names) {
    const path = join(directory, name);
    const document = readJsonFile(path, "CAMPAIGN_EVIDENCE_INVALID");
    const pointId = name.slice(0, -".json".length);
    if (document.point_id !== pointId) {
      fail("SELECTED_ONLY_EVIDENCE_INVALID", `${path} names ${String(document.point_id)}`);
    }
    if (results.has(pointId)) fail("SELECTED_ONLY_EVIDENCE_INVALID", `${pointId} committed twice`);
    results.set(pointId, document);
  }
  return results;
}

function macosCommittedResults(evidence: CampaignBatchEvidence): Map<string, Record<string, any>> {
  const results = macosPointResults(evidence);
  for (const [pointId, document] of results) {
    if (document.committed !== true) {
      fail("SELECTED_ONLY_EVIDENCE_INVALID", `${pointId} has no committed result`);
    }
    if (!["PASSED", "FAILED"].includes(String(document.outcome))) {
      fail("SELECTED_ONLY_EVIDENCE_INVALID", `${pointId} outcome ${String(document.outcome)}`);
    }
  }
  return results;
}

/** The macOS commits: one per selected point, named by the journal and backed by its own result. */
function macosCommittedAttempts(
  evidence: CampaignBatchEvidence,
  results: Map<string, Record<string, any>>,
): CommittedAttempt[] {
  const code = "SELECTED_ONLY_EVIDENCE_INVALID";
  const attempts: CommittedAttempt[] = [];
  const committed = new Set<string>();
  for (const event of evidence.events.filter((entry) => entry.type === "RESULT_COMMITTED")) {
    const payload = (event.payload ?? {}) as Record<string, any>;
    const pointId = String(payload.point_id ?? "");
    const attemptId = String(payload.attempt_id ?? "");
    const workerId = String(payload.worker_id ?? "");
    if (pointId === "" || attemptId === "" || workerId === "") {
      fail(code, `incomplete commit at sequence ${String(event.sequence)}`);
    }
    if (committed.has(pointId)) fail(code, `${pointId} committed twice`);
    const document = results.get(pointId);
    if (!document) fail(code, `${pointId} committed without a point result`);
    if (String(document.attempt_id) !== attemptId || String(document.worker_id) !== workerId) {
      fail(code, `${pointId} commit identity`);
    }
    if (
      payload.evidence_manifest_sha256 !== document.evidence_manifest_sha256
      || payload.dynamic_manifest_sha256 !== document.dynamic_manifest_sha256
    ) {
      fail(code, `${pointId} commit digests`);
    }
    const manifestPath = insideBatch(
      evidence.batchRoot, document.evidence_manifest_relative_path, code);
    committed.add(pointId);
    attempts.push({
      pointId,
      attemptId,
      workerId,
      sealedDir: dirname(manifestPath),
      sequence: Number(event.sequence ?? 0),
    });
  }
  for (const pointId of results.keys()) {
    if (!committed.has(pointId)) fail(code, `${pointId} has no RESULT_COMMITTED event`);
  }
  return attempts;
}

/** Every committed attempt the batch names, in journal order. */
export function committedAttempts(evidence: CampaignBatchEvidence): CommittedAttempt[] {
  if (evidence.layout === "MACOS_COMPOSED") {
    return macosCommittedAttempts(evidence, macosCommittedResults(evidence));
  }
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
 * selected point is missing one, every piece of evidence stays inside the batch's own tree, and on
 * the macOS layout every commit is additionally bound to its lease, its single-point input, its
 * worker's own result document and its station readback.
 */
export function assertSelectedOnlyAttempts(
  evidence: CampaignBatchEvidence,
  expectation: CampaignBatchExpectation,
): void {
  if (evidence.layout === "MACOS_COMPOSED") {
    assertMacosSelectedOnly(evidence, expectation);
    return;
  }
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
 * The macOS half of the same claim. The selection is the batch's own `selection-binding.json`,
 * cross-checked against the campaign's verdict document and the durable queue; every selected point
 * has exactly one lease, one committed point result and one journal commit, every lease is bound to
 * the selection's own point digest and to the single-point input on disk, and the commit's worker
 * result document still hashes to the digest the commitment recorded.
 */
function assertMacosSelectedOnly(
  evidence: CampaignBatchEvidence,
  expectation: CampaignBatchExpectation,
): void {
  const code = "SELECTED_ONLY_EVIDENCE_INVALID";
  const binding = evidence.manifest;
  if (binding.schema_version !== 1) {
    fail(code, `selection schema ${String(binding.schema_version)}`);
  }
  const batchId = String(binding.batch_id);
  const selection = binding.binding;
  if (!isRecord(selection)) fail(code, `no selection binding in ${batchId}`);
  const selected = pointIds(binding.selected_point_ids, code);
  if (!isSha256(binding.selection_sha256)) fail(code, `selection digest in ${batchId}`);
  if (
    selection.batch_id !== batchId
    || selection.selection_sha256 !== binding.selection_sha256
    || !["FIRST_PASS", "FULL_RESTART_RETRY"].includes(String(selection.kind))
    || typeof selection.campaign_id !== "string" || selection.campaign_id === ""
    || pointIds(selection.selected_point_ids, code).join("\u0000") !== selected.join("\u0000")
  ) {
    fail(code, `selection binding for ${batchId}`);
  }
  if (!Array.isArray(selection.points)) fail(code, `selection points for ${batchId}`);
  const pointDigests = new Map<string, string>();
  for (const entry of selection.points) {
    if (!isRecord(entry) || typeof entry.point_id !== "string" || !isSha256(entry.point_sha256)) {
      fail(code, `selection point entry for ${batchId}`);
    }
    pointDigests.set(entry.point_id, entry.point_sha256);
  }
  for (const pointId of selected) {
    if (!pointDigests.has(pointId)) fail(code, `selection point ${pointId}`);
  }
  const expected = [...expectation.selectedPointIds].sort();
  if (selected.join("\u0000") !== expected.join("\u0000")) {
    fail(code, `selection ${selected.join(",")} is not ${expected.join(",")}`);
  }
  if (selection.kind !== expectation.batchKind) {
    fail(code, `batch kind ${String(selection.kind)} is not ${expectation.batchKind}`);
  }

  // The campaign's verdict document is the same batch's own statement of its route and selection.
  const campaign = evidence.cleanup;
  const route = campaign.route;
  if (
    !isRecord(route)
    || route.batch_kind !== expectation.batchKind
    || route.worker_count !== expectation.workerCount
    || route.execution_profile !== expectation.executionProfile
    || route.schema_version !== expectation.schemaVersion
  ) {
    fail(code, `route ${JSON.stringify(isRecord(route) ? route : null)} is not `
      + `${expectation.executionProfile}/v${expectation.schemaVersion}`
      + `/${expectation.batchKind}/${expectation.workerCount}`);
  }
  const claimed = campaign.selection;
  if (
    !isRecord(claimed)
    || claimed.kind !== selection.kind
    || claimed.selection_sha256 !== binding.selection_sha256
    || pointIds(claimed.selected_point_ids, code).join("\u0000") !== selected.join("\u0000")
  ) {
    fail(code, `campaign selection for ${batchId}`);
  }
  const completeness = campaign.points;
  if (
    !isRecord(completeness)
    || completeness.complete !== true
    || !Array.isArray(completeness.duplicate_attempts) || completeness.duplicate_attempts.length !== 0
    || !Array.isArray(completeness.unselected_attempts) || completeness.unselected_attempts.length !== 0
    || !Array.isArray(completeness.unexecuted_point_ids) || completeness.unexecuted_point_ids.length !== 0
    || !Array.isArray(completeness.infrastructure_failures)
    || completeness.infrastructure_failures.length !== 0
    || !Array.isArray(completeness.missing_physical_evidence)
    || completeness.missing_physical_evidence.length !== 0
    || pointIds(completeness.selected_point_ids, code).join("\u0000") !== selected.join("\u0000")
    || pointIds(Object.keys(isRecord(completeness.committed) ? completeness.committed : {}), code)
      .join("\u0000") !== selected.join("\u0000")
  ) {
    fail(code, `points completeness for ${batchId}`);
  }

  // The durable queue is the third authority for the same selection.
  const queue = readJsonFile(join(evidence.batchRoot, "queue", "queue-state.json"), code);
  if (
    queue.batch_id !== batchId
    || queue.selection_sha256 !== binding.selection_sha256
    || pointIds(queue.selected_point_ids, code).join("\u0000") !== selected.join("\u0000")
    || pointIds(Object.keys(isRecord(queue.committed_results) ? queue.committed_results : {}), code)
      .join("\u0000") !== selected.join("\u0000")
  ) {
    fail(code, `queue selection for ${batchId}`);
  }

  // One lease per selected point, bound to the selection's point digest and to its own input.
  const leaseNames = readdirSync(evidence.batchRoot)
    .filter((entry) => /-lease-\d+\.json$/.test(entry))
    .sort();
  if (leaseNames.length === 0) fail(code, `no lease in ${evidence.batchRoot}`);
  const leases = new Map<string, Record<string, any>>();
  for (const name of leaseNames) {
    const document = readJsonFile(join(evidence.batchRoot, name), code);
    const pointId = String(document.point_id ?? "");
    if (pointId === "" || !selected.includes(pointId)) fail(code, `${name} leases ${pointId}`);
    if (
      document.batch_id !== batchId
      || document.selection_sha256 !== binding.selection_sha256
      || document.batch_kind !== selection.kind
      || document.point_sha256 !== pointDigests.get(pointId)
    ) {
      fail(code, `${name} is not bound to the selection`);
    }
    if (leases.has(pointId)) fail(code, `${pointId} leased twice`);
    leases.set(pointId, document);
  }

  const results = macosCommittedResults(evidence);
  const attempts = macosCommittedAttempts(evidence, results);
  for (const attempt of attempts) {
    if (!selected.includes(attempt.pointId)) {
      fail(code, `unselected point ${attempt.pointId} committed`);
    }
  }
  for (const pointId of selected) {
    const committed = attempts.filter((attempt) => attempt.pointId === pointId);
    if (committed.length !== 1) fail(code, `${pointId} committed ${committed.length} times`);
  }
  if (attempts.length !== selected.length) {
    fail(code, `${attempts.length} commits for ${selected.length} selected points`);
  }
  for (const attempt of attempts) {
    const document = results.get(attempt.pointId) as Record<string, any>;
    const lease = leases.get(attempt.pointId);
    if (!lease) fail(code, `no lease for ${attempt.pointId}`);
    if (lease.attempt_id !== attempt.attemptId || lease.worker_id !== attempt.workerId) {
      fail(code, `${attempt.pointId} lease identity`);
    }
    if (
      String(document.attempt_id) !== attempt.attemptId
      || String(document.worker_id) !== attempt.workerId
      || !isSha256(document.lease_sha256)
    ) {
      fail(code, `${attempt.pointId} result identity`);
    }
    const inputPath = join(evidence.batchRoot, "points", `${attempt.pointId}.yaml`);
    if (!existsSync(inputPath)) fail(code, `${attempt.pointId} single-point input`);
    const inputSha = sha256(readFileSync(inputPath));
    if (document.points_sha256 !== inputSha || lease.points_sha256 !== inputSha) {
      fail(code, `${attempt.pointId} single-point input digest`);
    }
    const stationRoot = withinBatch(
      evidence.batchRoot, lease.station_root, code, `${attempt.pointId} station`);
    const readback = document.station_readback;
    if (!isRecord(readback) || !samePath(readback.station_root, stationRoot)) {
      fail(code, `${attempt.pointId} station readback`);
    }
    // The worker's own result document is the commitment's provenance, digest and all.
    const workerResult = withinBatch(
      evidence.batchRoot, document.worker_result_path, code, `${attempt.pointId} worker result`);
    if (
      !isSha256(document.worker_result_sha256)
      || !existsSync(workerResult)
      || sha256(readFileSync(workerResult)) !== document.worker_result_sha256
    ) {
      fail(code, `${attempt.pointId} worker result`);
    }
    const evidenceInside = batchRelativeInside(evidence.batchRoot, attempt.sealedDir);
    if (evidenceInside === null || !evidenceInside.startsWith(`${attempt.workerId}-station${sep}`)) {
      fail(code, `${attempt.pointId} evidence outside its worker's station`);
    }
    // The durable queue committed the same result, under the same evidence digest.
    const queued = queue.committed_results[attempt.pointId];
    if (
      !isRecord(queued)
      || queued.attempt_id !== attempt.attemptId
      || queued.outcome !== document.outcome
      || queued.evidence_sha256 !== document.evidence_manifest_sha256
    ) {
      fail(code, `${attempt.pointId} queue commitment`);
    }
  }
}

/**
 * The committed prefix is the sequence the watermark closed: the journal chain is contiguous,
 * the named frame digest is the one on disk, every commit sits at or below the watermark, and the
 * service projection never runs ahead of the durable watermark.
 */
export function assertSequenceAndWatermark(evidence: CampaignBatchEvidence): void {
  if (evidence.layout === "MACOS_COMPOSED") {
    assertMacosSequenceAndWatermark(evidence);
    return;
  }
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
 * The macOS half. The chain is followed over the journal's own frames, so a segment header is
 * skipped deliberately when the event sequences are read - it carries no sequence and is not an
 * event - while still being the frame every first event of its epoch names. The watermark has to
 * name a frame that is on disk, in the writer's own epoch, at the batch's final sequence, and the
 * campaign's verdict document has to name that same frame: a moved or copied watermark cannot
 * satisfy both.
 */
function assertMacosSequenceAndWatermark(evidence: CampaignBatchEvidence): void {
  const code = "SEQUENCE_WATERMARK_INVALID";
  if (!Array.isArray(evidence.journalFrames) || evidence.journalFrames.length === 0) {
    fail(code, "no journal frames");
  }
  const frames = evidence.journalFrames;
  const events = frames.filter((frame) => frame.kind === "event");
  if (events.length === 0 || frames.length === events.length) {
    fail(code, "the journal carries no segment header");
  }
  events.forEach((frame, index) => {
    const sequence = Number(frame.sequence);
    if (!Number.isInteger(sequence) || sequence < 1) {
      fail(code, `journal sequence ${String(frame.sequence)}`);
    }
    if (sequence !== index + 1) {
      fail(code, `gap ${String(events[index - 1]?.sequence)} -> ${sequence}`);
    }
  });
  for (let index = 1; index < frames.length; index += 1) {
    // The segment header chains epochs; every event frame chains its epoch's frames.
    const declared = frames[index].kind === "segment"
      ? frames[index].document.prev_segment_sha256
      : frames[index].document.prev_frame_sha256;
    if (declared !== frames[index - 1].sha256) {
      fail(code, `broken chain at frame ${index}`);
    }
  }
  const watermark = evidence.watermark;
  if (!watermark) fail(code, "no committed watermark was published");
  if (watermark.batch_id !== evidence.manifest.batch_id) {
    fail(code, `watermark names batch ${String(watermark.batch_id)}`);
  }
  const sequence = Number(watermark.sequence);
  if (!Number.isInteger(sequence) || sequence < 1) {
    fail(code, `watermark sequence ${String(watermark.sequence)}`);
  }
  const boundary = events.find((frame) => frame.sequence === sequence);
  if (!boundary) fail(code, `watermark sequence ${sequence} names no committed frame`);
  if (watermark.event_sha256 !== boundary.sha256) {
    fail(code, `watermark digest at sequence ${sequence}`);
  }
  if (boundary.document.coordinator_epoch !== watermark.writer_epoch) {
    fail(code, `watermark writer epoch at sequence ${sequence}`);
  }
  const last = events[events.length - 1];
  if (boundary !== last || boundary.document.type !== "CLEANUP_COMMITTED") {
    fail(code, `the watermark does not close the journal at sequence ${sequence}`);
  }
  const journal = evidence.cleanup.journal;
  if (
    !isRecord(journal)
    || journal.batch_id !== evidence.manifest.batch_id
    || !isRecord(journal.terminal_watermark)
    || journal.terminal_watermark.batch_id !== watermark.batch_id
    || journal.terminal_watermark.sequence !== watermark.sequence
    || journal.terminal_watermark.event_sha256 !== watermark.event_sha256
    || journal.terminal_watermark.writer_epoch !== watermark.writer_epoch
  ) {
    fail(code, "the campaign verdict names another terminal watermark");
  }
  if (!isRecord(journal.watermark)) fail(code, "the campaign verdict names no first watermark");
  const first = events.find((frame) => frame.sequence === Number(journal.watermark.sequence));
  if (
    !first
    || journal.watermark.batch_id !== watermark.batch_id
    || journal.watermark.event_sha256 !== first.sha256
    || journal.watermark.writer_epoch !== first.document.coordinator_epoch
  ) {
    fail(code, "the campaign verdict's first watermark names no committed frame");
  }
  for (const attempt of committedAttempts(evidence)) {
    if (attempt.sequence > sequence) {
      fail(code, `commit ${attempt.pointId} beyond the watermark`);
    }
  }
  const projection = evidence.projection;
  if (projection && Number(projection.sequence) < sequence) {
    fail(code,
      `projection sequence ${String(projection.sequence)} is behind the watermark ${sequence}`);
  }
}

/**
 * Every committed attempt carries the sealed physical evidence set, byte for byte: the sealed
 * manifest's own inventory is the authority, and the MuJoCo physical document itself has to name
 * a real object state, simulation step and publisher sequence.
 */
export function assertPhysicalEvidenceSet(evidence: CampaignBatchEvidence): void {
  if (evidence.layout === "MACOS_COMPOSED") {
    assertMacosPhysicalEvidence(evidence);
    return;
  }
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

/**
 * The macOS half. A composed batch does not seal a fixed file list; its point result names its own
 * evidence manifest and dynamic manifest with their digests, and the evidence manifest seals an
 * inventory of everything the attempt produced, relative to the attempt's station so nothing can
 * point outside the batch. Both digests are recomputed from the bytes, the dynamic manifest has to
 * be the one the inventory seals, and its final sample has to name a real object state, simulation
 * step, publisher sequence, table contact, release marker and planning-scene readback. A point that
 * reports itself PASSED without that manifest is refused, never skipped.
 */
function assertMacosPhysicalEvidence(evidence: CampaignBatchEvidence): void {
  const code = "PHYSICAL_EVIDENCE_INVALID";
  const results = macosCommittedResults(evidence);
  for (const attempt of committedAttempts(evidence)) {
    const document = results.get(attempt.pointId) as Record<string, any>;
    const stationRoot = withinBatch(
      evidence.batchRoot, (document.station_readback as Record<string, any>)?.station_root, code,
      `${attempt.pointId} station`);
    const pickRoot = join(stationRoot, "pick");
    const manifestPath = insideBatch(
      evidence.batchRoot, document.evidence_manifest_relative_path, code);
    assertInside(pickRoot, manifestPath, code, `${attempt.pointId} evidence manifest`);
    if (
      !isSha256(document.evidence_manifest_sha256)
      || !existsSync(manifestPath)
      || sha256(readFileSync(manifestPath)) !== document.evidence_manifest_sha256
    ) {
      fail(code, `${attempt.pointId} evidence manifest digest`);
    }
    const manifest = parseDocument(
      readFileSync(manifestPath), code, `${attempt.pointId} evidence manifest`);
    if (
      manifest.id !== attempt.pointId
      || manifest.manifest_path !== "point-result.json"
      || typeof manifest.status !== "string" || manifest.status === ""
      || !Array.isArray(manifest.artifacts)
    ) {
      fail(code, `${attempt.pointId} evidence manifest`);
    }
    const sealed = new Set<string>();
    for (const entry of manifest.artifacts) {
      if (
        !isRecord(entry)
        || !isSha256(entry.sha256)
        || !Number.isInteger(entry.byte_size) || entry.byte_size <= 0
      ) {
        fail(code, `${attempt.pointId} evidence inventory`);
      }
      const target = insideDirectory(
        pickRoot, entry.relative_path, code, `${attempt.pointId} artifact`);
      const relativePath = relative(pickRoot, target);
      if (!existsSync(target)) fail(code, `${attempt.pointId} ${relativePath}`);
      const bytes = readFileSync(target);
      if (bytes.length !== entry.byte_size || sha256(bytes) !== entry.sha256) {
        fail(code, `${attempt.pointId} ${relativePath}`);
      }
      sealed.add(relativePath);
    }
    const dynamicRelative = document.dynamic_manifest_relative_path;
    if (dynamicRelative === null || dynamicRelative === undefined) {
      if (
        document.physical_evidence === true
        || document.outcome === "PASSED"
        || document.dynamic_manifest_sha256 !== null
      ) {
        fail(code, `${attempt.pointId} claims physical evidence it does not carry`);
      }
      continue;
    }
    if (document.physical_evidence !== true) {
      fail(code, `${attempt.pointId} dynamic manifest without the physical claim`);
    }
    const dynamicPath = insideBatch(evidence.batchRoot, dynamicRelative, code);
    assertInside(pickRoot, dynamicPath, code, `${attempt.pointId} dynamic manifest`);
    if (
      !isSha256(document.dynamic_manifest_sha256)
      || !existsSync(dynamicPath)
      || sha256(readFileSync(dynamicPath)) !== document.dynamic_manifest_sha256
    ) {
      fail(code, `${attempt.pointId} dynamic manifest digest`);
    }
    if (!sealed.has(relative(pickRoot, dynamicPath))) {
      fail(code, `${attempt.pointId} dynamic manifest is not sealed by its own inventory`);
    }
    assertMacosDynamicFacts(
      attempt,
      parseDocument(readFileSync(dynamicPath), code, `${attempt.pointId} dynamic manifest`),
      code);
  }
}

/** The physical facts one composed attempt's dynamic execute manifest has to name. */
function assertMacosDynamicFacts(
  attempt: CommittedAttempt,
  dynamic: Record<string, any>,
  code: string,
): void {
  const pointId = attempt.pointId;
  if (dynamic.schema !== MACOS_DYNAMIC_MANIFEST_SCHEMA) {
    fail(code, `${pointId} dynamic schema ${String(dynamic.schema)}`);
  }
  if (dynamic.status !== "DONE" || dynamic.current_state !== "DONE") {
    fail(code, `${pointId} dynamic status ${String(dynamic.status)}`);
  }
  if (
    !Number.isInteger(dynamic.transition_count) || dynamic.transition_count <= 0
    || !Array.isArray(dynamic.state_trace) || !dynamic.state_trace.includes("DONE")
  ) {
    fail(code, `${pointId} dynamic transitions`);
  }
  if (!Number.isInteger(dynamic.release_marker_sequence) || dynamic.release_marker_sequence <= 0) {
    fail(code, `${pointId} release marker`);
  }
  const readback = dynamic.planning_scene_readback;
  if (
    !isRecord(readback)
    || !Array.isArray(readback.attached_object_ids)
    || !isRecord(readback.world_primitive_counts)
    || Object.keys(readback.world_primitive_counts).length === 0
    || Object.values(readback.world_primitive_counts)
      .some((count) => !Number.isInteger(count) || (count as number) <= 0)
  ) {
    fail(code, `${pointId} planning scene readback`);
  }
  if (
    typeof dynamic.simulation_session_id !== "string"
    || !dynamic.simulation_session_id.includes(attempt.workerId)
    || !dynamic.simulation_session_id.includes(attempt.attemptId)
  ) {
    fail(code, `${pointId} simulation session`);
  }
  if (!Array.isArray(dynamic.final_samples) || dynamic.final_samples.length === 0) {
    fail(code, `${pointId} final samples`);
  }
  const sample = dynamic.final_samples[dynamic.final_samples.length - 1];
  if (!isRecord(sample)) fail(code, `${pointId} final sample`);
  const vector = (value: unknown, length: number): boolean =>
    Array.isArray(value) && value.length === length
    && value.every((entry) => typeof entry === "number" && Number.isFinite(entry));
  if (
    !vector(sample.cup_position_world_m, 3)
    || !vector(sample.cup_orientation_world_xyzw, 4)
    || !vector(sample.cup_linear_velocity_world_m_s, 3)
    || !vector(sample.cup_angular_velocity_world_rad_s, 3)
  ) {
    fail(code, `${pointId} object state`);
  }
  if (
    !Number.isInteger(sample.simulation_step) || sample.simulation_step <= 0
    || !Number.isInteger(sample.publisher_sequence) || sample.publisher_sequence <= 0
    || typeof sample.table_contact !== "boolean"
  ) {
    fail(code, `${pointId} physical facts`);
  }
}

/** The batch closed its own cleanup, and the service projection agrees it is complete. */
export function assertCleanupComplete(
  evidence: CampaignBatchEvidence,
  projection?: Record<string, unknown> | null,
): void {
  if (evidence.layout === "MACOS_COMPOSED") {
    assertMacosCleanupComplete(evidence, projection);
    return;
  }
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

/**
 * The macOS half: the campaign's own verdict document has to report a terminal verdict, a complete
 * cleanup with every worker reaped and every station read back clear, and the stations it declared
 * clear have to be exactly the stations the committed attempts ran in. A missing readback, a dirty
 * station or an extra station is a refusal.
 */
function assertMacosCleanupComplete(
  evidence: CampaignBatchEvidence,
  projection?: Record<string, unknown> | null,
): void {
  const code = "CLEANUP_INCOMPLETE";
  const campaign = evidence.cleanup;
  const batchId = String(evidence.manifest.batch_id);
  if (!(MACOS_TERMINAL_STATUSES as readonly string[]).includes(String(campaign.status))) {
    fail(code, `the campaign verdict for ${batchId} is ${String(campaign.status)}`);
  }
  const cleanup = campaign.cleanup;
  if (
    !isRecord(cleanup)
    || cleanup.complete !== true
    || cleanup.stations_clear !== true
    || cleanup.directory_removed !== true
    || cleanup.registry_empty !== true
    || !Array.isArray(cleanup.workers_reaped) || cleanup.workers_reaped.length === 0
    || cleanup.workers_reaped.some((reaped: unknown) => reaped !== true)
    || !Array.isArray(cleanup.stations) || cleanup.stations.length === 0
  ) {
    fail(code, `cleanup gates for ${batchId}`);
  }
  const stations = new Set<string>();
  for (const station of cleanup.stations) {
    if (
      !isRecord(station)
      || station.clear !== true
      || !Array.isArray(station.matches) || station.matches.length !== 0
    ) {
      fail(code, `station readback for ${batchId}`);
    }
    const root = withinBatch(
      evidence.batchRoot, station.station_root, code, `station readback in ${batchId}`);
    if (stations.has(root)) fail(code, `duplicate station readback in ${batchId}`);
    stations.add(root);
  }
  const results = macosCommittedResults(evidence);
  const attempts = committedAttempts(evidence);
  for (const attempt of attempts) {
    const document = results.get(attempt.pointId) as Record<string, any>;
    const readback = document.station_readback as Record<string, any> | undefined;
    const stationRoot = withinBatch(
      evidence.batchRoot, readback?.station_root, code, `${attempt.pointId} station`);
    if (!stations.has(stationRoot)) {
      fail(code, `${attempt.pointId} station ${stationRoot} was never read back clear`);
    }
    if (
      !isRecord(readback)
      || readback.clear !== true
      || !Array.isArray(readback.matches) || readback.matches.length !== 0
    ) {
      fail(code, `${attempt.pointId} station ${stationRoot} is not clear`);
    }
  }
  if (stations.size !== attempts.length) {
    fail(code, `${stations.size} stations for ${attempts.length} committed attempts`);
  }
  // The canonical stream closes with CLEANUP_COMMITTED; the legacy fixed coordinator closes with
  // BATCH_CLEANUP_COMPLETE. Either is the batch's own terminal cleanup proof.
  const closed = evidence.events.some(
    (event) => event.type === "CLEANUP_COMMITTED" || event.type === "BATCH_CLEANUP_COMPLETE");
  if (!closed) fail(code, "the journal never closed the batch cleanup");
  if (projection && projection.batch_cleanup_complete !== true) {
    fail(code, "projection still reports an unfinished cleanup");
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
