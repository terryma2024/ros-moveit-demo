/** Tampered or incomplete v2 live evidence must be refused, never trusted by name. */
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";

import { afterEach, describe, expect, test } from "vitest";

import { verifyV2LiveEvidence } from "./live-evidence";
import {
  PHYSICAL_EVIDENCE_FILES,
  assertCampaignBatchEvidence,
  readCampaignBatchEvidence,
  type CampaignBatchExpectation,
} from "../../e2e/expert-validation/assertions/live-evidence";

const roots: string[] = [];

afterEach(() => {
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true });
});

function sha256(data: Buffer | string): string {
  return createHash("sha256").update(data).digest("hex");
}

/**
 * One macOS batch shape: W2 (two parallel workers), W1 first-pass (one worker, any point count)
 * and the single-point FULL_RESTART_RETRY batch. The profile and qualification hashes are the
 * document's own, so a batch carrying the wrong profile cannot pass as another path.
 */
type BatchShape = {
  workerCount: number;
  pointIds: string[];
  profileSha256: string;
  qualificationSha256: string;
  executionIdentitySha256: string;
  releasePrefix: string;
};

const W2_SHAPE: BatchShape = {
  workerCount: 2,
  pointIds: ["p1", "p2", "p3", "p4"],
  profileSha256: "a".repeat(64),
  qualificationSha256: "b".repeat(64),
  executionIdentitySha256: "c".repeat(64),
  releasePrefix: "release",
};

function fixtureRoot(shape: BatchShape = W2_SHAPE): {
  root: string;
  expected: Parameters<typeof verifyV2LiveEvidence>[1];
} {
  const root = mkdtempSync(join(tmpdir(), "uq-live-evidence-"));
  roots.push(root);
  mkdirSync(join(root, "artifacts"), { recursive: true });
  const image = "frame-bytes";
  writeFileSync(join(root, "artifacts", "final.png"), image);
  const manifest = {
    schema_version: 2,
    worker_count: shape.workerCount,
    selected_point_ids: shape.pointIds,
    profile_sha256: shape.profileSha256,
    qualification_sha256: shape.qualificationSha256,
    execution_identity_sha256: shape.executionIdentitySha256,
    workers: Array.from({ length: shape.workerCount }, (_value, index) => ({
      worker_id: `worker-0${index + 1}`,
      generation: 1,
      pid: 4101 + index,
      starttime_ticks: 11 + index,
    })),
    concurrent_window: [1.0, 2.0],
  };
  const receipt = {
    schema_version: 2,
    profile_sha256: shape.profileSha256,
    qualification_sha256: shape.qualificationSha256,
    cleanup_complete: true,
  };
  const point = (id: string) => ({
    point_id: id,
    status: "PASSED",
    policy_state: "DONE",
    physics: {
      verification: "INDEPENDENT",
      cup_pose_world: [0, 0, 0.1, 0, 0, 0, 1],
      support_contact: true,
      gravity_verified: true,
      release_epoch: `${shape.releasePrefix}-${id}`,
    },
    moveit: { plan_result: "SUCCESS", execute_result: "SUCCESS", shadow_detached: true },
    artifacts: [{ path: "artifacts/final.png", sha256: sha256(image) }],
  });
  writeFileSync(join(root, "manifest.json"), JSON.stringify(manifest));
  writeFileSync(join(root, "receipt.json"), JSON.stringify(receipt));
  writeFileSync(join(root, "points.json"), JSON.stringify(shape.pointIds.map(point)));
  return {
    root,
    expected: {
      workerCount: shape.workerCount,
      pointCount: shape.pointIds.length,
      profileSha256: shape.profileSha256,
      qualificationSha256: shape.qualificationSha256,
      executionIdentitySha256: shape.executionIdentitySha256,
    },
  };
}

