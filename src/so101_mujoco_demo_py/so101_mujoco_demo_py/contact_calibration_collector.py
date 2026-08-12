"""Bounded collection of atomic MuJoCo contact-calibration evidence."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from so101_mujoco_demo_py.contact_calibration import PHYSICAL_REGIMES, REQUIRED_UNITS
from so101_mujoco_demo_py.contact_policy import validate_unilateral_rejection_contracts
from so101_mujoco_demo_py.mujoco.observer import EvidenceStale
from so101_mujoco_demo_py.simulation.types import (
    ContactEvidence,
    ReceivedSimulationEvidence,
    SimulationEvidence,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class CollectionAborted(RuntimeError):
    """Raised when a bounded collection cannot remain valid."""


class CalibrationReadinessPending(RuntimeError):
    """Raised while required ROS state has not published its first value."""


@dataclass(frozen=True, slots=True)
class RobotCalibrationState:
    q6_rad: float
    arm_joint_positions_rad: tuple[float, ...]
    tcp_position_world_m: tuple[float, float, float]
    tcp_orientation_xyzw: tuple[float, float, float, float]

    def __post_init__(self) -> None:
        _finite_values(
            (
                self.q6_rad,
                *self.arm_joint_positions_rad,
                *self.tcp_position_world_m,
                *self.tcp_orientation_xyzw,
            ),
            "robot state",
        )
        if len(self.arm_joint_positions_rad) != 5:
            raise ValueError("arm_joint_positions_rad must contain five joints")
        if len(self.tcp_position_world_m) != 3 or len(self.tcp_orientation_xyzw) != 4:
            raise ValueError("TCP state has invalid dimensions")


@dataclass(frozen=True, slots=True)
class CollectionRequest:
    regime: str
    sample_count: int
    simulation_session_id: str
    reset_epoch: int
    output_path: Path
    source_commit: str
    dependency_commit: str
    model_sha256: str
    scene_sha256: str
    motion_policy_sha256: str
    unilateral_rejection_contracts: dict[str, Any]
    reference_object_position_m: tuple[float, float, float]
    pre_contact: bool = False
    max_receipt_age_s: float = 0.2
    maximum_pre_contact_displacement_m: float = 0.003
    maximum_total_displacement_m: float = 0.010
    maximum_diagnostic_force_n: float = 11.60
    wrong_side_limit: int = 1
    stable_hold_preroll_s: float = 0.30
    table_only: bool = False
    post_release: bool = False

    def __post_init__(self) -> None:
        if self.regime not in PHYSICAL_REGIMES:
            raise ValueError(f"unsupported calibration regime: {self.regime}")
        validate_unilateral_rejection_contracts(self.unilateral_rejection_contracts)
        if self.sample_count <= 0:
            raise ValueError("sample_count must be positive")
        if not self.simulation_session_id:
            raise ValueError("simulation_session_id must be non-empty")
        if self.reset_epoch < 0:
            raise ValueError("reset_epoch must be non-negative")
        if self.wrong_side_limit <= 0:
            raise ValueError("wrong_side_limit must be positive")
        for field, value, length in (
            ("source_commit", self.source_commit, 40),
            ("dependency_commit", self.dependency_commit, 40),
            ("model_sha256", self.model_sha256, 64),
            ("scene_sha256", self.scene_sha256, 64),
            ("motion_policy_sha256", self.motion_policy_sha256, 64),
        ):
            _identifier(value, field, length)
        _finite_values(
            (
                *self.reference_object_position_m,
                self.max_receipt_age_s,
                self.maximum_pre_contact_displacement_m,
                self.maximum_total_displacement_m,
                self.maximum_diagnostic_force_n,
                self.stable_hold_preroll_s,
            ),
            "collection request",
        )
        if len(self.reference_object_position_m) != 3:
            raise ValueError("reference_object_position_m must contain three values")
        if self.max_receipt_age_s <= 0.0:
            raise ValueError("max_receipt_age_s must be positive")
        if self.maximum_pre_contact_displacement_m <= 0.0:
            raise ValueError("maximum_pre_contact_displacement_m must be positive")
        if self.maximum_total_displacement_m <= self.maximum_pre_contact_displacement_m:
            raise ValueError(
                "maximum_total_displacement_m must exceed the independent pre-contact limit"
            )
        if self.stable_hold_preroll_s < 0.0:
            raise ValueError("stable_hold_preroll_s must be non-negative")
        output = self.output_path.resolve()
        if output == REPOSITORY_ROOT or output.is_relative_to(REPOSITORY_ROOT):
            raise ValueError("raw calibration evidence must be written outside the repository")


def _finite_values(values: tuple[float, ...], name: str) -> None:
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        for value in values
    ):
        raise ValueError(f"{name} must contain only finite numeric values")


def _identifier(value: object, name: str, length: int) -> str:
    if not isinstance(value, str) or len(value) != length:
        raise ValueError(f"{name} must be a {length}-character hexadecimal identifier")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"{name} must be hexadecimal") from error
    if set(value) == {"0"}:
        raise ValueError(f"{name} uses a placeholder hash")
    return value


def _contact_document(item: ContactEvidence, side: str) -> dict[str, Any]:
    return {
        "side": side,
        "object_body": item.body1,
        "robot_geom": item.geom2,
        "signed_distance_m": item.signed_distance_m,
        "normal_force_n": item.normal_force_n,
    }


def _atomic_json_write(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(document, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _contact_shape_matches(regime: str, evidence: SimulationEvidence) -> bool:
    left = bool(evidence.left_fingertip_contacts)
    right = bool(evidence.right_fingertip_contacts)
    if regime == "no_contact":
        return not left and not right
    if regime == "left_only":
        return left and not right
    if regime == "right_only":
        return right and not left
    return left and right


class ContactCalibrationCollector:
    def __init__(
        self,
        observer: Any,
        robot_state: Callable[[], RobotCalibrationState],
        *,
        pump: Callable[[], None] = lambda: None,
        monotonic: Callable[[], float] = time.monotonic,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> None:
        self._observer = observer
        self._robot_state = robot_state
        self._pump = pump
        self._monotonic = monotonic
        self._cancelled = cancelled

    def collect(self, request: CollectionRequest) -> dict[str, Any]:
        samples: list[dict[str, Any]] = []
        previous_sequence: int | None = None
        wrong_side_count = 0
        first_contact_time_s: float | None = None
        try:
            while len(samples) < request.sample_count:
                if self._cancelled():
                    raise CollectionAborted("collection cancelled")
                self._pump()
                try:
                    received = self._observer.snapshot_with_receipt()
                except EvidenceStale:
                    continue
                except StopIteration as error:
                    raise CollectionAborted("insufficient fresh samples") from error
                if (
                    previous_sequence is not None
                    and received.evidence.publisher_sequence == previous_sequence
                ):
                    continue
                evidence = self._validated_evidence(request, received, previous_sequence)
                previous_sequence = evidence.publisher_sequence
                if not _contact_shape_matches(request.regime, evidence):
                    first_contact_time_s = None
                    wrong_side_count += 1
                    if wrong_side_count >= request.wrong_side_limit:
                        raise CollectionAborted(
                            f"{request.regime} requires its declared left/right bilateral contact shape"
                        )
                    continue
                wrong_side_count = 0
                if evidence.left_fingertip_contacts or evidence.right_fingertip_contacts:
                    if first_contact_time_s is None:
                        first_contact_time_s = evidence.simulation_time_s
                    contact_duration_s = evidence.simulation_time_s - first_contact_time_s
                else:
                    first_contact_time_s = None
                    contact_duration_s = 0.0
                if (
                    request.regime == "stable_hold"
                    and contact_duration_s < request.stable_hold_preroll_s
                ):
                    continue
                try:
                    sample = self._sample_document(request, evidence, received, contact_duration_s)
                except CalibrationReadinessPending:
                    continue
                samples.append(sample)
            document = self._matrix_document(request, samples)
            _atomic_json_write(request.output_path, document)
            request.output_path.with_suffix(".partial.json").unlink(missing_ok=True)
            return {
                "status": "VALID",
                "regime": request.regime,
                "collected_sample_count": len(samples),
                "output_path": str(request.output_path),
            }
        except CollectionAborted as error:
            partial = {
                "status": "INVALID",
                "regime": request.regime,
                "requested_sample_count": request.sample_count,
                "collected_sample_count": len(samples),
                "reason": str(error),
                "simulation_session_id": request.simulation_session_id,
                "reset_epoch": request.reset_epoch,
            }
            _atomic_json_write(request.output_path.with_suffix(".partial.json"), partial)
            raise

    def _validated_evidence(
        self,
        request: CollectionRequest,
        received: ReceivedSimulationEvidence,
        previous_sequence: int | None,
    ) -> SimulationEvidence:
        evidence = received.evidence
        if evidence.simulation_session_id != request.simulation_session_id:
            raise CollectionAborted("simulation session mismatch")
        if evidence.reset_epoch != request.reset_epoch:
            raise CollectionAborted("reset epoch changed")
        if evidence.truncated:
            raise CollectionAborted("truncated contact arrays")
        age = self._monotonic() - received.received_monotonic_s
        if not math.isfinite(age) or age < 0.0 or age > request.max_receipt_age_s:
            raise CollectionAborted("stale evidence receipt")
        if previous_sequence is not None and evidence.publisher_sequence < previous_sequence:
            raise CollectionAborted("publisher sequence is non-monotonic")
        state = evidence.object_state
        try:
            _finite_values(
                (
                    evidence.simulation_time_s,
                    evidence.minimum_signed_distance_m,
                    evidence.maximum_normal_force_n,
                    *state.position_world,
                    *state.orientation_xyzw,
                    *state.linear_velocity_world,
                    *state.angular_velocity_world,
                ),
                "atomic object state",
            )
        except ValueError as error:
            raise CollectionAborted(str(error)) from error
        if evidence.maximum_normal_force_n > request.maximum_diagnostic_force_n:
            raise CollectionAborted("diagnostic force boundary exceeded")
        displacement = math.dist(state.position_world, request.reference_object_position_m)
        if displacement > request.maximum_total_displacement_m:
            raise CollectionAborted("terminal total object displacement boundary exceeded")
        if request.pre_contact:
            if displacement > request.maximum_pre_contact_displacement_m:
                raise CollectionAborted("pre-contact object displacement boundary exceeded")
        return evidence

    def _sample_document(
        self,
        request: CollectionRequest,
        evidence: SimulationEvidence,
        received: ReceivedSimulationEvidence,
        contact_duration_s: float,
    ) -> dict[str, Any]:
        robot = self._robot_state()
        state = evidence.object_state
        return {
            "regime": request.regime,
            "subcohorts": {
                "table_only": request.table_only,
                "post_release": request.post_release,
            },
            "simulation_session_id": evidence.simulation_session_id,
            "reset_epoch": evidence.reset_epoch,
            "publisher_sequence": evidence.publisher_sequence,
            "simulation_step": evidence.simulation_step,
            "simulation_time_s": evidence.simulation_time_s,
            "receipt_monotonic_s": received.received_monotonic_s,
            "object_pose_world": {
                "position_m": list(state.position_world),
                "orientation_xyzw": list(state.orientation_xyzw),
            },
            "object_twist_world": {
                "linear_m_s": list(state.linear_velocity_world),
                "angular_rad_s": list(state.angular_velocity_world),
            },
            "left_fingertip_contacts": [
                _contact_document(contact, "left") for contact in evidence.left_fingertip_contacts
            ],
            "right_fingertip_contacts": [
                _contact_document(contact, "right") for contact in evidence.right_fingertip_contacts
            ],
            "other_object_contacts": [
                _contact_document(contact, "other") for contact in evidence.other_object_contacts
            ],
            "minimum_signed_distance_m": evidence.minimum_signed_distance_m,
            "maximum_normal_force_n": evidence.maximum_normal_force_n,
            "q6_rad": robot.q6_rad,
            "arm_joint_positions_rad": list(robot.arm_joint_positions_rad),
            "tcp_pose_world": {
                "position_m": list(robot.tcp_position_world_m),
                "orientation_xyzw": list(robot.tcp_orientation_xyzw),
            },
            "contact_duration_s": contact_duration_s,
        }

    def _matrix_document(
        self, request: CollectionRequest, samples: list[dict[str, Any]]
    ) -> dict[str, Any]:
        document: dict[str, Any] | None = None
        if request.output_path.is_file():
            try:
                existing = json.loads(request.output_path.read_text(encoding="utf-8"))
                if isinstance(existing, dict) and existing.get("schema_version") == 3:
                    document = existing
            except (OSError, json.JSONDecodeError):
                document = None
        if document is None:
            document = {
                "schema_version": 3,
                "units": dict(REQUIRED_UNITS),
                "fingerprint": {
                    "source_commit": request.source_commit,
                    "dependency_commit": request.dependency_commit,
                    "model_sha256": request.model_sha256,
                    "scene_sha256": request.scene_sha256,
                    "motion_policy_sha256": request.motion_policy_sha256,
                },
                "simulation_session_id": request.simulation_session_id,
                "reset_epoch": request.reset_epoch,
                "regimes": {regime: [] for regime in PHYSICAL_REGIMES},
                "unilateral_rejection_contracts": validate_unilateral_rejection_contracts(
                    request.unilateral_rejection_contracts
                ),
            }
        fingerprint = document.get("fingerprint")
        if not isinstance(fingerprint, dict):
            raise CollectionAborted("existing matrix fingerprint is missing")
        expected_fingerprint = {
            "source_commit": request.source_commit,
            "dependency_commit": request.dependency_commit,
            "model_sha256": request.model_sha256,
            "scene_sha256": request.scene_sha256,
            "motion_policy_sha256": request.motion_policy_sha256,
        }
        for field, value in expected_fingerprint.items():
            if fingerprint.get(field) != value:
                raise CollectionAborted(f"existing matrix {field} mismatch")
        expected_run = {
            "simulation_session_id": request.simulation_session_id,
            "reset_epoch": request.reset_epoch,
        }
        for field, value in expected_run.items():
            if document.get(field) != value:
                raise CollectionAborted(f"existing matrix {field} mismatch")
        existing_contracts = document.get("unilateral_rejection_contracts")
        if existing_contracts != request.unilateral_rejection_contracts:
            raise CollectionAborted("existing matrix unilateral rejection contracts mismatch")
        regimes = document.get("regimes")
        if not isinstance(regimes, dict) or set(regimes) != set(PHYSICAL_REGIMES):
            raise CollectionAborted("existing matrix regimes are incomplete")
        regimes[request.regime] = samples
        return document


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--regime", required=True, choices=PHYSICAL_REGIMES)
    parser.add_argument("--sample-count", type=int, default=20)
    parser.add_argument("--simulation-session-id", required=True)
    parser.add_argument("--reset-epoch", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--dependency-commit", required=True)
    parser.add_argument("--model-sha256", required=True)
    parser.add_argument("--scene-sha256", required=True)
    parser.add_argument("--motion-policy-sha256", required=True)
    parser.add_argument("--unilateral-contracts", type=Path, required=True)
    parser.add_argument("--reference-object-position-m", nargs=3, type=float, required=True)
    parser.add_argument("--pre-contact", action="store_true")
    parser.add_argument("--table-only", action="store_true")
    parser.add_argument("--post-release", action="store_true")
    parser.add_argument("--max-receipt-age-s", type=float, default=0.2)
    parser.add_argument("--stable-hold-preroll-s", type=float, default=0.30)
    parser.add_argument("--timeout-s", type=float, default=30.0)
    return parser


def run_ros_collection(options: argparse.Namespace) -> dict[str, Any]:
    """Collect one regime from the existing atomic evidence and robot-state streams."""
    import rclpy
    import tf2_ros
    from rclpy.qos import qos_profile_sensor_data
    from rclpy.time import Time
    from sensor_msgs.msg import JointState

    from so101_mujoco_demo_py.mujoco.observer import MujocoWorldObserver

    rclpy.init()
    node = rclpy.create_node("so101_contact_calibration_collector")
    latest_joint_state: JointState | None = None

    def accept_joint_state(message: JointState) -> None:
        nonlocal latest_joint_state
        if len(message.name) == len(message.position):
            latest_joint_state = message

    subscription = node.create_subscription(
        JointState, "/joint_states", accept_joint_state, qos_profile_sensor_data
    )
    del subscription
    observer = MujocoWorldObserver(
        node,
        options.simulation_session_id,
        max_age_s=options.max_receipt_age_s,
    )
    tf_buffer = tf2_ros.Buffer()
    tf_listener = tf2_ros.TransformListener(tf_buffer, node)
    del tf_listener
    deadline = time.monotonic() + options.timeout_s

    def cancelled() -> bool:
        return time.monotonic() >= deadline or not rclpy.ok()

    def pump() -> None:
        rclpy.spin_once(node, timeout_sec=0.05)

    def state() -> RobotCalibrationState:
        message = latest_joint_state
        if message is None:
            raise CalibrationReadinessPending("no joint state is available")
        positions = dict(zip(message.name, message.position, strict=True))
        missing = [name for name in ("1", "2", "3", "4", "5", "6") if name not in positions]
        if missing:
            raise CollectionAborted(f"joint state is missing joints: {missing}")
        try:
            transform = tf_buffer.lookup_transform("world", "so101_tcp", Time())
        except Exception as error:  # tf2 exception classes differ across ROS distributions.
            raise CalibrationReadinessPending(f"TCP transform unavailable: {error}") from error
        translation = transform.transform.translation
        rotation = transform.transform.rotation
        return RobotCalibrationState(
            q6_rad=float(positions["6"]),
            arm_joint_positions_rad=tuple(float(positions[str(index)]) for index in range(1, 6)),
            tcp_position_world_m=(
                float(translation.x),
                float(translation.y),
                float(translation.z),
            ),
            tcp_orientation_xyzw=(
                float(rotation.x),
                float(rotation.y),
                float(rotation.z),
                float(rotation.w),
            ),
        )

    contracts_document = json.loads(options.unilateral_contracts.read_text(encoding="utf-8"))
    if (
        isinstance(contracts_document, dict)
        and "unilateral_rejection_contracts" in contracts_document
    ):
        contracts_document = contracts_document["unilateral_rejection_contracts"]
    contracts = validate_unilateral_rejection_contracts(contracts_document)
    request = CollectionRequest(
        regime=options.regime,
        sample_count=options.sample_count,
        simulation_session_id=options.simulation_session_id,
        reset_epoch=options.reset_epoch,
        output_path=options.output,
        source_commit=options.source_commit,
        dependency_commit=options.dependency_commit,
        model_sha256=options.model_sha256,
        scene_sha256=options.scene_sha256,
        motion_policy_sha256=options.motion_policy_sha256,
        unilateral_rejection_contracts=contracts,
        reference_object_position_m=tuple(options.reference_object_position_m),
        pre_contact=options.pre_contact,
        table_only=options.table_only,
        post_release=options.post_release,
        max_receipt_age_s=options.max_receipt_age_s,
        stable_hold_preroll_s=options.stable_hold_preroll_s,
    )
    try:
        return ContactCalibrationCollector(
            observer,
            state,
            pump=pump,
            cancelled=cancelled,
        ).collect(request)
    finally:
        node.destroy_node()
        rclpy.shutdown()


def main(argv: list[str] | None = None) -> int:
    try:
        result = run_ros_collection(_argument_parser().parse_args(argv))
    except (CollectionAborted, ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0
