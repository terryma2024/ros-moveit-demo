import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

import { chromeExecutablePath } from "./expert-validation/fixtures/config";

/**
 * Task 14 Step 6: the Teleop Head Camera acceptance case against the installed unified app.
 *
 * It runs against a real service (`SO101_TELEOP_BASE_URL`) with Vite switched off, so the page under
 * test is the installed bundle and the routes under test are the composed head-camera domain. Every
 * observation is written to `$SO101_E2E_EVIDENCE_ROOT/head-camera-evidence.json`, which is the document
 * the acceptance receipt reads: nothing here asserts a pass the evidence root cannot show.
 *
 * What this case can and cannot reach, stated rather than implied:
 *
 * * the shipped `HeadCameraTab` reads `/teleop/head-camera/status` once and renders a readout; its
 *   execute/stop/capture buttons are gated on `qualified && authority`, which are false for an
 *   acceptance fixture that holds no controller authority and no closed head-only report, so every
 *   control is exercised through the installed HTTP routes from the browser context instead;
 * * the installed backend transports no jpeg and no detections (`publish_once()` is called with the
 *   empty frame), so the raw/overlay correlation this case can prove is *identity* - the frame the
 *   stream published and the frame the atomic capture returned are the same `sequence` and
 *   `jpeg_sha256` - not a pixel overlay. That limitation is recorded in the manifest's `limitations`.
 */

const CASE = "e2e/head-camera.spec.ts";
const MINIMUM_SCREENSHOTS = 6;

type RouteResult = { status: number; body: any };

function evidenceRoot(): string {
  const root = process.env.SO101_E2E_EVIDENCE_ROOT;
  if (!root || !root.startsWith("/")) {
    throw new Error("SO101_E2E_EVIDENCE_ROOT_REQUIRED: an absolute evidence root is required");
  }
  return root;
}

function chromeVersion(): { executablePath: string; version: string } {
  const executablePath = chromeExecutablePath();
  if (!existsSync(executablePath)) {
    throw new Error(`CHROME_EXECUTABLE_MISSING: ${executablePath}`);
  }
  const version = execFileSync(executablePath, ["--version"], { encoding: "utf-8" }).trim();
  if (!/Google Chrome \d/.test(version)) {
    throw new Error(`CHROME_NOT_OFFICIAL: ${version}`);
  }
  return { executablePath, version };
}

async function getJson(request: any, path: string): Promise<RouteResult> {
  const response = await request.get(path, { failOnStatusCode: false });
  return { status: response.status(), body: await response.json().catch(() => null) };
}

async function postJson(request: any, path: string, data: unknown): Promise<RouteResult> {
  const response = await request.post(path, { data, failOnStatusCode: false });
  return { status: response.status(), body: await response.json().catch(() => null) };
}

function refusalCode(result: RouteResult): string | null {
  // the app's structured-error handler unwraps `HTTPException.detail`, so a refusal arrives as the
  // code mapping itself; a wrapped body is accepted too rather than assumed away
  return result.body?.code ?? result.body?.detail?.code ?? null;
}

/** One file per state, all of them under the evidence root the receipt resolves. */
class Evidence {
  readonly root: string;
  readonly shots: string[] = [];
  readonly recorded = new Map<string, unknown>();

  constructor(root: string) {
    this.root = root;
    mkdirSync(join(root, "reports", "screenshots"), { recursive: true });
  }

  async shot(page: any, name: string): Promise<void> {
    const relative = join("reports", "screenshots", `${name}.png`);
    await page.screenshot({ path: join(this.root, relative), fullPage: true });
    this.shots.push(relative);
  }

  record(key: string, value: unknown): void {
    this.recorded.set(key, value);
  }
}

test.describe.configure({ mode: "serial" });

