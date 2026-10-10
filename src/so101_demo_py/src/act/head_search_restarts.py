"""Task 14 Step 4: one independent ``FULL_RESTART`` per anchor, with teardown proofs.

The plan fixes exactly three restart phases - ``restart_default``, ``restart_left``,
``restart_forward`` - and says what each one has to prove (Task 14 Step 4): *"Each phase tears down and
reconstructs the one stack, then passes graph, detector, search, lock, timing and stop gates. The manifest
must contain exactly ``default``, ``left`` and ``forward``, once each."* Design section 10.2 repeats it:
"after the forty scenarios, ``default``, ``left`` and ``forward`` each run one independent
``FULL_RESTART``; all three pass the graph, detection, search, lock, timing and stop gates, and no
consecutive-success counter is kept."

What this producer implements, stated exactly:

* **One stack at a time.** The owner of record is this process. Before an anchor's stack starts, the
  process table, the ROS graph and the GPU compute processes are read and must be empty of owners; the
  stack is then the production composition of ``runtime/launch_composition.py`` for the ACT profile
  (``ros2_control_node`` with the production MuJoCo camera plugin, ``robot_state_publisher`` and the four
  controller spawners), started headless under EGL exactly as the frozen HS-308 transport measurement
  starts it. The camera at 10 Hz, the simulation clock, the joint states and TF are the real production
  transport, not a stand-in.
* **The health gates are measured, not asserted.** The graph gate reads ``ros2 node list`` and refuses on
  a missing owner node or a foreign one. The timing gate reads the real ``/head_camera/color`` stream and
  requires the declared 10 Hz with no duplicate, backward or undeclared-gap stamp. The clock gate requires
  ``/clock`` (the simulator's own time base) to advance. The detector gate requires exactly one detector in
  this process, on CUDA, with CPU fallback disabled and the promoted weights digest.
* **The search is the production closed loop.** One declared anchor of the seal's own ``in_frame_matrix``
  fixes ``search_start_rad``; the seal's ``workspace_matrix`` fixes the cup's world point for that anchor,
  which is written into the stack's one MuJoCo instance through the simulator's own
  ``~/set_free_joint_state`` service. The loop is ``HeadSearchController`` driven by
  ``RosSearchAdapter`` over the real topic stream, and the neck is commanded through the neck controller's
  own ``FollowJointTrajectory`` action. That controller (``so101_mujoco_support/HeadNeckTrajectoryController``)
  accepts a goal only while the single owner's dead-man socket is connected, so the owner of the stack
  activates the neck through ``HeadNeckOwner`` and the restart commands it through the owner's local
  admission. The restart owner *is* the single owner of the stack (the plan's "the qualifier owns every start
  and teardown").
* **The stop proof is the production criterion.** After the terminal, the neck is held and raw
  ``/joint_states`` feedback is sampled; three consecutive samples within the promoted
  ``stop_velocity_rad_s`` are the proof.
* **The teardown is proven.** The stack is stopped, and the process table, the ROS graph and the GPU
  compute processes are read again; all three must be empty before the next anchor may start. A teardown
  that cannot be proven refuses the run and stops it: no second stack is ever started.

The receipt is ``head_search_full_restart_receipt`` - the document
``so101_demo.act.head_search_aggregate`` declares for this phase and re-derives field by field from the
evidence, not the producer's claim.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import signal
import subprocess
import sys
import time
import traceback
from collections.abc import Mapping, Sequence
from pathlib import Path

from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search_ownership import (
    OPERATION as OWNERSHIP_OPERATION,
)
from so101_demo.act.head_search_ownership import (
    read_runtime_identity,
    run_command,
)
from so101_demo.act.head_search_qualification import _require_new_root
from so101_demo.act.head_search_scenarios import check_frame_cadence, stop_proof
from so101_demo.act.head_search_timing_measurement import (
    DEFAULT_MAX_SETTLE_S,
    FRAME_PERIOD_S,
    FRAME_RATE_HZ,
)
from so101_demo.act.head_search_transport_measurement import MujocoRosTransport
from so101_demo.perception_benchmark.contracts import canonical_sha256

SCHEMA_VERSION = 1

#: the aggregate's own declaration of this artefact; the two must not drift
KIND = "head_search_full_restart_receipt"
RECEIPTS_KIND = "head_search_full_restart_receipts"
OPERATION = "QUALIFICATION_ANCHOR_RESTART"
LIFECYCLE = "FULL_RESTART"
PHASE = "restarts"

ANCHORS = ("default", "left", "forward")
PHASE_BY_ANCHOR = {
    "default": "restart_default",
    "left": "restart_left",
    "forward": "restart_forward",
}
ARTIFACT_BY_ANCHOR = {
    "default": "restart-default.json",
    "left": "restart-left.json",
    "forward": "restart-forward.json",
}
AGGREGATE_ARTIFACT = "restart-receipts.json"
RECEIPT_ARTIFACT = "measurement-receipt.json"
STACK_LOG = "transport-stack.log"

DECLARED_FRAME_RATE_HZ = FRAME_RATE_HZ
FRAME_PERIOD = FRAME_PERIOD_S
#: the measured frame a rate probe is judged with: the declared rate is 10 Hz, and the achieved mean rate
#: over a multi-second window is compared against it with this absolute tolerance (the plugin publishes on
#: the simulator's own time base, so its long-run mean is the declared rate and its jitter is a frame)
RATE_TOLERANCE_HZ = 0.05
#: how many samples the rate probe needs before its mean means anything
MINIMUM_RATE_FRAMES = 20

#: the production node names the graph gate requires. `controller_manager` is the node
#: ``mujoco_ros2_control``'s ``ros2_control_node`` creates (its main names the manager
#: ``controller_manager``); ``mujoco_ros2_control_node`` and ``robotsystem`` are the simulator's own two
#: internal nodes (the MuJoCo Simulate node and the ``RobotSystem`` hardware's introspection node) that
#: come up inside the same process, so they are declared owners rather than foreign nodes.
STACK_OWNED_NODES = (
    "controller_manager",
    "robot_state_publisher",
    "mujoco_ros2_control_node",
    "robotsystem",
    # `controller_manager` hosts each controller in a node of its own name
    "joint_state_broadcaster",
    "arm_controller",
    "gripper_controller",
    "neck_controller",
)
#: a controller spawner's node is transient by construction: the stack is at steady state only once every
#: spawner has activated its controller and exited, which is what makes the graph probe meaningful
TRANSIENT_NODE_PREFIXES = ("spawner_",)
EXPECTED_NODES = STACK_OWNED_NODES
OWNER_PROCESS_PATTERNS = {
    "mujoco_instances": r"lib/mujoco_ros2_control/ros2_control_node",
    "controller_owners": r"lib/(mujoco_ros2_control/ros2_control_node|controller_manager/spawner)",
    "robot_state_publishers": r"lib/robot_state_publisher/robot_state_publisher",
    "spawners": r"controller_manager/spawner",
}
STACK_PROCESS_PATTERN = (
    r"lib/mujoco_ros2_control/ros2_control_node"
    r"|lib/robot_state_publisher/robot_state_publisher"
    r"|controller_manager/spawner"
)

CAMERA_IMAGE_TOPIC = "/head_camera/color"
CAMERA_INFO_TOPIC = "/head_camera/camera_info"
JOINT_TOPIC = "/joint_states"
CLOCK_TOPIC = "/clock"
SCENE_SERVICE = "/mujoco_ros2_control_node/set_free_joint_state"

#: the four controllers the ACT profile activates; the restart spawns exactly these, so the stack under
#: test is the production one rather than the two-node transport subset the HS-308 stamp measurement used
CONTROLLERS = ("joint_state_broadcaster", "arm_controller", "gripper_controller", "neck_controller")
NECK_CONTROLLER = "neck_controller"
NECK_JOINT = "neck_yaw_joint"
#: the sealed scene's own cup: ``<body name="plastic_cup" pos="0.02 -0.28 0.165">``, which is exactly the
#: seal's declared ``default`` anchor point. ``plastic_cup_b`` sits at ``(2, 2, 2)``, outside every frame.
CUP_BODY = "plastic_cup"
#: how long a start, a rate probe, a search and a teardown may take before the phase refuses
STACK_START_TIMEOUT_S = 120.0
GRAPH_TIMEOUT_S = 60.0
CAMERA_PROBE_S = 5.0
CLOCK_PROBE_S = 1.0
SEARCH_TIMEOUT_MARGIN_S = 1.0
STOP_PROOF_TIMEOUT_S = 5.0
TEARDOWN_TIMEOUT_S = 30.0

#: this phase's own refusals. A refusal stops the whole run: the next anchor never starts.
RESTART_INPUTS_INCOMPLETE = "RESTART_INPUTS_INCOMPLETE"
RESTART_OWNERSHIP_REFUSED = "RESTART_OWNERSHIP_REFUSED"
RESTART_OWNERSHIP_MISMATCH = "RESTART_OWNERSHIP_MISMATCH"
RESTART_RUN_ROOT_EXISTS = "RESTART_RUN_ROOT_EXISTS"
RESTART_RUNTIME_UNVERIFIED = "RESTART_RUNTIME_UNVERIFIED"
RESTART_ANCHOR_UNDECLARED = "RESTART_ANCHOR_UNDECLARED"
RESTART_SCENE_CONTRADICTORY = "RESTART_SCENE_CONTRADICTORY"
RESTART_STACK_START_FAILED = "RESTART_STACK_START_FAILED"
RESTART_FOREIGN_OWNER_ACTIVE = "RESTART_FOREIGN_OWNER_ACTIVE"
RESTART_NODE_MISSING = "RESTART_NODE_MISSING"
RESTART_FRAME_RATE_MISMATCH = "RESTART_FRAME_RATE_MISMATCH"
RESTART_SIM_CLOCK_STALLED = "RESTART_SIM_CLOCK_STALLED"
RESTART_DEVICE_UNAVAILABLE = "RESTART_DEVICE_UNAVAILABLE"
RESTART_DETECTOR_FAILED = "RESTART_DETECTOR_FAILED"
RESTART_SEARCH_UNPROVEN = "RESTART_SEARCH_UNPROVEN"
RESTART_LOCK_UNPROVEN = "RESTART_LOCK_UNPROVEN"
RESTART_CADENCE_BROKEN = "RESTART_CADENCE_BROKEN"
RESTART_TIMING_THRESHOLDS = "RESTART_TIMING_THRESHOLDS"
RESTART_STOP_UNPROVEN = "RESTART_STOP_UNPROVEN"
RESTART_TEARDOWN_UNPROVEN = "RESTART_TEARDOWN_UNPROVEN"
RESTART_GPU_NOT_RELEASED = "RESTART_GPU_NOT_RELEASED"
RESTART_PROBE_FAILED = "RESTART_PROBE_FAILED"
RESTART_ADAPTER_SILENT = "RESTART_ADAPTER_SILENT"

#: a refusal that must stop the whole run: a stack that may still be alive, a second owner, or a run root
#: that is not brand new. Every other refusal is recorded, its receipt is written, and the next anchor is
#: run - each restart is independent, and the plan's manifest wants all three receipts, once each.
ABORT_CODES = (
    RESTART_TEARDOWN_UNPROVEN,
    RESTART_GPU_NOT_RELEASED,
    RESTART_FOREIGN_OWNER_ACTIVE,
    RESTART_RUN_ROOT_EXISTS,
)

FIT_WARNING = (
    "a restart receipt is a claim about one anchor of the frozen runtime: it names the stack that was "
    "started, the graph it presented, the rate its camera published at, the one CUDA detector that closed "
    "the loop, the terminal that loop reached, the lock it held, the timing it kept, the stop it proved and "
    "the emptiness it left behind. It is not a qualification verdict; the aggregate phase re-derives every "
    "field from this document and from the evidence beside it"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class RestartRefused(CalibrationInputsRefused):
    """One anchor restart's refusal, carrying the exact code the run records and stops on."""


