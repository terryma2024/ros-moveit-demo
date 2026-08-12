"""Build a deterministic read-only baseline from FULL_RESTART evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

SCHEMA = "so101-full-restart-baseline-v1"
PHASE_FILES = (
    "staged-approach",
    "contact-hold",
    "micro-lift",
    "policy-lift-waypoint1",
    "remaining-lift",
    "transport",
    "descend",
    "place-alignment",
    "release-retreat",
)
RAW_METRICS = (
    "maximum_normal_force_n",
    "fingertip_max_single_contact_force_n",
    "global_max_single_contact_force_n",
    "left_fingertip_total_normal_force_n",
    "right_fingertip_total_normal_force_n",
    "left_fingertip_compression_m",
    "right_fingertip_compression_m",
    "linear_speed_m_s",
    "angular_speed_rad_s",
    "object_x_m",
    "object_y_m",
    "object_z_m",
)
FINGERPRINT_FIELDS = {
    "source_commit": 40,
    "motion_policy_sha256": 64,
    "contact_policy_sha256": 64,
    "dependency_sha256": 64,
    "robot_mjcf_sha256": 64,
    "scene_sha256": 64,
    "task_scene_sha256": 64,
    "urdf_sha256": 64,
}


class BaselineEvidenceInvalid(ValueError):
    """Raised when stored evidence cannot support the baseline."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_mapping(path: Path, name: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BaselineEvidenceInvalid(f"{name} is not readable JSON: {path}") from error
    if not isinstance(value, dict):
        raise BaselineEvidenceInvalid(f"{name} must be a JSON object: {path}")
    return value


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BaselineEvidenceInvalid(f"{name} must be a mapping")
    return value


def _list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise BaselineEvidenceInvalid(f"{name} must be a list")
    return value


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BaselineEvidenceInvalid(f"{name} must be finite")
    result = float(value)
    if not math.isfinite(result):
        raise BaselineEvidenceInvalid(f"{name} must be finite")
    return result


def _non_negative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BaselineEvidenceInvalid(f"{name} must be a non-negative integer")
    return value


def _quantile(values: list[float], fraction: float) -> float:
    if not values:
        raise BaselineEvidenceInvalid("statistics require at least one sample")
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _statistics(values: list[float]) -> dict[str, float]:
    if any(not math.isfinite(value) for value in values):
        raise BaselineEvidenceInvalid("statistics contain a non-finite value")
    return {
        "min": min(values),
        "p50": _quantile(values, 0.50),
        "p95": _quantile(values, 0.95),
        "p99": _quantile(values, 0.99),
        "max": max(values),
    }


def _vector(value: Any, name: str, size: int) -> tuple[float, ...]:
    items = _list(value, name)
    if len(items) != size:
        raise BaselineEvidenceInvalid(f"{name} must contain {size} values")
    return tuple(_finite(item, name) for item in items)


def _magnitude(values: tuple[float, ...]) -> float:
    return math.sqrt(sum(value * value for value in values))


def _named_numbers(value: Any, key: str) -> Iterable[float]:
    if isinstance(value, dict):
        for name, item in value.items():
            if name == key:
                yield _finite(item, key)
            yield from _named_numbers(item, key)
    elif isinstance(value, list):
        for item in value:
            yield from _named_numbers(item, key)


def _evidence_path(value: Any, name: str) -> Path:
    if not isinstance(value, str) or not value:
        raise BaselineEvidenceInvalid(f"{name} must be an absolute path")
    path = Path(value)
    if not path.is_absolute():
        raise BaselineEvidenceInvalid(f"{name} must be an absolute path")
    return path


def _require_within(path: Path, root: Path, name: str) -> Path:
    resolved = path.resolve()
    if resolved != root and root not in resolved.parents:
        raise BaselineEvidenceInvalid(f"{name} escapes the experiment evidence root")
    return resolved


def _require_digest(path: Path, expected: Any, name: str) -> str:
    if not isinstance(expected, str) or len(expected) != 64:
        raise BaselineEvidenceInvalid(f"{name} sha256 is missing")
    actual = _sha256(path)
    if actual != expected:
        raise BaselineEvidenceInvalid(f"{name} sha256 mismatch")
    return actual


