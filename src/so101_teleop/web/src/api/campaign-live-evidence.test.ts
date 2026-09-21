/**
 * Campaign-level live evidence for the three macOS execution paths.
 *
 * W2 (two parallel workers), W1 first-pass (one worker, many points) and the single-point
 * FULL_RESTART_RETRY batch each have to prove four independent things from the batch's own bytes:
 * only the selected points were attempted, the journal sequence is covered by the published
 * durability watermark, every committed attempt carries the sealed physical evidence set, and the
 * batch completed its cleanup. A fabricated, truncated or unselected evidence tree fails closed.
 */
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, describe, expect, test } from "vitest";

import {
  PHYSICAL_EVIDENCE_FILES,
  assertCampaignBatchEvidence,
  assertRoutingClaim,
  readCampaignBatchEvidence,
  type CampaignBatchExpectation,
} from "../../e2e/expert-validation/assertions/live-evidence";

const roots: string[] = [];

afterEach(() => {
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true });
});

const sha256 = (data: Buffer | string): string =>
  createHash("sha256").update(data).digest("hex");

/** The documents a sealed execute attempt carries (the verifier's required physical evidence). */
const DOCUMENT_EVIDENCE: Record<string, unknown> = {
  "workspace_identity.json": { workspace_id: "ws-1" },
  "attempt-result.json": { status: "PASSED" },
  "pose_accepted.json": { type: "POSE_ACCEPTED" },
  "numeric/depth.json": { source_stamp_ns: 10, sha256: "a".repeat(64), byte_count: 8 },
  "numeric/tf.json": {
    source_frame: "world", target_frame: "cup", center_world_xyz: [0, 0, 0.1], source_stamp_s: 1,
  },
  "numeric/physical.json": {
    object_state: { cup_pose_world: [0, 0, 0.1, 0, 0, 0, 1], support_contact: true },
    simulation_step: 12,
    publisher_sequence: 3,
    simulation_session_id: "sim-1",
    reset_epoch: 1,
  },
};

const BINARY_EVIDENCE: Record<string, string> = {
  "initial-rgb.png": "initial-frame",
  "perception/input/rgb.npy": "raw-rgb",
  "terminal-rgb.png": "terminal-frame",
};

const canonical = (value: unknown): string => {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>).sort(([a], [b]) =>
      a < b ? -1 : a > b ? 1 : 0);
    return `{${entries.map(([key, entry]) => `${JSON.stringify(key)}:${canonical(entry)}`).join(",")}}`;
  }
  return JSON.stringify(value);
};

/** The journal frame layout: 8-byte big-endian length, the payload digest, the payload, a newline. */
function frame(document: Record<string, unknown>): Buffer {
  const payload = Buffer.from(canonical(document), "utf-8");
  const header = Buffer.alloc(8);
  header.writeBigUInt64BE(BigInt(payload.length));
  return Buffer.concat([
    header,
    Buffer.from(sha256(payload), "ascii"),
    payload,
    Buffer.from("\n"),
  ]);
}

function writeSealedAttempt(
  batchRoot: string, workerId: string, pointId: string, attemptId: string,
): string {
  const sealed = join(batchRoot, "workers", workerId, "attempts", pointId, attemptId, "sealed");
  mkdirSync(sealed, { recursive: true });
  const files: Array<Record<string, unknown>> = [];
  const write = (relative: string, bytes: Buffer) => {
    const target = join(sealed, relative);
    mkdirSync(join(target, ".."), { recursive: true });
    writeFileSync(target, bytes);
    files.push({
      relative_path: relative, size: bytes.length, sha256: sha256(bytes),
      producer_pid: 4101, producer_pgid: 4101,
    });
  };
  for (const [relative, document] of Object.entries(DOCUMENT_EVIDENCE)) {
    write(relative, Buffer.from(JSON.stringify(document)));
  }
  for (const [relative, contents] of Object.entries(BINARY_EVIDENCE)) {
    write(relative, Buffer.from(contents));
  }
  writeFileSync(
    join(sealed, "attempt_result_manifest.json"),
    JSON.stringify({ files, directories: [], identity: { batch_id: "batch" } }),
  );
  return sealed;
}

type ScenarioOptions = {
  batchId: string;
  batchKind: "FIRST_PASS" | "FULL_RESTART_RETRY";
  points: string[];
  workerCount: number;
  /** Selected points the journal never committed (an incomplete batch). */
  commits?: string[];
  /** Extra journal commits for points outside the selection. */
  extraCommits?: string[];
  projectionCleanup?: boolean;
  watermark?: { sequence?: number; event_sha256?: string } | null;
};

