"""The running-topic measurement: the head-search frame contract declaration and the source skew.

Two of the phase 6/7 measurement documents are properties of the **running ROS transport** rather than
of anything a single process can render: phase 7's ``max_skew_s`` is the p99.9 spread of the image,
CameraInfo and joint/TF stamps *the search actually pairs* plus one clock resolution, and the 10 Hz frame
contract every cap is expressed in is a declaration of the production camera pipeline.

What exists in this repository for that pipeline (established by reading it, not by assuming it):

* ``third_party/mujoco_ros2_control/mujoco_ros2_control_plugins/src/camera_plugin.cpp`` publishes the
  MJCF cameras the production plugin configuration declares. For ``head_camera`` it renders offscreen,
  stamps both the color image and its CameraInfo with the *same* ``rclcpp::Time`` built from
  ``mjData.time`` (the MuJoCo simulation clock), and publishes them on the configured topics;
* ``src/so101_demo_py/config/mujoco/act/mujoco_plugins.yaml`` declares that plugin for the production
  head camera: ``camera_publish_rate: 10.0``, ``image_topic: /head_camera/color``,
  ``info_topic: /head_camera/camera_info``, ``frame_name: head_camera_frame``, ``policy: streaming``;
* ``src/so101_demo_py/src/adapters/act/ros_search.py`` is the production consumer: it subscribes to
  exactly those two topics plus ``/joint_states`` and looks up ``base`` -> ``head_camera_frame`` at the
  image stamp, pairing CameraInfo and feedback through ``so101_demo.act.synchronizer.causal_sample``;
* ``src/so101_demo_py/assets/mujoco/act/so101.urdf`` declares ``head_camera_frame`` as a fixed child of
  ``head_mount``, so ``robot_state_publisher`` publishes the transform from the same joint states.

This module measures the contract and the skew **through that transport** and nothing else: the stack it
starts is the MuJoCo simulation, ``robot_state_publisher`` and the joint-state broadcaster. No detector
is loaded, no weights are read, no CUDA device is touched and no motion is commanded, which is what the
documents it writes say (``detector_loaded``, ``cuda_used``, ``motion_commanded`` all false).

Two deliberate decisions the code cannot make by itself, and which the documents record:

1. **The image/CameraInfo pair carries one stamp by construction.** The camera plugin stamps both
   messages from the same snapshot, so their difference is structurally zero; the *observable* skew is
   the difference between that pair and the joint state the production pairing rule selects, and that is
   what ``stamps`` holds. The TF lookup taken at the image stamp is recorded beside it
   (``sources.tf``) as corroboration rather than as a fourth stamp, because a transform is not a
   second stamp source: it is published by ``robot_state_publisher`` *from* those joint states.
2. **The clock resolution is measured, never declared.** Over the capture the node records its own
   clock readings (``RCL_ROS_TIME`` fed by the simulated ``/clock``); the resolution is the smallest
   positive step between two distinct readings. A capture that never saw the clock move refuses with
   ``CAL_SKEW_CLOCK_UNMEASURED`` rather than declaring a plausible number, because phase 7 adds exactly
   this value to the measured skew.

The decision layer is pure: the capture is an injected port, so the tests exercise the documents, the
pairing rules, every refusal and the phase-7 consumption without a ROS graph, a simulator or a GPU.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import signal
import subprocess
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

import yaml
from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search_timing_params import (
    FRAME_CONTRACT_HZ,
    FRAME_CONTRACT_ITEM,
    nearest_rank_percentile,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256

SCHEMA_VERSION = 1

FRAME_CONTRACT_KIND = "head_search_calibration_frame_contract"
SKEW_KIND = "head_search_calibration_skew_measurements"
RECEIPT_KIND = "head_search_calibration_transport_measurement_receipt"

FRAME_CONTRACT_PHASE = "frame_contract"
SKEW_PHASE = "skew_measurements"

FRAME_CONTRACT_ARTIFACT = "frame-contract.json"
SKEW_ARTIFACT = "skew-measurements.json"
RECEIPT_ARTIFACT = "measurement-receipt.json"

#: this measurement's own refusals
CAL_FRAME_CONTRACT_EVIDENCE_MISSING = "CAL_FRAME_CONTRACT_EVIDENCE_MISSING"
CAL_FRAME_CONTRACT_CONTRADICTORY = "CAL_FRAME_CONTRACT_CONTRADICTORY"
CAL_SKEW_TRANSPORT_UNREACHABLE = "CAL_SKEW_TRANSPORT_UNREACHABLE"
CAL_SKEW_NO_SAMPLES = "CAL_SKEW_NO_SAMPLES"
CAL_SKEW_SOURCE_MISSING = "CAL_SKEW_SOURCE_MISSING"
CAL_SKEW_EVIDENCE_CONTRADICTORY = "CAL_SKEW_EVIDENCE_CONTRADICTORY"
CAL_SKEW_CLOCK_UNMEASURED = "CAL_SKEW_CLOCK_UNMEASURED"
REFUSAL_CODES = (
    CAL_FRAME_CONTRACT_EVIDENCE_MISSING,
    CAL_FRAME_CONTRACT_CONTRADICTORY,
    CAL_SKEW_TRANSPORT_UNREACHABLE,
    CAL_SKEW_NO_SAMPLES,
    CAL_SKEW_SOURCE_MISSING,
    CAL_SKEW_EVIDENCE_CONTRADICTORY,
    CAL_SKEW_CLOCK_UNMEASURED,
)

#: the production head camera stream the plugin configuration has to declare for the contract to be the
#: one the search consumes; a configuration that declares another stream is refused, never reinterpreted
PRODUCTION_HEAD_CAMERA = {
    "policy": "streaming",
    "frame_name": "head_camera_frame",
    "image_topic": "/head_camera/color",
    "info_topic": "/head_camera/camera_info",
}

#: the three stamped sources the design's search set names (head image, CameraInfo, joint/TF). TF is a
#: transform derived from the joint states, not a fourth stamp, so it is recorded beside these.
REQUIRED_SOURCES = ("head_image", "camera_info", "joint_state")

#: the production consumer whose pairing rule the capture reproduces (`RosSearchAdapter`)
PRODUCTION_CONSUMER = "so101_demo.adapters.act.ros_search.RosSearchAdapter"

#: the topics the capture subscribes to, taken from the production plugin and controller declarations
JOINT_STATE_TOPIC = "/joint_states"
TF_PARENT_FRAME = "base"

#: the clock every stamp above is in, and how the resolution is measured from the capture itself
TIME_BASE = "ros_sim_time"
CLOCK_SOURCE = "RCL_ROS_TIME fed by the simulated /clock (MuJoCo mjData.time)"
CLOCK_RESOLUTION_BASIS = {
    "measured_from": "the smallest positive difference between two distinct clock readings the capture "
    "node observed while the stack ran",
    "clock_source": CLOCK_SOURCE,
    "convention": "a capture whose clock never moved refuses; the resolution is never declared",
}

DIGEST_CONVENTION = "sha256 = canonical_sha256(body without the sha256 field)"

#: the stack the capture starts: MuJoCo with the production camera plugin, the robot state publisher and
#: the joint-state broadcaster. No detector, no MoveIt, no teleoperation and no broker take part.
STACK_NODES = ("mujoco_ros2_control", "robot_state_publisher", "joint_state_broadcaster")


def _finite(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _refuse(code: str, detail: str) -> CalibrationInputsRefused:
    return CalibrationInputsRefused(code, detail)


def _sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _mapping(value, name: str) -> Mapping:
    if not isinstance(value, Mapping):
        raise _refuse(CAL_FRAME_CONTRACT_EVIDENCE_MISSING, f"{name} is not a mapping")
    return value


# --- the frame contract declaration ---------------------------------------------------------------


def read_production_head_camera(plugin_config_path) -> dict:
    """The production camera plugin's own declaration of the head camera stream and its rate.

    The configuration is the artefact that declares which topic the head camera is published on, under
    which frame id and at which rate; the run's 10 Hz contract is only the design's statement of it. A
    configuration that does not declare the production stream at 10 Hz is refused
    (`CAL_FRAME_CONTRACT_CONTRADICTORY`) instead of being read as if it did.
    """

    path = Path(plugin_config_path)
    if not path.is_file():
        raise _refuse(
            CAL_FRAME_CONTRACT_EVIDENCE_MISSING,
            f"no production camera plugin configuration at {path}",
        )
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise _refuse(
            CAL_FRAME_CONTRACT_EVIDENCE_MISSING,
            f"{path} is not readable YAML: {error}",
        ) from error
    root = _mapping(document, f"{path}")
    parameters = root.get("/**") or root.get("ros__parameters") or root
    parameters = _mapping(parameters, f"{path}:/**")
    parameters = _mapping(
        parameters.get("ros__parameters", parameters), f"{path}:/**/ros__parameters"
    )
    plugins = _mapping(parameters.get("mujoco_plugins"), f"{path}:mujoco_plugins")
    camera_plugin = _mapping(
        plugins.get("mujoco_camera_plugin"), f"{path}:mujoco_plugins.mujoco_camera_plugin"
    )
    rate = camera_plugin.get("camera_publish_rate")
    if not _finite(rate) or float(rate) != FRAME_CONTRACT_HZ:
        raise _refuse(
            CAL_FRAME_CONTRACT_CONTRADICTORY,
            f"{path} declares camera_publish_rate {rate!r}, but phase 7's contract is the "
            f"{FRAME_CONTRACT_HZ} Hz frame rate every one of its caps is expressed in",
        )
    head_camera = _mapping(camera_plugin.get("head_camera"), f"{path}:head_camera")
    for key, expected in PRODUCTION_HEAD_CAMERA.items():
        declared = head_camera.get(key)
        if declared != expected:
            raise _refuse(
                CAL_FRAME_CONTRACT_CONTRADICTORY,
                f"{path} declares head_camera.{key} = {declared!r}, but the production head camera "
                f"stream the search consumes is {expected!r}: a frame contract for another stream "
                f"would not be the contract the running pipeline uses",
            )
    return {
        "path": str(path),
        "sha256": _sha256_file(path),
        "camera_publish_rate": float(rate),
        "declared_plugin": camera_plugin.get("type"),
        "head_camera": {key: head_camera.get(key) for key in PRODUCTION_HEAD_CAMERA},
    }


def frame_contract_declaration(
    *,
    plugin_config_path,
    document_path,
    command=None,
    measured_rate_hz=None,
    measured_rate_detail=None,
    declared_sources=None,
    startup_readback=None,
) -> dict:
    """The 10 Hz frame contract as a declaration, citing the production artefact that declares it.

    The value is the production camera plugin's declared rate, so it is a declaration and says so
    (``measured_here`` false, ``value_source`` ``declaration``). A running-topic measurement of the same
    rate is recorded **beside** the declaration when the caller has one - it never replaces the value,
    and the document names which of the two the value came from.
    """

    camera = read_production_head_camera(plugin_config_path)
    path = Path(document_path)
    if measured_rate_hz is not None and not _finite(measured_rate_hz):
        raise ValueError("a measured frame rate must be a finite number of hertz")
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": FRAME_CONTRACT_KIND,
        "phase": FRAME_CONTRACT_PHASE,
        "path": str(path),
        "command": command,
        "item": FRAME_CONTRACT_ITEM,
        "frame_rate_hz": camera["camera_publish_rate"],
        "frame_period_s": 1.0 / camera["camera_publish_rate"],
        "value_source": "declaration",
        "measured_here": False,
        "declared_by": {
            "source": camera["path"],
            "sha256": camera["sha256"],
            "json_pointer": (
                "/**/ros__parameters/mujoco_plugins/mujoco_camera_plugin/camera_publish_rate"
            ),
            "declared_value": camera["camera_publish_rate"],
            "unit": "Hz",
            "plugin_type": camera["declared_plugin"],
            "head_camera": dict(camera["head_camera"]),
            "design": (
                "the head search design fixes the production camera contract (10 Hz production frame "
                "rate, ROS frame id, sim time and receive monotonic time) and records "
                "frame_contract_10_hz among phase 8's additionally-recorded items; phase 7's module "
                "fixes the rate and refuses any other, so this declaration cannot widen a cap"
            ),
        },
        "measured_frame_rate_hz": None if measured_rate_hz is None else float(measured_rate_hz),
        "measured_frame_rate_detail": (
            None if measured_rate_detail is None else dict(measured_rate_detail)
        ),
        "declared_sources": dict(declared_sources or {}),
        "production_owner": "so101_demo.act.head_search_timing_params.FRAME_CONTRACT_HZ",
        "production_consumer": PRODUCTION_CONSUMER,
        "startup_readback": (
            {
                "verified": False,
                "detail": (
                    "the startup readback that proves the running pipeline uses the 10 Hz contract "
                    "belongs to the run (phase 8); this declaration is the rate the production camera "
                    "plugin is configured to publish at"
                ),
            }
            if startup_readback is None
            else dict(startup_readback)
        ),
        "ros_nodes_started": False,
        "motion_commanded": False,
        "digest_convention": DIGEST_CONVENTION,
    }
    document["sha256"] = canonical_sha256(
        {key: value for key, value in document.items() if key != "sha256"}
    )
    return document


# --- the skew measurement -------------------------------------------------------------------------


def skew_sample(*, index, image, camera_info, joint_state, tf=None, clock_reading_s=None) -> dict:
    """One paired frame: the three required source stamps and the receipts they arrived with.

    The stamps are exactly those of the three required sources; a caller that hands in something else is
    refused by :func:`build_skew_document`, which recomputes the spread from them.
    """

    sources = {
        "head_image": {
            "stamp_s": _stamp_of(image, "the head image"),
            "received_monotonic_s": _receipt_of(image, "the head image"),
            "topic": image.get("topic", PRODUCTION_HEAD_CAMERA["image_topic"]),
        },
        "camera_info": {
            "stamp_s": _stamp_of(camera_info, "the CameraInfo"),
            "received_monotonic_s": _receipt_of(camera_info, "the CameraInfo"),
            "topic": camera_info.get("topic", PRODUCTION_HEAD_CAMERA["info_topic"]),
        },
        "joint_state": {
            "stamp_s": _stamp_of(joint_state, "the joint state"),
            "received_monotonic_s": _receipt_of(joint_state, "the joint state"),
            "topic": joint_state.get("topic", JOINT_STATE_TOPIC),
        },
    }
    if tf is not None:
        sources["tf"] = dict(tf)
    stamps = [sources[name]["stamp_s"] for name in REQUIRED_SOURCES]
    return {
        "index": int(index),
        "frame_id": image.get("frame_id", PRODUCTION_HEAD_CAMERA["frame_name"]),
        "stamps": stamps,
        "skew_s": max(stamps) - min(stamps),
        "sources": sources,
        "clock_reading_s": None if clock_reading_s is None else float(clock_reading_s),
        "pairing": {
            "rule": "causal_sample(latest source stamp at or before the image stamp)",
            "consumer": PRODUCTION_CONSUMER,
        },
    }


def _stamp_of(source, name: str) -> float:
    if not isinstance(source, Mapping) or not _finite(source.get("stamp_s")):
        raise _refuse(CAL_SKEW_SOURCE_MISSING, f"{name} records no finite stamp_s")
    return float(source["stamp_s"])


def _receipt_of(source, name: str) -> float:
    if not isinstance(source, Mapping) or not _finite(source.get("received_monotonic_s")):
        raise _refuse(CAL_SKEW_SOURCE_MISSING, f"{name} records no finite received_monotonic_s")
    return float(source["received_monotonic_s"])


def measure_clock_resolution(readings) -> float:
    """The smallest positive step between two distinct readings of the clock the stamps are in.

    A capture whose clock never moved cannot bound the resolution phase 7 adds to the measured skew, so
    it refuses (`CAL_SKEW_CLOCK_UNMEASURED`) instead of declaring an assumed one.
    """

    if isinstance(readings, (str, bytes)) or not isinstance(readings, Sequence):
        raise _refuse(CAL_SKEW_CLOCK_UNMEASURED, "the capture recorded no clock readings")
    values = sorted({float(value) for value in readings if _finite(value)})
    if len(values) < 2:
        raise _refuse(
            CAL_SKEW_CLOCK_UNMEASURED,
            f"the capture observed {len(values)} distinct clock reading(s); the resolution phase 7 "
            f"adds to the measured skew cannot be measured from a clock that never moved",
        )
    steps = [b - a for a, b in zip(values, values[1:]) if b > a]
    return min(steps)


def build_skew_document(
    *,
    document_path,
    samples,
    clock_resolution_s,
    clock_resolution_basis,
    frame_contract=None,
    command=None,
    capture=None,
    declared_sources=None,
    runtime_identity=None,
) -> dict:
    """The skew measurement document phase 7 reads: the paired stamps, the clock resolution and its basis.

    Every sample has to carry the three required sources and a spread that is exactly those stamps', an
    empty capture is refused, and a capture without a measured clock resolution is refused: a document
    that cannot feed `compute_max_skew_s` is never written as if it could.
    """

    path = Path(document_path)
    if isinstance(samples, (str, bytes)) or not isinstance(samples, Sequence) or not samples:
        raise _refuse(
            CAL_SKEW_NO_SAMPLES,
            "the capture paired no frame: a skew distribution needs at least one measured sample",
        )
    records = []
    for position, sample in enumerate(samples):
        if not isinstance(sample, Mapping):
            raise ValueError(f"skew sample {position} is not a record")
        sources = sample.get("sources")
        if not isinstance(sources, Mapping):
            raise _refuse(CAL_SKEW_SOURCE_MISSING, f"skew sample {position} records no sources")
        missing = [
            name
            for name in REQUIRED_SOURCES
            if not isinstance(sources.get(name), Mapping)
            or not _finite(sources[name].get("stamp_s"))
        ]
        if missing:
            raise _refuse(
                CAL_SKEW_SOURCE_MISSING,
                f"skew sample {position} records no finite stamp for {', '.join(missing)}: the search "
                f"set is the head image, its CameraInfo and the joint/TF state, and a tuple missing a "
                f"source is invalid rather than skewed by zero",
            )
        expected = [float(sources[name]["stamp_s"]) for name in REQUIRED_SOURCES]
        stamps = sample.get("stamps")
        if (
            isinstance(stamps, (str, bytes))
            or not isinstance(stamps, Sequence)
            or [float(stamp) for stamp in stamps if _finite(stamp)] != expected
            or not all(_finite(stamp) for stamp in stamps)
        ):
            raise _refuse(
                CAL_SKEW_EVIDENCE_CONTRADICTORY,
                f"skew sample {position} records stamps {stamps!r}, which are not the stamps of its "
                f"own {', '.join(REQUIRED_SOURCES)} sources {expected!r}",
            )
        spread = max(expected) - min(expected)
        if not _finite(sample.get("skew_s")) or not math.isclose(
            float(sample["skew_s"]), spread, rel_tol=0.0, abs_tol=1e-12
        ):
            raise _refuse(
                CAL_SKEW_EVIDENCE_CONTRADICTORY,
                f"skew sample {position} records a skew of {sample.get('skew_s')!r} but its own stamps "
                f"span {spread!r} s",
            )
        records.append(dict(sample))
    if not _finite(clock_resolution_s) or float(clock_resolution_s) <= 0.0:
        raise _refuse(
            CAL_SKEW_CLOCK_UNMEASURED,
            f"the capture measured no positive clock resolution ({clock_resolution_s!r}); phase 7 adds "
            f"one clock resolution to the measured skew and a missing one is refused, never defaulted",
        )
    if isinstance(clock_resolution_basis, str) or not isinstance(clock_resolution_basis, Mapping):
        raise ValueError(
            "the clock resolution basis must be a mapping that says how it was measured"
        )
    spreads = [float(sample["skew_s"]) for sample in records]
    cap_s = 0.5 / FRAME_CONTRACT_HZ
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": SKEW_KIND,
        "phase": SKEW_PHASE,
        "path": str(path),
        "command": command,
        "time_base": TIME_BASE,
        "clock_source": CLOCK_SOURCE,
        "samples": records,
        "clock_resolution_s": float(clock_resolution_s),
        "clock_resolution_basis": dict(clock_resolution_basis),
        "required_sources": list(REQUIRED_SOURCES),
        "declared_sources": dict(declared_sources or {}),
        "frame_contract": (
            None
            if frame_contract is None
            else {
                "path": frame_contract.get("path"),
                "sha256": frame_contract.get("sha256"),
                "frame_rate_hz": frame_contract.get("frame_rate_hz"),
            }
        ),
        "capture": dict(capture or {}),
        "observed": {
            "sample_count": len(records),
            "min_skew_s": min(spreads),
            "max_skew_s": max(spreads),
            "p99_9_skew_s": nearest_rank_percentile(spreads, 0.999),
            "cap_s": cap_s,
            "cap_frame_periods": 0.5,
            "inside_cap": max(spreads) + float(clock_resolution_s) <= cap_s,
        },
        "measured_here": True,
        "detector_loaded": False,
        "cuda_used": False,
        "motion_commanded": False,
        "runtime_identity": dict(runtime_identity or {}),
        "digest_convention": DIGEST_CONVENTION,
    }
    document["sha256"] = canonical_sha256(
        {key: value for key, value in document.items() if key != "sha256"}
    )
    return document


# --- the running stack and the capture ------------------------------------------------------------


def render_mujoco_robot_description(
    urdf_path,
    scene_path,
    *,
    initial_keyframe: str = "",
    headless: bool = True,
    sensor_rendering: bool = True,
    sim_speed_factor: float = -1.0,
) -> str:
    """The ACT URDF with the launch tokens resolved for the sealed scene and this capture.

    The five tokens are the ones ``so101_demo.runtime.launch_composition`` resolves. The initial keyframe
    is empty here on purpose: the sealed head-search scene declares no keyframe, and the simulator
    refuses to start when asked for one the model does not have.
    """

    description = Path(urdf_path).read_text(encoding="utf-8")
    for token, value in (
        ("@SO101_MUJOCO_SCENE@", str(scene_path)),
        ("@SO101_MUJOCO_INITIAL_KEYFRAME@", initial_keyframe),
        ("@SO101_MUJOCO_HEADLESS@", str(bool(headless)).lower()),
        ("@SO101_MUJOCO_DISABLE_RENDERING@", str(not sensor_rendering).lower()),
        ("@SO101_MUJOCO_SIM_SPEED_FACTOR@", str(sim_speed_factor)),
    ):
        description = description.replace(token, value)
    if "@SO101_" in description:
        raise ValueError("unresolved SO-101 URDF launch token")
    return description


def _package_executable(package: str, executable: str) -> str:
    """The installed executable of one package, from the prefix the active environment resolves."""

    from ament_index_python.packages import get_package_prefix

    prefix = Path(get_package_prefix(package))
    for candidate in (prefix / "lib" / package / executable, prefix / "lib" / executable):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    raise _refuse(
        CAL_SKEW_TRANSPORT_UNREACHABLE,
        f"{package} does not install the {executable} executable under {prefix}",
    )


class MujocoRosTransport:
    """The production head-camera transport: MuJoCo, the camera plugin, TF and the joint states.

    The stack is the one the production search consumes - the same URDF tokens, the same plugin and
    controller configurations and the same node set - started headless with EGL rendering. It carries no
    detector: this measurement needs stamps, not detections.
    """

    def __init__(
        self,
        *,
        urdf_path,
        scene_path,
        plugin_config_path,
        controller_config_path,
        workspace,
        session_id="hs308-skew",
        startup_timeout_s=90.0,
        logger=None,
    ) -> None:
        self.urdf_path = Path(urdf_path)
        self.scene_path = Path(scene_path)
        self.plugin_config_path = Path(plugin_config_path)
        self.controller_config_path = Path(controller_config_path)
        self.workspace = Path(workspace)
        self.session_id = session_id
        self.startup_timeout_s = float(startup_timeout_s)
        self.logger = logger
        self.processes: list[subprocess.Popen] = []
        self.handles: list = []
        self.log_path = None

    def _log(self, message: str) -> None:
        if self.logger is not None:
            self.logger(message)

    def _spawn(self, argv, name: str) -> subprocess.Popen:
        handle = open(self.log_path, "ab")  # noqa: SIM115 - one handle per child, closed on stop
        self.handles.append(handle)
        self._log(f"starting {name}: {' '.join(argv)}")
        return subprocess.Popen(  # noqa: S603 - the argv is built from installed package prefixes
            argv,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    def start(self) -> None:
        description = render_mujoco_robot_description(self.urdf_path, self.scene_path)
        parameters = self.workspace / "ros2-control-node.params.yaml"
        parameters.write_text(
            yaml.safe_dump(
                {
                    "/**": {
                        "ros__parameters": {
                            "use_sim_time": True,
                            "robot_description": description,
                            "simulation_session_id": self.session_id,
                        }
                    }
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        common = [
            "--ros-args",
            "--params-file",
            str(parameters),
            "--params-file",
            str(self.controller_config_path),
            "--params-file",
            str(self.plugin_config_path),
        ]
        self.processes.append(
            self._spawn(
                [_package_executable("mujoco_ros2_control", "ros2_control_node"), *common],
                "ros2_control_node",
            )
        )
        self.processes.append(
            self._spawn(
                [_package_executable("robot_state_publisher", "robot_state_publisher"), *common],
                "robot_state_publisher",
            )
        )
        self.processes.append(
            self._spawn(
                [
                    _package_executable("controller_manager", "spawner"),
                    "joint_state_broadcaster",
                    "--controller-manager-timeout",
                    str(self.startup_timeout_s),
                    "--param-file",
                    str(self.controller_config_path),
                ],
                "spawner joint_state_broadcaster",
            )
        )

    def stop(self) -> None:
        for process in self.processes:
            if process.poll() is not None:
                continue
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGINT)
            except (ProcessLookupError, PermissionError):
                continue
        deadline = time.monotonic() + 20.0
        for process in self.processes:
            remaining = max(0.0, deadline - time.monotonic())
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                process.wait(timeout=10.0)
        self.processes.clear()
        for handle in self.handles:
            handle.close()
        self.handles.clear()

    def __enter__(self):
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.log_path = self.workspace / "transport-stack.log"
        self.start()
        return self

    def __exit__(self, *exception) -> None:
        self.stop()


class RosTopicSkewCapture:
    """The capture node: it pairs the frames the production search would pair, and times nothing else."""

    def __init__(
        self,
        *,
        frames: int,
        timeout_s: float,
        pair_window_s: float,
        startup_timeout_s: float = 60.0,
        node_name: str = "head_search_skew_capture",
    ) -> None:
        if type(frames) is not int or frames < 1:
            raise ValueError("a capture needs a positive whole number of frames")
        self.frames = frames
        self.timeout_s = float(timeout_s)
        self.pair_window_s = float(pair_window_s)
        self.startup_timeout_s = float(startup_timeout_s)
        self.node_name = node_name

    def capture(self) -> dict:
        """Subscribe, pair the frames exactly as the production search does, and time nothing else.

        The pairing follows `RosSearchAdapter`: the CameraInfo of a frame has to carry **that frame's own
        stamp** (the camera plugin stamps both messages from one snapshot; the production consumer raises
        `INPUT_CAMERA_INFO_INVALID` on anything else), and the joint state is the latest one at or before
        the image stamp inside the pairing window. A frame whose pair is incomplete is never paired with a
        neighbouring source's stamp: the capture waits for the pair and drops the frame if the source has
        moved past it, recording the drop.
        """

        import rclpy
        from rclpy.node import Node
        from rclpy.parameter import Parameter
        from rclpy.qos import QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
        from rclpy.time import Time
        from sensor_msgs.msg import CameraInfo, Image, JointState
        from so101_demo.act.synchronizer import causal_sample
        from tf2_ros import Buffer, TransformListener

        rgb_qos = QoSProfile(depth=32, reliability=ReliabilityPolicy.RELIABLE)
        rclpy.init(args=None)
        node = Node(self.node_name, parameter_overrides=[Parameter("use_sim_time", value=True)])
        buffers: dict[str, list] = {"head_image": [], "camera_info": [], "joint_state": []}
        clock_readings: list[float] = []
        tf_buffer = Buffer()
        TransformListener(tf_buffer, node)

        def now_s() -> float:
            return node.get_clock().now().nanoseconds * 1e-9

        def keep(kind: str, stamp_s: float, message) -> None:
            buffers[kind].append((stamp_s, (message, time.monotonic())))
            clock_readings.append(now_s())

        def on_image(message) -> None:
            keep(
                "head_image",
                message.header.stamp.sec + message.header.stamp.nanosec * 1e-9,
                message,
            )

        def on_info(message) -> None:
            keep(
                "camera_info",
                message.header.stamp.sec + message.header.stamp.nanosec * 1e-9,
                message,
            )

        def on_joints(message) -> None:
            if (
                len(set(message.name)) != len(message.name)
                or len(message.name) != len(message.position)
                or len(message.name) != len(message.velocity)
            ):
                return
            keep(
                "joint_state",
                message.header.stamp.sec + message.header.stamp.nanosec * 1e-9,
                message,
            )

        node.create_subscription(Image, PRODUCTION_HEAD_CAMERA["image_topic"], on_image, rgb_qos)
        node.create_subscription(CameraInfo, PRODUCTION_HEAD_CAMERA["info_topic"], on_info, rgb_qos)
        node.create_subscription(JointState, JOINT_STATE_TOPIC, on_joints, qos_profile_sensor_data)

        samples: list[dict] = []
        dropped_camera_info = 0
        dropped_joint_state = 0
        cursor = 0
        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline and len(samples) < self.frames:
            rclpy.spin_once(node, timeout_sec=0.05)
            images = buffers["head_image"]
            infos = {round(stamp, 9): value for stamp, value in buffers["camera_info"]}
            newest_info = buffers["camera_info"][-1][0] if buffers["camera_info"] else None
            newest_joint = buffers["joint_state"][-1][0] if buffers["joint_state"] else None
            while cursor < len(images) and len(samples) < self.frames:
                stamp_s, (message, received_at) = images[cursor]
                pair = infos.get(round(stamp_s, 9))
                if pair is None:
                    if newest_info is not None and stamp_s < newest_info:
                        dropped_camera_info += 1
                        cursor += 1
                        continue
                    break
                try:
                    joints, joint_received = causal_sample(
                        buffers["joint_state"], stamp_s, self.pair_window_s
                    )
                except ValueError:
                    if newest_joint is not None and stamp_s < newest_joint:
                        dropped_joint_state += 1
                        cursor += 1
                        continue
                    break
                info, info_received = pair
                tf_record = {"resolved": False, "stamp_s": None, "error": None}
                try:
                    transform = tf_buffer.lookup_transform(
                        TF_PARENT_FRAME,
                        message.header.frame_id or PRODUCTION_HEAD_CAMERA["frame_name"],
                        Time.from_msg(message.header.stamp),
                    )
                    tf_record = {
                        "resolved": True,
                        "parent_frame": TF_PARENT_FRAME,
                        "child_frame": transform.child_frame_id,
                        "stamp_s": (
                            transform.header.stamp.sec + transform.header.stamp.nanosec * 1e-9
                        ),
                        "error": None,
                    }
                except Exception as error:  # noqa: BLE001 - a failed lookup is recorded, not raised
                    tf_record = {
                        "resolved": False,
                        "parent_frame": TF_PARENT_FRAME,
                        "child_frame": message.header.frame_id,
                        "stamp_s": None,
                        "error": str(error),
                    }
                samples.append(
                    skew_sample(
                        index=len(samples),
                        image={
                            "stamp_s": stamp_s,
                            "received_monotonic_s": received_at,
                            "frame_id": message.header.frame_id,
                        },
                        camera_info={
                            "stamp_s": info.header.stamp.sec + info.header.stamp.nanosec * 1e-9,
                            "received_monotonic_s": info_received,
                        },
                        joint_state={
                            "stamp_s": joints.header.stamp.sec + joints.header.stamp.nanosec * 1e-9,
                            "received_monotonic_s": joint_received,
                        },
                        tf=tf_record,
                        clock_reading_s=now_s(),
                    )
                )
                cursor += 1
        node.destroy_node()
        rclpy.shutdown()
        stamps = [sample["sources"]["head_image"]["stamp_s"] for sample in samples]
        window = (max(stamps) - min(stamps)) if len(stamps) > 1 else 0.0
        return {
            "samples": samples,
            "clock_readings_s": clock_readings,
            "capture": {
                "frames_requested": self.frames,
                "frames_paired": len(samples),
                "frames_received": len(buffers["head_image"]),
                "frames_dropped_without_camera_info": dropped_camera_info,
                "frames_dropped_without_joint_state": dropped_joint_state,
                "window_sim_s": window,
                "achieved_rate_hz": (len(samples) - 1) / window if window > 0 else None,
                "pair_window_s": self.pair_window_s,
                "pairing_rule": (
                    "the frame's own CameraInfo stamp (the production INPUT_CAMERA_INFO_INVALID rule) "
                    "and the latest joint state at or before the image stamp inside the pairing window"
                ),
                "timeout_s": self.timeout_s,
            },
        }


def write_transport_measurements(
    *,
    output_dir,
    command=None,
    mode: str,
    plugin_config_path=None,
    urdf_path=None,
    scene_path=None,
    controller_config_path=None,
    frames: int = 300,
    timeout_s: float = 120.0,
    pair_window_s: float = 0.15,
    transport=None,
    frame_contract_path=None,
    measured_rate_from=None,
    runtime_identity=None,
) -> dict:
    """Write one of the two documents into a brand-new directory, with its receipt.

    ``mode`` is ``frame_contract`` (a declaration: only the production plugin configuration is read) or
    ``skew`` (a measurement: the caller's transport is started, captured and stopped, and the stack is
    never left running). The directory is claimed before anything runs, so a measurement is never
    resumed or overwritten.
    """

    if mode not in {"frame_contract", "skew"}:
        raise ValueError("a transport measurement is frame_contract or skew")
    output = Path(output_dir)
    output.mkdir(parents=True)
    started = time.time()
    if mode == "frame_contract":
        measured_rate = None
        measured_detail = None
        if measured_rate_from is not None:
            skew_document = json.loads(Path(measured_rate_from).read_text(encoding="utf-8"))
            measured_rate = skew_document.get("capture", {}).get("achieved_rate_hz")
            measured_detail = {
                "source": str(measured_rate_from),
                "sha256": _sha256_file(measured_rate_from),
                "capture": dict(skew_document.get("capture", {})),
            }
        document = frame_contract_declaration(
            plugin_config_path=plugin_config_path,
            document_path=output / FRAME_CONTRACT_ARTIFACT,
            command=command,
            measured_rate_hz=measured_rate,
            measured_rate_detail=measured_detail,
            declared_sources={
                "camera_plugin_config": str(plugin_config_path),
                "camera_plugin_config_sha256": _sha256_file(plugin_config_path),
            },
        )
        artifact = FRAME_CONTRACT_ARTIFACT
        status = "DECLARED"
    else:
        if transport is None:
            raise ValueError("a skew measurement needs a transport")
        contract = _read_frame_contract_declaration(frame_contract_path)
        with transport as running:
            capture = running.capture() if hasattr(running, "capture") else running()
        samples = capture.get("samples")
        document = build_skew_document(
            document_path=output / SKEW_ARTIFACT,
            samples=samples,
            clock_resolution_s=measure_clock_resolution(capture.get("clock_readings_s", [])),
            clock_resolution_basis=dict(CLOCK_RESOLUTION_BASIS),
            frame_contract=contract,
            command=command,
            capture=capture.get("capture"),
            declared_sources={
                "camera_plugin_config": str(plugin_config_path),
                "camera_plugin_config_sha256": _sha256_file(plugin_config_path),
                "controller_config": str(controller_config_path),
                "controller_config_sha256": _sha256_file(controller_config_path),
                "scene": str(scene_path),
                "scene_sha256": _sha256_file(scene_path),
            },
            runtime_identity=runtime_identity,
        )
        artifact = SKEW_ARTIFACT
        status = "MEASURED"
    path = output / artifact
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": RECEIPT_KIND,
        "phase": document["phase"],
        "status": status,
        "command": command,
        "artifact": artifact,
        "measurement_path": str(path),
        "measurement_sha256": document["sha256"],
        "frame_rate_hz": document.get("frame_rate_hz"),
        "value_source": document.get("value_source"),
        "measured_here": document.get("measured_here"),
        "sample_count": len(document.get("samples", [])) or None,
        "clock_resolution_s": document.get("clock_resolution_s"),
        "observed": document.get("observed"),
        "stack_nodes": list(STACK_NODES) if mode == "skew" else [],
        "detector_loaded": False,
        "cuda_used": False,
        "motion_commanded": False,
        "elapsed_s": time.time() - started,
    }
    (output / RECEIPT_ARTIFACT).write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {"measurement": document, "receipt": receipt}


def leave_nothing_running() -> list[str]:
    """Any of this measurement's own stack processes still alive, so a caller can report or stop them."""

    import subprocess as _subprocess

    pattern = (
        "lib/mujoco_ros2_control/ros2_control_node"
        "|lib/robot_state_publisher/robot_state_publisher"
        "|controller_manager/spawner"
    )
    listing = _subprocess.run(  # noqa: S603 - a fixed read-only process listing
        ["pgrep", "-a", "-f", pattern],
        capture_output=True,
        text=True,
        check=False,
    )
    mine = str(os.getpid())
    return [
        line
        for line in listing.stdout.splitlines()
        if line.strip()
        and line.split(maxsplit=1)[0] != mine
        and "apport" not in line
        and "pgrep" not in line
        and "grep" not in line
    ]