def _validate_phase_artifacts(
    workflow_root: Path,
    manifest: Mapping[str, Any],
) -> tuple[dict[str, float], float]:
    artifact_hashes = _mapping(manifest.get("artifact_sha256"), "manifest artifact_sha256")
    phase_maxima: dict[str, float] = {}
    final_static_force: float | None = None
    for phase in PHASE_FILES:
        filename = f"{phase}.json"
        phase_path = workflow_root / filename
        _require_digest(phase_path, artifact_hashes.get(filename), filename)
        document = _load_mapping(phase_path, filename)
        force_values = list(_named_numbers(document, "maximum_normal_force_n"))
        if not force_values:
            raise BaselineEvidenceInvalid(f"{filename} contains no force evidence")
        phase_maxima[phase.replace("-", "_")] = max(force_values)
        if phase == "release-retreat":
            final_evidence = _mapping(document.get("final_evidence"), "final_evidence")
            final_static_force = _finite(
                final_evidence.get("maximum_normal_force_n"),
                "final_evidence.maximum_normal_force_n",
            )
    if final_static_force is None:
        raise BaselineEvidenceInvalid("release-retreat final static force is missing")
    return phase_maxima, final_static_force


def _validate_raw_transport(
    result: Mapping[str, Any],
    session_id: str,
    reset_epoch: int,
    experiment_root: Path,
) -> tuple[dict[str, Any], dict[str, list[float]]]:
    declared = _mapping(result.get("transport_raw_evidence"), "transport_raw_evidence")
    if declared.get("lossless") is not True:
        raise BaselineEvidenceInvalid("transport evidence is not declared lossless")
    timestep = _finite(declared.get("physics_timestep_s"), "physics_timestep_s")
    if timestep <= 0.0:
        raise BaselineEvidenceInvalid("physics_timestep_s must be positive")
    index_path = _require_within(
        _evidence_path(declared.get("run_index"), "run_index"),
        experiment_root,
        "run_index",
    )
    index_sha = _require_digest(index_path, declared.get("run_index_sha256"), "run-index")
    index = _load_mapping(index_path, "run-index")
    for key in (
        "run_id",
        "expected_session_id",
        "first_snapshot_session_id",
        "first_chunk_session_id",
    ):
        if index.get(key) != session_id:
            raise BaselineEvidenceInvalid(f"run-index {key} does not match the session")
    if (
        index.get("schema") != "so101-dynamic-transport-raw-v4"
        or index.get("status") != "COMPLETE"
        or index.get("outcome_class") != "PHYSICAL_TRANSPORT_SUCCESS"
        or not isinstance(index.get("physical_transport_outcome"), str)
    ):
        raise BaselineEvidenceInvalid("run-index terminal contract is incomplete")

    chunks = _list(index.get("chunks"), "run-index chunks")
    if not chunks:
        raise BaselineEvidenceInvalid("run-index contains no chunks")
    metric_values = {name: [] for name in RAW_METRICS}
    first_step: int | None = None
    last_step: int | None = None
    previous_chunk_sequence: int | None = None
    previous_time: float | None = None
    sample_count = 0
    raw_root = index_path.parent.resolve()
    for chunk_entry_value in chunks:
        entry = _mapping(chunk_entry_value, "chunk entry")
        sequence = _non_negative_int(entry.get("chunk_sequence"), "chunk_sequence")
        if previous_chunk_sequence is not None and sequence != previous_chunk_sequence + 1:
            raise BaselineEvidenceInvalid("chunk sequence is not contiguous")
        previous_chunk_sequence = sequence
        relative = entry.get("path")
        if not isinstance(relative, str) or not relative:
            raise BaselineEvidenceInvalid("chunk path is missing")
        chunk_path = (raw_root / relative).resolve()
        if raw_root not in chunk_path.parents:
            raise BaselineEvidenceInvalid("chunk path escapes the run evidence root")
        chunk_digest = _require_digest(chunk_path, entry.get("sha256"), "chunk")
        if not chunk_path.name.endswith(f"-{chunk_digest}.json"):
            raise BaselineEvidenceInvalid("chunk filename is not content addressed")
        chunk = _load_mapping(chunk_path, "chunk")
        if (
            chunk.get("chunk_sequence") != sequence
            or chunk.get("simulation_session_id") != session_id
            or chunk.get("reset_epoch") != reset_epoch
            or chunk.get("evidence_loss") is not False
            or chunk.get("failed_publish_attempts") != 0
        ):
            raise BaselineEvidenceInvalid("chunk identity or loss contract failed")
        samples = _list(chunk.get("samples"), "chunk samples")
        if not samples:
            raise BaselineEvidenceInvalid("chunk contains no samples")
        chunk_first: int | None = None
        chunk_last: int | None = None
        for sample_value in samples:
            sample = _mapping(sample_value, "physics sample")
            step = _non_negative_int(sample.get("physics_step"), "physics_step")
            simulation_time = _finite(sample.get("simulation_time_s"), "simulation_time_s")
            if (
                sample.get("simulation_session_id") != session_id
                or sample.get("reset_epoch") != reset_epoch
                or sample.get("truncated") is not False
            ):
                raise BaselineEvidenceInvalid("physics sample identity contract failed")
            if last_step is not None and step != last_step + 1:
                raise BaselineEvidenceInvalid("physics steps are not contiguous")
            if previous_time is not None and not math.isclose(
                simulation_time, previous_time + timestep, rel_tol=0.0, abs_tol=1e-11
            ):
                raise BaselineEvidenceInvalid("physics sample time is not contiguous")
            if first_step is None:
                first_step = step
            chunk_first = step if chunk_first is None else chunk_first
            chunk_last = step
            last_step = step
            previous_time = simulation_time
            sample_count += 1
            for metric in RAW_METRICS[:7]:
                value = _finite(sample.get(metric), metric)
                if value < 0.0:
                    raise BaselineEvidenceInvalid(f"{metric} must be non-negative")
                metric_values[metric].append(value)
            if not math.isclose(
                metric_values["maximum_normal_force_n"][-1],
                metric_values["global_max_single_contact_force_n"][-1],
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise BaselineEvidenceInvalid("maximum force does not preserve global semantics")
            twist = _vector(
                sample.get("object_twist_world_linear_angular"),
                "object_twist_world_linear_angular",
                6,
            )
            pose = _vector(sample.get("object_pose_world_xyz_xyzw"), "object_pose", 7)
            metric_values["linear_speed_m_s"].append(_magnitude(twist[:3]))
            metric_values["angular_speed_rad_s"].append(_magnitude(twist[3:]))
            metric_values["object_x_m"].append(pose[0])
            metric_values["object_y_m"].append(pose[1])
            metric_values["object_z_m"].append(pose[2])
        if (
            entry.get("first_physics_step") != chunk_first
            or entry.get("last_physics_step") != chunk_last
            or chunk.get("first_physics_step") != chunk_first
            or chunk.get("last_physics_step") != chunk_last
        ):
            raise BaselineEvidenceInvalid("chunk range does not match its samples")

    if (
        declared.get("chunk_count") != len(chunks)
        or declared.get("sample_count") != sample_count
        or declared.get("first_physics_step") != first_step
        or declared.get("last_physics_step") != last_step
    ):
        raise BaselineEvidenceInvalid("result transport counts do not match raw evidence")
    return (
        {
            "run_index_sha256": index_sha,
            "chunk_count": len(chunks),
            "sample_count": sample_count,
            "first_physics_step": first_step,
            "last_physics_step": last_step,
            "physics_timestep_s": timestep,
            "lossless": True,
        },
        metric_values,
    )


def _validate_transport_summary(
    workflow_root: Path,
    session_id: str,
    raw_metrics: Mapping[str, list[float]],
) -> dict[str, Any]:
    path = workflow_root / "transport-dynamic-summary.json"
    summary = _load_mapping(path, "transport-dynamic-summary")
    if (
        summary.get("run_id") != session_id
        or summary.get("acceptance_role") != "diagnostic_only"
        or summary.get("independent_experiment_units") != 1
    ):
        raise BaselineEvidenceInvalid("transport summary identity contract failed")
    peak = _finite(
        summary.get("peak_global_max_single_contact_force_n"),
        "peak_global_max_single_contact_force_n",
    )
    if not math.isclose(
        peak,
        max(raw_metrics["global_max_single_contact_force_n"]),
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise BaselineEvidenceInvalid("transport summary peak does not replay from raw samples")
    return {
        "sha256": _sha256(path),
        "peak_global_max_single_contact_force_n": peak,
        "force_time_exposure_n_s": _finite(
            summary.get("force_time_exposure_n_s"), "force_time_exposure_n_s"
        ),
        "shadow_excess_force_time_exposure_n_s": _finite(
            summary.get("shadow_excess_force_time_exposure_n_s"),
            "shadow_excess_force_time_exposure_n_s",
        ),
        "maximum_left_fingertip_compression_m": _finite(
            summary.get("maximum_left_fingertip_compression_m"),
            "maximum_left_fingertip_compression_m",
        ),
        "maximum_right_fingertip_compression_m": _finite(
            summary.get("maximum_right_fingertip_compression_m"),
            "maximum_right_fingertip_compression_m",
        ),
    }


def _validate_experiment(
    evidence_root: Path,
    experiment_id: str,
    visual_waivers: set[str],
) -> tuple[dict[str, Any], dict[str, list[float]], dict[str, str]]:
    suffix = experiment_id.removeprefix("EXP-")
    if not suffix.isdigit() or not experiment_id.startswith("EXP-"):
        raise BaselineEvidenceInvalid(f"invalid experiment id: {experiment_id}")
    result_path = evidence_root / f"exp{suffix}" / f"exp-{suffix}-result.json"
    experiment_root = result_path.parent.resolve()
    result = _load_mapping(result_path, f"{experiment_id} result")
    if (
        result.get("experiment_id") != f"{experiment_id}-01"
        or result.get("lifecycle") != "FULL_RESTART"
        or result.get("status") != "SUCCESS"
    ):
        raise BaselineEvidenceInvalid(f"{experiment_id} is not a successful FULL_RESTART")
    if _mapping(result.get("clean_shutdown"), "clean_shutdown").get("passed") is not True:
        raise BaselineEvidenceInvalid(f"{experiment_id} did not shut down cleanly")
    controller = _mapping(result.get("moveit_controller_result"), "moveit_controller_result")
    if controller.get("workflow_succeeded") is not True:
        raise BaselineEvidenceInvalid(f"{experiment_id} controller workflow did not succeed")
    visual_passed = _mapping(result.get("cua_visual"), "cua_visual").get("passed") is True
    visual_waived = experiment_id in visual_waivers
    if not visual_passed and not visual_waived:
        raise BaselineEvidenceInvalid(
            f"{experiment_id} visual evidence requires an explicit waiver"
        )
    session_id = result.get("simulation_session_id")
    if not isinstance(session_id, str) or not session_id:
        raise BaselineEvidenceInvalid(f"{experiment_id} session identity is missing")
    reset_epoch = _non_negative_int(result.get("reset_epoch"), "reset_epoch")

    owner_validation = _mapping(
        result.get("owner_evidence_validation"), "owner_evidence_validation"
    )
    counters = _mapping(
        owner_validation.get("forbidden_intervention_counters"),
        "forbidden_intervention_counters",
    )
    if counters != {
        "direct_object_state_writes": 0,
        "physics_pause_calls": 0,
        "simulator_constraint_calls": 0,
    }:
        raise BaselineEvidenceInvalid(f"{experiment_id} used a forbidden intervention")
    manifest_path = _require_within(
        _evidence_path(result.get("owner_evidence_manifest"), "owner manifest"),
        experiment_root,
        "owner manifest",
    )
    manifest_sha = _require_digest(
        manifest_path, owner_validation.get("manifest_sha256"), "owner manifest"
    )
    manifest = _load_mapping(manifest_path, "owner manifest")
    expected_phases = [phase.replace("-", "_") for phase in PHASE_FILES]
    if (
        manifest.get("schema") != "so101-mujoco-live-runtime-v1"
        or manifest.get("simulation_session_id") != session_id
        or manifest.get("expected_reset_epoch") != reset_epoch
        or manifest.get("status") != "DONE"
        or manifest.get("failure") is not None
        or manifest.get("failed_phase") is not None
        or manifest.get("completed_phases") != expected_phases
        or controller.get("completed_phases") != expected_phases
        or any(
            _mapping(manifest.get("phase_exit_codes"), "phase_exit_codes").get(phase) != 0
            for phase in expected_phases
        )
    ):
        raise BaselineEvidenceInvalid(f"{experiment_id} owner manifest is incomplete")
    workflow_root = manifest_path.parent
    phase_maxima, final_static_force = _validate_phase_artifacts(workflow_root, manifest)
    raw_summary, raw_metrics = _validate_raw_transport(
        result, session_id, reset_epoch, experiment_root
    )
    transport_summary = _validate_transport_summary(workflow_root, session_id, raw_metrics)

    physical = _mapping(result.get("physical_outcome"), "physical_outcome")
    if (
        physical.get("primary_failure") is not None
        or physical.get("intended_support_contact") is not True
        or physical.get("gripper_contact") is not False
        or physical.get("moveit_attached") is not False
        or physical.get("world_object_synchronized") is not True
    ):
        raise BaselineEvidenceInvalid(f"{experiment_id} final physical outcome failed")
    pose = _mapping(physical.get("final_pose"), "final_pose")
    physical_metrics = _mapping(physical.get("metrics"), "physical metrics")
    fingerprint = _mapping(result.get("fingerprint"), "runtime fingerprint")
    if set(fingerprint) != set(FINGERPRINT_FIELDS) or any(
        not isinstance(fingerprint[field], str)
        or len(fingerprint[field]) != length
        or any(character not in "0123456789abcdef" for character in fingerprint[field])
        for field, length in FINGERPRINT_FIELDS.items()
    ):
        raise BaselineEvidenceInvalid(f"{experiment_id} runtime fingerprint is incomplete")
    if (
        manifest.get("motion_policy_sha256") != fingerprint["motion_policy_sha256"]
        or manifest.get("contact_policy_sha256") != fingerprint["contact_policy_sha256"]
        or _mapping(result.get("artifact_sha256"), "artifact_sha256").get("owner_evidence_manifest")
        != manifest_sha
    ):
        raise BaselineEvidenceInvalid(f"{experiment_id} policy or manifest provenance mismatch")
    per_experiment = {
        "experiment_id": experiment_id,
        "simulation_session_id": session_id,
        "reset_epoch": reset_epoch,
        "visual_evidence": "USER_WAIVER" if visual_waived else "VERIFIED",
        "result_sha256": _sha256(result_path),
        "owner_manifest_sha256": manifest_sha,
        "phase_maximum_normal_force_n": phase_maxima,
        "released_static_final_maximum_normal_force_n": final_static_force,
        "raw_transport": raw_summary,
        "dynamic_transport_summary": transport_summary,
        "final_outcome": {
            "final_x_m": _finite(pose.get("x_m"), "final_x_m"),
            "final_y_m": _finite(pose.get("y_m"), "final_y_m"),
            "final_z_m": _finite(pose.get("z_m"), "final_z_m"),
            "final_upright_tilt_rad": _finite(
                physical_metrics.get("final_upright_tilt_rad"), "final_upright_tilt_rad"
            ),
            "maximum_linear_speed_m_s": _finite(
                physical_metrics.get("maximum_linear_speed_m_s"),
                "maximum_linear_speed_m_s",
            ),
            "maximum_angular_speed_rad_s": _finite(
                physical_metrics.get("maximum_angular_speed_rad_s"),
                "maximum_angular_speed_rad_s",
            ),
        },
        "clean_shutdown": True,
        "forbidden_intervention_counters": counters,
    }
    return per_experiment, raw_metrics, dict(fingerprint)


def build_full_restart_baseline(
    evidence_root: Path,
    experiment_ids: tuple[str, ...],
    *,
    visual_waivers: set[str] | None = None,
) -> dict[str, Any]:
    """Validate stored evidence and return a deterministic diagnostic baseline."""
    if len(experiment_ids) != 5 or len(set(experiment_ids)) != 5:
        raise BaselineEvidenceInvalid("baseline requires five unique experiments")
    waivers = set() if visual_waivers is None else set(visual_waivers)
    if not waivers.issubset(experiment_ids):
        raise BaselineEvidenceInvalid("visual waiver names an experiment outside the batch")
    experiments: list[dict[str, Any]] = []
    all_raw_metrics = {name: [] for name in RAW_METRICS}
    fingerprint: dict[str, str] | None = None
    for experiment_id in experiment_ids:
        experiment, raw_metrics, current_fingerprint = _validate_experiment(
            evidence_root.resolve(), experiment_id, waivers
        )
        if fingerprint is None:
            fingerprint = current_fingerprint
        elif current_fingerprint != fingerprint:
            raise BaselineEvidenceInvalid("runtime fingerprint differs across experiments")
        experiments.append(experiment)
        for name, values in raw_metrics.items():
            all_raw_metrics[name].extend(values)
    if fingerprint is None:
        raise BaselineEvidenceInvalid("runtime fingerprint is missing")

    phase_statistics = {
        phase.replace("-", "_"): _statistics(
            [
                experiment["phase_maximum_normal_force_n"][phase.replace("-", "_")]
                for experiment in experiments
            ]
        )
        for phase in PHASE_FILES
    }
    phase_statistics["released_static_final"] = _statistics(
        [experiment["released_static_final_maximum_normal_force_n"] for experiment in experiments]
    )
    final_fields = (
        "final_x_m",
        "final_y_m",
        "final_z_m",
        "final_upright_tilt_rad",
        "maximum_linear_speed_m_s",
        "maximum_angular_speed_rad_s",
    )
    summary_fields = (
        "peak_global_max_single_contact_force_n",
        "force_time_exposure_n_s",
        "shadow_excess_force_time_exposure_n_s",
        "maximum_left_fingertip_compression_m",
        "maximum_right_fingertip_compression_m",
    )
    first_number = experiment_ids[0].removeprefix("EXP-")
    last_number = experiment_ids[-1].removeprefix("EXP-")
    return {
        "schema": SCHEMA,
        "batch_id": f"MNT-Q-EXP{first_number}-{last_number}",
        "lifecycle": "FULL_RESTART",
        "independent_experiment_units": len(experiments),
        "source_evidence_root": str(evidence_root.resolve()),
        "runtime_fingerprint": fingerprint,
        "visual_waivers": sorted(waivers),
        "policy_effect": "NONE_READ_ONLY_BASELINE",
        "threshold_derivation": "NONE_DIAGNOSTIC_COMPARISON_ONLY",
        "experiments": experiments,
        "phase_maximum_normal_force_n": phase_statistics,
        "dynamic_transport_run_statistics": {
            field: _statistics(
                [experiment["dynamic_transport_summary"][field] for experiment in experiments]
            )
            for field in summary_fields
        },
        "raw_transport": {
            "sample_role": "repeated_measure_diagnostic",
            "sample_count": sum(
                experiment["raw_transport"]["sample_count"] for experiment in experiments
            ),
            "all_runs_lossless": all(
                experiment["raw_transport"]["lossless"] for experiment in experiments
            ),
            "metrics": {name: _statistics(values) for name, values in all_raw_metrics.items()},
        },
        "final_outcome": {
            field: _statistics([experiment["final_outcome"][field] for experiment in experiments])
            for field in final_fields
        },
    }


def _pretty_json(document: Mapping[str, Any]) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_baseline_artifacts(
    document: Mapping[str, Any],
    output_path: Path,
    sha256_path: Path,
) -> str:
    """Atomically write pretty JSON and its exact file digest."""
    content = _pretty_json(document)
    digest = hashlib.sha256(content).hexdigest()
    _atomic_write(output_path, content)
    _atomic_write(sha256_path, f"{digest}  {output_path.name}\n".encode())
    return digest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--experiment", action="append", required=True)
    parser.add_argument("--visual-waiver", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sha256-output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    document = build_full_restart_baseline(
        args.evidence_root,
        tuple(args.experiment),
        visual_waivers=set(args.visual_waiver),
    )
    digest = write_baseline_artifacts(document, args.output, args.sha256_output)
    print(
        "FULL_RESTART_BASELINE_OK "
        f"runs={document['independent_experiment_units']} "
        f"samples={document['raw_transport']['sample_count']} sha256={digest}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
