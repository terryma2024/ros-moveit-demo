import type { Pose6D, StepFrame } from "@/api/types";

type Quaternion = [number, number, number, number];

export const degreesToRadians = (degrees: number) => degrees * Math.PI / 180;
export const radiansToDegrees = (radians: number) => radians * 180 / Math.PI;

function quaternionFromRpy(roll: number, pitch: number, yaw: number): Quaternion {
  const [cr, sr] = [Math.cos(roll / 2), Math.sin(roll / 2)];
  const [cp, sp] = [Math.cos(pitch / 2), Math.sin(pitch / 2)];
  const [cy, sy] = [Math.cos(yaw / 2), Math.sin(yaw / 2)];
  return [sr * cp * cy - cr * sp * sy, cr * sp * cy + sr * cp * sy, cr * cp * sy - sr * sp * cy, cr * cp * cy + sr * sp * sy];
}

function multiply(a: Quaternion, b: Quaternion): Quaternion {
  const [ax, ay, az, aw] = a; const [bx, by, bz, bw] = b;
  return [aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx, aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz];
}

function rpyFromQuaternion([x, y, z, w]: Quaternion): [number, number, number] {
  const roll = Math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y));
  const pitchInput = 2 * (w * y - z * x);
  const pitch = Math.asin(Math.max(-1, Math.min(1, pitchInput)));
  const yaw = Math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z));
  return [roll, pitch, yaw];
}

function rotateVector([x, y, z, w]: Quaternion, vector: [number, number, number]): [number, number, number] {
  const rotated = multiply(multiply([x, y, z, w], [vector[0], vector[1], vector[2], 0]), [-x, -y, -z, w]);
  return [rotated[0], rotated[1], rotated[2]];
}

export function applyPoseStep(pose: Pose6D, axis: keyof Pick<Pose6D, "x_m" | "y_m" | "z_m" | "roll_rad" | "pitch_rad" | "yaw_rad">, direction: -1 | 1, frame: StepFrame): Pose6D {
  if (axis.endsWith("_m")) {
    const offset: [number, number, number] = [axis === "x_m" ? direction * 0.001 : 0, axis === "y_m" ? direction * 0.001 : 0, axis === "z_m" ? direction * 0.001 : 0];
    const worldOffset = frame === "TOOL" ? rotateVector(quaternionFromRpy(pose.roll_rad, pose.pitch_rad, pose.yaw_rad), offset) : offset;
    return { ...pose, x_m: pose.x_m + worldOffset[0], y_m: pose.y_m + worldOffset[1], z_m: pose.z_m + worldOffset[2] };
  }
  const angle = direction * degreesToRadians(1);
  const delta = quaternionFromRpy(axis === "roll_rad" ? angle : 0, axis === "pitch_rad" ? angle : 0, axis === "yaw_rad" ? angle : 0);
  const current = quaternionFromRpy(pose.roll_rad, pose.pitch_rad, pose.yaw_rad);
  const [roll_rad, pitch_rad, yaw_rad] = rpyFromQuaternion(frame === "WORLD" ? multiply(delta, current) : multiply(current, delta));
  return { ...pose, roll_rad, pitch_rad, yaw_rad };
}
