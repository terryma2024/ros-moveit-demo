/**
 * The installed suite's host rules.
 *
 * `playwright.installed.config.ts` was written against ai-station, and every way it fails on macOS
 * is one of these four rules rather than a missing product feature:
 *
 * - it sends `contract_version: 2` where the service accepts only 3, so seventeen of its
 *   twenty-five tests die in `preflight` with `CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION`;
 * - it reads `/proc/<pid>/stat`, which macOS does not have, so liveness checks answer "dead" for
 *   every process - a silent false green wherever the assertion was "still alive";
 * - it builds `PYTHONPATH` from `lib/python3.12/site-packages` and `/opt/ros/jazzy`, neither of
 *   which exists here;
 * - it asks for an ADAPTIVE route, which macOS does not carry at all.
 *
 * The rules are the ones the live fixtures already follow: a platform-bound host is answered by its
 * own support matrix, the executable layout comes from the platform, and liveness is read through
 * whatever the platform actually provides. Linux is unchanged - with no matrix the legacy rules
 * apply, `python3.12` stays the suffix, and `/proc` stays the reader.
 */

import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

import type {
  CapabilitiesDocument,
  FunctionalBatchKind,
  SupportMatrixRow,
} from "./functional-cases";

/**
 * The execution contract the service validates before it looks at anything else.
 *
 * `_reject_legacy_execution_contract` refuses any POST/PUT/PATCH body whose `contract_version` is
 * not exactly this, with `CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION`.
 */
export const EXECUTION_CONTRACT_VERSION = 3;

export type HostMode = "SEQUENTIAL" | "PARALLEL" | "ADAPTIVE";

export type HostRouteRequest = {
  mode: HostMode;
  workerCount: number;
  batchKind: FunctionalBatchKind;
};

export type HostRoute =
  | {
    runnable: true;
    platformBound: boolean;
    /** The matrix row's profile on a platform-bound host; null where the host has no matrix. */
    profile: string | null;
    schemaVersion: number | null;
  }
  | { runnable: false; platformBound: boolean; reason: string };

/**
 * Whether this host serves the requested shape, and under which row.
 *
 * A platform-bound host is answered strictly by its matrix: a shape the matrix does not carry is
 * refused with the host's own reason rather than downgraded to a shape it does serve. A host with no
 * matrix keeps the legacy rules - the mode has to be advertised, and a fixed worker count has to be
 * selectable.
 */
export function hostRoute(
  capabilities: CapabilitiesDocument,
  request: HostRouteRequest,
): HostRoute {
  const matrix = capabilities.support_matrix ?? [];
  const platformBound = matrix.length > 0;
  const availability = (capabilities.worker_count_availability ?? []).find(
    (entry) => entry.worker_count === request.workerCount,
  );

  if (platformBound) {
    const row = matrix
      .filter((candidate) => candidate.selectable !== false)
      .find(
        (candidate: SupportMatrixRow) =>
          candidate.execution_mode === request.mode
          && candidate.worker_count === request.workerCount
          && candidate.batch_kind === request.batchKind,
      );
    if (row) {
      return {
        runnable: true,
        platformBound,
        profile: row.profile ?? null,
        schemaVersion: row.schema_version ?? null,
      };
    }
    if (availability?.selectable === false) {
      return {
        runnable: false,
        platformBound,
        reason: availability.reason_codes?.[0] ?? "UNSUPPORTED_ON_MACOS",
      };
    }
    return { runnable: false, platformBound, reason: "UNSUPPORTED_ON_MACOS" };
  }

  const modes = capabilities.execution_modes ?? [];
  if (!modes.includes(request.mode)) {
    return { runnable: false, platformBound, reason: "MODE_NOT_ADVERTISED" };
  }
  if (request.mode !== "ADAPTIVE" && availability?.selectable === false) {
    return {
      runnable: false,
      platformBound,
      reason: availability.reason_codes?.[0] ?? "WORKER_COUNT_NOT_SELECTABLE",
    };
  }
  return { runnable: true, platformBound, profile: null, schemaVersion: null };
}

export type HostPaths = {
  /** The suffix an installed prefix carries its Python packages under, relative to the prefix. */
  pythonSite: string;
  /** The ROS underlay root, which is a different logical path on each host. */
  rosUnderlayRoot: string;
  /** Where the underlay keeps `rclpy`. */
  rosUnderlaySite: string;
  /** The audited dependency bases, colon separated. */
  dependencyPrefixDefault: string;
};

export function hostPaths(platform: NodeJS.Platform = process.platform): HostPaths {
  if (platform === "darwin") {
    return {
      pythonSite: "lib/python3.11/site-packages",
      rosUnderlayRoot: "/opt/ros/jazzy/install",
      rosUnderlaySite: "/opt/ros/jazzy/install/rclpy/lib/python3.11/site-packages",
      dependencyPrefixDefault:
        "/opt/data/so101/runtime/fork/current:/opt/ros/jazzy/extra_ws/install",
    };
  }
  return {
    pythonSite: "lib/python3.12/site-packages",
    rosUnderlayRoot: "/opt/ros/jazzy",
    rosUnderlaySite: "/opt/ros/jazzy/lib/python3.12/site-packages",
    dependencyPrefixDefault: "/data/work/ws_moveit/install",
  };
}

