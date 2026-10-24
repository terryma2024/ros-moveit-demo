"""Process, ROS node and GPU probes and the timed head detector."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
import subprocess
import time

from so101_demo.act.head_search.ownership import (
    run_command,
)
from so101_demo.act.head_search.restarts.contracts import (
    ANCHORS,
    RESTART_PROBE_FAILED,
    STACK_PROCESS_PATTERN,
    _digest,
    _refuse,
)
from so101_demo.act.head_search.restarts.observation import stack_observation


def measure_stack_processes(*, excluded_pids: Sequence[int] = ()) -> list[dict]:
    """Every live stack process, as ``{pid, argv}``; a probe that cannot run is a refusal."""

    listing = subprocess.run(  # noqa: S603 - a fixed read-only process listing
        ["pgrep", "-a", "-f", STACK_PROCESS_PATTERN],
        capture_output=True,
        text=True,
        check=False,
    )
    if listing.returncode not in (0, 1):
        raise _refuse(
            RESTART_PROBE_FAILED,
            f"the process-table probe failed with rc={listing.returncode}: {listing.stderr.strip()}",
        )
    excluded = {int(pid) for pid in excluded_pids}
    rows = []
    for line in listing.stdout.splitlines():
        tokens = line.strip().split(maxsplit=1)
        if len(tokens) != 2:
            continue
        pid = int(tokens[0])
        if pid in excluded or "apport" in tokens[1] or "pgrep" in tokens[1]:
            continue
        rows.append({"pid": pid, "argv": tokens[1]})
    return rows


def measure_ros_nodes(*, timeout: float = 20.0) -> list[str]:
    """The ROS graph's node list, read without starting a daemon."""

    rc, stdout, stderr = run_command(("ros2", "node", "list", "--no-daemon"), timeout=timeout)
    if rc != 0:
        raise _refuse(
            RESTART_PROBE_FAILED,
            f"`ros2 node list --no-daemon` failed with rc={rc}: {stderr.strip()}",
        )
    return [line.strip() for line in stdout.splitlines() if line.strip()]


def measure_gpu_compute_apps(*, timeout: float = 20.0) -> list[dict]:
    """Every process holding the GPU for compute, so "released" is observed rather than assumed."""

    rc, stdout, stderr = run_command(
        (
            "nvidia-smi",
            "--query-compute-apps=pid,process_name,used_memory",
            "--format=csv,noheader",
        ),
        timeout=timeout,
    )
    if rc != 0:
        raise _refuse(
            RESTART_PROBE_FAILED,
            f"`nvidia-smi --query-compute-apps` failed with rc={rc}: {stderr.strip()}",
        )
    rows = []
    for line in stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 3 or not parts[0]:
            continue
        rows.append({"pid": parts[0], "process_name": parts[1], "used_memory": parts[2]})
    return rows


#: every rclpy node this phase creates is named after its anchor; they are the phase's own participants and
#: are excluded from every graph read by name (the raw list is still recorded, and a node that is not one of
#: these is always foreign)
RUNNER_NODE_NAMES = tuple(f"/head_search_restart_{anchor}" for anchor in ANCHORS)


def probe_owners(
    *,
    excluded_pids: Sequence[int] = (),
    excluded_nodes: Sequence[str] = RUNNER_NODE_NAMES,
) -> dict:
    """One full read-only view: the process table, the graph, the GPU holds and the clock."""

    processes = measure_stack_processes(excluded_pids=excluded_pids)
    raw_nodes = measure_ros_nodes()
    excluded = {str(node) for node in excluded_nodes}
    residual = [node for node in raw_nodes if node in excluded]
    nodes = [node for node in raw_nodes if node not in excluded]
    observation = stack_observation(processes=processes, nodes=nodes)
    observation["raw_nodes"] = raw_nodes
    observation["excluded_runner_nodes"] = residual
    return observation


