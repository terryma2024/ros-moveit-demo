import { parse, stringify } from "yaml";

import type { ReplayableTarget } from "@/api/types";

export function serializeTargetYaml(target: ReplayableTarget): string {
  return stringify({ version: 1, target });
}

export function parseTargetYaml(text: string): ReplayableTarget {
  const document = parse(text);
  const target = document?.target;
  if (document?.version !== 1 || !target || !["WORLD", "TOOL"].includes(target.step_frame) || typeof target.joints_rad !== "object" || typeof target.tcp !== "object") {
    throw new Error("TARGET_YAML_INVALID");
  }
  const numericPose = ["x_m", "y_m", "z_m", "roll_rad", "pitch_rad", "yaw_rad"].every((key) => Number.isFinite(target.tcp[key]));
  const numericJoints = Object.values(target.joints_rad).every(Number.isFinite);
  if (!numericPose || !numericJoints || typeof target.tcp.frame_id !== "string" || typeof target.tcp.tcp_frame !== "string") {
    throw new Error("TARGET_YAML_INVALID");
  }
  return target as ReplayableTarget;
}
