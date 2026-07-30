// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { WorkflowPanel } from "./workflow-panel";

describe("WorkflowPanel", () => {
  it("disables workflow commands and exposes an executing state until the response returns", async () => {
    let resolve!: () => void;
    const command = vi.fn(() => new Promise<void>((done) => { resolve = done; }));
    const user = userEvent.setup();
    render(<WorkflowPanel snapshot={{ run_id: "run-1", current_state: "READY", next_state: "MOVE_ABOVE_OBJECT", snapshot_revision: 7 }} leaseHeld command={command} />);

    await user.click(screen.getByRole("button", { name: "Start" }));
    expect(command).toHaveBeenCalledWith("start");
    expect((screen.getByRole("button", { name: "Starting…" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByRole("status").textContent).toContain("Executing Start…");
    expect((screen.getByRole("button", { name: "Next Step" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Run" }) as HTMLButtonElement).disabled).toBe(true);

    resolve();
    expect((await screen.findByRole("button", { name: "Start" }) as HTMLButtonElement).disabled).toBe(false);
    expect(screen.queryByRole("status")).toBeNull();
  });
});