describe("verifyV2LiveEvidence", () => {
  test("accepts a complete untampered batch root", async () => {
    const { root, expected } = fixtureRoot();
    await expect(verifyV2LiveEvidence(root, expected)).resolves.toBeUndefined();
  });

  test("rejects a tampered artifact hash", async () => {
    const { root, expected } = fixtureRoot();
    writeFileSync(join(root, "artifacts", "final.png"), "tampered");
    await expect(verifyV2LiveEvidence(root, expected))
      .rejects.toThrow("QUALIFICATION_EVIDENCE_INVALID");
  });

  test("rejects fewer runtime slots than the selected exact N", async () => {
    const { root, expected } = fixtureRoot();
    const manifest = JSON.parse(
      (await import("node:fs")).readFileSync(join(root, "manifest.json"), "utf-8"));
    manifest.workers = manifest.workers.slice(0, 1);
    writeFileSync(join(root, "manifest.json"), JSON.stringify(manifest));
    await expect(verifyV2LiveEvidence(root, expected))
      .rejects.toThrow("QUALIFICATION_EVIDENCE_INVALID");
  });

  test("rejects a policy DONE point without independent physics", async () => {
    const { root, expected } = fixtureRoot();
    const points = JSON.parse(
      (await import("node:fs")).readFileSync(join(root, "points.json"), "utf-8"));
    delete points[0].physics;
    writeFileSync(join(root, "points.json"), JSON.stringify(points));
    await expect(verifyV2LiveEvidence(root, expected))
      .rejects.toThrow("QUALIFICATION_EVIDENCE_INVALID");
  });

  test("rejects an identity or profile mismatch", async () => {
    const { root, expected } = fixtureRoot();
    await expect(verifyV2LiveEvidence(root, { ...expected, profileSha256: "d".repeat(64) }))
      .rejects.toThrow("QUALIFICATION_EVIDENCE_INVALID");
    await expect(verifyV2LiveEvidence(root, { ...expected, executionIdentitySha256: "e".repeat(64) }))
      .rejects.toThrow("QUALIFICATION_EVIDENCE_INVALID");
  });

  test("accepts a W1 first-pass batch with one worker and a many-point selection", async () => {
    const { root, expected } = fixtureRoot({
      workerCount: 1,
      pointIds: ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8"],
      profileSha256: "1".repeat(64),
      qualificationSha256: "2".repeat(64),
      executionIdentitySha256: "3".repeat(64),
      releasePrefix: "w1-first-pass",
    });
    await expect(verifyV2LiveEvidence(root, expected)).resolves.toBeUndefined();
    // The same bytes are not a W2 batch and not a retry batch: the profile is the batch's own.
    await expect(verifyV2LiveEvidence(root, { ...expected, workerCount: 2 }))
      .rejects.toThrow("QUALIFICATION_EVIDENCE_INVALID");
    await expect(verifyV2LiveEvidence(root, { ...expected, profileSha256: "4".repeat(64) }))
      .rejects.toThrow("QUALIFICATION_EVIDENCE_INVALID");
  });

  test("accepts a single-point retry batch only under the retry profile", async () => {
    const { root, expected } = fixtureRoot({
      workerCount: 1,
      pointIds: ["p2"],
      profileSha256: "5".repeat(64),
      qualificationSha256: "6".repeat(64),
      executionIdentitySha256: "7".repeat(64),
      releasePrefix: "retry",
    });
    await expect(verifyV2LiveEvidence(root, expected)).resolves.toBeUndefined();
    await expect(verifyV2LiveEvidence(root, { ...expected, profileSha256: "1".repeat(64) }))
      .rejects.toThrow("QUALIFICATION_EVIDENCE_INVALID");
  });

  test("rejects evidence for a point outside the selected set", async () => {
    const { root, expected } = fixtureRoot({
      workerCount: 2,
      pointIds: ["p1", "p2", "p3", "p4"],
      profileSha256: "a".repeat(64),
      qualificationSha256: "b".repeat(64),
      executionIdentitySha256: "c".repeat(64),
      releasePrefix: "release",
    });
    // Same point count, one wrong id: a count alone is not the selection.
    const points = JSON.parse(readFileSync(join(root, "points.json"), "utf-8"));
    points[3] = { ...points[3], point_id: "p5" };
    writeFileSync(join(root, "points.json"), JSON.stringify(points));
    await expect(verifyV2LiveEvidence(root, {
      ...expected, selectedPointIds: ["p1", "p2", "p3", "p4"],
    })).rejects.toThrow("QUALIFICATION_EVIDENCE_INVALID");
  });

  test("rejects more point evidence than the selection carries", async () => {
    const { root, expected } = fixtureRoot({
      workerCount: 2,
      pointIds: ["p1", "p2", "p3", "p4"],
      profileSha256: "a".repeat(64),
      qualificationSha256: "b".repeat(64),
      executionIdentitySha256: "c".repeat(64),
      releasePrefix: "release",
    });
    const points = JSON.parse(readFileSync(join(root, "points.json"), "utf-8"));
    points.push({ ...points[0], point_id: "p5" });
    writeFileSync(join(root, "points.json"), JSON.stringify(points));
    // An unselected point's evidence is not part of this batch's selected-only evidence set.
    await expect(verifyV2LiveEvidence(root, expected))
      .rejects.toThrow("QUALIFICATION_EVIDENCE_INVALID");
  });

  test("accepts a batch whose declared selection is exactly its evidence set", async () => {
    const { root, expected } = fixtureRoot();
    await expect(verifyV2LiveEvidence(root, {
      ...expected, selectedPointIds: ["p1", "p2", "p3", "p4"],
    })).resolves.toBeUndefined();
    await expect(verifyV2LiveEvidence(root, {
      ...expected, selectedPointIds: ["p1", "p2", "p3", "p6"],
    })).rejects.toThrow("QUALIFICATION_EVIDENCE_INVALID");
  });

  test("rejects a batch whose receipt did not complete its cleanup", async () => {
    const { root, expected } = fixtureRoot();
    writeFileSync(join(root, "receipt.json"), JSON.stringify({
      schema_version: 2,
      profile_sha256: expected.profileSha256,
      qualification_sha256: expected.qualificationSha256,
      cleanup_complete: false,
    }));
    await expect(verifyV2LiveEvidence(root, expected))
      .rejects.toThrow("QUALIFICATION_EVIDENCE_INVALID");
  });
});

