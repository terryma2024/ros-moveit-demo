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
) -> tuple[tuple[PhaseSpec, ...], dict[str, str]]:
    evidence_root = config.evidence_root
    python = config.python_executable
    staged_evidence = evidence_root / "staged-approach.json"
    specs = [
        PhaseSpec(
            "staged_approach",
            (
                python,
                "-m",
                "so101_mujoco_demo_py.staged_approach",
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
                    f"so101_mujoco_demo_py.live_phases.{phase}",
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


def _validate_final_release(document: Mapping[str, object]) -> bool:
    evaluation = document.get("final_evaluation")
    evidence = document.get("final_evidence")
    acm = document.get("radial_acm_scope")
    scene = document.get("planning_scene_readback")
    if not all(isinstance(item, dict) for item in (evaluation, evidence, acm, scene)):
        return False
    assert isinstance(evaluation, dict)
    assert isinstance(evidence, dict)
    assert isinstance(acm, dict)
    assert isinstance(scene, dict)
    position = evidence.get("cup_position_world_m")
    primitives = scene.get("world_primitive_counts")
    return bool(
        evaluation.get("success") is True
        and isinstance(position, list)
        and len(position) == 3
        and -0.085 <= float(position[0]) <= -0.075
        and -0.255 <= float(position[1]) <= -0.245
        and evidence.get("table_contact") is True
        and evidence.get("left_contact_count") == 0
        and evidence.get("right_contact_count") == 0
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
) -> str | None:
    if document.get("status") != spec.expected_status:
        return "EVIDENCE_STATUS_MISMATCH"
    if document.get("simulation_session_id") != config.simulation_session_id:
        return "EVIDENCE_PROVENANCE_REJECTED"
    epochs = _reset_epochs(document)
    if epochs and epochs != {config.expected_reset_epoch}:
        return "EVIDENCE_PROVENANCE_REJECTED"
    if spec.name == "release_retreat" and not _validate_final_release(document):
        return "PHYSICAL_FINAL_EVIDENCE_REJECTED"
    return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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
    if not config.motion_policy.is_file():
        raise ValueError(f"motion policy does not exist: {config.motion_policy}")
    config.evidence_root.mkdir(parents=True, exist_ok=True)
    manifest_path = config.evidence_root / "live-runtime-manifest.json"
    specs, environment = build_phase_specs(config)
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
            evidence_failure = _validate_phase_evidence(spec, document, config)
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
