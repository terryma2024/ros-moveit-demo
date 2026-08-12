"""Production orchestration for the physically validated MuJoCo pick-place path."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml
from so101_demo.core.contact_policy import ContactPolicyFingerprint
from so101_demo.core.outcome import (
    FinalPlacementSample,
    PhysicalOutcomePolicy,
    evaluate_final_placement,
)
from so101_demo.core.policy import TaskPolicy, load_task_policy

LIVE_PHASES = (
    "staged_approach",
    "contact_hold",
    "micro_lift",
    "policy_lift_waypoint1",
    "remaining_lift",
    "transport",
    "descend",
    "place_alignment",
    "release_retreat",
)

_EXPECTED_STATUS = {
    "staged_approach": "CLOSE_READY",
    "contact_hold": "CONTACT_ONLY_PROVED",
    "micro_lift": "PHYSICAL_MICRO_LIFT_PROVED",
    "policy_lift_waypoint1": "POLICY_LIFT_WAYPOINT1_PHYSICAL_TRANSFER_PROVED",
    "remaining_lift": "REMAINING_FORMAL_LIFT_PROVED",
    "transport": "FORMAL_MOVE_ABOVE_PLACE_PROVED",
    "descend": "FORMAL_DESCEND_TO_PRE_RELEASE_CLEARANCE_PROVED",
    "place_alignment": "PRE_RELEASE_ALIGNMENT_PROVED",
    "release_retreat": "RELEASE_RETREAT_FINAL_PLACEMENT_PROVED",
}


@dataclass(frozen=True, slots=True)
class LiveRuntimeConfig:
    simulation_session_id: str
    expected_reset_epoch: int
    evidence_root: Path
    motion_policy: Path
    contact_policy: Path
    python_executable: str = sys.executable

    def __post_init__(self) -> None:
        if not self.simulation_session_id:
            raise ValueError("simulation session ID must be non-empty")
        if self.expected_reset_epoch < 0:
            raise ValueError("expected reset epoch must be non-negative")
        if not self.python_executable:
            raise ValueError("python executable must be non-empty")


@dataclass(frozen=True, slots=True)
class PhaseSpec:
    name: str
    command: tuple[str, ...]
    evidence_path: Path
    expected_status: str


@dataclass(frozen=True, slots=True)
class LiveRuntimeResult:
    success: bool
    failed_phase: str | None
    failure: str | None
    completed_phases: tuple[str, ...]
    manifest_path: Path


CommandRunner = Callable[[PhaseSpec, Mapping[str, str], Path], int]
Resume = Callable[[LiveRuntimeConfig], bool]


def build_phase_specs(
    config: LiveRuntimeConfig,
    fingerprint: ContactPolicyFingerprint | None = None,
) -> tuple[tuple[PhaseSpec, ...], dict[str, str]]:
    if fingerprint is None:
        fingerprint = _expected_contact_fingerprint(config)
    evidence_root = config.evidence_root
    python = config.python_executable
    staged_evidence = evidence_root / "staged-approach.json"
    specs = [
        PhaseSpec(
            "staged_approach",
            (
                python,
                "-m",
                "so101_demo.application.staged_approach",
                "--policy",
                str(config.motion_policy),
                "--mode",
                "execute",
                "--execute",
                "--stop-after",
                "DESCEND",
                "--simulation-session-id",
                config.simulation_session_id,
                "--evidence-file",
                str(staged_evidence),
            ),
            staged_evidence,
            _EXPECTED_STATUS["staged_approach"],
        )
    ]
    for phase in LIVE_PHASES[1:]:
        file_stem = phase.replace("_", "-")
        specs.append(
            PhaseSpec(
                phase,
                (
                    python,
                    "-m",
                    f"so101_demo.application.phases.{phase}",
                ),
                evidence_root / f"{file_stem}.json",
                _EXPECTED_STATUS[phase],
            )
        )
    environment = dict(os.environ)
    environment.update(
        {
            "SO101_SIMULATION_SESSION_ID": config.simulation_session_id,
            "SO101_EXPECTED_RESET_EPOCH": str(config.expected_reset_epoch),
            "SO101_EVIDENCE_ROOT": str(config.evidence_root),
            "SO101_MOTION_POLICY": str(config.motion_policy),
            "SO101_CONTACT_POLICY": str(config.contact_policy),
            "SO101_DEPENDENCY_COMMIT": fingerprint.dependency_commit,
            "SO101_MODEL_SHA256": fingerprint.model_sha256,
            "SO101_SCENE_SHA256": fingerprint.scene_sha256,
            "SO101_MOTION_POLICY_SHA256": fingerprint.motion_policy_sha256,
            "SO101_SOURCE_EVIDENCE_SHA256": fingerprint.source_evidence_sha256,
        }
    )
    return tuple(specs), environment


def _default_command_runner(
    spec: PhaseSpec,
    environment: Mapping[str, str],
    log_path: Path,
) -> int:
    with log_path.open("w", encoding="utf-8") as output:
        completed = subprocess.run(
            spec.command,
            env=dict(environment),
            stdout=output,
            stderr=subprocess.STDOUT,
            check=False,
        )
    return int(completed.returncode)


def _default_resume(config: LiveRuntimeConfig) -> bool:
    import rclpy
    from mujoco_ros2_control_msgs.srv import SetPause

    rclpy.init()
    node = rclpy.create_node("so101_live_runtime_resume")
    try:
        client = node.create_client(SetPause, "/mujoco_ros2_control_node/set_pause")
        if not client.wait_for_service(timeout_sec=5.0):
            return False
        request = SetPause.Request()
        request.paused = False
        future = client.call_async(request)
        deadline = time.monotonic() + 5.0
        while not future.done() and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.01)
        response = future.result() if future.done() else None
        return bool(response is not None and response.success)
    finally:
        node.destroy_node()
        rclpy.shutdown()


def _reset_epochs(value: object) -> set[int]:
    observed: set[int] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "reset_epoch" and isinstance(item, int) and not isinstance(item, bool):
                observed.add(item)
            else:
                observed.update(_reset_epochs(item))
    elif isinstance(value, list):
        for item in value:
            observed.update(_reset_epochs(item))
    return observed


_FINAL_SAMPLE_KEYS = frozenset(
    {
        "release_epoch_id",
        "receipt_sequence",
        "source_timestamp_s",
        "observed_monotonic_s",
        "pose_xyz_xyzw",
        "support_contact",
        "gripper_contact",
        "gazebo_detached",
        "moveit_detached",
        "controller_healthy",
        "safety_healthy",
        "shadow_divergence_healthy",
    }
)


def _deserialize_final_samples(value: object) -> tuple[FinalPlacementSample, ...] | None:
    if not isinstance(value, list) or not value:
        return None
    converted: list[FinalPlacementSample] = []
    boolean_fields = (
        "support_contact",
        "gripper_contact",
        "gazebo_detached",
        "moveit_detached",
        "controller_healthy",
        "safety_healthy",
        "shadow_divergence_healthy",
    )
    for item in value:
        if not isinstance(item, dict) or set(item) != _FINAL_SAMPLE_KEYS:
            return None
        epoch = item["release_epoch_id"]
        sequence = item["receipt_sequence"]
        source_time = item["source_timestamp_s"]
        observed_time = item["observed_monotonic_s"]
        pose = item["pose_xyz_xyzw"]
        if not isinstance(epoch, str) or not epoch:
            return None
        if isinstance(sequence, bool) or not isinstance(sequence, int):
            return None
        if any(
            isinstance(number, bool) or not isinstance(number, (int, float))
            for number in (source_time, observed_time)
        ):
            return None
        if (
            not isinstance(pose, list)
            or len(pose) != 7
            or any(
                isinstance(number, bool) or not isinstance(number, (int, float)) for number in pose
            )
        ):
            return None
        if any(not isinstance(item[field], bool) for field in boolean_fields):
            return None
        converted.append(
            FinalPlacementSample(
                release_epoch_id=epoch,
                receipt_sequence=sequence,
                source_timestamp_s=float(source_time),
                observed_monotonic_s=float(observed_time),
                pose_xyz_xyzw=tuple(float(number) for number in pose),  # type: ignore[arg-type]
                support_contact=item["support_contact"],
                gripper_contact=item["gripper_contact"],
                gazebo_detached=item["gazebo_detached"],
                moveit_detached=item["moveit_detached"],
                controller_healthy=item["controller_healthy"],
                safety_healthy=item["safety_healthy"],
                shadow_divergence_healthy=item["shadow_divergence_healthy"],
            )
        )
    return tuple(converted)


def _validate_final_release(document: Mapping[str, object], policy: PhysicalOutcomePolicy) -> bool:
    samples = _deserialize_final_samples(document.get("final_samples"))
    release_epoch_id = document.get("release_epoch_id")
    release_marker_sequence = document.get("release_marker_sequence")
    acm = document.get("radial_acm_scope")
    scene = document.get("planning_scene_readback")
    if (
        samples is None
        or not isinstance(release_epoch_id, str)
        or not release_epoch_id
        or isinstance(release_marker_sequence, bool)
        or not isinstance(release_marker_sequence, int)
        or not isinstance(acm, dict)
        or not isinstance(scene, dict)
    ):
        return False
    evaluation = evaluate_final_placement(
        samples,
        policy,
        release_epoch_id,
        release_marker_sequence,
    )
    primitives = scene.get("world_primitive_counts")
    return bool(
        evaluation.success
        and acm.get("moving_jaw_link_allowed") is False
        and acm.get("restored_before_vertical") is True
        and acm.get("restored_pair_allowed") is False
        and scene.get("attached_object_ids") == []
        and primitives == {"table": 1, "pedestal": 1, "plastic_cup": 13}
    )


def _validate_phase_evidence(
    spec: PhaseSpec,
    document: Mapping[str, object],
    config: LiveRuntimeConfig,
    physical_outcome_policy: PhysicalOutcomePolicy,
) -> str | None:
    if document.get("status") != spec.expected_status:
        return "EVIDENCE_STATUS_MISMATCH"
    if document.get("simulation_session_id") != config.simulation_session_id:
        return "EVIDENCE_PROVENANCE_REJECTED"
    epochs = _reset_epochs(document)
    if epochs and epochs != {config.expected_reset_epoch}:
        return "EVIDENCE_PROVENANCE_REJECTED"
    if spec.name == "release_retreat" and not _validate_final_release(
        document, physical_outcome_policy
    ):
        return "PHYSICAL_FINAL_EVIDENCE_REJECTED"
    return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _expected_contact_fingerprint(config: LiveRuntimeConfig) -> ContactPolicyFingerprint:
    package_root = config.motion_policy.resolve().parents[2]
    lock = yaml.safe_load((package_root / "config" / "dependency-lock.yaml").read_bytes())
    contact = yaml.safe_load(config.contact_policy.read_bytes())
    try:
        dependency_commit = lock["fork"]["policy_behavior_commit"]
        source_evidence_sha256 = contact["fingerprint"]["source_evidence_sha256"]
    except (KeyError, TypeError) as error:
        raise ValueError("runtime policy fingerprint inputs are incomplete") from error
    return ContactPolicyFingerprint(
        dependency_commit=str(dependency_commit),
        model_sha256=_sha256(package_root / "mjcf" / "so101.xml"),
        scene_sha256=_sha256(package_root / "mjcf" / "scene.xml"),
        motion_policy_sha256=_sha256(config.motion_policy),
        source_evidence_sha256=str(source_evidence_sha256),
    )


def _preflight_task_policy(config: LiveRuntimeConfig) -> tuple[TaskPolicy | None, str | None]:
    try:
        document = yaml.safe_load(config.contact_policy.read_bytes())
    except (OSError, yaml.YAMLError):
        return None, "POLICY_FINGERPRINT_MISMATCH"
    approval = document.get("approval") if isinstance(document, dict) else None
    if (
        not isinstance(approval, dict)
        or approval.get("enabled") is not True
        or approval.get("approved") is not True
    ):
        return None, "CONTACT_POLICY_NOT_APPROVED"
    try:
        fingerprint = _expected_contact_fingerprint(config)
        task_policy = load_task_policy(
            config.motion_policy,
            config.contact_policy,
            fingerprint,
            require_approved_contact=True,
        )
    except (OSError, TypeError, ValueError, yaml.YAMLError):
        return None, "POLICY_FINGERPRINT_MISMATCH"
    return task_policy, None


def load_live_task_policy(
    environment: Mapping[str, str] = os.environ,
) -> TaskPolicy:
    """Load the immutable approved policy passed to a temporary live phase."""

    required = (
        "SO101_MOTION_POLICY",
        "SO101_CONTACT_POLICY",
        "SO101_DEPENDENCY_COMMIT",
        "SO101_MODEL_SHA256",
        "SO101_SCENE_SHA256",
        "SO101_MOTION_POLICY_SHA256",
        "SO101_SOURCE_EVIDENCE_SHA256",
    )
    missing = tuple(name for name in required if not environment.get(name))
    if missing:
        raise ValueError(f"missing live policy environment: {', '.join(missing)}")
    fingerprint = ContactPolicyFingerprint(
        dependency_commit=environment["SO101_DEPENDENCY_COMMIT"],
        model_sha256=environment["SO101_MODEL_SHA256"],
        scene_sha256=environment["SO101_SCENE_SHA256"],
        motion_policy_sha256=environment["SO101_MOTION_POLICY_SHA256"],
        source_evidence_sha256=environment["SO101_SOURCE_EVIDENCE_SHA256"],
    )
    return load_task_policy(
        Path(environment["SO101_MOTION_POLICY"]),
        Path(environment["SO101_CONTACT_POLICY"]),
        fingerprint,
        require_approved_contact=True,
    )


def _atomic_manifest(path: Path, document: Mapping[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def run_live_workflow(
    config: LiveRuntimeConfig,
    *,
    resume: Resume = _default_resume,
    command_runner: CommandRunner = _default_command_runner,
) -> LiveRuntimeResult:
    config.evidence_root.mkdir(parents=True, exist_ok=True)
    manifest_path = config.evidence_root / "live-runtime-manifest.json"
    task_policy, preflight_failure = _preflight_task_policy(config)
    if preflight_failure is not None or task_policy is None or task_policy.contact is None:
        failure = preflight_failure or "CONTACT_POLICY_NOT_APPROVED"
        _atomic_manifest(
            manifest_path,
            {
                "schema": "so101-mujoco-live-runtime-v1",
                "status": "FAILED",
                "simulation_session_id": config.simulation_session_id,
                "expected_reset_epoch": config.expected_reset_epoch,
                "motion_policy": str(config.motion_policy),
                "contact_policy": str(config.contact_policy),
                "completed_phases": [],
                "failed_phase": "preflight",
                "failure": failure,
                "phase_exit_codes": {},
                "artifact_sha256": {},
            },
        )
        return LiveRuntimeResult(False, "preflight", failure, (), manifest_path)
    specs, environment = build_phase_specs(config, task_policy.contact.fingerprint)
    completed: list[str] = []
    exit_codes: dict[str, int] = {}
    failure: str | None = None
    failed_phase: str | None = None

    if not resume(config):
        failure = "RESUME_FAILED"
        failed_phase = "resume_physics"
    else:
        for spec in specs:
            print(f"LIVE_PHASE {spec.name}", flush=True)
            exit_code = command_runner(
                spec,
                environment,
                config.evidence_root / f"{spec.name}.log",
            )
            exit_codes[spec.name] = exit_code
            if exit_code != 0:
                failure = "PHASE_EXIT_NONZERO"
                failed_phase = spec.name
                break
            if not spec.evidence_path.is_file():
                failure = "EVIDENCE_MISSING"
                failed_phase = spec.name
                break
            try:
                document = json.loads(spec.evidence_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                failure = "EVIDENCE_INVALID"
                failed_phase = spec.name
                break
            if not isinstance(document, dict):
                failure = "EVIDENCE_INVALID"
                failed_phase = spec.name
                break
            evidence_failure = _validate_phase_evidence(
                spec, document, config, task_policy.physical_outcome
            )
            if evidence_failure is not None:
                failure = evidence_failure
                failed_phase = spec.name
                break
            completed.append(spec.name)

    artifacts = {
        spec.evidence_path.name: _sha256(spec.evidence_path)
        for spec in specs
        if spec.evidence_path.is_file()
    }
    manifest = {
        "schema": "so101-mujoco-live-runtime-v1",
        "status": "DONE" if failure is None else "FAILED",
        "simulation_session_id": config.simulation_session_id,
        "expected_reset_epoch": config.expected_reset_epoch,
        "motion_policy": str(config.motion_policy),
        "contact_policy": str(config.contact_policy),
        "motion_policy_sha256": task_policy.fingerprint.motion_policy_sha256,
        "contact_policy_sha256": task_policy.fingerprint.contact_policy_sha256,
        "completed_phases": completed,
        "failed_phase": failed_phase,
        "failure": failure,
        "phase_exit_codes": exit_codes,
        "artifact_sha256": artifacts,
    }
    _atomic_manifest(manifest_path, manifest)
    return LiveRuntimeResult(
        success=failure is None,
        failed_phase=failed_phase,
        failure=failure,
        completed_phases=tuple(completed),
        manifest_path=manifest_path,
    )