/**
 * The W2 first-pass batch as the campaign itself writes it: the service's own journal, sealed
 * attempt tree, published durability watermark and cleanup gates. The v2 documents above are the
 * per-N qualification format; this is the live campaign evidence a browser run has to prove.
 */
function writeW2BatchRoot(batchId: string): string {
  const root = mkdtempSync(join(tmpdir(), "uq-w2-campaign-"));
  roots.push(root);
  const points = ["p1", "p2", "p3", "p4"];
  const workers = ["worker-01", "worker-02"];
  const events: Array<Record<string, unknown>> = [
    { type: "CAMPAIGN_STARTED", payload: { batch_id: batchId } },
  ];
  points.forEach((pointId, index) => {
    const workerId = workers[index % workers.length];
    const sealed = join(
      root, "workers", workerId, "attempts", pointId, `attempt-${index + 1}`, "sealed");
    mkdirSync(sealed, { recursive: true });
    const files = PHYSICAL_EVIDENCE_FILES.map((relative) => {
      const document = relative === "numeric/physical.json"
        ? {
          object_state: { cup_pose_world: [0, 0, 0.1, 0, 0, 0, 1], support_contact: true },
          simulation_step: 4,
          publisher_sequence: 2,
        }
        : { relative };
      const bytes = Buffer.from(JSON.stringify(document));
      const target = join(sealed, relative);
      mkdirSync(dirname(target), { recursive: true });
      writeFileSync(target, bytes);
      return { relative_path: relative, size: bytes.length, sha256: sha256(bytes.toString()) };
    });
    writeFileSync(
      join(sealed, "attempt_result_manifest.json"),
      JSON.stringify({ files, directories: [] }),
    );
    events.push({
      type: "RESULT_COMMITTED",
      payload: {
        identity: {
          batch_id: batchId, coordinator_epoch: 1, worker_id: workerId, worker_generation: 1,
          point_id: pointId, attempt_id: `attempt-${index + 1}`, lease_generation: 1,
        },
        response: { status: "PASSED", sha256: "d".repeat(64), location: sealed },
      },
    });
  });
  events.push({ type: "BATCH_FINISHED", payload: { terminal_reason: "COMPLETED" } });
  events.push({ type: "CLEANUP_COMMITTED", payload: { cleanup_complete: true } });

  const journalRoot = join(root, "coordinator");
  mkdirSync(join(journalRoot, "events"), { recursive: true });
  let previous = "";
  const frames = events.map((event, index) => {
    const payload = Buffer.from(JSON.stringify({
      kind: "event", batch_id: batchId, type: event.type,
      idempotency_key: `${batchId}-${index + 1}`, payload: event.payload,
      coordinator_epoch: 1, sequence: index + 1, prev_frame_sha256: previous,
    }));
    const header = Buffer.alloc(8);
    header.writeBigUInt64BE(BigInt(payload.length));
    const bytes = Buffer.concat([
      header, Buffer.from(sha256(payload.toString()), "ascii"), payload, Buffer.from("\n"),
    ]);
    previous = sha256(bytes);
    return bytes;
  });
  const journal = Buffer.concat(frames);
  writeFileSync(join(journalRoot, "events", "epoch-1.journal"), journal);
  // The frame digest is over the frame's own bytes, so derive it from what was actually written.
  let offset = 0;
  let lastFrameSha = "";
  while (offset < journal.length) {
    const payloadLength = Number(journal.readBigUInt64BE(offset));
    const frameBytes = journal.subarray(offset, offset + 73 + payloadLength);
    lastFrameSha = sha256(frameBytes);
    offset += 73 + payloadLength;
  }
  writeFileSync(join(journalRoot, "committed-watermark.json"), JSON.stringify({
    batch_id: batchId, writer_epoch: 1, sequence: events.length, event_sha256: lastFrameSha,
  }));
  writeFileSync(join(root, "batch_manifest.json"), JSON.stringify({
    schema_version: 3, batch_kind: "FIRST_PASS", batch_id: batchId, run_mode: "execute",
    selected_point_ids: points, worker_count: 2, evidence_root: root,
  }));
  writeFileSync(join(root, "cleanup-gates.json"), JSON.stringify({
    schema_version: 1, batch_id: batchId, cleanup_gates_passed: true,
    coordinator_completion: { attempted: true, succeeded: true },
    batch_cleanup_complete: true,
  }));
  return root;
}

