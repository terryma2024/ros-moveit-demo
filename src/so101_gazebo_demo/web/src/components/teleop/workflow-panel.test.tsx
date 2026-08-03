// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { WorkflowPanel } from "./workflow-panel";

const isDisabled = (name: string) =>
  (screen.getByRole("button", { name }) as HTMLButtonElement).disabled;

describe("WorkflowPanel", () => {
  it("enables Start and Run only before a workflow exists", () => {
    render(<WorkflowPanel leaseHeld command={vi.fn()} />);

    expect(isDisabled("Start")).toBe(false);
    expect(isDisabled("Run")).toBe(false);
    expect(isDisabled("Resume")).toBe(true);
    expect(isDisabled("Next Step")).toBe(true);
    expect(isDisabled("Reset workflow")).toBe(true);
  });

  it("enables Resume but not Start or Run after Start creates a workflow", () => {
    render(<WorkflowPanel
      snapshot={{ run_id: "run-1", current_state: "PREPARE_OPEN_GRIPPER" }}
      leaseHeld
      command={vi.fn()}
    />);

    expect(isDisabled("Start")).toBe(true);
    expect(isDisabled("Run")).toBe(true);
    expect(isDisabled("Resume")).toBe(false);
    expect(isDisabled("Next Step")).toBe(false);
    expect(isDisabled("Reset workflow")).toBe(false);
  });

  it("leaves only Reset workflow enabled when the workflow is done", () => {
    render(<WorkflowPanel
      snapshot={{ run_id: "run-1", current_state: "DONE" }}
      leaseHeld
      command={vi.fn()}
    />);

    expect(isDisabled("Start")).toBe(true);
    expect(isDisabled("Run")).toBe(true);
    expect(isDisabled("Resume")).toBe(true);
    expect(isDisabled("Next Step")).toBe(true);
    expect(isDisabled("Stop")).toBe(true);
    expect(isDisabled("Reset workflow")).toBe(false);
  });

  it("disables workflow commands and exposes an executing state until the response returns", async () => {
    let resolve!: () => void;
    const command = vi.fn(() => new Promise<void>((done) => { resolve = done; }));
    const user = userEvent.setup();
    render(<WorkflowPanel leaseHeld command={command} />);

    await user.click(screen.getByRole("button", { name: "Start" }));
    expect(command).toHaveBeenCalledWith("start");
    expect((screen.getByRole("button", { name: "Starting…" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByRole("status").textContent).toContain("Executing Start…");
    expect((screen.getByRole("button", { name: "Next Step" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Run" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Resume" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Reset workflow" }) as HTMLButtonElement).disabled).toBe(true);

    resolve();
    expect((await screen.findByRole("button", { name: "Start" }) as HTMLButtonElement).disabled).toBe(false);
    expect(isDisabled("Run")).toBe(false);
    expect(screen.queryByRole("status")).toBeNull();
  });
});
