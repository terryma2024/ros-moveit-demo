/** Tampered or incomplete v2 live evidence must be refused, never trusted by name. */
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, describe, expect, test } from "vitest";

import { verifyV2LiveEvidence } from "./live-evidence";

const roots: string[] = [];

afterEach(() => {
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true });
});

function sha256(data: string): string {
  return createHash("sha256").update(Buffer.from(data)).digest("hex");
}

function fixtureRoot(): { root: string; expected: Parameters<typeof verifyV2LiveEvidence>[1] } {
  const root = mkdtempSync(join(tmpdir(), "uq-live-evidence-"));
  roots.push(root);
  mkdirSync(join(root, "artifacts"), { recursive: true });
  const image = "frame-bytes";
  writeFileSync(join(root, "artifacts", "final.png"), image);
  const manifest = {
    schema_version: 2,
    worker_count: 2,
    selected_point_ids: ["p1", "p2", "p3", "p4"],
    profile_sha256: "a".repeat(64),
    qualification_sha256: "b".repeat(64),
    execution_identity_sha256: "c".repeat(64),
    workers: [
      { worker_id: "worker-01", generation: 1, pid: 4101, starttime_ticks: 11 },
      { worker_id: "worker-02", generation: 1, pid: 4102, starttime_ticks: 12 },
    ],
    concurrent_window: [1.0, 2.0],
  };
  const receipt = {
    schema_version: 2,
    profile_sha256: "a".repeat(64),
    qualification_sha256: "b".repeat(64),
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
      release_epoch: "release-1",
    },
    moveit: { plan_result: "SUCCESS", execute_result: "SUCCESS", shadow_detached: true },
    artifacts: [{ path: "artifacts/final.png", sha256: sha256(image) }],
  });
  writeFileSync(join(root, "manifest.json"), JSON.stringify(manifest));
  writeFileSync(join(root, "receipt.json"), JSON.stringify(receipt));
  writeFileSync(join(root, "points.json"), JSON.stringify(
    ["p1", "p2", "p3", "p4"].map(point)));
  return {
    root,
    expected: {
      workerCount: 2,
      pointCount: 4,
      profileSha256: "a".repeat(64),
      qualificationSha256: "b".repeat(64),
      executionIdentitySha256: "c".repeat(64),
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
});