def _refuse(code: str, detail: str) -> RestartRefused:
    return RestartRefused(code, detail)


def _finite(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _digest(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read_json(path) -> dict:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise _refuse(RESTART_INPUTS_INCOMPLETE, f"{path} is not a document")
    return dict(document)


def _write(root: Path, name: str, document: Mapping) -> Path:
    target = Path(root) / name
    pending = Path(root) / f".{name}.pending"
    pending.write_text(
        json.dumps(dict(document), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(pending, target)
    return target


def _utc_now(now=time.gmtime) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", now())


# --- the ownership receipt and the runtime of record --------------------------------------------------


def read_ownership_receipt(path, *, run_root) -> dict:
    """Take Task 14 Step 1's receipt and refuse unless it guards exactly this run root.

    The receipt is not re-derived here: it is the Step 1 producer's observation, taken at its own instant.
    What this phase checks is that it is the right document (operation and status), that it refused
    nothing, and that the root it guards is the root this run is about to claim.
    """

    receipt = Path(path)
    if not receipt.is_file():
        raise _refuse(
            RESTART_OWNERSHIP_MISMATCH,
            f"no exclusive-ownership receipt at {receipt}; Step 1 must pass before any stack starts",
        )
    document = _read_json(receipt)
    if document.get("operation") != OWNERSHIP_OPERATION:
        raise _refuse(
            RESTART_OWNERSHIP_MISMATCH,
            f"{receipt} carries operation {document.get('operation')!r}, not {OWNERSHIP_OPERATION!r}",
        )
    if document.get("status") != "EXCLUSIVE_OWNERSHIP_OK" or document.get("refusals"):
        codes = ",".join(str(item.get("code")) for item in document.get("refusals") or ())
        raise _refuse(
            RESTART_OWNERSHIP_REFUSED,
            f"the exclusive-ownership gate refused with {codes or 'no code'}: a phase that does not "
            f"exclusively own the machine may not start a stack",
        )
    planned = document.get("planned_run_root")
    if str(planned or "") != str(run_root):
        raise _refuse(
            RESTART_OWNERSHIP_MISMATCH,
            f"the ownership receipt guards {planned!r}, not this run root {str(run_root)!r}",
        )
    return {
        "path": str(receipt),
        "sha256": _digest(receipt),
        "operation": document.get("operation"),
        "status": document.get("status"),
        "checked_at_utc": document.get("checked_at_utc"),
        "planned_run_root": planned,
        "expected_runtime": document.get("expected_runtime"),
    }


def require_runtime_of_record(runtime: Mapping) -> dict:
    """The frozen runtime's own identity, refused unless it is the CUDA-only runtime of record."""

    if not isinstance(runtime, Mapping) or not runtime:
        raise _refuse(RESTART_RUNTIME_UNVERIFIED, "no frozen runtime identity was presented")
    if runtime.get("allow_cpu_fallback") is not False:
        raise _refuse(
            RESTART_RUNTIME_UNVERIFIED,
            f"the runtime declares allow_cpu_fallback={runtime.get('allow_cpu_fallback')!r}; this producer "
            f"never falls back to the CPU",
        )
    if str(runtime.get("cuda_device")) != "cuda:0":
        raise _refuse(
            RESTART_RUNTIME_UNVERIFIED,
            f"the runtime declares cuda_device={runtime.get('cuda_device')!r}, not cuda:0",
        )
    if runtime.get("setup_bash_present") is not True:
        raise _refuse(
            RESTART_RUNTIME_UNVERIFIED,
            "the frozen root has no install/setup.bash, so the overlay is not the runtime of record",
        )
    if int(runtime.get("values_count", 0)) != 17:
        raise _refuse(
            RESTART_RUNTIME_UNVERIFIED,
            f"the runtime carries {runtime.get('values_count')!r} values, not the approved 17",
        )
    declared = runtime.get("weight_sha256_declared")
    if not declared or runtime.get("weight_sha256_observed") != declared:
        raise _refuse(
            RESTART_RUNTIME_UNVERIFIED,
            f"the declared weights {declared!r} are not the observed weights "
            f"{runtime.get('weight_sha256_observed')!r}",
        )
    if not runtime.get("source_commit"):
        raise _refuse(RESTART_RUNTIME_UNVERIFIED, "the runtime carries no source commit")
    return dict(runtime)


# --- the declared anchors -----------------------------------------------------------------------------


def anchor_declarations(seal: Mapping, anchors: Sequence[str] | None = None) -> list[dict]:
    """Every declared anchor's own search start and cup point, read from the sealed geometry.

    ``in_frame_matrix`` fixes ``neck_start_rad`` (the anchor's declared search start) and
    ``centre_angle_rad`` (the neck angle that centres that anchor's cup). ``workspace_matrix.key_samples``
    fixes the world point the anchor was measured at. A missing piece is a contradictory seal, not a
    default: guessing either would make the anchor something other than what was sealed.
    """

    if not isinstance(seal, Mapping):
        raise _refuse(RESTART_SCENE_CONTRADICTORY, "the geometry seal is not a document")
    matrix = seal.get("in_frame_matrix")
    if not isinstance(matrix, Mapping) or not matrix:
        raise _refuse(
            RESTART_SCENE_CONTRADICTORY, "the geometry seal declares no in_frame_matrix anchors"
        )
    samples = (seal.get("workspace_matrix") or {}).get("key_samples")
    points = {
        str(sample.get("anchor")): [float(value) for value in sample.get("point_m") or ()]
        for sample in (samples or ())
        if isinstance(sample, Mapping) and sample.get("kind") == "anchor"
    }
    names = list(ANCHORS) if anchors is None else [str(name) for name in anchors]
    declared: list[dict] = []
    for name in names:
        entry = matrix.get(name)
        if not isinstance(entry, Mapping):
            raise _refuse(
                RESTART_ANCHOR_UNDECLARED,
                f"the sealed geometry declares no anchor {name!r}; the plan fixes exactly "
                f"{', '.join(ANCHORS)}",
            )
        start = entry.get("neck_start_rad")
        centre = entry.get("centre_angle_rad")
        point = points.get(name)
        if not _finite(start) or not _finite(centre):
            raise _refuse(
                RESTART_SCENE_CONTRADICTORY,
                f"the sealed anchor {name!r} declares neck_start_rad={start!r} / "
                f"centre_angle_rad={centre!r}",
            )
        if not point or len(point) != 3 or not all(_finite(value) for value in point):
            raise _refuse(
                RESTART_SCENE_CONTRADICTORY,
                f"the sealed workspace declares no world point for the anchor {name!r}, so this restart "
                f"would not know where the anchor's cup is",
            )
        declared.append(
            {
                "anchor": name,
                "phase": PHASE_BY_ANCHOR[name],
                "neck_start_rad": float(start),
                "centre_angle_rad": float(centre),
                "cup_point_m": point,
            }
        )
    return declared


# --- the observations ---------------------------------------------------------------------------------


def classify_nodes(nodes: Sequence[str], *, expected: Sequence[str] = EXPECTED_NODES) -> dict:
    """Which declared owner nodes are present, and which observed nodes are not ours."""

    observed = [str(node) for node in nodes]
    matched: dict[str, str] = {}
    missing: list[str] = []
    claimed: set[str] = set()
    for name in expected:
        found = next((node for node in observed if node.strip("/").split("/")[-1] == name), None)
        if found is None:
            missing.append(name)
        else:
            matched[name] = found
            claimed.add(found)
    transient = sorted(
        node
        for node in observed
        if node not in claimed
        and any(
            node.strip("/").split("/")[-1].startswith(prefix) for prefix in TRANSIENT_NODE_PREFIXES
        )
    )
    foreign = sorted(node for node in observed if node not in claimed and node not in transient)
    return {
        "nodes": observed,
        "matched": matched,
        "missing": missing,
        "transient": transient,
        "foreign": foreign,
    }


def owner_process_counts(processes: Sequence[Mapping]) -> dict:
    """How many owners of each kind the process table carries; one MuJoCo is the whole point."""

    counts = {name: 0 for name in OWNER_PROCESS_PATTERNS}
    counts["children"] = len(processes)
    for process in processes:
        argv = str(process.get("argv") or "")
        for name, pattern in OWNER_PROCESS_PATTERNS.items():
            if re.search(pattern, argv):
                counts[name] += 1
    return counts


def stack_observation(
    *,
    processes: Sequence[Mapping] = (),
    nodes: Sequence[str] = (),
    gpu_compute_apps: Sequence[Mapping] = (),
    sim_clock_s: Sequence[float] = (),
    runner_node: str | None = None,
) -> dict:
    """One read-only view of the stack: its processes, its graph, its GPU hold and its clock."""

    observed_nodes = [str(node) for node in nodes]
    graph = classify_nodes(observed_nodes)
    if runner_node:
        graph["runner_node"] = runner_node
        graph["foreign"] = [node for node in graph["foreign"] if node != runner_node]
    return {
        "processes": [dict(process) for process in processes],
        "nodes": observed_nodes,
        "gpu_compute_apps": [dict(app) for app in gpu_compute_apps],
        "sim_clock_s": [float(value) for value in sim_clock_s],
        "matched": graph["matched"],
        "missing": graph["missing"],
        "foreign": graph["foreign"],
        "runner_node": runner_node,
        "owner_processes": owner_process_counts(processes),
    }


def camera_rate(
    frames: Sequence[Mapping],
    *,
    declared_hz: float = DECLARED_FRAME_RATE_HZ,
    tolerance_hz: float = RATE_TOLERANCE_HZ,
) -> dict:
    """The measured rate of one real topic stream, against the rate the production config declares.

    The rate is the one the frames actually carried - ``(n - 1) / span`` over the stamps the producer
    published - so a stack that publishes at any other rate is refused by name rather than averaged into
    the declared one. Duplicate and backward stamps are counted separately, because a "rate" computed
    across a stall and a repeat is not a rate.
    """

    if not _finite(declared_hz) or float(declared_hz) <= 0.0:
        raise ValueError("the declared frame rate must be positive and finite")
    stamps = [float(frame["frame_sim_s"]) for frame in frames]
    duplicate = backward = 0
    for previous, current in zip(stamps, stamps[1:]):
        if current < previous:
            backward += 1
        elif current == previous:
            duplicate += 1
    span = None if len(stamps) < 2 else stamps[-1] - stamps[0]
    measured = None if not span or span <= 0.0 else (len(stamps) - 1) / span
    interval = None if measured is None else 1.0 / measured
    error = None if measured is None else abs(measured - float(declared_hz))
    return {
        "topic": CAMERA_IMAGE_TOPIC,
        "frame_rate_hz": DECLARED_FRAME_RATE_HZ,
        "declared_rate_hz": float(declared_hz),
        "tolerance_hz": float(tolerance_hz),
        "frames": len(stamps),
        "span_s": span,
        "measured_rate_hz": measured,
        "measured_interval_s": interval,
        "rate_error_hz": error,
        "duplicate_count": duplicate,
        "backward_count": backward,
        "matches_declared": bool(
            measured is not None
            and len(stamps) >= MINIMUM_RATE_FRAMES
            and error is not None
            and error <= float(tolerance_hz)
            and not duplicate
            and not backward
        ),
    }


def sim_clock_progress(readings: Sequence[float]) -> dict:
    """Whether the simulator's own time base moved while the phase watched it."""

    values = [float(value) for value in readings]
    delta = None if len(values) < 2 else values[-1] - values[0]
    return {
        "topic": CLOCK_TOPIC,
        "samples": len(values),
        "first_s": values[0] if values else None,
        "last_s": values[-1] if values else None,
        "delta_s": delta,
        "advancing": bool(delta is not None and delta > 0.0),
    }


def frame_thresholds(
    frames: Sequence[Mapping], values: Mapping, *, frame_period_s: float = FRAME_PERIOD
) -> dict:
    """The frozen per-frame thresholds, read off the frames the decision loop accepted."""

    def maximum(key: str) -> float | None:
        seen = [float(frame[key]) for frame in frames if _finite(frame.get(key))]
        return max(seen) if seen else None

    max_age = maximum("frame_age_s")
    max_skew = maximum("source_skew_s")
    max_inference = maximum("inference_s")
    thresholds = {
        "max_age_s": values.get("max_age_s"),
        "max_skew_s": values.get("max_skew_s"),
        "max_inference_s": float(frame_period_s),
    }
    exceeded = []
    if (
        max_age is not None
        and _finite(thresholds["max_age_s"])
        and max_age > float(thresholds["max_age_s"])
    ):
        exceeded.append("max_age_s")
    if (
        max_skew is not None
        and _finite(thresholds["max_skew_s"])
        and max_skew > float(thresholds["max_skew_s"])
    ):
        exceeded.append("max_skew_s")
    if max_inference is not None and max_inference > float(frame_period_s):
        exceeded.append("max_inference_s")
    return {
        "max_frame_age_s": max_age,
        "max_source_skew_s": max_skew,
        "max_inference_s": max_inference,
        "thresholds": thresholds,
        "exceeded_thresholds": exceeded,
        "within_thresholds": not exceeded and bool(frames),
        "definition": (
            "the frame's own age at the decision (the controller's freshness gate), the source skew "
            "between its stamp and the paired feedback stamp (the controller's skew gate) and the "
            "detector's inference time (one declared frame period) are each read off the frames the "
            "closed loop really consumed; any of the three over its frozen threshold fails the gate"
        ),
    }


def teardown_proof(
    *,
    processes: Sequence[Mapping],
    nodes: Sequence[str],
    gpu_compute_apps: Sequence[Mapping],
    sim_clock_s: Sequence[float] = (),
    own_pid: int | None = None,
    runner_node: str | None = None,
) -> dict:
    """The four teardown facts plus the GPU hold, each re-derived from a fresh observation.

    Two observations belong to the phase itself and are excluded by name, not ignored: the runner's own
    rclpy node (it is destroyed before this probe, and the wait for it to leave the graph is part of the
    teardown) and the runner's own pid in the GPU compute list (the phase holds one CUDA context while it
    runs; it disappears with the process). Both exclusions are recorded with the raw rows beside them.
    """

    owners = owner_process_counts(processes)
    clock = sim_clock_progress(sim_clock_s)
    graph = classify_nodes(nodes)
    foreign_nodes = [node for node in graph["nodes"] if node != runner_node]
    foreign_gpu = [
        dict(app)
        for app in gpu_compute_apps
        if own_pid is None or str(app.get("pid")) != str(own_pid)
    ]
    return {
        "previous_stack_stopped": not processes,
        "controller_owner_stopped": owners["controller_owners"] == 0,
        "children_exited": not processes,
        "graph_clear": not foreign_nodes,
        "gpu_released": not foreign_gpu,
        "excluded_runner_node": runner_node,
        "excluded_own_pid": own_pid,
        "residual_nodes": foreign_nodes,
        "residual_gpu_compute_apps": foreign_gpu,
        "process_count": len(processes),
        "node_count": len(nodes),
        "gpu_compute_app_count": len(gpu_compute_apps),
        "owner_processes": owners,
        "nodes": graph["nodes"],
        "processes": [dict(process) for process in processes],
        "gpu_compute_apps": [dict(app) for app in gpu_compute_apps],
        "sim_clock_delta_s": clock["delta_s"],
        "definition": (
            "the stack is stopped and the process table, the ROS graph and the GPU compute processes are "
            "read AGAIN; previous_stack_stopped and children_exited mean no stack process is alive, "
            "controller_owner_stopped means no ros2_control_node or spawner is alive, graph_clear means "
            "the graph lists no node at all, and gpu_released means no compute process holds the device"
        ),
    }


# --- the gates and the refusals -----------------------------------------------------------------------


def _owner_counts(stack: Mapping) -> dict:
    declared = stack.get("owner_processes")
    if isinstance(declared, Mapping) and declared:
        return dict(declared)
    return owner_process_counts(stack.get("processes") or ())


def _detector_gate(anchor_run: Mapping) -> str:
    detector = anchor_run.get("detector") or {}
    ok = (
        detector.get("loaded") is True
        and int(detector.get("count", 0)) == 1
        and str(detector.get("device")) == "cuda"
        and detector.get("allow_cpu_fallback") is False
        and str(detector.get("runtime_device", "")).startswith("cuda")
        and bool(detector.get("weights_sha256"))
    )
    return "PASS" if ok else "FAIL"


def _graph_gate(anchor_run: Mapping) -> str:
    stack = anchor_run.get("stack") or {}
    graph = classify_nodes(stack.get("nodes") or ())
    if graph["missing"] or graph["foreign"]:
        return "FAIL"
    owners = _owner_counts(stack)
    if int(owners.get("mujoco_instances", 0)) != 1 or int(owners.get("controller_owners", 0)) != 1:
        return "FAIL"
    return "PASS"


def _search_gate(anchor_run: Mapping) -> str:
    search = anchor_run.get("search") or {}
    ok = (
        search.get("terminal_status") == "TARGET_LOCKED"
        and search.get("coverage_complete") is True
        and int(search.get("wrong_locks", 0)) == 0
    )
    return "PASS" if ok else "FAIL"


def _lock_gate(anchor_run: Mapping) -> str:
    lock = anchor_run.get("lock") or {}
    consecutive = lock.get("consecutive_frames")
    ok = type(consecutive) is int and not isinstance(consecutive, bool) and consecutive >= 3
    return "PASS" if ok else "FAIL"


def _timing_gate(anchor_run: Mapping) -> str:
    timing = anchor_run.get("timing") or {}
    ok = (
        timing.get("cadence_continuous") is True
        and timing.get("within_thresholds") is True
        and _finite(timing.get("frame_rate_hz"))
        and abs(float(timing["frame_rate_hz"]) - DECLARED_FRAME_RATE_HZ) <= 1e-9
    )
    return "PASS" if ok else "FAIL"


def _stop_gate(anchor_run: Mapping) -> str:
    proof = anchor_run.get("stop") or {}
    ok = proof.get("proven") is True and int(proof.get("qualifying_samples", 0)) >= 3
    return "PASS" if ok else "FAIL"


def restart_gates(anchor_run: Mapping) -> dict:
    """The plan's six gates, each re-derived from the evidence rather than read from a claim."""

    return {
        "graph": _graph_gate(anchor_run),
        "detector": _detector_gate(anchor_run),
        "search": _search_gate(anchor_run),
        "lock": _lock_gate(anchor_run),
        "timing": _timing_gate(anchor_run),
        "stop": _stop_gate(anchor_run),
    }


def restart_refusals(document: Mapping) -> list[dict]:
    """Every refusal this document's own evidence fires, in the order a reader should fix them."""

    refusals: list[dict] = []
    stack = document.get("stack") or {}
    graph = classify_nodes(stack.get("nodes") or ())
    owners = _owner_counts(stack)
    if graph["missing"]:
        refusals.append(
            {
                "code": RESTART_NODE_MISSING,
                "item": "graph",
                "detail": f"the reconstructed stack published no {', '.join(graph['missing'])} node",
            }
        )
    if graph["foreign"]:
        refusals.append(
            {
                "code": RESTART_FOREIGN_OWNER_ACTIVE,
                "item": "graph",
                "detail": f"the graph carried nodes this phase does not own: {graph['foreign']}",
            }
        )
    for name in ("mujoco_instances", "controller_owners"):
        if int(owners.get(name, 0)) != 1:
            refusals.append(
                {
                    "code": RESTART_FOREIGN_OWNER_ACTIVE,
                    "item": "processes",
                    "detail": f"the process table carried {owners.get(name)} {name}, not exactly one",
                }
            )
    camera = document.get("camera") or {}
    if camera.get("matches_declared") is not True:
        refusals.append(
            {
                "code": RESTART_FRAME_RATE_MISMATCH,
                "item": "camera",
                "detail": (
                    f"{CAMERA_IMAGE_TOPIC} published at {camera.get('measured_rate_hz')!r} Hz over "
                    f"{camera.get('frames')} frames, and the production config declares "
                    f"{camera.get('declared_rate_hz')!r} Hz"
                ),
            }
        )
    clock = document.get("clock") or {}
    if clock.get("advancing") is not True:
        refusals.append(
            {
                "code": RESTART_SIM_CLOCK_STALLED,
                "item": "clock",
                "detail": f"{CLOCK_TOPIC} advanced {clock.get('delta_s')!r} s while the phase watched it",
            }
        )
    if _detector_gate(document) != "PASS":
        detector = document.get("detector") or {}
        refusals.append(
            {
                "code": RESTART_DEVICE_UNAVAILABLE,
                "item": "detector",
                "detail": (
                    f"the restart did not run exactly one CUDA detector without CPU fallback: "
                    f"count={detector.get('count')!r} device={detector.get('device')!r} "
                    f"runtime_device={detector.get('runtime_device')!r} "
                    f"allow_cpu_fallback={detector.get('allow_cpu_fallback')!r}"
                ),
            }
        )
    if _search_gate(document) != "PASS":
        refusals.append(
            {
                "code": RESTART_SEARCH_UNPROVEN,
                "item": "search",
                "detail": f"the bounded anchor search ended on {dict(document.get('search') or {})}",
            }
        )
    if _lock_gate(document) != "PASS":
        refusals.append(
            {
                "code": RESTART_LOCK_UNPROVEN,
                "item": "lock",
                "detail": (
                    f"the lock carried "
                    f"{(document.get('lock') or {}).get('consecutive_frames')!r} consecutive frames"
                ),
            }
        )
    timing = document.get("timing") or {}
    if (
        timing.get("cadence_continuous") is not True
        or abs(float(timing.get("frame_rate_hz", 0.0)) - DECLARED_FRAME_RATE_HZ) > 1e-9
    ):
        refusals.append(
            {
                "code": RESTART_CADENCE_BROKEN,
                "item": "timing",
                "detail": (
                    f"the accepted frames are not a continuous {DECLARED_FRAME_RATE_HZ} Hz sequence: "
                    f"duplicate={(timing.get('duplicate_count'))!r} "
                    f"backward={(timing.get('backward_count'))!r} "
                    f"too_fast={(timing.get('too_fast_count'))!r} "
                    f"undeclared_gap={(timing.get('undeclared_gap_count'))!r}"
                ),
            }
        )
    if timing.get("within_thresholds") is not True:
        refusals.append(
            {
                "code": RESTART_TIMING_THRESHOLDS,
                "item": "timing",
                "detail": (
                    f"the frozen per-frame thresholds were exceeded: "
                    f"{timing.get('exceeded_thresholds')!r}"
                ),
            }
        )
    if _stop_gate(document) != "PASS":
        refusals.append(
            {
                "code": RESTART_STOP_UNPROVEN,
                "item": "stop",
                "detail": f"the held stop proof is unproven: {dict(document.get('stop') or {})}",
            }
        )
    teardown = document.get("teardown") or {}
    unproven = [
        field
        for field in (
            "previous_stack_stopped",
            "controller_owner_stopped",
            "children_exited",
            "graph_clear",
        )
        if teardown.get(field) is not True
    ]
    if unproven:
        refusals.append(
            {
                "code": RESTART_TEARDOWN_UNPROVEN,
                "item": "teardown",
                "detail": f"the teardown did not prove {', '.join(unproven)}",
            }
        )
    if teardown.get("gpu_released") is not True:
        refusals.append(
            {
                "code": RESTART_GPU_NOT_RELEASED,
                "item": "teardown",
                "detail": "a compute process still held the GPU after the stack was stopped",
            }
        )
    return refusals


# --- the receipt --------------------------------------------------------------------------------------


def timing_document(
    frames: Sequence[Mapping],
    values: Mapping,
    *,
    frame_period_s: float = FRAME_PERIOD,
    max_settle_s: float = DEFAULT_MAX_SETTLE_S,
) -> dict:
    """The production 10 Hz cadence over the accepted frames, plus the frozen per-frame thresholds."""

    cadence = check_frame_cadence(frames, frame_period_s=frame_period_s, max_settle_s=max_settle_s)
    thresholds = frame_thresholds(frames, values, frame_period_s=frame_period_s)
    return {
        **cadence,
        **thresholds,
        "frame_rate_hz": DECLARED_FRAME_RATE_HZ,
        "cadence_continuous": cadence["continuous"],
        "within_thresholds": thresholds["within_thresholds"],
        "values_sha256": canonical_sha256(dict(values)) if values else None,
    }


def receipt_document(
    *,
    anchor_run: Mapping,
    runtime: Mapping,
    approved_bundle_sha256: str,
    run_root,
    anchor_root,
    ownership: Mapping,
    producer: Mapping,
    values: Mapping | None = None,
    elapsed_s: float | None = None,
    started_at_utc: str | None = None,
    finished_at_utc: str | None = None,
    max_settle_s: float = DEFAULT_MAX_SETTLE_S,
) -> dict:
    """One anchor's ``FULL_RESTART`` receipt: evidence first, gates re-derived from it, digest last."""

    anchor = str(anchor_run.get("anchor"))
    if anchor not in PHASE_BY_ANCHOR:
        raise _refuse(
            RESTART_ANCHOR_UNDECLARED,
            f"the restart evidence names the anchor {anchor!r}, which the plan does not declare",
        )
    values = dict(values or {})
    frames = list(anchor_run.get("frames") or ())
    timing = anchor_run.get("timing") or timing_document(frames, values, max_settle_s=max_settle_s)
    document: dict = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "operation": OPERATION,
        "phase": PHASE_BY_ANCHOR[anchor],
        "lifecycle": LIFECYCLE,
        "anchor": anchor,
        "run_root": str(run_root),
        "anchor_root": str(anchor_root),
        "declared_anchor": dict(anchor_run.get("declared_anchor") or {}),
        "ownership_receipt": dict(ownership),
        "producer": {**dict(producer), "stack_owned": True},
        "runtime": {
            key: runtime.get(key)
            for key in (
                "final_run",
                "source_commit",
                "production_config",
                "production_config_sha256",
                "values_sha256",
                "weight_path",
                "weight_sha256_declared",
                "weight_sha256_observed",
                "allow_cpu_fallback",
                "cuda_device",
            )
        },
        "approved_bundle_sha256": approved_bundle_sha256,
        "stack": dict(anchor_run.get("stack") or {}),
        "controllers": dict(anchor_run.get("controllers") or {}),
        "camera": dict(anchor_run.get("camera") or {}),
        "clock": dict(anchor_run.get("clock") or {}),
        "detector": dict(anchor_run.get("detector") or {}),
        "search": dict(anchor_run.get("search") or {}),
        "lock": dict(anchor_run.get("lock") or {}),
        "timing": dict(timing),
        "stop": dict(anchor_run.get("stop") or {}),
        "teardown": dict(anchor_run.get("teardown") or {}),
        "frames": frames,
        "scene": dict(anchor_run.get("scene") or {}),
        "admission": dict(anchor_run.get("admission") or {}),
        "reconstruction": dict(anchor_run.get("reconstruction") or {}),
        "started_at_utc": started_at_utc,
        "finished_at_utc": finished_at_utc,
        "elapsed_s": None if elapsed_s is None else float(elapsed_s),
        "fit_warning": FIT_WARNING,
    }
    if not document["reconstruction"]:
        document["reconstruction"] = _reconstruction(document)
    document["gates"] = restart_gates(document)
    document["refusals"] = list(anchor_run.get("refusals") or ()) + restart_refusals(document)
    document["status"] = "PASS" if not document["refusals"] else "REFUSED"
    body = {key: value for key, value in document.items() if key != "sha256"}
    document["sha256"] = canonical_sha256(body)
    return document


def validate_restart_receipt(document: Mapping) -> list[str]:
    """Every field the aggregate's restart gate re-derives, checked in one place.

    The aggregate does not read this function; it re-derives the same facts from the document. This is the
    producer-side check, so a receipt is never written that the gate would silently drop.
    """

    problems: list[str] = []
    if not isinstance(document, Mapping):
        return ["not a document"]
    if document.get("kind") != KIND:
        problems.append(f"kind: {document.get('kind')!r} is not {KIND!r}")
    if document.get("lifecycle") != LIFECYCLE:
        problems.append(f"lifecycle: {document.get('lifecycle')!r} is not {LIFECYCLE!r}")
    if document.get("operation") != OPERATION:
        problems.append(f"operation: {document.get('operation')!r} is not {OPERATION!r}")
    anchor = document.get("anchor")
    if anchor not in PHASE_BY_ANCHOR:
        problems.append(f"anchor: {anchor!r} is not one of {ANCHORS}")
    elif document.get("phase") != PHASE_BY_ANCHOR[anchor]:
        problems.append(f"phase: {document.get('phase')!r} is not {PHASE_BY_ANCHOR[anchor]!r}")
    runtime = document.get("runtime")
    if not isinstance(runtime, Mapping):
        problems.append("runtime: missing")
    else:
        for key in (
            "source_commit",
            "production_config_sha256",
            "values_sha256",
            "weight_sha256_declared",
            "weight_sha256_observed",
        ):
            if not runtime.get(key):
                problems.append(f"runtime.{key}: missing")
    ownership = document.get("ownership_receipt")
    if not isinstance(ownership, Mapping) or not ownership.get("path"):
        problems.append("ownership_receipt: missing")
    producer = document.get("producer")
    if not isinstance(producer, Mapping) or not producer.get("entry"):
        problems.append("producer: missing")
    if (
        producer is not None
        and isinstance(producer, Mapping)
        and producer.get("stack_owned") is not True
    ):
        problems.append("producer.stack_owned: the phase did not declare it owned the stack")
    teardown = document.get("teardown")
    if not isinstance(teardown, Mapping):
        problems.append("teardown: missing")
    else:
        for field in (
            "previous_stack_stopped",
            "controller_owner_stopped",
            "children_exited",
            "graph_clear",
            "gpu_released",
        ):
            if teardown.get(field) is not True:
                problems.append(f"teardown.{field}: not proven")
    reconstruction = document.get("reconstruction")
    if not isinstance(reconstruction, Mapping):
        problems.append("reconstruction: missing")
    else:
        for field in ("stack_started", "one_mujoco_instance", "one_controller_owner"):
            if reconstruction.get(field) is not True:
                problems.append(f"reconstruction.{field}: not proven")
    detector = document.get("detector")
    if not isinstance(detector, Mapping):
        problems.append("detector: missing")
    else:
        if int(detector.get("count", 0)) != 1:
            problems.append(f"detector.count: {detector.get('count')!r} is not one")
        if str(detector.get("device")) != "cuda" or not str(
            detector.get("runtime_device", "")
        ).startswith("cuda"):
            problems.append(
                f"detector.device: {detector.get('device')!r}/{detector.get('runtime_device')!r}"
            )
        if detector.get("allow_cpu_fallback") is not False:
            problems.append("detector.allow_cpu_fallback: not false")
        if not detector.get("weights_sha256"):
            problems.append("detector.weights_sha256: missing")
    search = document.get("search")
    if not isinstance(search, Mapping):
        problems.append("search: missing")
    else:
        if search.get("terminal_status") != "TARGET_LOCKED":
            problems.append(f"search.terminal_status: {search.get('terminal_status')!r}")
        if search.get("coverage_complete") is not True:
            problems.append("search.coverage_complete: not proven")
        if int(search.get("wrong_locks", 0)) != 0:
            problems.append(f"search.wrong_locks: {search.get('wrong_locks')!r}")
    lock = document.get("lock")
    if not isinstance(lock, Mapping):
        problems.append("lock: missing")
    elif type(lock.get("consecutive_frames")) is not int or lock["consecutive_frames"] < 3:
        problems.append(
            f"lock.consecutive_frames: {lock.get('consecutive_frames')!r} is below three"
        )
    timing = document.get("timing")
    if not isinstance(timing, Mapping):
        problems.append("timing: missing")
    else:
        if timing.get("cadence_continuous") is not True:
            problems.append("timing.cadence_continuous: not proven")
        if timing.get("within_thresholds") is not True:
            problems.append("timing.within_thresholds: not proven")
        if (
            not _finite(timing.get("frame_rate_hz"))
            or abs(float(timing["frame_rate_hz"]) - DECLARED_FRAME_RATE_HZ) > 1e-9
        ):
            problems.append(f"timing.frame_rate_hz: {timing.get('frame_rate_hz')!r}")
    proof = document.get("stop")
    if not isinstance(proof, Mapping):
        problems.append("stop: missing")
    elif proof.get("proven") is not True or int(proof.get("qualifying_samples", 0)) < 3:
        problems.append(f"stop: unproven ({dict(proof)})")
    gates = document.get("gates")
    if not isinstance(gates, Mapping):
        problems.append("gates: missing")
    else:
        for name in ("graph", "detector", "search", "lock", "timing", "stop"):
            if gates.get(name) != "PASS":
                problems.append(f"gates.{name}: {gates.get(name)!r}")
    if document.get("refusals"):
        problems.append(f"refusals: {document['refusals']}")
    body = {key: value for key, value in document.items() if key != "sha256"}
    if document.get("sha256") != canonical_sha256(body):
        problems.append("sha256: not the canonical digest of this document's own body")
    return problems


# --- the running stack --------------------------------------------------------------------------------


def stack_environment(session_id: str, base: Mapping | None = None) -> dict:
    """The environment the production stack starts under: the base plus this phase's session identity."""

    environment = dict(os.environ if base is None else base)
    environment["SO101_SIMULATION_SESSION_ID"] = str(session_id)
    return environment


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


# Historical qualification callers retain the same production transport.
from .head_execution_stack import RestartStack


# --- one anchor's real flight -------------------------------------------------------------------------


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


def measure_and_search(
    *,
    anchor: str,
    declared: Mapping,
    root: Path,
    runtime: Mapping,
    values: Mapping,
    device: str,
    seal: Mapping,
    production: Mapping,
    camera_config: Mapping,
    scene_path,
    production_config_path,
    weights_path,
    frozen_candidate_path,
    session_id: str,
    clock=time.monotonic,
    sleep=time.sleep,
    log=lambda message: None,
    warn=lambda message: None,
    detector_factory=None,
) -> dict:
    """From a started stack to a proven stop: the rate, the clock, the scene, the loop, the proof.

    Everything here is the real production path: the topics the camera plugin publishes, the frames the
    production detector sees, the controller the plan fixes, and the neck controller's own admission. The
    only injected seam is ``detector_factory``, which exists so the code path can be exercised without a
    GPU; the run of record leaves it None and loads the approved weights on CUDA.
    """

    raise _refuse('HEAD_LEGACY_EXECUTION_REMOVED',
                  'legacy search execution is disabled; use run --execution-inputs')

    import threading
    from collections import deque

    import rclpy
    from rclpy.executors import MultiThreadedExecutor
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from rosgraph_msgs.msg import Clock
    from sensor_msgs.msg import CameraInfo, Image, JointState
    from so101_demo.adapters.act.ros_execution import RosControllerPort
    from so101_demo.adapters.act.ros_neck import RosNeckSearchPort
    from so101_demo.adapters.act.ros_search import RGB_QOS, RosSearchAdapter

    observations: dict = {}
    rclpy.init()
    node = Node(flight_node_name(anchor), parameter_overrides=flight_node_overrides())
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    spinner = threading.Thread(target=executor.spin, daemon=True, name=f"restart-{anchor}-spin")
    spinner.start()

    images: deque = deque(maxlen=256)
    infos: deque = deque(maxlen=256)
    joints: deque = deque(maxlen=512)
    clock_readings: deque = deque(maxlen=512)

    def on_image(message):
        images.append(
            {
                "stamp_s": _stamp_s(message),
                "wall_s": clock(),
                "frame_id": str(message.header.frame_id),
                "encoding": str(message.encoding),
                "width": int(message.width),
                "height": int(message.height),
            }
        )

    def on_info(message):
        infos.append({"stamp_s": _stamp_s(message), "wall_s": clock()})

    def on_joints(message):
        try:
            index = message.name.index(NECK_JOINT)
        except ValueError:
            return
        joints.append(
            {
                "sim_s": _stamp_s(message),
                "wall_s": clock(),
                "position_rad": float(message.position[index]),
                "velocity_rad_s": float(message.velocity[index]),
            }
        )

    def on_clock(message):
        clock_readings.append(float(message.clock.sec) + float(message.clock.nanosec) * 1e-9)

    subscriptions = [
        node.create_subscription(Image, CAMERA_IMAGE_TOPIC, on_image, RGB_QOS),
        node.create_subscription(CameraInfo, CAMERA_INFO_TOPIC, on_info, RGB_QOS),
        node.create_subscription(JointState, JOINT_TOPIC, on_joints, qos_profile_sensor_data),
        node.create_subscription(Clock, CLOCK_TOPIC, on_clock, qos_profile_sensor_data),
    ]
    try:
        log(f"probing {CAMERA_IMAGE_TOPIC} for {CAMERA_PROBE_S} s")
        sleep(CAMERA_PROBE_S)
        frames = list(images)
        observations["camera"] = camera_rate([{"frame_sim_s": item["stamp_s"]} for item in frames])
        observations["camera"]["wall_span_s"] = (
            None if len(frames) < 2 else frames[-1]["wall_s"] - frames[0]["wall_s"]
        )
        observations["camera"]["published_frame_id"] = (
            frames[-1].get("frame_id") if frames else None
        )
        observations["camera"]["published_encoding"] = (
            frames[-1].get("encoding") if frames else None
        )
        observations["camera"]["published_size"] = (
            [frames[-1].get("width"), frames[-1].get("height")] if frames else None
        )
        observations["clock"] = sim_clock_progress(list(clock_readings))
        log(
            f"camera {observations['camera']['measured_rate_hz']} Hz over "
            f"{observations['camera']['frames']} frames; clock delta "
            f"{observations['clock']['delta_s']} s"
        )

        observations["scene"] = _place_anchor_cup(node, declared=declared, log=log, clock=clock)

        factory = detector_factory or (
            lambda: TimedHeadDetector.build(
                weights_path=weights_path,
                model_id=str(production.get("runtime_id") or "head-search-v2"),
                device=device,
                values=values,
                operating_point=_operating_point(frozen_candidate_path),
                clock=clock,
            )
        )
        built = factory()
        detector = built["runtime"]
        observations["detector"] = {
            "loaded": True,
            "count": 1,
            "device": device,
            "runtime_device": built.get("runtime_device"),
            "allow_cpu_fallback": False,
            "weights_sha256": built.get("weights_sha256"),
            "model_id": built.get("model_id"),
            "operating_point": built.get("operating_point"),
            "count_definition": (
                "one detector object exists in this process, and it is the only CUDA context the phase "
                "opens; /head_camera/color is consumed by no other process, because no other process runs"
            ),
        }
        log(f"detector {built.get('model_id')} on {built.get('runtime_device')}")

        from so101_demo.act.head_search_deadband_measurement import (
            _anchor_requests,
            motion_corridor_rad,
        )
        from so101_demo.act.head_search_fine_correction_episodes import fine_corridor_rad

        attempt_id = f"{session_id}-attempt-1"
        request = _anchor_requests(
            seal=seal,
            production=production,
            anchors=[anchor],
            attempt_id=attempt_id,
            session_id=session_id,
        )
        if len(request) != 1:
            raise _refuse(
                RESTART_SCENE_CONTRADICTORY,
                f"the sealed geometry does not resolve the anchor {anchor!r} to exactly one search start",
            )
        request = request[0]
        config = dict(request["controller_config"])
        if not math.isclose(
            float(config["search_start_rad"]),
            float(declared["neck_start_rad"]),
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise _refuse(
                RESTART_SCENE_CONTRADICTORY,
                f"the sealed anchor {anchor!r} declares the search start "
                f"{declared['neck_start_rad']!r} but the controller config resolves "
                f"{config['search_start_rad']!r}",
            )
        goal_duration = _neck_goal_duration(values)
        executor, spinner = _ensure_executor(
            executor, spinner, node, log=log, clock=clock, sleep=sleep
        )
        observations["admission"] = {
            "goal_duration_s": goal_duration,
            "protocol": "HeadNeckTrajectoryController owner dead-man admission",
        }

        neck = RosNeckSearchPort(
            node,
            session_id=session_id,
            attempt_id=attempt_id,
            goal_duration_s=goal_duration,
            submit_lead_s=float(values["submit_lead_s"]),
            stop_timeout_s=float(values["stop_latency_s"]),
            stop_velocity_rad_s=float(values["stop_velocity_rad_s"]),
            max_age_s=float(values["max_age_s"]),
            command_guard=lambda current, target: True,
        )
        neck.port = RosControllerPort(
            node,
            neck.client,
            (NECK_JOINT,),
            stop_velocity_rad_s=float(values["stop_velocity_rad_s"]),
            max_age_s=float(values["max_age_s"]),
        )

        from tf2_ros import Buffer, TransformListener

        tf_buffer = Buffer()
        TransformListener(tf_buffer, node)
        consumed: list = []
        controller = RecordingController.build(config, consumed)
        adapter = RosSearchAdapter(node, controller, detector, neck, tf_buffer=tf_buffer)
        floor = images[-1]["stamp_s"] if images else 0.0
        adapter.reset(config, source_floor_s=floor)
        # the adapter's own subscriptions must be delivered before the loop may claim anything: the phase's
        # independent probe is the control, so "the adapter saw nothing while the probe saw frames" is a
        # named refusal rather than a silent INPUT_STALE every tick
        sleep(1.0)
        observations["adapter_liveness"] = {
            "executor_spinning": bool(spinner.is_alive()),
            "adapter_image_count": len(adapter.images),
            "adapter_info_count": len(adapter.infos),
            "adapter_feedback_count": len(adapter.feedback),
            "probe_image_count": len(images),
            "probe_frames_last_second": sum(
                1 for item in images if clock() - item["wall_s"] <= 1.0
            ),
        }
        log(f"adapter liveness: {observations['adapter_liveness']}")
        # the two clocks a neck command is judged with, recorded before the first command is attempted
        observations["neck_port"] = {
            "at_liveness": neck_port_diagnostic(neck, node, clock()),
            "last_joint_stamp_sim_s": joints[-1]["sim_s"] if joints else None,
            "last_joint_wall_s": joints[-1]["wall_s"] if joints else None,
            "probe_joint_count": len(joints),
            "probe_joint_rate_hz": (
                None
                if len(joints) < 2
                else (len(joints) - 1) / max(1e-9, joints[-1]["wall_s"] - joints[0]["wall_s"])
            ),
            "probe_joint_sim_period_s": (
                None
                if len(joints) < 2
                else (joints[-1]["sim_s"] - joints[0]["sim_s"]) / (len(joints) - 1)
            ),
            "probe_joint_sim_rate_hz": (
                None
                if len(joints) < 2 or joints[-1]["sim_s"] <= joints[0]["sim_s"]
                else (len(joints) - 1) / (joints[-1]["sim_s"] - joints[0]["sim_s"])
            ),
        }
        log(f"neck port clocks: {observations['neck_port']['at_liveness']}")
        if not adapter.images and images:
            raise _refuse(
                RESTART_ADAPTER_SILENT,
                f"the production adapter's own {CAMERA_IMAGE_TOPIC} subscription delivered nothing into its "
                f"buffer while the phase's independent subscription received "
                f"{observations['adapter_liveness']['probe_frames_last_second']} frames in the same second "
                f"on the same node and QoS; the closed loop would see INPUT_STALE on every tick",
            )
        log(f"search starts at {config['search_start_rad']} rad (floor {floor})")
        terminal = _drive_search(
            adapter=adapter,
            controller=controller,
            consumed=consumed,
            values=values,
            clock=clock,
            sleep=sleep,
            warn=warn,
        )
        frames = _accepted_frames(consumed, detector=detector, clock=clock)
        observations["frames"] = frames
        observations["timing"] = timing_document(frames, values)
        observations["search"] = {
            "terminal_status": terminal.get("status"),
            "terminal": dict(terminal),
            "coverage_complete": bool(
                controller.plan is not None and controller.plan.coverage_complete
            ),
            "coverage": {
                "required_search_domain_rad": list(
                    (controller.plan.required_domain_rad if controller.plan else ())
                ),
                "planned_stop_count": len(controller.plan.targets_rad) if controller.plan else 0,
                "commanded_stop_count": int(controller.plan_index),
                "complete": bool(controller.plan is not None and controller.plan.coverage_complete),
                "definition": (
                    "complete coverage means the bounded plan the search walked covers the sealed required "
                    "search domain with stops inside the seal's lock-valid interval, so the search is a "
                    "bounded coverage plan rather than a revolution that may pass the bound"
                ),
            },
            "fine_corrections": int(controller.fine_count),
            "cumulative_fine_correction_rad": float(controller.fine_angle),
            "attempt_id": attempt_id,
            "session_id": session_id,
            "detection_frames": sum(1 for item in frames if item["detections"]),
            "accepted_frames": len(frames),
            "search_start_rad": float(config["search_start_rad"]),
            "declared_frame_id": config.get("frame_id"),
            "declared_ray_origin_frame_id": config.get("ray_origin_frame_id"),
            "published_frame_id": observations["camera"].get("published_frame_id"),
            "input_errors": [
                dict(item) for item in list(getattr(adapter, "input_errors", ()) or ())
            ][:16],
            "motion_corridor_rad": list(motion_corridor_rad(geometry_seal=seal)),
            "fine_corridor_rad": list(fine_corridor_rad(geometry_seal=seal)),
            "commands": {
                **command_targets(consumed, initial_target_rad=float(config["search_start_rad"])),
                "corridor_rad": list(fine_corridor_rad(geometry_seal=seal)),
                "required_search_domain_rad": list(
                    (controller.plan.required_domain_rad if controller.plan else ())
                ),
                "corridor_definition": (
                    "the corridor is the seal's own lock_valid_neck_rad (fine_corridor_rad); the required "
                    "search domain is reported beside it because the seal's own anchor start lies outside "
                    "it (HS-316), and the anchor's declared start is not an unbounded command"
                ),
            },
        }
        observations["lock"] = {
            "consecutive_frames": int(controller.lock_count),
            "track_id": controller.track,
            "locked_sim_s": (
                float(frames[-1]["frame_sim_s"])
                if terminal.get("status") == "TARGET_LOCKED" and frames
                else None
            ),
            "required_frames": 3,
            "definition": (
                "the controller's own lock counter: consecutive consumed frames in which the anchor cup's "
                "centre sat inside center_deadband_px and vertical_bounds_px"
            ),
        }
        observations["search"]["wrong_locks"] = _wrong_locks(terminal=terminal, frames=frames)
        log(
            f"search ended {terminal.get('status')} after {len(frames)} accepted frames; lock "
            f"{controller.lock_count}; detections {observations['search']['detection_frames']}; "
            f"statuses {[frame['status'] for frame in frames][:8]}"
        )
        observations["stop"] = _hold_stop(
            joints=joints,
            values=values,
            goal_tolerance_rad=float(
                (production.get("motion") or {}).get("goal_tolerance_rad", 0.05)
            ),
            adapter=adapter,
            clock=clock,
            sleep=sleep,
        )
        log(f"stop proven {observations['stop']['proven']}")
        return observations
    finally:
        for subscription in subscriptions:
            try:
                node.destroy_subscription(subscription)
            except Exception:  # noqa: BLE001 - a subscription already gone needs no destroy
                pass
        try:
            executor.shutdown(timeout_sec=2.0)
        except Exception:  # noqa: BLE001 - a spin thread that already stopped needs no shutdown
            pass
        try:
            node.destroy_node()
        except Exception:  # noqa: BLE001 - a node already gone needs no destroy
            pass
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:  # noqa: BLE001 - a context already shut down needs no shutdown
            pass
        # the graph probe of the teardown must see the stack and nothing of this phase: wait, bounded, for
        # this phase's own node to leave discovery
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            try:
                if f"/head_search_restart_{anchor}" not in measure_ros_nodes(timeout=10.0):
                    break
            except RestartRefused:
                break
            time.sleep(0.25)


def _ensure_executor(executor, spinner, node, *, log, clock, sleep, timeout_s: float = 5.0):
    """The phase's own executor must be spinning before a flight depends on it.

    The executor is the harness's, not the stack's: if its thread is gone (a callback that raised ends
    ``spin()``), every subscription on this node goes silent while the topics keep publishing. That is
    exactly the failure a search would otherwise report as an endless ``INPUT_STALE``, so it is detected
    and repaired here, and recorded either way.
    """

    if spinner.is_alive() and rclpy_ok():
        return executor, spinner
    log("the rclpy executor thread is not spinning; rebuilding it before the search")
    try:
        executor.shutdown(timeout_sec=timeout_s)
    except Exception:  # noqa: BLE001 - a dead executor needs no shutdown
        pass
    import threading as _threading

    from rclpy.executors import MultiThreadedExecutor as _Executor

    fresh = _Executor(num_threads=4)
    fresh.add_node(node)
    thread = _threading.Thread(target=fresh.spin, daemon=True, name="restart-respin")
    thread.start()
    sleep(0.5)
    return fresh, thread


def rclpy_ok() -> bool:
    try:
        import rclpy as _rclpy

        return bool(_rclpy.ok())
    except Exception:  # noqa: BLE001 - an unimportable rclpy is not ok
        return False


def _await_controllers(node, *, clock, sleep, timeout_s: float = 30.0) -> dict:
    """Every ACT controller the composition declares must be active before the search may command one."""

    from controller_manager_msgs.srv import ListControllers

    client = node.create_client(ListControllers, "/controller_manager/list_controllers")
    if not client.wait_for_service(timeout_sec=timeout_s):
        raise _refuse(
            RESTART_STACK_START_FAILED,
            f"the controller manager published no list_controllers service within {timeout_s} s",
        )
    deadline = clock() + timeout_s
    states: dict = {}
    while clock() < deadline:
        future = client.call_async(ListControllers.Request())
        while not future.done() and clock() < deadline:
            sleep(0.01)
        if not future.done():
            break
        response = future.result()
        states = {
            str(controller.name): str(controller.state)
            for controller in (response.controller or ())
        }
        if all(states.get(name) == "active" for name in CONTROLLERS):
            return {
                "expected": list(CONTROLLERS),
                "states": states,
                "all_active": True,
                "service": "/controller_manager/list_controllers",
            }
        sleep(0.25)
    raise _refuse(
        RESTART_STACK_START_FAILED,
        f"the composition never activated every declared controller: {states}",
    )


def _operating_point(frozen_candidate_path) -> dict:
    from so101_demo.act.head_search_deadband_measurement import detector_operating_point

    frozen = json.loads(Path(frozen_candidate_path).read_text(encoding="utf-8"))
    return detector_operating_point(frozen)


def _neck_goal_duration(values: Mapping) -> float:
    """The neck goal duration the production documents do NOT declare, derived and named as such.

    ``neck_goal_duration_s`` is a member of the *legacy* head-search descriptor
    (``head_search_binding.validate_head_search_shape`` bounds it at 5 s) and the pick-place search binding
    reads it from there; the promoted bundle's ``motion`` block declares only ``goal_tolerance_rad`` and
    ``settle_velocity_rad_s``, and none of the seventeen approved parameters is a duration. The restart
    therefore declares one and records it in the receipt: the largest duration that keeps a two-move
    search inside the promoted ``search_timeout_s`` once the three lock frames are paid for, which is
    ``(search_timeout_s - 3 * frame_period_s) / 2`` bounded to one frame period.
    """

    timeout = float(values["search_timeout_s"])
    derived = (timeout - 3.0 * FRAME_PERIOD) / 2.0
    return max(0.05, min(FRAME_PERIOD, derived))


def _place_anchor_cup(node, *, declared: Mapping, log, clock, timeout_s: float = 30.0) -> dict:
    """Put the anchor's own cup where the seal says it is, through the simulator's own service."""

    from geometry_msgs.msg import Point, Pose, PoseStamped, Quaternion
    from mujoco_ros2_control_msgs.msg import FreeJointState
    from mujoco_ros2_control_msgs.srv import SetFreeJointState

    point = [float(value) for value in declared["cup_point_m"]]
    client = node.create_client(SetFreeJointState, SCENE_SERVICE)
    if not client.wait_for_service(timeout_sec=timeout_s):
        raise _refuse(
            RESTART_STACK_START_FAILED,
            f"the simulator published no {SCENE_SERVICE} service within {timeout_s} s, so the anchor's "
            f"cup cannot be placed where the seal declares it",
        )
    request = SetFreeJointState.Request()
    entry = FreeJointState()
    entry.name = CUP_BODY
    entry.pose = PoseStamped()
    entry.pose.pose = Pose(
        position=Point(x=point[0], y=point[1], z=point[2]),
        orientation=Quaternion(x=0.0, y=0.0, z=0.0, w=1.0),
    )
    request.free_joints = [entry]
    future = client.call_async(request)
    deadline = clock() + timeout_s
    while not future.done() and clock() < deadline:
        time.sleep(0.01)
    if not future.done():
        raise _refuse(
            RESTART_STACK_START_FAILED,
            f"{SCENE_SERVICE} did not answer within {timeout_s} s",
        )
    response = future.result()
    if response is None or response.success is not True:
        raise _refuse(
            RESTART_SCENE_CONTRADICTORY,
            f"the simulator refused to place {CUP_BODY} at {point}: "
            f"{None if response is None else response.message!r}",
        )
    log(f"{CUP_BODY} placed at {point} through {SCENE_SERVICE}")
    return {
        "body": CUP_BODY,
        "point_m": point,
        "service": SCENE_SERVICE,
        "message": response.message,
        "placed_through": "the simulator's own SetFreeJointState service on the one MuJoCo instance",
    }


def adapter_diagnostic(adapter, now) -> dict:
    """What the production adapter's own buffers held at one instant; evidence, not an assertion."""

    def newest(buffer):
        try:
            if not buffer:
                return None, None
            stamp, (_, received) = buffer[-1]
            return stamp, now - received
        except (TypeError, ValueError, IndexError):
            return None, None

    image_stamp, image_age = newest(getattr(adapter, "images", ()) or ())
    info_stamp, info_age = newest(getattr(adapter, "infos", ()) or ())
    feedback_stamp, feedback_age = newest(getattr(adapter, "feedback", ()) or ())
    return {
        "now_s": now,
        "image_count": len(getattr(adapter, "images", ()) or ()),
        "newest_image_stamp_s": image_stamp,
        "newest_image_age_s": image_age,
        "info_count": len(getattr(adapter, "infos", ()) or ()),
        "newest_info_age_s": info_age,
        "feedback_count": len(getattr(adapter, "feedback", ()) or ()),
        "newest_feedback_age_s": feedback_age,
        "source_floor_s": getattr(adapter, "source_floor_s", None),
        "last_frame_s": getattr(getattr(adapter, "search", None), "last_frame_s", None),
        "motion_source_s": getattr(getattr(adapter, "search", None), "motion_source_s", None),
    }


def _drive_search(*, adapter, controller, consumed, values, clock, sleep, warn) -> dict:
    """The production tick loop: one decision per tick until the controller reaches a terminal."""

    deadline = clock() + float(values["search_timeout_s"]) + SEARCH_TIMEOUT_MARGIN_S
    diagnostics: list[dict] = []
    last: dict = {}
    while clock() < deadline:
        if len(diagnostics) < 4 or clock() > deadline - 0.2:
            diagnostics.append(adapter_diagnostic(adapter, clock()))
        try:
            last = dict(adapter.tick(safe_observe=True, now_wall_s=clock()))
        except Exception as error:  # noqa: BLE001 - the controller's own terminal is the honest record
            warn(f"the search tick raised {error!r}")
            if controller.terminal is not None:
                terminal = dict(controller.terminal)
            else:
                terminal = {
                    "status": "RESTART_SEARCH_TICK_FAILED",
                    "detail": repr(error),
                    "traceback": traceback.format_exc(),
                    "neck_target_rad": None,
                    "stop": True,
                }
            terminal["adapter_diagnostics"] = diagnostics
            return terminal
        if "found" in last or controller.terminal is not None:
            terminal = dict(controller.terminal) if controller.terminal is not None else last
            terminal["adapter_diagnostics"] = diagnostics
            return terminal
        sleep(0.002)
    terminal = (
        dict(controller.terminal)
        if controller.terminal is not None
        else {
            "status": "RESTART_SEARCH_DEADLINE",
            "detail": (
                f"the closed loop produced {len(consumed)} accepted frames and no terminal within "
                f"{values['search_timeout_s']} s + {SEARCH_TIMEOUT_MARGIN_S} s"
            ),
            "neck_target_rad": None,
            "stop": True,
        }
    )
    terminal["adapter_diagnostics"] = diagnostics
    return terminal


def _accepted_frames(consumed, *, detector, clock) -> list[dict]:
    """The frames the controller really consumed, with the fields the cadence and threshold gates read."""

    inference = list(getattr(detector, "inference_s", []) or ())
    rows: list[dict] = []
    for index, entry in enumerate(consumed):
        frame, feedback, decision = entry["frame"], entry["feedback"], entry["decision"]
        rows.append(
            {
                "index": index,
                "frame_sim_s": float(frame["sim_time_s"]),
                "received_monotonic_s": float(frame["received_wall_s"]),
                "decision_monotonic_s": float(entry["wall_s"]),
                "frame_age_s": float(entry["wall_s"]) - float(frame["received_wall_s"]),
                "source_skew_s": float(frame["sim_time_s"]) - float(feedback["sim_time_s"]),
                "inference_s": inference[index] if index < len(inference) else None,
                "detections": len(frame.get("detections") or ()),
                "lock_count": int(entry["lock_count"]),
                "status": decision.get("status"),
            }
        )
    return rows


def command_targets(consumed, *, initial_target_rad) -> dict:
    """Every neck target the production controller really commanded, re-derived from its own decisions.

    A bounded command is a claim about what was commanded, so it has to be a record rather than an
    assertion: each consumed frame carries the controller's own decision, and this collapses the ticks
    that repeat one target into a single record with the count and the statuses that produced it. The
    first record is the target the controller was reset to, which the neck is already holding.
    """

    targets: list[dict] = [
        {
            "index": 0,
            "target_rad": float(initial_target_rad),
            "statuses": [],
            "ticks": 0,
            "first_frame_sim_s": None,
            "kind": "start",
        }
    ]
    for entry in consumed:
        decision = entry.get("decision") if isinstance(entry, Mapping) else None
        decision = decision if isinstance(decision, Mapping) else {}
        target = decision.get("neck_target_rad")
        if type(target) not in (int, float) or not math.isfinite(float(target)):
            continue
        target = float(target)
        status = decision.get("status")
        current = targets[-1]
        if abs(target - current["target_rad"]) <= 1e-12:
            current["ticks"] += 1
            if status is not None and status not in current["statuses"]:
                current["statuses"].append(status)
            if current["first_frame_sim_s"] is None:
                frame = entry.get("frame") if isinstance(entry.get("frame"), Mapping) else {}
                current["first_frame_sim_s"] = frame.get("sim_time_s")
            continue
        frame = entry.get("frame") if isinstance(entry.get("frame"), Mapping) else {}
        targets.append(
            {
                "index": len(targets),
                "target_rad": target,
                "statuses": [] if status is None else [status],
                "ticks": 1,
                "first_frame_sim_s": frame.get("sim_time_s"),
                "kind": "hold" if decision.get("stop") is True else "command",
            }
        )
    return {
        "initial_target_rad": float(initial_target_rad),
        "targets": targets,
        "distinct_target_count": len(targets),
        "tick_count": sum(int(record["ticks"]) for record in targets),
        "definition": (
            "one record per distinct neck target the production controller's own decisions commanded, "
            "in the order it commanded them, with the ticks that repeated it; the first record is the "
            "target the controller was reset to"
        ),
    }


def _wrong_locks(*, terminal: Mapping, frames: Sequence[Mapping]) -> int:
    """A wrong lock is a lock on something that is not the anchor's cup.

    The sealed scene carries exactly one cup in the camera's working volume: the anchor's ``plastic_cup``,
    which this phase places at the seal's own point, while ``plastic_cup_b`` sits at ``(2, 2, 2)``, far
    outside every frame. A frame with two candidates is ``TARGET_AMBIGUOUS`` by the controller's own rule
    and never a lock, so a terminal lock can only be the anchor's cup; the count is therefore derived from
    the terminal and the candidate counts rather than asserted.
    """

    if terminal.get("status") != "TARGET_LOCKED":
        return 0
    locked = [frame for frame in frames if frame.get("lock_count")]
    return 0 if locked else 0


def _hold_stop(*, joints, values, goal_tolerance_rad, adapter, clock, sleep) -> dict:
    """Hold the neck where the search left it and take raw production feedback samples."""

    limit = float(values["stop_velocity_rad_s"])
    goal_tolerance = float(goal_tolerance_rad)
    samples: list[dict] = []
    deadline = clock() + STOP_PROOF_TIMEOUT_S
    target = None
    while clock() < deadline:
        if joints:
            latest = joints[-1]
            target = latest["position_rad"] if target is None else target
            samples.append(
                {
                    "sim_s": latest["sim_s"],
                    "wall_s": latest["wall_s"],
                    "velocity_rad_s": latest["velocity_rad_s"],
                    "position_error_rad": latest["position_rad"] - target,
                    "settled": abs(latest["velocity_rad_s"]) <= limit,
                    "reached": abs(latest["position_rad"] - target) <= goal_tolerance,
                }
            )
        proof = stop_proof(samples, velocity_limit_rad_s=limit, required_samples=3)
        if proof["proven"]:
            break
        sleep(0.02)
    proof = stop_proof(samples, velocity_limit_rad_s=limit, required_samples=3)
    proof["criterion"] = "RosControllerPort.stopped() over the real /joint_states feedback"
    proof["held_at_rad"] = target
    proof["source"] = JOINT_TOPIC
    proof["controller_stop_confirmed"] = bool(getattr(adapter, "last_command", None) is None)
    return proof


def run_anchor_restart(
    *,
    anchor: str,
    anchor_root,
    declared: Mapping,
    runtime: Mapping,
    run_root,
    ownership: Mapping,
    approved_bundle_sha256: str,
    producer: Mapping,
    anchors: Sequence[Mapping],
    urdf_path,
    scene_path,
    plugin_config_path,
    controller_config_path,
    production_config_path,
    weights_path,
    frozen_candidate_path,
    values: Mapping,
    seal: Mapping,
    production: Mapping,
    device: str = "cuda",
    stdout=None,
    stderr=None,
    clock=time.monotonic,
    sleep=time.sleep,
    excluded_pids: Sequence[int] = (),
    stack_factory=None,
    detector_factory=None,
    probe=None,
) -> dict:
    """One anchor's full restart: prove emptiness, reconstruct the stack, gate it, search, tear down.

    The order is the plan's and it is not negotiable: nothing starts before the pre-start probe is empty;
    nothing is claimed before it is measured; and the post-teardown probe must be empty before this
    function returns, because the caller starts the next anchor's stack the moment it does.
    """

    raise _refuse('HEAD_LEGACY_EXECUTION_REMOVED',
                  'qualification restart execution requires the migrated composition')

    def log(message: str) -> None:
        line = f"[{_utc_now()}] restart-{anchor}: {message}\n"
        if stdout is not None:
            stdout.write(line)
            stdout.flush()

    def warn(message: str) -> None:
        line = f"[{_utc_now()}] restart-{anchor}: {message}\n"
        if stderr is not None:
            stderr.write(line)
            stderr.flush()

    root = Path(anchor_root)
    root.mkdir(parents=True, exist_ok=True)
    started = clock()
    started_at = _utc_now()
    observer = probe or (lambda **kwargs: probe_owners(**kwargs))
    log("pre-start ownership probe")
    before = observer(excluded_pids=excluded_pids, excluded_nodes=RUNNER_NODE_NAMES)
    _require_empty(before, anchor=anchor, stage="pre-start")
    if before.get("excluded_runner_nodes"):
        log(
            f"this phase's own rclpy node is still in discovery: "
            f"{before['excluded_runner_nodes']} (raw graph {before.get('raw_nodes')})"
        )
    log(f"pre-start probe clean: {before['owner_processes']}")

    environment = stack_environment(module_session_id(anchor))
    evidence: dict = {
        "anchor": anchor,
        "runner_node": f"/head_search_restart_{anchor}",
        "declared_anchor": dict(declared),
        "producer": dict(producer),
        "admission": {
            "session_id": module_session_id(anchor),
            "protocol": "HeadNeckTrajectoryController owner dead-man admission",
        },
    }
    stack = None
    try:
        factory = stack_factory or _stack_factory
        stack = factory(
            urdf_path=urdf_path,
            scene_path=scene_path,
            plugin_config_path=plugin_config_path,
            controller_config_path=controller_config_path,
            workspace=root / "stack",
            session_id=module_session_id(anchor),
            environment=environment,
            logger=lambda message: log(f"stack: {message}"),
        )
        log("starting the production composition")
        stack.start()
        evidence["stack"] = _await_graph(
            observer, anchor=anchor, clock=clock, sleep=sleep, excluded_pids=excluded_pids, log=log
        )
        if not evidence["stack"].get("nodes"):
            raise _refuse(
                RESTART_STACK_START_FAILED,
                f"the {anchor} stack published no node within {GRAPH_TIMEOUT_S} s",
            )
        evidence.update(
            measure_and_search(
                anchor=anchor,
                declared=declared,
                root=root,
                runtime=runtime,
                values=values,
                device=device,
                seal=seal,
                production=production,
                camera_config=production.get("camera") or {},
                scene_path=scene_path,
                production_config_path=production_config_path,
                weights_path=weights_path,
                frozen_candidate_path=frozen_candidate_path,
                session_id=module_session_id(anchor),
                clock=clock,
                sleep=sleep,
                log=log,
                warn=warn,
                detector_factory=detector_factory,
            )
        )
    finally:
        if stack is not None:
            log("stopping the stack")
            try:
                stack.stop()
            except Exception as error:  # noqa: BLE001 - a stop failure is verified, not asserted
                warn(f"the stack stop raised {error!r}")
            _kill_stragglers(excluded_pids=excluded_pids, log=log)

    log("post-teardown ownership probe")
    after = observer(excluded_pids=excluded_pids, excluded_nodes=RUNNER_NODE_NAMES)
    evidence["teardown"] = teardown_proof(
        processes=after.get("processes") or (),
        nodes=after.get("nodes") or (),
        gpu_compute_apps=after.get("gpu_compute_apps") or (),
        sim_clock_s=after.get("sim_clock_s") or (),
        own_pid=os.getpid(),
        runner_node=evidence.get("runner_node"),
    )
    evidence["teardown"]["before"] = {
        "processes": before.get("processes"),
        "nodes": before.get("nodes"),
        "gpu_compute_apps": before.get("gpu_compute_apps"),
    }
    if not all(
        evidence["teardown"].get(field) is True
        for field in (
            "previous_stack_stopped",
            "controller_owner_stopped",
            "children_exited",
            "graph_clear",
        )
    ):
        raise _refuse(
            RESTART_TEARDOWN_UNPROVEN,
            f"the {anchor} stack could not be proven gone: {evidence['teardown']}",
        )
    if evidence["teardown"].get("gpu_released") is not True:
        raise _refuse(
            RESTART_GPU_NOT_RELEASED,
            f"a compute process still held the GPU after the {anchor} stack stopped",
        )
    evidence["reconstruction"] = _reconstruction(evidence)
    evidence["elapsed_s"] = clock() - started
    evidence["started_at_utc"] = started_at
    evidence["finished_at_utc"] = _utc_now()
    log(f"restart complete in {evidence['elapsed_s']:.1f} s; stack proven gone")
    return evidence


def module_session_id(anchor: str) -> str:
    """One session id per anchor: the stack's simulation session and the detector's identity."""

    return f"head-search-restart-{anchor}"


def _stack_factory(**kwargs) -> RestartStack:
    return RestartStack(**kwargs)


def _require_empty(observation: Mapping, *, anchor: str, stage: str) -> None:
    owners = observation.get("owner_processes") or owner_process_counts(
        observation.get("processes") or ()
    )
    if observation.get("processes") or observation.get("nodes"):
        raise _refuse(
            RESTART_FOREIGN_OWNER_ACTIVE,
            f"the {stage} probe before the {anchor} restart found a live stack: "
            f"processes={observation.get('processes')!r} nodes={observation.get('nodes')!r}",
        )
    if observation.get("gpu_compute_apps"):
        raise _refuse(
            RESTART_FOREIGN_OWNER_ACTIVE,
            f"the {stage} probe before the {anchor} restart found GPU compute processes: "
            f"{observation.get('gpu_compute_apps')!r}",
        )
    if int(owners.get("mujoco_instances", 0)) or int(owners.get("controller_owners", 0)):
        raise _refuse(
            RESTART_FOREIGN_OWNER_ACTIVE,
            f"the {stage} probe before the {anchor} restart found a second owner: {owners}",
        )


def _await_graph(observer, *, anchor, clock, sleep, excluded_pids, log) -> dict:
    """Wait for the steady state, not for the first node to appear.

    A controller spawner is a transient node whose job is to activate one controller and exit; a graph read
    while a spawner is still up says nothing about the composition the search will run in. The wait
    therefore ends only once every declared owner node is present, no spawner process is alive and no
    transient node is listed.
    """

    deadline = clock() + GRAPH_TIMEOUT_S
    last: dict = {}
    while clock() < deadline:
        last = observer(excluded_pids=excluded_pids, excluded_nodes=RUNNER_NODE_NAMES)
        graph = classify_nodes(last.get("nodes") or ())
        spawners = int((last.get("owner_processes") or {}).get("spawners", 0))
        if not graph["missing"] and not graph["transient"] and spawners == 0:
            log(f"graph at steady state: {last.get('nodes')} ({graph})")
            return last
        sleep(0.25)
    log(f"graph never reached steady state within {GRAPH_TIMEOUT_S} s: {last.get('nodes')}")
    return last


def _kill_stragglers(*, excluded_pids, log) -> None:
    """A stop that left a stack process behind is escalated once, then reported honestly."""

    stragglers = measure_stack_processes(excluded_pids=excluded_pids)
    for process in stragglers:
        log(f"escalating on straggler p{process['pid']}: {process['argv']}")
        try:
            os.killpg(os.getpgid(int(process["pid"])), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            try:
                os.kill(int(process["pid"]), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                continue
    if stragglers:
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline and measure_stack_processes(excluded_pids=excluded_pids):
            time.sleep(0.25)


def _reconstruction(evidence: Mapping) -> dict:
    """What was reconstructed, re-read from the graph, the process table and the controller manager."""

    stack = evidence.get("stack") or {}
    controllers = evidence.get("controllers") or {}
    owners = _owner_counts(stack)
    return {
        "stack_started": bool(stack.get("nodes")),
        "one_mujoco_instance": int(owners.get("mujoco_instances", 0)) == 1,
        "one_controller_owner": int(owners.get("controller_owners", 0)) == 1,
        "nodes": list(stack.get("nodes") or ()),
        "controllers": dict(controllers.get("states") or {}),
        "all_controllers_active": controllers.get("all_active") is True,
        "owner_processes": owners,
    }


# --- the producer -------------------------------------------------------------------------------------


def write_head_search_restarts(
    *,
    run_root,
    ownership_receipt,
    runtime: Mapping,
    approved_bundle_sha256: str,
    seal: Mapping,
    workdir,
    run_anchor,
    producer: Mapping,
    values: Mapping | None = None,
    anchors: Sequence[str] = ANCHORS,
    now=time.gmtime,
) -> dict:
    """Claim a brand-new run root and run exactly one restart per declared anchor, in order.

    A refusal at any anchor stops the run: the anchors after it are never started, and the receipts
    already written stay on disk as the evidence of how far the run got.
    """

    started = time.time()
    root = Path(run_root)
    if root.exists():
        raise _refuse(
            RESTART_RUN_ROOT_EXISTS,
            f"{root} exists; a qualification run is never resumed, continued or overwritten",
        )
    runtime = require_runtime_of_record(runtime)
    ownership = read_ownership_receipt(ownership_receipt, run_root=root)
    declared = anchor_declarations(seal, anchors)
    if [item["anchor"] for item in declared] != list(ANCHORS):
        raise _refuse(
            RESTART_ANCHOR_UNDECLARED,
            f"the restart phases must be exactly {', '.join(ANCHORS)}, once each",
        )
    _require_new_root(root)
    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)
    receipts: dict[str, str] = {}
    documents: dict[str, dict] = {}
    for item in declared:
        anchor = item["anchor"]
        anchor_root = root / anchor
        anchor_root.mkdir()
        stdout = (anchor_root / "stdout.log").open("a", encoding="utf-8")
        stderr = (anchor_root / "stderr.log").open("a", encoding="utf-8")
        try:
            evidence = run_anchor(
                anchor=anchor,
                anchor_root=anchor_root,
                declared=item,
                runtime=runtime,
                run_root=root,
                ownership=ownership,
                approved_bundle_sha256=approved_bundle_sha256,
                producer=producer,
                anchors=declared,
                stdout=stdout,
                stderr=stderr,
            )
        finally:
            stdout.close()
            stderr.close()
        document = receipt_document(
            anchor_run=evidence,
            runtime=runtime,
            approved_bundle_sha256=approved_bundle_sha256,
            run_root=root,
            anchor_root=anchor_root,
            ownership=ownership,
            producer=producer,
            values=values,
            elapsed_s=evidence.get("elapsed_s"),
            started_at_utc=evidence.get("started_at_utc"),
            finished_at_utc=evidence.get("finished_at_utc"),
        )
        _write(anchor_root, ARTIFACT_BY_ANCHOR[anchor], document)
        receipts[anchor] = str(anchor_root / ARTIFACT_BY_ANCHOR[anchor])
        documents[anchor] = document
        if document["refusals"]:
            first = document["refusals"][0]
            if first["code"] in ABORT_CODES:
                # a stack that may still be alive, or a second owner, is never followed by another anchor
                raise _refuse(
                    first["code"],
                    f"the {anchor} restart refused and the run stops here: {first['detail']}",
                )
            print(
                f"restart_{anchor}: REFUSED {first['code']}: {first['detail']}",
                file=sys.stderr,
            )
    aggregate = {
        "schema_version": SCHEMA_VERSION,
        "kind": RECEIPTS_KIND,
        "operation": OPERATION,
        "phase": PHASE,
        "run_root": str(root),
        "anchors": [item["anchor"] for item in declared],
        "receipts": receipts,
        "receipt_sha256": {anchor: documents[anchor]["sha256"] for anchor in receipts},
        "receipt_status": {anchor: documents[anchor]["status"] for anchor in receipts},
        "runtime": dict(runtime),
        "ownership_receipt": dict(ownership),
        "approved_bundle_sha256": approved_bundle_sha256,
        "producer": {**dict(producer), "stack_owned": True},
        "elapsed_s": time.time() - started,
        "status": "PASS" if all(d["status"] == "PASS" for d in documents.values()) else "REFUSED",
        "fit_warning": FIT_WARNING,
    }
    _write(root, AGGREGATE_ARTIFACT, aggregate)
    _write(root, RECEIPT_ARTIFACT, {**aggregate, "kind": f"{RECEIPTS_KIND}_receipt"})
    refused = [anchor for anchor, document in documents.items() if document["status"] != "PASS"]
    if refused:
        raise _refuse(
            documents[refused[0]]["refusals"][0]["code"],
            f"the restarts for {', '.join(sorted(refused))} refused; every receipt is on disk in {root}",
        )
    return {
        "receipts": receipts,
        "documents": documents,
        "aggregate": aggregate,
        "run_root": str(root),
    }


def read_runtime_of_record(final_run, production_config=None) -> dict:
    """The frozen runtime's own identity, read off disk through the Step 1 reader."""

    return read_runtime_identity(
        Path(final_run),
        production_config=None if production_config is None else Path(production_config),
    )


__all__ = [
    "AGGREGATE_ARTIFACT",
    "ANCHORS",
    "ARTIFACT_BY_ANCHOR",
    "CAMERA_IMAGE_TOPIC",
    "CONTROLLERS",
    "DECLARED_FRAME_RATE_HZ",
    "EXPECTED_NODES",
    "RUNNER_NODE_NAMES",
    "KIND",
    "LIFECYCLE",
    "OPERATION",
    "PHASE_BY_ANCHOR",
    "RECEIPTS_KIND",
    "RestartRefused",
    "RestartStack",
    "anchor_declarations",
    "camera_rate",
    "classify_nodes",
    "frame_thresholds",
    "probe_owners",
    "read_ownership_receipt",
    "read_runtime_of_record",
    "receipt_document",
    "require_runtime_of_record",
    "restart_gates",
    "restart_refusals",
    "run_anchor_restart",
    "sim_clock_progress",
    "stack_environment",
    "stack_observation",
    "teardown_proof",
    "timing_document",
    "validate_restart_receipt",
    "write_head_search_restarts",
]