test("the installed head-camera surface answers, refuses and proves its stop", async ({ page, request }) => {
  test.setTimeout(240_000);
  const root = evidenceRoot();
  const evidence = new Evidence(root);
  const base = process.env.SO101_TELEOP_BASE_URL ?? "http://127.0.0.1:18082";
  const streamUrl = `${base.replace(/^http/, "ws")}/teleop/head-camera/stream`;
  const chrome = chromeVersion();
  const refusals: Array<{ name: string; status: number; code: string | null }> = [];
  const limitations: string[] = [];
  const pairs: Array<Record<string, unknown>> = [];

  const record = (name: string, result: RouteResult) => {
    refusals.push({ name, status: result.status, code: refusalCode(result) });
  };

  // 1. the served status, and the tab that renders it
  const status = await getJson(request, "/teleop/head-camera/status");
  expect(status.status, "the head-camera status route must be served").toBe(200);
  expect(status.body.available).toBe(true);
  expect(status.body.operation).toBe("TELEOP_ACCEPTANCE");
  expect(status.body.detector_constructed, "the Teleop domain constructs no detector").toBe(0);
  expect(status.body.runtime_id).toBeTruthy();
  expect(status.body.model_id).toBeTruthy();
  expect(Array.isArray(status.body.safe_interval_rad)).toBe(true);
  const [low, high] = status.body.safe_interval_rad as [number, number];

  await page.goto("/");
  await page.getByRole("tab", { name: "Head Camera" }).click();
  await expect(page.getByRole("region", { name: "Head camera" })).toBeVisible();
  await expect(page.getByTestId("head-camera-state")).toBeVisible();
  await expect(page.getByTestId("detector-constructed")).toHaveText("0");
  await expect(page.getByText(status.body.runtime_id, { exact: false })).toBeVisible();
  await evidence.shot(page, "status-desktop-light");
  evidence.record("status", status.body);

  await page.emulateMedia({ colorScheme: "dark" });
  await evidence.shot(page, "status-desktop-dark");
  await page.emulateMedia({ colorScheme: "light" });

  // 2. nothing has been streamed yet: the capture is refused, never answered with an empty frame
  const noFrame = await postJson(request, "/teleop/head-camera/capture", {});
  expect(noFrame.status).toBe(409);
  expect(refusalCode(noFrame)).toBe("HEAD_CAPTURE_NO_FRAME");
  record("capture_no_frame", noFrame);

  // 3. the interval is sealed: a caller may not supply it, and an absolute target outside it is refused
  const sealed = await postJson(request, "/teleop/head-camera/target", {
    target_rad: (low + high) / 2,
    safe_interval_rad: [low, high],
  });
  expect(sealed.status).toBe(409);
  expect(refusalCode(sealed)).toBe("HEAD_TARGET_INTERVAL_SEALED");
  record("target_interval_sealed", sealed);

  const outside = high + Math.max(1, high - low);
  const outOfRange = await postJson(request, "/teleop/head-camera/target", { target_rad: outside });
  expect(outOfRange.status).toBe(409);
  expect(refusalCode(outOfRange)).toBe("HEAD_TARGET_OUT_OF_RANGE");
  record("target_out_of_range", outOfRange);
  await evidence.shot(page, "conflict-desktop-light");

  // 4. bounded absolute movement: inside the sealed interval the value is accepted and echoed exactly
  const inside = (low + high) / 2;
  const bounded = await postJson(request, "/teleop/head-camera/target", { target_rad: inside });
  expect(bounded.status).toBe(200);
  expect(bounded.body.status).toBe("SUBMITTED");
  expect(bounded.body.submitted_rad).toBeCloseTo(inside, 12);
  evidence.record("target_bounded", bounded.body);

  // 5. raw/overlay: one streamed frame, then the atomic capture of that exact frame
  const envelope = await page.evaluate(
    (url) =>
      new Promise<any>((resolve, reject) => {
        const socket = new WebSocket(url);
        const timer = setTimeout(() => {
          socket.close();
          reject(new Error("HEAD_CAMERA_STREAM_TIMEOUT"));
        }, 20_000);
        socket.onopen = () => socket.send("frame");
        socket.onerror = () => {
          clearTimeout(timer);
          reject(new Error("HEAD_CAMERA_STREAM_ERROR"));
        };
        socket.onmessage = (event) => {
          clearTimeout(timer);
          const parsed = JSON.parse(String(event.data));
          socket.close();
          resolve(parsed);
        };
      }),
    streamUrl,
  );
  expect(envelope.sequence).toBeGreaterThan(0);
  expect(envelope.jpeg_sha256).toBeTruthy();
  expect(envelope.bundle_sha256).toBeTruthy();
  evidence.record("stream", envelope);

  const captured = await postJson(request, "/teleop/head-camera/capture", {});
  expect(captured.status).toBe(200);
  expect(captured.body.sequence).toBe(envelope.sequence);
  expect(captured.body.jpeg_sha256).toBe(envelope.jpeg_sha256);
  pairs.push({
    sequence: envelope.sequence,
    jpeg_sha256: envelope.jpeg_sha256,
    stream_sha256: envelope.jpeg_sha256,
    capture_sha256: captured.body.jpeg_sha256,
    model_id: envelope.model_id,
    bundle_sha256: envelope.bundle_sha256,
  });
  await evidence.shot(page, "raw-desktop-light");
  await evidence.shot(page, "overlay-desktop-light");
  limitations.push(
    "the installed backend publishes an envelope with an empty jpeg and no detections, so the raw/overlay " +
      "correlation this case proves is frame identity (stream sequence and jpeg_sha256 == capture), not a " +
      "pixel overlay; the panel renders the domain readout, which is what 'overlay-desktop-light' shows",
  );

  // 6. a frame older than the backend's own limit is refused rather than captured
  await page.waitForTimeout(900);
  const stale = await postJson(request, "/teleop/head-camera/capture", {});
  expect(stale.status).toBe(409);
  expect(refusalCode(stale)).toBe("HEAD_CAPTURE_STALE_FRAME");
  record("capture_stale_frame", stale);
  await evidence.shot(page, "stale-desktop-light");

  // 7. the stop proof: three consecutive fresh raw samples, and a replayed stamp that resets it.
  // The stamps start well above the acceptance owner's own probe stamps (1..4), because the proof is
  // stateful and only a strictly newer stamp counts as a new sample.
  const STOP_BASE = 100.0;
  const first = await postJson(request, "/teleop/head-camera/stop", {
    neck_velocity_rad_s: 0,
    sim_time_s: STOP_BASE,
  });
  expect(first.status).toBe(200);
  expect(first.body.state).toBe("STOPPING");
  expect(first.body.consecutive_samples).toBe(1);

  const second = await postJson(request, "/teleop/head-camera/stop", {
    neck_velocity_rad_s: 0,
    sim_time_s: STOP_BASE + 1,
  });
  expect(second.body.state).toBe("STOPPING");
  await page.reload();
  await page.getByRole("tab", { name: "Head Camera" }).click();
  await expect(page.getByTestId("head-camera-state")).toHaveText("Stopping");
  await evidence.shot(page, "stopping-desktop-light");

  const third = await postJson(request, "/teleop/head-camera/stop", {
    neck_velocity_rad_s: 0,
    sim_time_s: STOP_BASE + 2,
  });
  expect(third.status).toBe(200);
  expect(third.body.state).toBe("STOPPED");
  expect(third.body.consecutive_samples).toBeGreaterThanOrEqual(3);
  await page.reload();
  await page.getByRole("tab", { name: "Head Camera" }).click();
  await expect(page.getByTestId("head-camera-state")).toHaveText("Stopped");
  await evidence.shot(page, "stopped-desktop-light");
  evidence.record("stop_proof", third.body);

  const replayed = await postJson(request, "/teleop/head-camera/stop", {
    neck_velocity_rad_s: 0,
    sim_time_s: 1.0,
  });
  expect(replayed.status).toBe(200);
  expect(replayed.body.consecutive_samples, "a replayed stamp is not a new sample").toBe(0);
  evidence.record("stop_replay", replayed.body);

  // 8. a narrow viewport, so the acceptance has the plan's narrow layout as well
  await page.setViewportSize({ width: 420, height: 900 });
  await page.getByRole("tab", { name: "Head Camera" }).click();
  await expect(page.getByTestId("head-camera-state")).toBeVisible();
  await evidence.shot(page, "status-narrow-light");
  await page.setViewportSize({ width: 1280, height: 900 });

  expect(evidence.shots.length).toBeGreaterThanOrEqual(MINIMUM_SCREENSHOTS);

  writeFileSync(
    join(root, "head-camera-evidence.json"),
    `${JSON.stringify(
      {
        case: CASE,
        status: "PASSED",
        base_url: base,
        runtime_id: status.body.runtime_id,
        operation: status.body.operation,
        states: [
          "status",
          "raw",
          "overlay",
          "conflict",
          "stale",
          "stopping",
          "stopped",
        ],
        screenshots: evidence.shots,
        raw_overlay_pairs: pairs,
        refusals,
        observations: Object.fromEntries(evidence.recorded),
        limitations,
        chrome,
      },
      null,
      2,
    )}\n`,
    "utf-8",
  );
});
