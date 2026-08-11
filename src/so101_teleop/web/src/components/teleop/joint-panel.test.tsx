// @vitest-environment jsdom
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { JointPanel } from "./joint-panel";

describe("JointPanel", () => {
  it("disables manual joint operations when the backend capability is false", () => {
    render(<JointPanel joints={{}} targets={{}} leaseHeld plan={{ executable: true }} manualJointExecute={false} onEdit={vi.fn()} onPlan={vi.fn()} onExecute={vi.fn()} onExecuteGripper={vi.fn()} onExecuteAll={vi.fn()} onCancel={vi.fn()} />);

    for (const name of ["Plan Arm", "Execute Arm", "Cancel", "Execute gripper", "Execute All"]) {
      expect((screen.getByRole("button", { name }) as HTMLButtonElement).disabled).toBe(true);
    }
  });

  it("blocks planning without a lease and explains the safety gate", () => {
    render(<JointPanel joints={{}} targets={{}} leaseHeld={false} plan={{ executable: false }} onEdit={vi.fn()} onPlan={vi.fn()} onExecute={vi.fn()} onExecuteGripper={vi.fn()} onExecuteAll={vi.fn()} onCancel={vi.fn()} />);
    expect((screen.getByRole("button", { name: "Plan Arm" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByRole("button", { name: "Plan joints" })).toBeNull();
    expect(screen.getByText("Acquire a control lease before planning.")).toBeTruthy();
  });

  it("exposes Execute All only for a fresh server-owned plan", () => {
    render(<JointPanel joints={{}} targets={{ "6": -0.04 }} leaseHeld plan={{ id: "p1", executable: true }} onEdit={vi.fn()} onPlan={vi.fn()} onExecute={vi.fn()} onExecuteGripper={vi.fn()} onExecuteAll={vi.fn()} onCancel={vi.fn()} />);
    expect((screen.getByRole("button", { name: "Execute All" }) as HTMLButtonElement).disabled).toBe(false);
    expect(screen.getByRole("button", { name: "Execute Arm" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Execute planned" })).toBeNull();
  });

  it("shows the half-degree safe range and clamps direct entry at the upper boundary", () => {
    const onEdit = vi.fn();
    const onClampNotice = vi.fn();
    render(<JointPanel joints={{ "3": { name: "3", position_rad: 0, velocity_rad_s: 0, lower_limit_rad: -1.74533, upper_limit_rad: 1.5708 } }} targets={{ "3": 0 }} leaseHeld plan={{ executable: false }} onEdit={onEdit} onClampNotice={onClampNotice} onPlan={vi.fn()} onExecute={vi.fn()} onExecuteGripper={vi.fn()} onExecuteAll={vi.fn()} onCancel={vi.fn()} />);

    const input = screen.getByRole("spinbutton", { name: "joint 3 target" }) as HTMLInputElement;
    expect(input.min).toBe("-99.50004285756798");
    expect(input.max).toBe("89.50021045914973");
    expect(screen.getByText("Safe −99.50° to 89.50°")).toBeTruthy();
    fireEvent.change(input, { target: { value: "100" } });
    expect(onEdit).toHaveBeenCalledWith("3", 1.5620733537400284);
    expect(onClampNotice).toHaveBeenCalledWith("Joint 3 clamped to 89.50° (0.5° safety margin).");
  });

  it("clamps one-degree trims and disables editing when authoritative limits are absent", () => {
    const onEdit = vi.fn();
    const onClampNotice = vi.fn();
    render(<JointPanel joints={{ "1": { name: "1", position_rad: 0, velocity_rad_s: 0, lower_limit_rad: -1, upper_limit_rad: 1 } }} targets={{ "1": 0.99 }} leaseHeld plan={{ executable: false }} onEdit={onEdit} onClampNotice={onClampNotice} onPlan={vi.fn()} onExecute={vi.fn()} onExecuteGripper={vi.fn()} onExecuteAll={vi.fn()} onCancel={vi.fn()} />);
    const row1 = screen.getByRole("row", { name: /1 0\.00/ });
    fireEvent.click(within(row1).getByRole("button", { name: "+1°" }));
    expect(onEdit).toHaveBeenCalledWith("1", 0.9912733537400283);
    expect(onClampNotice).toHaveBeenCalledWith("Joint 1 clamped to 56.80° (0.5° safety margin).");

    const missing = screen.getByRole("spinbutton", { name: "joint 2 target" }) as HTMLInputElement;
    expect(missing.disabled).toBe(true);
    expect(screen.getAllByText("Safe limits unavailable").length).toBeGreaterThan(0);
  });
});
