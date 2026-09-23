/**
 * The installed suite's host rules, exercised offline.
 *
 * `playwright.installed.config.ts` was written against ai-station and cannot run on macOS: it sends
 * `contract_version: 2` where the service accepts only 3, reads `/proc/<pid>/stat` for liveness,
 * builds `PYTHONPATH` from `lib/python3.12/site-packages` and `/opt/ros/jazzy`, and asks for an
 * ADAPTIVE route macOS does not carry. Twenty-four of its twenty-five tests fail on this host for
 * those reasons, and every one of them is a host assumption rather than a missing feature.
 *
 * The rules are the ones the live fixtures already follow: a platform-bound host is answered by its
 * own support matrix, the executable layout comes from the platform, and liveness is read through
 * whatever the platform actually provides. Linux behaviour is unchanged - the matrix rules do not
 * apply where there is no matrix, `python3.12` stays the suffix, and `/proc` stays the reader.
 */

import { describe, expect, it } from "vitest";

import type { CapabilitiesDocument } from "../../e2e/expert-validation/fixtures/functional-cases";
import {
  EXECUTION_CONTRACT_VERSION,
  hostCoordinatorRelative,
  hostExecutionDocument,
  hostPaths,
  hostRoute,
  hostUnderlayPrefixPath,
  hostUnderlayPythonPath,
  readProcessState,
} from "../../e2e/expert-validation/fixtures/host-routes";

/** The matrix this host actually serves, as the deployed service publishes it. */
const MACOS: CapabilitiesDocument = {
  platform: "macos",
  execution_modes: ["SEQUENTIAL", "PARALLEL"],
  fixed_worker_counts: [1, 2],
  worker_count_availability: [
    { worker_count: 1, selectable: true },
    { worker_count: 2, selectable: true },
    { worker_count: 3, selectable: false, reason_codes: ["UNSUPPORTED_ON_MACOS"] },
    { worker_count: 4, selectable: false, reason_codes: ["UNSUPPORTED_ON_MACOS"] },
  ],
  support_matrix: [
    { profile: "MPS_W2_FIRST_PASS", schema_version: 4, execution_mode: "PARALLEL", worker_count: 2, batch_kind: "FIRST_PASS" },
    { profile: "MPS_W1_FIRST_PASS", schema_version: 6, execution_mode: "SEQUENTIAL", worker_count: 1, batch_kind: "FIRST_PASS" },
    { profile: "MPS_W1_FULL_RESTART_RETRY", schema_version: 5, execution_mode: "SEQUENTIAL", worker_count: 1, batch_kind: "FULL_RESTART_RETRY" },
  ],
  start_guard_policy: { timeout_s: 600 },
};

/** ai-station: per-N availability plus the adaptive ladder, and no matrix at all. */
const LINUX: CapabilitiesDocument = {
  platform: "linux",
  execution_modes: ["SEQUENTIAL", "PARALLEL", "ADAPTIVE"],
  fixed_worker_counts: [1, 2, 4],
  worker_count_availability: [
    { worker_count: 1, selectable: true },
    { worker_count: 2, selectable: true },
    { worker_count: 4, selectable: true },
  ],
  support_matrix: [],
  start_guard_policy: { timeout_s: 600 },
};

describe("execution contract version", () => {
  it("is the version the service accepts", () => {
    expect(EXECUTION_CONTRACT_VERSION).toBe(3);
  });
});

describe("hostRoute", () => {
  it("names the matrix row a platform-bound host serves", () => {
    const route = hostRoute(MACOS, { mode: "PARALLEL", workerCount: 2, batchKind: "FIRST_PASS" });
    expect(route.runnable).toBe(true);
    expect(route.platformBound).toBe(true);
    if (route.runnable) expect(route.profile).toBe("MPS_W2_FIRST_PASS");
  });

  it("refuses a shape the platform-bound matrix does not carry, with its reason", () => {
    const route = hostRoute(MACOS, { mode: "ADAPTIVE", workerCount: 2, batchKind: "FIRST_PASS" });
    expect(route.runnable).toBe(false);
    if (!route.runnable) expect(route.reason).toBe("UNSUPPORTED_ON_MACOS");
  });

  it("refuses a worker count the host marks unselectable", () => {
    const route = hostRoute(MACOS, { mode: "PARALLEL", workerCount: 4, batchKind: "FIRST_PASS" });
    expect(route.runnable).toBe(false);
    if (!route.runnable) expect(route.reason).toBe("UNSUPPORTED_ON_MACOS");
  });

  it("keeps the legacy host runnable for everything it advertises", () => {
    for (const request of [
      { mode: "SEQUENTIAL", workerCount: 1, batchKind: "FIRST_PASS" },
      { mode: "PARALLEL", workerCount: 2, batchKind: "FIRST_PASS" },
      { mode: "ADAPTIVE", workerCount: 2, batchKind: "FIRST_PASS" },
    ] as const) {
      const route = hostRoute(LINUX, request);
      expect(route.runnable, `${request.mode}/${request.workerCount}`).toBe(true);
      expect(route.platformBound).toBe(false);
      if (route.runnable) expect(route.profile).toBeNull();
    }
  });

  it("refuses an unadvertised mode on the legacy host too", () => {
    const route = hostRoute(
      { ...LINUX, execution_modes: ["SEQUENTIAL", "PARALLEL"] },
      { mode: "ADAPTIVE", workerCount: 2, batchKind: "FIRST_PASS" },
    );
    expect(route.runnable).toBe(false);
    if (!route.runnable) expect(route.reason).toBe("MODE_NOT_ADVERTISED");
  });
});

