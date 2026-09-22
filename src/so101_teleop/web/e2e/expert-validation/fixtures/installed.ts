import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import { createServer } from "node:net";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { test as base, expect } from "@playwright/test";

import { e2eEvidenceRoot, proveChrome } from "./chrome";

const PACKAGE_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../../../..");
const LAUNCHER = join(PACKAGE_ROOT, "test/e2e/installed_test_launcher.py");
const HELPER_SPECS = join(PACKAGE_ROOT, "test/fixtures/expert_validation_e2e/helper-specs");

/** Product packages come from the task overlay; every other package from the audited
 *  verified dependency underlay. A missing prefix fails closed instead of filtering. */
export const OVERLAY_PACKAGES = ["so101_demo_py", "so101_teleop"] as const;
export const VERIFIED_DEPENDENCY_PACKAGES = [
  "mujoco_3d_lidar",
  "mujoco_ros2_control_msgs",
  "mujoco_ros2_control_plugins",
  "mujoco_ros2_control",
  "so101_mujoco_support",
] as const;

/** A package nothing carries: the candidate is named for a single base, and the package plus every
 *  base searched when the dependency side is a list. */
function missingPackage(name: string, bases: readonly string[]): Error {
  if (bases.length === 1) return new Error(`PACKAGE_PREFIX_MISSING: ${join(bases[0], name)}`);
  return new Error(`PACKAGE_PREFIX_MISSING: ${name} (searched: ${bases.join(", ")})`);
}

/**
 * Resolve the two overlay prefixes and the five audited dependency prefixes.
 *
 * `verifiedDependencyPrefixes` is a list separated by `:` - a layout portability rule, the same
 * shape as the darwin evidence-root branch: ai-station keeps the whole verified set under one
 * install base (`/data/work/ws_moveit/install`), while macOS installs the MuJoCo fork with
 * `--merge-install` into its own prefix and `so101_mujoco_support` with the task overlay, so the
 * set genuinely lives in two bases there. A single base behaves exactly as before.
 *
 * The audit is not relaxed: every package has to be carried by one of the bases and a package that
 * none of them carries fails closed with `PACKAGE_PREFIX_MISSING`. There is no fallback base and
 * nothing is skipped - an overlay package is never rescued by a dependency base.
 */
export function resolvePackagePrefixes(
  overlayPrefix: string,
  verifiedDependencyPrefixes: string,
): string[] {
  // The project install is a dependency base in its own right: `so101_mujoco_support` ships there,
  // not in any overlay, so it is searched first and every other base after it.
  const dependencyBases = [
    overlayPrefix,
    ...verifiedDependencyPrefixes.split(":").filter((entry) => entry !== ""),
  ].filter((entry, index, all) => all.indexOf(entry) === index);
  if (dependencyBases.length === 0) dependencyBases.push(verifiedDependencyPrefixes);
  const resolved: string[] = [];
  for (const name of [...OVERLAY_PACKAGES, ...VERIFIED_DEPENDENCY_PACKAGES]) {
    if ((OVERLAY_PACKAGES as readonly string[]).includes(name)) {
      const candidate = join(overlayPrefix, name);
      if (!existsSync(candidate)) throw missingPackage(name, [overlayPrefix]);
      resolved.push(candidate);
      continue;
    }
    // Two installed layouts carry a package: an isolated install gives it a directory of its own
    // (`<base>/<name>`), a merged install represents it by its ament index marker
    // (`<base>/share/ament_index/resource_index/packages/<name>`) and keeps the libraries in the
    // base's own `lib`. This host's runtime fork is merged - it carries all four fork packages as
    // markers and none as directories - so both shapes are checked, and the prefix pushed is the one
    // the caller's `lib`/`site-packages` joins need.
    const isolated = dependencyBases
      .map((base) => join(base, name))
      .find((path) => existsSync(path));
    const merged = dependencyBases
      .find((base) => existsSync(join(base, "share/ament_index/resource_index/packages", name)));
    const candidate = isolated ?? merged;
    if (candidate === undefined) {
      throw missingPackage(
        name,
        dependencyBases.flatMap((base) => [
          join(base, name),
          join(base, "share/ament_index/resource_index/packages", name),
        ]),
      );
    }
    resolved.push(candidate);
  }
  return resolved;
}