type Scenario = {
  root: string;
  expectation: CampaignBatchExpectation;
  sealedFor: (pointId: string) => string;
  journalRoot: string;
};

function scenario(options: ScenarioOptions): Scenario {
  const root = mkdtempSync(join(tmpdir(), "uq-campaign-evidence-"));
  roots.push(root);
  const workers = Array.from({ length: options.workerCount }, (_value, index) =>
    `worker-0${index + 1}`);
  const sealedDirs = new Map<string, string>();
  options.points.forEach((pointId, index) => {
    sealedDirs.set(
      pointId,
      writeSealedAttempt(root, workers[index % workers.length], pointId, `attempt-${index + 1}`),
    );
  });

  const events: Array<Record<string, unknown>> = [
    { type: "CAMPAIGN_STARTED", payload: { batch_id: options.batchId } },
  ];
  const commit = (pointId: string) => {
    const identity = {
      batch_id: options.batchId,
      coordinator_epoch: 1,
      worker_id: workers[options.points.indexOf(pointId) % workers.length] ?? workers[0],
      worker_generation: 1,
      point_id: pointId,
      attempt_id: `attempt-${pointId}`,
      lease_generation: 1,
      location: sealedDirs.get(pointId) ?? join(root, "workers", workers[0], "attempts", pointId),
    };
    events.push({
      type: "RESULT_COMMITTED",
      payload: {
        identity,
        response: {
          status: "PASSED",
          sha256: "b".repeat(64),
          location: identity.location,
        },
      },
    });
  };
  for (const pointId of options.commits ?? options.points) commit(pointId);
  for (const pointId of options.extraCommits ?? []) commit(pointId);
  events.push({ type: "BATCH_FINISHED", payload: { terminal_reason: "COMPLETED" } });
  events.push({ type: "CLEANUP_COMMITTED", payload: { cleanup_complete: true } });

  const journalRoot = join(root, "coordinator");
  mkdirSync(join(journalRoot, "events"), { recursive: true });
  writeFileSync(
    join(journalRoot, "coordinator_epoch.json"),
    JSON.stringify({ batch_id: options.batchId, coordinator_epoch: 1 }),
  );
  const frames: Buffer[] = [];
  let previous = "";
  events.forEach((event, index) => {
    const document = {
      kind: "event",
      batch_id: options.batchId,
      type: event.type,
      idempotency_key: `${options.batchId}-${index + 1}`,
      payload: event.payload,
      coordinator_epoch: 1,
      sequence: index + 1,
      prev_frame_sha256: previous,
    };
    const bytes = frame(document);
    frames.push(bytes);
    previous = sha256(bytes);
  });
  writeFileSync(join(journalRoot, "events", "epoch-1.journal"), Buffer.concat(frames));

  const lastSequence = frames.length;
  const defaultWatermark = {
    batch_id: options.batchId,
    writer_epoch: 1,
    sequence: lastSequence,
    event_sha256: previous,
  };
  const watermark = options.watermark === undefined
    ? defaultWatermark
    : options.watermark === null ? null : { ...defaultWatermark, ...options.watermark };
  if (watermark !== null) {
    writeFileSync(join(journalRoot, "committed-watermark.json"), JSON.stringify(watermark));
  }

  writeFileSync(join(root, "batch_manifest.json"), JSON.stringify({
    schema_version: 3,
    batch_kind: options.batchKind,
    batch_id: options.batchId,
    run_mode: "execute",
    selected_point_ids: options.points,
    worker_count: options.workerCount,
    evidence_root: root,
  }));
  writeFileSync(join(root, "cleanup-gates.json"), JSON.stringify({
    schema_version: 1,
    batch_id: options.batchId,
    actions: {},
    process_cleanup: { succeeded: true },
    container_cleanup: { succeeded: true },
    cleanup_gates_passed: true,
    coordinator_completion: { attempted: true, succeeded: true, error_type: null },
    batch_cleanup_complete: true,
  }));

  const projection = options.projectionCleanup === undefined
    ? null
    : { batch_id: options.batchId, batch_cleanup_complete: options.projectionCleanup, sequence: lastSequence };

  return {
    root,
    journalRoot,
    sealedFor: (pointId: string) => sealedDirs.get(pointId) as string,
    expectation: {
      batchKind: options.batchKind,
      executionProfile: options.batchKind === "FULL_RESTART_RETRY"
        ? "MPS_W1_FULL_RESTART_RETRY"
        : options.workerCount === 2 ? "MPS_W2_FIRST_PASS" : "MPS_W1_FIRST_PASS",
      schemaVersion: options.batchKind === "FULL_RESTART_RETRY"
        ? 5
        : options.workerCount === 2 ? 4 : 6,
      workerCount: options.workerCount,
      selectedPointIds: options.points,
      projection,
    },
  };
}

