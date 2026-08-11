// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { TcpPanel } from "./tcp-panel";

const pose = { frame_id: "world", tcp_frame: "so101_tcp", x_m: 0.02, y_m: -0.28, z_m: 0.2, roll_rad: 0, pitch_rad: 0, yaw_rad: 0 };

describe("TcpPanel", () => {
  it("disables manual TCP operations when the backend capability is false", () => {
    render(<TcpPanel pose={pose} frame="WORLD" leaseHeld manualTcpExecute={false} plan={{ executable: true }} onFrame={vi.fn()} onEdit={vi.fn()} onStep={vi.fn()} onPlan={vi.fn()} onExecute={vi.fn()} onCancel={vi.fn()} />);
    expect((screen.getByRole("button", { name: "Plan TCP" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Execute planned TCP" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Cancel TCP" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows a duplicate-safe pending state while TCP IK planning is in progress", () => {
    render(<TcpPanel pose={pose} frame="WORLD" leaseHeld planning plan={{ executable: false }} onFrame={vi.fn()} onEdit={vi.fn()} onStep={vi.fn()} onPlan={vi.fn()} onExecute={vi.fn()} onCancel={vi.fn()} />);
    expect((screen.getByRole("button", { name: "Planning TCP…" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByRole("button", { name: "Plan TCP" })).toBeNull();
  });
  it("sends Tool-frame fixed steps after the operator selects Tool", async () => {
    const onFrame = vi.fn(); const onStep = vi.fn(); const user = userEvent.setup();
    render(<TcpPanel pose={pose} frame="WORLD" leaseHeld plan={{ executable: false }} onFrame={onFrame} onEdit={vi.fn()} onStep={onStep} onPlan={vi.fn()} onExecute={vi.fn()} onCancel={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Tool frame" }));
    expect(onFrame).toHaveBeenCalledWith("TOOL");
    await user.click(screen.getByRole("button", { name: "X +1 mm" }));
    expect(onStep).toHaveBeenCalledWith("x_m", 1);
  });

  it("renders an accessible segmented ButtonGroup with visible active state and keyboard activation", async () => {
    const onFrame = vi.fn(); const user = userEvent.setup();
    render(<TcpPanel pose={pose} frame="WORLD" leaseHeld plan={{ executable: false }} onFrame={onFrame} onEdit={vi.fn()} onStep={vi.fn()} onPlan={vi.fn()} onExecute={vi.fn()} onCancel={vi.fn()} />);
    const group = screen.getByRole("group", { name: "TCP step frame" });
    const world = screen.getByRole("button", { name: "World frame" });
    const tool = screen.getByRole("button", { name: "Tool frame" });
    expect(group.dataset.slot).toBe("button-group");
    expect(world.getAttribute("aria-pressed")).toBe("true");
    expect(tool.getAttribute("aria-pressed")).toBe("false");
    expect(world.className).toContain("bg-sky-600");
    expect(group.className).not.toMatch(/(?:^|\s)gap-/);
    tool.focus();
    await user.keyboard("{Enter}");
    expect(onFrame).toHaveBeenCalledWith("TOOL");
  });
});