describe("hostPaths", () => {
  it("keeps ai-station's layout on linux", () => {
    const paths = hostPaths("linux");
    expect(paths.pythonSite).toBe("lib/python3.12/site-packages");
    expect(paths.rosUnderlayRoot).toBe("/opt/ros/jazzy");
    expect(paths.rosUnderlaySite).toBe("/opt/ros/jazzy/lib/python3.12/site-packages");
  });

  it("uses this Mac's layout on darwin", () => {
    const paths = hostPaths("darwin");
    expect(paths.pythonSite).toBe("lib/python3.11/site-packages");
    expect(paths.rosUnderlayRoot).toBe("/opt/ros2_jazzy/install");
    expect(paths.rosUnderlaySite).toBe("/opt/ros2_jazzy/install/rclpy/lib/python3.11/site-packages");
  });
});

describe("the underlay search path", () => {
  it("keeps the merged linux underlay", () => {
    expect(hostUnderlayPythonPath("linux", {})).toEqual(["/opt/ros/jazzy/lib/python3.12/site-packages"]);
    expect(hostUnderlayPrefixPath("linux", {})).toEqual(["/opt/ros/jazzy"]);
  });

  it("inherits every site directory the darwin overlays already name", () => {
    // The macOS ROS install is isolated: `ament_index_python`, `rclpy` and the message packages
    // each carry their own site directory, so naming one of them drops the rest and the server
    // dies on `ModuleNotFoundError: No module named 'ament_index_python'` before it can serve.
    const environment = {
      PYTHONPATH: "/opt/ros2_jazzy/install/ament_index_python/lib/python3.11/site-packages"
        + ":/opt/ros2_jazzy/install/rclpy/lib/python3.11/site-packages",
      AMENT_PREFIX_PATH: "/opt/data/so101/workspace/install/so101_teleop:/opt/ros2_jazzy/install/rclpy",
    };
    expect(hostUnderlayPythonPath("darwin", environment)).toEqual([
      "/opt/ros2_jazzy/install/ament_index_python/lib/python3.11/site-packages",
      "/opt/ros2_jazzy/install/rclpy/lib/python3.11/site-packages",
    ]);
    expect(hostUnderlayPrefixPath("darwin", environment)).toEqual([
      "/opt/data/so101/workspace/install/so101_teleop",
      "/opt/ros2_jazzy/install/rclpy",
    ]);
  });

  it("answers with nothing rather than a linux path when darwin has no overlay sourced", () => {
    expect(hostUnderlayPythonPath("darwin", {})).toEqual([]);
    expect(hostUnderlayPrefixPath("darwin", {})).toEqual([]);
  });
});

describe("readProcessState", () => {
  it("reads the state field of a live linux process", () => {
    expect(readProcessState("linux", 42, { readProc: () => "42 (node) S 1 42 42 0 -1" })).toBe("S");
  });

  it("treats a linux zombie as not alive", () => {
    expect(readProcessState("linux", 42, { readProc: () => "42 (node) Z 1 42 42 0 -1" })).toBe("Z");
  });

  it("reports an absent process as null on both platforms", () => {
    expect(readProcessState("linux", 42, { readProc: () => null })).toBeNull();
    expect(readProcessState("darwin", 42, { runPs: () => null })).toBeNull();
  });

  it("reads darwin liveness from ps instead of /proc", () => {
    let askedForProc = false;
    const state = readProcessState("darwin", 42, {
      readProc: () => {
        askedForProc = true;
        return null;
      },
      runPs: () => "S+",
    });
    expect(state).toBe("S");
    expect(askedForProc, "darwin must not consult /proc").toBe(false);
  });
});

describe("the execution document and coordinator this host runs", () => {
  it("names the active execution document and its own coordinator default on linux", () => {
    // `require_v3_execution` refuses new execution for any contract version but 3, and the installed
    // v2 document declares 2. The gate runner and the plan's own profiles are v3/v4/v5/v6 for that
    // reason; pointing the legacy host at v2 refused every preflight with
    // CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION.
    expect(hostExecutionDocument("linux")).toBe("parallel_batch_v3.yaml");
    expect(hostCoordinatorRelative("linux")).toBeNull();
  });

  it("names the macOS profile document and the macOS coordinator on darwin", () => {
    // The probe admitted nothing with the legacy v2 document here: its rows are the ai-station
    // ladder, and the macOS profiles resolve only beside a macOS document.
    expect(hostExecutionDocument("darwin")).toBe("parallel_batch_v6_macos_mps_w1_first_pass.yaml");
    expect(hostCoordinatorRelative("darwin")).toBe(
      "lib/so101_demo_py/so101_macos_service_campaign",
    );
  });
});