describe("assertCampaignBatchEvidence", () => {
  test("accepts the W2 first-pass batch: two workers, four selected points, one attempt each", () => {
    const { root, expectation } = scenario({
      batchId: "b-w2", batchKind: "FIRST_PASS", points: ["p1", "p2", "p3", "p4"],
      workerCount: 2, projectionCleanup: true,
    });
    expect(() => assertCampaignBatchEvidence(readCampaignBatchEvidence(root), expectation))
      .not.toThrow();
  });

  test("accepts the W1 first-pass batch: one worker runs the whole selection sequentially", () => {
    const { root, expectation } = scenario({
      batchId: "b-w1", batchKind: "FIRST_PASS", points: ["p1", "p2", "p3", "p4"],
      workerCount: 1,
    });
    expect(() => assertCampaignBatchEvidence(readCampaignBatchEvidence(root), expectation))
      .not.toThrow();
  });

  test("accepts the single-point retry batch only for the one failed point", () => {
    const { root, expectation } = scenario({
      batchId: "retry-001", batchKind: "FULL_RESTART_RETRY", points: ["p2"], workerCount: 1,
    });
    expect(() => assertCampaignBatchEvidence(readCampaignBatchEvidence(root), expectation))
      .not.toThrow();
  });

  test("rejects a commit for a point that was not selected", () => {
    const { root, expectation } = scenario({
      batchId: "b-w2", batchKind: "FIRST_PASS", points: ["p1", "p2", "p3", "p4"],
      workerCount: 2, extraCommits: ["p5"],
    });
    expect(() => assertCampaignBatchEvidence(readCampaignBatchEvidence(root), expectation))
      .toThrow(/SELECTED_ONLY_EVIDENCE_INVALID/);
  });

  test("rejects a selected point that has no committed evidence", () => {
    const { root, expectation } = scenario({
      batchId: "b-w1", batchKind: "FIRST_PASS", points: ["p1", "p2", "p3"], workerCount: 1,
      commits: ["p1", "p2"],
    });
    expect(() => assertCampaignBatchEvidence(readCampaignBatchEvidence(root), expectation))
      .toThrow(/SELECTED_ONLY_EVIDENCE_INVALID/);
  });

  test("rejects a batch manifest that claims a different selection than the expectation", () => {
    const { root, expectation } = scenario({
      batchId: "b-w1", batchKind: "FIRST_PASS", points: ["p1", "p2"], workerCount: 1,
    });
    const manifestPath = join(root, "batch_manifest.json");
    const manifest = JSON.parse(readFileSync(manifestPath, "utf-8"));
    manifest.selected_point_ids = ["p1", "p2", "p3", "p4"];
    writeFileSync(manifestPath, JSON.stringify(manifest));
    expect(() => assertCampaignBatchEvidence(readCampaignBatchEvidence(root), expectation))
      .toThrow(/SELECTED_ONLY_EVIDENCE_INVALID/);
  });

  test("rejects a watermark that does not name the committed frame", () => {
    const mismatched = scenario({
      batchId: "b-w2", batchKind: "FIRST_PASS", points: ["p1", "p2"], workerCount: 2,
      watermark: { event_sha256: "c".repeat(64) },
    });
    expect(() => assertCampaignBatchEvidence(
      readCampaignBatchEvidence(mismatched.root), mismatched.expectation))
      .toThrow(/SEQUENCE_WATERMARK_INVALID/);

    const beyond = scenario({
      batchId: "b-w2", batchKind: "FIRST_PASS", points: ["p1", "p2"], workerCount: 2,
      watermark: { sequence: 99 },
    });
    expect(() => assertCampaignBatchEvidence(
      readCampaignBatchEvidence(beyond.root), beyond.expectation))
      .toThrow(/SEQUENCE_WATERMARK_INVALID/);

    const missing = scenario({
      batchId: "b-w2", batchKind: "FIRST_PASS", points: ["p1", "p2"], workerCount: 2,
      watermark: null,
    });
    expect(() => assertCampaignBatchEvidence(
      readCampaignBatchEvidence(missing.root), missing.expectation))
      .toThrow(/SEQUENCE_WATERMARK_INVALID/);
  });

  test("rejects a missing or tampered physical evidence file", () => {
    const removed = scenario({
      batchId: "b-w1", batchKind: "FIRST_PASS", points: ["p1"], workerCount: 1,
    });
    rmSync(join(removed.sealedFor("p1"), "numeric", "physical.json"));
    expect(() => assertCampaignBatchEvidence(
      readCampaignBatchEvidence(removed.root), removed.expectation))
      .toThrow(/PHYSICAL_EVIDENCE_INVALID/);

    const tampered = scenario({
      batchId: "b-w1", batchKind: "FIRST_PASS", points: ["p1"], workerCount: 1,
    });
    writeFileSync(join(tampered.sealedFor("p1"), "numeric", "physical.json"), "{}");
    expect(() => assertCampaignBatchEvidence(
      readCampaignBatchEvidence(tampered.root), tampered.expectation))
      .toThrow(/PHYSICAL_EVIDENCE_INVALID/);
  });

  test("rejects a batch that did not complete its cleanup", () => {
    const { root, expectation } = scenario({
      batchId: "b-w2", batchKind: "FIRST_PASS", points: ["p1", "p2"], workerCount: 2,
      projectionCleanup: false,
    });
    const cleanupPath = join(root, "cleanup-gates.json");
    const cleanup = JSON.parse(readFileSync(cleanupPath, "utf-8"));
    cleanup.batch_cleanup_complete = false;
    writeFileSync(cleanupPath, JSON.stringify(cleanup));
    expect(() => assertCampaignBatchEvidence(readCampaignBatchEvidence(root), expectation))
      .toThrow(/CLEANUP_INCOMPLETE/);
  });

  test("the physical evidence set is the sealed inventory the verifier guarantees", () => {
    expect([...PHYSICAL_EVIDENCE_FILES]).toEqual([
      "workspace_identity.json",
      "attempt-result.json",
      "initial-rgb.png",
      "perception/input/rgb.npy",
      "pose_accepted.json",
      "numeric/depth.json",
      "numeric/tf.json",
      "numeric/physical.json",
      "terminal-rgb.png",
    ]);
  });
});

