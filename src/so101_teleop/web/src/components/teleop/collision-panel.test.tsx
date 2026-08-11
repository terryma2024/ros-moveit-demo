// @vitest-environment jsdom
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";
import { CollisionPanel, formatAge, formatDepth, formatPoseCoordinate } from "./collision-panel";

const pose = {
  frame_id: "world",
  tcp_frame: "plastic_cup",
  x_m: 0.0199997,
  y_m: -0.2800001,
  z_m: 0.1649999,
  roll_rad: 0,
  pitch_rad: 0,
  yaw_rad: 0,
};

function renderPanel(overrides: Partial<React.ComponentProps<typeof CollisionPanel>> = {}) {
  return render(<TooltipProvider><CollisionPanel
    objectPose={pose}
    controllers={{ arm_controller: "active", gripper_controller: "inactive" }}
    sourceAges={{ joints: 0.0156, tcp: 0, object: 100.25, gazebo_contacts: 1.2, moveit_collisions: 2.3 }}
    moveit={[]}
    gazebo={[]}
    {...overrides}
  /></TooltipProvider>);
}

describe("CollisionPanel formatters", () => {
  it("formats operator values with fixed units and normalizes tiny negative depth", () => {
    expect(formatPoseCoordinate(0.0199997)).toBe("0.020 m");
    expect(formatAge(0.0156)).toBe("0.016 s");
    expect(formatAge(100.25)).toBe(">99.999 s");
    expect(formatDepth(-7.2349e-9)).toBe("0.000 mm");
    expect(formatDepth(0.0012345)).toBe("1.234 mm");
  });
});

describe("CollisionPanel", () => {
  it("renders structured telemetry in a fixed order without raw JSON", () => {
    renderPanel();
    const summary = screen.getByLabelText("Telemetry summary");
    expect(summary.textContent).not.toContain("{");
    expect(summary.textContent).not.toContain("arm_controller");
    expect(within(summary).getByText("X").compareDocumentPosition(within(summary).getByText("Y")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(summary).getByText("Y").compareDocumentPosition(within(summary).getByText("Z")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(summary).getByText("Arm")).toBeTruthy();
    expect(within(summary).getByText("Gripper")).toBeTruthy();
    for (const value of ["0.020 m", "-0.280 m", "0.165 m", "0.016 s", ">99.999 s", "—"]) {
      expect(within(summary).getByText(value)).toBeTruthy();
    }
    const labels = ["joints", "tcp", "object", "gazebo contacts", "MoveIt collisions", "scene"];
    const positions = labels.map((label) => within(summary).getByText(label).compareDocumentPosition(summary) ? within(summary).getByText(label) : null);
    expect(positions.every(Boolean)).toBe(true);
    expect(within(summary).getByTitle("joints: 0.0156")).toBeTruthy();
  });

  it("keeps both evidence panes, scroll structure, exact titles and truncated cells", () => {
    const longName = "plastic_cup::body::" + "very_long_collision_name_".repeat(8);
    renderPanel({
      moveit: [{ object_a: longName, object_b: "jaw", depth_m: 0.0012345, source: "moveit_collision_source_with_long_name" }],
      gazebo: [{ object_a: "cup", object_b: "table", depth_m: -7.2349e-9, source: "gazebo_contacts" }],
    });
    const moveit = screen.getByLabelText("MoveIt evidence pane");
    const gazebo = screen.getByLabelText("Gazebo evidence pane");
    expect(within(moveit).getByRole("table", { name: "MoveIt collisions" })).toBeTruthy();
    expect(within(gazebo).getByRole("table", { name: "Gazebo contacts" })).toBeTruthy();
    expect(within(moveit).getByTitle(longName).className).toContain("truncate");
    expect(within(moveit).getByTitle("0.0012345 m").textContent).toBe("1.234 mm");
    expect(within(gazebo).getByTitle("-7.2349e-9 m").textContent).toBe("0.000 mm");
    expect(moveit.className).toContain("h-56");
    expect(gazebo.className).toContain("h-56");
  });

  it("uses equal-height empty states when evidence is unavailable", () => {
    renderPanel({ objectPose: undefined, controllers: {}, sourceAges: {}, moveit: [], gazebo: [] });
    expect(screen.getAllByText("No evidence")).toHaveLength(2);
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(9);
  });
});
