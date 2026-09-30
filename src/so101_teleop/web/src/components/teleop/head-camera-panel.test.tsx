// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HeadCameraPanel, type HeadCameraStatus } from "./head-camera-panel";

function status(overrides: Partial<HeadCameraStatus> = {}): HeadCameraStatus {
  return {
    available: true,
    operation: "TELEOP_ACCEPTANCE",
    runtime_id: "runtime-0001",
    model_id: "head-search-v2",
    state: "STOPPING",
    detector_constructed: 0,
    qualified: false,
    authority: false,
    safe_interval_rad: [-1.0, 1.0],
    ...overrides,
  };
}

describe("HeadCameraPanel", () => {
  it("keeps control disabled until authority and qualification are present", () => {
    render(<HeadCameraPanel status={status()} />);

    expect(screen.getByRole("button", { name: "Execute" })).toBeDisabled();
    expect(screen.getByText("View only")).toBeVisible();
  });

  it("enables control only when authority and qualification are both present", () => {
    render(<HeadCameraPanel status={status({ qualified: true, authority: true })} />);

    expect(screen.getByRole("button", { name: "Execute" })).toBeEnabled();
    expect(screen.queryByText("View only")).toBeNull();
  });

  it("bounds the controls to the sealed interval and offers no threshold editing", () => {
    render(<HeadCameraPanel status={status({ qualified: true, authority: true })} />);

    const slider = screen.getByLabelText("Target angle") as HTMLInputElement;
    expect(slider.min).toBe("-1");
    expect(slider.max).toBe("1");
    for (const forbidden of ["Confidence", "IoU", "Model", "Threshold"]) {
      expect(screen.queryByLabelText(forbidden)).toBeNull();
    }
  });

  it("renders the frame, the overlay fields and the runtime identities", () => {
    render(
      <HeadCameraPanel
        status={status({ state: "READY" })}
        frame={{
          sequence: 7,
          jpeg_sha256: "a".repeat(64),
          detections: [
            {
              class_id: 0,
              class_name: "plastic_cup",
              confidence: 0.91,
              track_id: "cup-1",
              xyxy: [10, 20, 110, 220],
              mask_sha256: "b".repeat(64),
            },
          ],
          model_id: "head-search-v2",
          bundle_sha256: "c".repeat(64),
        }}
      />,
    );

    expect(screen.getByLabelText("Head camera frame")).toBeTruthy();
    expect(screen.getByTestId("overlay-mask")).toBeTruthy();
    expect(screen.getByTestId("overlay-bbox")).toBeTruthy();
    expect(screen.getByText("plastic_cup 0.91")).toBeTruthy();
    expect(screen.getByText("cup-1")).toBeTruthy();
    expect(screen.getByTestId("optical-axis")).toBeTruthy();
    expect(screen.getByTestId("deadband")).toBeTruthy();
    expect(screen.getByTestId("vertical-bounds")).toBeTruthy();
    expect(screen.getByTestId("candidate-center")).toBeTruthy();
    expect(screen.getByTestId("lock-progress")).toHaveTextContent("1 of 3");
    expect(screen.getByText("head-search-v2")).toBeTruthy();
    expect(screen.getByText("runtime-0001")).toBeTruthy();
  });

  it("shows the stopping state until the proof completes and then stopped", () => {
    const { rerender } = render(<HeadCameraPanel status={status({ state: "STOPPING" })} />);
    expect(screen.getByTestId("head-camera-state")).toHaveTextContent("Stopping");

    rerender(<HeadCameraPanel status={status({ state: "STOPPED" })} />);
    expect(screen.getByTestId("head-camera-state")).toHaveTextContent("Stopped");
  });

  it("says the domain is unavailable rather than showing a frame", () => {
    render(<HeadCameraPanel status={null} />);

    expect(screen.getByText("Head camera unavailable")).toBeVisible();
    expect(screen.queryByLabelText("Head camera frame")).toBeNull();
  });

  it("never claims a detector of its own", () => {
    render(<HeadCameraPanel status={status({ detector_constructed: 0 })} />);

    expect(screen.getByTestId("detector-constructed")).toHaveTextContent("0");
  });
});
