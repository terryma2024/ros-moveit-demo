import { readFileSync } from "node:fs";

import { test, expect } from "@playwright/test";

/**
 * The functional manifest is the acceptance's own input, so it is checked against the execution
 * contract rather than trusted.  A worker count of one *is* the sequential mode in the contract:
 * a case that asks for PARALLEL at one worker can never be accepted by the service, and a retry
 * batch is by definition a single point on a freshly restarted stack.
 */

type FunctionalCase = {
  id: string;
  mode: string;
  worker_count: number;
  point_count: number;
  lifecycle: string;
  maximum_attempts: number;
  batch_timeout_s: number;
};

type FunctionalManifest = {
  cases: FunctionalCase[];
  stability: {
    mode: string;
    worker_count: number;
    point_count: number;
    lifecycle: string;
    consecutive_batches: number;
    batch_timeout_s: number;
  };
};

const REQUIRED_MODES = ["SEQUENTIAL", "PARALLEL", "ADAPTIVE"];

function loadManifest(): FunctionalManifest {
  const path = process.env.SO101_FUNCTIONAL_MANIFEST ?? "";
  if (!path) throw new Error("FUNCTIONAL_MANIFEST_REQUIRED");
  return JSON.parse(readFileSync(path, "utf8")) as FunctionalManifest;
}

test("every functional case is a valid execution contract", () => {
  const manifest = loadManifest();
  expect(manifest.cases.length).toBeGreaterThan(0);
  for (const entry of manifest.cases) {
    expect(REQUIRED_MODES, `${entry.id}: mode`).toContain(entry.mode);
    if (entry.mode === "PARALLEL") {
      expect(entry.worker_count, `${entry.id}: PARALLEL worker count`).toBeGreaterThanOrEqual(2);
      expect(entry.point_count, `${entry.id}: first-pass point count`).toBeGreaterThanOrEqual(4);
      expect(entry.point_count, `${entry.id}: first-pass point count`).toBeLessThanOrEqual(20);
    }
    if (entry.mode === "SEQUENTIAL") {
      expect(entry.worker_count, `${entry.id}: SEQUENTIAL worker count`).toBe(1);
    }
    if (entry.lifecycle === "FULL_RESTART_RETRY") {
      expect(entry.point_count, `${entry.id}: retry point count`).toBe(1);
      expect(entry.worker_count, `${entry.id}: retry worker count`).toBe(1);
      expect(entry.mode, `${entry.id}: retry mode`).toBe("SEQUENTIAL");
    }
    expect(entry.maximum_attempts, `${entry.id}: attempts`).toBeGreaterThanOrEqual(1);
    expect(entry.batch_timeout_s, `${entry.id}: timeout`).toBe(5400);
  }
});

test("the stability record is the frozen one", () => {
  const { stability } = loadManifest();
  expect(stability).toBeTruthy();
  expect(stability.mode).toBe("SEQUENTIAL");
  expect(stability.worker_count).toBe(1);
  expect(stability.point_count).toBe(20);
  expect(stability.lifecycle).toBe("FULL_RESTART_RETRY");
  expect(stability.consecutive_batches).toBe(5);
  expect(stability.batch_timeout_s).toBe(5400);
});
