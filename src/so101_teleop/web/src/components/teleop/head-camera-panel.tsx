import { useEffect, useState } from "react";

import type { HeadCameraClient } from "@/api/head-camera-client";

export interface HeadCameraDetection {
  class_id: number;
  class_name: string;
  confidence: number;
  track_id: string;
  xyxy: [number, number, number, number];
  mask_sha256: string;
}

export interface HeadCameraFrame {
  sequence: number;
  jpeg_sha256: string;
  detections: HeadCameraDetection[];
  model_id: string;
  bundle_sha256: string;
}

export interface HeadCameraStatus {
  available: boolean;
  operation: string;
  runtime_id: string;
  model_id: string;
  state: string;
  detector_constructed: number;
  qualified: boolean;
  authority: boolean;
  safe_interval_rad: [number, number];
}

export interface HeadCameraPanelProps {
  status: HeadCameraStatus | null;
  frame?: HeadCameraFrame | null;
  lockProgress?: number;
  lockRequired?: number;
  onExecute?: (targetRad: number) => void;
  onStop?: () => void;
  onCapture?: () => void;
}

const LOCK_REQUIRED = 3;

function stateLabel(state: string): string {
  if (state === "STOPPING") return "Stopping";
  if (state === "STOPPED") return "Stopped";
  return "Ready";
}

/**
 * The Teleop Head Camera view. It reads the composed domain's status and frames and can only ask the
 * backend for a bounded target, a stop or a capture: it holds no threshold, switches no model, and reports
 * the detector count it was told rather than implying one of its own.
 */
export function HeadCameraPanel({
  status,
  frame = null,
  lockProgress = 1,
  lockRequired = LOCK_REQUIRED,
  onExecute,
  onStop,
  onCapture,
}: HeadCameraPanelProps) {
  const [target, setTarget] = useState(0);

  if (status === null || !status.available) {
    return (
      <section aria-label="Head camera">
        <h2>Head Camera</h2>
        <p>Head camera unavailable</p>
      </section>
    );
  }

  const [low, high] = status.safe_interval_rad;
  const controllable = status.qualified && status.authority;
  const detection = frame?.detections?.[0] ?? null;

  return (
    <section aria-label="Head camera">
      <header>
        <h2>Head Camera</h2>
        {controllable ? null : <span>View only</span>}
        <span data-testid="head-camera-state">{stateLabel(status.state)}</span>
        <span data-testid="detector-constructed">{String(status.detector_constructed)}</span>
        <span>{status.model_id}</span>
        <span>{status.runtime_id}</span>
      </header>

      {frame ? (
        <figure aria-label="Head camera frame">
          <div data-testid="overlay-mask" />
          <div data-testid="overlay-bbox" />
          <div data-testid="optical-axis" />
          <div data-testid="deadband" />
          <div data-testid="vertical-bounds" />
          <div data-testid="candidate-center" />
          <div data-testid="lock-progress">{`${lockProgress} of ${lockRequired}`}</div>
          {detection ? (
            <figcaption>
              <span>{`${detection.class_name} ${detection.confidence.toFixed(2)}`}</span>
              <span>{detection.track_id}</span>
            </figcaption>
          ) : null}
        </figure>
      ) : null}

      <label>
        Target angle
        <input
          type="range"
          aria-label="Target angle"
          min={String(low)}
          max={String(high)}
          step="0.05"
          value={target}
          disabled={!controllable}
          onChange={(event) => setTarget(Number(event.target.value))}
        />
      </label>

      <button type="button" disabled={!controllable} onClick={() => onExecute?.(target)}>
        Execute
      </button>
      <button type="button" disabled={!controllable} onClick={() => onStop?.()}>
        Stop
      </button>
      <button type="button" disabled={!controllable} onClick={() => onCapture?.()}>
        Capture
      </button>
    </section>
  );
}

/**
 * The tab body: it owns the status it shows, reads it from the Head Camera API, and renders the panel. A
 * failed read is shown as an unavailable domain rather than as a stale frame.
 */
export function HeadCameraTab({ client }: { client: Pick<HeadCameraClient, "status"> }) {
  const [status, setStatus] = useState<HeadCameraStatus | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    client
      .status()
      .then((next) => {
        if (live) setStatus(next);
      })
      .catch(() => {
        if (live) setFailed(true);
      });
    return () => {
      live = false;
    };
  }, [client]);

  if (failed) return <HeadCameraPanel status={null} />;
  return <HeadCameraPanel status={status} />;
}
