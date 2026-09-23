import { spawn } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, it } from "vitest";

import { processAlive } from "../../e2e/expert-validation/fixtures/host-routes";
import { stopOwnedDescendants } from "../../e2e/expert-validation/fixtures/owned-descendants";

const helper = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../../test/e2e/process_helpers/descendant_helper.py",
);

it("reaps only a descendant attributed to this installed test root", async () => {
  const evidenceRoot = process.env.SO101_E2E_EVIDENCE_ROOT ?? tmpdir();
  mkdirSync(evidenceRoot, { recursive: true });
  const ownerRoot = mkdtempSync(join(evidenceRoot, "owned-descendant-"));
  const foreignRoot = `${ownerRoot}-foreign`;
  mkdirSync(foreignRoot);
  const readyFile = join(ownerRoot, "ready.txt");
  const foreignReady = join(foreignRoot, "ready.txt");
  const child = spawn(process.env.SO101_E2E_PYTHON ?? "python3", [
    helper, "--owner-root", ownerRoot, "--max-lifetime-s", "30",
  ], {
    env: { ...process.env, SO101_E2E_DESCENDANT_READY: readyFile },
    stdio: "ignore",
  });
  const foreign = spawn(process.env.SO101_E2E_PYTHON ?? "python3", [
    helper, "--owner-root", foreignRoot, "--max-lifetime-s", "30",
  ], {
    env: { ...process.env, SO101_E2E_DESCENDANT_READY: foreignReady },
    stdio: "ignore",
  });
  expect(child.pid).toBeTypeOf("number");
  try {
    const deadline = Date.now() + 5_000;
    while ((!existsSync(readyFile) || !existsSync(foreignReady)) && Date.now() < deadline) {
      await new Promise((done) => setTimeout(done, 25));
    }
    expect(existsSync(readyFile)).toBe(true);
    expect(existsSync(foreignReady)).toBe(true);
    expect(processAlive(child.pid!)).toBe(true);
    expect(await stopOwnedDescendants(ownerRoot)).toEqual([child.pid]);
    expect(processAlive(child.pid!)).toBe(false);
    expect(processAlive(foreign.pid!)).toBe(true);
  } finally {
    if (child.pid && processAlive(child.pid)) child.kill("SIGKILL");
    if (foreign.pid && processAlive(foreign.pid)) foreign.kill("SIGKILL");
  }
});
