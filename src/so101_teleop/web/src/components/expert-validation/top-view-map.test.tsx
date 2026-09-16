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
