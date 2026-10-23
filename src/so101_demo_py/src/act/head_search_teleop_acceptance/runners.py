"""The real stack factory, detector flight, HTTP probe, app factory and end-to-end runner."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess  # noqa: S404 - the app and the e2e runner are installed programs
import time
import urllib.error
import urllib.request

from so101_demo.act.head_search_teleop_acceptance.receipts import (
    E2E_CASE,
    E2E_COMMAND,
    E2E_TIMEOUT_S,
    HEAD_CAMERA_IMAGE_TOPIC,
    TELEOP_FRAME_PROBE_FAILED,
    TELEOP_INPUTS_INCOMPLETE,
)


class TeleopAcceptanceRefused(RuntimeError):
    """The acceptance refused by name; the code is the receipt's own vocabulary."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _write(root: Path, name: str, document: Mapping) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    target = root / name
    target.write_text(json.dumps(dict(document), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def stack_environment(session_id: str, base: Mapping | None = None) -> dict:
    from so101_demo.act.head_search_restarts.gates import stack_environment as build

    return build(session_id, base)


def real_stack_factory(**kwargs):
    """The frozen production composition: the same transport and the same four controllers."""

    from so101_demo.act.head_execution_stack import RestartStack

    kwargs.pop("logger", None)
    return RestartStack(
        urdf_path=kwargs["urdf_path"],
        scene_path=kwargs["scene_path"],
        plugin_config_path=kwargs["plugin_config_path"],
        controller_config_path=kwargs["controller_config_path"],
        workspace=kwargs["workspace"],
        session_id=kwargs["session_id"],
        environment=stack_environment(kwargs["session_id"]),
    )


def real_ownership_probe() -> dict:
    from so101_demo.act.head_search_restarts.process_probes import probe_owners

    observation = probe_owners()
    return {
        "processes": observation.get("processes") or [],
        "nodes": observation.get("nodes") or [],
        "gpu_compute_apps": observation.get("gpu_compute_apps") or [],
        "sim_clock_s": observation.get("sim_clock_s") or [],
    }


def detector_flight(
    *,
    session_id: str,
    values: Mapping,
    weights_path,
    model_id: str,
    device: str,
    frames: int,
    log,
    operating_point: Mapping | None = None,
    timeout_s: float = 150.0,
    clock=time.monotonic,
    sleep=time.sleep,
) -> dict:
    """One production detector, on CUDA, over the real head-camera frames of the owned stack."""

    import numpy as np
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import Image

    from so101_demo.act.head_search_restarts.process_probes import TimedHeadDetector

    # the operating point is the frozen candidate's own declaration when it was supplied
    point = dict(operating_point or {}) or {"iou": float(values.get("tracking_iou", 0.5))}
    built = TimedHeadDetector.build(
        weights_path=weights_path,
        model_id=model_id,
        device=device,
        values=values,
        operating_point=point,
    )
    detector = built["runtime"]

    if not rclpy.ok():
        rclpy.init(args=None)
    # a ROS node name allows alphanumerics and underscores only; the session id carries the runtime id,
    # which is hyphenated on purpose
    node = Node("head_teleop_acceptance_" + re.sub(r"[^0-9a-zA-Z_]", "_", str(session_id)))
    frames_seen: list[dict] = []

    def on_image(message) -> None:
        if len(frames_seen) >= int(frames):
            return
        frames_seen.append(
            {
                "stamp_s": float(message.header.stamp.sec)
                + float(message.header.stamp.nanosec) * 1e-9,
                "frame_id": str(message.header.frame_id),
                "received_wall_s": clock(),
                "rgb": np.frombuffer(bytes(message.data), np.uint8).reshape(
                    int(message.height), int(message.width), 3
                ),
            }
        )

    subscription = node.create_subscription(Image, HEAD_CAMERA_IMAGE_TOPIC, on_image, 10)
    del subscription
    deadline = clock() + float(timeout_s)
    while len(frames_seen) < int(frames) and clock() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    if not frames_seen:
        node.destroy_node()
        raise RuntimeError(
            f"{TELEOP_FRAME_PROBE_FAILED}: {HEAD_CAMERA_IMAGE_TOPIC} published no frame"
        )

    detections = 0
    raw_sha = ""
    measured: list[dict] = []
    ages: list[float] = []
    received: list[float] = []
    # the production detector refuses a repeated source stamp, so a duplicated camera stamp is recorded
    # as skipped rather than fed to it and turned into a false detector failure
    last_stamp_ns = 0
    for frame in frames_seen:
        rgb = frame["rgb"]
        raw_sha = hashlib.sha256(rgb.tobytes()).hexdigest()
        stamp_ns = max(1, int(round(float(frame["stamp_s"]) * 1e9)))
        if stamp_ns <= last_stamp_ns:
            continue
        last_stamp_ns = stamp_ns
        found = detector.detect(
            rgb,
            session_id=session_id,
            attempt_id="teleop-acceptance",
            source_stamp_ns=stamp_ns,
            source_frame_id=frame["frame_id"],
        )
        detections += len(found or [])
        ages.append(clock() - float(frame["received_wall_s"]))
        received.append(float(frame["received_wall_s"]))
        measured.append({"stamp_s": frame["stamp_s"], "frame_id": frame["frame_id"]})
    node.destroy_node()
    # the rate is the span between the first and the last measured arrival, never one frame's own age
    span = max(1e-9, received[-1] - received[0]) if len(received) > 1 else 1e-9
    return {
        "detector_count": 1,
        "runtime_device": built.get("runtime_device"),
        "allow_cpu_fallback": False,
        "weights_sha256": built.get("weights_sha256"),
        "model_id": model_id,
        "frame_count": len(frames_seen),
        "measured_frames": len(measured),
        "detections": detections,
        "max_frame_age_s": max(ages) if ages else None,
        "frame_rate_hz": round((len(measured) - 1) / span, 4) if len(measured) > 1 else None,
        "raw_frame_sha256": raw_sha,
        "frames": measured,
        "source": f"the acceptance's own production HeadRgbDetector over {HEAD_CAMERA_IMAGE_TOPIC}",
    }


def http_probe(request: Mapping) -> dict:
    """The installed routes, called over HTTP exactly as the app serves them."""

    action = str(request.get("action"))
    base_url = str(request.get("base_url", ""))
    routes = {
        "status": ("GET", "/teleop/head-camera/status", None),
        "capture": ("POST", "/teleop/head-camera/capture", {}),
        "target": ("POST", "/teleop/head-camera/target", request.get("payload")),
        "stop": ("POST", "/teleop/head-camera/stop", request.get("payload")),
    }
    method, path, payload = routes[action]
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    http_request = urllib.request.Request(  # noqa: S310 - the acceptance'as own loopback URL
        f"{base_url}{path}", data=data, method=method
    )
    if data is not None:
        http_request.add_header("content-type", "application/json")
    try:
        with urllib.request.urlopen(http_request, timeout=10.0) as response:  # noqa: S310
            body = json.loads(response.read().decode("utf-8"))
            status = int(response.status)
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {"raw": raw}
        status = int(error.code)
    except Exception as error:  # noqa: BLE001 - an unreachable route is a failed probe, not a crash
        return {"ok": False, "status": None, "body": {"error": repr(error)}}
    return {"ok": 200 <= status < 300, "status": status, "body": body}


def app_factory(*, command, environment, port, capture_dir, stdout_path, static_dir=None):
    """The installed unified app as its own process group, so its exit can be proven.

    The installed web bundle is passed explicitly: the app resolves it relative to the module that runs
    it, and the acceptance runs the worktree module first on PYTHONPATH (disclosed), so leaving it to the
    module's own walk would serve 503 for every page while the bundle sat in the frozen install.
    """

    stdout_path = Path(stdout_path)
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(stdout_path, "ab")  # noqa: SIM115 - one handle, closed when the app is reaped
    argv = [*command, "--host", "127.0.0.1", "--port", str(port), "--capture-dir", str(capture_dir)]
    if static_dir is not None:
        argv += ["--static-dir", str(static_dir)]
    return subprocess.Popen(  # noqa: S603 - the command is the frozen install's own entry
        argv,
        stdout=handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env=dict(environment),
    )


def e2e_runner(*, base_url, evidence_root, web_dir, stdout_path, stderr_path):
    """The installed Playwright case, run through Bun with the app's own URL and evidence root."""

    if web_dir is None:
        raise ValueError(f"{TELEOP_INPUTS_INCOMPLETE}: no web directory was declared")
    environment = dict(os.environ)
    environment["SO101_TELEOP_BASE_URL"] = str(base_url)
    environment["SO101_E2E_EVIDENCE_ROOT"] = str(evidence_root)
    # Chrome's own profile singleton is an AF_UNIX socket, so the browser's temporary directory must
    # satisfy the same 103-byte limit the plan imposes on the bridge endpoints (a deep scratch TMPDIR
    # aborts the browser before the first navigation)
    browser_tmp = Path(os.environ.get("SO101_E2E_TMPDIR") or "/tmp") / f"so101-e2e-{os.getpid()}"
    browser_tmp.mkdir(parents=True, exist_ok=True)
    environment["TMPDIR"] = environment["TMP"] = environment["TEMP"] = str(browser_tmp)
    stdout_path = Path(stdout_path)
    stderr_path = Path(stderr_path)
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    with open(stdout_path, "wb") as out, open(stderr_path, "wb") as err:
        completed = subprocess.run(  # noqa: S603 - the frozen web toolchain's own script
            ["bun", "run", "test:e2e", "--", E2E_CASE],
            cwd=str(web_dir),
            stdout=out,
            stderr=err,
            env=environment,
            timeout=E2E_TIMEOUT_S,
            check=False,
        )
    command = f"cd {web_dir} && SO101_TELEOP_BASE_URL={base_url} {E2E_COMMAND}"
    return {"rc": int(completed.returncode), "command": command}
