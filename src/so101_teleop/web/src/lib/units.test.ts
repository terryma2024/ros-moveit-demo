import { describe, expect, it } from "vitest";

import { applyPoseStep, degreesToRadians } from "./units";

const base = { frame_id: "world", tcp_frame: "so101_tcp", x_m: 0.02, y_m: -0.28, z_m: 0.2, roll_rad: 0, pitch_rad: 0, yaw_rad: 0 };

describe("fixed teleop units", () => {
  it("steps World Y by exactly one millimetre", () => {
    expect(applyPoseStep(base, "y_m", 1, "WORLD").y_m).toBeCloseTo(-0.279, 12);
  });

  it("maps Tool X to World Y at ninety-degree yaw", () => {
    const yaw90 = { ...base, yaw_rad: Math.PI / 2 };
    const stepped = applyPoseStep(yaw90, "x_m", 1, "TOOL");
    expect(stepped.x_m).toBeCloseTo(0.02, 12);
    expect(stepped.y_m).toBeCloseTo(-0.279, 12);
  });

  it("uses exactly one degree for angular steps", () => {
    expect(degreesToRadians(1)).toBeCloseTo(Math.PI / 180, 15);
  });
});
