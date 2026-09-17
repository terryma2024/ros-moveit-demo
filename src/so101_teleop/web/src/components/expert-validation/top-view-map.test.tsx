// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import fixture from "@/fixtures/top_view_projection_v1.json";
import { TopViewMap, type MapPointState } from "./top-view-map";

function renderState(state: MapPointState, options: Record<string, unknown> = {}) {
  return render(
    <TopViewMap
      manifest={fixture}
      campaign={{
        points: fixture.points.map((point, index) => ({
          point_id: point.id,
          status: index === 0 ? state : "ELIGIBLE_UNRUN",
          active_worker_id: index === 0 ? (options.activeWorkerId as string | undefined) : undefined,
          phase: index === 0 ? "EXECUTING" : undefined,
          reason: index === 0 ? (options.reason as string | undefined) : undefined,
        })),
      }}
      selectedPointId={options.selectedPointId as string | undefined}
      onSelect={(options.onSelect as (id: string) => void) ?? (() => undefined)}
    />,
  );
}

describe("TopViewMap", () => {
  test("trims legacy canvas whitespace while retaining measured outlying labels and selection clearance", () => {
    // jsdom has no SVG layout engine. Supply the browser-measured content envelope,
    // including a label outside the table, rather than mocking projection math.
    const measured = { x: 265, y: 48, width: 800, height: 804 };
    const original = Object.getOwnPropertyDescriptor(SVGElement.prototype, "getBBox");
    Object.defineProperty(SVGElement.prototype, "getBBox", { configurable: true, value: () => measured });
    try {
      const { container, rerender } = renderState("PASSED");
      const svg = container.querySelector("svg")!;
      const [x, y, width, height] = svg.getAttribute("viewBox")!.split(" ").map(Number);
      expect(width).toBeLessThan(fixture.projection.width_px);
      expect(x).toBeLessThan(measured.x);
      expect(y).toBeLessThan(measured.y);
      expect(x + width).toBeGreaterThan(measured.x + measured.width);
      expect(y + height).toBeGreaterThan(measured.y + measured.height);
      const initial = svg.getAttribute("viewBox");
      rerender(<TopViewMap manifest={fixture} campaign={{ points: [] }}
        selectedPointId="task_start" onSelect={() => {}} />);
      expect(container.querySelector('[data-focus-ring="task_start"]')).toBeTruthy();
      expect(svg.getAttribute("viewBox")).toBe(initial);
    } finally {
      if (original) Object.defineProperty(SVGElement.prototype, "getBBox", original);
      else delete (SVGElement.prototype as unknown as Record<string, unknown>).getBBox;
    }
  });
  test("world grid remains inside the server-provided table rather than baseline bounds", () => {
    const serverManifest = { ...fixture,
      geometry: { ...fixture.geometry, table_bounds: [-0.1, 0.1, -0.35, -0.2] },
      projection: { ...fixture.projection, bounds_m: [-0.1, 0.1, -0.35, -0.2],
        pixels_per_m: 3000, offset_x_px: 600, offset_y_px: -375 },
    };
    const { container } = render(<TopViewMap manifest={serverManifest} campaign={{ points: [] }} onSelect={() => {}} />);
    const lines = Array.from(container.querySelectorAll("line"));
    expect(lines.length).toBeGreaterThan(0);
    for (const line of lines) {
      for (const key of ["x1", "x2"]) expect(Number(line.getAttribute(key))).toBeGreaterThanOrEqual(300);
      for (const key of ["x1", "x2"]) expect(Number(line.getAttribute(key))).toBeLessThanOrEqual(900);
      for (const key of ["y1", "y2"]) expect(Number(line.getAttribute(key))).toBeGreaterThanOrEqual(225);
      for (const key of ["y1", "y2"]) expect(Number(line.getAttribute(key))).toBeLessThanOrEqual(675);
    }
  });

  test.each([
    ["ELIGIBLE_UNRUN", "blue"],
    ["LEASED", "blue"],
    ["EXECUTING", "blue"],
    ["INFRA_INTERRUPTED_REQUEUEABLE", "blue"],
    ["PASSED", "green"],
    ["FAILED", "red"],
    ["INDETERMINATE", "red"],
    ["TERMINAL_UNRUN", "red"],
    ["INVALID_BLOCKED", "red"],
    ["INFRA_FAILED_REMAINDER", "red"],
  ] as const)("renders %s with %s semantic style", (state, color) => {
    renderState(state);
    expect(screen.getByLabelText(/P01/).getAttribute("data-color")).toBe(color);
  });

  test("renders stable geometry and all equal-radius markers", () => {
    const { container } = renderState("PASSED");
    expect(container.querySelector('[data-geometry="table"]')).toBeTruthy();
    expect(container.querySelector('[data-geometry="base"]')).toBeTruthy();
    expect(container.querySelector('[data-geometry="target-tolerance"]')).toBeTruthy();
    const markers = Array.from(container.querySelectorAll("[data-point-id]"));
    expect(markers).toHaveLength(20);
    expect(new Set(markers.map((marker) => marker.getAttribute("data-radius")))).toEqual(
      new Set([String(fixture.marker_radius_px)]),
    );
  });

  test("selection adds a focus ring while an active Worker only strengthens stroke", () => {
    const { container } = renderState("EXECUTING", {
      activeWorkerId: "worker-2",
      selectedPointId: "task_start",
    });
    const point = screen.getByLabelText(/P01/);
    expect(point.getAttribute("data-active-worker")).toBe("worker-2");
    expect(point.getAttribute("data-selected")).toBe("true");
    expect(container.querySelector('[data-focus-ring="task_start"]')).toBeTruthy();
  });

  test("point selection works with click and keyboard", () => {
    const onSelect = vi.fn();
    renderState("FAILED", { onSelect, reason: "UNREACHABLE" });
    const point = screen.getByLabelText(/P01.*UNREACHABLE/);
    fireEvent.click(point);
    fireEvent.keyDown(point, { key: "Enter" });
    expect(onSelect).toHaveBeenNthCalledWith(1, "task_start");
    expect(onSelect).toHaveBeenNthCalledWith(2, "task_start");
  });
});
