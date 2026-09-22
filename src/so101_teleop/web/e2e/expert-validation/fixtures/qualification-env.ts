/**
 * The qualification environment the installed fixtures hand to the production server.
 *
 * The installed gate *spawns* that server and passes this document as its environment, so anything
 * written here overrides what the operator exported. Every model and acceptance location in it used
 * to be an absolute ai-station path under `/data/work`, which made the gate unrunnable anywhere else:
 * on macOS the server refused to start with `SO101_VALIDATION_YOLO_WEIGHTS_INVALID` - the file it was
 * pointed at cannot exist off ai-station - and all twenty-five installed specs failed in about
 * 630 ms each.
 *
 * The rule is the one the durable-root fixture already follows for the same class of value: evidence
 * that lives in ai-station's tree is asserted only where that tree can exist. On a platform-bound
 * host the locations come from the environment the operator supplies; a host-independent entry keeps
 * its constant, because none of those is a filesystem location. An ambient value always wins, on
 * either platform, so the gate can still be pointed at fresh artifacts without editing this file.
 */

/** Model and acceptance locations as they exist on ai-station. Never asserted where `/data` cannot exist. */
export const AI_STATION_QUALIFICATION_PATHS = {
  SO101_VALIDATION_YOLO_WEIGHTS:
    "/data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/models/yolo/best.pt",
  SO101_VALIDATION_GROUNDED_ROOT: "/data/work/so101-models/grounded-sam-v2-scipy-lock",
  SO101_VALIDATION_PARALLEL_ACCEPTANCE:
    "/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-20-f91/aggregate_results.json",
  SO101_VALIDATION_ADAPTIVE_ACCEPTANCE:
    "/data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/e2001/aggregate_results.json",
  SO101_VALIDATION_ADAPTIVE_FAULT_INJECTION:
    "/data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/su09/aggregate_results.json",
} as const;

/** Entry that names no filesystem location, so it reads the same on every host. */
export const HOST_INDEPENDENT_QUALIFICATION = {
  SO101_VALIDATION_BROKER_IMAGE: "so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1",
  SO101_VALIDATION_ADAPTIVE_PERFORMANCE_TIERS: "1,2,4,6,8",
} as const;

export type QualificationEnvDeps = {
  /** Injectable so the branch that cannot exist on this host is still exercised offline. */
  platform?: NodeJS.Platform;
  environment?: Record<string, string | undefined>;
};

/**
 * Resolve the qualification environment for the platform.
 *
 * An empty ambient value counts as unset, so an exported `KEY=` cannot silently shadow a default
 * with an empty string.
 */
export function qualificationEnvironment(deps: QualificationEnvDeps = {}): Record<string, string> {
  const platform = deps.platform ?? process.platform;
  const environment = deps.environment ?? process.env;
  const resolved: Record<string, string> = {};
  for (const [key, constant] of Object.entries(HOST_INDEPENDENT_QUALIFICATION)) {
    const ambient = environment[key];
    resolved[key] = ambient ? ambient : constant;
  }
  for (const [key, aiStationPath] of Object.entries(AI_STATION_QUALIFICATION_PATHS)) {
    const ambient = environment[key];
    if (ambient) {
      resolved[key] = ambient;
      continue;
    }
    if (platform === "darwin") continue;
    resolved[key] = aiStationPath;
  }
  return resolved;
}
