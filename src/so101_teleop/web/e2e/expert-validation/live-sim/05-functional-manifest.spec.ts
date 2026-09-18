import { readFileSync } from "node:fs";

import { liveSimTest as test, expect, requireGateDetail } from "../fixtures/live-sim";

/**
 * R05: one registered case per entry of the frozen functional manifest.
 *
 * The manifest is produced by `bun run prepare:functional-manifest` from the *deployed*
 * service's capabilities before Playwright collects, so this file fails collection when it is
 * missing or malformed instead of quietly running a single case. Each case asserts that the
 * deployed service really accepts that configuration — the mode is advertised, the worker
 * count is selectable, and the guard policy it will be judged by is present. It is a
 * configuration acceptance, not a physical-success claim.
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
  runtime_code_head: string;
  worker_counts: number[];
  execution_modes: string[];
  cases: FunctionalCase[];
  stability: Record<string, unknown>;
};

const manifestPath = process.env.SO101_FUNCTIONAL_MANIFEST;
if (!manifestPath) {
  throw new Error("SO101_FUNCTIONAL_MANIFEST is required before collection");
}
let manifest: FunctionalManifest;
try {
  manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
} catch (error) {
  throw new Error(`FUNCTIONAL_MANIFEST_UNREADABLE: ${String(error)}`);
}
if (!Array.isArray(manifest.cases) || manifest.cases.length === 0) {
  throw new Error("FUNCTIONAL_MANIFEST_EMPTY");
}
for (const entry of manifest.cases) {
  if (!entry.id || !entry.mode || !Number.isInteger(entry.worker_count)) {
    throw new Error(`FUNCTIONAL_CASE_MALFORMED: ${JSON.stringify(entry)}`);
  }
}

for (const entry of manifest.cases) {
  test(`R05 ${entry.id} accepted by the deployed service @live-sim`, async ({ liveServer }) => {
    test.setTimeout(120_000);
    requireGateDetail(process.env.SO101_E2E_EVIDENCE_ROOT!, "R01", {
      evidenceRoot: process.env.SO101_E2E_EVIDENCE_ROOT,
    });
    const response = await fetch(`${liveServer.baseURL}/expert-validation/capabilities`);
    expect(response.ok).toBe(true);
    const capabilities = await response.json();

    expect(capabilities.execution_modes, `${entry.id}: mode ${entry.mode}`).toContain(entry.mode);
    expect(capabilities.start_guard_policy?.timeout_s).toBeGreaterThan(0);

    if (entry.mode === "PARALLEL") {
      const selectable = (capabilities.worker_count_availability ?? [])
        .filter((item: any) => item.selectable === true)
        .map((item: any) => item.worker_count);
      expect(selectable, `${entry.id}: worker count ${entry.worker_count}`)
        .toContain(entry.worker_count);
    }
    expect(entry.point_count).toBeGreaterThanOrEqual(1);
    expect(entry.batch_timeout_s).toBeGreaterThan(0);
    expect(entry.maximum_attempts).toBeGreaterThanOrEqual(1);
  });
}
