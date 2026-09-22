import { createHash } from "node:crypto";
import { chmodSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import { dirname, join } from "node:path";

import { test, expect } from "@playwright/test";

import {
  assertPhysicalEvidenceSet,
  assertProjectedPointEvidence,
  type CampaignBatchEvidence,
} from "../assertions/live-evidence";

/**
 * The per-point evidence expectation, split by batch layout.
 *
 * The Linux/fixed layout registers each attempt's artifacts on the service projection. The macOS
 * composed layout registers none *by design* - the product states that the campaign layout has no
 * sealed attempt manifest to import and that no artifact is registered for it - and binds every
 * point to the committed point result its own bytes carry instead. The shared assertion therefore
 * dispatches on the batch's own layout: the Linux expectation is unchanged, the macOS one verifies
 * the point result and its manifest digest from the bytes, and both refuse missing or tampered
 * evidence.
 */

const sha256 = (data: Buffer | string): string =>
  createHash("sha256").update(data).digest("hex");

function tempBatch(prefix: string): string {
  const root = mkdtempSync(join(os.tmpdir(), prefix));
  chmodSync(root, 0o700);
  return root;
}

/** A Linux/fixed batch: the projection carries the artifacts, the journal carries the commits. */
function linuxEvidence(batchRoot: string, sealedDir: string): CampaignBatchEvidence {
  return {
    batchRoot,
    layout: "LINUX_FIXED",
    manifest: { batch_id: "b-linux", selected_point_ids: ["p1"] },
    cleanup: { batch_cleanup_complete: true },
    watermark: null,
    events: [
      {
        type: "RESULT_COMMITTED",
        sequence: 4,
        payload: {
          point_id: "p1",
          attempt_id: "p1-attempt-1",
          worker_id: "w1",
          response: { location: sealedDir },
        },
      },
    ] as any,
    frameSha256: new Map(),
    journalFrames: null,
  };
}

/**
 * A macOS/composed batch, in the shape the product writes: `point-results/<point>.json` is the
 * committed point result, and the evidence manifest it names is the station document whose bytes
 * its own digest covers.
 *
 * `outcome` and the dynamic-manifest fields are the caller's, because the retry shape that matters
 * here is a business FAILED that carries no physical claim at all.
 */
function macosEvidence(
  overrides: { outcome?: string; dynamicRelative?: string | null } = {},
): {
  evidence: CampaignBatchEvidence;
  resultPath: string;
  manifestPath: string;
  manifestBytes: () => Buffer;
} {
  const batchRoot = tempBatch("so101-layout-macos-");
  const manifestPath = join(
    batchRoot, "w1-station", "p1-attempt-1", "pick", "batches", "b-macos", "points", "01-p1",
    "point-result.json",
  );
  mkdirSync(dirname(manifestPath), { recursive: true });
  const manifestBytes = () =>
    Buffer.from(JSON.stringify({
      id: "p1",
      manifest_path: "point-result.json",
      status: "PASSED",
      artifacts: [
        { relative_path: "initial-rgb.png", sha256: sha256("image"), byte_size: 5 },
      ],
    }));
  writeFileSync(manifestPath, manifestBytes());
  // The manifest's own inventory is relative to the station's `pick` root and has to be real
  // bytes: the physical-evidence reader walks it exactly like the product's own reader does.
  mkdirSync(join(batchRoot, "w1-station", "p1-attempt-1", "pick"), { recursive: true });
  writeFileSync(
    join(batchRoot, "w1-station", "p1-attempt-1", "pick", "initial-rgb.png"),
    Buffer.from("image"),
  );

  const resultsDirectory = join(batchRoot, "point-results");
  mkdirSync(resultsDirectory, { recursive: true });
  const resultPath = join(resultsDirectory, "p1.json");
  const document = {
    point_id: "p1",
    committed: true,
    outcome: overrides.outcome ?? "PASSED",
    attempt_id: "p1-attempt-1",
    worker_id: "w1",
    failure_code: "RGBD_PERCEPTION_EXITED_EARLY",
    physical_evidence: false,
    station_readback: { station_root: "w1-station/p1-attempt-1" },
    evidence_manifest_relative_path:
      "w1-station/p1-attempt-1/pick/batches/b-macos/points/01-p1/point-result.json",
    evidence_manifest_sha256: sha256(readFileSync(manifestPath)),
    dynamic_manifest_relative_path: overrides.dynamicRelative ?? null,
    dynamic_manifest_sha256: null,
  };
  writeFileSync(resultPath, JSON.stringify(document));

  return {
    evidence: {
      batchRoot,
      layout: "MACOS_COMPOSED",
      manifest: { batch_id: "b-macos", selected_point_ids: ["p1"] },
      cleanup: { cleanup: { complete: true } },
      watermark: null,
      events: [
        {
          type: "RESULT_COMMITTED",
          sequence: 7,
          payload: {
            point_id: "p1",
            attempt_id: "p1-attempt-1",
            worker_id: "w1",
            evidence_manifest_sha256: document.evidence_manifest_sha256,
            dynamic_manifest_sha256: null,
          },
        },
      ] as any,
      frameSha256: new Map(),
      journalFrames: null,
    },
    resultPath,
    manifestPath,
    manifestBytes,
  };
}

test("the Linux layout keeps its registered-artifact expectation", () => {
  const batchRoot = tempBatch("so101-layout-linux-");
  const sealedDir = join(batchRoot, "workers", "w1", "attempts", "p1", "p1-attempt-1", "sealed");
  mkdirSync(sealedDir, { recursive: true });
  const evidence = linuxEvidence(batchRoot, sealedDir);

  // Exactly today's expectation: a point without a registered artifact fails.
  expect(() =>
    assertProjectedPointEvidence(evidence, { points: [{ point_id: "p1", artifacts: [] }] }),
  ).toThrow(/POINT_EVIDENCE_INVALID: p1 has no registered artifact/);
  // ...and a point with one passes.
  expect(() =>
    assertProjectedPointEvidence(evidence, {
      points: [{ point_id: "p1", artifacts: [{ artifact_id: "a1" }] }],
    }),
  ).not.toThrow();
});

test("the macOS layout asserts the committed point result its bytes carry", () => {
  const { evidence } = macosEvidence();
  expect(() =>
    assertProjectedPointEvidence(evidence, {
      points: [{ point_id: "p1", display_id: "P01", artifacts: [] }],
    }),
  ).not.toThrow();
});

test("missing or tampered composed evidence is refused", () => {
  const { evidence, manifestPath } = macosEvidence();

  // A point the batch never committed is a refusal, never a skip.
  expect(() =>
    assertProjectedPointEvidence(evidence, {
      points: [{ point_id: "p2", display_id: "P02", artifacts: [] }],
    }),
  ).toThrow(/POINT_EVIDENCE_INVALID: P02 has no committed attempt/);

  // A projection without points is a refusal too.
  expect(() => assertProjectedPointEvidence(evidence, { points: [] })).toThrow(
    /POINT_EVIDENCE_INVALID: projection carries no points/,
  );

  // Tampering with the evidence manifest breaks the digest its point result carries.
  writeFileSync(manifestPath, Buffer.from(JSON.stringify({
    id: "p1",
    manifest_path: "point-result.json",
    status: "PASSED",
    artifacts: [],
  })));
  expect(() =>
    assertProjectedPointEvidence(evidence, { points: [{ point_id: "p1", display_id: "P01" }] }),
  ).toThrow(/POINT_EVIDENCE_INVALID: P01 evidence manifest digest/);

  // A tampered manifest that also drops its inventory is refused on the inventory too.
  const rewritten = macosEvidence();
  const parsed = JSON.parse(rewritten.manifestBytes().toString());
  parsed.artifacts = [];
  const bytes = Buffer.from(JSON.stringify(parsed));
  writeFileSync(rewritten.manifestPath, bytes);
  const result = JSON.parse(readFileSync(rewritten.resultPath, "utf-8"));
  result.evidence_manifest_sha256 = sha256(bytes);
  writeFileSync(rewritten.resultPath, JSON.stringify(result));
  const event = rewritten.evidence.events[0] as any;
  event.payload.evidence_manifest_sha256 = sha256(bytes);
  expect(() =>
    assertProjectedPointEvidence(rewritten.evidence, {
      points: [{ point_id: "p1", display_id: "P01" }],
    }),
  ).toThrow(/POINT_EVIDENCE_INVALID: P01 evidence manifest inventory/);
});

test("a composed point whose evidence manifest is gone is refused", () => {
  const { evidence, manifestPath } = macosEvidence();
  rmSync(manifestPath);
  expect(() =>
    assertProjectedPointEvidence(evidence, { points: [{ point_id: "p1", display_id: "P01" }] }),
  ).toThrow(/POINT_EVIDENCE_INVALID/);
});

/**
 * The retry shape the product really writes: one point, one lease, one RESULT_COMMITTED /
 * POINT_TERMINAL, business FAILED, `RGBD_PERCEPTION_EXITED_EARLY`, no dynamic manifest and no
 * physical claim. The reader has to accept that shape, refuse the same document when it claims
 * PASSED, and never hand a null relative path to the filesystem.
 */
test("a business FAILED attempt without a physical claim is valid composed evidence", () => {
  const { evidence } = macosEvidence({ outcome: "FAILED" });
  expect(() => assertPhysicalEvidenceSet(evidence)).not.toThrow();
});

test("a PASSED attempt without physical evidence stays PHYSICAL_EVIDENCE_INVALID", () => {
  const { evidence } = macosEvidence({ outcome: "PASSED" });
  expect(() => assertPhysicalEvidenceSet(evidence)).toThrow(
    /PHYSICAL_EVIDENCE_INVALID: p1 claims physical evidence it does not carry/,
  );
});

test("the composed reader never reads a null dynamic manifest as a file", () => {
  const { evidence } = macosEvidence({ outcome: "FAILED" });
  // The historical reader passed the null path to readFileSync and crashed with EISDIR/ENOENT
  // instead of classifying the attempt. The refusal, when it comes, is this module's own code.
  try {
    assertPhysicalEvidenceSet(evidence);
  } catch (error) {
    expect(String(error)).not.toMatch(/EISDIR|ENOENT|TypeError/);
    throw error;
  }
  const claimed = macosEvidence({ outcome: "PASSED" });
  expect(() => assertPhysicalEvidenceSet(claimed.evidence)).toThrow(
    /^PHYSICAL_EVIDENCE_INVALID: p1 claims physical evidence it does not carry$/,
  );
});

test("a composed attempt that names a dynamic manifest still has to carry it", () => {
  const { evidence } = macosEvidence({
    outcome: "FAILED",
    dynamicRelative: "w1-station/p1-attempt-1/pick/never-written.json",
  });
  expect(() => assertPhysicalEvidenceSet(evidence)).toThrow(/PHYSICAL_EVIDENCE_INVALID/);
});
