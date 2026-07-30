import type { JointSample } from "@/api/types";
import { degreesToRadians, radiansToDegrees } from "@/lib/units";

export type SafeJointBounds = { lowerRad: number; upperRad: number };
export type JointClampResult = { value: number; clamped: boolean; unavailable?: boolean; message?: string };
export const JOINT_SAFETY_MARGIN_RAD = degreesToRadians(2);

export function safeJointBounds(sample: JointSample | undefined): SafeJointBounds | undefined {
  const lower = sample?.lower_limit_rad;
  const upper = sample?.upper_limit_rad;
  if (lower == null || upper == null || !Number.isFinite(lower) || !Number.isFinite(upper)) return undefined;
  const bounds = { lowerRad: lower + JOINT_SAFETY_MARGIN_RAD, upperRad: upper - JOINT_SAFETY_MARGIN_RAD };
  return bounds.lowerRad <= bounds.upperRad ? bounds : undefined;
}

export function clampJointTarget(joint: string, value: number, sample: JointSample | undefined): JointClampResult {
  const bounds = safeJointBounds(sample);
  if (!bounds) return { value, clamped: false, unavailable: true };
  const clampedValue = Math.min(bounds.upperRad, Math.max(bounds.lowerRad, value));
  if (clampedValue === value) return { value, clamped: false };
  return {
    value: clampedValue,
    clamped: true,
    message: `Joint ${joint} clamped to ${radiansToDegrees(clampedValue).toFixed(2)}° (2° safety margin).`,
  };
}
