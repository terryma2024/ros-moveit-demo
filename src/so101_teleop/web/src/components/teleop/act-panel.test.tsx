// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ACT_PANEL_PHASES, ActPanel, type ActStatus } from "./act-panel";

function status(overrides: Partial<ActStatus> = {}): ActStatus {
  return {
    phase: "SEARCH",
    remaining_s: 42.5,
    cameras: { head: true, wrist: true },
    outcome: null,
    last_command: null,
    ...overrides,
  };
}

describe("ActPanel", () => {
  it("says nothing is running rather than inventing a session", () => {
    render(<ActPanel status={null} />);

    expect(screen.getByLabelText("ACT panel")).toBeTruthy();
    expect(screen.getByText("No session has been started from this browser.")).toBeTruthy();
    expect(screen.queryByTestId("act-phase")).toBeNull();
  });

  it("shows the phase, the remaining budget and both cameras", () => {
    render(<ActPanel status={status({ phase: "RECORD", last_command: "start" })} />);

    expect(screen.getByTestId("act-phase").textContent).toBe("RECORD");
    expect(screen.getByTestId("act-remaining").textContent).toBe("42.5 s");
    expect(screen.getByTestId("act-camera-head").textContent).toBe("streaming");
    expect(screen.getByTestId("act-camera-wrist").textContent).toBe("streaming");
    expect(screen.getByTestId("act-last-command").textContent).toBe("start");
    expect(screen.getByTestId("act-outcome").textContent).toBe("in progress");
  });

  it("reports an unavailable camera and a finished outcome without smoothing them over", () => {
    render(<ActPanel status={status({ cameras: { head: true, wrist: false }, outcome: "FAILED" })} />);

    expect(screen.getByTestId("act-camera-head").textContent).toBe("streaming");
    expect(screen.getByTestId("act-camera-wrist").textContent).toBe("unavailable");
    expect(screen.getByTestId("act-outcome").textContent).toBe("FAILED");
  });

  it("marks a phase outside the planned sequence instead of pretending it is one of them", () => {
    render(<ActPanel status={status({ phase: "RECOVERING" })} />);

    expect(screen.getByTestId("act-phase").textContent).toBe("RECOVERING");
    expect(screen.getByText(/not a planned phase/)).toBeTruthy();
    expect(ACT_PANEL_PHASES).toHaveLength(10);
  });
});