export function installPrefix(): string {
  const value = process.env.SO101_E2E_INSTALL_PREFIX;
  if (!value || !existsSync(join(value, "so101_teleop"))) {
    throw new Error("SO101_E2E_INSTALL_PREFIX_INVALID");
  }
  return value;
}

export function pythonExecutable(): string {
  const value = process.env.SO101_E2E_PYTHON;
  if (!value || !existsSync(value)) {
    throw new Error("SO101_E2E_PYTHON_REQUIRED");
  }
  return value;
}

async function freePort(): Promise<number> {
  return new Promise((resolvePromise, rejectPromise) => {
    const server = createServer();
    server.once("error", rejectPromise);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (address === null || typeof address === "string") {
        rejectPromise(new Error("PORT_ALLOCATION_FAILED"));
        return;
      }
      const { port } = address;
      server.close(() => resolvePromise(port));
    });
  });
}

export type InstalledServer = {
  port: number;
  baseURL: string;
  evidenceDir: string;
  serverRoot: string;
  serverLog: string;
  serverPid: () => number;
  specId: string;
  stop: () => Promise<number | null>;
  killHard: () => Promise<void>;
  start: () => Promise<void>;
  restart: () => Promise<void>;
};

type InstalledFixtures = {
  installedServer: InstalledServer;
  consoleErrors: string[];
};

export const QUALIFICATION_ENV = {
  SO101_VALIDATION_YOLO_WEIGHTS:
    "/data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/models/yolo/best.pt",
  SO101_VALIDATION_GROUNDED_ROOT: "/data/work/so101-models/grounded-sam-v2-scipy-lock",
  SO101_VALIDATION_BROKER_IMAGE: "so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1",
  SO101_VALIDATION_PARALLEL_ACCEPTANCE:
    "/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-20-f91/aggregate_results.json",
  SO101_VALIDATION_ADAPTIVE_ACCEPTANCE:
    "/data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/e2001/aggregate_results.json",
  SO101_VALIDATION_ADAPTIVE_FAULT_INJECTION:
    "/data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/su09/aggregate_results.json",
  SO101_VALIDATION_ADAPTIVE_PERFORMANCE_TIERS: "1,2,4,6,8",
};

