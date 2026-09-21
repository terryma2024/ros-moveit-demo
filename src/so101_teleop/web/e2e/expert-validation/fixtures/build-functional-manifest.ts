#!/usr/bin/env bun
/**
 * Build the closed functional-acceptance manifest from the *deployed* service.
 *
 * The manifest is what Playwright registers cases from at collection time, so it is built before
 * the run and fails loudly when the service is unreachable, advertises no worker option, or the
 * required modes are missing. Nothing here is a resource qualification: the cases are "run this
 * mode at this worker count with this many points".
 *
 * A platform-bound host (macOS) is answered by its support matrix: the sweep is derived from the
 * matrix rows, everything the matrix does not carry is recorded in `skipped` with its reason, and
 * ADAPTIVE is not required because such a host has no adaptive route. A legacy host keeps exactly
 * the cases it has always had.
 *
 * `SO101_FUNCTIONAL_CASES` optionally restricts the sweep to a comma/space separated list of case
 * ids. A requested id the host does not advertise is refused with its reason (`FUNCTIONAL_CASE_
 * NOT_IN_SUPPORT_MATRIX`) - it is never downgraded to a case the host does run.
 */
import { writeFileSync } from "node:fs";
import { execSync } from "node:child_process";

import { selectFunctionalCases } from "./functional-cases";

const BASE = process.env.SO101_LIVE_SERVICE_BASE_URL;
if (!BASE) throw new Error("SO101_LIVE_SERVICE_BASE_URL is required");
const OUT = process.env.SO101_FUNCTIONAL_MANIFEST;
if (!OUT) throw new Error("SO101_FUNCTIONAL_MANIFEST is required");
const requestedIds = (process.env.SO101_FUNCTIONAL_CASES ?? "")
  .split(/[,\s]+/)
  .filter(Boolean);

const response = await fetch(`${BASE}/expert-validation/capabilities`);
if (!response.ok) throw new Error(`CAPABILITIES_HTTP_${response.status}`);
const capabilities: any = await response.json();

const selection = selectFunctionalCases(capabilities, { requestedIds });

let head = "unknown";
try {
  head = execSync("git rev-parse HEAD", { cwd: import.meta.dir + "/../../../.." }).toString().trim();
} catch {
  head = "unknown";
}

// Loud record: every shape this host does not carry is named with the reason it cannot run.
for (const skip of selection.skipped) {
  console.error(`SKIPPED ${skip.id}: ${skip.reason}`);
}

const manifest = {
  runtime_code_head: head,
  platform: capabilities.platform ?? null,
  worker_counts: selection.workerCounts,
  execution_modes: selection.executionModes,
  start_guard_timeout_s: capabilities.start_guard_policy.timeout_s,
  support_matrix: capabilities.support_matrix ?? [],
  // The matrix row every registered case claims; a case without a route is a legacy case.
  case_routes: selection.caseRoutes,
  // What this host cannot run, and why. A skip is never a silently dropped case.
  skipped: selection.skipped,
  cases: selection.cases,
  stability: {
    // The stability record the plan froze: five consecutive twenty-point full-restart batches at
    // N1, which is the sequential mode (the macOS W1 retry route when a matrix is published).
    mode: "SEQUENTIAL",
    worker_count: 1,
    point_count: 20,
    lifecycle: "FULL_RESTART_RETRY",
    consecutive_batches: 5,
    batch_timeout_s: 5400,
  },
};
writeFileSync(OUT, JSON.stringify(manifest, null, 2) + "\n");
console.log(JSON.stringify({
  platform: capabilities.platform ?? null,
  platform_bound: selection.platformBound,
  cases: selection.cases.length,
  case_ids: selection.cases.map((entry) => entry.id),
  skipped: selection.skipped.length,
  worker_counts: selection.workerCounts,
  modes: selection.executionModes,
}));