describe("W2 campaign batch evidence", () => {
  const expectation: CampaignBatchExpectation = {
    batchKind: "FIRST_PASS",
    executionProfile: "MPS_W2_FIRST_PASS",
    schemaVersion: 4,
    workerCount: 2,
    selectedPointIds: ["p1", "p2", "p3", "p4"],
  };

  test("accepts the W2 batch: selected-only commits, watermark, physics and cleanup", () => {
    const root = writeW2BatchRoot("b-w2");
    expect(() => assertCampaignBatchEvidence(readCampaignBatchEvidence(root), expectation))
      .not.toThrow();
  });

  test("refuses the W2 batch when the projection reports unfinished cleanup", () => {
    const root = writeW2BatchRoot("b-w2");
    expect(() => assertCampaignBatchEvidence(readCampaignBatchEvidence(root), {
      ...expectation,
      projection: { batch_id: "b-w2", batch_cleanup_complete: false, sequence: 8 },
    })).toThrow(/CLEANUP_INCOMPLETE/);
  });

  test("refuses the W2 batch when a sealed attempt lost its physical evidence", () => {
    const root = writeW2BatchRoot("b-w2");
    rmSync(join(root, "workers", "worker-01", "attempts", "p1", "attempt-1", "sealed",
      "numeric", "tf.json"));
    expect(() => assertCampaignBatchEvidence(readCampaignBatchEvidence(root), expectation))
      .toThrow(/PHYSICAL_EVIDENCE_INVALID/);
  });
});