export const installedTest = base.extend<InstalledFixtures>({
  consoleErrors: async ({ page }, use) => {
    const errors: string[] = [];
    page.on("console", (message) => {
      if (message.type() !== "error") return;
      const url = message.location()?.url ?? "";
      if (url.endsWith("/favicon.ico")) return;
      errors.push(`${message.text()} (${url})`);
    });
    page.on("pageerror", (error) => errors.push(String(error)));
    await use(errors);
  },
  baseURL: async ({ installedServer }, use) => {
    await use(installedServer.baseURL);
  },
  installedServer: async ({ }, use, testInfo) => {
    const specId = testInfo.title.match(/spec:([a-z0-9-]+)/)?.[1] ?? "default";
    const specPath = join(HELPER_SPECS, `${specId}.json`);
    if (!existsSync(specPath)) {
      throw new Error(`HELPER_SPEC_MISSING: ${specPath}`);
    }
    const slug = testInfo.title.replace(/[^a-zA-Z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 100);
    const evidenceDir = join(
      e2eEvidenceRoot(), "server", `${slug}-${Date.now().toString(36)}`,
    );
    mkdirSync(evidenceDir, { recursive: true });
    proveChrome(evidenceDir);
    const serverRoot = join(evidenceDir, "runtime");
    mkdirSync(serverRoot);

    const prefix = installPrefix();
    const packagePrefixes = ["mujoco_3d_lidar", "mujoco_ros2_control_msgs",
      "mujoco_ros2_control_plugins", "mujoco_ros2_control", "so101_mujoco_support",
      "so101_demo_py", "so101_teleop"]
      .map((name) => join(prefix, name))
      .filter((path) => existsSync(path));
    const port = await freePort();
    const readyFile = join(serverRoot, "ready.json");
    const serverLog = join(evidenceDir, "server.log");
    const staticDir = join(prefix, "so101_teleop/share/so101_teleop/web");

    let child: ChildProcess | null = null;
    let currentPid = 0;
    const start = async () => {
      if (child) throw new Error("SERVER_ALREADY_STARTED");
      if (existsSync(readyFile)) rmSync(readyFile);
      child = spawn(
        pythonExecutable(),
        [
          LAUNCHER,
          "--install-prefix", prefix,
          "--evidence-root", serverRoot,
          "--port", String(port),
          "--spec", specPath,
          "--static-dir", staticDir,
          "--ready-file", readyFile,
        ],
        {
          cwd: PACKAGE_ROOT,
          env: {
            ...process.env,
            ...QUALIFICATION_ENV,
            SO101_DISABLE_KIMI_EDITABLE_FINDER: "1",
            PYTHONNOUSERSITE: "1",
            AMENT_PREFIX_PATH: [...packagePrefixes, "/opt/ros/jazzy"].join(":"),
            ROS_HOME: join(serverRoot, "ros-home"),
            ROS_LOG_DIR: join(serverRoot, "ros-home", "log"),
          },
          stdio: ["ignore", "pipe", "pipe"],
        },
      );
      const logStream = (await import("node:fs")).createWriteStream(serverLog, { flags: "a" });
      child.stdout?.pipe(logStream);
      child.stderr?.pipe(logStream);
      const deadline = Date.now() + 30_000;
      while (!existsSync(readyFile)) {
        if (child.exitCode !== null) {
          const log = existsSync(serverLog) ? readFileSync(serverLog, "utf-8").slice(-2000) : "";
          throw new Error(`INSTALLED_SERVER_EXITED:${child.exitCode}\n${log}`);
        }
        if (Date.now() > deadline) {
          child.kill("SIGKILL");
          child = null;
          throw new Error("INSTALLED_SERVER_READY_TIMEOUT");
        }
        await new Promise((resolvePromise) => setTimeout(resolvePromise, 100));
      }
      const ready = JSON.parse(readFileSync(readyFile, "utf-8"));
      currentPid = ready.pid;
    };
    const exited = (process_: ChildProcess) =>
      process_.exitCode !== null || process_.signalCode !== null;
    const stop = async (): Promise<number | null> => {
      if (!child) return null;
      const current = child;
      child = null;
      current.kill("SIGINT");
      const deadline = Date.now() + 15_000;
      while (!exited(current)) {
        if (Date.now() > deadline) {
          current.kill("SIGKILL");
          break;
        }
        await new Promise((resolvePromise) => setTimeout(resolvePromise, 100));
      }
      return current.exitCode;
    };
    const killHard = async (): Promise<void> => {
      if (!child) return;
      const current = child;
      child = null;
      current.kill("SIGKILL");
      const deadline = Date.now() + 15_000;
      while (!exited(current)) {
        if (Date.now() > deadline) throw new Error("SERVER_SIGKILL_TIMEOUT");
        await new Promise((resolvePromise) => setTimeout(resolvePromise, 50));
      }
    };

    await start();
    const server: InstalledServer = {
      port,
      baseURL: `http://127.0.0.1:${port}`,
      evidenceDir,
      serverRoot,
      serverLog,
      serverPid: () => currentPid,
      specId,
      stop,
      killHard,
      start,
      restart: async () => {
        await stop();
        await start();
      },
    };
    await use(server);
    const exitCode = await stop();
    writeFileSync(
      join(evidenceDir, "server-exit.json"),
      JSON.stringify({ exitCode }) + "\n",
    );
    let leftovers = "";
    try {
      leftovers = execFileSync("pgrep", ["-f", serverRoot], { encoding: "utf-8" }).trim();
    } catch {
      leftovers = "";
    }
    if (leftovers) {
      throw new Error(`OWNED_PROCESS_LEAK: ${leftovers}`);
    }
  },
});

export { expect };