def _read_frame_contract_declaration(frame_contract_path) -> dict:
    """The declaration the capture is paced against: the same 10 Hz rate phase 7 fixes, cited by digest."""

    if frame_contract_path is None:
        raise _refuse(
            CAL_FRAME_CONTRACT_EVIDENCE_MISSING,
            "a skew measurement is paced against the declared frame contract and needs the document "
            "produced by measure-frame-contract",
        )
    path = Path(frame_contract_path)
    if not path.is_file():
        raise _refuse(CAL_FRAME_CONTRACT_EVIDENCE_MISSING, f"no frame contract at {path}")
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise _refuse(CAL_FRAME_CONTRACT_CONTRADICTORY, f"{path} is not a frame contract document")
    rate = document.get("frame_rate_hz")
    if not _finite(rate) or float(rate) != FRAME_CONTRACT_HZ:
        raise _refuse(
            CAL_FRAME_CONTRACT_CONTRADICTORY,
            f"{path} declares {rate!r} Hz, not the {FRAME_CONTRACT_HZ} Hz contract phase 7's caps are "
            f"expressed in",
        )
    body = {key: value for key, value in document.items() if key != "sha256"}
    if document.get("sha256") != canonical_sha256(body):
        raise _refuse(
            CAL_FRAME_CONTRACT_CONTRADICTORY,
            f"{path} carries a sha256 that is not the canonical digest of its own body",
        )
    return dict(document)
