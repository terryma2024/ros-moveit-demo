import { chmodSync, mkdirSync, mkdtempSync, rmSync, symlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, describe, expect, test } from "vitest";

import {
  DURABLE_EVIDENCE_PREFIX,
  durableRootFailure,
} from "../../e2e/expert-validation/fixtures/durable-root";

/**
 * The platform-bound durable-evidence-root rule.
 *
 * Linux (ai-station) keeps exactly one registered tree and nothing else. macOS has no `/data`
 * volume at all, so the registered root there is the task's own `SO101_TASK_ROOT` and the run
 * directory has to be private inside it. Both branches fail closed: no fallback root, no silently
 * created directory, and no acceptance of a symlink or a world-readable path.
 */

const roots: string[] = [];

function privateDir(parent?: string, name?: string): string {
  const path = parent && name ? join(parent, name) : mkdtempSync(join(tmpdir(), "so101-durable-"));
  mkdirSync(path, { recursive: true, mode: 0o700 });
  chmodSync(path, 0o700);
  if (!parent) roots.push(path);
  return path;
}

afterEach(() => {
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true });
});

describe("the darwin branch", () => {
  test("accepts a private run directory inside the registered task root", () => {
    const taskRoot = privateDir();
    const run = privateDir(taskRoot, "web-live");
    expect(
      durableRootFailure(run, { SO101_TASK_ROOT: taskRoot }, { platform: "darwin" }),
    ).toBeNull();
    // The registered root itself is a registered root too.
    expect(
      durableRootFailure(taskRoot, { SO101_TASK_ROOT: taskRoot }, { platform: "darwin" }),
    ).toBeNull();
  });

  test("refuses a relative, unregistered or missing root", () => {
    const taskRoot = privateDir();
    const run = privateDir(taskRoot, "web-live");
    expect(durableRootFailure("web-live", { SO101_TASK_ROOT: taskRoot }, { platform: "darwin" }))
      .toBe("REQUIRED");
    expect(durableRootFailure(run, {}, { platform: "darwin" })).toBe("REQUIRED");
    expect(
      durableRootFailure(run, { SO101_TASK_ROOT: "relative/task" }, { platform: "darwin" }),
    ).toBe("REQUIRED");
    const outside = privateDir();
    expect(
      durableRootFailure(outside, { SO101_TASK_ROOT: taskRoot }, { platform: "darwin" }),
    ).toBe("REQUIRED");
    expect(
      durableRootFailure(join(taskRoot, "not-created"), { SO101_TASK_ROOT: taskRoot },
        { platform: "darwin" }),
    ).toBe("REQUIRED");
    // The ai-station prefix is not a registered root on a host that has no /data volume.
    const unregistered = `${DURABLE_EVIDENCE_PREFIX}task/run-1`;
    expect(
      durableRootFailure(unregistered, { SO101_TASK_ROOT: taskRoot }, { platform: "darwin" }),
    ).toBe("REQUIRED");
  });

  test("refuses a symlink, another account's directory, and a readable-by-others run root", () => {
    const taskRoot = privateDir();
    const run = privateDir(taskRoot, "web-live");
    const link = join(taskRoot, "linked");
    symlinkSync(run, link);
    expect(durableRootFailure(link, { SO101_TASK_ROOT: taskRoot }, { platform: "darwin" }))
      .toBe("NOT_PRIVATE");

    const loose = privateDir(taskRoot, "loose");
    chmodSync(loose, 0o755);
    expect(durableRootFailure(loose, { SO101_TASK_ROOT: taskRoot }, { platform: "darwin" }))
      .toBe("NOT_PRIVATE");

    const foreign = privateDir(taskRoot, "foreign");
    expect(
      durableRootFailure(foreign, { SO101_TASK_ROOT: taskRoot },
        { platform: "darwin", uid: 4242, pathInfo: (path) => ({
          isDirectory: path !== foreign,
          isSymbolicLink: false,
          mode: 0o700,
          uid: path === foreign ? 4242 : (process.getuid?.() ?? 0),
        }) }),
    ).toBe("NOT_PRIVATE");
  });
});

describe("the ai-station branch", () => {
  test("refuses every root outside the one registered tree", () => {
    const taskRoot = privateDir();
    const run = privateDir(taskRoot, "web-live");
    expect(durableRootFailure(run, { SO101_TASK_ROOT: taskRoot }, { platform: "linux" }))
      .toBe("REQUIRED");
    expect(durableRootFailure("/tmp/so101-evidence", {}, { platform: "linux" })).toBe("REQUIRED");
    expect(durableRootFailure("", {}, { platform: "linux" })).toBe("REQUIRED");
  });

  test("accepts only the registered prefix there, and reports a missing tree as required", () => {
    const registered = `${DURABLE_EVIDENCE_PREFIX}so101-macos-service-campaign-closure/run-1`;
    expect(
      durableRootFailure(registered, {}, { platform: "linux", pathExists: () => true }),
    ).toBeNull();
    // The same path on a host where the tree does not exist is still refused.
    expect(durableRootFailure(registered, {}, { platform: "linux" })).toBe("REQUIRED");
  });
});
