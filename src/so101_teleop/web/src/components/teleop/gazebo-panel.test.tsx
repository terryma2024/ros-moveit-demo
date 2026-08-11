// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { GazeboPanel } from "./gazebo-panel";

describe("GazeboPanel camera presets", () => {
  it("shows configured presets and applies the selected view", async () => {
    const onCameraPreset = vi.fn();
    render(<GazeboPanel
      leaseHeld={true}
      cameraPresets={["overview", "top", "side"]}
      onCameraPreset={onCameraPreset}
      onScreenshot={vi.fn()}
      onAttach={vi.fn()}
      onDetach={vi.fn()}
      onRepair={vi.fn()}
      onHome={vi.fn()}
      onReset={vi.fn()}
    />);

    await userEvent.click(screen.getByRole("button", { name: "Top" }));

    expect(onCameraPreset).toHaveBeenCalledWith("top");
  });

  it("disables camera controls without a control lease", () => {
    render(<GazeboPanel
      leaseHeld={false}
      cameraPresets={["overview"]}
      onCameraPreset={vi.fn()}
      onScreenshot={vi.fn()}
      onAttach={vi.fn()}
      onDetach={vi.fn()}
      onRepair={vi.fn()}
      onHome={vi.fn()}
      onReset={vi.fn()}
    />);

    expect((screen.getByRole("button", { name: "Overview" }) as HTMLButtonElement).disabled).toBe(true);
  });
});
