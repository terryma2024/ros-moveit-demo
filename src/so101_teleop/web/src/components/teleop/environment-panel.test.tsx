// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";
import { EnvironmentPanel, TELEOP_ENVIRONMENT_KEYS } from "./environment-panel";

function renderPanel(environment: Record<string, string>) {
  return render(<TooltipProvider><EnvironmentPanel environment={environment} /></TooltipProvider>);
}

describe("EnvironmentPanel", () => {
  beforeEach(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
  });

  it("renders the approved environment keys in a stable order without inventing missing values", () => {
    renderPanel({ ROS_DOMAIN_ID: "55", GZ_PARTITION: "partition-a" });

    expect(screen.getAllByTestId("environment-key").map((node) => node.textContent)).toEqual([
      "ROS_DOMAIN_ID", "ROS_DISTRO", "ROS_VERSION", "ROS_PYTHON_VERSION",
      "ROS_AUTOMATIC_DISCOVERY_RANGE", "AMENT_PREFIX_PATH", "COLCON_PREFIX_PATH",
      "GZ_PARTITION", "GZ_CONFIG_PATH", "GZ_SIM_RESOURCE_PATH",
      "GZ_SIM_SYSTEM_PLUGIN_PATH", "PYTHONPATH", "LD_LIBRARY_PATH",
    ]);
    expect(TELEOP_ENVIRONMENT_KEYS).toHaveLength(13);
    expect(screen.getByTitle("ROS_DOMAIN_ID=55").textContent).toBe("55");
    expect(screen.getByTitle("ROS_DISTRO unavailable").textContent).toBe("—");
  });

  it("shows immutable backend provenance separately from the environment", () => {
    render(<TooltipProvider><EnvironmentPanel
      environment={{}}
      backend={{ backend: "gazebo_py", owner_package: "so101_demo_py" }}
    /></TooltipProvider>);

    expect(screen.getByText("gazebo_py")).toBeTruthy();
    expect(screen.getByText("so101_demo_py")).toBeTruthy();
  });

  it("copies the complete value even when the visible cell is bounded", async () => {
    const longValue = "/opt/ros/jazzy:" + "/data/work/ws_moveit/install:".repeat(20);
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText");
    renderPanel({ LD_LIBRARY_PATH: longValue });

    const value = screen.getByTitle(`LD_LIBRARY_PATH=${longValue}`);
    expect(value.className).toContain("break-all");
    await user.click(screen.getByRole("button", { name: "Copy LD_LIBRARY_PATH" }));
    expect(writeText).toHaveBeenCalledWith(longValue);
  });
});
