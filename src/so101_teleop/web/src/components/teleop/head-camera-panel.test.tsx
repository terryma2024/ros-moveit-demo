// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HeadCameraPanel, type HeadCameraStatus } from "./head-camera-panel";

function status(overrides: Partial<HeadCameraStatus> = {}): HeadCameraStatus {
  return {
    available: true,
    operation: "TELEOP_ACCEPTANCE",
    runtime_id: "runtime-0001",
    model_id: "head-search-runtime",
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

    expect(screen.getByRole("button", { name: "Execute" })).toHaveProperty("disabled", true);
    expect(screen.getByText("View only")).toBeTruthy();
  });

  it("enables control only when authority and qualification are both present", () => {
    render(<HeadCameraPanel status={status({ qualified: true, authority: true })} />);

    expect(screen.getByRole("button", { name: "Execute" })).toHaveProperty("disabled", false);
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
          model_id: "head-search-runtime",
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
    expect(screen.getByTestId("lock-progress").textContent).toBe("1 of 3");
    expect(screen.getByText("head-search-runtime")).toBeTruthy();
    expect(screen.getByText("runtime-0001")).toBeTruthy();
  });

  it("shows the stopping state until the proof completes and then stopped", () => {
    const { rerender } = render(<HeadCameraPanel status={status({ state: "STOPPING" })} />);
    expect(screen.getByTestId("head-camera-state").textContent).toBe("Stopping");

    rerender(<HeadCameraPanel status={status({ state: "STOPPED" })} />);
    expect(screen.getByTestId("head-camera-state").textContent).toBe("Stopped");
  });

  it("says the domain is unavailable rather than showing a frame", () => {
    render(<HeadCameraPanel status={null} />);

    expect(screen.getByText("Head camera unavailable")).toBeTruthy();
    expect(screen.queryByLabelText("Head camera frame")).toBeNull();
  });

  it("never claims a detector of its own", () => {
    render(<HeadCameraPanel status={status({ detector_constructed: 0 })} />);

    expect(screen.getByTestId("detector-constructed").textContent).toBe("0");
  });
});

describe("HeadCameraPanel overlays and bounds", () => {
  const frame = {
    sequence: 3,
    jpeg_sha256: "d".repeat(64),
    detections: [
      {
        class_id: 0,
        class_name: "plastic_cup",
        confidence: 0.8,
        track_id: "cup-9",
        xyxy: [100, 120, 200, 320] as [number, number, number, number],
        mask_sha256: "e".repeat(64),
        mask_polygon: [
          [100, 120],
          [200, 120],
          [200, 320],
        ] as Array<[number, number]>,
      },
    ],
    model_id: "head-search-runtime",
    bundle_sha256: "f".repeat(64),
  };

  it("draws the overlay geometry from the frame rather than leaving placeholders", () => {
    render(<HeadCameraPanel status={status({ state: "READY" })} frame={frame} />);

    const box = screen.getByTestId("overlay-bbox");
    expect(box.getAttribute("x")).toBe("100");
    expect(box.getAttribute("width")).toBe("100");
    const mask = screen.getByTestId("overlay-mask");
    expect(mask.getAttribute("points")).toBe("100,120 200,120 200,320");
    expect(mask.getAttribute("data-mask-sha256")).toBe("e".repeat(64));
    expect(mask.getAttribute("points")).not.toBe("");
    expect(screen.getByTestId("candidate-center").getAttribute("cx")).toBe("150");
    expect(screen.getByTestId("optical-axis").getAttribute("x1")).toBe("320");
    expect(screen.getByTestId("deadband")).toBeTruthy();
    expect(screen.getByTestId("vertical-bounds").getAttribute("height")).not.toBe("0");
  });

  it("clamps the target into the sealed interval however it was set", () => {
    render(<HeadCameraPanel status={status({ qualified: true, authority: true })} />);

    const slider = screen.getByLabelText("Target angle") as HTMLInputElement;
    expect(Number(slider.min)).toBe(-1);
    expect(Number(slider.max)).toBe(1);
    expect(Number(slider.value)).toBeLessThanOrEqual(1);
    expect(Number(slider.value)).toBeGreaterThanOrEqual(-1);
  });
});


describe("HeadCameraPanel execute bound", () => {
  it("hands onExecute a clamped angle even when the interval is narrow", () => {
    const executed: number[] = [];
    render(
      <HeadCameraPanel
        status={status({ qualified: true, authority: true, safe_interval_rad: [-0.2, 0.2] })}
        onExecute={(target) => executed.push(target)}
      />,
    );

    const slider = screen.getByLabelText("Target angle") as HTMLInputElement;
    expect(Number(slider.min)).toBeCloseTo(-0.2);
    expect(Number(slider.max)).toBeCloseTo(0.2);
    // drive the control out of range so the clamp itself is exercised, not just the initial value
    fireEvent.change(slider, { target: { value: "99" } });
    expect(Number((screen.getByLabelText("Target angle") as HTMLInputElement).value)).toBeLessThanOrEqual(0.2);
    screen.getByRole("button", { name: "Execute" }).click();
    expect(executed).toHaveLength(1);
    expect(executed[0]).toBeGreaterThanOrEqual(-0.2);
    expect(executed[0]).toBeLessThanOrEqual(0.2);

    fireEvent.change(screen.getByLabelText("Target angle"), { target: { value: "-99" } });
    screen.getByRole("button", { name: "Execute" }).click();
    expect(executed[1]).toBeGreaterThanOrEqual(-0.2);
    expect(executed[1]).toBeLessThanOrEqual(0.2);
  });
});