class TimedHeadDetector:
    """A ``HeadRgbDetector`` that records its own inference time, so the timing gate can read it.

    It is built by subclassing the production detector rather than wrapping it: ``detect_head`` checks
    ``isinstance(bundle["runtime"], HeadRgbDetector)``, so a wrapper would be refused by the production
    adapter's own guard.
    """

    @staticmethod
    def build(*, weights_path, model_id, device, values, operating_point, clock=time.monotonic):
        from so101_demo.adapters.act.detector import HeadRgbDetector
        from so101_demo.adapters.perception.yolo_seg import YoloSegDetector

        digest = _digest(weights_path)
        yolo = YoloSegDetector(
            weights_path=Path(weights_path),
            expected_sha256=digest,
            requested_device=device,
            allow_cpu_fallback=False,
            model_id=model_id,
            imgsz=640,
        )

        class _Timed(HeadRgbDetector):
            def __init__(self):
                super().__init__(
                    yolo,
                    model_id=model_id,
                    weights_sha256=digest,
                    tracking_iou=float(operating_point["iou"]),
                    min_bbox_aspect=float(values["min_bbox_aspect"]),
                )
                self.inference_s: list[float] = []

            def detect(self, rgb, **kwargs):
                started = clock()
                try:
                    return super().detect(rgb, **kwargs)
                finally:
                    self.inference_s.append(clock() - started)

        runtime = _Timed()
        return {
            "runtime": runtime,
            "runtime_device": str(getattr(yolo, "runtime_device", device)),
            "weights_sha256": digest,
            "model_id": model_id,
            "operating_point": dict(operating_point),
        }


class RecordingController:
    """The production ``HeadSearchController``, recording every frame it really consumed."""

    @staticmethod
    def build(config, sink: list):
        from so101_demo.act.search import HeadSearchController

        class _Recording(HeadSearchController):
            def __init__(self, configuration):
                self.sink = sink
                super().__init__(configuration)

            def tick(self, frame, feedback, now_wall_s):
                terminal = super().tick(frame, feedback, now_wall_s)
                self.sink.append(
                    {
                        "frame": frame,
                        "feedback": feedback,
                        "decision": dict(terminal),
                        "wall_s": now_wall_s,
                        "lock_count": int(self.lock_count),
                        "track": self.track,
                    }
                )
                return terminal

        return _Recording(config)


def _stamp_s(message) -> float:
    return float(message.header.stamp.sec) + float(message.header.stamp.nanosec) * 1e-9


def flight_node_overrides():
    """The flight node's clock is the **stack's** clock, because the production ports compare both.

    ``RosNeckSearchPort.command_neck`` judges the neck feedback with two ages: the wall-clock age of the
    last ``/joint_states`` receipt, and ``node.get_clock().now() - message.header.stamp``. The stack's own
    nodes run on the simulator's clock (``use_sim_time: true``, which is what
    ``head_search_transport_measurement`` sets on its node and what the ACT composition sets on
    ``ros2_control_node``), so a flight node left on the wall clock sees a ``sim_time`` stamp about
    279 000 s in the past and refuses every neck command with ``NECK_FEEDBACK_STALE``. The smoke found
    this: the restart phase never reached it only because its frames were refused before any motion.
    """

    from rclpy.parameter import Parameter

    return [Parameter("use_sim_time", value=True)]


def flight_node_name(anchor: str) -> str:
    """One node name per anchor, so a graph probe can tell this phase's participant from the stack's."""

    return f"head_search_restart_{anchor}"


def neck_port_diagnostic(neck, node, now) -> dict:
    """The two ages ``RosNeckSearchPort.command_neck`` judges a command with, read before it is asked.

    The port refuses a neck command when the wall-clock age of its last ``/joint_states`` receipt exceeds
    ``max_age_s``, and again when the *node clock's* age of that message's header stamp does. The two are
    different clocks, so a flight that never commands cannot tell which one refused it; this records both,
    the node's own clock reading and the effective ``use_sim_time``, in the flight's evidence.
    """

    node_now = node.get_clock().now().nanoseconds * 1e-9
    received = getattr(neck, "_received", None)
    stamp = getattr(neck, "_stamp", None)
    try:
        use_sim_time = bool(node.get_parameter("use_sim_time").value)
    except Exception:  # noqa: BLE001 - a node without the parameter is exactly what this records
        use_sim_time = None
    return {
        "node_name": node.get_name(),
        "use_sim_time": use_sim_time,
        "monotonic_now_s": now,
        "node_clock_s": node_now,
        "feedback_received_monotonic_s": received,
        "feedback_wall_age_s": None if received is None else now - received,
        "feedback_stamp_sim_s": stamp,
        "feedback_clock_age_s": None if stamp is None else node_now - stamp,
        "max_age_s": getattr(neck, "max_age", None),
        "definition": (
            "command_neck refuses when the port's last /joint_states receipt is older than max_age_s on "
            "the wall clock, or when node.get_clock().now() - message.header.stamp exceeds max_age_s; the "
            "stack's own nodes run on the simulator's clock, so the flight node must too"
        ),
    }


def rclpy_ok() -> bool:
    try:
        import rclpy as _rclpy

        return bool(_rclpy.ok())
    except Exception:  # noqa: BLE001 - an unimportable rclpy is not ok
        return False
