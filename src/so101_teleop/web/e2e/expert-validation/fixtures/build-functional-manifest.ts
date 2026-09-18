#!/usr/bin/env bun
/**
 * Build the closed functional-acceptance manifest from the *deployed* service.
 *
 * The manifest is what Playwright registers cases from at collection time, so it is built
 * before the run and fails loudly when the service is unreachable, advertises no worker
 * option, or the required modes are missing. Nothing here is a resource qualification: the
 * cases are "run this mode at this worker count with this many points".
 */
import { writeFileSync } from "node:fs";
import { execSync } from "node:child_process";

const BASE = process.env.SO101_LIVE_SERVICE_BASE_URL;
if (!BASE) throw new Error("SO101_LIVE_SERVICE_BASE_URL is required");
const OUT = process.env.SO101_FUNCTIONAL_MANIFEST;
if (!OUT) throw new Error("SO101_FUNCTIONAL_MANIFEST is required");

const response = await fetch(`${BASE}/expert-validation/capabilities`);
if (!response.ok) throw new Error(`CAPABILITIES_HTTP_${response.status}`);
const capabilities: any = await response.json();

const selectable: number[] = (capabilities.worker_count_availability ?? [])
  .filter((entry: any) => entry.selectable === true)
  .map((entry: any) => entry.worker_count)
  .sort((a: number, b: number) => a - b);
if (selectable.length === 0) throw new Error("NO_SELECTABLE_WORKER_OPTION");

const modes: string[] = capabilities.execution_modes ?? [];
for (const required of ["SEQUENTIAL", "PARALLEL", "ADAPTIVE"]) {
  if (!modes.includes(required)) throw new Error(`MODE_NOT_ADVERTISED: ${required}`);
}
if (!capabilities.start_guard_policy?.timeout_s) {
  throw new Error("START_GUARD_POLICY_MISSING");
}

let head = "unknown";
try {
  head = execSync("git rev-parse HEAD", { cwd: import.meta.dir + "/../../../.." }).toString().trim();
} catch {
  head = "unknown";
}

const cases: any[] = [];
for (const workerCount of selectable) {
  for (const pointCount of [4, 20]) {
    cases.push({
      id: `fixed-n${workerCount}-p${pointCount}`,
      mode: "PARALLEL",
      worker_count: workerCount,
      point_count: pointCount,
      lifecycle: "FIRST_PASS",
      maximum_attempts: 1,
      batch_timeout_s: 5400,
    });
  }
}
cases.push({
  id: "sequential-n1-p4",
  mode: "SEQUENTIAL",
  worker_count: 1,
  point_count: 4,
  lifecycle: "FIRST_PASS",
  maximum_attempts: 1,
  batch_timeout_s: 5400,
});
cases.push({
  id: "adaptive-ladder-p20",
  mode: "ADAPTIVE",
  worker_count: capabilities.adaptive_default_ladder?.[0] ?? 8,
  point_count: 20,
  lifecycle: "FIRST_PASS",
  maximum_attempts: 1,
  batch_timeout_s: 5400,
});
cases.push({
  id: "n1-full-restart-single-point",
  mode: "PARALLEL",
  worker_count: 1,
  point_count: 1,
  lifecycle: "FULL_RESTART_RETRY",
  maximum_attempts: 1,
  batch_timeout_s: 5400,
});

const manifest = {
  runtime_code_head: head,
  worker_counts: selectable,
  execution_modes: modes,
  start_guard_timeout_s: capabilities.start_guard_policy.timeout_s,
  cases,
  stability: {
    mode: "PARALLEL",
    worker_count: 1,
    point_count: 20,
    lifecycle: "FULL_RESTART_RETRY",
    consecutive_batches: 5,
    batch_timeout_s: 5400,
  },
};
writeFileSync(OUT, JSON.stringify(manifest, null, 2) + "\n");
console.log(JSON.stringify({ cases: cases.length, worker_counts: selectable, modes }));