describe("assertRoutingClaim", () => {
  const expectation: CampaignBatchExpectation = {
    batchKind: "FIRST_PASS",
    executionProfile: "MPS_W1_FIRST_PASS",
    schemaVersion: 6,
    workerCount: 1,
    selectedPointIds: ["p1", "p2", "p3", "p4"],
  };

  test("accepts the receipt that resolved the claimed profile from real bytes", () => {
    expect(() => assertRoutingClaim({
      execution_profile: "MPS_W1_FIRST_PASS",
      execution_schema_version: 6,
      execution_batch_kind: "FIRST_PASS",
      admitted: true,
    }, expectation)).not.toThrow();
  });

  test("rejects a receipt for a different profile, schema or batch kind", () => {
    expect(() => assertRoutingClaim({
      execution_profile: "MPS_W2_FIRST_PASS", execution_schema_version: 4,
      execution_batch_kind: "FIRST_PASS", admitted: true,
    }, expectation)).toThrow(/ROUTING_CLAIM_INVALID/);
    expect(() => assertRoutingClaim({
      execution_profile: "MPS_W1_FIRST_PASS", execution_schema_version: 5,
      execution_batch_kind: "FIRST_PASS", admitted: true,
    }, expectation)).toThrow(/ROUTING_CLAIM_INVALID/);
    expect(() => assertRoutingClaim({
      execution_profile: "MPS_W1_FIRST_PASS", execution_schema_version: 6,
      execution_batch_kind: "FULL_RESTART_RETRY", admitted: true,
    }, expectation)).toThrow(/ROUTING_CLAIM_INVALID/);
  });

  test("rejects a receipt with no routing claim and a refused receipt", () => {
    expect(() => assertRoutingClaim({ admitted: true }, expectation))
      .toThrow(/ROUTING_CLAIM_INVALID/);
    expect(() => assertRoutingClaim({ admitted: false, reason_codes: ["EXECUTION_PROFILE_REQUIRED"] }, expectation))
      .toThrow(/ROUTING_CLAIM_INVALID/);
  });
});
