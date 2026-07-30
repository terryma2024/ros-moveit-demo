// @vitest-environment jsdom
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ConnectionHeader } from "./connection-header";

describe("ConnectionHeader", () => {
  it("keeps title, mode badge and lease action in a stable cluster before metadata", () => {
    render(<ConnectionHeader mode="READY" session={"session-" + "long-".repeat(30)} revision={9876543210} leaseHeld={false} rttMs={12345} onAcquire={vi.fn()} />);
    const cluster = screen.getByLabelText("Primary connection actions");
    const title = within(cluster).getByRole("heading", { name: "SO-101 Teleop" });
    const badge = within(cluster).getByText("READY");
    const button = within(cluster).getByRole("button", { name: "Acquire lease" });
    const metadata = screen.getByLabelText("Connection metadata");
    expect(cluster.className).toContain("shrink-0");
    expect(metadata.className).toContain("min-w-0");
    expect(badge.getAttribute("data-slot")).toBe("badge");
    expect(title.compareDocumentPosition(badge) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(badge.compareDocumentPosition(button) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(button.compareDocumentPosition(metadata) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(metadata.textContent).not.toContain("ROS domain");
    expect(metadata.textContent).not.toContain("GZ partition");
    expect(metadata.textContent).toContain("simulation-only · session");
  });
});
