import { describe, expect, it } from "vitest";

import type { JointSample } from "@/api/types";
import { clampJointTarget, safeJointBounds } from "./joint-limits";

const limited: JointSample = {
  name: "3",
  position_rad: 0,
  velocity_rad_s: 0,
  lower_limit_rad: -1.74533,
  upper_limit_rad: 1.5708,
};

describe("joint safe target limits", () => {
  it("insets both hard limits by exactly two degrees", () => {
    expect(safeJointBounds(limited)).toEqual({
      lowerRad: -1.7104234149601134,
      upperRad: 1.5358934149601133,
    });
  });

  it("passes an in-range target through without a notice", () => {
    expect(clampJointTarget("3", 0.5, limited)).toEqual({ value: 0.5, clamped: false });
  });

  it("stops targets at either safe boundary and identifies the joint", () => {
    expect(clampJointTarget("3", -9, limited)).toEqual({
      value: -1.7104234149601134,
      clamped: true,
      message: "Joint 3 clamped to -98.00° (2° safety margin).",
    });
    expect(clampJointTarget("3", 9, limited)).toEqual({
      value: 1.5358934149601133,
      clamped: true,
      message: "Joint 3 clamped to 88.00° (2° safety margin).",
    });
  });

  it("fails closed when either hard limit is unavailable", () => {
    expect(safeJointBounds({ ...limited, upper_limit_rad: undefined })).toBeUndefined();
    expect(clampJointTarget("3", 0.5, { ...limited, lower_limit_rad: undefined })).toEqual({
      value: 0.5,
      clamped: false,
      unavailable: true,
    });
  });
});
