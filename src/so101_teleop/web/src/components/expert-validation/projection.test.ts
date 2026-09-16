import { describe, expect, test } from "vitest";

import fixture from "@/fixtures/top_view_projection_v1.json";
import { projectBounds, projectXY } from "./projection";

describe("expert validation projection", () => {
  test("matches every Python projection fixture point", () => {
    expect(projectXY(fixture.projection, 0.02, -0.28)).toEqual(fixture.p01_px);
    for (const point of fixture.points) {
      expect(projectXY(
        fixture.projection,
        point.position_world_m[0],
        point.position_world_m[1],
      )).toEqual(point.projected_px);
    }
  });

  test("uses one equal scale for geometry bounds", () => {
    const projected = projectBounds(fixture.projection, fixture.geometry.base_bounds);
    expect(projected.width).toBeCloseTo(0.18 * fixture.projection.pixels_per_m, 10);
    expect(projected.height).toBeCloseTo(0.18 * fixture.projection.pixels_per_m, 10);
  });
});
