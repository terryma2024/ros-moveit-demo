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
import {
  mkdirSync, mkdtempSync, readdirSync, readFileSync, realpathSync, rmSync, unlinkSync, writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join, relative } from "node:path";

import { afterEach, describe, expect, test } from "vitest";

import {
  PHYSICAL_EVIDENCE_FILES,
  assertCampaignBatchEvidence,
  assertRoutingClaim,
  campaignBatchLayout,
  committedAttempts,
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

// ---------------------------------------------------------------------------------------------
// The macOS composed campaign layout: `journal/` (coordinator segments), `selection-binding.json`,
// `points/`, `point-results/`, the per-attempt station trees, the lease/ack/result documents and
// `campaign-result.json`. The Linux layout above and this one share no manifest, no sealed tree and
// no cleanup document, so the verifier has to pick the branch from the batch's own bytes.
// ---------------------------------------------------------------------------------------------

const MACOS_DYNAMIC_SCHEMA = "so101-dynamic-mujoco-execute-v1";

type MacosOptions = {
  batchId: string;
  batchKind: "FIRST_PASS" | "FULL_RESTART_RETRY";
  points: string[];
  workerCount: number;
  executionProfile: string;
  schemaVersion: number;
  /** Selected points whose committed result document is never written. */
  committed?: string[];
  /** Points outside the selection that were committed anyway. */
  extraPoints?: string[];
  /** A selected point the journal commits a second time. */
  duplicateCommit?: string;
  /** A committed result document the journal never commits at all. */
  orphanPointResult?: string;
  /** Coordinator epochs the journal is split into; each segment header chains onto the last frame. */
  segments?: number;
  /** Published watermark overrides; `null` omits the watermark document. */
  watermark?: { sequence?: number; event_sha256?: string; writer_epoch?: number } | null;
  /** The frame index whose `prev_frame_sha256` no longer names its predecessor. */
  breakChainAt?: number;
  cleanupComplete?: boolean;
  stationClear?: boolean;
  /** How the point result's recorded digests relate to the bytes on disk. */
  evidenceDigest?: "MATCH" | "MISMATCH";
  dynamicDigest?: "MATCH" | "MISMATCH";
  /** Write bytes into the dynamic manifest after its digest was recorded. */
  tamperDynamic?: boolean;
  /** Remove one physical fact before the digest is recorded. */
  stripDynamic?: "NONE" | "PUBLISHER_SEQUENCE" | "SIMULATION_STEP" | "CUP_POSE"
    | "RELEASE_MARKER" | "SCENE_READBACK";
  /** Record `physical_evidence: false` even though the dynamic manifest exists. */
  physicalFlag?: boolean;
  /** Never write the dynamic manifest at all (a PASSED point without physical evidence). */
  omitDynamic?: boolean;
  /** A file the evidence inventory names, matched by path suffix, is deleted after sealing. */
  removeArtifact?: string;
  /** Record a lease whose `selection_sha256` is not the binding's. */
  leaseSelectionMismatch?: boolean;
  /** Rewrite a worker result after its digest was recorded. */
  tamperWorkerResult?: boolean;
  /**
   * Write the nested binding in the vocabulary the campaign's `FULL_RESTART_RETRY` composition
   * emits: the catalog it was selected from as `original_catalog_sha256`, and its one point as
   * `point` instead of `points`/`selected_point_ids`.
   */
  retryBinding?: boolean;
  /** The last word on the nested binding document, for the refusal cases. */
  bindingMutation?: (binding: Record<string, any>) => void;
};

type MacosScenario = {
  root: string;
  expectation: CampaignBatchExpectation;
  selected: string[];
  pointResultPath: (pointId: string) => string;
  dynamicPath: (pointId: string) => string;
  stationRoot: (pointId: string) => string;
};

function macosDynamicManifest(
  pointId: string, workerId: string, attemptId: string, campaignId: string, index: number,
  options: MacosOptions,
): Record<string, any> {
  const sample: Record<string, any> = {
    reset_epoch: 1,
    cup_position_world_m: [0.02, -0.28, 0.1648],
    cup_orientation_world_xyzw: [0, 0, 0, 1],
    cup_linear_velocity_world_m_s: [0, 0, 0],
    cup_angular_velocity_world_rad_s: [0, 0, 0],
    left_contact_count: 0,
    right_contact_count: 0,
    maximum_normal_force_n: 0.2328,
    table_contact: true,
    simulation_step: 32411 + index,
    publisher_sequence: 7429 + index,
  };
  const document: Record<string, any> = {
    schema: MACOS_DYNAMIC_SCHEMA,
    simulation_session_id: `${campaignId}-${workerId}-${attemptId}`,
    status: "DONE",
    current_state: "DONE",
    transition_count: 19,
    state_trace: ["IDLE", "PREPARE_OPEN_GRIPPER", "DONE"],
    state_events: [{ state: "DONE", before: sample, after: sample }],
    final_samples: [sample],
    release_marker_sequence: 7407 + index,
    planning_scene_readback: {
      attached_object_ids: [],
      world_primitive_counts: { pedestal: 1, table: 1, plastic_cup: 13 },
    },
    input_cup_pose_world: [0.02, -0.28, 0.1648, 0, 0, 0, 1],
    expected_reset_epoch: 1,
  };
  if (options.stripDynamic === "PUBLISHER_SEQUENCE") delete sample.publisher_sequence;
  if (options.stripDynamic === "SIMULATION_STEP") delete sample.simulation_step;
  if (options.stripDynamic === "CUP_POSE") delete sample.cup_position_world_m;
  if (options.stripDynamic === "RELEASE_MARKER") document.release_marker_sequence = null;
  if (options.stripDynamic === "SCENE_READBACK") document.planning_scene_readback = {};
  return document;
}

/** The macOS batch as the composed campaign writes it, with one knob per refusal under test. */
function macosScenario(options: MacosOptions): MacosScenario {
  const root = mkdtempSync(join(tmpdir(), "uq-macos-campaign-"));
  roots.push(root);
  const selected = [...options.points].sort();
  const committed = new Set(options.committed ?? selected);
  const extra = [...(options.extraPoints ?? [])].sort();
  const campaignId = `cand-${options.batchId}`;
  const workers = Array.from({ length: options.workerCount }, (_value, index) => `w${index + 1}`);
  const pointSha = (pointId: string) => sha256(`point:${pointId}`);
  const selectionSha = sha256(canonical({
    batch_id: options.batchId,
    selected: selected.map((pointId) => [pointId, pointSha(pointId)]),
  }));

  mkdirSync(join(root, "points"), { recursive: true });
  const stations = new Map<string, { station: string; pick: string; dynamic: string }>();
  const documents = new Map<string, Record<string, any>>();
  const events: Array<{ type: string; payload: Record<string, any> }> = [
    { type: "CAMPAIGN_STARTED", payload: { batch_id: options.batchId, campaign_id: campaignId } },
  ];
  const stationReadbacks: Array<{ station_root: string; clear: boolean; matches: unknown[] }> = [];
  const commitOrder: string[] = [];

  const build = (pointId: string, index: number) => {
    const workerId = workers[index % workers.length];
    const attemptId = `${pointId}-attempt-${index + 1}`;
    const station = join(root, `${workerId}-station`, attemptId);
    const pick = join(station, "pick");
    const pointDir = join(
      pick, "batches", options.batchId, "points",
      `${String(index + 1).padStart(2, "0")}-${pointId}`);
    const dynamicPath = join(pointDir, "dynamic", "dynamic-execute-manifest.json");
    mkdirSync(join(pointDir, "dynamic"), { recursive: true });
    mkdirSync(join(root, "points"), { recursive: true });
    const inputPath = join(root, "points", `${pointId}.yaml`);
    writeFileSync(inputPath, `point_id: ${pointId}\nposition_xyz_m: [0.0, 0.0, 0.165]\n`);
    const inputSha = sha256(readFileSync(inputPath));

    // The artifacts the point result's own inventory seals, relative to the station's pick root.
    const artifacts: Array<{ path: string; bytes: Buffer }> = [];
    const add = (path: string, bytes: Buffer) => {
      mkdirSync(join(path, ".."), { recursive: true });
      writeFileSync(path, bytes);
      artifacts.push({ path, bytes });
    };
    add(join(pick, "resets", `${pointId}-1790039920813193000.json`),
      Buffer.from(JSON.stringify({ point_id: pointId, reset_epoch: 1 })));
    if (!options.omitDynamic) {
      const document = macosDynamicManifest(
        pointId, workerId, attemptId, campaignId, index, options);
      add(dynamicPath, Buffer.from(`${JSON.stringify(document, null, 2)}\n`));
      if (options.tamperDynamic) {
        writeFileSync(dynamicPath, `${JSON.stringify(document, null, 2)}\n# tampered\n`);
      }
    }
    add(join(pointDir, "rgb.png"), Buffer.from(`rgb-${pointId}`));
    add(join(pointDir, "viewer.png"), Buffer.from(`viewer-${pointId}`));
    add(join(pointDir, "dynamic-consumer.log"), Buffer.from(`log-${pointId}\n`));
    const inventory = artifacts.map((entry) => ({
      relative_path: relative(pick, entry.path),
      sha256: sha256(entry.bytes),
      byte_size: entry.bytes.length,
      media_type: "application/json",
      producing_process: "workflow",
    }));
    if (options.removeArtifact) {
      const named = inventory.find((entry) => entry.relative_path.endsWith(options.removeArtifact!));
      if (!named) throw new Error(`TEST_FIXTURE_ARTIFACT_MISSING: ${options.removeArtifact}`);
      unlinkSync(join(pick, named.relative_path));
    }
    const innerPath = join(pointDir, "point-result.json");
    writeFileSync(innerPath, `${JSON.stringify({
      schema_version: 1,
      id: pointId,
      manifest_path: "point-result.json",
      status: "SUCCEEDED",
      failure_code: null,
      reachability_status: "REACHABLE",
      reset_epoch: 1,
      artifacts: inventory,
    }, null, 2)}\n`);

    const workerResultPath = join(root, `${workerId}-result-${attemptId}.json`);
    const workerResultBytes = Buffer.from(`${JSON.stringify({
      worker_id: workerId, pid: 54700 + index, batch_kind: options.batchKind,
      execution_profile: options.executionProfile,
      station_record: { ready: { ready: true, exit_code: 0 } },
      pick_place: { point_id: pointId, attempt_id: attemptId, exit_code: 0 },
    }, null, 2)}\n`);
    writeFileSync(workerResultPath, workerResultBytes);
    const workerResultSha = sha256(workerResultBytes);
    if (options.tamperWorkerResult) {
      writeFileSync(workerResultPath, "{}\n");
    }
    writeFileSync(join(root, `${workerId}-ack-${attemptId}.json`),
      `${JSON.stringify({ pid: 59980 + index, pgid: 59980 + index, argv: ["worker", workerId], station: true })}\n`);

    const evidenceBytes = readFileSync(innerPath);
    const dynamicBytes = options.omitDynamic ? null : readFileSync(dynamicPath);
    const document: Record<string, any> = {
      schema_version: 1,
      point_id: pointId,
      attempt_id: attemptId,
      outcome: "PASSED",
      committed: committed.has(pointId),
      lease_identity: [campaignId, options.batchId, pointId, attemptId, 1, workerId],
      lease_sha256: sha256(`lease:${pointId}`),
      worker_id: workerId,
      slot_id: `slot-${index % options.workerCount}`,
      generation: 1,
      points_path: inputPath,
      points_sha256: inputSha,
      evidence_manifest_relative_path: relative(root, innerPath),
      evidence_manifest_sha256: options.evidenceDigest === "MISMATCH"
        ? "f".repeat(64) : sha256(evidenceBytes),
      dynamic_manifest_relative_path: options.omitDynamic ? null : relative(root, dynamicPath),
      dynamic_manifest_sha256: options.omitDynamic
        ? null
        : options.dynamicDigest === "MISMATCH" ? "f".repeat(64) : sha256(dynamicBytes as Buffer),
      physical_evidence: options.omitDynamic ? false : (options.physicalFlag ?? true),
      station_ready: true,
      moveit_executed: true,
      cleanup_owned: true,
      failure_code: null,
      batch_exit_code: 0,
      worker_result_path: workerResultPath,
      worker_result_sha256: workerResultSha,
      worker_pid: 54700 + index,
      released: "EXITED",
      station_readback: {
        clear: options.stationClear ?? true,
        matches: [],
        station_root: station,
      },
      execution_result: null,
    };
    mkdirSync(join(root, "point-results"), { recursive: true });
    if (committed.has(pointId)) {
      writeFileSync(join(root, "point-results", `${pointId}.json`),
        `${JSON.stringify(document, null, 2)}\n`);
    }
    documents.set(pointId, document);
    stations.set(pointId, { station, pick, dynamic: dynamicPath });
    stationReadbacks.push({
      station_root: station,
      clear: options.stationClear ?? true,
      matches: [],
    });
    writeFileSync(join(root, `${workerId}-lease-${String(index + 1).padStart(2, "0")}.json`),
      JSON.stringify({
        worker_id: workerId, slot_id: `slot-${index % options.workerCount}`,
        batch_id: options.batchId, campaign_id: campaignId,
        execution_profile: options.executionProfile, batch_kind: options.batchKind,
        schema_version: options.schemaVersion, coordinator_epoch: 1, worker_generation: 1,
        lease_generation: 1, reset_epoch: "epoch-1", point_id: pointId, model_id: "yolo",
        attempt_id: attemptId, point_sha256: pointSha(pointId),
        points_path: inputPath, points_sha256: inputSha,
        selection_sha256: options.leaseSelectionMismatch ? "e".repeat(64) : selectionSha,
        station_root: station, snapshot_path: join(root, `${workerId}-frame.npy`),
      }, null, 2));
    if (committed.has(pointId)) {
      commitOrder.push(pointId);
      events.push(
        {
          type: "POINT_LEASED",
          payload: {
            point_id: pointId, attempt_id: attemptId, worker_id: workerId,
            slot_id: document.slot_id, generation: 1, lease_sha256: document.lease_sha256,
            points_path: inputPath, points_sha256: inputSha, selection_sha256: selectionSha,
          },
        },
        {
          type: "WORKER_REGISTERED",
          payload: {
            point_id: pointId, attempt_id: attemptId, worker_id: workerId,
            slot_id: document.slot_id, generation: 1, pid: document.worker_pid, status: "ACTIVE",
          },
        },
        {
          type: "ATTEMPT_STARTED",
          payload: {
            point_id: pointId, attempt_id: attemptId, worker_id: workerId,
            slot_id: document.slot_id, generation: 1,
          },
        },
        {
          type: "RESULT_COMMITTED",
          payload: {
            point_id: pointId, attempt_id: attemptId, worker_id: workerId,
            slot_id: document.slot_id, generation: 1, outcome: "PASSED",
            evidence_manifest_sha256: document.evidence_manifest_sha256,
            dynamic_manifest_sha256: document.dynamic_manifest_sha256,
            failure_code: null, station_ready: true, moveit_executed: true, cleanup_owned: true,
          },
        },
        {
          type: "POINT_TERMINAL",
          payload: {
            point_id: pointId, attempt_id: attemptId, outcome: "PASSED",
            state: "COMMITTED", result_sha256: sha256(`terminal:${pointId}`),
          },
        },
      );
    }
  };

  selected.forEach((pointId, index) => build(pointId, index));
  extra.forEach((pointId, index) => build(pointId, selected.length + index));
  if (options.orphanPointResult) {
    const pointId = options.orphanPointResult;
    const template = documents.get(selected[0]) as Record<string, any>;
    writeFileSync(join(root, "point-results", `${pointId}.json`), `${JSON.stringify({
      ...template, point_id: pointId, attempt_id: `${pointId}-attempt-9`,
    }, null, 2)}\n`);
  }
  if (options.duplicateCommit) {
    const pointId = options.duplicateCommit;
    const document = documents.get(pointId) as Record<string, any>;
    events.push({
      type: "RESULT_COMMITTED",
      payload: {
        point_id: pointId, attempt_id: document.attempt_id, worker_id: document.worker_id,
        slot_id: document.slot_id, generation: 1, outcome: "PASSED",
        evidence_manifest_sha256: document.evidence_manifest_sha256,
        dynamic_manifest_sha256: document.dynamic_manifest_sha256,
        failure_code: null, station_ready: true, moveit_executed: true, cleanup_owned: true,
      },
    });
  }
  events.push({ type: "BATCH_TERMINAL", payload: { outcome: `${options.batchId} DONE` } });
  events.push({ type: "CLEANUP_COMMITTED", payload: { cleanup_complete: true } });

  // The journal: segment headers carry no sequence and chain the coordinator epochs together.
  const segments = Math.max(1, options.segments ?? 1);
  const perSegment = Math.ceil(events.length / segments);
  const journalRoot = join(root, "journal");
  mkdirSync(join(journalRoot, "events"), { recursive: true });
  writeFileSync(join(journalRoot, "coordinator_epoch.json"),
    JSON.stringify({ batch_id: options.batchId, coordinator_epoch: segments }));
  writeFileSync(join(journalRoot, "events", "segment-00000000000000000001.journal"), "");
  let terminal = "0".repeat(64);
  let sequence = 0;
  let frameIndex = 0;
  let terminalEpoch = 1;
  const lastWriters: Array<{ name: string; bytes: Buffer }> = [];
  for (let epoch = 1; epoch <= segments; epoch += 1) {
    const frames: Buffer[] = [];
    const header = frame({
      kind: "segment", batch_id: options.batchId, coordinator_epoch: epoch,
      prev_segment_sha256: terminal, prev_tail_sha256: null,
    });
    frames.push(header);
    terminal = sha256(header);
    if (options.breakChainAt === frameIndex) {
      // deliberately re-encode with a predecessor that is not the frame before it
      frames[frames.length - 1] = frame({
        kind: "segment", batch_id: options.batchId, coordinator_epoch: epoch,
        prev_segment_sha256: "d".repeat(64),
        prev_tail_sha256: null,
      });
      terminal = sha256(frames[frames.length - 1]);
    }
    frameIndex += 1;
    for (const event of events.slice((epoch - 1) * perSegment, epoch * perSegment)) {
      sequence += 1;
      const document = {
        kind: "event", batch_id: options.batchId, type: event.type,
        idempotency_key: `${options.batchId}/${event.type}/${sequence}`,
        payload: event.payload, coordinator_epoch: epoch,
        sequence, prev_frame_sha256: terminal,
      };
      let bytes = frame(document);
      if (options.breakChainAt === frameIndex) {
        bytes = frame({ ...document, prev_frame_sha256: "d".repeat(64) });
      }
      frames.push(bytes);
      terminal = sha256(bytes);
      terminalEpoch = epoch;
      frameIndex += 1;
    }
    const name = `segment-${String(epoch).padStart(20, "0")}.journal`;
    const bytes = Buffer.concat(frames);
    writeFileSync(join(journalRoot, "events", name), bytes);
    lastWriters.push({ name, bytes });
  }
  const terminalSequence = sequence;
  const firstEventSha = (() => {
    const data = lastWriters[0].bytes;
    let offset = 0;
    while (offset < data.length) {
      const length = Number(data.readBigUInt64BE(offset));
      const end = offset + 73 + length;
      const document = JSON.parse(data.subarray(offset + 72, end - 1).toString("utf-8"));
      if (document.sequence === 1) return sha256(data.subarray(offset, end));
      offset = end;
    }
    throw new Error("TEST_FIXTURE_NO_FIRST_EVENT");
  })();
  const lastFrameSha = (() => {
    const data = lastWriters[lastWriters.length - 1].bytes;
    let offset = 0;
    let sha = "";
    while (offset < data.length) {
      const length = Number(data.readBigUInt64BE(offset));
      sha = sha256(data.subarray(offset, offset + 73 + length));
      offset += 73 + length;
    }
    return sha;
  })();
  const published = {
    batch_id: options.batchId, writer_epoch: terminalEpoch, sequence: terminalSequence,
    event_sha256: lastFrameSha,
  };
  const watermark = options.watermark === undefined
    ? published
    : options.watermark === null ? null : { ...published, ...options.watermark };
  if (watermark !== null) {
    writeFileSync(join(journalRoot, "committed-watermark.json"), JSON.stringify(watermark));
  }

  const selectionPoint = (pointId: string) => ({
    point_id: pointId, point_sha256: pointSha(pointId), position_xyz_m: [0.02, -0.28, 0.165],
  });
  const nestedBinding: Record<string, any> = options.retryBinding
    ? {
        batch_id: options.batchId, campaign_id: campaignId, kind: options.batchKind,
        original_catalog_sha256: sha256("catalog"),
        original_selection_sha256: sha256("original-selection"),
        original_result_sha256: sha256("original-result"),
        original_outcome: "FAILED",
        point: selectionPoint(selected[0]),
        config_sha256: sha256("config"),
        runtime_closure_sha256: sha256("closure"),
        selection_sha256: selectionSha,
      }
    : {
        batch_id: options.batchId, campaign_id: campaignId, kind: options.batchKind,
        schema_version: 1, coordinate_frame: "world",
        catalog_sha256: sha256("catalog"), config_sha256: sha256("config"),
        runtime_closure_sha256: sha256("closure"),
        points: selected.map(selectionPoint),
        selected_point_ids: selected, selection_sha256: selectionSha,
      };
  options.bindingMutation?.(nestedBinding);
  const selectionBinding = {
    batch_id: options.batchId,
    binding: nestedBinding,
    campaign_id: campaignId,
    catalog_path: join(root, "catalog.yaml"),
    catalog_sha256: sha256("catalog"),
    config_sha256: sha256("config"),
    runtime_closure_sha256: sha256("closure"),
    schema_version: 1,
    selected_point_ids: selected,
    selection_sha256: selectionSha,
  };
  writeFileSync(join(root, "selection-binding.json"), JSON.stringify(selectionBinding, null, 2));

  const committedIds = [...commitOrder].sort();
  const campaignResult = {
    status: options.workerCount === 2 ? "W2_CAMPAIGN_PASS" : "N1_CAMPAIGN_PASS",
    execution_profile: options.executionProfile,
    route: {
      schema_version: options.schemaVersion,
      execution_profile: options.executionProfile,
      batch_kind: options.batchKind,
      worker_count: options.workerCount,
      module: "so101_demo.cli.macos_w2_campaign",
      config_path: join(root, "route.yaml"),
      config_sha256: sha256("config"),
    },
    selection: {
      kind: options.batchKind, selected_point_ids: selected, selection_sha256: selectionSha,
      catalog_sha256: sha256("catalog"), config_sha256: sha256("config"),
      runtime_closure_sha256: sha256("closure"), document_path: join(root, "selection-binding.json"),
    },
    points: {
      complete: committedIds.length === selected.length
        && extra.length === 0 && !options.duplicateCommit,
      selected_point_ids: selected,
      committed: Object.fromEntries(committedIds.map((pointId) => [pointId, "PASSED"])),
      duplicate_attempts: options.duplicateCommit ? [options.duplicateCommit] : [],
      unselected_attempts: extra,
      unexecuted_point_ids: selected.filter((pointId) => !committed.has(pointId)),
      infrastructure_failures: [],
      missing_physical_evidence: [],
      attempts: committedIds.map((pointId) => documents.get(pointId)),
      workers: [...new Set(committedIds.map(
        (pointId) => (documents.get(pointId) as Record<string, any>).worker_id))].sort(),
      spawns: [],
    },
    cleanup: {
      complete: options.cleanupComplete ?? true,
      stations_clear: options.stationClear ?? true,
      directory_removed: true,
      registry_empty: true,
      workers_reaped: workers.map(() => true),
      stations: stationReadbacks,
    },
    journal: {
      batch_id: options.batchId,
      segment: join(journalRoot, "events", lastWriters[lastWriters.length - 1].name),
      watermark: {
        batch_id: options.batchId, writer_epoch: 1, sequence: 1, event_sha256: firstEventSha,
      },
      // The first watermark names the batch's first committed frame; its epoch is that frame's.
      terminal_watermark: watermark,
    },
    workers: workers.map((workerId) => ({ worker_id: workerId, status: "ACTIVE" })),
    worker_results: [],
    served: { count: selected.length, devices: ["mps"], duplicates_refused: 0 },
    queue: { root: join(root, "queue"), state_path: join(root, "queue", "queue-state.json") },
  };
  writeFileSync(join(root, "campaign-result.json"), JSON.stringify(campaignResult, null, 2));

  mkdirSync(join(root, "queue"), { recursive: true });
  writeFileSync(join(root, "queue", "queue-state.json"), JSON.stringify({
    schema_version: 1,
    batch_id: options.batchId,
    campaign_id: campaignId,
    selected_point_ids: selected,
    selection_sha256: selectionSha,
    active_leases: {},
    abandoned_attempts: [],
    committed_results: Object.fromEntries(committedIds.map((pointId) => {
      const document = documents.get(pointId) as Record<string, any>;
      return [pointId, {
        point_id: pointId, attempt_id: document.attempt_id, outcome: "PASSED",
        evidence_sha256: document.evidence_manifest_sha256,
        result_sha256: sha256(`result:${pointId}`),
      }];
    })),
    slot_generations: {},
  }, null, 2));
  mkdirSync(join(root, "supervisor"), { recursive: true });
  writeFileSync(join(root, "supervisor", "owner-receipt.json"), JSON.stringify({
    campaign_id: campaignId, coordinator_pid: 54689, children: [],
  }));

  return {
    root,
    selected,
    expectation: {
      batchKind: options.batchKind,
      executionProfile: options.executionProfile,
      schemaVersion: options.schemaVersion,
      workerCount: options.workerCount,
      selectedPointIds: selected,
    },
    pointResultPath: (pointId: string) => join(root, "point-results", `${pointId}.json`),
    dynamicPath: (pointId: string) => (stations.get(pointId) as { dynamic: string }).dynamic,
    stationRoot: (pointId: string) => (stations.get(pointId) as { station: string }).station,
  };
}

/**
 * Re-point the batch's own absolute paths at `alias`, keeping every sealed digest valid: only the
 * documents that name paths are rewritten, and a worker result is digest-bound by its point result,
 * so its recorded digest is re-taken afterwards.
 */
function reRootDocuments(root: string, alias: string): void {
  const documents = [
    join(root, "campaign-result.json"),
    ...readdirSync(join(root, "point-results")).map((name) => join(root, "point-results", name)),
    ...readdirSync(root).filter((name) => /-(lease|result)-.*\.json$/.test(name))
      .map((name) => join(root, name)),
  ];
  for (const document of documents) {
    writeFileSync(document, readFileSync(document, "utf8").split(root).join(alias));
  }
  for (const name of readdirSync(join(root, "point-results"))) {
    const path = join(root, "point-results", name);
    const document = JSON.parse(readFileSync(path, "utf-8"));
    document.worker_result_sha256 = sha256(readFileSync(document.worker_result_path));
    writeFileSync(path, `${JSON.stringify(document, null, 2)}\n`);
  }
}

const W2_MACOS: Omit<MacosOptions, "batchId" | "points"> = {
  batchKind: "FIRST_PASS",
  workerCount: 2,
  executionProfile: "MPS_W2_FIRST_PASS",
  schemaVersion: 4,
};

/** The v5 single-point retry route, whose binding names its selection in the retry vocabulary. */
const RETRY_MACOS: Omit<MacosOptions, "batchId" | "points"> = {
  batchKind: "FULL_RESTART_RETRY",
  workerCount: 1,
  executionProfile: "MPS_W1_FULL_RESTART_RETRY",
  schemaVersion: 5,
  retryBinding: true,
};

describe("the macOS composed campaign layout", () => {
  test("accepts the W2 route: segment header skipped, four selected points, one result each", () => {
    const batch = macosScenario({ ...W2_MACOS, batchId: "w2-b001", points: ["p1", "p2", "p3", "p4"] });
    const evidence = readCampaignBatchEvidence(batch.root);
    expect(evidence.layout).toBe("MACOS_COMPOSED");
    // The segment header is the journal's first frame and carries no sequence of its own.
    expect(evidence.events.filter((event) => event.kind === "segment")).toHaveLength(1);
    expect(evidence.events.filter((event) => event.type === "RESULT_COMMITTED")).toHaveLength(4);
    const attempts = committedAttempts(evidence);
    expect(attempts.map((attempt) => attempt.pointId)).toEqual(["p1", "p2", "p3", "p4"]);
    expect(attempts.every((attempt) => attempt.sealedDir.startsWith(batch.root))).toBe(true);
    expect(() => assertCampaignBatchEvidence(evidence, {
      ...batch.expectation,
      projection: {
        batch_id: "w2-b001", batch_cleanup_complete: true, sequence: evidence.watermark?.sequence,
      },
    })).not.toThrow();
  });

  test("accepts the W1 route: one worker runs the whole selection sequentially", () => {
    const batch = macosScenario({
      batchId: "w1-b001", points: ["p1", "p2", "p3", "p4"], batchKind: "FIRST_PASS",
      workerCount: 1, executionProfile: "MPS_W1_FIRST_PASS", schemaVersion: 6,
    });
    expect(() => assertCampaignBatchEvidence(
      readCampaignBatchEvidence(batch.root), batch.expectation)).not.toThrow();
  });

  test("accepts the retry route: a one-point binding in the retry's own vocabulary", () => {
    // RED: the recorded retry batch (`campaign-e94a4b74…/retry-001`) was refused here with
    // `SELECTED_ONLY_EVIDENCE_INVALID`, because its binding names the catalog it was selected from
    // as `original_catalog_sha256` and the one point it executes as `point`, not `points`.
    const batch = macosScenario({
      ...RETRY_MACOS, batchId: "retry-001", points: ["sample_05_near_center"],
    });
    const evidence = readCampaignBatchEvidence(batch.root);
    expect(evidence.layout).toBe("MACOS_COMPOSED");
    expect(() => assertCampaignBatchEvidence(evidence, batch.expectation)).not.toThrow();
  });

  test("rejects a retry binding that names neither selection vocabulary", () => {
    const nameless = macosScenario({
      ...RETRY_MACOS, batchId: "retry-001", points: ["p1"],
      bindingMutation: (binding) => {
        delete binding.point;
      },
    });
    expect(() => assertCampaignBatchEvidence(
      readCampaignBatchEvidence(nameless.root), nameless.expectation))
      .toThrow(/SELECTED_ONLY_EVIDENCE_INVALID: selection points in the selection binding/);

    const catalog = macosScenario({
      ...RETRY_MACOS, batchId: "retry-001", points: ["p1"],
      bindingMutation: (binding) => {
        delete binding.original_catalog_sha256;
      },
    });
    expect(() => assertCampaignBatchEvidence(
      readCampaignBatchEvidence(catalog.root), catalog.expectation))
      .toThrow(/SELECTED_ONLY_EVIDENCE_INVALID: catalog digest in the selection binding/);
  });

  test("rejects a retry binding whose point is not the one the batch's bytes carry", () => {
    // The lease and the single-point input are the batch's own verified bytes: a binding that names
    // another digest, or another point, is not the selection this batch executed.
    const digest = macosScenario({
      ...RETRY_MACOS, batchId: "retry-001", points: ["p1"],
      bindingMutation: (binding) => {
        binding.point.point_sha256 = "f".repeat(64);
      },
    });
    expect(() => assertCampaignBatchEvidence(
      readCampaignBatchEvidence(digest.root), digest.expectation))
      .toThrow(/SELECTED_ONLY_EVIDENCE_INVALID: w1-lease-01\.json is not bound to the selection/);

    const point = macosScenario({
      ...RETRY_MACOS, batchId: "retry-001", points: ["p1"],
      bindingMutation: (binding) => {
        binding.point.point_id = "p9";
      },
    });
    expect(() => assertCampaignBatchEvidence(
      readCampaignBatchEvidence(point.root), point.expectation))
      .toThrow(/SELECTED_ONLY_EVIDENCE_INVALID: selection binding for retry-001/);
  });

  test("accepts a restarted coordinator: the second segment chains onto the first", () => {
    const batch = macosScenario({
      batchId: "w2-b002", points: ["p1", "p2"], ...W2_MACOS, segments: 2,
    });
    const evidence = readCampaignBatchEvidence(batch.root);
    expect(evidence.events.filter((event) => event.kind === "segment")).toHaveLength(2);
    expect(() => assertCampaignBatchEvidence(evidence, batch.expectation)).not.toThrow();
  });

  test("refuses a batch that matches neither layout, and one that matches both", () => {
    const empty = mkdtempSync(join(tmpdir(), "uq-campaign-shape-"));
    roots.push(empty);
    writeFileSync(join(empty, "campaign.log"), "not a batch\n");
    expect(() => readCampaignBatchEvidence(empty)).toThrow(/CAMPAIGN_EVIDENCE_INVALID/);

    const linux = scenario({
      batchId: "b-w2", batchKind: "FIRST_PASS", points: ["p1"], workerCount: 2,
    });
    expect(campaignBatchLayout(linux.root)).toBe("LINUX_FIXED");
    const macos = macosScenario({ ...W2_MACOS, batchId: "w2-b001", points: ["p1"] });
    expect(campaignBatchLayout(macos.root)).toBe("MACOS_COMPOSED");
    writeFileSync(join(macos.root, "batch_manifest.json"), JSON.stringify({ batch_id: "w2-b001" }));
    expect(() => readCampaignBatchEvidence(macos.root)).toThrow(/CAMPAIGN_EVIDENCE_INVALID/);
  });

  test("accepts a batch whose documents name it through a physical alias of the root", () => {
    // Darwin's /var and /tmp are symlinks: a service that resolved its evidence root records
    // /private/... while the caller inspected /.... That is one batch, not two.
    const batch = macosScenario({ ...W2_MACOS, batchId: "w2-b001", points: ["p1", "p2"] });
    const alias = realpathSync(batch.root);
    reRootDocuments(batch.root, alias);
    expect(() => assertCampaignBatchEvidence(
      readCampaignBatchEvidence(batch.root), batch.expectation)).not.toThrow();
  });

  test("rejects a selected point whose committed result document is missing", () => {
    const batch = macosScenario({
      ...W2_MACOS, batchId: "w2-b001", points: ["p1", "p2", "p3"], committed: ["p1", "p2"],
    });
    expect(() => assertCampaignBatchEvidence(
      readCampaignBatchEvidence(batch.root), batch.expectation))
      .toThrow(/SELECTED_ONLY_EVIDENCE_INVALID/);
  });

  test("rejects a point committed twice and a point outside the selection", () => {
    const duplicate = macosScenario({
      ...W2_MACOS, batchId: "w2-b001", points: ["p1", "p2"], duplicateCommit: "p1",
    });
    expect(() => assertCampaignBatchEvidence(
      readCampaignBatchEvidence(duplicate.root), duplicate.expectation))
      .toThrow(/SELECTED_ONLY_EVIDENCE_INVALID/);

    const unselected = macosScenario({
      ...W2_MACOS, batchId: "w2-b001", points: ["p1", "p2"], extraPoints: ["p9"],
    });
    expect(() => assertCampaignBatchEvidence(
      readCampaignBatchEvidence(unselected.root), unselected.expectation))
      .toThrow(/SELECTED_ONLY_EVIDENCE_INVALID/);

    // A committed document the journal never committed is not a committed attempt either.
    const orphan = macosScenario({
      ...W2_MACOS, batchId: "w2-b001", points: ["p1", "p2"], orphanPointResult: "p9",
    });
    expect(() => assertCampaignBatchEvidence(
      readCampaignBatchEvidence(orphan.root), orphan.expectation))
      .toThrow(/SELECTED_ONLY_EVIDENCE_INVALID/);
  });

  test("rejects a batch whose own route does not carry the claimed profile", () => {
    const batch = macosScenario({ ...W2_MACOS, batchId: "w2-b001", points: ["p1", "p2"] });
    expect(() => assertCampaignBatchEvidence(readCampaignBatchEvidence(batch.root), {
      ...batch.expectation, workerCount: 1,
    })).toThrow(/SELECTED_ONLY_EVIDENCE_INVALID/);
    expect(() => assertCampaignBatchEvidence(readCampaignBatchEvidence(batch.root), {
      ...batch.expectation, executionProfile: "MPS_W1_FIRST_PASS",
    })).toThrow(/SELECTED_ONLY_EVIDENCE_INVALID/);
    expect(() => assertCampaignBatchEvidence(readCampaignBatchEvidence(batch.root), {
      ...batch.expectation, selectedPointIds: ["p1"],
    })).toThrow(/SELECTED_ONLY_EVIDENCE_INVALID/);
  });

  test("rejects a lease that is not bound to the selection or to the single-point input", () => {
    const unbound = macosScenario({
      ...W2_MACOS, batchId: "w2-b001", points: ["p1", "p2"], leaseSelectionMismatch: true,
    });
    expect(() => assertCampaignBatchEvidence(
      readCampaignBatchEvidence(unbound.root), unbound.expectation))
      .toThrow(/SELECTED_ONLY_EVIDENCE_INVALID/);

    const input = macosScenario({ ...W2_MACOS, batchId: "w2-b001", points: ["p1", "p2"] });
    writeFileSync(join(input.root, "points", "p1.yaml"), "point_id: p1\ntampered: true\n");
    expect(() => assertCampaignBatchEvidence(
      readCampaignBatchEvidence(input.root), input.expectation))
      .toThrow(/SELECTED_ONLY_EVIDENCE_INVALID/);
  });

  test("rejects a commit whose worker result no longer matches its digest", () => {
    const batch = macosScenario({
      ...W2_MACOS, batchId: "w2-b001", points: ["p1", "p2"], tamperWorkerResult: true,
    });
    expect(() => assertCampaignBatchEvidence(
      readCampaignBatchEvidence(batch.root), batch.expectation))
      .toThrow(/SELECTED_ONLY_EVIDENCE_INVALID/);
  });

  test("rejects a missing, mismatched or unreachable committed watermark", () => {
    const missing = macosScenario({
      ...W2_MACOS, batchId: "w2-b001", points: ["p1", "p2"], watermark: null,
    });
    expect(() => assertCampaignBatchEvidence(
      readCampaignBatchEvidence(missing.root), missing.expectation))
      .toThrow(/SEQUENCE_WATERMARK_INVALID/);

    const mismatched = macosScenario({
      ...W2_MACOS, batchId: "w2-b001", points: ["p1", "p2"],
      watermark: { event_sha256: "c".repeat(64) },
    });
    expect(() => assertCampaignBatchEvidence(
      readCampaignBatchEvidence(mismatched.root), mismatched.expectation))
      .toThrow(/SEQUENCE_WATERMARK_INVALID/);

    const beyond = macosScenario({
      ...W2_MACOS, batchId: "w2-b001", points: ["p1", "p2"], watermark: { sequence: 99 },
    });
    expect(() => assertCampaignBatchEvidence(
      readCampaignBatchEvidence(beyond.root), beyond.expectation))
      .toThrow(/SEQUENCE_WATERMARK_INVALID/);

    const wrongEpoch = macosScenario({
      ...W2_MACOS, batchId: "w2-b001", points: ["p1", "p2"], watermark: { writer_epoch: 7 },
    });
    expect(() => assertCampaignBatchEvidence(
      readCampaignBatchEvidence(wrongEpoch.root), wrongEpoch.expectation))
      .toThrow(/SEQUENCE_WATERMARK_INVALID/);
  });

  test("rejects a journal frame that no longer names its predecessor", () => {
    const batch = macosScenario({
      ...W2_MACOS, batchId: "w2-b001", points: ["p1", "p2"], breakChainAt: 3,
    });
    expect(() => assertCampaignBatchEvidence(
      readCampaignBatchEvidence(batch.root), batch.expectation))
      .toThrow(/SEQUENCE_WATERMARK_INVALID/);
  });

  test("rejects a tampered dynamic manifest and a wrong recorded digest", () => {
    const tampered = macosScenario({
      ...W2_MACOS, batchId: "w2-b001", points: ["p1", "p2"], tamperDynamic: true,
    });
    expect(() => assertCampaignBatchEvidence(
      readCampaignBatchEvidence(tampered.root), tampered.expectation))
      .toThrow(/PHYSICAL_EVIDENCE_INVALID/);

    const wrong = macosScenario({
      ...W2_MACOS, batchId: "w2-b001", points: ["p1", "p2"], dynamicDigest: "MISMATCH",
    });
    expect(() => assertCampaignBatchEvidence(
      readCampaignBatchEvidence(wrong.root), wrong.expectation))
      .toThrow(/PHYSICAL_EVIDENCE_INVALID/);

    const evidence = macosScenario({
      ...W2_MACOS, batchId: "w2-b001", points: ["p1", "p2"], evidenceDigest: "MISMATCH",
    });
    expect(() => assertCampaignBatchEvidence(
      readCampaignBatchEvidence(evidence.root), evidence.expectation))
      .toThrow(/PHYSICAL_EVIDENCE_INVALID/);
  });

  test("rejects a dynamic manifest without its physical facts", () => {
    for (const stripDynamic of [
      "PUBLISHER_SEQUENCE", "SIMULATION_STEP", "CUP_POSE", "RELEASE_MARKER", "SCENE_READBACK",
    ] as const) {
      const batch = macosScenario({
        ...W2_MACOS, batchId: "w2-b001", points: ["p1"], stripDynamic,
      });
      expect(() => assertCampaignBatchEvidence(readCampaignBatchEvidence(batch.root), batch.expectation),
        stripDynamic).toThrow(/PHYSICAL_EVIDENCE_INVALID/);
    }
  });

  test("rejects a point that claims physical evidence it cannot show", () => {
    const falseFlag = macosScenario({
      ...W2_MACOS, batchId: "w2-b001", points: ["p1"], physicalFlag: false,
    });
    expect(() => assertCampaignBatchEvidence(
      readCampaignBatchEvidence(falseFlag.root), falseFlag.expectation))
      .toThrow(/PHYSICAL_EVIDENCE_INVALID/);

    const absent = macosScenario({
      ...W2_MACOS, batchId: "w2-b001", points: ["p1"], omitDynamic: true,
    });
    expect(() => assertCampaignBatchEvidence(
      readCampaignBatchEvidence(absent.root), absent.expectation))
      .toThrow(/PHYSICAL_EVIDENCE_INVALID/);
  });

  test("rejects an artifact the point result's own inventory names but cannot verify", () => {
    const batch = macosScenario({
      ...W2_MACOS, batchId: "w2-b001", points: ["p1"], removeArtifact: "viewer.png",
    });
    expect(() => assertCampaignBatchEvidence(
      readCampaignBatchEvidence(batch.root), batch.expectation))
      .toThrow(/PHYSICAL_EVIDENCE_INVALID/);
  });

  test("rejects an incomplete cleanup or a station that is not clear", () => {
    const incomplete = macosScenario({
      ...W2_MACOS, batchId: "w2-b001", points: ["p1", "p2"], cleanupComplete: false,
    });
    expect(() => assertCampaignBatchEvidence(
      readCampaignBatchEvidence(incomplete.root), incomplete.expectation))
      .toThrow(/CLEANUP_INCOMPLETE/);

    const dirty = macosScenario({
      ...W2_MACOS, batchId: "w2-b001", points: ["p1", "p2"], stationClear: false,
    });
    expect(() => assertCampaignBatchEvidence(
      readCampaignBatchEvidence(dirty.root), dirty.expectation))
      .toThrow(/CLEANUP_INCOMPLETE/);
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
