import { chmodSync, mkdirSync, mkdtempSync } from "node:fs";
import os from "node:os";
import { join } from "node:path";

import { test, expect } from "@playwright/test";

import {
  OVERLAY_PACKAGES,
  VERIFIED_DEPENDENCY_PACKAGES,
  resolvePackagePrefixes,
} from "../fixtures/installed";

/**
 * The dependency-prefix audit, exercised offline.
 *
 * ai-station keeps the whole verified dependency set under one install base
 * (`/data/work/ws_moveit/install`). macOS cannot: the MuJoCo fork is installed with
 * `--merge-install` into its own prefix, and `so101_mujoco_support` is installed by the task
 * overlay. `SO101_E2E_DEPENDENCY_PREFIX` therefore takes a colon-separated list of bases and every
 * package resolves from the first base that actually carries it - the same package-shaped rule the
 * darwin evidence-root branch applies to the durable root, and nothing more.
 *
 * The audit itself is not relaxed: a package that no base carries is still a hard failure, the
 * message still starts with `PACKAGE_PREFIX_MISSING`, and no fallback base is ever consulted.
 */

function tempRoot(prefix: string): string {
  const path = mkdtempSync(join(os.tmpdir(), prefix));
  chmodSync(path, 0o700);
  return path;
}

/** A base that carries exactly the named packages, the way a colcon install base does. */
function baseWith(root: string, name: string, packages: readonly string[]): string {
  const base = join(root, name);
  mkdirSync(base, { recursive: true });
  for (const packageName of packages) mkdirSync(join(base, packageName), { recursive: true });
  return base;
}

test("a single dependency base keeps the audited resolution unchanged", () => {
  const root = tempRoot("so101-prefix-single-");
  const overlay = baseWith(root, "overlay", OVERLAY_PACKAGES);
  const dependencies = baseWith(root, "install", VERIFIED_DEPENDENCY_PACKAGES);

  const resolved = resolvePackagePrefixes(overlay, dependencies);

  expect(resolved).toEqual([
    ...OVERLAY_PACKAGES.map((name) => join(overlay, name)),
    ...VERIFIED_DEPENDENCY_PACKAGES.map((name) => join(dependencies, name)),
  ]);
});

test("split dependency bases resolve from the first base that carries each package", () => {
  // The macOS layout: the merged MuJoCo fork prefix, then the task overlay's dependency base.
  const root = tempRoot("so101-prefix-split-");
  const overlay = baseWith(root, "overlay", OVERLAY_PACKAGES);
  const fork = baseWith(root, "fork-share", [
    "mujoco_3d_lidar",
    "mujoco_ros2_control_msgs",
    "mujoco_ros2_control_plugins",
    "mujoco_ros2_control",
  ]);
  const support = baseWith(root, "workspace-install", ["so101_mujoco_support"]);

  const resolved = resolvePackagePrefixes(overlay, `${fork}:${support}`);

  expect(resolved).toEqual([
    ...OVERLAY_PACKAGES.map((name) => join(overlay, name)),
    join(fork, "mujoco_3d_lidar"),
    join(fork, "mujoco_ros2_control_msgs"),
    join(fork, "mujoco_ros2_control_plugins"),
    join(fork, "mujoco_ros2_control"),
    join(support, "so101_mujoco_support"),
  ]);
  // A package an earlier base already carries is never taken from a later one.
  const later = baseWith(root, "later-install", ["mujoco_3d_lidar"]);
  const shadowed = resolvePackagePrefixes(overlay, `${fork}:${support}:${later}`);
  expect(shadowed).toEqual(resolved);
  expect(shadowed).not.toContain(join(later, "mujoco_3d_lidar"));
});

test("a package no base carries is refused, naming the package and the bases searched", () => {
  const root = tempRoot("so101-prefix-missing-");
  const overlay = baseWith(root, "overlay", OVERLAY_PACKAGES);
  const fork = baseWith(root, "fork-share", [
    "mujoco_ros2_control_msgs",
    "mujoco_ros2_control_plugins",
    "mujoco_ros2_control",
  ]);
  const support = baseWith(root, "workspace-install", ["so101_mujoco_support"]);

  const resolve = () => resolvePackagePrefixes(overlay, `${fork}:${support}`);
  expect(resolve).toThrow(/PACKAGE_PREFIX_MISSING: mujoco_3d_lidar/);
  const message = (() => {
    try {
      resolve();
    } catch (error) {
      return String(error);
    }
    return "";
  })();
  expect(message).toContain(fork);
  expect(message).toContain(support);

  // A single base keeps the original message shape: the candidate path it looked for.
  expect(() => resolvePackagePrefixes(overlay, fork)).toThrow(
    new RegExp(`PACKAGE_PREFIX_MISSING: ${join(fork, "mujoco_3d_lidar")}`),
  );
});

test("an overlay package is never rescued by a dependency base", () => {
  const root = tempRoot("so101-prefix-overlay-");
  const overlay = baseWith(root, "overlay", ["so101_teleop"]);
  const dependencies = baseWith(root, "install", [
    ...VERIFIED_DEPENDENCY_PACKAGES,
    "so101_demo_py",
  ]);

  expect(() => resolvePackagePrefixes(overlay, dependencies)).toThrow(
    new RegExp(`PACKAGE_PREFIX_MISSING: ${join(overlay, "so101_demo_py")}`),
  );
});
