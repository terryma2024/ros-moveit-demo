"""Kinds, abort codes, owned stack nodes and constants of the per-anchor restart."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time

from so101_demo.act.head_search.calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search.timing_measurement.contracts import (
    FRAME_PERIOD_S,
    FRAME_RATE_HZ,
)

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


#: over a multi-second window is compared against it with this absolute tolerance (the plugin publishes on
#: the simulator's own time base, so its long-run mean is the declared rate and its jitter is a frame)
RATE_TOLERANCE_HZ = 0.05


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
#: test is the production one rather than the two-node transport subset the stamp measurement used
CONTROLLERS = ("joint_state_broadcaster", "arm_controller", "gripper_controller", "neck_controller")


NECK_CONTROLLER = "neck_controller"


NECK_JOINT = "neck_yaw_joint"


#: seal's declared ``default`` anchor point. ``plastic_cup_b`` sits at ``(2, 2, 2)``, outside every frame.
CUP_BODY = "plastic_cup"


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