/**
 * The ROS underlay's Python search path for this host.
 *
 * ai-station installs ROS merged, so one directory carries every package. macOS installs it
 * isolated - `ament_index_python`, `rclpy` and each message package have a site directory of their
 * own - and the sourced overlays are what names them all. Re-deriving a single path there drops
 * everything except `rclpy`, which is how the installed entry died with
 * `ModuleNotFoundError: No module named 'ament_index_python'` before it could bind a port.
 *
 * A host with nothing sourced answers with nothing, rather than reaching for the other platform's
 * path and failing later with a missing-package error that names the wrong cause.
 */
export function hostUnderlayPythonPath(
  platform: NodeJS.Platform = process.platform,
  environment: Record<string, string | undefined> = process.env,
): string[] {
  if (platform === "darwin") {
    return (environment.PYTHONPATH ?? "").split(":").filter((entry) => entry !== "");
  }
  return ["/opt/ros/jazzy/lib/python3.12/site-packages"];
}

/** The ROS underlay's ament prefix path for this host, by the same rule. */
export function hostUnderlayPrefixPath(
  platform: NodeJS.Platform = process.platform,
  environment: Record<string, string | undefined> = process.env,
): string[] {
  if (platform === "darwin") {
    return (environment.AMENT_PREFIX_PATH ?? "").split(":").filter((entry) => entry !== "");
  }
  return ["/opt/ros/jazzy"];
}

/**
 * The installed execution document this host runs, as a basename under the config directory.
 *
 * `require_v3_execution` refuses new execution for any contract version but 3, and the v2 document
 * declares 2 - pointing the legacy host at it refused every preflight with
 * `CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION`, which then surfaced as a start refusal rather than as
 * the version problem it was. macOS resolves its profiles beside a macOS document, so the
 * deployment's own first-pass document is configured there.
 */
export function hostExecutionDocument(platform: NodeJS.Platform = process.platform): string {
  return platform === "darwin"
    ? "parallel_batch_v6_macos_mps_w1_first_pass.yaml"
    : "parallel_batch_v3.yaml";
}

/**
 * The campaign coordinator module, relative to the demo package's install prefix.
 *
 * Null means "leave the service's own default": ai-station's default is the coordinator it runs,
 * while macOS needs the one its campaigns actually use - without it the resource probe answers
 * `CoordinatorError` and every preflight is refused with `RESOURCE_PROBE_FAILED`.
 */
export function hostCoordinatorRelative(platform: NodeJS.Platform = process.platform): string | null {
  return platform === "darwin" ? "lib/so101_demo_py/so101_macos_service_campaign" : null;
}

export type ProcessReaders = {
  /** Raw `/proc/<pid>/stat`, or null when the file cannot be read. */
  readProc?: (pid: number) => string | null;
  /** The `ps -o stat=` field, or null when the process is gone. */
  runPs?: (pid: number) => string | null;
};

function defaultReaders(platform: NodeJS.Platform): Required<ProcessReaders> {
  return {
    readProc: (pid) => {
      try {
        return readFileSync(`/proc/${pid}/stat`, "utf-8");
      } catch {
        return null;
      }
    },
    runPs: (pid) => {
      try {
        const out = execFileSync("ps", ["-o", "stat=", "-p", String(pid)], {
          encoding: "utf-8",
        }).trim();
        return out === "" ? null : out;
      } catch {
        return null;
      }
    },
  };
}

/**
 * The process-state letter, or null when the process is gone.
 *
 * Darwin has no `/proc`, so it is asked through `ps`. Reading `/proc` there returns null for every
 * pid, which reads as "dead" - the opposite of a fail-closed default, so the platform decides which
 * reader is consulted rather than trying one and falling back.
 */
export function readProcessState(
  platform: NodeJS.Platform,
  pid: number,
  readers: ProcessReaders = {},
): string | null {
  const resolved = { ...defaultReaders(platform), ...readers };
  if (platform === "darwin") {
    const state = resolved.runPs(pid);
    if (state === null) return null;
    const letter = state.replace(/[^A-Za-z]/g, "").charAt(0).toUpperCase();
    return letter === "" ? null : letter;
  }
  const stat = resolved.readProc(pid);
  if (stat === null) return null;
  const close = stat.lastIndexOf(")");
  if (close === -1) return null;
  const field = stat.slice(close + 2).trim().split(/\s+/)[0];
  return field === undefined || field === "" ? null : field;
}

/** True while the process exists and is not a zombie. */
export function processAlive(
  pid: number,
  platform: NodeJS.Platform = process.platform,
  readers: ProcessReaders = {},
): boolean {
  const state = readProcessState(platform, pid, readers);
  return state !== null && state !== "Z";
}
